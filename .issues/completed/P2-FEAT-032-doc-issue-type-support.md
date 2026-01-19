---
discovered_commit: 0c81bb3
discovered_branch: main
discovered_date: 2026-01-12T00:00:00Z
---

# FEAT-032: Add DOC Issue Type for Documentation Changes

## Summary

Add support for a new `DOC` issue type to track documentation-focused work that doesn't fit well into the existing BUG, FEAT, or ENH categories.

## Motivation

The current issue type system supports:
- **BUG** - Bug fixes
- **FEAT** - New features
- **ENH** - Enhancements to existing features

However, documentation-focused work doesn't fit cleanly into these categories:
- README updates
- API documentation improvements
- Architecture documentation
- Tutorial and guide creation
- Inline code documentation

Creating a dedicated `DOC` issue type provides:
1. Clearer categorization of documentation work
2. Better filtering and reporting on documentation tasks
3. Consistent action verb ("document") for documentation issues
4. Dedicated directory for organization

## Proposed Implementation

### 1. Update Default Categories in Config

**File**: `scripts/little_loops/config.py` (lines 87-93)

Add DOC category to the default categories dict:

```python
categories_data = data.get(
    "categories",
    {
        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
        "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
        "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
    },
)
```

### 2. Update Issue Type Matching

**File**: `scripts/little_loops/issue_discovery.py` (lines 339-343)

Add DOC to the hardcoded issue type matching:

```python
issue_type_match = (
    (finding_type == "BUG" and "/bugs/" in str(issue_path))
    or (finding_type == "ENH" and "/enhancements/" in str(issue_path))
    or (finding_type == "FEAT" and "/features/" in str(issue_path))
    or (finding_type == "DOC" and "/documentation/" in str(issue_path))
    or is_completed
)
```

### 3. Update Template Files

Add DOC category to all template configurations:
- `templates/generic.json`
- `templates/python-generic.json`

```json
"documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"}
```

### 4. Update Documentation

**File**: `.claude/CLAUDE.md`
```markdown
- Types: `BUG`, `FEAT`, `ENH`, `DOC`
```

**File**: `README.md`
Update the configuration example to include DOC category.

### 5. Update Test Fixtures

**File**: `scripts/tests/conftest.py`

Add DOC to the `sample_config` fixture's categories.

### 6. Create Documentation Directory

Create the new directory: `.issues/documentation/`

## Location

- **Modified**: `scripts/little_loops/config.py`
- **Modified**: `scripts/little_loops/issue_discovery.py`
- **Modified**: `templates/generic.json`
- **Modified**: `templates/python-generic.json`
- **Modified**: `.claude/CLAUDE.md`
- **Modified**: `README.md`
- **Modified**: `scripts/tests/conftest.py`
- **New Directory**: `.issues/documentation/`

## Current Behavior

- Only three issue types are supported: BUG, FEAT, ENH
- Documentation work must be categorized as ENH or FEAT
- Issue discovery only matches against three directory paths

## Expected Behavior

- Four issue types supported: BUG, FEAT, ENH, DOC
- Documentation issues stored in `.issues/documentation/`
- Issue parsing and discovery correctly handle DOC type
- Templates include DOC category by default

## Acceptance Criteria

- [ ] DOC category added to default config in `config.py`
- [ ] Issue discovery matches DOC type to documentation directory
- [ ] All template files include DOC category
- [ ] `.claude/CLAUDE.md` documents DOC type
- [ ] `README.md` shows DOC in configuration example
- [ ] Test fixtures include DOC category
- [ ] `.issues/documentation/` directory created
- [ ] Existing tests pass
- [ ] DOC issues can be created and parsed correctly

## Impact

- **Severity**: Low - Additive change, no breaking changes
- **Effort**: Low - Configuration and documentation updates
- **Risk**: Very Low - Existing behavior unchanged

## Dependencies

None

## Blocked By

None

## Blocks

None

## Labels

`feature`, `configuration`, `issue-management`

---

## Verification Notes

**Verified: 2026-01-19**

This issue was **superseded by FEAT-033** (Generalize Issue Type System).

The implementation in FEAT-033 created a generalized category system where:
- `REQUIRED_CATEGORIES` in `config.py` (lines 32-36) defines BUG, FEAT, ENH as required
- Users can add custom categories (including DOC) via `ll-config.json`:
  ```json
  "issues": {
    "categories": {
      "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"}
    }
  }
  ```
- `_matches_issue_type()` in `issue_discovery.py` (lines 445-469) now iterates over all configured categories dynamically

The hardcoded approach described in this issue is no longer needed. The generalized system provides the same functionality more flexibly.

---

## Status

**Resolved** | Created: 2026-01-12 | Resolved: 2026-01-19 | Priority: P2

**Resolution**: Superseded by FEAT-033 (Generalize Issue Type System)
