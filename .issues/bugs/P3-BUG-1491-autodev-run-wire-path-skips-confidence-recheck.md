---
id: BUG-1491
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T04:06:13Z'
completed_at: '2026-05-16T04:58:35Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
relates_to: BUG-1490
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1491: `autodev` `run_wire` repair path skips confidence recheck; stale scores cause silent skip

## Summary

When `autodev`'s `check_missing_artifacts` → `run_wire` → `run_refine` path runs to repair
a wiring gap, no confidence-check is rerun afterward. `enqueue_or_skip` evaluates whether
children were created (they won't be for a repair run), then `recheck_after_size_review`
checks readiness against the **pre-repair frontmatter scores**. If wire+refine improved the
issue but the scores weren't recalculated, the issue is silently skipped even though it is
now implementation-ready.

## Current Behavior

Repair path in `autodev.yaml`:

```
check_missing_artifacts (yes) → run_wire → run_refine → enqueue_or_skip
  → no children created → recheck_after_size_review
  → reads stale outcome_confidence from frontmatter → fails threshold → dequeue_next (skip)
```

No `confidence-check` call exists between `run_refine` and `enqueue_or_skip`.

## Steps to Reproduce

1. Run `ll-auto` or `ll-sprint` on an issue that has `missing_artifacts=true` in frontmatter
2. `check_missing_artifacts` routes `on_yes` → `run_wire`
3. `run_wire` executes `/ll:wire-issue` and chains to `run_refine`
4. `run_refine` executes `/ll:refine-issue` — wire+refine improves the issue but does not create child issues
5. `enqueue_or_skip` detects no new children and routes `on_no` → `recheck_after_size_review`
6. `recheck_after_size_review` reads `outcome_confidence` from frontmatter — these are the **pre-repair** scores
7. Observe: issue is silently skipped (`dequeue_next`) even though wire+refine resolved the wiring gap

## Expected Behavior

After `run_wire` → `run_refine`, rerun `/ll:confidence-check` so frontmatter scores
reflect the post-repair state before `recheck_after_size_review` evaluates them.
Mirrors the `rerun_confidence_after_decide` → `recheck_after_decide` pattern already
used in the `run_decide` path.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **States**: `run_wire` (line 241) → `run_refine` (line 252) → `enqueue_or_skip` (line 442)
- **Missing step**: A `rerun_confidence_after_wire` state between `run_refine` and
  `enqueue_or_skip`, analogous to `rerun_confidence_after_decide` (line 188)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Exact current state structures (verified):

```yaml
# autodev.yaml line 241
run_wire:
    fragment: with_rate_limit_handling
    action: "/ll:wire-issue ${captured.input.output} --auto"
    action_type: slash_command
    next: run_refine
    on_error: run_refine
    on_rate_limit_exhausted: done

# autodev.yaml line 252
run_refine:
    fragment: with_rate_limit_handling
    action: "/ll:refine-issue ${captured.input.output} --auto"
    action_type: slash_command
    next: enqueue_or_skip          # ← must change to rerun_confidence_after_wire
    on_error: enqueue_or_skip      # ← must change to rerun_confidence_after_wire
    on_rate_limit_exhausted: done

# autodev.yaml line 188 — exact template to mirror
rerun_confidence_after_decide:
    fragment: with_rate_limit_handling
    action: "/ll:confidence-check ${captured.input.output}"
    action_type: slash_command
    next: recheck_after_decide
    on_error: recheck_after_decide
    on_rate_limit_exhausted: done
```

The interpolation variable `${captured.input.output}` is the issue ID propagated from `dequeue_next`'s `capture: input` (line 87). It is used identically across all states in this chain.

## Proposed Solution

Add a `rerun_confidence_after_wire` state between `run_refine` and `enqueue_or_skip` in
`autodev.yaml`, modeled directly on the existing `rerun_confidence_after_decide` state:

```yaml
rerun_confidence_after_wire:
  # After run_wire → run_refine repairs a wiring gap, frontmatter scores still hold
  # pre-repair values. Re-run confidence-check so enqueue_or_skip / recheck_after_size_review
  # evaluate fresh scores — mirrors rerun_confidence_after_decide.
  fragment: with_rate_limit_handling
  action: "/ll:confidence-check ${captured.input.output}"
  action_type: slash_command
  next: enqueue_or_skip
  on_error: enqueue_or_skip
  on_rate_limit_exhausted: done
```

Update `run_refine` transitions:

```yaml
run_refine:
  next: rerun_confidence_after_wire      # was: enqueue_or_skip
  on_error: rerun_confidence_after_wire  # was: enqueue_or_skip
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add `rerun_confidence_after_wire` state; update `run_refine.next` and `run_refine.on_error`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — FSM executor; no changes needed (state is self-describing)

### Similar Patterns
- `rerun_confidence_after_decide` in `autodev.yaml` (~line 188) — exact template to mirror

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` class; add tests for `rerun_confidence_after_wire` mirroring `test_rerun_confidence_after_decide_*` methods (lines 1703–1760); also add `rerun_confidence_after_wire` to the `required` set in `test_required_states_exist` (line 1165); add `test_run_refine_next_routes_to_rerun_confidence_after_wire` and `test_run_refine_on_error_routes_to_rerun_confidence_after_wire` (no `run_refine.next` tests exist yet)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — line 483 flow diagram shows `run_wire → enqueue_or_skip` (stale; misses `run_refine` and the new `rerun_confidence_after_wire` step); line 507 prose describes the `check_missing_artifacts` branch as routing to `run_wire` "before re-queuing" without naming `run_refine` or the confidence recheck — both need updating to show the full chain `run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip` [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/autodev.yaml` and locate `run_refine` (line 252)
2. Add `rerun_confidence_after_wire` state immediately after `run_refine`, copied verbatim from `rerun_confidence_after_decide` (line 188) with `next/on_error` changed to `enqueue_or_skip`
3. Update `run_refine.next` (currently `enqueue_or_skip`) and `run_refine.on_error` (currently `enqueue_or_skip`) to `rerun_confidence_after_wire`
4. Verify FSM graph: `check_missing_artifacts → run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip`
4a. Update `docs/guides/LOOPS_GUIDE.md`:
    - Line 483 flow diagram: replace `run_wire → enqueue_or_skip → dequeue_next` with `run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip → dequeue_next`
    - Line 507 prose: update the `check_missing_artifacts` branch description to name the full chain `run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip` (also update identical stale descriptions on lines 490, 493, 498 if present)
5. In `scripts/tests/test_builtin_loops.py`, `TestAutodevLoop` class:
   a. Add `"rerun_confidence_after_wire"` to the `required` set in `test_required_states_exist` (line 1165)
   b. Add 7 test methods for `rerun_confidence_after_wire` mirroring the `test_rerun_confidence_after_decide_*` block (lines 1703–1760): state_exists, fragment, action_type, action_contains_confidence_check, next→enqueue_or_skip, on_error→enqueue_or_skip, on_rate_limit_exhausted→done
   c. Add `test_run_refine_next_routes_to_rerun_confidence_after_wire` and `test_run_refine_on_error_routes_to_rerun_confidence_after_wire` (no `run_refine.next` tests currently exist)
6. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v` to confirm no regressions

## Impact

- **Priority**: P3 — Affects reliability of the `check_missing_artifacts` repair path; issues with wiring gaps are silently skipped instead of proceeding to implementation
- **Effort**: Small — Single additive state in `autodev.yaml` mirroring a proven pattern; no new logic required
- **Risk**: Low — Purely additive; only the repair path is affected; the `rerun_confidence_after_decide` pattern is already proven in production
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A new state (`rerun_confidence_after_wire` or equivalent) runs between `run_refine`
      and `enqueue_or_skip` in the `check_missing_artifacts` repair path
- [ ] After wire+refine, `recheck_after_size_review` reads fresh frontmatter scores
- [ ] The fix mirrors the `rerun_confidence_after_decide` → `recheck_after_decide` pattern
      (autodev.yaml lines ~197-219)
- [ ] Issues that pass confidence post-repair proceed to `implement_current`, not `dequeue_next`

## Labels

`automation`, `loop-fsm`, `autodev`, `confidence-check`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-16T04:56:44 - `8a4d937a-2a7e-45c3-bd45-fbce611870f9.jsonl`
- `/ll:confidence-check` - 2026-05-16T04:15:00Z - `ac74761e-2330-4861-988a-80903ebce34d.jsonl`
- `/ll:wire-issue` - 2026-05-16T04:53:47 - `90727a00-58ce-45b8-ae57-4915dac8ae35.jsonl`
- `/ll:refine-issue` - 2026-05-16T04:50:05 - `eabd0815-cd65-4f7d-8ee4-1f7018ddccaa.jsonl`
- `/ll:format-issue` - 2026-05-16T04:10:07 - `bcde298f-4572-40d8-ac16-583ca4707b75.jsonl`
- `/ll:capture-issue` - 2026-05-16T04:06:13Z - `ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
