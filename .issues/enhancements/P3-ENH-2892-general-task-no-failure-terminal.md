---
id: ENH-2892
type: ENH
status: done
priority: P3
captured_at: '2026-07-28T00:00:00Z'
completed_at: '2026-07-29T05:44:52Z'
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
confidence_score: 90
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings (2026-07-29)

_Added by `/ll:refine-issue` — based on codebase analysis. **This finding
contradicts the issue's core premise and should be resolved before
implementation proceeds.**_

`StateConfig.from_dict()` (`scripts/little_loops/fsm/schema.py:860-865`)
already defaults `failure=True` for any `terminal: true` state whose *name*
is in `FAILURE_TERMINAL_NAMES` (`schema.py:33-35`: `{"failed", "error",
"aborted", "finalize_aborted"}`) when the YAML omits an explicit `failure:`
key — a backward-compat fallback added by **ENH-2814**
(commit `66cec5a8`, 2026-07-26 — two days *before* this issue was captured
on 2026-07-28).

Verified directly against the current `general-task.yaml` via the real
production load path (`load_and_validate()`,
`scripts/little_loops/fsm/validation/structural_rules.py:1514`):

```
>>> fsm, _ = load_and_validate(Path("little_loops/loops/general-task.yaml"), raise_on_error=False)
>>> fsm.get_failure_states()
{'failed'}
>>> fsm.states['partial'].failure, fsm.states['done'].failure, fsm.states['failed'].failure
(False, False, True)
```

This is exactly the target state this issue asks for (`failed`=failure,
`partial`/`done`=not-failure) — already true today, with **no YAML edit
required**. The ENH-2825 gate test this issue's Discovery Context cites
(`test_no_failure_edge_routes_to_a_success_terminal`,
`scripts/tests/test_builtin_loops.py:60-92`) currently **passes** for
`general-task.yaml`, confirming `get_failure_states()` is non-empty in the
same code path the gate exercises. `scripts/tests/test_fsm_schema.py`'s
`get_failure_states()` coverage and `test_fsm_persistence.py`'s
`final_status` mapping tests also pass on current `main`.

The issue's claim "`FSM.get_failure_states()` ... returns an **empty set**
for this loop" (Current Behavior) does not hold against current `main` —
it would only hold if the `failed` state name were *not* in
`FAILURE_TERMINAL_NAMES`, or if `from_dict` were called without passing
`name=` (the standalone-parse case, per the docstring at
`schema.py:799-802`), neither of which applies to the real load path.

**What still needs to be confirmed, not assumed, before closing this issue
as stale:**
- Whether the *explicit* `failure: true` key is still wanted on
  `general-task.yaml`'s `failed` terminal for clarity/documentation, even
  though the implicit default already produces correct behavior (the name-based
  fallback is explicitly documented as backward-compat, not a long-term
  substitute for the explicit flag — see `schema.py:26-32`).
- Whether AC items about `spike-gate`/`proof-first-task` `impl_failed`
  reachability and the `prd-hermes` `--dry-run` handler still need live
  verification (schema-level confirmation above only proves
  `get_failure_states()`, not the full sub-loop dispatch / CLI exit-code
  chain end-to-end).
- Re-run `/ll:ready-issue ENH-2892` or `/ll:verify-issues` to re-validate
  the issue's claims against current `main` before implementation — the
  premise driving Acceptance Criteria #1 and #3 may already be satisfied,
  which would make this a no-op or a much smaller "make it explicit"
  change rather than the behavior change described in Blast Radius.

**Additional corrections surfaced by deeper analysis of the exit-code /
sub-loop-dispatch chain** (`scripts/little_loops/fsm/executor.py`):

- `PersistentExecutor._finish()` (`executor.py:2935-2946`) and the sub-loop
  `on_yes`/`on_no` dispatch (`executor.py:1038-1053`) both key off
  `ExecutionResult.failure_terminal`, which is itself derived from
  `get_failure_states()` membership — not a fresh name check. So the same
  fallback that makes `get_failure_states()` non-empty for `general-task`
  should already propagate through to CLI exit code
  (`cli/loop/_helpers.py:1921-1923`) and to `spike-gate`/`proof-first-task`'s
  `on_failure: impl_failed` routing, under current code.
- The issue's "~15 `on_error: diagnose` edges" count is closer to **10**
  (`general-task.yaml:113, 132, 185, 266, 376, 395, 549, 625, 649, 772`).
  `diagnose` itself is a single unconditional `next: failed`
  (`general-task.yaml:938-949`), so all 10 land on `failed` deterministically.
- `final_verify` itself does **not** route to `diagnose`/`failed` — its
  `on_error: summarize_partial` (`general-task.yaml:592`) deliberately lands
  on `partial` (ENH-2575 rationale, comment at `:587-591`). Only its
  downstream sibling states (`run_final_tests:625`, `count_final:649`) carry
  their own `on_error: diagnose` edges into the shared funnel — "`final_verify`'s
  chain" in Current Behavior should read as those downstream states, not
  `final_verify` itself.
- No current test in `test_builtin_loops.py` or `test_general_task_loop.py`
  exercises `general-task`'s `failed` terminal's `failure` flag or asserts an
  exit code for a run reaching it — AC #4 ("audit tests for exit-code
  assumptions") likely finds nothing to update, not because the audit is
  unnecessary but because no such test currently exists.
- `.issues/enhancements/P2-ENH-2825-add-failed-terminals-to-built-in-loops.md`
  (this issue's own `relates_to` list) has a Resolution Note discussing
  `general-task` already having "a failure terminal" at that time —
  consistent with the fallback already being active before ENH-2892 was
  captured, and worth reading directly before deciding this issue's fate.

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

- [x] `failed` in `general-task.yaml` carries `failure: true`
- [x] `partial` and `done` are left **without** `failure: true` (see Proposed change)
- [x] A test asserts `get_failure_states()` for general-task is non-empty
- [x] Existing tests that drive general-task to `failed` are audited for exit-code
      assumptions and updated where they assumed exit 0
- [x] `spike-gate`'s and `proof-first-task`'s `impl_failed` states are shown to be
      reachable — a general-task sub-loop run reaching `failed` routes to
      `on_failure`, not `on_success`
- [x] The `prd-hermes` `ll_loop_run --dry-run` handler expectation
      (`success=True`) is re-checked against the new exit code
- [x] `python -m pytest scripts/tests/` exits 0

## Resolution

- Added `failure: true` to `general-task.yaml`'s `failed` terminal
  (`general-task.yaml:951-953`). This is behavior-preserving at the
  `get_failure_states()` level (the implicit `FAILURE_TERMINAL_NAMES`
  fallback already covered it — see Codebase Research Findings above) but
  makes the flag explicit rather than relying on the name-convention
  fallback, and closes the test gaps below.
- `scripts/tests/test_fsm_schema.py::test_general_task_failed_terminal_is_flagged`
  — pins `get_failure_states()` non-empty and `failure` flags for
  `failed`/`done`/`partial` against the real `general-task.yaml`, not just
  the generic name-convention fallback (would catch a regression to
  implicit-only).
- `scripts/tests/test_enh2892_subloop_failure_dispatch.py` — new e2e
  subprocess test mirroring `spike-gate`/`proof-first-task`'s exact
  sub-loop delegation shape (`loop: ${context.impl_loop}`,
  `on_success`/`on_failure`). Confirms a sub-loop reaching a `failure:
  true` terminal routes the parent to `on_failure` (`impl_failed`), not
  `on_success` — closing the previously-unreachable branch.
- Audited existing tests referencing general-task for exit-code
  assumptions (`test_general_task_loop.py`, `test_ll_loop_commands.py`,
  `test_builtin_loops.py`, etc.) — none drive a real run to the `failed`
  terminal and assert on exit code/status, confirming the issue's own
  finding that nothing needed updating.
- `--dry-run` (`cli/loop/run.py:251`) renders the execution plan/diagram
  and returns before any state executes, so it can never reach `failed`
  regardless of this change — the prd-hermes handler's `success=True`
  expectation is unaffected. No live test covers that handler (it's design
  prose under `.loops/plans/prd-hermes/`), so this is a confirmation note,
  not a code change.
- Full suite: `python -m pytest scripts/tests/` — 17006 passed, 42 skipped.

### Tests

_Wiring pass added by `/ll:wire-issue` (2026-07-29):_

- `scripts/tests/test_fsm_schema.py:4435` — existing `test_get_failure_states()`
  is the generic-suite location; add a general-task-specific pin here (or
  alongside it) asserting `load_and_validate("general-task.yaml")`'s
  `fsm.get_failure_states()` contains `"failed"` and
  `fsm.states["failed"].failure is True` — narrower than
  `test_builtin_loops.py`'s whole-suite `test_no_failure_edge_routes_to_a_success_terminal`
  (`scripts/tests/test_builtin_loops.py:57-96`), which already passes today via
  the implicit `FAILURE_TERMINAL_NAMES` fallback and won't catch a regression
  to that fallback itself. [Agent 3 finding]
- `scripts/tests/test_enh2814_failure_terminal_e2e.py` — pattern to follow for
  an e2e exit-code/persistence test against the *real* `general-task.yaml`
  (its own tests use a synthetic fixture loop, not general-task itself):
  `test_failure_terminal_exits_nonzero`, `test_success_terminal_still_exits_zero`,
  `test_conventional_failed_name_defaults_to_flagged`,
  `test_persisted_final_status_is_failed`. [Agent 3 finding]
- Sub-loop delegation coverage gap confirmed absent, not just unverified: grep
  for `impl_failed|impl_loop` across `scripts/tests/` returns no hits — no
  existing test drives a failing `general-task` sub-run through
  `loops/spike-gate.yaml` or `loops/proof-first-task.yaml` to their
  `impl_failed` terminal. A new subprocess-based test for this closes AC #5
  rather than just "showing reachability" by inspection. [Agent 3 finding]
- prd-hermes `ll_loop_run --dry-run` `success=True` expectation (AC #6): no
  `test_prd_hermes*`/`hermes`-named test file exists under `scripts/tests/` —
  the references are design-doc prose under `.loops/plans/prd-hermes/`, not a
  live test. Confirm during implementation whether that handler even has
  automated coverage to update, or whether AC #6 is satisfied by a manual
  confirmation note. [Agent 3 finding]

### Confirmation (no new coupling found)

_Wiring pass added by `/ll:wire-issue` (2026-07-29):_ a side-effect-surface
sweep across the executor (`_finish()`, sub-loop `on_yes`/`on_no` dispatch),
persistence (`_map_final_status()`), validation
(`_validate_failure_terminal_action`), CLI exit-code plumbing, and the FSM
JSON schema found every consumer reads the parsed `StateConfig.failure`
boolean — none inspect the YAML source text for a literal `failure:` key.
No code path behaves differently between the implicit
`FAILURE_TERMINAL_NAMES` fallback and the explicit flag, and no additional
documentation, CLI, or schema coupling exists beyond what's already listed
in Blast Radius. This reinforces the issue's own finding that the change is
behavior-preserving at the schema level; its value is explicitness plus
closing the test gaps above. [Agent 2 finding]

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-07-29T00:00:00Z - `09e05048-ae16-423d-ab04-2d7cf0eb1dd3.jsonl`
- `/ll:wire-issue` - 2026-07-29T05:34:33 - `e303e84c-229a-4fac-9851-3739bde117c7.jsonl`
- `/ll:refine-issue` - 2026-07-29T05:28:19 - `54e44bce-2024-41cd-b8d9-3c07fef671ab.jsonl`
- `/ll:manage-issue` - 2026-07-29T05:44:20Z - `06ac3d9d-829b-481b-b75f-8123b4a0596b.jsonl`
