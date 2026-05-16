---
captured_at: "2026-04-25T19:07:05Z"
completed_at: "2026-04-25T20:07:48Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1288: Autodev outcome-confidence triage before size-review

## Summary

When `outcome_confidence` is below the project's `outcome_threshold`, autodev routes the issue to `issue-size-review` regardless of why the score is low. The three distinct root causes — structural bigness, unresolved design decisions, and missing artifacts — each warrant a different intervention, but the loop treats them identically.

## Current Behavior

When `check_passed` fails (either `confidence_score < readiness_threshold` or `outcome_confidence < outcome_threshold`), autodev routes through `detect_children` → `size_review_snap` → `check_broke_down` → `recheck_scores` → (on fail) → `check_decision_before_size_review` → `run_size_review`.

The `check_decision_before_size_review` gate reads `decision_needed` from frontmatter, but `decision_needed` is only set by confidence-check Phase 4.6 when `outcome_confidence < 60`. Issues where outcome confidence fails purely because of `outcome_threshold: 75` but `outcome_confidence` is 60–74 fall through to `run_size_review` unconditionally.

This means a well-specified, coherent Medium issue with one unresolved design decision (but adequate complexity score) gets sent to size-review and incorrectly decomposed into children — even though the right fix was `decide-issue` or `refine-issue`.

## Expected Behavior

After `check_passed` fails, autodev should diagnose **why** `outcome_confidence` is low before choosing an intervention:

| Bottleneck | `score_*` signal | Right intervention |
|---|---|---|
| Structural bigness | `score_complexity` low (many files, broad scope) | `issue-size-review` |
| Unresolved design | `score_ambiguity` low (≤10) | `decide-issue` |
| Missing artifacts or wiring | `score_complexity` low (absent files, not scope) | `wire-issue` / `refine-issue` |

A new `triage_outcome_failure` state should read `score_ambiguity` (and optionally `score_complexity`) from `ll-issues show --json` and route accordingly, without calling `issue-size-review` when the bottleneck is clearly qualitative.

## Motivation

Spurious decomposition is worse than skipping an issue — it creates child issues that have to be cleaned up, moves the parent to completed prematurely, and wastes several autodev iterations on children that mirror the parent's ambiguity. This is the scenario that prompted the conversation: a P3 settings-page issue with `outcome_confidence: 64` got broken down when it should have stayed whole and had its one ambiguity (ScannerSection disposal) resolved first.

## Proposed Solution

Add a `triage_outcome_failure` state to `autodev.yaml` that replaces the direct `check_passed on_no: detect_children` routing:

```python
# In triage_outcome_failure action (shell):
issue_id = captured.input.output
d = ll-issues show issue_id --json

score_ambiguity = int(d.get('score_ambiguity') or 25)  # default to non-ambiguous

if score_ambiguity <= 10:
    exit 0  # → run_decide
else:
    exit 1  # → detect_children (existing path toward size-review)
```

Route: `on_yes: run_decide`, `on_no: detect_children`, `on_error: detect_children`.

Update `check_passed` to use `on_no: triage_outcome_failure` instead of `on_no: detect_children`.

The existing `run_decide` and `detect_children` states are unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add `triage_outcome_failure` state after `check_decision_before_size_review` (line 384); change `check_passed.on_no` at line 162 from `detect_children` to `triage_outcome_failure`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py:233` — emits `score_ambiguity` as a string (`str(score_ambiguity)`); the new state must coerce with `int(d.get('score_ambiguity') or 25)` — the `or 25` default treats absent/null score as non-ambiguous, routing safely to `detect_children`

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml:361–384` — `check_decision_before_size_review` state: the exact pattern to copy (read JSON field, compare, route via `fragment: shell_exit`)
- `scripts/little_loops/loops/autodev.yaml:318–359` — `recheck_scores` state: shows `int(d.get('field') or 0)` coercion pattern for all numeric score fields

### Tests
- `scripts/tests/test_builtin_loops.py:1026` — `TestAutodevLoop` required-states set: add `"triage_outcome_failure"` to the list
- `scripts/tests/test_builtin_loops.py:1379+` — add three routing tests following the `test_check_decision_before_size_review_*` pattern:
  - `test_triage_outcome_failure_uses_shell_exit_fragment`
  - `test_triage_outcome_failure_on_yes_routes_to_run_decide`
  - `test_triage_outcome_failure_on_no_routes_to_detect_children`
- `scripts/tests/test_builtin_loops.py:1379+` — also add `test_check_passed_on_no_routes_to_triage_outcome_failure` to verify the routing change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1150` — existing `test_check_passed_on_no_routes_to_detect_children` **will break** when `check_passed.on_no` changes from `"detect_children"` to `"triage_outcome_failure"`; must rename to `test_check_passed_on_no_routes_to_triage_outcome_failure` and update the expected value — do not add a new test alongside the old one [Agent 2 + Agent 3 finding]

### Documentation
- N/A — autodev state machine not documented externally

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:444–468` — ASCII state-graph for the autodev loop shows `check_passed → NO → detect_children` directly; must be revised to route through `triage_outcome_failure` first, showing both YES→`run_decide` and NO/ERROR→`detect_children` exits [Agent 2 finding]

### Configuration
- `scripts/little_loops/loops/lib/common.yaml:15–21` — `shell_exit` fragment definition (`action_type: shell`, `evaluate.type: exit_code`); no changes needed
- `context.outcome_threshold` in `autodev.yaml:23` — no change needed

## Implementation Steps

1. In `autodev.yaml:384`, insert `triage_outcome_failure` state after `check_decision_before_size_review`, using `fragment: shell_exit` — copy the `check_decision_before_size_review` block (lines 361–384) as the structural template; replace the `decision_needed == 'true'` check with `int(d.get('score_ambiguity') or 25) <= 10`; set `on_yes: run_decide`, `on_no: detect_children`, `on_error: detect_children`
2. In `autodev.yaml:162`, change `on_no: detect_children` to `on_no: triage_outcome_failure` in the `check_passed` state (and update `on_error: detect_children` — keep it pointing to `detect_children` as the safe fallback, matching the existing pattern)
3. Verify `run_decide` (line 190–199) already has `next: implement_current`, so no downstream changes are needed — the `triage_outcome_failure → run_decide → implement_current → dequeue_next` path is already connected
4. In `scripts/tests/test_builtin_loops.py:1026`, add `"triage_outcome_failure"` to the required-states set; add four routing assertion tests after the existing `check_decision_before_size_review` tests (line 1379+) following the same pattern
5. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v` to validate; also run `python -m pytest scripts/tests/ -v --tb=short` for full suite

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Rename `test_check_passed_on_no_routes_to_detect_children` at line 1150 to `test_check_passed_on_no_routes_to_triage_outcome_failure` and change the expected value from `"detect_children"` to `"triage_outcome_failure"` — this existing test **will fail** after Step 2 changes `check_passed.on_no`
7. Update `docs/guides/LOOPS_GUIDE.md:444–468` — revise the ASCII autodev state-graph to route `check_passed.on_no` through `triage_outcome_failure` before `detect_children`, showing both YES→`run_decide` and NO/ERROR→`detect_children` exits

## Impact

- **Priority**: P2 — autodev incorrectly decomposes ready-to-decide issues, causing downstream churn; affects every project using autodev with `outcome_threshold > 60`
- **Effort**: Small — adds one new state (~20 lines) and changes one routing key; no new concepts
- **Risk**: Low — purely additive routing; existing paths untouched; on_error falls through to the existing path
- **Breaking Change**: No

## Scope Boundaries

- Does not change `check_decision_before_size_review` (that gate is specifically for `decision_needed: true`; this triage precedes it)
- Does not change `issue-size-review` itself
- Does not handle the missing-artifact path (would require checking `score_complexity` intent vs. `score_ambiguity`; out of scope for this issue)

## Labels

`enhancement`, `autodev`, `confidence-gate`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-25T20:02:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d91172b8-863e-4769-93e7-a021faef4012.jsonl`
- `/ll:confidence-check` - 2026-04-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b7d7390-3c8f-4a78-93f8-76c1fb641f32.jsonl`
- `/ll:wire-issue` - 2026-04-25T19:57:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad8fab7d-0083-4716-8dda-143a2383efe9.jsonl`
- `/ll:refine-issue` - 2026-04-25T19:52:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efe031ff-e7e7-4a96-bddc-f126892b5254.jsonl`
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

## Resolution

**Status**: Completed  
**Completed**: 2026-04-25

### Changes Made
1. Added `triage_outcome_failure` state to `autodev.yaml` after `check_decision_before_size_review` — reads `score_ambiguity` from `ll-issues show --json` and routes to `run_decide` (≤10) or `detect_children` (>10/error)
2. Changed `check_passed.on_no` from `detect_children` to `triage_outcome_failure`
3. Added `"triage_outcome_failure"` to required states set in `test_builtin_loops.py`
4. Renamed `test_check_passed_on_no_routes_to_detect_children` → `test_check_passed_on_no_routes_to_triage_outcome_failure` with updated expected value
5. Added 4 new routing tests for `triage_outcome_failure`
6. Updated autodev FSM ASCII diagram in `docs/guides/LOOPS_GUIDE.md`

---

**Completed** | Created: 2026-04-25 | Priority: P2
