# ENH-099: Support 4+ Digit Issue IDs - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-099-support-4-digit-issue-ids.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The issue ID validation currently enforces exactly 3 digits via `[0-9]{3}` patterns, limiting projects to 999 issues maximum.

### Key Discoveries
- `hooks/scripts/check-duplicate-issue-id.sh:56` - Uses `grep -oE '(BUG|FEAT|ENH)-[0-9]{3}'` to extract issue IDs
- `commands/normalize_issues.md:113,130,162-163,300` - Multiple occurrences of `[0-9]{3}` patterns
- `scripts/little_loops/issue_lifecycle.py:293` - Missing `:03d` formatting (inconsistency with issue_parser.py:270)

### Patterns Already Supporting 4+ Digits
- `scripts/little_loops/issue_parser.py:19` - Uses `\d+` (flexible)
- `scripts/little_loops/issue_parser.py:66,235` - Uses `\d+` (flexible)
- `scripts/little_loops/issue_parser.py:270` - Uses `:03d` (pads to 3 but handles larger)
- `commands/capture_issue.md:310` - Uses `[0-9]+` (flexible)
- `commands/find_dead_code.md:248` - Uses `[0-9]+` (flexible)

## Desired End State

- Issue IDs support 3 or more digits (001-9999+)
- Regex patterns use `[0-9]{3,}` to allow 3+ digits
- Python formatting uses `:03d` consistently for zero-padding

### How to Verify
- Existing 3-digit IDs (BUG-001, FEAT-123) continue to work
- New 4+ digit IDs (BUG-1234, FEAT-1000) are recognized and validated
- All tests pass

## What We're NOT Doing

- Not changing minimum digit requirement (still minimum 3 digits with zero-padding)
- Not migrating existing issues - backwards compatible
- Not updating documentation prose about "3-digit" - only updating regex patterns

## Solution Approach

Update all `[0-9]{3}` patterns to `[0-9]{3,}` in shell scripts and markdown documentation. Fix the formatting inconsistency in `issue_lifecycle.py`.

## Implementation Phases

### Phase 1: Update Shell Script

#### Overview
Update the duplicate issue ID check hook to support 4+ digit IDs.

#### Changes Required

**File**: `hooks/scripts/check-duplicate-issue-id.sh`

**Line 54**: Update comment to reflect new pattern
```bash
# Pattern: P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-
```

**Line 56**: Change regex from `{3}` to `{3,}`
```bash
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | head -1 || true)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Update normalize_issues.md Command

#### Overview
Update all grep patterns in the normalize issues command documentation to support 4+ digit IDs.

#### Changes Required

**File**: `commands/normalize_issues.md`

**Line 21**: Update documentation
```markdown
- `[NNN]` is a 3+ digit **globally unique** sequential ID (e.g., 001, 042, 1234)
```

**Line 113**: Update validation grep pattern
```bash
if ! echo "$basename" | grep -qE '(BUG|FEAT|ENH)-[0-9]{3,}'; then
```

**Line 130**: Update ID extraction grep patterns (both occurrences on same line)
```bash
id_num=$(echo "$basename" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | grep -oE '[0-9]{3,}')
```

**Lines 162-163**: Update find command grep patterns
```bash
find {{config.issues.base_dir}} -name "*.md" -type f | \
    grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | \
    grep -oE '[0-9]{3,}' | \
```

**Line 300**: Update validation regex
```regex
^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$
```

**Line 305**: Update normalization rule text
```markdown
- Missing 3+ digit ID number
```

#### Success Criteria

**Automated Verification**:
- [ ] File updated successfully
- [ ] Markdown syntax valid (no broken code blocks)

---

### Phase 3: Fix Python Formatting Inconsistency

#### Overview
Add `:03d` formatting to `issue_lifecycle.py` for consistency with `issue_parser.py`.

#### Changes Required

**File**: `scripts/little_loops/issue_lifecycle.py`

**Line 293**: Add `:03d` formatting
```python
bug_id = f"{prefix}-{bug_num:03d}"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Existing tests should pass unchanged (they use 3-digit IDs)
- The `:03d` format specifier handles larger numbers correctly

### Integration Tests
- No new tests needed - backwards compatible change
- Existing test coverage validates current behavior continues working

## References

- Original issue: `.issues/enhancements/P3-ENH-099-support-4-digit-issue-ids.md`
- Related pattern: `scripts/little_loops/issue_parser.py:270` (`:03d` formatting)
- Similar implementation: `commands/capture_issue.md:310` (already uses `[0-9]+`)
