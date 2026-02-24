---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-476: `session_log.py` append replaces all occurrences instead of first

## Summary

`append_session_log_entry` uses `str.replace()` without a `count` argument, which replaces ALL occurrences of `## Session Log\n` in the file. If the header appears more than once (e.g., from a prior bug or user edit), the new entry is inserted after every occurrence.

## Location

- **File**: `scripts/little_loops/session_log.py`
- **Line(s)**: 66-71 (at scan commit: 95d4139; updated HEAD: fb6579c)
- **Anchor**: `in function append_session_log_entry`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/session_log.py#L66-L70)
- **Code**:
```python
if "## Session Log" in content:
    content = content.replace(
        "## Session Log\n",
        f"## Session Log\n{entry}\n",
    )
```

## Current Behavior

`str.replace("## Session Log\n", ...)` replaces every occurrence of the section header string in the file content.

## Expected Behavior

Only the first occurrence of the section header is targeted for the insertion.

## Steps to Reproduce

1. Create an issue file that has `## Session Log` appearing twice (e.g., from a copy/paste error)
2. Run any skill that appends a session log entry
3. Observe the entry is inserted after both occurrences

## Proposed Solution

Add the `count=1` argument:

```python
content = content.replace(
    "## Session Log\n",
    f"## Session Log\n{entry}\n",
    1,  # Only replace first occurrence
)
```

## Implementation Steps

1. Add `count=1` argument to `str.replace` call in `append_session_log_entry`
2. Add test with duplicate `## Session Log` headers

## Integration Map

### Files to Modify
- `scripts/little_loops/session_log.py` — add `count=1` to `str.replace` call

### Dependent Files (Callers/Importers)
- Multiple skills call `append_session_log_entry`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add test with duplicate `## Session Log` headers

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Low probability of duplicate headers, but when it occurs causes file corruption
- **Effort**: Small — Single argument addition
- **Risk**: Low — Strictly more correct behavior
- **Breaking Change**: No

## Labels

`bug`, `session-log`, `auto-generated`

## Resolution

- **Status**: Fixed
- **Fixed date**: 2026-02-24
- **Fix**: Added `count=1` to `str.replace()` call in `append_session_log_entry` (`scripts/little_loops/session_log.py`). Added `test_duplicate_session_log_headers_only_inserts_once` test.

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:manage-issue` - 2026-02-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`

---

## Status

**Closed** | Created: 2026-02-24 | Resolved: 2026-02-24 | Priority: P3
