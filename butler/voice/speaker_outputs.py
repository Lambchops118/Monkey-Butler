"""Speaker output choices shared by the launcher and voice worker.

``system`` keeps the old behaviour: the backend's default output device (or
``BUTLER_AUDIO_OUTPUT_DEVICE_INDEX``). ``respeaker`` plays through the
XVF3800's own USB playback, which drives the speaker on its JST connector. The
chip uses that playback as its echo-cancellation reference, so the ReSpeaker's
ASR channel is echo-cleaned on the chip itself and barge-in works with no host
AEC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpeakerOutput:
    name: str
    label: str
    device_name_env: str
    default_device_name: str
    # True when the device's own AEC cancels this output on the matching mic.
    hardware_aec_microphone: str


SPEAKER_OUTPUTS = {
    "system": SpeakerOutput(
        name="system",
        label="System default output",
        device_name_env="",
        default_device_name="",
        hardware_aec_microphone="",
    ),
    "respeaker": SpeakerOutput(
        name="respeaker",
        label="ReSpeaker XVF3800 JST speaker",
        device_name_env="BUTLER_RESPEAKER_OUTPUT_DEVICE_NAME",
        default_device_name="Echo Cancelling Speakerphone",
        hardware_aec_microphone="respeaker",
    ),
}

DEFAULT_SPEAKER_OUTPUT = "system"


def normalize_speaker_output(value: object) -> str:
    name = str(value or "").strip().lower()
    return name if name in SPEAKER_OUTPUTS else DEFAULT_SPEAKER_OUTPUT


def get_speaker_output(value: object) -> SpeakerOutput:
    return SPEAKER_OUTPUTS[normalize_speaker_output(value)]


def uses_hardware_aec(speaker: object, microphone: object) -> bool:
    """True when this speaker/mic pair is echo-cancelled on the device itself."""

    output = get_speaker_output(speaker)
    mic = str(microphone or "").strip().lower()
    return bool(output.hardware_aec_microphone) and output.hardware_aec_microphone == mic


def find_output_device_index(audio: Any, name_contains: str) -> int:
    """Index of the first PortAudio output whose name contains ``name_contains``."""

    needle = name_contains.strip().lower()
    if not needle:
        raise ValueError("name_contains must not be empty")
    for index in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(index)
        name = str(info.get("name") or "").lower()
        if needle in name and int(info.get("maxOutputChannels") or 0) > 0:
            return index
    raise RuntimeError(f"No audio output device containing '{name_contains}' was found.")
