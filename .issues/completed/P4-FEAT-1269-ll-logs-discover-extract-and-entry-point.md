---
id: FEAT-1269
type: FEAT
priority: P4
status: backlog
title: "ll-logs: discover + extract subcommands and entry-point registration"
discovered_date: 2026-04-23
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 46
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 0
size: Very Large
---

# FEAT-1269: ll-logs: discover + extract subcommands and entry-point registration

## Summary

Create `scripts/little_loops/cli/logs.py` with `main_logs()` entry point implementing the `discover` and `extract` subcommands. Register the entry point in `cli/__init__.py` and `pyproject.toml`. This covers the core use case: discovering ll-active projects and extracting filtered JSONL entries into a structured `logs/` directory.

## Parent Issue
Decomposed from FEAT-1002: Implement ll-logs CLI core tool (logs.py + entry point)

## Current Behavior

No tool exists to discover which projects are running ll- CLI tools or to extract ll-relevant JSONL entries from `~/.claude/projects/`.

## Expected Behavior

```bash
ll-logs discover                  # List all projects with ll activity
ll-logs extract --project <slug>  # Extract logs for one project to logs/<slug>/
ll-logs extract --all             # Extract all projects to logs/
ll-logs extract --cmd <tool>      # Filter by specific ll- CLI tool (e.g., ll-history)
```

Output structure:
```
logs/
  index.md
  little-loops/
    e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl
  my-other-project/
    ...
```

## API/Interface

```python
def main_logs() -> int:
    """Entry point for ll-logs CLI tool."""
```

## Implementation Steps

1. **Create `scripts/little_loops/cli/logs.py`** with `main_logs()` entry point:
   - Implement `discover_all_projects()` helper: `(Path.home() / ".claude" / "projects").iterdir()` — decode each dir name back to a path via `.replace("-", "/")` (inverse of `user_messages.py:371`'s `replace("/", "-")`); no existing reusable function for this
   - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup
   - Use `session_log.py:62`'s `glob("*.jsonl")` + `agent-*.jsonl` exclusion pattern for per-project JSONL enumeration; alternatively use `extract_user_messages(include_agent_sessions=False)` at `user_messages.py:383`
   - Stream-filter JSONL using pattern from `user_messages.py:437`; detect ll-relevance via: (a) `queue-operation` records containing any `ll-` prefix command, (b) `type: "user"` records with `<command-name>/ll:` pattern (see `user_messages.py:771` — `build_examples()` or `cli/messages.py:193`), (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
   - Structure output as `logs/<project-slug>/<session-id>.jsonl`
   - Add `logs/index.md` summary
   - Add argparse subcommands (`discover`, `extract`) following pattern in `cli/history.py:12`
   - Use `Logger(verbose=args.verbose)` from `scripts/little_loops/logger.py:17` (class) / `logger.py:38` (constructor); use `add_config_arg()`, `add_quiet_arg()` from `cli_args.py` where appropriate
   - `main_logs()` return type must be `-> int:` — return `0` for success, `1` for errors, `1` when no subcommand given with `parser.print_help()`

2. **Register entry point** (AFTER logs.py exists — do not reverse order):
   - Add `from little_loops.cli.logs import main_logs` to `cli/__init__.py` after line 29 (after `main_issues`, before `main_loop`)
   - Add `"main_logs"` to `__all__` at `cli/__init__.py` after line 51 (after `"main_issues"`, before `"main_loop"` at line 52)
   - Update module docstring in `cli/__init__.py:1-20` — add `- ll-logs: Discover and extract ll-relevant JSONL entries from ~/.claude/projects/` after `- ll-history:` at line 11
   - Add `ll-logs = "little_loops.cli:main_logs"` to `pyproject.toml` after line 65 (after `ll-generate-schemas`, before `mcp-call` at line 66)

3. **Verify**: `ll-logs discover` runs without error

_Documentation file updates (README.md, docs/ARCHITECTURE.md, docs/reference/CLI.md, docs/reference/API.md, CONTRIBUTING.md) belong to FEAT-1005. Skills/commands wiring belongs to FEAT-1006._

## Integration Map

### Files to Create
- `scripts/little_loops/cli/logs.py` — new CLI tool

### Files to Modify
- `scripts/little_loops/cli/__init__.py:22-62` — add `main_logs` import after line 29; add `"main_logs"` to `__all__` after line 51
- `scripts/pyproject.toml:48-66` — add `ll-logs` entry point after line 65

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imported by 20+ test files across the test suite; any syntax error or broken import in `logs.py` will cascade and fail all tests that do `from little_loops.cli import <anything>`. The sequencing guard in Step 2 (create `logs.py` before registering) already addresses this — but `logs.py` must be importable with zero errors before committing the `cli/__init__.py` change.

### Similar Patterns
- `scripts/little_loops/user_messages.py:354` — `get_project_folder(cwd)`: encodes CWD path to `~/.claude/projects/<encoded>`
- `scripts/little_loops/session_log.py:62` — `get_current_session_jsonl()`: `project_folder.glob("*.jsonl")` excluding `agent-*.jsonl`
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern
- `scripts/little_loops/user_messages.py:771` — detects `/ll:` invocations via `<command-name>/ll:SKILL-NAME</command-name>` (inside `build_examples()`); also `cli/messages.py:193`
- `scripts/little_loops/cli/history.py:12` — `main_history()`: multi-subcommand argparse

### Tests
- `scripts/tests/test_ll_logs.py` — new test file
- `scripts/tests/test_cli.py` — existing CLI integration test file; has `TestMainHistoryIntegration` and `TestMainMessagesIntegration` patterns — consider adding a `TestMainLogsIntegration` class here following the same `patch.object(sys, "argv", ...)` + `capsys` pattern [wiring pass added by `/ll:wire-issue`]
- **Test classes**:
  - `class TestArgumentParsing` — argparse unit tests via `_parse_args()` helper, no filesystem
  - `class TestDiscover` — integration tests for `discover` subcommand; mock `Path.home()` or `get_project_folder`
  - `class TestExtract` — integration tests for `extract` subcommand; use `tmp_path` + `_write_jsonl()` helper
- **Key test patterns**:
  - `patch.object(sys, "argv", ["ll-logs", "discover"])` — argv injection
  - `capsys.readouterr()` — capture stdout/stderr
  - `_write_jsonl(path, records)` helper (pattern from `test_user_messages.py:103`)
  - `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)`
  - For multi-project tests: `patch("pathlib.Path.home", return_value=tmp_path)`

### Codebase Research Findings (from FEAT-1002)
- **JSONL record fields**: `type`, `uuid`, `parentUuid`, `timestamp` (ISO 8601 with `Z`), `sessionId`, `cwd`, `gitBranch`, `isSidechain`, `userType`, `entrypoint`, `version`
- **Multi-project decode**: No existing helper. Decode: `dir.name.replace("-", "/")` — leading `-` becomes leading `/`
- **Sequencing risk**: adding `main_logs` to `cli/__init__.py` before `logs.py` exists causes cascade import failures — create `logs.py` first
- **`cli_args.py` exact signatures**: `add_dry_run_arg(parser)` at line 15; `add_config_arg(parser)` at line 35; `add_quiet_arg(parser)` at line 167
- **Logger constructor**: `Logger(verbose=True, use_color=None, colors=None)` at `logger.py:38`
- **`extract_user_messages()` at line 383**: use `include_agent_sessions=False` to exclude agent sessions
- **pyproject.toml format**: all entries use `ll-<name> = "little_loops.cli:main_<name>"`

### Codebase Research Findings (from /ll:refine-issue)

_Added by `/ll:refine-issue` — verified via parallel codebase analysis:_

- **`cli/__init__.py` verified insertion points**: import after line 29 (`main_issues` line 29, `main_loop` line 30); `__all__` after line 51 (`"main_issues"` line 51, `"main_loop"` line 52) — confirmed correct
- **`pyproject.toml` verified insertion point**: after line 65 (`ll-generate-schemas = ...`), before line 66 (`mcp-call = ...`) — confirmed correct
- **`extract_user_messages()` full signature**: `extract_user_messages(project_folder: Path, limit: int | None = None, since: datetime | None = None, include_agent_sessions: bool = True, include_response_context: bool = False)` — `project_folder` is required positional arg; set `include_agent_sessions=False`
- **JSONL streaming exact pattern** (`user_messages.py:437-450`): `open(jsonl_file, encoding="utf-8")` → strip line → skip blank/JSONDecodeError → `json.loads(line)` — `OSError` caught and silently skipped at line 452
- **`history.py` subcommand dispatch pattern** (lines 35-281): `add_subparsers(dest="command")`, guard `if not args.command: return 1`, sequential `if args.command == "..."` blocks — no `set_defaults(func=...)` pattern
- **No existing CLI-layer `index.md` generation**: only analog is `doc_scraper.py:504-528` (sitemap → markdown). Implementer writes fresh: iterate `logs/` subdirs, aggregate metadata (project name, JSONL count, date range), write markdown table
- **Test patch target**: `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)` for unit tests; `patch("pathlib.Path.home", return_value=tmp_path)` for multi-project integration tests
- **`temp_project_folder` fixture** (`test_user_messages.py:103-107`): `tempfile.TemporaryDirectory()` yielded as `Path` — pass directly to `extract_user_messages()` without patching `get_project_folder`

## Acceptance Criteria

- [ ] `ll-logs discover` lists all Claude projects with ll activity
- [ ] `ll-logs extract --all` populates `logs/` with filtered JSONL entries
- [ ] `ll-logs extract --project <slug>` works for a specific project
- [ ] `logs/index.md` is created with a readable summary
- [ ] Entry point is registered and `ll-logs` is available after `pip install -e ./scripts`

## Impact

- **Priority**: P4 - utility tooling enhancement
- **Effort**: Medium - new CLI module with JSONL parsing
- **Risk**: Low - additive only; no changes to existing code paths
- **Breaking Change**: No

## Labels

`feature`, `cli`, `logging`, `analysis`

## Blocks

- FEAT-1270 (tail subcommand — depends on logs.py existing)
- FEAT-1003
- FEAT-1005
- FEAT-1006

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-23_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 46/100 → LOW

### Outcome Risk Factors
- **Wide cascade blast radius**: `cli/__init__.py` is imported by 22+ test files. Any import-time error in `logs.py` fails all 22. Mitigation: verify `python -c "from little_loops.cli.logs import main_logs"` before touching `cli/__init__.py`.
- **Zero pre-existing test coverage on new module**: `test_ll_logs.py` doesn't exist yet. Write the specified test classes (`TestArgumentParsing`, `TestDiscover`, `TestExtract`) in the same PR to close this gap.

## Session Log
- `/ll:confidence-check` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed4d5750-36dc-4fa5-b93c-32d8a7a1ab88.jsonl`
- `/ll:wire-issue` - 2026-04-23T15:17:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed4d5750-36dc-4fa5-b93c-32d8a7a1ab88.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:12:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d712c91e-065b-4dbb-b4d3-ea0c962ee8f6.jsonl`
- `/ll:issue-size-review` - 2026-04-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36817284-b23d-4550-8ba1-417e527e53d0.jsonl`

---

## Status

**Open** | Created: 2026-04-23 | Priority: P4
