---
id: ENH-2067
title: 'll-logs: suppress stale-worktree decoded-path warnings'
type: ENH
priority: P4
status: done
captured_at: '2026-06-10T04:03:22Z'
completed_at: '2026-06-10T04:49:50Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 98
score_complexity: 25
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2067: ll-logs suppress stale-worktree decoded-path warnings

## Summary

`ll-logs extract --all` (and `discover`) emit a `[WARNING] Decoded path does not exist` line for every stale worktree path registered in the Claude projects dir. On a machine with many old ll-parallel runs, this floods stderr with dozens of noise lines that obscure the actual extraction output.

## Current Behavior

`ll-logs extract --all` and `ll-logs discover` emit a `[WARNING] Decoded path does not exist` line at the default log level for every stale worktree path registered in the Claude projects directory. On machines with many old `ll-parallel` runs, this produces dozens of consecutive warning lines on stderr before any actual output, making it difficult to determine whether the command succeeded or produced meaningful results.

## Expected Behavior

- `ll-logs extract --all` produces no output on stderr for missing/stale paths at the default log level.
- Running with `LL_LOG_LEVEL=DEBUG` still shows the skipped-path lines for diagnostic use.
- Existing extract/discover behavior (correctly skipping missing paths via `continue`) is unchanged.

## Motivation

Users running `ll-logs extract --all` for the first time see hundreds of warning lines for worktree paths that were cleaned up long ago. These warnings carry no actionable information — the tool already skips those paths correctly (`continue` on line 182 of `scripts/little_loops/cli/logs.py`). The noise makes it hard to tell whether the command succeeded or produced meaningful output.

## Proposed Solution

Downgrade the `logger.warning(...)` at `scripts/little_loops/cli/logs.py:181` to `logger.debug(...)` so it only appears at `--verbose` / `DEBUG` log level. Alternatively, add a `--quiet` flag to the top-level `ll-logs` parser that sets the log level to `WARNING` or higher, suppressing these info-level path skips.

**Preferred approach**: downgrade to `debug` — it's a one-line fix, requires no new CLI surface, and the message is still reachable via `LL_LOG_LEVEL=DEBUG ll-logs extract --all` for diagnostic use.

## Implementation Steps

1. In `scripts/little_loops/cli/logs.py:181`, change `logger.warning(...)` → `logger.debug(...)`.
2. Add a test in `scripts/tests/test_builtin_loops.py` (or a new `test_ll_logs.py`) that calls `discover_projects()` with a project dir containing a path that doesn't exist and asserts no warning is emitted at the default log level.

## Scope Boundaries

- Only downgrade the stale-worktree decoded-path warning to `debug` level; no other log messages are changed.
- Does not add a `--quiet` flag or any new CLI surface (mentioned as an alternative but deferred).
- Does not modify path-skip logic — behavior remains identical; only the log verbosity changes.
- Does not address other categories of `ll-logs` warnings or noisy output.

## Impact

- **Priority**: P4 — Quality-of-life noise reduction; command already functions correctly.
- **Effort**: Small — One-line change (`logger.warning` → `logger.debug`) plus a targeted test.
- **Risk**: Low — No behavioral change; only log verbosity is affected.
- **Breaking Change**: No

## Labels

`cli`, `logging`, `ux-noise`

## Status

**Open** | Created: 2026-06-10 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-10T04:46:37 - `a74e466d-daf0-4199-acc1-46473c772ae3.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `286cebf8-b4d5-4504-ad25-1507239fa3dd.jsonl`
- `/ll:format-issue` - 2026-06-10T04:08:21 - `62b84f66-68e2-4bb7-8596-0007f0868fbf.jsonl`
- `/ll:capture-issue` - 2026-06-10T04:03:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
