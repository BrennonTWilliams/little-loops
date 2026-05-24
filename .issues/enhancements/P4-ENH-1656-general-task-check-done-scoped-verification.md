---
id: ENH-1656
type: ENH
priority: P4
status: cancelled
discovered_date: 2026-05-23
discovered_by: audit-loop-run
confidence_score: 70
outcome_confidence: 60
---

# ENH-1656: check_done re-verifies all criteria every iteration, causing excessive session duration

Cancelled 2026-05-24 — superseded by ENH-1671, which carries this issue's audit data, delta-aware-prompt mechanism, phased-DoD alternative, and API-failure-exposure framing forward. ENH-1658 addresses the `check_done` gate and explicitly preserves the prompt action; ENH-1671 scopes the prompt action itself.

## Summary

The `general-task` loop's `check_done` state re-verifies every DoD criterion from scratch on every iteration, regardless of what changed. In the audited run, this produced sessions of 2.5–8.5 minutes per `check_done` call (accumulating ~12 minutes of verification across 6 cycles for a 34-minute run). Each long session increases exposure to transient API failures.

## Problem

During the `2026-05-23T224029` run, `check_done` durations were:

| Iteration | Duration | Criteria |
|-----------|----------|----------|
| 4 | 163s | 47 criteria verified |
| 6 | 151s | 47 criteria re-verified |
| 8 | 161s | 47 criteria re-verified |
| 10 | 158s | 47 criteria re-verified |
| 12 | 152s | 47 criteria re-verified |
| 14 | 510s | 47 criteria re-verified → API error |

Only 1 step changed between each `check_done` invocation, yet all ~47+ criteria were re-checked. The per-iteration delta is small (e.g., "composite-audio.ts now imports renderLogoSting") but the verification cost is constant. The 510s session at iteration 14 was the one that hit the API error.

## Proposal

Pass the delta (which step just completed, which files were touched) to `check_done` so the action can scope verification to criteria relevant to that step, plus a quick sanity check that previously-verified criteria haven't regressed.

Options:
1. **Delta-aware prompt**: Include "Step N was just completed" in the check_done action prompt, instructing the model to focus verification on criteria related to that step and spot-check 3 previously-[x] criteria
2. **Phased DoD**: Structure the DoD file with phase headers and pass the current phase, scoping verification to that phase only
3. **Cached verification**: Track which criteria were verified in previous iterations and only re-verify criteria whose underlying files have changed (mtime-based)

## Impact

- Reduces per-iteration check_done cost from ~$0.30 to ~$0.05–$0.10
- Reduces exposure to API failures (shorter sessions = fewer transient errors)
- Speeds up loop iteration time significantly
- Trade-off: risk of stale [x] criteria if a later step accidentally breaks something verified earlier — mitigated by sample re-verification
