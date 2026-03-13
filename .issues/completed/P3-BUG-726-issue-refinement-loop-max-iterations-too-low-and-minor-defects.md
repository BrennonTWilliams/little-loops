---
discovered_date: 2026-03-13
discovered_by: audit
resolved_date: 2026-03-13
resolved_by: manual
---

# BUG-726: `loops/issue-refinement.yaml` — max_iterations too low and minor defects

## Summary

Five defects found in `loops/issue-refinement.yaml` via audit of live loop history:

1. **`max_iterations=100` too low** — the loop hit the hard cap mid-work on a 64-issue backlog
   (requires ~145+ iterations), forcing manual restart. `on_handoff: spawn` does not fire on
   max_iterations — it only fires on LLM context exhaustion.
2. **`init` state had dead evaluate config** — `rm -f` never errors (`-f` suppresses all errors),
   so `on_success` and `on_error` both pointed to `evaluate`. Should be an unconditional `next:`.
3. **`parse_id` awk lacked row anchor** — `awk '{printf $2}'` would concatenate field 2 from every
   line if multi-line output leaked into the `classify` capture variable.
4. **No `description:` field** — `ll-loop list` showed no description for this loop; all other
   loops have one.
5. **`rc >= 5` cap comment missing** — the graduation guard ordering (cap before threshold check)
   was non-obvious; ENH-507 was the only issue that had hit the cap.

## Location

- **File**: `loops/issue-refinement.yaml`
- **Lines**: `max_iterations: 100` (line 111), `init` state (lines 9–15), `parse_id` awk (line 49),
  loop header (lines 1–6), evaluate Python script (lines 29–35)

## Root Cause

- `max_iterations` was set conservatively at 100 when the loop was first written; backlog growth
  (64 issues × ~5 iterations/issue = ~320 minimum) outpaced the limit.
- `init` state was copy-pasted from a state that needed exit-code evaluation; `rm -f` never needs it.
- `parse_id` awk was written for the single-line case and not defensively guarded.
- `description:` field was never added at creation time.
- `rc >= 5` cap logic was self-evident to the original author but opaque to future readers.

## Fix Applied

All five changes made to `loops/issue-refinement.yaml` in a single session:

**1 — Increase max_iterations**
```yaml
# Before:
max_iterations: 100
# After:
max_iterations: 300
```

**2 — Simplify init state**
```yaml
# Before:
init:
  action: rm -f /tmp/issue-refinement-commit-count
  action_type: shell
  evaluate:
    type: exit_code
  on_success: evaluate
  on_error: evaluate
# After:
init:
  action: rm -f /tmp/issue-refinement-commit-count
  action_type: shell
  next: evaluate
```

**3 — Add row anchor to parse_id awk**
```yaml
# Before:
action: echo "${captured.classify.output}" | awk '{printf $2}'
# After:
action: echo "${captured.classify.output}" | awk 'NR==1{printf $2}'
```

**4 — Add description field**
```yaml
name: issue-refinement
description: |
  Progressively refine all active issues through format → score → refine pipeline.
  Routes each issue to the correct step using a deterministic shell classifier.
  Commits every 5 actions and continues until all issues meet quality thresholds.
```

**5 — Add clarifying comment for rc≥5 cap**
```python
# Cap: after 5 refinements with cs>=85, graduate even if oc is still low.
# Prevents infinite refinement loops on stubborn issues.
if cs >= 85 and rc >= 5:
    continue
```

## Verification Steps

1. `ll-loop run issue-refinement` — confirm loop processes past iteration 100
2. `ll-loop history issue-refinement` — verify history ends with `[terminal]` or `[handoff]`, not `[max_iterations]`
3. `ll-issues refine-status --json | python3 -c "import json,sys; issues=json.load(sys.stdin); print(sum(1 for i in issues if i.get('confidence_score') is None))"` — verify unscored count reaches 0 after a full run

## Impact

- **Priority**: P3 — loop silently stopped mid-work on every large run; users had to manually restart
- **Effort**: Trivial — five localized YAML edits, no logic changes
- **Risk**: None — max_iterations increase and awk guard are purely additive/defensive

## Labels

`bug`, `loops`, `fsm`, `issue-refinement`

## Session Log
- audit + fix — 2026-03-13 — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ece248e3-a7ba-4bdc-9a07-c3af61df2fe9.jsonl`

---

**Completed** | Created: 2026-03-13 | Resolved: 2026-03-13 | Priority: P3
