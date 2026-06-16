---
id: FEAT-1264
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by:
- FEAT-1156
- FEAT-1262
parent: FEAT-1159
relates_to:
- FEAT-1156
- FEAT-1262
- FEAT-1263
- FEAT-1113
---

# FEAT-1264: PreCompact Handoff — Event Log Integration

## Summary

Enhance `precompact-handoff.sh` (delivered by FEAT-1156) to read structured event records from `.ll/ll-session-events.jsonl` (delivered by FEAT-1262) instead of reconstructing state from git diff and ll-issues at compaction time. This replaces the FEAT-1156 fallback approach with a complete, accurate session history.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Current Behavior

`precompact-handoff.sh` (delivered by FEAT-1156) reconstructs session state at compaction time using a fallback strategy: `git diff --name-only HEAD` for files edited, `ll-issues list --status in_progress` for active issue status, and `.ll/loops/` JSON for loop state. This approach misses files edited then reverted, tasks completed mid-session, and errors that were subsequently resolved.

## Expected Behavior

`precompact-handoff.sh` reads `.ll/ll-session-events.jsonl` (delivered by FEAT-1262) when available to produce a more accurate, deduplicated session snapshot: file edits sorted by recency with reverts excluded, only unresolved errors, and net task state where the last event per subject wins. When the event log is absent, the FEAT-1156 fallback path is used unchanged.

## Motivation

FEAT-1156 builds `precompact-handoff.sh` using a fallback strategy: `git diff --name-only HEAD` for files edited, `ll-issues list --status in_progress` for active issues, and `.ll/loops/` JSON for loop state. This is reasonably accurate but has gaps — it can't distinguish files edited early then reverted, tasks completed mid-session, or errors that were subsequently resolved.

With FEAT-1262's event log available, the snapshot builder can group events by type, deduplicate file edits, filter resolved errors, and produce a more accurate priority-tiered snapshot without any model involvement.

## Use Case

**Who**: A developer running `ll-auto`, `ll-parallel`, or a long interactive session.

**Context**: After an extended session, Claude Code triggers context compaction. `precompact-handoff.sh` runs before the compaction window closes to produce a session snapshot.

**Goal**: The snapshot accurately reflects what happened — files actually edited (not reverted), errors that remain unresolved, and tasks still in progress.

**Outcome**: The next context window opens with a precise, noise-free summary rather than stale references to reverted files, resolved errors, or completed tasks.

## Acceptance Criteria

- `precompact-handoff.sh` reads `.ll/ll-session-events.jsonl` when available
- File ops section derived from event log (deduplicated, sorted by recency) instead of `git diff --name-only HEAD`
- Error section includes only events where `type=error` with no subsequent `type=error` resolution for the same subject — i.e., unresolved errors only
- Task section reflects net task state (last event per subject wins) rather than a static `ll-issues` snapshot
- Fallback preserved: if `.ll/ll-session-events.jsonl` does not exist (FEAT-1262 not yet active), the FEAT-1156 git-diff/ll-issues approach continues to work unchanged
- Priority-tier size-capping and idempotency from FEAT-1156 remain intact
- Existing `TestPrecompactHandoff` tests (FEAT-1157) pass without modification
- New tests added to `TestPrecompactHandoff` covering event-log-driven path:
  - Snapshot built from synthetic JSONL input (not git diff)
  - Deduplication: multiple Write events for same file → one entry
  - Resolved errors excluded; unresolved errors included
  - Fallback path exercised when JSONL is absent

## Implementation

### Modify: `hooks/scripts/precompact-handoff.sh`

Add an event-log read path before the existing fallback:

```bash
EVENT_LOG=".ll/ll-session-events.jsonl"
if [[ -f "$EVENT_LOG" ]]; then
  # Build sections from event log
  FILES_EDITED=$(jq -r 'select(.type=="file") | .subject' "$EVENT_LOG" | sort -u)
  ERRORS=$(jq -r 'select(.type=="error") | .subject' "$EVENT_LOG" | sort -u)
  # ... group by type, deduplicate, build tiered sections
else
  # FEAT-1156 fallback: git diff + ll-issues + loops
  FILES_EDITED=$(git diff --name-only HEAD 2>/dev/null || true)
  # ...
fi
```

The event-log path uses `jq` (already required by the script) to filter and group records. The fallback path is the existing FEAT-1156 implementation, untouched.

### Error Resolution Heuristic

The error-resolution heuristic is defined canonically in FEAT-1262's `### Event Semantics` section. This issue is the consumer; cite that schema rather than redefining the rule here. If the heuristic needs to evolve, update FEAT-1262's schema first, then update this consumer to match.

### Size-Capping Compatibility

The event-log path builds the same tiered markdown sections as the fallback path. The existing `wc -c` size-capping and LIFO drop logic (FEAT-1156) applies to both paths without modification.

## Files to Modify

- `hooks/scripts/precompact-handoff.sh` — add event-log read path with fallback

## Files to Add Tests To

- `scripts/tests/test_hooks_integration.py` — extend `TestPrecompactHandoff` with event-log-path tests

## Scope Boundary

This issue modifies only `precompact-handoff.sh`. It does NOT modify:
- `session-capture.sh` (FEAT-1262) — that issue owns the writer
- `session-start-inject.sh` (FEAT-1263) — that issue owns the injector
- The FEAT-1156 fallback path — it must remain working

**MVP Designation** (2026-05-01 audit): FEAT-1264 is the MVP for "reconstruct PreCompact summary at handoff" — the JSONL+jq path defined here. FEAT-1112's SQLite/FTS5-backed reconstruction is a future replacement that reuses the same snapshot-builder API surface (input → markdown sections). Designing the snapshot builder as a stable interface allows the SQLite implementation to swap in without changes to `precompact-handoff.sh` consumers. The error-resolution heuristic lives canonically in FEAT-1262's Event Semantics section.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/precompact-handoff.sh` does not exist (FEAT-1156 not yet delivered) ✓
- `.ll/ll-session-events.jsonl` not produced (FEAT-1262 not yet delivered) ✓
- Both upstream dependencies (FEAT-1156, FEAT-1262) still open — this issue is blocked ✓
- Feature not yet implemented ✓

## References

- Parent: FEAT-1159
- Modifies deliverable from: FEAT-1156 (`precompact-handoff.sh`)
- Reads from: FEAT-1262 (`ll-session-events.jsonl`)
- Downstream beneficiary: FEAT-1263 (richer snapshot → richer injection)
- Original vision: FEAT-1159 Component 2 integration notes

## Impact

- **Priority**: P3 — Enhances session snapshot accuracy for long sessions; not blocking but meaningfully improves handoff quality
- **Effort**: Medium — Adds event-log read path to an existing shell script; extends `TestPrecompactHandoff` with new test scenarios
- **Risk**: Low — New path is additive; FEAT-1156 fallback preserved unchanged; isolated to a single script
- **Breaking Change**: No

## Labels

`hooks`, `session-events`, `precompact`, `integration`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's implementation plan references `hooks/scripts/precompact-handoff.sh` as the target file to modify. Per FEAT-1156's Scope Boundary, that path does not exist. FEAT-1156 delivers a Python handler at `scripts/little_loops/hooks/pre_compact_handoff.py` and a 3-line passthrough adapter at `hooks/adapters/claude-code/precompact-handoff.sh` (no logic to modify). The event-log integration code shown in the implementation section (bash `jq` extraction into `FILES_EDITED`, `ERRORS`, etc.) must be rewritten as Python inside `pre_compact_handoff.handle()` in `scripts/little_loops/hooks/pre_compact_handoff.py`. The fallback/primary-path structure and size-capping logic remain as described, just in Python rather than bash.

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-16T23:26:53 - `6859bdb6-28b4-4bbd-942d-3775826e1d79.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
