# Archived awareness subsystem

Retired on 2026-11-18 at the owner's request. This directory is historical
reference, not an application package or an independently runnable deployment.
The implementation also remains in Git history/main.

The original relative paths are preserved beneath this directory: backend,
migrations, rules/action definitions, HTTP/MCP clients, signal producer,
awareness-only tests, database Compose file, and dependency manifest. Mixed
home-automation modules are saved under `integration-reference/` as text. The
original imports and relative paths inside archived files deliberately remain
historical; do not add this directory to `PYTHONPATH` or restore its workers to
the active launcher. `SOURCE_MANIFEST.json` records the archived file hashes.

## Active changes

- Butler's launcher no longer starts PostgreSQL, migrations or the awareness API.
  Old saved launcher keys are ignored. The GUI and CLI expose no awareness
  start/clear controls. Normal startup no longer requires Docker for awareness.
- Conversation, voice, jobs and phone handling no longer fetch awareness context,
  emit presence/outcome signals, or mirror saved facts into PostgreSQL.
- The live MCP catalog excludes awareness reads/memory, reminders, briefings,
  action requests and legacy pump/fan tools. No direct MQTT bypass replaces the
  retired action authority. Independent light/time/weather/display tools remain.
- Dashboard compatibility fields explicitly report `archived`; they do not poll
  the old API or classify retirement itself as a service failure.
- Generic announcement endpoints and the existing display scheduler remain;
  retaining transport endpoints does not enable archived producers.
- SQLite conversation history, paired tool history, saved facts, conversation
  identity and current-time injection remain active. Existing physical-action
  truthfulness guards remain defensive code; no retired tool is registered.

## Capabilities retired

Automatic household snapshots; awareness state/event/telemetry reads and source
health; overflow/offline alerts and attention; awareness notification/retry
workers; reminders; morning/arrival briefings; human-presence recording;
PostgreSQL long-term memory/vector retrieval; and registered pump/fan execution.
The phone house-status endpoint reports unavailable without an injected provider.
None of these functions has a replacement in this change.

## Data and deployment

No databases, Docker containers/volumes, backups, local environments, model files,
credentials, firmware or hardware were removed or changed. The active `.env`
may still contain unused legacy credentials; it is not read by an awareness
client anymore. Archived maintenance commands are not active data-management
options. No running process was stopped or restarted, so restart Butler and its
MCP children to load the retirement. A previously launched awareness process is
outside the new launcher's lifecycle; stop that old process separately if it is
still running. Existing database data was not exported or migrated.

Historical design/status/session records remain under
[`docs/awareness-memory`](../../docs/awareness-memory/IMPLEMENTATION_STATUS.md).
Their older source links and acceptance claims describe the retired system.
Do not begin a replacement implementation without a separately bounded task.

## Verification

See [retirement validation](../../docs/awareness-memory/RETIREMENT_2026-11-18.md)
for exact test commands, results, limitations and the stop condition.
