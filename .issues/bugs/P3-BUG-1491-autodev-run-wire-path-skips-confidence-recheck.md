---
id: BUG-1491
type: BUG
priority: P3
status: open
captured_at: '2026-05-16T04:06:13Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
relates_to: BUG-1490
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
- **States**: `run_wire` (line ~241) → `run_refine` (line ~252) → `enqueue_or_skip`
- **Missing step**: A `rerun_confidence_after_wire` state between `run_refine` and
  `enqueue_or_skip`, analogous to `rerun_confidence_after_decide` (line ~197)

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
- `scripts/little_loops/ll_loop.py` — FSM executor; no changes needed (state is self-describing)

### Similar Patterns
- `rerun_confidence_after_decide` in `autodev.yaml` (~line 188) — exact template to mirror

### Tests
- `scripts/tests/test_builtin_loops.py` — verify autodev FSM graph includes new state and correct transitions

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/autodev.yaml` and locate `run_refine` (~line 252)
2. Add `rerun_confidence_after_wire` state immediately after `run_refine`, copied from `rerun_confidence_after_decide` with `next/on_error` pointing to `enqueue_or_skip`
3. Update `run_refine.next` and `run_refine.on_error` to `rerun_confidence_after_wire`
4. Verify FSM graph: `check_missing_artifacts → run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip`
5. Run `scripts/tests/test_builtin_loops.py` to confirm no regressions

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
- `/ll:format-issue` - 2026-05-16T04:10:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcde298f-4572-40d8-ac16-583ca4707b75.jsonl`
- `/ll:capture-issue` - 2026-05-16T04:06:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
