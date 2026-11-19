from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler.agent.conversation import resolve_session
from butler.router import request_uses_background
from butler.text.server import TextAgentRequestHandler, _stream_state_snapshot


class TextServerLoggingTests(unittest.TestCase):
    def test_event_poll_requests_are_suppressed(self) -> None:
        handler = object.__new__(TextAgentRequestHandler)
        handler.command = "GET"
        handler.path = "/sessions/main-pc/events?after_id=63"
        handler.address_string = lambda: "127.0.0.1"

        with mock.patch("builtins.print") as print_mock:
            handler.log_message('"%s" %s %s', "GET /sessions/main-pc/events?after_id=63 HTTP/1.1", "200", "-")

        print_mock.assert_not_called()

    def test_non_event_requests_still_log(self) -> None:
        handler = object.__new__(TextAgentRequestHandler)
        handler.command = "GET"
        handler.path = "/health"
        handler.address_string = lambda: "127.0.0.1"

        with mock.patch("builtins.print") as print_mock:
            handler.log_message('"%s" %s %s', "GET /health HTTP/1.1", "200", "-")

        print_mock.assert_called_once()


class TextServerStreamContextTests(unittest.TestCase):
    def test_stream_preserves_explicit_status_without_backend_access(self) -> None:
        self.assertEqual(
            _stream_state_snapshot({"state_snapshot": "legacy state"}),
            "legacy state",
        )

    def test_stream_has_no_automatic_household_snapshot(self) -> None:
        self.assertEqual(_stream_state_snapshot({}), "no recent status")


class OwnerConversationTests(unittest.TestCase):
    def test_existing_background_mode_requires_explicit_authorized_request(self) -> None:
        self.assertFalse(request_uses_background("work on this", "http", "auto", "full"))
        self.assertTrue(request_uses_background("work on this", "http", "background", "full"))
        self.assertFalse(request_uses_background("work on this", "http", "background", "restricted"))

    def test_owner_routes_share_history_across_deliveries_and_isolate_debug(self) -> None:
        handler = object.__new__(TextAgentRequestHandler)
        handler.client_address = ("127.0.0.1", 1)
        handler.server = SimpleNamespace(
            config=SimpleNamespace(api_token="test-token", request_timeout=1),
            central_queue=queue.Queue(),
            claim_request=mock.Mock(return_value=True),
        )
        handler.headers = {}
        handler._sleep_phrase_note = lambda *args: None
        handler._publish_turn_banner = mock.Mock()
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler._send_sse = mock.Mock()
        handler._write_json = mock.Mock()
        handler._read_json_body = lambda: {
            "message": "first turn", "source": "imessage", "session_id": "shortcut",
        }

        def accept(message):
            collected_session.append(message.payload.session_id)
            message.payload.reply_queue.put({"ok": True, "response": "Reply"})

        collected_session = []
        handler.server.central_queue.put = accept
        with mock.patch.dict("os.environ", {"BUTLER_HOSTED_DEBUG": "0", "BUTLER_VOICE_SESSION": "voice-worker"}):
            handler._handle_chat()
            handler._read_json_body = lambda: {
                "message": "follow-up", "source": "voice", "session_id": "voice-worker",
            }
            with (
                mock.patch("butler.text.server._stream_state_snapshot", return_value="snapshot"),
                mock.patch("butler.text.server.turn_context", return_value=None),
                mock.patch("butler.text.server.agent_runtime.run_command_stream", return_value=iter(["Reply"])) as run,
            ):
                handler._handle_chat_stream()

            self.assertEqual(run.call_args.kwargs["session_id"], collected_session[0])
            self.assertEqual(resolve_session("sms:test", owner=True), collected_session[0])
            restricted = handler._turn_session("owner", "discord", "restricted")
            self.assertNotEqual(restricted, collected_session[0])
            with mock.patch.dict("os.environ", {"BUTLER_HOSTED_DEBUG": "1"}):
                debug = handler._turn_session("shortcut", "imessage", "full")
                self.assertNotEqual(debug, collected_session[0])
                self.assertEqual(debug, handler._turn_session("voice-worker", "voice", "full"))
                self.assertNotEqual(restricted, handler._turn_session("owner", "discord", "restricted"))
            self.assertEqual(handler._turn_session("shortcut", "imessage", "full"), collected_session[0])


if __name__ == "__main__":
    unittest.main()
