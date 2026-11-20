"""WCS contracts against simulated weather, real SQLite and model transports."""

import asyncio
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime
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
from zoneinfo import ZoneInfo

from butler.wcs import client, service
from butler.wcs.models import Batch, Observation, ReadResult, unavailable
from butler.wcs.store import ContextStore
from butler.wcs.weather import WeatherReader


def observation(now=None, **kwargs):
    now = now or time.time()
    values = dict(observation_id='evidence-1', category='weather', subject='Test town',
        source='openweather-current', kind='observation', observed_at=now-60, received_at=now,
        valid_from=None, valid_until=None, timezone='UTC',
        values={'temperature': {'value': 22, 'unit': 'C'}, 'humidity': {'value': 45, 'unit': '%'}})
    return Observation(**(values | kwargs))


class Reader:
    category = 'weather'
    poll_seconds = 900
    identity = {'location': 'Test town', 'units': 'metric'}

    def __init__(self):
        self.calls = 0
        self.batch = Batch((observation(),))

    def read(self):
        self.calls += 1
        return self.batch


class WCSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'butler.sqlite3'

    def make(self, reader=None):
        reader = reader or Reader()
        svc = service.WorldContextService((reader,), ContextStore(self.path))
        self.addCleanup(svc.stop)
        svc.store.register(svc.adapters)
        svc._publish()
        return svc, reader

    def test_commit_and_cache_reads_never_touch_network_or_database(self):
        svc, reader = self.make()
        svc._poll(reader)
        self.assertEqual(reader.calls, 1)
        with mock.patch.object(reader, 'read', side_effect=AssertionError('network')), \
             mock.patch.object(svc.store, 'load', side_effect=AssertionError('database')):
            result = svc.read('weather')
            summary = svc.summary()
        self.assertEqual(result['observations'][0]['values']['temperature']['value'], 22)
        self.assertEqual(result['sources'][0]['status'], 'ready')
        self.assertIn('OUTDOORS', summary)
        self.assertNotIn('appid', json.dumps(result))

    def test_failure_retains_timestamped_observation_and_backs_off(self):
        svc, reader = self.make()
        svc._poll(reader)
        original = svc.read()['observations'][0]
        reader.batch = Batch((), ('timeout',))
        svc._poll(reader)
        first_next = svc._cache[0][0]['next_poll']
        svc._poll(reader)
        result = svc.read()
        self.assertEqual(result['sources'][0]['status'], 'error')
        self.assertEqual(result['observations'][0]['observed_at'], original['observed_at'])
        self.assertGreater(svc._cache[0][0]['next_poll'], first_next+800)

    def test_restart_uses_saved_data_and_schedule_without_another_poll(self):
        svc, reader = self.make()
        svc._poll(reader)
        saved = svc.read()
        other, next_reader = self.make()
        other.start()
        time.sleep(.05)
        self.assertEqual(next_reader.calls, 0)
        self.assertEqual(other.read()['sources'][0]['next_poll_at'], saved['sources'][0]['next_poll_at'])
        self.assertEqual(other.read()['observations'][0]['observation_id'], 'evidence-1')

    def test_crash_reservation_prevents_immediate_duplicate_request(self):
        svc, reader = self.make()
        svc.store.reserve('weather', time.time(), time.time()+900)
        other, next_reader = self.make()
        other.start()
        time.sleep(.05)
        self.assertEqual(next_reader.calls, 0)
        self.assertEqual(other.read()['sources'][0]['status'], 'unknown')

    def test_changed_location_does_not_relabel_old_observations(self):
        svc, reader = self.make()
        svc._poll(reader)
        other = Reader()
        other.identity = {'location': 'Elsewhere', 'units': 'metric'}
        svc.store.register((other,))
        svc._publish()
        self.assertEqual(svc.read()['observations'], [])

    def test_partial_update_preserves_forecast_and_old_date(self):
        svc, reader = self.make()
        now = time.time()
        forecast = observation(kind='forecast', observed_at=None, valid_from=now-86400, valid_until=now-1,
                               source='openweather-daily')
        reader.batch = Batch((observation(), forecast))
        svc._poll(reader)
        reader.batch = Batch((observation(),), ('daily_authorization_failed',))
        svc._poll(reader)
        result = svc.read()
        self.assertEqual(result['sources'][0]['status'], 'partial')
        self.assertEqual(svc._cache[0][0]['failures'], 0)
        self.assertEqual(len(result['observations']), 2)
        old = next(o for o in result['observations'] if o['kind'] == 'forecast')
        self.assertEqual(old['temporal_status'], 'outside_forecast_interval')
        self.assertEqual(old['values'], {})
        self.assertTrue(old['last_reported_values'])
        self.assertNotIn('last_reported_values', svc.summary())
        self.assertIn('valid_until', svc.summary())
        self.assertIn('Forecasts apply ONLY', svc.summary())

    def test_page_bounds_unknown_category_and_summary_budget(self):
        svc, reader = self.make()
        svc._poll(reader)
        self.assertEqual(svc.read('cameras')['status'], 'not_found')
        for args in (('', 0, 9), ('bad/id', 0, 8), ('', -1, 8)):
            with self.assertRaises(ValueError):
                svc.read(*args)
        svc.settings = service.Settings(summary_chars=512)
        summary = svc.summary()
        self.assertLessEqual(len(summary), 512)
        self.assertIn('omitted 1', summary)
        self.assertEqual(svc.read(offset=1)['coverage']['total'], 1)

    def test_stale_source_time_is_never_replaced_with_fetch_time(self):
        svc, reader = self.make()
        reader.batch = Batch((observation(observed_at=time.time()-86400),))
        svc._poll(reader)
        o = svc.read()['observations'][0]
        self.assertGreaterEqual(o['age_seconds'], 86400)
        self.assertNotEqual(o['observed_at'], o['received_at'])

    def test_storage_failure_does_not_publish_uncommitted_data(self):
        svc, reader = self.make()
        with mock.patch.object(svc.store, 'commit', side_effect=RuntimeError('disk')):
            with self.assertRaises(RuntimeError):
                svc._poll(reader)
        self.assertEqual(svc.read()['observations'], [])

    def test_new_settings_validate_and_disabled_start_has_no_effects(self):
        with self.assertRaises(ValueError):
            service.Settings(weather_poll_seconds=0)
        with mock.patch.object(service, '_service', None), mock.patch.dict(os.environ, {'BUTLER_WCS_ENABLED': '0'}), \
             mock.patch.object(service, 'ContextStore') as store:
            service.start_service()
            self.assertEqual(service.read_context()['error'], 'disabled')
            store.assert_not_called()

    def test_observation_schema_rejects_unbounded_or_invalid_data(self):
        for kwargs in ({'values': {'temperature': {'value': float('nan'), 'unit': 'C'}}},
                       {'observed_at': time.time()+1000}, {'subject': 'x'*161},
                       {'kind': 'forecast'}, {'values': {'x': {'value': True, 'unit': None}}}):
            with self.assertRaises(ValueError):
                observation(**kwargs)

    def test_upgrade_from_dis_database_preserves_device_rows(self):
        from butler import storage
        from butler.dis.models import Device, Reading
        from butler.dis.store import DeviceStore
        owners = {k: v for k, v in storage.TABLE_OWNERS.items() if v not in ('wcs', 'ltms')}
        with mock.patch.object(storage, 'MIGRATIONS', storage.MIGRATIONS[:3]), mock.patch.object(storage, 'TABLE_OWNERS', owners):
            device_store = DeviceStore(self.path)
            device = Device('test-lamp', 'Test lamp', 'unused', 'light')
            device_store.register((device,))
            device_store.record('test-lamp', time.time(), Reading(True, time.time()), None)
            device_store.close()
        svc, reader = self.make()
        svc._poll(reader)
        device_store = DeviceStore(self.path)
        try:
            self.assertTrue(device_store.load((device,))[0].reading.power)
        finally:
            device_store.close()

    def test_conversation_clear_preserves_wcs_observations(self):
        from butler.memory import MemoryStore
        svc, reader = self.make()
        svc._poll(reader)
        memory = MemoryStore(self.path)
        try:
            memory.record_turn('owner', 'hello', 'hi')
            memory.clear_all()
            svc._publish()
            self.assertEqual(len(svc.read()['observations']), 1)
        finally:
            memory.close()


class Response:
    def __init__(self, payload, status=200):
        self.data = json.dumps(payload).encode()
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.data


class WeatherTests(unittest.TestCase):
    def make(self, daily_status=200, now=None, daily=None):
        now = now or time.time()
        current = {'dt': now-90, 'timezone': -18000,
            'main': {'temp': 50, 'humidity': 70, 'temp_min': -99, 'temp_max': 999},
            'weather': [{'description': 'clear sky'}]}
        payload = {'timezone': 'America/New_York', 'daily': [
            {'dt': now, 'temp': {'min': 40, 'max': 60}, 'pop': .2}]}
        if daily is not None:
            payload = daily.copy()
        payload.setdefault('hourly', [{'dt': int(now//3600)*3600+i*3600, 'temp': 38+i, 'pop': .1}
                                      for i in range(48)])
        responses = [Response([{'lat': 39, 'lon': -76}]), Response(current), Response(payload, daily_status)]
        get = mock.Mock(side_effect=responses)
        with mock.patch.dict(os.environ, {'BUTLER_WEATHER_LOCATION': 'Test town',
            'BUTLER_WEATHER_UNITS': 'imperial', 'OPEN_WEATHER_API_KEY': 'test-secret'}):
            reader = WeatherReader(get=get)
        return reader, get

    def test_weather_is_typed_and_daily_range_not_current_spatial_range(self):
        reader, get = self.make()
        batch = reader.read()
        self.assertEqual(batch.errors, ())
        self.assertEqual(len(batch.observations), 2)
        current, forecast = batch.observations
        self.assertEqual(current.values['temperature']['value'], 50)
        self.assertEqual(forecast.values['high']['value'], 60)
        self.assertEqual(forecast.values['low']['value'], 40)
        self.assertIsNone(forecast.observed_at)
        self.assertLess(current.observed_at, current.received_at)
        self.assertEqual(get.call_count, 3)
        self.assertNotIn('test-secret', repr(batch))

    def test_forecast_failure_preserves_successful_current_observation(self):
        reader, get = self.make(daily_status=401)
        batch = reader.read()
        self.assertEqual(batch.errors, ('daily_authorization_failed',))
        self.assertEqual(len(batch.observations), 1)

    def test_day_boundaries_respect_dst_and_forecast_targets(self):
        zone = ZoneInfo('America/New_York')
        now = datetime(2026, 11, 1, 12, tzinfo=zone).timestamp()
        reader, get = self.make(now=now)
        with mock.patch('butler.wcs.weather.time.time', return_value=now):
            batch = reader.read()
        forecast = batch.observations[1]
        self.assertEqual(forecast.valid_until-forecast.valid_from, 25*3600)
        self.assertEqual(forecast.timezone, 'America/New_York')

    def test_missing_daily_target_is_not_presented_as_today(self):
        reader, get = self.make(daily={'daily': [{'dt': time.time()-864000, 'temp': {'min': 1, 'max': 2}}]})
        self.assertEqual(reader.read().errors, ('daily_forecast_unavailable',))

    def test_missing_config_and_rate_limits_never_retry_immediately(self):
        with mock.patch.dict(os.environ, {'OPEN_WEATHER_API_KEY': ''}):
            reader = WeatherReader(get=mock.Mock(side_effect=AssertionError('network')))
        self.assertEqual(reader.read().errors, ('not_configured',))
        reader, get = self.make()
        get.side_effect = [Response({}, 429)]
        self.assertEqual(reader.read().errors, ('rate_limited',))
        self.assertEqual(get.call_count, 1)

    def test_oversized_invalid_data_and_timeouts_are_redacted(self):
        import requests
        reader, get = self.make()
        get.side_effect = requests.Timeout('url?appid=SECRET')
        self.assertEqual(reader.read().errors, ('timeout',))
        reader, get = self.make()
        response = Response({})
        response.data = b'x'*262145
        get.side_effect = [response]
        self.assertEqual(reader.read().errors, ('response_too_large',))


class WCSIntegrationTests(unittest.TestCase):
    def test_owner_http_bridge_and_typed_mcp_tool(self):
        from butler.text.server import TextAgentHTTPServer, TextServerConfig
        from mcp.server.fastmcp import FastMCP
        from butler.mcp_servers.providers.world_context import register
        config = replace(TextServerConfig.from_env(), api_token='test-secret',
                         allowed_networks=(ipaddress.ip_network('127.0.0.0/8'),))
        server = TextAgentHTTPServer(('127.0.0.1', 0), queue.Queue(), config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = unavailable('not_started')
            with mock.patch.dict(os.environ, {'TEXT_AGENT_PORT': str(server.server_address[1]),
                 'TEXT_AGENT_API_TOKEN': 'test-secret'}), mock.patch.object(service, 'read_context', return_value=result) as read:
                self.assertEqual(client.read_information(), result)
                server_mcp = FastMCP('wcs-test')
                register(server_mcp)
                tools = asyncio.run(server_mcp.list_tools())
                self.assertEqual([t.name for t in tools], ['get_world_context'])
                self.assertTrue(tools[0].outputSchema)
                asyncio.run(server_mcp.call_tool('get_world_context', {'category': 'weather'}))
                read.assert_called_with('weather', 0, 8, 'overview', '', '')
                client.read_information('weather', forecast='hourly', start_at='2026-11-19T08:00:00-05:00')
                read.assert_called_with('weather', 0, 8, 'hourly', '2026-11-19T08:00:00-05:00', '')
                self.assertFalse(client.read_information('weather', forecast='hourly', start_at='2026-11-19T08:00:00')['ok'])

                with self.assertRaises(Exception):
                    asyncio.run(server_mcp.call_tool('get_world_context', {'limit': 9}))
            with mock.patch.dict(os.environ, {'TEXT_AGENT_PORT': str(server.server_address[1]), 'TEXT_AGENT_API_TOKEN': 'wrong'}):
                self.assertFalse(client.read_information()['ok'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_direct_weather_route_is_removed_and_wcs_read_remains(self):
        from mcp.server.fastmcp import FastMCP
        from butler.mcp_servers.providers import home_automation, world_context
        mcp = FastMCP('weather-route-test')
        home_automation.register(mcp)
        world_context.register(mcp)
        names = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertNotIn('get_current_weather', names)
        self.assertIn('get_current_datetime', names)
        self.assertIn('get_world_context', names)
        with mock.patch.object(home_automation.actions, 'get_current_weather', side_effect=AssertionError('live weather')) as fetch:
            with self.assertRaises(Exception):
                asyncio.run(mcp.call_tool('get_current_weather', {}))
            fetch.assert_not_called()

    def test_owner_only_summary_in_real_turn_and_structured_result_preserved(self):
        from butler.agent import runtime
        with mock.patch.object(service, 'prompt_summary', return_value='WCS fixture: outdoors 22 C'), \
             mock.patch.dict(os.environ, {'BUTLER_WCS_SUMMARY_ENABLED': '1'}):
            self.assertIsNone(runtime._world_context('restricted'))
            self.assertIn('22 C', runtime._world_context('full'))
        payload = json.dumps(unavailable('disabled'))
        self.assertEqual(runtime._shape_tool_output('get_world_context', payload), payload)


    def test_real_turn_prompt_receives_one_wcs_block_for_owner_only(self):
        from test_run_command_stream import _FakeBackend, _FakeMCP
        from butler.agent import runtime
        from butler.memory import MemoryStore
        from butler.voice.backends.base import LLMCompletion, LLMTextDelta
        backend = _FakeBackend([
            [LLMTextDelta('Outside 22 C.'), LLMCompletion(text='Outside 22 C.')],
            [LLMTextDelta('Hello.'), LLMCompletion(text='Hello.')],
        ])
        mcp = _FakeMCP()
        mcp.openai_tool_definitions = lambda: []
        memory = MemoryStore(':memory:')
        try:
            with ExitStack() as stack:
                for name, value in (('get_local_mcp_client', mcp), ('_get_memory_store', memory),
                                    ('_get_stream_backend', backend), ('_resource_tool_definitions', [])):
                    stack.enter_context(mock.patch.object(runtime, name, return_value=value))
                stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_WCS_SUMMARY_ENABLED': '1'}))
                summary = stack.enter_context(mock.patch.object(service, 'prompt_summary', return_value='WCS fixture: 22 C outdoors'))
                list(runtime.run_command_stream('How warm outside?', session_id='owner-wcs', tool_access='full'))
                list(runtime.run_command_stream('Hello', session_id='visitor-wcs', tool_access='restricted'))
            self.assertEqual(summary.call_count, 1)
            self.assertEqual(sum(str(m.get('content', '')).startswith('WCS fixture') for m in backend.stream_calls[0]), 1)
            self.assertFalse(any('WCS fixture' in str(m.get('content')) for m in backend.stream_calls[1]))
            self.assertFalse(any('WCS fixture' in str(m.get('content')) for m in memory.get_recent_messages('owner-wcs')))
        finally:
            memory.close()

    def test_responses_turn_prompt_receives_wcs_for_owner_only(self):
        from types import SimpleNamespace
        from butler.agent import runtime
        from butler.memory import MemoryStore
        memory = MemoryStore(':memory:')
        response = SimpleNamespace(id='wcs-response-test', output=[], output_text='Weather reply.')
        try:
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(runtime, 'get_local_mcp_client', return_value=mock.Mock()))
                stack.enter_context(mock.patch.object(runtime, '_build_tool_definitions', return_value=[]))
                stack.enter_context(mock.patch.object(runtime, '_get_memory_store', return_value=memory))
                stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_WCS_SUMMARY_ENABLED': '1'}))
                summary = stack.enter_context(mock.patch.object(service, 'prompt_summary', return_value='WCS fixture: 22 C outdoors'))
                create = stack.enter_context(mock.patch.object(runtime, '_responses_create_with_retry', return_value=response))
                runtime.run_command('How warm outside?', session_id='wcs-owner-responses', tool_access='full')
                runtime.run_command('Hello', session_id='wcs-visitor-responses', tool_access='restricted')
            self.assertEqual(summary.call_count, 1)
            first, second = [call.kwargs['input'] for call in create.call_args_list]
            self.assertTrue(any(str(m.get('content', '')).startswith('WCS fixture') for m in first))
            self.assertFalse(any(str(m.get('content', '')).startswith('WCS fixture') for m in second))
        finally:
            memory.close()
