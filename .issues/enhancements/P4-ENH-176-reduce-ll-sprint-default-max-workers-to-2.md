---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-176: Reduce ll-sprint default max workers to 2

## Summary

Reduce the default `max_workers` value in `ll-sprint` from 4 to 2 for more conservative resource usage.

## Context

User description: "In `ll-sprint` - reduce default max workers from 4 to 2"

## Current Behavior

The `ll-sprint` CLI defaults to 4 concurrent workers when processing sprint issues in parallel.

## Expected Behavior

The default should be 2 workers, providing a more conservative default for parallel processing.

## Proposed Solution

Update the following locations:
1. `scripts/little_loops/sprint.py:30` - Change `max_workers: int = 4` to `max_workers: int = 2`
2. `scripts/little_loops/sprint.py:57` - Change fallback default from 4 to 2
3. Update tests in `scripts/tests/test_sprint.py` to expect 2 as the default

## Impact

- **Priority**: P4
- **Effort**: Low (simple value change)
- **Risk**: Low

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | CLI tools architecture |

## Labels

`enhancement`, `captured`, `cli`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P4
