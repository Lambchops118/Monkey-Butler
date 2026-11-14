# Model interaction surface rework — 2026-11-10

**Status (2026-11-14):** Shared turn engine and owner conversation implemented. Live adapter verification remains pending. This communication layer precedes the background rework.

## Goal

Butler should feel like one continuous conversation across ReSpeaker, Discord, iMessage, and the other supported channels. Assume one person interacts with Butler at a time. Streaming and collected replies are delivery choices over the same turn engine. Local inference is the default. The explicit launcher hosted-debug setting switches all participating turns to the hosted backend while enabled. Provider failures surface as errors, with no automatic fallback in either mode.

Include existing non-phone channels. Defer inbound ElevenLabs calls. Browser and terminal are low priority and should not block migration of the main channels. The browser UI can be dropped if it becomes a blocker. Preserve the HTTP contracts used by other adapters regardless of the browser UI decision.

This plan complements [the foreground/background proposal](background_rework_11102026.md). It does not authorize that proposal's runtime implementation or a later awareness phase.

## Paths before the migration

| Ingress | Current path | Consequence |
|---|---|---|
| Voice worker | `stream_message` → `POST /chat/stream` → `run_command_stream` | Uses the configured OpenAI-compatible backend, normally local Ollama. Streams deltas and supports request cancellation/telemetry, but bypasses the router's job classification and current job context. |
| Browser page at `/` | `POST /chat` → central queue/router → `run_command` | Waits for a complete JSON response. The agent turn uses the hosted OpenAI Responses client even when the launcher is set to local Ollama. |
| Terminal client | `send_message_payload` → `POST /chat` → same router/runtime path | Interactive `butler>` prompt exists, but ordinary local-only chat can fail on a missing/placeholder OpenAI key. The client's `/jobs` and `/job` read the job store. |
| SMS webhook | `text_cmd` on central queue → same router/runtime path | Uses the nonstreaming path and therefore inherits its hosted dependency. The owner is unsure whether SMS is enabled on the deployed host or accepts other senders. Verify both before mapping any SMS caller to the shared owner conversation. |
| Discord | Separate sibling checkout, `Discord-Voice-Frontend`. Its Python brain bridge calls Talos `/chat/stream` and `/chat`, forwarding the session, source, and privilege information. | The client can fall back to `/chat` when streaming is unavailable or produces no text. Empty output can occur after a turn starts. Migration must avoid replaying a turn or its tool effects. |
| iMessage | An Apple Shortcut on an older iPhone forwards only the owner's messages. It uses **Get Contents of URL** to reach Talos over Tailscale at HTTPS port `8443`, path `/chat`, sending JSON fields `message`, `session_id`, and `source`. | Talos handles `/chat` as a POST route. Verify the Shortcut's configured method, authentication, and response handling during adapter characterization. Preserve the existing payload contract. |
| Background job | router → `JobManager` → `run_command` | Persists a job, but executes through the hosted Responses loop today. |

Relevant code: [`butler/text/server.py`](butler/text/server.py), [`butler/text/service_client.py`](butler/text/service_client.py), [`butler/text/client.py`](butler/text/client.py), [`butler/router.py`](butler/router.py), [`butler/agent/runtime.py`](butler/agent/runtime.py), and [`butler/jobs.py`](butler/jobs.py).

The launcher’s “hosted API models” switch overrides the **streaming backend** configuration for main/voice processes and skips Ollama, but `run_command` and the route classifier already use the hosted Responses client directly. Thus the switch does not consistently govern all ingress paths. The `/chat/stream` handler also hardcodes `interaction_mode="voice"`, even when a nonvoice client supplies a different `source`. The text client and browser cannot obtain the local streaming path through their normal UI.

The two runtime loops have accumulated different handling for prompts, tool calls/results, conversation persistence, status/job context, cancellation, and telemetry. Some details have existing tests, but parity must be established with behavioral checks, not assumed from shared helper names. The prior local streaming tool-history repair explicitly covered `run_command_stream`; the legacy Responses loop was unchanged.

## Target shape: one turn, multiple presentations

```text
voice / browser / terminal / SMS / API
                 │
                 ▼
        normalized TurnRequest
        session, source, request ID,
        requested mode, permissions
                 │
                 ▼
    one controller and turn engine
    route → context → model → tools → evidence
                 │
       structured TurnEvents
       ├─ stream as events/SSE to voice or browser
       └─ collect to one JSON reply for SMS or simple callers
```

The controller should own routing, durable job submission and status retrieval, model/provider policy, cancellation, action boundaries, and outcomes. The turn engine should own one prompt/history/tool-call implementation. A backend adapter can use local Ollama or an explicitly selected hosted provider without changing those semantics. Keep the wire endpoints needed by existing clients during migration; flatten their **behavior** first, then simplify the public API when clients have moved. A single endpoint with optional streaming is possible, but not required to remove the dangerous split.

### Proposed contracts

- `TurnRequest`: stable request and source identifiers, server-resolved conversation identity, user content, modality and presentation preference, explicit execution preference if supplied, authorized capabilities, and correlation metadata. The server resolves identity and permissions from the trusted ingress.
- `TurnEvent`: typed start, text delta, tool call/result reference, job acceptance/progress, terminal success/failure/cancelled/interrupted, and telemetry. Clients see only bounded, appropriate fields. Persist actual tool call/result pairs and their used schemas.
- `TurnResult`: a collected projection of the same event stream, with `ok`, execution mode, provider/model actually used, response text, job/action IDs, authoritative outcome state, and structured error. A queued job or action is not reported as completed.
- Provider policy: one explicit launcher mode for every participating modality and execution lane. Hosted debug routes new turns and model-based routing through the configured hosted backend, and local mode routes them through the configured local backend. Record the actual provider and model per turn. A credential or URL alone does not enable hosted mode.
- Hosted debug history: start a fresh shared conversation when hosted debug is enabled. Exclude existing conversation history and any summaries derived from it from hosted requests. Turns during the debug session can use history created within that session across participating channels. Saved memory and live household context follow the normal context and permission rules. Keep the local conversation available to resume when local mode returns.
- Status questions: bounded structured retrieval of current job/action state before model phrasing. The stream and JSON views must see the same facts and authorization rules.

No ordinary spoken reply needs a canned sentence. Deterministic code can validate intent and outcomes while local Qwen phrases acknowledgement and completion. Critical alerts still retain the existing deterministic fallback when the model is unavailable.

### Shared owner conversation

Resolve trusted ReSpeaker input directly to the owner's conversation without speaker verification. Resolve authorized Discord, iMessage, and other owner inputs to that same conversation so follow-ups work immediately across channels. Keep channel and destination metadata for reply delivery. Preserve Discord's existing privilege boundary. Restricted or unrecognized callers cannot read or append to owner context, and a client-supplied session ID cannot grant access. Verify how each remote adapter identifies the owner before mapping it to shared history.

## Migration in bounded steps

1. **Characterize behavior.** Exercise ReSpeaker, Discord, iMessage, and SMS through their existing entry points with fake model backends where practical. Confirm the live iMessage Shortcut contract and Discord retry behavior. Cover browser and terminal opportunistically. Record provider selection, identity, history, tool permissions, cancellation, and errors before changing routing.
2. **Select one canonical agent loop.** Prefer the current local streaming loop as the basis because voice already depends on its incremental output and recent structured tool-history repair. Extract only the common turn logic needed for both delivery modes. Preserve prompt caching, Qwen think/no-think handling, tool scoping, paired call/results, safety checks, and barge-in cancellation. Do not merely make `/chat` concatenate raw SSE text while leaving the old policy split in place.
3. **Unify provider policy.** Apply the launcher mode to the shared turn engine and routing decisions. Remove implicit hosted execution from participating paths. Keep existing-job execution within that policy wherever it is retained. Automatic background routing, the worker redesign, and proactive job delivery belong to the later background plan.
4. **Unify routing and context.** Resolve the owner's shared conversation on the server and derive modality from the trusted adapter. Pass bounded context through one path. Preserve voice barge-in, permissions, and the emergency and physical-action paths.
5. **Keep adapter delivery compatible.** Preserve Discord and ReSpeaker streaming and existing collected replies for messaging clients. Closing the terminal stops display while an accepted turn continues. An explicit cancellation still targets the relevant operation. Defer browser and terminal improvements that would block the primary channels.
6. **Verify on the deployed host.** Check cross-channel follow-ups, local and hosted modes, ReSpeaker interruption, and physical-action status. Validate the iMessage Shortcut through its actual Tailscale path and Discord through its frontend.

This order is a proposal. Each implementation step should be separately bounded, tested, and reviewed under the repository phase rules.

## Acceptance checks

- All migrated channels use the configured local model in local mode and the configured hosted model in hosted-debug mode. Provider outages surface as errors.
- The first hosted request after enabling debug contains no prior conversation history or derived summaries. Later debug turns can continue that debug conversation across channels. Switching back resumes the local conversation.
- A follow-up on ReSpeaker can use the immediately preceding authorized Discord exchange, and the reverse works too. Restricted callers cannot access that shared conversation.
- The same request has the same routing, permissions, relevant context, tool schemas, paired tool history, and outcome across stream and JSON presentations. Wording may differ because generation is nondeterministic.
- ReSpeaker and Discord retain incremental delivery. Messaging adapters can consume collected replies. Disconnecting the terminal leaves an accepted turn running.
- Cancellation stops the relevant inference/stream and preserves completed tool effects in history. Cancelling speech, inference, a job, and a dispatched physical action remain distinct outcomes.
- The launcher makes hosted debug mode visible. The server records the actual provider without logging secrets.
- Registered physical actions retain schema validation, authorization, configured confirmation, idempotency, acknowledgement, timeouts, and transition audit. No transport adapter can bypass them.

## Open design choices

- Whether the final public API is one endpoint with negotiated stream/JSON delivery or two thin endpoints over one controller. Either is acceptable if behavior is identical.
- Confirm iMessage authentication and whether SMS is enabled and accepts other senders on the deployed host.

## Implementation notes

- `/chat` and `/chat/stream` retain their existing wire formats. Both use the streaming engine and shared owner history. Existing explicit background mode is available through either endpoint. Automatic routing to background work is deferred.
- Loopback clients are trusted for the household path. Remote HTTP turns require the configured API token to reach owner history, and external adapters such as Discord also need their existing privilege proof. A verified SMS webhook with one allowlisted sender treats that sender as the owner. With multiple senders, set `BUTLER_SMS_OWNER_SENDER` to identify the owner explicitly.
- Disconnecting a delivery client leaves an accepted turn running. HTTP adapters can supply a stable `request_id` to reject a duplicate within the process's recent-request window. The Discord client reports a broken stream without replaying it after HTTP acceptance. Voice barge-in targets the interrupted request's stored reply.
- Hosted debug uses a fresh history namespace for each launcher run. Local conversation history resumes after restarting in local mode. Existing pre-migration histories remain stored under their original session IDs.
- The ElevenLabs phone handler preserves its legacy turn path. Live ReSpeaker, Discord, iMessage/Tailscale, SMS, and provider checks remain deployment verification items.

## Verification

- The combined Talos regression run executed 187 cases with 176 passing, 10 skipped, and one Windows loopback connection abort in the notification authorization test. That test passed on rerun with the shared-session and interrupt cases (8 passed).
- The final focused engine, memory, provider, text handler, and interruption suite passed 69 cases. Discord client access tests passed both cases. Diff whitespace checks passed in both checkouts.
- No live device, provider, or physical-action deployment checks were performed.

**Stop point:** Communication-layer implementation only. Background reasoning and worker changes await a separate assignment.
