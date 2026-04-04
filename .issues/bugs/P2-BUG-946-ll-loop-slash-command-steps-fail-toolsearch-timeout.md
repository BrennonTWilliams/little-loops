---
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
- **Anchor**: `DefaultActionRunner.run()` — slash command `cmd` built at lines 79–85
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

    def _on_proc_start(p: subprocess.Popen[str]) -> None:
        self._current_process = p

    def _on_proc_end(p: subprocess.Popen[str]) -> None:
        self._current_process = None

    try:
        completed = run_claude_command(
            command=action,
            timeout=timeout,
            stream_callback=_stream_cb,
            on_process_start=_on_proc_start,
            on_process_end=_on_proc_end,
        )
    except subprocess.TimeoutExpired:
        return ActionResult(
            output="",
            stderr="Action timed out",
            exit_code=124,
            duration_ms=timeout * 1000,
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_current_process` tracking is required** — The signal handler at `scripts/little_loops/cli/loop/_helpers.py:57-59` reads `runner._current_process` directly on SIGTERM to kill any running subprocess (added in BUG-592). If this attribute is not maintained during slash command execution, SIGTERM will silently fail to kill the child Claude process. The `on_process_start`/`on_process_end` callbacks in `run_claude_command()` (`subprocess_utils.py:67-68`) exist precisely for this purpose.

**`subprocess.TimeoutExpired` must be caught** — `run_claude_command()` raises `subprocess.TimeoutExpired` on timeout (`subprocess_utils.py:160, 171`), unlike the current path which returns `ActionResult(exit_code=124)`. Without a catch block, a timeout in a slash command step would propagate as an uncaught exception through `FSMExecutor._run_action()` (`executor.py:441-446`) and crash the loop instead of triggering the normal timeout routing.

**`run_claude_command()` actual signature** (`subprocess_utils.py:62-71`):
```python
def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,   # Callable[[str, bool], None]
    on_process_start: ProcessCallback | None = None, # Callable[[Popen], None]
    on_process_end: ProcessCallback | None = None,   # Callable[[Popen], None]
    idle_timeout: int = 0,
    on_model_detected: ModelCallback | None = None,
) -> subprocess.CompletedProcess[str]:
```

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
- `scripts/tests/test_fsm_executor.py:2952` — `TestDefaultActionRunnerProcessTracking` — extend with an `is_slash_command=True` test; patch `little_loops.subprocess_utils.run_claude_command` (not `subprocess.Popen`) since the fix bypasses Popen entirely for slash commands
- `scripts/tests/test_fsm_executor.py:3041` — `TestDefaultActionRunnerStderrDrain` — all existing tests use `is_slash_command=False`; no changes needed here
- E2E tests in `scripts/tests/test_ll_loop_execution.py:111` patch `little_loops.fsm.executor.subprocess.Popen` — this still works for shell command states but new slash command E2E tests must patch `little_loops.subprocess_utils.run_claude_command`
- Run: `python -m pytest scripts/tests/ -k "fsm"`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Import `run_claude_command` and `subprocess` in `runners.py` (confirm `subprocess` is already imported at line 11)
2. Replace the slash command `cmd = [...]` block (`runners.py:79-85`) and the shared `Popen` call with a `run_claude_command()` invocation
3. Add `on_process_start`/`on_process_end` callbacks to maintain `self._current_process` (required for SIGTERM handling via `_helpers.py:57-59`)
4. Wrap the `run_claude_command()` call in `try/except subprocess.TimeoutExpired` and return `ActionResult(exit_code=124)` to match current timeout behavior
5. Verify shell command path (`bash -c`, lines 87-88) is unchanged — only the `if is_slash_command` branch changes
6. Add a test in `TestDefaultActionRunnerProcessTracking` (`test_fsm_executor.py:2952`) for `is_slash_command=True` verifying `_current_process` lifecycle via the new callbacks
7. Run FSM tests: `python -m pytest scripts/tests/ -k "fsm"` and do a live end-to-end test with a slash command loop step

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
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b333ee9b-a17d-4e46-80c3-e1e9b655ac40.jsonl`
- `/ll:refine-issue` - 2026-04-04T03:48:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56740bd0-a1c0-4c17-82fe-d5a9a3b4cb7c.jsonl`

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b25bbd11-d148-42ec-b212-9c6172060a64.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P2
