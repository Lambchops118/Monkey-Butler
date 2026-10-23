import unittest

import numpy as np

from butler.voice.streaming.windows_audio import (
    EndpointPinMismatch,
    WindowsAudioEndpointInfo,
    WindowsAudioEndpoints,
    normalize_audio_graph_pcm,
    parse_mmdevice_endpoint_id,
    resolve_pinned_windows_audio_endpoints,
)


class NormalizeAudioGraphPcmTests(unittest.TestCase):
    def test_converts_one_float32_quantum_to_pcm16(self):
        native = np.array([-1.0, -0.5, 0.0, 0.5, 1.0], dtype=np.float32).tobytes()

        pcm = normalize_audio_graph_pcm(
            native,
            samples_per_quantum=5,
            channels=1,
        )

        self.assertEqual(
            np.frombuffer(pcm, dtype=np.int16).tolist(),
            [-32767, -16383, 0, 16383, 32767],
        )

    def test_leaves_unexpected_frame_shape_unchanged(self):
        pcm = b"\x01\x02" * 5

        self.assertIs(
            normalize_audio_graph_pcm(
                pcm,
                samples_per_quantum=5,
                channels=1,
            ),
            pcm,
        )


def _capture_id(guid):
    return (
        r"\\?\SWD#MMDEVAPI#{0.0.1.00000000}.{" + guid + "}"
        "#{2eef81be-33fa-4800-9670-1cd474972c3f}"
    )


def _render_id(guid):
    return (
        r"\\?\SWD#MMDEVAPI#{0.0.0.00000000}.{" + guid + "}"
        "#{e6327cad-dcec-4949-ae8a-991e976a79d2}"
    )


RESPEAKER = "Echo Cancelling Speakerphone (reSpeaker XVF3800 4-Mic Array)"
BENQ = "BenQ GL2460 (HD Audio Driver for Display Audio)"
OLD_CAPTURE = _capture_id("de76a30a")
NEW_CAPTURE = _capture_id("0670a5da")
RENDER = _render_id("d43b40c9")


class ResolvePinnedEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.devices = {
            NEW_CAPTURE: WindowsAudioEndpointInfo(NEW_CAPTURE, "capture", RESPEAKER, True),
            RENDER: WindowsAudioEndpointInfo(RENDER, "render", BENQ, True),
        }
        self.name_counts = {("capture", RESPEAKER): 1, ("render", BENQ): 1}

    def resolve(self, pinned, defaults, **names):
        return resolve_pinned_windows_audio_endpoints(
            pinned,
            defaults,
            describe=self.devices.get,
            count_active_named=lambda flow, name: self.name_counts.get((flow, name), 0),
            **names,
        )

    def test_exact_pins_are_accepted_without_names(self):
        pair = WindowsAudioEndpoints(NEW_CAPTURE, RENDER)

        result = self.resolve(pair, pair)

        self.assertEqual(result.endpoints, pair)
        self.assertEqual((result.capture, result.render), ("pinned", "pinned"))
        self.assertFalse(result.reenumerated)

    def test_mismatch_without_pinned_name_still_fails_closed(self):
        with self.assertRaises(EndpointPinMismatch) as caught:
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
                WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
            )

        self.assertEqual(caught.exception.details["capture_pinned_id"], OLD_CAPTURE)
        self.assertEqual(caught.exception.details["capture_default_id"], NEW_CAPTURE)
        self.assertEqual(caught.exception.details["capture_default_name"], RESPEAKER)

    def test_follows_reenumerated_device_with_matching_name(self):
        result = self.resolve(
            WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
            WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
            capture_name=RESPEAKER.lower(),
        )

        self.assertEqual(result.endpoints, WindowsAudioEndpoints(NEW_CAPTURE, RENDER))
        self.assertEqual((result.capture, result.render), ("reenumerated", "pinned"))
        self.assertTrue(result.reenumerated)
        self.assertEqual(result.details["capture_resolution"], "reenumerated")

    def test_refuses_when_pinned_endpoint_is_still_active(self):
        # The owner picked a different default; the pinned device still exists.
        self.devices[OLD_CAPTURE] = WindowsAudioEndpointInfo(
            OLD_CAPTURE, "capture", RESPEAKER, True
        )

        with self.assertRaisesRegex(EndpointPinMismatch, "still active"):
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
                WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
                capture_name=RESPEAKER,
            )

    def test_refuses_a_different_device_name(self):
        yeti = _capture_id("1783577d")
        self.devices[yeti] = WindowsAudioEndpointInfo(
            yeti, "capture", "Microphone (Yeti Stereo Microphone)", True
        )

        with self.assertRaisesRegex(EndpointPinMismatch, "name differs"):
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
                WindowsAudioEndpoints(yeti, RENDER),
                capture_name=RESPEAKER,
            )

    def test_refuses_an_ambiguous_name(self):
        self.name_counts[("capture", RESPEAKER)] = 2

        with self.assertRaisesRegex(EndpointPinMismatch, "not unique"):
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
                WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
                capture_name=RESPEAKER,
            )

    def test_refuses_an_inactive_default(self):
        self.devices[NEW_CAPTURE] = WindowsAudioEndpointInfo(
            NEW_CAPTURE, "capture", RESPEAKER, False
        )

        with self.assertRaisesRegex(EndpointPinMismatch, "not an active endpoint"):
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, RENDER),
                WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
                capture_name=RESPEAKER,
            )

    def test_render_side_follows_independently(self):
        old_render = _render_id("2b69dbdf")

        result = self.resolve(
            WindowsAudioEndpoints(NEW_CAPTURE, old_render),
            WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
            render_name=BENQ,
        )

        self.assertEqual(result.endpoints.render_id, RENDER)
        self.assertEqual((result.capture, result.render), ("pinned", "reenumerated"))

    def test_reports_failures_on_both_sides(self):
        with self.assertRaises(EndpointPinMismatch) as caught:
            self.resolve(
                WindowsAudioEndpoints(OLD_CAPTURE, _render_id("2b69dbdf")),
                WindowsAudioEndpoints(NEW_CAPTURE, RENDER),
            )

        self.assertIn("capture:", str(caught.exception))
        self.assertIn("render:", str(caught.exception))


class ParseEndpointIdTests(unittest.TestCase):
    def test_parses_flow_and_guid(self):
        self.assertEqual(
            parse_mmdevice_endpoint_id(NEW_CAPTURE), ("capture", "{0670a5da}")
        )
        self.assertEqual(parse_mmdevice_endpoint_id(RENDER), ("render", "{d43b40c9}"))

    def test_rejects_malformed_ids(self):
        self.assertIsNone(parse_mmdevice_endpoint_id(""))
        self.assertIsNone(parse_mmdevice_endpoint_id("Microphone"))


if __name__ == "__main__":
    unittest.main()
