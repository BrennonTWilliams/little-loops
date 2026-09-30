---
id: ENH-3680
type: ENH
title: Spool context-monitor.sh history writes instead of detached background writes
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
relates_to:
- ENH-3677
- ENH-3658
- ENH-3679
confidence_score: 85
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
---

# ENH-3680: Spool context-monitor.sh history writes instead of detached background writes

## Summary

Under a remote history backend, replace the direct writes in `hooks/scripts/context-monitor.sh` (`record_handoff_needed`, `record_context_pressure`) with immutable local event files drained at SessionStart and Stop, so network latency never sits on the context-monitor hook's critical path. Keep the current immediate writer path for local SQLite and `LL_HISTORY_DB`. Split out of ENH-3658 after two Opus reviews found the detached-background-write design unproven.

## Decision Gate and Interim Fix (2026-09-30 Opus review)

Under remote, the hook spawns a Python interpreter only for `resolve_history_db` to raise and `|| true` to swallow it. Do this first, independently of the spool:

1. **Gate:** verify whether any remote consumer needs live `context_pressure`/handoff rows (dashboards, `ll-doctor`, digest, `ctx-stats`; `ll-ctx-stats` is already refused under remote by ENH-3657). Record the answer in this issue.
2. **If no consumer:** make remote a documented no-op — detect a remote target cheaply (no Python spawn where feasible) and skip both `record_*` calls; local and `LL_HISTORY_DB` keep immediate writes. **Close the spool design below as not needed.**
   - **Remote detection must not grep `.ll/ll-config.json`:** `.ll/ll.local.md` deep-merges over it, so a shell-side grep misses local overrides. Have the Python SessionStart handler (which already classifies the store via `resolve_history_store`) write a small marker (e.g. `.ll/.history-remote`, removed when the store is local) and have the shell hook test for that file. Stale-marker risk is bounded to one session; the hook must still fail soft (`|| true`) if the marker and the actual target disagree.
3. **If a consumer exists:** implement the spool below and add the fixture dependency edge at that point (the remote-stub tests need the hoisted `remote` fixture). Sharing ENH-3679's envelope stays speculative; do not couple the two. Until then the gate and the no-op need no fixture, so this issue carries no fixture dependency.

## Current Behavior

Both `record_*` calls pre-resolve with `resolve_history_db(".ll/history.db")` (`context-monitor.sh:56-58`, `:82-84`), which raises `HistoryBackendNotLocal` under `history.backend.provider: libsql`; the shell `|| true` swallows it, so handoff/pressure rows never reach the remote store. ENH-3658's chosen Option A (drop the pre-resolve, detach the writes with `( record_* ) </dev/null >/dev/null 2>&1 &`) has no precedent in `hooks/scripts/` and it is unverified whether Claude Code kills the process group or waits on children with redirected fds; the writes run before `exit 2`, so a slow remote can lose the handoff reminder.

## Expected Behavior

Under a remote target, the hook atomically publishes one immutable, mode-0600 event file per row and returns immediately. A bounded drain step claims complete files and replays typed lifecycle/pressure operations, including their `search_index` effects, at SessionStart and Stop. Cap pending spool size and age so a long remote outage cannot grow disk use without limit; report pruned events with a visible drop count. The remote insert(s) plus deduplication marker must be one atomic Hrana transaction or use durable per-row idempotency keys; separate `LibsqlConnection.execute()` calls plus `commit()` do not provide that guarantee. Local SQLite and `LL_HISTORY_DB` still write immediately. First verify that no remote consumer requires live `context_pressure` rows; remote rows may land up to one turn late.

> **2026-09-30 design correction:** the local SQLite drain sketched in ENH-3683 (ENH-3679's deferred spool) cannot serve remote libSQL. The two may share an immutable event-file envelope and claim/recovery rules only if both are ever built; ENH-3680 owns the remote drain regardless. Implementation order is independent.

## Scope Boundaries

- **In scope**: remote-target `context-monitor.sh` handoff and pressure writes, immutable files, and the target-aware drain at SessionStart and Stop; preserve immediate local writes.
- **Out of scope**: the five hand-built Python paths (ENH-3658), general telemetry-writer spooling (ENH-3679), other hooks.

## Behavior Parity

With local SQLite or `LL_HISTORY_DB`, `context-monitor.sh` continues its immediate writes and existing local tests keep immediate row assertions. Threshold reminders, exit codes, empty stderr on best-effort write failure, and the `|| true` fail-soft behavior stay intact. Only remote-target writes become eventual through the spool.

## Program Design

### Types

- `HookSpoolEvent` is a typed lifecycle or context-pressure operation with event UUID, timestamp, payload, and a non-secret target identity. The immutable file envelope is compatible with ENH-3679's format if both implementations exist; replay remains separate.

### Signatures

- `spool_publish(target_id: str, event: HookSpoolEvent) -> None` — publishes one mode-0600 immutable file without contacting the remote endpoint.
- `drain_remote_spool(target: RemoteTarget, *, budget_s: float) -> int` — claims matching pending/recovered files and uses an atomic remote batch or durable row idempotency keys.

### Call Path

`context-monitor.sh` → remote-target `spool_publish` → SessionStart/Stop `handle` → `drain_remote_spool` → existing `record_session_lifecycle_event` / `record_context_pressure_event` semantics plus `search_index`. A local target keeps the existing direct-writer path.

## Impact

- **Priority**: P4 - only affects handoff/pressure telemetry for remote-backend users; local behavior unchanged
- **Effort**: Medium - target classification, immutable files, remote atomic replay, bounded hook drains, and failure recovery
- **Risk**: Medium - hook timing and shell portability
- **Breaking Change**: No

## Acceptance Criteria

- [ ] The consumer-need gate is answered in this issue; if no remote consumer needs the rows, remote is a documented no-op (no Python spawn, reminder and exit 2 unchanged, local writes immediate) and the spool criteria below are dropped.
- [ ] (Spool path only) `context-monitor.sh` no longer calls `resolve_history_db` for remote writes; with a slow-but-reachable remote stub it returns in under 2 s with exit 2 and the reminder on stderr, without opening a network connection on that path.
- [ ] Under a `HranaStub` remote, spooled lifecycle and pressure rows (and their search-index effects) arrive after the drain; with the stub stopped, the hook exits 0 with empty stderr and rows remain spooled. A threshold-crossing reminder is still delivered when the drain fails.
- [ ] Each file records a non-secret target identity (project/backend/endpoint identity, never an auth token); a later config or `LL_HISTORY_DB` change cannot replay it into the wrong store. A stale target is quarantined with a visible count.
- [ ] SessionStart and Stop drains name their owning hooks and finish within a total 2 s budget per invocation, leaving pending files for a later run on timeout. A crash before/after claim or remote commit neither loses nor duplicates unpruned rows; remote atomicity is proven by the batch protocol or explicit idempotency keys.
- [ ] Pending spool size and age are bounded. An extended remote outage prunes old pending or recovered claimed files only under the documented retention policy and increments a visible drop count; idempotency markers are retained long enough to prevent replay of any retained file.
- [ ] Existing local `TestContextMonitor` tests keep their immediate row assertions under `LL_HISTORY_DB`; separate remote tests cover eventual drain. `test_portability_gate.py` and `test_pre_compact.py::TestContextMonitorContract` still pass.

## Related

- ENH-3658 (split from), ENH-3677 (fixture; relevant only on the spool path), ENH-3679 (no coupling: its Phase 2 is deferred; separate local and remote drains).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-30_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 56/100 → LOW

### Concerns
- The issue is a two-branch plan (no-op vs spool) gated on a consumer-need question that is not yet answered; the implementation path cannot be chosen until the Decision Gate result is recorded in this issue.
- No Integration Map / Files to Modify section: change sites (`hooks/scripts/context-monitor.sh`, `session_start.py`, `usage_stop.py`, marker writer, new spool/drain module) are inferred from prose, not enumerated.
- Spool path leans on unproven mechanisms: atomic Hrana batch or durable idempotency keys, crash/claim recovery, and retention pruning have no precedent to model after.
- Test fixture dependency (ENH-3677 hoisted `remote` fixture) is deferred to the spool path only; `HranaStub` exists in `scripts/tests/` but the hoisted fixture is still open.

### Outcome Risk Factors
- Ambiguity: decision gate unresolved (no-op vs spool) — resolve first; the no-op branch is small and mechanical, the spool branch is deep (atomicity, recovery, retention).
- Deep per-site complexity on the spool path, broad enumeration across 6+ sites (shell hook, two Python hook handlers, marker, spool module, drain).
- Recommended: answer the consumer gate and record it, then slice the spool into its own issue if a consumer exists.

## Status

**Open** | Created: 2026-09-30 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:24 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
