---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# BUG-821: `StateManager.save` non-atomic write — crash mid-write corrupts state file

## Summary

`StateManager.save` uses `Path.write_text()` which truncates the file before writing new content. If the process is killed (SIGKILL, OOM, system crash) between truncation and write completion, the state file will be empty or partially written. On next run, state loading fails and all progress is lost.

## Location

- **File**: `scripts/little_loops/state.py`
- **Line(s)**: 119-126 (at scan commit: 8c6cf90)
- **Anchor**: `in method StateManager.save`
- **Code**:
```python
def save(self) -> None:
    """Save current state to file."""
    try:
        self.state.timestamp = datetime.now().isoformat()
        self.state_file.write_text(json.dumps(self.state.to_dict(), indent=2))
        self.logger.info(f"State saved to {self.state_file}")
    except Exception as e:
        self.logger.error(f"Failed to save state: {e}")
```

## Current Behavior

`Path.write_text()` opens, truncates, and writes. A crash during write leaves an empty or partial file. `StateManager.load` then hits `json.JSONDecodeError` (caught at line 113-114), skips resume, and all completed-issue state is lost.

## Expected Behavior

State writes should be atomic: write to a temporary file in the same directory, then `os.replace()` to the target path. This ensures the state file is always either the old valid version or the new valid version.

## Steps to Reproduce

1. Start `ll-auto` on a large issue set
2. Send SIGKILL while state is being written
3. Restart — no state is resumed, all previously-completed issues are reprocessed

## Proposed Solution

Replace `self.state_file.write_text(...)` with an atomic write pattern:

```python
import tempfile
import os

tmp_fd, tmp_path = tempfile.mkstemp(
    dir=self.state_file.parent, suffix=".tmp"
)
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(self.state.to_dict(), f, indent=2)
    os.replace(tmp_path, self.state_file)
except Exception:
    os.unlink(tmp_path)
    raise
```

The same pattern should be applied to `_save_state` in `orchestrator.py`.

## Impact

- **Priority**: P3 - Data loss risk during crashes; reprocessing issues wastes time and tokens
- **Effort**: Small - Standard atomic write pattern
- **Risk**: Low - `os.replace` is atomic on POSIX; well-established pattern
- **Breaking Change**: No

## Labels

`bug`, `state`, `data-integrity`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
