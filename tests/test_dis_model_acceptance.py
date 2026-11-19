"""Opt-in local-model acceptance through the real turn engine, simulated devices.

Run with BUTLER_DIS_LIVE_MODEL_TEST=1. No physical/control tools are offered.
"""

from contextlib import ExitStack
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from butler.agent import runtime
from butler.dis import service
from butler.dis.models import Device, Reading
from butler.dis.store import DeviceStore
from butler.memory import MemoryStore


@unittest.skipUnless(os.getenv('BUTLER_DIS_LIVE_MODEL_TEST') == '1', 'opt-in real local model test')
class DISLocalModelAcceptance(unittest.TestCase):
    def test_local_model_uses_injected_state_without_inventing_device_capabilities(self):
        backend = runtime._get_stream_backend()
        self.assertTrue(backend.is_local, 'This acceptance run must not send fixture context to a hosted model')
        with tempfile.TemporaryDirectory() as tmp:
            dis = service.DeviceInformationService(
                (Device('test-lamp', 'Test lamp', 'unused', 'light'),
                 Device('test-coffee', 'Test coffee plug', 'unused', 'appliance')),
                DeviceStore(tmp + '/dis.sqlite3'), None)
            dis.store.register(dis.devices)
            dis._records = dis.store.load(dis.devices)
            dis._error = None
            dis._accept('test-lamp', time.monotonic(), Reading(False, time.time()), None)
            dis._accept('test-coffee', time.monotonic(), Reading(True, time.time()), None)
            memory = MemoryStore(':memory:')

            class ReadOnlyMCP:
                def openai_tool_definitions(self):
                    return [{'type': 'function', 'name': 'get_device_information',
                        'description': 'Read device power and communication health. Never controls hardware.',
                        'parameters': {'type': 'object', 'properties': {'device_id': {'type': 'string'}},
                                       'required': ['device_id'], 'additionalProperties': False}}]

                def call_tool(self, name, arguments):
                    if name != 'get_device_information':
                        raise AssertionError('No mutation tool exists in this acceptance harness')
                    args = json.loads(arguments) if isinstance(arguments, str) else arguments
                    return json.dumps(service.read_devices(args['device_id']))

            try:
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(service, '_service', dis))
                    stack.enter_context(mock.patch.object(runtime, '_get_memory_store', return_value=memory))
                    stack.enter_context(mock.patch.object(runtime, 'get_local_mcp_client', return_value=ReadOnlyMCP()))
                    stack.enter_context(mock.patch.object(runtime, '_resource_tool_definitions', return_value=[]))
                    stack.enter_context(mock.patch.object(runtime, 'TOOLS_DISABLED', False))
                    stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_DIS_SUMMARY_ENABLED': '1'}))

                    def ask(prompt):
                        return runtime.collect_command(prompt, 'no recent status', session_id='dis-acceptance',
                            interaction_mode='text', runtime_lane='foreground', extra_context=None,
                            tool_access='full').lower()

                    self.assertRegex(ask('Is the test lamp on?'), r'\boff\b|not on')
                    self.assertRegex(ask('Is the test coffee machine brewing?'),
                                     r"cannot|can't|unknown|only|unable|not.*(?:know|tell|confirm)")
                    dis._accept('test-lamp', time.monotonic(), None, 'timeout')
                    self.assertRegex(ask('Is the test lamp on right now?'),
                                     r"unknown|stale|unreachable|cannot|can't|not.*(?:know|tell|confirm)")
                    with mock.patch.object(service, '_service', None):
                        self.assertRegex(ask('Is the test lamp on right now?'),
                                         r"unknown|unavailable|cannot|can't|not.*(?:know|tell|confirm)")
            finally:
                memory.close()
                dis.stop()
