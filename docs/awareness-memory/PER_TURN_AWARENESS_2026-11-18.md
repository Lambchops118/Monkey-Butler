# Per-turn awareness investigation — 2026-11-18

Scope: source inspection of the current shared conversation engine and light integration. No runtime change, live model request, device query, or physical action.

## Findings

The shared engine in `butler/agent/runtime.py:run_command_stream` assembles persona and modality/domain instructions, optional SQLite prompt memory (full-access callers), a supplied household situation snapshot, bounded conversation history including preserved tool exchanges, history-grounding instructions, current time, the user message, and available tool schemas. Conditional KiCad/Minecraft context and extra runtime/job context can also be included. Defaults are 32 history messages / 16,000 characters and 1,600 characters of prompt memory; configuration can override these. Awareness long-term memory is available through `search_memory`, rather than automatically being injected as the SQLite prompt-memory block.

Router requests and HTTP streaming both obtain the awareness snapshot through `snapshot_with_fallback`. The client enables situation fetching by default, caches it for five seconds, and falls back to the caller's legacy snapshot if disabled/unavailable. This does not poll every physical device per turn. The situation broker selects database facts by priority under its budget: critical alerts, other alerts, presence, attention, state, transitions, and source health. Inclusion is bounded, so even a tracked device is not guaranteed a line. The runtime has a 4,000-character default backstop.

The smart-plug provider exposes only `list_smart_plugs` and `set_smart_plug`. Its schema includes configured device IDs; listing returns configuration (ID/name/host), not current power. Setting accepts only `on` or `off`, with `all` selecting lights and excluding appliances. No toggle or light-status tool is registered there.

The service connects and refreshes device data internally before setting power, but does not return that prior state to the model, branch on it to implement toggle, or perform a post-command state read. Its success text therefore represents a completed control API call, not independent verification of the final relay state. No Kasa/light-state ingestion path was found in the inspected awareness code. Generic `get_current_state(entity_id)` reads awareness database observations; it does not discover or poll a Kasa switch on demand. A separately configured external producer could supply light observations, but that was not verified against the running deployment.

Consequently, “turn the lights on/off” is implementable with the existing setter without knowing their previous state. “Toggle the lights” requires current state, which this integration does not expose to the model. Old tool history can provide a past command outcome, not trustworthy present state after wall-switch use or another controller.

## Evidence

- `butler/agent/runtime.py`: prompt constants, `_get_prompt_memory`, `_format_context`, `_history_grounding_notice`, `_build_tool_definitions`, `run_command_stream`.
- `butler/agent/prompting.py`: `PromptAssembler.build_sections`.
- `butler/router.py`: voice/text snapshot assembly.
- `butler/text/server.py`: `_stream_state_snapshot`.
- `butler/services/awareness_client.py`: situation fetch/cache/fallback.
- `butler/awareness/context/broker.py`: priority and budget selection.
- `butler/mcp_servers/providers/awareness.py`: structured state/history/health/memory tools.
- `butler/mcp_servers/providers/smart_plugs.py` and `butler/services/smart_plugs.py`: available light tools and actual device operations.

## Verification and stop

Source inspection only; no tests run because executable behavior was unchanged. Running prompt contents, deployed process revision, device availability, and any external database producers were not verified. Existing unrelated working-tree changes were preserved. Stop at investigation; implementing light-state retrieval, toggle semantics, or awareness ingestion requires a separate bounded assignment and the tool implementation guide.

## Follow-up: actual snapshot behavior (2026-11-18)

### Live checks

Read-only loopback probes reached the awareness HTTP service at port 8600. `/situation` returned HTTP 500 twice; `/state/quad_pump` returned HTTP 500; `/capabilities` returned HTTP 200 and explicitly reported database-backed reads/actions as `degraded: database unreachable`. `/health` and `/health/components` each exceeded a five-second timeout. `docker ps -a` could not reach the configured Docker Desktop Linux engine because its named pipe did not exist. The repository compose file places the awareness database in that engine (`talos-awareness-db`, loopback 5433). This is consistent with the current database outage; no service was restarted and no data was changed. The underlying reason Docker is unavailable was not established.

### Saved actual model inputs

Inspected only the five newest `butler/logs/llm_io_*.jsonl` files, directly relevant to proving injection. Counts below are model request records with `messages`, including follow-up inference rounds, not distinct user turns. The dates in filenames are UTC; November 19 00:29/00:32 UTC is November 18 evening in the owner's timezone.

| Input record file suffix | Model requests | With snapshot | With non-owner STATE lines |
|---|---:|---:|---:|
| 20261119T003236_33604 | 2 | 0 | 0 |
| 20261119T002956_21168 | 10 | 0 | 0 |
| 20261116T054125_20540 | 8 | 7 | 0 |
| 20261115T231300_21400 | 52 | 51 | 19 |
| 20261114T194615_27572 | 54 | 53 | 47 |

Thus the injection HAS worked: 111 of these 126 model requests contain an actual `Context (read-only): Situation as of ...` system message. That does not establish useful complete device awareness. All 12 records in today's two newest files lack the snapshot entirely, consistent with the live database failure and fallback behavior. Three other records lack it too; their cause was not established.

Snapshots in the three older files were approximately 2,073–2,162 characters. A character-based extraction of announcement sections gave average shares of approximately 65%, 71%, and 73% across those files. Those are approximate text shares, not tokenizer measurements. Included content was primarily up to three historical voice-announcement receipts (morning weather/reminders and pump-offline announcements), presence/interaction data, and the following device fields across the sample:

- `quad_pump.pin_17 = False`, explicitly stale and last received August 30 (a legacy source).
- `quad_pump.fuse_1`, `fuse_2`, `fuse_3 = 'unknown'`, with current/offline qualifications depending on the request.

No light-power STATE field appeared. No canonical pump relay/running property appeared in these sampled snapshot messages. The seven injected snapshots in the November 16 05:41 run contained only owner.detail/owner.modality STATE fields plus an offline alert and historical announcements. This is evidence of poor selected device coverage, not evidence that those other properties were absent from the database. No `get_current_state` or `get_system_health` tool call appeared in the sampled messages' structured tool-call history; other tools including light setting and action requests did appear. This does not establish that the model never uses state tools outside this bounded sample.

### Why useful state is displaced even when the backend works

1. The broker's default budget is 600 estimated tokens. Announcement receipts use priority 3 (presence), ahead of device state (5), transitions (6), and source health (7). Each of up to three receipts can include 800 characters of prose plus identifiers and caution text and remains eligible for 24 hours. They repeatedly occupy most of the budget.
2. Device-state candidate collection fetches only the latest 20 property rows globally, rather than 20 devices or a selected set of useful properties per device. High-frequency publishers/many properties can consume candidate slots before budget selection.
3. Within equal priority/relevance, selection sorts by item ID, not usefulness or recency. `state:owner.*` and `state:quad_pump.fuse_*` precede other pump properties lexically. Unknown/stale properties remain candidates and consume budget.
4. The normal automatic fetch does not pass the current command or an entity filter. The broker supports an entity filter, but the automatic client fetch uses only an optional budget. Attention relevance uses entities in recent interaction/agent events, not a fresh resolution of the current question. Device STATE items themselves are not given request-specific relevance.
5. The client passes only `as_of` and rendered `text`; `audit`, `truncated`, `limitations`, and the structured presence summary are not automatically sent to the model. On fetch failure it returns the legacy snapshot without an explicit awareness-unavailable notice. If legacy status is empty (`no recent status`), runtime omits the context message entirely. The newest saved requests demonstrate the resulting missing context.
6. The snapshot only covers ingested sources. Known seeded entities include fan, plant-waterer/pots, simulator, owner, and agent. Existing Kasa light control is not a state-ingestion adapter.

### Historical evidence and limits

The July 17 session record documents restoring missing `/chat/stream` awareness injection. The current `_format_context` implementation documents a later measured failure: the former 500-character runtime cutoff discarded 1,559 of a 2,059-character snapshot, including state/health/transitions. Current code uses a default 4,000-character backstop, and the saved November inputs above demonstrate snapshots exceeding 2,000 characters reaching the model. That cutoff repair is therefore present in actual captured inputs; it did not solve the broker's allocation/coverage problem. These historical records establish earlier failures and repairs, not uninterrupted operation since then.

### Verification

- `.venv-awareness/Scripts/python.exe -m unittest discover -s tests -p test_awareness_context_unit.py -q`: 4 passed.
- `.venv-runtime/Scripts/python.exe -m unittest discover -s tests -p test_awareness_client_and_provider.py -q` with loopback allowed: 8 passed.
- Initial module-style unittest invocation failed to import both `tests.*` modules (test discovery corrected this).
- Context-unit discovery under runtime venv skipped the module for missing awareness dependencies; rerun in awareness venv passed.
- Sandboxed client/provider run stalled on its local HTTP fixture and was interrupted; the socket-enabled rerun passed.
- No database integration suite, new model inference, physical action, restart, or deployment ran. Existing unit/client tests validate mechanics with fixtures, not current database availability or household coverage.

### Recommended bounded follow-ups (not implemented)

Restore/diagnose the local database service first. Then repair snapshot allocation: compact historical announcement receipts, reserve space for representative device state, select useful properties with explicit unknown/stale treatment, and carry degradation/truncation information into model context. Add light observations/read tools through the tool contract and physical-action rules if lights are expected to participate. Verify with captured prompt assertions for representative household questions and real observed state. The present investigation stops here; no runtime repair or later phase is started.
