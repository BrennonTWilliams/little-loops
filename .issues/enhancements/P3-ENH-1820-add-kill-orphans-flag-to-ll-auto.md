---
id: ENH-1820
title: Kill orphaned Claude processes by default on ll-auto startup with --no-kill-orphans opt-out
type: ENH
status: open
priority: P3
captured_at: '2026-05-31T02:45:00Z'
discovered_date: '2026-05-31'
discovered_by: capture-issue
labels:
- enhancement
- ll-auto
- process-management
- orphan-cleanup
---

# ENH-1820: Kill orphaned Claude processes by default on ll-auto startup with --no-kill-orphans opt-out

## Summary

Add process tracking to `AutoManager` so `ll-auto` detects and kills orphaned child Claude processes from prior stuck iterations before starting new work, with a `--no-kill-orphans` flag to opt out. Each stuck autodev iteration leaves behind a `claude` child process that `ll-auto` was waiting on; when the outer loop times out or is killed, `ll-auto` exits but its Claude child may detach and persist. Over repeated runs, orphaned Claude processes accumulate across TTYs (5 observed during one incident across `s003`, `s010`, `s012`, `s013`, `s015`, `s033`). Neither `ll-auto` nor `ll-loop` has a cleanup mechanism for prior stuck iterations. The detection is specific (matches project path + issue/loop pattern), making false positives unlikely, so killing should be the default — the real failure mode is silent orphan accumulation over unattended operation, which is worse than the hypothetical risk of a false-positive kill.

## Current Behavior

- `AutoManager` (`scripts/little_loops/issue_manager.py`) has no process tracking — no equivalent of `WorkerPool._processes` or `WorkerPool.terminate_all_processes()`
- When an autodev FSM loop kills a stuck `ll-auto` subprocess, the inner `claude` child may detach and persist as an orphan
- There is no detection or warning for existing orphaned processes when `ll-auto` starts a new iteration
- `WorkerPool` (`scripts/little_loops/parallel/worker_pool.py:140`) already has the pattern: `terminate_all_processes()` registers processes via `on_start`/`on_end` callbacks and forcefully terminates on shutdown

## Expected Behavior

1. `AutoManager` tracks child Claude processes it spawns (via `run_claude_command` / `run_with_continuation`)
2. On startup, `ll-auto` detects Claude processes from prior stuck iterations (matching project path + issue/loop pattern) and terminates them automatically, logging the count
3. On normal exit, tracked processes are cleaned up; on abnormal exit, the next `ll-auto` invocation finds and kills them
4. `--no-kill-orphans` flag skips orphan detection and termination, for the rare case where a user needs to preserve orphaned processes

## Motivation

This is the one remaining gap from BUG-1759 (signal forwarding + pre-continuation guard were fixed in `5124c51d`). Orphan accumulation was observed in production:

- **Incident 2 (BUG-1799)**: 5 orphaned `claude` processes across 6+ TTYs after repeated autodev runs hit context limits
- **Incident 3 (BUG-1815)**: Killing the `ll-loop` parent left a `claude` child orphaned and still running

Without cleanup, each context-limit encounter in an autodev loop leaves a zombie Claude process consuming resources. Over hours of unattended operation, this accumulates.

## Success Metrics

- **Orphan detection rate**: 100% of orphaned `claude` processes from prior `ll-auto` iterations detected on startup
- **Cleanup speed**: All detected orphans terminated in < 5 seconds (SIGTERM → wait → SIGKILL)
- **Prevention**: Zero orphan accumulation across repeated `ll-auto` runs under normal operation

## Proposed Solution

Model after `WorkerPool.terminate_all_processes()` at `worker_pool.py:140`:

1. **Add `_child_processes` tracking to `AutoManager`** — register each spawned subprocess via `on_start`/`on_end` callback pattern (mirroring `WorkerPool` lines 671-691)
2. **Add `terminate_all_processes()` to `AutoManager`** — iterate tracked processes, send SIGTERM, wait, escalate to SIGKILL
3. **Orphan detection and cleanup on startup** (`scripts/little_loops/cli/auto.py`):
   - Before starting work, scan for running `claude` processes whose command line matches the project path + issue/loop pattern
   - Kill any matches, log the action, and report count of cleaned processes
   - This is the default behavior — no flag required
4. **Add `--no-kill-orphans` CLI flag** — opt-out for the rare case where a user needs to preserve orphaned processes

### Pattern to Follow

`WorkerPool.terminate_all_processes()` (`worker_pool.py:140`) — registers processes via `self._processes.append(process)` on start and `self._processes.remove(process)` on end, with `terminate_all_processes()` iterating, sending SIGTERM, waiting, and escalating to SIGKILL.

## API/Interface

New CLI argument on `ll-auto`:

```
ll-auto --no-kill-orphans
```

- **Default behavior**: On startup, scans for and terminates orphaned `claude` child processes from prior stuck iterations, logging the count
- **Flag**: `--no-kill-orphans` (optional, boolean) — skip orphan detection and termination entirely

## Implementation Steps

1. Add `_child_processes: list[subprocess.Popen]` and `_process_lock` to `AutoManager`
2. Wrap `run_claude_command` / `run_with_continuation` calls in `AutoManager.run()` to register/deregister child processes
3. Implement `AutoManager.terminate_all_processes()` following `WorkerPool` pattern at `worker_pool.py:140`
4. Add `--no-kill-orphans` argument to `main_auto()` argument parser in `scripts/little_loops/cli/auto.py`
5. Implement orphan detection (default on): scan for `claude` processes with matching project path or issue/loop pattern in their command line, kill if found, log count
6. Gate detection behind `--no-kill-orphans` check — skip entirely when flag is present
7. Wire cleanup into `atexit` or signal handler for graceful shutdown

## Scope Boundaries

- **In scope**: Process tracking in `AutoManager`, default-on orphan detection and cleanup, `--no-kill-orphans` opt-out flag
- **Out of scope**: Cross-machine orphan detection, orphan detection in `ll-parallel` (already has `terminate_all_processes()`), orphan detection in `ll-sprint` (separate tool), PID file reconciliation for loop state files (covered by ENH-1669)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `AutoManager` class: add `_child_processes`, `terminate_all_processes()`, orphan detection
- `scripts/little_loops/cli/auto.py` — `main_auto()`: add `--no-kill-orphans` argument

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:140` — `WorkerPool.terminate_all_processes()`: reference implementation for process tracking and cleanup
- `scripts/little_loops/parallel/worker_pool.py:671-691` — `on_start`/`on_end` callback pattern for process registration

### Tests
- `scripts/tests/test_issue_manager.py` — add tests for `AutoManager` process tracking, orphan detection, and `terminate_all_processes()`
- `scripts/tests/test_cli.py` — add test for `--no-kill-orphans` flag parsing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — `main_auto()` calls `AutoManager.run()`; orphan detection may also be invoked at CLI entry
- `scripts/little_loops/issue_manager.py` — `run_claude_command` / `run_with_continuation` callers within `AutoManager`

### Documentation
- `docs/reference/API.md` — document new `AutoManager` methods and `--no-kill-orphans` flag

### Configuration
- N/A

## Impact

- **Priority**: P3 — Completes the BUG-1759 fix; orphan accumulation only occurs after repeated context-limit encounters, not every run
- **Effort**: Small — Follows an existing, well-tested pattern in `WorkerPool`; primarily copy-and-adapt work
- **Risk**: Low — Default-on orphan cleanup is a behavioral change, but detection is specific (project path + issue/loop pattern match); false positives are unlikely and `--no-kill-orphans` provides an escape hatch
- **Breaking Change**: No

## Related Key Documentation

- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — system design and orchestration patterns
- [API.md](../docs/reference/API.md) — `AutoManager` and `WorkerPool` API reference

## Related Issues

- BUG-1759 (done): ll-auto CONTEXT_HANDOFF signal forwarding — this is the one remaining gap from that fix
- BUG-1799 (done): audit-issue-conflicts scans terminal issues — Incident 2 where 5 orphans were observed
- BUG-1815: Continuation death spiral — Incident 3 where killing parent left orphaned child
- ENH-1669 (done): Auto-reconcile orphaned `status: running` state files — different layer (state files, not processes)
- BUG-818 (done): `_run_subprocess` no `_current_process` tracking — different scope (FSM executor MCP subprocesses)

## Labels

`enhancement`, `ll-auto`, `process-management`, `orphan-cleanup`

## Session Log
- `/ll:format-issue` - 2026-05-31T03:05:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde5e059-f5e9-4d77-8522-48c6692a972c.jsonl`
- `/ll:capture-issue` - 2026-05-31T02:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/402d74eb-4a8a-4e98-8242-2b8c5e9efb08.jsonl`

---

## Status

**Open** | Created: 2026-05-31 | Priority: P3
