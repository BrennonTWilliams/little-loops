---
discovered_date: 2026-03-13
discovered_by: manual-audit
resolved_date: 2026-03-13
resolved_by: manual
confidence_score: 100
outcome_confidence: 100
---

# BUG-735: `issue-refinement` loop exhausts iteration budget on stubborn issues

## Summary

Three defects in `loops/issue-refinement.yaml` caused the loop to terminate at
`max_iterations=50` mid-run without completing — stuck cycling on a single issue (ENH-731)
that never graduated. Evidence from `ll-loop history issue-refinement`: iterations 41–50 were
all consumed by a single NEEDS_REFINE issue.

---

## Defects Fixed

### 1. CRITICAL — `max_iterations=50` structurally too low

**Root cause:** Each work cycle burns ~6 FSM iterations:
```
evaluate(1) → parse_id(1) → route_format(1) → [route_score(1)] → action(1) → check_commit(1)
```
50 iterations ≈ 8 work actions — insufficient for any non-trivial backlog (10+ issues).

**Fix:** Raised `max_iterations` from 50 to 200, providing ~33 work actions per run.

```yaml
# before
max_iterations: 50

# after
max_iterations: 200
```

---

### 2. HIGH — Per-issue refinement cap required `cs >= 85` to graduate

**Root cause:** The graduation condition was `cs >= 85 and rc >= 5`. An issue stuck below
`cs=85` (like ENH-731) could never graduate regardless of how many refinements it had
accumulated — it would loop forever until max_iterations.

**Fix:** Removed the `cs >= 85` precondition. The cap is now unconditional: any issue with
`rc >= 5` is graduated, period. This prevents a single pathologically stubborn issue from
consuming the entire iteration budget.

```python
# before
if cs >= 85 and rc >= 5:
    continue

# after (hard cap)
if rc >= 5:
    continue  # graduate regardless of score after 5 refinements
```

---

### 3. MEDIUM — `on_error: evaluate` in `evaluate` state caused infinite retry

**Root cause:** If `ll-issues refine-status` had a persistent failure (corrupted issue file,
CLI bug), the `on_error: evaluate` transition caused the loop to retry the failing shell
command on every iteration until max_iterations, burning the entire budget with no useful work.

**Fix:** Changed `on_error` to `done` so a broken classifier fails gracefully instead of
retrying forever.

```yaml
# before
on_error: evaluate

# after
on_error: done
```

---

## File Changed

- `loops/issue-refinement.yaml`

## Verification

After changes, the loop should:
1. Reach `done` terminal state rather than `loop_complete [max_iterations]`
2. Process multiple distinct issues per run (not just one stuck issue)
3. Graduate any issue that has been through `/ll:refine-issue` 5 times, regardless of score
4. Fail gracefully (exit to `done`) if `ll-issues` itself is broken
