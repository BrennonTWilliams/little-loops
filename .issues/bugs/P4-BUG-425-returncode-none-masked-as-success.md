---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-425: process.returncode None masked as success

## Summary

In `run_claude_command()`, `process.returncode or 0` converts `None` to `0` (success). If the process hasn't properly terminated, this masks abnormal termination by reporting success instead of raising an error.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 157 (at scan commit: 71616c7)
- **Anchor**: `in function run_claude_command()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/subprocess_utils.py#L157)
- **Code**:
```python
return subprocess.CompletedProcess(
    cmd_args,
    process.returncode or 0,  # None → 0, masking abnormal termination
    stdout="\n".join(stdout_lines),
    stderr="\n".join(stderr_lines),
)
```

## Current Behavior

`process.returncode or 0` converts both `None` and `0` to `0`. While the `or 0` is intended as a fallback, it masks the case where `returncode` is genuinely `None` (process hasn't terminated).

## Expected Behavior

`returncode` of `None` should be treated as an error condition, not silently converted to success.

## Steps to Reproduce

1. Interrupt execution between process spawn and wait (difficult to reproduce)
2. `process.returncode` is `None`
3. Return value reports success (0) instead of indicating an error

## Actual Behavior

Success (returncode 0) is reported even though the process may not have terminated properly.

## Root Cause

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Anchor**: `in function run_claude_command()`
- **Cause**: `or 0` operator treats `None` the same as `0`, masking an abnormal state.

## Proposed Solution

Use explicit None check:

```python
returncode = process.returncode
if returncode is None:
    returncode = 1  # or raise an error
```

Or more concisely: `process.returncode if process.returncode is not None else 1`

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py`
- `scripts/little_loops/issue_manager.py`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_subprocess_utils.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace `process.returncode or 0` with explicit None check
2. Decide on behavior for None case (return 1 or raise)
3. Add test covering the edge case

## Impact

- **Priority**: P4 - Very unlikely edge case, requires unusual process state
- **Effort**: Small - Single line change
- **Risk**: Low - More explicit is strictly better
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `subprocess`, `error-handling`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
