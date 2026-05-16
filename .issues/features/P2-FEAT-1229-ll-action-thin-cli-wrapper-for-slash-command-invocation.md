---
captured_at: "2026-04-21T16:19:58Z"
completed_at: "2026-04-21T17:16:34Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
---

# FEAT-1229: ll-action Thin CLI Wrapper for Slash-Command Invocation

## Summary

Add `ll-action`, a thin CLI wrapper that exposes `DefaultActionRunner`'s slash-command path as a standalone subprocess command with JSON-structured output. This makes individual ll skills invocable from scripts, dashboards, and cron jobs without embedding FSM loop machinery.

## Use Case

**Who**: A developer using the little-loops Vite dashboard (or a shell script) who wants to trigger a single skill (e.g., `refine-issue`, `confidence-check`) on demand, outside of a running loop.

**Context**: The dashboard's action UI needs to fire individual skills and stream their output through SSE. Today there's no way to invoke a skill as a one-shot command; the only options are `ll-auto` (full backlog) or `ll-loop` (FSM-driven). A dedicated `ll-action invoke` fills that gap.

**Goal**: Fire `ll-action invoke refine-issue --args P2-ENH-1229` from the dashboard (or terminal) and receive streaming JSON events that the frontend can relay via SSE — same parser, zero new frontend code.

**Outcome**: The dashboard can surface a "Run action" button for any skill without implementing new subprocess logic or a new event format.

## Current Behavior

- No standalone CLI entry point exists for invoking a single skill
- `DefaultActionRunner` is embedded inside the FSM executor — not accessible as a one-shot command
- The dashboard has no way to fire an individual skill and stream structured output

## Expected Behavior

`ll-action` supports three subcommands:

```bash
ll-action invoke <skill> [--args <arg>...] [--timeout <seconds>] [--output json|stream-json]
ll-action capabilities [--output json]
ll-action list [--output json]
```

### `invoke` (default `--output stream-json`)

Emits newline-delimited JSON events to stdout:
```json
{"event":"action_start","ts":"...","skill":"refine-issue","args":["ENH-353"]}
{"event":"action_output","ts":"...","line":"Analyzing ENH-353..."}
{"event":"action_complete","ts":"...","exit_code":0,"duration_ms":45230}
```

With `--output json`: runs to completion, then prints a single JSON object:
```json
{"exit_code":0,"duration_ms":45230,"output":"...","error":null}
```

### `capabilities`

No Claude invocation. Probes `which claude`, `claude --version`, and reads the plugin manifest:
```json
{"available":true,"version":"1.0.3","supported_skills":["refine-issue","confidence-check",...]}
```

### `list`

Returns skill names and descriptions from the plugin manifest:
```json
[{"name":"refine-issue","description":"..."},...]
```

## Motivation

The Vite plugin dashboard (FEAT-363) needs an "actions" panel where users can trigger individual skills on demand. Without `ll-action`, the dashboard would need its own subprocess management — duplicating all the hard-won fixes from `run_claude_command()` (BUG-618 deadlock, BUG-946 deferred tools, worktree env handling).

`ll-action` also benefits shell scripting and cron use cases where a single skill result is needed without a full FSM loop.

## Proposed Solution

### New file: `scripts/little_loops/cli/action.py`

- `main_action()` entry point with argparse subcommand dispatch
- `invoke`: calls `run_claude_command(f"/ll:{skill} {' '.join(args)}", timeout=timeout)` from `subprocess_utils`; wraps stdout lines into `action_output` JSON events; emits `action_start` before and `action_complete` after
- `capabilities`: `shutil.which("claude")`, `subprocess.run(["claude", "--version"])`, reads plugin manifest skill list
- `list`: reads plugin manifest, returns skills with names and descriptions

### Changes to existing files

**`scripts/little_loops/cli/__init__.py`**
- Import and export `main_action`

**`scripts/pyproject.toml`**
- Add `ll-action = "little_loops.cli:main_action"` to `[project.scripts]`

### Key design decisions

1. **Reuse `run_claude_command()`** from `subprocess_utils` — no new subprocess logic, all existing fixes apply automatically
2. **stream-json by default** — event shape matches FSM executor so the dashboard SSE layer reuses its existing parser
3. **No concurrency in ll-action** — the Vite plugin owns the queue (max 1 concurrent per FEAT-363); `ll-action` is fire-and-forget, killable via PID on cancel

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`run_claude_command()` output pre-processing** (`subprocess_utils.py:190-212`): The function internally parses Claude's stream-json format. The `stream_callback` receives **already-extracted text** — it extracts `text` blocks from `assistant` events, skips `system`/`tool_use`/`result` events entirely, and falls through non-JSON lines as raw text. The `invoke` subcommand's `action_output` event wrapping therefore just wraps each `stream_callback` line; it does not need to parse JSON itself.

**`plugin.json` skills is a directory pointer, not a flat list** (`.claude-plugin/plugin.json:20`): The manifest stores `"skills": ["./skills"]` — a relative path to the `skills/` directory at the project root. There is no inline skill list with names/descriptions. The `list` and `capabilities` subcommands must enumerate `skills/*/SKILL.md` files to discover skills. Each skill's **name = directory name** (e.g., `refine-issue`, `confidence-check`). The **description** comes from the YAML frontmatter `description` field in `SKILL.md`. There is no `name` key in the frontmatter — only `description`, `model`, and `allowed-tools`. No existing Python code in `scripts/little_loops/` reads `plugin.json` at runtime; path resolution should use `skill_expander._find_plugin_root()` (`skill_expander.py:22-30`) which respects `CLAUDE_PLUGIN_ROOT` env var and resolves to repo root; skills dir = `plugin_root / "skills"`.

**`print_json()` utility** (`cli/output.py:102-104`): For `--output json` mode, use `print_json(data)` from `little_loops.cli.output` rather than raw `print(json.dumps(..., indent=2))`. Already used throughout `ll-issues` subcommands.

**`DefaultActionRunner` invoke pattern** (`fsm/runners.py:86-123`): The runner's slash-command branch calls `run_claude_command(command=action, timeout=timeout, stream_callback=_stream_cb, on_process_start=..., on_process_end=...)` with no `working_dir` or `idle_timeout`. `ll-action invoke` should follow the same signature — do not forward `working_dir` or `idle_timeout` to `run_claude_command()`.

**Subcommand dispatch pattern**: Follow `cli/loop/__init__.py` (subparsers pattern, lines 93-392) for the three-subcommand dispatch, not `auto.py` (which is flat/no subcommands). Imports inside `main_action()` body are deferred (see `loop/__init__.py:21-26`) to avoid circular imports.

**Test pattern for CLI entry points** (`test_cli.py:1561-1566`): All existing CLI entry-point tests use `patch.object(sys, "argv", ["ll-action", ...])` + direct `main_action()` call. No `CliRunner`, no subprocess invocation.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — import and export `main_action`
- `scripts/pyproject.toml` — add `ll-action` to `[project.scripts]`

### New Files
- `scripts/little_loops/cli/action.py` — `main_action()` + three subcommand handlers

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:62` — `run_claude_command()` called by `invoke`; `stream_callback` receives pre-extracted text lines (assistant events only)
- `.claude-plugin/plugin.json:20` — `"skills": ["./skills"]` directory pointer; enumerate `skills/*/SKILL.md` for skill names/descriptions
- `skills/*/SKILL.md` — YAML frontmatter with `description` field; directory name = skill name

### Similar Patterns
- `scripts/little_loops/cli/auto.py:21` — `main_auto()` entry point structure (argparse, returns `int`)
- `scripts/little_loops/cli/loop/__init__.py:93-392` — `main_loop()` subcommand dispatch pattern to mirror for three-subcommand dispatch
- `scripts/little_loops/fsm/runners.py:86-123` — `DefaultActionRunner.run()` slash-command branch: exact pattern for calling `run_claude_command()` with `stream_callback` + process lifecycle callbacks
- `scripts/little_loops/mcp_call.py:315` — closest analog: thin CLI wrapper with JSON-to-stdout + `sys.exit()` pattern

### Tests
- `scripts/tests/test_action.py` — new test file covering all three subcommands
- `scripts/tests/test_subprocess_utils.py` — mock patterns to follow: `patch("subprocess.Popen", ...)` + `_patch_selector_cm(mock_selector)` fixture
- `scripts/tests/test_cli_e2e.py` — integration test pattern (marked `pytest.mark.integration`); not required for `test_action.py`
- `scripts/tests/test_cli.py:1561-1566` — entry-point test pattern: `patch.object(sys, "argv", [...])` + direct function call

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py:79` — asserts `"15 CLI tools"` in `README.md`; update assertion to `"16 CLI tools"` after README change [Agent 2 finding]
- `scripts/tests/test_create_extension_wiring.py:57` — asserts `"Authorize all 14"` in `skills/configure/areas.md`; update to `"Authorize all 15"` after areas.md change [Agent 2 finding]

### Documentation
- `scripts/little_loops/cli/__init__.py` module docstring — add `ll-action` entry

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:103-118` — CLI Tools bullet list; add `ll-action` bullet [Agent 2 finding]
- `README.md:90` — `"15 CLI tools"` count string; increment to `"16 CLI tools"` [Agent 2 finding]
- `README.md:239-466` — per-tool `### ll-*` sections; add `### ll-action` section with usage examples [Agent 2 finding]
- `commands/help.md:217-233` — CLI TOOLS block printed by `/ll:help`; add `ll-action` line [Agent 2 finding]
- `docs/reference/CLI.md` — full CLI reference; add `### ll-action` section with flags, subcommands, examples [Agent 2 finding]
- `CONTRIBUTING.md:183-196` — `scripts/little_loops/cli/` directory tree; add `action.py` entry [Agent 2 finding]

### Registration / Manifest

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md:426-444` — permissions block written during `ll init`; add `"Bash(ll-action:*)"` entry [Agent 2 finding]
- `skills/init/SKILL.md:489-503` — update-CLAUDE.md boilerplate block; add `ll-action` bullet [Agent 2 finding]
- `skills/init/SKILL.md:515-529` — create-CLAUDE.md boilerplate block; add `ll-action` bullet [Agent 2 finding]
- `skills/configure/areas.md:823` — permission area description string; increment `"14"` → `"15"` and append `ll-action` to tool list [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Create `scripts/little_loops/cli/action.py` with `main_action()` — mirror `loop/__init__.py:13-393` subcommand dispatch structure with `argparse` + `add_subparsers(dest="command")`
2. Implement `invoke`: call `run_claude_command(command=f"/ll:{skill} {' '.join(args)}", timeout=timeout, stream_callback=_stream_cb)` following `runners.py:86-123`; wrap each `stream_callback` line into `action_output` NDJSON event (callback receives pre-parsed text, not raw JSON)
3. Implement `capabilities`: `shutil.which("claude")`, `subprocess.run(["claude", "--version"])`, then glob `Path.cwd() / "skills" / "*" / "SKILL.md"` to collect supported skill names (directory names)
4. Implement `list`: glob `Path.cwd() / "skills" / "*" / "SKILL.md"`, parse YAML frontmatter `description` field from each; return `[{"name": dir_name, "description": description}]`
5. Update `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.action import main_action` (after line 37), add `"main_action"` to `__all__`, add `ll-action` line to module docstring
6. Add `ll-action = "little_loops.cli:main_action"` to `scripts/pyproject.toml` `[project.scripts]` (after line 64)
7. Write `scripts/tests/test_action.py` — use `patch.object(sys, "argv", [...])` + direct `main_action()` call pattern from `test_cli.py:1561`; mock `run_claude_command` and filesystem for `capabilities`/`list`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `.claude/CLAUDE.md:103-118` — add `ll-action` bullet to CLI Tools section
9. Update `README.md:90` — change `"15 CLI tools"` → `"16 CLI tools"`; add `### ll-action` section in the per-tool listing (lines 239–466)
10. Update `commands/help.md:217-233` — add `ll-action` line to the CLI TOOLS block shown by `/ll:help`
11. Update `docs/reference/CLI.md` — add `### ll-action` section with subcommands, flags, and usage examples
12. Update `CONTRIBUTING.md:183-196` — add `action.py` to the `scripts/little_loops/cli/` directory tree
13. Update `skills/init/SKILL.md` — add `"Bash(ll-action:*)"` to the permissions block (lines 426–444); add `ll-action` bullet to both the update-CLAUDE.md (lines 489–503) and create-CLAUDE.md (lines 515–529) boilerplate blocks
14. Update `skills/configure/areas.md:823` — increment `"14"` → `"15"` and append `ll-action` to the tool list in the description string
15. Update `scripts/tests/test_create_extension_wiring.py:79` — change assertion from `"15 CLI tools"` to `"16 CLI tools"`; update line 57 from `"Authorize all 14"` to `"Authorize all 15"`

## API/Interface

```python
# scripts/little_loops/cli/action.py

def main_action() -> None:
    """Entry point for ll-action CLI."""
```

**stream-json event shapes:**
```python
# action_start
{"event": "action_start", "ts": str, "skill": str, "args": list[str]}

# action_output (one per stdout line from claude)
{"event": "action_output", "ts": str, "line": str}

# action_complete
{"event": "action_complete", "ts": str, "exit_code": int, "duration_ms": int}
```

**json output shape (`invoke --output json`):**
```python
{"exit_code": int, "duration_ms": int, "output": str, "error": str | None}
```

**capabilities output:**
```python
{"available": bool, "version": str, "supported_skills": list[str]}
```

**list output:**
```python
[{"name": str, "description": str}]
```

## Acceptance Criteria

- [ ] `ll-action invoke refine-issue --args P2-ENH-1229` streams `action_start`, `action_output` lines, `action_complete` to stdout as NDJSON
- [ ] `ll-action invoke <skill> --output json` runs to completion and prints a single JSON object
- [ ] `ll-action capabilities` returns valid JSON without invoking Claude
- [ ] `ll-action list` returns skill list from plugin manifest without invoking Claude
- [ ] `--timeout` is forwarded to `run_claude_command()` (default 300s)
- [ ] Console script `ll-action` is registered in `pyproject.toml` and callable after install
- [ ] All three subcommands have test coverage in `scripts/tests/test_action.py`

## Impact

- **Priority**: P2 — unblocks dashboard actions panel (FEAT-363)
- **Effort**: Small — one new CLI module (~150 lines) + two small edits to existing files
- **Risk**: Low — additive only; no changes to existing subprocess, FSM, or worker logic
- **Breaking Change**: No
- **Enables**: Dashboard "actions" panel (FEAT-363), cron-based skill invocation

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/subprocess_utils.py` | Source of `run_claude_command()` being reused |
| `scripts/little_loops/fsm/runners.py` | `DefaultActionRunner` pattern being mirrored |
| `.claude-plugin/plugin.json` | Manifest read by `capabilities` and `list` |

## Labels

`feature`, `cli`, `dashboard`, `automation`

## Status

**Status**: Completed
**Assignee**: Unassigned

## Resolution

Implemented `ll-action` as `scripts/little_loops/cli/action.py` with three subcommands:
- `invoke`: calls `run_claude_command()` and wraps output as NDJSON `action_start`/`action_output`/`action_complete` events (stream-json mode) or collects into a single JSON object (json mode)
- `capabilities`: probes `claude` availability via `shutil.which` + `subprocess.run(["claude", "--version"])`, enumerates `skills/*/SKILL.md` for skill names
- `list`: enumerates `skills/*/SKILL.md` and parses YAML frontmatter descriptions

Registered `ll-action = "little_loops.cli:main_action"` in `pyproject.toml`. All acceptance criteria met; 57 tests pass including full wiring suite.

---

## Session Log
- `/ll:manage-issue` - 2026-04-21T17:16:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current-session.jsonl`
- `/ll:ready-issue` - 2026-04-21T17:05:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de0addfd-b5f2-407c-a851-0927b44fecc6.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/822c48e1-ef44-4af9-8758-ad90ec148023.jsonl`
- `/ll:wire-issue` - 2026-04-21T16:47:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa148307-a740-4cfb-a0a0-18cc0f7967a8.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:34:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24aea90c-410b-44e1-8768-f887bdf017e4.jsonl`
- `/ll:format-issue` - 2026-04-21T16:23:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/475826cc-7152-4238-88ba-f765d2ba39dd.jsonl`
- `/ll:capture-issue` - 2026-04-21T16:19:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73395bc0-9919-4b5b-bdc2-9c26c0d59d7f.jsonl`
