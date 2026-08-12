---
id: FEAT-3145
title: 'll-mcp: tasks/get + tasks/cancel poll surface via Server.add_request_handler
  (tier-3, evidence-gated)'
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
- mcp tasks start path
depends_on:
- FEAT-3143
- ENH-3144
- FEAT-3149
relates_to:
- FEAT-3143
- FEAT-3149
- FEAT-3151
confidence_score: 95
outcome_confidence: 75
verify_verdict: VALID
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
missing_artifacts: false
size: Medium
testable: true
reconcile_attempted: true
---

# FEAT-3145: ll-mcp: tasks/get + tasks/cancel poll surface via Server.add_request_handler

## ✅ Gate opened 2026-08-11 — cleared to implement

EPIC-3127 held the job tier behind an explicit evidence gate: long-running
orchestration was to be "built only if real usage of the first two tiers shows
hosts wanting to *drive* runs rather than plan them." That usage evidence never
materialized. The gate was opened anyway by explicit product decision (not
observed usage) — job control over MCP (start/poll/stop) was judged 100%
aligned to and required by product strategy. Recorded in EPIC-3127's tier-3
split bullet, 2026-08-11.

**Tier ordering is satisfied.** EPIC-3127's ordering is strict — "Tier 2 blocks
tier 3, and tier 3 is additionally evidence-gated." Tier 2 (guarded mutations,
**FEAT-3149**) landed 2026-08-11 (commit `24e2c0c8`), so the dry-run-by-default
convention and per-method transport policy this surface needs to sit behind now
exist. Both the ordering blocker and the evidence-gate blocker are now cleared.

**Note on the split (2026-08-11):** the start path moved to **FEAT-3151**. This
issue is the *read/stop* half — `tasks/get`, `tasks/cancel`, and the transport
policy gate. Nothing here spawns an agent, which was the specific thing
EPIC-3127's gate protected against.

## Summary

Expose in-flight little-loops runs over MCP as a `tasks/*` request surface —
poll, cancel, retrieve result — registered through `Server.add_request_handler`
on the existing lowlevel server, and shaped to match SEP-2663 so it can be
replaced by the official `io.modelcontextprotocol/tasks` extension when an SDK
ships one.

**Scope: `ll-loop` runs only.** `ll-queue` is explicitly out of scope — see
Decision 2.

**Scope: no start path.** Starting a run is FEAT-3151, which depends on this
issue. This issue registers `tasks/get` and `tasks/cancel` and gates them behind
the tier-2 transport policy; runs are started by existing means (`ll-loop run`
on the workstation) and polled/stopped over MCP.

## Use Case

A developer has `ll-mcp` registered in a second MCP host (a phone-side agent, or
a Claude Code session on a different machine reaching the workstation over the
FEAT-3143 HTTP transport). A long `ll-loop run rn-refine` is already going on the
workstation. Rather than SSH-ing in to `ll-loop status` every few minutes, they
poll it from the second host while doing other work, and pull the
`ExecutionResult` when `terminated_by` is set. If the loop wedges, they stop it
from the same surface rather than hunting for a PID — and the answer they get
back is honest about the run being resumable, not a fake terminal "cancelled."

Kicking the run off from that same host is the natural next step and is exactly
what FEAT-3151 adds; it is deliberately not in this issue, because a start path
spawns an agent and that is the specific capability EPIC-3127's evidence gate
holds back.

## Current Behavior

`ll-mcp` serves five tier-1 read-only tools plus FEAT-3149's four guarded
mutation tools. Orchestration (`ll-auto`, `ll-parallel`, `ll-loop`, `ll-action
invoke`) is deliberately absent from the tool surface — correctly, since a tool
call that runs for minutes does not fit the tools primitive. There is no way to
reach a run from an MCP host at all: not to start one, not to poll one, not to
stop one.

## Expected Behavior

Two custom methods — `tasks/get` and `tasks/cancel` — dispatch to the existing
`ll-loop` status and stop machinery, so a host can poll a run and collect its
result without the call itself being long-running, and stop a wedged run without
hunting for a PID. Both sit behind the tier-2 transport policy gate, denied over
HTTP by default (Decision 4). Progress rides `subscriptions/listen` rather than a
bespoke notification channel.

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

The constraint was once thought to be in tension with the start path; the spike
showed it is not (see the resolved Open Question 1 below), and the start path has
since moved to FEAT-3151 regardless. For `tasks/get` and `tasks/cancel` the
constraint is unambiguous: both are additive method names that collide with
nothing in the spec.

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
result reports the spec-shaped `status: "cancelled"` — SEP-2663 fidelity is the
point of the surface — but **never bare**: it always carries `resumable: true`
and the backend's raw `"user_stopped"` verbatim in a separate field. The lie
Decision 3 forbids is the *silent* mapping, where a host sees `cancelled` and has
no way to learn the run can be resumed. Carrying both makes the mapping visible
rather than removing it.

Concretely: `{"status": "cancelled", "resumable": true, "runStatus":
"user_stopped"}`. Emitting `status: "cancelled"` with no `resumable` field, or
with `resumable: false`, is the defect this decision exists to prevent.

### Decision 4 — Auth for `tasks/*` over HTTP: extend the tier-2 policy gate

_Promoted from Open Question 2, resolved 2026-08-11 by `/ll:decide-issue`. Full
scored comparison and evidence in § Proposed Solution → Decision Rationale._

`tasks/*` methods are gated by widening `check_tool_call()`'s method guard
(`mcp_server/policy.py:102`) rather than by restricting the surface to stdio.
Denied over HTTP by default, allowed over stdio by default — the same
deny-by-default posture `McpTransportPolicyConfig` already documents for
mutating tools (`config/features.py:531-571`).

**Why not stdio-only:** no per-method transport-conditional dispatch exists
anywhere in the codebase to build that on (`main_mcp()` selects transport once
per process, `mcp_server/__init__.py:51-82`), it would mean inventing a second
ASGI deny mechanism beside the one tier 2 just shipped, and it contradicts this
issue's own rationale for depending on FEAT-3143.

Two implementation notes this decision commits to:

- `check_tool_call()`'s denial `reason` string hardcodes `tools/call/{tool_name}`
  (`policy.py:113-118`). Widening the guard requires reworking that message, not
  just the conditional — a `tasks/get` denial must not report itself as a
  `tools/call` denial.
- Which config field expresses the `tasks/*` allow/deny — a new
  `McpTransportPolicyConfig` field vs. reusing `http_allow_mutations` — is
  settled by Decision 6 below.

### Decision 5 — `taskId` is the `ll-loop` `instance_id`; project root comes from CWD

`TasksGetParams.taskId` **is** the run's `instance_id` verbatim — no separate
handle registry, no mapping table. `loops_dir` is resolved per request from
`Path.cwd()` via `BRConfig`, exactly as `mcp_server/tools.py` already resolves
project context.

**Why:** the server is stateless per request (FEAT-3143 runs
`stateless_http=True`), so any handle the server minted itself would have to be
persisted somewhere new. `instance_id` is already the disk-level primary key —
`<instance_id>.state.json`, `<instance_id>.pid` — and is already surfaced to
users by `ll-loop status`, so a host that saw a run in the CLI can poll it over
MCP with the same string. This also keeps `tasks/get` a pure disk read with no
new state.

**Consequence:** a `taskId` that does not resolve to a state file returns a
not-found error, not an empty `running` shape. An unknown handle must be
distinguishable from a live run.

### Decision 6 — `tasks/*` gets its own config field, not `http_allow_mutations`

`McpTransportPolicyConfig` gains `http_allow_tasks: bool = False` /
`stdio_allow_tasks: bool = True`, parallel to the existing mutation pair, rather
than `tasks/*` riding the mutation flag.

**Why:** the two are genuinely different grants. An operator who enables
mutating issue tools over HTTP has consented to issue-file writes; they have not
thereby consented to stopping a running agent on their workstation. Collapsing
both onto one flag makes the narrower grant impossible to express, and the
config's own stated principle — "a policy question this config has no answer for
is answered by refusing" (`config/features.py:541-542`) — argues for the
separate, separately-refusable question.

## Anti-goals

- Do not advertise `io.modelcontextprotocol/tasks` in the capabilities response.
  The server would be claiming an extension it implements privately. This is
  EPIC-3127 open question 4 and it stays closed until an SDK ships the extension.
  Note this is *server-side non-advertisement*, which is deliberately separate
  from FEAT-3151's *client-side* capability check — the two are not in conflict
  and neither should be "fixed" by breaking the other.
- Do not turn `ll-auto` / `ll-parallel` into tools as a side effect.
- Do not introduce a new terminal `cancelled` status in `fsm/persistence` as part
  of this issue (Decision 3).
- Do not add `ll-queue` dispatch (Decision 2).
- Do not add a start path (FEAT-3151). No code in this issue spawns a process;
  `tasks/cancel` signals an existing one.

## Open Questions

_None remain. Open Question 1 (spec-faithful start path) was resolved
affirmatively by spike on 2026-08-11 and its subject matter moved to FEAT-3151;
Open Question 2 (HTTP auth) was resolved as Decision 4 above. Both are retained
below for provenance._

### Resolved — Open Question 1: Is a spec-faithful start path reachable at all? — **yes** (2026-08-11)

_Subject matter now lives in **FEAT-3151**; this record is kept here because it is
the proof that the split is safe — the start path is a `tools/call` augmentation
and does not re-register anything this issue registers, so the two can ship
independently and in either order._

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

**Consequence:** the value proposition survives intact. Mechanism 2 is the
recommended one, since swapping to the official extension later becomes a
registration change exactly as promised. **Carried into FEAT-3151.**

**One forward-compatibility caveat, carried into FEAT-3151:** `runner.py:370`
carries a `TODO(L56)` to reject extension `resultType` values unless the matching
extension is present in the request's `_meta.clientCapabilities.extensions`.
Emitting `resultType: "task"` *without* honoring the client's declared extension
capabilities passes today but is forward-incompatible. The start-path
implementation must gate task materialization on the client having declared the
extension — which is also what SEP-2663 requires ("the client signals support ...
the server decides").

Note this is a *client-side* declaration check and does not conflict with this
issue's anti-goal against *server-side* advertisement of the extension.

### Resolved — Open Question 2: Authentication for `tasks/*` over HTTP — **Decision 4** (2026-08-11)

FEAT-3143 landed the streamable HTTP transport with an explicit scope note: "No
authentication, TLS termination, or session model in this issue." Its defenses
are loopback bind (`127.0.0.1`) plus DNS-rebinding protection — which stop a
browser, not a local process. Without a gate, any local process able to reach the
bound port could stop a running agent (and, once FEAT-3151 lands, start one).

**Resolved as Decision 4** above: extend the tier-2 policy gate, deny-by-default
on HTTP, with a dedicated config field per Decision 6.

## Dependencies

- **FEAT-3149** (done, tier 2, guarded mutations) — establishes the
  dry-run-by-default convention and the `check_tool_call()` /
  `TransportPolicyMiddleware` per-method transport policy that Decision 4 widens.
  Strict per EPIC-3127's tier ordering; satisfied as of commit `24e2c0c8`.
- **FEAT-3143** (done) — the surface is most useful over HTTP. Note the gate from
  Decision 4 means HTTP is *available but closed by default*, so an operator opts
  in rather than the surface being withheld from the transport.
- **ENH-3144** (done) — the epic's guidance needed correcting first, or this
  issue read as contradicting its own parent.

**Not a dependency:** FEAT-3151 (start path) `depends_on` this issue, not the
reverse. This issue ships standalone.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **FEAT-3149 status update**: completed 2026-08-11 (commit `24e2c0c8`), the same day this dependency was filed. All three `depends_on` entries (FEAT-3143, ENH-3144, FEAT-3149) are now `status: done` — the tier-2 mutation surface exists. This does not resolve Open Question 2: FEAT-3149's guarded-mutation policy (`mcp_server/policy.py`) is `tools/call`-specific and does not gate `tasks/*` methods as written (see Integration Map / Program Design findings above). The tier-ordering blocker ("tier 2 does not exist") that Confidence Check Notes cited as a dominant blocker is now cleared; the evidence-gate blocker (EPIC-3127 tier-3 gate) and Open Question 2 (auth) are unaffected and remain open.

## Acceptance Criteria

*(All open questions are resolved — see Decisions 1-6. The only unmet
precondition is EPIC-3127's tier-3 evidence gate, which is a product decision,
not a criterion this issue can satisfy.)*

**Poll path**

1. A `tasks/get` request over stdio for a live `ll-loop` run returns within
   normal request latency (no long-running request), with a status field derived
   through the PID-liveness reconciliation path — asserted by a test that kills
   the run's process without updating its state file and confirms `tasks/get`
   reports it as not-running rather than `running` (Decision 1).
2. A `tasks/get` request for a completed run returns the `ExecutionResult` fields
   (`final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`) as
   serialized by `ExecutionResult.to_dict()` (`fsm/types.py:66`).
3. A `tasks/get` request whose `taskId` matches no state file returns a
   not-found error distinguishable from a live run — never an empty or default
   `running` shape (Decision 5).

**Stop path**

4. A `tasks/cancel` request stops a running `ll-loop` run and its result payload
   contains `status: "cancelled"`, `resumable: true`, and the backend's raw
   `runStatus: "user_stopped"` together — asserted as three separate assertions,
   so a regression that drops `resumable` fails loudly (Decision 3).

**Transport policy gate (Decision 4)**

5. A `tasks/get` request over HTTP is denied by default, with JSON-RPC error
   code `-32001` and HTTP 403, matching the shape
   `test_feat_3149_transport_policy.py` already asserts for mutating tools.
6. The same request succeeds over HTTP when `mcp.transport_policy.http.allow_tasks`
   is `true`, and succeeds over stdio at default config — proving the gate is a
   config switch, not a transport ban.
7. A `tasks/*` denial never awaits the request body — asserted by instrumenting
   `receive()`, modelled on
   `test_ac5_denial_never_awaits_the_request_body` (`test_feat_3149_transport_policy.py:134-150`).
8. Enabling `http.allow_mutations` alone does **not** enable `tasks/*` over HTTP,
   and enabling `http.allow_tasks` alone does **not** enable mutating tools — the
   two grants are independently expressible (Decision 6).
9. A denied `tasks/get` reports itself as a `tasks/get` denial; the `reason`
   string does not claim a `tools/call` denial (Decision 4, second note).

**Boundaries**

10. `initialize`'s capabilities response does **not** contain the string
    `io.modelcontextprotocol/tasks` — asserted by a dedicated test, since no
    existing test covers the capabilities payload.
11. `tasks/*` requests for a `ll-queue` entry are not registered at all (Decision
    2) — no partial or stub queue dispatch ships.
12. No code path added by this issue spawns a process. `tasks/cancel` signals an
    existing PID; nothing calls `run_background()` / `run_foreground()`. This is
    what keeps the issue inside EPIC-3127's gate rather than across it.
13. Each registered method name and result field is annotated in code with the
    SEP-2663 construct it mirrors, so the later swap is mechanically checkable by
    a human even though nothing enforces it automatically.
14. `cmd_status`'s CLI output is byte-identical before and after the
    `read_run_status()` extraction — asserted against a captured baseline, since
    the extraction is a refactor of a user-facing surface.
15. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — no longer gated. Tier ordering was satisfied by FEAT-3149,
  and EPIC-3127's evidence gate was opened 2026-08-11 by explicit product
  decision. P3 now reflects normal scheduling priority, not a hold.
- **Effort**: Medium. The mechanism is proven and the poll path is a disk read,
  but the change spans five files: the `_status_single` extraction (inline
  JSON-shaping coupled to `argparse.Namespace`), the first locally-authored
  Pydantic models in the package, a widened `check_tool_call()` guard plus its
  denial-message rework, two new config fields with schema, and three doc files.
  Splitting the start path to FEAT-3151 is what keeps this from being Large.
- **Risk**: Medium. The design premise is settled — Open Question 1 was resolved
  affirmatively by spike and Open Question 2 by Decision 4. Residual risk is
  concentrated in two places: the `cmd_status` extraction touches a user-facing
  CLI output path (AC 14 guards it), and a mis-scoped policy widening could
  either leave `tasks/*` open over HTTP or accidentally gate existing tier-1
  reads (ACs 5-9 guard both directions).
- **Breaking Change**: No — purely additive method registration inside
  `build_server()`; `test_build_server_signature_unchanged` keeps passing. The
  two new config fields default closed on HTTP / open on stdio, matching the
  existing mutation pair, so no deployment changes behavior on upgrade.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 3 (job API). **The evidence gate opened 2026-08-11** — see the header note
and EPIC-3127's amended tier-3 split bullet.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

**Option A**: Extend the tier-2 policy gate — widen `check_tool_call()`'s method guard (`mcp_server/policy.py:102`) to also cover `tasks/*` methods (or add a parallel branch it consults), reusing the existing `McpTransportPolicyConfig` deny-by-default-on-HTTP convention (`config/features.py:531-571`) and `TransportPolicyMiddleware`'s already-generic header-extraction/deny-before-receive plumbing (`policy.py:123-177`, wired into `build_http_app()` unconditionally per request regardless of method). Test scaffolding to extend already exists (`scripts/tests/test_feat_3149_transport_policy.py`).

> **Selected:** Option A — reuses the tier-2 gate's already-generic middleware and existing test scaffolding; Option B has no precedent anywhere in the codebase and contradicts this issue's own Dependencies rationale for HTTP.

**Option B**: Restrict `tasks/*` to stdio only until real auth exists — contradicts the Dependencies rationale that this surface is "most useful over HTTP" (see Dependencies § FEAT-3143), and has no existing mechanism to build on: transport selection today is a single whole-process switch in `main_mcp()` (`mcp_server/__init__.py:51-82`), not a per-method dispatch; the only per-request transport-aware code path in the codebase is the tier-2 middleware itself (Option A's mechanism). Implementing this would mean inventing a new ASGI-layer method-keyed deny gate from scratch, duplicating rather than reusing Option A's plumbing.

**Recommended**: Option A — it reuses the tier-2 gate's already-generic middleware and matches this codebase's established "not yet safe → deny-by-default config, ship the capability" idiom (`MUTATING_TOOLS` dry-run guard, `CompactionConfig.enabled = False`, `PreCompactRubricConfig.enabled = False`), rather than introducing a novel transport-restriction mechanism (Option B) that exists nowhere else in the codebase.

### Decision Rationale

**Selected: Option A — extend the tier-2 policy gate (`check_tool_call()`/`TransportPolicyMiddleware`) to cover `tasks/*`.**

Two independent research passes (`ll:codebase-analyzer`, `ll:codebase-pattern-finder`) converged on the same evidence: `TransportPolicyMiddleware` already calls `check_tool_call()` unconditionally on every HTTP request regardless of method, so widening its method guard (`policy.py:102`) is the only change needed at the plumbing layer — the middleware, header extraction, and deny-before-`receive()` behavior are already method-generic. By contrast, no per-method transport-conditional dispatch exists anywhere else in the codebase to build a stdio-only restriction on; `main_mcp()` selects transport once, for the whole process, at startup. Option B would mean inventing a new ASGI-layer deny mechanism from scratch — duplicating, not reusing, Option A's own plumbing — while also contradicting this issue's own Dependencies section, which states the surface is "most useful over HTTP."

Option A also matches this codebase's established idiom for "not yet safe": ship the capability, default it closed via config (`McpTransportPolicyConfig.http_allow_mutations = False`), document why, and let an operator opt in — the same shape as `MUTATING_TOOLS`'s dry-run-by-default guard and several other `enabled = False`-by-default config flags. Test scaffolding to extend already exists in `scripts/tests/test_feat_3149_transport_policy.py`.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — extend tier-2 gate | 3 | 2 | 3 | 2 | 10/12 |
| B — stdio-only restriction | 0 | 0 | 1 | 1 | 2/12 |

Key evidence:
- `check_tool_call()`'s guard is a single conditional (`policy.py:102`); `TransportPolicyMiddleware` needs no change to gate additional methods (`policy.py:123-177`).
- No stdio-only precedent exists anywhere in `scripts/little_loops/`; transport selection is a whole-process switch in `main_mcp()` (`mcp_server/__init__.py:51-82`).
- `McpTransportPolicyConfig` (`config/features.py:531-571`) already documents the "deny-by-default on HTTP until trusted" rationale this decision extends.
- `scripts/tests/test_feat_3149_transport_policy.py` already exercises the deny/allow/passthrough/never-awaits-body shapes Option A's tests would extend.

The follow-on question of which config field(s) express the `tasks/*`-specific allow/deny (a new `McpTransportPolicyConfig` field vs. reusing `http_allow_mutations`) is **settled by Decision 6**: a dedicated `http_allow_tasks` / `stdio_allow_tasks` pair, because stopping a running agent and writing an issue file are different grants that an operator must be able to give separately.

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

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **Stale line-number reference**: `build_server()` moved from `server.py:30` to `server.py:52` since this issue's last refine — FEAT-3149 inserted a new `build_http_app()` function at line 30 above it. `build_server()` itself is otherwise unchanged: still six keyword-only `on_*` handlers plus `cache_hints` (lines 84-101), no `add_request_handler` call, and `test_build_server_signature_unchanged` (`test_feat_3143_mcp_http_transport.py:67-69`) still only asserts `inspect.signature(build_server).parameters == {}` — a `tasks/*` registration inside the function body would not break it.
- **FEAT-3149 (tier 2) landed today, 2026-08-11, commit `24e2c0c8`** — all three `depends_on` entries on this issue (FEAT-3143, ENH-3144, FEAT-3149) are now `status: done`. It added `mcp_server/policy.py` (new file): a `MUTATING_TOOLS` registry (`:55`), `check_tool_call(transport, method, tool_name, *, config=None)` (`:78-120`), and `TransportPolicyMiddleware` (`:123-177`) composed around `server.streamable_http_app(...)` in `build_http_app()` (`server.py:30-49`).
- **RESOLVED** — acted on by Decision 4. **`check_tool_call()` is `tools/call`-specific and does not extend to `tasks/*` as written** — line 102 opens with `if method != "tools/call" or tool_name not in MUTATING_TOOLS: return PolicyDecision(allowed=True)`. A `tasks/get`/`tasks/cancel` method registered via `add_request_handler` would have `method == "tasks/get"` etc. and pass through this check unconditionally allowed — no gating exists today for `tasks/*` over HTTP. FEAT-3149's own issue text (`P3-FEAT-3149-...md:449-451`) states verbatim that its transport-policy section "is also the policy hook FEAT-3145's Open Question 2 ... would extend rather than reinvent" — extending it means broadening `check_tool_call`'s method check beyond the `"tools/call"` literal, which is now Decision 4 and is listed in § Files to Modify.
- `TransportPolicyMiddleware`'s plumbing (SEP-2243 header extraction via raw ASGI `scope["headers"]`, deny-before-`receive()`-is-awaited, JSON-RPC `-32001`/HTTP 403 error response) is transport-generic and reusable for a `tasks/*` gate; only the policy *content* (`MUTATING_TOOLS`, the `tools/call`-only branch) is not.
- Confirmed still accurate: no `pydantic.BaseModel` subclass exists anywhere in `scripts/little_loops/` (repo-wide grep, zero matches) — FEAT-3149's four mutation tools use the existing `types.Tool`/JSON-schema `input_schema` dict convention, not `BaseModel`. A `TasksGetParams(BaseModel)` would still be the first.
- Confirmed still accurate: `_status_single()` (`lifecycle.py:131`), `_reconcile_stale_running()` (`persistence.py:243`), `cmd_stop()` (`lifecycle.py:317`), `run_background()` (`_helpers.py:1510`) are all unchanged since last refine and match the issue's existing Program Design description exactly.
- **RESOLVED** — acted on by Decision 4. New test file to model the `tasks/*` test module on, in addition to the previously-cited `test_feat_3143_mcp_http_transport.py`: `scripts/tests/test_feat_3149_transport_policy.py` — reuses local `_envelope()`/`_call_tool()` helpers (`:52-75`), wraps `starlette.testclient.TestClient` directly around `build_http_app()` (not `build_server()`), and includes a test that instruments `receive()` directly to prove a denial path never awaits the request body (`test_ac5_denial_never_awaits_the_request_body`, `:134-150`) — the pattern ACs 5-9 now require, since Decision 4 does extend this middleware.

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **RESOLVED** — became Decision 4. **Mechanism comparison (analyzer/pattern-finder, 2026-08-11)**: `check_tool_call()` (`mcp_server/policy.py:78-120`) gates on a single guard at line 102 — `if method != "tools/call" or tool_name not in MUTATING_TOOLS: return PolicyDecision(allowed=True)`. `TransportPolicyMiddleware` (`policy.py:123-177`, wired into `build_http_app()`, `server.py:30-49`) already extracts SEP-2243 headers and calls `check_tool_call()` unconditionally on every HTTP request regardless of method — the middleware itself needs no change to participate in a `tasks/*` gate; only the method-literal guard inside `check_tool_call()` (or a parallel branch it also consults) would need to widen.
- **No stdio-only precedent exists.** `build_server()` (`server.py:52-102`) constructs one transport-agnostic `Server` consumed identically by `run_stdio()` and `build_http_app()`; transport selection happens exactly once, at process start, in `main_mcp()` (`mcp_server/__init__.py:51-82`) via `--http`/`LL_MCP_TRANSPORT`. There is no per-method transport-conditional dispatch anywhere else in the codebase to build a stdio-only restriction on — `TransportPolicyMiddleware` is the *only* per-request transport-aware code path that exists today. A repo-wide grep for `stdio` outside `mcp_server/`, its tests, and docs surfaces nothing.
- **Established "not yet safe" idiom is deny-by-default config, not a transport ban.** `McpTransportPolicyConfig` (`config/features.py:531-571`, `http_allow_mutations: bool = False` / `stdio_allow_mutations: bool = True`) documents the exact precedent for "no auth yet": *"the safe posture is that the transport a remote host can reach stays read-only until someone opts in"* — the capability ships live in code, gated only by a config default, never withheld from a whole transport. `MUTATING_TOOLS`'s dry-run-by-default guard (`tools.py:735-773`, `apply: true` required) is the same shape applied to individual write tools. This pattern repeats across the config surface (`CompressionConfig.heuristic_underperforms`, `CompactionConfig.enabled = False`, `PreCompactRubricConfig.enabled = False`) — ship the capability, default it closed, let config opt in.
- **Test scaffolding to extend**: `scripts/tests/test_feat_3149_transport_policy.py` already covers the deny/allow/passthrough/never-awaits-body/direct-`check_tool_call` shapes against `build_http_app()` via raw JSON-RPC `TestClient` calls (not `mcp.client.Client`, since transport headers are never emitted by the in-memory client) — a `tasks/*` gate extending `check_tool_call()` would add cases to this same file rather than needing a new test harness.

### Files to Modify

> ⚠ Superseded — this list was rewritten by the 2026-08-11 review pass. Earlier
> revisions cited `build_server()` at `server.py:30` (stale since FEAT-3149
> inserted `build_http_app()` above it) and omitted `policy.py`,
> `config/features.py`, and `config-schema.json` entirely, which the selected
> Decision 4 requires. The `### Codebase Research Findings` corrections above
> are folded in below; read this list, not the findings blocks.

- `scripts/little_loops/mcp_server/server.py` — `build_server()` (`:52`) constructs the `Server` using only `on_*` keyword handlers (`:84-101`); add the two `add_request_handler("tasks/get" | "tasks/cancel", ...)` registrations inside its body. Additive: `test_build_server_signature_unchanged` (`test_feat_3143_mcp_http_transport.py:67-69`) only asserts the parameter list is empty, so it keeps passing.
- `scripts/little_loops/cli/loop/lifecycle.py` — extract `_status_single()`'s (`:131`) JSON-shaping logic into an importable helper decoupled from `argparse.Namespace`/`print_json`, so a `tasks/get` handler can call it directly (Decision 1 depends on reusing its reconciliation path, not reimplementing it). `cmd_status` (`:317` `cmd_stop` nearby) must keep byte-identical output — AC 14.
- **`scripts/little_loops/mcp_server/policy.py`** — Decision 4. Widen `check_tool_call()`'s guard (`:102`, currently `if method != "tools/call" or tool_name not in MUTATING_TOOLS`) to also decide `tasks/*`, and rework the denial `reason` string (`:113-118`) which hardcodes `tools/call/{tool_name}` (AC 9). `TransportPolicyMiddleware` (`:123-177`) itself needs **no** change — it already invokes `check_tool_call()` on every HTTP request regardless of method.
- **`scripts/little_loops/config/features.py`** — Decision 6. Add `http_allow_tasks: bool = False` / `stdio_allow_tasks: bool = True` to `McpTransportPolicyConfig` (`:531-571`), plus an `allows_tasks(transport)` accessor parallel to `allows_mutations()`, and matching `from_dict`/`to_dict` handling (note `from_dict` is lenient and defaults per-key, so both directions need the new keys).
- **`scripts/little_loops/config-schema.json`** — the two new config keys under the `mcp.transport_policy.http` / `.stdio` objects.
- **`scripts/little_loops/mcp_server/__init__.py`** — module docstring says `ll-mcp` exposes "five coarse read-only tools" and describes `main_mcp` as owning only those handlers; goes stale once `tasks/*` is registered. (Note: FEAT-3149 already added four mutation tools, so this docstring may be stale independently of this issue — check and fix in passing.)

**Not modified by this issue:** `mcp_server/tools.py`. There is no start tool here — the start path and its `compose_tool_call_handler` wiring are FEAT-3151. `MUTATING_TOOLS` is untouched.

_(The `/ll:wire-issue` pass's separate `mcp_server/__init__.py` docstring finding is folded into the list above.)_

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

_Wiring pass added by `/ll:wire-issue`, renumbered to the current AC list:_
- **New test module** `test_feat_3145_mcp_tasks.py` (to be created under the `scripts/tests/` dir), modeled on `test_feat_3143_mcp_http_transport.py`'s `_envelope()`/`_post()` raw-JSON-RPC helpers (the same shape the learning test used for `tasks/get`, since `add_request_handler`-registered methods aren't reachable via `mcp.client.Client`'s typed tool-call surface). Covers the poll/stop path — ACs 1-4. A real `ll-loop` run is not needed: the poll path is a disk read, so tests can write a `<instance_id>.state.json` fixture directly and, for AC 1, a PID that is known-dead. [Agent 3 finding]
- **Extend** the existing `test_feat_3149_transport_policy.py` module rather than adding a second policy harness — ACs 5-9. It already covers deny/allow/passthrough/never-awaits-body/direct-`check_tool_call` against `build_http_app()`. AC 8 (independent grants) is the one genuinely new shape: parameterize over the four `(allow_mutations, allow_tasks)` combinations.
- No existing test asserts the capabilities-response anti-goal ("do not advertise `io.modelcontextprotocol/tasks`"); a new test is needed since neither `test_build_server_signature_unchanged` nor `test_http_tools_list_matches_stdio_path` (`test_feat_3143_mcp_http_transport.py:67-69`, confirmed unaffected) covers it [Agent 2 finding] — AC 10
- **New regression test for the extraction** — AC 14: capture `ll-loop status` output before and after `read_run_status()` is extracted and assert byte-identity. This is the only test guarding a user-facing surface this issue refactors.
- **New negative test** — AC 12: assert no module added or touched by this issue imports `run_background` / `run_foreground`, keeping the "nothing spawns a process" boundary mechanically checked rather than a review-time promise.
- Confirmed non-breaking: `test_build_server_signature_unchanged` only asserts `inspect.signature(build_server).parameters == {}`; an `add_request_handler` call added inside `build_server()`'s body does not change its parameter list, so this test keeps passing as-is [Agent 3 finding]

### Backend entry points a `tasks/*` handler dispatches to
- `tasks/get` → `read_run_status()` (new, extracted from `_status_single()`, `cli/loop/lifecycle.py:131`) → `_reconcile_stale_running()` (`fsm/persistence.py:243`) → `StatePersistence.load_state()`. Pure disk read.
- `tasks/cancel` → `cmd_stop()` (`cli/loop/lifecycle.py:317`) → `_kill_with_timeout()` (`:88`) → `os.killpg(pgid, SIGTERM)`, escalating to `SIGKILL` after 10s.
- **Start path — not in this issue.** `cli/loop/run.py:92 cmd_run()` → `cli/loop/_helpers.py:1510 run_background()` is FEAT-3151's territory; AC 12 asserts nothing here reaches it.
- `ll-queue`: out of scope per Decision 2

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/MCP_SERVER_GUIDE.md` — `## What ll-mcp Is` (states `ll-mcp` "exposes a little-loops project read-only") and `## Read-Only by Design` ("There is no ... way to start `ll-auto`, `ll-parallel`, `ll-loop`, or `ll-action invoke` through this server") need revising: `tasks/cancel` is a control operation over an existing run, so the "no way to *start*" claim survives verbatim while "read-only" does not. `## Contents`/`## See Also` TOC needs a new entry. Also document the two new config keys and why they default closed on HTTP. [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-mcp` section: "exposing five coarse, read-only tools" and "no orchestration ... intentionally off the tool surface" both go stale; add a subsection parallel to the existing tools/resources/prompts paragraphs for the `tasks/*` method shapes. (Check whether FEAT-3149 already updated the "five ... read-only" phrasing when it added four mutation tools; if not, fix in passing.) [Agent 2 finding]
- `docs/index.md` — line 45 guide-link summary calls it "the read-only `ll-mcp` server" [Agent 2 finding]

### Configuration

**Two new keys** (Decision 6), under the existing `mcp.transport_policy` block that FEAT-3149 introduced:

```json
{
  "mcp": {
    "transport_policy": {
      "http":  { "allow_mutations": false, "allow_tasks": false },
      "stdio": { "allow_mutations": true,  "allow_tasks": true }
    }
  }
}
```

- `http.allow_tasks` defaults `false` — the FEAT-3143 HTTP transport still has no authentication, so a reachable port must not imply the ability to stop a running agent (Decision 4).
- `stdio.allow_tasks` defaults `true` — stdio is a same-machine, same-user channel, matching the existing `stdio_allow_mutations` posture.
- Unknown transport names fall back to `false`, per the accessor convention already in `McpTransportPolicyConfig.allows_mutations()`.
- Transport *selection* remains FEAT-3143's `LL_MCP_TRANSPORT` / `--http`; these keys govern policy within a transport, not which transport runs.

## Program Design

### Types
- `TasksGetParams(BaseModel)` — wire params for `tasks/get`, camelCase-aliased (`taskId`) per the learning test's proven validation path. Would be the first locally-authored Pydantic model in `scripts/little_loops/`. `taskId` is the `ll-loop` `instance_id` verbatim (Decision 5).
- `TasksCancelParams(BaseModel)` — wire params for `tasks/cancel`; same `taskId` semantics.
- `TasksCancelResult` — carries `status: "cancelled"`, `resumable: bool`, and `runStatus: str` (the backend value verbatim) together (Decision 3).
- Start-path params: **not in this issue** — FEAT-3151.

### Signatures
- `Server.add_request_handler(method: str, params_model: type[BaseModel], handler: Callable)` — proven against the unmodified `build_server()` `Server` in `.ll/learning-tests/mcp-extension-mechanism.md` (claim 4); zero call sites in `scripts/little_loops/mcp_server/` today.
- `build_server() -> Server` — `scripts/little_loops/mcp_server/server.py:52`; constructs `Server` via keyword-only `on_*` handlers (`:84-101`) with no `add_request_handler` call. `test_build_server_signature_unchanged` (`scripts/tests/test_feat_3143_mcp_http_transport.py:67-69`) asserts this function takes zero parameters — a `tasks/*` registration is additive inside the function body, not a signature change.
- `read_run_status(instance_id: str, loops_dir: Path) -> dict` — new importable helper extracted from `_status_single()` (`cli/loop/lifecycle.py:131`), preserving its `_reconcile_stale_running()` call (Decision 1) but decoupled from `argparse.Namespace`/`print_json`. Raises (or returns a sentinel) for an unresolvable `instance_id` rather than a default `running` shape (Decision 5, AC 3). `cmd_status` becomes its first caller; the `tasks/get` handler its second.
- `check_tool_call(transport, method, tool_name, *, config=None) -> PolicyDecision` (`mcp_server/policy.py:78-120`) — **widened by this issue**. Today line 102 short-circuits every non-`tools/call` method to `allowed=True`; it must additionally consult `config.mcp.transport_policy.allows_tasks(transport)` when `method` starts with `tasks/`. The `tool_name` parameter is `None` on those calls, so the widened branch must not assume it is populated.
- `McpTransportPolicyConfig.allows_tasks(transport: str) -> bool` — new accessor parallel to `allows_mutations()` (`config/features.py:548-554`), same unknown-transport-returns-`False` behavior.
- `MethodBinding(method: str, ...)` raises `ValueError` at construction for a spec-colliding method name (e.g. `tools/call`), and `MethodBinding.protocol_versions` raises `ValueError` for an empty `frozenset` — both are `mcp` SDK behavior (2.0.0), not `little_loops` code, per the learning test's claims 1 and 5. Neither `tasks/get` nor `tasks/cancel` collides, so neither is at risk.

### Call Path
`MCP host request` -> (HTTP only) `TransportPolicyMiddleware` -> `check_tool_call()` — deny here returns JSON-RPC `-32001` / HTTP 403 before the body is read -> `Server.add_request_handler`-registered `tasks/*` binding (new, inside `build_server()`) -> one of:
- poll: `read_run_status()` (new, extracted) -> `fsm/persistence.py:243 _reconcile_stale_running()` -> `StatePersistence.load_state()`
- cancel: `cli/loop/lifecycle.py:317 cmd_stop()` -> `:88 _kill_with_timeout()` -> `os.killpg(pgid, SIGTERM)`

There is deliberately no third branch; the start path (`cmd_run()` -> `run_background()`) belongs to FEAT-3151 and AC 12 asserts its absence here.

### Decision Rules
- **Job-state truth:** always reconcile PID liveness before reporting `running` (Decision 1). No configuration toggle; the reconciled read is the only read.
- **Unknown handle:** a `taskId` with no state file is a not-found error, never a default `running` shape (Decision 5).
- **Cancel result:** map `user_stopped` -> `{status: "cancelled", resumable: true, runStatus: "user_stopped"}` — spec-shaped `status` for fidelity, always accompanied by the two fields that make the mapping visible (Decision 3). Bare `cancelled` is the defect.
- **Transport policy:** `tasks/*` is allowed iff `allows_tasks(transport)`; this is a separate question from `allows_mutations(transport)` and neither implies the other (Decisions 4 and 6).
- Method routing (which `tasks/*` method dispatches to which primitive) is the only other logic; no keyword lists or thresholds.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- `build_server()` (`scripts/little_loops/mcp_server/server.py:52`, moved from `:30` — see Integration Map) — confirmed still zero-parameter, still no `add_request_handler` call.
- **RESOLVED** — acted on by Decision 4. `check_tool_call(transport: str, method: str, tool_name: str, *, config: BRConfig | None = None) -> PolicyDecision` (`mcp_server/policy.py:78-120`) — new as of FEAT-3149 (2026-08-11). Guards only `method == "tools/call"` against `MUTATING_TOOLS` (`policy.py:55`); any other method, including a `tasks/*` binding, returns `PolicyDecision(allowed=True)` unconditionally at line 102. Decision 4 broadens that method guard; see § Signatures above for the widened contract.

## Confidence Check Notes

_Consolidated 2026-08-11 — supersedes five near-identical passes run 2026-08-10
(21:19, 22:29, 22:39, 22:45, 22:49) plus this re-run later on 2026-08-11 after
FEAT-3149 landed, all of which converged on the same blocker._

**Readiness Score**: 66/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 38/100 → VERY LOW

_Re-scored 2026-08-11 (post-FEAT-3149): +1 point vs. the prior pass — all three
`depends_on` entries are now `done`, but Criterion 5 (Dependencies Satisfied)
still scores 0 because the issue's own explicit preconditions (EPIC-3127's
tier-3 evidence gate, Open Question 2) remain unmet; those are not frontmatter
`blocked_by` entries so they don't trip the mechanical Phase 1.7 override, but
they are "critical dependencies unresolved, cannot proceed" by the issue's own
stated text._

**RESOLVED** — **these scores predate the 2026-08-11 review pass and are stale.**
Open Question 2
is now Decision 4, two further ambiguities are settled (Decisions 5 and 6), the
AC list has grown from 7 to 15 with the transport gate covered, and the start
path has been split out. `confidence_score`/`outcome_confidence` in frontmatter
are left at their old values deliberately — re-run `/ll:confidence-check` **once**
to re-score against the revised text. The prior instruction not to re-run no
longer applies; it was predicated on nothing having changed, and the file has
changed substantially. The evidence gate remains the one thing a re-run cannot
move.

### Concerns

_Superseded by the 2026-08-11 review pass below; retained for provenance._

- **Dominant blocker: the tier-3 evidence gate is shut.** EPIC-3127
  (`.issues/epics/P3-EPIC-3127-ll-mcp-mcp-server-as-little-loops-host-agnostic-serving-layer.md`, `status: open`) still frames tier 3 as
  "built only if real usage of the first two tiers shows hosts wanting to *drive*
  runs rather than plan them." No amount of further research resolves this; five
  consecutive confidence checks re-derived the same conclusion, which is itself
  evidence that further refine cycles on this file are wasted. **Still true.**
- ~~**Second blocker: tier 2 does not exist.**~~ **Cleared** — FEAT-3149 landed
  2026-08-11 (commit `24e2c0c8`). EPIC-3127's ordering requirement is satisfied.
- ~~**Third blocker: Open Question 1**~~ **RESOLVED** — settled affirmatively by
  spike ([[mcp-tasks-start-path]], 11/11 claims). The subject matter has since
  moved to FEAT-3151 in any case.
- All three `depends_on` entries (`FEAT-3143`, `ENH-3144`, `FEAT-3149`) are
  `status: done`.
- `## Program Design` is populated and `ll-issues check-design FEAT-3145` passes.

### Review pass — 2026-08-11 (manual)

Structural review before implementation. Changes applied:

- **Frontmatter cleared of stale automation state** — `decision_needed`,
  `deferred_by`/`deferred_date`/`deferred_reason`, and `missing_artifacts` were
  all false as of the 2026-08-11 decide/refine passes but still set; the
  `mcp tasks start path` learning test was missing from
  `learning_tests_required`.
- **RESOLVED** — **Open Question 2 promoted to Decision 4.** It had been settled by
  `/ll:decide-issue` (Option A, scored 10/12) but was still filed under "Open
  Questions — resolve before implementation," which made the issue read as
  blocked by something already decided.
- **Two new decisions added** to close ambiguities the ACs would otherwise have
  coin-flipped: Decision 5 (`taskId` == `instance_id`, project root from CWD, and
  what an unknown handle returns) and Decision 6 (a dedicated `allow_tasks`
  config pair rather than reusing `http_allow_mutations`).
- **Decision 3 self-contradiction fixed** — the prose forbade reporting
  `cancelled` while the Decision Rules mandated exactly that mapping. Settled in
  favor of the spec-shaped value plus mandatory `resumable` / `runStatus`
  companions, with a stated defect condition.
- **AC coverage gaps closed** — the transport gate from the selected decision had
  no acceptance criteria at all, so the security fix would have shipped untested;
  ACs 5-9 now cover it in both directions (not open by default, not
  over-broadly gating tier-1 reads). AC 14 guards the `cmd_status` output
  refactor; AC 12 mechanically asserts nothing here spawns a process.
- **Files to Modify / Configuration corrected** — both omitted the selected
  decision's own targets (`policy.py`, `config/features.py`, `config-schema.json`),
  and Configuration still read "N/A — no new config keys" while the Decision
  Rationale committed to a config-gated capability.
- **Start path split to FEAT-3151** — it was the riskiest, most spec-sensitive
  part and the only part that spawns an agent. Splitting keeps this issue Medium,
  keeps it inside EPIC-3127's gate rather than across it, and lets the poll/stop
  surface generate the tier-3 evidence the epic is waiting on.

### Outcome Risk Factors
- No test coverage exists for the `tasks/*` handlers themselves — only the
  underlying `add_request_handler` mechanism, via the throwaway learning-test
  harness, not `scripts/tests/`.
- The `_status_single()` extraction touches `ll-loop status`, a user-facing CLI
  surface, and is the one part of this issue that can regress existing behavior.
  AC 14 is the guard.
- Widening `check_tool_call()` can fail in two directions — leaving `tasks/*`
  open over HTTP, or accidentally gating tier-1 reads. ACs 5-9 cover both.
- SEP-2663 fidelity has no automated enforcement; AC 13 downgrades this to a
  human-checkable annotation convention rather than pretending otherwise.
- **The evidence gate remains the sole product-level blocker.** It cannot be
  closed by refinement, only by a decision to open it (and a corresponding
  amendment to EPIC-3127).

## Status

**Open** — design settled; EPIC-3127's tier-3 evidence gate has not fired | Created: 2026-08-10 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-11 — re-scored per the instruction in
the prior notes above ("re-run once to re-score against the revised text")._

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

Substantially higher than the stale frontmatter values (66/38): since the last
scoring pass, Open Question 2 became Decision 4, two further ambiguities were
settled (Decisions 5, 6), the AC list grew from 7 to 15 with the transport gate
fully covered, `## Program Design` was populated (`check-design` passes), and
the start path split to FEAT-3151 keeping this issue's own scope tight. Criterion
5 (Dependencies) is still held at 0/20 — not because `depends_on` is unresolved
(all three are `done`), but because the issue's own header text states the
tier-3 evidence gate has not fired and implementation must not proceed without
amending EPIC-3127. That is a product-level precondition no amount of
refinement can close, so it caps the aggregate below what the otherwise
near-complete design work would earn.

### Concerns
- ~~**The tier-3 evidence gate is still shut.**~~ **RESOLVED same session,
  2026-08-11.** The gate was opened by explicit product decision (job control
  over MCP judged 100% aligned to and required by product strategy) rather than
  by observed usage — recorded in EPIC-3127's tier-3 split bullet. Criterion 5
  (Dependencies Satisfied) was scored 0/20 above on the pre-decision state; with
  the gate now open, that criterion would score 20/20 on a re-run, moving the
  aggregate readiness to 95/100 → PROCEED. Frontmatter scores below are updated
  accordingly rather than requiring a full re-run.
- **First locally-authored Pydantic `BaseModel` in `scripts/little_loops/`.**
  `TasksGetParams`/`TasksCancelParams` deviate from the existing convention of
  consuming only the SDK's own types — justified by `Server.add_request_handler`
  requiring a `BaseModel` params type, but still a minor architectural
  precedent-setter worth a reviewer's attention.

## Session Log
- `/ll:confidence-check` - 2026-08-12T02:07:06 - `2a82a443-5d46-418f-a842-19472b08c75b.jsonl`
- `/ll:confidence-check` - 2026-08-12T01:13:40 - `2a82a443-5d46-418f-a842-19472b08c75b.jsonl`
- `/ll:confidence-check` - 2026-08-11T22:29:39 - `f1065447-42b2-4db1-ad91-d87145159e04.jsonl`
- `/ll:decide-issue` - 2026-08-11T22:01:26 - `314945f7-8bec-4626-b595-4c659c7763ed.jsonl`
- `/ll:refine-issue` - 2026-08-11T22:00:00 - `4fa39a29-8b93-4a9a-adb4-d7d71347e160.jsonl`
- `/ll:refine-issue` - 2026-08-11T21:54:53 - `d5d81416-64f3-45f6-83b0-ea146a218034.jsonl`
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
