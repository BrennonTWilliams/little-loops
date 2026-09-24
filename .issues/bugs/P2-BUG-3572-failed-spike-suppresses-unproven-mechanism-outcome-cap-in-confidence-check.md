---
id: BUG-3572
type: BUG
title: Failed spike suppresses unproven-mechanism outcome cap in confidence-check
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
---

# BUG-3572: Failed spike suppresses unproven-mechanism outcome cap in confidence-check

## Summary

On failure, `/ll:spike` sets only `spike_attempted: true` (not `spike_completed`) and says a
failed spike means the approach is wrong. But confidence-check Phase 1.9 (ENH-3350) sets
`SPIKE_SUPPRESSED` when **either** `spike_attempted` or `spike_completed` is set. `rubric.md`
then applies no unproven-mechanism cap, and `outcome_confidence` becomes the raw Criteria A–D
sum. A spike that *disproved* the mechanism therefore removes the very cap that demanded
proof. Whether the issue stays blocked depends on the scorer noticing `## Spike Findings`,
which is discretionary, not an FSM guarantee.

## Current Behavior

A failed spike → `spike_attempted: true` → cap suppressed → the issue can pass the outcome
threshold on an approach its own spike refuted.

## Expected Behavior

Only a proven spike retires the proof requirement. A refuted spike routes to a decision,
design change or decomposition. An inconclusive or errored spike keeps the cap.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Separate evidence truth from attempt bounding:

- Keep `spike_attempted` purely as a retry/attempt bound (autodev's remedy dispatcher and
  `check_spike_needed` rely on it).
- Suppress the cap only on `spike_completed: true`.
- Add a refuted outcome (e.g. `spike_refuted: true`, or a `spike_verdict: proven|refuted|inconclusive`
  field). Parent and child spike returns route a refuted result to `resolve_decision` or
  size-review instead of straight back to confidence scoring.

Check first: whether anything relies on attempted-only suppression to avoid a
spike → score → spike loop. The attempt bound should already prevent that.

## Integration Map

- `skills/spike/SKILL.md` (failure contract)
- `skills/confidence-check/SKILL.md` Phase 1.9; `skills/confidence-check/rubric.md` cap row
- `scripts/little_loops/loops/autodev.yaml` `run_spike` / `rerun_confidence_after_spike`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` spike return path
- Skill edits trip the mirror gates (`ll-adapt --apply` for gemini/kimi-code/qwen)

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2. A refuted approach can reach implementation.
- **Effort**: Medium
- **Risk**: Medium. Changes the spike/scoring contract used by several loops.

## Acceptance Criteria

- [ ] A failed spike does not suppress the unproven-mechanism cap
- [ ] A refuted spike routes to decision/design/decomposition, not straight to rescoring
- [ ] Attempt limits still bound spike re-runs

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2
