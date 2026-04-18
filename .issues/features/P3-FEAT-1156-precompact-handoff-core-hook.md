---
id: FEAT-1156
type: FEAT
priority: P3
status: wont_do
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by: [FEAT-1112]
parent: FEAT-1113
related: [ENH-152, ENH-495, FEAT-150, FEAT-1157, FEAT-1158]
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
