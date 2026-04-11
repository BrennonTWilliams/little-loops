---
id: BUG-1026
type: bug
priority: P3
title: "fix retry routing in refine-to-ready-issue loop"
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# BUG-1026: Fix retry routing in refine-to-ready-issue loop

## Summary

In the `refine-to-ready-issue` FSM loop, when confidence thresholds are not met after a refinement pass, the retry path routes back through `check_lifetime_limit` before reaching `refine_issue`. This is one step too far back — `format_issue` only needs to run once per run, and `check_lifetime_limit` is unnecessary indirection on intra-run retries. Worse, the lifetime cap may have already incremented from the just-completed refinement, which can falsely trip the cap mid-run. The `on_yes` transition from `check_refine_limit` should route directly to `refine_issue`.

## Current Behavior

When scores don't meet thresholds after a refinement pass:

```
check_scores (no) → check_refine_limit (yes) → check_lifetime_limit → refine_issue
```

`check_lifetime_limit` re-checks `ll-issues refine-status`, but the count may have just incremented from the completed refinement — potentially causing a false lifetime-cap trip that aborts the run prematurely.

## Expected Behavior

The retry path should skip `check_lifetime_limit` and go directly to `refine_issue`:

```
check_scores (no) → check_refine_limit (yes) → refine_issue
```

The lifetime cap is already enforced at the beginning of each run before the first refinement. Skipping it on the intra-run retry is correct.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue` on an issue that needs two refinement passes
2. Observe that after the first pass fails the confidence check, the loop visits `check_lifetime_limit` before attempting the second pass
3. If the lifetime refine count is near its cap, the second pass may be incorrectly aborted

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `check_refine_limit` state (line 158)
- **Cause**: `on_yes` is set to `check_lifetime_limit` instead of `refine_issue`. The lifetime cap check belongs only at the start of a run, not between intra-run retry attempts.

## Motivation

Intra-run retries are governed by `check_refine_limit` (per-run cap). The lifetime cap (`check_lifetime_limit`) was designed as a pre-run guard against over-refining issues across sessions. Re-checking it mid-run can prematurely abort a run that is still within its per-run budget, especially when the lifetime count increments right after the first refinement.

## Proposed Solution

In `scripts/little_loops/loops/refine-to-ready-issue.yaml`, line 158:

Change:
```yaml
on_yes: check_lifetime_limit
```

To:
```yaml
on_yes: refine_issue
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — change `check_refine_limit.on_yes`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — FSM executor that reads the YAML config; no changes needed
- Any loop that calls `refine-to-ready-issue` as a sub-loop

### Similar Patterns
- Other built-in loops with `check_*_limit` states should be audited to ensure retry paths are similarly minimal

### Tests
- No automated FSM routing tests exist for this loop; trace manually
- Verify with `ll-loop run refine-to-ready-issue` on a stubborn issue

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/refine-to-ready-issue.yaml`
2. In the `check_refine_limit` state (line 158), change `on_yes: check_lifetime_limit` to `on_yes: refine_issue`
3. Trace the full FSM happy path and retry path to confirm no dead ends
4. Run a manual smoke test: `ll-loop run refine-to-ready-issue <issue-id>` and verify the retry goes directly to `refine_issue`

## Impact

- **Priority**: P3 - Logic error that can prematurely abort intra-run retries; affects only multi-pass refinement scenarios near the lifetime cap
- **Effort**: Small - Single line change in one YAML file
- **Risk**: Low - No Python code changes; FSM routing is declarative
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM loop execution model |
| `.claude/CLAUDE.md` | CLI tools reference for `ll-loop` |

## Labels

`bug`, `fsm`, `loops`, `refine-to-ready-issue`, `captured`

## Session Log
- `/ll:format-issue` - 2026-04-11T04:16:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11232320-22e5-4553-9a97-2031c0377954.jsonl`

- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4254e7c6-6671-4edc-8250-54edc6b02c61.jsonl`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3
