---
id: ENH-3234
type: ENH
title: ActionSpec credential scope declaration and runner_spec.py wiring
priority: P2
status: open
parent: ENH-3203
epic: EPIC-3212
blocked_by: [ENH-3233]
discovered_by: /ll:issue-size-review
discovered_date: '2026-08-17'
testable: true
decision_needed: false
relates_to:
- ENH-3184
---

# ENH-3234: ActionSpec credential scope declaration and runner_spec.py wiring

## Summary

Add a scope-declaration field to `ActionSpec` and wire it into the `ll-action`/`ll-queue`/
`ll-harness` call path so a task run through this path can declare the capability set it needs,
and its `bash -c` execution in `runner_spec.py::_run_cmd()` is denied everything else — using the
deny-capable `project_child_env()`/`HostInvocation.env_allow` chokepoint landed in ENH-3233.

## Parent Issue

Decomposed from ENH-3203: Declare and enforce per-task credential scope via deny-by-default env
projection. This child covers the `ActionSpec` declaration surface only; the FSM `StateConfig`/
loop-YAML surface is ENH-3235. Both converge on the shared chokepoint from ENH-3233, which this
issue depends on.

**Why a separate surface from FSM, not a shared one**: `fsm/runners.py`'s shell branch never
constructs or touches an `ActionSpec` (zero matches for `ActionSpec` under
`scripts/little_loops/fsm/`), and `runner_spec.py::_run_cmd()` never calls `resolve_host()` or
reads a `StateConfig`/loop-YAML object. A single declaration surface cannot structurally reach
both `bash -c` paths without a larger unification the parent issue explicitly does not attempt —
see ENH-3203's Decision Rationale (Option C).

## Current Behavior

`ActionSpec` (`runner_spec.py:77-89`, `@dataclass(frozen=True)`) fields today: `name: str`,
`runner: RunnerType`, `target: str`, `args: dict[str, Any]`, `timeout: int | None = 120`. No
declaration field exists. `args` is the established untyped grab-bag already smuggling per-call
options (`automation_profile`, `disable_background_tasks`, `trace_mode`, `tools`, `model`, etc.)
into `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` via `spec.args.get(...)`. Confirmed
production construction sites: `queue_store.py:247`, `cli/loop/run.py:132`,
`cli/action.py:239,292`, `cli/harness.py:735,769,811,844`, `cli/queue.py:163,171,186,195`.

`runner_spec.py::_run_cmd()` (`runner_spec.py:214-286`) calls `project_child_env()` with **zero
arguments** at lines 225-232 — no `HostInvocation` exists at this call site today, and the
function never calls `resolve_host()` anywhere.

## Expected Behavior

- `ActionSpec` gains a scope-declaration field naming the capabilities a task needs (resolved
  against ENH-3233's capability registry).
- Every production `ActionSpec` construction site (listed above) can populate it.
- `runner_spec.py::_run_cmd()` resolves the declared scopes into an `env_allow` set and passes
  it via the explicit kwarg ENH-3233 provides for invocation-less call sites —
  `project_child_env(env_allow=...)` — so everything not declared is denied. No synthetic
  `HostInvocation` is constructed.
- `ActionSpec`s with no declaration keep today's coarse (full-inherit) behavior — the `env_allow`
  path is opt-in per spec, matching ENH-3233's `env_allow=None` no-op default.

## Proposed Solution

**Decided: a typed field** (e.g. `scopes: frozenset[str] | None = None`), deliberately diverging
from `ActionSpec`'s established `args: dict[str, Any]` grab-bag convention
(`runner_spec.py:120-136`; no typed field added since ENH-2668). Rationale: this is a security
control — with an `args` key, a typo'd key name (`"scope"` vs `"scopes"`) silently yields an
**unscoped** task with no error anywhere, exactly the "looks like protection that isn't there"
failure mode the parent issue warns about. A typed field also stays symmetric with ENH-3235's
typed `StateConfig` field. Resolve the declared names against ENH-3233's credential-scope
registry at spec-construction or resolve time (AC3's fail-loud direct raise applies here).

### Call Path
`ActionSpec` (scope declared) → `runner_spec.py::_run_cmd()` resolves scopes → `env_allow`
set → `project_child_env(env_allow=...)` (ENH-3233's kwarg; no `HostInvocation` at this call
site) → `subprocess.*`

## Acceptance Criteria

- **AC1 (ActionSpec half).** An `ActionSpec` can declare the capability set a task requires.
- **AC7.2.** `runner_spec.py::_run_cmd()` — the `ll-action`/`ll-queue`/`ll-harness` `bash -c`
  path — is covered by the same projection as the host-CLI paths, with a test proving an
  undeclared credential variable is absent from the shell action's environment.
- **AC5 (this surface).** `ActionSpec`s without a declaration keep working with today's coarse
  behavior — no regression to any existing `ll-action`/`ll-queue`/`ll-harness` caller.

## Program Design

### Tests
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch::test_cmd_dispatch_matches_legacy_shape`
  (lines 172-176) — the closest existing real-subprocess `RunnerType.CMD` test (spawns `echo hi`,
  no `Popen` mocking); the natural site to extend for AC7.2 (`monkeypatch.setenv(...)` + a shell
  command that echoes the var, then assert absence).
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py` — general
  coverage location per ENH-3203's Tests section.

### Documentation
- No dedicated doc section for `ActionSpec` scope was identified in the parent's wiring pass
  beyond the `project_child_env`/`HostInvocation` updates already covered by ENH-3233; if the
  chosen field shape (typed field vs. `args` key) merits documentation, add it alongside the
  existing `ActionSpec` field description in `docs/reference/API.md`.

## Scope Boundaries

Out of scope for this child:

- The FSM `StateConfig`/loop-YAML declaration surface and `fsm/runners.py:266` wiring — that's
  ENH-3235.
- The chokepoint's deny logic, capability registry, and baseline — that's ENH-3233, a hard
  dependency of this issue.
- Retrofitting declarations onto existing `ll-action`/`ll-queue`/`ll-harness` callers in this
  repo — AC5 keeps undeclared specs working; migrating real callers to declare scopes is
  follow-on work per ENH-3203's Scope Boundaries.

## Impact

- **Priority**: P2 — matches parent.
- **Effort**: Small-Medium — one field/convention on `ActionSpec`, one call site
  (`_run_cmd()`) to wire, cross-referenced against ENH-3233's already-built chokepoint.
- **Risk**: Low-Medium — confined to the `RunnerType.CMD` path; `ActionSpec`'s other runner
  branches (`_run_skill`, `_run_mcp`, `_run_prompt`) are unaffected unless the declaration is
  extended to them later (out of scope here — AC7.2 only requires the `_run_cmd()` shell path).
- **Breaking Change**: No — declaration is opt-in per `ActionSpec`.

## Status

**Open** | Created: 2026-08-17 | Priority: P2 | Blocked by: ENH-3233

## Session Log
- `/ll:issue-size-review` - 2026-08-17T16:32:35 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
