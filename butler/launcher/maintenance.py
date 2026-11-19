"""Explicit maintenance for the active SQLite conversation store."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from butler.storage import database_path

LogFn = Callable[[str, str], None]


def _default_log(source: str, message: str) -> None:
    print(f"[{source}] {message}")


def conversation_db_path() -> Path:
    """The shared application file, resolved exactly as the runtime does."""
    return database_path()


def clear_conversation_memory(log: Optional[LogFn] = None) -> str:
    """Clear conversation tables, including facts; never delete the DB file."""
    log = log or _default_log
    path = conversation_db_path()
    if str(path) == ":memory:":
        return "conversation memory is in-memory; nothing to clear"
    if not path.exists():
        return "no conversation memory file existed"
    from butler.memory.store import MemoryStore

    store = MemoryStore(path)
    try:
        store.clear_all()
    finally:
        store.close()
    log("clear", "cleared conversation history, facts and summaries; jobs/calls preserved")
    return "cleared conversation memory; jobs and phone records preserved"


def clear_chat_history(log: Optional[LogFn] = None) -> str:
    """Clear every session's conversation turns; leave durable facts alone.

    Safe to run with Butler running or stopped: it opens its own connection to
    the same SQLite file (WAL mode tolerates a second, short-lived writer)
    rather than deleting the file, and only removes rows -- ``conversation_sessions``,
    ``conversation_messages``, and each session's summary -- via
    :meth:`MemoryStore.clear_session`, which is the same call the main agent
    itself uses to reset a session. The ``conversation_facts`` table is untouched.
    """

    log = log or _default_log
    path = conversation_db_path()
    if str(path) == ":memory:":
        log("clear", "conversation memory is in-memory only; nothing to clear.")
        return "conversation memory is in-memory; nothing to clear"
    if not path.exists():
        log("clear", f"no conversation memory file found at {path}")
        return "no chat history existed"

    from butler.memory.store import MemoryStore

    store = MemoryStore(path)
    try:
        session_ids = store.list_session_ids()
        for session_id in session_ids:
            store.clear_session(session_id)
    finally:
        store.close()

    if session_ids:
        log("clear", f"cleared chat history for: {', '.join(session_ids)}")
        return f"cleared chat history ({len(session_ids)} session(s): {', '.join(session_ids)})"
    log("clear", "no sessions to clear")
    return "no chat history existed"




def clear_all_memory(log: Optional[LogFn] = None) -> str:
    """Clear the active SQLite conversation store, including saved facts."""
    return clear_conversation_memory(log)
