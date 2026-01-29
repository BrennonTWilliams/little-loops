---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-186: Harmonize timeout defaults across CLI tools

## Summary

The three CLI tools have inconsistent default timeout values, which can cause confusion and unexpected behavior when users switch between tools.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Configuration Defaults Comparison shows timeout inconsistency
- Listed as "Medium Priority" standardization opportunity

## Current Behavior

| Tool | Default Timeout |
|------|----------------|
| ll-auto | 3600s (1 hour) |
| ll-parallel | 7200s (2 hours) |
| ll-sprint | 3600s (1 hour) |

## Expected Behavior

All tools should use the same default timeout, or have clearly documented reasons for differences.

## Proposed Solution

### Option A: Align to 1 hour (3600s)
- Pros: Faster feedback on stuck issues, resource conservation
- Cons: May be too short for complex issues in parallel mode
- Change: Update ll-parallel default from 7200s to 3600s

### Option B: Align to 2 hours (7200s)
- Pros: More lenient for complex issues
- Cons: Longer wait when issues are stuck
- Change: Update ll-auto and ll-sprint defaults from 3600s to 7200s

### Option C: Document and keep differences
- ll-parallel may legitimately need longer timeouts due to concurrent execution overhead
- Add clear documentation explaining the rationale
- No code changes, just documentation

### Recommendation

Option A (align to 3600s) is recommended because:
- Users can always override with `--timeout/-t`
- Faster feedback is generally preferable
- Complex issues can be given explicit longer timeouts

## Files to Modify

If aligning defaults:
- `scripts/little_loops/parallel/types.py` - ParallelConfig.timeout default
- Or `scripts/little_loops/config.py` - BRConfig.timeout default
- Or `scripts/little_loops/sprint.py` - SprintOptions.timeout default

## Impact

- **Priority**: P4 (Low - minor inconsistency)
- **Effort**: Very Low (single value change)
- **Risk**: Low (users can override)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| audit | docs/CLI-TOOLS-AUDIT.md | Configuration Defaults table |

## Labels

`enhancement`, `consistency`, `configuration`, `captured`

---

## Status

**Completed** | Created: 2026-01-29 | Completed: 2026-01-29 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made

- `scripts/little_loops/parallel/types.py`: Changed `ParallelConfig.timeout_per_issue` default from 7200 to 3600
- `config-schema.json`: Updated `parallel.timeout_per_issue` default from 7200 to 3600
- `scripts/tests/test_parallel_types.py`: Updated test assertion to match new default

### Verification Results

- Tests: PASS (101 related tests)
- Lint: PASS
- Types: PASS

### Implementation Approach

Selected Option A (align to 3600s) as recommended:
- All three CLI tools now share the same 1-hour default timeout
- Users can override with `--timeout/-t` for longer operations
- Faster feedback on stuck issues
