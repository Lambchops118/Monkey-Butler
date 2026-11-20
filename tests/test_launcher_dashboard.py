from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler.launcher import dashboard
from butler.launcher.dashboard import DASHBOARD_URL, DashboardProcess


class _FakePopen:
    def __init__(self, exit_code=None):
        self.returncode = exit_code
        self.stdout = iter(())
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class LauncherDashboardTests(unittest.TestCase):
    def test_memory_graph_starts_or_reuses_same_dashboard(self):
        process = DashboardProcess(log=lambda *_: None)
        response = mock.MagicMock()
        response.__enter__.return_value.headers = {'Content-Type': 'text/html; charset=utf-8'}
        with mock.patch.object(dashboard, '_port_open', return_value=True), \
                mock.patch.object(dashboard.urllib.request, 'urlopen', return_value=response) as opened, \
                mock.patch.object(dashboard.subprocess, 'Popen') as popen:
            self.assertEqual(DASHBOARD_URL + '/memory', process.ensure_running('/memory'))
            opened.assert_called_once_with(DASHBOARD_URL + '/memory', timeout=3)
            popen.assert_not_called()

    def test_old_running_dashboard_reports_missing_graph_without_killing_it(self):
        process = DashboardProcess(log=lambda *_: None)
        with mock.patch.object(dashboard, '_port_open', return_value=True), \
                mock.patch.object(dashboard.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError(DASHBOARD_URL+'/memory',404,'missing',{},None)), \
                mock.patch.object(dashboard.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'Close its owning launcher'):
                process.ensure_running('/memory')
            popen.assert_not_called()

    def test_memory_button_opens_requested_page_off_ui_thread(self):
        from butler.launcher.gui import LauncherGUI
        gui = LauncherGUI.__new__(LauncherGUI)
        gui.dashboard = mock.Mock()
        gui.dashboard.ensure_running.return_value = DASHBOARD_URL + '/memory'
        gui.root = mock.Mock()
        with mock.patch('webbrowser.open') as opened:
            gui._open_dashboard_worker('/memory')
        gui.dashboard.ensure_running.assert_called_once_with('/memory')
        opened.assert_called_once_with(DASHBOARD_URL + '/memory')

    def test_reuses_a_console_that_is_already_listening(self) -> None:
        process = DashboardProcess(log=lambda *_: None)
        with mock.patch.object(dashboard, "_port_open", return_value=True), \
                mock.patch.object(dashboard.subprocess, "Popen") as popen:
            self.assertEqual(process.ensure_running(), DASHBOARD_URL)
        popen.assert_not_called()
        process.stop()  # nothing it started, nothing to stop

    def test_starts_console_and_waits_for_its_port(self) -> None:
        process = DashboardProcess(log=lambda *_: None)
        fake = _FakePopen()
        with mock.patch.object(dashboard, "_port_open", side_effect=[False, False, True]), \
                mock.patch.object(dashboard.subprocess, "Popen", return_value=fake) as popen, \
                mock.patch.object(dashboard.time, "sleep"):
            self.assertEqual(process.ensure_running(), DASHBOARD_URL)
        args = popen.call_args[0][0]
        self.assertEqual(args[1:3], ["-m", "butler.debug_dashboard"])
        self.assertIn("127.0.0.1", args)
        process.stop()
        self.assertTrue(fake.terminated)

    def test_reports_a_console_that_exits_during_startup(self) -> None:
        process = DashboardProcess(log=lambda *_: None)
        with mock.patch.object(dashboard, "_port_open", return_value=False), \
                mock.patch.object(dashboard.subprocess, "Popen", return_value=_FakePopen(exit_code=1)):
            with self.assertRaisesRegex(RuntimeError, "exited with code 1"):
                process.ensure_running()


if __name__ == "__main__":
    unittest.main()
