import unittest

from butler.launcher.config import LauncherConfig
from butler.launcher.core import _microphone_env
from butler.voice.speaker_outputs import (
    find_output_device_index,
    normalize_speaker_output,
    uses_hardware_aec,
)


class _Audio:
    devices = [
        {"name": "Default Sink", "maxOutputChannels": 32},
        {"name": "alsa_output.usb-Seeed_Studio_reSpeaker.monitor", "maxOutputChannels": 0},
        {"name": "alsa_output.usb-Seeed_Studio_reSpeaker_XVF3800", "maxOutputChannels": 2},
    ]

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        return self.devices[index]


class SpeakerOutputTests(unittest.TestCase):
    def test_unknown_output_falls_back_to_system(self):
        self.assertEqual(normalize_speaker_output("bogus"), "system")

    def test_hardware_aec_needs_matching_mic(self):
        self.assertTrue(uses_hardware_aec("respeaker", "respeaker"))
        self.assertFalse(uses_hardware_aec("respeaker", "yeti"))
        self.assertFalse(uses_hardware_aec("system", "respeaker"))

    def test_finds_named_output_skipping_inputs(self):
        self.assertEqual(find_output_device_index(_Audio(), "Seeed_Studio_reSpeaker"), 2)

    def test_launcher_keeps_barge_in_for_jst_speaker(self):
        cfg = LauncherConfig(microphone_profile="respeaker", speaker_output="respeaker")
        env = _microphone_env(
            {"BUTLER_BARGE_IN": "1", "BUTLER_AUDIO_OUTPUT_DEVICE_INDEX": "4"}, cfg
        )
        self.assertEqual(env["BUTLER_SPEAKER_OUTPUT"], "respeaker")
        self.assertEqual(env["BUTLER_BARGE_IN"], "1")
        self.assertNotIn("BUTLER_AUDIO_OUTPUT_DEVICE_INDEX", env)


if __name__ == "__main__":
    unittest.main()
