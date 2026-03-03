---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# BUG-528: Resource Leak — Log File Handle Never Closed in `run_background`

## Summary

`run_background` opens a log file and passes it to `subprocess.Popen` as both stdout and stderr, but never closes the file handle in the parent process. The `# noqa: SIM115` comment explicitly suppresses the linter warning about missing context manager. In long-running parent processes or test harnesses that call `run_background` repeatedly, file descriptors accumulate without release.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 171–178 (at scan commit: 47c81c8)
- **Anchor**: `in function run_background()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/_helpers.py#L171-L178)
- **Code**:
```python
log_fh = open(log_file, "w")  # noqa: SIM115
process = subprocess.Popen(
    cmd,
    start_new_session=True,
    stdout=log_fh,
    stderr=log_fh,
    stdin=subprocess.DEVNULL,
)
```

## Current Behavior

`log_fh` is opened in the parent process and passed to `Popen`. The parent never calls `log_fh.close()`, so the file descriptor stays open in the parent until garbage collection (CPython: usually immediate; PyPy/other: indefinite). After `Popen`, the file handle in the parent is no longer needed — the child process has inherited the fd.

## Expected Behavior

After `subprocess.Popen` returns, the parent closes `log_fh`. The child process retains its inherited copy of the fd, so background logging continues unaffected.

## Motivation

Each leaked fd consumes a kernel file descriptor slot. On Linux the default per-process limit is 1024 (`ulimit -n`). Test suites that run dozens of background loop starts will exhaust fds, causing subsequent `open()` calls to fail with `EMFILE`. The `# noqa` suppression means the static analysis safety net is deliberately disabled.

## Steps to Reproduce

1. Write a test that calls `run_background` in a loop 1024+ times
2. Observe: `OSError: [Errno 24] Too many open files`

Or more subtly: a long-running parent (e.g., an orchestrator starting many loops) slowly leaks fds over hours.

## Actual Behavior

`log_fh` stays open in the parent process for the duration of the Python process or until GC collects the frame.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in function run_background()`
- **Cause**: `open()` called without context manager; no explicit `close()` after `Popen`; linter suppressed with `noqa`

## Proposed Solution

Close `log_fh` in the parent immediately after `Popen` returns:

```python
log_fh = open(log_file, "w")  # noqa: SIM115
try:
    process = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
    )
finally:
    log_fh.close()
```

Or use a context manager — `Popen` with `close_fds=True` (default on POSIX) ensures the *other* fds are closed in the child, not the log fd. The parent can safely close its copy after `Popen` returns because the child has its own inherited copy.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `run_background()`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_start()` may call `run_background()`

### Similar Patterns
- N/A — only one use of `run_background` in codebase

### Tests
- `scripts/tests/test_cli_loop_background.py` — verify fd count does not increase after `run_background`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `try/finally: log_fh.close()` after `Popen` in `run_background()`
2. Remove the `# noqa: SIM115` comment (or replace with context manager if refactoring)
3. Verify existing `test_cli_loop_background.py` tests still pass

## Impact

- **Priority**: P3 — Real but low-urgency leak; only matters at scale or in test loops
- **Effort**: Small — 2-line fix
- **Risk**: Low — Closing the parent's copy of an fd that the child has inherited is safe
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `resource-leak`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P3
