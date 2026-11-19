from __future__ import annotations

import io
import json
import queue
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from butler.launcher.config import LauncherConfig
from butler.launcher.core import Supervisor
from butler.launcher.gui import LauncherGUI
from butler.launcher import config as launcher_config, gui as launcher_gui
from butler.llm_debug import LLM_DEBUG_PREFIX, emit_llm_io, llm_debug_log_path


class LLMDebugEmitterTests(unittest.TestCase):
    def test_emitter_is_silent_unless_launcher_opted_in(self):
        output = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            emit_llm_io("sent", {"input": "private"}, api="test")
        self.assertEqual(output.getvalue(), "")

    def test_enabled_emitter_preserves_full_payload_in_one_prefixed_record(self):
        payload = {"messages": [{"role": "user", "content": "exact text"}]}
        output = io.StringIO()
        with (
            mock.patch.dict("os.environ", {"BUTLER_LLM_DEBUG_STDOUT": "1"}, clear=True),
            redirect_stdout(output),
        ):
            emit_llm_io("sent", payload, api="chat.completions", operation="stream")

        line = output.getvalue().strip()
        self.assertTrue(line.startswith(LLM_DEBUG_PREFIX))
        event = json.loads(line[len(LLM_DEBUG_PREFIX) :])
        self.assertEqual(event["payload"], payload)
        self.assertEqual(event["direction"], "sent")

    def test_configured_log_directory_persists_one_jsonl_record(self):
        payload = {"messages": [{"role": "user", "content": "keep this"}]}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.dict(
                    "os.environ", {"BUTLER_LLM_DEBUG_LOG_DIR": temp_dir}, clear=True
                ),
                redirect_stdout(output),
            ):
                emit_llm_io("sent", payload, api="chat.completions")
                path = llm_debug_log_path()
                self.assertIsNotNone(path)
                lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["payload"], payload)


class LauncherLLMDebugRoutingTests(unittest.TestCase):
    def setUp(self):
        self.gui = LauncherGUI.__new__(LauncherGUI)
        self.gui._log_queue = queue.Queue()
        self.gui._llm_queue = queue.Queue()

    def test_structured_main_record_routes_only_to_llm_tab(self):
        event = {
            "direction": "sent",
            "api": "chat.completions",
            "payload": {"messages": [{"role": "user", "content": "hello"}]},
        }

        self.gui._enqueue_log("main", LLM_DEBUG_PREFIX + json.dumps(event))

        self.assertEqual(self.gui._llm_queue.get_nowait(), event)
        self.assertTrue(self.gui._log_queue.empty())

    def test_malformed_debug_record_remains_visible_in_normal_logs(self):
        message = LLM_DEBUG_PREFIX + "not-json"
        self.gui._enqueue_log("main", message)
        self.assertEqual(self.gui._log_queue.get_nowait(), ("main", message))
        self.assertTrue(self.gui._llm_queue.empty())

    def test_non_main_prefixed_output_is_not_treated_as_trusted_debug_data(self):
        message = LLM_DEBUG_PREFIX + json.dumps({"payload": "spoofed"})
        self.gui._enqueue_log("voice", message)
        self.assertEqual(self.gui._log_queue.get_nowait(), ("voice", message))
        self.assertTrue(self.gui._llm_queue.empty())

    def test_render_uses_distinct_sent_and_received_color_tags(self):
        class FakeText:
            def __init__(self):
                self.inserts = []

            def configure(self, **_kwargs):
                pass

            def insert(self, index, text, tag):
                self.inserts.append((index, text, tag))

            def count(self, *_args):
                return (0,)

            def see(self, _index):
                pass

            def delete(self, *_args):
                pass

        self.gui.llm_text = FakeText()
        self.gui._append_llm_event({"direction": "sent", "payload": {"x": 1}})
        self.gui._append_llm_event({"direction": "received", "payload": {"y": 2}})

        tags = [tag for _index, _text, tag in self.gui.llm_text.inserts]
        self.assertEqual(
            tags,
            ["sent_header", "sent_payload", "received_header", "received_payload"],
        )


class LauncherLLMDebugProcessTests(unittest.TestCase):
    def test_launcher_managed_main_process_enables_debug_stdout(self):
        supervisor = Supervisor(LauncherConfig(), log=lambda _source, _message: None)
        with (
            mock.patch("butler.launcher.core.venv_python", return_value=Path("missing-python")),
            mock.patch.object(supervisor, "_spawn") as spawn,
            mock.patch.object(supervisor, "_wait_port"),
        ):
            supervisor._start_main({})

        child_env = spawn.call_args.args[2]
        self.assertEqual(child_env["BUTLER_LLM_DEBUG_STDOUT"], "1")
        self.assertEqual(
            Path(child_env["BUTLER_LLM_DEBUG_LOG_DIR"]).parts[-2:],
            ("butler", "logs"),
        )


class LauncherContextControlsTests(unittest.TestCase):
    """Exercise widget construction and real settings persistence without a display."""

    class Variable:
        def __init__(self, value=None, **_kwargs):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    def test_launcher_saves_active_context_without_reintroducing_awareness(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(launcher_config, "SETTINGS_PATH", Path(tmp) / "settings.env"), \
             mock.patch.object(launcher_config, "LAUNCHER_CONFIG_PATH", Path(tmp) / "launcher.json"), \
             mock.patch.object(launcher_gui, "ttk") as widgets, \
             mock.patch.object(launcher_gui, "tk") as tk, \
             mock.patch.object(launcher_gui, "_ollama_models", return_value=[]):
            tk.BooleanVar.side_effect = self.Variable
            tk.StringVar.side_effect = self.Variable
            gui = LauncherGUI.__new__(LauncherGUI)
            gui.root = mock.Mock()
            gui.cfg = LauncherConfig()
            gui.gpus = []
            gui._build_widgets()
            gui._load_into_widgets()
            with mock.patch.object(gui, "_apply_volume"):
                gui._persist()
                first_save = launcher_config.SETTINGS_PATH.read_text(encoding="utf-8")
                gui.var_memory.set(False)
                gui._persist()
                second_save = launcher_config.SETTINGS_PATH.read_text(encoding="utf-8")

            labels = [str(call.kwargs.get("text", ""))
                      for kind in (widgets.LabelFrame, widgets.Checkbutton, widgets.Button)
                      for call in kind.call_args_list]
            self.assertIn("Conversation memory (history + saved facts)", labels)
            self.assertIn("Clear conversation memory…", labels)
            self.assertFalse(any("awareness" in label.lower() for label in labels))
            self.assertFalse(hasattr(gui, "var_situation"))
            self.assertFalse(hasattr(gui, "var_mqtt"))
            self.assertIn("BUTLER_MEMORY_ENABLED=1", first_save)
            self.assertIn("BUTLER_MEMORY_ENABLED=0", second_save)
            self.assertNotIn("BUTLER_AWARENESS_", second_save)
            self.assertFalse(any(key.startswith("BUTLER_AWARENESS_")
                                 for key in launcher_config._SETTINGS_DEFAULTS))


if __name__ == "__main__":
    unittest.main()
