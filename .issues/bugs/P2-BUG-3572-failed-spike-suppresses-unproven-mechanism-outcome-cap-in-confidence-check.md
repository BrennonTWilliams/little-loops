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
blocks:
- ENH-3577
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

## Steps to Reproduce

1. Take an issue with `unproven_mechanism: true` whose mechanism is wrong
2. Run `/ll:spike --auto`; verification fails, and only `spike_attempted: true` is written
3. Run `/ll:confidence-check`: Phase 1.9 sets `SPIKE_SUPPRESSED`, and the outcome is scored with no unproven-mechanism cap

## Motivation

Spikes exist to prove a mechanism before implementation. Treating a disproof as permission to proceed defeats the purpose.

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

## Program Design

### Types

- `spike_verdict: str` — frontmatter field, one of `proven`, `refuted`, `inconclusive`; `spike_attempted` stays an attempt bound only.

### Signatures

- `check_spike_needed(spike_needed: bool, spike_attempted: bool) -> bool` — existing autodev guard; unchanged.
- `route_spike_result(spike_verdict: str) -> str` — new routing rule: `refuted` goes to `resolve_decision` or size review, anything else to rescoring.

### Call Path

`run_spike` -> `route_spike_result` -> `rerun_confidence_after_spike`

## Integration Map

- `skills/spike/SKILL.md` (failure contract)
- `skills/confidence-check/SKILL.md` Phase 1.9; `skills/confidence-check/rubric.md` cap row
- `scripts/little_loops/loops/autodev.yaml` `run_spike` / `rerun_confidence_after_spike`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` spike return path
- Skill edits trip the mirror gates (`ll-adapt --apply` for gemini/kimi-code/qwen)

## Implementation Steps

1. Confirm no loop depends on attempted-only suppression for termination
2. Change Phase 1.9 suppression to `spike_completed` only
3. Add a refuted marker to the spike failure contract
4. Route refuted results to decision/size-review in autodev and refine-to-ready-issue
5. Regression test: failed spike keeps the cap; refuted spike never reaches implementation

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


## Session Log
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
