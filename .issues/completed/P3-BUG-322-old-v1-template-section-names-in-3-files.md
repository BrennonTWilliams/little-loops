---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# BUG-322: Old v1.0 template section names used in 3 files

## Summary

Three files still use old v1.0 issue template section names (`Reproduction Steps` instead of `Steps to Reproduce`, `Proposed Fix` instead of `Proposed Solution`) after the v2.0 template migration. These create inconsistency with the centralized template at `templates/issue-sections.json`.

## Current Behavior

- `scripts/little_loops/issue_lifecycle.py` (in function `create_failure_issue()`) generates bug issues with `## Reproduction Steps` (line 468) and `## Proposed Fix` (line 472)
- `scripts/tests/test_issue_discovery.py` test fixture uses `## Proposed Fix` (line 125)
- `commands/find_dead_code.md` issue template example uses `## Proposed Fix` (line 181)

## Expected Behavior

All files should use v2.0 section names:
- `## Steps to Reproduce` (not `Reproduction Steps`)
- `## Proposed Solution` (not `Proposed Fix`)

## Motivation

Template consistency is critical for the issue management pipeline. `ready_issue` validates against `templates/issue-sections.json` which defines `Steps to Reproduce` and `Proposed Solution`. Issues created with old names require auto-correction, increasing the correction rate unnecessarily.

## Root Cause

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `in function create_failure_issue()`
- **Cause**: This function was written before v2.0 and hardcodes section names in an f-string template rather than reading from `templates/issue-sections.json`. The v2.0 migration updated commands but missed this Python code path and the test fixture.

## Steps to Reproduce

1. Trigger an implementation failure during `/ll:manage-issue` (e.g., via `ll-auto` or `ll-parallel`)
2. Observe the auto-generated bug issue file
3. Note it uses `## Reproduction Steps` and `## Proposed Fix` instead of v2.0 names

## Actual Behavior

Generated issues use old section names, causing `ready_issue` to flag them for auto-correction.

## Proposed Solution

Rename the section headers in all 3 files:

**`scripts/little_loops/issue_lifecycle.py`** (in function `create_failure_issue()`):
- `## Reproduction Steps` → `## Steps to Reproduce`
- `## Proposed Fix` → `## Proposed Solution`

**`scripts/tests/test_issue_discovery.py`** (test fixture):
- `## Proposed Fix` → `## Proposed Solution`

**`commands/find_dead_code.md`** (template example):
- `## Proposed Fix` → `## Proposed Solution`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — rename 2 section headers in f-string
- `scripts/tests/test_issue_discovery.py` — rename 1 section header in test fixture
- `commands/find_dead_code.md` — rename 1 section header in example template

### Dependent Files (Callers/Importers)
- N/A — these are string literals in templates, no callers depend on the old names

### Similar Patterns
- N/A — all other commands already reference `templates/issue-sections.json`

### Tests
- `scripts/tests/test_issue_discovery.py` — fixture itself needs updating
- `scripts/tests/test_issue_lifecycle.py` — verify no tests assert old section names

### Documentation
- N/A — docs already use v2.0 names

### Configuration
- N/A

## Implementation Steps

1. Rename section headers in all 3 files (simple find-and-replace)
2. Run tests to verify nothing breaks
3. Grep for any remaining `Reproduction Steps` or `Proposed Fix` in non-historical files

## Impact

- **Priority**: P3 - Causes unnecessary auto-corrections but doesn't block functionality
- **Effort**: Small - 3 simple string renames across 3 files
- **Risk**: Low - Only changes string literals in templates
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| template | docs/ISSUE_TEMPLATE.md | Defines v2.0 section names |
| template | templates/issue-sections.json | Authoritative template definition |

## Labels

`bug`, `template-v2`, `captured`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_lifecycle.py`: Renamed `Reproduction Steps` → `Steps to Reproduce`, `Proposed Fix` → `Proposed Solution`
- `scripts/tests/test_issue_discovery.py`: Renamed `Proposed Fix` → `Proposed Solution`
- `commands/find_dead_code.md`: Renamed `Proposed Fix` → `Proposed Solution`

### Verification Results
- Tests: PASS (2674 passed)
- Lint: PASS
- Integration: PASS — no remaining old section names in active files

---

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P3
