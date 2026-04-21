---
captured_at: "2026-04-21T16:19:58Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — import and export `main_action`
- `scripts/pyproject.toml` — add `ll-action` to `[project.scripts]`

### New Files
- `scripts/little_loops/cli/action.py` — `main_action()` + three subcommand handlers

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` called by `invoke`
- `.claude-plugin/plugin.json` — read by `capabilities` and `list` for skill metadata

### Tests
- `scripts/tests/test_action.py` — new test file covering all three subcommands

### Documentation
- `scripts/little_loops/cli/__init__.py` module docstring — add `ll-action` entry

### Configuration
- N/A

## Implementation Steps

1. Create `scripts/little_loops/cli/action.py` with `main_action()` and three subcommand handlers
2. Implement `invoke`: wrap `run_claude_command()` with stream-json / json output modes
3. Implement `capabilities`: probe `claude` binary, read plugin manifest
4. Implement `list`: read plugin manifest skills section
5. Update `scripts/little_loops/cli/__init__.py` — import/export `main_action`, update module docstring
6. Add `ll-action` entry to `scripts/pyproject.toml` `[project.scripts]`
7. Write `scripts/tests/test_action.py` covering all three subcommands

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

- **Scope**: One new CLI module (~150 lines) + two small edits to existing files
- **Risk**: Low — additive only; no changes to existing subprocess, FSM, or worker logic
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

**Status**: Open
**Assignee**: Unassigned

---

## Session Log
- `/ll:capture-issue` - 2026-04-21T16:19:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73395bc0-9919-4b5b-bdc2-9c26c0d59d7f.jsonl`
