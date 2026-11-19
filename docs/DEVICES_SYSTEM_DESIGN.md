# Devices system: bounded design proposal

> Storage update (2026-11-18): the owner subsequently authorized a unified Butler
> SQLite database, now implemented in [DATABASE.md](DATABASE.md). Devices must
> use its owned tables through that layer, rather than the dedicated-file
> proposal below. No Devices runtime/schema has been implemented.

Date: 2026-11-18. Status: design/discovery only; no runtime implementation or
restoration of retired controls is authorized by this document.

## Product contract

Devices answers: **Which devices does Butler know, what can each actually report
or support, what was last observed, and how trustworthy is that observation now?**

The first increment owns a finite registry, validated observations, latest state,
device communication health, and structured reads plus a compact per-turn view.
It starts and stops with Butler and works without a language model. A device
adapter failure must not prevent conversation or other adapters from operating.

Device observations, their qualification and capability availability are its
authority. It does not own human presence, conversation memory, long-term memory,
numeric analytics, alerts/attention, notification delivery, reminders, scheduled
automation, proactive briefings or arbitrary external events.

## Deployment and ownership

Use one module within the main Butler process, with a bounded background worker
and ordinary internal interfaces. No separate API service, Docker database,
TimescaleDB, vector store or embedding model is proposed. Existing MQTT remains
the transport for firmware that already uses it; a Kasa adapter uses its local
protocol. Do not add a second broker or change existing firmware topics casually.

A proposed small, dedicated SQLite file under `db/` stores the registry/current
observations and the minimal evidence needed to identify an observation. It is
separate from the conversational database and belongs to Devices. The local
store is authoritative; any in-memory read view is a projection of committed
records. Persist observations asynchronously from network operations; do not
hold database transactions across device calls. Serialize writes, bound waits
and results, and expose storage failure rather than presenting an uncommitted
value as authoritative. Final schema/retention choices belong to the first
bounded implementation, not to speculative future modules.

The MCP provider runs in a child process today. A later device read tool must
reach the main process's owning service through the existing main-service
boundary rather than starting another poller or independently writing its DB.
Per-turn injection can call the owner directly. This inter-process bridge needs
design and tests in the read-tool increment; there is no new standalone Devices
service. Keep authorization at the ingress, including snapshot injection for
restricted callers; context visibility must never bypass existing tool-access
or owner-conversation permissions.

## Small set of contracts

| Record/interface | Required meaning |
|---|---|
| Device definition | Stable ID; display name and explicit aliases; device kind; adapter and endpoint/credential reference; enabled flag; supported observed properties; bounded refresh policy; primary summary properties |
| Property observation | Typed value/unit; source/device ID; observed time if known and receipt time; evidence reference; qualification and expiry policy |
| Communication health | Last successful contact, latest attempt, bounded error reason and heartbeat/poll deadline; reachable/offline/unknown/disabled as applicable |
| Device read | Device metadata and qualified properties; current health; as-of time; explicit missing/unsupported fields; structured failure if the owner/store is unavailable |
| Per-turn summary | Deterministic projection of the same device-read contract; generated/as-of time; per-property ages/qualification; coverage and omission metadata |

Use one authoritative registry. Migrate existing configured IDs instead of
inventing a parallel list. Aliases support names such as "desk lamp" but do not
guess identities when ambiguous. Store credential references, not secrets in
records, tools or prompts. Property declarations must reflect adapter-supported
reads, not a wish list of future capabilities.

Keep communication health separate from state freshness. A controller may be
reachable while one sensor value is stale. A failed request must not overwrite
the last observed `on` value with `off`. Preserve that last observation with its
age/status. After restart, requalify saved observations; old records are not
fresh simply because they loaded successfully. Retained MQTT replay is evidence,
not proof that a controller is currently alive.

## Adapters, not a generic event platform

Use a small explicit adapter contract: start/stop, bounded refresh where
supported, and delivery of validated typed property/health updates. Push devices
subscribe to their registered topics; polled devices have configurable intervals,
timeouts, bounded concurrency and backoff. Avoid duplicate connections and
overlapping polls of the same device. Device-specific mapping stays in adapters;
normalization, persistence and qualification stay in the owner module.

Updates validate device/property identity, value type, source ownership and
ordering before replacing state. Apply device sequence/boot identifiers where
available; delayed packets must not move current state backwards. Where clocks
are unsynchronized, retain that fact and use receipt time appropriately. Device
identifiers and free-text values are bounded and treated as data in prompts.

The initial store needs latest observations and enough evidence to explain them,
plus operational diagnostics. It does not need a general event bus, arbitrary
payload archive, incident graph, long-term telemetry or memory consolidation.
Future history integration can consume explicit observations when separately
assigned; no placeholder consumer or future schema is created now.

## Device-specific reality

| Device | Existing integration/evidence | Proposed useful state and limits |
|---|---|---|
| Lights | Six configured smart switches/plugs through Kasa; live controls exist, but no model-facing power read today | Observe each relay's power and communication health. Relay on does not prove the bulb emits light. A wall-switch change must eventually be reflected by polling/observations |
| Coffee machine | `coffee-pot` is configured as a Kasa appliance smart plug and excluded from the all-lights group | Track plug power and reachability. Brewing, water level, temperature and readiness are unsupported unless actual sensors/protocols supply them |
| Plant watering | Canonical MQTT firmware and historical action/liveness evidence; backend control tools retired | Controller reachability and individually reported channel/relay states. Do not equate relay on, controller online, command accepted and water delivered. Preserve firmware maximum duration/interlocks; do not assume fuse/flow/moisture sensors exist |
| Kitchen screen | Owner identifies it as required; previous tool-history tests contain `kitchen_screen_control`, but its deployed reporting/control contract has not been verified in this design inspection | Identify its actual adapter and observable fields first. Possible fields must be justified by its API. Do not confuse it with the existing InfoPanel/TV display-power integration |
| Other devices | Add through a bounded, reviewed registry/adapter change | New device support needs proven reads, explicit limits and acceptance checks; "etc" does not authorize speculative integrations |

Configuration/source inspection establishes the first two integrations, not
current connectivity. No device was queried or actuated during this design task.

## Relationship to control

Observation and execution remain distinct. The initial Devices assignment does
not restore pump/fan execution or create a generic action engine. Existing
independent controls stay as they are until a separately scoped migration; they
may report an actual fresh observation through the adapter, but a successful
command submission never becomes an observed state by assignment.

Any later control integration uses declared operations and typed parameters,
runtime-bound identity/idempotency, permissions, configured confirmations,
timeouts, acknowledgements, reconciliation and audit. Validate state-dependent
preconditions at execution time; prompt context is not authorization or a safety
check. After ambiguous mutation timeouts, reconcile before retrying. Firmware and
hardware retain immediate interlocks. A registry capability entry does not
register a callable action until its implementation is available.

## Per-turn device summary

**Recommend yes:** inject a short device-only summary on every authorized owner
turn, from committed observations already kept up to date by adapters. Do not
poll the whole house, call an LLM, or contact another service to prepare a turn.
The conversation engine uses a bounded local read and inserts a fresh system
context block, separate from historical messages and long-term memories.

Illustration only, not live readings:

```text
Devices as of 14:02:10; coverage 4/4; no omitted devices.
desk-lamp-0: relay=off [current; age 3s]; reachable.
coffee-pot: plug_power=on [current; age 8s]; brewing=unsupported.
plant-waterer: offline; channel_1=off [last observed 12m ago; stale].
kitchen-screen: state=unknown [adapter not connected].
```

The illustration shows four devices for readability, not the current full
registry. Production starts with one short row per registered device for this
small household; the watering controller has a compact channel group rather
than one row per low-level property. Primary properties are explicit adapter/
registry choices. Do not spend space on raw payloads, provenance paragraphs,
announcements, presence or arbitrary fuse properties at the expense of device
coverage. Unknown, stale, offline, unsupported and disabled remain visible.

Start with a measured target around 500-800 tokens for this inventory, not a
fixed promise that all future devices fit. Enforce a hard bound with structured
coverage fields (`shown`, `total`, `omitted_count`, `truncated`). If it is exceeded,
include requested devices first where deterministically resolved, then a stable
bounded selection, and explicitly identify incomplete coverage. Preserve the
availability/omission header and atomic rows; never silently slice a string.
Do not treat omitted devices as off or absent. Revisit the budget/format when
the registry grows rather than introducing an elaborate ranking subsystem.

If the module/store fails, inject `Device state unavailable` with a bounded
reason and as-of time. An empty registry is a separate condition. Never omit the
block silently, reuse an earlier turn's block as current, or fall back to model
memory. Log request correlation, summary size, included device IDs, ages and
omissions so actual model input can be verified without logging secrets.

This saves routine read-tool calls, but the summary is not a synchronized
physical measurement at the instant of speech. A later structured read/refresh
tool is still useful for expired/missing properties, explicit "check now"
requests, details omitted from the summary, or reconciliation after a command.
A known fresh summary can support ordinary state questions without another
device query. Safety-critical actions always apply their own fresh checks.

## Scope gate and acceptance

An addition belongs here only if it identifies a device, obtains/qualifies a
real observation, exposes supported device capability metadata, or reports
Devices' own availability. Suggestions to remember preferences, infer occupancy,
schedule watering, notify about silence or generate briefings go to another
bounded assignment. Offline is a state here; deciding to interrupt the owner
about it is not.

Proposed increments, each separately reviewable:

1. **Registry plus Kasa observation vertical slice.** Reuse configured IDs and
   cover lights plus the coffee plug; implement lifecycle, durable latest state,
   qualified reads and bounded polling. Demonstrate real wall-switch changes,
   offline behavior and restart semantics. Existing control behavior remains.
2. **Pump observation and kitchen-screen discovery.** Add only verified read
   adapters/fields. Preserve MQTT freshness/order rules; no pump activation or
   speculative kitchen-screen adapter. A missing integration is an explicit
   acceptance gap, not placeholder success.
3. **Per-turn injection and read tools.** Use the existing shared conversation
   engine and permission boundary, prove summary coverage in captured model
   inputs, and expose structured detail/refresh through the existing main/MCP
   boundary without duplicate worker ownership.

Each increment must be runnable and honest about which devices it supports. Do
not advertise whole-house tracking until every required device is verified.
No increment above authorizes physical-action restoration or another product
system.

Required checks include typed mapping; partial adapter failure; stale versus
offline/unknown; reboot/retained/late-message behavior; local-store failure;
bounded startup/shutdown and no overlapping polls; primary-property coverage;
visible omission/degradation; permission filtering; and real call/result history.
Use existing appropriate tests with simulated network/device effects. Add an
opt-in real-model acceptance set for prompt/tool changes: correct state answers,
fresh evidence over stale history, refusal to invent brewing/water-flow state,
unavailable-device honesty and correct tool selection. Record model/settings,
latency and repeated outcomes; never actuate hardware during model tests.

## Open design/discovery items

- Confirm the kitchen screen's current endpoint, ownership and observable fields.
- Select refresh intervals and per-property expiry from device behavior and
  required latency; no single global threshold proves every property current.
- Finalize the small SQLite schema, evidence/diagnostic retention bounds and
  thread/process read bridge in the first relevant implementation assignment.
- Measure summary size with the complete verified registry and actual tokenizer;
  decide any hosted-provider/context disclosure policy using existing settings
  and permissions, not an implicit new external data path.

The owner has selected Devices as the next subject; module/storage/contracts and
increments above are proposals. Stop at this design and the
[awareness retrospective](AWARENESS_RETROSPECTIVE.md). No runtime modules,
migrations, adapters, tools or dependencies were added by this document.
