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

The `ll-sprint` CLI defaults to 3 concurrent workers when processing sprint issues in parallel.

## Expected Behavior

The default should be 2 workers, providing a more conservative default for parallel processing.

## Proposed Solution

Update the following locations:
1. `scripts/little_loops/sprint.py:27` - Change `max_workers: int = 3` to `max_workers: int = 2`
   - Anchor: `class SprintOptions` → field `max_workers`
2. `scripts/little_loops/sprint.py:52` - Change fallback default from 3 to 2
   - Anchor: `SprintOptions.from_dict` → `data.get("max_workers", ...)`
3. Update tests in `scripts/tests/test_sprint.py` to expect 2 as the default (lines 18, 56, 144 currently expect 4, which is already incorrect)
   - Anchor: `TestSprintOptions.test_default_values`, `TestSprintOptions.test_from_dict_none`, `TestSprint.test_from_dict_defaults`

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

**Completed** | Created: 2026-01-28 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sprint.py`: Changed SprintOptions.max_workers default from 3 to 2
- `scripts/little_loops/config.py`: Changed SprintsConfig.default_max_workers from 3 to 2
- `scripts/little_loops/cli.py`: Changed CLI --max-workers default from 4 to 2, updated help text, and runtime fallback
- `scripts/tests/test_sprint.py`: Updated test expectations from 4 to 2
- `scripts/tests/test_config.py`: Updated SprintsConfig test expectation from 4 to 2

### Verification Results
- Tests: PASS (138 tests in sprint, config, and CLI modules)
- Lint: PASS
- Types: PASS
