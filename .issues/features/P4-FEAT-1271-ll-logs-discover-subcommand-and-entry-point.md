---
id: FEAT-1271
type: FEAT
priority: P4
status: backlog
title: "ll-logs: discover subcommand and entry-point registration"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false
parent_issue: FEAT-1269
size: Very Large
confidence_score: 100
outcome_confidence: 54
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
---

# FEAT-1271: ll-logs: discover subcommand and entry-point registration

## Summary

Create `scripts/little_loops/cli/logs.py` with `main_logs()` entry point implementing the `discover` subcommand. Register the entry point in `cli/__init__.py` and `pyproject.toml`. This establishes the foundation for the `ll-logs` CLI tool.

## Parent Issue
Decomposed from FEAT-1269: ll-logs: discover + extract subcommands and entry-point registration

## Current Behavior

No `ll-logs` CLI tool exists. There is no way to list which Claude projects have ll activity.

## Expected Behavior

```bash
ll-logs discover   # List all projects with ll activity
ll-logs            # Prints help, exits 1
```

## Implementation Steps

1. **Create `scripts/little_loops/cli/logs.py`** with `main_logs()` entry point:
   - Implement `discover_all_projects()` helper: `(Path.home() / ".claude" / "projects").iterdir()` — decode each dir name back to a path via `.replace("-", "/")` (inverse of `user_messages.py:371`'s `replace("/", "-")`); no existing reusable function for this
   - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup
   - Use `session_log.py:62`'s `glob("*.jsonl")` + `agent-*.jsonl` exclusion pattern for per-project JSONL enumeration
   - Stream-filter JSONL using pattern from `user_messages.py:437`; detect ll-relevance via: (a) `queue-operation` records containing any `ll-` prefix command, (b) `type: "user"` records with `<command-name>/ll:` pattern (see `user_messages.py:771`), (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
   - Add argparse with `discover` subcommand following pattern in `cli/history.py:12`
   - Use `Logger(verbose=args.verbose)` from `logger.py:17`; use `add_config_arg()`, `add_quiet_arg()` from `cli_args.py` where appropriate
   - **⚠ Correction from codebase research**: All existing CLI modules use `configure_output()` + `Logger(use_color=use_color_enabled())`, NOT `Logger(verbose=args.verbose)`. Pattern confirmed in `cli/history.py:8-9,197`, `cli/deps.py:8,209-210`, `cli/docs.py:8,78`. Required imports: `from little_loops.cli.output import configure_output, use_color_enabled`. Call `configure_output()` at the top of `main_logs()`, then instantiate `Logger(use_color=use_color_enabled())`. If quiet mode is needed, use `verbose=not args.quiet` with `add_quiet_arg()`.
   - **⚠ queue-operation records**: The `queue-operation` record type is not currently filtered or used anywhere in `user_messages.py` or other codebase modules. Implementer must inspect actual JSONL files to determine the schema before implementing criterion (a). The `type: "user"` + `<command-name>/ll:` detection (criterion b) is confirmed at `user_messages.py:771`.
   - `main_logs()` return type must be `-> int:` — return `0` for success, `1` for errors, `1` when no subcommand given with `parser.print_help()`

2. **Register entry point** (AFTER `logs.py` exists — do not reverse order):
   - Add `from little_loops.cli.logs import main_logs` to `cli/__init__.py` after line 29 (after `main_issues`, before `main_loop`)
   - Add `"main_logs"` to `__all__` at `cli/__init__.py` after line 51 (after `"main_issues"`, before `"main_loop"`)
   - Update module docstring in `cli/__init__.py:1-20` — add `- ll-logs: Discover and extract ll-relevant JSONL entries from ~/.claude/projects/` after `- ll-history:`
   - Add `ll-logs = "little_loops.cli:main_logs"` to `pyproject.toml` after line 65 (after `ll-generate-schemas`, before `mcp-call`)

3. **Verify**: `ll-logs discover` runs without error; `ll-logs` prints help and exits 1

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. After implementation, implement **FEAT-1004** for docs/skills wiring — `CLAUDE.md`, `commands/help.md`, `skills/init/SKILL.md`, `skills/configure/areas.md`, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md` all need `ll-logs` added. These are tracked separately to keep this issue scoped.
5. When writing `test_ll_logs.py`, model the file structure on `scripts/tests/test_cli_sync.py` (top-level import from sub-module, `patch("sys.argv", ...)`, class-per-subcommand organization).
6. When adding `TestMainLogsIntegration` to `test_cli.py`, insert after `TestMainHistoryCoverage` (line ~2590) using the deferred-import + `patch.object(sys, "argv", ...)` pattern matching `TestMainHistoryCoverage`.

## Integration Map

### Files to Create
- `scripts/little_loops/cli/logs.py` — new CLI tool (discover subcommand only)

### Files to Modify
- `scripts/little_loops/cli/__init__.py:22-62` — add `main_logs` import after line 29; add `"main_logs"` to `__all__` after line 51
- `scripts/pyproject.toml:48-66` — add `ll-logs` entry point after line 65

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — imported by 20+ test files; any syntax error in `logs.py` cascades. Verify `python -c "from little_loops.cli.logs import main_logs"` before touching `cli/__init__.py`.

_Wiring pass added by `/ll:wire-issue`:_

The following test files import from `little_loops.cli` via `from little_loops.cli import main_*` and will fail at collection time (not just execution) if `cli/__init__.py` fails to load:
- `scripts/tests/test_cli.py` — imports `main_auto`, `main_parallel`, `main_messages`, `main_loop`, `main_sprint`, `main_history`
- `scripts/tests/test_issue_history_cli.py` — imports `main_history`
- `scripts/tests/test_next_issues.py` — imports `main_issues`
- `scripts/tests/test_next_action.py` — imports `main_issues`
- `scripts/tests/test_ll_loop_state.py` — imports `main_loop`
- `scripts/tests/test_ll_loop_errors.py` — imports `main_loop`
- `scripts/tests/test_ll_loop_parsing.py` — imports `main_loop`
- `scripts/tests/test_ll_loop_commands.py` — imports `main_loop`
- `scripts/tests/test_builtin_loops.py` — imports `main_loop`
- `scripts/tests/test_doc_synthesis.py` — imports `main_history`
- `scripts/tests/test_sprint.py` — imports `main_sprint`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

Documentation and skills registration updates are tracked in **FEAT-1004** (`.issues/completed/P4-FEAT-1004-ll-logs-docs-and-wiring.md`, status: backlog). That issue covers: `.claude/CLAUDE.md` CLI Tools section, `commands/help.md` CLI TOOLS block, `skills/init/SKILL.md` allow entries + CLI Commands blocks, `skills/configure/areas.md` count, `README.md`, `docs/reference/CLI.md`, `docs/reference/API.md`. Do not duplicate those updates here — implement FEAT-1004 after this issue.

### Similar Patterns
- `scripts/little_loops/user_messages.py:354` — `get_project_folder(cwd)`: encodes CWD path to `~/.claude/projects/<encoded>`
- `scripts/little_loops/session_log.py:62` — `get_current_session_jsonl()`: `project_folder.glob("*.jsonl")` excluding `agent-*.jsonl`
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern
- `scripts/little_loops/user_messages.py:771` — detects `/ll:` invocations via `<command-name>/ll:</command-name>` regex
- `scripts/little_loops/cli/history.py:8-9,197` — `configure_output, use_color_enabled` imports + `Logger(use_color=use_color_enabled())` pattern
- `scripts/little_loops/cli/history.py:12` — `main_history()`: multi-subcommand argparse with `add_config_arg(parser)` at root level

### Tests
- `scripts/tests/test_ll_logs.py` — new test file
  - `class TestArgumentParsing` — argparse unit tests via `_parse_args()` helper, no filesystem
  - `class TestDiscover` — integration tests for `discover` subcommand; mock `Path.home()` or `get_project_folder`
- `scripts/tests/test_cli.py` — add `TestMainLogsIntegration` class following `patch.object(sys, "argv", ...)` + `capsys` pattern

_Wiring pass added by `/ll:wire-issue`:_

Test pattern guidance:
- `test_ll_logs.py` should model `scripts/tests/test_cli_sync.py` — top-level import from sub-module (`from little_loops.cli.logs import main_logs`), `patch("sys.argv", [...])` context manager, `result == 0` / `result == 1` assertions
- `TestMainLogsIntegration` in `test_cli.py` should be added after `TestMainHistoryCoverage` (line ~2590); use deferred `from little_loops.cli import main_logs` inside test body with `patch.object(sys, "argv", [...])` pattern (matches `TestMainHistoryCoverage` style at line 2683+)

## Acceptance Criteria

- [ ] `ll-logs discover` lists all Claude projects with ll activity
- [ ] `ll-logs` (no subcommand) prints help and exits 1
- [ ] Entry point registered; `ll-logs` available after `pip install -e ./scripts`
- [ ] `TestArgumentParsing` and `TestDiscover` test classes pass

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small-Medium — new CLI module, ~80-120 LOC + tests
- **Risk**: Low — new file; entry-point registration is 3 lines with sequencing guard
- **Breaking Change**: No

## Blocks

- FEAT-1272 (extract subcommand — depends on logs.py existing)
- FEAT-1270 (tail subcommand — depends on logs.py existing)

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 54/100 → LOW

### Outcome Risk Factors
- **Wide blast radius on cli/__init__.py**: 20+ test files fail at collection time if `__init__.py` breaks. Follow the sequencing guard strictly (`python -c "from little_loops.cli.logs import main_logs"` before touching `cli/__init__.py`).
- **queue-operation schema is unverified**: The JSONL schema is unknown and requires runtime file inspection before implementing ll-relevance criterion (a). Plan a short investigation step upfront; criterion (a) can be deferred to FEAT-1272 without blocking the discover subcommand.
- **New module has no pre-existing tests**: Test coverage is built during this issue. If tests are skipped or deferred, failures in `discover_all_projects()` will go undetected until integration.

## Session Log
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de8ffde5-dc2f-4352-8703-9f41f72514a5.jsonl`
- `/ll:wire-issue` - 2026-04-23T15:32:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de8ffde5-dc2f-4352-8703-9f41f72514a5.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:26:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fde7109f-3979-4ed7-a527-cc1fc3edcffb.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
