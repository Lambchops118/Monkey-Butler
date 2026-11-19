"""The archived subsystem must not remain an implicit runtime dependency."""

import ast
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from butler.agent import runtime
from butler.launcher import config, core
from butler.memory import MemoryStore
from butler.mcp_servers.aggregate import create_aggregate_server
from butler.debug_dashboard import server as dashboard


ROOT = Path(__file__).resolve().parents[1]
RETIRED_TOOLS = {
    'get_current_state', 'get_recent_events', 'get_sensor_history',
    'get_active_alerts', 'get_system_health', 'set_owner_presence',
    'get_event_provenance', 'search_memory', 'propose_memory_candidate',
    'request_device_action', 'get_action_status', 'water_plants', 'toggle_fan',
    'set_reminder', 'list_reminders', 'cancel_reminder',
    'list_recent_briefings', 'set_briefing_preference', 'get_awareness_capabilities',
}


class AwarenessRetirementTests(unittest.TestCase):
    def test_live_tool_catalog_excludes_retired_capabilities(self):
        with mock.patch.dict('os.environ', {'BUTLER_MCP_DISABLED_PROVIDERS': ''}):
            tools = asyncio.run(create_aggregate_server().list_tools())
        names = {tool.name for tool in tools}
        self.assertFalse(names & RETIRED_TOOLS)
        self.assertTrue({'list_smart_plugs', 'set_smart_plug',
                         'get_current_datetime', 'get_current_weather'} <= names)

    def test_saved_legacy_launcher_settings_cannot_restore_archived_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'launcher.json'
            path.write_text(json.dumps({'start_awareness': True,
                'start_awareness_db': True, 'manage_docker': True,
                'run_migrations': True, 'start_voice': False}))
            with mock.patch.object(config, 'LAUNCHER_CONFIG_PATH', path):
                cfg = config.LauncherConfig.load()
        self.assertFalse(cfg.start_voice)
        self.assertNotIn('awareness', cfg.to_json())
        self.assertNotIn('awareness', config.VENV_DIRS)
        self.assertNotIn('awareness', {entry.key for entry in config.mcp_catalog()})
        supervisor = core.Supervisor(cfg, log=lambda *_: None)
        with mock.patch.object(config, 'detect_gpus', return_value=[]), \
             mock.patch.object(supervisor, '_spawn') as spawn, \
             mock.patch.object(supervisor, '_run_blocking') as blocking, \
             mock.patch.object(supervisor, '_start_ollama'), \
             mock.patch.object(supervisor, '_start_main'), \
             mock.patch.object(supervisor, '_start_display'), \
             mock.patch.object(supervisor, '_start_discord'):
            supervisor.start()
        spawn.assert_not_called()
        blocking.assert_not_called()

    def test_remember_fact_writes_only_active_sqlite_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(Path(tmp) / 'memory.sqlite3')
            try:
                with mock.patch.object(runtime, '_get_memory_store', return_value=store), \
                     mock.patch('urllib.request.urlopen', side_effect=AssertionError('unexpected HTTP')):
                    result = json.loads(runtime._invoke_host_tool(None,
                        'remember_memory_fact', {'key': 'units', 'value': 'metric'},
                        session_id='owner'))
                self.assertTrue(result['success'])
                self.assertNotIn('awareness_memory_synced', result)
                self.assertEqual(store.search_facts('units')[0].value, 'metric')
            finally:
                store.close()

    def test_active_python_does_not_import_archived_code(self):
        for path in (ROOT / 'butler').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ''] + [alias.name for alias in node.names]
                else:
                    continue
                self.assertFalse(any(name.startswith(('butler.awareness',
                    'archive.awareness')) or name in ('awareness_client',
                    'awareness_signals', 'register_awareness_tools') for name in imports),
                    str(path))

    def test_dashboard_never_probes_retired_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = dashboard.DebugSnapshotService(log_root=root,
                memory_db=root / 'missing.sqlite3', job_db=root / 'jobs.sqlite3')
            with mock.patch.object(service, '_service_health', return_value=[]), \
                 mock.patch.object(dashboard, 'read_json_endpoint',
                     return_value={'status': 'unavailable', 'data': {}}) as read, \
                 mock.patch.object(dashboard, 'read_ollama_placement', return_value={}), \
                 mock.patch.object(service, '_host_snapshot', return_value={}):
                snapshot = service.snapshot(event_limit=5, interaction_limit=5)
        self.assertTrue(all('8600' not in str(call) for call in read.call_args_list))
        self.assertEqual(snapshot['operations']['awareness_metrics']['status'], 'archived')
        self.assertEqual(snapshot['operations']['actions']['status'], 'archived')


if __name__ == '__main__':
    unittest.main()
