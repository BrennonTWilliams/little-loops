---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-175: Process Single-Issue Waves In-Place in ll-sprint

## Summary

When a wave in `ll-sprint` contains only a single issue, process it in-place (in the main working directory) without creating a git worktree, similar to how `ll-auto` operates.

## Context

User description: "In `ll-sprint` - process single-issue waves in-place without worktrees (like `ll-auto`)"

## Current Behavior

`ll-sprint` currently creates git worktrees for all parallel wave processing, regardless of wave size. Even single-issue waves spawn worktree-based workers.

## Expected Behavior

- When a wave contains only 1 issue, process it directly in the main working directory
- Skip worktree creation/cleanup overhead for single-issue waves
- Behavior matches `ll-auto` for sequential processing scenarios
- Multi-issue waves continue to use worktrees as normal

## Proposed Solution

Modify the wave execution logic in `ll-sprint` to detect single-issue waves and route them through in-place processing:

```python
async def process_wave(self, wave: List[IssueInfo]) -> WaveResult:
    if len(wave) == 1:
        # Process single issue in-place (like ll-auto)
        return await self._process_issue_in_place(wave[0])
    else:
        # Use worktree-based parallel processing
        return await self._process_wave_parallel(wave)
```

## Impact

- **Priority**: P3 (Quality of life improvement)
- **Effort**: Small - Conditional routing based on wave size
- **Risk**: Low - Falls back to existing behavior for multi-issue waves

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`enhancement`, `cli`, `ll-sprint`, `performance`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-01-29
- **Reason**: already_fixed
- **Closure**: Automated (ready_issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
