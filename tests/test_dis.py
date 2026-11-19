"""DIS tests use simulated readers and real temporary SQLite; no actuation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import ipaddress
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest import mock

from butler.dis import client, service
from butler.dis.adapters import KasaReader, ReadFailure
from butler.dis.models import Device, Reading
from butler.dis.store import DeviceStore
from butler.memory import MemoryStore


DEVICES = (Device('desk-lamp', 'Desk lamp', '10.0.0.1', 'light'),
           Device('coffee', 'Coffee plug', '10.0.0.2', 'appliance'))


class Reader:
    def __init__(self):
        self.power = False
        self.failure = None
        self.calls = 0

    def read(self, device):
        self.calls += 1
        if self.failure:
            raise ReadFailure(self.failure)
        return Reading(self.power, time.time())


class DISStoreAndServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'butler.sqlite3'

    def make_service(self, devices=DEVICES, reader=None, started=False, settings=service.Settings()):
        store = DeviceStore(self.path)
        svc = service.DeviceInformationService(devices, store, reader or Reader(), settings)
        self.addCleanup(svc.stop)
        if started:
            svc.start()
        else:
            store.register(devices)
            svc._records = store.load(devices)
            svc._error = None
        return svc

    def test_actual_read_then_failure_preserves_power_and_evidence_as_stale(self):
        svc = self.make_service()
        svc._accept('desk-lamp', time.monotonic(), Reading(True, time.time()), None)
        before = svc.read('desk-lamp')['devices'][0]
        self.assertEqual(before['properties']['power']['status'], 'current')
        self.assertEqual(before['health']['status'], 'reachable')
        svc._accept('desk-lamp', time.monotonic(), None, 'timeout')
        after = svc.read('desk-lamp')['devices'][0]
        self.assertIsNone(after['properties']['power']['value'])
        self.assertTrue(after['properties']['power']['last_observed_value'])
        self.assertEqual(after['properties']['power']['status'], 'stale')
        self.assertEqual(after['health']['status'], 'unreachable')
        self.assertEqual(after['properties']['power']['evidence_id'], before['properties']['power']['evidence_id'])
        self.assertNotIn('10.0.0.', json.dumps(svc.read()))

    def test_restart_never_treats_saved_readings_as_live_contact(self):
        svc = self.make_service()
        svc._accept('desk-lamp', time.monotonic(), Reading(True, time.time()), None)
        reloaded = self.make_service()
        view = reloaded.read('desk-lamp')['devices'][0]
        self.assertEqual(view['health']['status'], 'unknown')
        self.assertEqual(view['properties']['power']['status'], 'stale')

    def test_expiry_is_calculated_on_read_without_network_or_sqlite(self):
        svc = self.make_service()
        received = time.time()
        svc._accept('desk-lamp', time.monotonic(), Reading(True, received), None)
        with mock.patch.object(svc.store, 'load', side_effect=AssertionError('DB on turn path')), \
             mock.patch.object(svc.reader, 'read', side_effect=AssertionError('network on turn path')), \
             mock.patch('butler.dis.service.time.time', return_value=received + 21):
            result = svc.read('desk-lamp')['devices'][0]
            text = svc.summary()
        self.assertEqual(result['properties']['power']['status'], 'stale')
        self.assertIn('stale', text)

    def test_remapping_endpoint_discards_old_device_observations(self):
        svc = self.make_service()
        svc._accept('desk-lamp', time.monotonic(), Reading(True, time.time()), None)
        changed = (replace(DEVICES[0], host='10.0.0.99'),)
        reloaded = self.make_service(devices=changed)
        self.assertIsNone(reloaded.read()['devices'][0]['properties']['power']['value'])
        self.assertEqual(len(reloaded.read()['devices']), 1)

    def test_old_read_cannot_replace_newer_state(self):
        svc = self.make_service()
        now = time.time()
        svc.store.record('desk-lamp', now, Reading(True, now), None)
        svc.store.record('desk-lamp', now - 1, Reading(False, now - 1), None)
        self.assertTrue(svc.store.load(DEVICES)[0].reading.power)
        with self.assertRaises(ValueError):
            svc.store.record('missing', now, Reading(True, now), None)
        with self.assertRaises(ValueError):
            Reading('on', now)

    def test_storage_failure_exposes_unavailability_and_recovery(self):
        svc = self.make_service()
        with mock.patch.object(svc.store, 'record', side_effect=OSError('private failure')):
            svc._accept('desk-lamp', time.monotonic(), Reading(True, time.time()), None)
        self.assertEqual(svc.read()['error']['code'], 'storage_unavailable')
        self.assertNotIn('private failure', svc.summary())
        svc._accept('desk-lamp', time.monotonic(), Reading(False, time.time()), None)
        self.assertTrue(svc.read()['ok'])

    def test_all_lights_control_invalidates_only_lights_without_waiting(self):
        svc = self.make_service()
        for device in DEVICES:
            svc._accept(device.device_id, time.monotonic(), Reading(True, time.time()), None)
        with mock.patch.object(service, '_service', svc):
            self.assertFalse(service.after_control('all'))
        lamp, coffee = svc.read()['devices']
        self.assertTrue(lamp['refresh_pending'])
        self.assertIsNone(lamp['properties']['power']['value'])
        self.assertFalse(coffee['refresh_pending'])
        self.assertTrue(coffee['properties']['power']['value'])

    def test_unknown_pagination_and_summary_omissions_are_explicit(self):
        svc = self.make_service()
        self.assertEqual(svc.read('missing')['status'], 'not_found')
        first = svc.read(limit=1)
        self.assertEqual(first['coverage']['next_offset'], 1)
        self.assertEqual(first['coverage']['omitted_count'], 1)
        self.assertEqual(svc.read(offset=1, limit=1)['devices'][0]['device_id'], 'coffee')
        devices = tuple(Device(f'device-{i}', 'x' * 100, 'host', 'light') for i in range(12))
        bounded = self.make_service(devices=devices, settings=replace(service.Settings(), summary_chars=512))
        text = bounded.summary()
        self.assertLessEqual(len(text), 512)
        self.assertIn('omitted', text)
        self.assertNotIn('shown 12/12', text)

    def test_command_refresh_reads_actual_power_without_waiting_poll_interval(self):
        reader = Reader()
        svc = self.make_service(reader=reader, started=True,
                                settings=replace(service.Settings(), poll_seconds=60, stale_seconds=120))
        self.assertTrue(svc.refresh(['desk-lamp']))
        self.assertFalse(svc.read('desk-lamp')['devices'][0]['properties']['power']['value'])
        reader.power = True
        self.assertTrue(svc.refresh(['desk-lamp']))
        self.assertTrue(svc.read('desk-lamp')['devices'][0]['properties']['power']['value'])
        reader.failure = 'timeout'
        self.assertTrue(svc.refresh(['desk-lamp']))
        self.assertEqual(svc.read('desk-lamp')['devices'][0]['properties']['power']['status'], 'stale')

    def test_streamed_command_refresh_never_waits_or_fabricates_history(self):
        from contextlib import ExitStack
        from test_run_command_stream import _FakeBackend
        from butler.agent import runtime
        from butler.voice.backends.base import LLMCompletion, LLMTextDelta, LLMToolCall
        entered, release = threading.Event(), threading.Event()

        class CommandReader(Reader):
            block = False

            def read(self, device):
                if self.block:
                    entered.set()
                    if not release.wait(3):
                        raise ReadFailure('timeout')
                return super().read(device)

        reader = CommandReader()
        svc = self.make_service(devices=DEVICES[:1], reader=reader, started=True)
        self.assertTrue(svc.refresh(['desk-lamp']))
        memory = MemoryStore(':memory:')
        self.addCleanup(memory.close)
        backend = _FakeBackend([
            [LLMCompletion(text='', tool_calls=(LLMToolCall(call_id='set-1', name='set_smart_plug',
                arguments='{"device_id":"desk-lamp","state":"on"}'),))],
            [LLMTextDelta('Command sent.'), LLMCompletion(text='Command sent.')],
        ])

        class MCP:
            def openai_tool_definitions(self):
                return [{'type': 'function', 'name': 'set_smart_plug',
                         'parameters': {'type': 'object', 'properties': {}}}]

            def call_tool(self, name, arguments):
                reader.power = True
                reader.block = True
                return 'Command accepted'

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(service, '_service', svc))
            for name, value in (('get_local_mcp_client', MCP()), ('_get_memory_store', memory),
                                ('_get_stream_backend', backend), ('_resource_tool_definitions', [])):
                stack.enter_context(mock.patch.object(runtime, name, return_value=value))
            stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_DIS_SUMMARY_ENABLED': '1'}))
            with ThreadPoolExecutor(max_workers=1) as pool:
                done = pool.submit(lambda: list(runtime.run_command_stream('Turn on the desk lamp', session_id='dis-command')))
                try:
                    done.result(timeout=1)
                    self.assertTrue(entered.wait(1))
                    pending = svc.read()['devices'][0]
                    self.assertTrue(pending['refresh_pending'])
                    self.assertIsNone(pending['properties']['power']['value'])
                    self.assertFalse(pending['properties']['power']['last_observed_value'])
                finally:
                    release.set()
        fresh_context = [m['content'] for m in backend.stream_calls[-1]
                         if m.get('role') == 'system' and 'Post-command' in str(m.get('content'))]
        self.assertEqual(len(fresh_context), 1)
        self.assertEqual(sum(m.get('role') == 'system' and str(m.get('content', '')).startswith('DIS')
                             for m in backend.stream_calls[-1]), 1)
        self.assertIn('"power":null', fresh_context[0])
        self.assertIn('unconfirmed', fresh_context[0])
        self.assertTrue(svc.refresh(['desk-lamp']))
        self.assertTrue(svc.read()['devices'][0]['properties']['power']['value'])
        history = memory.get_recent_messages('dis-command')
        results = [m for m in history if m.get('role') == 'tool']
        self.assertEqual([m['content'] for m in results], ['Command accepted'])
        self.assertFalse(any('Post-command' in str(m.get('content')) for m in history))

    def test_refresh_does_not_reuse_a_read_started_before_command(self):
        entered, release = threading.Event(), threading.Event()

        class BlockingReader(Reader):
            def read(self, device):
                self.calls += 1
                if self.calls == 1:
                    entered.set()
                    if not release.wait(2):
                        raise ReadFailure('timeout')
                    return Reading(False, time.time())
                return Reading(True, time.time())

        reader = BlockingReader()
        svc = self.make_service(devices=DEVICES[:1], reader=reader, started=True)
        self.assertTrue(entered.wait(1))
        with ThreadPoolExecutor(max_workers=1) as pool:
            done = pool.submit(svc.refresh, ['desk-lamp'])
            with svc._condition:
                self.assertTrue(svc._condition.wait_for(lambda: 'desk-lamp' in svc._requested, timeout=1))
            release.set()
            self.assertTrue(done.result(timeout=3))
        self.assertEqual(reader.calls, 2)
        self.assertTrue(svc.read()['devices'][0]['properties']['power']['value'])

    def test_disabled_start_does_not_connect_or_start_reader(self):
        with mock.patch.object(service, '_service', None), \
             mock.patch.object(service, '_startup_error', 'not_started'), \
             mock.patch.dict(os.environ, {'BUTLER_DIS_ENABLED': '0'}), \
             mock.patch.object(service, 'DeviceStore') as store:
            service.start_service()
            result = service.read_devices()
            store.assert_not_called()
            self.assertEqual(result['error']['code'], 'disabled')


class DISAdapterTests(unittest.TestCase):
    def test_kasa_only_reads_and_disconnects(self):
        device = mock.Mock()
        device.is_on = True
        device.update = mock.AsyncMock()
        device.disconnect = mock.AsyncMock()
        device.turn_on = mock.AsyncMock()
        device.turn_off = mock.AsyncMock()
        kasa = mock.Mock()
        kasa.exceptions.AuthenticationError = type('AuthError', (Exception,), {})
        kasa.Discover.discover_single = mock.AsyncMock(return_value=device)
        with mock.patch('butler.dis.adapters.smart_plugs._kasa', return_value=kasa), \
             mock.patch('butler.dis.adapters.smart_plugs._credentials', return_value=None):
            self.assertTrue(KasaReader().read(DEVICES[0]).power)
        device.update.assert_awaited_once()
        device.disconnect.assert_awaited_once()
        device.turn_on.assert_not_called()
        device.turn_off.assert_not_called()

    def test_timeout_is_bounded_and_does_not_expose_library_errors(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
        kasa = mock.Mock()
        kasa.exceptions.AuthenticationError = type('AuthError', (Exception,), {})
        kasa.Discover.discover_single = slow
        with mock.patch('butler.dis.adapters.smart_plugs._kasa', return_value=kasa), \
             mock.patch('butler.dis.adapters.smart_plugs._credentials', return_value=None):
            with self.assertRaises(ReadFailure) as error:
                KasaReader(timeout=0.01).read(DEVICES[0])
        self.assertEqual(error.exception.code, 'timeout')

    def test_transient_authentication_retries_remain_read_only(self):
        kasa = mock.Mock()
        auth = type('AuthError', (Exception,), {})
        kasa.exceptions.AuthenticationError = auth
        device = mock.Mock(is_on=False)
        device.update, device.disconnect = mock.AsyncMock(), mock.AsyncMock()
        kasa.Discover.discover_single = mock.AsyncMock(side_effect=[auth('private secret'), device])
        with mock.patch('butler.dis.adapters.smart_plugs._kasa', return_value=kasa), \
             mock.patch('butler.dis.adapters.smart_plugs._credentials', return_value=None):
            self.assertFalse(KasaReader().read(DEVICES[0]).power)
        self.assertEqual(kasa.Discover.discover_single.await_count, 2)


class DISHTTPAndToolTests(unittest.TestCase):
    def test_owner_http_bridge_and_mcp_have_one_owner_and_validate_bounds(self):
        from butler.text.server import TextAgentHTTPServer, TextServerConfig
        from mcp.server.fastmcp import FastMCP
        from butler.mcp_servers.providers.device_information import register
        config = replace(TextServerConfig.from_env(), api_token='test-secret',
                         allowed_networks=(ipaddress.ip_network('127.0.0.0/8'),))
        server = TextAgentHTTPServer(('127.0.0.1', 0), queue.Queue(), config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = service.unavailable('not_started')
            with mock.patch.dict(os.environ, {'TEXT_AGENT_PORT': str(server.server_address[1]),
                                             'TEXT_AGENT_API_TOKEN': 'test-secret'}), \
                 mock.patch.object(service, 'read_devices', return_value=result) as read:
                self.assertEqual(client.read_information(), result)
                read.assert_called_once_with('', 0, 8, False)
                mcp = FastMCP('dis-test')
                register(mcp)
                tools = asyncio.run(mcp.list_tools())
                self.assertEqual({t.name for t in tools}, {'list_device_information', 'get_device_information'})
                self.assertTrue(all(t.outputSchema for t in tools))
                asyncio.run(mcp.call_tool('get_device_information', {'device_id': 'desk-lamp'}))
                read.assert_called_with('desk-lamp', 0, 8, False)
                with self.assertRaises(Exception):
                    asyncio.run(mcp.call_tool('list_device_information', {'limit': 9}))
            with mock.patch.dict(os.environ, {'TEXT_AGENT_PORT': str(server.server_address[1]),
                                             'TEXT_AGENT_API_TOKEN': 'wrong'}):
                self.assertFalse(client.read_information()['ok'])
            from butler.text.server import TextAgentRequestHandler
            server.config = replace(config, api_token='')
            with mock.patch.dict(os.environ, {'TEXT_AGENT_PORT': str(server.server_address[1]),
                                             'TEXT_AGENT_API_TOKEN': ''}), \
                 mock.patch.object(TextAgentRequestHandler, '_is_loopback', return_value=False), \
                 mock.patch.object(service, 'read_devices') as read:
                self.assertFalse(client.read_information()['ok'])
                read.assert_not_called()
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


class DISPromptTests(unittest.TestCase):
    def test_real_prompt_assembly_injects_fresh_cache_only_for_full_access(self):
        from contextlib import ExitStack
        from test_run_command_stream import _FakeBackend, _FakeMCP
        from butler.agent import runtime
        from butler.voice.backends.base import LLMCompletion, LLMTextDelta
        backend = _FakeBackend([
            [LLMTextDelta('Lamp off.'), LLMCompletion(text='Lamp off.')],
            [LLMTextDelta('Hello.'), LLMCompletion(text='Hello.')],
        ])
        mcp = _FakeMCP()
        mcp.openai_tool_definitions = lambda: []
        store = MemoryStore(':memory:')
        self.addCleanup(store.close)
        with ExitStack() as stack:
            for name, value in (('get_local_mcp_client', mcp), ('_get_memory_store', store),
                                ('_get_stream_backend', backend), ('_resource_tool_definitions', [])):
                stack.enter_context(mock.patch.object(runtime, name, return_value=value))
            stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_DIS_SUMMARY_ENABLED': '1'}))
            summary = stack.enter_context(mock.patch.object(service, 'prompt_summary',
                return_value='DIS: desk-lamp power=false current age=1s'))
            list(runtime.run_command_stream('Is the lamp on?', session_id='owner-dis', tool_access='full'))
            list(runtime.run_command_stream('Hello', session_id='visitor-dis', tool_access='restricted'))
        self.assertEqual(summary.call_count, 1)
        self.assertTrue(any('DIS: desk-lamp' in str(m.get('content')) for m in backend.stream_calls[0]))
        self.assertFalse(any('DIS: desk-lamp' in str(m.get('content')) for m in backend.stream_calls[1]))
        self.assertEqual(backend.stream_calls[0][0]['content'], backend.stream_calls[1][0]['content'])

    def test_control_hook_requests_read_and_never_assigns_intended_state(self):
        from butler.agent import runtime
        with mock.patch.object(service, 'after_control', return_value=False) as read, \
             mock.patch.object(service, 'prompt_summary', return_value='DIS: last observation is on'), \
             mock.patch.dict(os.environ, {'BUTLER_DIS_SUMMARY_ENABLED': '1'}):
            context = runtime._observe_device_control('set_smart_plug',
                '{"device_id":"desk-lamp","state":"off"}', 'full')
        read.assert_called_once_with('desk-lamp')
        self.assertIn('last observation is on', context)
        self.assertIn('unconfirmed', context)
        self.assertNotIn('power=false', context)

    def test_structured_device_results_survive_tool_shaping_intact(self):
        from butler.agent import runtime
        result = json.dumps({'schema_version': 1, 'devices': [{'evidence': 'x' * 5000}],
                             'coverage': {'truncated': True}})
        for name in ('list_device_information', 'get_device_information'):
            self.assertEqual(runtime._shape_tool_output(name, result), result)
