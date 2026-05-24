---
captured_at: '2026-05-24T04:52:29Z'
discovered_date: '2026-05-24'
discovered_by: capture-issue
status: open
---

# BUG-1668: `ll-loop status` shows `Log: (not found)` for foreground runs even when the run is healthy

## Summary

`ll-loop status` always prints `Log: (not found)` for foreground-run loops because `run_foreground()` never creates a `.log` file in the first place — only `run_background()` does. The status output implies the log is missing/broken when it was never expected to exist, masking the more useful signal that an events file does exist and that the instance was a foreground run. This was observed when `ll-loop status autodev` listed 8 instances (all foreground) with `Log: (not found)`, plus a live `deep-research` instance with the same misleading message.

## Current Behavior

For every foreground-run instance, including the currently-live one:

```
Loop: autodev
Status: running
...
PID: 40692 (dead)
Log: (not found)
```

The same line appears for legitimate stale entries, healthy foreground runs, and the (rare) case where a background run's `.log` was actually deleted — three distinct conditions with one undifferentiated message.

Verified directly in `.loops/.running/`:
- 8 `autodev-*.state.json` files exist
- Zero matching `autodev-*.pid` files
- Zero matching `autodev-*.log` files
- `deep-research-20260523T233221` is alive with a `.pid` and `.lock`, but no `.log` file (started in foreground)

## Expected Behavior

The Log line should distinguish three cases:

- `Log: <path>` — when the `.log` file exists (background run, current behavior preserved)
- `Log: (foreground run — output went to terminal)` — when no `.pid` file exists for the instance (foreground runs never write a PID file)
- `Log: (expected <path>, missing)` — when a `.pid` file exists but the `.log` doesn't (genuine "something is wrong" case)

Additionally, every instance has `{instance_id}.events.jsonl` regardless of run mode. The status output should surface it on its own line, e.g.:

```
Events: <path>  (N events, last at <ts>)
```

This gives the operator a recoverable artifact for foreground runs too.

## Motivation

`Log: (not found)` is currently a false-positive failure signal. It implies the log was lost when in fact the run mode never produced one. Operators investigating "is this loop healthy?" waste time looking for a missing file. Surfacing run-mode-accurate labels (and pointing at the always-present events file) turns the status line from misleading into useful.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchors**: `_status_single()` (~lines 61–139) and `cmd_status()` multi-instance branch (~lines 196–228)
- **Cause**: Both branches reconstruct `running_dir / f"{stem}.log"` and check existence, with no awareness of whether the instance ever had a log to begin with. There is no `log_path` field on `LoopState` (verified in `.loops/.running/*.state.json`), so the status code can't tell run mode from state alone.
- **Why no log for foreground**: `run_background()` at `_helpers.py:540, 589` opens `{instance_id}.log` and redirects child stdout/stderr into it. `run_foreground()` at `_helpers.py:608+` does not — output goes to the user's terminal and nothing is persisted.

The `.pid` file presence is a reliable run-mode discriminator: only background runs write `.pid` files (confirmed by inspection of `run_foreground` vs `run_background`). So a status renderer can use `.pid` existence as the signal for "this run should have had a log file."

## Steps to Reproduce

1. Run any foreground loop (e.g. `ll-loop run autodev <some-arg>`) and let it exit or interrupt without graceful shutdown.
2. Run `ll-loop status autodev`.
3. Observe `Log: (not found)` — but `.loops/.running/autodev-*.events.jsonl` does exist with real entries.
4. Confirm no matching `.pid` or `.log` file ever existed: `ls .loops/.running/autodev-*.{pid,log} 2>/dev/null`.

## Proposed Solution

### Part A — Make the status line honest

In both `_status_single()` (~lines 61–139) and `cmd_status()` multi-instance branch (~lines 196–228) of `lifecycle.py`:

1. Look up the instance's `.pid` file alongside the `.log` file check.
2. Print one of three labels:
   - `Log: <path>` when the `.log` exists.
   - `Log: (foreground run — output went to terminal)` when no `.pid` file exists for the instance.
   - `Log: (expected <path>, missing)` when a `.pid` file exists but the `.log` doesn't.

Factor the 3-way label decision into a small helper near the top of the file so the single-instance and multi-instance renderers don't drift.

### Part B — Surface the events file

Add one line below `Log:` in both renderers:

```
Events: <path/to/instance.events.jsonl>  (N events, last at <ts>)
```

This is the closest thing to a structured log the system already produces and exists for every instance regardless of run mode.

### JSON output

`ll-loop status --json` should still emit `log_file: null` for foreground runs (no schema change) and add a new `events_file` field with the path. Existing consumers (e.g. cleanup-loops) are unaffected.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/lifecycle.py` — `_status_single()` (~lines 61–139) and `cmd_status()` multi-instance branch (~lines 196–228); factor 3-way label helper near top of file.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_status` as the `status` subcommand handler.

### Similar Patterns

- ENH-899 (done) added the original `Log:` line and the `_format_relative_time` helper — that helper can be reused for the `last at <ts>` portion of the new `Events:` line.
- BUG-1352 (done) added `pid_source` field for the same status command; this change follows the same surgical-additive shape.

### Tests

- `scripts/tests/test_cli_loop_lifecycle.py` — extend `TestCmdStatusLogFile` with three scenarios: foreground run (no `.pid`, no `.log`), background run with `.log` removed (`.pid` exists, `.log` missing), background run with `.log` present (current behavior).
- `scripts/tests/test_cli_loop_background.py` — `TestCmdStatusWithPid` already writes real PID files; add `events.jsonl` fixture alongside.
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdStatusJson` should assert presence of `events_file` in JSON output and `log_file: null` for foreground.

### Documentation

- `docs/reference/CLI.md` — `#### ll-loop status <loop>` section: document the three Log labels and the new `Events:` line.

### Configuration

- N/A

## Implementation Steps

1. Add a small helper in `lifecycle.py` (e.g. `_format_log_label(running_dir, stem) -> str`) that returns one of the three Log labels by checking `.pid` and `.log` file existence.
2. Replace the current `Log: ...` rendering in `_status_single()` (~lines 61–139) with a call to the helper.
3. Apply the same change in the multi-instance branch in `cmd_status()` (~lines 196–228).
4. Add an `_format_events_line(running_dir, stem) -> str | None` helper that reads `{stem}.events.jsonl`, counts lines, and reads the last entry's timestamp; print `Events: ...` if the file exists.
5. Wire the `events_file` field into the `--json` output dict in both branches.
6. Add tests in `test_cli_loop_lifecycle.py` per the Integration Map.
7. Update `docs/reference/CLI.md`.

## Impact

- **Priority**: P3 — misleading status output that wastes investigation time; not blocking work, but compounds across every foreground run.
- **Effort**: Small — 10–15 line core change plus a small helper, in one file. No schema changes.
- **Risk**: Low — read-only display change; existing JSON contract preserved.
- **Breaking Change**: No (additive `events_file` field, refined human-readable labels).

## Scope Boundaries

- Only the `Log:` and new `Events:` lines in `ll-loop status` are in scope.
- **Out of scope** (filed as separate issues per the originating plan):
  - Reconciling orphaned `status: running` state files with dead PIDs (auto-flip to `interrupted`) — affects `cmd_stop`, `cmd_resume`, `_find_instances`.
  - Optional log capture for foreground runs (tee to `{instance_id}.log` even in foreground).

## Verification

1. `ll-loop status autodev` — all stale instances should show `Log: (foreground run — output went to terminal)` and an `Events: …` line with a real path. Confirm by visiting one of the `.events.jsonl` paths.
2. Start a real background run in a clean scope: `ll-loop run <non-conflicting-loop> --background`. `ll-loop status <loop>` should show `Log: <path>` pointing at the live `.log`.
3. Manually `rm` the `.log` for a background instance whose `.pid` still exists; rerun status; expect `Log: (expected …, missing)`.
4. `ll-loop status autodev --json` should still emit `log_file: null` for foreground runs plus a new `events_file` field. Pipe through `jq` to confirm.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `cli`, `status`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-24T05:07:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6eeae06-e4aa-4cf4-b5de-f799be9249c8.jsonl`
- `/ll:capture-issue` - 2026-05-24T04:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f605fdcc-8000-4585-8dc4-835fc0020291.jsonl`

---

## Status

**Open** | Created: 2026-05-24 | Priority: P3
