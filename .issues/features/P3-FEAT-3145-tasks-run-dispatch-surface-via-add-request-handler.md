---
id: FEAT-3145
title: 'll-mcp: tasks/* run-dispatch surface via Server.add_request_handler (tier-3,
  evidence-gated)'
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-10'
discovered_by: learning-test
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp extension mechanism
depends_on:
- FEAT-3143
- ENH-3144
- FEAT-3149
relates_to:
- FEAT-3143
- FEAT-3149
confidence_score: 65
outcome_confidence: 38
verify_verdict: VALID
score_complexity: 10
score_test_coverage: 0
score_ambiguity: 10
score_change_surface: 18
missing_artifacts: true
size: Medium
testable: true
reconcile_attempted: true
deferred_by: automation
deferred_date: '2026-08-10T22:50:16Z'
deferred_reason: low_readiness
---

# FEAT-3145: ll-mcp: tasks/* run-dispatch surface via Server.add_request_handler

## ⚠ Gated — do not implement before the tier-3 evidence gate opens

EPIC-3127 holds the job tier behind an explicit gate: long-running orchestration
is "built only if real usage of the first two tiers shows hosts wanting to
*drive* runs rather than plan them." That evidence does not exist yet. This issue
is captured so the proven mechanism and the design shape are not lost, **not**
because the gate has opened. Anything that spawns an agent or runs for minutes
stays off the tool surface until it has.

**Additionally blocked by tier 2.** EPIC-3127's ordering is strict — "Tier 2
blocks tier 3, and tier 3 is additionally evidence-gated." Tier 2 (guarded
mutations) is tracked by **FEAT-3149** and has not shipped. Landing this issue
first would make "spawn an agent and run it for minutes" the *first* write path
into a project over MCP, with no dry-run-by-default convention or per-method
transport policy to hang it on. See Open Questions below.

## Summary

Expose long-running little-loops work over MCP as a `tasks/*` request surface —
start, poll, cancel, retrieve result — registered through
`Server.add_request_handler` on the existing lowlevel server, and shaped to match
SEP-2663 so it can be replaced by the official `io.modelcontextprotocol/tasks`
extension when an SDK ships one.

**Scope: `ll-loop` runs only.** `ll-queue` is explicitly out of scope — see
Scope Decision below.

## Use Case

A developer has `ll-mcp` registered in a second MCP host (a phone-side agent, or
a Claude Code session on a different machine reaching the workstation over the
FEAT-3143 HTTP transport). They've triaged a backlog through the tier-1 read-only
tools and now want to kick off `ll-loop run rn-refine` against a specific issue
without SSH-ing to the workstation and without the MCP call itself hanging for
the twenty minutes the loop takes. They call the start method, get a handle back
immediately, poll it from the same host every couple of minutes while doing
other work, and pull the `ExecutionResult` when `terminated_by` is set. If the
loop wedges, they cancel it from the same surface rather than hunting for a PID.

## Current Behavior

`ll-mcp` serves five read-only tools. Orchestration (`ll-auto`, `ll-parallel`,
`ll-loop`, `ll-action invoke`) is deliberately absent from the tool surface —
correctly, since a tool call that runs for minutes does not fit the tools
primitive. There is no other way to reach a run from an MCP host.

## Expected Behavior

A small set of custom methods — shaped as `tasks/get`, `tasks/cancel`, and a
start path — dispatch to the existing `ll-loop` run machinery, so a host can
begin a run, poll it, and collect its result without the call itself being
long-running. Progress rides `subscriptions/listen` rather than a bespoke
notification channel.

## Proven by learning test

`.ll/learning-tests/mcp-extension-mechanism.md` (`proven`, mcp 2.0.0, 6/6):

- **The mechanism works today.** `Server.add_request_handler("tasks/get",
  TasksGetParams, handler)` on the unmodified `build_server()` server dispatched
  over streamable HTTP and returned the handler's result, with wire params
  validated through the camelCase alias (`taskId`). No `MCPServer` migration
  required.
- The formal `Extension` API is *not* the path: it attaches via
  `MCPServer(extensions=[...])`, and the lowlevel `Server` has no `extensions`
  parameter.
- `MethodBinding` enforces additive-only naming (a spec method such as
  `tools/list` raises `ValueError`), which is the same boundary a custom
  `tasks/*` surface should respect.
- `MethodBinding.protocol_versions` gates a method by wire version; an empty
  frozenset raises at construction.
- MRTR is available for any step needing human input mid-flight:
  `INPUT_REQUIRED_METHODS` covers `prompts/get`, `resources/read`, and
  `tools/call`, with `is_input_required` as the TypeGuard.

## Design constraint: imitate SEP-2663, do not diverge from it

The value of matching the spec's shape is that swapping to the official
extension later becomes a registration change rather than a client-visible
protocol change. Method names, params, and result shapes should track SEP-2663
even though nothing enforces that today.

**This constraint is in tension with the start path — see Open Question 1.**

## Decisions

### Decision 1 — Job-state truth: use the live-PID-reconciled convention

`tasks/get` MUST reconcile PID liveness before reporting a run as `running`,
following `fsm/persistence.py`'s convention (`_reconcile_stale_running`,
`persistence.py:243-265`), not `queue_store`'s trust-the-DB-column convention.

**Why:** `queue_store`'s trusted-column read is only safe because its callers are
in-process and short-lived — a stale `running` value is corrected on the next
tick. Across an MCP boundary there is no next tick: a host that receives
`running` for a run whose process died of OOM or a kernel kill polls forever,
with no timeout and no way to distinguish "still working" from "dead." The
reconciliation pass already exists and is already the convention of the backend
this issue wraps, so this costs nothing to adopt.

This closes the "unresolved job-state-truth conflict" that prior confidence
checks flagged as the dominant ambiguity driver.

### Decision 2 — Scope: `ll-loop` only, `ll-queue` deferred

Only the `ll-loop` backend is in scope. `ll-queue` is dropped from this issue.

**Why:** the two backends share no job-state bridge — PID-liveness
reconciliation is independently reimplemented three times across the codebase
and no module in `scripts/little_loops/` imports both `queue_store.py` and
`fsm/persistence.py` (see Conventions in Force). Spanning both is what made this
issue `Large`, and `ll-queue` does not have a coherent start/poll/cancel triple
to expose anyway: `reset_to_pending()` is a re-runnable transition, not a cancel.
`ll-loop run_background()` has a real detached-start/disk-poll/process-group-kill
triple and is the backend the Use Case actually wants. If `ll-queue` dispatch is
ever wanted, file it separately against a settled `tasks/*` surface.

### Decision 3 — `tasks/cancel` means "stop, resumable" and must say so

Neither backend has a terminal cancelled status. `cmd_stop()`
(`cli/loop/lifecycle.py:317`) writes a `user-stop.marker`, `SIGTERM`s the process
group, escalates to `SIGKILL` after 10s, and lands the run in `"user_stopped"` —
which stays inside `RESUMABLE_STATUSES` (`persistence.py:46`).

This issue does **not** introduce a new terminal status. Instead `tasks/cancel`'s
result shape must carry the resumability explicitly (e.g. a `resumable: true`
field alongside the status), so a host is never told "cancelled" when the
truthful answer is "stopped, and resumable." Silently mapping `user_stopped` onto
a spec `cancelled` value would be a lie at the protocol boundary.

## Anti-goals

- Do not advertise `io.modelcontextprotocol/tasks` in the capabilities response.
  The server would be claiming an extension it implements privately. This is
  EPIC-3127 open question 4 and it stays closed until an SDK ships the extension.
- Do not turn `ll-auto` / `ll-parallel` into tools as a side effect.
- Do not introduce a new terminal `cancelled` status in `fsm/persistence` as part
  of this issue (Decision 3).
- Do not add `ll-queue` dispatch (Decision 2).

## Open Questions — resolve before implementation

### Open Question 1 — Is a spec-faithful start path reachable at all? — **RESOLVED: yes** (2026-08-11)

**Resolved affirmatively by spike.** Learning test:
[`.ll/learning-tests/mcp-tasks-start-path.md`](../../.ll/learning-tests/mcp-tasks-start-path.md)
— 11/11 claims pass against the pinned `mcp==2.0.0` over streamable HTTP.
The two constraints are **not** in conflict, and no `tasks/start` needs inventing.

**The question contained a false step.** SEP-2663's start is indeed an
augmentation of `tools/call` — the spec's own example request is a *completely
ordinary* `tools/call` body, with the client signalling support via per-request
capabilities and the server deciding per-request whether to materialize a task.
But that augmentation is **on the response, not the registration**: the server
returns `CreateTaskResult` (`resultType: "task"`) in lieu of a `CallToolResult`.

`ll-mcp` already *owns* its `tools/call` handler (`on_call_tool=handle_call_tool`,
`mcp_server/server.py:63`). Nothing is re-registered, so the additive-only
`MethodBinding` boundary is never engaged — it was only ever a constraint on
*registering* a spec method name, which the start path does not do.

Three independently sufficient mechanisms, all proven on the lowlevel `Server`:

1. **Return a task-shaped `Mapping` from `handle_call_tool`.** `runner._serialize`
   (`runner.py:364-378`) skips the spec-method sieve whenever `resultType` is a
   modern-era string outside `CORE_RESULT_TYPES` (`{'input_required','complete'}`)
   — extension-owned shapes are passed through by design, not by accident.
   `_dump_result` accepts `BaseModel | dict | None`, so a raw mapping works at
   runtime despite the `CallToolResult | InputRequiredResult` annotation.
2. **`compose_tool_call_handler([TasksExtension()], handle_call_tool)`** — the
   extension-faithful path. This is a *free function*, so it works on the
   lowlevel `Server` even though that class has no `extensions=` parameter
   (which is what [[mcp-extension-mechanism]] claim 3 established).
3. **`Server.middleware`**, for wire-level rewriting above params validation.

`tasks/get` / `tasks/update` / `tasks/cancel` all register and dispatch normally
via `add_request_handler(method, params_type, handler)` — these *are* additive
method names and were never at risk.

**Consequence for this issue:** the value proposition survives intact. Mechanism 2
is the recommended one, since swapping to the official extension later becomes a
registration change exactly as this issue promised.

**One forward-compatibility caveat to carry into implementation:** `runner.py:370`
carries a `TODO(L56)` to reject extension `resultType` values unless the matching
extension is present in the request's `_meta.clientCapabilities.extensions`.
Emitting `resultType: "task"` *without* honoring the client's declared extension
capabilities passes today but is forward-incompatible. The implementation must
gate task materialization on the client having declared the extension — which is
also what SEP-2663 requires ("the client signals support ... the server decides").

**This no longer blocks implementation.** The remaining blockers are Open
Question 2 (below), the unfired tier-3 evidence gate on EPIC-3127, and tier
ordering behind FEAT-3149.

### Open Question 2 — Authentication for run dispatch over HTTP

FEAT-3143 landed the streamable HTTP transport with an explicit scope note: "No
authentication, TLS termination, or session model in this issue." Its defenses
are loopback bind (`127.0.0.1`) plus DNS-rebinding protection — which stop a
browser, not a local process.

The Dependencies section below says this surface "is most useful over HTTP." That
combination means any local process that can reach the bound port can start an
agent run with the project's full tool permissions. Before implementation, pick
one:

- add a per-method policy gate / auth requirement to this issue's scope (which
  overlaps tier 2's per-method transport policy — another reason FEAT-3149 comes
  first), **or**
- restrict `tasks/*` to stdio only until auth exists — which contradicts the
  Dependencies rationale for depending on FEAT-3143 and should be stated plainly
  rather than left implicit.

## Dependencies

- **FEAT-3149** (tier 2, guarded mutations) — establishes the dry-run-by-default
  convention and per-method transport policy that a run-dispatch surface needs to
  sit behind. Strict per EPIC-3127's tier ordering.
- **FEAT-3143** (done) — the surface is most useful over HTTP; stdio-only
  dispatch has little reason to exist. See Open Question 2.
- **ENH-3144** (done) — the epic's guidance needed correcting first, or this
  issue read as contradicting its own parent.

## Acceptance Criteria

*(Open Question 1 is resolved affirmatively — the start-path criteria stand.
Open Question 2 (HTTP auth) is still open and gates implementation.)*

1. A `tasks/get` request over HTTP for a live `ll-loop` run returns within
   normal request latency (no long-running request), with a status field derived
   through the PID-liveness reconciliation path — asserted by a test that kills
   the run's process without updating its state file and confirms `tasks/get`
   reports it as not-running rather than `running` (Decision 1).
2. A `tasks/get` request for a completed run returns the `ExecutionResult` fields
   (`final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`) as
   serialized by `ExecutionResult.to_dict()` (`fsm/types.py:66`).
3. A `tasks/cancel` request stops a running `ll-loop` run and its result payload
   reports the run as resumable, matching the `user_stopped` reality rather than
   claiming a terminal cancellation (Decision 3).
4. `initialize`'s capabilities response does **not** contain the string
   `io.modelcontextprotocol/tasks` — asserted by a dedicated test, since no
   existing test covers the capabilities payload.
5. `tasks/*` requests for a `ll-queue` entry are not registered at all (Decision
   2) — no partial or stub queue dispatch ships.
6. Each registered method name and result field is annotated in code with the
   SEP-2663 construct it mirrors, so the later swap is mechanically checkable by
   a human even though nothing enforces it automatically.
7. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — gated on evidence that has not appeared, and blocked behind
  a tier-2 issue that does not exist yet. Nothing about this is urgent; it is
  captured to preserve proven research.
- **Effort**: Medium — reduced from Large by Decision 2 (single backend). The
  mechanism is proven and the poll path is a disk read, but `_status_single`'s
  JSON-shaping logic is currently inline and coupled to `argparse.Namespace`, so
  extracting an importable helper is real work, and this would be the first
  locally-authored Pydantic model in the package.
- **Risk**: High — not from the code size but from the design premise: Open
  Question 1 may show the SEP-2663-fidelity goal is unreachable via
  `add_request_handler`, and Open Question 2 exposes an unauthenticated remote
  run-start path. Both must close before code is written.
- **Breaking Change**: No — purely additive method registration inside
  `build_server()`; `test_build_server_signature_unchanged` keeps passing.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 3 (job API), evidence-gated.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `PersistentExecutor.run()`/`.resume()` (`fsm/persistence.py:960`,`:999`) are **blocking** calls that return an `ExecutionResult` only when the FSM finishes — neither supports "start and return a handle." The start/poll split is implemented one layer up: `run_background()` spawns a detached re-exec'd child and returns immediately with only `instance_id`/PID/log path available; the eventual `ExecutionResult` is written to disk by that child, not returned to the spawning call.
- `ExecutionResult.to_dict()` (`fsm/types.py:29`,`:66`) is the existing JSON-serializable result shape (`final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`, conditional `failure_terminal`/`error`/`handoff`) — the closest existing analog to a `tasks/get` result payload for the `ll-loop` backend.
- A poller does not need to re-enter `PersistentExecutor`: existing status-read code (`_status_single()`, `cli/loop/lifecycle.py:131`) is already a pure disk-read path — `StatePersistence.load_state()` reads `<instance_id>.state.json`, `_reconcile_stale_running()` (`fsm/persistence.py:243`) re-verifies PID liveness before trusting a persisted `"running"` status, `_read_pid_file()`/`_resolve_live_pid()` (`persistence.py:212,222`) resolve the PID via `.pid` file → `.lock` file → `state.pid` fallback chain, and log/event files are read directly. This JSON-shaping logic is currently inline inside `_status_single`, coupled to `argparse.Namespace`/`print_json` — not yet a standalone importable helper a `tasks/get` handler could call directly.
- Existing cancel mechanism for a detached `ll-loop` run is `cmd_stop()` (`lifecycle.py:317`) → `_kill_with_timeout()` (`lifecycle.py:88`): writes a `user-stop.marker` before signalling (to distinguish user-stop from OOM/kernel kill), then `os.killpg(pgid, SIGTERM)` against the whole process group (required because `start_new_session=True` makes the spawned PID a session leader), polling up to 10s before escalating to `SIGKILL`. Final status becomes `"user_stopped"`, which stays inside `RESUMABLE_STATUSES` (`persistence.py:46`) — `ll-loop` has no separate non-resumable "cancelled" terminal status. **Decision 3 addresses this.**
- No `pydantic.BaseModel` subclass is authored anywhere in `scripts/little_loops/` today (only test/spike code uses Pydantic, and only via the third-party `mcp` SDK's own types, e.g. `mcp_server/tools.py` imports `mcp_types as types` for `types.Tool`/`types.CallToolRequestParams`). The existing convention for wire shapes is to consume the SDK's own models rather than hand-author parallel `BaseModel` subclasses — a `TasksGetParams`-style model would be the first locally-authored one.
- Reusable HTTP test scaffolding already exists for exactly this shape of test: `test_feat_3143_mcp_http_transport.py`'s `_make_project()` (`:32`), `_envelope()` (`:39`), and `_post()` (`:48`) post raw JSON-RPC bodies through `starlette.testclient.TestClient` wrapping `server.streamable_http_app(...)` — the same approach needed for `tasks/*` methods, which aren't reachable via `mcp.client.Client`'s typed tool-call surface.

_Out-of-scope background (retained for the deferred `ll-queue` follow-up, Decision 2):_

- `ll-queue`'s closest cancel analog, `reset_to_pending()` (`queue_store.py:388`), is a `running`→`pending` transition (re-runnable), not a terminal cancelled state.
- PID-liveness reconciliation is independently reimplemented three times in this codebase with no shared bridge: `cli/loop/queue.py:_verify_queue_pid_identity()` (`:88`, cmdline-identity check + create_time fallback, for `ll-loop`'s file-based queue), `cli/queue.py:_verify_owner_alive()` (`:508`, same pattern, for `ll-queue`'s DB-backed queue, docstring explicitly notes it parallels but does not share code with the loop-queue version), and `fsm/persistence.py:_reconcile_stale_running()`/`_reconcile_stale_runs()` (`:243`,`:605`, liveness-only, no cmdline-identity check). No file in `scripts/little_loops/` imports both `queue_store.py` and `fsm/persistence.py` together — confirming no existing bridge reconciles the two backends' job-state conventions. This is the primary evidence for Decision 2.

### Files to Modify
- `scripts/little_loops/mcp_server/server.py` — `build_server()` (line 30) constructs the `Server` using only `on_*` keyword handlers (lines 59-80: `on_list_tools`, `on_call_tool`, `on_list_resources`, `on_read_resource`, `on_list_prompts`, `on_get_prompt`, `cache_hints`); no `add_request_handler` call exists yet, and `build_server()` is asserted unchanged by `test_build_server_signature_unchanged` in `scripts/tests/test_feat_3143_mcp_http_transport.py:67-69`.
- `scripts/little_loops/cli/loop/lifecycle.py` — extract `_status_single()`'s (`:131`) JSON-shaping logic into an importable helper decoupled from `argparse.Namespace`/`print_json`, so a `tasks/get` handler can call it directly (Decision 1 depends on reusing its reconciliation path, not reimplementing it).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/__init__.py` — module docstring states `ll-mcp` exposes "five coarse read-only tools" and describes the `main_mcp` entry point as owning only those five handlers; goes stale once a sixth, non-read-only surface (`tasks/*`) is registered [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/tests/test_mcp_server.py` — imports `build_server`, exercises tool/resource/prompt dispatch via `mcp.client.Client(server)`
- `scripts/tests/test_feat_3143_mcp_http_transport.py` — imports `build_server`, exercises `run_http()` via `starlette.testclient.TestClient` wrapping `server.streamable_http_app(...)`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status` remains the CLI caller of the extracted status helper; must keep identical output

### Conventions in Force
- Tool handlers register as one shared `on_call_tool`/`on_list_tools` pair over a module-level dict, not per-tool SDK registration — evidence: `mcp_server/tools.py` (`_TOOL_HANDLERS`, `_TOOLS`), `server.py:59-67`.
- Stateful handler indexes (resources/prompts) are built via factory functions that close over an index constructed once at `build_server()` time — evidence: `resources.py::make_list_resources_handler`/`build_resource_index`, `prompts.py` equivalent.
- No production code calls `Server.add_request_handler` or constructs `MethodBinding` today — the only call site is the learning-test harness (`.ll/learning-tests/mcp-extension-mechanism.md`, `.ll/learning-tests/raw/mcp-extension-mechanism.txt`), never `scripts/little_loops/`.
- Job-state truth differs across the two orchestration backends: `ll-queue`'s `queue_store.py` trusts its DB `status` column as written; `ll-loop`'s `fsm/persistence.py` does **not** trust its persisted `status` without a live-PID reconciliation pass (`_reconcile_stale_running`, `persistence.py:243-265`). **Settled by Decision 1** — this issue adopts the reconciled convention.
- MCP server tests skip cleanly via `pytest.importorskip("mcp")`; the stdio-equivalent path is tested through `mcp.client.Client(server)`, the HTTP path through `starlette.testclient.TestClient` wrapping `server.streamable_http_app(...)` — both files share a `_make_project(tmp_path, monkeypatch)` fixture and drive async bodies via `anyio.run(run)`, not `pytest.mark.asyncio`.

### Tests
- `scripts/tests/test_mcp_server.py` — existing coverage for tool/resource/prompt dispatch; no `tasks/*` coverage
- `scripts/tests/test_feat_3143_mcp_http_transport.py` — existing coverage for streamable HTTP transport; no `tasks/*` coverage
- No test exists in `scripts/tests/` for `Server.add_request_handler` — the only exercise of that call is the throwaway learning-test harness (`.ll/learning-tests/raw/mcp-extension-mechanism.txt`)

_Wiring pass added by `/ll:wire-issue`:_
- New test module needed, modeled on `test_feat_3143_mcp_http_transport.py`'s `_envelope()`/`_post()` raw-JSON-RPC-over-HTTP helpers (the same shape the learning test used for `tasks/get`, since `add_request_handler`-registered methods aren't reachable via `mcp.client.Client`'s typed tool-call surface) — posts `tasks/*` bodies and asserts dispatch into `run_background`/`run_foreground` primitives (mocked, given `run_background` detaches a subprocess) [Agent 3 finding]
- No existing test asserts the capabilities-response anti-goal ("do not advertise `io.modelcontextprotocol/tasks`"); a new test is needed since neither `test_build_server_signature_unchanged` nor `test_http_tools_list_matches_stdio_path` (`test_feat_3143_mcp_http_transport.py:67-69`, confirmed unaffected) covers it [Agent 2 finding] — AC 4
- New test for Decision 1: kill a background run's process without updating its state file, then assert `tasks/get` reports not-running (exercises the reconciliation path, not just the happy path) — AC 1
- Confirmed non-breaking: `test_build_server_signature_unchanged` only asserts `inspect.signature(build_server).parameters == {}`; an `add_request_handler` call added inside `build_server()`'s body does not change its parameter list, so this test keeps passing as-is [Agent 3 finding]

### Orchestration entry points a `tasks/*` handler would dispatch to
- `ll-loop run`: `cli/loop/run.py:92` `cmd_run()` → `cli/loop/_helpers.py:1510` `run_background()` (detached spawn, PID file under `<loops_dir>/.running`) or `:1677` `run_foreground()` → `fsm/persistence.py:668` `PersistentExecutor.run()` (`:960`) / `.resume()` (`:999`)
- `ll-queue`: out of scope per Decision 2

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/MCP_SERVER_GUIDE.md` — `## What ll-mcp Is` (states `ll-mcp` "exposes a little-loops project read-only") and `## Read-Only by Design` ("There is no ... way to start `ll-auto`, `ll-parallel`, `ll-loop`, or `ll-action invoke` through this server") are directly falsified by `tasks/*` shipping; `## Contents`/`## See Also` TOC needs a new entry [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-mcp` section: "exposing five coarse, read-only tools" and "no orchestration (`ll-auto`/`ll-parallel`/`ll-loop`/`ll-action invoke` are intentionally off the tool surface)" both go stale; a new subsection parallel to the existing tools/resources/prompts paragraphs is needed for `tasks/*` method shapes [Agent 2 finding]
- `docs/index.md` — line 45 guide-link summary calls it "the read-only `ll-mcp` server" [Agent 2 finding]

### Configuration
- N/A — no new config keys; transport selection is inherited from FEAT-3143's `LL_MCP_TRANSPORT`.

## Program Design

### Types
- `TasksGetParams(BaseModel)` — wire params for `tasks/get`, camelCase-aliased (`taskId`) per the learning test's proven validation path. Would be the first locally-authored Pydantic model in `scripts/little_loops/`.
- `TasksCancelParams(BaseModel)` — wire params for `tasks/cancel`; result shape carries an explicit `resumable: bool` (Decision 3).
- Start-path params: **undetermined pending Open Question 1.**

### Signatures
- `Server.add_request_handler(method: str, params_model: type[BaseModel], handler: Callable)` — proven against the unmodified `build_server()` `Server` in `.ll/learning-tests/mcp-extension-mechanism.md` (claim 4); zero call sites in `scripts/little_loops/mcp_server/` today.
- `build_server() -> Server` — `scripts/little_loops/mcp_server/server.py:30`; constructs `Server` via keyword-only `on_*` handlers (`:59-80`) with no `add_request_handler` call. `test_build_server_signature_unchanged` (`scripts/tests/test_feat_3143_mcp_http_transport.py:67-69`) asserts this function takes zero parameters — a `tasks/*` registration is additive inside the function body, not a signature change.
- `read_run_status(instance_id: str, loops_dir: Path) -> dict` — new importable helper extracted from `_status_single()` (`cli/loop/lifecycle.py:131`), preserving its `_reconcile_stale_running()` call (Decision 1) but decoupled from `argparse.Namespace`/`print_json`. `cmd_status` becomes its first caller; the `tasks/get` handler its second.
- `MethodBinding(method: str, ...)` raises `ValueError` at construction for a spec-colliding method name (e.g. `tools/call`), and `MethodBinding.protocol_versions` raises `ValueError` for an empty `frozenset` — both are `mcp` SDK behavior (2.0.0), not `little_loops` code, per the learning test's claims 1 and 5. **Claim 1 is the crux of Open Question 1.**

### Call Path
`MCP host request` -> `Server.add_request_handler`-registered `tasks/*` binding (new, inside `build_server()`) -> one of:
- poll: `read_run_status()` (new, extracted) -> `fsm/persistence.py:243 _reconcile_stale_running()` -> `StatePersistence.load_state()`
- start: `cli/loop/run.py:92 cmd_run()` -> `cli/loop/_helpers.py:1510 run_background()`
- cancel: `cli/loop/lifecycle.py:317 cmd_stop()` -> `:88 _kill_with_timeout()` -> `os.killpg(pgid, SIGTERM)`

### Decision Rules
- **Job-state truth:** always reconcile PID liveness before reporting `running` (Decision 1). No configuration toggle; the reconciled read is the only read.
- **Cancel result:** map `user_stopped` -> `{status: "cancelled", resumable: true}`, never bare `cancelled` (Decision 3).
- Method routing (which `tasks/*` method dispatches to which primitive) is the only other logic; no gates, keyword lists, or thresholds.

## Confidence Check Notes

_Consolidated 2026-08-11 — supersedes five near-identical passes run 2026-08-10
(21:19, 22:29, 22:39, 22:45, 22:49), all of which converged on the same blocker._

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 38/100 → VERY LOW

### Concerns
- **Dominant blocker: the tier-3 evidence gate is shut.** EPIC-3127
  (`.issues/epics/P3-EPIC-3127-ll-mcp-mcp-server-as-little-loops-host-agnostic-serving-layer.md`, `status: open`) still frames tier 3 as
  "built only if real usage of the first two tiers shows hosts wanting to *drive*
  runs rather than plan them." No amount of further research resolves this; five
  consecutive confidence checks re-derived the same conclusion, which is itself
  evidence that further refine cycles on this file are wasted.
- **Second blocker, newly identified 2026-08-11: tier 2 does not exist.**
  EPIC-3127's ordering is strict and tier 2 (guarded mutations) had no issue at
  all until FEAT-3149 was filed. Implementing this first would put the highest-
  blast-radius mutation on the surface before any mutation-guarding convention.
- **Third blocker: Open Question 1** — "track SEP-2663 line-by-line" and
  "respect additive-only method naming" may be mutually incompatible for the
  start path, which would collapse this issue's core value proposition. Needs a
  spike, not a refine pass.
- Both original `depends_on` entries (`FEAT-3143`, `ENH-3144`) are `status: done`
  — the mechanical dependency blocker from earlier passes is resolved. The
  remaining blockers are product-level and design-level, not file dependencies.
- `## Program Design` is populated and `ll-issues check-design FEAT-3145` passes.

### Resolved since prior passes
- Job-state-truth convention — settled by Decision 1 (was the top ambiguity
  driver across all five prior passes).
- Two-backend scope — settled by Decision 2 (`size` reduced Large → Medium).
- Cancel semantics mismatch — settled by Decision 3.
- Missing `Impact` and `Use Case` sections — added; `format-check` should now
  pass.
- Acceptance Criteria — now individually testable, though provisional pending
  Open Question 1.

### Outcome Risk Factors
- No test coverage exists for the `tasks/*` handlers themselves — only the
  underlying `add_request_handler` mechanism, via the throwaway learning-test
  harness, not `scripts/tests/`.
- Open Question 2 (unauthenticated run-start over the FEAT-3143 HTTP transport)
  is a security-shaped gap that overlaps tier 2's per-method transport policy.
- SEP-2663 fidelity has no automated enforcement; AC 6 downgrades this to a
  human-checkable annotation convention rather than pretending otherwise.

## Status

**Open (gated)** | Created: 2026-08-10 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-08-10T22:49:20 - `56906449-2ef0-4f25-9e4c-8ae68ff20b20.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T22:47:32 - `235c9a55-26d5-4bf5-8282-d66bd8adfad6.jsonl`
- `/ll:confidence-check` - 2026-08-10T22:45:10 - `ed060967-353b-47f3-b2e8-b9977e6cbc11.jsonl`
- `/ll:decide-issue` - 2026-08-10T22:41:50 - `3ea41e32-6eb5-4927-b998-ff2ec848f75a.jsonl`
- `/ll:confidence-check` - 2026-08-10T22:39:42 - `2f71e447-73c1-44c6-bc93-86a3674fc9b9.jsonl`
- `/ll:refine-issue` - 2026-08-10T22:34:16 - `b34f73de-22c6-45b5-bec4-6064ae28ac66.jsonl`
- `/ll:confidence-check` - 2026-08-10T22:29:02 - `21855423-8259-44f2-9bd4-78c7dd650aeb.jsonl`
- `/ll:verify-issues` - 2026-08-10T22:26:08 - `9016214d-62b4-4804-be57-478b5d383061.jsonl`
- `/ll:wire-issue` - 2026-08-10T22:24:02 - `14d7d2ef-ea03-4364-9bda-498c5d093a41.jsonl`
- `/ll:refine-issue` - 2026-08-10T22:17:51 - `983f5e90-2a6f-4bec-b11d-ab095983715b.jsonl`
- `/ll:confidence-check` - 2026-08-10T21:19:52 - `c399e98c-b001-4568-9896-227421406281.jsonl`
