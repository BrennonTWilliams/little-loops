---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "YAGNI — same reasoning as ENH-242. Hardcoded (BUG|FEAT|ENH) regex only matters if custom types (SEC, DOC, etc.) are added. No one is using custom categories. Fix when someone actually needs it."
---

# ENH-243: Use config prefixes in sync module instead of hardcoded regex

## Summary

`GitHubSyncManager._extract_issue_id()` uses a hardcoded `(BUG|FEAT|ENH)` regex, and `_create_local_issue()` uses a hardcoded `category_map`. Both should dynamically build patterns from `self.config.issues.categories` to support custom issue types.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 347-361, 674-675 (at scan commit: a8f4144)
- **Anchor**: `in methods GitHubSyncManager._extract_issue_id and _create_local_issue`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sync.py#L347-L361)
- **Code**:
```python
# _extract_issue_id
match = re.search(r"(BUG|FEAT|ENH)-(\d+)", filename)

# _create_local_issue
category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
```

## Current Behavior

Custom categories (e.g., "SEC" for security, "DOC" for documentation) are silently ignored by sync operations.

## Expected Behavior

Both the regex and category map should be built dynamically from config.

## Proposed Solution

```python
def _extract_issue_id(self, filename: str) -> str:
    prefixes = "|".join(
        re.escape(cat.prefix)
        for cat in self.config.issues.categories.values()
    )
    match = re.search(rf"({prefixes})-(\d+)", filename)
    ...

# For _create_local_issue:
category_map = {
    cat.prefix: name for name, cat in self.config.issues.categories.items()
}
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p3`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P3
