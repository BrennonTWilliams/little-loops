---
id: FEAT-1003
type: FEAT
priority: P4
status: backlog
title: Write test suite for ll-logs CLI tool
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 78
outcome_confidence: 97
blocked_by: [ENH-753, FEAT-1002]
---

# FEAT-1003: Write test suite for ll-logs CLI tool

## Summary

Create `scripts/tests/test_ll_logs.py` with comprehensive tests for the `ll-logs` CLI tool. Tests cover discovery isolation, JSONL extraction with real fixture data, and `main_logs()` integration via patched `sys.argv`.

## Parent Issue
Decomposed from FEAT-1001: Add log discovery and extraction for ll-loop and ll-commands

## Prerequisites

FEAT-1002 must be implemented first (logs.py must exist before tests can import it).

ENH-753 must be completed before this test suite is written. FEAT-1003's session log
fixtures reference skill invocation strings; after ENH-753 renames `/ll:confidence-check`
→ `/ll:score-confidence`, any fixture containing that string must use the new name.
Writing tests before ENH-753 lands guarantees stale fixture data. See `blocked_by:
[ENH-753, FEAT-1002]` in frontmatter.

## Current Behavior

No test suite exists for the `ll-logs` CLI tool. The `logs.py` module introduced by FEAT-1002 will have zero test coverage once implemented, leaving discovery isolation, JSONL extraction, and subcommand routing unverified.

## Expected Behavior

`scripts/tests/test_ll_logs.py` exists with passing tests covering:
- Discovery isolation (no access to real `~/.claude/projects/`)
- JSONL extraction with real fixture data via `tmp_path`
- `main_logs()` CLI integration via patched `sys.argv`
- Subcommand guard: no-subcommand case returns exit code 1

Running `python -m pytest scripts/tests/test_ll_logs.py -v` reports all tests passing.

## Use Case

A developer implements FEAT-1002 (the `ll-logs` CLI) and wants to verify correctness before merging. They run `python -m pytest scripts/tests/test_ll_logs.py -v` and get immediate confidence that discovery isolation, JSONL extraction filtering, and subcommand routing all work correctly — without touching real `~/.claude` data.

## Motivation

FEAT-1002 introduces `ll-logs`, a new CLI with discovery, extraction, and tail subcommands. Without a test suite, regressions would be caught only at runtime. This test file ensures the tool remains correct as the logs infrastructure evolves and establishes the canonical pattern for future log-related tests.

## Implementation Steps

1. **Create `scripts/tests/test_ll_logs.py`**:
   - Patch `get_project_folder` and `Path.home()` for discovery isolation (see `test_session_log.py:20-53`)
   - Use `tmp_path` with real JSONL fixture data for extraction tests
   - Test `main_logs()` via `patch("sys.argv", ["ll-logs", "discover"])` (see `test_cli_sync.py:14-18`)
   - Model subcommand tests after `test_issue_history_cli.py:74-93` (canonical subcommand `main_*()` test pattern)
   - Test no-command case returns exit code 1 (subparser guard)
   - Test `discover`, `extract`, `tail` subcommands

2. **Use canonical fixture-writing pattern** from `test_user_messages.py:109` (`_write_jsonl()` helper) to create JSONL test fixtures containing:
   - `queue-operation` records with `ll-` prefix commands
   - `type: "user"` records with `<command-name>/ll:SKILL-NAME</command-name>` patterns
   - `type: "assistant"` Bash tool-use blocks with `ll-` invocations
   - Non-ll records (to test filtering)

3. **Verify**: `python -m pytest scripts/tests/test_ll_logs.py -v` all pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Before running tests, confirm FEAT-1002 has wired `scripts/little_loops/cli/__init__.py` — `main_logs` must appear in the import block (lines 20-35) and `__all__` list (lines 38-56); the deferred `from little_loops.cli import main_logs` inside `patch.object(sys, "argv", ...)` blocks will raise `ImportError` otherwise
5. Do NOT add new `@pytest.mark` decorators without first declaring them in `scripts/pyproject.toml:111-114`; existing `integration` and `slow` markers are sufficient for this test file

## Integration Map

### Files to Create
- `scripts/tests/test_ll_logs.py` — new test file

### Files to Modify
- N/A — test-only addition; no production files changed

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` — module under test (created by FEAT-1002)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:20-56` — must add `from little_loops.cli.logs import main_logs` and `"main_logs"` to `__all__`; the canonical test import `from little_loops.cli import main_logs` raises `ImportError` until this is wired (FEAT-1002 responsibility, but blocking prerequisite for all `TestMainLogs` tests)

### Similar Patterns (Reference Tests)
- `scripts/tests/test_session_log.py:20-53` — `get_project_folder` patching pattern
- `scripts/tests/test_cli_messages_save.py` — save-helper pattern with `MagicMock` records
- `scripts/tests/test_cli_sync.py:14-18` — `main_*()` via `patch("sys.argv", [...])`
- `scripts/tests/test_user_messages.py:109` — `_write_jsonl()` canonical fixture-writing helper
- `scripts/tests/test_issue_history_cli.py:74-93` — canonical subcommand `main_*()` test pattern
- `scripts/tests/test_cli.py:769-775` — `patch.object(sys, "argv", [...])` + deferred import pattern

### Documentation
- N/A

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:99-114` — pytest config: `--strict-markers` means any new `@pytest.mark.*` decorator must be pre-declared in the `markers` list (lines 111-114); existing markers `integration` and `slow` suffice — no changes needed unless new markers are added. `fail_under = 80` coverage threshold: deploying FEAT-1002 (`logs.py`) without this test file will drop coverage below the floor; both issues should merge together.
- `scripts/tests/conftest.py` — no shared fixtures apply to `test_ll_logs.py`; `temp_project_dir` (line 55-62) creates `.ll/` structure (wrong), `events_file` (line 285-305) is FSM-specific (wrong). Use pytest built-in `tmp_path` directly; define `_write_jsonl()` as an inline instance method (copy from `test_user_messages.py:109-113`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Module path (critical)**: The module under test lives at `scripts/little_loops/cli/logs.py`, not `scripts/little_loops/logs.py`. Import in tests: `from little_loops.cli.logs import main_logs` (direct) or `from little_loops.cli import main_logs` (after FEAT-1002 wires `cli/__init__.py`). Use the deferred import pattern inside `with patch.object(sys, "argv", [...]):` blocks, matching `test_issue_history_cli.py:76-80`.

**Exact patch targets for test isolation**:
- Single-project lookup: `patch("little_loops.cli.logs.get_project_folder", return_value=tmp_path)` — mirrors `test_session_log.py:24`
- Multi-project discovery: build fake `tmp_path / ".claude" / "projects" / "<encoded-slug>"` tree, then `patch("pathlib.Path.home", return_value=tmp_path)` — mirrors `test_cli.py:770`'s `patch("pathlib.Path.cwd", ...)` technique

**Test class structure** (from FEAT-1002 Integration Map + `test_issue_history_cli.py` pattern):
- `class TestArgumentParsing` — argparse unit tests via `_parse_args()` helper, no filesystem; subcommands: `discover`, `extract` (with `--project`, `--all`, `--cmd`), `tail` (with `--loop`)
- `class TestDiscover` — integration tests for `discover` subcommand; `patch("pathlib.Path.home", return_value=tmp_path)` to inject fake project tree
- `class TestExtract` — integration tests for `extract` subcommand; use `_write_jsonl()` helper with real fixture records
- `class TestTail` — integration tests for `tail` subcommand
- `class TestMainLogs` — no-subcommand guard test: `patch.object(sys, "argv", ["ll-logs"])` → `assert result == 1`

**Confirmed JSONL detection signals** (from `user_messages.py:189`, `user_messages.py:573`):
- `type: "user"` records: detect `<command-name>/ll:SKILL-NAME</command-name>` in `message.content`
- `type: "assistant"` Bash tool-use blocks: detect `ll-` prefix in `message.content[n]["input"]["command"]`
- NOTE: `queue-operation` records are referenced in FEAT-1002's spec but not confirmed in existing test fixtures or production code; do not rely on this record type for tests — use the two signals above

**Exact JSONL record shapes for fixtures**:
```python
# ll-relevant user record (skill invocation)
{"type": "user", "uuid": "u1", "sessionId": "sess-abc", "timestamp": "2026-01-10T12:00:00Z",
 "message": {"content": "<command-message>ll:capture-issue</command-message>\n<command-name>/ll:capture-issue</command-name>"}}

# ll-relevant assistant record (Bash tool-use)
{"type": "assistant", "uuid": "u2", "sessionId": "sess-abc", "timestamp": "2026-01-10T12:01:00Z",
 "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ll-loop run my-loop"}}]}}

# Non-ll record (must be excluded by filter)
{"type": "user", "uuid": "u3", "sessionId": "sess-xyz", "timestamp": "2026-01-10T11:00:00Z",
 "message": {"content": "Just a normal user message"}}
```

**`agent-*.jsonl` exclusion**: Add an `agent-session.jsonl` file to the `TestExtract` fixture tree and assert it does NOT appear in extracted output. Pattern: `session_log.py:78` uses `if not f.name.startswith("agent-")`; `user_messages.py:411` uses `include_agent_sessions=False` param.

**`sys.argv` patching style**: Use `patch.object(sys, "argv", [...])` with deferred import (Style A from `test_issue_history_cli.py:76`), not `patch("sys.argv", [...])` (Style B from `test_cli_sync.py:16`) — Style A is the canonical pattern for multi-subcommand CLI tests in this codebase.

**Output assertions**: Use `capsys.readouterr()` for stdout capture (pattern from `test_issue_history_cli.py:95-115`) when testing `discover` output; use `(tmp_path / "logs").iterdir()` filesystem assertions for `extract` output.

## Acceptance Criteria

- [ ] `python -m pytest scripts/tests/test_ll_logs.py -v` passes with no failures
- [ ] Discovery isolation: tests don't access real `~/.claude/projects/`
- [ ] Extraction tests use real JSONL fixture data with `tmp_path`
- [ ] Subcommand guard: `ll-logs` (no subcommand) returns exit code 1
- [ ] `discover`, `extract --all`, `extract --project` subcommands are covered

## Impact

- **Priority**: P4 - utility tooling
- **Effort**: Small-medium - test file only, no production code changes
- **Risk**: Low
- **Breaking Change**: No

## Labels

`feature`, `cli`, `testing`, `logging`

## Session Log
- `/ll:wire-issue` - 2026-04-08T21:47:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36ed4d98-082d-4fb8-b061-42af2b5aa85b.jsonl`
- `/ll:refine-issue` - 2026-04-08T21:42:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22e0ba7a-4320-4721-8390-e8c136127c39.jsonl`
- `/ll:format-issue` - 2026-04-08T21:39:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d03855f-5cb9-451c-afa5-26788c7cded0.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4567c5b-d32d-41b7-b9a6-b02cb4590a4e.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
