# Voice wake interaction requirements — 2026-11-10

**Status:** owner-requested behavior specification. This document defines the desired experience and acceptance criteria; it does not prescribe an implementation or authorize runtime changes.

## Purpose

Butler must support both natural ways of beginning a voice request:

1. **One utterance:** “Butler, turn on the lights.” Butler acknowledges the request and handles it.
2. **Wake, then request:** “Butler?” Butler acknowledges that it is listening. The user then says “Turn on the lights” without repeating the wake word. Butler acknowledges and handles that request.

The second pattern must feel like one continuous interaction. The user should not need to guess whether Butler is listening, rush to speak before a hidden cutoff, or repeat “Butler” after receiving an acknowledgement.

## Current behavior to replace

The current voice callback accepts a transcript that starts with the wake word and contains a command. It plays a wake cue after transcription. When the transcript contains only the wake word, it records `wake_word_without_command` and ends that turn. A later utterance without the wake word is rejected as `wake_word_missing_in_transcript`. This behavior is exercised in [`tests/test_voice_agent_wake_gate.py`](tests/test_voice_agent_wake_gate.py) and implemented in [`butler/voice/agent.py`](butler/voice/agent.py).

## Required user-visible behavior

### Wake and listening

- Butler clearly acknowledges a recognized wake-only address, such as “Butler?” or “Butler.” The user can tell when it is ready to hear the request.
- After a wake-only address, the next utterance is accepted as the request without another wake word, provided it occurs within a bounded listening period.
- A command spoken immediately after “Butler” continues to work as one utterance. Butler must not interrupt an in-progress command with a wake-only response.
- If the user starts the request while Butler is acknowledging the wake, the request is still captured correctly. Butler's own audio must not be mistaken for the user's command.
- If the user repeats “Butler,” Butler remains available for the request without treating the repeat as a task or producing stacked acknowledgements.
- If the user says nothing, the listening period ends quietly and Butler returns to its normal wake-word requirement. The user can always start again with “Butler.”
- A deliberate dismissal such as “never mind” ends the pending interaction without triggering a tool or physical action.
- Speech from another person, a TV, or general room conversation after the listening period must not be treated as an authorized request simply because Butler was recently addressed.

### Responses and task truth

- Ordinary spoken acknowledgement and task wording should come from the configured **local model**, not fixed response strings. A nonverbal cue or visible listening indicator may provide immediate feedback.
- A wake-only acknowledgement must not claim that a task has been accepted or completed; Butler has not yet heard one.
- After a request, Butler's wording must match the actual task state. “I’ll turn on the lights” requires that the request was accepted. “The lights are on” requires completion evidence. If acceptance, execution, or verification fails, Butler reports that truthfully.
- Ambiguous or unsupported requests lead to a natural clarification or failure response. They must not be silently dropped or presented as successful.
- Physical actions continue through registered definitions, authorization, configured confirmation, idempotency, timeouts, acknowledgements, and transition audit. Immediate device safety stays in firmware or hardware.
- Normal voice interaction stays local unless the owner explicitly selects a hosted service for the particular purpose. Model unavailability must not silently switch to a hosted provider.

### Conversation quality

- The two entry patterns lead to the same request interpretation, permissions, tools, session context, and outcome once the command is known.
- Butler's acknowledgement should feel prompt on the deployed ReSpeaker and speaker setup. The final timing threshold is an owner acceptance choice measured on that host, not an invented number in this document.
- Interrupting Butler, correcting a misheard command, or cancelling before an action is accepted should have clear outcomes. An already-dispatched physical action must not be reported as cancelled merely because speech stopped.
- False wakes and missed commands must be observable in bounded diagnostics so a live room test can distinguish wake detection, transcription, listening-window, and action failures. Ordinary room audio is not silently retained as a debugging artifact.

## Acceptance scenarios

| Scenario | Expected result |
|---|---|
| “Butler, turn on the lights.” | One request is understood and handled; response reflects accepted/completed/failed state. |
| “Butler?” → Butler acknowledges → “Turn on the lights.” | The second utterance is handled without repeating “Butler”; one task is created. |
| “Butler?” → user starts speaking during Butler's acknowledgement | User speech is retained and Butler's own speech does not become a command. |
| “Butler?” → silence | Listening ends quietly; later unrelated speech does not dispatch. |
| “Butler?” → “Butler, turn on the lights.” | The repeated wake word does not corrupt or duplicate the task. |
| “Butler?” → “Never mind.” | No tool or physical action is invoked; interaction closes. |
| “Butler?” → ambiguous device request | Butler asks for clarification before any unsafe or guessed action. |
| Accepted action later fails or remains unverified | Butler distinguishes the failure or unknown outcome from completion. |
| Wake or request during Butler playback | Interaction is handled according to the existing interruption policy without echo-triggered commands or duplicate execution. |

Acceptance requires room tests on the actual Linux host, ReSpeaker, speaker path, and configured local model. Test natural pauses, short and long commands, background noise, playback overlap, false wakes, missed wake words, and model or device failures. Record which cases pass and their measured response timing; unit tests alone do not establish that the interaction feels reliable.

## Scope boundary and open product choices

This specification covers the two ways of **starting** a request. It does not decide whether Butler should keep listening for additional unrelated turns after answering; that is a separate continued-conversation policy. It also does not select an audio architecture, wake detector, endpointing method, timeout value, cue, phrasing prompt, or implementation sequence. The coding agent should choose and justify those details against the acceptance scenarios and existing repository safety rules.

**Stop point:** requirements documentation only. No voice, model, tool, or device behavior has been changed.
