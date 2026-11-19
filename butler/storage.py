"""Shared local SQLite lifecycle. Domain stores own their tables and queries."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from butler.config import REPO_ROOT, load_environment
from butler.storage_schema import MIGRATIONS, TABLE_OWNERS


DEFAULT_DB_PATH = REPO_ROOT / "db" / "butler.sqlite3"
BUSY_TIMEOUT_SECONDS = 5.0
APPLICATION_ID = 0x4255544C  # BUTL; reject accidental reuse of unrelated files.


class DatabaseError(RuntimeError):
    """Storage could not open, migrate, or match this application's schema."""


def database_path(override: str | Path | None = None) -> Path | None:
    """One runtime path; explicit :memory: remains available for isolated tests.

    Relative paths are rooted in the repository in every process, independent
    of working directory. Retired per-module environment settings are ignored.
    """
    load_environment()
    selected = str(override) if override is not None else os.getenv("BUTLER_DB_PATH", "").strip()
    selected = selected or str(DEFAULT_DB_PATH)
    if selected == ":memory:":
        if override is None:
            raise DatabaseError("BUTLER_DB_PATH must be a persistent file, not :memory:.")
        return None
    if selected.startswith("file:"):
        raise DatabaseError("Use a filesystem path for BUTLER_DB_PATH, not a SQLite URI.")
    path = Path(selected).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def _checksum(statements: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(statements).encode("utf-8")).hexdigest()


def _enable_wal(connection: sqlite3.Connection) -> None:
    # SQLite may return BUSY immediately when two first-open connections both
    # request the journal-mode change. Bound the retry across processes too.
    deadline = time.monotonic() + BUSY_TIMEOUT_SECONDS
    while True:
        remaining = max(0.0, deadline - time.monotonic())
        connection.execute(f"PRAGMA busy_timeout = {int(remaining * 1000)}")
        try:
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode != "wal":
                raise DatabaseError("Butler database could not enable WAL mode.")
            break
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))
    connection.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_SECONDS * 1000)}")


def _migrate(connection: sqlite3.Connection) -> None:
    """Serialize schema changes across connections/processes; commit atomically."""
    if tuple(m[0] for m in MIGRATIONS) != tuple(range(1, len(MIGRATIONS) + 1)):
        raise DatabaseError("Butler migration versions must be consecutive starting at one.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )}
        if app_id not in (0, APPLICATION_ID):
            raise DatabaseError("Database belongs to another application; choose a clean BUTLER_DB_PATH.")
        if "butler_schema_migrations" not in tables and tables:
            raise DatabaseError("Database has no Butler migration ledger; choose a clean BUTLER_DB_PATH. Legacy stores are not imported.")
        if app_id == 0 and tables:
            raise DatabaseError("Database is missing its Butler application identity.")
        connection.execute("""CREATE TABLE IF NOT EXISTS butler_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )""")
        applied = connection.execute(
            "SELECT version, name, checksum FROM butler_schema_migrations ORDER BY version"
        ).fetchall()
        if len(applied) > len(MIGRATIONS):
            raise DatabaseError("Database schema is newer than this Butler build.")
        for row, migration in zip(applied, MIGRATIONS):
            version, name, statements = migration
            if tuple(row) != (version, name, _checksum(statements)):
                raise DatabaseError("Database migration history does not match this Butler build.")
        for version, name, statements in MIGRATIONS[len(applied):]:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO butler_schema_migrations VALUES (?, ?, ?, ?)",
                (version, name, _checksum(statements), datetime.now(timezone.utc).isoformat()),
            )
        existing = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        if not TABLE_OWNERS.keys() <= existing:
            raise DatabaseError("Butler database is missing required tables; refusing to recreate lost data silently.")
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def connect_database(override: str | Path | None = None) -> sqlite3.Connection:
    """Open an owned connection with shared settings and an up-to-date schema.

    Each store holds its own connection and thread lock. WAL permits concurrent
    readers; SQLite serializes short writes with a bounded five-second wait.
    Callers must close connections and commit/rollback their own transactions.
    """
    path = database_path(override)
    connection = None
    try:
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(path) if path is not None else ":memory:",
            timeout=BUSY_TIMEOUT_SECONDS, check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_SECONDS * 1000)}")
        if path is not None:
            _enable_wal(connection)
        _migrate(connection)
        return connection
    except BaseException as exc:
        if connection is not None:
            connection.close()
        if isinstance(exc, (sqlite3.Error, OSError)):
            raise DatabaseError(f"Butler database initialization failed at {path}: {exc}") from exc
        raise


def initialize_database(override: str | Path | None = None) -> None:
    """Ensure storage is ready before Butler launches its dependent workers."""
    connection = connect_database(override)
    connection.close()


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Dashboard projection: bounded reads, no file creation or migrations."""
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection
