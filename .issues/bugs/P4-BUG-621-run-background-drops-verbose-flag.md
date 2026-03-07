---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-621: `run_background` does not forward `--verbose` flag to background process

## Summary

`run_background()` in `_helpers.py` re-execs the loop runner as a background process, forwarding several flags (`--max-iterations`, `--no-llm`, `--quiet`, `--queue`). It does not forward `--verbose`. When a user runs `ll-loop run --verbose --background`, the background process runs without verbose output despite the user's explicit request.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 212–273 (at scan commit: 12a6af0)
- **Anchor**: `in function run_background()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/cli/loop/_helpers.py#L212-L273)
- **Code**:
```python
if getattr(args, "quiet", False):
    cmd.append("--quiet")
if getattr(args, "queue", False):
    cmd.append("--queue")
# --verbose is never forwarded
```

## Current Behavior

`--verbose` is silently dropped when `--background` is also specified. The background process uses default (non-verbose) logging.

## Expected Behavior

`--verbose` should be forwarded to the background process just like `--quiet` is.

## Steps to Reproduce

1. Run `ll-loop run myloop --verbose --background`.
2. Check the background process log (`ll-loop status` / loop events file).
3. Observe: the background process stdout/stderr (visible via `ll-loop status`) contains no DEBUG or verbose-level lines.

## Acceptance Criteria

- [ ] Running `ll-loop run myloop --verbose --background` causes the background process to log at verbose level
- [ ] The background process stdout/stderr (via `ll-loop status`) includes DEBUG/verbose-level output when `--verbose` is passed
- [ ] Running without `--verbose` produces no change in behavior
- [ ] Existing `--quiet` and `--queue` flag forwarding is unaffected

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in function run_background()`
- **Cause**: `--verbose` forwarding was simply not included when `--quiet` and `--queue` forwarding was added. One-line omission.

## Proposed Solution

```python
if getattr(args, "verbose", False):
    cmd.append("--verbose")
if getattr(args, "quiet", False):
    cmd.append("--quiet")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()`

### Tests
- `scripts/tests/` — add or update test for `run_background` verifying `--verbose` is forwarded

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--verbose` forwarding in `run_background()` adjacent to the existing `--quiet` forwarding
2. Add or update test in `scripts/tests/` for `run_background` verifying `--verbose` is included in the re-exec command when the flag is set
3. Run tests and verify fix resolves the issue without regressing `--quiet`/`--queue` forwarding

## Impact

- **Priority**: P4 — Minor UX inconsistency; users expecting verbose logs from background runs get none
- **Effort**: Small — One-line fix
- **Risk**: Low — Isolated to flag forwarding
- **Breaking Change**: No

## Labels

`bug`, `cli`, `loop`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4
