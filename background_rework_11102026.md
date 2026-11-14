# Foreground and background rework — 2026-11-10

**Status (2026-11-13):** Owner direction recorded below. The [platform-agnostic communication layer](interaction_surface_rework_11102026.md) comes first. Background rework awaits a separate implementation assignment.

## Goal and constraints

Talos runs on a local Linux host with an RTX 5080, a ReSpeaker and speaker setup, local Qwen, and a local voice model. Development may happen on a Mac or Windows computer, but the integrated voice and hardware path ultimately needs testing on that Linux host.

The desired interaction is to **respond promptly, perform the task carefully, then report the verified outcome**. The foreground must remain usable for normal conversation and answer “How is the error analysis going?” from current job state. Foreground latency optimization can wait. Background work prioritizes careful analysis and completion over speed. Inference stays local unless the owner explicitly opts into a hosted call. A spare A2000 12 GB is available if isolation on the 5080 is inadequate.

Routing, permissions, and job state must behave consistently across ReSpeaker, text, iMessage, Discord, and other channels. Jobs follow the user across channels. For example, a job started in Discord can be inspected or cancelled in a ReSpeaker conversation when both interactions resolve to the same authorized user. The communication layer must establish that identity and enforce access. Completion can default to the originating conversation. Its presentation and delivery timing follow the channel's capabilities.

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
| Background job | An open-ended user query whose scope exceeds a short no-think call, such as analysis or multi-step work | Persist the query and run a local thinking-capable model with the tools authorized for the turn. Publish progress and an evidence-based outcome while foreground conversation remains available. |
| Specialized subagent | Extended coding, PCB design, or another long specialist project | Separate future delegation design with its own context, tools, budget, and review. This document does not authorize or implement it. |

These are scheduling choices, not necessarily three models. Think/no-think mode, background execution, and delegation are independent decisions. Background is useful when a task is too slow to hold the voice turn open but small enough for one bounded worker and a clear result.

Qwen's usual thinking output places `<think>…</think>` before the user-facing answer. Prompting it to speak *before* its own thinking is not a reliable fast-response mechanism. Use a short local no-think turn for the first spoken response, then a separate task turn. A quick normal conversation need not generate a redundant “working on it” message.

### Proposed first-pass routing

Make one bounded routing decision at the start of the turn. Keep ordinary dialogue and clearly simple requests in the foreground. Route requests that clearly need sustained reasoning or multiple dependent steps to the background automatically. When uncertainty concerns what the user wants or authorizes, ask a focused clarification question. For uncertain effort, start with the foreground default and evaluate misroutes before adding a mid-turn handoff. Apply the same rules across channels. Validate the route, permissions, and queue capacity before acknowledging job acceptance. The worker receives the original query and relevant authorized context. Progress and outcomes come from recorded milestones and tool evidence.

## Proposed interaction contract

1. **Understand and accept.** The foreground local model interprets the request and produces a short natural reply. The controller validates the structured intent, authorization, tool/action schema, and whether it can actually accept the work. For ambiguous or unaccepted requests, the reply asks for clarification or reports the actual problem; it does not promise execution. Speech can begin after acceptance is recorded, without waiting for task completion.
2. **Execute.** The controller schedules either a bounded background job or a registered physical action. A background worker uses a local model endpoint and tools; the foreground retains its own turn capacity. The worker writes durable status, timestamped progress, tool/result evidence, and a terminal result or failure. Model prose is not authoritative job state.
3. **Stay aware.** Resolve the intended job from bounded structured records using the authorized user, job identifier, and conversation context. The originating session is useful context for resolving the request. If there are multiple plausible jobs, ask which one. Track queued, running, waiting, succeeded, failed, cancelled, and interrupted explicitly, with timeout and uncertain effects represented in the outcome.
4. **Report the outcome.** Deliver model-phrased job notices at the next conversational gap. Make the stored result available on request as soon as it exists. Track delivery and playback separately from task completion and respect barge-in. Model unavailability is a critical system error and takes precedence over ordinary delivery timing. Use the existing deterministic critical-alert path if the model cannot phrase that alert. Pending ordinary job notices still require model phrasing.

### Queue, cancellation, and crash recovery

Start with one active job and a small bounded queue. Report saturation before promising work. Cancel queued jobs immediately and stop running jobs at a safe point. Record any in-flight effect whose outcome cannot be verified as unknown.

After a worker crash, mark the attempt interrupted. Allow one automatic retry when the execution record confirms that replay is safe. If the retry is in progress at the next conversational gap, send one model-phrased retry notice. If it has already finished, send the final outcome alone. Once the job has a terminal outcome, deliver it at the next gap. If replay cannot be verified as safe, report the interruption and any uncertain effects and leave the job for review. Persist attempts and notification state so a restart cannot reset the retry budget or repeat the retry notice.

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

1. **Complete the platform-agnostic communication layer first.** Follow its separate plan. Establish shared turn handling and a trusted cross-channel identity and authorization model before starting this rework.
2. **Make background execution local and observable.** Move it off the hosted Responses path. Preserve caller permissions, tool schemas, and complete call/result history. Define typed job, result, notification, and error contracts with queue limits, deadlines, cancellation, and durable retry rules. Verify outcomes from evidence. The current worker treats a returned string as success, so successful model generation alone is insufficient to verify a task.
3. **Connect shared routing and status.** Add first-pass automatic routing and authorized cross-channel status retrieval through the shared controller. Connect submission only once local execution is available. Keep quick turns on the normal reply path.
4. **Split worker execution.** Move job execution to a supervised local process backed by durable work claiming and recovery rules. Give the foreground a small, predictable resource budget. First measure contention on the 5080; pin a separate local inference endpoint to the A2000 if the foreground latency target fails or model scheduling is unstable.
5. **Add the two spoken moments.** Generate the initial acknowledgement with a bounded local no-think turn after acceptance. On a terminal event, generate a result/failure follow-up from evidence, with delivery and barge-in policy. Keep physical-action lifecycle reporting tied to its authoritative action state.
6. **Verify and roll out.** Exercise the same routing and job semantics across supported channels, including ReSpeaker conversation on the Linux host while a job runs. Measure contention when evaluating placement. A future subagent tier requires a separate owner-approved design.

The sequence is a proposal, not permission to begin runtime implementation. Small staged changes and whole-system checks on the real Linux host are both needed: component tests catch contract regressions, while integrated voice/hardware tests establish whether the experience actually works.

## Acceptance checks

- With a long local job running, the user can start and complete another voice conversation. Foreground latency tuning can follow the functional checks.
- An authorized user can start a job on one channel and inspect or cancel it from another. Equivalent turns follow the same routing and permission rules across channels.
- “How is the analysis going?” returns the current job's actual state and latest meaningful milestone, including queued, failed, or interrupted cases. It never invents progress from dialogue history.
- Captured background provider calls use only the configured loopback/local endpoint. An unavailable local model produces a truthful failed/degraded state, with no hosted fallback.
- Initial replies accurately reflect acceptance. Model-phrased completion notices arrive at a conversational gap and distinguish verified success, failure, timeout, cancellation, and unknown outcome. Restart and retry preserve the attempt budget and suppress duplicate notices. Model failure raises a critical system alert.
- Tool call/result history remains complete. Queue saturation, worker crash, restart, cancellation, duplicate delivery, and model outage have bounded, observable outcomes.
- Physical actions retain the existing action-service confirmation and audit path; no safety rule or hardware interlock depends on model availability.
- On the deployed host, measure 5080/A2000 model placement and memory with the real context/tool load, plus voice first speech latency and latency under concurrent work. Choose the GPU layout from these results.

## Deferred design details

- Routing criteria and evaluation examples. Revisit mid-turn escalation after observing first-pass behavior.
- What counts as a conversational gap on each channel and whether interrupted voice playback is replayed or left available on request.
- Queue capacity, job deadlines, and how to establish safe replay from the execution record.
- Foreground latency targets when optimization begins.
- Background model and context size after A2000 fit and tool-quality measurements.

**Stop point:** Documentation only. Complete the platform-agnostic communication layer first. Background rework requires a separate assignment.
