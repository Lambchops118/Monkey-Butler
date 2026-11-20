"""Immutable migrations and explicit table ownership for the unified DB.

Add a new numbered migration for schema changes; never edit an applied migration.
Only currently implemented modules have tables. Cross-module access goes through
its owning store, except explicitly read-only dashboard projections.
"""

TABLE_OWNERS = {
    "conversation_sessions": "conversation",
    "conversation_messages": "conversation",
    "conversation_facts": "conversation",
    "conversation_summaries": "conversation",
    "jobs": "jobs",
    "job_events": "jobs",
    "phone_calls": "phone",
    "phone_call_events": "phone",
    "butler_schema_migrations": "storage",
    "dis_devices": "dis",
    "dis_observations": "dis",
    "dis_health": "dis",
    "wcs_sources": "wcs",
    "wcs_observations": "wcs",
    "wcs_hourly_forecasts": "wcs",
    "ltms_memories": "ltms",
    "ltms_edges": "ltms",
    "ltms_jobs": "ltms",
}

# (version, name, ordered SQL statements). SQL runs in one transaction.
MIGRATIONS = (
    (1, "initial_conversation_jobs_phone", (
        # conversation owns these tables.
        """CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )""",
        """CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
            )""",
        """CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_id
            ON conversation_messages(session_id, id)""",
        """CREATE TABLE IF NOT EXISTS conversation_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                salience INTEGER NOT NULL DEFAULT 5,
                source_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope, key)
            )""",
        """CREATE INDEX IF NOT EXISTS idx_conversation_facts_salience
            ON conversation_facts(salience DESC, updated_at DESC)""",
        """CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope, scope_id)
            )""",
        """CREATE INDEX IF NOT EXISTS idx_conversation_summaries_scope
            ON conversation_summaries(scope, scope_id)""",
        # jobs owns these tables.
        """CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                request_text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                progress_message TEXT,
                result_summary TEXT,
                result_payload_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                requires_user_input INTEGER NOT NULL DEFAULT 0,
                resource_locks_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )""",
        """CREATE INDEX IF NOT EXISTS idx_jobs_session_status
            ON jobs(session_id, status, updated_at DESC)""",
        """CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            )""",
        """CREATE INDEX IF NOT EXISTS idx_job_events_session
            ON job_events(session_id, id)""",
        # phone owns these tables.
        """CREATE TABLE IF NOT EXISTS phone_calls (
                call_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_call_id TEXT,
                conversation_id TEXT,
                agent_id TEXT,
                session_id TEXT,
                direction TEXT NOT NULL,
                remote_number TEXT NOT NULL,
                contact_name TEXT,
                purpose TEXT,
                brief_context TEXT,
                status TEXT NOT NULL,
                outcome TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT,
                last_error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )""",
        """CREATE INDEX IF NOT EXISTS idx_phone_calls_updated
            ON phone_calls(updated_at DESC, call_id DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_phone_calls_provider_call_id
            ON phone_calls(provider_call_id)""",
        """CREATE INDEX IF NOT EXISTS idx_phone_calls_session_id
            ON phone_calls(session_id, updated_at DESC)""",
        """CREATE TABLE IF NOT EXISTS phone_call_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(call_id) REFERENCES phone_calls(call_id) ON DELETE CASCADE
            )""",
        """CREATE INDEX IF NOT EXISTS idx_phone_call_events_call_id
            ON phone_call_events(call_id, id)""",
    )),
    (2, "dis_latest_device_information", (
        """CREATE TABLE dis_devices (
            device_id TEXT PRIMARY KEY, name TEXT NOT NULL, adapter TEXT NOT NULL,
            config_json TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))""",
        """CREATE TABLE dis_observations (
            device_id TEXT NOT NULL REFERENCES dis_devices(device_id) ON DELETE CASCADE,
            property_name TEXT NOT NULL, value_json TEXT NOT NULL, received_at REAL NOT NULL,
            evidence_id TEXT NOT NULL, PRIMARY KEY(device_id, property_name))""",
        """CREATE TABLE dis_health (
            device_id TEXT PRIMARY KEY REFERENCES dis_devices(device_id) ON DELETE CASCADE,
            last_attempt REAL NOT NULL, last_success REAL, error TEXT)""",
    )),
    (3, "dis_passive_source_provenance", (
        "ALTER TABLE dis_observations ADD COLUMN source TEXT NOT NULL DEFAULT 'kasa_local_read'",
        "ALTER TABLE dis_observations ADD COLUMN retained INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE dis_observations ADD COLUMN boot_id TEXT",
        "ALTER TABLE dis_observations ADD COLUMN source_sequence INTEGER",
        "ALTER TABLE dis_health ADD COLUMN status TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE dis_health ADD COLUMN boot_id TEXT",
        "ALTER TABLE dis_health ADD COLUMN last_contact REAL",
    )),
    (4, "wcs_latest_observations", (
        """CREATE TABLE wcs_sources (
            category TEXT PRIMARY KEY, config_json TEXT NOT NULL, status TEXT NOT NULL,
            last_attempt REAL, last_success REAL, next_poll REAL,
            errors_json TEXT NOT NULL DEFAULT '[]', failures INTEGER NOT NULL DEFAULT 0)""",
        """CREATE TABLE wcs_observations (
            category TEXT NOT NULL REFERENCES wcs_sources(category) ON DELETE CASCADE,
            subject TEXT NOT NULL, kind TEXT NOT NULL, observed_at REAL, received_at REAL NOT NULL,
            data_json TEXT NOT NULL, PRIMARY KEY(category, subject, kind))""",
    )),
    (5, "wcs_hourly_forecasts", (
        """CREATE TABLE wcs_hourly_forecasts (
            category TEXT NOT NULL REFERENCES wcs_sources(category) ON DELETE CASCADE,
            valid_from REAL NOT NULL, data_json TEXT NOT NULL,
            PRIMARY KEY(category, valid_from))""",
    )),

    (6, "ltms_graph", (
        """CREATE TABLE ltms_memories (
            id TEXT PRIMARY KEY, content TEXT NOT NULL, source TEXT NOT NULL,
            updated_at REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
            embedding TEXT, embedding_model TEXT)""",
        """CREATE TABLE ltms_edges (
            source_id TEXT NOT NULL REFERENCES ltms_memories(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES ltms_memories(id) ON DELETE CASCADE,
            relation TEXT NOT NULL, PRIMARY KEY(source_id,target_id,relation))""",
        "CREATE INDEX ltms_edge_target ON ltms_edges(target_id)",
        """CREATE TABLE ltms_jobs (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
            error TEXT, created_at REAL NOT NULL)""",
    )),

)
