---
id: FEAT-3151
type: FEAT
title: "ll-mcp: SEP-2663 start path \u2014 tools/call materializes a task and starts\
  \ an ll-loop run (tier-3, evidence-gated)"
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-08-11'
captured_at: '2026-08-11T23:07:21Z'
parent: EPIC-3127
labels:
- multi-host
- mcp
learning_tests_required:
- mcp extension mechanism
- mcp tasks start path
depends_on:
- FEAT-3145
relates_to:
- FEAT-3143
- FEAT-3145
- FEAT-3149
size: Medium
testable: true
deferred_by: automation
deferred_date: '2026-08-12T01:10:28Z'
deferred_reason: blocked_by_gate
---

# FEAT-3151: ll-mcp: SEP-2663 start path — tools/call materializes a task and starts an ll-loop run (tier-3, evidence-gated)

## ⚠ Gated — this is the half the tier-3 evidence gate exists to hold back

EPIC-3127: long-running orchestration is "built only if real usage of the first
two tiers shows hosts wanting to *drive* runs rather than plan them," and "until
that evidence exists, anything that spawns an agent or runs for minutes stays off
the tool surface by design."

FEAT-3145 (poll + stop) deliberately spawns nothing, so it sits inside that
sentence. **This issue does not.** Implementing it requires the gate to have
opened, and EPIC-3127 amended to record that it did and on what evidence.

## Summary

Add the SEP-2663 start path to `ll-mcp`: a `tools/call` that materializes a
task — returning `CreateTaskResult` (`resultType: "task"`) instead of a
`CallToolResult` — and starts a detached `ll-loop` run, so an MCP host can begin
a run without the request itself being long-running.

Split out of **FEAT-3145** (2026-08-11), which ships the `tasks/get` /
`tasks/cancel` poll-and-stop half plus the transport policy gate both halves sit
behind. The split is safe because the start path is a `tools/call` *augmentation*
and re-registers nothing FEAT-3145 registers — proven below.

**Scope: `ll-loop` runs only.** `ll-queue` is out of scope, inherited from
FEAT-3145's Decision 2.

## Current Behavior

`ll-mcp` serves tier-1 read-only tools plus FEAT-3149's four guarded mutation
tools. Orchestration (`ll-auto`, `ll-parallel`, `ll-loop`, `ll-action invoke`) is
deliberately absent — correctly, since a tool call that runs for minutes does not
fit the tools primitive. Once FEAT-3145 lands, a host can poll and stop an
`ll-loop` run it did not start; there is still no way to start one.

## Expected Behavior

Calling a designated run tool over `tools/call` — from a client that has declared
the tasks extension — starts a detached `ll-loop` run and returns immediately with
a `CreateTaskResult` whose task id is the run's `instance_id`, pollable through
FEAT-3145's `tasks/get` and stoppable through its `tasks/cancel`.

A client that has **not** declared the extension gets ordinary `tools/call`
behavior, never a task-shaped result.

## Use Case

The FEAT-3145 use case, completed: a developer polling a workstation run from a
phone-side agent or a second Claude Code session can now also *start* the run
from there — `ll-loop run rn-refine` against a specific issue — without SSH-ing to
the workstation and without the MCP call hanging for the twenty minutes the loop
takes.

## Motivation

FEAT-3145 delivers two thirds of the "start, poll, cancel" triple EPIC-3127's
tier 3 describes. This is the remaining third and the one with real leverage:
polling a run you had to start by other means is useful but awkward; starting,
polling, and stopping from one surface is the actual capability.

It is separated rather than merged because it carries all of the tier's risk —
it is the only part that spawns an agent, the only part whose result shape is
spec-sensitive, and the only part that cannot ship before the evidence gate
opens.

## Proven by learning test — the mechanism works

[`.ll/learning-tests/mcp-tasks-start-path.md`](../../.ll/learning-tests/mcp-tasks-start-path.md)
— 11/11 claims pass against the pinned `mcp==2.0.0` over streamable HTTP.

**SEP-2663's start is an augmentation of `tools/call`, not a new method.** The
spec's own example request is a *completely ordinary* `tools/call` body; the
client signals support via per-request capabilities and the server decides per
request whether to materialize a task. The augmentation is **on the response**:
the server returns `CreateTaskResult` (`resultType: "task"`) in lieu of a
`CallToolResult`.

`ll-mcp` already *owns* its `tools/call` handler (`on_call_tool=handle_call_tool`,
`mcp_server/server.py:63`). Nothing is re-registered, so `MethodBinding`'s
additive-only naming boundary is never engaged — that was only ever a constraint
on *registering* a spec method name, which this does not do. This is also why the
FEAT-3145 split is safe: the two issues touch disjoint registration surfaces.

Three independently sufficient mechanisms, all proven on the lowlevel `Server`:

1. **Return a task-shaped `Mapping` from `handle_call_tool`.** `runner._serialize`
   (`runner.py:364-378`) skips the spec-method sieve whenever `resultType` is a
   modern-era string outside `CORE_RESULT_TYPES` (`{'input_required','complete'}`)
   — extension-owned shapes are passed through by design, not by accident.
   `_dump_result` accepts `BaseModel | dict | None`, so a raw mapping works at
   runtime despite the `CallToolResult | InputRequiredResult` annotation.
2. **`compose_tool_call_handler([TasksExtension()], handle_call_tool)`** — the
   extension-faithful path. A *free function*, so it works on the lowlevel
   `Server` even though that class has no `extensions=` parameter (which is what
   [[mcp-extension-mechanism]] claim 3 established).
3. **`Server.middleware`**, for wire-level rewriting above params validation.

## Decisions

### Decision 1 — Use `compose_tool_call_handler` (mechanism 2)

**Why:** it is the extension-faithful path, so swapping to the official
`io.modelcontextprotocol/tasks` extension when an SDK ships one becomes a
registration change rather than a client-visible protocol change — which is the
entire value proposition FEAT-3145 and this issue inherit from EPIC-3127.

Mechanism 1 works but leans on `_dump_result` accepting a shape its type
annotation does not advertise; mechanism 3 rewrites at the wire level, below the
abstraction the rest of the server is written against.

### Decision 2 — Gate task materialization on the client's declared extension

`runner.py:370` carries a `TODO(L56)` to reject extension `resultType` values
unless the matching extension is present in the request's
`_meta.clientCapabilities.extensions`. Emitting `resultType: "task"` *without*
honoring the client's declared capabilities passes today but is
forward-incompatible — when that TODO is implemented upstream, an ungated
implementation breaks.

It is also what SEP-2663 requires: "the client signals support ... the server
decides."

**This is a client-side declaration check and is deliberately separate from
FEAT-3145's anti-goal against server-side advertisement of the extension.** The
server does not claim the extension in its capabilities response; it does honor
the client's claim. Neither should be "fixed" by breaking the other.

### Decision 3 — Task id is the `ll-loop` `instance_id`

Inherited from FEAT-3145 Decision 5, and load-bearing here: the id returned in
`CreateTaskResult` must be exactly what `tasks/get` accepts, or the start/poll
pair does not compose. No separate handle registry.

### Decision 4 — The start tool is gated by the same `allow_tasks` policy

Reuses FEAT-3145 Decision 4/6's `mcp.transport_policy.{http,stdio}.allow_tasks`
rather than adding a third grant. Starting and stopping a run are the same
class of authority over the same resource; an operator who has enabled `tasks/*`
over HTTP has consented to run control.

Open sub-question for implementation: whether the start tool *also* belongs in
`MUTATING_TOOLS` (`policy.py:55`) so it additionally inherits the dry-run-by-
default `apply: true` convention. Resolve during implementation — the argument
for is that spawning an agent is the largest-blast-radius write on the surface;
the argument against is that a dry-run "start" has no coherent meaning.

## Anti-goals

- Do not advertise `io.modelcontextprotocol/tasks` in the capabilities response
  (inherited from FEAT-3145; EPIC-3127 open question 4).
- Do not invent a `tasks/start` method. SEP-2663 has no such method and adding
  one forfeits the swap-to-official-extension property.
- Do not turn `ll-auto` / `ll-parallel` into tools as a side effect. One start
  tool, `ll-loop` only.
- Do not add `ll-queue` dispatch (FEAT-3145 Decision 2).

## Dependencies

- **FEAT-3145** (open) — supplies `tasks/get` / `tasks/cancel`, the
  `allow_tasks` transport policy, and the `taskId` == `instance_id` convention.
  A start path without a poll path returns a handle nothing can read.
- **FEAT-3149** (done) — the `MUTATING_TOOLS` / dry-run convention Decision 4's
  sub-question refers to.
- **FEAT-3143** (done) — HTTP transport.
- **EPIC-3127 tier-3 evidence gate** — not a file dependency, and not closable by
  refinement. See the header note.

## Acceptance Criteria

1. A `tools/call` naming the start tool, from a client that declares the tasks
   extension in `_meta.clientCapabilities.extensions`, returns a result with
   `resultType: "task"` and a task id equal to the started run's `instance_id`.
2. The same call from a client that does **not** declare the extension returns an
   ordinary `CallToolResult` — never a task-shaped result (Decision 2). Asserted
   as a distinct test, since this is the forward-compatibility property that
   `runner.py:370`'s `TODO(L56)` will later enforce upstream.
3. The call returns within normal request latency; the `ll-loop` run continues
   after the response is sent — asserted by confirming the request completes
   while the spawned process is still alive.
4. The task id returned by AC 1 is accepted by FEAT-3145's `tasks/get` and
   resolves to the same run (Decision 3) — an integration test across both
   issues, not two isolated unit tests.
5. The start tool is denied over HTTP when
   `mcp.transport_policy.http.allow_tasks` is `false` (the default), with the
   same `-32001` / HTTP 403 shape as FEAT-3145's `tasks/*` denials (Decision 4).
6. `initialize`'s capabilities response does **not** contain the string
   `io.modelcontextprotocol/tasks`, unchanged from FEAT-3145 AC 10.
7. The `compose_tool_call_handler` composition preserves existing `tools/call`
   behavior for every tier-1 and tier-2 tool — asserted by the existing
   `test_mcp_server.py` and `test_feat_3149_transport_policy.py` suites passing
   unmodified.
8. Each method name and result field is annotated in code with the SEP-2663
   construct it mirrors, so the later swap to the official extension is
   mechanically checkable by a human (inherited from FEAT-3145 AC 13).
9. `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` — add the start tool to `_TOOLS` /
  `_TOOL_HANDLERS`, following the existing shared-dispatch convention (one
  `on_call_tool` pair over a module-level dict, not per-tool SDK registration).
- `scripts/little_loops/mcp_server/server.py` — wrap `handle_call_tool` in
  `compose_tool_call_handler([...])` at the `on_call_tool=` site (`:63` region,
  inside `build_server()` at `:52`). Additive; `test_build_server_signature_unchanged`
  (`test_feat_3143_mcp_http_transport.py:67-69`) keeps passing.
- `scripts/little_loops/mcp_server/policy.py` — Decision 4 sub-question only:
  whether the start tool joins `MUTATING_TOOLS` (`:55`). The `allow_tasks` gate
  itself arrives with FEAT-3145 and needs no further change here.
- `scripts/little_loops/cli/loop/_helpers.py` / `cli/loop/run.py` — likely need an
  importable start entry point decoupled from `argparse`, mirroring FEAT-3145's
  `read_run_status()` extraction from `_status_single()`. `run_background()`
  (`_helpers.py:1510`) already returns immediately with `instance_id`/PID/log
  path, so the shape is right; the coupling to `cmd_run()`'s
  `argparse.Namespace` (`run.py:92`) is the work.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_mcp_server.py` — exercises `tools/call` dispatch via
  `mcp.client.Client(server)`; must keep passing unmodified (AC 7).
- `scripts/tests/test_feat_3149_transport_policy.py` — exercises the policy
  middleware; must keep passing unmodified (AC 7).

### Similar Patterns
- FEAT-3149's four mutation tools are the model for adding a tool to the shared
  dispatch dict, including the `apply: true` dry-run guard (`tools.py:735-773`)
  relevant to Decision 4's sub-question.
- FEAT-3145's `read_run_status()` extraction is the model for decoupling a
  `cli/loop/` entry point from `argparse.Namespace`.

### Tests
- New test module `test_feat_3151_mcp_start_path.py` (to be created under the `scripts/tests/` dir), modeled on
  `test_feat_3143_mcp_http_transport.py`'s `_envelope()`/`_post()` raw-JSON-RPC
  helpers — the declared-vs-undeclared client capability distinction (AC 2)
  requires control over `_meta`, which `mcp.client.Client`'s typed surface does
  not expose.
- `run_background()` detaches a real subprocess. Tests should either mock it
  (unit) or start a trivially-terminating loop and reap it (integration); AC 3
  specifically needs the un-mocked path to be meaningful.
- AC 4 is a cross-issue integration test and should live in whichever module
  ends up owning the `tasks/get` fixtures from FEAT-3145.

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — `## Read-Only by Design`'s claim that
  "There is no ... way to start `ll-auto`, `ll-parallel`, `ll-loop`, or
  `ll-action invoke` through this server" survives FEAT-3145 verbatim but is
  **directly falsified by this issue**. Needs rewriting, not amending.
- `docs/reference/CLI.md` — `### ll-mcp` section: the "no orchestration ...
  intentionally off the tool surface" claim likewise.
- `docs/index.md` — line 45's "the read-only `ll-mcp` server" summary.

### Configuration
- No new keys. Reuses `mcp.transport_policy.{http,stdio}.allow_tasks` introduced
  by FEAT-3145 (Decision 4).

## Implementation Steps

1. Extract an importable `ll-loop` start entry point from `cmd_run()`, decoupled
   from `argparse.Namespace`, returning `instance_id` immediately.
2. Add the start tool to `tools.py`'s dispatch dict; settle Decision 4's
   `MUTATING_TOOLS` sub-question.
3. Wrap `handle_call_tool` in `compose_tool_call_handler`, gating task
   materialization on the client's declared extension (Decision 2).
4. Verify: ACs 1-3 and 5 in the new test module, AC 4 as a cross-issue
   integration test, AC 7 by running the existing suites unmodified.

## Program Design

### Types
- `CreateTaskResult` — the SDK's own SEP-2663 result model (`resultType: "task"`), returned in lieu of `CallToolResult`. Consumed from the `mcp` package rather than hand-authored, matching the existing convention of reusing the SDK's wire models (`mcp_server/tools.py` imports `mcp_types as types` for `types.Tool` / `types.CallToolRequestParams`).
- The start tool's input schema is a plain JSON-schema `dict` on a `types.Tool`, following FEAT-3149's four mutation tools — not a locally-authored `BaseModel`. (FEAT-3145 introduces `TasksGetParams(BaseModel)` because `add_request_handler` requires a params model; `tools/call` does not.)

### Signatures
- `compose_tool_call_handler(extensions: list, handler: Callable) -> Callable` — free function from the `mcp` SDK (2.0.0), proven in [[mcp-tasks-start-path]] to work on the lowlevel `Server` despite that class having no `extensions=` parameter. Zero call sites in `scripts/little_loops/` today.
- `handle_call_tool(...)` — `scripts/little_loops/mcp_server/tools.py`; the existing shared `on_call_tool` dispatcher, wrapped rather than replaced (Decision 1).
- `build_server() -> Server` — `scripts/little_loops/mcp_server/server.py:52`; the `on_call_tool=` argument (`:63` region) changes from `handle_call_tool` to the composed handler. Zero-parameter signature unchanged, so `test_build_server_signature_unchanged` (`test_feat_3143_mcp_http_transport.py:67-69`) keeps passing.
- `run_background(...) -> tuple[str, int, Path]` — `scripts/little_loops/cli/loop/_helpers.py:1510`; already returns immediately with `instance_id` / PID / log path, which is exactly the handle `CreateTaskResult` needs. The work is decoupling its `cmd_run()` caller (`cli/loop/run.py:92`) from `argparse.Namespace`, mirroring FEAT-3145's `read_run_status()` extraction.
- `check_tool_call(transport, method, tool_name, *, config=None) -> PolicyDecision` — `mcp_server/policy.py:78-120`, as widened by FEAT-3145 Decision 4. This issue adds the start tool to whatever registry that widened guard consults; no further signature change (Decision 4 sub-question: whether it also joins `MUTATING_TOOLS`, `policy.py:55`).

### Call Path
`MCP host tools/call` -> (HTTP only) `TransportPolicyMiddleware` -> `check_tool_call()` — deny returns `-32001` / 403 before the body is read -> `compose_tool_call_handler([TasksExtension()], handle_call_tool)` -> branch on the client's declared extension in `_meta.clientCapabilities.extensions`:
- declared: materialize a task -> extracted `ll-loop` start entry point -> `cli/loop/_helpers.py:1510 run_background()` (detached spawn, PID file under `<loops_dir>/.running`) -> return `CreateTaskResult(taskId=instance_id)`
- not declared: fall through to the unmodified `handle_call_tool` -> ordinary `CallToolResult`

The returned `instance_id` is subsequently readable via FEAT-3145's `tasks/get` -> `read_run_status()` -> `fsm/persistence.py:243 _reconcile_stale_running()`.

### Decision Rules
- **Materialize a task iff the client declared the extension** (Decision 2). Undeclared clients get unmodified `tools/call` behavior; never emit `resultType: "task"` unilaterally.
- **Task id is the `instance_id` verbatim** (Decision 3). No handle registry, no mapping table — this is what makes the id returned here valid input to FEAT-3145's `tasks/get`.
- **Transport policy reuses `allow_tasks`** (Decision 4), not a third config grant.
- No other branching: one start tool, `ll-loop` only, no `ll-queue`.

## Impact

- **Priority**: P3 — inherits FEAT-3145's gating and adds its own; nothing here
  is urgent.
- **Effort**: Medium — the mechanism is fully proven (11/11 learning-test claims)
  and the composition point is a single call site, but the `cmd_run()` extraction
  is real work and the declared-capability plumbing has no precedent in the
  package.
- **Risk**: Medium-High — this is the only code path on the MCP surface that
  spawns an agent with the project's full tool permissions. The transport gate
  (FEAT-3145 Decision 4) is what makes that acceptable, which is precisely why
  this issue `depends_on` FEAT-3145 rather than shipping alongside it.
- **Breaking Change**: No — additive tool plus a handler composition; existing
  `tools/call` behavior is unchanged for every existing tool (AC 7).

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 3 (job API), evidence-gated. **The gate has not fired.**

## Related Key Documentation

- [`docs/guides/MCP_SERVER_GUIDE.md`](../../docs/guides/MCP_SERVER_GUIDE.md)
- [`docs/reference/CLI.md`](../../docs/reference/CLI.md)
- [`.ll/learning-tests/mcp-tasks-start-path.md`](../../.ll/learning-tests/mcp-tasks-start-path.md)
- [`.ll/learning-tests/mcp-extension-mechanism.md`](../../.ll/learning-tests/mcp-extension-mechanism.md)

## Status

**Open** — EPIC-3127's tier-3 evidence gate has not fired, and FEAT-3145 is a prerequisite | Created: 2026-08-11 | Priority: P3
