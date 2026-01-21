---
discovered_date: 2026-01-21
discovered_by: capture_issue
---

# ENH-099: Support 4+ Digit Issue IDs

## Summary

The current issue ID validation pattern (`[0-9]{3}`) enforces exactly 3 digits, limiting projects to 999 issues maximum. Update the validation pattern to support 3 or more digits (`[0-9]{3,}`) to accommodate larger projects.

## Context

**Direct mode**: User description: "The 3-digit Issue ID pattern (001-999) gets exceeded relatively quickly. We need to Update the validation pattern to support 4+ digit IDs - Change the regex from [0-9]{3} to [0-9]{3,} (3 or more digits). Include any other updates necessary to support 4+ digit Issue IDs"

## Current Behavior

- Issue IDs are limited to 3 digits (001-999)
- Regex patterns like `[0-9]{3}` enforce exactly 3 digits
- Validation fails or doesn't recognize IDs with 4+ digits

## Expected Behavior

- Issue IDs support 3 or more digits (001-9999+)
- Regex patterns use `[0-9]{3,}` to allow 3+ digits
- All commands and hooks properly handle 4+ digit IDs

## Proposed Solution

Update validation patterns across the codebase:

1. **Shell script** (`hooks/scripts/check-duplicate-issue-id.sh`):
   - Line 54: Update comment pattern documentation
   - Line 56: Change `[0-9]{3}` to `[0-9]{3,}` in the grep pattern

2. **Command documentation** (`commands/normalize_issues.md`):
   - Line 113: Update grep pattern `[0-9]{3}` to `[0-9]{3,}`
   - Line 130: Update grep patterns for ID extraction
   - Lines 162-163: Update grep patterns in find command
   - Line 300: Update regex validation pattern

3. **Fix inconsistency** in `scripts/little_loops/issue_lifecycle.py:293`:
   - Add `:03d` formatting for consistency with `issue_parser.py:270`

Note: Python's `:03d` format specifier already handles 4+ digit numbers correctly (it only pads numbers shorter than 3 digits).

## Anchors

- `hooks/scripts/check-duplicate-issue-id.sh`: function `allow_response`, pattern `(BUG|FEAT|ENH)-[0-9]`
- `commands/normalize_issues.md`: section `### 1. Scan for Invalid Filenames`, pattern `(BUG|FEAT|ENH)-[0-9]`
- `scripts/little_loops/issue_lifecycle.py`: function `create_failure_issue`, variable `bug_id`

## Impact

- **Priority**: P3
- **Effort**: Low (pattern updates across ~6 locations)
- **Risk**: Low (backwards compatible - existing 3-digit IDs continue to work)

## Labels

`enhancement`, `captured`, `validation`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-21
- **Status**: Completed

### Changes Made
- `hooks/scripts/check-duplicate-issue-id.sh`: Updated grep pattern from `[0-9]{3}` to `[0-9]{3,}` (lines 53-56)
- `commands/normalize_issues.md`: Updated 6 patterns from `[0-9]{3}` to `[0-9]{3,}` (lines 21, 113, 130, 162-163, 300, 305)
- `scripts/little_loops/issue_lifecycle.py`: Added `:03d` formatting to bug_id for consistency (line 293)

### Verification Results
- Tests: PASS (1442 tests)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-01-21 | Priority: P3
