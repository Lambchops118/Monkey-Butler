# Session Log — awareness & memory

Condensed record of every bounded session on the awareness/memory subsystem.
Each entry replaces a former SESSION_HANDOFF_<date>[_TOPIC].md file, keeping
the goal, what shipped, the decisions, and anything still outstanding; the per-
session file inventories and test transcripts were dropped, since git history
carries them. Ongoing status lives in IMPLEMENTATION_STATUS.md, architectural
decisions in DECISIONS.md, and open items in OPEN_QUESTIONS.md. New sessions
append an entry here using SESSION_HANDOFF_TEMPLATE.md as the field list.

## 2026-07-16 — Awareness subsystem Phases 0–6
<a id="session-handoff-2026-07-16"></a>

Resume awareness-subsystem implementation on memory_system_3_07152026 under the
reorganized docs/awareness-memory/ specification.

**Shipped:** Port of Phase 0+1 (88f0e64) and partial Phase 2 (08b510e) from
memory_system_2_07152026; Phase 2 completion; documentation reconciliation;
Phase 3 (state authority/conflict/deadband manager, freshness worker,
measurements hypertable + 1m/1h/1d continuous aggregates, state_transitions +
source_health_history tables, bounded /state /events /telemetry reads;
migration dbfc40d327c0); Phase 4 (TOML rule policy + engine, alert dedup
lifecycle, attention cooldown/quiet hours, notification outbox + SKIP LOCKED
worker, gui/log adapters, text-server POST /notify, /alerts API; migration
7bf1cd5508d3); Phase 5 (SituationBroker + /situation /provenance /capabilities,
awareness_client + router snapshot fallback, MCP awareness provider with seven
read tools; no migration); Phase 6 (memory schema abc5ba9b578d with pgvector,
deterministic + candidate writes, supersession/conflict, episode-on-resolve,
embedding outbox handler, hybrid search, /memory API, search_memory tool,
remember_memory_fact mirroring).

**Decisions:** ADR-011..015 recorded from 2026-07-15 owner approvals; ADR-016
(2026-07-16): waive Phase 0 gate, port branch-2 work, continue phases in order.

**Limitations:** no MQTT lag metrics yet (MQTT-005 partial); dev machine off-
LAN, so the real Pi broker was never contacted — integration evidence is
against the owner-approved test broker; firmware issues remain (shared client
ID, status/16 collision, no reconnect) per ADR-014.

**Deployment:** requires Docker (timescale/timescaledb-ha:pg17 on :5433; test
Mosquitto on :1885 via --profile test) and .venv-awareness (Python 3.12).

**Security:** awareness API loopback-only; topic ownership enforced; broker
TLS/auth supported via config but Pi broker assumed anonymous (OQ-B).

## 2026-07-18 — Voice conversation continuity
<a id="session-handoff-2026-07-18"></a>

Diagnose and repair voice-chat conversation continuity and awareness-context
integration.

**Shipped:** Enabled the local conversation/prompt-memory store by default;
serialized streamed session context retrieval with turn completion; added
conversation-reset cleanup that preserves explicit facts; restored awareness
situation injection for /chat/stream; enabled memory in the local .env; added
multi-turn, reset, and awareness-injection regression tests.

**Decisions:** No new architectural decision. Existing separation was
confirmed: SQLite owns bounded conversation/session prompt context; awareness
PostgreSQL owns validated semantic/episodic long-term memory and situation
data.

**Limitations:** Conversation prompt context is a bounded compact summary (last
eight stored messages, subject to BUTLER_PROMPT_MEMORY_CHAR_LIMIT), not an
unlimited transcript. A live model/voice smoke test still requires restarting
the main and voice processes and starting awareness for situation data.

**Deployment:** Restart the main Butler process so import-time memory
configuration and code changes take effect. Start the separate awareness
process for house situation/state context; voice continuity itself degrades to
SQLite and does not depend on awareness availability.

**Security:** Conversation turns persist locally in ignored
db/talos_memory.sqlite3 by default. BUTLER_MEMORY_ENABLED=0 remains an explicit
privacy opt-out. Session reset deletes stored turns/summary but preserves
explicit durable facts.

## 2026-07-18 — Dynamic Reasoning (Thinking) Control
<a id="session-handoff-2026-07-18-dynamic-thinking"></a>

Reduce local-model (Ollama mb-core-v1, a Qwen3-14B finetune) response latency
after the cutover from hosted OpenAI Chat Completions.

**Shipped:** Added dynamic per-request reasoning control for the streamed lane.
Qwen3's /no_think and /think soft switches are appended to the outgoing user
turn based on a complexity heuristic (auto), with always/never/off overrides
via BUTLER_LLM_THINK_MODE. Only the live outgoing turn is decorated; the
original command is persisted to memory, so stored history stays clean and
continuity is unaffected.

**Decisions:** Default BUTLER_LLM_THINK_MODE=auto. auto suppresses thinking on
quick commands/chit-chat/status and enables it on analytical requests
(why/how/explain/compare/debug/plan/long or background-lane work). The
heuristic errs toward off because latency is the point. off exists for swapping
to non-Qwen models that would otherwise receive a literal /no_think token.

**Deployment:** Restart the streamed text-agent/voice process so it loads the
new code. Set BUTLER_LLM_THINK_MODE in the live .env only if overriding the auto
default.

## 2026-07-18 — Spoken Tool-Call JSON (Leaked Tool Calls)
<a id="session-handoff-2026-07-18-leaked-tool-calls"></a>

Investigate and fix the system speaking raw tool-call JSON aloud on tool
queries ("what's the temperature", "are there any calls recently").

**Decisions:** Treat a leaked tool call as a tool call (parse + execute) rather
than muting it, so the local model behaves like the structured Responses API
did. Keep markup out of both speech and history to also kill the self-
perpetuating mimicry loop.

**Limitations:** Recovery keys off content that begins with '{' or
'<tool_call'; a leak that begins with natural preamble text then emits markup
mid-stream would have the preamble spoken and the markup potentially spoken too
(not observed -- real leaks were pure markup from the first token). The false-
alarm path buffers a turn that starts with '{' until completion, a minor
latency cost for that rare case only.

**Deployment:** RESTART the streamed text-agent/voice process to load the
change. No new env required (BUTLER_RECOVER_LEAKED_TOOL_CALLS defaults on).

## 2026-07-18 — Local Ollama Inference
<a id="session-handoff-2026-07-18-local-ollama"></a>

Replace the streamed home-automation agent's hosted OpenAI Chat Completions
target with the owner's locally installed custom Ollama model while keeping STT
and inference local-first.

**Shipped:** Identified the installed model as mb-core-v1:latest; configured
the ignored live .env for Ollama on loopback; changed the streamed runtime to
use the existing backend factory; made Ollama the factory default with a
loopback endpoint; removed the streamed lane's OPENAI_API_KEY fallback; made
remote STT and legacy remote LLM failover explicit opt-ins; documented and
tested the profile. Correction follow-up: recovered the exact latest pre-
cutover live `.env` from VS Code Local History and merged the eight new
settings, restoring all prior machine-specific values without displaying them.

**Decisions:** ADR-017 records BUTLER_LLM_BACKEND=ollama,
BUTLER_LLM_BASE_URL=http://127.0.0.1:11434/v1, and BUTLER_LLM_MODEL=mb-
core-v1:latest for the default streamed lane. Remote STT and voice LLM fallback
default off to preserve the local-only boundary.

**Limitations:** The default streamed voice LLM and STT lanes are local. The
legacy non-streaming run_command path still uses hosted OpenAI Responses when
explicitly selected, and speech synthesis still uses AWS Polly, so those
separately bounded migrations are required before claiming the entire voice
stack has no network dependency. Weather and other explicitly hosted
integrations also remain network-dependent.

**Deployment:** Restart the main Butler/text-agent process and voice worker so
they load the new .env. Ollama must be running and mb-core-v1:latest must
remain installed. The ignored .env is machine-local and is not included in
source control.

**Security:** The local LLM target is loopback and no API key is used. Audio
stays local by default; remote transcription and legacy remote LLM failover
require explicit opt-in. Existing physical-action schemas, authorization,
confirmation, and audit boundaries are unchanged.

## 2026-07-18 — Personality Response Discipline
<a id="session-handoff-2026-07-18-personality"></a>

Make the active home-agent personality feel like a persistent household
presence rather than a customer-service chatbot.

**Shipped:** Confirmed butler/personality/monkey_butler.md is the active base
soul document for voice and text; added persistent-home framing, terse routine
confirmations, direct yes/no behavior, clean stopping behavior, prohibited
generic follow-up offers, explanation-length limits, and tool/device-confirmed
success language; replaced the conflicting Tactical Follow-Ups allowance; added
a prompt-assembly regression test.

**Decisions:** No ADR required. The existing active base prompt remains
authoritative; overlays and response code remain unchanged.

**Limitations:** Prompt compliance ultimately depends on the selected model. No
hard response post-processor was added because it could damage substantive
answers and was unnecessary for the requested smallest change.

**Deployment:** Restart the main Butler process to reload the base personality
content for subsequent turns.

**Security:** The existing evidence requirement was strengthened; an action may
not be described as successful without confirming tool/device evidence.

## 2026-07-18 — Time Increment & Follow-up Mimicry
<a id="session-handoff-2026-07-18-time-and-mimicry"></a>

Investigate two reported local-model misbehaviors — (1) responses ending with
"let me know what else I can help with" despite the persona forbidding it, and
(2) repeated "what time is it" turns incrementing the time by one each call
(5:55 -> 5:56 -> 5:57...) while the real clock was unchanged — and fix them.

**Decisions:** Fix the time bug structurally (ground-truth in context =
structured retrieval, per the architectural invariant) rather than only
instructing the model. For the pleasantry, owner chose history reset over a
deterministic stripper to avoid making output too rigid; the stripper remains
the fallback if it recurs.

**Limitations:** The pleasantry fix relies on history staying clean plus the
persona rule; if a pleasantry ever slips through and is persisted, mimicry
could restart. If that recurs, add the deterministic trailing-offer stripper
(strip before speaking and before persisting) that was designed and declined
this session. Time injection adds ~200 chars/turn.

**Deployment:** RESTART the streamed text-agent/voice process to load the time-
injection code. The history reset needs no restart. No new env required
(BUTLER_INJECT_CURRENT_TIME defaults on).

## 2026-07-18 — Tool Scoping & Local-Model Behavior
<a id="session-handoff-2026-07-18-tool-scoping-behavior"></a>

After the Ollama cutover, the local model (mb-core-v1, a Qwen3-14B finetune)
mis-selected tools (a "write pygame code" request triggered the kitchen recipe
screen) and ignored anti-agentic/followup controls that worked with
gpt-4o-mini. Determine whether this is an inherent model limitation and fix
what is fixable without making tool use so rigid that inferential behavior
("it's hot in here" -> lower the temperature) is lost.

**Decisions:** Preserve inference over rigidity — scope tools by intent
(structural) and steer behavior with balanced prompt guidance, rather than
forbidding tool calls that don't exact-match (owner-declined item 2).
BUTLER_SCOPE_TOOL_SURFACE defaults on; only the kitchen group is scoped today,
mechanism is extensible.

**Limitations:** Only the kitchen group is intent-scoped; other large future
groups can be added to _scope_specialized_tools. Multi-turn cooking followups
rely on kitchen-vocabulary terms; a purely pronoun followup ("add two more")
mid-recipe could drop kitchen tools for that turn. Scoping keys off the current
command only, not conversation state.

**Deployment:** Restart the streamed text-agent/voice process to load the new
code and prompt overlay. No new env required (BUTLER_SCOPE_TOOL_SURFACE defaults
on).

## 2026-07-18 — Streamed Voice Context
<a id="session-handoff-2026-07-18-voice-context"></a>

Repair the repeated streamed-voice failure to resolve immediate conversational
references such as “go with both.”

**Shipped:** Inspected the live local SQLite evidence and confirmed the exact
water-plants exchange was persisted under voice-worker. Replaced system-prompt-
only session-summary continuity in run_command_stream with bounded recent
user/assistant messages in actual Chat Completions role order. Kept durable
facts/summaries in the prompt-memory block without duplicating the active
session summary. Added message/character limits and exact regression coverage
for “Water the plants” → “Which pot?” → “Go with both.”

**Decisions:** No ADR required. Immediate conversational context is now
transported in the model API's native message roles; semantic/durable facts
remain separate.

**Limitations:** Streamed history defaults to the latest eight user/assistant
messages and 4,000 characters. Older conversation relies on summaries/facts and
is not guaranteed to preserve pronoun-level references.

**Deployment:** Restart the main Butler process to load the code. The voice
worker may also be restarted for a clean operational smoke test.

## 2026-07-20 — Proactive Presence
<a id="session-handoff-2026-07-20-proactive-presence"></a>

Let the awareness system speak up on its own — (A) route alerts to a spoken,
LLM-phrased channel instead of a silent GUI banner; (B) give the backend a
wall-clock reminder mechanism so "remind me at 7pm" is actually spoken at 7pm.

**Shipped:** Gap A (voice notification channel) + Gap B (due-time reminders).

**Decisions:** - Alerts are spoken via the existing voice_cmd router lane (the
same seam the legacy morning_report_job uses), so wording is the LLM's;
detection/rendering stay deterministic in the backend (no Ollama in the
awareness process). voice is the default preferred channel, with gui+log as
automatic fallback for resilience. - Reminders live in the awareness backend
(durable table + deterministic worker), reusing AlertService.raise_attention →
identical dedup/quiet-hours/cooldown/audit and one shared notification egress
for overflow AND reminders. - Natural-language time parsing is the LLM's job at
set_reminder time; the API requires an absolute timezone-aware future due_at
and rejects past/naive values.

**Limitations:** - "Confirmed" on the voice channel means the text server
enqueued the spoken alert, NOT that a human heard it (documented, consistent
with INV-14). Actual speech requires the main agent process + Ollama up; if
that path is down the outbox falls back to the gui banner then the log. - The
set_reminder tool trusts the LLM to compute the absolute due_at; a wrong offset
yields a wrong fire time. The API guards only against past/naive timestamps. -
No recurring reminders (one-shot only) and no "snooze"; add later if wanted.

**Deployment:** run migrations (`python -m butler.awareness migrate`) before
serving — the reminders table is new. New env vars (all optional, sensible
defaults): BUTLER_AWARENESS_NOTIFY_VOICE_ENABLED, _REMINDER_INTERVAL_SECONDS,
_REMINDER_INTERRUPTIBILITY, _REMINDER_CHANNEL.

**Security:** /speak reuses the same text-server auth as /notify (bearer +
allowed-network). Reminder write routes use require_write_auth (loopback-
trusted; bearer-gated when BUTLER_AWARENESS_API_TOKEN is set) — not fail-closed
like physical actions, since a reminder performs no physical action.

## 2026-07-24 — Pipeline Telemetry
<a id="session-handoff-2026-07-24-pipeline-telemetry"></a>

Investigate the perceived speech/latency regression, review the awareness and
full speech-to-LLM-to-output pipeline, answer the owner's focused questions,
and implement only correlated pipeline telemetry.

**Shipped:** Added telemetry identifying local versus hosted/fallback backends,
prompt-token estimates and provider counts when exposed, model-load
timing/status, and durations for each instrumented pipeline stage. Events share
a request ID across voice, text service, agent runtime, tools, LLM, TTS, and
playback. The new JSONL event stream intentionally excludes prompt, transcript,
response, and tool-argument content.

**Decisions:** - Use append-only per-process JSONL with correlated request IDs
as the durable telemetry record and SSE telemetry events for the voice/text-
process boundary. - Record prompt tokens as an explicitly labeled conservative
estimate unless the provider supplies usage. - Record exact faster-whisper load
duration. For Ollama's OpenAI-compatible stream, report an already-loaded zero
measurement when `/api/ps` confirms residency; otherwise report time-to-first-
token as a labeled cold-start upper bound because this endpoint does not expose
native model `load_duration`. - Keep telemetry best-effort so logging failure
cannot break the assistant pipeline.

**Limitations:** - Prompt-token telemetry is estimated when streaming providers
do not return usage. - Ollama native model load duration is unavailable through
the current OpenAI-compatible streaming response. The cold-load value is
therefore explicitly marked as a TTFT upper bound. - Per-process log files need
request-ID correlation when the voice and text services run separately. - Stage
timings add observability but do not themselves correct the suspected
regression.

**Deployment:** Telemetry is enabled by default through
`BUTLER_PIPELINE_TELEMETRY_ENABLED=1` and writes under `butler/logs` unless
`BUTLER_PIPELINE_TELEMETRY_DIR` overrides it. The directory must be writable. No
schema or service dependency was added.

**Security:** The new JSONL telemetry excludes conversational and tool-argument
payloads. It records operational metadata such as model/backend names, counts,
durations, request IDs, and error types. Existing legacy benchmark logs retain
their pre-existing behavior and were not broadened by this task.

## 2026-07-26 — Barge-In Redesign Phase A
<a id="session-handoff-2026-07-26-barge-in-phase-a"></a>

Implement the next bounded phase in `docs/voice/BARGE_IN_REDESIGN_PLAN.md`.

**Shipped:** Yes. Phase A is complete and the work stopped before the Phase B
AEC feasibility spike.

**Decisions:** - ADR-023: the unsafe legacy RMS-plus-ASR barge-in path fails
closed through both tracked configuration and its code default. - Synchronized
room-audio recording requires a separate explicit operator opt-in. It is local-
only, visibly announced, background-written through a non-blocking bounded
queue, capped by duration and PCM bytes, and subject to bounded retention of
recorder-owned fixture directories.

**Limitations:** - The legacy heuristic remains structurally unreliable. Phase
A contains it but does not improve its double-talk discrimination. - Aggregate
measurements are cumulative for the voice-worker process. They do not contain
transcripts/PCM and use bounded rejection labels. - Faster-whisper currently
provides no confidence in the active backend result, so ASR confidence remains
truthfully absent until supported. - Fixture WAV streams use monotonic per-
block timestamps and sample offsets for synchronization; live device-clock
accuracy has not been measured. - Graceful recorder close is wired into normal
voice-worker shutdown. Abrupt process termination may leave the newest fixture
incomplete.

**Deployment:** - Restart the voice worker to load the fail-closed code/config
default and new observability. - Normal deployment should leave both
`BUTLER_BARGE_IN=0` and `BUTLER_BARGE_IN_FIXTURE_RECORDING=0`. - An operator
fixture session needs deliberate configuration and should be handled as
sensitive room audio.

**Security:** - Raw room audio is off by default and requires
`BUTLER_BARGE_IN_FIXTURE_RECORDING=1`. - The recorder prints a visible warning,
stores only locally, writes under an ignored local data directory by default,
enforces duration/byte/session bounds, and deletes only prefix-matched
directories containing its manifest. - Privacy-safe barge-in telemetry contains
numeric counts/timings/RMS and bounded reason labels, never transcript text or
PCM. - Hosted-service behavior is unchanged.

## 2026-07-26 — Barge-in review
<a id="session-handoff-2026-07-26-barge-in-review"></a>

Investigate the unreliable barge-in voice interruption feature at both code and
architectural levels; fix it only if the design is sound, otherwise produce a
replacement plan.

**Shipped:** Traced microphone capture, render tracking, energy gate, ducking,
endpointing, faster-whisper transcription, interruption classification, local
playback cancellation, agent cancellation, conversation repair, and follow-up
redispatch. Determined that the front-end RMS-plus-ASR design cannot robustly
distinguish double-talk from echo. Documented an AEC-first redesign with phased
implementation and acceptance criteria. Added a README warning. Runtime
behavior was intentionally not patched.

**Decisions:** No owner-level architecture decision was recorded. The review
recommends WebRTC APM/AEC3 or a proven Windows endpoint AEC path, with AEC
output feeding VAD before ASR. Exact backend selection remains OQ-H pending a
deployment-host spike.

**Limitations:** - Current barge-in remains enabled by the tracked
`settings.env` and remains unreliable until the operator disables it or the
redesign is implemented. - Wake-word-required mode only contains false command
acceptance; it does not prevent false ducking or solve double-talk detection. -
The exact deployed input/output endpoints, Windows build, driver AEC support,
room response, and native WebRTC binding choice were not available from the
repository. - Current "audible prefix" bookkeeping marks a whole sentence at
its first PCM block, not the exact text heard.

**Deployment:** Safe interim posture is `BUTLER_BARGE_IN=0`. A production
redesign requires a Windows endpoint/AEC capability spike on the deployed host.
AEC failure must degrade to ordinary wake-word operation without barge-in,
never silently back to the RMS heuristic.

**Security:** False ASR text can currently enter the conversation as a user
command. Existing action authorization and safety boundaries still apply, but
this is not an acceptable authentication signal. Optional synchronized audio
fixture recording in the plan is explicitly opt-in, local, visible, and
retention-bounded because room audio is sensitive.

## 2026-07-26 — Plant Waterer Firmware and Awareness Integration
<a id="session-handoff-2026-07-26-plant-waterer-firmware"></a>

Execute Peripherals/quad_pump/plan.md: replace the legacy plant-waterer Pico W
firmware with safe, non-blocking firmware and add its bounded awareness
integration.

**Shipped:** Firmware rewrite + host tests + canonical source registration +
canonical run_pump/stop_pump actions + per-channel cooldown scope +
documentation. Rollout steps 1-3 of the plan's staged migration. Steps 4-10 are
physical and owner-executed.

**Decisions:** ADR-018 hardware/safety policy (relays GP0-3, fuse GP6-9,
active-high, 1 concurrent pump, 30 s hard max, 8 s default, fuse fault inhibits
start and stops a run, channel 1 = pot 1, channel 2 = pot 2) ADR-019 ship
without fuse monitoring; fuse state is permanently "unknown" ADR-020 staged
rollout; water_plants stays on the legacy topic for now ADR-021 at_most_once
retained; additive per-parameter cooldown scope

**Limitations:** - Fuse sensing is not implemented; every channel reports
"unknown" and no fuse interlock is active (ADR-019, OQ-D). The
debounce/hysteresis and fuse-policy code paths exist and are tested with fake
fuse readings, but the hardware cannot feed them. - Channel-to-pot ordering is
unverified (OQ-E). - Device-side persistent deduplication is implemented and
tested on the host across a simulated restart, but has not been power-loss
tested on hardware, so the action registry stays at at_most_once. - The device
clock is untrusted; issued_at is never a rejection input and the source keeps
clock_quality = server_received. - The backend's own command publications
return on its home/# subscription and dead-letter as unauthorized_topic (pre-
existing behavior, OQ-F). - qp_net contains a copy of umqtt.simple's wait_msg,
modified to expose the PUBLISH retain flag so a retained command replay cannot
water a plant. Keep it in step if simple.py is ever updated.

**Deployment:** - Copy main.py, simple.py, qp_config.py, qp_hardware.py,
qp_protocol.py, qp_ledger.py, qp_controller.py, qp_net.py, and a filled-in
qp_secrets.py to the Pico root. - Broker ACLs must allow the new client ID on
home/irrigation/quad_pump/# (see BROKER_HARDENING_PLAN.md). Owner-executed. -
The awareness backend must be restarted so seed_registry adds
quad_pump_canonical.

**Security:** - The Wi-Fi SSID and password that were committed in the old
main.py are gone from the current file but remain in Git history. **Rotate the
Wi-Fi password before or during deployment.** Deleting the file does not remove
them. - New secrets live in an untracked device-local qp_secrets.py; a redacted
qp_secrets_example.py is committed and .gitignore covers the real file. - The
device now uses a unique MQTT client ID (talos-quad-pump-<unique_id>) instead
of sharing "pico-w-client" with the fan Pico. - Published payloads carry no
credentials and bounded, non-secret error codes only (no tracebacks). A test
asserts this.

## 2026-07-26 — Plant-Waterer GPIO Mapping Hotfix
<a id="session-handoff-2026-07-26-plant-waterer-gpio-mapping"></a>

Resolve why fully acknowledged pump commands produced no physical relay click.

**Shipped:** Queried the durable action and event audit for the latest channel
3 and channel 1 requests. Both progressed requested → validated → approved →
dispatched → acknowledged → completed. The Pico reported command receipt,
`relay_N=true`, an approximately eight-second run, `relay_N=false`, and a
positive execution acknowledgement; health reported 6 accepted and 0 rejected
commands. This isolated the failure to the hardware mapping/interface. The
owner then supplied known-working MicroPython code using active-high `Pin(9)`,
`Pin(10)`, `Pin(11)`, and `Pin(12)`, proving the original mapping table
contained GPIO identifiers and the deployed GP0-GP3 interpretation was wrong.
Corrected channels 1-4 to GP9-GP12 and recorded fuse inputs GP1/GP2/GP4/GP5
while leaving fuse sensing unavailable.

**Decisions:** ADR-022 records live-board evidence: relay channels 1-4 use
GP9-GP12 and are active-high. The GPIO mapping portion of ADR-018 is
superseded. Safety/runtime/channel/legacy policies remain unchanged. Fuse
sensing remains disabled under ADR-019.

**Limitations:** The corrected mapping is only in the host repository until
`qp_config.py` is copied to the Pico root and the board restarts. Fuse sensing
is unavailable. Physical pot/zone assignment still requires one-channel-at-a-
time verification.

**Deployment:** Copy `Peripherals/quad_pump/qp_config.py` over `/qp_config.py`
on the Pico, ensure the application file is `/main.py`, and restart/power-cycle
the board. Confirm a new boot heartbeat before issuing one observed channel
command.

## 2026-07-26 — Voice Physical-Action Dispatch
<a id="session-handoff-2026-07-26-voice-action-dispatch"></a>

Diagnose and fix repeated voice claims that a plant-waterer action had been
initiated even though no relay activated.

**Shipped:** Confirmed from the post-reboot pipeline telemetry and conversation
database that the requests “water the monstera” and “turn on the pump for pot
two” each completed with zero tool execution while the model generated and
persisted an invented initiation claim. Added deterministic routing for
unambiguous pump/pot/channel commands through the existing registered
`request_device_action` tool. Added a general streamed physical-action guard
that withholds an unsupported success claim, retries the model once with a
fresh tool requirement, and emits a deterministic truthful failure if no action
tool is called. A subsequent live retry proved deterministic tool routing was
active, but exposed a second truthfulness defect: the model paraphrased the
action API's immediate `approved` (queued) response as “activated.” Explicit
pump commands now bypass that model paraphrase and deterministically report the
request ID/status with “physical activation has not yet been confirmed”;
rejected requests surface their bounded reason and API errors cannot become
success prose.

**Decisions:** Clear imperative pump commands with an explicit channel/pot
number route deterministically to `run_pump` or `stop_pump` through the
registered action boundary. The deterministic parser does not dispatch plant-
name-only or otherwise ambiguous requests. It recognizes the deployed speech-
to-text variants `too`/`to` for channel 2 and `tree` for channel 3 only when
they follow `pump`, `pot`, or `channel`. The awareness action service remains
authoritative for authorization, validation, cooldown, MQTT dispatch,
acknowledgement, timeout, and audit.

**Limitations:** The running main/voice process must be restarted again to load
the shortened deterministic action-result wording; request UUIDs remain in the
database audit but are no longer spoken. Plant-name-only requests still require
the model or stored entity context to select a channel. The Pico is online and
publishing recurring heartbeats from a stable boot. Database evidence for the
latest channel 3 and channel 1 runs shows command receipt, `relay_N=true`, an
approximately eight-second run, `relay_N=false`, and a positive execution
acknowledgement; device health reports 6 accepted and 0 rejected commands. That
state is firmware-commanded state, not electrical relay feedback. The remaining
no-click failure therefore requires direct GP0-GP3 voltage, polarity, power,
common-ground, logic-level, and wiring bench checks. Channel-to-physical-pot
wiring remains unverified.

**Deployment:** Stop and restart Butler from the launcher. Confirm awareness is
healthy on port 8600 before testing. Leave the Pico running `main.py` without
interrupting it from Thonny. Issue one explicit command with a channel number
and observe the action record, acknowledgement, and relay.

**Security:** No raw MQTT or GPIO bypass was added. Deterministic routing calls
the existing registered action tool, preserving API authorization, schema
validation, cooldown, idempotency, acknowledgement, timeout, and audit
boundaries. Ambiguous requests do not dispatch.

## 2026-07-26 — Windows Awareness MQTT Hotfix
<a id="session-handoff-2026-07-26-windows-mqtt-hotfix"></a>

Diagnose and fix accepted plant-waterer actions that never energized a relay.

**Shipped:** Fixed the Windows awareness server event loop so aiomqtt ingestion
and action publication can connect to the configured Mosquitto broker.

**Decisions:** No architectural decision. The Windows awareness entrypoint now
explicitly gives Uvicorn an asyncio.SelectorEventLoop factory because Uvicorn
0.36+ otherwise selects ProactorEventLoop on Windows even after a global
selector policy is installed. The selector policy is also retained for non-
Uvicorn asyncio CLI commands.

**Limitations:** The already-running launcher-owned awareness process on port
8600 loaded the old code and remains MQTT-degraded until Butler is restarted.
The activated plant-waterer board still has not emitted state, health, or a
heartbeat during a 35-second direct broker subscription (OQ-G). Physical
channel mapping, relay operation, and fuse limitations remain as documented in
the plant-waterer handoff.

**Deployment:** Restart Butler/the launcher so the awareness subprocess loads
the new loop configuration. Verify /health/components reports
mqtt.state=connected before another action. Then diagnose the Pico over its
serial console and require a heartbeat before physical pump testing.

## 2026-07-27 — Barge-In Phases B-F
<a id="session-handoff-2026-07-27-barge-in-phases-b-f"></a>

Implement all remaining phases of `docs/voice/BARGE_IN_REDESIGN_PLAN.md`.

**Shipped:** Selected and proved Windows communications AEC; added pinned
endpoint checks, bounded continuous duplex capture, clean idle recognition,
stateful Silero VAD with hysteresis/pre-roll, bounded off-audio-thread ASR,
segment evidence gates, safe PCM/chunk bookkeeping, an offline fixture
acceptance runner, rollout controls, and documentation.

**Decisions:** ADR-024 selects pinned Windows communications AEC; the RMS path
is diagnostic-only and never fallback; production stays disabled pending live
acceptance.

**Limitations:** Without Polly word speech marks, an interrupted current chunk
is deliberately under-claimed as partially heard; completed earlier chunks
remain exact. Live room acceptance remains unknown.

**Deployment:** Install pinned PyWinRT packages from `requirements-voice-
py312.txt`. The full MMDevice IDs are host-specific. Endpoint mismatch disables
barge-in and preserves ordinary wake capture.

**Security:** Raw room PCM remains off by default, explicit, bounded, local-
only, and uncommitted. AEC/VAD/ASR are local. No new action authority is
introduced.

## 2026-08-09 — Local Debug Dashboard
<a id="session-handoff-2026-08-09-debug-dashboard"></a>

Build an expandable, barebones web debug screen for interaction I/O, system
health, CPU/GPU data, and available audio metrics, with minimal impact on the
running system.

**Shipped:** Added a standalone local read-only debug dashboard with
Interaction I/O, System Health, Live Audio, and Raw Events tabs. It polls
bounded snapshots and uses existing artifacts/probes only.

**Decisions:** ADR-026 records the standalone read-only loopback service
boundary. ADR-027 records that system hardware metrics are remote-only because
the console runs on a different computer. The dashboard does not join the
agent/audio hot paths and refuses non-loopback binding unless the operator
explicitly supplies `--allow-remote`.

**Limitations:** Existing audio sources update after utterance/barge-in
snapshots, not per frame. Exact prompts and detailed tool calls are
unavailable. Conversation messages and pipeline request IDs cannot always be
correlated because current memory metadata does not store request IDs. Service
health is probe-based, not launcher-process authority. Remote hardware cards
remain `NOT_CONFIGURED` until a Butler-host metrics endpoint is selected and
supplied through `BUTLER_DEBUG_SYSTEM_METRICS_URL`.

**Deployment:** Start separately with `.venv-main\Scripts\python.exe -m
butler.debug_dashboard`; default URL is `http://127.0.0.1:8787`. The launcher
was intentionally not changed.

**Security:** The page exposes private conversation content. It binds to
loopback by default, has no authentication, is read-only, sets a restrictive
content security policy, and requires an explicit `--allow-remote` override for
non-loopback binding. It never reads or records raw PCM.

## 2026-08-09 — Wake Latency and Accuracy Recovery
<a id="session-handoff-2026-08-09-wake-latency-accuracy"></a>

Implement recommendations 1, 2, and the accuracy-safe parts of 5 from the wake-
word regression analysis for commit `e33c2f1`.

**Shipped:** Restored SpeechRecognition as the production idle utterance
segmenter without restoring duplicate transcription; added independent
idle/barge-in VAD lanes; gated idle VAD behind both an enable request and
explicit corpus acceptance; increased idle pre-roll to 640 ms; preserved
utterances across playback boundaries; asynchronously preloaded faster-whisper;
and serialized local ASR through a bounded priority queue that selects fresh
idle commands before queued barge-in confirmations.

**Decisions:** ADR-025. SpeechRecognition segmentation is not a second
transcription pass. Experimental idle VAD cannot activate unless both
`BUTLER_IDLE_VAD_ENDPOINTING=1` and `BUTLER_IDLE_VAD_CORPUS_ACCEPTED=1`.

**Limitations:** Faster-whisper remains a finished-utterance batch backend.
Speculative chunk decoding was not added because it would reintroduce redundant
inference and has no accuracy evidence; true incremental decoding needs a
supported streaming backend and its own accepted corpus. The independent idle
endpoint retains the conservative 480 ms trailing-silence setting until real
command-pause evidence exists.

**Deployment:** Restart the voice worker to pick up `BUTLER_VAD_ENDPOINTING=0`.
Production uses SpeechRecognition segmentation immediately. The new idle Silero
lane remains inactive under tracked settings. Faster-whisper begins loading
asynchronously during voice-worker startup.

**Security:** Audio remains local-first. No new upload path or action authority
was added. Room recording remains explicit and disabled by default.

## 2026-08-28 — Plant-Waterer Relay Activation Hotfix (GPIO Map)
<a id="session-handoff-2026-08-28-plant-waterer-relay-activation"></a>

Determine why `run_pump` / `water_plants` commands were accepted and
acknowledged while no pump physically activated.

**Shipped:** Traced the full dispatch path and reproduced the host's command
envelope against the firmware parser: the envelope parses cleanly,
`PumpController._run_command` reaches `_begin_run`, and `RelayBank.set` drives
its mapped GPIO high. The failure is the mapping itself. Extracting the netlist
from `Controller_Board_mk2.kicad_pcb` shows the relay drivers on
GP6/GP7/GP8/GP9 (GPIO -> base resistor -> low-side NPN -> relay coil -> output
terminal): GP6->R1->Q1->K4->J2, GP7->R4->Q4->K3->J3, GP8->R3->Q3->K2->J4,
GP9->R2->Q2->K1->J5. The fuse dividers reach GP0-GP3 through R5-R8. The same
netlist marks GP10, GP11 and GP12 `unconnected`, so `CHANNEL_RELAY_GPIO = {1:
9, 2: 10, 3: 11, 4: 12}` drove floating pins on channels 2-4. Corrected the
relay map to GP6-GP9 and the fuse map to GP0-GP3, numbering channels in output-
connector order J2-J5. Separately, commit `25e3fd2` raised the firmware
`DEFAULT_RUN_SECONDS` from 8 to 30 without touching the `water_plants` registry
entry, whose `timeout_seconds` was still 20. Because the legacy path publishes
`status/{pin} = 0` only after the cycle finishes, every successful 30 s run
would have been marked timed out. Raised it to 45 s, matching `run_pump`.

**Decisions:** ADR-028 records the netlist-derived map: relay channels 1-4 on
GP6/GP7/GP8/GP9, fuse inputs on GP0/GP1/GP2/GP3, channels numbered in output-
connector order, relays active-high (Q1-Q4 are low-side NPN switches). It
supersedes ADR-022 and the GPIO portion of ADR-018. ADR-029 raises the
`water_plants` timeout to 45 s.

**Limitations:** The correction is netlist-derived, not bench-measured; no
relay has been observed to click. Fuse sensing remains unavailable (ADR-019,
OQ-D). Firmware state reports remain commanded software state, not electrical
feedback.

**Deployment:** Done for the device. Remaining: issue one observed command per
channel and watch for a relay click on each of GP6-GP9 before trusting
unattended watering. The submodule changes (`qp_config.py`, `qp_hardware.py`,
`qp_secrets.py`) are uncommitted, and the submodule already carries commit
`25e3fd2` that the parent repository does not record, so both a submodule
commit and a parent pointer bump are still needed. Do not commit
`qp_secrets.py` further — see the security finding.

## 2026-09-01 — Plant-Waterer Network Resilience (Watchdog Reset Loop)
<a id="session-handoff-2026-09-01-plant-waterer-network-resilience"></a>

Determine why the pump controller board stopped working after several days
idle, distinguish a code fault from hardware damage, and — after owner
authorization — fix it and deploy.

**Shipped:** Diagnosed and fixed a permanent watchdog reset loop in the quad-
pump firmware's network path, deployed the fix to the Pico on COM6, and
verified it against the original failure conditions on hardware. ## Hardware
findings (no damage) The board on COM6 is healthy. USB enumerates as
`USB\VID_2E8A&PID_0005` with `ConfigManagerErrorCode 0`; MicroPython 1.28.0 on
`RPI_PICO_W`, RP2040 at 125 MHz, UID `e66598541b809938`; 200,800 B free RAM
against 4,640 B allocated (no leak or fragmentation); 757 KB of 868 KB flash
free with all eleven firmware files present and the ledger intact. The radio
joins in ~4 s at RSSI −32 dBm, DHCP issues `192.168.1.166`, and TCP to the
broker at `192.168.1.160:1883` completes in 12 ms. The watchdog was confirmed
armed and functioning: with the firmware interrupted at the REPL the board
reset at 7.8 s. ## Root cause Before anything was touched, the board reported
`machine.reset_cause() == 3` (`WDT_RESET`). Its last restart was a watchdog
timeout, not a power cycle. `NetworkSupervisor.ensure_connected()` performed
the Wi-Fi association wait **and** the MQTT connect inside a single call, while
`main.py` fed the 8 s watchdog only once per loop iteration. Both legs were
measured on the board: - Wi-Fi join from cold: ~4,000 ms (previously bounded by
`SOCKET_TIMEOUT_SECONDS = 5`) - TCP connect to an unreachable LAN host with the
firmware's own timeout: **5,003 ms** That is ~9 s between two watchdog feeds
against an 8,000 ms watchdog. The board reset *mid-connect*, before the failure
was ever recorded as a backoff, then rebooted into exactly the same conditions
and did it again — a permanent reset loop for as long as the broker was
unreachable. This matches the reported symptom precisely: the board goes idle
for days, the broker host goes down or changes address, and the pump controller
loops forever and looks dead until something power-cycles it at a moment when
the network happens to be healthy. The RP2040 hardware watchdog maxes out at
~8,388 ms, so the budget cannot be raised to fit the network. The blocking work
had to fit under it instead. Worst case was larger than 9 s: `_connect_mqtt`
also blocked on CONNACK and on three separate QoS 1 SUBACK reads, and
`publish(qos=1)` blocks on its PUBACK, with up to four publishes drained per
tick. ## Secondary defects fixed in the same path 1. **No liveness bound.**
`_maybe_ping` sent PINGREQ every 20 s and updated `_last_ping_ms`
unconditionally; nothing ever checked that a PINGRESP came back. A half-open
TCP connection left the board reporting `mqtt_connected: true` indefinitely. 2.
**The socket timeout was silently cleared.** `connect()` set a timeout, but
`check_msg()` → `wait_msg()` called `sock.setblocking(True)`, equivalent to
`settimeout(None)`. After the first poll every later read could block the main
loop forever. 3. **`poll()` caught only `OSError`** while `publish()` caught
broad `Exception`. The vendored client can raise `AssertionError`, `IndexError`
or `MemoryError` on a malformed packet; those escaped into the main loop and
stopped the relay deadline checks. 4. **No escalation.** `ensure_connected`
retried forever at the 60 s cap, never resetting the CYW43 and never resetting
the board, while the loop kept feeding the watchdog — hiding a wedged radio
rather than recovering from it. 5. **Cosmetic:** `uptime_ms` was a `ticks_diff`
against a boot reading, which goes negative after ~6.2 days (half the tick
period). ## Changes made `Firmware/qp_net.py` — the connect sequence is now a
state machine staged across loop iterations (`IDLE` → start association, non-
blocking → `WIFI` → poll `isconnected()` each tick → handshake). The MQTT
handshake is the only blocking step left and is bounded by
`SOCKET_TIMEOUT_SECONDS`, with watchdog feeds around it and between
subscriptions. Added `stale()` liveness detection driven by an `activity_hook`
the client fires for every received packet (PINGRESP included), `reset_radio()`
for the escalation ladder, broad exception handling in `poll()`, watchdog
feeding in `publish()`, wrap-safe tick arithmetic, and a `_restore_timeout()`
in the vendored-client subclass that restores the socket timeout instead of
clearing it. `Firmware/qp_config.py` — `SOCKET_TIMEOUT_SECONDS` 5 → 3; new
`WIFI_JOIN_TIMEOUT_MS = 8000`, `MQTT_INACTIVITY_TIMEOUT_MS = 90000`,
`RECONNECT_RADIO_RESET_ATTEMPTS = 5`, `RECONNECT_HARD_RESET_ATTEMPTS = 20`,
`OUTBOUND_DRAIN_PER_TICK = 4`. The measurements behind each value are recorded
in the file. `Firmware/main.py` — passes the watchdog to the supervisor;
accumulates uptime tick by tick instead of differencing against a boot reading;
reports `consecutive_failures` and `radio_resets` in health; and adds
`_should_hard_reset()` / `_hard_reset()`, which reset the board after the full
escalation ladder **only while no pump is running and none is queued**.
`Firmware/qp_controller.py` — `Clock.ticks_add()` and wrap-safe run-deadline
arithmetic. `tests/test_quad_pump_firmware.py` — `FakeClock.ticks_add`, plus a
`NetworkSupervisorTest` class of 14 cases driving the real supervisor with only
its two MicroPython-only steps stubbed.

**Decisions:** ADR-030 (stage the connect inside the watchdog budget), ADR-031
(liveness bound plus radio/board reset escalation ladder), ADR-032
(`WIFI_JOIN_TIMEOUT_MS` as a measured stall detector).

**Limitations:** The escalation ladder's final rung — `machine.reset()` after
20 consecutive failures — was verified by unit test and by inspection, not by
driving a real board through 20 failures. The relay map remains netlist-derived
and no relay has been observed to click. Fuse sensing remains unavailable
(ADR-019, OQ-D).

**Deployment:** Done for the device. The `Peripherals/Pump-Power-Controller`
submodule is **uncommitted** and still carries commit `25e3fd2` that the parent
repository does not record, so both a submodule commit and a parent pointer
bump are outstanding. Do not commit `qp_secrets.py` further.

## 2026-09-06 — announcement routing repair
<a id="session-handoff-2026-09-06-announcement-fix"></a>

Fix the owner's live arrival tests speaking the background-work
acknowledgement.

**Shipped:** /speak now creates a typed announcement, not a voice command.
Router sends supplied text to its existing voice-worker helper and GUI, without
classifying, invoking an agent/tools, creating a job, or emitting human
activity signals.

**Decisions:** ADR-038. Typed system-output routing fixes classification and
protects sourced briefing text from a second model rewrite. Existing voice-
worker API is reused.

**Limitations:** Text-server HTTP 200 still confirms enqueue, not audible
playback. The existing speech helper remains best-effort. Source text may be
technical; this repair does not add greeting generation or promise verbatim
"welcome home" output.

**Deployment:** Restart main agent/text server to load the changed message type
and router. Repeat absent→present injection afterwards; previous committed
receipts remain.

**Security:** Existing /speak authorization is preserved. Announcements cannot
run tools or physical actions. No new external integration or speech-worker
endpoint.

## 2026-09-06 — concise briefing speech
<a id="session-handoff-2026-09-06-briefing-speech"></a>

Fix owner-reported logs/JSON spoken by arrival briefings.

**Shipped:** Separate diagnostic text from deterministic speech; filter
presence metadata and summarize legacy queued payloads safely.

**Decisions:** ADR-039; no model rewrite. Candidate contract adds optional
spoken_text while preserving diagnostic text and source evidence.

**Limitations:** Safe fallbacks can be generic. HTTP acceptance is not
playback. Baseline p50 1238 ms / p95 2541 ms was not remeasured. Triggers,
bounded selection, model-failure fallback and critical overflow behavior remain
unchanged.

**Deployment:** Restart awareness backend; pending old payloads use safe
rendering too. Main agent needs the previous announcement fix loaded.

## 2026-09-06 — Human context and internal ingestion
<a id="session-handoff-2026-09-06-human-context"></a>

Turn the awareness subsystem from a device backend into one that also knows
about the person it serves and about its own work, and add a way to put a
message into it by hand while debugging.

**Shipped:** Seven refactoring steps plus a manual-input endpoint, all
authorized by the owner in this session: 1. Registered `owner` (person) and
`butler` (agent) as entities, and the `talos_agent` source, in registry
bootstrap. 2. Made ingestion transport-plural: the pipeline is built at API
startup independently of MQTT and is shared by both ingress paths. 3.
Conversation reported as bounded interaction *facts* (started/ended, modality,
routing mode, duration, ok) — never utterance text. 4. Wake word and barge-in
treated as presence observations that decay through the existing freshness
worker. 5. Agent job outcomes and failed tool calls emitted as `agent.*`
events. 6. Situation broker honors `interruptibility` and scores
`conversation_relevance`; presence is its own section. 7. Wired the previously
caller-less `POST /memory/candidates` to a new `propose_memory_candidate` MCP
tool. B. `POST /ingest` — internal/manual ingestion returning the pipeline
disposition synchronously. Unsorted-data handling was explicitly out of scope
this session.

**Decisions:** ADR-050 (record presence/interaction/agent outcomes, never
transcripts) ADR-051 (POST /ingest runs the same pipeline; no bypass) ADR-052
(metadata.allowed_transports; internal sources cannot be forged over the LAN
broker) ADR-053 (interruptibility honored; relevance orders within a priority
band only, never across one) ADR-054 (sources may opt out of offline detection;
silence is only a fault for a source expected to report on a schedule)
Renumbered from this session's original ADR-028..032, which collided with the
plant-waterer ADR-028..032 added on `main` while this branch was diverged; see
ADR-050 in DECISIONS.md.

**Limitations:** - Interaction events carry `entity_ids` only when the caller
genuinely knows them; the router currently cannot attribute an utterance to an
entity, so in practice that list is usually empty and conversation relevance
contributes nothing. This is reported in the snapshot's `limitations` rather
than papered over. Populating it (e.g. from device-action tool parameters) is
the obvious next increment. - User location within the home is still not
modeled at all. - Presence is single-occupant: one `owner` entity, no
identification of who is present. - Text-modality presence proves someone is at
a keyboard, not in the room; it is recorded with its own modality so the two
are never conflated. - `propose_candidate` inserts with status "active" and
lower confidence rather than status "candidate"; the review queue implied by
the status column is still not a workflow anyone drives.

**Deployment:** No migration to apply. New registry rows are seeded
idempotently on next backend start (ON CONFLICT DO NOTHING), including on an
already-booted database. The rule policy version moved 1 -> 2 and is re-
registered in schema_registry at startup. Both new environment variables
default to enabled; no configuration change is required to adopt this, and
setting either to 0 restores the previous behavior.

**Security:** `POST /ingest` is loopback-bound and bearer-gated by the same
`require_write_auth` as other mutations, and can be disabled outright with
BUTLER_AWARENESS_INGEST_API_ENABLED=0. It grants no authority the broker path
does not already have: registry topic ownership still applies, so it cannot
write on behalf of an unregistered source. ADR-052 is a net security
*improvement*: internal sources are now unforgeable from the unauthenticated
LAN broker, which was previously possible for any `home/` topic. No new data
leaves the host. Utterance text is never transmitted or stored.

## 2026-09-06 — Phase 9A
<a id="session-handoff-2026-09-06-phase-09a"></a>

Implement the requested Phase 9 plan within its explicit sub-phase gates.

**Shipped:** Deterministic read-only candidate assembly from alerts, pending
attention, transitions, agent/interaction events, and hourly measurement
aggregates. Candidate contract extends the situation broker's Candidate
vocabulary with category, entity/source, timestamp, query identifier, evidence,
and novelty. Shared temporal helpers render one-line historical qualification.
Arbitrary event payload text and memories are not included. Window derives from
the latest confirmed notification delivery carrying metadata.briefing_kind, or
an explicitly audited configured first-run window. All storage reads share a
repeatable-read snapshot. Time/count/global bounds are enforced and audited.
Potential critical-alert truncation fails closed. No partial result is returned
on query failure; only error type/kind is logged. Novelty uses SQL pooled
sample variance from complete prior hourly buckets, with units separated and no
self-baseline. Empty results contain no filler.

**Decisions:** ADR-033: reuse situation contract and notification ledger; no
migration for 9A. ADR-034: SQL pooled novelty; bounded history is not evidence
of first-ever; no partial safety summary after overflow/query errors.

**Limitations:** 9A only: no trigger behavior, delivery cap, model selection
guard/fallback, prompt version, delivery producer, or user feedback capture
exists yet. Delivered attention and alert incidents are excluded, but
comprehensive cross-kind deduplication of every candidate remains 9B work.
Missing/constant/nonfinite/over-bound baselines are unscored. Materialized
aggregate refresh lag can reduce coverage. Aggregates combine sources per
entity/measurement/unit. No claim of first-ever observations is made. Derived
records may have unknown source attribution; it is shown explicitly. Critical
overflow fails assembly; independent existing alerting is unchanged.

**Deployment:** No migration or live setting changes required. Four optional
configuration fields control assembly only (24-hour default lookback, 100
candidates, seven-day baseline, z threshold 3); this does not turn on proactive
output.

## 2026-09-06 — Phase 9A–9D
<a id="session-handoff-2026-09-06-phase-09-complete"></a>

Complete the proactive briefing plan. Owner explicitly authorized continuation
through 9D without further pauses except for critical reasons, requesting
efficient implementation/testing. No subagents were used.

**Shipped:** 9A: deterministic bounded candidates, six categories,
temporal/source/query provenance, SQL novelty, first-run/delivery-derived
windows. Extended to exclude confirmed items across kinds and apply structured
preferences. 9B: daily host-local schedule and stored arrival transitions,
idempotent outbox keys, restart recovery within configured windows, hard per-
batch cap, durable critical continuations, quiet-hours deferral,
receipt/attention bookkeeping, and truthful failures. Ordinary notifications
keep their own queued alerts/reminders; no second notification egress was
created. 9C: separate filtered outbox worker, bounded local Ollama ranking,
frozen selection before delivery, strict supplied-id validation, critical
overrides, source-only output text, prompt/model/selection provenance, and
deterministic fallback. The model decides neither the moment nor detection nor
severity. 9D: explicit dismissal/interest/neutral feedback using existing
memory writes, structured exact-key retrieval, filtering before prompt and
before delivery, and bearer-gated API/MCP operations. Critical items cannot be
dismissed. The work landed as `butler/awareness/briefing/` (service, worker,
selection, feedback), `butler/awareness/context/briefing.py`,
`butler/awareness/history/briefing.py`, `butler/awareness/api/routes/briefing.py`,
and four briefing test modules.

**Decisions:** ADR-033/034 (9A), ADR-035 (dedicated outbox/ledger), ADR-036
(critical batches and honest confirmation), ADR-037 (bounded ranking and
durable preferences). OQ-M/N resolved. OQ-O records production acceptance still
outstanding.

**Limitations:** Proactive delivery defaults off. Enable
BUTLER_AWARENESS_BRIEFING_ENABLED=1 on restart; defaults are 08:00 host local,
arrival enabled, cap 3, voice channel. Optional ranking defaults off. It uses
configured CHAT_MODEL on loopback Ollama when enabled, otherwise explicit
deterministic fallback. Adapter acceptance is the delivery boundary. Existing
/speak phrases through the reply system; GUI avoids that model dependency. A
crash/timeout after enqueue but before receipt commit can duplicate transport
because existing adapters have no end-to-end idempotency/playback
acknowledgement. Confirmed committed receipts prevent subsequent candidate re-
offering; exactly-once speech is not claimed. Critical query overflow still
fails assembly rather than silently truncating critical context; ordinary
alerting is independent. Novelty remains unscored with
missing/constant/nonfinite/over-bound baselines; aggregate lag limits coverage.
No first-ever claim from bounded history. Presence is single-owner and
interaction-based, not proof of physical arrival. Scheduled catch-up is today
only; arrivals have a bounded catch-up window.

**Deployment:** No migration. Opt-in settings and their defaults are documented
in the subsystem README. No existing live settings were changed. Worker state
is exposed in health/metrics, receipts in GET /briefings, and feedback in POST
/briefings/feedback plus the two narrow MCP tools. Do not also enable the old
commented-out morning_report_job schedule.

**Security:** No remote trigger endpoint. Feedback and receipt API routes use
configured bearer auth. Model requests use only loopback Ollama, no
proxy/redirects, bounded prompts/timeouts/output. Model text never drives
physical state, detection, alerts, or delivered candidate wording. Feedback
reads exact structured normal/personal active memories only; restricted memory
statements and transcripts are not read. No new credentials or external
integrations.

## 2026-09-07 — announcement recall
<a id="session-handoff-2026-09-07-announcement-recall"></a>

Owner requested remembering proactive output in later voice turns.

**Shipped:** Persist exact rendered wording in existing delivery receipts;
expose recent accepted voice output in situation context and saved briefing
text through the existing history tool. No fabricated legacy backfill.

**Decisions:** ADR-040. Output is historical evidence of an attempted/accepted
announcement, not a fact about a real arrival or proof of playback.

**Limitations:** Latest three voice receipts in 24 hours enter budgeted
context; long excerpts truncate at 800 characters and are labeled. Full
briefing wording remains tool-accessible within existing history/retention
limits. Legacy receipt wording is unknown. Baseline p50 1238 ms / p95 2541 ms
was not remeasured.

**Deployment:** Restart awareness backend and MCP provider/main agent. Use a
fresh briefing to test recall. No migration or changes to trigger behavior.

**Security:** No model calls, physical actions, or external services. Quoted
announcement data is explicitly distinguished from instructions/facts.

## 2026-09-08 — awareness block diagram
<a id="session-handoff-2026-09-08-block-diagram"></a>

Explain the awareness system with a detailed block diagram.

**Shipped:** Four Mermaid diagrams and supporting explanation of current
repository behavior.

**Decisions:** No new architecture or owner decisions; DECISIONS.md unchanged
by this task.

**Limitations:** Diagrams describe checked-out implementation, not verified
running services; Mermaid rendering not visually tested.

**Deployment:** None.

## 2026-09-08 — Four reported behavior fixes
<a id="session-handoff-2026-09-08-four-behavior-fixes"></a>

Close out four owner-reported defects: an unrequested "welcome back" after a
quiet stretch, a morning briefing that said only "plant waterer offline", a
failing sleep/dim tool call, and 500-character response truncation.

**Shipped:** (1) Presence staleness is now resolved through one shared helper,
`effective_state_status` in `butler/awareness/state/freshness.py`, so the read
path (`SituationBroker._qualified_status`, `history/queries.py`) honors the same
`state_freshness_detection = false` opt-out the worker does; transitions whose
value is unchanged are suppressed for owner presence, and a source migration
clears the stale `stale_after_seconds: 900.0` still on the deployed
`talos_agent` row (`reconcile_never_expiring_state` repairs rows the old
deadline had already marked stale). Speech `VERSION` is `briefing-speech-v2`.
(2)-(4) Briefing content selection, the sleep/dim tool call, and the response
length cap were repaired in the same pass.

**Deployment:** Restart the awareness backend and the text/voice agent, and run
migrations so the source-metadata fix lands on the live row.

## 2026-09-08 — Launcher logs and LLM I/O tabs
<a id="session-handoff-2026-09-08-launcher-llm-debug"></a>

Put ordinary launcher logs in a separate tab and add a third tab that shows
exactly what is sent to and received from the LLM for prompt-breakage
debugging.

**Shipped:** Replaced the launcher's single-page layout with Launcher, Logs,
and LLM I/O tabs. Launcher-managed main-agent children now emit structured LLM
boundary records. Chat Completions capture includes the final request dict
after tool conversion, raw SDK response chunks, assembled text, tool calls,
finish reason, and telemetry. Warmup and Responses API traffic are labeled
separately. The GUI routes valid main-process records only to the LLM tab and
leaves malformed or non-main records visible in ordinary logs. Sent records
render in blue/cyan and received records render in green, with distinct heading
and payload tags.

**Decisions:** ADR-042. Exact LLM capture is enabled only for a launcher-
managed main process, travels through the existing private stdout pipe, is not
separately persisted or network-served, and is capped at the latest 5,000,000
displayed characters. Capture errors fail open for inference.

**Limitations:** The display is an SDK-boundary representation: it shows the
exact request object supplied to the SDK and every response chunk the SDK
exposes, not encrypted HTTP bytes. The oldest display text is discarded after
the five-million-character cap. Directly starting the main agent without the
launcher does not enable capture. A launcher-started headless process emits the
structured records to its console because no GUI consumes them.

**Deployment:** Restart the launcher and launcher-managed main agent. No
setting, schema, database, network listener, or external service changes are
required.

**Security:** The LLM tab may contain private conversation history, remembered
facts, awareness context, tool arguments, and tool results. It is local and
ephemeral but remains shoulder-surfable and copyable. No secret redaction is
attempted because that would conflict with the requested exact payload view;
API transport headers/keys are not part of the SDK request object and are not
captured.

## 2026-09-08 — Persistent LLM debug transcripts
<a id="session-handoff-2026-09-08-llm-debug-persistence"></a>

Determine whether exact LLM I/O was permanently logged and, when it was not,
create a persistent location under the logs folder.

**Shipped:** Confirmed the existing feed was stdout/GUI memory only. Added
best-effort per-run JSONL persistence at `butler/logs/llm_io_<UTC
timestamp>_<pid>.jsonl`. Launcher-managed main-agent processes enable both the
existing stdout feed and the new file sink. The GUI identifies the saved-file
pattern. Exact transcript files are git-ignored.

**Decisions:** ADR-043 supersedes ADR-042 only where it prohibited a persistent
transcript. Per-run files preserve unredacted events, have no automatic
retention/pruning, and fail open for inference.

**Limitations:** No transcript appears until the restarted launcher-managed
main agent performs an LLM call. Files can grow for the lifetime of a process
and accumulate across runs because permanent logging has no automatic pruning.
Directly launched main agents remain opt-out unless the log-directory variable
is explicitly supplied.

**Deployment:** Restart the launcher and its managed main agent. New files will
appear under `butler/logs` on the first LLM debug event.

**Security:** These files contain unredacted prompts, conversation history,
memory, awareness context, tool schemas, tool arguments/results, and model
output. They exclude API transport headers but must still be treated as
sensitive local data. Gitignore reduces accidental commits but is not access
control or encryption.

## 2026-09-08 — Selectable Yeti/ReSpeaker Capture
<a id="session-handoff-2026-09-08-microphone-profiles"></a>

Repair the severe STT regression after switching from a Blue Yeti to a Seeed
Studio ReSpeaker XVF3800, and add an explicit launcher choice for either
microphone.

**Shipped:** Added shared microphone profiles, deterministic named PortAudio
capture, stereo PCM channel selection, launcher GUI and headless selection,
profile-specific endpoint/threshold behavior, regression tests, and operator
documentation. Set the tracked and current machine-local launcher selection to
ReSpeaker.

**Decisions:** ADR-041 selects microphone-specific capture contracts. The
ReSpeaker uses 16 kHz stereo USB channel 2 and calibrated SpeechRecognition
segmentation. Its barge-in and experimental idle VAD are disabled until a real
far-end/AEC topology and owner-visible corpus pass. The Yeti keeps its existing
Windows communications-AEC contract and fixed threshold.

**Limitations:** Production recall and WER are not yet measured on the new
path. The existing post-capture RMS gate remains 300. ReSpeaker barge-in and
experimental idle VAD are unavailable by design until their independent
acceptance requirements pass. If the USB friendly name changes, its
configurable name fragment must be updated.

**Deployment:** Restart the voice worker, or stop and restart the launcher
stack, to load the selected profile. Use the GUI **Room microphone** dropdown
or headless `--microphone respeaker|yeti`. No firmware upgrade is required for
this repair.

**Security:** Capture remains local. No PCM or transcript content was added to
logs or persisted by this repair. Profile selection only changes the voice
child process environment.

## 2026-09-08 — ReSpeaker XVF3800 STT Diagnosis
<a id="session-handoff-2026-09-08-respeaker-stt-diagnosis"></a>

Investigate the severe STT accuracy regression after replacing the Blue Yeti
with a Seeed Studio ReSpeaker XVF3800 USB 4-mic array, and identify whether the
cause is in Butler or the device.

**Shipped:** Traced the configured and live Windows capture paths, enumerated
the exact PortAudio devices used by the voice environment, compared fresh voice
telemetry before and after the fallback, inspected the Butler capture/STT code,
checked current official ReSpeaker documentation and firmware history, and
queried the connected XVF3800 through its official USB control protocol in
read-only mode.

**Decisions:** None. OQ-P records the owner-visible acceptance and capture
architecture choice required before a repair.

**Limitations:** Windows/PortAudio's precise stereo-to-mono mixing behavior was
not established from room audio. Whether it selects left or combines both
channels, the current path does not intentionally consume the documented right
ASR channel. The telemetry lacks rejected transcript text by design, so the
snapshot measures pipeline acceptance rather than WER against ground truth.

**Deployment:** The deployed voice worker is presently on the generic
SpeechRecognition fallback, not the pinned AEC/idle-VAD path described by the
tracked settings. Merely changing Windows's default microphone is insufficient
because Butler separately pins full MMDevice identities.
## 2026-09-13 — Pump 3 (Philodendron) registration; watering-failure diagnosis
<a id="session-handoff-2026-09-13"></a>

Owner asked why pumps 3 and 4 were unreachable and why the 2026-09-13 15:30
watering of pumps 1 and 2 did not run, then reported that a pump is now
physically connected to channel 3 watering a Philodendron.

**Shipped:** Registered pot 3 end to end — `plant_pot_3` seed entity
("Plant pot 3 (Philodendron)"), channel descriptions on `run_pump`/`stop_pump`
naming each pot and marking channel 4 as wired-but-unconnected, corrected
`request_device_action` / `get_current_state` / `water_plants` docstrings so the
legacy 2-pot tool can no longer be read as the system's limit, `philodendron`
added to the physical-action noun guard in `runtime.py`, and a canonical
channel-3 `mosquitto_pub` example in `Peripherals/debug_command.txt`. No
firmware, board, or migration change was needed: `CHANNELS`,
`CHANNEL_RELAY_GPIO`, and the action registry already carried all four
channels.

**Diagnosis (no fix applied, owner decision pending):** Three independent
defects. (1) Channels 3/4 were never blocked in code — the model inferred the
"pots 1 and 2 only" limit from the legacy `water_plants` tool, and the
deterministic router could not correct it because `water` does not match
"watering" and ASR had turned "pump" into "trump"/"comes". (2) `run_pump`
channel 2 (948a46f2) really was published at 15:30:02 and honestly timed out —
`quad_pump_canonical` had fired its last will at 15:29:47, fifteen seconds
before dispatch; `source_health_history` shows this device flapping roughly
every 15 minutes. (3) The channel-1 turn produced no action request row at all,
yet was answered "Pump 1 request is approved" — the no-tool-call guard at
`runtime.py` is gated on `_looks_like_physical_action_request`, which failed on
the mis-transcribed noun, so nothing forced a tool call or an honest denial.
Separately, `IngestionPipeline` flips any non-healthy source back to `healthy`
on `message_received` for *any* ingested event, including the broker's own
`{"online": false, "reason": "last_will"}` — which is why `sources` reports the
pump healthy while it is unreachable.

**Decisions:** Pot 3 gets no legacy pin encoding. Legacy pins 16 and 18 have no
owner-confirmed pot (`qp_config.LEGACY_PIN_TO_CHANNEL`), and the established
contract is to reject an unmapped legacy pin rather than guess it, so channel 3
is reachable only through the canonical `run_pump` path.

**Validation:** 20 action-registry tests passed in `.venv-awareness` and 15
home-automation/runtime-recovery tests in `.venv-main` (`unittest`; pytest is
not installed in either venv). All five touched Python modules compile, the
TOML parses, the registry loads and validates `{"channel": 3}`, and the noun
guard was confirmed to fire on "water the philodendron". No process restart,
GUI smoke test, live MQTT command, or full-suite run occurred.

**Limitations / outstanding:** The `plant_pot_3` row is seed-only — inserts are
`ON CONFLICT DO NOTHING` and run at startup, so the awareness backend must be
restarted before the entity exists in the live database (it is absent as of
this session). Nothing was done about the three diagnosed defects, the pump's
MQTT flapping, or the last-will health false positive; the pot-2 species is
still unrecorded.

## 2026-09-24 — SMS control channel over Twilio

**Task:** Owner asked to text the system commands (e.g. water plants, adjust
lights) through their Twilio number and get replies by text, not speech.
Calling deferred.

**Implemented:** New `butler/sms/` package. `twilio.py` holds `SmsConfig`,
stdlib Twilio signature validation, and REST send. `server.py` is a local
listener (default `127.0.0.1:8430`) meant to be exposed only via Tailscale
Funnel; it rejects bad `X-Twilio-Signature`, silently ignores non-allowlisted
senders, dedupes `MessageSid`, answers Twilio with empty TwiML at once, and
enqueues a normal `text_cmd` (session `sms:<number>`, source `sms`, SMS
formatting note as `extra_context`). Replies go out via the Messages API;
background-lane jobs get the ack and then the job result. `butler/main.py`
starts/stops it; it is disabled by default and refuses to start without public
URL, Twilio SID/token, from-number, and sender allowlist. Settings added to
`settings.env` and `.env.example`; README "SMS Control" section added. No
new agent tool, migration, or dependency; the text-agent server is unchanged
and stays private.

**Validation:** `tests/test_sms_webhook.py` (11 tests, including Twilio's
documented signature vector) plus `tests/test_text_server_phone_events.py`
(5 tests): 16 passed in `.venv-main` via `unittest`. `butler.main` imports.
No live Twilio send, Funnel exposure, restart, or full-suite run occurred.

**Limitations / outstanding:** Owner must add Twilio credentials, enable
Funnel for the node, set the Twilio messaging webhook, and restart Butler.
US A2P 10DLC (or toll-free verification) is required for outbound replies to
deliver. Sender allowlist is the authorization boundary and SMS caller ID is
spoofable. Inbound voice control is not built.

## 2026-09-30 — Shared runtime and remote-ready InfoPanel boundary

**Task:** Consolidate the main and voice Python versions/environments, and
split the GUI from main so it can later run on another machine.

**Implemented:** Replaced the main/voice requirement manifests with one Python
3.12 `requirements-runtime-py312.txt` and mapped both launcher components to
`.venv-runtime`. The explicit NumPy conflict is resolved at 2.3.4. Added a
focused `requirements-display-py312.txt` / `.venv-display`. Main is now
headless: it owns a thread-safe latest display projection and serves it through
authenticated `GET /display/state`, including the authoritative sleep/dim
state. `butler.display.worker` polls that endpoint and feeds the existing pygame
renderer without importing the main runtime or reading its local state file.
The launcher starts the display independently, supports `--no-display`, and
pins local display traffic to loopback while allowing a separately configured
remote agent URL. Bootstrap scripts and active documentation now use the new
environment names.

**Validation:** Six display-boundary/launcher tests, 20 text-server tests, 65
barge-in tests, six microphone-profile launcher tests, and 15 MCP-selection
tests passed. A composed Python 3.12 import using the installed main and voice
site packages loaded NumPy 2.3.4, MCP, pygame/ModernGL, faster-whisper,
openwakeword, PyAudio, SpeechRecognition, `butler.main`, `butler.voice.agent`,
and the display client together. `git diff --check` passed. The first compileall
attempt could not write existing `__pycache__` directories in this relocated
checkout; imports and tests supplied syntax/import coverage instead.

**Limitations / deployment:** No live Windows install, microphone/AEC session,
or pygame display smoke test was run. Create `.venv-runtime` and `.venv-display`
from the new manifests before deployment. A remote panel also requires a
reachable `TEXT_AGENT_HOST`, an allowed panel network, and matching bearer
token; the defaults remain loopback-safe. Awareness remains in its own venv.

## 2026-09-30 — Correlated observability and operations visualization

**Task:** Implement the repo-wide visualization recommendations for bug
reduction, latency optimization, and operational analysis.

**Implemented:** Upgraded privacy-safe pipeline telemetry to schema v2 with a
trace ID plus host, process, PID, process boot ID, runtime version, build SHA,
and non-secret configuration fingerprint. Launcher-managed children receive
stable process/boot identities. The debug dashboard now builds correlated
request traces with timed-stage bars and p50/p95/max latency, aggregates
per-tool success/failure and latency, reads sanitized durable job state, and
pulls awareness worker/queue metrics plus physical-action lifecycle timestamps.
Host resource history is retained by the dashboard process across browser
reloads. Main health now exposes central queue depth, bounded awareness-signal
queue/counters, side-effect-free MCP lifecycle state, and remote display
clients. The display client reports the last snapshot sequence consumed through
an authenticated heartbeat. No prompt text, tool arguments, job request text,
raw PCM, credentials, or continuous idle-room audio were added to telemetry.

**Validation:** Pipeline telemetry (1), debug dashboard (10), display boundary
(8), text server (3), launcher (18), MCP disable/selection (15), awareness signals
(7), awareness action unit tests (20), barge-in observability (6), and barge-in
agent integration (16) passed: 104 focused tests total. JavaScript syntax validation and
`git diff --check` passed. The MCP lifecycle module could not be collected by
the repository's current unittest-discovery invocation because it imports
`tests.test_local_mcp_client_resources` while `tests/` is not a package; the
separate MCP selection suite passed. No live model, voice session, MQTT action,
remote display, or production awareness database was used.

**Deployment / limitations:** Restart the main, voice, display, awareness, and
dashboard processes to populate the new feeds. The launcher derives build SHA
from Git; non-launcher deployments can supply `BUTLER_BUILD_SHA`. Dashboard host history is
process-retained, not a new durable metrics database. Barge-in accuracy still
requires the existing opt-in fixture/ground-truth workflow; runtime counters
alone cannot infer false negatives.

**Optimization follow-up:** Removed the synchronous display-heartbeat request;
the last rendered sequence is now acknowledged on the next normal state GET,
halving steady-state display HTTP traffic and removing a possible two-second
delay. Dashboard file/database/remote feeds now use bounded TTL caches, the
three cold remote reads run concurrently, and only 300 downsampled host-history
points are transported while the process retains up to 3,600. Conversation and
voice-benchmark text is redacted unless `BUTLER_DEBUG_INCLUDE_CONTENT=1`.
Pipeline JSONL and voice benchmark CSVs rotate non-destructively at configurable
32 MiB limits. The dashboard now reads both the current rolling
`voice_benchmarks.csv` and archived timestamped files; it previously ignored
the current file. Automatic deletion was not added because no retention window
was authorized. Updated focused coverage is 111 passing tests; JS syntax and
patch whitespace checks also pass.

## 2026-10-02 — Launcher hang with missing split-runtime venvs

**Symptom:** First GUI launch on this branch sat on "starting..." while main,
display, and voice never came up.

**Cause:** ADR-055 moved main/voice to `.venv-runtime` and display to
`.venv-display`, but neither existed on the host. `venv_python()` silently fell
back to the legacy `.venv` (the launcher's own Python 3.14 environment), so all
three children crashed on import (`openai`, `pygame`, and `audioop` missing).
`_wait_port` did not watch the child, so the launcher waited out the full 45 s
main timeout before continuing, which looked like a hang.

**Change:** Components with a dedicated venv no longer fall back to `.venv`.
A missing interpreter is logged with the exact create/install command
(`venv_setup_hint`) and that component is skipped instead of spawned.
`_wait_port` now returns as soon as the watched child exits and logs its exit
code. Separate runtime/display environments are kept as designed (owner
decision); splitting the display into its own repo was discussed and deferred.
Created `.venv-runtime` and `.venv-display` on this host from their py312
requirements files.

A fresh `.venv-runtime` resolved the unpinned `mcp[cli]` to 2.3.0, which
removed `mcp.server.fastmcp`; main still started but the local MCP server died
and the agent warmed with 3 tools instead of 27. Pinned `mcp[cli]>=1.28,<2` in
`requirements-runtime-py312.txt` (resolved 1.30.0). SpeechRecognition 3.14.3
installs a top-level `tests` package into site-packages that shadows this
repo's `tests/` for `python -m unittest tests.<module>`; run suites from that
venv with `python -m unittest discover -s tests -t tests -p <pattern>`.

**Validation:** New `tests/test_launcher_venvs.py` (5) plus existing launcher,
display-boundary, maintenance, and microphone-profile suites: 32 tests passed
under both `.venv-main` and `.venv-runtime`. Smoke run of `python -m butler`
from `.venv-runtime` bound 8420 and warmed 27 tools; component modules import
in their target venvs. No live GUI launch, voice session, or display window
was run by the agent.

## 2026-10-02 — Barge-in silently disabled by stale endpoint pins

**Symptom:** Barge-in never fired. In the 2026-10-03T02:45 run, a 14 s spoken
reply was recorded by ordinary capture (Butler's own speech plus the owner's
"that's enough") and rejected as `wake_word_missing_in_transcript`. Every
`barge_in_metrics_snapshot` back to 2026-09-22 shows zero candidates.

**Cause:** Windows re-enumerated both test-rig endpoints (same ReSpeaker
XVF3800 and BenQ GL2460 display audio, new MMDevice IDs). The pinned
`...5dda5d51...` capture and `...2b69dbdf...` render IDs no longer exist, so
`_start_aec_duplex` raised on the default-pair check and the worker fell back
to the plain profile microphone. That fallback is only a console `print`; no
telemetry records it.

**Change:** Re-pinned `BUTLER_RESPEAKER_CAPTURE_ENDPOINT_ID`,
`BUTLER_AUDIO_CAPTURE_ENDPOINT_ID` (`...de76a30a...`) and
`BUTLER_AUDIO_RENDER_ENDPOINT_ID` (`...d43b40c9...`) in `settings.env`. Same
physical devices that previously passed the AEC contract, so the probe was not
re-run.

**Validation:** In `.venv-runtime`, the pins now equal the current default
pair and `SileroProbabilityVAD()` constructs in the worker import order. Not
run live: no voice session or barge-in attempt was made by the agent.
Observed but not fixed: in a bare process, querying the winrt endpoints before
the first faster-whisper/onnxruntime import segfaults in onnxruntime 1.30
(access violation); importing `butler.voice.agent` first avoids it.

## 2026-10-03 — Debug console Model & Memory tab

**Request:** Owner asked for the dashboard to surface four findings from a
latency/memory investigation: first-vs-follow-up LLM latency (prompt-cache
misses on Ministral), Ollama GPU placement, per-turn prompt composition and
unused tool schemas, and whether memory is stored and injected at all.

**Findings that motivated it (not fixed):** Ministral 3's chat template places
`[AVAILABLE_TOOLS]` before the last user message, so each turn re-reads ~6.5k
prompt tokens (first-round TTFT ~1.6 s vs ~0.25 s after a tool call). 14 of 27
tool schemas (~2.7k tokens) were never called in 263 logged turns. Both memory
stores were empty (SQLite facts 0, recreated 2026-10-02 22:45; awareness
`memories` 0 with 74k events since 2026-07-26). Memory proposed into Postgres
is never auto-injected into prompts; only SQLite facts are.

**Change:** New `butler/debug_dashboard/insights.py` (bounded, read-only
readers: telemetry round stats over the newest 40 files, LLM I/O transcript
structure only, Ollama `/api/ps`, SQLite row counts) and a **Model & Memory**
tab. `prompt_ready` telemetry now carries `memory_block_chars` and
`history_message_count` (sizes only). Awareness `/metrics` gains a `memory`
section with counts by status/type, provenance rows, and newest timestamp —
never statements; a database error is reported as an error, not zero. The
stale "prompts are not persisted" dashboard notice now cites ADR-043.

**Validation:** `tests/test_debug_dashboard.py` 17 passed (4 new; one status
assertion updated from `not_available` to `structure_only` because prompts are
persisted by the launcher); new `tests/test_awareness_metrics_memory.py` 3
passed in `.venv-awareness`; `tests/test_run_command_stream.py` 16 passed with
two new field assertions; changed Python files compile; `node --check app.js`
passes. Dashboard rendered live in the browser against real logs. Not run: the
awareness `/metrics` route against a live backend (the API was not running);
the main agent was not restarted, so live turns do not yet report the new
fields.

**Observed, not fixed:** `tests/test_run_command_stream.py` writes telemetry
into the real `butler/logs/` directory; three such files from this session
were identified by `process: test_run_command_stream` and removed.

## 2026-10-03 — Launcher "Open debug console" button

**Change:** New `butler/launcher/dashboard.py` (`DashboardProcess`) and an
**Open debug console** button in the launcher GUI. It reuses a console already
listening on 127.0.0.1:8787, otherwise starts `python -m butler.debug_dashboard`
from `.venv-runtime` bound to loopback, waits up to 15 s for the port (failing
fast if the child exits), opens the default browser, and stops only a console
it started when the launcher window closes. Independent of the Supervisor, so
it works with Butler stopped. Remote binding is unchanged (still requires the
explicit `--allow-remote` flag).

**Validation:** New `tests/test_launcher_dashboard.py` 3 passed; all launcher
suites via `unittest discover -s tests -t tests -p "test_launcher*.py"` in
`.venv-runtime`: 28 passed. Live helper check: started the console in 1.2 s,
`/api/health` returned 200, and the port closed after `stop()`. The Tk button
itself was not clicked in a live launcher window.

<<<<<<< HEAD
## 2026-10-04 — Inbound ElevenLabs phone calls

**Change:** New `butler/phone/inbound_server.py`, a local listener (default
`127.0.0.1:8431`, disabled unless `BUTLER_PHONE_INBOUND_ENABLED=1`) published
via Tailscale Funnel at `/phone`. It serves ElevenLabs' conversation-initiation
webhook (dynamic-variable briefing from memory and the awareness situation),
five mid-call server tools (`recall`, `house_status`, `verify_pin`,
`ask_talos` with restricted tool access, `do_action` with full access after a
per-call PIN), and the post-call webhook (stored, summarized, written to memory,
and announced as `phone_call_completed`). Bearer token or ElevenLabs HMAC
signature required; callers outside `BUTLER_PHONE_INBOUND_ALLOWED_CALLERS` get
nothing. Inbound transcripts now record caller number, direction, and session
`phone:<number>`. `PhoneConfig.main_notify_*` got defaults, which fixed three
stale tests; four others now tolerate Windows' sqlite temp-dir cleanup lock.
Setup guide: `docs/phone-inbound/SETUP.md`.

**Validation:** Phone and SMS suites: 51 passed (15 new inbound-server tests,
1 new provider test). Full `unittest discover` in `.venv-main`: 3 failures and
37 errors, versus 3 failures and 47 errors before the change. The remaining
failures are pre-existing (awareness, audio, MCP, and prompting tests). Not
done: no live call, Funnel path, or ElevenLabs dashboard configuration was tested.

**Revision (same day):** Owner chose carrier attestation over a spoken PIN.
The ElevenLabs initiation webhook does not expose `StirVerstat`, so Talos now
owns the Twilio voice webhook (`/phone/twilio/voice`, Twilio-signature
verified). It rejects any call that is not from an allowlisted number with
`TN-Validation-Passed-A` (configurable), and registers admitted calls through
ElevenLabs `POST /v1/convai/twilio/register-call` with a briefing and a
per-call token. Tools (`recall`, `house_status`, `ask_talos` with full access)
require that token. The PIN, `verify_pin`, `do_action`, and the initiation
endpoint were removed. Phone and SMS suites: 54 passed. Not done: no live call,
and no check of which `StirVerstat` value the owner's carrier actually sends.

## 2026-10-05 — Inbound calling live; hallucinated presence source; test memory leak

**Live setup (owner-approved):** the Twilio number's voice webhook now points to
`/phone/twilio/voice`. The ElevenLabs agent has webhook tools `recall`,
`house_status`, and `ask_talos`, a tools section appended to its existing
personality prompt, and placeholder values for the `talos_*` variables. Owner
confirmed that lights off and on worked over a call through `ask_talos`.

**Hallucination:** asked how it knew the owner was home, the agent said "phone
signal". The briefing actually said `present via text` (a typed message 18
minutes earlier); Talos has no phone or location tracking. Fix: the briefing
now carries a plain-language presence note, and the agent prompt now says to
cite only the briefing or tool results and never invent data sources.

**Test leak:** `tests/test_phone_service.py` and
`tests/test_text_server_phone_events.py` wrote phone-call summaries into the
real `db/talos_memory.sqlite3` (fixture calls conv_123/456/789/evt). Both now
patch `get_default_memory_store` with an in-memory store at module level, and a
re-run added no rows. Removed 4 fixture facts and 40 fixture messages, and
cleared the test-only `main-pc` and `phone:inbound` session summaries. The
database was backed up first.
=======
## 2026-11-10 — Foreground/background rework design record

Session goal: Record the conversation and implementation plan for local,
nonblocking foreground/background work.

Current phase: Bounded architecture consultation and documentation; no awareness
runtime phase or background rework phase started.

Bounded task completed: Added a top-level design record with current behavior,
owner constraints, proposed interaction contract, staged work, acceptance checks,
and open choices.

Files added: `background_rework_11102026.md`.

Files modified: `docs/awareness-memory/IMPLEMENTATION_STATUS.md`,
`DECISIONS.md`, `OPEN_QUESTIONS.md`, and `SESSION_LOG.md`.

Migrations added: None.

Decisions made: Documented owner direction: local-only inference by default,
foreground responsiveness and job awareness, model-generated ordinary speech,
and A2000 availability if measurements warrant it. No runtime design choice was
accepted for implementation.

Assumptions confirmed or changed: Current streaming voice bypasses router job
routing; current background executor uses the hosted Responses path. This is a
source inspection, not a deployed-host validation.

Tests run: None; documentation-only change. Documentation links and diff
whitespace will be checked before handoff.

Tests passed: None at the time of this entry.

Tests failed: None at the time of this entry.

Commands not run: Python test suites, live voice/hardware runs, GPU benchmarks,
model placement checks, deployment.

Known limitations: The plan does not establish GPU fit, latency targets,
background model quality, or notification timing.

Security implications: No runtime surface changed. The plan preserves local
inference and registered action authorization/audit.

Deployment implications: None yet.

Unresolved questions: Foreground latency target, completion-delivery timing,
A2000 model/context fit, and cancellation/restart policy.

Current repository state: `main` tracked files were clean before this task;
the pre-existing untracked `Peripherals/Pump-Power-Controller` was untouched.

Next permitted task: Owner-approved, bounded implementation step from the
proposal, beginning with contracts and baseline measurements.

Required reading for next session: Top-level design record, this status file,
`ARCHITECTURAL_INVARIANTS.md`, and relevant current runtime/job/action code.

Explicit stop point: Documentation complete; no runtime work started.

## 2026-11-10 — Model interaction surface design record

Session goal: Document discrepancies and fixes needed across `/chat`,
`/chat/stream`, voice, terminal, browser, SMS, and background jobs.

Current phase: Bounded architecture consultation and documentation; no runtime
phase started.

Bounded task completed: Added a top-level interaction-surface proposal with
current routing/provider paths, a common turn/event/result contract, a bounded
migration sequence, and acceptance checks.

Files added: `interaction_surface_rework_11102026.md`.

Files modified: `docs/awareness-memory/IMPLEMENTATION_STATUS.md`,
`DECISIONS.md`, `OPEN_QUESTIONS.md`, and `SESSION_LOG.md`.

Migrations added: None.

Decisions made: Recorded the owner's direction for consistent client behavior
and local-first inference; no API shape or runtime migration accepted yet.

Assumptions confirmed or changed: `/chat` uses the router and hosted Responses
agent loop; `/chat/stream` directly uses the configured streaming backend;
the latter hardcodes voice interaction mode. Terminal/browser and SMS use the
nonstreaming path, and background jobs call the hosted loop. Source inspection
only; no deployed system validation.

Tests run: None; documentation-only task. Link and diff checks performed at
handoff.

Tests passed: None (no test suite run).

Tests failed: None (no test suite run).

Commands not run: Python tests, live local-model calls, browser/voice/SMS
end-to-end sessions, hardware tests, deployment.

Known limitations: The proposal has not selected a final HTTP endpoint shape
or measured behavioral parity and latency.

Security implications: No runtime access changed. The design calls for explicit
provider selection and no silent remote fallback.

Deployment implications: None yet.

Unresolved questions: Final endpoint shape, asynchronous completion delivery,
partial-output errors, hosted-debug control.

Current repository state: Existing documentation edits and top-level background
proposal from the prior bounded task remain in the worktree; `settings.env` was
already modified before this task and was left untouched. The pre-existing
untracked `Peripherals/Pump-Power-Controller` was untouched.

Next permitted task: A separately assigned, bounded characterization or
implementation step from the proposal.

Required reading for next session: This design record,
`ARCHITECTURAL_INVARIANTS.md`, `TOOL_IMPLEMENTATION_GUIDE.md` if agent-facing
tools change, and current text/router/runtime/client code.

Explicit stop point: Documentation complete; no runtime work started.

## 2026-11-10 — Wake-only voice interaction requirements

Session goal: Specify the desired one-utterance and wake-then-command voice
experience without prescribing implementation mechanics.

Current phase: Bounded requirements documentation; no voice runtime phase
started.

Bounded task completed: Added top-level requirements and acceptance scenarios
for both voice entry patterns, truthful action acknowledgements, interruptions,
timeouts, and local model wording.

Files added: `voice_wake_interaction_requirements_11102026.md`.

Files modified: `docs/awareness-memory/IMPLEMENTATION_STATUS.md`,
`DECISIONS.md`, `OPEN_QUESTIONS.md`, and `SESSION_LOG.md`.

Migrations added: None.

Decisions made: Recorded the owner's two required voice patterns and preference
for local model-generated ordinary speech. No technical design was selected.

Assumptions confirmed or changed: Source inspection showed wake-only transcripts
are rejected after the existing cue, and a later phrase without the wake word
is rejected. No live microphone result was claimed.

Tests run: None; documentation-only change. Link and whitespace checks performed
at handoff.

Tests passed: None (no test suite run).

Tests failed: None (no test suite run).

Commands not run: Python tests, live ReSpeaker/audio corpus, model latency
benchmarks, hardware actions, deployment.

Known limitations: No user-approved response timing target, listening-window
duration, or continued-conversation policy yet.

Security implications: No access changed. Requirements retain local inference,
authorized action boundaries, and bounded diagnostics.

Deployment implications: None yet.

Unresolved questions: Response timing, listening feedback and timeout, optional
continued conversation after a completed turn.

Current repository state: `main` tracked files were clean before this task;
the pre-existing untracked `Peripherals/Pump-Power-Controller` was untouched.

Next permitted task: A separately authorized, bounded implementation of these
voice requirements within the existing phase rules.

Required reading for next session: This requirements file,
`ARCHITECTURAL_INVARIANTS.md`, current voice callback/recognition tests, and
the relevant action and audio paths.

Explicit stop point: Requirements documented; no runtime work started.
>>>>>>> 1ef7b7c0f3f810da998e5b778ff6d855dffcaaa8

## 2026-11-14 — Pump liveness and action-truthfulness repair

Session goal: Correct inaccurate pump online/offline determination and prevent
unconfirmed watering requests from being reported as active.

Current phase: Bounded Phase 7 action/health repair authorized by the owner.

Bounded task completed: Firmware now creates a unique retained offline will for
each MQTT session and overwrites it with retained online health after connect.
Awareness no longer treats retained replay or last-will delivery as live device
traffic; last-wills transition source/state offline immediately and live traffic
alone recovers health. The pump deadline is 120 seconds. `run_pump` checks the
canonical source at request and dispatch; `stop_pump` remains available.
Runtime-bound mutation identity prevents cross-turn idempotency collisions, and
physical-action speech is derived from structured lifecycle status.

Files added: None.

Files modified: Pump firmware `main.py`, `qp_net.py`, and `plan.md`; awareness
ingestion/freshness/registry/action files and README; agent runtime and awareness
provider; five focused test modules; `IMPLEMENTATION_STATUS.md`, `DECISIONS.md`,
and this log.

Migrations added: None. Conditional registry bootstrap migration changes an
existing canonical pump `offline_after_seconds` only when it is still unset.

Decisions made: ADR-056 (live-only liveness plus retained health symmetry) and
ADR-057 (fail-closed pump starts plus lifecycle-derived action speech).

Assumptions confirmed or changed: MQTT non-retained publishes do not clear
retained values. Broker/event inspection confirmed the November 13 offline row
was retained replay, while a direct broker observation still found no live pump
traffic. Retained evidence is therefore not a connection timestamp.

Tests run: `.venv-main` unittest over firmware, streaming runtime, legacy action
wrapper, history grounding, argument parsing, and leaked-tool recovery; 120
passed. `.venv-awareness` unittest over action/ingestion/state unit suites plus
action/state/presence integration against scratch Postgres; 87 passed. Python
compile checks and root/submodule `git diff --check` ran.

Tests passed: 207 total, zero failures/errors/skips in the reported runs.

Tests failed: None.

Commands not run: Full repository suite, broker-backed ingestion integration,
live local-model acceptance, firmware flashing, production service restart,
physical relay/pump command, and production database mutation.

Known limitations: Firmware health publication was host-tested at the network
contract/helper level, not on the Pico. Current pump hardware remains offline or
unable to publish, and fuse sensing remains unavailable. The pre-existing
session-log conflict marker above was not altered as unrelated repository state.

Security implications: Energizing fails closed on non-healthy canonical-source
state; model-provided mutation identity is overwritten by runtime identity. No
new listener, arbitrary MQTT path, cloud dependency, or secret handling was
introduced.

Deployment implications: Copy the changed firmware files to the pump Pico and
reboot it; no broker firmware is involved. Restart awareness so bootstrap applies
the 120-second source deadline, then restart the main agent. The first successful
controller connection overwrites the stale retained offline message. Verify
retained online health, multiple live heartbeats, one acknowledged bounded run,
and a disconnect/reconnect cycle before acceptance.

Unresolved questions: None within the approved repair. Physical acceptance is
pending owner deployment.

Current repository state: Root tracked changes are the bounded repair listed
above. The pump submodule has targeted diffs in `Firmware/main.py`, `qp_net.py`,
and `plan.md`; its pre-task status could not be captured because the parent
worktree's initial recursive status was denied access to submodule metadata.

Next permitted task: Owner-directed deployment/physical acceptance or a separate
bounded repair; do not start another phase automatically.

Required reading for next session: This entry, ADR-056/057, Phase 7 actions,
architectural invariants, tool implementation guide, pump firmware plan, and
current implementation status.

Explicit stop point: Implementation and simulated/database validation complete;
no deployment or physical action performed.

## 2026-11-14 — Pump Pico firmware deployment

Session goal: Deploy the approved pump liveness firmware repair to the Pico
connected to this PC and verify that it reports truthfully after reboot.

Current phase: Bounded Phase 7 deployment/acceptance follow-up authorized by the
owner; no new implementation phase started.

Bounded task completed: Installed the official MicroPython `mpremote` utility in
the project main virtual environment, backed up the Pico's installed `main.py`
and `qp_net.py`, staged and checksum-verified the repaired files, retained unique
on-device copies of the prior versions, activated the repaired files, and
rebooted the Pico on COM3. Read-only MQTT observation confirmed a live online
health event, retained online health, a subsequent heartbeat, and all relays off.

Files added: None.

Files modified: `IMPLEMENTATION_STATUS.md` and this log. Device files `main.py`
and `qp_net.py` were replaced with the already-approved repository versions.

Migrations added: None.

Decisions made: None. Deployment followed ADR-056/057; no pump command was used
as a connectivity test.

Assumptions confirmed or changed: The attached VID 2E8A/PID 0005 device on COM3
was a running MicroPython Pico, not a BOOTSEL mass-storage device. Its installed
`qp_controller.Message` already supported the repaired retained-publication
field. The broker's initially observed retained last-will was stale; after the
post-flash reconnect it was replaced by retained `online=true` as designed.

Tests run: On-device SHA-256 for both deployed modules; live MQTT wildcard
observation excluding retained messages; final retained-health readback.

Tests passed: `main.py` matched
`0c3816d182934458fa97448bfc9d0bd748b02806756c5fdfac49e169ac37b3c7` and
`qp_net.py` matched
`2d5d1ba4ddefc79bbe39ab605cab731833a6438eb0bbddd252bce19ebf2bd9ef`.
The final boot published `online=true`, `wifi_connected=true`,
`mqtt_connected=true`, RSSI -30, zero dropped inbound/outbound messages, all
four relays false, and a heartbeat at about 30 seconds uptime.

Tests failed: None. One pre-verification retained read returned the expected old
offline last-will before the rebooted controller completed its reconnect; live
observation then showed the replacement online record.

Commands not run: Physical relay/pump activation, watering command, production
awareness restart, main-agent restart, disconnect/reconnect fault injection,
full repository suite, or new local-model acceptance.

Known limitations: Fuse sensing still reports unavailable. Server-side changes
are present in the worktree but do not take effect in running awareness/main
processes until those services restart. Physical water delivery remains
unverified.

Security implications: Existing `qp_secrets.py` and `qp_ledger.json` were not
read out, replaced, or modified. No command topic was published and no relay was
energized.

Deployment implications: The Pico firmware portion is complete. Prior device
files remain on the Pico as `main.py.pre-20261114-125056` and
`qp_net.py.pre-20261114-125056`; local copies are under
`C:\Users\aljac\AppData\Local\Temp\Talos-Pico-Backup-20261114-125056`.
Restart awareness and then the main agent to activate the server-side portion.

Unresolved questions: None within firmware deployment. A supervised bounded
watering cycle and disconnect/reconnect test remain acceptance work, not
performed automatically because they affect physical equipment.

Current repository state: The approved bounded repair remains in the dirty
worktree. This follow-up changed only status/session documentation; installing
`mpremote` changed the existing `.venv-main` environment, which is not a tracked
source change.

Next permitted task: Owner-directed service restart and supervised physical
acceptance, or a separately authorized bounded task.

Required reading for next session: The preceding pump liveness repair entry,
this deployment entry, ADR-056/057, Phase 7 actions, and current implementation
status.

Explicit stop point: Pico deployment and non-actuating MQTT verification are
complete. Do not energize a relay, water plants, or start another phase without
owner direction.

## 2026-11-14 — Wall-powered pump command diagnosis

Session goal: Determine why pump commands do not go through after installing the
controller with its pumps and wall power.

Current phase: Read-only Phase 7 deployment diagnosis; no implementation change.

Bounded task completed: Correlated live MQTT, awareness state/health, action
audit, voice pipeline telemetry, and the controller schematic. The final
USB-powered controller session emitted its last-will at 12:58:09. No new boot,
state, online health, or heartbeat arrived after wall installation. Requests at
13:01:19 and 13:01:46 reached `run_pump` and were rejected before dispatch with
`controller source 'quad_pump_canonical' is offline`. Awareness MQTT ingestion,
database, freshness worker, outbox, and broker connection were healthy.

Files added: None.

Files modified: `IMPLEMENTATION_STATUS.md` and this log only.

Migrations added: None.

Decisions made: None.

Assumptions confirmed or changed: COM3 disappearance is expected after moving
the controller off the PC and is not evidence of failure. The apparent watchdog
reboots between 12:48 and 12:58 coincide with the serial deployment session.
The meaningful installed-state evidence is the absence of any new MQTT boot
after the final unplug. PCB connectivity confirms J1 feeds the AP63205 buck
input/enable, whose output feeds Pico VSYS pin 39; J2-J5 are pump outputs.

Tests run: Read-only retained-health and live-heartbeat subscriptions; awareness
`/state/quad_pump`, `/health/components`, `/events`, and `/actions` queries;
pipeline telemetry inspection; PCB net inspection.

Tests passed: Server-side components reported healthy. Both recent requests have
durable rejected records and were never dispatched. The last controller record
is an explicit last-will rather than a stale online inference.

Tests failed: No wall-powered controller boot or heartbeat was observed during
the initial window. After
the owner unplugged and replugged the green-LED power brick, a fresh retained
health read still returned the old offline last-will, the awareness event query
contained no new controller events, and a 45-second live wildcard subscription
received no boot, state, health, or heartbeat traffic. This was transient: a
later observation found a fresh power-on boot at about 13:23, online health at
4.1 seconds uptime, and continuing heartbeats.

Commands not run: MQTT command publication, relay/pump activation, firmware
change, service restart, broker mutation, or physical power measurement.

Known limitations: Remote evidence cannot distinguish no Pico power from a Pico
that is powered but unable to associate with Wi-Fi. A physical power-path check
or isolated USB-wall-power test is required to split those cases.

Owner clarification: The wall adapter is connected directly to the Pico USB
port, not J1. This rules out the board's J1/buck/VSYS path as the active supply
path, but remote evidence still cannot distinguish unreliable USB power or a
boot fault from failed Wi-Fi association. Serial boot inspection is the next
non-actuating diagnostic; firmware reflash is not presently indicated.

Recovery evidence: The Pico answered at its previously recorded DHCP address
`192.168.1.166` with 30/30 ICMP replies, then published a new boot's state and
retained `online=true` health. Health reported RSSI -40, Wi-Fi and MQTT
connected, one successful connection, zero consecutive failures/radio resets,
and no dropped messages. Six heartbeats arrived at 30-second intervals through
180 seconds uptime. Awareness classified health and all four false relay states
as current. No firmware change or physical command was used.

Subsequent failure evidence: Heartbeats continued only through 270 seconds
uptime. None of the heartbeat, health report, or state snapshot due at 300
seconds arrived. Mosquitto emitted the unique last-will at 13:28:57, 90 seconds
after the final heartbeat, and `192.168.1.166` then had 100% packet loss. A
13:31 `run_pump` request was correctly rejected before dispatch. A host harness
advanced the same main loop through 301 seconds and successfully encoded and
published the three due messages, so the pure scheduling path did not reproduce
the fault. Passive serial capture across the boundary is required to distinguish
a Pico-only exception/MemoryError, watchdog stall, or USB-power instability.

Controlled power-source comparison: With the owner moving the same Pico USB
connection to this PC, COM3 was opened passively at 115200 baud with DTR/RTS
disabled; no input, REPL control, reset, flash, or command was sent. The board
connected at RSSI -41/-38 and published uninterrupted 30-second heartbeats
through 450 seconds uptime. At 300 seconds it successfully published the
previously missing health, state, and heartbeat batch; retained health remained
online with zero failures, radio resets, or dropped messages. The serial stream
contained no traceback or reboot output, awareness remained current, and all
relays remained false. This controlled run rules out the firmware's five-minute
schedule and Wi-Fi/MQTT route. The wall USB source is the remaining changed
variable and its near-exact five-minute loss is consistent with low-current
auto-shutoff or unstable USB output despite a lit brick indicator. No reflash is
indicated; replace/configure the USB source for continuous output and repeat a
non-actuating soak before physical acceptance.

12 V/J1 confirmation: With all pumps detached, the owner powered the controller
through its 12 V input. A read-only MQTT soak observed a fresh boot, online
health in about four seconds, RSSI improving from -44 to -36, zero failures,
radio resets, or dropped messages, and every 30-second heartbeat through 480
seconds uptime. The health/state/heartbeat batch at 300 seconds completed
normally, 10/10 initial ICMP checks succeeded, awareness remained current, and
all four relays stayed false. No serial access, firmware change, or action
publication occurred. Together with the PC USB control, this confirms the
previous USB wall source—not firmware, Wi-Fi, MQTT, or the board regulator—as
the failed boundary. Pump-load and relay behavior remain untested.

Security implications: None; all inspection was read-only and no physical action
was dispatched.

Deployment implications: Verify that the supply is connected to J1 and that the
Pico receives VSYS power. If power is present, diagnose Wi-Fi association at the
installed location. Do not bypass the offline interlock.

Unresolved questions: Whether J1/Pico VSYS has power at the installed location;
if it does, whether the installed location can join the configured Wi-Fi.

Current repository state: Existing bounded repair changes remain; this diagnosis
changed documentation only.

Next permitted task: Owner-assisted power/Wi-Fi isolation at the installed
controller, followed by non-actuating MQTT verification.

Required reading for next session: This entry, the preceding deployment entry,
ADR-056/057, and the controller PCB power nets.

Explicit stop point: Software-side diagnosis is complete. Do not publish a pump
command until the controller is live and the owner authorizes physical testing.

## 2026-11-18 — Per-turn model awareness investigation

Session goal: Determine default model context and whether light state can be read.
Current phase: Bounded source investigation; no phase implementation.
Bounded task completed: Traced prompt assembly, snapshot selection/fallback, awareness read tools, and smart-switch provider/service.
Files added: PER_TURN_AWARENESS_2026-11-18.md in this directory.
Files modified: IMPLEMENTATION_STATUS.md; SESSION_LOG.md.
Migrations added: None.
Decisions made: None; no new architecture decision.
Assumptions confirmed or changed: Automatic household context is bounded database context, not a fresh poll of every device; configured light IDs do not imply current power knowledge.
Tests run: None (documentation/source investigation only).
Tests passed: None run.
Tests failed: None run.
Commands not run: Runtime suites, live model requests, device queries/actions, deployment checks.
Known limitations: Running process version and external light-state producers were not verified. Root git status required --ignore-submodules because the pump submodule metadata was inaccessible.
Security implications: No device actions or secret output.
Deployment implications: None.
Unresolved questions: No owner decision needed for this investigation; live deployment coverage remains unverified.
Current repository state: Pre-existing runtime/config/test/documentation modifications preserved; this task adds documentation only.
Next permitted task: Owner-assigned bounded follow-up; no automatic implementation.
Required reading for next session: Investigation report, implementation status, architectural invariants; tool guide if tools change.
Explicit stop point: Investigation complete; no light-state/toggle implementation or later-phase work.

## 2026-11-18 — Observed household snapshot effectiveness

Session goal: Verify whether compact household context ever reached the model and what it supplied.
Current phase: Bounded investigation, documentation only.
Bounded task completed: Compared five recent saved input files, live awareness read endpoints, Docker status, selection logic and prior repair records.
Files added: None.
Files modified: PER_TURN_AWARENESS_2026-11-18.md, IMPLEMENTATION_STATUS.md, OPEN_QUESTIONS.md, SESSION_LOG.md (this directory).
Migrations added: None.
Decisions made: None; diagnosis/recommendations only.
Assumptions confirmed or changed: Actual injection is proven, but useful device coverage is poor; current missing context coincides with database outage. Automatic snapshot failure can omit context without a model-visible degradation notice.
Tests run: Four context-selection cases in awareness venv; eight client/provider cases in runtime venv with loopback allowed.
Tests passed: 12. Documentation diff whitespace check also passed.
Tests failed: Initial module-style invocation produced two import errors; corrected discovery runs passed. Runtime context discovery skipped for missing dependencies; awareness rerun passed. Sandboxed client/provider run stalled and was interrupted before successful socket-enabled rerun.
Commands not run: Database integration suites, live model inference, physical actions, service restart/deployment.
Known limitations: Five-file sample includes inference rounds, not distinct turns; historical announcement text shares are approximate character ratios. No database access meant absent selected properties could not be compared to all stored properties. Docker outage root cause remains unknown.
Security implications: Read-only service/log inspection; no secret output or actuation.
Deployment implications: Awareness reads currently report database unreachable; Docker's configured engine named pipe is absent. No service state changed.
Unresolved questions: Recorded in OPEN_QUESTIONS.md; database availability and guaranteed state coverage.
Current repository state: Existing unrelated modifications preserved; investigation changed documentation only.
Next permitted task: Separately assigned bounded diagnosis/repair, no automatic later-phase work.
Required reading for next session: Investigation report, implementation status, architectural invariants; tool guide if tools change.
Explicit stop point: Investigation complete; no restoration, snapshot-selection repair, or light-tool implementation begun.

## 2026-11-18 — Awareness capability and boundary overview

Session goal: Explain the subsystem's components, capabilities and limits.
Current phase: Bounded documentation consultation.
Bounded task completed: Mapped registry/ingestion, state/health/history, rules/alerts/delivery, reminders, context/tools, human signals, memory, actions, briefings and operations; distinguished external systems.
Files added: CAPABILITY_MAP_2026-11-18.md.
Files modified: IMPLEMENTATION_STATUS.md; SESSION_LOG.md.
Migrations added: None.
Decisions made: None.
Assumptions confirmed or changed: Scope extends well beyond prompt context; registered action safeguards and reminder/notification workers depend on awareness, while Kasa control and SQLite conversation history are separate.
Tests run: None; documentation/source/config inspection only.
Tests passed: None run.
Tests failed: None run.
Commands not run: Live service checks, model/device requests, suites, restarts and deployment.
Known limitations: Implemented features are not all production-accepted; database outage from preceding checks was not rechecked. Some README descriptions are historical; current code/config and observed evidence take precedence.
Security implications: No secrets or physical actions.
Deployment implications: None.
Unresolved questions: Existing database/coverage questions remain; no new owner decision required for overview.
Current repository state: Pre-existing modifications preserved; this task changes documentation only.
Next permitted task: Separately assigned bounded work.
Required reading for next session: Capability map, implementation status and per-turn investigation.
Explicit stop point: Overview complete; no archival, removal, replacement or runtime implementation.

## 2026-11-18 - Decouple and archive awareness

Session goal: Retire the broad awareness subsystem for later scoped replacement.
Current phase: Owner-authorized bounded archival, not a new implementation phase.
Bounded task completed: Removed launcher/API/worker startup, awareness tool registration, signals, snapshot retrieval, fact mirroring, phone retrieval and dashboard polling; archived sources/deployment/tests and retired dependent pump/fan tools.
Files added: archive/awareness/ (131 original versioned files, README, hash manifest, historical settings and mixed-module references); RETIREMENT_2026-11-18.md; tests/test_awareness_retirement.py. Pre-existing untracked CAPABILITY_MAP_2026-11-18.md remains.
Files modified: Active launcher/config/GUI/maintenance, router/jobs, agent runtime, text/phone server, voice signal/telemetry code, MCP providers, clock/weather service, debug dashboard, scheduler comments, settings.env, .env.example, Start-Butler.ps1, README, AGENTS.md, active text/voice tests, docs/awareness-memory README/status/decisions/session log. Original awareness-only files moved to archive. Local ignored launcher.config.json had obsolete awareness flags removed.
Migrations added: None; old migrations archived without execution.
Decisions made: ADR-058, retire awareness while retaining conversational SQLite ownership and independent tools; no unsafe physical-action bypass.
Assumptions confirmed or changed: Old persisted launcher flags cannot reactivate the retired services. The current tool catalog contains no awareness/reminder/pump/fan tools; independent light/clock/weather tools remain. Existing tool-history and action truthfulness guards remain defensive runtime behavior.
Tests run: Exact commands/results in RETIREMENT_2026-11-18.md: 14 targeted discovery groups and a five-pattern combined loader run, compileall, JavaScript syntax, diff whitespace, source/import/archive-integrity inspection.
Tests passed: 225 final passing cases; Python compilation, JavaScript syntax, whitespace and 131-file archive hash checks passed.
Tests failed: One unchanged personality-text assertion expects wording absent from committed persona assets. Intermediate socket restrictions, a retired-signal mock and a UTF-8 editing error were corrected/retested as detailed in the report; no tests weakened.
Commands not run: Full suite, archived subsystem suites, live model/audio/GUI acceptance, physical device actions, service restarts, database migration/export/deletion.
Known limitations: Already-running processes retain old code until restarted; an old standalone awareness process is no longer supervised. Historical documentation links describe original paths. Personality test mismatch remains unrelated and unmodified. Smart-plug mocked async tests emitted warnings. Git submodule inspection remains sandbox-inaccessible.
Security implications: Removed runtime callers and retired physical tools with their safety authority. No raw MQTT fallback, credential exposure, data deletion or firmware change.
Deployment implications: Restart Butler and MCP children to load retirement; normal launcher startup has no awareness Docker/Postgres/API dependency. Existing DB/volumes/backups/venvs and .env credentials were preserved. Old standalone awareness processes require separate shutdown if still running.
Unresolved questions: Existing snapshot/database questions are historical for the archived system. Replacement scope/design awaits a new assignment; unrelated personality assertion remains recorded.
Current repository state: Changes are uncommitted on the owner's branch. Pre-existing documentation work retained. No submodule, data or environment modification.
Next permitted task: Separately assigned bounded replacement work; no automatic scaffolding or next phase.
Required reading for next session: Retirement report, archive README, ADR-058 and root AGENTS.md; tool guide for new/modified capabilities.
Explicit stop point: Awareness archived and decoupled; no replacement implementation started.


## 2026-11-18 - Devices scope design and awareness retrospective

Session goal: Propose a streamlined Devices replacement and record why awareness was retired.
Current phase: Bounded design/discovery consultation; no runtime implementation.
Bounded task completed: Inspected existing Kasa configuration/service, display integration, main lifecycle, tool guide and archived-awareness evidence; documented scope, contracts, adapter/lifecycle ownership, state versus command semantics, summary policy and acceptance increments.
Files added: docs/AWARENESS_RETROSPECTIVE.md; docs/DEVICES_SYSTEM_DESIGN.md.
Files modified: docs/awareness-memory/IMPLEMENTATION_STATUS.md, DECISIONS.md, OPEN_QUESTIONS.md, SESSION_LOG.md.
Migrations added: None.
Decisions made: ADR-059 records the owner's Devices-first scope and distinguishes recommendations from approved implementation choices.
Assumptions confirmed or changed: Coffee pot is a smart plug, not an observed brewing machine; six light configurations exist; kitchen screen reporting contract remains unverified and is distinct from the InfoPanel TV. Proposed per-turn summaries use background observations rather than per-turn network polling.
Tests run: Documentation link/required-section checks and diff whitespace only (results reported in this session); no runtime tests.
Tests passed: Documentation links/required sections and diff whitespace checks passed.
Tests failed: None in this documentation task.
Commands not run: Runtime/integration suites, real-model requests, live device polling/actions, service restart/deployment, database migrations or dependency installation.
Known limitations: Design is proposed; configured devices were not contacted. Historical awareness findings are a bounded sample, not exhaustive operational history. Kitchen screen API and refresh/retention budgets require discovery.
Security implications: No credentials copied into new documents. Proposed summary/read interfaces must honor existing caller access and provider disclosure boundaries; actuation safeguards remain mandatory.
Deployment implications: None; existing retirement changes and process-restart requirement remain as previously documented.
Unresolved questions: Kitchen screen integration, refresh/expiry policies, minimal schema/retention, MCP ownership bridge and measured prompt budget recorded in OPEN_QUESTIONS.md.
Current repository state: Prior retirement modifications and untracked historical docs preserved; this task changes/adds documentation only.
Next permitted task: Owner-assigned bounded Devices increment after design review; no automatic implementation.
Required reading for next session: DEVICES_SYSTEM_DESIGN.md, AWARENESS_RETROSPECTIVE.md, current status, architectural invariants and tool guide if tools change.
Explicit stop point: Devices design and awareness retrospective complete. No runtime scaffolding, action restoration, or other replacement system begun.


## 2026-11-18 - Unified application database

Session goal: Unify the three active SQLite stores for system-wide use with automatic initialization.
Current phase: Owner-authorized bounded storage implementation; no replacement product module.
Bounded task completed: Added shared path/connection/read-only/migration helpers and immutable schema ownership; converted conversation/jobs/phone stores, main startup, dashboard reads and conversation clearing. Created a clean unified local DB with no import.
Files added: butler/storage.py, butler/storage_schema.py, tests/test_unified_storage.py, docs/DATABASE.md. Ignored runtime file db/butler.sqlite3 initialized.
Files modified: butler/main.py, memory/store.py, jobs.py, phone/store.py and provider.py, launcher maintenance/GUI, debug dashboard server/insights, settings.env, AGENTS.md, README.md; affected memory/dashboard/phone/launcher test fixtures; Devices design storage note; awareness-memory status/decisions/questions/session log. Prior retirement/design changes preserved.
Migrations added: Initial atomic version 1, initial_conversation_jobs_phone (eight implemented-domain tables plus storage ledger); no Devices/World Context/future-memory schemas.
Decisions made: ADR-060; owner waived old-data import; retain domain ownership while sharing the file and migration policy.
Assumptions confirmed or changed: SQLite has no server to launch. Butler initializes/migrates before workers; old per-domain environment settings no longer select independent files. Both memory-clear operations preserve jobs/calls and migration history.
Tests run: Exact 14 discovery patterns and final counts in docs/DATABASE.md, using .venv-runtime; 12 new storage cases include real file concurrency, lock timeout/recovery, migration rollback/rejection, read-only isolation, startup-failure ordering and clearing. Existing effects mocked/local; no live inference/actuation.
Tests passed: 170 final cases, zero failures/skips; Python compilation, document-link/whitespace checks and clean runtime integrity/bootstrap checks passed. Old database size/mtime metadata unchanged.
Tests failed: Initial new suite had a WAL first-open lock race and two Windows fixture-cleanup errors from unclosed SQLite connections. Bounded journal retry and explicit connection closure fixed them; final suite passed. A later phone rerun caught an unnecessary constructor-field removal; compatibility was restored and all 19 phone tests passed again. No tests weakened.
Commands not run: Full suite, unrelated known personality test, live LLM/voice/GUI/phone/device acceptance, old-data import, process restart/deployment, OS startup registration or database deletion.
Known limitations: SQLite serializes writers; future heavy telemetry needs measurement. Ownership is a code convention, not SQLite roles. Existing running processes need restart. Existing audioop deprecation warning remains. Missing-table/history checks do not constitute general corruption recovery or automatic backups.
Security implications: Centralized path/policies; non-creating read-only dashboard connections; memory clear no longer deletes a shared file; provider/network effects mocked. No new tool/external service, credential movement, or physical action.
Deployment implications: Restart Butler and MCP/dashboard processes to adopt new path/schema. New empty db/butler.sqlite3 is ready. Old three SQLite files, archived Postgres data and firmware unchanged. No Docker needed for active storage.
Unresolved questions: Product-module schemas and future backup/retention policy remain separately scoped; no dependency blocks this cutover.
Current repository state: Uncommitted implementation plus prior retirement/design work preserved. No submodule edits or destructive filesystem operations.
Next permitted task: Separately assigned bounded task; do not begin Devices automatically.
Required reading for next session: docs/DATABASE.md, ADR-060, root AGENTS.md; Devices design if implementing that module; tool guide for agent-facing changes.
Explicit stop point: Unified storage complete and verified. No future product systems, tables, import pipeline or boot-service installation started.


## 2026-11-18 - Launcher awareness-artifact follow-up

Session goal: Inspect and remove remaining retired-awareness artifacts in the launcher.
Current phase: Bounded retirement follow-up; no replacement implementation.
Bounded task completed: Removed the Awareness/MQTT panel and obsolete broker variables/load/save wiring, awareness situation checkbox/prompt flag, fallback API/MQTT defaults and stale package description. Removed four obsolete settings previously reintroduced by launcher saves. Clarified active conversation memory/history/saved-fact controls and clearing labels.
Files added: None.
Files modified: butler/launcher/gui.py, config.py, __init__.py; settings.env; tests/test_launcher_llm_debug.py; docs/awareness-memory/IMPLEMENTATION_STATUS.md and SESSION_LOG.md.
Migrations added: None.
Decisions made: No new architectural decision. Applied ADR-058 retirement while retaining ADR-060 conversation-owned facts/history.
Assumptions confirmed or changed: The prior cleanup missed launcher controls that still rewrote retired settings. Remembered facts are active conversation SQLite functionality, not the retired PostgreSQL awareness memory.
Tests run: .venv-runtime/Scripts/python.exe -m unittest discover -s tests -p test_launcher*.py -q; py_compile on launcher GUI/config and changed test; targeted artifact searches and Git diff whitespace check.
Tests passed: 29 launcher cases; compilation, no-retired-key search and whitespace checks passed. New headless widget/persistence regression constructs the full layout, loads and saves settings, checks obsolete controls absent and verifies the active memory setting still toggles.
Tests failed: Initial new test referenced the wrong fallback-default constant name; corrected it and all 29 passed. No production failure or test weakening.
Commands not run: Live Tk GUI/screenshot acceptance, full suite, model/device calls, process restart/deployment.
Known limitations: Already-open launchers retain old code and must be closed/reopened; an old GUI can still rewrite obsolete keys until restarted. Headless widget tests do not establish visual layout acceptance.
Security implications: No secrets, data deletion or device operations; memory behavior unchanged.
Deployment implications: Reopen launcher to apply control removal; no database migration.
Unresolved questions: None for this cleanup.
Current repository state: Prior retirement/storage/design changes preserved; no unrelated runtime changes.
Next permitted task: Separately assigned bounded work; do not begin Devices automatically.
Required reading for next session: Current status, ADR-058/060, docs/DATABASE.md.
Explicit stop point: Launcher artifacts removed and active conversation-memory labeling clarified.


## 2026-11-18 - Device Information System first release

Session goal: Begin DIS implementation, asking design questions as needed.
Current phase: Owner-authorized bounded first release: Kasa information slice and model read integration.
Bounded task completed: Registry reuses existing six-light/coffee configuration; migration 2 persists latest observations and contact health; a bounded Butler-owned background worker supplies committed cache, freshness/unknown/current separation, generation-based read refresh, read-only main HTTP/MCP interface, owner-only per-turn context and nonblocking observation triggers after actual set_smart_plug calls. No physical-control implementation in DIS.
Files added: butler/dis/{__init__,models,store,adapters,service,client}.py; butler/mcp_servers/providers/device_information.py; tests/test_dis.py; tests/test_dis_model_acceptance.py; docs/DIS.md.
Files modified: butler/storage_schema.py (append migration 2/ownership only), main.py, text/server.py, agent/runtime.py, MCP provider init/aggregate, launcher/config.py, settings.env, tests/test_unified_storage.py (version-aware assertions), README.md, AGENTS.md, Devices design/database docs, awareness-memory status/decisions/questions/session log. Prior changes preserved.
Migrations added: Version 2, dis_latest_device_information: dis_devices, dis_observations, dis_health. Original migration 1 unchanged and exercised through upgrade/read-only live checks.
Decisions made: ADR-061. Owner confirmed information-only boundary, automatic summaries, five-second polling plus command-triggered reads; clarified no reply-path waiting; explicitly skipped kitchen screen. Pump adapter remains next scoped work, not automatically implemented.
Assumptions confirmed or changed: Current values must be null when stale/unverified, with last-observed values separately retained. A local-model test demonstrated that a stale boolean plus a label was insufficient. Request generations replaced coarse clock comparisons. No control return string or requested state is treated as an observation.
Tests run: Fifteen deterministic discovery patterns in docs/DIS.md; opt-in local-model fixtures; live read-only Kasa checks and automatic startup/sweep/shutdown; cache formatting measurement; compilation/link/whitespace checks.
Tests passed: 206 deterministic cases. Final four-scenario local Ollama mb-core-v1:latest acceptance passed three consecutive runs (12 question scenarios), with simulated devices/read tools and no mutations. Live final sweep reached all six lights, reporting on; coffee plug remained unreachable/unknown. Cache-only seven-device summary measured about 0.039 ms median / 0.043 ms p95 over 1000 calls. Compilation, links and whitespace passed.
Tests failed: Initial deterministic refresh tests exposed a timestamp-resolution race; generation matching fixed it. Initial real-model stale-state case incorrectly answered off; explicit null-current/separate-history projection and uncertainty guidance fixed it without weakening assertions. Earlier partial live reads exposed transient authentication failures; bounded read-only retry improved coverage. Coffee timeout remains truthful unavailability, not a claimed success. Existing mocked-async and audioop warnings were not suppressed.
Commands not run: Full suite, real control actions, microphone/GUI acceptance, continuous soak, deployment restart, pump integration/commands, kitchen-screen adapter, other replacement systems. Default real-model discovery is opt-in/skipped unless explicitly enabled.
Known limitations: First release supports Kasa power observations only; no brewing/illumination/mechanical proof. Five seconds is a target polling interval plus timeout/concurrency/backoff, not a hard detection SLA. Larger registries use explicit summary/page omission. Cached qualifiers change immediately after controls, but new observations arrive asynchronously. Local-model acceptance is a bounded behavior sample, not a reliability guarantee.
Security implications: No physical actions exposed by DIS. Remote reads require configured owner API auth; restricted model turns have no automatic device context. MCP child reads main's cache and does not start another owner. Credentials/endpoints excluded from model data and raw library errors redacted. Actual calls/results preserved; no fabricated tool exchanges or writes of command intent.
Deployment implications: Restart Butler/MCP children to apply lifecycle/tool/catalog/settings changes; shared DB migrated to version 2 by live validation. Temporary read-only DIS worker was stopped. Existing controls remain independent. Coffee availability needs owner/network attention if current information is expected.
Unresolved questions: Coffee plug availability, future pump read adapter and later complex-device protocols; kitchen screen intentionally deferred. No unresolved design choice blocks this first release.
Current repository state: Uncommitted first-release implementation; no firmware/submodule changes, power commands or data import. Existing shared DB contains actual bounded Kasa observations and preserved other domains.
Next permitted task: Separately assigned bounded adapter/deployment acceptance; do not automatically begin pump, notifications, memory or other systems.
Required reading for next session: docs/DIS.md, docs/DATABASE.md, ADR-061, root AGENTS.md and tool guide for tool changes.
Explicit stop point: First Kasa DIS release complete; no broader awareness functionality or control engine added.


## 2026-11-18 - DIS passive waterer and owner-declared inventory

Session goal: Audit deterministic replies and extend DIS to other devices.
Current phase: Owner-authorized bounded waterer information adapter and inventory records.
Bounded task completed: Audited conversational paths; no DIS direct conversational reply added. Added passive canonical MQTT waterer reader and six explicit not_integrated inventory entries. Preserved nonblocking cache-only prompt path and existing controls. Registry now 14 devices; Minecraft software and computer separate.
Files added: butler/dis/pump.py; tests/test_dis_pump.py.
Files modified: DIS models/store/service; storage_schema.py; device_information provider descriptions; settings.env; docs/DIS.md, DATABASE.md and awareness-memory status/decisions/questions/session log. Earlier uncommitted first-release changes preserved.
Migrations added: Version 3 dis_passive_source_provenance extends existing observation/health tables; migrations 1 and 2 unchanged.
Decisions made: ADR-062; inventory-only entries have no fake adapters or observed capabilities. Waterer remains passive. Per-source liveness and per-property freshness are distinct. Retained replay cannot prove current state; sequence checks are per stream with boot invalidation. Fixed strings are data/context, never new direct chat replies.
Assumptions confirmed or changed: Firmware publishes 30-second heartbeats and 300-second periodic state, so use 120-second contact deadline and 360-second property TTL. Five-second Kasa cadence does not apply to source MQTT publication. Firmware RSSI may be null; omit unavailable values. New process cannot requalify DB relay evidence from heartbeat alone.
Tests run: .venv-main/Scripts/python.exe -m unittest discover -s tests -p test_dis.py; same for test_dis_pump.py and test_unified_storage.py; opt-in BUTLER_DIS_LIVE_MODEL_TEST=1 test_dis_model_acceptance.py; compileall for DIS/provider/new tests; git diff --check; bounded actual subscribe-only source check; full-registry summary-size check.
Tests passed: 19 DIS regressions, 7 passive/inventory cases, 12 unified-storage cases (38 deterministic total). Local model acceptance test passed all four question scenarios in one run. Real 35-second MQTT subscription received current heartbeat, quad_pump-2.0.0 retained firmware/network metadata, no live relay snapshot. All 14 registry entries fit in the 3600-character summary (2130 characters with initial unknown readings). Compilation and whitespace checks passed.
Tests failed: Initial command used system Python lacking dotenv; reran using repository .venv-main. Restricted-sandbox DIS test execution stalled on local socket fixtures and was interrupted; authorized unsandboxed execution passed, including final rerun. No final functional assertion failures. Targeted rg wildcard paths were corrected/avoided; no code affected. Existing audioop deprecation warning remains.
Commands not run: Full repository suite, physical commands, live relay transition test, full five-minute source sweep, firmware changes, deployment restart, adapters for inventory-only devices.
Known limitations: Live check proves transport/heartbeat reception only, not current relay-state coverage. Retained data remains historical and source startup may wait for next periodic full state. Bounded retired-boot history is not durable event ingestion. No water flow, fuse sensing, printing, TV playback, Minecraft load or vehicle state inferred. Older deterministic action acknowledgements/failure guards remain in runtime, unchanged by DIS.
Security implications: Exact three telemetry subscriptions; no publish, command subscriptions, will registration or actuation. Typed bounded source data, provenance and explicit uncertainty survive persistence and read projection. Endpoints/credentials excluded from model output. Existing owner-auth HTTP/tool restrictions unchanged.
Deployment implications: Restart Butler and MCP children; normal shared-DB initialization applies migration 3. Live check used a temporary subscriber and stopped it. No production process restart, physical state change or sub-repo edit.
Unresolved questions: Later endpoint/auth contracts for OctoPrint, kitchen kiosk, Toshiba TV, Minecraft software/host; Jeep conceptual. Future faster waterer source detection is a separately scoped firmware decision.
Current repository state: Uncommitted extension atop first-release working tree; no git commit/reset or firmware/submodule modification.
Next permitted task: Owner supplies/authorizes a bounded real status adapter or deployment acceptance; do not begin further integrations automatically.
Required reading for next session: docs/DIS.md, DATABASE.md, ADR-062, OPEN_QUESTIONS.md and root AGENTS/tool guide.
Explicit stop point: Passive waterer and six informational inventory entries complete; no broader awareness or control systems added.


## 2026-11-19 - Weather-only World Context System v1

Session goal: Implement WCS in the DIS shape, with local weather active and room for later bounded source adapters; ask design questions as needed.
Current phase: Owner-authorized weather WCS v1; DIS v1 accepted as done by owner.
Bounded task completed: Added typed source observations and weather adapter, shared-DB latest slots/source schedules, main-owned polling/cache lifecycle, owner-only per-turn summaries in both agent paths, HTTP read bridge and typed MCP get_world_context tool. Home get_current_weather now reads WCS cache; explicit other locations preserve existing live behavior. No universal expiry, physical actions, notification logic or placeholder future sources.
Files added: butler/wcs/{__init__,models,store,weather,service,client}.py; butler/mcp_servers/providers/world_context.py; tests/test_wcs.py; tests/test_wcs_model_acceptance.py; docs/WCS.md.
Files modified: main.py, text/server.py, agent/runtime.py, storage_schema.py, MCP aggregate/provider init/home_automation provider, launcher/config.py, settings.env, AGENTS.md, README.md, DATABASE.md, awareness-memory status/decisions/questions/session log.
Migrations added: Version 4 wcs_latest_observations adds wcs_sources and wcs_observations with explicit wcs ownership. Migrations 1-3 unchanged; upgrade from actual temporary version-3 DIS schema preserves device rows.
Decisions made: ADR-063. Owner selected 900-second weather polling. Poll reservation persists before API access. Fully failed source polls back off; partial daily failures preserve normal current-weather cadence. Original observation/receipt time and forecast day intervals are distinct. Outside-interval forecast values are historical, not today's values. No API call from ordinary model-turn/context/cache reads.
Assumptions confirmed or changed: Existing configured OpenWeather endpoints and credentials work for both current weather and daily forecast. Current API min/max are spatial ranges, not daily high/low. Daily dt is target day, not forecast issue time. No fabricated confidence or issue timestamp. Future categories need real typed read/push contracts, not placeholder adapters. Existing host clock/timezone-injection limitations remain out of scope.
Tests run: Repository .venv-main unittest discovery for test_wcs.py, test_unified_storage.py, test_home_automation_weather.py, test_mcp_disable_selection.py, test_dis.py, test_dis_pump.py, test_run_command_stream.py, test_tool_access.py, test_awareness_retirement.py, test_agent_runtime_recovery.py. Opt-in BUTLER_WCS_LIVE_MODEL_TEST=1 test_wcs_model_acceptance.py. Compileall for WCS and touched integration/test modules; git diff --check. Single live weather poll into temporary SQLite; 1000 cache-only summary formatting calls.
Tests passed: 123 deterministic cases: 24 WCS, 12 shared-storage, 3 existing weather, 15 provider selection, 19 DIS, 7 waterer/inventory, 17 streaming turn, 9 caller-access, 5 retirement and 12 agent recovery. Final real local-model acceptance passed three consecutive four-question runs (12 scenarios) covering outdoor temperature, indoor humidity uncertainty, expired forecast rejection and WCS unavailability. Live poll reached both current/daily endpoints and validated observations; fetch about 0.57 s and pre-final-guidance summary 1665 chars. Formatting averaged about 0.038 ms over 1000 calls. Compilation/whitespace passed.
Tests failed: An initial compile found an SQL string quoting typo and was corrected before tests. Restricted-sandbox retirement fixtures stalled and were interrupted; authorized unsandboxed execution passed. Initial model run passed but repetition exposed unavailable-context fixture bypass (tool read a retained service directly despite disabled service) and expired forecast misinterpretation. Fixed fixture to use service.read_context, strengthened unavailable guidance and implemented temporal projection rather than weakening assertions. Final local-model runs all passed. Final review also caught the non-streaming WCS insertion in a recovery helper instead of initial prompt assembly; it was moved to the correct path and a direct Responses-path owner/restricted test plus existing recovery regressions passed. Existing audioop warning remains visible.
Commands not run: Full repository suite, actual physical commands, firmware/submodule changes, continuous 15-minute polling soak, deployment restart, full launcher GUI/voice acceptance, camera/indoor/presence/location adapters, user-plan extraction, Memory or Proactivity implementation.
Known limitations: Source polling is designed for one main Butler owner; not an account-wide quota/distributed polling coordinator. Explicit other-location weather lookups can spend calls beyond WCS schedule. Request connect/read timeouts are not a hard total deadline; shutdown reports incomplete if its 45-second wait expires. No immutable observation history/raw payload archive. Saved source data may be old and remains timestamped; forecasts explicitly separate applicability from history. Local-model samples do not guarantee future reply correctness; unnecessary offers to fetch information remain possible without triggering API calls.
Security implications: No new actuation or deterministic chat path. Read endpoints use existing owner/loopback token rules; restricted automatic context is absent. MCP child does not open storage/start polling. Bounded typed measurements and structured results preserve provenance; raw errors, URLs, coordinates and API credentials excluded from model context. WCS changes do not restore archived awareness.
Deployment implications: Restart Butler/MCP children to load lifecycle/catalog/settings. Shared startup migration applies version 4 automatically. Validation used temporary DBs; no deployment process restarted or active source poller left running. Existing outdoor weather location/key/units reused.
Unresolved questions: No blocking v1 question. Real future source contracts, identity/privacy semantics and time-injection hardening recorded in OPEN_QUESTIONS; not automatically implemented.
Current repository state: Uncommitted weather WCS implementation on the existing branch, no commits/resets or sub-repo edits.
Next permitted task: Owner-authorized deployment/soak acceptance or one separately scoped real WCS source adapter. Do not automatically begin the next awareness replacement system.
Required reading for next session: docs/WCS.md, DATABASE.md, ADR-063, root AGENTS.md, tool implementation guide and implementation status.
Explicit stop point: Weather-only WCS v1 implemented and validated; future source integrations and other systems remain unimplemented.


## 2026-11-19 - Direct weather tool route removal

Session goal: Remove redundant weather tool calling now that WCS handles weather.
Current phase: Owner-assigned bounded WCS cleanup.
Bounded task completed: Removed get_current_weather registration and runtime result-shaping exemption; retained WCS summaries/read tool and date/time tool. Launcher description and catalog tests updated. Internal weather formatting helper left unregistered.
Files added: None.
Files modified: home_automation provider, agent/runtime.py, launcher/config.py, tests/test_wcs.py, tests/test_awareness_retirement.py, WCS/status/decisions/questions/session docs. Prior WCS working-tree changes preserved.
Migrations added: None.
Decisions made: ADR-064. Arbitrary other-location live weather lookup is no longer an agent capability; no fallback alias introduced.
Assumptions confirmed or changed: WCS adapter uses constants/normalization helpers, not the removed tool registration. Current date/time remains independent.
Tests run: Repository .venv-main unittest discovery for test_wcs.py, test_awareness_retirement.py, test_mcp_disable_selection.py; BUTLER_WCS_LIVE_MODEL_TEST=1 test_wcs_model_acceptance.py; compilation and whitespace check.
Tests passed: 44 deterministic cases (24+5+15), one four-scenario local-model fixture with simulated weather and only WCS read tools. Catalog absence/failed direct invocation and retained WCS/time routes verified. Compilation/whitespace passed.
Tests failed: None in this cleanup. Existing audioop deprecation warning remains.
Commands not run: Full repository suite, actual weather API, physical commands, deployment restart.
Known limitations: Weather covers only configured local location; no agent lookup of arbitrary other cities. Internal legacy formatter remains unused by registered tools.
Security implications: Removes model-triggered direct weather API route. Existing WCS owner access/cache-only reads unchanged.
Deployment implications: Restart Butler/MCP children to discard old tool catalogs.
Unresolved questions: None blocking.
Current repository state: Uncommitted route cleanup atop WCS implementation; no reset/commit or deployment action.
Next permitted task: Separately assigned bounded work; no new source/system automatically begun.
Required reading for next session: docs/WCS.md and implementation status.
Explicit stop point: Direct weather route retired; WCS remains operational.


## 2026-11-19 - Investigate unsupported 8 a.m. weather answer

Session goal: Determine whether 68 F versus external 38 F was an API discrepancy or system problem.
Current phase: Bounded WCS diagnosis and hourly-forecast interpretation correction.
Bounded task completed: Read-only inspection of WCS records and relevant saved conversation identified daily high 68.22 F reused for both 8 a.m. and 9 a.m.; current source record was 44.24 F. Added explicit no-hourly-data guidance and realistic sequential model regression cases.
Files added: None.
Files modified: butler/wcs/service.py, world_context provider description, tests/test_wcs_model_acceptance.py, WCS docs and status/decisions/questions/session log. Existing working tree preserved.
Migrations added: None.
Decisions made: ADR-065. Specific-hour forecasts are unavailable, not derived from a daily high/low or current reading. No additional source polling.
Assumptions confirmed or changed: Persisted values were correctly separated; the error occurred when the model interpreted a daily high as an hourly prediction. User's external 38 F source was not independently verified at the same time/location, so no general API-accuracy conclusion is claimed.
Tests run: .venv-main unittest discovery test_wcs.py and test_awareness_retirement.py; opt-in test_wcs_model_acceptance.py with seven scenarios; compilation/whitespace checks.
Tests passed: 29 deterministic cases (24 WCS, 5 catalog/retirement). Two final seven-scenario local-model runs passed (14 scenarios), explicitly declining unsupported 8/9 a.m. forecasts while preserving daily high/current readings. Compilation/whitespace passed.
Tests failed: None in final validation. Summary guidance was kept within the existing minimum budget. Existing audioop warning remains.
Commands not run: Full suite, external weather API, independent external hourly verification, production restart, hourly integration or physical commands.
Known limitations: WCS still cannot answer hourly forecasts; model acceptance is a bounded sample, not a universal guarantee. Existing API observation and daily forecast values may themselves vary between providers.
Security implications: Read-only diagnosis, no new API or action route. Replies remain model-generated.
Deployment implications: Restart Butler/MCP children to load prompt/tool-description correction. No running process restarted.
Unresolved questions: Whether to separately implement hourly forecasts later; not needed for truthful v1 behavior.
Current repository state: Uncommitted bounded fix atop existing WCS work, no resets/commits/sub-repo edits.
Next permitted task: Separately authorized source expansion or deployment acceptance.
Required reading for next session: docs/WCS.md and ADR-065.
Explicit stop point: Hourly misinterpretation diagnosed and guarded; no weather data expansion.


## 2026-11-19 - Hourly forecasts in WCS

Session goal: Implement lightweight hourly weather forecasts while keeping replies routed through the LLM.
Current phase: Owner-authorized bounded hourly WCS extension.
Bounded task completed: Existing One Call poll includes hourly data; validates and caches up to 48 target-time records with temperature/conditions/precipitation. Added atomic bounded series persistence, offset-aware cached time-range reads through existing HTTP/MCP route, compact date/offset-grouped summary and actual-schema model acceptance. No new direct weather tool, process, notification behavior or deterministic reply.
Files added: tests/test_wcs_hourly.py.
Files modified: WCS models/weather/store/service/client, world_context provider, text/server.py, storage_schema.py, settings.env, WCS/shared-DB/status/decisions/questions/session docs and existing WCS/model tests. Prior working tree preserved.
Migrations added: Version 5 wcs_hourly_forecasts with WCS ownership and per-category/time primary key. Migrations 1-4 unchanged.
Decisions made: ADR-066. Keep 900-second polling/request count; hourly resolution/target dates are explicit. None hourly batch preserves old data on failure, valid replacement is atomic. Context cap increased from 2200 to 2400 chars for compact temperature/precipitation timeline; full structured detail stays in read tools. Date/offset/metric matching required; no interpolation or reuse of daily extrema.
Assumptions confirmed or changed: Configured One Call API supports hourly on the same request; live check returned all 48 records. Partial next-hours previews proved insufficient for this local model: it reused other dates/hours and invented missing hourly precipitation despite guidance. Compact grouped timeline corrected tested cases. Forecast_at explicitly includes offset, including fixed-offset fallback/repeated DST hour. Hour buckets are selection windows, not constant-weather assertions.
Tests run: Repository unittest discovery test_wcs_hourly.py, test_wcs.py, test_unified_storage.py, test_dis.py and test_awareness_retirement.py; opt-in BUTLER_WCS_LIVE_MODEL_TEST=1 test_wcs_model_acceptance.py using actual provider schema. Single real weather poll into temporary SQLite; compilation/whitespace checks.
Tests passed: 72 deterministic cases: 12 hourly, 24 WCS, 12 shared DB, 19 DIS and 5 retirement/catalog. Final eleven-scenario local-model acceptance passed twice (22 question scenarios), including 38 F/40 F at 8/9 a.m., 55 F at a different date/hour and 73 percent hourly precipitation. Existing current/daily/indoor/expired/unavailable cases retained. Live API returned 48 hourly records with ready source health and no additional endpoint request. Compilation/whitespace passed.
Tests failed: Early local-model runs reused another previewed hour/date, claimed unavailable without lookup, invented indoor humidity after an over-shortened prompt, and invented hourly precipitation omitted from context. Restored indoor boundary and improved compact full-date/metric context rather than weakening assertions. A summary-fit case exposed float-representation bloat and metadata overhead; two-decimal preview rounding and compact source/overview fields fixed it within the explicit budget. Final assertions pass. Existing audioop warning remains visible.
Commands not run: Full repository suite, continuous 15-minute soak, production restart, arbitrary other-location API or physical actions. No source other than weather added.
Known limitations: Forecast horizon/provider availability bounded to cached hours; no interpolation. Smaller budgets/longer text can omit points, requiring read tools. LLM may still misinterpret or offer unnecessary work; model tests are bounded samples, not universal guarantees. Conditions and less-common current/daily metrics are in full structured reads. Connect/read timeout and single-main-owner limitations unchanged.
Security implications: Existing owner/loopback auth, restricted-turn context exclusion and schema validation preserved. New time queries require explicit UTC offset and max 48h range. No model-path API calls, arbitrary endpoint, command execution or canned user reply.
Deployment implications: Restart Butler/MCP children to load migration 5 and extended schema. Existing persisted next-poll reservation remains; first hourly data arrives at next scheduled poll. Temporary live-check service/store stopped. No production process restarted or shared DB manually rewritten.
Unresolved questions: None blocking; future sources/beyond-horizon forecasts remain separate tasks.
Current repository state: Uncommitted hourly extension atop WCS working tree; no commit/reset/sub-repo edit.
Next permitted task: Separately assigned deployment/soak acceptance or real source extension; do not begin automatically.
Required reading for next session: docs/WCS.md, DATABASE.md, ADR-066 and tool guide.
Explicit stop point: Hourly weather implemented and validated; no broader awareness/proactivity work.


## 2026-11-19 - Investigate persistent 68 F hourly answer after history reset

Session goal: Trace actual failed 9 a.m. answer after conversation/memory reset.
Current phase: Bounded rollout diagnosis and collection-upgrade bootstrap fix.
Bounded task completed: Read-only DB inspection and exact sent LLM payload at 01:27:50 proved new code was active but hourly cache was empty. Legacy 01:17 current/daily records retained next poll 01:32. The model ignored missing coverage and reused daily high 68.22 F. Added version-only schedule invalidation while preserving evidence; unchanged-version backoff stays intact. Observed actual scheduled poll populate forecasts without restart/forced refresh.
Files added: None.
Files modified: butler/wcs/weather.py, store.py, tests/test_wcs_hourly.py, WCS/status/decisions/questions/session docs. Prior changes preserved.
Migrations added: None.
Decisions made: ADR-067. Weather collection_version=2 triggers one immediate background poll on upgrade, not on every restart/request. Observation identity changes still clear mismatched data; version-only changes preserve evidence.
Assumptions confirmed or changed: Clearing conversation does not clear WCS by design. Updated code was running, so a blanket stale-process explanation was wrong. Missing hourly rollout data came from reusing the pre-hourly schedule. Live 01:32:13 poll now supplies 52.18 F for November 19 09:00 America/New_York. Geocoding resolves Baltimore, Maryland, not another Baltimore. External approximately 45 F source was not supplied/independently verified; no claim it agrees with provider.
Tests run: .venv-main unittest discovery test_wcs_hourly.py and test_wcs.py; compilation and git diff --check. Read-only running cache query/short monitoring through scheduled poll, targeted request-log/SQLite inspection, one read-only direct-geocoding request.
Tests passed: 38 deterministic cases (14 hourly +24 WCS), including preserving saved facts while immediately collecting upgraded data and keeping same-version failure backoff. Compilation/whitespace passed. Live running cache returned one exact 9 a.m. forecast with source ready and explicit offset/temperature 52.18 F.
Tests failed: No final functional assertion failures. Sandbox CIM inventory was unavailable; existing per-run request logs identified the running process/context without escalation. No raw credentials or unrelated conversations printed. Existing audioop warning remains.
Commands not run: Full suite, new local-model acceptance, actual user-turn replay, forced weather fetch, production restart, broad log dump, physical actions or changes to history/settings.
Known limitations: This fixes bootstrap collection, not model obedience during genuine missing data. User's expected approximately 45 F still differs from the actual provider's 52.18 F; source/time/location comparison remains unverified. New code's upgrade handling loads on next restart; current process already obtained hourly data at its regular poll.
Security implications: Read-only diagnosis and normal module registration fix; no direct deterministic reply, prompt-path API fetch or controls. Geocoding check only; weather forecast came from the running cache/normal poll.
Deployment implications: No restart performed. Current hourly cache is populated. Next restart loads one-time versioned bootstrap behavior; same-version restarts preserve API budget/backoff.
Unresolved questions: Which external source/location/time produced approximately 45 F, if a provider comparison is desired. No blocker to fixing the confirmed bootstrap bug.
Current repository state: Uncommitted fix atop WCS work; no commit/reset or sub-repo edit.
Next permitted task: Separately assigned provider comparison or deployment acceptance; no broader subsystem expansion.
Required reading for next session: docs/WCS.md, ADR-067 and implementation status.
Explicit stop point: Actual failing prompt traced, bootstrap bug fixed/tested and running hourly data verified; no deterministic response path added.


## 2026-11-19 - Bounded LTMS v1

Session goal: Implement owner-approved simple local graph memory.
Current phase: New LTMS bounded v1, not revival of archived Phase 6 dependencies.
Bounded task completed: Shared SQLite memories/edges/jobs, background intake and
local inference, atomic validated operations, embedding/lexical recall and one-hop
context, legacy fact route retirement with immediate conversation history preserved.
Files added: butler/ltms/{__init__,store,service,local_server}.py, docs/LTMS.md,
tests/test_ltms.py, tests/test_ltms_model_acceptance.py.
Files modified: butler/agent/runtime.py, butler/main.py, butler/phone/service.py,
butler/storage_schema.py, docs/DATABASE.md, status/decisions/open questions/session
log; tests/test_awareness_retirement.py, tests/test_phone_service.py, tests/test_wcs.py.
Migrations added: 6 (ltms_graph); prior migration statements unchanged.
Decisions made: ADR-068. No Mem0/import; immediate async learning; dedicated A2000
Ollama, CPU all-minilm; operations validated before commit; reflection deferred.
Assumptions confirmed or changed: Owner clarified no wait for extraction between
turns. Archived awareness retirement deliberately retained the separate fact store.
Tests run/passed: .venv-main/Scripts/python.exe -m unittest discover -s tests -p
PATTERN -q: test_ltms.py 12, test_memory_store.py 11, test_unified_storage.py 12,
test_run_command_stream.py 17, test_tool_ordering.py 5, test_phone_service.py 11,
test_dis.py 19, test_wcs.py 24. Four non-catalog retirement tests also passed.
Total deterministic passing: 115. DIS/WCS final runs permitted local fixture sockets.
Local model: BUTLER_LTMS_LIVE_MODEL_TEST=1 test_ltms_model_acceptance.py passed one
three-step learn/semantic recall/change/forget scenario on temporary storage, using
qwen3:8b and all-minilm with a separately owned A2000 Ollama process. No controls.
Compilation and git diff --check passed.
Tests failed: Initial live run learned/recalled but rejected a malformed change
operation; introduced schema-constrained output (no assertion relaxation), final
run passed. Fixed test cleanup to close SQLite before temporary directory deletion.
Initial phone test expected legacy saved facts; replaced with assertions that no
legacy fact is written and stored conversation summaries remain idempotent. Its
first replacement used replay-only history (which excludes system summaries);
corrected to inspect stored conversation messages. WCS pre-WCS migration fixture
needed to exclude LTMS ownership when simulating migrations 1-3; final run passed.
Commands not run: Full repository suite, continuous soak, GUI/audio acceptance,
full main-model live conversation acceptance, deployment restart. Sandboxed
retirement/DIS/WCS discovery stalled; stopped specific test processes. Final
DIS/WCS socket-enabled runs passed; full retirement catalog test not completed.
Known limitations: Intake inbox crash window roughly 100 ms; sampled changes can
miss transitions; model semantic correctness is not deterministic validation;
no exact count/streak engine; bounded linear search; capacity caps and no automatic
capacity scheduler. Failed jobs stop after three attempts. New-node edges require
later batches. History versioning not promised. Socket timeouts are not hard
wall-clock deadlines. See LTMS.md for explicit settings/limits/degradation.
Security implications: Local inference only; strict mutation schemas/reference
checks; memories are data, not action authorization. Owner-only conversation
injection/learning; no external messaging or arbitrary SQL. Forget deletes node
and incident edges; archived merge inputs remain until explicitly forgotten.
Deployment implications: Downloads qwen3:8b and all-minilm; default runtime owns
port 11435 Ollama pinned by A2000 UUID, separate from main chat Ollama. Models were
exercised, but Butler was not restarted and production DB not manually migrated.
Unresolved questions: Future tuning of consolidation/retrieval; not blockers for v1.
Current repository state: Uncommitted implementation/documentation/tests; no
physical commands, firmware changes or awareness reactivation.
Next permitted task: Owner review/use of LTMS v1 and separately bounded tuning.
Required reading for next session: docs/LTMS.md, docs/DATABASE.md, repository
AGENTS.md, this handoff and current implementation status.
Explicit stop point: LTMS v1. Executor and chained reflection remain future work.


## 2026-11-19 - LTMS 2D diagnostic graph

Session goal: Show stored LTMS nodes and edges for evaluation.
Current phase: Bounded read-only visualization, no LTMS redesign.
Bounded task completed: Dashboard /memory page and /api/ltms-graph snapshot endpoint;
SVG directed labelled graph, pan/zoom/drag, fit, manual refresh, active/archived
filter, loaded-view search and memory/evidence inspector.
Files added: butler/debug_dashboard/memory_graph.py; static/memory.html,
static/memory.css, static/memory.js; tests/test_memory_graph.py.
Files modified: butler/debug_dashboard/server.py, static/index.html, docs/LTMS.md,
IMPLEMENTATION_STATUS.md, DECISIONS.md, OPEN_QUESTIONS.md and this session log.
Migrations added: None. No database or memory content changed by viewer.
Decisions made: ADR-069. Native SVG; reuse dashboard read-only storage exception.
Assumptions confirmed or changed: Real DB currently has 3 active memories and 0
edges. Fixture DB verified actual directed labelled edges and archived nodes.
Tests run: python -m unittest discover -s tests -p test_memory_graph.py -v (5 passed)
and test_debug_dashboard.py -q (17 passed); node --check memory.js; Python
compilation; git diff --check. PYTHONPATH points to existing .venv-main site-packages
and `python` resolves to Inkscape's Python 3.12.12. Repo venv executable fails
because its base Python312 is missing. Installed Python314 requires escalation
and lacks dotenv; no dependencies installed or environment changed.
Tests passed: 22 deterministic checks; browser verified real memory details,
fixture graph edges, archives and search. Adjusted layout centering strength after
browser review of sparse disconnected graph. Final browser view checked real DB.
Tests failed: No failing test assertions. Initial commands could not launch the
obsolete venv Python; reran with available compatible Python and existing packages.
Commands not run: Full repository suite, model/physical/device acceptance, automated
browser assertions, load benchmark. No runtime worker/main-agent restart.
Known limitations: 250 nodes default/500 max, 2000 edges; latest-node subset and
loaded-view text search only. No editing, clustering, live refresh or 3D/VR.
Security implications: Local read-only diagnostics exposes memory/evidence under
existing dashboard access boundaries; no external resources, inference or DB writes.
Deployment implications: Restart existing debug dashboard to load new routes. Main
Butler need not restart for this viewer. Preview servers were temporary QA only.
Unresolved questions: Transient and duplicate-looking real memories warrant a
separate learning-quality investigation if owner authorizes; no viewer blocker.
Current repository state: Existing uncommitted LTMS work preserved; unrelated
.claude/settings.local.json left untouched. No migrations/production writes.
Next permitted task: Owner evaluation using graph; separately scoped tuning only.
Required reading for next session: docs/LTMS.md viewer section and this handoff.
Explicit stop point: Simple 2D read-only nodes/edges viewer. No executor/3D/learning
policy expansion.


## 2026-11-19 - Launcher LTMS/DIS/WCS and graph access

Session goal: Make graph accessible and update launcher for implemented systems.
Current phase: Bounded launcher integration.
Bounded task completed: Open memory graph button starts/reuses dashboard and checks
/memory availability; separate Information & memory tab persists implemented
DIS/WCS/LTMS settings, fixes history wording and clarifies clearing isolation.
Files added: None.
Files modified: butler/launcher/{dashboard,gui,core}.py, settings.env,
tests/test_launcher_{dashboard,llm_debug}.py, docs/LTMS.md and status/decision/
open-question/session records.
Migrations added: None.
Decisions made: ADR-070; no separate launcher LTMS lifecycle or silent interpreter
fallback for main runtime. Diagnostic buttons moved to their own row; system
settings in separate tab to avoid crowding main launcher.
Assumptions confirmed or changed: Dashboard runs independently from Butler, on
demand through launcher. Configured venv base Python312 executable no longer
exists. Main owns LTMS, so no duplicate process start in Supervisor.
Tests run/passed: python -m unittest discover -s tests -p 'test_launcher*.py' -q:
32 passed (including headless widget construction/persistence, graph URL reuse,
old-server error and browser-opening callback). test_memory_graph.py: 5 passed.
Compilation and git diff --check passed. Test interpreter was available Inkscape
Python 3.12 with existing .venv-main site-packages supplied via PYTHONPATH.
Tests failed: No assertions failed. Existing runtime --version probe confirms
missing base interpreter; environment not rebuilt.
Commands not run: Full repository suite, live native launcher UI, main-agent/model
restart, hardware/control actions. No package installation.
Known limitations: Fresh child startup from the configured runtime requires
restoring its base Python installation; error now explicitly points to it. New
widgets require reopening launcher; saved settings require restarting Butler.
Security implications: Dashboard stays loopback/read-only; Windows dashboard child
uses CREATE_NO_WINDOW. No cloud exposure or changes to action authorization.
Deployment implications: Started operational diagnostic server hidden on 8787
using available Python and existing packages, kept running for owner use; verified
via launcher DashboardProcess.ensure_running('/memory') and browser showing 62
active nodes and 11 edges at observation. Main Butler not restarted. Server is
external to a newly reopened launcher, which will reuse without owning it.
Unresolved questions: Restore old Python312 base or rebuild runtime separately.
Current repository state: Prior LTMS/viewer changes preserved; uncommitted launcher
updates. Unrelated .claude/settings.local.json untouched.
Next permitted task: Owner uses graph/launcher; separately bounded runtime repair
or LTMS learning-quality fixes only when assigned.
Required reading: docs/LTMS.md launcher section and this record.
Explicit stop point: Launcher/access integration. No LTMS policy changes, 3D/VR or
executor implementation.


## 2026-11-19 - Stop direct DIS status ingestion into LTMS

Session goal: Stop device status evidence from filling LTMS; defer DIS package.
Current phase: Bounded LTMS ingestion correction.
Bounded task completed: Removed DIS cache reads; reject source dis: submissions,
discard old DIS jobs on startup and before inference; clarify device-status prompt
exclusion while preserving explicit conversational preferences.
Files added: None.
Files modified: butler/ltms/service.py, tests/test_ltms.py, docs/LTMS.md and
status/decision/open-question/session records.
Migrations added: None.
Decisions made: ADR-071; future DIS package is not implemented or scaffolded.
Assumptions confirmed or changed: WCS remains in scope as existing input. No stored
memories or edges should be removed by this cutoff.
Tests run: test_ltms.py full 15 cases; then 14-case suite excluding the environment-
blocked main-runtime import check; Python compilation and git diff --check.
Tests passed: 14 (including three new checks for no DIS cache read, rejected direct
input, old pending/failed queue cleanup, preserved memory and no model invocation).
Tests failed: Existing test_retired_fact_tools_absent_and_history_still_readable
cannot import main runtime: pydantic_core._pydantic_core unavailable using current
Inkscape Python312 plus existing .venv-main site-packages. No assertion was changed
or test weakened; remaining 14 cases reran and passed.
Commands not run: Live-model acceptance, full repository tests, Butler restart,
production DB queue cleanup or node deletion. Tests use temporary SQLite only.
Known limitations: Running Butler still uses previously loaded code until restart.
Routine statuses repeated in conversation are discouraged by prompt; direct DIS
feed cutoff is deterministic, semantic extraction policy remains model-dependent.
Security implications: Less raw device evidence reaches LTMS; no new access paths.
Deployment implications: Restart Butler to stop the old sampler and discard old
DIS pending/failed jobs. Existing memories and graph remain unchanged.
Unresolved questions: Future DIS status-package contract requires its own bounded
assignment. Existing noisy memories can be reviewed/cleaned separately.
Current repository state: Uncommitted prior work preserved; no runtime/deployment
or unrelated edits performed by this change.
Next permitted task: Owner restart/evaluation; future package or cleanup only if
assigned.
Required reading: docs/LTMS.md, ADR-071 and this record.
Explicit stop point: Direct DIS ingestion cutoff, no replacement system.


## 2026-11-19 - Remove persisted DIS status updates from LTMS

Session goal: Owner-directed deletion of existing DIS status updates.
Current phase: Bounded data cleanup.
Bounded task completed: Inspected source provenance and conversational status
entries, deleted 90 LTMS nodes, 10 incident edges and 70 DIS extraction jobs in one
BEGIN IMMEDIATE transaction. 18 LTMS memories remained at commit.
Files added: None.
Files modified: Production shared DB LTMS-owned rows only; status and session log.
Migrations added: None.
Decisions made: Delete 85 directly DIS-sourced entries plus five individually
reviewed status statements extracted through owner/assistant conversation inputs;
preserve weather/other memories and all non-LTMS data. No general cleanup rule or
backup/export retaining deleted memory content was added.
Assumptions confirmed or changed: Some device status statements had conversational
rather than dis: source provenance, requiring explicit inspected IDs.
Tests run/passed: Transaction checked non-LTMS table row counts unchanged, no
remaining DIS-source memories and no dangling edges; independent post-commit
read verified zero DIS memories/jobs and zero PRAGMA foreign_key_check violations.
Tests failed: None.
Commands not run: Unit suite (no runtime code change), model calls, Butler restart,
physical controls. No full-file deletion, vacuum, migration or history clearing.
Known limitations: Prior running Butler code can admit new DIS data until restarted
with the already-implemented cutoff. This cleanup does not alter learning policy.
Security implications: Authorized permanent deletion of selected LTMS rows and
incident edges only; other module data preserved.
Deployment implications: Refresh graph to see deletion. Restart Butler if the
previous direct-DIS ingestion code is still running.
Unresolved questions: No cleanup blocker; future DIS package remains deferred.
Current repository state: Prior uncommitted code preserved; only current records
and documentation changed by this task.
Next permitted task: Owner graph evaluation; separately assigned work only.
Required reading: docs/LTMS.md and current implementation status.
Explicit stop point: Remove existing device-status memory data; no other cleanup.


## 2026-11-20 - Read-only LTMS content and operation evaluation

Session goal: Assess stored memory quality, effective organization and admitted data.
Current phase: Bounded audit, no implementation or cleanup authorization.
Bounded task completed: Query-only consistent DB inspection, source/evidence review,
exact-text redundancy analysis, active-edge analysis, three real local-embedding
retrieval probes, code inspection and targeted existing main-model input capture.
Files added: None.
Files modified: Implementation status, open questions and this audit record only.
Migrations added: None.
Decisions made: No new design decision; findings are evidence for owner review.
Assumptions confirmed or changed: Working persistence/embeddings do not establish
useful memory. Direct DIS cutoff appears effective; conversational status leakage
and transient WCS ingestion continue. Distinguish active graph from archival edges.
Tests run/passed: Read-only DB probes: 711 total/214 active/497 archived, 54 distinct
normalized active texts (160 excess copies); 214 active embeddings, all 384-dim
all-minilm; 199 total edges/60 active edges/52 connected active nodes/162 isolates;
zero PRAGMA foreign_key_check violations. No active direct DIS-source entries.
Failure snapshot: 160 exhausted jobs, 85 ValueError/48 ReadTimeout/27 JSONDecodeError;
no successful-job ledger, so cannot calculate lifetime success/failure percentage.
WCS dominates failures; queue counts change during live activity.
Recall probes used Store methods bound to a query-only connection (constructor not
called) and LocalModel.embed only; no extraction/inference writes. Sleep lighting:
8 results/2 distinct texts; Minecraft (no stored Minecraft memory): 6 unrelated
lamp results/3 texts; current-time query: 8 results/2 texts including obsolete time.
Existing llm_io_20261120T224722_2720.jsonl: 34 sent records include LTMS blocks;
latest excerpt contains four Ask-time copies, four old 6:18 PM copies and linked
historical time-correction claims. This proves context contamination, not sole
causation of any main-model answer.
Evidence review: Memory claiming bed-lamp-off preference attached to new owner
message 'turn on the lights.' Weather evidence attached to conversational request
pattern summaries. Shows insufficient new-evidence grounding/provenance retention;
prior supporting evidence may be lost when updates replace the source field.
Tests failed: No test assertions were run or failed; 160 failed production jobs are
a finding, not tests generated by the audit.
Commands not run: Unit suite, extraction/model mutation, cleanup, restart, hardware
commands, broad raw log dumps or write-enabled DB access.
Known limitations: No successful extraction operation ledger; cannot establish
lifetime failure rate, which archival operations occurred, or historical recall
coverage. Content classification is qualitative; exact duplicates exclude semantic
paraphrases. Proposed remedies require a new bounded implementation assignment.
Security implications: All DB connections query-only; local CPU embedding requests
only; no data sent externally. Avoided repeating offensive one-off utterances in
user report; they are also stored as inferred durable preferences without a useful
context distinction. No deletion or changes to source history.
Deployment implications: None.
Unresolved questions: Owner may authorize bounded admission/consolidation/evidence/
retrieval corrections before enabling executor use; no automatic next phase.
Current repository state: Only audit documentation modified; unrelated existing
.claude/settings.local.json preserved. Runtime DB and configuration unchanged.
Next permitted task: Owner review and separately assigned repairs; no expansion.
Required reading: docs/LTMS.md, current source, this audit and architectural invariants.
Explicit stop point: Evaluation delivered; no runtime or memory modifications.


## 2026-11-20 - Controlled LTMS model versus input/contract discovery

Session goal: Test owner's garbage-in/insufficient-model hypothesis without repairs.
Current phase: Discovery only, explicit no code edits.
Bounded task completed: Current-prompt/model/schema inspection, local Ollama metadata,
17 inference-only probes, real-context reconstruction from query-only DB, and two
in-memory operation-contract reproductions. No extracted operations applied to live DB.
Files added: None.
Files modified: Discovery status, open questions, this session record only.
Migrations added: None.
Decisions made: None; evidence narrows failure boundaries for owner review.
Assumptions confirmed or changed: Source mismatch in prior audit is not sufficient
proof of a model unsupported claim: merge/update overwrite original provenance.
Tests run: 17 bounded local requests (15 qwen3:8b, 2 mb-core-v1:latest) plus
in-memory Store operation probes, no full suite and no code under change.
Runtime metadata: Qwen 8.2B Q4_K_M, 8192 context, reported size_vram equals model
size ~5.73 GB. CPU all-minilm present. Existing main model 14.8B Q4_K_M, 16384
context, custom template/system. Requests used temperature 0 and think=false;
production probes num_predict=4096, comparison/ablation probes 512. Options changed
per request only, not configuration. Live service concurrency makes timings
non-isolated; no throughput/hardware adequacy benchmark is claimed.
Probe results, original prompt/schema:
- Clean explicit warm-light preference -> one sensible create_memory.
- Clean assistant light-status statement -> inappropriate current-state memory.
- Existing exact warm-light preference + same new assertion -> duplicate create.
- Clean weather plus an existing preference -> current-temperature memory.
- Real-context 'turn on the lights' -> 3 merges + 10 edge removals, 4212 prompt
  tokens/1224 output tokens, stop. Includes removing edges by IDs archived by merges.
- Real-context 'what time is it' -> 5 repeated existing memories + 11 edges,
  5430 prompt tokens/1082 output tokens, stop. Reproduces amplification pattern.
Ablations:
- Same 8B with clearer decision rules/examples, clean transient and known duplicate:
  both correctly return empty operations. Generic JSON rather than schema, original
  prompt: both original errors persist, so schema decoding alone is not the cause.
- Existing 14B main model, same original task: invented edge IDs for transient and
  duplicate examples; invalid references. Custom model/template makes this a narrow
  comparison, not a definitive base-model capacity benchmark.
- Clearer prompt but full polluted time context: still copies old memory and edges;
  hit experimental 512-token output limit, leaving invalid/incomplete JSON.
- Original prompt, clean time query: stores 'Asked about the current time'.
- Clearer prompt, clean weather: correctly empty operations.
- Explicitly requested two-node graph consolidation: correct merge_memories(a,b).
- Clearer prompt, same time query with 3 unique content/ID references and no edges:
  correctly empty operations (625 prompt tokens, 5 output tokens).
In-memory contract checks:
- Merge two nodes then remove an old source-node edge -> ValueError 'memory not
  found or archived', rolls entire batch back (three active original nodes remain).
- Valid merge-only of old warm-light evidence, triggered by 'turn on the lights':
  resulting memory source becomes exactly that new trigger, losing original
  evidence provenance in the merged node. This is application behavior, not an LLM.
Tests passed/failed: Mixed behavioral outcomes are discovery findings, not a passing
acceptance suite. Both deterministic contract reproductions observed as described.
Commands not run: Production extraction/write calls, cleanup, unit suite, model
installation/switching, runtime restart, persistent prompt/model/template edits.
Known limitations: Small deterministic examples, not statistical broad evaluation;
no direct plain-Qwen14B benchmark (would require changing loaded deployment).
Historical failed jobs keep only exception class, not proposal/body/done_reason,
so cannot assign all 85 prior ValueErrors or 27 JSON errors to the reproduced causes.
512-token experimental truncation proves a possible failure mechanism, not the
cause of historical production failures with a 4096-token budget. Full contexts
inspected fit the reported 8192 input context; overflow not established here.
Security implications: Production SQL used query-only connections. All inference
local; in-memory databases alone used for operation application. No external data
transfer or production memory mutation.
Deployment implications: None. Existing loaded model instances used for probes;
no new model downloaded or deployment settings changed.
Unresolved questions: Boundary/specification of meaningful experience, new evidence
versus consolidation, legal batch lifecycle and multi-source provenance, reference
context selection, and model capacity under a clarified fixed contract. These
require owner agreement before implementation.
Current repository state: Source/config/database unchanged by discovery; only
required documentation records updated. Existing .claude/settings.local.json untouched.
Next permitted task: Owner review of findings and explicit bounded repair scope.
Required reading: This discovery record, current LTMS prompt/Store.apply and prior audit.
Explicit stop point: Discovery; no prompt, ingestion, operation or retrieval repairs.


## 2026-11-21 - Disable automatic WCS input to LTMS

Session goal: Apply the existing DIS ingestion cutoff to WCS, no other changes.
Current phase: Bounded ingestion change.
Bounded task completed: Removed LTMS source polling and unused fingerprint state;
reject both dis:/wcs: evidence, discard pending/failed jobs at worker startup and
before extraction. WCS-owned collection/cache and conversational learning unchanged.
Files added: None.
Files modified: butler/ltms/service.py, tests/test_ltms.py, docs/LTMS.md,
implementation status, decisions, open questions and session log.
Migrations added: None.
Decisions made: ADR-072; trend packages deferred without placeholders.
Assumptions confirmed or changed: Weekly history is not currently retained by WCS;
future trend support requires its own evidence contract.
Tests run: Full test_ltms.py (15 cases): 14 pass, one existing import error;
14-case subset excluding that environment-blocked test passes. Python compileall
and git diff --check pass. Used available Inkscape Python312 plus existing
.venv-main site-packages; no environment repair.
Tests passed: Rejection of WCS current/forecast, preserved conversational weather
preference, no DIS/WCS cache calls during intake, cleanup of pending/failed DIS/WCS
jobs while retaining memory/owner job, and no model call for old observation jobs;
other 10 LTMS store/worker cases also pass (14 total).
Tests failed: Existing test_retired_fact_tools_absent_and_history_still_readable
cannot import pydantic_core._pydantic_core via main runtime; unchanged assertion.
Commands not run: Full repository, local-model acceptance (prompt unchanged),
production cleanup, Butler restart, source collection or hardware actions.
Known limitations: Existing running code continues until restarted; conversational
weather remains eligible input. No existing weather memory deletion requested.
Security implications: Reduced automatic observation input, no new access or writes.
Deployment implications: Restart Butler to stop old WCS sampling and discard its
queued work. Existing LTMS nodes and edges are preserved.
Unresolved questions: Future bounded WCS trends/status package remains unassigned.
Current repository state: Earlier staged discovery documentation preserved; no
production DB writes. Unrelated .claude/settings.local.json untouched.
Next permitted task: Owner restart/evaluation; other work only if assigned.
Required reading: docs/LTMS.md current ingestion section and ADR-072.
Explicit stop point: Automatic WCS feed disabled, no other behavioral repairs.
