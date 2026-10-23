from __future__ import annotations

import unittest
from unittest import mock

from butler.voice import agent
from butler.voice.streaming.windows_audio import EndpointPinMismatch


class AecFallbackTelemetryTests(unittest.TestCase):
    """A disabled AEC barge-in lane must be visible outside the console."""

    def test_fallback_emits_unavailable_event_with_endpoint_details(self) -> None:
        fake_source = mock.MagicMock()
        fake_source.__enter__ = mock.Mock(return_value=fake_source)
        fake_source.__exit__ = mock.Mock(return_value=False)
        mismatch = EndpointPinMismatch(
            "Pinned Windows audio endpoint identity does not match.",
            {"capture_pinned_id": "old", "capture_default_id": "new"},
        )

        with mock.patch.object(agent, "_ensure_asr_worker"), mock.patch.object(
            agent, "_ensure_stt_preload_worker"
        ), mock.patch.object(agent, "_ensure_wake_cue_worker"), mock.patch.object(
            agent, "_ensure_polly_keepalive_worker"
        ), mock.patch.object(agent, "_ensure_boot_phrase_worker"), mock.patch.object(
            agent, "_build_profile_microphone", return_value=fake_source
        ), mock.patch.object(agent.r, "adjust_for_ambient_noise"), mock.patch.object(
            agent.r, "listen_in_background", return_value=lambda wait_for_stop=True: None
        ), mock.patch.object(agent, "BARGE_IN_ENABLED", True), mock.patch.object(
            agent, "BARGE_IN_BACKEND", "aec"
        ), mock.patch.object(
            agent, "_start_aec_duplex", side_effect=mismatch
        ), mock.patch.object(agent, "emit_pipeline_event") as emit:
            agent.run_voice_recognition()

        events = [call.kwargs for call in emit.call_args_list]
        unavailable = [e for e in events if e["event"] == "aec_barge_in_unavailable"]
        self.assertEqual(len(unavailable), 1)
        self.assertEqual(unavailable[0]["error_type"], "EndpointPinMismatch")
        self.assertEqual(unavailable[0]["endpoints"]["capture_default_id"], "new")
        self.assertFalse(agent._barge_in_runtime_ready)


if __name__ == "__main__":
    unittest.main()
