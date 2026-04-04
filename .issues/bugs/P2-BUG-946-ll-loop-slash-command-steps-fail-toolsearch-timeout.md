---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# BUG-946: ll-loop slash command steps fail due to ToolSearch timeout with --no-session-persistence

## Summary

When running `ll-loop run <loop> <issue>`, any FSM state that uses a slash command (e.g. `/ll:format_issue`) fails immediately with a ToolSearch timeout error. The step runs for ~1m 27s before giving up with:

> I'm unable to load the tools needed to execute this command. The tool search system isn't returning results. This may be a temporary issue...

## Current Behavior

`DefaultActionRunner.run()` in `runners.py` invokes slash commands using:

```python
cmd = ["claude", "--dangerously-skip-permissions", "--no-session-persistence", "-p", action]
```

The `--no-session-persistence` flag prevents Claude from loading cached plugin/tool context in the subprocess. The `Skill` tool appears as a deferred tool and requires `ToolSearch` to load its schema. `ToolSearch` fails in this context, causing every slash command state to error out after a ~90s timeout.

## Expected Behavior

Slash command steps should execute successfully. The subprocess invocation should use the same flags as `ll-auto`/`ll-parallel` (`--verbose`, `--output-format stream-json`) which work correctly because they use a different initialization path where tool schemas are available from the start.

## Motivation

Any loop with slash command steps (e.g. `refine-to-ready-issue`) is completely broken. Users cannot run `ll-loop` for these workflows at all, making the tool useless for its primary automation use case.

## Steps to Reproduce

1. Create or use a loop YAML with a `slash_command` action (e.g. `/ll:format_issue`)
2. Run `ll-loop run refine-to-ready-issue FEAT-001` in a project with a valid FEAT-001 issue file
3. Observe `format_issue` state fails after ~90s with ToolSearch timeout error

## Root Cause

- **File**: `scripts/little_loops/fsm/runners.py`
- **Anchor**: `DefaultActionRunner.run()` (lines ~77–95)
- **Cause**: The `--no-session-persistence` flag added in BUG-588 (to prevent session accumulation) prevents Claude subprocesses from loading the plugin/tool context needed for deferred tools like `Skill`. When `Skill` needs its schema loaded via `ToolSearch`, `ToolSearch` cannot fetch it in this context. `ll-auto`/`ll-parallel` work because they use `--output-format stream-json` via `subprocess_utils.run_claude_command()`, which uses a different initialization path.

## Proposed Solution

Replace the slash command subprocess invocation in `DefaultActionRunner.run()` with a call to `subprocess_utils.run_claude_command()`:

```python
from little_loops.subprocess_utils import run_claude_command

# In DefaultActionRunner.run():
if is_slash_command:
    start = _now_ms()

    def _stream_cb(line: str, is_stderr: bool) -> None:
        if not is_stderr and on_output_line:
            on_output_line(line)

    completed = run_claude_command(
        command=action,
        timeout=timeout,
        stream_callback=_stream_cb,
    )
    return ActionResult(
        output=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        duration_ms=_now_ms() - start,
    )
else:
    # Shell command path unchanged
    cmd = ["bash", "-c", action]
    ...
```

**Trade-off**: Sessions will accumulate on disk (the BUG-588 concern), but this is preferable to broken tool loading. Session accumulation is a minor operational concern vs. a correctness failure.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` slash command branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` to reuse
- `scripts/little_loops/fsm/executor.py` — uses `DefaultActionRunner`

### Similar Patterns
- `scripts/little_loops/auto.py` — uses `run_claude_command()` (reference for correct invocation)
- `scripts/little_loops/parallel.py` — uses `run_claude_command()` (reference for correct invocation)
- `scripts/little_loops/fsm/evaluators.py` — uses `--output-format json` + `--no-session-persistence` for evaluation-only prompts (no Skill tool needed — this path is correct, do NOT change)

### Tests
- `scripts/tests/fsm/` — existing FSM tests; run `python -m pytest scripts/tests/ -k fsm`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Import `run_claude_command` in `runners.py`
2. Replace the slash command subprocess block in `DefaultActionRunner.run()` with a `run_claude_command()` call
3. Map `CompletedProcess` result fields to `ActionResult` fields
4. Verify shell command path (`bash -c`) is unchanged
5. Run FSM tests and do a live end-to-end test with a slash command loop step

## Impact

- **Priority**: P2 — Core `ll-loop` functionality is broken for any loop using slash command states
- **Effort**: Small — single function change reusing an existing utility
- **Risk**: Low — replaces custom subprocess logic with a well-tested utility already used by `ll-auto`/`ll-parallel`
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM executor and subprocess invocation design |
| `docs/reference/API.md` | `run_claude_command()` API reference |

## Labels

`bug`, `fsm`, `ll-loop`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b25bbd11-d148-42ec-b212-9c6172060a64.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P2
