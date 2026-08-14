---
id: FEAT-3151
type: FEAT
title: "ll-mcp: SEP-2663 start path \u2014 tools/call materializes a task and starts\
  \ an ll-loop run (tier-3, evidence-gated)"
priority: P3
status: open
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
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3151: ll-mcp: SEP-2663 start path — tools/call materializes a task and starts an ll-loop run (tier-3, evidence-gated)

## ✅ Gate opened 2026-08-11 — cleared to implement

The title and filename still carry "evidence-gated" for ID stability; the gate
itself is **open**.

EPIC-3127's tier-3 rule originally held that long-running orchestration is
"built only if real usage of the first two tiers shows hosts wanting to *drive*
runs rather than plan them." That rule was amended in place on 2026-08-11:

> **Gate opened 2026-08-11, by product decision, not observed usage.** … The
> gate is opened anyway on an explicit call: job control over MCP
> (start/poll/stop) is 100% aligned to and required by product strategy … Both
> FEAT-3145 (poll/cancel) and FEAT-3151 (start path) are cleared to implement.

The amendment explicitly does **not** relax anything else: this issue still owes
the client-capability gate on task materialization (Decision 2), and FEAT-3145's
transport-policy gate (Decision 4) still applies.

**Prerequisites are all satisfied** as of 2026-08-14: FEAT-3145, FEAT-3149, and
FEAT-3143 are `done`. Nothing blocks implementation.

## Summary

Add the SEP-2663 start path to `ll-mcp`: a `tools/call` that materializes a
task — returning a task-shaped result (`resultType: "task"`) instead of a
`CallToolResult` — and starts a detached `ll-loop` run, so an MCP host can begin
a run without the request itself being long-running.

(On the pinned SDK the task-shaped result is hand-built, *not*
`types.CreateTaskResult`; see Decision 5 — that model dumps to `{"task": {...}}`
with no `resultType` key and would fail the spec-method sieve.)

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
fit the tools primitive. FEAT-3145 shipped, so a host can now poll and stop an
`ll-loop` run it did not start (`tasks/get` / `tasks/cancel`,
`mcp_server/tasks.py`); there is still no way to start one.

## Expected Behavior

Calling a designated run tool over `tools/call` — from a client that has declared
the tasks extension **and asked for task-augmented execution on this call** —
starts a detached `ll-loop` run and returns immediately with a task-shaped result
whose task id is the run's `instance_id`, pollable through FEAT-3145's
`tasks/get` and stoppable through its `tasks/cancel`.

A client that has not declared the extension — or that declared it but did not
set `params.task` on this call — gets ordinary `tools/call` behavior, never a
task-shaped result. Both conditions are required (Decision 2).

**The plain path still starts the run.** `run_background()` is detach-and-return
regardless of caller, so the non-task path performs the identical detached spawn
and returns a normal `CallToolResult` carrying the `instance_id` in its payload.
The task/plain distinction is about **result shape only**, never about whether
the run starts — a legacy or non-tasks client can still start runs (subject to
the same transport policy) and poll by other means (Decision 2a).

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
it is the only part that spawns an agent, and the only part whose result shape is
spec-sensitive.

## Proven by learning test — the mechanism works

[`.ll/learning-tests/mcp-tasks-start-path.md`](../../.ll/learning-tests/mcp-tasks-start-path.md)
— 6 recorded claims (11/11 raw checks), all pass, against the pinned `mcp==2.0.0`
over streamable HTTP. **What it does *not* cover:** the client-capability read
that Decision 2 depends on — its `TasksExtension` materializes unconditionally.

**SEP-2663's start is an augmentation of `tools/call`, not a new method.** The
spec's own example request is a *completely ordinary* `tools/call` body; the
client signals support via per-request capabilities and the server decides per
request whether to materialize a task. The augmentation is **on the response**:
the server returns a task-shaped result (`resultType: "task"`) in lieu of a
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

### Decision 2 — Gate task materialization on **two** signals: declared capability *and* per-call request

**Both conditions must hold. Capability says *can*; `params.task` says *wants*.**

1. **Capability.** `runner.py:370` carries a `TODO(L56)` to reject extension
   `resultType` values unless the matching extension is present in the request's
   `_meta.clientCapabilities.extensions` (wire key
   `io.modelcontextprotocol/clientCapabilities`, exposed to handlers as
   `ctx.meta` — a `RequestParamsMeta` open `TypedDict`). Emitting
   `resultType: "task"` without honoring the client's declared capabilities
   passes today but is forward-incompatible — when that TODO is implemented
   upstream, an ungated implementation breaks.

2. **Per-call opt-in.** `types.CallToolRequestParams` already carries
   `task: TaskMetadata | None` — the SDK's own docstring: *"If specified, the
   caller requests task-augmented execution."* This is the signal the client uses
   to ask for a task *on this call*.

Gating on capability alone (the original framing of this decision) would mean
every ordinary call to the start tool from a tasks-capable client silently
becomes a task, with no way for that client to make a plain blocking call. That
is wrong on the spec's own terms, so the rule is the conjunction.

**Both are client-side checks and are deliberately separate from FEAT-3145's
anti-goal against server-side advertisement of the extension.** The server does
not claim the extension in its capabilities response; it does honor the client's
claim. Neither should be "fixed" by breaking the other.

### Decision 2a — Plain-path semantics: same spawn, plain result shape

When any gating condition is absent (no declared capability, no `params.task`,
or a legacy protocol version), the start tool **still performs the identical
detached `run_background()` spawn** and returns an ordinary `CallToolResult`
whose payload carries the `instance_id`. It does not refuse, and it never runs
the loop synchronously — `run_background()` returns immediately by construction,
so there is no blocking variant to offer.

This is what makes Decision 2's own rationale coherent (a tasks-capable host
"making a plain call" still gets work done) and what AC 2c's
legacy-client-gets-no-error requirement implies. ACs 2/2b/2c are therefore
assertions about **result shape**, not about whether a run starts.

**Implementation note:** the cleanest composition is for the start tool's
`_TOOL_HANDLERS` entry to always spawn and return the plain payload, with the
local tasks extension's `intercept_tool_call` merely **re-shaping** that result
into the task-shaped mapping when all three conditions hold — rather than
duplicating the spawn logic in the interceptor. Two mechanics that note glosses
over, made explicit:

- **Extraction:** the interceptor reads the `instance_id` from the plain
  result's `structured_content` — `handle_call_tool` always attaches the
  payload dict there (`tools.py:786-789`), so no text-JSON parsing of
  `content[0].text` is needed or acceptable.
- **Error pass-through:** a result with `is_error=True` (spawn failure, AC 3b)
  passes through **un-reshaped**. Never wrap a failure in a task envelope —
  that is exactly the "task id for a run that does not exist" Decision 7
  forbids.

**Scoping:** `compose_tool_call_handler` wraps **all** `tools/call` traffic,
not just the start tool. The interceptor's first check is
`params.name == <start tool>`; anything else calls `call_next` untouched. A
tasks-capable client setting `params.task` on `issues_query` must get ordinary
`issues_query` behavior — this check is what keeps AC 7 true for every
existing tool.

**Unproven step — the only one in this issue.** The learning test's
`TasksExtension` materializes *unconditionally*; nothing has verified that
`ctx.meta["io.modelcontextprotocol/clientCapabilities"]` actually arrives
populated on a real 2026-07-28 request. `RequestParamsMeta` is an open TypedDict,
so the read is plausible but untested — and ACs 1, 2, and 2b all hinge on it.
See Implementation Step 0.

**`ctx.meta` is `Optional` — guard the read.** Verified on the pinned SDK:
`ServerRequestContext.meta` is `RequestParamsMeta | None = None`, so the naive
`ctx.meta.get(...)` raises `AttributeError` on any request carrying no `_meta`
— which is precisely the AC 2 path. The read must be
`(ctx.meta or {}).get(types.CLIENT_CAPABILITIES_META_KEY)`, and Step 0's
learning-test extension must cover both arms: meta populated for a declaring
client *and* `None`/absent for a plain one.

### Decision 3 — Task id is the `ll-loop` `instance_id`

Inherited from FEAT-3145 Decision 5, and load-bearing here: the id returned in
the task-shaped result must be exactly what `tasks/get` accepts, or the
start/poll pair does not compose. No separate handle registry.

The clean seam already exists: `run_background()` takes
`instance_id: str | None = None` and only calls `_make_instance_id()` when it is
omitted. The MCP layer mints the id itself, passes it in, and therefore knows the
handle without `run_background` needing to return it (see Decision 7).

**Mint with entropy — do not reuse `_make_instance_id()`'s format verbatim.**
`_make_instance_id()` returns `f"{loop_name}-%Y%m%dT%H%M%S"` — one-second
resolution. Human-paced CLI use cannot collide; an MCP agent issuing two starts
of the same loop inside one second (with disjoint scopes, so the scope-conflict
pre-flight does not reject the second) mints the same instance_id — colliding
PID/state/log files under `.running/` and an ambiguous task handle. Decision 3
requires taskId == instance_id *verbatim*, not any particular format, so the
MCP boundary mints its own id with a short entropy suffix (e.g.
`{loop_name}-%Y%m%dT%H%M%S-{4 hex chars}`) or check-and-bumps against
`.running/`. `StatePersistence` resolves paths from `instance_id` alone, so any
unique string composes with `tasks/get` unchanged.

### Decision 4 — The start tool is gated by the same `allow_tasks` policy

Reuses FEAT-3145 Decision 4/6's `mcp.transport_policy.{http,stdio}.allow_tasks`
rather than adding a third grant. Starting and stopping a run are the same
class of authority over the same resource; an operator who has enabled `tasks/*`
over HTTP has consented to run control.

**Sub-question resolved: no, the start tool does *not* join `MUTATING_TOOLS`.**
A dry-run "start" has no coherent meaning, and joining that set would make
`handle_call_tool`'s guard 1 refuse to dispatch without `apply: true` for no
gain. Use a separate registry keyed to `allow_tasks` instead — see Decision 8,
which is real work this issue owns.

### Decision 5 — Hand-shape the task result; do not return `types.CreateTaskResult`

Checked against the pinned `mcp==2.0.0`:

```python
CreateTaskResult(task=Task(...)).model_dump(by_alias=True, exclude_none=True)
# → {'task': {'taskId': 'x', 'status': 'working', 'createdAt': ..., 'lastUpdatedAt': ...}}
```

No `resultType` key at all, and `taskId` is nested under `task` rather than
top-level. That breaks the passthrough this whole issue rests on:
`runner._serialize` skips the spec-method sieve **only** when `resultType` is a
modern-era string outside `CORE_RESULT_TYPES`. `tools/call` *is* in
`SPEC_CLIENT_METHODS`, so a dump with no `resultType` goes to
`serialize_server_result` and fails `CallToolResult` validation.

So: return a hand-built `Mapping` carrying top-level `resultType: "task"` and
`taskId` — exactly the `TASK_SEED` shape the learning test proved — and reference
`types.Task` / `types.CreateTaskResult` only for field naming and the AC-8
annotations. This matches what FEAT-3145 already does: `mcp_server/tasks.py`
returns hand-built dicts, not `types.GetTaskResult`.

**Field-set consistency with `tasks/get` — scoped to the task-core fields.**
FEAT-3145's `handle_tasks_get` returns `{taskId, status, runStatus, …}` with no
`createdAt` / `lastUpdatedAt` / `ttl`, while `types.Task` requires them. Start
and get must not disagree about what a task looks like — but "identical field
sets" is unachievable by construction: `tasks/get` for a terminal run adds
`runStatus` plus the reconstructed `ExecutionResult` fields (`final_state`,
`iterations`, `terminated_by`, `duration_ms`, `captured`), which a just-started
task can never carry, and the runner stamps different `resultType` envelopes on
the two methods (`"task"` vs `"complete"`). The consistency contract is
therefore: the **shared task-core fields — `taskId` and `status` — agree in
name, casing, and value vocabulary** for the same working run; get-side run
detail and envelope keys are explicitly excluded (AC 4b).

**Era mismatch — largely resolved by Decision 6's pinning.** Every SDK task type
(`Task`, `CreateTaskResult`, `TaskMetadata`, `ClientTasksCapability`, …) is
docstring-tagged **"2025-11-25 only"**, while EPIC-3127 targets **2026-07-28**,
where the client signal moved to `ClientCapabilities.extensions`. Decision 6
settles the runtime side: the task path only ever triggers on modern
(2026-07-28, per-request-envelope) connections, where the capability envelope
exists — so the 2025-11-25-tagged SDK models are irrelevant at runtime, which
confirms hand-shaping. Residual rule: take field names from SEP-2663 rather
than from the SDK models wherever the two disagree.

### Decision 6 — Protocol-version guard

`runner._serialize`'s comment is explicit: *"Legacy connections sieve everything
— claimed shapes are 2026-era vocabulary and cannot be delivered on a legacy
wire."* A client on a pre-modern `protocolVersion` must therefore fall through to
the ordinary `CallToolResult` path, never receive an error. `ctx.protocol_version`
carries what is needed.

**"Modern" is pinned, not vibes:** the check is
`ctx.protocol_version in mcp.server.runner.MODERN_PROTOCOL_VERSIONS`, which on
the pinned SDK is exactly `{"2026-07-28"}`. Modern connections are the
per-request-envelope kind — no `initialize` handshake at all — and only they
carry the `clientCapabilities` `_meta` envelope Decision 2 reads.

**Consequence for tests (stronger than the `_meta`-control rationale below):**
`tools.py`'s own comment (`:780` region) records that `mcp==2.0.0`'s typed
`mcp.client.Client` negotiates the legacy handshake down to 2025-11-25 even when
asking for 2026-07-28 — so **the typed client can never reach the task path at
all**. The raw `_envelope()`/`_post()` helpers are not merely convenient for
controlling `_meta`; they are the *only* way to open a modern connection.

### Decision 7 — How to cross the `argparse` boundary into `run_background()`

`run_background()` (`_helpers.py:1510`) is **not** the clean entry point earlier
drafts of this issue assumed. It takes `args: argparse.Namespace` and forwards
~30 fields through `getattr(args, ...)` when building the child command line; it
returns an **`int` exit code**, not a handle.

Two options, and the issue must pick one because the effort estimate depends on
it:

- **(a) `SimpleNamespace` at the MCP boundary** — construct a namespace carrying
  only the fields the start tool exposes and hand it to `run_background()`
  unchanged. Cheap, honest about the coupling, no churn in `cli/loop/`. **This is
  the recommended option** and the one "Medium" effort assumes.
- **(b) Real extraction** — a keyword-argument entry point that `cmd_run()` also
  routes through. Cleaner long-term, materially more work and more regression
  surface across every existing `ll-loop run` flag.

Either way, the handle comes from Decision 3's pre-minted `instance_id`, not from
a changed return type.

**Failure mapping (not optional).** `run_background()` returns `1` *before
spawning* on a scope conflict and on a loop load/parse failure. A non-zero return
must become a tool error, never a task id for a run that does not exist —
otherwise the host polls a handle that will never resolve. AC 3b covers this.

### Decision 8 — `check_tool_call` needs a third branch; FEAT-3145 did not add one

`policy.check_tool_call` (`policy.py:78`) gates exactly two things today:
`tools/call` naming a member of `MUTATING_TOOLS`, and any method whose name
starts with `tasks/`. The start tool is a `tools/call` and matches neither, so
**AC 5 is not satisfied by anything FEAT-3145 shipped** — earlier drafts of this
issue claimed the guard had been "widened" and that no registry change was
needed. It had not, and there is no such registry.

Add a `TASK_STARTING_TOOLS` frozenset alongside `MUTATING_TOOLS` and a third
branch that gates `tools/call` naming one of its members on
`allows_tasks(transport)`, reusing the existing `-32001` / 403 denial shape. The
HTTP path already routes on the `Mcp-Name` header, so
`TransportPolicyMiddleware` needs no change beyond what `check_tool_call`
returns.

**stdio enforcement is a known, pre-existing gap — accepted here, explicitly.**
`check_tool_call` has exactly **one call site** in the package: the HTTP-only
`TransportPolicyMiddleware` (`policy.py:176`). Over stdio there is no middleware
and the handlers never invoke the policy themselves, so
`mcp.transport_policy.stdio.allow_tasks: false` (and equally
`stdio.allow_mutations: false`) is silently unenforced today for `tasks/*` and
the mutation tools — and would be for the start tool. This issue **does not fix
that**: enforcing stdio policy properly requires plumbing transport identity
into `build_server()`'s handlers, which is a cross-cutting change owed equally
to FEAT-3145's and FEAT-3149's surfaces, not something to half-do for one tool.
stdio defaults open (same-machine, same-user channel), so the default posture is
unaffected. Consequences owned by this issue: (1) the Risk section must credit
the **HTTP** gate specifically, not "the transport gate"; (2) the
MCP_SERVER_GUIDE rewrite (Documentation section) must state that stdio policy
knobs are currently advisory; (3) a follow-up issue for uniform stdio
enforcement across all three grants should be filed at implementation time.

### Decision 9 — Close the start→poll visibility window: `tasks/get` falls back to the PID file

**The gap (verified 2026-08-14):** `run_background()`'s parent writes only the
PID file (`.running/<instance_id>.pid`) before returning; the *child* writes the
first state file. `read_run_status()` (`cli/loop/lifecycle.py:132`) returns
`None` when no state file exists, which `handle_tasks_get` maps to the
task-not-found error. So without a fix, a host that starts a run and
immediately polls the returned taskId gets "no run found" for a run that
genuinely exists — and AC 4's integration test is racy for the same reason.

**Resolution: teach `tasks/get` a PID-file fallback.** When
`read_run_status()` returns `None` but `.running/<instance_id>.pid` exists and
its PID is alive, `handle_tasks_get` returns
`{taskId, status: "working", runStatus: "starting"}` (no run-detail fields —
none exist yet). The parent writes the PID file before the start call returns,
so start→poll composes correctly by construction. A dead PID with no state
file remains task-not-found (the child died before ever writing state — there
is no status to report, and FEAT-3145 Decision 5 forbids a default "running"
shape for a run that cannot be confirmed live).

This is a small, additive change inside `handle_tasks_get`
(`mcp_server/tasks.py`) plus reuse of the existing PID-liveness helpers in
`lifecycle.py`; it does not change `read_run_status()`'s own contract, which
`ll-loop status --json` shares. AC 4 must exercise the immediate-poll path
(poll right after start returns, before the child can plausibly have written
state) so the fallback is what the test proves.

## Anti-goals

- Do not advertise `io.modelcontextprotocol/tasks` in the capabilities response
  (inherited from FEAT-3145; EPIC-3127 open question 4).
- Do not invent a `tasks/start` method. SEP-2663 has no such method and adding
  one forfeits the swap-to-official-extension property.
- Do not turn `ll-auto` / `ll-parallel` into tools as a side effect. One start
  tool, `ll-loop` only.
- Do not add `ll-queue` dispatch (FEAT-3145 Decision 2).

## Dependencies

All prerequisites are satisfied as of 2026-08-14.

- **FEAT-3145** (**done**) — supplies `tasks/get` / `tasks/cancel`
  (`mcp_server/tasks.py`), the `allow_tasks` transport policy, and the
  `taskId` == `instance_id` convention. A start path without a poll path returns
  a handle nothing can read. Note it did **not** widen `check_tool_call` to gate
  `tools/call` on `allow_tasks` (Decision 8).
- **FEAT-3149** (done) — the `MUTATING_TOOLS` / dry-run convention Decision 4's
  sub-question refers to.
- **FEAT-3143** (done) — HTTP transport.
- **EPIC-3127 tier-3 evidence gate** — **opened 2026-08-11**. See the header
  note.

## Acceptance Criteria

1. A `tools/call` naming the start tool, from a client that declares the tasks
   extension in `_meta.clientCapabilities.extensions` **and sets `params.task`**,
   returns a top-level `resultType: "task"` result whose task id equals the
   started run's `instance_id` (Decisions 2, 5).
2. The same call from a client that does **not** declare the extension returns an
   ordinary `CallToolResult` — never a task-shaped result — whose payload still
   carries the started run's `instance_id` (Decisions 2, 2a). Asserted
   as a distinct test, since this is the forward-compatibility property that
   `runner.py:370`'s `TODO(L56)` will later enforce upstream.
2b. The same call from a client that **does** declare the extension but omits
   `params.task` also returns an ordinary `CallToolResult`, run still started
   (Decision 2's second condition, Decision 2a). Without this, a tasks-capable
   host loses the ability to make a plain call to the start tool.
2c. A client on a pre-modern `protocolVersion` gets the ordinary
   `CallToolResult` path — run still started, never an error (Decisions 6, 2a).
3. The call returns within normal request latency; the `ll-loop` run continues
   after the response is sent — asserted by confirming the request completes
   while the spawned process is still alive.
3b. When `run_background()` fails before spawning — scope conflict, unloadable
   loop — the call returns a tool error, **never** a task-shaped result carrying
   an `instance_id` for a run that was never started (Decision 7). Asserted for
   at least the scope-conflict path, which is reachable without mocking.
4. The task id returned by AC 1 is accepted by FEAT-3145's `tasks/get` and
   resolves to the same run (Decision 3) — an integration test across both
   issues, not two isolated unit tests. The test polls **immediately** after
   the start call returns, before the child can plausibly have written its
   state file, so it is Decision 9's PID-file fallback that the test proves —
   not a sleep-papered-over race.
4b. The **task-core fields** (`taskId`, `status`) returned by AC 1 and by
   `handle_tasks_get` for the same working run agree in name, casing, and value
   vocabulary (Decision 5's consistency note). The start result's `status` is
   the literal `"working"` — the same value `handle_tasks_get` maps a running
   run to (`tasks.py:88-89`) — so the vocabulary agreement holds by
   construction. Get-side run-detail fields
   (`runStatus`, the terminal-run `ExecutionResult` fields) and envelope keys
   (`resultType`) are explicitly out of scope for this comparison — a start
   result can never carry them.
5. The start tool is denied over HTTP when
   `mcp.transport_policy.http.allow_tasks` is `false` (the default), with the
   same `-32001` / HTTP 403 shape as FEAT-3145's `tasks/*` denials (Decisions 4,
   8). Requires the new `check_tool_call` branch; nothing existing satisfies this.
6. `initialize`'s capabilities response does **not** contain the string
   `io.modelcontextprotocol/tasks`, unchanged from FEAT-3145 AC 10.
7. The `compose_tool_call_handler` composition preserves existing `tools/call`
   behavior for every tier-1 and tier-2 tool — asserted by the existing
   `test_mcp_server.py` and `test_feat_3149_transport_policy.py` suites passing,
   with **exactly one sanctioned modification**: the registry-invariant test
   (`test_mcp_server.py:298-311`) asserts every advertised tool outside the
   tier-1 five is in `MUTATING_TOOLS` with an `apply` schema default, which the
   start tool deliberately fails (Decision 4: not in `MUTATING_TOOLS`, no
   `apply` param). Widen that test's invariant to "tier-1 ∪ `MUTATING_TOOLS` ∪
   `TASK_STARTING_TOOLS`" — same forget-the-registry guard, now covering
   Decision 8's registry. Every other test in both suites must pass unmodified;
   treat any other failure as a regression, not something to edit around.
8. Each method name and result field is annotated in code with the SEP-2663
   construct it mirrors, so the later swap to the official extension is
   mechanically checkable by a human (inherited from FEAT-3145 AC 13).
9. `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` — add the start tool to `_TOOLS` /
  `_TOOL_HANDLERS`, following the existing shared-dispatch convention (one
  `on_call_tool` pair over a module-level dict, not per-tool SDK registration).
  Also update `handle_list_tools`'s docstring (`:723`), which says "fixed
  nine-tool catalog" — the start tool makes it ten.
- `scripts/little_loops/mcp_server/server.py` — wrap `handle_call_tool` in
  `compose_tool_call_handler([...])` at the `on_call_tool=` site (`:91`,
  inside `build_server()` at `:52`). Additive; `test_build_server_signature_unchanged`
  (`test_feat_3143_mcp_http_transport.py:67-69`) keeps passing.
- `scripts/little_loops/mcp_server/policy.py` — **required work, not a
  sub-question** (Decision 8): add a `TASK_STARTING_TOOLS` frozenset alongside
  `MUTATING_TOOLS` (`:55`) and a third branch in `check_tool_call` (`:78`) gating
  `tools/call` on `allows_tasks(transport)`. The start tool does **not** join
  `MUTATING_TOOLS` (Decision 4).
- `scripts/little_loops/cli/loop/_helpers.py` / `cli/loop/run.py` — the
  `argparse` boundary (Decision 7). `run_background()` (`_helpers.py:1510`) takes
  `args: argparse.Namespace`, forwards ~30 fields via `getattr(args, ...)`, and
  returns an **`int` exit code** — it does not return `instance_id`. Recommended
  option (a) touches neither file: build a `SimpleNamespace` at the MCP boundary
  and pre-mint `instance_id`. **Verified 2026-08-14: every `args` access in
  `run_background()`'s body is a defensive `getattr(args, ..., default)` — a
  `SimpleNamespace` carrying only the fields the tool exposes (even none) cannot
  raise `AttributeError`.** Option (b) — a real keyword entry point that
  `cmd_run()` (`run.py:92`) also routes through — is where these files would
  change.
- `scripts/little_loops/mcp_server/tasks.py` — Decision 9's PID-file fallback in
  `handle_tasks_get`: state file absent but `.running/<instance_id>.pid` alive →
  `{taskId, status: "working", runStatus: "starting"}`. Reuses `lifecycle.py`'s
  existing PID-read/liveness helpers; `read_run_status()` itself is unchanged.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_mcp_server.py` — exercises `tools/call` dispatch via
  `mcp.client.Client(server)`; must keep passing (AC 7), with one sanctioned
  edit: the registry-invariant test (`:298-311`) is widened to accept
  `TASK_STARTING_TOOLS` members alongside `MUTATING_TOOLS` — see AC 7.
- `scripts/tests/test_feat_3149_transport_policy.py` — exercises the policy
  middleware; must keep passing unmodified (AC 7).

### Similar Patterns
- FEAT-3149's four mutation tools are the model for adding a tool to the shared
  dispatch dict. Note the `apply: true` dry-run guard in `handle_call_tool`
  (`tools.py:734+`) is what the start tool must **avoid** inheriting (Decision 4).
- `mcp_server/tasks.py` (FEAT-3145) is the model for the result shape: hand-built
  dicts with SEP-2663 field names and per-field mirroring comments, not SDK
  result models (Decision 5, AC 8).
- FEAT-3145's `read_run_status()` extraction (`cli/loop/lifecycle.py:132`) is the
  model *only* if Decision 7 option (b) is chosen.

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
  **directly falsified by this issue**. Needs rewriting, not amending. The
  rewrite must also state that `stdio` transport-policy knobs are currently
  advisory (Decision 8's stdio note).
- `docs/reference/CLI.md` — `### ll-mcp` section: the "no orchestration ...
  intentionally off the tool surface" claim likewise.
- `docs/index.md` — line 45's MCP Server Guide bullet. It no longer says
  "read-only" (FEAT-3149 already amended it to "including its guarded mutation
  tools"); it needs extending to cover run control, not correcting.

### Configuration
- No new keys. Reuses `mcp.transport_policy.{http,stdio}.allow_tasks` introduced
  by FEAT-3145 (Decision 4).

## Implementation Steps

0. **Prove the capability read first** (Decision 2's unproven step). Extend
   `.ll/learning-tests/mcp-tasks-start-path.md` with a claim that
   `ctx.meta["io.modelcontextprotocol/clientCapabilities"]` and
   `params.task` both arrive populated on a real request from a declaring client.
   ACs 1, 2, and 2b are unimplementable until this is known; if the read is not
   available, the gating strategy — not just the code — has to change.
1. Cross the `argparse` boundary per Decision 7 option (a): pre-mint
   `instance_id` with the entropy suffix (Decision 3's minting note), build a
   `SimpleNamespace`, call `run_background()`, and map a non-zero return to a
   tool error (AC 3b).
1b. Add Decision 9's PID-file fallback to `handle_tasks_get` so a
   just-started run is pollable before its child writes state (AC 4's
   immediate-poll assertion).
2. Add the start tool to `tools.py`'s dispatch dict. Add `TASK_STARTING_TOOLS`
   and the third `check_tool_call` branch in `policy.py` (Decision 8) — do
   **not** add the tool to `MUTATING_TOOLS`.
3. Wrap `handle_call_tool` in `compose_tool_call_handler`, materializing a task
   only on capability ∧ `params.task` ∧ modern protocol version (Decisions 2, 6),
   returning the hand-shaped mapping from Decision 5.
4. Verify: ACs 1-3b and 5 in the new test module, ACs 4/4b as cross-issue
   integration tests, AC 7 by running the existing suites unmodified.

## Program Design

### Types
- The task-shaped result is a **hand-built `dict[str, Any]`** with top-level `resultType: "task"` and `taskId`, matching the learning test's proven `TASK_SEED` and `mcp_server/tasks.py`'s existing hand-built returns. `types.CreateTaskResult` is **not** used: it dumps to `{"task": {...}}` with no `resultType`, which fails the spec-method sieve on `tools/call` (Decision 5). SDK task models are consulted for field naming only.
- `types.CallToolRequestParams.task: TaskMetadata | None` — already present on the pinned SDK; the per-call task-augmentation request (Decision 2, condition 2). No new params model needed.
- `types.RequestParamsMeta` — an open `TypedDict` (`extra_items=Any`); the declared-capability read is `(ctx.meta or {}).get(types.CLIENT_CAPABILITIES_META_KEY)`, where that constant is `"io.modelcontextprotocol/clientCapabilities"`. The `or {}` is mandatory: `ServerRequestContext.meta` is `RequestParamsMeta | None = None` (Decision 2's guard note). Unproven end-to-end (Implementation Step 0).
- The start tool's input schema is a plain JSON-schema `dict` on a `types.Tool`, following FEAT-3149's four mutation tools — not a locally-authored `BaseModel`. (FEAT-3145's `TasksGetParams` exists because `add_request_handler` requires a params model; `tools/call` does not.) **v1 schema is pinned to exactly two properties:** `loop` (string, required — the loop name) and `context` (array of `"KEY=VALUE"` strings, optional — mirrors `ll-loop run --context`, and is how a target issue reaches a loop per the Use Case). Every other `ll-loop run` flag (`max_iterations`, `delay`, models, diagrams, …) is deliberately deferred — `run_background()` reads them all via `getattr(..., default)`, so widening the schema later is additive.
- **`TasksExtension` is locally authored — the SDK ships no such class.** `mcp.server.extension` (2.0.0) exports only the `Extension` base, `compose_tool_call_handler`, and the binding dataclasses. The class named in the Call Path is a local subclass of `mcp.server.extension.Extension` overriding `intercept_tool_call` (the learning test's pattern, made conditional per Decision 2), living in `mcp_server/tasks.py` alongside the FEAT-3145 handlers.

### Signatures
- `compose_tool_call_handler(extensions: list, handler: Callable) -> Callable` — free function from the `mcp` SDK (2.0.0), proven in [[mcp-tasks-start-path]] to work on the lowlevel `Server` despite that class having no `extensions=` parameter. Zero call sites in `scripts/little_loops/` today.
- `handle_call_tool(...)` — `scripts/little_loops/mcp_server/tools.py`; the existing shared `on_call_tool` dispatcher, wrapped rather than replaced (Decision 1).
- `build_server() -> Server` — `scripts/little_loops/mcp_server/server.py:52`; the `on_call_tool=` argument (`:91`) changes from `handle_call_tool` to the composed handler. Zero-parameter signature unchanged, so `test_build_server_signature_unchanged` (`test_feat_3143_mcp_http_transport.py:67-69`) keeps passing.
- `run_background(loop_name: str, args: argparse.Namespace, loops_dir: Path, subcommand: str = "run", instance_id: str | None = None) -> int` — `scripts/little_loops/cli/loop/_helpers.py:1510`. **Returns an exit code, not a handle** (Decision 7). The handle comes from pre-minting `instance_id` via `_make_instance_id(loop_name)` and passing it in through the existing keyword. A return of `1` means nothing was spawned (scope conflict / load failure) and must surface as a tool error (AC 3b).
- `_make_instance_id(loop_name: str) -> str` — `cli/loop/_helpers.py`; the id minter `run_background` falls back to. **Not called directly by the MCP layer**: its one-second timestamp resolution can collide under agent-paced calls, so the MCP boundary mints its own id with an entropy suffix (Decision 3's minting note) and passes it through `run_background(instance_id=...)`.
- `check_tool_call(transport, method, tool_name, *, config=None) -> PolicyDecision` — `mcp_server/policy.py:78`. Signature unchanged, **body changes**: today it gates only `MUTATING_TOOLS` on `tools/call` and any `tasks/*` method. Decision 8 adds a third branch for `tools/call` naming a `TASK_STARTING_TOOLS` member, gated on `allows_tasks(transport)`. FEAT-3145 did not widen this.

### Call Path
`MCP host tools/call` -> (HTTP only) `TransportPolicyMiddleware` -> `check_tool_call()` — deny returns `-32001` / 403 before the body is read; requires Decision 8's new branch -> `compose_tool_call_handler([TasksExtension()], handle_call_tool)` (`TasksExtension` = the locally-authored `Extension` subclass, § Types) -> evaluate all three of: declared extension in `(ctx.meta or {})[CLIENT_CAPABILITIES_META_KEY].extensions` (meta is `Optional` — Decision 2's guard note), `params.task` present, modern `ctx.protocol_version`:
- all three: mint entropy-suffixed `instance_id` (Decision 3's minting note) -> `SimpleNamespace` -> `cli/loop/_helpers.py:1510 run_background(instance_id=...)` (detached spawn, PID file under `<loops_dir>/.running`) -> non-zero return becomes a tool error (AC 3b); zero returns the hand-shaped `{"resultType": "task", "taskId": instance_id, "status": "working", ...}` mapping (AC 4b: literal `"working"`)
- any missing: fall through to `handle_call_tool` -> the start tool's dispatch-dict handler performs the **same detached spawn** -> ordinary `CallToolResult` carrying the `instance_id` (Decision 2a; shape differs, behavior does not)

The returned `instance_id` is subsequently readable via FEAT-3145's `tasks/get` -> `read_run_status()` (`cli/loop/lifecycle.py:132`) -> `fsm/persistence.py _reconcile_stale_running()`; when `read_run_status()` returns `None` for a just-spawned run whose child has not yet written state, Decision 9's PID-file fallback in `handle_tasks_get` reports `status: "working"` / `runStatus: "starting"` instead of task-not-found.

### Decision Rules
- **Materialize a task iff capability ∧ `params.task` ∧ modern protocol version** (Decisions 2, 6). Any of the three missing means the plain path — same detached spawn, ordinary `CallToolResult` carrying the `instance_id` (Decision 2a); never emit `resultType: "task"` unilaterally, and never error on a client that simply did not ask.
- **Never return a task id for a run that was not spawned** (Decision 7). `run_background() != 0` is a tool error.
- **Task id is the `instance_id` verbatim** (Decision 3), pre-minted by the caller. No handle registry, no mapping table — this is what makes the id valid input to FEAT-3145's `tasks/get`.
- **Transport policy reuses `allow_tasks`** (Decision 4) via a new `TASK_STARTING_TOOLS` registry (Decision 8), not a third config grant and not `MUTATING_TOOLS`.
- **The interceptor is scoped to the start tool by name** (Decision 2a's
  scoping note): `params.name != <start tool>` means `call_next` untouched,
  regardless of capability or `params.task`. No other tool ever returns a
  task shape.
- No other branching: one start tool, `ll-loop` only, no `ll-queue`.

## Impact

- **Priority**: P3 — unblocked as of 2026-08-11, but nothing here is urgent.
- **Effort**: Medium **under Decision 7 option (a)**; Large under option (b).
  The composition point is a single call site and the wire mechanism is proven,
  but three pieces are real work with no precedent in the package: the
  declared-capability plumbing (and its unproven read, Step 0), the `argparse`
  boundary crossing, and Decision 8's policy branch — which earlier drafts of
  this issue wrongly assumed FEAT-3145 had already delivered.
- **Risk**: Medium-High — this is the only code path on the MCP surface that
  spawns an agent with the project's full tool permissions. The **HTTP**
  transport gate is what makes that acceptable (stdio policy knobs are
  advisory-only today — Decision 8's stdio note), and per Decision 8 that gate
  does **not yet cover this tool**; AC 5 is the one that must not be waved
  through.
- **Breaking Change**: No — additive tool plus a handler composition; existing
  `tools/call` behavior is unchanged for every existing tool (AC 7).

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 3 (job API). **The gate opened 2026-08-11** by product decision; see the
header note. The "evidence-gated" phrasing in this issue's title and filename is
retained only for ID stability.

## Related Key Documentation

- [`docs/guides/MCP_SERVER_GUIDE.md`](../../docs/guides/MCP_SERVER_GUIDE.md)
- [`docs/reference/CLI.md`](../../docs/reference/CLI.md)
- [`.ll/learning-tests/mcp-tasks-start-path.md`](../../.ll/learning-tests/mcp-tasks-start-path.md)
- [`.ll/learning-tests/mcp-extension-mechanism.md`](../../.ll/learning-tests/mcp-extension-mechanism.md)

## Status

**Open** — unblocked; EPIC-3127's tier-3 gate opened 2026-08-11 and FEAT-3145/3149/3143 are all done. Ready to implement once Implementation Step 0 (the capability-read proof) lands | Created: 2026-08-11 | Reviewed: 2026-08-14 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-14T18:35:57 - `933ada91-532f-44ff-8f0f-0b177ad3e4c3.jsonl`
