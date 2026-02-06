---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "YAGNI — no one uses custom categories. This only matters if someone adds custom issue categories beyond BUG/FEAT/ENH. The project's own config uses standard categories and there's no evidence anyone has ever used custom categories. Fix when someone actually needs it."
---

# ENH-242: Use config categories in sprint manager instead of hardcoded list

## Summary

Both `SprintManager.validate_issues()` and `load_issue_infos()` iterate over a hardcoded `["bugs", "features", "enhancements"]` list instead of using `self.config.issue_categories`. Custom categories added via config will never be found by sprint validation or execution.

## Location

- **File**: `scripts/little_loops/sprint.py`
- **Line(s)**: 318-326, 328-356 (at scan commit: a8f4144)
- **Anchor**: `in methods SprintManager.validate_issues and load_issue_infos`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sprint.py#L318-L356)
- **Code**:
```python
for category in ["bugs", "features", "enhancements"]:
    issue_dir = self.config.get_issue_dir(category)
```

## Current Behavior

Hardcoded category list means custom categories (e.g., "tasks" with prefix "TASK") are never searched.

## Expected Behavior

Use `self.config.issue_categories` to discover all configured categories dynamically.

## Proposed Solution

```python
for category in self.config.issue_categories:
    issue_dir = self.config.get_issue_dir(category)
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
