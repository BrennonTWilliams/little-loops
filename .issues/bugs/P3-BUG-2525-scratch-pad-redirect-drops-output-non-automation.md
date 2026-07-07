---
id: BUG-2525
title: Scratch-pad redirect drops output file outside automation context
type: BUG
priority: P3
status: open
discovered_date: 2026-07-07
discovered_by: capture-issue
testable: false
---

## Summary

The scratch-pad pattern `mkdir -p .loops/tmp/scratch && <command> > .loops/tmp/scratch/<name>.txt 2>&1` exits 0 but the output file is absent after the command completes when run from a non-automation Claude Code session. CLAUDE.md documents that "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" — it does not: the file disappears, the `> redirect` succeeds, and `echo $?` lies about success.

## Current Behavior

```bash
$ mkdir -p .loops/tmp/scratch && python -m pytest scripts/tests/ --tb=short -q > .loops/tmp/scratch/test-results.txt 2>&1; echo "EXIT_CODE=$?"
EXIT_CODE=0
$ ls -la .loops/tmp/scratch/
ls: .loops/tmp/scratch/: No such file or directory
```

Exit code 0 indicates success, but the scratch directory itself is gone — meaning the `scratch-pad-redirect` hook (or a session-cleanup hook) wiped `.loops/tmp/` after the command finished. The user gets no output and no error.

## Expected Behavior

Either:

1. The scratch-pad pattern should work as documented: the `> .loops/tmp/scratch/<name>.txt` redirect should produce a persistent file the user can `Read` afterward, OR
2. The bash command should exit non-zero (or emit a warning to stderr) when the scratch dir is wiped by a hook, so the user knows to use a different path, OR
3. CLAUDE.md should be updated to clarify the pattern is unreliable outside automation mode and recommend `/tmp/` or a project-root path instead.

## Motivation

The scratch-pad pattern is the recommended way to keep large command output out of conversation context (CLAUDE.md: "For test/lint runs and other large command output, pipe to scratch and tail the summary"). If the pattern silently loses output, it is worse than not using it — the user assumes the file exists, navigates to it, and finds nothing.

## Proposed Solution

Two options:

- **Fix the pattern** — make the `mkdir -p` + redirect self-sufficient by adding a `chmod` or `touch` to anchor the file, or change the cleanup hook to only sweep `*.tmp` patterns, not the whole `.loops/tmp/` directory.
- **Fix the documentation** — clarify that the scratch-pad pattern is automation-only and recommend `/tmp/<name>.txt` for manual use.

The structural fix is to ensure the cleanup hook preserves files the user explicitly created via redirect. A user-intent-aware cleanup (e.g., only sweep `*.pid` or files older than N hours) would solve it without losing the auto-cleanup benefit.

## Steps to Reproduce

1. From repo root, run `mkdir -p .loops/tmp/scratch && python -m pytest scripts/tests/ --tb=short -q > .loops/tmp/scratch/test-results.txt 2>&1; echo "EXIT_CODE=$?"` from a non-automation Claude Code session.
2. After the command completes, run `ls -la .loops/tmp/scratch/`.
3. Observe: `No such file or directory`. The scratch dir has been removed by a hook.

## Root Cause

- **File**: `hooks/hooks.json` (or the hook implementation registered for session cleanup)
- **Anchor**: the session-end / post-tool-use hook that sweeps `.loops/tmp/`
- **Cause**: The cleanup hook removes `.loops/tmp/` (or `.loops/tmp/scratch/`) on session boundary or post-command, wiping files the user explicitly created with `> redirect`. The hook fires in all modes, not just automation.

## Location

- **File**: `hooks/hooks.json` (or the corresponding implementation under `scripts/little_loops/hooks/`)
- **Anchor**: the cleanup hook intent that removes `.loops/tmp/`

## Implementation Steps

1. Identify the hook responsible for cleaning `.loops/tmp/` (search `hooks/hooks.json` and `scripts/little_loops/hooks/` for path patterns matching `.loops/tmp`).
2. Update the hook to:
   - Only sweep files matching known transient patterns (e.g., `*.tmp`, `*.pid`, `*.lock`), OR
   - Only sweep on session-end, not post-command, OR
   - Skip files modified within the last N minutes (preserves active scratch files).
3. Update `CLAUDE.md` § "Automation: Scratch Pad" to reflect the actual semantics.
4. Verify by running the pattern in a non-automation session and confirming the file persists for `Read`.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — adjust the cleanup hook's path filter
- `scripts/little_loops/hooks/` — the Python handler that performs the sweep
- `.claude/CLAUDE.md` — clarify the scratch-pad pattern's reliability

### Tests
- A new test under `scripts/tests/` that exercises the scratch-pad pattern and asserts the file persists.

## Impact

Low-severity user-experience bug. Developers using `/ll:run-tests` (or any command with large output) in non-automation mode will hit this and lose test output. The pattern is documented as the recommended approach, so the failure is misleading.

## Related Key Documentation

- `.claude/CLAUDE.md` § "Automation: Scratch Pad"

## Status

open

## Session Log

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
