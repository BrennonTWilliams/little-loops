---
id: BUG-1759
title: ll-auto does not forward CONTEXT_HANDOFF signal to outer FSM loop
type: BUG
status: open
priority: P2
captured_at: '2026-05-28T00:42:55Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
labels:
- bug
- ll-loop
- fsm
- autodev
- handoff
---

# BUG-1759: ll-auto does not forward CONTEXT_HANDOFF signal to outer FSM loop

## Summary

When the autodev FSM runs `ll-auto` as a subprocess action, `ll-auto` internally spawns a Claude manage-issue session. If that Claude session hits its context limit and emits `CONTEXT_HANDOFF:` to its own stdout, `ll-auto` does not forward this signal to its own stdout. The outer autodev FSM's `signal_detector` only sees `ll-auto`'s stdout — so it never detects the handoff and cannot take any terminal action for that iteration.

## Motivation

This bug blocks autodev FSM loops from detecting when their child `ll-auto` processes hit context limits. Without signal forwarding, the outer loop cannot take terminal action (handoff, timeout, skip), causing:

- Indefinite iteration hangs (4+ hours observed) on every context-limit encounter
- Accumulation of orphaned `claude` child processes across TTYs (5 observed across one incident)
- Scope creep from continuation prompts that don't check whether the target issue is already resolved

## Root Cause

- **File**: `scripts/little_loops/fsm/signal_detector.py`, `scripts/little_loops/fsm/executor.py`
- **Function**: `SignalDetector.detect_first()` / `_run_action()` `on_output_line` callback
- **Explanation**: The `signal_detector` correctly detects `CONTEXT_HANDOFF:` in direct Claude action output (when `ll-loop run` calls Claude directly). But when the action is `ll-auto`, the subprocess chain is `autodev FSM → ll-auto → claude manage-issue`. The Claude process emits `CONTEXT_HANDOFF:` to `ll-auto`'s internal subprocess pipe, not to `ll-auto`'s own stdout. `ll-auto` does not surface this signal upward, so the autodev FSM's executor receives no handoff event and continues waiting.

## Current Behavior

**Incident 1 (2026-05-27, ENH-1702):** Claude subprocess hit context limit (301%), spawned a continuation session, and completed the work. But `ll-auto` (PID 31860) kept running waiting for the inner process; the outer autodev FSM never received a handoff signal and hung in `implement_current` for 4+ hours with no events since 6:56 PM.

**Incident 2 (2026-05-30, BUG-1799):** Same chain — `ll-loop run autodev BUG-1799` → `ll-auto --only BUG-1799` → `claude`. BUG-1799 was completed and committed (`2311d7f4`, status: `done`) before the claude session hit its context limit. The continuation prompt told the fresh session to "continue from the interruption point" and "close the issue as usual," but the issue was already done. The new session began implementing *unrelated* issues (ENH-1805, BUG-1800, ENH-1769), burning tokens on work `ll-auto --only BUG-1799` never requested. All three processes (`ll-loop`, `ll-auto`, `claude`) remained alive in a wait chain with no progress.

**Incident 3 (2026-05-30, BUG-1815):** Same chain — `ll-loop run autodev BUG-1815` → `ll-auto` → `claude`. BUG-1815 was already fixed and committed (`c5e5cf41`, status: `done`) in a prior session. The continuation prompt shipped the full 3.1M-token session history (1552% of context limit) into a fresh session, creating a continuation death spiral — the handoff prompt itself blows the context limit immediately on load. The `ll-loop` process (PID 11442) sat for 40+ minutes waiting on a claude child (PID 79771) that could never make progress. Killing the parent left the claude child orphaned and still running.

### Continuation prompt design flaw

The "fresh session continuation" prompt unconditionally instructs the new session to "continue implementation from the interruption point" and "Complete normally: test, commit, close the issue as usual." It does not check whether the target issue was already resolved before the context limit was hit. When the issue is already `done`, the continuation session invents new work — implementing other issues that the parent `ll-auto --only <ID>` invocation never asked for. This turns a context-limit handoff into unbounded scope creep.

### Orphan accumulation

Each stuck iteration leaves behind a `claude` child process that `ll-auto` is waiting on. When the outer loop eventually times out or is killed, `ll-auto` exits but its claude child may detach and persist. Over repeated autodev runs, orphaned claude processes accumulate across TTYs (5 observed during the BUG-1799 incident across `s003`, `s010`, `s012`, `s013`, `s015`, `s033`). Neither `ll-auto` nor `ll-loop` has a cleanup mechanism for prior stuck iterations before starting a new one.

## Steps to Reproduce

1. Run `ll-loop run autodev <issue-id>` which invokes `ll-auto` as a subprocess action
2. The autodev FSM spawns `ll-auto --only <issue-id>`
3. `ll-auto` spawns a Claude manage-issue session
4. The Claude session hits its context limit and emits `CONTEXT_HANDOFF:` to its stdout
5. Observe: `ll-auto` does not forward the signal to its own stdout
6. Observe: The outer autodev FSM never detects the handoff, and the iteration hangs indefinitely (4+ hours)

## Expected Behavior

When `ll-auto`'s child Claude process emits `CONTEXT_HANDOFF:`, `ll-auto` should either:
1. Print `CONTEXT_HANDOFF: <payload>` to its own stdout so the outer FSM can detect and handle it, OR
2. Exit with a specific exit code that the autodev FSM routes as a terminal/handoff state

Alternatively, the autodev FSM's `implement_current` state should have a mandatory wall-clock timeout (via BUG-1723's `idle_timeout`) so a stuck `ll-auto` subprocess is killed after a configurable threshold regardless of signal propagation.

## Proposed Solution

Modify `ll-auto`'s child process output handling to detect and forward `CONTEXT_HANDOFF:` signals:

1. In `scripts/little_loops/cli/auto.py`, add signal detection on the child Claude subprocess stdout — when `CONTEXT_HANDOFF:` is detected, print it to `ll-auto`'s own stdout and exit cleanly
2. Alternative: exit with a specific handoff exit code (e.g., 75) that the autodev FSM's `implement_current` state routes to a terminal path
3. Add a pre-continuation guard: before spawning a fresh Claude session, check whether the target issue is already `status: done` or `cancelled` — if so, skip the continuation and exit cleanly
4. Add orphan detection: before starting a new iteration, `ll-loop` should detect and warn about prior claude processes still running for the same loop/issue

## Implementation Steps

1. Identify where `ll-auto` reads output from its child Claude subprocess (likely in `scripts/little_loops/cli/auto.py` or equivalent)
2. Add signal detection on `ll-auto`'s child stdout — when `CONTEXT_HANDOFF:` is detected, print it to `ll-auto`'s own stdout and exit cleanly
3. Alternatively: add a handoff exit code (e.g. 75) that the autodev FSM's `implement_current` state routes to a terminal path
4. Update autodev loop YAML to handle the handoff route if using exit code approach
5. Add test covering: `ll-auto` child emits `CONTEXT_HANDOFF:` → outer FSM detects it
6. **Continuation prompt guard**: before spawning a continuation session, `ll-auto` should check whether the target issue is already `status: done` (or `cancelled`). If so, skip the continuation and exit cleanly — the work is complete regardless of how the prior session ended
7. **Orphan cleanup**: `ll-loop` (or `ll-auto`) should detect and warn about prior claude processes still running for the same loop/issue before starting a new iteration, and provide a `--kill-orphans` flag to clean them up

## Related Issues

- BUG-1723: Wire idle_timeout through FSM schema — complementary fix; idle_timeout would unblock the hang even without signal propagation
- BUG-1799 (done): audit-issue-conflicts scans terminal issues — the issue whose autodev run triggered Incident 2 on 2026-05-30; already completed but the continuation session didn't know that
- BUG-819 (done): Missed handoff in WorkerPool silently continues as success — different code path (parallel worker pool, not FSM action runner)

## Session Log
- `/ll:capture-issue` - 2026-05-28T00:42:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
