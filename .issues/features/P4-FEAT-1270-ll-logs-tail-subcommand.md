---
id: FEAT-1270
type: FEAT
priority: P4
status: backlog
title: "ll-logs: tail subcommand for live loop session streaming"
discovered_date: 2026-04-23
discovered_by: issue-size-review
---

# FEAT-1270: ll-logs: tail subcommand for live loop session streaming

## Summary

Add the `tail` subcommand to `scripts/little_loops/cli/logs.py` (created by FEAT-1269), implementing live tailing of active ll-loop JSONL sessions. Includes `TestTail` integration tests.

## Parent Issue
Decomposed from FEAT-1002: Implement ll-logs CLI core tool (logs.py + entry point)

## Depends On
- FEAT-1269 — `logs.py` and entry-point registration must exist first

## Current Behavior

No live-tail capability exists for monitoring active ll-loop sessions.

## Expected Behavior

```bash
ll-logs tail --loop <name>   # Live tail active loop sessions matching <name>
```

Streams new JSONL lines as they are written to the active session file, similar to `tail -f`.

## Motivation

Adding `tail` to `ll-logs` enables real-time loop observability:
- **Developer visibility**: See what a running loop is doing without waiting for completion or manually polling the JSONL file.
- **Debugging aid**: Live output makes it easy to catch early failures or unexpected behavior in long-running loops.
- **Completes the `ll-logs` toolset**: Pairs `discover`/`extract` (historical queries) with live tailing for a complete log interaction model.

## Use Case

**Who**: Developer running active ll-loop sessions who wants to monitor progress in real time.

**Context**: `ll-loop run <name>` is executing a long-running automation. The developer wants to see what the loop is doing — without waiting for it to finish or manually opening the JSONL file.

**Goal**: Tail the active loop's session JSONL file live, seeing new records as they are written.

**Outcome**: `ll-logs tail --loop <name>` streams formatted output as the loop runs and exits cleanly on Ctrl-C.

## API/Interface

```bash
ll-logs tail --loop <name>
```

The subcommand:
- Locates the active session JSONL for the named loop (using `get_project_folder()` + JSONL discovery from FEAT-1269's helpers)
- Streams new records as they arrive (follow mode)
- Formats output readably (e.g., timestamps + message type + content snippet)
- Exits cleanly on Ctrl-C

## Implementation Steps

1. **Add `tail` subparser** to the argparse setup in `logs.py` (alongside existing `discover`/`extract` subparsers):
   - `--loop <name>` argument: filter by loop name
   - Reuse `get_project_folder()` and JSONL discovery helpers already in `logs.py`
   - Implement follow logic: open file, seek to end, poll for new lines with a small sleep (or use `inotify`/`kqueue` if available)

2. **Add tests** to `scripts/tests/test_ll_logs.py`:
   - `class TestTail` — integration tests for `tail` subcommand
   - Test that `tail --loop` locates the correct session file
   - Test graceful handling when no active session exists for the given loop name

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `tail` subparser and handler (created by FEAT-1269)
- `scripts/tests/test_ll_logs.py` — add `TestTail` class (created by FEAT-1269)

### Similar Patterns
- `scripts/little_loops/session_log.py:62` — JSONL file discovery
- `scripts/little_loops/cli/history.py:12` — subcommand dispatch pattern
- Standard `tail -f` follow pattern: open, seek end, loop + sleep polling for new content

### Codebase Research Findings (from FEAT-1002)
- **Agent subdir structure**: Some projects have UUID subdirs under `~/.claude/projects/<encoded>/` with `subagents/agent-*.jsonl`. Top-level `glob("*.jsonl")` covers non-agent files only.
- **Loop session detection**: `queue-operation` records containing `ll-loop run <name>` identify the loop's session

### Dependent Files (Callers/Importers)
- N/A — `logs.py` is a CLI entry point, not imported by other modules

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestTail` class (see Files to Modify)

### Documentation
- N/A — no user-facing docs reference `ll-logs tail`

### Configuration
- N/A

## Acceptance Criteria

- [ ] `ll-logs tail --loop <name>` streams live JSONL entries from an active loop session
- [ ] Exits gracefully on Ctrl-C without a traceback
- [ ] Prints a useful message when no active session is found for the given loop name
- [ ] `TestTail` tests pass

## Impact

- **Priority**: P4 - utility tooling enhancement
- **Effort**: Small - single subcommand added to existing logs.py
- **Risk**: Low - additive only
- **Breaking Change**: No

## Labels

`feature`, `cli`, `logging`, `analysis`

---

## Session Log
- `/ll:format-issue` - 2026-04-23T20:02:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c47a923b-b9ae-4547-9ded-e6860b7798af.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36817284-b23d-4550-8ba1-417e527e53d0.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
