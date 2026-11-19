# Awareness retirement — 2026-11-18

Owner authorization: decouple and archive the awareness system on the current
branch; replace it incrementally through separately scoped systems later.
This task implements retirement only, not a replacement or another awareness
phase. See [archive inventory and impact](../../archive/awareness/README.md).

## Boundaries

Removed startup/deployment dependencies, runtime HTTP calls, internal signals,
fact mirroring, provider registration and launcher maintenance controls. Pump/fan
tools are retired with their action backend; safeguards were not bypassed.
Conversation SQLite storage and real tool-exchange history remain. Direct smart
switch control, clock/weather, voice/display, generic notification/speech ingress,
existing scheduler jobs and job storage remain independent. Phone house-state
reads return unavailable without an explicitly injected provider. Dashboard
legacy fields return `archived` without probing the service.

Archived sources are outside active application imports and test discovery.
Historical documentation remains in place with retirement notices. Existing
data/volumes/environments and running processes were not changed. Restart is
required to load the new source in already-running Butler/MCP processes. Old
standalone awareness processes are not supervised by the new launcher.

## Validation

Validation results are recorded below after the final checks. No live model
acceptance, voice/audio acceptance, physical action, database integration,
data deletion, migration or deployment is part of this retirement.

## Stop condition

Awareness is archived and disconnected from active Butler. No new device,
notification, human-context, memory or briefing system is started. The next
implementation requires a separately bounded owner assignment.

### Test results

Commands below use `.venv-runtime/Scripts/python.exe -m unittest discover -s tests -p PATTERN -q` unless noted. Socket-dependent checks ran with local sockets permitted; all device/provider effects were mocked.

| Pattern | Final result |
|---|---|
| `test_launcher*.py` | 28 passed |
| `test_run_command_stream.py` | 17 passed |
| `test_router*.py` | 13 passed |
| `test_memory_store.py` | 11 passed |
| `test_debug_dashboard.py` | 17 passed |
| `test_awareness_retirement.py` | 5 passed (verbose equivalent) |
| `test_text_server*.py` | 26 passed |
| `test_phone_inbound_server.py` | 18 passed |
| `test_voice_agent_wake_gate.py` | 3 passed |
| `test_smart_plugs.py` | 12 passed |
| `test_jobs.py` | 3 passed |
| `test_history_grounding.py` | 8 passed |
| `test_sleep_mode.py` | 34 passed |
| `test_mcp_disable_selection.py` | 15 passed |
| Combined loader discovery of `test_home_automation_weather.py`, `test_voice_benchmarking.py`, `test_prompting.py`, `test_current_time_context.py`, `test_tool_ordering.py` | 15 passed, 1 failed |

Final results: **225 passed, 1 failed, no skipped cases** across these checks.
The failure is `PromptAssemblerTests.test_default_personality_enforces_home_presence_response_discipline`: it expects `persistent presence in the home`, which the default persona does not contain. Prompt assembler, persona/overlays and its test are unchanged from HEAD; inspection also confirmed the expected phrase is absent from committed personality assets. This unrelated assertion was not weakened or edited.

Intermediate failures: the initial sandboxed dashboard run could not use loopback or read temporary SQLite fixtures and passed on the socket-enabled rerun. Two sandboxed retirement-test runs stalled at FastMCP async catalog listing and were interrupted; all five passed with sockets permitted. A stale text test patched removed `router.awareness_signals`; it now asserts that the signal dependency is absent while retaining exact-delivery/no-model/no-job assertions. An intermediate UTF-8 editing error affected the curly-apostrophe wake check; source encoding was restored and all 34 sleep tests passed. Smart-plug tests emitted unawaited-coroutine warnings from their existing mocked async failure cases; speech-recognition emitted its existing aifc deprecation warning. No warnings were suppressed.

Additional checks: `python -m compileall -q butler tests`, `node --check butler/debug_dashboard/static/app.js`, and Git diff whitespace checks passed. All **131 archived versioned files** hash-match their pre-retirement Git index objects; SHA-256 values are recorded in `archive/awareness/SOURCE_MANIFEST.json`. Active Python import inspection found no imports of retired awareness clients/backend/provider or archived packages. Legacy physical-action truthfulness guards remain active but register no tools.

Not run: full repository suite, archived subsystem tests, live local-model tool-selection acceptance, microphone/audio or GUI acceptance, hardware commands, service restart, migration, backup/export, or data deletion. Main-repository Git commands used `--ignore-submodules`/`diff.ignoreSubmodules=all` where necessary because the existing pump submodule metadata is inaccessible in this sandbox.
