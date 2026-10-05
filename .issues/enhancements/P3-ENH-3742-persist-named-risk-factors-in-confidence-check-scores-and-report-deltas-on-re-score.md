---
id: ENH-3742
title: Persist named risk factors in confidence-check scores and report deltas on re-score
type: ENH
priority: P3
status: open
discovered_date: '2026-10-05'
labels:
- verification
- confidence-check
---

## Summary

`/ll:confidence-check`'s total score cannot register a real reduction in risk. FEAT-3504 was split to separate untested stateful page work from the transport change. Its re-score came back **85/64, identical to before**: the bucket totals did not move, though the Concerns prose did change (the page bullets were gone; the transport and submit-path bullets were unchanged).

Persist the named risk factors alongside each score. On re-score, diff them and report the result as added, removed and unchanged, so "did my change matter?" gets an answer even when the totals are static.

This is purely additive: no rubric change, no threshold change, no migration and no re-scoring of existing issues. It is the first, separable step of a broader scoring-granularity change (continuous scoring for countable inputs, per-site depth), which will be filed separately.

## Current Behavior

- Each run appends a new `## Confidence Check Notes` prose section with Concerns and Outcome Risk Factors bullets (`skills/confidence-check/rubric.md`, ~L616-647).
- `## Resolved Concerns`, written by `/ll:reconcile-issue` (`rubric.md` ~L649-658), only tells the scorer not to re-raise a listed concern. It does not diff anything.
- `ll-issues set-scores` overwrites the score fields and has no risk-factor fields (`scripts/little_loops/cli/issues/set_scores.py`).
- Nothing compares one run's risk factors with the previous run's.

## Expected Behavior

- Each confidence-check run records its risk factors as **named, stable items**: a short id, the criterion it bears on, and a one-line description. They are stored machine-readably next to the scores.
- Re-scoring an issue that already has recorded factors reports a **delta** (added, removed, unchanged) in the skill output and in the new notes section, including when both totals are unchanged.
- A first-ever score records the factors and reports that no prior set exists.

## Motivating Example

The FEAT-3504 re-score, raw bucket sum 64:

| Criterion | Score | Why it didn't move |
| --- | --- | --- |
| Complexity | 10 | About 8 code files plus 5 docs, still in the 6–15 breadth bucket; whole-issue depth "Moderate" |
| Test coverage | 18 | "Most modules": new `policy_builder_routes.py` and `do_POST` lack tests |
| Ambiguity | 18 | The checker still flags a bare-token redirect as a minor open question |
| Change surface | 18 | 3–5 callers, unchanged by the split |

The split removed exactly the risk the rubric cannot see. The qualitative layer tracked the change; the numeric layer could not. A factor delta makes that visible without touching the numbers.

## Proposed Implementation

1. Define the risk-factor record, as a frontmatter list or a fenced machine-readable block in the notes section. Pick whichever `set-scores` can write atomically alongside the scores.
2. Extend `ll-issues set-scores` to accept and persist the current factor set while keeping the previous set available for diffing.
3. Update `skills/confidence-check` (`SKILL.md` and `rubric.md`) to emit factors with stable ids, pass them to `set-scores`, and render the delta.
4. Matching across runs uses the scorer's stable ids. Decide during implementation whether reworded factors need a similarity fallback, or whether stable ids are enough.

## Acceptance Criteria

- Scoring an issue persists its named risk factors alongside the scores.
- Re-scoring reports added, removed and unchanged factors, including when both totals are identical.
- The four criteria, point allocations and the 65 gate are unchanged. Existing scored issues need no migration and score exactly as before.
- Tests cover:
  - a `set-scores` round-trip of risk factors;
  - delta computation for added, removed and unchanged factors;
  - a re-score with identical totals but changed factors, which reports a non-empty delta.

## Out of Scope

- Scoring countable inputs (breadth, callers, coverage) by formula instead of bucket.
- Per-site depth classification with a weighted aggregate.

Both shift existing scores and need a one-time re-check of issues scored near the 65 gate. They follow this change as separate work.
