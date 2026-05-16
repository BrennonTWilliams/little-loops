---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "Irrelevant for the target platform. little-loops is a Claude Code plugin running on macOS/Linux where Python 3.11+ defaults to UTF-8. Windows is not a supported platform, so this fix solves a problem that can't occur in practice."
---

# BUG-238: Missing encoding="utf-8" in sprint.py file operations

## Summary

The `Sprint.save()` and `Sprint.load()` methods open files without specifying `encoding="utf-8"`. On systems where the default encoding is not UTF-8, this could cause `UnicodeDecodeError` or data corruption for sprint YAML files containing non-ASCII characters.

## Location

- **File**: `scripts/little_loops/sprint.py`
- **Line(s)**: 177, 195 (at scan commit: a8f4144)
- **Anchor**: `in methods Sprint.save and Sprint.load`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sprint.py#L177)
- **Code**:
```python
# save method (line 177)
with open(sprint_path, "w") as f:
    yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

# load method (line 195)
with open(sprint_path) as f:
    data = yaml.safe_load(f)
```

## Current Behavior

Both `open()` calls rely on the system default encoding. The rest of the codebase consistently uses `encoding="utf-8"` (e.g., `issue_parser.py`, `issue_discovery.py`, `sync.py`).

## Expected Behavior

Both calls should specify `encoding="utf-8"` for consistency and cross-platform correctness.

## Proposed Solution

```python
with open(sprint_path, "w", encoding="utf-8") as f:
    yaml.dump(...)

with open(sprint_path, encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p3`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P3
