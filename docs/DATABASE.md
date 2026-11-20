# Butler application database

Implemented 2026-11-18. All active persistent stores use one local SQLite file:
`db/butler.sqlite3`. This is application infrastructure, not a revived awareness
backend. No Docker, database server, vector extension or new dependency is needed.

> DIS update: migration 2 adds three implemented DIS tables; migration 3 adds passive-source provenance and health metadata. See [DIS.md](DIS.md).
> WCS update: migration 4 adds latest observations and durable source schedules; migration 5 adds the bounded latest hourly forecast series. See [WCS.md](WCS.md).
> The original storage-unification validation below remains a historical record.

## Startup and configuration

`butler.main.main()` calls `initialize_database()` before starting the router,
servers or scheduler. It creates the parent/file when missing, applies numbered
migrations atomically, and closes its bootstrap connection. Domain stores then
open their own connections using the same configuration. Database initialization
failure stops startup before workers begin. SQLite starts when Butler opens it;
this change does not install Windows boot/login scheduling for Butler itself.

Set `BUTLER_DB_PATH` in `settings.env` or the process environment to change the
file. Relative paths resolve against the repository root, consistently across
processes and working directories. The previous `BUTLER_MEMORY_DB_PATH`,
`BUTLER_JOBS_DB_PATH` and `BUTLER_PHONE_DB_PATH` variables are no longer read.
Domain constructors accept an explicit path or `:memory:` for isolated testing
and dependency injection. A global `:memory:` environment setting is rejected:
independent connections would not share the intended application database.

All connections enable foreign keys, a five-second busy timeout, full synchronous
writes and WAL for on-disk storage. A bounded retry handles concurrent first-open
journal initialization; migrations use `BEGIN IMMEDIATE` to serialize across
processes. Each store has its own connection/thread lock and uses short write
transactions with rollback on failure. Network/model work must stay outside
transactions. SQLite still has one writer at a time; heavy future telemetry
would require measurement before choosing another storage design.

## Ownership and current tables

| Owner | Tables |
|---|---|
| Conversation (`MemoryStore`) | `conversation_sessions`, `conversation_messages`, `conversation_facts`, `conversation_summaries` |
| Jobs (`JobStore`) | `jobs`, `job_events` |
| Phone (`PhoneCallStore`) | `phone_calls`, `phone_call_events` |
| DIS | `dis_devices`, `dis_observations`, `dis_health` |
| WCS | `wcs_sources`, `wcs_observations`, `wcs_hourly_forecasts` |
| LTMS | `ltms_memories`, `ltms_edges`, `ltms_jobs` |
| Storage | `butler_schema_migrations` |

Conversation records retain real paired tool exchanges/schema metadata and
interruption semantics. Sharing storage does not merge conversational memory
with another product module. Initial unification created no speculative tables. DIS now owns only the
registry/latest-observation/contact tables implemented in its first release;
WCS owns latest timestamped observations and source polling metadata only.
Future semantic-memory/history tables are still absent.

`butler/storage_schema.py` defines the ownership map and immutable migration
statements. `butler/storage.py` owns path resolution, connection settings,
read-only connections and migration execution. Domain stores own their records
and business queries; access another domain through its interface. The dashboard
is an explicit exception for bounded read-only projections: it uses a
non-creating, query-only connection and never migrates a database.

Ownership is an application convention enforced by module interfaces and tests,
not separate SQLite security roles. An internal connection can technically read
every table. Keep cross-owner foreign keys and cascading deletes out unless an
explicitly reviewed requirement justifies their lifecycle coupling.

## Adding a module or changing schema

1. Implement only the currently assigned module's storage contract.
2. Add its table ownership entries and append the next numbered migration with
   ordered SQL statements. Do not modify an applied migration: names/checksums
   are validated on open and versions must be consecutive.
3. Use shared connection/path helpers and the module's store interface. Do not
   add per-module runtime file settings, ad-hoc `CREATE TABLE` calls, independent
   SQLite connection policies or speculative future tables.
4. Test atomic migration, reopening, foreign keys, contention/error recovery and
   clearing isolation from existing owners. Back up valuable future data before
   upgrading a deployment; automatic migration is not automatic backup.

Application identity and the migration ledger reject unrelated/legacy database
files, newer/inconsistent history, and missing required tables. A missing table
is reported rather than silently recreated with lost contents. The checks do
not replace full corruption recovery or verify every manually altered column.

## Clean cutover and clearing

The owner explicitly waived old data preservation/import. The new database was
initialized clean with eight empty domain tables, one schema-migration record,
and a passing SQLite integrity check. The three old database files were left in
place and are not imported or selected by runtime defaults; their size/mtime
metadata was checked unchanged during bootstrap. Archived awareness PostgreSQL
data is also outside this change. Explicitly pointing the shared path at a
legacy store fails with an instruction to select a clean file.

The launcher/CLI memory-clear operations delete only conversation-owned rows.
They never unlink the shared file or its WAL/SHM sidecars:

- Clear conversation memory: history, facts and summaries; jobs, call records
  and the migration ledger survive.
- Clear chat history: session dialogue/tool history and session summaries;
  explicit facts, jobs and call records survive.

Do not copy/delete just the main SQLite file while active WAL connections exist.
For future backups use SQLite's backup API, or stop all writers and use a
consistent offline procedure. This task adds no backup scheduler or general
whole-application reset command.

Already-running Butler/MCP/dashboard processes need a restart to select the new
code/path. No process was restarted and no phone call, device command or model
request was sent during this implementation. Old files may be archived/deleted
later independently; they are not required by the new runtime.

## Validation

All commands use `.venv-runtime/Scripts/python.exe -m unittest discover -s tests
-p PATTERN -q`, with local sockets permitted for fixtures that require them:

| Pattern | Final result |
|---|---:|
| `test_unified_storage.py` | 12 passed |
| `test_memory_store.py` | 11 passed |
| `test_jobs.py` | 3 passed |
| `test_phone_store.py` | 1 passed |
| `test_launcher*.py` | 28 passed |
| `test_run_command_stream.py` | 17 passed |
| `test_phone_service.py` | 11 passed |
| `test_agent_runtime_phone_tools.py` | 4 passed |
| `test_elevenlabs_twilio_provider.py` | 4 passed |
| `test_debug_dashboard.py` | 17 passed |
| `test_awareness_retirement.py` | 5 passed |
| `test_text_server*.py` | 26 passed |
| `test_phone_inbound_server.py` | 18 passed |
| `test_router*.py` | 13 passed |

Total: **170 passing cases**, zero final failures/skips. Tests exercise real
temporary SQLite files for shared persistence, tool-history continuity,
concurrent first-open/writes, contention timeout/recovery, schema failure
rollback, unsupported/legacy schemas, read-only behavior, startup failure and
module-specific clearing. Provider/network effects are mocked/local fixtures.

The first new-storage run exposed one real journal initialization race and two
test cleanup errors from SQLite context managers not closing connections on
Windows. Bounded WAL retry and explicit fixture connection closure fixed them;
the final 12-case suite passed. A subsequent phone-provider rerun caught removal
of a legacy constructor field; its compatibility field was restored while runtime
selection stays on the unified path, and all 19 phone cases passed again.
The existing audioop deprecation warning was
not suppressed. No tests were weakened.

Python compilation, changed-document local-link checks, and Git whitespace
checks passed. Full repository tests, live LLM/voice/GUI/phone/device acceptance,
process deployment/restart, and importing old data were not run. The previously
recorded unrelated personality assertion was not included in this bounded run.

Stop at unified storage. New product systems, data import, whole-database reset
and startup-service installation are separate assignments.

Migration 6 implements LTMS; see [LTMS.md](LTMS.md). Legacy fact tables remain
for schema compatibility but no longer feed agent recall. No fact import.
