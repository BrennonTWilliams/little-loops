---
id: FEAT-1001
type: FEAT
priority: P4
status: backlog
title: Add log discovery and extraction for ll-loop and ll-commands
discovered_date: 2026-04-08
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 71
---

# FEAT-1001: Add log discovery and extraction for ll-loop and ll-commands

## Summary

Identify system-level Claude log locations on this machine, then extract and save logs from running `ll-loop`, `/ll:` skills, and other ll-commands across all projects into a new `logs/` directory for analysis.

## Current Behavior

Claude Code writes session logs to `~/.claude/projects/<encoded-path>/*.jsonl`, but there is no tool or workflow for:
- Discovering which projects on this machine are running any ll- CLI tool
- Extracting ll-relevant entries (loop state transitions, skill invocations, CLI command invocations, results) from raw JSONL
- Aggregating logs from multiple projects into a single location for cross-project analysis

## Expected Behavior

A `logs/` directory (or CLI tool) that:
1. Discovers all Claude project log directories on the machine (`~/.claude/projects/*/`)
2. Filters sessions that contain any ll- CLI invocation (`ll-loop`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-messages`, `ll-history`, `ll-deps`, `ll-sync`, `ll-issues`, `ll-workflows`, `ll-gitignore`, `ll-verify-docs`, `ll-check-links`) or `/ll:` skill activity
3. Extracts relevant entries and writes them to `logs/<project>/<session>.log` (or structured JSONL)
4. Optionally tails active sessions for live ll-loop monitoring

## Motivation

Debugging ll-loop execution, skill failures, and command behavior across projects requires manually hunting through `~/.claude/projects/` JSONL files. A dedicated log extraction workflow would dramatically speed up analysis of FSM state transitions, identify cross-project patterns, and support the `ll-analyze-loop` and `ll-analyze-history` commands with richer source data.

## Proposed Solution

Create a new `ll-logs` CLI tool at `scripts/little_loops/cli/logs.py` (following the codebase pattern: all CLI tools live in `cli/`) that discovers Claude log directories, filters ll-relevant JSONL entries, and writes them to a structured `logs/` directory. Follows patterns established by `user_messages.py` and `session_log.py` for JSONL parsing and project path decoding. Expose as `ll-logs` via `little_loops.cli:main_logs` entry point in `pyproject.toml`.

## Use Case

Developer runs `ll-loop outer-loop-eval` on two separate projects. When a loop behaves unexpectedly, they want to quickly pull the relevant log entries from both projects into one place, correlate the FSM transitions, and understand what context was passed at each state.

## Implementation Steps

1. **Create `scripts/little_loops/cli/logs.py`** with `main_logs()` entry point:
   - Implement `discover_all_projects()` helper: `(Path.home() / ".claude" / "projects").iterdir()` — decode each dir name back to a path via `.replace("-", "/")` (inverse of `user_messages.py:371`'s `replace("/", "-")`); no existing reusable function for this
   - Reuse `get_project_folder()` from `user_messages.py:354` for single-project lookup
   - Use `session_log.py:62`'s `glob("*.jsonl")` + `agent-*.jsonl` exclusion pattern for per-project JSONL enumeration
   - Stream-filter JSONL using pattern from `user_messages.py:436`; detect ll-relevance via: (a) `queue-operation` records containing any `ll-` prefix command, (b) `type: "user"` records with `<command-name>/ll:` pattern (see `user_messages.py:189`), (c) `type: "assistant"` Bash tool-use blocks with `ll-` invocations
   - Structure output as `logs/<project-slug>/<session-id>.jsonl`
   - Add argparse subcommands (`discover`, `extract`, `tail`) following pattern in `cli/history.py:12`

2. **Register entry point**:
   - Add `from little_loops.cli.logs import main_logs` to `cli/__init__.py:20-36`
   - Add `"main_logs"` to `__all__` at `cli/__init__.py:38-56`
   - Add `ll-logs = "little_loops.cli:main_logs"` to `pyproject.toml:48-63`

3. **Write tests in `scripts/tests/test_ll_logs.py`**:
   - Patch `get_project_folder` and `Path.home()` for discovery isolation (see `test_session_log.py:20-53`)
   - Use `tmp_path` with real JSONL fixture data for extraction tests
   - Test `main_logs()` via `patch("sys.argv", ["ll-logs", "discover"])` (see `test_cli_sync.py:14-18`)

4. **Update documentation**:
   - Add `ll-logs` to `CLAUDE.md` CLI Tools section (after `ll-gitignore` entry)
   - Add `ll-logs` to `docs/reference/API.md` and `docs/reference/CLI.md`

5. **Verify**: `python -m pytest scripts/tests/test_ll_logs.py -v && ll-logs discover`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Update `skills/init/SKILL.md`** — add `"Bash(ll-logs:*)"` to the canonical `permissions.allow` list (lines 428–443) and add `ll-logs` description to both CLAUDE.md boilerplate blocks (lines 510–522 and 539–546)
7. **Update `skills/configure/areas.md:793`** — increment count and add `ll-logs` to the "Authorize all N ll- CLI tools" enumerated list
8. **Update `README.md`** — change `13 CLI tools` → `14 CLI tools` (line 90); add `### ll-logs` section after `ll-gitignore` section
9. **Update `commands/help.md:208-221`** — add `ll-logs` entry to CLI TOOLS block
10. **Update `docs/reference/CLI.md`** — add `### ll-logs` section after `ll-messages` section with subcommands and flag table
11. **Update `docs/ARCHITECTURE.md`** — add `├── logs.py` to the `scripts/little_loops/cli/` directory tree (~line 180)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — new CLI tool (create; follows pattern of `cli/messages.py`)
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.logs import main_logs` import and `"main_logs"` to `__all__`
- `scripts/pyproject.toml:48-63` — add `ll-logs = "little_loops.cli:main_logs"` to `[project.scripts]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:20-56` — re-exports all `main_*` functions; add `main_logs` here
- `scripts/pyproject.toml:48-63` — `[project.scripts]` section registering all `ll-*` entry points

### Similar Patterns
- `scripts/little_loops/user_messages.py:354` — `get_project_folder(cwd)`: encodes CWD path to `~/.claude/projects/<encoded>` using `str(path.resolve()).replace("/", "-")`; returns `None` if not found
- `scripts/little_loops/session_log.py:62` — `get_current_session_jsonl()`: `project_folder.glob("*.jsonl")` excluding `agent-*.jsonl`, picks most-recent by `st_mtime`
- `scripts/little_loops/user_messages.py:436` — JSONL stream-parsing pattern: `json.loads(line)` in try/except, `_parse_user_record()` for user messages, `_parse_command_record()` for assistant tool-use blocks
- `scripts/little_loops/user_messages.py:189` — `--skill` filter: detects `/ll:` invocations via `<command-name>/ll:SKILL-NAME</command-name>` in `message.content`
- `scripts/little_loops/cli/messages.py:11` — `main_messages()`: flat argparse CLI structure with `Logger(verbose=args.verbose)`, deferred imports, `return int` exit code pattern
- `scripts/little_loops/cli/history.py:12` — `main_history()`: multi-subcommand argparse (`add_subparsers`, `set_defaults`, guard `if not args.command`)
- **NOTE**: `ll-history` does NOT parse JSONL — it reads `.issues/completed/` markdown files only. The JSONL-parsing pattern to follow is `user_messages.py` + `session_log.py`.

### Tests
- `scripts/tests/test_ll_logs.py` — new test file to create; model after `test_session_log.py` (patch `get_project_folder`, use `tmp_path`), `test_cli_messages_save.py` (test save helper with `MagicMock` records), and `test_cli_sync.py` (test `main_logs()` via `patch("sys.argv", [...])`)
- `scripts/tests/test_session_log.py` — existing tests showing `get_project_folder` patching pattern
- `scripts/tests/test_cli_messages_save.py` — existing tests showing save-helper pattern
- `scripts/tests/test_user_messages.py` — existing tests for JSONL parsing functions; `_write_jsonl()` helper at line 109 is the canonical fixture-writing pattern for extraction tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_cli.py:74-93` — canonical subcommand `main_*()` test pattern; `test_ll_logs.py` should model `ll-logs discover`/`extract`/`tail` tests after this (subparser guard: no-command returns 1)
- `scripts/tests/test_cli.py:769-775` — canonical `patch.object(sys, "argv", [...])` + deferred import pattern for `main_*` integration tests
- **Sequencing risk**: adding `main_logs` to `cli/__init__.py` before `logs.py` exists will cause cascade import failures across `test_cli.py`, `test_issue_history_cli.py`, `test_next_issues.py`, `test_next_action.py`, `test_ll_loop_state.py`, `test_create_loop.py`, `test_create_eval_from_issues.py`, `test_cli_e2e.py` — create `logs.py` first, update `cli/__init__.py` second

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CLAUDE.md` — add `ll-logs` to CLI Tools section
- `docs/reference/API.md` — add `ll-logs` command reference
- `docs/reference/CLI.md` — add `### ll-logs` section (after `ll-messages` section ~line 822); follows pattern of other tool sections with flag tables
- `docs/ARCHITECTURE.md` — add `├── logs.py` to `cli/` directory tree (~line 180 in `scripts/little_loops/cli/` listing)
- `README.md:90` — update `13 CLI tools` prose count to `14`; add `### ll-logs` section (~line 431, after `ll-gitignore` section) following same pattern
- `commands/help.md:208-221` — add `ll-logs` to CLI TOOLS block (currently ends at `ll-check-links`)

### Configuration
- `scripts/pyproject.toml:48-63` — `[project.scripts]` CLI entry point registration

### Skills Registration

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md:428-443` — add `"Bash(ll-logs:*)"` to canonical `permissions.allow` list written to `.claude/settings.local.json` during init
- `skills/init/SKILL.md:510-522` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (file-exists case)
- `skills/init/SKILL.md:539-546` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (create-new case)
- `skills/configure/areas.md:793` — update count (`12` → `13`) and enumerated list in the "Authorize all N ll- CLI tools" description string

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **JSONL record fields** (from live log inspection): `type`, `uuid`, `parentUuid`, `timestamp` (ISO 8601 with `Z`), `sessionId`, `cwd`, `gitBranch`, `isSidechain`, `userType`, `entrypoint`, `version`. Skill invocations appear in `type: "user"` records as `<command-name>/ll:SKILL-NAME</command-name>` embedded in `message.content`. CLI tools appear in `queue-operation` records as `content: "/ll-loop run <name>"`. 
- **Multi-project decode**: No existing helper. Decode: `dir.name.replace("-", "/")` — every `-` that was a `/`; leading `-` becomes leading `/`. Forward encode at `user_messages.py:371`.
- **Agent subdir structure**: Some projects have UUID subdirs under `~/.claude/projects/<encoded>/` (e.g., `5aef.../subagents/agent-*.jsonl`). The `glob("*.jsonl")` at `user_messages.py:411` only finds top-level JSONL files; recurse if agent-session coverage is needed.
- **Shared `Logger`**: `scripts/little_loops/logger.py:17` — `Logger(verbose=args.verbose)`, use `logger.error()` for stderr. Use `Logger(use_color=False)` in tests.
- **Shared arg factories**: `scripts/little_loops/cli_args.py` — `add_config_arg()`, `add_dry_run_arg()`, `add_quiet_arg()` available for reuse.

## API/Interface

```bash
# New CLI or subcommand
ll-logs discover                  # List all projects with ll activity
ll-logs extract --project <slug>  # Extract logs for one project
ll-logs extract --all             # Extract all projects to logs/
ll-logs tail --loop outer-loop-eval  # Live tail active loop sessions
ll-logs extract --cmd ll-history     # Extract logs for a specific ll- CLI tool
```

Output structure:
```
logs/
  index.md
  little-loops/
    e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl
    ...
  my-other-project/
    ...
```

## Acceptance Criteria

- [ ] `logs/` directory is populated with filtered entries from at least the current project
- [ ] Entries are correctly attributed to the specific ll- CLI tool or loop that produced them
- [ ] Cross-project discovery works for at least 2 projects on the machine
- [ ] `logs/index.md` provides a readable summary of what was extracted and when

## Impact

- **Priority**: P4 - utility tooling enhancement; valuable for debugging but not blocking core workflows
- **Effort**: Medium - new `ll-logs` CLI tool with JSONL parsing and multi-project discovery
- **Risk**: Low - additive new CLI tool; no changes to existing code paths
- **Breaking Change**: No

## Labels

`feature`, `cli`, `logging`, `analysis`, `captured`

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Architecture | ll-loop FSM internals and log structure |
| [docs/reference/API.md](../../docs/reference/API.md) | Architecture | CLI tool API reference |

## Session Log
- `/ll:confidence-check` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b07b1c-a2bc-4b42-ad8d-3bb135de155e.jsonl`
- `/ll:wire-issue` - 2026-04-08T21:19:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27202b3b-3157-49a8-8dc9-cd7f6690b42f.jsonl`
- `/ll:refine-issue` - 2026-04-08T21:13:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a569a938-713f-4245-a2c8-b4fe32d2801d.jsonl`
- `/ll:format-issue` - 2026-04-08T21:08:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97d18de7-fd1d-462e-ba82-62e58ba8fba0.jsonl`
- `/ll:capture-issue` - 2026-04-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4567c5b-d32d-41b7-b9a6-b02cb4590a4e.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-08
- **Reason**: Issue too large for single session (score: 9/11)

### Decomposed Into
- FEAT-1002: Implement ll-logs CLI core tool (logs.py + entry point)
- FEAT-1003: Write test suite for ll-logs CLI tool
- FEAT-1004: Documentation and wiring updates for ll-logs

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
