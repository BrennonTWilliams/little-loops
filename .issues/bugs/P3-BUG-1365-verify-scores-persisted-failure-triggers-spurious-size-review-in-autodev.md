---
discovered_date: 2026-05-04
discovered_by: session-analysis
status: done
completed_at: 2026-05-04T00:00:00Z
priority: P3
---

# BUG-1365: `verify_scores_persisted` failure triggers spurious size-review in autodev

## Summary

When `/ll:confidence-check` runs inside `refine-to-ready-issue` but the LLM skips the Phase 4 `ll-issues set-scores` Bash call, scores are displayed in output but never written to the issue frontmatter. `verify_scores_persisted` correctly detects this and routes to the `failed` terminal state. However, the autodev outer loop has no way to distinguish "sub-loop failed because scores weren't persisted" from "scores are genuinely low," so it reads 0/0 from the frontmatter and routes identically to the normal low-score path — triggering `/ll:issue-size-review` on an issue that had actually passed with 100/100 readiness and 93/100 outcome confidence.

## Root Cause

**`/ll:confidence-check` computed correct scores but did not call `ll-issues set-scores` to persist them.**

The confidence-check skill instructs the LLM in Phase 4 to run:
```bash
ll-issues set-scores <ID> --confidence N --outcome N --score-complexity N ...
```
The LLM intermittently skips this Bash call. Scores appear in the skill's output but `confidence_score` and `outcome_confidence` are never written to the issue frontmatter.

**Failure chain (from blender-agents autodev run on ENH-9143):**

1. `[7/500] confidence_check` — `/ll:confidence-check ENH-9143` displayed 100/100 readiness and 93/100 outcome ✓
2. `[8/500] verify_scores_persisted` — `ll-issues show --json` returned `confidence=None`, `outcome=None` (frontmatter never written) → exit 1 → sub-loop `failed` terminal state
3. autodev `check_passed` — `ll-issues check-readiness` reads `confidence_score`/`outcome_confidence` from frontmatter, finds 0/0 → exit 1
4. `triage_outcome_failure` → `check_missing_artifacts` → `detect_children` → `size_review_snap` → `check_broke_down` → `recheck_scores` (also 0/0) → `check_decision_before_size_review` → `run_size_review` ← user interrupted here

**Design gap:** `verify_scores_persisted`'s comment said "Routes to `failed` to prevent spurious issue-size-review" — but this only prevents size-review *inside* the sub-loop. The outer autodev loop still triggers it because absent scores are indistinguishable from low scores at the `check_passed` / `recheck_scores` states.

## Location

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **State**: `verify_scores_persisted` (previously routed `on_no` directly to `failed`)

## Expected Behavior

A single LLM skip of the `ll-issues set-scores` call should not trigger size-review on an issue that passed confidence thresholds. The system should retry confidence-check once before giving up.

## Fix Applied

Added two new states to `scripts/little_loops/loops/refine-to-ready-issue.yaml`:

**`verify_scores_persisted`** — changed `on_no: failed` → `on_no: retry_confidence_check`

**`retry_confidence_check`** (new) — re-runs `/ll:confidence-check` once when `verify_scores_persisted` detects missing scores.

**`verify_scores_persisted_final`** (new) — checks scores again after the retry; routes to `check_readiness` on success, `failed` on a second consecutive miss.

Updated routing comment at top of file to reflect the new states.

## Integration Map

### Files Modified
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `verify_scores_persisted` on_no/on_error routing; added `retry_confidence_check` and `verify_scores_persisted_final` states; updated routing comment

### Related Files (read-only during investigation)
- `scripts/little_loops/loops/autodev.yaml` — outer loop; `check_passed`, `recheck_scores`, `run_size_review`
- `skills/confidence-check/SKILL.md` — Phase 4 (line ~400): instructs LLM to call `ll-issues set-scores`
- `scripts/little_loops/cli/issues/set_scores.py` — writes `confidence_score`/`outcome_confidence` to frontmatter
- `scripts/little_loops/cli/issues/show.py` — `ll-issues show --json` maps `confidence_score` → `confidence`, `outcome_confidence` → `outcome` (lines 147, 228–229)
- `scripts/little_loops/cli/issues/check_readiness.py` — reads `confidence_score`/`outcome_confidence` from frontmatter

## Status

**Closed** | Created: 2026-05-04 | Resolved: 2026-05-04 | Priority: P3

## Session Log
- Session analysis and fix - 2026-05-04 - `blender-agents-autodev-debug.txt` investigation
