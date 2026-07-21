---
id: BUG-2718
type: BUG
title: "run_claude_command's fixed 30s post-stream-close kill fires while legitimate synchronous parallel subagent work is still in flight"
priority: P2
status: open
captured_at: '2026-07-21T05:20:00Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
labels:
- subprocess
- automation
- hardening
relates_to:
- ENH-2717
- ENH-1999
- ENH-2712
---

# BUG-2718: run_claude_command's fixed 30s post-stream-close kill fires while legitimate synchronous parallel subagent work is still in flight

## Summary

`run_claude_command` (`scripts/little_loops/subprocess_utils.py`) kills its child `claude` process if it doesn't exit within a **fixed 30 seconds** after its stdout/stderr streams close (`subprocess_utils.py:511-518`). This constant assumes the main session should self-terminate almost immediately once its own output stream is done. That assumption breaks for any skill that spawns multiple **synchronous, blocking** subagents in parallel (the documented `Agent` tool pattern: "spawn multiple in a single message... wait for all to complete") — legitimate multi-minute background work can still be in flight when the parent's own stdout/stderr close, and the fixed 30s grace force-kills the whole process group (`_kill_process_group`, SIGKILL) before that work finishes, silently discarding it.

This is the root cause behind [[ENH-2717]]: `/ll:decide-issue ENH-2712 --auto` was killed (`exit -9`) mid-turn while waiting on two parallel `codebase-pattern-finder` evidence-gathering agents (explicitly spawned with `run_in_background: false` per `skills/decide-issue/SKILL.md` Phase 4), losing the scoring work and leaving `decision_needed: true` unresolved. ENH-2717 only stops the FSM from compounding that loss with a redundant size-review call — it does not stop the kill itself from happening.

## Current Behavior

In `run_claude_command`'s read loop (`subprocess_utils.py:389-509`): once both stdout and stderr hit EOF (or a stream-json `result` event breaks the loop early — the design intentionally does this because background Workflow/Task children can hold inherited FDs open forever, see the comment at `subprocess_utils.py:389-395` and [[ENH-1999]]), the code calls `process.wait(timeout=30)`. If the process hasn't exited by then, it force-kills the entire process group via `os.killpg(..., SIGKILL)`.

Observed in `.loops/.running/autodev-20260720T235236.log` (`[8/500] run_decide`): the assistant's last narrated line was *"I'm waiting on the second evidence agent (Option B) to finish before scoring both options"* — synchronous work explicitly still pending — followed immediately by `Process 48056 did not exit within 30s after streams closed, killing` and `exit: -9`.

30 seconds is nowhere near enough for two parallel research subagents doing multi-file codebase investigation (each agent's own transcript in this run shows many tool calls spanning minutes). The fixed constant has no way to distinguish "process is genuinely hung/zombied" from "process is alive and doing real, synchronous, in-flight work."

## Expected Behavior

The post-stream-close grace period should not force-kill a process that is still doing legitimate work. At minimum:
- Don't apply a flat, short timer as the sole signal — check process/process-group liveness (e.g., whether the process group still has live children consuming CPU, via `psutil`) before killing, and only kill once the group is genuinely idle/exited or a much longer absolute cap is hit.
- If a liveness check is out of scope for now, raise the 30s constant substantially (e.g., to the order of minutes) for call sites known to invoke skills with the synchronous-parallel-agent pattern, since 30s directly contradicts the `Agent` tool's own documented usage guidance.

## Root Cause

`subprocess_utils.py:511-518`:

```python
try:
    process.wait(timeout=30)
except subprocess.TimeoutExpired:
    logger.warning(
        "Process %s did not exit within 30s after streams closed, killing",
        process.pid,
    )
    _kill_process_group(process)
```

The `30` is a hardcoded magic number with no config surface, no liveness awareness, and — per the log evidence above — actively fires against a documented, intended usage pattern (synchronous parallel `Agent` tool calls) rather than only against genuinely hung processes.

**Unresolved ambiguity worth instrumenting before the fix**: it's not yet certain from the log alone whether (a) the stream-json `result` event fired prematurely (turn ended from the CLI's perspective before the blocking Task/Agent tool calls returned — possibly a host-CLI-level issue outside this codebase's control) or (b) the read loop hit natural EOF on both pipes without a `result` event (suggesting something else closed the streams while the process was still alive and working). Add a debug-level log of the terminal stream-json event type (or "natural EOF, no result event") immediately before the `process.wait(30)` call, so the next occurrence can distinguish these cases conclusively.

## Proposed Solution

1. Add the diagnostic logging above (terminal event type / EOF-without-result) so the next occurrence is conclusive rather than guesswork.
2. Replace (or supplement) the flat 30s `process.wait()` with a liveness-aware wait: poll `psutil.Process(process.pid).children(recursive=True)` (or process-group CPU-time delta) at short intervals up to a much longer absolute cap (e.g., 300s), only killing once the group is confirmed idle or the cap is hit.
3. If liveness polling is deemed too heavy for this call site, raise the flat constant to something compatible with the documented multi-agent pattern (minutes, not seconds) and note the tradeoff (a genuinely hung process now takes longer to reap).
4. Regression test: simulate a child that keeps a grandchild process alive and writing past the old 30s mark; assert it is not killed prematurely.

## Impact

- **Priority**: P2 — silently discards real, paid-for agent work (tokens + time) and produces incorrect downstream state (e.g., ENH-2712 was deferred as `low_readiness` when the real cause was an infrastructure kill, not a genuine readiness problem). Affects any skill following the documented parallel-`Agent` pattern, not just `decide-issue`.
- **Effort**: Small for the diagnostic logging; Medium for the liveness-aware wait.
- **Risk**: Low — the change only extends how long we wait before killing; it doesn't change kill mechanics for genuinely hung processes.

## Session Log
- `/ll:capture-issue` - 2026-07-21T05:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
