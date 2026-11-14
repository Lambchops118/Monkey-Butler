from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]

# Secrets and machine-specific credentials only (API keys, tokens, passwords).
# Git-ignored; created from .env.example.
ENV_PATH = REPO_ROOT / ".env"

# Everything else: hosts, ports, model names, feature flags, timeouts. Committed
# to the repo, fully populated with defaults, and safe to edit/share.
SETTINGS_PATH = REPO_ROOT / "settings.env"


# settings.env carries the Windows deploy host's audio device names and pinned
# MMDevice IDs. On other platforms, seed Linux-appropriate values first; because
# load_dotenv never overrides existing variables, these beat settings.env, while
# real shell exports still beat both.
POSIX_DEFAULTS = {
    "BUTLER_RESPEAKER_DEVICE_NAME": "alsa_input.usb-Seeed_Studio_reSpeaker",
    "BUTLER_RESPEAKER_OUTPUT_DEVICE_NAME": "alsa_output.usb-Seeed_Studio_reSpeaker",
    "BUTLER_RESPEAKER_CAPTURE_ENDPOINT_ID": "",
    "BUTLER_YETI_CAPTURE_ENDPOINT_ID": "",
    "BUTLER_AUDIO_CAPTURE_ENDPOINT_ID": "",
    "BUTLER_AUDIO_RENDER_ENDPOINT_ID": "",
    "BUTLER_DISPLAY_FULLSCREEN": "1",
}


def apply_platform_defaults() -> None:
    if os.name == "nt":
        return
    for key, value in POSIX_DEFAULTS.items():
        os.environ.setdefault(key, value)


def load_environment() -> None:
    apply_platform_defaults()
    # Load non-secret settings first, then secrets. Neither call overrides a
    # variable already present in the real process environment, so an explicit
    # shell export still wins over both files. The two files hold disjoint keys.
    load_dotenv(dotenv_path=SETTINGS_PATH)
    load_dotenv(dotenv_path=ENV_PATH)


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def require_env(name: str) -> str:
    load_environment()
    if not ENV_PATH.exists():
        raise RuntimeError(
            f"Missing environment file: {ENV_PATH}. "
            "Create it from .env.example and add the required credentials."
        )

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set in {ENV_PATH}. "
            "Add it to that file and restart Butler."
        )
    return value

