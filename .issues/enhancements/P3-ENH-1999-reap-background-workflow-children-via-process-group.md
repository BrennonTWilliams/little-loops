---
id: ENH-1999
status: done
captured_at: 2026-06-07 03:43:15+00:00
completed_at: 2026-06-07 04:17:33+00:00
discovered_date: 2026-06-07 00:00:00+00:00
discovered_by: capture-issue
relates_to:
- BUG-1997
labels:
- subprocess
- automation
- hardening
- ll-auto
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1999: Reap background Workflow children via process group on subprocess kill

## Summary

When `run_claude_command` (`scripts/little_loops/subprocess_utils.py`) kills the
headless `claude -p` subprocess — on wall-clock timeout, idle timeout, or the
post-stream-close fallback — it signals only the **main** `claude` PID via
`process.kill()`. If that session spawned background `Workflow`/`Task` child
processes (the multi-agent path `manage-issue` now uses), those children are
**not** in the parent's kill target and can be orphaned, left running, or
continue holding inherited stdout/stderr pipe FDs after the parent gives up.

Harden the kill paths to reap the whole process tree by launching the child in
its own process group (`start_new_session=True`) and sending the signal to the
group (`os.killpg`) instead of the single PID.

## Motivation

This is the structural follow-up to the post-`result` break fix (the reader now
stops on the stream-json `result` event instead of blocking on a pipe EOF that
inherited FDs never deliver — see related fix in `subprocess_utils.py` and
`test_subprocess_utils.py::TestRunClaudeCommandResultBreak`). That fix stops the
*successful* run from hanging to the 3600s timeout, but it does **not** address
the lifecycle of background children when the parent genuinely has to kill (real
timeout / idle / hung main process):

- **Orphaned work**: a killed session can leave background Workflow agents
  running with no parent, consuming tokens and CPU and possibly mutating the repo
  after the orchestrator considered the issue dead.
- **Resource leaks**: orphaned children holding pipe write-ends or worktree locks
  can interfere with subsequent `ll-auto` / `ll-parallel` iterations.
- **Determinism**: batch automation should leave no stray processes between
  issues; today a timeout can.

## Current Behavior

In `run_claude_command` (`scripts/little_loops/subprocess_utils.py`):

- `subprocess.Popen(...)` is created without `start_new_session=True`, so the
  child shares the parent's process group.
- Three kill sites call `process.kill()` (SIGKILL to the single PID only):
  1. wall-clock timeout branch (`if timeout and (now - start_time) > timeout`)
  2. idle-timeout branch (`if idle_timeout and ...`)
  3. post-stream-close fallback (`process.wait(timeout=30)` → `except` → `process.kill()`)
- None of these reach grandchild/background processes spawned by the session.

## Expected Behavior

- The subprocess is launched in its own session/process group.
- Every kill site sends the terminating signal to the **process group**
  (`os.killpg(os.getpgid(process.pid), signal.SIGKILL)`), reaping the main
  session and any background Workflow/Task children together.
- Graceful-shutdown nicety (optional): try `SIGTERM` to the group, wait briefly,
  then `SIGKILL` the group, so well-behaved children can clean up worktrees.
- Behavior is unchanged on the normal (non-kill) exit path.

## Root Cause

`scripts/little_loops/subprocess_utils.py` → `run_claude_command`: `Popen` omits
`start_new_session`, and the kill sites target a single PID via `process.kill()`
rather than the process group. Background children spawned by the `claude`
session are therefore outside the signal's reach.

## API / Interface

No public signature change to `run_claude_command`. Internal only:

- `subprocess.Popen(..., start_new_session=True)`.
- A small helper, e.g. `_kill_process_group(process)`, used at all three kill
  sites in place of the bare `process.kill()` / `process.wait()` dance.
- Must remain cross-platform-guarded: `os.getpgid` / `os.killpg` are POSIX-only.
  Fall back to `process.kill()` on platforms without them (Windows) — the project
  targets darwin/Linux automation but the guard avoids import-time breakage.

## Implementation Steps

1. Add `start_new_session=True` to the `Popen` call in `run_claude_command`.
2. Add a module-level helper `_kill_process_group(process, *, grace: float = 0.0)`
   that resolves the group via `os.getpgid(process.pid)` and `os.killpg(...)`,
   with a `try/except (ProcessLookupError, PermissionError, AttributeError)`
   fallback to `process.kill()`.
3. Replace `process.kill()` at the wall-clock timeout, idle-timeout, and
   post-stream-close fallback sites with the helper.
4. Keep the existing `process.wait(timeout=...)` reaping and the
   "did not terminate within 10s" warning logs.
5. Tests in `scripts/tests/test_subprocess_utils.py`: assert `Popen` is called
   with `start_new_session=True`; assert the timeout/idle/fallback paths invoke
   the group-kill helper (patch `os.killpg`/`os.getpgid`) and degrade gracefully
   when `killpg` raises `ProcessLookupError`.

## Scope Boundaries

**In scope:**
- `run_claude_command` in `scripts/little_loops/subprocess_utils.py`: launch the
  child with `start_new_session=True` and signal the process group at all three
  kill sites.
- A `_kill_process_group` helper with a POSIX guard and a single-PID fallback.
- Unit tests in `scripts/tests/test_subprocess_utils.py`.

**Out of scope:**
- The post-`result` stream-break fix — already landed separately; this is the
  structural follow-up, not a re-do.
- Any change to the `host_runner` abstraction layer; this fix lives strictly
  below it in `subprocess_utils`.
- Restarting, retrying, or rescheduling background children that were killed —
  the goal is to reap them, not recover their work.
- Windows-native process-tree reaping beyond the graceful single-PID fallback
  (the project targets darwin/Linux automation).

## Impact

- **Priority**: P3 — hardening follow-up. The companion `result`-break fix
  already removed the common hang-on-success symptom, so this is
  defense-in-depth for the genuine-kill path, not a live failure.
- **Effort**: Small — one function plus a small module-level helper and its
  tests; no public API change.
- **Severity**: Low–Medium. The companion `result`-break fix already prevents the
  most common symptom (hang-on-success). This addresses the remaining
  orphaned-children case on genuine kills.
- **Scope**: `scripts/little_loops/subprocess_utils.py` (one function + small
  helper) and its test module. Affects all consumers: `ll-auto`, `ll-parallel`,
  `ll-sprint`, `run_with_continuation`.
- **Risk**: Signalling a process group is broader than a single PID — verify the
  parent orchestrator (ll-auto) is not itself in the child's new group (it won't
  be, since `start_new_session` gives the child a fresh group). POSIX-guard the
  `killpg` calls so non-POSIX hosts don't break.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Host CLI Abstraction | Subprocess invocation goes through `host_runner`; this change is below that layer in `subprocess_utils`. |

## Session Log
- `/ll:ready-issue` - 2026-06-07T04:08:55 - `747d5276-7607-4a6a-8f69-8154437e1ff3.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `485f5a18-987f-47b8-baf1-80430c8e8af3.jsonl`
- `/ll:format-issue` - 2026-06-07T03:46:28 - `32cf3ee0-7e8b-4b29-bb4f-4a7fbbff706f.jsonl`
- `/ll:capture-issue` - 2026-06-07T03:43:15Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<session>.jsonl`
- /ll:manage-issue - 2026-06-07T04:17:33Z - manage-issue-session

---

## Status

open
