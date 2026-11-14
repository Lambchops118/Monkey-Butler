# Foreground and background rework — 2026-11-10

**Status:** design proposal for owner review. No runtime behavior is changed by this document.

## Goal and constraints

Talos runs on a local Linux host with an RTX 5080, a ReSpeaker and speaker setup, local Qwen, and a local voice model. Development may happen on a Mac or Windows computer, but the integrated voice and hardware path ultimately needs testing on that Linux host.

The desired interaction is: **respond promptly, perform the task, then acknowledge verified success or failure**. The foreground must remain usable for normal conversation while a background task runs. It must be able to answer a question such as “How is the error analysis going?” immediately from current job state. Inference stays local unless the owner explicitly opts into a hosted call. A spare A2000 12 GB is available if isolation on the 5080 is inadequate.

For ordinary dialogue, acknowledgements and follow-ups should be worded by local Qwen, not selected from canned response strings. Code still owns routing, job state, safety, retries, and evidence. Critical alerts and safety behavior must remain available without an LLM, as required by the existing awareness architecture.

## What exists today

- The usual voice stream uses `POST /chat/stream` in `butler/text/server.py`, which calls `run_command_stream` directly. That path uses the configured local OpenAI-compatible backend; `settings.env` currently points at Ollama and `qwen3-butler:14b`, with remote fallback disabled. Streaming itself does not prevent background work, but this path bypasses the router's background classification and `JobManager`.
- The nonstreaming router in `butler/router.py` can classify foreground, status, and background requests. A background request gets a durable job row and event, then an in-process daemon thread executes it. The router has recent-job context, but the usual streaming voice path does not receive that context.
- `butler/jobs.py` stores jobs/events in local SQLite. It records queued, running, succeeded, failed, or interrupted states and a final summary. Progress during execution is currently generic. On startup, incomplete jobs are marked interrupted; they are not resumed. Existing job/session HTTP endpoints expose records, but there is no complete spoken progress and completion loop.
- The background executor currently calls `run_command`, while the streaming foreground calls `run_command_stream`. These are separate agent loops. `run_command` uses the OpenAI Responses client, so the current background path does **not** meet the owner's local-only requirement even though the usual voice stream does. An acknowledgement may also fall back to the fixed `BACKGROUND_ACK` string.
- Foreground and background already use distinct conversation lane locks, but they share a process, services, memory/tool dependencies, CPU, and potentially accelerator resources. Separate lane locks alone do not prove that voice latency is protected.

## Three useful levels of work

| Level | Typical use | Execution |
|---|---|---|
| Immediate foreground | Conversation, quick status lookup, simple action request | Local Qwen with no-think or a short bounded turn; return or stream promptly. |
| Background job | Bounded analysis, multi-step tool work, slow I/O, waiting for an external acknowledgement | Persist a job, run it independently, publish progress and a verified outcome. Foreground conversation remains available. |
| Specialized subagent | Extended coding, PCB design, or another long specialist project | Separate future delegation design with its own context, tools, budget, and review. This document does not authorize or implement it. |

These are scheduling choices, not necessarily three models. Think/no-think mode, background execution, and delegation are independent decisions. Background is useful when a task is too slow to hold the voice turn open but small enough for one bounded worker and a clear result.

Qwen's usual thinking output places `<think>…</think>` before the user-facing answer. Prompting it to speak *before* its own thinking is not a reliable fast-response mechanism. Use a short local no-think turn for the first spoken response, then a separate task turn. A quick normal conversation need not generate a redundant “working on it” message.

## Proposed interaction contract

1. **Understand and accept.** The foreground local model interprets the request and produces a short natural reply. The controller validates the structured intent, authorization, tool/action schema, and whether it can actually accept the work. For ambiguous or unaccepted requests, the reply asks for clarification or reports the actual problem; it does not promise execution. Speech can begin after acceptance is recorded, without waiting for task completion.
2. **Execute.** The controller schedules either a bounded background job or a registered physical action. A background worker uses a local model endpoint and tools; the foreground retains its own turn capacity. The worker writes durable status, timestamped progress, tool/result evidence, and a terminal result or failure. Model prose is not authoritative job state.
3. **Stay aware.** A job-status request resolves the user's intended job from session and job identifiers, reads bounded structured records, and supplies those facts to foreground Qwen for a natural spoken answer. If there are multiple plausible jobs, ask which one. The record must distinguish queued, running, waiting, succeeded, failed, cancelled, and interrupted rather than guess from conversation history.
4. **Report the outcome.** A terminal job event triggers a foreground notification policy. Foreground Qwen phrases a concise completion or failure message from the stored outcome and evidence. Delivery/playback is tracked separately from task completion; a queued notification is not a heard acknowledgement. Define interruption and barge-in behavior so a late completion does not talk over an active conversation.

The protocol should carry a stable `request_id`, `session_id`, `job_id` or `action_id`, timestamps, status, progress summary, evidence references, and error category. Progress updates need bounds and meaningful milestones; avoid dumping an entire tool transcript into a voice prompt. Tool calls and results remain paired in history, including failures and uncertain outcomes.

### Physical actions

Do not wrap a lights or watering command in a generic model job just to make the first reply fast. Use the existing registered action service, with schema validation, authorization, configured confirmation, idempotency, timeout, acknowledgement, state evidence where available, and transition audit. The first reply may say the request was received or accepted only after that is true. “Done” is reserved for verified completion. Firmware or hardware retains immediate interlocks. The LLM never acts as the safety controller or retry loop.

## Runtime shape

```text
ReSpeaker / text input
        │
        ▼
Foreground controller + local Qwen on 5080
        ├─ quick answer or natural acknowledgement → voice output
        ├─ registered physical action → action lifecycle store
        └─ accepted background request → durable job store / queue
                                          │
                                          ▼
                                local background worker
                                (5080 initially, A2000 if needed)
                                          │
                               progress + terminal evidence
                                          │
                                          ▼
                    bounded status retrieval / notification event
                                          │
                                          ▼
                         foreground Qwen → natural follow-up
```

Use a separate worker **process** for real failure and latency isolation, rather than relying on the current thread. It may use the same Qwen model or a smaller tool-capable local model; its contract is structured progress and accurate results, not a second conversational persona. A separate loopback model server pinned to the A2000 is a practical option. Start with the current 5080 only if measured foreground speech latency remains acceptable under background load. VRAM fit alone does not prove this: generation can contend for compute, and both lanes still share CPU, databases, MCP tools, and I/O. The exact 14B model and context fit on the A2000 is unverified; test before selecting that deployment.

Configuration should make the background endpoint/model explicit and reject a hosted endpoint or silent remote fallback in local-only mode. The foreground and background can have different models. The model choice is an implementation/deployment parameter, not a condition for job awareness.

## Bounded implementation sequence

1. **Establish baseline and contracts.** Record foreground first speech latency and conversational latency during a synthetic long job. Define typed request, job progress, result, notification, and error contracts; specify queue limits, deadlines, cancellation, and restart behavior. Keep existing voice and action behavior working.
2. **Connect streaming voice to job state.** Add a shared routing/status seam for `/chat/stream` so voice can submit and inspect jobs. Read current status from the durable store; feed only bounded, relevant facts to Qwen. Keep the normal streaming reply path for quick conversations. Remove fixed spoken job acknowledgements from this interaction path once local model phrasing is working.
3. **Make background local and observable.** Move background execution off `run_command`'s hosted Responses path to a local backend. Preserve tool schemas and complete call/result history. Emit milestones, terminal results, and truthful failure/interruption state. Do not advertise success for a queued or merely dispatched operation.
4. **Split worker execution.** Move job execution to a supervised local process backed by durable work claiming and recovery rules. Give the foreground a small, predictable resource budget. First measure contention on the 5080; pin a separate local inference endpoint to the A2000 if the foreground latency target fails or model scheduling is unstable.
5. **Add the two spoken moments.** Generate the initial acknowledgement with a bounded local no-think turn after acceptance. On a terminal event, generate a result/failure follow-up from evidence, with delivery and barge-in policy. Keep physical-action lifecycle reporting tied to its authoritative action state.
6. **Roll out on the Linux host.** Gate the new routing per channel, verify under simultaneous ReSpeaker conversation and background work, then enable it by default only after the acceptance checks below. A future subagent tier requires a separate owner-approved design.

The sequence is a proposal, not permission to begin runtime implementation. Small staged changes and whole-system checks on the real Linux host are both needed: component tests catch contract regressions, while integrated voice/hardware tests establish whether the experience actually works.

## Acceptance checks

- With a long local job running, the user can start and complete another voice conversation; foreground latency is measured against an agreed baseline and stays within an owner-approved target.
- “How is the analysis going?” returns the current job's actual state and latest meaningful milestone, including queued, failed, or interrupted cases. It never invents progress from dialogue history.
- Captured background provider calls use only the configured loopback/local endpoint. An unavailable local model produces a truthful failed/degraded state, with no hosted fallback.
- Initial speech is natural and varied but accurately reflects acceptance. Final speech distinguishes verified success, failure, timeout, cancellation, and unknown outcome. No duplicate spoken completion after restart/retry.
- Tool call/result history remains complete. Queue saturation, worker crash, restart, cancellation, duplicate delivery, and model outage have bounded, observable outcomes.
- Physical actions retain the existing action-service confirmation and audit path; no safety rule or hardware interlock depends on model availability.
- On the deployed host, measure 5080/A2000 model placement and memory with the real context/tool load, plus voice first speech latency and latency under concurrent work. Choose the GPU layout from these results.

## Open choices for owner review

- The target maximum first speech and concurrent-conversation latency on the deployed ReSpeaker path.
- Whether background completion should speak immediately, wait for a conversational gap, or become a retrievable notification by default; urgent failures may need a separate policy.
- Background model and context size after A2000 fit and tool-quality measurements.
- Cancellation and restart semantics: which jobs can resume safely, and which must remain interrupted or require a fresh request.

**Stop point:** documentation only. Runtime routing, local worker migration, GPU pinning, and spoken notification changes await a separately bounded implementation task.
