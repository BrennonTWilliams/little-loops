---
id: ENH-3680
type: ENH
title: Spool context-monitor.sh history writes instead of detached background writes
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
---

# ENH-3680: Spool context-monitor.sh history writes instead of detached background writes

## Summary

Replace the direct writes in `hooks/scripts/context-monitor.sh` (`record_handoff_needed`, `record_context_pressure`) with a local append-only JSONL spool that is drained at SessionStart and Stop, so a remote history backend never puts network latency on the hook's critical path. Split out of ENH-3658 after two Opus reviews found the detached-background-write design unproven.

## Current Behavior

Both `record_*` calls pre-resolve with `resolve_history_db(".ll/history.db")` (`context-monitor.sh:56-58`, `:82-84`), which raises `HistoryBackendNotLocal` under `history.backend.provider: libsql`; the shell `|| true` swallows it, so handoff/pressure rows never reach the remote store. ENH-3658's chosen Option A (drop the pre-resolve, detach the writes with `( record_* ) </dev/null >/dev/null 2>&1 &`) has no precedent in `hooks/scripts/` and it is unverified whether Claude Code kills the process group or waits on children with redirected fds; the writes run before `exit 2`, so a slow remote can lose the handoff reminder.

## Expected Behavior

The hook appends one small JSON line (kept under `PIPE_BUF`, 4 KB, for atomic `O_APPEND`) per row to a spool file and returns immediately. A drain step (rename-claim, time-boxed, idempotent) inserts the rows via the target-aware writers at SessionStart (first, to fix handoff ordering) and Stop. Local sqlite behavior is unchanged (`LL_HISTORY_DB` still redirects). First verify that no consumer reads `context_pressure` rows live; rows may land up to one turn late.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `context-monitor.sh` no longer calls `resolve_history_db`; with a slow-but-reachable remote stub it returns in under 2 s with exit 2 and the reminder on stderr.
- [ ] Under a `HranaStub` remote, spooled lifecycle and pressure rows arrive after the drain; with the stub stopped, the hook exits 0 with empty stderr and rows stay spooled.
- [ ] Drain is idempotent and bounded; a crash mid-drain neither loses nor duplicates rows.
- [ ] Existing `TestContextMonitor` tests stay green (poll rather than assert immediately where the drain is async); `test_portability_gate.py` and `test_pre_compact.py::TestContextMonitorContract` still pass.

## Related

- ENH-3658 (split from), ENH-3678 (share the spool/drain mechanism if both land).

## Status

**Open** | Created: 2026-09-30 | Priority: P4
