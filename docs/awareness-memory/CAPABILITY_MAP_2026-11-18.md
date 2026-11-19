# Awareness subsystem capability map — 2026-11-18

This is a source-based overview, not an assertion that all capabilities are operational. During the immediately preceding investigation, the API reported database unreachable. No live health recheck was performed for this overview.

| System | Implemented responsibility | Boundary / practical limitation |
|---|---|---|
| Entity/source registry | Device identity, locations, owned topics, source authority/freshness settings | No general device discovery or automatic adapter creation |
| Ingestion and provenance | Registered MQTT and internal/manual events; validation, deduplication, ordering/boot tracking, rejected-event ledger | Only modeled/registered inputs; no arbitrary household data understanding; not lossless during DB outages |
| Current-state manager | Latest property values with freshness, confidence, source and conflict qualification | Database observations, not proof of physical reality; no on-demand Kasa polling |
| Source-health worker | Detect silence, offline/recovery and associated alerts | Connectivity does not prove mechanical health |
| Structured history/telemetry | Event timelines, state transitions, numeric measurements and aggregate queries | Only collected signals, bounded windows and retention; simulator data must not be confused with real sensors |
| Rule engine | Deterministic overflow/all-clear rules, source-offline handling, failed-job attention | No general LLM anomaly reasoning; configured overflow rule does not establish installed overflow sensing; recommended stop is not automatic actuation |
| Alert/attention management | Persistent incident deduplication, acknowledgement/resolution, urgency, quiet hours and cooldown | Attention scheduling and incident truth are separate; acknowledgement is not resolution |
| Notification outbox | Durable bounded retries and delivery attempts through voice/display/log adapters | Adapter acceptance is not proof of playback or human receipt; not exactly-once delivery |
| Reminders | Durable timestamped reminders, due worker, listing/cancellation | LLM interprets natural-language time; not general recurring automation or job execution |
| Situation broker and model read tools | Automatic bounded context plus explicit state/event/telemetry/health/provenance tools | Actual prompt audit showed announcements crowding out device facts; failure may omit context; no complete-house snapshot |
| Human/agent context | Owner interaction/presence observations, explicit presence changes, job outcomes and tool failures | No room tracking, multi-person identity proof, continuous physical presence sensing, or raw conversation transcript storage in awareness |
| Long-term memory | Facts/preferences and incident episodes, evidence, validity/supersession, candidates, local embeddings and hybrid search | Separate from SQLite chat history/prompt memory; awareness memories are not automatically all injected; existence of pipeline does not establish useful populated memory |
| Registered physical actions | Fan and legacy/canonical pump commands, validation, permissions, configured confirmations, timeouts, acknowledgement/state confirmation and audit | Not all household controls use it (Kasa light tools are separate); hardware/firmware owns immediate interlocks; no arbitrary command executor |
| Proactive briefings | Scheduled/arrival-triggered summaries, bounded catch-up, deduplication, preferences, optional local model ranking and deterministic fallback | Not general autonomous work; arrival is inferred from owner signals, not proven physical arrival; numeric novelty needs adequate history; production acceptance remains pending |
| Operations | Health/metrics, retention, aggregate refresh, memory consolidation, artifact checksums, backup/restore commands | CLI availability does not install/run a maintenance schedule; database/Docker availability is a shared dependency |

Known primary inputs: legacy fan Pico, legacy and canonical pump controller, development simulator, and internal owner/agent signals. Pot records do not establish that each pot has a live sensor. Lights are controlled separately and have no state-ingestion adapter found in the inspected code.

Deployment shape: separate local Python service (port 8600), local Docker PostgreSQL/TimescaleDB/pgvector (5433), existing Pi MQTT broker, main-agent HTTP/MCP clients, existing voice/display delivery adapters, optional local Ollama for memory embeddings/briefing selection. Alert detection and ordinary notification wording do not require LLM inference; speech still depends on the existing output stack. Current settings enable MQTT, situation injection and proactive briefings, but settings do not prove a healthy running deployment.

External boundaries: main conversation engine and SQLite conversation store, STT/wake word/TTS and interruption, device firmware, MQTT broker, general agent tools/integrations and background job execution are not owned by awareness. Awareness records selected signals/results and calls established delivery/action interfaces.

Evidence: butler/awareness/README.md (component sections), api/app.py (registered routes/workers), registry/bootstrap.py, rules/rules.toml, actions/actions.toml, mcp_servers/providers/awareness.py, and PER_TURN_AWARENESS_2026-11-18.md (observed effectiveness). README prose includes historical assumptions, so current configuration/code and measured evidence take precedence; in particular, presence expiry cannot be inferred solely from its older README description.

Verification: targeted source/document/config inspection only; no tests, service probes, model calls, actions, or deployment run for this overview. Stop at capability mapping; no archive/removal or runtime changes authorized or performed.
