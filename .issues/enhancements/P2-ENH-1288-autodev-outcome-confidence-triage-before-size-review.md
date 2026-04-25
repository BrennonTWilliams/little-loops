---
captured_at: "2026-04-25T19:07:05Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
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
- `scripts/little_loops/loops/autodev.yaml` — add `triage_outcome_failure` state; update `check_passed.on_no`

### Dependent Files (Callers/Importers)
- N/A — autodev.yaml is self-contained FSM; the new state reuses existing `run_decide` and `detect_children`

### Similar Patterns
- `check_decision_before_size_review` state in `autodev.yaml` — mirrors exact pattern (read a field, route yes/no)
- `recheck_scores` state — mirrors pattern of re-reading issue JSON for a gate decision

### Tests
- TBD — requires FSM integration test fixture: issue with `score_ambiguity ≤ 10`, `outcome_confidence` in 60–74 range
- Verify: routes to `run_decide`, not `run_size_review`

### Documentation
- N/A — autodev state machine not documented externally

### Configuration
- `context.outcome_threshold` in `autodev.yaml` — no change needed

## Implementation Steps

1. Add `triage_outcome_failure` state to `autodev.yaml` using `shell_exit` fragment
2. State reads `score_ambiguity` from `ll-issues show --json`; exits 0 if ≤10 (decision path), 1 otherwise (size-review path)
3. Change `check_passed on_no` from `detect_children` to `triage_outcome_failure`
4. Verify the route from `triage_outcome_failure → run_decide` handles the full `run_decide → implement_current → dequeue_next` success path correctly
5. Test with fixture: issue with `score_ambiguity: 5`, `outcome_confidence: 64`, `readiness_threshold: 90` in project config

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
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P2
