---
id: FEAT-1002
type: FEAT
priority: P4
status: backlog
title: Implement ll-logs CLI core tool (logs.py + entry point)
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 71
---

# FEAT-1002: Implement ll-logs CLI core tool (logs.py + entry point)

## Summary

Create `scripts/little_loops/cli/logs.py` with `main_logs()` entry point and register it in `cli/__init__.py` and `pyproject.toml`. This is the core CLI tool for discovering Claude project log directories, filtering ll-relevant JSONL entries, and writing them to a structured `logs/` directory.

## Parent Issue
Decomposed from FEAT-1001: Add log discovery and extraction for ll-loop and ll-commands

## Current Behavior

No tool exists to discover which projects are running ll- CLI tools or to extract ll-relevant JSONL entries from `~/.claude/projects/`.

## Expected Behavior

`ll-logs` CLI available with three subcommands:
```bash
ll-logs discover                  # List all projects with ll activity
ll-logs extract --project <slug>  # Extract logs for one project
ll-logs extract --all             # Extract all projects to logs/
ll-logs tail --loop <name>        # Live tail active loop sessions
ll-logs extract --cmd ll-history  # Extract logs for a specific ll- CLI tool
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

## Motivation

No tool currently exists to discover which Claude projects use ll- CLI tools or to extract ll-relevant entries from `~/.claude/projects/`. This matters because:
- Developers lose visibility into which projects are actively running ll- automation
- Debugging ll-loop runs requires manually hunting through raw JSONL files in `~/.claude/projects/`
- Extracting ll-relevant entries by hand is error-prone without a dedicated tool

## Use Case

**Who**: A developer running ll- CLI tools across multiple Claude projects

**Context**: Investigating which projects are actively using ll-loop or ll-commands, or debugging a specific loop run by tracing its JSONL session entries

**Goal**: Discover all projects with ll activity and extract filtered JSONL entries into a structured `logs/` directory for review

**Outcome**: `ll-logs discover` lists active projects; `ll-logs extract --all` produces a `logs/` directory with filtered JSONL files and an `index.md` summary

## API/Interface

```bash
# Entry point: ll-logs
ll-logs discover                  # List all projects with ll activity
ll-logs extract --project <slug>  # Extract logs for one project to logs/<slug>/
ll-logs extract --all             # Extract all projects to logs/
ll-logs extract --cmd <tool>      # Filter by specific ll- CLI tool (e.g., ll-history)
ll-logs tail --loop <name>        # Live tail active loop sessions
```

```python
def main_logs() -> int:
    """Entry point for ll-logs CLI tool."""
```

## Implementation Steps

1. **Create `scripts/little_loops/cli/logs.py`** with `main_logs()` entry point:
   - Implement `discover_all_projects()` helper: `(Path.home() / ".claude" / "projects").iterdir()` — decode each dir name back to a path via `.replace("-", "/")` (inverse of `user_messages.py:371`'s `replace("/", "-")`); no existing reusable function for this
   - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup
   - Use `session_log.py:62`'s `glob("*.jsonl")` + `agent-*.jsonl` exclusion pattern for per-project JSONL enumeration
   - Stream-filter JSONL using pattern from `user_messages.py:436`; detect ll-relevance via: (a) `queue-operation` records containing any `ll-` prefix command, (b) `type: "user"` records with `<command-name>/ll:` pattern (see `user_messages.py:189`), (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
   - Structure output as `logs/<project-slug>/<session-id>.jsonl`
   - Add argparse subcommands (`discover`, `extract`, `tail`) following pattern in `cli/history.py:12`
   - Use `Logger(verbose=args.verbose)` from `scripts/little_loops/logger.py:17`; use `add_config_arg()`, `add_dry_run_arg()`, `add_quiet_arg()` from `cli_args.py` where appropriate

2. **Register entry point** (AFTER logs.py exists — do not reverse order):
   - Add `from little_loops.cli.logs import main_logs` to `cli/__init__.py:20-36`
   - Add `"main_logs"` to `__all__` at `cli/__init__.py:38-56`
   - Add `ll-logs = "little_loops.cli:main_logs"` to `pyproject.toml:48-63`

3. **Verify**: `ll-logs discover` runs without error

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `commands/help.md` — append `ll-logs` entry to the CLI TOOLS block (two-column format matching existing entries)
5. Update `skills/configure/areas.md:793` — increment "all ll- commands" count and append `ll-logs` to the enumerated list
6. Update `README.md:90` — increment `13 CLI tools` to `14 CLI tools`; add `### ll-logs` section after `### ll-gitignore`
7. Update `docs/ARCHITECTURE.md:175-184` — add `├── logs.py` with comment to the `cli/` directory tree
8. Update `CONTRIBUTING.md:183-194` — add `logs.py` to the `cli/` directory listing
9. Update `docs/reference/API.md` — add `ll-logs` entry in the CLI tools reference section

## Integration Map

### Files to Create
- `scripts/little_loops/cli/logs.py` — new CLI tool

### Files to Modify
- `scripts/little_loops/cli/__init__.py:20-56` — add `main_logs` import and `__all__` entry
- `scripts/pyproject.toml:48-63` — add `ll-logs` entry point
- `commands/help.md` — append `ll-logs` entry to the CLI TOOLS block [Wiring: registration]
- `skills/configure/areas.md:793` — increment tool count and append `ll-logs` to the enumerated authorization list [Wiring: registration]

### Similar Patterns
- `scripts/little_loops/user_messages.py:354` — `get_project_folder(cwd)`: encodes CWD path to `~/.claude/projects/<encoded>`
- `scripts/little_loops/session_log.py:62` — `get_current_session_jsonl()`: `project_folder.glob("*.jsonl")` excluding `agent-*.jsonl`
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern
- `scripts/little_loops/user_messages.py:189` — `--skill` filter: detects `/ll:` invocations via `<command-name>/ll:SKILL-NAME</command-name>`
- `scripts/little_loops/cli/messages.py:11` — `main_messages()`: flat argparse CLI
- `scripts/little_loops/cli/history.py:12` — `main_history()`: multi-subcommand argparse

### Dependent Files (Callers/Importers)
- N/A — new module; `cli/__init__.py` and `pyproject.toml` will import/register it (covered in Files to Modify)

### Tests
- `scripts/tests/test_ll_logs.py` — new test file for `main_logs()` subcommands (`discover`, `extract`, `tail`)
- **Test class structure** (from `test_issue_history_cli.py` + `test_user_messages.py`):
  - `class TestArgumentParsing` — argparse unit tests via `_parse_args()` helper, no filesystem
  - `class TestDiscover` — integration tests for `discover` subcommand; mock `Path.home()` or `get_project_folder`
  - `class TestExtract` — integration tests for `extract` subcommand; use `tmp_path` + `_write_jsonl()` helper
  - `class TestTail` — integration tests for `tail` subcommand
- **Key test patterns** (all confirmed in test suite):
  - `patch.object(sys, "argv", ["ll-logs", "discover"])` — argv injection
  - `capsys.readouterr()` — capture stdout/stderr
  - `_write_jsonl(path, records)` helper — write JSONL fixture files (pattern from `test_user_messages.py:103`)
  - `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)` — mock project folder lookup (pattern from `test_session_log.py:18`)
  - For multi-project tests: build a fake `~/.claude/projects/` tree under `tmp_path` and `patch("pathlib.Path.home", return_value=tmp_path)`

### Documentation
- `CLAUDE.md` — CLI Tools section should list `ll-logs` after implementation
- `docs/reference/CLI.md` — CLI reference lists `ll-messages`, `ll-history`; add `ll-logs` entry here

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:90` — `13 CLI tools` count needs incrementing to 14; add `### ll-logs` section after `### ll-gitignore` [Wiring: doc count]
- `docs/ARCHITECTURE.md:175-184` — `cli/` directory tree lists individual files; add `logs.py` entry [Wiring: architecture doc]
- `CONTRIBUTING.md:183-194` — `cli/` directory listing; add `logs.py` entry [Wiring: contributing doc]
- `docs/reference/API.md` — CLI entry point references section; add `ll-logs` entry [Wiring: API reference]

### Configuration
- N/A — `pyproject.toml` entry point registration already listed in Files to Modify

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **JSONL record fields**: `type`, `uuid`, `parentUuid`, `timestamp` (ISO 8601 with `Z`), `sessionId`, `cwd`, `gitBranch`, `isSidechain`, `userType`, `entrypoint`, `version`. Skill invocations in `type: "user"` records as `<command-name>/ll:SKILL-NAME</command-name>`. CLI tools in `queue-operation` records as `content: "/ll-loop run <name>"`.
- **Multi-project decode**: No existing helper. Decode: `dir.name.replace("-", "/")` — leading `-` becomes leading `/`. Forward encode at `user_messages.py:371`.
- **Agent subdir structure**: Some projects have UUID subdirs under `~/.claude/projects/<encoded>/` with `subagents/agent-*.jsonl`. Top-level `glob("*.jsonl")` only covers non-agent files.
- **Sequencing risk**: adding `main_logs` to `cli/__init__.py` before `logs.py` exists causes cascade import failures — create `logs.py` first.
- **`main_logs()` return type**: must be `-> int:` (not `None`) to match all other `main_*()` functions (`messages.py:11`, `history.py:12`). Return `0` for success, `1` for errors, `1` when no subcommand given with `parser.print_help()`.
- **`cli_args.py` exact signatures** (at `scripts/little_loops/cli_args.py`, NOT inside `cli/`):
  - `add_dry_run_arg(parser)` — line 15; adds `--dry-run`/`-n` with `action="store_true"`
  - `add_config_arg(parser)` — line 35; adds `--config`/`-C` with `type=Path`; call on **top-level parser** (not per-subparser), as done in `history.py:183`
  - `add_quiet_arg(parser)` — line 167; adds `--quiet`/`-q` with `action="store_true"`
- **Logger constructor**: `Logger(verbose=True, use_color=None, colors=None)` at `logger.py:38`. Instantiate as `Logger(verbose=args.verbose)` where `--verbose`/`-v` is `store_true` (pattern from `messages.py:133`).
- **Agent session exclusion in `user_messages.py`**: `extract_user_messages()` at line 411 uses an `include_agent_sessions` bool parameter (default `False`) to filter out `agent-*.jsonl` files — alternative to the manual `startswith("agent-")` guard in `session_log.py:78`.
- **`history.py` subcommand dispatch pattern**: `if not args.command: parser.print_help(); return 1` then `if args.command == "discover": ...` etc. All domain imports deferred inside function body.
- **pyproject.toml format confirmed** (lines 48–63): all entries use `ll-<name> = "little_loops.cli:main_<name>"` targeting the `cli/__init__.py` re-export layer (not the module directly).

## Acceptance Criteria

- [ ] `ll-logs discover` lists all Claude projects on the machine with ll activity
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

## Verification Notes

**Verdict**: NEEDS_UPDATE — `ll-generate-schemas` was added to the codebase after this issue was refined, shifting key line references:

- `scripts/pyproject.toml`: `ll-generate-schemas` now at line 62; `mcp-call` shifted to line **63** (not 62 as stated). Add `ll-logs` entry after `ll-generate-schemas` at line 62.
- `scripts/little_loops/cli/__init__.py`: now imports `main_generate_schemas` from `cli.schemas` (line 29) and includes it in `__all__`. The import block ends at line 36 and `__all__` at 56 (confirmed). Alphabetical insertion point for `main_logs`: after `from little_loops.cli.issues import main_issues` (between `issues` and `loop`).
- Core feature not yet implemented — `logs.py` does not exist ✓
- All other claims about reusable helpers accurate (user_messages.py:374, session_log.py:62, cli_args.py functions)

— Verified 2026-04-11

## Blocks

- FEAT-1003
- FEAT-1005
- FEAT-1006

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:confidence-check` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5bfe55d-50b8-488b-a0ce-e714fb6c9ff8.jsonl`
- `/ll:wire-issue` - 2026-04-08T21:33:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cc6f86f-01df-44f7-81d6-a9508a1aad5a.jsonl`
- `/ll:refine-issue` - 2026-04-08T21:29:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91b646f5-8dba-4b71-a137-52289ce2376f.jsonl`
- `/ll:format-issue` - 2026-04-08T21:25:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5ce561f-0842-4a37-9ea8-b3dd59ec9887.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4567c5b-d32d-41b7-b9a6-b02cb4590a4e.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
