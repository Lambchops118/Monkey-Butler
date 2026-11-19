# Device Information System (DIS)

Implemented 2026-11-18. Scope: **read-only information about the six configured
Kasa lights, the coffee-machine smart plug and passive plant-waterer telemetry**.
Six owner-declared inventory entries explicitly have no live integration. DIS never switches power,
starts a device job, publishes control messages or executes subsystem commands.
It is not a replacement alert, reminder, memory or briefing service.

The owner authorized implementation, selected default owner-turn summaries,
requested five-second background observation plus command-triggered refresh,
and explicitly prioritized no waiting for verification in the conversational
path. The owner subsequently authorized the waterer read adapter and explicitly
requested informational inventory entries for devices without status interfaces.

## Data path and latency

```text
Kasa read adapter -> committed SQLite observations -> immutable cached records
                                                        |
                 owner turn -> format small DIS block ---+-> model input

existing set_smart_plug tool -> enqueue priority read -> return immediately
```

Butler starts/stops DIS with its main process. The existing main HTTP service
provides the read bridge to the MCP child; no additional server, container or
database is created. Schema migration 2 adds `dis_devices`, `dis_observations`
and `dis_health` to `db/butler.sqlite3`. Migration 3 adds typed-property source,
retained-message, boot/sequence and contact-health metadata. Earlier migrations
are unchanged.

Background reads have at most three concurrent tasks and never overlap reads of
the same device. Each read has a three-second overall network deadline, bounded
disconnect cleanup and bounded authentication retries for intermittent Kasa
handshake failures. Failed devices back off up to 60 seconds. Polling intervals
are targets, not hard five-second outage-detection guarantees: network timeout,
bounded concurrency and backoff also affect detection/recovery time.

Network operations run outside SQLite transactions and the cache lock. The
owner publishes cached records only after storage succeeds. Prompt assembly
reads that cache and calculates expiry; it does not open SQLite, poll devices,
perform HTTP or call another model. Storage/worker failure becomes explicit
unavailability, not a silent missing block. Each inference retains one device
block rather than accumulating old copies across tool rounds.

An existing `set_smart_plug` attempt in either agent loop requests a priority
background read. It does not wait. It invalidates the pre-command observation's
*current* qualification until a new read started after that request completes.
Request generations prevent an old in-flight read from satisfying the refresh,
including when clock timestamps have coarse resolution. The requested power
value is never written as an observation. The `all` shortcut invalidates lights
only, excluding the coffee appliance. DIS does not own the control operation,
change its result or fabricate another tool exchange.

An explicit read tool with `refresh=true` may wait up to five seconds for an
attempt, then reports completion/pending state. This is opt-in information
retrieval, not a hidden wait on every turn or control reply.

## Registry, evidence and state semantics

The single configuration source is the existing `BUTLER_SMART_PLUGS` array.
DIS reuses its IDs, names, endpoints and light/appliance distinction. Add another
supported plug there and restart Butler; it automatically joins polling, the
summary and paginated reads. Registry bounds are 64 devices and bounded IDs/names.
Connection endpoints are persisted internally but excluded from model responses;
credentials remain in their existing secret environment settings.

A changed endpoint/kind invalidates old observations for that ID; removed
configuration entries become disabled internally and are not advertised. There
is no independently editable second registry. Configuration changes currently
require restart; no hot-reload/discovery framework is implied.

Each latest property has source, receipt time, age and an observation identifier.
The identifier refers to the latest observation, not an immutable-history API.
No event stream, full telemetry history or generic payload archive is introduced.
Kasa has no synchronized observation timestamp here, so `observed_at` is null
and the qualified receipt time is explicit.

Structured reads distinguish:

- `value`: current verified boolean power, or null if it cannot be established.
- `last_observed_value`: the preserved last read, including when expired or
  invalidated; it is never proof of the present.
- `status`: current, stale or unknown; `age_seconds` qualifies the observation.
- `health`: reachable, unreachable or unknown, with last contact/error metadata.
- `refresh_pending`: a control-triggered read has not reconciled current state.

On startup, saved observations are stale and health is unknown until this DIS
run contacts the device. A read failure does not turn a stored `on` into `off`.
Clock expiry is evaluated even if no new update arrives. Initialization/storage
failure is explicitly distinguished from an available empty registry.

Relay/plug power does not prove illumination, successful brewing, water flow or
mechanical operation. The coffee plug has no brewing/readiness/temperature
sensor in this integration. The first release supports power observations only;
a different protocol requires a real read adapter and declared property mapping,
not arbitrary device data or automatic commands. No printer/computer/pump or
kitchen-screen capability is advertised before implementation and acceptance.

## Model context and read tools

Full-access owner turns get a compact, timestamped device block, after stable
instructions/tool schemas and conversation history. Restricted turns receive no
automatic device block. The block includes primary power, health, age and
qualification; unknown/stale power is null rather than an easily misread old
boolean. Its coverage header reports shown/total/omitted rows. It contains no
announcements, human context, raw payloads, credentials or endpoint addresses.

The default summary budget is 3,600 characters. Stable rows are admitted whole,
never sliced into malformed fragments. The current seven-device inventory fits;
for larger registries the summary takes a bounded first page of eight devices
and explicitly reports omitted devices. Use paginated reads for full coverage;
do not treat omitted devices as off or absent. No promise of whole-house coverage
at arbitrary registry size is made.

`device_context_chars` in prompt telemetry records composition size. Existing
explicit LLM I/O capture can show the actual injected block; no new raw-content
telemetry stream is enabled by DIS.

The aggregate MCP provider group `device_information` exposes two typed,
structured, read-only tools:

- `list_device_information(offset=0, limit=8)`: bounded cached pages with explicit
  coverage and a next offset.
- `get_device_information(device_id, refresh=false)`: exact configured ID and
  optional bounded immediate read; unknown IDs return not_found.

They share one versioned result contract and retain JSON freshness, provenance,
coverage and errors intact through runtime result shaping. Normal tool
authorization and paired call/result history still apply. The main bridge is
`GET /dis/devices`: it validates input bounds, uses the existing API token when
configured, and rejects non-loopback reads without a configured owner API token.
The MCP child uses the loopback main service, never starts another poller or
writes directly to the database. `/health` exposes DIS component availability
without device names or values.

## Settings and rollout

| Setting | Default |
|---|---:|
| `BUTLER_DIS_ENABLED` | 1 |
| `BUTLER_DIS_SUMMARY_ENABLED` | 1 |
| `BUTLER_DIS_POLL_SECONDS` | 5 |
| `BUTLER_DIS_STALE_SECONDS` | 20 |
| `BUTLER_DIS_READ_TIMEOUT` | 3 |
| `BUTLER_DIS_SUMMARY_CHARS` | 3600 |

Restart Butler and its MCP children to load the new lifecycle, tools and
configuration. Summaries follow the configured conversation backend, including
explicit hosted-debug mode, and existing owner/caller access boundaries. DIS
does not select a provider or introduce a new external inference path.

No process deployment restart was performed by this task. A temporary live
read-only validation worker was started and stopped. No physical command or
firmware change ran. The coffee plug's reachability remains a deployment/hardware
question; DIS correctly exposes unknown information while it is unavailable.

## Verification and observed limitations

Deterministic discovery command: `.venv-runtime/Scripts/python.exe -m unittest
discover -s tests -p PATTERN -q`, with local sockets permitted for fixtures.

| Pattern | Final passing cases |
|---|---:|
| `test_dis.py` | 19 |
| `test_unified_storage.py` | 12 |
| `test_memory_store.py` | 11 |
| `test_launcher*.py` | 29 |
| `test_run_command_stream.py` | 17 |
| `test_awareness_retirement.py` | 5 |
| `test_text_server*.py` | 26 |
| `test_phone_inbound_server.py` | 18 |
| `test_router*.py` | 13 |
| `test_mcp_disable_selection.py` | 15 |
| `test_agent_runtime_phone_tools.py` | 4 |
| `test_debug_dashboard.py` | 17 |
| `test_smart_plugs.py` | 12 |
| `test_jobs.py` | 3 |
| `test_tool_ordering.py` | 5 |

Total: **206 deterministic passing cases**. DIS checks include real temporary
SQLite, cache-only turn reads, expiry/restart/remapping, failures and recovery,
stale versus current values, pagination/omission, bounded adapter timeout/auth
retry, authenticated HTTP/MCP schemas, restricted-context exclusion, no physical
adapter calls, generation ordering and nonblocking command refresh. A deliberately
blocked reader proves the simulated control reply finishes before readback.

The opt-in real-model test is `test_dis_model_acceptance.py`, enabled with
`BUTLER_DIS_LIVE_MODEL_TEST=1`. It refuses a hosted backend, uses the real turn
engine with simulated device observations and a simulated read-only tool, and
offers no mutation tools. The final four scenarios (fresh lamp state, unsupported
brewing inference, stale state, total DIS unavailability) passed **three
consecutive runs** on local Ollama `mb-core-v1:latest`. The test is skipped by
default. It evaluates these specific truthfulness cases, not broad language or
tool-selection reliability.

The initial real-model run failed: a stale false value was answered as current
off. The contract was changed to separate current `value` from
`last_observed_value`, omit stale booleans from routine summaries, and explicitly
require uncertainty. The assertions were not weakened. Two initial deterministic
refresh cases also exposed a clock-resolution race; generations fixed it.

Live read-only checks initially reached three lamps and saw intermittent switch
read failures plus a coffee timeout. After bounded authentication retry, a full
background sweep reached all **six lights**, reporting power on; the coffee plug
remained unreachable/unknown. The worker shut down afterward. This is a bounded
observation, not proof of continuous availability or physical illumination.

On this host, 1,000 cache-only summary-format calls for seven devices measured
about **0.039 ms median / 0.043 ms p95**. The seven-device block was roughly
1,200 characters. This measures formatting only, not inference, polling delay or
end-to-end voice latency. Additional model tokens still incur inference cost.

Python compilation, document links and whitespace checks passed. Existing
audioop deprecation and mocked-async smart-plug warnings remain visible. Full
repository tests, audio/GUI acceptance, physical switching tests, continuous
soak and deployment restart were not run. Previously recorded unrelated
personality wording tests were not included.

## Stop condition

Stop at the waterer adapter and explicitly requested inventory records. Do not
restore retired pump/fan actions, implement additional live adapters, or begin
World Context, Memory, alerts/attention, notifications, reminders or briefings.
Each later integration needs a separately bounded assignment and real read
contract. The historical [design proposal](DEVICES_SYSTEM_DESIGN.md) and
[awareness retrospective](AWARENESS_RETROSPECTIVE.md) remain background context.


## Waterer and inventory extension (2026-11-18)

The passive adapter reads exactly `home/irrigation/quad_pump/state`, `/health`
and `/heartbeat` from the existing broker. It never publishes, sets a will,
subscribes to commands, or restores retired action tools. It exposes four relay
booleans plus available firmware/uptime/Wi-Fi/MQTT/RSSI metadata. Fuse sensing
and actual water flow are not verified. There are no synthetic observations.

Firmware sends heartbeats every 30 seconds and periodic full state every 300
seconds (also on transitions). DIS uses a 120-second live-contact deadline and
360-second property freshness bound. These are source-specific; five-second
Kasa polling does not imply five-second waterer outage detection. Receipt time
is local; the firmware supplies boot/sequence identity, not synchronized wall
time. Per-stream sequence checks reject duplicates/older packets; changing boot
invalidates previous-boot current qualification. Retired boot tracking is bounded
to 16 IDs. Retained MQTT messages are historical evidence only: replay cannot
prove liveness or current relay state. Heartbeats never redate relay readings.
Previously persisted readings cannot become current merely because a new
process receives a heartbeat. Broker loss reports unknown source reachability;
a source last-will or expired heartbeat reports unreachable. An explicit MQTT
refresh returns `passive_source_no_query` immediately; no query is published.

`BUTLER_DIS_PUMP_ENABLED` defaults to 1. Optional broker settings:
`BUTLER_DIS_MQTT_HOST` (falls back to the configured display broker, then the
existing household broker), `BUTLER_DIS_MQTT_PORT` (1883), and
`BUTLER_DIS_MQTT_USERNAME`/`BUTLER_DIS_MQTT_PASSWORD`. Credentials and endpoints
never enter model context. Configuration is read at startup.

Inventory records: `ender-3-pro` (OctoPrint/Pi 3), `kitchen-screen` (Chromium
kiosk/Pi 4), `toshiba-tv`, `minecraft-server` (software), `minecraft-host`
(computer), `jeep-wrangler` (conceptual). These have adapter `inventory`, health
`not_integrated`, empty observed capabilities/properties, and explanatory notes.
They are not polled, do not imply supported controls and cannot report online,
printing, playback or vehicle state. They are declared alongside the integrated
registry in `configured_devices`; no dummy adapter or future service was added.
Summary generation considers the whole bounded registry, while public read tools
retain eight-device pages and explicit omission counts. Summary budget remains
3,600 characters by default; whole records are omitted rather than clipped.

Audit: DIS adds no deterministic user-facing conversational replies. Its fixed
strings are context or structured read results fed into the existing model turn.
Older deterministic action acknowledgements/failure guards remain in the agent
runtime and were not changed by this extension.

Extension validation: `test_dis.py` 19 cases; `test_dis_pump.py` 7 cases;
`test_unified_storage.py` 12 cases passed. The opt-in
`test_dis_model_acceptance.py` passed its four model-question scenarios in one
run against the configured local backend, with simulated devices and no control
tools. A real 35-second subscribe-only check received a live heartbeat from
`quad_pump-2.0.0`; retained health metadata was available, but no relay snapshot
arrived within that window. This verifies telemetry reception, not a complete
live relay-state sweep. Full suite, physical actions and deployment restart
were not run for this extension. Restart Butler and MCP children to apply it.
