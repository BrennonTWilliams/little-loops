---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-246: Optimize get_next_issue_number regex compilation

## Summary

`get_next_issue_number()` runs a separate `re.search()` for each prefix on each file, re-compiling the regex pattern every time. A single pre-compiled regex matching all prefixes would eliminate the inner loop.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 37-73 (at scan commit: a8f4144)
- **Anchor**: `in function get_next_issue_number`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/issue_parser.py#L37-L73)
- **Code**:
```python
for file in dir_path.glob("*.md"):
    for prefix in all_prefixes:
        match = re.search(rf"{prefix}-(\d+)", file.name)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
```

## Current Behavior

O(dirs * files * prefixes) regex compilations and searches.

## Expected Behavior

O(dirs * files) with a single pre-compiled regex.

## Proposed Solution

```python
prefixes = "|".join(re.escape(p) for p in all_prefixes)
pattern = re.compile(rf"(?:{prefixes})-(\d+)")
for dir_path in dirs_to_scan:
    for file in dir_path.glob("*.md"):
        match = pattern.search(file.name)
        if match:
            max_num = max(max_num, int(match.group(1)))
```

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (Won't Fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4

**Closure reason**: Premature optimization. Runs on ~30 files max; regex compilation cost is microseconds. No user-visible performance benefit.
