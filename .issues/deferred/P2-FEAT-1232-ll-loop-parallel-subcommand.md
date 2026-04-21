---
discovered_date: "2026-04-21"
discovered_by: planning-discussion
confidence_score: 88
size: Medium
status: deferred
deferred_date: "2026-04-21"
deferred_reason: low-value
---

# FEAT-1232: `ll-loop parallel` Subcommand — Core Launcher

## Summary

Add an `ll-loop parallel <loop1> [loop2 ...]` subcommand that starts multiple FSM loops as concurrent background subprocesses, waits for all to complete, and exits with a non-zero code if any loop failed.

The state layer already supports concurrent loops — persistence files are namespaced as `.loops/.running/<loop_name>.state.json` and PID files as `.loops/.running/<loop_name>.pid`. The only missing piece is a launcher that orchestrates them as a group.

## Current Behavior

Running multiple loops in parallel requires manual background shell tricks (`ll-loop run a --background && ll-loop run b --background && ...`). There is no way to start a group of loops together, wait for all of them, or stop them as a unit with Ctrl-C.

## Expected Behavior

```
ll-loop parallel code-review test-watcher dependency-audit
```

- Validates that no two of the named loops declare overlapping `scope:` fields (load each loop's YAML, compare scopes using the same intersection logic as `LockManager.find_conflict`). If conflicts are found, print which loops conflict and exit 1 before starting any subprocess.
- Starts each loop as a detached subprocess (same mechanism as `run_background()` in `_helpers.py`, but without printing individual start messages — prints one summary line instead).
- Waits until all subprocesses have exited (poll PID files; a loop is done when its `.pid` file is gone).
- Prints a per-loop result summary when all are done (loop name, exit code, iterations, terminal state — read from each loop's `.state.json`).
- Exit code: 0 if all loops completed successfully (exit 0), 1 if any loop failed or was stopped.
- Signal handling: on SIGINT/SIGTERM, send SIGTERM to all child processes (using their PID files), then wait up to 30s before force-killing with SIGKILL. A second Ctrl-C forces immediate SIGKILL.

## Deferral Notes

Deferred as potentially low value. The core problem this solves — running multiple loops simultaneously — is already achievable today with `ll-loop run a --background && ll-loop run b --background`. The incremental value this adds is narrow: a grouped exit code for CI/scripting, pre-flight conflict detection before any process starts, and a single Ctrl-C to kill the group. These are real improvements but not compelling enough to justify the implementation complexity for current usage patterns. Revisit if a CI/scripting use case emerges that concretely requires the aggregated exit code.

## Motivation

Enables running independent automation loops concurrently without shell plumbing. The common case is workflows that are genuinely independent (e.g., a code-review loop and a test-watcher loop operating on different parts of the repo).

## Acceptance Criteria

- [ ] `ll-loop parallel --help` shows usage with `loop_names...` positional args
- [ ] Pre-flight scope conflict check errors with loop names before starting any process
- [ ] All named loops start as subprocesses; subprocess PIDs are written to `.loops/.running/<name>.pid`
- [ ] Command blocks until all loops exit
- [ ] Summary table printed on completion: loop name | status (success/failed/stopped) | iterations | final state | duration
- [ ] Ctrl-C sends SIGTERM to all children; second Ctrl-C sends SIGKILL
- [ ] Exit code 0 iff all loops exited 0
- [ ] Loops with non-overlapping scopes actually run concurrently (verified by checking process overlap via timestamps)

## Implementation Notes

- New `cmd_parallel` function in a new file `scripts/little_loops/cli/loop/parallel.py`; wire into `__main__.py` as `ll-loop parallel`
- Subprocess spawning: reuse the `subprocess.Popen(..., start_new_session=True)` pattern from `run_background()` — do NOT call `run_background()` directly since it prints per-loop start messages
- PID polling loop: check each loop's `.pid` file every 2s; a loop is done when its PID file is absent OR the PID it contains is no longer alive (`_process_alive()` from `concurrency.py`)
- Scope conflict check: for each pair of loops, load their FSMs with `load_and_validate`, compare `fsm.scope or ["."]` using `LockManager.find_conflict` logic (path intersection). Do not instantiate a LockManager for this — just compare scope lists directly.
- Summary result: read `.loops/.running/<name>.state.json` after each loop exits to get `iterations`, `current_state`, `terminated_by`; correlate with subprocess exit code
- Log files: each loop writes its own log to `.loops/.running/<name>.log` (same as `run_background()`); print log paths in the pre-start summary so users know where to tail
