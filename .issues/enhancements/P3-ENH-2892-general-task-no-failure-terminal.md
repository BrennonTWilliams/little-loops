---
id: ENH-2892
type: ENH
status: open
priority: P3
captured_at: "2026-07-28T00:00:00Z"
discovered_date: 2026-07-28
discovered_by: capture-issue
labels:
- loops
- general-task
- fsm
- verification
relates_to:
- ENH-2814
- ENH-2825
- ENH-2857
---

# ENH-2892: general-task.yaml has no `failure: true` terminal — ENH-2814 exit-code plumbing is inert

## Summary

`scripts/little_loops/loops/general-task.yaml` defines three terminals — `partial`,
`done`, and `failed` (`general-task.yaml:933`, `:936`, `:952`) — and **none** of
them carries `failure: true`. Since
`FSM.get_failure_states()` (`scripts/little_loops/fsm/schema.py:1565`) is the
single source of truth for failure-ness and derives it solely from that flag, every
general-task run exits 0 and persists as `completed`, including runs that reach
`failed` via the `diagnose` state.

This makes ENH-2814's failure plumbing (exit 2, `final_status: "failed"`,
`loop_runs.failure_terminal`) completely inert for this loop, and it means a parent
loop dispatching general-task as a sub-loop cannot distinguish a diagnosed failure
from a clean success.

## Current Behavior

`ll-loop run general-task` exits 0 for every outcome. A run that hits an
unrecoverable error, routes through `diagnose`, and lands on the `failed`
terminal is indistinguishable — by exit code, by persisted `final_status`, and by
sub-loop dispatch routing — from a run that completed cleanly.

Concretely:

- `FSM.get_failure_states()` returns an **empty set** for this loop.
- `loop_runs.failure_terminal` is never populated.
- `spike-gate` and `proof-first-task` both declare `on_failure: impl_failed` for
  their general-task delegation, and **that branch has never been taken**.

## Discovery context

Found while fixing the ENH-2825 gate failure on `check_abandoned_route.on_error`
(`test_builtin_loops.py::test_no_failure_edge_routes_to_a_success_terminal`). The
obvious fix — route the edge to "the loop's failure terminal" — was unavailable
because no such terminal exists. That edge was routed to the non-terminal `diagnose`
instead, which satisfies the gate and is the loop's established convention for
unrecoverable errors, but it deliberately sidesteps this underlying gap.

## Proposed change

Add `failure: true` to the `failed` terminal in `general-task.yaml`.

Deliberately **not** `partial`: ENH-2575 designed `partial` as a distinct non-`done`,
non-`failed` terminal precisely so a verify timeout is neither laundered as success
nor discards the run's verified progress. Marking it a failure terminal would undo
that.

## Blast radius (must be assessed before implementing)

This is a behavior change, not a lint fix — it is why it was split out rather than
folded into the test-fix pass:

- Every path reaching `failed` (~15 `on_error: diagnose` edges plus `final_verify`'s
  chain) starts exiting 2 instead of 0.
- Any caller that shells out to `ll-loop run general-task` and checks the exit code
  will begin seeing failures it previously did not.
- Sub-loop dispatch routing for parents delegating to general-task changes from
  on_success to on_failure for those paths.

### Audited blast radius (2026-07-29)

**Sub-loop delegators — two, both already carrying dead `on_failure` branches:**

| Loop | Delegation | Routing |
|---|---|---|
| `loops/spike-gate.yaml` | `impl_loop: "general-task"` (`:15`), `loop: "${context.impl_loop}"` (`:77`) | `on_success: done` / `on_failure: impl_failed` (`:80-81`) |
| `loops/proof-first-task.yaml` | `impl_loop: "general-task"` (`:19`), `loop: "${context.impl_loop}"` (`:91`) | `on_success: done` / `on_failure: impl_failed` (`:94-95`) |

This reframes the change: both parents **already have an `impl_failed` state that
is currently unreachable**, because general-task can never report failure. The
change does not invent new routing — it makes existing, already-authored failure
branches live for the first time. That is an argument *for* the change, and the
two `impl_failed` states are the first things to exercise in testing.

Note both bind via `context.impl_loop`, so a caller overriding `impl_loop` to a
different loop is unaffected.

**Direct `ll-loop run general-task` shell-outs — none in automation.** All hits
are documentation/prose (`README.md:34,117`, `docs/reference/CLI.md:610,620`,
`docs/guides/LOOPS_REFERENCE.md:86,88,122`, `docs/guides/LOOPS_GUIDE.md:76`) plus
two references in `.loops/plans/prd-hermes/` describing an `ll_loop_run` MCP
handler that calls it with `--dry-run` and asserts `success=True`. That handler is
the one place worth re-checking during implementation: a `--dry-run` invocation
should not reach `failed`, but confirm rather than assume.

No `scripts/` code path shells out to it, so the CLI-exit-code half of the blast
radius is effectively empty.

## Expected Behavior

A general-task run that reaches the `failed` terminal exits 2, persists with
`final_status: "failed"`, and populates `loop_runs.failure_terminal` — the
ENH-2814 plumbing behaving as designed. A parent loop delegating to general-task
routes such a run to `on_failure`, reaching the `impl_failed` state it already
declares.

Runs reaching `done` or `partial` are unchanged: both continue to exit 0 and
persist as `completed`.

## Scope Boundaries

**In scope:**
- Adding `failure: true` to `general-task.yaml`'s `failed` terminal
- Auditing and updating existing tests that drive general-task to `failed`
- Confirming `spike-gate` and `proof-first-task` route to `impl_failed` correctly

**Explicitly out of scope:**
- **Marking `partial` as a failure terminal** — ENH-2575 designed it precisely
  not to be; see Proposed change.
- **Auditing other loops for the same missing-`failure: true` gap.** Several
  built-ins likely share it. This issue changes one loop whose blast radius has
  been measured; a fleet-wide sweep is a separate issue with a separate risk
  profile.
- **Changing the `~15 on_error: diagnose` edges themselves.** They keep routing to
  `diagnose`; only the terminal they eventually reach gains failure-ness. The
  ENH-2825 decision to route `check_abandoned_route.on_error` to `diagnose` stands.
- Any change to `ll-loop`'s exit-code contract or ENH-2814's plumbing — this issue
  makes existing plumbing reachable, it does not modify it.

## Impact

- **Severity**: Moderate — a designed failure-reporting path is inert for the
  most-used built-in loop, and two parent loops have unreachable failure branches
  as a direct result.
- **Scope**: `general-task.yaml` (one line), plus `spike-gate` and
  `proof-first-task` sub-loop routing, which change behaviour without changing
  code.
- **Risk of fix**: Moderate — this is a deliberate behaviour change. Runs that
  previously exited 0 will exit 2. The audited blast radius above bounds it:
  no `scripts/` code path shells out to `ll-loop run general-task`, so the
  exposure is limited to the two sub-loop delegators and the `prd-hermes`
  `--dry-run` handler expectation.
- **User-visible**: Yes — non-zero exit codes and `failed` run status where runs
  previously reported success. That is the point, but it should land deliberately.

## Acceptance Criteria

- [ ] `failed` in `general-task.yaml` carries `failure: true`
- [ ] `partial` and `done` are left **without** `failure: true` (see Proposed change)
- [ ] A test asserts `get_failure_states()` for general-task is non-empty
- [ ] Existing tests that drive general-task to `failed` are audited for exit-code
      assumptions and updated where they assumed exit 0
- [ ] `spike-gate`'s and `proof-first-task`'s `impl_failed` states are shown to be
      reachable — a general-task sub-loop run reaching `failed` routes to
      `on_failure`, not `on_success`
- [ ] The `prd-hermes` `ll_loop_run --dry-run` handler expectation
      (`success=True`) is re-checked against the new exit code
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

open
