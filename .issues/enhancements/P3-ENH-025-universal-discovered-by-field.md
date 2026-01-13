---
discovered_commit: null
discovered_branch: main
discovered_date: 2026-01-09T00:00:00Z
---

# ENH-025: Universal discovered_by Field for Issue Tracking

## Summary

Add a `discovered_by` field to all issue frontmatter to track which workflow or command created each issue. This provides provenance tracking independent of product analysis features.

## Motivation

Understanding where issues come from enables:
- Filtering issues by source (e.g., "show me all issues from architecture audits")
- Tracking which workflows generate the most actionable issues
- Debugging and improving scanning workflows
- Providing context when reviewing issues

This is useful for ALL users, not just those with product analysis enabled. Currently, there's no way to distinguish between:
- Issues from `/ll:scan_codebase`
- Issues from `/ll:audit_architecture`
- Issues from `/ll:scan_product` (when product enabled)
- Manually created issues

## Proposed Implementation

### 1. Frontmatter Schema Addition

Add optional `discovered_by` field to issue frontmatter:

```yaml
---
discovered_commit: abc123
discovered_branch: main
discovered_date: 2026-01-09T00:00:00Z
discovered_by: scan_codebase  # NEW FIELD
---
```

### 2. Valid Values

```yaml
discovered_by:
  type: string
  enum:
    - scan_codebase      # From /ll:scan_codebase
    - scan_product       # From /ll:scan_product (product dimension)
    - audit_architecture # From /ll:audit_architecture
    - audit_docs         # From /ll:audit_docs
    - manual             # User-created
  description: Which workflow discovered this issue
  optional: true
  default: null  # For backwards compatibility
```

### 3. Commands to Update

Update these commands to populate `discovered_by`:

| Command | Value |
|---------|-------|
| `/ll:scan_codebase` | `scan_codebase` |
| `/ll:audit_architecture` | `audit_architecture` |
| `/ll:audit_docs` | `audit_docs` |
| `/ll:scan_product` | `scan_product` |

### 4. Parser Update

Update `scripts/little_loops/issue_parser.py`:

```python
@dataclass
class IssueInfo:
    """Parsed information from an issue file."""
    # ... existing fields ...
    discovered_by: Optional[str] = None
```

### 5. Backwards Compatibility

- Field is optional - existing issues remain valid
- Missing `discovered_by` treated as `null` (unknown source)
- No migration required for existing issues

## Location

- **Modified**: `scripts/little_loops/issue_parser.py`
- **Modified**: `commands/scan_codebase.md`
- **Modified**: `commands/audit_architecture.md`
- **Modified**: `commands/audit_docs.md`

## Current Behavior

Issues have no indication of which workflow created them.

## Expected Behavior

New issues include `discovered_by` in frontmatter indicating their source command.

## Acceptance Criteria

- [ ] `discovered_by` field added to issue parser
- [ ] `/ll:scan_codebase` populates `discovered_by: scan_codebase`
- [ ] `/ll:audit_architecture` populates `discovered_by: audit_architecture`
- [ ] Existing issues without field parse correctly (null value)
- [ ] Unit test for parsing issues with and without `discovered_by`

## Impact

- **Severity**: Low - Quality-of-life improvement
- **Effort**: Small - Straightforward field addition
- **Risk**: Low - Optional field, backwards compatible

## Dependencies

None - this is independent of product analysis features.

## Blocked By

None

## Blocks

- ENH-024: Product Impact Fields in Issue Templates (can use this field)

## Labels

`enhancement`, `issue-format`, `tracking`

---

## Status

**Open** | Created: 2026-01-09 | Priority: P3
