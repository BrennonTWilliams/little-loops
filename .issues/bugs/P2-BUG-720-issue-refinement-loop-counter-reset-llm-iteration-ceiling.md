---
discovered_date: 2026-03-13
discovered_by: audit
---

# BUG-720: `issue-refinement` loop has three logic defects — counter reset, LLM-managed iteration, and LLM ceiling-acceptance

## Summary

A targeted audit of `loops/issue-refinement.yaml` uncovered three high-severity bugs: (1) the commit counter is reset on every loop iteration, making it impossible to trigger periodic commits after the first pass; (2) `refine_issues` delegates iteration counting and threshold checking to the LLM inside a prose `while` loop, which is unreliable; (3) the ceiling-acceptance rule (`refine_count >= 5 and readiness >= 85`) lives only in LLM prompt prose instead of deterministic shell logic. A minor routing issue — `format_issues` and `score_issues` bypassing `check_commit` — was also identified and fixed.

## Current Behavior

1. **Counter reset**: `evaluate` runs `rm -f /tmp/issue-refinement-commit-count` unconditionally before every classification pass, so `N` always resets to 0. `check_commit` can never reach `N % 5 == 0` after the first commit.
2. **LLM inner loop**: `refine_issues` contained a `while (readiness < 85 OR outcome_confidence < 70) and iterations < 5` construct in prose, asking the LLM to count iterations and read scores — work that belongs to the FSM.
3. **LLM ceiling**: The ceiling-acceptance rule was prose in the LLM prompt; `refine_count` was never read in the Python classifier.
4. **Routing gap**: `format_issues.next: evaluate` and `score_issues.next: evaluate` skipped `check_commit`, so format and score operations never counted toward the commit cadence.

## Expected Behavior

1. Counter file is removed once at startup (`init` state) and accumulates monotonically throughout the run.
2. `refine_issues` runs one refine + confidence-check cycle per FSM invocation; the FSM loop is the iteration mechanism.
3. Ceiling-acceptance is deterministic Python in `evaluate`: `if cs >= 85 and rc >= 5: continue`.
4. All three action states (`format_issues`, `score_issues`, `refine_issues`) route through `check_commit`.

## Root Cause

- **File**: `loops/issue-refinement.yaml`
- **Bug 1**: `rm -f /tmp/issue-refinement-commit-count` was embedded in the `evaluate` shell action rather than a one-time `init` state.
- **Bug 2**: `refine_issues` was written as a self-contained agent prompt that managed its own retry loop, duplicating logic the FSM already provides.
- **Bug 3**: `refine_count` field returned by `ll-issues refine-status --json` was never referenced in the Python classifier block.
- **Minor**: `format_issues` and `score_issues` had `next: evaluate` instead of `next: check_commit`.

## Proposed Solution

All fixes are in `loops/issue-refinement.yaml`:

1. Extract `rm -f /tmp/issue-refinement-commit-count` into a new `init` state; change `initial: evaluate` → `initial: init`.
2. Collapse `refine_issues` prompt to a single refine + score invocation (remove the `while` loop, reduce `timeout` from 1200 → 600).
3. Add ceiling check to the Python block in `evaluate`:
   ```python
   rc = issue.get('refine_count', 0)
   if cs >= 85 and rc >= 5:
       continue
   ```
4. Change `format_issues.next` and `score_issues.next` from `evaluate` to `check_commit`.

## Acceptance Criteria

- [x] `ll-loop validate loops/issue-refinement.yaml` passes with no errors
- [x] `init` state exists; `initial` is `init`
- [x] `rm -f` counter command does not appear in `evaluate`
- [x] `refine_issues` prompt contains no `while` loop or iteration-count prose
- [x] `evaluate` Python block references `refine_count` and applies ceiling rule
- [x] `format_issues.next` and `score_issues.next` are both `check_commit`

## Impact

- **Priority**: P2 — Counter reset means periodic commits never fire after pass 1; LLM iteration management is unreliable (miscounting, stale score reads, early termination)
- **Effort**: Small — Single-file YAML edit
- **Risk**: Low — No Python code changed; changes are to loop configuration only
- **Breaking Change**: No

## Labels

`bug`, `loop`, `fsm`, `issue-refinement`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `loops/issue-refinement.yaml` | The file modified |
| `docs/ARCHITECTURE.md` | FSM loop design |

---

**Resolved** | Created: 2026-03-13 | Completed: 2026-03-13 | Priority: P2

## Resolution

Applied all four fixes to `loops/issue-refinement.yaml` in a single edit:

1. Added `init` state with `rm -f /tmp/issue-refinement-commit-count`; changed `initial` from `evaluate` to `init`.
2. Rewrote `refine_issues` as a single-cycle prompt (one `/ll:refine-issue` + `/ll:confidence-check`); removed `while` loop prose; reduced `timeout` 1200 → 600.
3. Added `rc = issue.get('refine_count', 0)` and `if cs >= 85 and rc >= 5: continue` to the Python classifier in `evaluate`.
4. Changed `format_issues.next` and `score_issues.next` from `evaluate` to `check_commit`.

`ll-loop validate` confirmed no schema errors. All 10 states present: `init`, `evaluate`, `route_format`, `route_score`, `format_issues`, `score_issues`, `refine_issues`, `check_commit`, `commit`, `done`.

## Session Log
- Audit & fix - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/405e3b7b-9162-4cd6-b556-4ce959c0924a.jsonl`
