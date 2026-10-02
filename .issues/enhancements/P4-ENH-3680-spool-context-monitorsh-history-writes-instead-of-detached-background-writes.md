---
id: ENH-3680
type: ENH
title: Spool context-monitor.sh history writes instead of detached background writes
priority: P4
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
relates_to:
- ENH-3677
- ENH-3658
- ENH-3679
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3680: Spool context-monitor.sh history writes instead of detached background writes

## Summary

**Cancelled 2026-10-02:** retain the existing remote no-op and document the omitted context-pressure/handoff rows. No spool, detached writer or new remote marker is required. The former spool design is retained in git history; it is not an implementation plan.

## Current Behavior

Both context-monitor writer calls pre-resolve with `resolve_history_db(".ll/history.db")`. Remote config raises `HistoryBackendNotLocal` before any network request; the shell suppresses that best-effort write failure. Local SQLite and `LL_HISTORY_DB` still record immediately. The threshold reminder and exit behavior are independent of persistence. One Python interpreter is launched for the existing config check; cancelling the spool does not claim to remove that cost.

## Resolution

**Consumer audit:** remote consumers already exist: backend-aware `ll-session recent --kind context_pressure` and indexed `session_store.queries.search` can read these rows from libSQL. A migrated-stub probe recorded a context-pressure event, retrieved it through both queries and created no shadow DB. Other readers include `history_reader/context.py`, lifecycle/handoff summaries and `ll-ctx-stats` (refused by ENH-3657). The reason to defer persistence is not absence of consumers: no live control-flow dependency on the context-monitor writes was found, and no current requirement justifies the durability/replay machinery.

Retain the current fail-soft no-op. A SessionStart marker would add staleness and override handling only to save interpreter startup; direct detached remote writes have unproven host process-lifetime behavior. Revisit in a separate issue if a demonstrated consumer requires these live hook rows, with explicit remote transaction/idempotency, crash recovery and bounded retention requirements.

## Scope Boundaries

- No implementation in this cancelled issue; local immediate writes and reminder/exit contracts remain intact.
- ENH-3657 documents that remote context-monitor pressure/handoff rows are omitted.
- ENH-3658 adds the permanent hazard-gate exception: remote writes intentionally skipped. This does not allow a remote reader to consult a shadow local DB.
- ENH-3683's deferred local CLI telemetry spool is independent.

## Expected Behavior

Remote context-monitor writes remain skipped before network I/O; docs state the missing pressure/handoff telemetry explicitly. Local persistence, threshold reminders and exit codes retain their current contracts. No new marker, spool or background remote request is introduced.

## Program Design

The existing `resolve_history_db(".ll/history.db")` refusal and shell fail-soft handling remain in place. No new runtime types or functions are added. ENH-3657 owns the support-table text and ENH-3658 owns the permanent executable-hazard exception.

### Signatures

- `resolve_history_db(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path` — existing signature stays unchanged; remote defaults raise `HistoryBackendNotLocal` before a writer is reached.

### Call Path

- `context-monitor.sh` → `little_loops.session_store.db.resolve_history_db` → remote `HistoryBackendNotLocal` → existing shell `|| true`; threshold reminders and exit handling continue independently.

## Impact

- **Priority:** P4 — cancelled after the consumer-need review.
- **Effort:** Documentation and hazard-gate follow-through in the active siblings; no spool implementation.
- **Risk:** Remote pressure/handoff telemetry stays incomplete, explicitly documented; existing reminders remain functional.
- **Breaking Change:** No.

## Acceptance Criteria

- [x] Consumer audit distinguishes existing remote readers from a live control-flow requirement; the cancellation rationale is recorded above.
- [x] The unproven spool/marker implementation is removed from the active plan and the issue is `cancelled`.
- [ ] Documentation and the hazard-gate exception are delivered by ENH-3657/3658, not a reopening of this cancelled issue.

## Confidence Check Notes

_Pre-spool 85/56 scores were cleared 2026-10-02; they do not describe the cancelled no-op decision. No implementation confidence gate applies to this terminal issue._

## Related

- ENH-3657 (support documentation), ENH-3658 (hazard-gate exception), ENH-3679/3683 (independent local telemetry work), FEAT-3535 (existing remote consumers).

## Status

**Cancelled** | Created: 2026-09-30 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:24 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
