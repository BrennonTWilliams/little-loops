---
id: BUG-2744
type: bug
status: done
captured_at: '2026-07-23T00:48:32Z'
completed_at: '2026-07-23T01:12:44Z'
discovered_date: 2026-07-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
---

# BUG-2744: autodev's check_guard2_verdict can read stale cross-issue captured state

## Summary

`check_guard2_verdict` in `scripts/little_loops/loops/autodev.yaml` (~line 1092)
evaluates `${captured.size_review_output.output}`, but `size_review_output` is
only ever captured by `run_size_review` (line 917). A shortcut path exists —
`detect_children → size_review_snap → check_broke_down` (`on_no`, line 723) →
`enqueue_or_skip` → `check_parent_resolved_post_size_review` (`on_no`) →
`check_spike_needed_before_skip` (`on_no`) → `check_reconcile_needed` (`on_no`)
→ `check_guard2_verdict` — that reaches `check_guard2_verdict` **without
`run_size_review` ever running for the current issue**. `ll-loop validate`
already flags this:

```
[WARNING] states.check_guard2_verdict.action: References ${captured.size_review_output.*}
but 'size_review_output' is captured by state 'run_size_review' which may not execute on
all paths to 'check_guard2_verdict'.
```

`self.captured` in `scripts/little_loops/fsm/executor.py:227` is a single dict
that persists for the **entire autodev run**, across all dequeued issues —
confirmed by grep, there is no reset site (no `captured.clear()`, no
`captured = {}`, nothing keyed by issue on `dequeue_next`). So when the
shortcut path is taken, `check_guard2_verdict` doesn't fail closed on missing
data — it reads whatever a **previous, unrelated issue** left in
`captured.size_review_output` during the same run.

## Current Behavior

If issue A earlier in the run went through `run_size_review` and got a
guard-2 "Very Large, declined decomposition" verdict (`skipped: score 8-11`)
captured, and issue B later in the same run takes the `check_broke_down`
shortcut (its sub-loop already decomposed it, but
`check_parent_resolved_post_size_review`'s parent-status check doesn't
short-circuit because the parent isn't yet marked `done`/`cancelled`),
`check_guard2_verdict` evaluates issue A's stale captured text against issue
B. If it matches the guard-2 pattern, issue B — which was never itself
size-reviewed this pass and was already handled by decomposition — gets
misrouted into `check_readiness_for_atomic_remediation`'s earn-the-pass
remediation flow, which doesn't apply to it.

(On the first issue of a run, or when no prior issue captured
`size_review_output`, `interpolate()` raises `InterpolationError`, which is
caught and falls back to empty `raw_output` — that case is safe. The bug is
specifically the stale-carryover case.)

## Expected Behavior

`check_guard2_verdict`'s evaluation should only ever reflect the *current*
issue's size-review outcome. When `run_size_review` did not run for this
issue this pass, the state should not evaluate `captured.size_review_output`
at all.

## Motivation

Cross-issue state leakage in an unattended automation loop (`ll-auto`) is a
silent-misrouting bug: it can trigger `remediate_oversized_atomic` for an
issue that was already correctly resolved by decomposition, wasting a
remediation pass and potentially perturbing an issue that needed no further
action. It's narrow (requires a specific combination of a prior guard-2-skip
issue plus a later issue hitting the parent-not-yet-resolved edge), but it's
a genuine correctness bug, not a validator false-positive — confirmed by
tracing `self.captured`'s lifetime in the executor.

## Proposed Solution

Preferred: route around `check_guard2_verdict` on paths where
`run_size_review` didn't run this pass, since guard-2 semantics only make
sense when the current issue actually went through size-review this pass.
Concretely:

- `check_broke_down`'s `on_no: enqueue_or_skip` (line 723) shortcut, and/or
- `check_parent_resolved_post_size_review`'s `on_no` chain (line 1001),

should bypass `check_guard2_verdict` and go straight to
`recheck_after_size_review` (mirroring `check_spike_needed_before_skip`'s
`on_error` fallback at line 1036, which already does this).

Alternative (not preferred — treats the symptom, not the cause): clear/reset
`captured.size_review_output` at `dequeue_next` so a stale read fails closed
instead of matching wrong data. This still requires `check_guard2_verdict` to
handle the now-guaranteed-missing case gracefully (falls back to `on_no` via
the existing `InterpolationError` catch, so this alone would fix the reported
symptom) but doesn't address the deeper issue that `check_guard2_verdict` is
reachable on paths where it has no valid input at all.

### Verification

After the fix, `ll-loop validate scripts/little_loops/loops/autodev.yaml`
should no longer emit the `check_guard2_verdict` / `size_review_output`
reachability warning.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/validation.py:2765` `_validate_capture_reachability()`
  is the rule emitting the cited warning (dominance check via
  `_dominated_by_any`, line 2650). It already has a documented, narrower
  false-positive carve-out for this same state in
  `scripts/tests/test_builtin_loops.py`'s `ALLOWLIST` dict (~line 10988),
  keyed `("autodev", "capture-ordering")`. That entry's rationale covers only
  the *children-found* branch of `check_broke_down.on_no` (a runtime
  invariant the static validator can't see) and predates this issue's
  no-children/stale-carryover case. Whichever fix lands should revisit that
  allowlist entry: the preferred routing fix narrows what it needs to cover;
  the alternative (clear-on-dequeue) fix may let the entry be removed
  entirely once `ll-loop validate` stops flagging the path at all.
- Two existing tests assert `check_guard2_verdict`'s own `on_no`/`on_error`
  targets and must keep passing under either fix, since neither fix removes
  `check_guard2_verdict` itself:
  - `scripts/tests/test_builtin_loops.py:4330`
    `test_check_guard2_verdict_routes_to_remediation_chain`
  - `scripts/tests/test_autodev_decision_gate.py:520`
    `test_reconcile_gate_routing`
- `scripts/tests/test_autodev_decision_gate.py:36-94` provides a reusable
  `_StubRunner` / `_state()` / `_loop()` / `_run_decision_chain()` harness
  (see `TestReconcilePlateauRouting`) that runs a real `FSMExecutor` over a
  miniature FSM graph to prove routing at execution time, not just via
  YAML-shape assertions — the established pattern for a regression test
  proving the bypass chain reaches `recheck_after_size_review` without ever
  visiting `check_guard2_verdict`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — reroute `check_broke_down`'s
  `on_no` (lines 701-724) and/or `check_parent_resolved_post_size_review`'s
  `on_no` chain (lines 983-1002 → 1004-1036 → 1038-1069) to bypass
  `check_guard2_verdict` (1071-1098) and land directly on
  `recheck_after_size_review` (starts line 1214), mirroring
  `check_spike_needed_before_skip`'s `on_error: recheck_after_size_review`
  (line 1036).
- `scripts/tests/test_builtin_loops.py` — `ALLOWLIST` dict entry keyed
  `("autodev", "capture-ordering")` (~line 10988) needs its rationale
  narrowed or removed depending on which fix lands (see Codebase Research
  Findings under Proposed Solution).

### Dependent Files (Callers/Referencing States)
- `scripts/little_loops/loops/autodev.yaml:922-981` `enqueue_or_skip` — reached
  both from `check_broke_down.on_no` (bypass path) and from
  `run_size_review.next` (normal path); same state, two provenances, unaffected
  by the fix itself but confirms the shortcut's entry point.
- `scripts/little_loops/loops/autodev.yaml:903-920` `run_size_review` — the
  sole state that populates `capture: size_review_output`; not modified by
  the preferred fix.
- `scripts/little_loops/fsm/executor.py:227` `self.captured` init, and capture
  write sites at lines 895, 972, 979, 991, 1679 — relevant only to the
  alternative (clear-on-dequeue) fix, which would add a reset call near
  `dequeue_next` (`autodev.yaml:73-110`).
- `scripts/little_loops/fsm/validation.py:2765` `_validate_capture_reachability()`
  — the validator whose warning should disappear (or narrow) after the fix;
  not itself modified unless the allowlist entry is removed.

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml:1004-1036` `check_spike_needed_before_skip`
  — its `on_error: recheck_after_size_review` fallback is the direct routing
  precedent to mirror for the preferred fix.

### Tests
- `scripts/tests/test_builtin_loops.py:4330`
  `test_check_guard2_verdict_routes_to_remediation_chain` — existing
  structural assertion on `check_guard2_verdict`'s own `on_no`/`on_error`;
  must keep passing.
- `scripts/tests/test_autodev_decision_gate.py:520` `test_reconcile_gate_routing`
  — existing structural assertion on the same chain from the caller's side;
  must keep passing.
- `scripts/tests/test_autodev_decision_gate.py:36-94` — `_StubRunner`/`_state()`/
  `_loop()`/`_run_decision_chain()` harness for a new executor-driven
  regression test proving the bypass chain never visits
  `check_guard2_verdict`.

### Configuration
- None — this is a routing-only change confined to `autodev.yaml` and its
  test coverage.

## Implementation Steps

1. Update `check_broke_down`'s `on_no` target (`autodev.yaml:701-724`) and/or
   `check_parent_resolved_post_size_review`'s `on_no` chain
   (`autodev.yaml:983-1002`) so the shortcut path routes to
   `recheck_after_size_review` instead of continuing through
   `check_spike_needed_before_skip` → `check_reconcile_needed` →
   `check_guard2_verdict`.
2. Add a `TestCheckGuard2VerdictBypass`-style test class in
   `scripts/tests/test_autodev_decision_gate.py`, modeled on
   `TestReconcilePlateauRouting` (lines 36-94), that runs a real
   `FSMExecutor` over the shortcut chain and asserts `check_guard2_verdict`
   is never visited while `recheck_after_size_review` is.
3. Update or remove the `("autodev", "capture-ordering")` `ALLOWLIST` entry
   in `scripts/tests/test_builtin_loops.py` (~line 10988) to match the new
   routing, and confirm `test_check_guard2_verdict_routes_to_remediation_chain`
   (line 4330) and `test_reconcile_gate_routing`
   (`test_autodev_decision_gate.py:520`) still pass unchanged.
4. Run `ll-loop validate scripts/little_loops/loops/autodev.yaml` and confirm
   the `check_guard2_verdict` / `size_review_output` reachability warning is
   gone (or, if the alternative fix is chosen instead, confirm it now reads
   as a guaranteed-missing case that fails closed).
5. Run `python -m pytest scripts/tests/test_autodev_decision_gate.py
   scripts/tests/test_builtin_loops.py -v`.

## Impact

- **Priority**: P3 — narrow edge case (requires a specific sequence of two
  issues in one `ll-auto` run) but a real automation-correctness bug with a
  clear, already-flagged repro signal.
- **Effort**: Small — routing-only change to `on_no` targets in
  `scripts/little_loops/loops/autodev.yaml`, no executor changes required for
  the preferred fix.
- **Risk**: Low — the new route target (`recheck_after_size_review`) is
  already a valid next-state used by sibling paths in the same file.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/autodev.yaml` | File containing the bug |
| `scripts/little_loops/fsm/executor.py` | `self.captured` lifecycle (line 227) |

## Root Cause

`scripts/little_loops/fsm/executor.py:227` — `self.captured` is a flat dict
scoped to the executor instance (the whole run), not to the current
loop-body iteration. `scripts/little_loops/loops/autodev.yaml:917` captures
`size_review_output` only in `run_size_review`, but
`scripts/little_loops/loops/autodev.yaml:1094`
(`check_guard2_verdict.evaluate.source`) is reachable via a routing path
(`check_broke_down.on_no` → ... → `check_guard2_verdict`) that never visits
`run_size_review` for the current issue, so the read can return a value
written by a prior issue's pass through `run_size_review` instead.

## Session Log
- `/ll:ready-issue` - 2026-07-23T01:03:15 - `190ad800-a68e-48d0-bda9-88c8b3e425c3.jsonl`
- `/ll:refine-issue` - 2026-07-23T00:54:20 - `696cd091-d01d-41fa-bc37-653ef4a837a3.jsonl`
- `/ll:confidence-check` - 2026-07-23T01:15:00 - `8c0250f9-ef2b-4eb5-b183-6f897ea1b541.jsonl`
- `/ll:capture-issue` - 2026-07-23T00:48:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eeda73bb-8da1-43d1-990e-7fe80e806725.jsonl`
- `/ll:manage-issue` - 2026-07-23T01:12:06Z - `9844e5a4-d909-4645-926d-e2ee406f7cb8.jsonl`

---

## Status

- [x] Fixed
