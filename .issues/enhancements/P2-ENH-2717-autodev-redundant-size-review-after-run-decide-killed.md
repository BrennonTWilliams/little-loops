---
id: ENH-2717
type: ENH
title: "autodev run_decide \u2192 run_size_review path wastes a full size-review call\
  \ when decide-issue is killed mid-turn"
priority: P2
status: done
captured_at: '2026-07-21T05:07:30Z'
completed_at: '2026-07-21T15:08:12Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
labels:
- autodev
- fsm
- token-cost
relates_to:
- ENH-2712
- BUG-2718
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2717: autodev run_decide → run_size_review path wastes a full size-review call when decide-issue is killed mid-turn

## Summary

During `ll-loop run autodev ENH-2712`, `run_decide` invoked `/ll:decide-issue ENH-2712 --auto`. The subprocess was still mid-turn — waiting on two parallel evidence-gathering subagents scoring Option A vs Option B — when `subprocess_utils.py`'s post-stream-close watchdog force-killed it (SIGKILL, exit -9) before it could produce a score or clear `decision_needed`. `run_decide`'s `on_error` routed to `recheck_after_decide`, which (correctly) still failed readiness, and fell through to `snap_and_size_review` → `run_size_review` — a full second LLM call (`/ll:issue-size-review --auto`, ~1m8s) that independently re-discovered the exact same unresolved `decision_needed: true` blocker before finally deferring via `mark_gate_blocked`.

## Current Behavior

`run_decide` (`scripts/little_loops/loops/autodev.yaml`, ~line 300) has `on_error: recheck_after_decide`. When `/ll:decide-issue --auto` is killed before completing (subprocess watchdog, crash, or any other on_error path), the FSM cannot distinguish "decide genuinely failed/was interrupted" from "decide ran to completion but scores are still low for unrelated reasons." Both cases fall through the same `recheck_after_decide` → `snap_and_size_review` → `run_size_review` path, which reruns `/ll:issue-size-review --auto` — a costly LLM call — even when the blocking cause (`decision_needed: true`, unchanged) is already fully known from `run_decide`'s failure.

## Expected Behavior

When `run_decide` fails to clear `decision_needed` (whether via `on_error` or via `recheck_after_decide` finding the flag still `true` post-run), the loop should short-circuit directly to `record_decision_unresolved` / `mark_gate_blocked` instead of routing through `snap_and_size_review` → `run_size_review`. Size-review adds no new information when the known blocker is an incomplete/failed decision — it's the same `decision_needed` check re-run against a fact that hasn't changed.

## Root Cause

Observed in `.loops/runs/autodev-20260720T235236/` / `.loops/.running/autodev-20260720T235236.log`:

- `[8/500] run_decide`: `/ll:decide-issue ENH-2712 --auto` started scoring Option A vs Option B via two parallel evidence-gathering subagents. Before it finished, the log shows: `Process 48056 did not exit within 30s after streams closed, killing` (`scripts/little_loops/subprocess_utils.py:511-518`), then `exit: -9`, then `-> recheck_after_decide` (the `on_error` route).
- `decision_needed` remained `true` on ENH-2712's frontmatter (decide never wrote a score).
- `recheck_after_decide` re-ran the readiness check (still failing) → `snap_and_size_review` → `[11/500] run_size_review`: `/ll:issue-size-review --auto` ran a full analysis and independently concluded: *"There's also an unresolved blocker: `decision_needed: true` ... hasn't been formally closed via `/ll:decide-issue`"* — the identical fact already known 3 states earlier — before the loop finally deferred ENH-2712 with `deferred_reason: low_readiness`.

**This issue is a mitigation, not the root-cause fix.** The actual reason `run_decide` failed to clear `decision_needed` is [[BUG-2718]]: `subprocess_utils.py`'s fixed 30s post-stream-close kill watchdog force-killed the `/ll:decide-issue --auto` process while it still had legitimate parallel subagent work in flight. This ENH stops the FSM from compounding that loss with a redundant `run_size_review` call regardless of *why* `run_decide` fails — but BUG-2718 is what should stop the kill (and the lost work) from happening in the first place. Implement both; this one is defense-in-depth for any `run_decide` failure mode, not a substitute for fixing the kill.

## Proposed Solution

In `autodev.yaml`, have `run_decide`'s `on_error` route to a state that checks whether `decision_needed` is still `true` and, if so, goes straight to `record_decision_unresolved` (bypassing `snap_and_size_review`/`run_size_review` entirely). If `decision_needed` was somehow cleared despite the error (unlikely but possible), fall back to the existing `recheck_after_decide` path so readiness is still re-evaluated normally.

## Implementation Steps

1. Add a `check_decision_after_decide_error` (or similar) state between `run_decide`'s `on_error` and `recheck_after_decide`, mirroring the existing `check-flag decision_needed` pattern used elsewhere in the file (`check_decision_at_dequeue`, `check_decision_after_refine`, `assert_decision_cleared`).
2. `on_yes` (decision_needed still true) → `record_decision_unresolved` directly.
3. `on_no`/`on_error` → fall through to existing `recheck_after_decide`.
4. Verify with a single-iteration run against an issue whose `decide-issue --auto` is forced to fail (or via `ll-loop simulate`/routing dry-run) that the redundant `run_size_review` state is skipped.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact edit point**: `scripts/little_loops/loops/autodev.yaml:311` — `run_decide.on_error: recheck_after_decide` is the single line to repoint to the new gate state (`run_decide` itself spans lines 301–312).
- **New state placement**: insert the new `check_decision_after_decide_error` state block between `run_decide` (ends line 312) and `mark_decide_ran` (starts line 314), or anywhere before `recheck_after_decide` (line 340) — ordering in the YAML doesn't affect FSM resolution, but co-locating it near `run_decide` keeps the decide-error path readable.
- **Exact pattern to copy**: `assert_decision_cleared` (`scripts/little_loops/loops/autodev.yaml:358-370`) is the closest structural analog — same one-field `check-flag decision_needed` predicate, same `on_yes: record_decision_unresolved` target:
  ```yaml
  check_decision_after_decide_error:
    action: "ll-issues check-flag ${captured.input.output} decision_needed"
    fragment: shell_exit
    on_yes: record_decision_unresolved
    on_no: recheck_after_decide
    on_error: recheck_after_decide
  ```
  (`check_decision_at_dequeue` at line 112-124 and `check_decision_after_refine` at line 182-190 use the identical three-line action/fragment/on_yes-on_no-on_error shape.)
- **`record_decision_unresolved`** (already exists, `scripts/little_loops/loops/autodev.yaml:372-387`) is the correct terminal target per the Proposed Solution — not `mark_gate_blocked` (line 504, a different gate for `LEARNING_GATE_BLOCKED`, unrelated to decisions). `record_decision_unresolved` already does the full job: appends to `autodev-decision-unresolved.txt`, clears the inflight sentinel, and calls `ll-issues set-status ... deferred --by automation --reason decision_unresolved` — no changes needed there.
- **Test pattern to follow**: `scripts/tests/test_autodev_decision_gate.py:686-724` (`TestAssertDecisionClearedStructural`) is the direct precedent for testing this kind of gate — structural assertions via a `_load_autodev_yaml()` fixture checking `state.get("on_yes") == ...` and `"ll-issues check-flag" in action`. A new `TestCheckDecisionAfterDecideErrorStructural` class following the same shape (asserting `run_decide.on_error == "check_decision_after_decide_error"`, the new state exists, uses the check-flag predicate, and routes `on_yes`→`record_decision_unresolved`/`on_no`→`recheck_after_decide`) would give this ENH the same test coverage BUG-2595 got for the analogous `assert_decision_cleared` gate.
- **`ll-issues check-flag` exit-code contract** (`scripts/little_loops/cli/issues/check_flag.py`): exits 0 if the frontmatter field equals `'true'` (→ `fragment: shell_exit`'s `on_yes`), non-zero otherwise (→ `on_no`) — confirms the same three-branch shape used by every other decision-gate state in this file is sufficient here; no new CLI surface needed.

## Impact

- **Priority**: P2 — low risk, saves a full LLM call (~1m8s+ tokens) on every autodev run where `run_decide` fails without clearing `decision_needed`.
- **Effort**: Small — one new routing state plus a re-point of `run_decide`'s `on_error`.
- **Risk**: Low — read-only routing change to an already-defensive gate chain (`assert_decision_cleared`/`record_decision_unresolved` already exist for the analogous post-`recheck_after_decide` case).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:4513-4516` (`test_run_decide_on_error_routes_to_implement_current`) — **will break**: hardcodes `assert state.get("on_error") == "recheck_after_decide"` for the `run_decide` state; must be updated to assert `"check_decision_after_decide_error"` once `run_decide.on_error` is repointed. Confirmed via grep across all `run_decide`/`on_error` hits in `scripts/tests/` — no other test asserts this specific edge. [wiring-pass finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:996,999,1011,1014,1023` — the ASCII FSM-flow diagram's five repeated `run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → ... (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)` lines show no `run_decide.on_error` branch at all; they go stale (silently incomplete, not wrong) once `check_decision_after_decide_error` becomes a real branch off `run_decide`. [wiring-pass finding]
- `docs/guides/LOOPS_REFERENCE.md:1028` — the "Diagram omissions" paragraph already documents `assert_decision_cleared → record_decision_unresolved` as one entry point into `record_decision_unresolved`; it should gain a sentence noting the new second entry point via `run_decide.on_error → check_decision_after_decide_error → record_decision_unresolved` (short-circuiting before `recheck_after_decide` ever runs). [wiring-pass finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py` — add a `TestCheckDecisionAfterDecideErrorStructural` class mirroring `TestAssertDecisionClearedStructural` (lines 686-780): state-exists, `ll-issues check-flag`+`decision_needed` predicate, `shell_exit` fragment, `on_yes → record_decision_unresolved`, `on_no → recheck_after_decide`, `on_error → recheck_after_decide` assertions. The refine-pass findings above (line 71) note this class as a nice-to-have; wiring makes it a required step, since it's the only permanent regression coverage for this gate — step 4's "single-iteration run" verification doesn't persist. [wiring-pass finding]
- `scripts/tests/test_builtin_loops.py:4513-4516` — update the existing assertion (see Dependent Files above) rather than leave it failing. [wiring-pass finding]

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_builtin_loops.py:4513-4516` — change the asserted value of `run_decide.on_error` from `"recheck_after_decide"` to `"check_decision_after_decide_error"` (this test otherwise fails immediately after the routing change).
6. Add `TestCheckDecisionAfterDecideErrorStructural` to `scripts/tests/test_autodev_decision_gate.py`, following the `TestAssertDecisionClearedStructural` pattern (lines 686-780).
7. Update `docs/guides/LOOPS_REFERENCE.md`'s ASCII FSM-flow diagram (lines 996-1023) and the "Diagram omissions" paragraph (line 1028) to reflect the new `run_decide.on_error → check_decision_after_decide_error` branch and its short-circuit into `record_decision_unresolved`.

## Resolution

Added `check_decision_after_decide_error` state to `scripts/little_loops/loops/autodev.yaml`, repointing `run_decide.on_error` to it (was `recheck_after_decide`). The new state runs `ll-issues check-flag ... decision_needed`: `on_yes` (still unresolved) short-circuits directly to `record_decision_unresolved`, bypassing `snap_and_size_review`/`run_size_review`; `on_no`/`on_error` fall back to the existing `recheck_after_decide` path.

- Updated `scripts/tests/test_builtin_loops.py::test_run_decide_on_error_routes_to_implement_current` to assert the new routing target.
- Added `TestCheckDecisionAfterDecideErrorStructural` to `scripts/tests/test_autodev_decision_gate.py` mirroring `TestAssertDecisionClearedStructural`.
- Updated `docs/guides/LOOPS_REFERENCE.md`'s "Diagram omissions" paragraph to document the new `run_decide.on_error → check_decision_after_decide_error` branch.
- `ll-loop validate` confirms the loop is structurally valid with the new state; full test suite (15719 passed, 38 skipped) and `ruff check` pass.

This is a mitigation for the FSM routing side of the problem; the underlying kill cause is tracked separately in [[BUG-2718]].

## Session Log
- `/ll:manage-issue` - 2026-07-21T15:07:30Z - `08403a1b-7e37-482e-b26a-65d54a388ff0.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00Z - `0302c6c3-3217-48a0-8b67-9a883481d865.jsonl`
- `/ll:wire-issue` - 2026-07-21T14:59:48 - `409cae54-3743-493c-9c93-11778287302e.jsonl`
- `/ll:refine-issue` - 2026-07-21T14:53:06 - `c8731edc-b610-421a-8d9b-ecb20724fb28.jsonl`
- `/ll:capture-issue` - 2026-07-21T05:07:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
