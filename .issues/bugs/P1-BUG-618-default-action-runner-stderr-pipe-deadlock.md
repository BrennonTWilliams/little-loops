---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-618: `DefaultActionRunner` stderr pipe can deadlock on large stderr output

## Summary

`DefaultActionRunner.run()` streams stdout line-by-line from a subprocess while `stderr=PIPE` buffers stderr in the OS pipe. If the subprocess writes more stderr than the OS pipe buffer (~64 KB) before stdout is exhausted, the child blocks on its stderr write while the parent blocks reading stdout — a classic pipe deadlock. The process hangs indefinitely.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 159–184 (at scan commit: 12a6af0)
- **Anchor**: `in class DefaultActionRunner, method run()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/executor.py#L159-L184)
- **Code**:
```python
process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
...
for line in process.stdout:      # streams stdout line-by-line
    output_chunks.append(line)
    if on_output_line:
        on_output_line(line.rstrip())
process.wait(timeout=timeout)    # hangs if stderr buffer full
...
stderr = process.stderr.read()   # never reached in deadlock case
```

## Current Behavior

When a subprocess action emits more than ~64 KB to stderr concurrently with stdout output, the FSM executor hangs silently. The subprocess blocks trying to write stderr; the parent blocks waiting for more stdout lines. The `timeout` guard (`process.wait(timeout=timeout)`) will eventually fire, but only after the full timeout period has elapsed — meaning every action that triggers this path effectively runs for its maximum timeout duration.

Additionally, in the `TimeoutExpired` path the code returns immediately with `stderr="Action timed out"` (a literal string), silently discarding all actual stderr output from the killed process.

## Expected Behavior

The executor should drain both stdout and stderr concurrently so neither pipe buffer fills. The standard library fix is to use `process.communicate()` (which handles this internally) or to drain stderr in a background thread while the main thread reads stdout. Actual stderr content should be returned even on timeout.

## Steps to Reproduce

1. Create an FSM loop with a shell action that writes more than ~64 KB to stderr (e.g., `bash -c "python3 -c \"import sys; sys.stderr.write('x'*65536)\"; echo done"`).
2. Run the loop with `ll-loop run`.
3. Observe: the loop hangs until the action timeout fires, then terminates with `exit_code=124` and `stderr="Action timed out"` (literal string, not actual stderr content).

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `in class DefaultActionRunner, method run()`
- **Cause**: `subprocess.Popen` is called with both `stdout=PIPE` and `stderr=PIPE`, but only stdout is streamed. Stderr is read only after `process.wait()` returns. The OS pipe buffer fills when stderr output is large, blocking the child, which prevents it from writing to stdout, which prevents the parent from making progress on its stdout read loop.

## Proposed Solution

Replace the current pattern with `subprocess.communicate()` for the non-streaming case, or drain stderr in a background thread for the streaming case:

```python
# Option A: background thread (preserves line-by-line streaming)
import threading

stderr_chunks: list[str] = []

def drain_stderr() -> None:
    assert process.stderr is not None
    for line in process.stderr:
        stderr_chunks.append(line)

stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
stderr_thread.start()

for line in process.stdout:  # type: ignore[union-attr]
    output_chunks.append(line)
    if on_output_line:
        on_output_line(line.rstrip())

process.wait(timeout=timeout)
stderr_thread.join(timeout=5)
stderr = "".join(stderr_chunks)

# Option B: communicate() — loses line-by-line streaming, simpler
stdout_out, stderr_out = process.communicate(timeout=timeout)
```

Option A preserves the existing `on_output_line` streaming behavior. Option B is simpler but would require refactoring the output callback mechanism.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `DefaultActionRunner.run()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` calls `DefaultActionRunner.run()`
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` wraps `FSMExecutor`

### Similar Patterns
- `scripts/little_loops/fsm/executor.py` — `SimulationActionRunner.run()` does not use subprocess, not affected

### Tests
- `scripts/tests/test_fsm_executor.py` — needs a test with large stderr output that verifies no hang

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add a `threading.Thread` to drain `process.stderr` concurrently with stdout streaming in `DefaultActionRunner.run()`
2. Update the `TimeoutExpired` path to join the stderr thread and return actual stderr content
3. Add a test in `test_fsm_executor.py` using a subprocess that writes large stderr

## Impact

- **Priority**: P1 — A production action that emits verbose error output to stderr (e.g., a failing test suite, verbose compiler output) will silently hang the entire FSM loop until timeout
- **Effort**: Small — Threading fix is ~10 lines; well-understood pattern
- **Risk**: Low — The fix is isolated to `DefaultActionRunner.run()`; no interface changes
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `loop`, `executor`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P1
