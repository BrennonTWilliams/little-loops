---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-178: Track and display total execution duration in ll-sprint

## Summary

Track the total execution duration across all waves in `ll-sprint` and display the cumulative time at the end of the sprint run.

## Context

User description: "In `ll-sprint` - track total duration (sum duration of each wave) and show the total execution time at the end"

## Current Behavior

`ll-sprint` processes issues in waves but does not aggregate or display the total execution time across all waves.

## Expected Behavior

- Track the start time when the sprint begins
- Sum the duration of each wave as it completes
- Display the total execution time at the end of the sprint
- Example output: `Total sprint duration: 15m 32s (3 waves)`

## Proposed Solution

1. Record `sprint_start_time` at the beginning of execution
2. Track `wave_durations` list as each wave completes
3. At sprint completion, calculate and display:
   - Total duration (end time - start time, or sum of wave durations)
   - Number of waves processed
   - Optionally: breakdown per wave

## Impact

- **Priority**: P3
- **Effort**: Low
- **Risk**: Low

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`enhancement`, `ll-sprint`, `captured`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3
