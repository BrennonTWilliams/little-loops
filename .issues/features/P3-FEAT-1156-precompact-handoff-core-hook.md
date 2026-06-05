---
id: FEAT-1156
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by: [FEAT-1112]
parent: FEAT-1113

relates_to: ['ENH-152', 'ENH-495', 'FEAT-150', 'FEAT-1157', 'FEAT-1158']
---

# FEAT-1156: PreCompact Handoff Hook — Core Implementation

## Summary

Implement `hooks/scripts/precompact-handoff.sh` with priority-tiered snapshot logic, size-capping, and idempotency, then register it as a second PreCompact hook in `hooks/hooks.json`.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Motivation

`/ll:handoff` today is a manual step. Claude Code's PreCompact event fires before context compaction; hooking into it ensures a continuity snapshot is always written before state is lost. This is the core deliverable of FEAT-1113.

## Acceptance Criteria

- `hooks/scripts/precompact-handoff.sh` exists and is executable
- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority tiers drop LIFO under size pressure (tool-event summary dropped first, then decisions, etc.)
- Idempotency: skips write if `ll-continue-prompt.md` mtime is newer than `compacted_at` from `.ll/ll-precompact-state.json`
- `hooks/hooks.json` registers the new script as a second PreCompact entry (existing `precompact-state.sh` entry preserved)
- Schema of written file passes `/ll:resume` compatibility: frontmatter with `session_date`, `session_branch`, `issues_in_progress` + sections `## Intent`, `## File Modifications`, `## Decisions Made`, `## Next Steps`

## Implementation

### New File: `hooks/scripts/precompact-handoff.sh`

Follow `precompact-state.sh` structure:
- Read stdin JSON, extract `transcript_path` via jq
- Source `hooks/scripts/lib/common.sh`
- Check `ll_feature_enabled` guard
- Build tiered content sections:
  1. Active issue + loop state (always kept) — from `ll-issues list --status in_progress` + `.ll/loops/` JSON files
  2. Files edited this session (always kept) — from `git diff --name-only HEAD`
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- Cap at 2KB with `wc -c`; drop sections LIFO until under cap
- Write atomically using `acquire_lock` / `atomic_write_json` from `lib/common.sh`
- Exit 2 with message to surface errors to user

### Idempotency Guard

Before writing, compare `.ll/ll-continue-prompt.md` mtime against `compacted_at` from `.ll/ll-precompact-state.json`. If prompt is already fresh (mtime > compacted_at), skip write and exit 0.

### Registration: `hooks/hooks.json:89-100`

Add a second object to the PreCompact array. Do NOT remove the existing `precompact-state.sh` entry — `context-monitor.sh:check_compaction()` (lines 176–206) depends on `.ll/ll-precompact-state.json` being written.

### Output Schema

Follow `commands/handoff.md:134-158` structured schema. The `commands/resume.md:28-42` consumer validates `## Intent` + `## Next Steps` presence. The legacy `hooks/prompts/continuation-prompt-template.md` is for reference only.

### State Sources (FEAT-1112 Fallback)

FEAT-1112 (session store) is not yet implemented; gather state without it:
- **Files edited**: `git diff --name-only HEAD`
- **Active issues**: `ll-issues list --status in_progress` or frontmatter scan of `.issues/`
- **Loop state**: read `.ll/loops/` JSON files

## Files to Modify

- `hooks/hooks.json:89-100` — add second PreCompact entry
- `hooks/scripts/precompact-state.sh` — read-only reference for structure (do not modify)
- `hooks/scripts/lib/common.sh` — import only (`acquire_lock`, `release_lock`, `atomic_write_json`, `ll_config_value`, `ll_feature_enabled`, `to_epoch`, `get_mtime`)

## New Files

- `hooks/scripts/precompact-handoff.sh`

## References

- Related tests: FEAT-1157
- Docs/config updates: FEAT-1158
- Depends on: FEAT-1112 (fallback available without it)
- Consumers of `ll-continue-prompt.md`: `commands/resume.md:28-42`, `scripts/little_loops/subprocess_utils.py:31-58`, `hooks/scripts/context-monitor.sh:334-348`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1116 (hook-intent abstraction layer) is migrating PreCompact hooks from `hooks/scripts/` shell scripts to Python core handlers with thin per-host adapters. This issue adds a new shell script in the legacy layer FEAT-1116 is retiring. Implement `precompact-handoff.sh` as specified here for the MVP, but scope it to be replaced by — or restructured as — the Python core handler + Claude Code adapter pattern once FEAT-1116's PreCompact migration scaffolding is in place.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/precompact-handoff.sh` does not exist ✓
- `hooks/hooks.json` has no second PreCompact entry for handoff ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:15 - `82d256a6-9a99-40f5-8866-377a208de262.jsonl`

## Blocks

- FEAT-1157
- FEAT-1158
- FEAT-1264
- FEAT-1315

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The State Sources section specifies git diff/ll-issues/loops-JSON as the fallback approach — but does not acknowledge FEAT-1262's `.ll/ll-session-events.jsonl` as the richer primary source. If `.ll/ll-session-events.jsonl` is present and non-empty (i.e., FEAT-1262 has been shipping and running), prefer it as the primary source for the files-edited and decisions sections of the snapshot. Fall back to `git diff --name-only HEAD` and `ll-issues list` only when the JSONL is absent. FEAT-1264 (which formally integrates the event log) depends on this issue; this note ensures the fallback/primary distinction is documented in the implementation contract so FEAT-1264 doesn't need to re-explain the fallback semantics.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-11): This issue implements `precompact-handoff.sh` as a full-logic shell script. FEAT-1116 (Hook-Intent Abstraction Layer) will migrate PreCompact hooks to Python core handlers with thin per-host shell adapters. Implement the shell script as specified here for the MVP, but treat it as temporary: once FEAT-1116's PreCompact migration scaffolding lands, port the snapshot logic to a Python intent handler (e.g., `scripts/little_loops/hooks/pre_compact_handoff.py`) and replace `precompact-handoff.sh` with a thin Claude Code adapter that delegates to the Python handler. Do not embed new business logic in the shell script beyond what is required for the initial implementation.
