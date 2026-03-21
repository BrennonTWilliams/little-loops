# BUG-848: Implementation Failure - FEAT-543

## Summary
`ll-auto` subprocess invocations failed because the Claude CLI now requires `--verbose` when using `--output-format stream-json` with `--print` (`-p`).

## Root Cause
`subprocess_utils.py` constructed the Claude command without `--verbose`:
```
claude --dangerously-skip-permissions --output-format stream-json -p <command>
```
The CLI now enforces: `--output-format=stream-json requires --verbose` when `--print` is used.

## Fix
Added `--verbose` to `cmd_args` in `subprocess_utils.py`:
```python
cmd_args = [
    "claude",
    "--dangerously-skip-permissions",
    "--verbose",          # required with --output-format stream-json + -p
    "--output-format",
    "stream-json",
    "-p",
    command,
]
```
Updated three test files to match the new expected command signature:
- `scripts/tests/test_subprocess_utils.py`
- `scripts/tests/test_subprocess_mocks.py`

## Files Changed
- `scripts/little_loops/subprocess_utils.py`
- `scripts/tests/test_subprocess_utils.py`
- `scripts/tests/test_subprocess_mocks.py`

## Related Issues
- [FEAT-543](/Users/brennon/AIProjects/brenentech/little-loops/.issues/features/P4-FEAT-543-ll-loop-history-filtering.md)

---

## Status
**Completed** | Resolved: 2026-03-20 | Priority: P1
