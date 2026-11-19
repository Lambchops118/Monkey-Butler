"""Opt-in real local-model acceptance; simulated sources, no paid API calls."""

from contextlib import ExitStack
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from butler.agent import runtime
from butler.memory import MemoryStore
from butler.wcs import service
from butler.wcs.models import Batch, Observation
from butler.wcs.store import ContextStore


@unittest.skipUnless(os.getenv('BUTLER_WCS_LIVE_MODEL_TEST') == '1', 'opt-in real local model test')
class WCSLocalModelAcceptance(unittest.TestCase):
    def test_model_uses_weather_times_and_scope(self):
        self.assertTrue(runtime._get_stream_backend().is_local, 'Fixtures must stay on the local backend')
        now = time.time()
        class Reader:
            category = 'weather'
            poll_seconds = 900
            identity = {'location': 'Test town'}

        current = Observation('current-evidence', 'weather', 'Test town', 'openweather-current',
            'observation', now-30, now, None, None, 'UTC', {
                'temperature': {'value': 22, 'unit': 'C'}, 'humidity': {'value': 45, 'unit': '%'}})
        old_forecast = Observation('forecast-evidence', 'weather', 'Test town', 'openweather-daily',
            'forecast', None, now-86400, now-172800, now-86400, 'UTC', {
                'high': {'value': 99, 'unit': 'C'}, 'low': {'value': 10, 'unit': 'C'}})
        with tempfile.TemporaryDirectory() as tmp:
            svc = service.WorldContextService((Reader(),), ContextStore(tmp+'/butler.sqlite3'))
            svc.store.register(svc.adapters)
            svc.store.reserve('weather', now, now+900)
            svc.store.commit('weather', Batch((current, old_forecast)), now, now+900)
            svc._publish()
            memory = MemoryStore(':memory:')

            from mcp.server.fastmcp import FastMCP
            from butler.mcp_servers.providers.world_context import register
            server = FastMCP('wcs-model-schema')
            register(server)
            schema = asyncio.run(server.list_tools())[0]
            class ReadOnlyMCP:
                def openai_tool_definitions(self):
                    return [{'type': 'function', 'name': schema.name,
                        'description': schema.description, 'parameters': schema.inputSchema}]

                def call_tool(self, name, arguments):
                    if name != 'get_world_context':
                        raise AssertionError('No mutation/source polling tool exists')
                    args = json.loads(arguments) if isinstance(arguments, str) else arguments
                    return json.dumps(service.read_context(**args))
            try:
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(service, '_service', svc))
                    for name, value in (('_get_memory_store', memory), ('get_local_mcp_client', ReadOnlyMCP()),
                                        ('_resource_tool_definitions', [])):
                        stack.enter_context(mock.patch.object(runtime, name, return_value=value))
                    stack.enter_context(mock.patch.object(runtime, 'TOOLS_DISABLED', False))
                    stack.enter_context(mock.patch.dict(os.environ, {'BUTLER_WCS_SUMMARY_ENABLED': '1'}))
                    def ask(prompt):
                        answer = runtime.collect_command(prompt, 'no recent weather', session_id='wcs-acceptance',
                            interaction_mode='text', runtime_lane='foreground', extra_context=None, tool_access='full').lower()
                        print('WCS model:', answer)
                        return answer
                    self.assertRegex(ask('What is the local outdoor temperature in Celsius?'), r'\b22\b')
                    self.assertRegex(ask('What is the humidity inside my kitchen?'),
                        r"unknown|unavailable|cannot|can't|no.*(?:indoor|kitchen|sensor)|not.*(?:know|available|have)")
                    answer = ask("What is today's forecast high? Give only a verified forecast for today.")
                    self.assertRegex(answer, r"unknown|unavailable|cannot|can't|outdated|expired|no.*(?:today|current|forecast)|not.*(?:available|have|verified)")
                    # Reproduce the reported mix-up with an applicable daily high,
                    # realistic Fahrenheit values and the same conversation history.
                    actual = Observation('actual-temp', 'weather', 'Test town', 'openweather-current',
                        'observation', now-30, now, None, None, 'UTC', {
                            'temperature': {'value': 44.24, 'unit': 'F'}})
                    start = int(now//86400)*86400
                    today = Observation('daily-high', 'weather', 'Test town', 'openweather-daily',
                        'forecast', None, now, start, start+86400, 'UTC', {
                            'high': {'value': 68.22, 'unit': 'F'}, 'low': {'value': 35.44, 'unit': 'F'}})
                    svc.store.commit('weather', Batch((actual, today)), now, now+900)
                    svc._publish()
                    self.assertRegex(ask("What's the weather like?"), r'44(?:\.24)?')
                    for prompt in ("What's the temperature going to be at 8 a.m.?", 'What about 9 a.m.?'):
                        self.assertRegex(ask(prompt),
                            r"unknown|unavailable|cannot|can't|no.*hourly|not.*(?:available|have|provide|predict|determine)")
                    local = datetime.fromtimestamp(now, ZoneInfo('America/New_York'))
                    target = local.replace(hour=8, minute=0, second=0, microsecond=0)
                    if target.timestamp() <= now:
                        target += timedelta(days=1)
                    base = int(now//3600)*3600
                    hourly = []
                    for i in range(48):
                        at = base+i*3600
                        temp = 38 if at == target.timestamp() else 40 if at == target.timestamp()+3600 else 55 if i == 30 else 42
                        hourly.append(Observation(f'forecast-hour-{i}', 'weather', 'Test town', 'openweather-hourly',
                            'forecast', None, now, at, at+3600, 'America/New_York', {
                                'temperature': {'value': temp, 'unit': 'F'},
                                'precipitation_probability': {'value': 73 if at == target.timestamp() else 1, 'unit': '%'}}, resolution='hourly'))
                    svc.store.commit('weather', Batch((actual, today), hourly=tuple(hourly)), now, now+900)
                    svc._publish()
                    self.assertRegex(ask(f'What is the temperature forecast in Fahrenheit at 8 a.m. on {target.date()} in America/New_York?'), r'\b38(?:\.0)?\b')
                    self.assertRegex(ask('What about 9 a.m. that same day? Give Fahrenheit.'), r'\b40(?:\.0)?\b')
                    far = datetime.fromtimestamp(base+30*3600, ZoneInfo('America/New_York'))
                    self.assertRegex(ask(f'What is the forecast temperature in Fahrenheit at {far.hour}:00 on {far.date()} in America/New_York?'), r'\b55(?:\.0)?\b')
                    self.assertRegex(ask(f'What is the precipitation probability as a percentage specifically at 8 a.m. on {target.date()} in America/New_York?'), r'\b73(?:\.0)?\b')


                    with mock.patch.object(service, '_service', None):
                        self.assertRegex(ask('What is the local outdoor temperature right now?'),
                            r"unknown|unavailable|cannot|can't|no.*(?:access|current|weather)|not.*(?:know|available|have)")
            finally:
                memory.close()
                svc.stop()
