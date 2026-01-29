---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-177: Improve ll-sprint wave completion messages

## Summary

Improve wave completion messages in `ll-sprint` to make it clear that a wave is completed, not the entire process. Users may be confused when they see a completion message after a wave finishes, thinking the sprint is done when there are still more waves to process.

## Context

User description: "In `ll-sprint` - improve wave completion messages to make it clear that a wave is completed, not the entire process"

## Current Behavior

When a wave completes in `ll-sprint`, the output message may be ambiguous about whether the wave or the entire sprint has finished.

## Expected Behavior

Wave completion messages should clearly indicate:
- That a specific wave (e.g., "Wave 1 of 3") has completed
- How many waves remain
- That processing will continue with the next wave (if applicable)

## Proposed Solution

Update the wave completion output in the `ll-sprint` CLI tool to:
1. Include wave number and total wave count (e.g., "Wave 1/3 completed")
2. Add clear indication of remaining work (e.g., "Continuing to wave 2...")
3. Distinguish between wave completion and sprint completion messages visually

## Impact

- **Priority**: P3
- **Effort**: Low
- **Risk**: Low

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`enhancement`, `captured`, `ll-sprint`, `ux`

---

## Status

**Completed** | Created: 2026-01-28 | Completed: 2026-01-29 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Updated wave messages to include "X/Y" format (e.g., "Wave 1/3") for wave start, completion, and failure messages
- Added "Continuing to wave X/Y..." message between waves to indicate more work remains
- Updated ParallelOrchestrator wave_label to include total count
- Updated sprint completion message to include wave count (e.g., "3 issues processed (2 waves)")

### Verification Results
- Tests: PASS (1863 passed, 5 pre-existing failures unrelated to this change)
- Lint: PASS (1 pre-existing warning unrelated to this change)
- Types: PASS
