"""Resolve trusted adapter inputs to the shared owner conversation."""

import os
from uuid import uuid4

from butler.config import env_bool


OWNER_CONVERSATION = "owner"
_DEBUG_NAMESPACE = f"debug:{uuid4().hex}"


def voice_session_id() -> str:
    return os.getenv("BUTLER_VOICE_SESSION", "voice-worker")


def resolve_session(session_id: str, *, owner: bool) -> str:
    hosted = env_bool("BUTLER_HOSTED_DEBUG", False)
    if owner:
        return f"{_DEBUG_NAMESPACE}:{OWNER_CONVERSATION}" if hosted else OWNER_CONVERSATION
    namespace = _DEBUG_NAMESPACE if hosted else "isolated"
    return f"{namespace}:channel:{session_id}"
