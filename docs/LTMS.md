# Long Term Memory System (LTMS), bounded v1

LTMS owns durable knowledge, distinct from DIS device observations, WCS environmental
observations and immediate conversation history. It uses the shared BUTLER_DB_PATH.
Migration 6 adds ltms_memories, ltms_edges and ltms_jobs. No old facts are imported.
The legacy saved-fact tool is removed from the advertised catalog; its compatibility
handler returns an explicit unavailable result. Conversation messages, real paired
tool exchanges and recent-history replay remain unchanged. Phone summaries remain
conversation history but no longer write saved-fact digests.

## Data flow

Owner message -> bounded nonblocking inbox -> intake thread -> durable pending job
-> dedicated local model -> validated atomic graph batch + job completion.
Assistant completions/tool results are separately labelled evidence, not owner assertions.
Restricted turns neither retrieve nor submit LTMS conversation evidence.
Every eligible turn embeds the incoming message, searches SQLite, reads one-hop
relations and inserts bounded context before the chat model. No generative recall pass.
An unfinished extraction never blocks the next conversational turn.

Direct DIS device ingestion is disabled as of 2026-11-19. LTMS does not sample
DIS caches, including state changes or errors. New `dis:` submissions are rejected;
startup discards old pending/failed DIS jobs, and extraction also discards old DIS
jobs before any model call. Existing memory nodes and edges are not deleted.
A future bounded DIS status-package contract is deferred; no replacement exists.
Conversation learning still permits explicit owner preferences about devices;
the worker prompt excludes routine device readings repeated in replies/results.
This prompt policy is not a guarantee of semantic model compliance.

WCS overview weather remains sampled every five seconds outside model turns,
with observation/receipt/validity times preserved; age/receipt changes alone are
ignored for deduplication. No new API calls or telemetry history adapter.

## Operations and limits

The worker returns a JSON batch of up to 16 operations with exact field validation:
create_memory(content), update_memory(id,content), archive_memory(id),
forget_memory(id), merge_memories(ids,content),
create_edge(source_id,target_id,relation), remove_edge(source_id,target_id,relation).
The store also implements search_memories and traverse_graph (one hop). Search and
traversal prefetch related records before extraction; v1 does not expose a recursive
model tool loop. New-node relationships can be added in later batches.
Content is at most 2000 characters, relations 80 characters. References must exist
and be active. A bad operation rolls back the entire batch. Merging archives inputs
and transfers external edges; archiving hides memories and their edges from recall.
Forgetting physically deletes the node and incident edges. Updates replace content
and invalidate its embedding. Historical versions are not promised in v1.

Each active memory retains bounded supporting source evidence, timestamp and
embedding-model identity. Validation establishes schema/reference integrity, not
semantic truth: model inference can still be wrong. Text labels explicit/inferred
knowledge and must not treat model actions as user confirmation. Memory never
authorizes physical execution. A future executor has a separate authorization boundary.

Corpus cap: 4096 total nodes including archived nodes, 16384 edges. Inbox: 256
entries, maximum 16000 characters each. Pending/failed job cap: 2048. Queue overflow
is logged and counted; accepted inbox items become durable on the intake drain
(roughly 100 ms), so abrupt process death can lose that small uncommitted window.
Successful jobs are deleted atomically with graph changes; failures retain a class
name, retry after 60/120 seconds and stop after three attempts. Failed jobs are not
silently discarded. No retention scheduler or unbounded reflection loop is included.

## Models and lifecycle

Butler starts/stops the memory worker and a dedicated Ollama process on loopback
port 11435. An existing service there is treated as externally managed. Default
extraction: qwen3:8b. Default embeddings: all-minilm with num_gpu=0 (CPU).
The owned Ollama process detects the A2000 UUID, disables Vulkan and sets
CUDA_VISIBLE_DEVICES; it cannot evict the main chat model in the port-11434 process.
Model files are shared with the existing Ollama installation. No cloud fallback.

Settings: BUTLER_LTMS_ENABLED (default 1), BUTLER_LTMS_OLLAMA_URL
(default http://127.0.0.1:11435), BUTLER_LTMS_GPU (optional GPU UUID override),
BUTLER_LTMS_MODEL (qwen3:8b), BUTLER_LTMS_EMBED_MODEL (all-minilm).
The URL must be HTTP loopback. Restart Butler to apply settings.
No Butler deployment restart is performed by this implementation task.

SQLite search scans the bounded corpus and combines lexical overlap with cosine
similarity using the better score, then expands at most eight one-hop edges.
Embedding model/dimension mismatch excludes semantic scores. Missing embeddings
fall back to lexical retrieval with explicit degraded context. Embeddings are
written asynchronously after commit. Query embedding has 1-second connect and
2-second socket-read timeouts; extraction has a 90-second read timeout. These are
socket timeouts, not absolute wall-clock guarantees. No model work holds a DB lock.
SQLite write contention retains the shared five-second busy timeout.

## Deferred

Chained reflection: search -> traverse -> compare -> reflect -> merge -> create
relationships. Also deferred: executor, advanced consolidation/history, automatic
capacity pruning, exact observation-count aggregates, embedding-index acceleration,
GUI tuning and broad multi-user identity. This task stops at bounded LTMS v1.


## Verification (2026-11-19)

115 deterministic cases passed: LTMS 12, memory store 11, shared storage 12,
streaming 17, tool ordering 5, phone 11, DIS 19, WCS 24, four non-catalog
retirement checks. One opt-in local-model learn/recall/change/forget test passed.
Initial malformed model output was rejected; schema-constrained output fixed the
acceptance failure. Full retirement catalog discovery stalled under the sandbox;
full repository/continuous soak/live main-agent acceptance and restart were not run.
See the dated session log for initial failures and precise fixture changes.


## Read-only 2D viewer (2026-11-19)

Open `/memory` on the debug dashboard (normally http://127.0.0.1:8787/memory).
The console toolbar links to it. Restart the dashboard process to load new routes;
no Butler restart is needed solely for the viewer. There are no new dependencies,
external assets, inference calls or schema migrations. Graph positions are local
presentation state and are never persisted.

`GET /api/ltms-graph?limit=250&archived=0` reads a consistent query-only SQLite
snapshot through the existing dashboard exception. Default 250 nodes, maximum 500;
maximum 2000 directed edges whose endpoints are both in the selected node set.
Newest memories are selected first. Coverage explicitly reports omitted nodes and
edges; absence from a limited view does not establish absence in storage.
Include archived is opt-in. Evidence and embedding presence are visible on selection;
embedding vectors are not returned. Missing database/schema reports unavailable
without creating or migrating anything. Empty databases are visibly distinguished
from errors. The endpoint inherits the dashboard's local-only default and existing
explicit remote-access opt-in, with no new authentication model or write route.

The buildless SVG view supports directed relation labels, pan/zoom, node dragging,
manual refresh, fit, selection details, a searchable list, and archived filtering.
Search highlights/filters only the loaded view; it is not semantic retrieval or
whole-database search. There is no editing, automatic refresh or graph expansion.

Verification: five new graph/data/HTTP tests and all 17 existing dashboard tests
passed using the available Inkscape Python 3.12 interpreter with existing .venv-main
site-packages on PYTHONPATH. The repository virtual environments point at a missing
Python312 executable; no environment was repaired. Node syntax and git whitespace
checks passed. Browser checks verified real data (3 active nodes, 0 edges), selection,
evidence, fixture relation arrows/labels, archived nodes and search. Real observations
included transient state/duplicate-looking memories; no LTMS learning policy changed.


## Launcher integration (2026-11-19)

The viewer is a separate diagnostic HTTP process, independent of the main agent.
Launcher **Open memory graph** starts/reuses the debug dashboard on 127.0.0.1:8787
and opens /memory; no separate manual server command is normally required. It
works before Start Butler and after Stop. A launcher-owned dashboard stops when
that launcher closes; an already-running externally owned dashboard is reused.
An older dashboard without /memory is reported with instructions to reopen its
owning launcher/console; it is never silently terminated.

The **Information & memory** launcher tab controls DIS collection/context, WCS
collection/context, LTMS enablement, extraction/CPU-embedding model, dedicated
Ollama URL, and optional GPU UUID (blank detects A2000). Settings save to settings.env
and apply after a Butler restart. DIS/WCS/LTMS remain main-process-owned modules,
not new Supervisor components. Conversation continuity stays separately labelled;
existing runtime behavior still requires its memory switch for LTMS turn learning
and recall. Clear conversation memory does not clear LTMS/DIS/WCS.

The environment's .venv-runtime base Python312 executable is currently missing.
The launcher now points startup failures toward that interpreter/dependency issue;
it does not silently switch the main runtime. An operational local dashboard was
started using the available Inkscape Python 3.12 and existing .venv-main packages,
then verified through the launcher's own ensure_running('/memory') helper and in
the browser. Restore the configured runtime installation for fresh automatic
launches. No package installation or runtime environment repair was performed.
