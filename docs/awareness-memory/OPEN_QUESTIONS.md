# Open Questions

## Wake-only voice product choices (2026-11-10)

See [`voice_wake_interaction_requirements_11102026.md`](../../voice_wake_interaction_requirements_11102026.md).
The deployed-host response timing target, exact wake/listening feedback,
listening-window duration, and policy for continuing conversation after a
completed answer remain open. The coding agent must choose implementation
mechanics within the documented behavior and repository invariants; no design
choice is implied by this requirements record.

## Model interaction surface choices (2026-11-10)

See [`interaction_surface_rework_11102026.md`](../../interaction_surface_rework_11102026.md).
Choose whether the eventual public API has one endpoint with negotiated output
or two thin endpoints over one controller; decide how terminal, browser, and SMS
show asynchronous completion; define partial-output/error presentation; and
specify an explicit hosted-debug control without accidental remote fallback.
No runtime choice is implied by the documentation proposal.

## Foreground/background rework choices (2026-11-10)

The proposed design is in
[`background_rework_11102026.md`](../../background_rework_11102026.md).
Before implementation rollout, establish the acceptable foreground first-speech
and concurrent-turn latency on the Linux/ReSpeaker host; decide the default
delivery timing for background completion; measure model/context/tool fit and
quality on the A2000; and define cancellation and restart behavior for jobs
whose external effects may already have happened. No GPU layout or background
model has been selected yet.

## Tool-history repair acceptance (2026-09-21)

The no-op lights tool is removed and structured local streaming history is
implemented (ADR-055). Owner acceptance still needs deployed local-model trials:
long/contaminated histories, stale observations, failed tools, keyword-free
follow-ups, and latency. Check whether the existing 8-message/4000-character
history budget omits useful large tool turns before changing it. No new model
accuracy or latency claim is made by unit-test success.

Deployment clarification is confirmed: local inference, AWS Polly speech as the
current hosted exception. Hosted inference remains a separate future decision.

## Architecture consultation follow-up (2026-09-21)

Tool review follow-up: choose the authoritative catalog and initial always-visible
capabilities; agree mutation retry/unknown-outcome policy and result contracts;
define which display surfaces/content types the agent may present. See
[tool review](../TOOL_SYSTEM_REVIEW.md). These are design decisions for future
work, not requests to start a migration.

The [review](../ARCHITECTURE_REVIEW.md) is complete; these questions constrain
future implementation rather than block the consultation.

- What model, quantization, and chat/tool template actually run under
  `mb-core-v1:latest`? Owner description and historical diagnostics differ.
- Is cloud audio acceptable for an isolated comparison or eventual optional
  operation? Until decided, preserve local-first behavior.
- What foreground/background GPU memory and scheduling budget is available on
  the deployed host, and what useful-response/interrupt latency is acceptable?
- Which proactive actions may Talos initiate under standing authorization, and
  which should remain suggestions or require confirmation?
- Which existing store owns durable user/project facts versus conversation and
  episodic records? Agree ownership before proposing a data migration.

Choose a bounded work package from the review before runtime implementation.

These questions require Phase 0 repository/deployment evidence or owner input. Confirmed source facts—local-first operation, reuse of the existing Mosquitto broker, central database authority, and deterministic safety behavior—are not open.

## Phase 9 follow-up (2026-09-06)

- **OQ-M — Resolved.** Owner explicitly authorized continuation through 9D
  without further pauses except for critical issues (2026-09-06).
- **OQ-N — Resolved for implementation by ADR-036.** Critical overflow uses
  separately capped durable batches. Existing ordinary critical notifications
  remain independent. Receipts represent adapter acceptance, never confirmed
  playback or exactly-once delivery.
- **OQ-O — Production acceptance remains open.**
  ADR-040 adds receipt-based announcement recall; owner-visible follow-up voice
  testing is still needed after restart, using a newly delivered test briefing.
  Historical receipts do not gain reconstructed wording. Measure voice latency against
  p50 1238 ms / p95 2541 ms and verify real morning/arrival/feedback behavior
  after opt-in rollout. The acknowledgement bug is fixed: `/speak` now routes
  supplied text as an announcement without model phrasing, but confirms enqueue
  only. ADR-039 also replaces spoken diagnostic briefing strings with concise
  factual rendering; restart awareness backend before retesting. Real playback
  and voice latency still need owner-visible verification.
  No live speech session, production model interruption, or latency benchmark
  was performed during Phase 9 implementation.

| ID | Question | Why it matters | Evidence / owner decision needed | Recommended starting interpretation |
|---|---|---|---|---|
| OQ-001 | What language, runtime, dependency manager, formatter, linter, type checker, entry points, and module boundaries are established? | Determines additive integration and tooling. | Repository inspection. | Use established suitable patterns before defaults. |
| OQ-002 | What database/ORM/migration/storage/cache code exists, and what can the target host deploy? | Determines whether defaults fit. | Repo and host/deployment evidence. | PostgreSQL is required by default; validate TimescaleDB and pgvector suitability. |
| OQ-003 | Can TimescaleDB and pgvector run reliably on the central host? | Affects telemetry and semantic retrieval. | Host resources, packaging, backups, operational constraints. | Use them when feasible; any local substitute must preserve section 5.4 properties. |
| OQ-004 | Is Home Assistant present, and who owns state, events, registry, recorder, and automations? | Avoids duplicate authoritative layers. | Repository/deployment inspection plus owner approval. | Present the three source-defined ownership options; do not choose silently. |
| OQ-005 | What MQTT topic conventions, schemas, client identities, QoS, session behavior, authentication, ACLs, TLS, and broker endpoint already exist? | Controls compatible ingestion and security. | Configuration and broker/client evidence; redact secrets. | Preserve existing topics; connect to the existing broker. |
| OQ-006 | Which remote devices/gateways can buffer events, and how reliable are their clocks and boot/sequence identifiers? | Determines loss, ordering, and timestamp guarantees. | Firmware/gateway inspection and owner/device documentation. | Claim only implemented guarantees; use received time when clocks are untrusted. |
| OQ-007 | What Ollama/Qwen client, tool-calling, tokenization, prompt, STT/TTS, conversation, phone, calendar, weather, and voice paths exist? | Defines adapters and Phase 5/6 integration. | Repository inspection and live configuration where safe. | Extend existing interfaces. |
| OQ-008 | Which notification endpoints exist, and what constitutes delivery or acknowledgement for each? | Determines adapter scope and truthful status. | Repo/configuration and owner policy. | Initially implement only existing channels behind an extensible interface. |
| OQ-009 | What action registry/layer, permissions, confirmations, safety checks, transports, and acknowledgements exist? | Phase 7 must integrate rather than replace. | Repository/device inspection and owner policy. | Add only missing lifecycle controls. |
| OQ-010 | What deployment and process-management mechanism is authoritative? | Determines startup, shutdown, health, and migrations. | Docker/Compose/systemd/supervisor/Kubernetes/launch configuration. | Use the existing mechanism; Docker Compose is only a default. |
| OQ-011 | What authentication, authorization, network binding, firewall, secret management, and API exposure already exist? | Determines security integration. | Repository and deployment evidence. | Bind privately and require auth for state changes. |
| OQ-012 | What event/telemetry volume, burst rate, retention target, disk budget, and context/model budget are expected? | Sets bounded queues, batching, indexes, capacity tests, and retention. | Measurements or owner estimates. | Configure conservative bounds and never shed critical safety events. |
| OQ-013 | What backup destination, schedule, encryption, restore objective, and artifact coverage are required? | Needed before durable data is operationally complete. | Existing backup policy and owner constraints. | Local secured backups; test restore where feasible. |
| OQ-014 | Which components must operate while the central host, broker, database, notification endpoint, or Ollama is unavailable? | Defines partition and recovery claims. | Deployment topology and device behavior. | Firmware retains immediate safety; backend reports degraded state truthfully. |
| OQ-015 | Are there source requirements that conflict with repository constraints? | Adaptations must preserve intent and be approved. | Phase 0 conflict inventory. | Record both facts, recommend an adaptation, and request owner confirmation. |

## Phase 0 resolution status (2026-07-16)

Evidence lives in [`DISCOVERY.md`](DISCOVERY.md) (section references below).

| ID | Status | Resolution |
|---|---|---|
| OQ-001 | Resolved | Python-only, run-in-place, per-process venvs, stdlib-first, no linter/typechecker; CI is compile-only (§1). |
| OQ-002 | Resolved | 3 SQLite stores, no ORM/migrations; defaults adopted via Docker (§7, §11, ADR-011). |
| OQ-003 | Resolved | Yes — `timescale/timescaledb-ha:pg17` runs on the dev machine; verified live by Phase 1 health checks (§11). |
| OQ-004 | Resolved | Home Assistant absent; backend is the authoritative layer (§8). |
| OQ-005 | Resolved | Flat legacy topics, QoS 0, no TLS/auth observed client-side; broker-side config still unverified (§3-§4; remaining part → OQ-B below). |
| OQ-006 | Resolved | No buffering anywhere; Pico clocks untrusted → `server_received` clock quality (§3, §9). |
| OQ-007 | Resolved | Responses API lane + OpenAI-compatible streaming seam; no embeddings; integration points mapped (§5; addendum §15 adds `POST /phone/events`). |
| OQ-008 | Resolved | No deterministic channel exists; v1 = GUI banner `POST /notify` + log adapter (§6, ADR-015). |
| OQ-009 | Resolved | No action registry; `water_plants`/`toggle_fan` fire-and-forget MQTT; Phase 7 wraps them (§4, §10). |
| OQ-010 | Resolved | No process manager in repo; plain venv processes + Docker Compose for the DB (§11, ADR-011). |
| OQ-011 | Resolved | Text-server bearer token + localhost/Tailscale allowlist is the precedent; awareness API binds loopback (§1, §10 C17). |
| OQ-012 | Resolved | Current traffic trivial; design target 10-100 msg/s burst; payload bound 64 KiB (§9 volumes). |
| OQ-013 | Open | Backup destination/schedule/restore objective — due before Phase 8; owner input needed. |
| OQ-014 | Resolved | Firmware behaviors + Pi TV controller run independently of the central host (§3). |
| OQ-015 | Resolved | 7 conflicts inventoried with adaptations (§9.1); owner approved via ADR-011..016. |

Remaining open items:

| ID | Question | Needed by |
|---|---|---|
| OQ-013 | Backup destination, schedule, encryption, restore objective. | Phase 8 (SEC-007) |
| OQ-B | Broker-side Mosquitto config (anonymous? ACLs?) on the Pi — unverifiable off-LAN; assumed anonymous. | Phase 8 hardening plan |
| OQ-C | Owner appetite for firmware fixes (unique client IDs, status-topic prefixes, abort-during-run, reconnect, native command IDs/acks) — currently out of scope per ADR-014. Phase 7 completed against simulated devices and repository-confirmed legacy status shapes; this is now optional physical-device remediation, not a Phase 7 completion blocker. **Resolved for the plant waterer only** (2026-07-26, ADR-018..021): the rewritten firmware has a unique client ID, canonical topics, stop-during-run, bounded reconnect, and native command IDs/acks. Still open for the fan Pico. | Owner-approved post-Phase-7 firmware work |
| OQ-D | Plant-waterer fuse sensing has no viable ADC path. The fuse signal is an analog divider on GP0/GP1/GP2/GP3 (netlist: F2/F1/F3/F4 -> R5/R6/R7/R8), but those pins are digital-only and the Pico W exposes ADC on GP26-GP28 only (three, not four). Which resolution does the owner want: (a) add an external I2C ADC such as an ADS1115, (b) measure the divider and confirm fuse-good > ~2.0 V / fuse-blown < ~0.8 V so it can be read as a debounced digital signal, or (c) leave fuse monitoring permanently out? Until then every channel reports `unknown` and no fuse interlock exists (ADR-019/ADR-028). | Before any fuse-fault alerting or fuse-based safety claim |
| OQ-E | ~~Which physical pot does each relay channel drive?~~ **Resolved (owner, 2026-08-28):** pot assignment is not a firmware concern — the owner reassigns pots by moving pump leads between the J2-J5 output terminals. Channels are defined in connector order (ch1 = GP6/K4/J2, ch2 = GP7/K3/J3, ch3 = GP8/K2/J4, ch4 = GP9/K1/J5) per ADR-028. | Resolved |
| OQ-F | Should the ingestion pipeline skip its own registered command topics instead of dead-lettering them as `unauthorized_topic`? The backend subscribes to `home/#` and therefore receives every command it publishes. Pre-existing behavior (the simulator's command topic does the same); it costs one dead-letter row per dispatched command. | Optional cleanup; not a pump blocker |
| OQ-H | **Resolved 2026-07-27 (ADR-024).** Windows communications-mode AudioGraph AEC is proven and selected on the pinned Yeti capture and BenQ render endpoints. Live far-end probe measured 45.696 dB ERLE with no callback errors; Windows reported AEC/NS/AGC/deep-NS. | Resolved |
| OQ-I | Does the owner-visible room corpus and eight-hour soak meet the Phase F recall, false-command, latency, overflow, wake-latency, and memory-prefix thresholds across real near-end/double-talk positions, volumes, noise, and device restart? | Before changing `BUTLER_BARGE_IN` from 0 to 1 |
| OQ-J | Does the independent idle Silero lane meet or beat the SpeechRecognition baseline for "Butler" recall, false wakes, command-pause handling, and endpoint p95 across the owner-visible room corpus? | Before setting `BUTLER_IDLE_VAD_CORPUS_ACCEPTED=1`; keep SpeechRecognition idle segmentation in production until then |
| OQ-K | **Partially resolved 2026-09-08 by ADR-042/043.** Exact LLM request/response payloads are owner-authorized only in a launcher-managed main process, sent over its existing local stdout pipe, shown outside ordinary logs, bounded to the latest 5,000,000 GUI characters, and permanently stored without automatic pruning in git-ignored per-run files under `butler/logs`. No new endpoint is exposed. What policy should apply to generated-versus-audible output and continuously sampled idle audio RMS/ambient baseline? | Before adding either remaining hot-path or content-bearing telemetry producer; the separate web dashboard must continue to report unavailable feeds truthfully. |
| OQ-L | Which authenticated metrics endpoint/exporter will run on the Butler system host for remote CPU, GPU, memory, disk, and temperature data, and how will the separate console reach it? | Before configuring `BUTLER_DEBUG_SYSTEM_METRICS_URL`; do not substitute metrics from the console computer. |
| OQ-P | **Capture architecture resolved 2026-09-08 (ADR-041).** The XVF3800 profile explicitly consumes 16 kHz stereo USB and selects channel 2, its documented auto-selected ASR beam, with calibrated energy segmentation. ReSpeaker AEC/barge-in remains disabled because Butler playback does not provide its hardware far-end reference. Remaining empirical question: does the owner-visible wake/command corpus restore acceptable recall and false-trigger behavior versus the Yeti? | Before claiming XVF3800 production accuracy or enabling its barge-in/idle-VAD lanes; run the visible A/B phrase corpus and, separately, validate a real far-end/AEC topology. |

## Potential source tension to confirm

OQ-G was resolved on 2026-07-26 after correcting the Pico's Wi-Fi SSID. Awareness received canonical state, health, and recurring heartbeat events from `quad_pump_canonical`; reported Wi-Fi/MQTT state was connected, RSSI was -47, and the firmware reported no last error. No relay command had reached the board at that point (`commands_accepted=0`).

No direct contradiction was found in the source. One wording tension is deliberate: PostgreSQL/TimescaleDB/pgvector and the listed Python stack are strong defaults, while existing suitable repository technology takes precedence. Phase 0 must explicitly decide whether the defaults apply; it must not treat either side as an unconditional mandate.

## Snapshot coverage follow-up (2026-11-18)

The observed snapshot investigation in [PER_TURN_AWARENESS_2026-11-18.md](PER_TURN_AWARENESS_2026-11-18.md) leaves two repository/deployment questions: why the local Docker Desktop Linux engine/database is unavailable, and what representative device/property coverage should be guaranteed within the automatic snapshot budget. Current selection prioritizes historical announcements over device facts and has no per-turn entity targeting. No policy decision or runtime repair was made in this investigation.

## Retirement disposition (2026-11-18)

The owner chose archival instead of further repair (ADR-058). Earlier database availability and snapshot coverage questions now describe the retired implementation; do not repair or reactivate it implicitly. Replacement-system requirements and the unrelated default-personality test mismatch are documented in RETIREMENT_2026-11-18.md and await separately bounded work.


## Devices design/discovery items (2026-11-18)

See [Devices design](../DEVICES_SYSTEM_DESIGN.md). Before the relevant bounded
implementation, verify the kitchen screen's actual integration and observable
fields, choose adapter polling/expiry intervals, finalize minimal local storage
and evidence retention, design the main-process-to-MCP read bridge, and measure
summary size/coverage and existing permission/provider disclosure behavior.
These are explicit design/discovery items, not blockers requiring a new service
or authorization to scaffold future systems. No runtime implementation started.


## Shared-storage resolution (2026-11-18)

ADR-060 resolves the database-file/connection/migration ownership question:
active domains share one application SQLite database. Old data import was waived;
no data reconciliation project is pending. Future Devices schema and diagnostic
retention remain part of its separately assigned implementation; the kitchen
screen contract, adapter refresh/expiry and per-turn coverage questions remain.
See ../DATABASE.md. This change does not configure Butler to launch at OS boot.


## DIS first-release disposition (2026-11-18)

Owner choices resolved: automatic owner-turn summary enabled; five-second
background reads; command-triggered priority reads are nonblocking rather than
waiting before replies; kitchen screen explicitly deferred. Source reads use a
configurable three-second deadline, 20-second freshness default and bounded
failure backoff. The coffee plug remained unreachable during live read-only
validation; its network/power availability remains unverified. Six lights were
read successfully with no switching. Pump information requires a separately
assigned adapter/liveness review and has no placeholder here. Model acceptance
covers four specific simulated truthfulness cases, not broad tool-use reliability
or a continuous deployment soak. See ../DIS.md.


## DIS subsequent adapters (2026-11-18)

Inventory is now recorded, but real endpoints/auth/read contracts remain unknown:
OctoPrint on the Ender 3 Pro's Pi 3; status agent for the kitchen Pi 4 kiosk;
Toshiba TV model/protocol; Minecraft server status endpoint/version and separate
host telemetry. Jeep remains conceptual. No answer is needed to maintain honest
inventory-only records. Waterer firmware currently has 30-second heartbeats and
300-second periodic state; shorter outage detection would require a separately
authorized source-protocol/firmware decision. No firmware change was made.


## WCS v1 and later sources (2026-11-19)

Weather-only v1 has no blocking owner question. The owner selected a 900-second
poll interval. Camera observations, room sensors, presence and personal location
still need real read/push contracts, privacy/identity semantics and independent
source schedules in separately assigned tasks. User-reported plans and temporal
interpretation are not implemented by weather WCS. Existing host-clock injection
and invalid-timezone fallback limitations remain a separate hardening task;
this implementation preserves source/receipt/forecast times without fixing the
host's clock synchronization. API budgets outside scheduled home-weather polls
(explicit other-location lookups/other clients) remain outside WCS ownership.


WCS route update (2026-11-19): direct get_current_weather and its other-location
lookup capability are removed from agent registration (ADR-064). The earlier
other-location API-budget exception is no longer an active agent route. No
blocking question remains for this cleanup.


Hourly weather (2026-11-19): v1 deliberately has no hourly forecasts. The reported
68 F at 8 a.m. was a model reuse of the daily high, not a source hourly reading.
Adding hourly data is a separate owner decision; no such integration is needed
to stop unsupported answers. No blocking question remains for this correction.


Hourly weather update (2026-11-19): owner authorized implementation (ADR-066).
Up to 48 hours are now collected in the existing poll, with cached time-range
reads. Earlier lack-of-hourly questions are resolved; no blocking design question
remains. Future beyond-horizon forecasts or other-location weather require a
separate assignment. Forecast/model reliability still requires observation in use.


Hourly rollout diagnosis (2026-11-19): actual failed turn had zero hourly records
while retaining an old collector's future schedule. ADR-067 addresses versioned
bootstrap without clearing evidence or bypassing retry schedules on every
restart. LLM behavior when the provider genuinely has no hourly coverage remains
an observed reliability limit; this fix does not claim to eliminate that risk.


## LTMS v1 follow-up (2026-11-19)

No unresolved owner choice blocks bounded v1. Measure real household consolidation,
retrieval latency/relevance and capacity before expanding it. Owner explicitly
defers chained reflection (search -> traverse -> compare -> reflect -> merge ->
relationships) and the DIS/WCS/LTMS-consuming executor to separate projects.


## LTMS visualization observation (2026-11-19)

Read-only viewer found three active memories, no edges, transient device-state
statements and duplicate-looking lamp statements. A separately authorized learning
quality investigation may assess these; this viewer assignment does not fix them.
3D/AR/VR remains shelved. No owner choice blocks the 2D first pass.


## Local launcher runtime installation (2026-11-19)

.venv-runtime and other old environments point to missing Python312/python.exe.
Fresh automatic launcher child startup requires restoring that base installation
or a separately scoped environment rebuild. The diagnostic graph is running using
an available compatible interpreter; main-runtime selection was not changed.


## Future DIS-to-LTMS contract (2026-11-19)

Owner defers a DIS status package for meaningful long-term evidence. Content,
provenance, aggregation and delivery contract remain unassigned. Direct device
status sampling is disabled; do not add a placeholder adapter.
