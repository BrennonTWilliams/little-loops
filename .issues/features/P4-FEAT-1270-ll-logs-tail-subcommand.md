---
id: FEAT-1270
type: FEAT
priority: P4
status: backlog
title: "ll-logs: tail subcommand for live loop session streaming"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false
confidence_score: 95
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation guidance:_

1. **Add `tail` subparser in `logs.py`** following `history.py:35-281`:
   - `tail_parser = subparsers.add_parser("tail", help="Stream live events from an active loop session")`
   - `tail_parser.add_argument("--loop", required=True, metavar="NAME", help="Loop name to tail")`
   - No-command guard (see `history.py:189-191`): `if not args.command: parser.print_help(); return 1`
   - Load `loops_dir = Path(BRConfig(Path.cwd()).loops.loops_dir)` same as `cli/loop/__init__.py:34`

2. **Implement `_cmd_tail(args, loops_dir)` handler**:
   - Construct path: `events_file = loops_dir / ".running" / f"{args.loop}.events.jsonl"` (from `persistence.py:206-207`)
   - If not found: `print(f"No active session for loop '{args.loop}'", file=sys.stderr); return 1`
   - Optional liveness guard: `StatePersistence(args.loop, loops_dir).load_state()` → check `state.status == "running"` + `_process_alive(pid)` from `concurrency.py:26`
   - Follow loop: `f.seek(0, 2)` → `while True: line = f.readline()` → if non-empty: `_format_history_event(json.loads(line.strip()), verbose, terminal_width())` from `info.py:189` → print
   - Wrap in `try/except KeyboardInterrupt: return 0`

3. **Add `TestTail` to `test_ll_logs.py`** following `test_ll_loop_commands.py`:
   - Write a temp `<name>.events.jsonl` file with fixture events; call `_cmd_tail(argparse.Namespace(loop="name"), loops_dir)` and assert via `capsys`
   - Test missing-file path returns 1 and prints error
   - Test `KeyboardInterrupt` exits with 0 by mocking `readline` to raise after first record
   - **Test filesystem style**: `test_ll_logs.py` uses `tempfile.TemporaryDirectory()` (not `tmp_path`) — match this pattern for TestTail
   - **`capsys` style**: declare as plain method parameter without type annotation: `def test_...(self, capsys) -> None:`
   - **`KeyboardInterrupt` mock**: no existing pattern in codebase; `TestTail` will be the first. Use `patch("time.sleep", side_effect=KeyboardInterrupt)` to cause the follow loop to raise after one sleep cycle, or mock `readline` with `side_effect=["line1\n", "", KeyboardInterrupt()]`

4. **Verification**: `python -m pytest scripts/tests/test_ll_logs.py -v -k TestTail`

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CORRECTION — Correct loop events file path** (refs to `get_project_folder()` in the API section below are wrong for this use case):
- `scripts/little_loops/fsm/persistence.py:206-207` — `StatePersistence` constructs the events file as `loops_dir / ".running" / f"{loop_name}.events.jsonl"`. This is the authoritative source for the file path. `get_project_folder()` / `get_current_session_jsonl()` serve Claude Code conversation JSONL files only — not loop event files.
- `scripts/little_loops/fsm/persistence.py:40-41` — constants `RUNNING_DIR = ".running"` and `HISTORY_DIR = ".history"`
- `loops_dir` is obtained via `BRConfig(Path.cwd()).loops.loops_dir` (same pattern as `scripts/little_loops/cli/loop/__init__.py:34`)

**Reusable event formatter:**
- `scripts/little_loops/cli/loop/info.py:189-336` — `_format_history_event(event, verbose, width)` formats loop JSONL event dicts for human-readable output; returns `None` for `action_output` events when non-verbose; directly reusable in `tail` output loop

**Active session detection:**
- `scripts/little_loops/fsm/persistence.py:561-608` — `list_running_loops()` discovers all currently running loops
- `scripts/little_loops/fsm/concurrency.py:26-38` — `_process_alive(pid)` sends signal 0 to check process liveness; combine with `StatePersistence.load_state()` status check (same as `scripts/little_loops/cli/loop/lifecycle.py:100`)

**Argparse dispatch (exact lines):**
- `scripts/little_loops/cli/history.py:35-281` — canonical 3-subcommand pattern; no-command guard at `history.py:189-191`; dispatch chain at `history.py:201-280`
- `scripts/little_loops/cli/loop/__init__.py:254-296` — `history` subparser shows `--verbose/-v`, `--json/-j`, `--event/-e` filter flags; reference for `tail`'s optional flags

**Follow-loop pattern (no existing impl — establish new):**
- `f.seek(0, 2)` to jump to end; poll `f.readline()`; `json.loads(line.strip())`; `_format_history_event(...)`; `time.sleep(0.1)` when empty
- Wrap in `try/except KeyboardInterrupt: return 0` (same pattern as `scripts/little_loops/parallel/orchestrator.py:170-172`)

**Test patterns:**
- `scripts/tests/test_ll_loop_commands.py` — `argparse.Namespace(...)` + direct handler function call + `capsys` for testing subcommand handlers
- `scripts/tests/test_cli.py:TestMainHistoryIntegration` — full `sys.argv` patch + `capsys` for integration-level tests

### Dependent Files (Callers/Importers)
- N/A — `logs.py` is a CLI entry point, not imported by other modules

### Import Dependencies (files `logs.py` imports from)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py:189` — `_format_history_event(event, verbose, width)` is a **private symbol** (leading `_`); importing it from `logs.py` creates a cross-module coupling risk. If the signature changes, `logs.py` breaks at runtime (not caught by static analysis). No other module currently imports it externally — `logs.py` will be the first external consumer. Verify signature stability before finalizing.

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestTail` class (see Files to Modify)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py:55-58` — asserts `"Authorize all 15"` in `skills/configure/areas.md`; will break when the full `ll-logs` ecosystem ships (FEAT-1006 scope, not FEAT-1270 directly)
- `scripts/tests/test_create_extension_wiring.py:77-81,192-196` — asserts `"16 CLI tools"` in `README.md`; same breakage pattern when FEAT-1005 updates the count (sibling issue scope)
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` class (FEAT-1271 scope) will test `main_logs` dispatch including `tail`; ensure TestTail patterns in `test_ll_logs.py` align with the integration test that covers the same handler via `sys.argv` patching

### Documentation
- N/A — no user-facing docs reference `ll-logs tail`

### Configuration
- N/A

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Verify `_format_history_event` signature before import** — check `scripts/little_loops/cli/loop/info.py:189` for the current signature `(event: dict[str, Any], verbose: bool, width: int, full: bool = False) -> str | None`; import it via `from little_loops.cli.loop.info import _format_history_event` and add a comment noting the cross-module private-symbol coupling.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- ~~**FEAT-1269 artifacts missing**: FEAT-1269 is in `.issues/completed/` but `scripts/little_loops/cli/logs.py` does not exist and `main_logs` is not registered in `pyproject.toml`. The completed file still reads `status: backlog`. FEAT-1270 cannot add a `tail` subparser to a file that doesn't exist — verify FEAT-1269 was actually implemented before proceeding.~~ **RESOLVED** (2026-04-23): `scripts/little_loops/cli/logs.py` exists with `discover` subcommand implemented; `ll-logs = "little_loops.cli:main_logs"` is registered in `pyproject.toml`. Dependency satisfied — FEAT-1270 is unblocked.

## Session Log
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab6a7ae5-8378-48e7-a8ed-89a936671ad3.jsonl`
- `/ll:refine-issue` - 2026-04-23T20:56:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a21ca7a-517c-4dd8-bde5-60ff72516da7.jsonl`
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e99e13eb-7a4b-4f4e-bb27-a602348fe421.jsonl`
- `/ll:wire-issue` - 2026-04-23T20:14:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2e7414d-e15b-4602-a8d9-40d2d0d4cfeb.jsonl`
- `/ll:refine-issue` - 2026-04-23T20:07:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd2a44ac-a328-4dcd-9e75-55059451afac.jsonl`
- `/ll:format-issue` - 2026-04-23T20:02:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c47a923b-b9ae-4547-9ded-e6860b7798af.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36817284-b23d-4550-8ba1-417e527e53d0.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
