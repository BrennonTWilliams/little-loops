---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
---

# BUG-1032: `refine-to-ready-issue`: no direct path from score-failure to breakdown

## Summary

In `refine-to-ready-issue.yaml`, when `check_scores` fails and the per-run retry budget is exhausted (`check_refine_limit` → `on_no: failed`), the sub-loop exits at `failed` with no route to `breakdown_issue`. The `breakdown_issue` state is only reachable from `check_lifetime_limit` (the lifetime cap path). Breakdown is silently delegated to the parent `recursive-refine` loop via its indirect `detect_children → size_review_snap → recheck_scores → run_size_review` chain — meaning the sub-loop never initiates decomposition when scores persistently fail.

## Current Behavior

`check_refine_limit` at `scripts/little_loops/loops/refine-to-ready-issue.yaml:143` routes:
- `on_yes: refine_issue` (retry when under budget)
- `on_no: failed` (exit sub-loop when budget exhausted)

`breakdown_issue` at `refine-to-ready-issue.yaml:191` is only reachable from `check_lifetime_limit:71` (`on_no: breakdown_issue`). There is no edge from `check_refine_limit` → `breakdown_issue`.

When `recursive-refine` invokes the sub-loop via `run_refine` (`recursive-refine.yaml:88`), it routes `on_failure: detect_children`. If no children were auto-created by the sub-loop, `detect_children` exits 1 → `size_review_snap` → `recheck_scores` → `run_size_review`. This indirect path works only when the parent is `recursive-refine`; running `refine-to-ready-issue` standalone never triggers breakdown regardless of scores.

## Expected Behavior

When the per-run retry budget is exhausted and scores still fail, `refine-to-ready-issue` should directly invoke `breakdown_issue` (i.e., route `check_refine_limit on_no: breakdown_issue` instead of `failed`). This makes the sub-loop self-contained and ensures breakdown happens regardless of which parent loop called it.

## Motivation

Running `refine-to-ready-issue` standalone silently exits `failed` when the retry budget is exhausted — no child issues are ever created. The fix makes the sub-loop self-contained:
- Breakdown happens regardless of which parent loop (or no parent) invoked the sub-loop
- Removes fragile coupling where correct behavior depended on `recursive-refine`'s `on_failure: detect_children` route
- `recursive-refine`'s `on_failure` path becomes a true error condition rather than a normal budget-exhaustion route

## Root Cause

`refine-to-ready-issue.yaml:159` — `check_refine_limit.on_no` is wired to `failed` instead of `breakdown_issue`.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue "ISSUE_ID"` on an issue that scores below `outcome_threshold`
2. Allow two refine attempts to complete
3. Observe: sub-loop exits `failed`; no `breakdown_issue` is ever called; no child issues are created

## Impact

- **Priority**: P3 — Logic gap causes unexpected behavior; breakdown only works as a side-effect of the parent loop
- **Effort**: Trivial — single routing change
- **Risk**: Low — `breakdown_issue` already exists and is proven via the lifetime-cap path
- **Breaking Change**: No

## Proposed Solution

Change `check_refine_limit.on_no` from `failed` to `breakdown_issue` in `scripts/little_loops/loops/refine-to-ready-issue.yaml:159`.

## Implementation Steps

1. Edit `scripts/little_loops/loops/refine-to-ready-issue.yaml:159` — change `on_no: failed` to `on_no: breakdown_issue`
2. Update the comment block on `check_refine_limit` (lines 151–153) to reflect that budget exhaustion now triggers decomposition rather than failing
3. Update the comment block on `run_refine` at `recursive-refine.yaml:89-92` — change the `on_failure` description from "retries exhausted, no breakdown" to "unexpected error condition; breakdown now occurs in sub-loop before reaching `failed`"
4. Verify `recursive-refine`'s `run_refine` state still handles both paths:
   - `on_success`: sub-loop reached `done` (confidence pass or breakdown → done)
   - `on_failure`: sub-loop reached `failed` (true error condition, no longer the normal budget-exhaustion path)
5. Add test `test_check_refine_limit_on_no_routes_to_breakdown_issue` to `TestRefineToReadyIssueSubLoop` in `scripts/tests/test_builtin_loops.py:654`
6. Run `scripts/tests/test_builtin_loops.py` to confirm no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:159` — `on_no: failed` → `on_no: breakdown_issue`
- `scripts/little_loops/loops/recursive-refine.yaml:89-92` — comment block on `run_refine` explicitly states "on_failure = sub-loop reached 'failed' (retries exhausted, no breakdown)"; after the fix this comment is misleading and should be updated to reflect that `failed` is now a true error condition, not normal budget exhaustion

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — invokes sub-loop via `run_refine`; after this fix, `on_failure` becomes a true error condition rather than normal budget exhaustion

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — `check_lifetime_limit.on_no: breakdown_issue` is the existing pattern this fix mirrors on `check_refine_limit`

### Tests
- `scripts/tests/test_builtin_loops.py` — add test asserting `check_refine_limit.on_no == breakdown_issue`; verify `recursive-refine` integration paths remain unaffected

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Insert after `test_check_refine_limit_routes_to_refine_issue` at `test_builtin_loops.py:654` in class `TestRefineToReadyIssueSubLoop`. Mirror the structural twin at line 548:

```python
def test_check_refine_limit_on_no_routes_to_breakdown_issue(self, data: dict) -> None:
    """check_refine_limit.on_no must route to breakdown_issue (not failed)."""
    state = data["states"].get("check_refine_limit", {})
    assert state.get("on_no") == "breakdown_issue", (
        f"check_refine_limit.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
    )
```

The structural twin is `test_check_lifetime_limit_routes_to_breakdown_issue` at `test_builtin_loops.py:548-553`, which uses identical assertion style. No external fixtures needed — class-local `data` fixture loads YAML directly via `yaml.safe_load`.

### Documentation
- N/A

### Configuration
- N/A

## Downstream Impact

- **ENH-1033** (`refine-to-ready-issue`: skip retry when only outcome confidence fails) is blocked by this fix. ENH-1033 adds a direct `breakdown_issue` route when outcome confidence fails but readiness passes; that routing is only meaningful once `breakdown_issue` is correctly reachable from the score-failure path.

## Labels

`bug`, `loops`, `fsm`, `refine-to-ready-issue`, `recursive-refine`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4d2ee8a-2f4f-412d-b789-1c3f3d4748e3.jsonl`
- `/ll:refine-issue` - 2026-04-11T05:38:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/beb925f3-1081-49e6-920c-e728c119f859.jsonl`
- `/ll:format-issue` - 2026-04-11T05:22:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ede2e27-e614-4fb9-a6db-bba4198effb0.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
