# World Context System (WCS), weather v1

> Current update (2026-11-19): hourly forecasts are now implemented. The same
> 15-minute request collects up to 48 hourly samples. Default summary budget is
> 2,400 characters; see the hourly extension below. Earlier validation/incident
> sections remain historical records.

> InfoPanel update (2026-11-26): the existing One Call request now includes its
> current UV index. WCS stores it as a separate current observation with its own
> provider observation and receipt times. The collection-version change schedules
> the upgraded source after restart while preserving prior observations. Display
> reads remain cached; UV updates on WCS's normal 15-minute poll.

Implemented 2026-11-19 following owner authorization. DIS v1 is considered done;
WCS is a separate information-only module. Its only active source is configured
local outdoor weather. No cameras, room sensors, presence, personal location,
user-plan ingestion, memory, notifications, reminders or action execution are
implemented or advertised.

## Shape and ownership

```text
registered source adapter -> validate timestamped observations
                                      |
                           shared SQLite transaction
                                      |
                         committed in-process cache
                            /                   \
                  owner-turn summary       HTTP/MCP reads
```

Like DIS, WCS starts and stops with the main Butler process. It has one background
source worker, not another service, container, server or database. MCP children
read the main process through the existing HTTP service; importing a provider
does not start collection. Network work runs outside database transactions and
the cache lock. A committed snapshot is published only after storage succeeds.
Conversation/model paths never open WCS storage or call its weather provider.
No new deterministic conversational response is added.

Migration 4 adds `wcs_sources` and `wcs_observations` to the shared `BUTLER_DB_PATH`;
migration 5 adds bounded `wcs_hourly_forecasts` latest-series rows.
Earlier migrations are unchanged. WCS owns those tables exclusively; clearing
conversation history preserves them and DIS records. This is a latest-observation
store, not a telemetry/event archive or semantic memory. Weather occupies two
overview slots: the latest observation and latest daily forecast for the configured
place, plus up to 48 separately bounded latest hourly samples.
A location/units/provider identity change clears only that source's old slots
and schedule so observations cannot be relabelled as a different location.

## Polling and API use

| Setting | Default | Meaning |
|---|---|---|
| `BUTLER_WCS_ENABLED` | `1` | Start the module with Butler |
| `BUTLER_WCS_SUMMARY_ENABLED` | `1` | Include context for full/owner turns |
| `BUTLER_WCS_WEATHER_POLL_SECONDS` | `900` | Home weather polling interval; owner selected 15 minutes |
| `BUTLER_WCS_SUMMARY_CHARS` | `2400` | Whole-record summary budget |

Uses existing `OPEN_WEATHER_API_KEY`, `BUTLER_WEATHER_LOCATION` and
`BUTLER_WEATHER_UNITS`. Supported units remain imperial, metric or standard.
Missing location/key reports `not_configured` without network calls. Settings
are read at startup; restart Butler/MCP children after changing them. Poll
interval bounds are 60–86,400 seconds and summary bounds 512–10,000 characters.

At the selected interval, there are approximately 96 scheduled polls/day. Each
successful poll calls current weather and One Call daily/hourly forecast separately,
approximately 192 endpoint requests/day, plus location resolution once per worker
lifetime when its first due poll runs. No request is made merely because a user
starts a conversation or reads cached weather. Resolution is cached in process.
This is not a universal account-wide API quota or a distributed multi-process
polling coordinator; run one main Butler owner, as with DIS.

The next poll is committed **before** network access and retained across process
restarts. An interrupted poll therefore waits until its reserved next slot.
Completed polls schedule the next interval from completion; fully failed
polls use persisted exponential backoff capped at six hours (never faster
than the configured interval). Partial daily-forecast failures keep current
weather on its normal schedule. There are no immediate request retries or model
refresh tools. Missing configuration requires correction and restart.

Requests have 3-second connection and 6-second read timeouts, no adapter-level
retries, and a 256 KiB response-size bound. These socket timeouts are not a hard
whole-operation deadline. Shutdown waits up to 45 seconds and reports an
incomplete stop if the source worker has not returned. A storage/worker failure
reports WCS unavailable rather than silently presenting a healthy empty cache.

`get_world_context(category='', offset=0, limit=8, forecast='overview', start_at='', end_at='')` reads cached observations,
source errors and schedule. `weather` is the only supported category. Unknown
categories return `not_found`; pages are at most eight observations and report
omission/next offset. `ok=true` means the cache was read successfully, **not**
that every source is available or every value describes the present.

The direct `get_current_weather` MCP route was removed on 2026-11-19 after
owner review. Weather now reaches the model through WCS summaries and the typed
`get_world_context` cached read tool only. Arbitrary other-city live weather
lookups are no longer an agent capability. Current-date/time tools remain.
The old internal weather formatting helper remains unregistered; WCS's adapter
continues using the existing API constants and location-normalization helpers.

Route-removal validation: 24 WCS, 5 retirement/catalog and 15 provider-selection
cases passed (44 deterministic). The four-scenario local-model fixture passed
one run with only the WCS read tool available. No API call or deployment restart
was performed for this cleanup. Restart Butler/MCP children to refresh catalogs.

## What the observations mean

An observation includes category, subject, provider source, evidence ID, kind,
provider observation/calculation timestamp, local receipt timestamp, units and
bounded measurements. The current-weather adapter exposes temperature, humidity,
available feels-like/pressure/wind/clouds and conditions. Humidity and temperature
are **outdoor weather**, not readings inside a room.

Daily forecast exposes high/low, available precipitation probability and daily
UV index. It is a forecast, not an actual measured high/low. Current API
`temp_min`/`temp_max` are spatial current ranges, so they are not used for daily
high/low. See [OpenWeather current-weather fields](https://openweathermap.org/api/current)
and [One Call 3 daily data](https://samples.openweathermap.org/api/one-call-3?collection=one_call_api_3.0).

Provider `daily.dt` identifies a target day; it is not an issue/observation time.
Forecast `observed_at` is therefore null, receipt time remains explicit, and
`valid_from`/`valid_until` delimit that local calendar day. The provider's IANA
timezone handles daylight-saving changes; if unavailable, an explicitly labelled
fixed UTC offset is used. No household timezone is silently substituted for a
different weather location. Only a forecast whose target matches the fetch day's
local date is accepted. An old saved forecast retains its original interval;
failed fetching does not turn yesterday's forecast into today's forecast.
At read time, `temporal_status` explicitly distinguishes observed data from
forecasts within/outside their interval. An out-of-interval forecast has empty
`values`, with its original numbers in `last_reported_values` for historical
retrieval. Routine summaries omit those historical numbers. This prevents old
high/low values from looking like today's forecast, without expiring observations.

There is no universal observation-expiry rule. Records retain their timestamps
and the model judges conversational relevance. Source failure retains prior
observations with explicit source errors; fetch time never replaces the provider
timestamp. Forecast date intervals are semantic boundaries, not arbitrary TTLs.
The existing current-date/time prompt accompanies WCS; its host-clock/timezone
limitations remain unchanged by this implementation. Source clocks are not
assumed perfectly synchronized.

## Access and context limits

Automatic summaries are included in both main agent turn paths only for full
access, consistent with DIS. Restricted callers receive none; tool access remains
subject to the existing allowlist. The new `/wcs/context` route uses the same
owner-token and loopback rules as DIS. Credentials, provider URLs, coordinates
and raw errors are excluded from model results. Summary text treats source strings
as data, not instructions. Full WCS tool results are preserved through result
shaping rather than truncated or summarized into ambiguous prose.

The summary has whole-record omission reporting; current conditions are preferred
before forecasts. It never dumps raw API responses. WCS currently accepts at most
eight registered sources and eight latest observation slots per source, 16
measurements per observation, bounded identifiers/text and finite numeric values.
No raw images, video or unrestricted payloads are stored.

## Adding a source later

Implement a small adapter with a stable category, configuration identity, its own
poll interval and a typed/validated `Batch` of `Observation` records. Register it
in the same module lifecycle and add source-specific configuration and tests.
Push-based sources need a separately scoped ingestion contract rather than a
dummy polling adapter. Add semantic fields such as track identity or interpretation
confidence when a real integration needs them; do not manufacture these for
weather or add placeholder camera services now. Version the contract/migration
when necessary. Shared storage, source scheduling, cache, pagination and owner
summary delivery can be reused without merging WCS with DIS.

Vision interpretation belongs in the vision source; WCS would store its bounded
observations. Notification decisions belong in future Proactivity. Durable
preferences/history belong in Memory. Device connectivity/control remains outside
WCS. Future heavy-rate sources must be measured before using this latest-slot
polling implementation as an event-ingestion system.

## Validation and stop condition

Validation commands and final counts are recorded in the 2026-11-19 session log.
Tests cover cache-only turns, owner/restricted injection, source failures and
partial results, restart/crash scheduling, backoff, time/units, forecast target
dates/DST, bounds, shared-DB migration/ownership, HTTP/MCP schemas and existing
DIS/runtime behavior. The opt-in local-model fixture is:

```powershell
$env:BUTLER_WCS_LIVE_MODEL_TEST='1'
.venv-main/Scripts/python.exe -m unittest discover -s tests -p test_wcs_model_acceptance.py
```

It uses simulated weather and no control tools. Three consecutive final four-question runs passed:
outdoor temperature, no invented indoor humidity, expired forecast rejected for
today, and unavailable WCS handled without copying historical temperature. This
is a bounded model-behavior sample, not a guarantee of all future replies.

A single real weather poll reached both endpoints and produced validated current
and daily records. It wrote only temporary SQLite and did not start a continuous
poller. Fetch took about 0.57 seconds; cached summary formatting averaged about
0.038 ms over 1,000 calls on this host (not inference/end-to-end latency). Before the final cache-only guidance sentence was added, the
observed summary was 1,665 characters, within its 2,200-character budget.

Stop at weather WCS v1. No camera/presence/location integration, indoor adapter,
plan extraction, memory, notification/rule engine, firmware change or deployment
restart is part of this assignment.


Deterministic validation (123 cases passed):

| Discovery pattern | Cases |
|---|---:|
| `test_wcs.py` | 24 |
| `test_unified_storage.py` | 12 |
| `test_home_automation_weather.py` | 3 |
| `test_mcp_disable_selection.py` | 15 |
| `test_dis.py` | 19 |
| `test_dis_pump.py` | 7 |
| `test_run_command_stream.py` | 17 |
| `test_tool_access.py` | 9 |
| `test_awareness_retirement.py` | 5 |
| `test_agent_runtime_recovery.py` | 12 |

Run each with `.venv-main/Scripts/python.exe -m unittest discover -s tests -p PATTERN`.
Socket-based fixtures required execution outside the restricted socket sandbox.
Compilation and whitespace checks passed. The existing audioop deprecation warning
remains visible. Full repository tests, launcher GUI/voice acceptance, continuous
soak and deployment restart were not run.

An initial local-model pass was followed by intermittent failures on unavailable
context and expired forecast. One unavailable-case failure exposed a fixture bug:
its read tool bypassed service availability. The fixture was corrected to use the
real service interface. The expired-forecast failure exposed a real projection
weakness; separate historical values and temporal status fixed it. Acceptance
assertions were not weakened. Final four-scenario acceptance passed three runs
(12 question scenarios). The model can still make unnecessary offers to fetch
information; no such offer performs an API request or guarantees reply reliability.


## Daily-high/hourly-answer correction (2026-11-19)

A saved owner conversation reproduced an unsupported forecast: the model first
correctly reported current 44.24 F and daily high 68.22 F, then reused 68.22 F
when asked about both 8 a.m. and 9 a.m. The persisted WCS records correctly
separated those values. The daily API high was not an hourly forecast, and WCS
excludes hourly data. No same-time external 38 F reading was independently
verified; the evidence establishes a model interpretation error, not an API
claim that 8 a.m. would be 68 F.

Summary and read-tool descriptions now explicitly prohibit using daily extrema
or current observations as specific-hour forecasts. The model must report hourly
information unavailable. The real-model fixture reproduces the exact sequence
with realistic current/daily Fahrenheit data and both hourly questions; it now
has seven scenarios. No hourly endpoint, extra polling or deterministic response
was added. A later hourly integration requires a separate bounded assignment.


## Hourly extension (2026-11-19)

Owner authorized hourly forecasts. Removed hourly from the existing One Call
request's exclude parameter; polling remains 900 seconds and request count is
unchanged. No direct weather tool, additional process, model call or deterministic
chat reply is added. Hourly forecasts include temperature, optional conditions
and precipitation probability in percent, at up to 48 consecutive hourly targets.
Raw provider issue time is still unknown; receipt time is recorded separately.
Malformed/missing hourly data reports a partial source error and preserves the
previous series. Daily parsing failures do not discard valid hourly data.

Migration 5 owns `wcs_hourly_forecasts` under WCS with a category/target-time key.
A successful replacement transaction deletes/replaces only that source's bounded
series. Failed writes roll back the deletion and inserts. Configuration identity
changes cascade-delete old hourly data along with the old source. No unbounded
forecast history or source-slot-limit increase is introduced.

`get_world_context(forecast='hourly', start_at='2026-11-19T08:00:00-05:00')`
selects the cached hour bucket overlapping that one-hour interval. An optional
end_at selects a range up to 48 hours. Both timestamps require an explicit UTC
offset; end without start, zero/reversed ranges and naive dates are rejected.
No time range defaults to upcoming 48 hours. Pages remain at most eight records;
coverage and forecast_window report pagination and available cache horizon.
Outside coverage means unavailable, not an interpolated daily high/low. Tool
reads never poll the API. Default overview reads continue returning current/daily
records only, so existing overview pages are not buried by 48 forecast records.

Hourly records identify resolution='hourly', forecast_at (ISO timestamp with
offset), valid_from/valid_until (UTC), and timezone. The hourly value predicts
conditions at its target; the one-hour bucket is for selection, not a promise
that weather is constant or an interpolation to a different minute. Future
hourly values remain available as future_forecast; expired values are historical
and separate. IANA zones distinguish the repeated fall-back hour; explicitly
labelled fixed offsets remain supported. Daily extrema remain separate.

The automatic summary now compactly groups temperature and available precipitation
by full local date and UTC offset, with explicit column names/units and missing
values left unknown. Common weather data plus all 48 paired points fit the default
2,400-character budget in the tested realistic fixture. Smaller budgets/longer
text may omit whole points with coverage counts; the read tool retrieves detail.
Temperature preview rounds to two decimal places; full read results preserve the
stored numeric values. Current conditions/essential daily fields remain automatic;
pressure, wind, feels-like, UV, hourly descriptions and other details remain in
structured reads. Source status/errors and last success are preserved in the
summary; full scheduling/evidence metadata remains in read results.

Validation: 72 deterministic cases passed across test_wcs_hourly.py (12),
test_wcs.py (24), test_unified_storage.py (12), test_dis.py (19) and
 test_awareness_retirement.py (5). A real one-poll check returned 48 hourly records
from the configured provider without any extra endpoint request, using temporary
storage. Compilation/whitespace checks passed. Final model validation uses the
actual tool schema and tests current weather, absent indoor data, expired daily
forecast, missing hourly coverage, exact 8/9 a.m. temperatures, next-day/date
matching, hourly precipitation and WCS unavailable. Initial model runs confused
partial previews or daily precipitation with requested hours; compact date-grouped
temperature/precipitation context and explicit full-date/metric matching corrected
those cases without weakening assertions. Full suite, continuous soak and production
restart were not run. Restart Butler/MCP children to apply migration and schemas;
existing reserved schedules remain, so first hourly data arrives at the next poll.


## Hourly upgrade bootstrap correction (2026-11-19)

A real request at 01:27 local time was captured with the updated WCS summary but
zero cached hourly samples. Source health was ready from the old 01:17 poll,
with the next poll reserved for 01:32. Saved current/daily records lacked the
hourly collector's resolution fields. The model answered 68 F at 9 a.m. anyway:
68.22 F was only the daily high. Clearing conversation/memory did not affect the
separate WCS source schedule or observations. This was not a new hourly API value.

The hourly collector now declares collection_version=2 in source configuration.
On a collection-version-only upgrade, registration preserves current/daily/source
evidence but invalidates the old collector's next-poll reservation and marks the
source unknown until the new poll finishes. This triggers immediate background
collection once; unchanged-version restarts preserve schedules and failure
backoff. Location/units/provider identity changes still clear the mismatched
source's data. No new DB migration, prompt-path API request, direct reply or
routine forced polling is added. The current process continues its existing poll;
updated upgrade handling is loaded on restart.

Regression validation: 14 hourly and 24 WCS cases passed (38 deterministic),
including the exact pre-upgrade-data/future-schedule scenario and unchanged-version
failure backoff. Compilation/whitespace passed. No new local-model acceptance or
full suite was run for this source-registration fix. Exact request logs were used
to diagnose the actual failed answer; the model ignored missing coverage, so this
fix addresses collection startup rather than guaranteeing all future model replies.


Observed running-service confirmation: its existing scheduled poll completed at
01:32:13 America/New_York and the cached November 19 09:00 -05:00 target became
52.18 F. This was read through the owner HTTP cache endpoint, not a forced source
refresh. A single direct-geocoder check confirmed configured Baltimore,US resolves
to Baltimore, Maryland (39.2908816,-76.610759). Thus 68 F was unsupported reuse of
the daily high; the remaining 52.18 versus user-expected approximately 45 F is not
explained by this startup bug and was not independently verified against the
user's external forecast source. No running Butler process was restarted.
