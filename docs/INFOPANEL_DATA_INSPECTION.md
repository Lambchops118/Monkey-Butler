# InfoPanel data hookup inspection (2026-11-26)

Scope: read-only inspection of current display and backend interfaces. No runtime hookup or new source was implemented.

The display client polls authenticated `GET /display/state`. Its snapshot has command/response text, generic `statuses`, display-client heartbeats and sleep state. The renderer currently hardcodes all five dynamo states to online and overwrites each subtext every frame. Its finance and weather values are literals. Time, weekday and date already use the host clock via `time.strftime`; they are live, though timezone is the display host's local timezone.

| Display item | Existing source | Hookup assessment |
|---|---|---|
| Time/date/weekday | Display host clock | Immediately usable; remove any implication that these are placeholders. Configure/verify the host timezone if a specific household timezone is required. |
| Temperature/weather | WCS cached current observation | Data exists; add a bounded display projection and respect source/receipt time, units, errors and unknown state. |
| Forecast/UV | WCS cached daily and hourly forecasts | Data exists. Define which forecast text is wanted. Daily UV is a forecast for its valid day, not a current UV measurement. Do not show out-of-interval values as current. |
| Net worth/surplus/spent | Separate finance tracker referenced in README | No local finance adapter, display endpoint or verified contract found. Inspect the tracker API and definitions before connecting. Monthly spent and surplus need an explicit month/timezone and authoritative calculation. |
| Awareness dynamo | DIS and WCS component health; LTMS worker/store | DIS and WCS health exists at `/health`; no unified LTMS health in the display snapshot. Define membership and states, then project to display. A source failure can coexist with an old readable cache. |
| MQTT dynamo | DIS pump MQTT subscriber; display-power MQTT publisher | No broker-wide health endpoint exists. Pump subscriber connectivity is narrower than broker availability. Add an explicit bounded broker status source before asserting broker health. |
| IoT dynamo | DIS Kasa lights/coffee plug and passive plant-waterer telemetry | Structured device health/freshness exists. Other listed devices are inventory-only. Define which integrated devices count; never treat `not_integrated`, stale, or unknown as healthy or offline proof. |
| Interaction dynamo | Voice worker, text HTTP server, Discord integration | No common per-channel readiness/status contract found. Define active channels and heartbeat/health evidence before aggregating. |
| Fabrication suite | No implemented suite | Keep unimplemented/grey; do not report online. |

Suggested display contract for a later bounded implementation: versioned `display/state` projection with explicit `as_of`, per-member `online`/`error`/`offline`/`unknown` or `not_integrated`, and per-value timestamp/unit/availability. Aggregate green only when every configured member is verified working; red when any member has an error; grey when all configured members are verified offline or the suite is unimplemented. Unknown must remain distinct from offline. Show `ERR: <system>` for errored members. The current `Dynamo` widget only supports green/off and spins only for status `1`, so red support and subtext preservation require renderer changes.

Unresolved owner definitions: finance tracker endpoint and exact net-worth/monthly-surplus semantics; forecast wording and UV target day; which voice/text/Discord channels and IoT devices count as configured; how to distinguish an intentionally offline member from a malfunction; broker monitor authority. These are contract choices, not license to create placeholder integrations.

Stop condition: inspection only. Owner review is required before a bounded runtime hookup task.
