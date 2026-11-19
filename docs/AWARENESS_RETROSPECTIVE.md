# Awareness retrospective

Date: 2026-11-18. Status: historical record of the retired implementation.

## Intent and original scope

Awareness was intended to give Butler reliable knowledge of the household while
keeping continuous processing and safety decisions outside the language model.
It grew to cover source/device registration, event ingestion and provenance,
current state, source health, historical/numeric queries, rules, alerts and
attention, notification delivery, reminders, human observations, long-term
memory, physical-action validation and proactive briefings. A bounded situation
summary and MCP read tools connected those capabilities to conversation.

The backend ran separately from Butler, using Docker-hosted PostgreSQL with
TimescaleDB and pgvector, the existing MQTT broker, multiple background workers,
and optional local Ollama embeddings/briefing selection. Conversation history
and prompt memory remained in a separate SQLite store owned by the main agent.

## What was useful

- Separating current observations from immutable events and semantic memories
  was sound. Freshness, source identity, clock qualification and conflict
  handling are useful properties worth retaining where required.
- Live pump investigations demonstrated heartbeat/last-will/offline/recovery
  tracking. Recorded offline pump requests were rejected before dispatch.
  These are concrete successes, not merely implemented interfaces.
- Registered actions distinguished request acceptance from acknowledgement and
  physical completion, preserved audit evidence, and retained firmware/hardware
  interlocks. Retirement must not justify restoring unvalidated MQTT commands.
- The backend provided structured reads and deterministic processing independent
  of model inference. A local model was not the alert detector or clock.
- Prior session records document exercised ingestion/migration/action tests,
  backup restoration and useful operational telemetry. These establish specific
  tested behaviors, not comprehensive household acceptance.
- Actual captured model inputs prove household context sometimes reached the
  model. The system was not entirely nonfunctional.

## What failed or remained unproven

**The agent-facing result did not match the breadth of the implementation.**
In a bounded audit of five recent model-input files, 111 of 126 model request
records contained a situation snapshot. Those are inference requests, including
follow-up rounds, rather than distinct user turns. In the three older files,
historical announcement sections occupied approximately 65-73% of snapshot
characters. Selected device facts were limited to stale legacy pump-pin or
unknown fuse properties; useful canonical running/relay properties were absent
from those snapshots. This does not prove they were absent from the database.

The broker prioritized up to three verbose historical announcement receipts
ahead of device state, considered only a global limited set of recently updated
property rows, and sorted equal-priority candidates by identifier. It did not
reserve representative state coverage per device or target the current request.
Successful prompt injection therefore did not establish useful device awareness.

The newest 12 audited requests had no snapshot. Read-only probes returned HTTP
500 for situation and pump state; capabilities explicitly reported database
unreachable. The configured Docker engine was unavailable. Retrieval could fall
back to empty legacy status and omit context without a model-visible explanation.
This was a concrete availability failure, not proof that Docker or PostgreSQL
are intrinsically unsuitable.

Earlier integration failures had already required restoring streaming snapshot
injection and removing a 500-character cutoff that discarded device facts.
Later captures demonstrated that longer snapshots reached the model, but
selection/coverage weaknesses remained.

**Coverage and ownership were fragmented.** Light/coffee smart-plug controls were
outside awareness state ingestion and its action authority. Listing configured
lights did not read their power. Setting power did not independently verify the
final relay state. A broadly named household backend did not mean all household
devices were actually represented.

**Memory infrastructure exceeded demonstrated deployment.** Awareness had a
PostgreSQL memory store alongside SQLite conversation/prompt memory, with partial
mirroring rather than a single ownership model. Vector search required a local
embedding model. Inspection of the default Ollama manifests found chat models
but no configured `nomic-embed-text`; this supports a missing current dependency,
not a claim that embeddings could never have operated under another directory
or earlier installation. Keyword retrieval and non-memory functions did not
depend on embeddings. Operational semantic-memory value was not established.

**Tests and implementation status did not establish product acceptance.**
Mocked tests could prove serialization, selection mechanics and lifecycle rules
while accepting poor context allocation. They did not prove that the real model
could answer representative household questions or consistently select state
tools. Several live acceptance items remained pending. Both deterministic
contract checks and explicit model/device acceptance were needed.

## Why the owner chose replacement

The owner accepted the underlying goals but chose incremental, narrowly scoped
replacement systems rather than additional repairs to the broad subsystem.
Many independently useful functions had accumulated shared deployment,
information-selection and lifecycle dependencies. The resulting integration
cost and failure behavior were disproportionate to the small set of real device
integrations and the demonstrated conversational benefit.

This is an architectural/product judgment supported by the evidence above, not
a claim that every component was defective. In particular, proven physical
safeguards and observation semantics should inform replacements even where the
old implementation is not reused.

On 2026-11-18 the owner authorized decoupling and archival. Source, migrations,
isolated tests and deployment manifests are preserved under
[`archive/awareness`](../archive/awareness/README.md) and in Git history/main.
Startup hooks, runtime clients/signals/mirroring and awareness tools were removed.
Pump/fan tools were retired with their action authority; no direct control bypass
was introduced. Conversation history, saved SQLite facts, independent controls,
existing database data/volumes and firmware were preserved. Retirement source
changes require process restart to affect already-running deployments.

## Constraints for replacements

1. Start with a concrete user need and a finite acceptance checklist. A working
   real-device example must precede claims of broad support.
2. Give each fact one owner. Other modules read it through explicit interfaces;
   model prose, command intent and old announcements do not become observations.
3. Prefer modules within Butler's lifecycle and existing suitable infrastructure.
   Add services/extensions only for a measured need.
4. Make loss of capability explicit to both the operator and model. Unknown,
   stale, offline and unsupported are meaningful outcomes.
5. Keep device summaries dedicated to device state, with coverage checks and
   visible omission metadata. Other future context cannot consume that budget.
6. Keep conversation history in the conversation engine. Exact device questions
   use structured observations, not semantic memory.
7. Test actual prompt contents and behavior, not just component internals. Live
   model acceptance is opt-in, uses simulated actuation, and records the model
   and configuration; physical acceptance is separately supervised.
8. Do not rebuild reminders, attention, briefings, semantic memory or a generic
   event platform while implementing the first Devices increment.

## Evidence and limits

- [Per-turn investigation](awareness-memory/PER_TURN_AWARENESS_2026-11-18.md):
  bounded input-file sample, live API/Docker observations and code-level causes.
- [Capability map](awareness-memory/CAPABILITY_MAP_2026-11-18.md): original
  responsibilities and external boundaries.
- [Session record](awareness-memory/SESSION_LOG.md): earlier deployment/testing
  evidence, including pump liveness and power-source diagnosis.
- [Retirement report](awareness-memory/RETIREMENT_2026-11-18.md) and
  [ADR-058](awareness-memory/DECISIONS.md#adr-058---retire-awareness-without-replacing-conversation-memory):
  authorized removal, validation results and remaining limitations.

This retrospective adds no new live probes or acceptance claims. It records the
known evidence and its limits for future implementers.
