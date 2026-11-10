# Model interaction surface rework — 2026-11-10

**Status:** architecture proposal for review. This document changes no runtime code or deployment setting.

## Goal

Butler should have one coherent way to process a user turn, regardless of whether it arrives from voice, browser, terminal, SMS, or another client. Streaming versus waiting for a complete reply should be a **delivery choice**. It should not silently select a different model, tool loop, memory/history behavior, job router, or safety policy. Local inference remains the default; a hosted model is used only when explicitly selected for that task or debugging.

This plan complements [the foreground/background proposal](background_rework_11102026.md). It does not authorize that proposal's runtime implementation or a later awareness phase.

## Current paths and discrepancies

| Ingress | Current path | Consequence |
|---|---|---|
| Voice worker | `stream_message` → `POST /chat/stream` → `run_command_stream` | Uses the configured OpenAI-compatible backend, normally local Ollama. Streams deltas and supports request cancellation/telemetry, but bypasses the router's job classification and current job context. |
| Browser page at `/` | `POST /chat` → central queue/router → `run_command` | Waits for a complete JSON response. The agent turn uses the hosted OpenAI Responses client even when the launcher is set to local Ollama. |
| Terminal client | `send_message_payload` → `POST /chat` → same router/runtime path | Interactive `butler>` prompt exists, but ordinary local-only chat can fail on a missing/placeholder OpenAI key. The client's `/jobs` and `/job` read the job store. |
| SMS webhook | `text_cmd` on central queue → same router/runtime path | Uses the nonstreaming path and therefore inherits its hosted dependency. SMS delivery has separate external-service requirements. |
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

- `TurnRequest`: stable request/session/source identifiers, user content, modality and presentation preference, explicit execution preference if supplied, authorized capabilities, and correlation metadata. The server derives trusted identity and permissions; clients cannot grant themselves tools by sending fields.
- `TurnEvent`: typed start, text delta, tool call/result reference, job acceptance/progress, terminal success/failure/cancelled/interrupted, and telemetry. Clients see only bounded, appropriate fields. Persist actual tool call/result pairs and their used schemas.
- `TurnResult`: a collected projection of the same event stream, with `ok`, execution mode, provider/model actually used, response text, job/action IDs, authoritative outcome state, and structured error. A queued job or action is not reported as completed.
- Provider policy: local endpoint by default for every modality and execution lane. Hosted use requires an explicit choice; never infer permission from an OpenAI-compatible URL or an available API key. Model/backend unavailability must surface as a failure or degraded capability, without a silent remote fallback.
- Status questions: bounded structured retrieval of current job/action state before model phrasing. The stream and JSON views must see the same facts and authorization rules.

No ordinary spoken reply needs a canned sentence. Deterministic code can validate intent and outcomes while local Qwen phrases acknowledgement and completion. Critical alerts still retain the existing deterministic fallback when the model is unavailable.

## Migration in bounded steps

1. **Characterize behavior.** Add a small cross-channel contract matrix that exercises the same request through `/chat`, `/chat/stream`, terminal, browser, and SMS adapters with fake local and hosted backends. Record current provider calls, tool history, context, cancellation, job IDs, and errors. Establish a baseline before changing routing.
2. **Select one canonical agent loop.** Prefer the current local streaming loop as the basis because voice already depends on its incremental output and recent structured tool-history repair. Extract only the common turn logic needed for both delivery modes. Preserve prompt caching, Qwen think/no-think handling, tool scoping, paired call/results, safety checks, and barge-in cancellation. Do not merely make `/chat` concatenate raw SSE text while leaving the old policy split in place.
3. **Unify provider policy.** Make the foreground, status, and background paths use the same explicit model configuration and local-first rule. Keep optional hosted debugging/delegation as a named, visible selection. Remove the implicit hosted dependency from `/chat`, SMS, route classification, and current background execution.
4. **Unify routing and context.** Let the streaming handler reach the same job/status controller as nonstreaming clients. Replace the `voice` interaction-mode hardcode with a validated mode derived from the ingress. Pass consistent awareness, session, job, and action context through one bounded builder. Keep the voice latency budget and emergency/safety path intact.
5. **Move clients without breaking them.** Update terminal and browser clients to show streaming text and typed job events, with a collected-response option for simple scripts and SMS. Retain compatibility for existing `/chat` callers until they are migrated; document any deliberate API changes before removing an endpoint.
6. **Verify on the deployed host.** Exercise Mac headless text chat, local Linux voice/terminal/browser/SMS paths, hosted opt-in debug mode, background progress, interruption, and physical-action status. Measure first useful response and confirm that normal text chat cannot quietly leave the local network.

This order is a proposal. Each implementation step should be separately bounded, tested, and reviewed under the repository phase rules.

## Acceptance checks

- With hosted mode off, browser and terminal text chat, voice streaming, and SMS all call the configured **local** model. An unavailable local endpoint yields a truthful error; no channel switches to OpenAI.
- The same request has the same routing, permissions, relevant context, tool schemas, paired tool history, and outcome across stream and JSON presentations. Wording may differ because generation is nondeterministic.
- Voice and browser receive incremental text. Terminal can converse interactively. SMS receives a complete reply or an explicit job receipt and later delivery policy. All clients can inspect job state without guessing.
- Cancellation stops the relevant inference/stream and preserves completed tool effects in history. Cancelling speech, inference, a job, and a dispatched physical action remain distinct outcomes.
- A hosted debug request is visibly attributed to its actual provider and is permitted only by explicit selection. The server logs or records the provider choice without logging secrets.
- Registered physical actions retain schema validation, authorization, configured confirmation, idempotency, acknowledgement, timeouts, and transition audit. No transport adapter can bypass them.

## Open design choices

- Whether the final public API is one endpoint with negotiated stream/JSON delivery or two thin endpoints over one controller. Either is acceptable if behavior is identical.
- How the existing terminal and browser clients display asynchronous job completion and whether SMS sends a separate follow-up.
- Which nonvoice channels should default to streaming once the canonical path is available, and how to present partial output before an eventual tool or model error.
- How to expose an explicit hosted-debug selection without making it an accidental global fallback.

**Stop point:** documentation only. No route, client, model policy, or runtime loop has been changed.
