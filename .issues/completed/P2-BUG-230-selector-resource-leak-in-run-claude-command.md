---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-230: Selector resource leak in run_claude_command

## Summary

The `selectors.DefaultSelector` created in `run_claude_command` is never closed, leaking file descriptors. Over many invocations (e.g., processing dozens of issues in `ll-auto` or `ll-parallel`), this accumulates leaked file descriptors.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 106-148 (at scan commit: a8f4144)
- **Anchor**: `in function run_claude_command`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/subprocess_utils.py#L106-L148)
- **Code**:
```python
sel = selectors.DefaultSelector()
if process.stdout:
    sel.register(process.stdout, selectors.EVENT_READ)
if process.stderr:
    sel.register(process.stderr, selectors.EVENT_READ)

# ... no sel.close() anywhere in the function ...

try:
    while sel.get_map():
        # ...
    process.wait()
finally:
    if on_process_end:
        on_process_end(process)

return subprocess.CompletedProcess(...)
```

## Current Behavior

The selector is created but never closed. The `DefaultSelector` holds file descriptors that are not released when the function returns.

## Expected Behavior

The selector should be used as a context manager (`with selectors.DefaultSelector() as sel:`) or explicitly closed in a `finally` block to ensure OS resources are released.

## Reproduction Steps

1. Run `ll-auto` or `ll-parallel` processing many issues
2. Monitor file descriptors (e.g., `lsof -p <pid>`)
3. Observe file descriptor count grows with each processed issue

## Proposed Solution

Use the context manager protocol:
```python
with selectors.DefaultSelector() as sel:
    if process.stdout:
        sel.register(process.stdout, selectors.EVENT_READ)
    # ... rest of function
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Completed** | Created: 2026-02-06T03:41:30Z | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/subprocess_utils.py`: Wrapped `selectors.DefaultSelector()` in `with` statement to ensure OS file descriptors are released on both normal completion and exception paths
- `scripts/tests/test_subprocess_utils.py`: Added `_patch_selector_cm` helper and `TestRunClaudeCommandSelectorCleanup` test class with tests for selector closure on success and timeout; updated all existing tests to support context manager protocol
- `scripts/tests/test_subprocess_mocks.py`: Updated selector mocks to support context manager protocol

### Verification Results
- Tests: PASS (39/39 + 22/22)
- Lint: PASS
- Types: PASS
