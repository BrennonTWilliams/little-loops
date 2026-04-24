---
id: FEAT-1263
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by: [FEAT-1156]
parent: FEAT-1159
related: [FEAT-1156, FEAT-1264, FEAT-1262]
---

# FEAT-1263: SessionStart Context Injector (`session-start-inject.sh`)

## Summary

Implement `hooks/scripts/session-start-inject.sh` as a SessionStart hook that reads `ll-continue-prompt.md` (when fresh) and outputs it as `additionalContext` JSON, injecting the handoff snapshot authoritatively into Claude's context on session resume — without requiring the user to run `/ll:resume`.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Motivation

The current resume flow is passive: `ll-continue-prompt.md` is a file Claude *can* read, not a directive Claude *receives*. After compaction, Claude typically asks the user to re-explain what they were doing. A SessionStart hook that outputs `additionalContext` makes context restoration authoritative — Claude receives a structured brief at session start, not a file reference.

## Acceptance Criteria

- `hooks/scripts/session-start-inject.sh` exists and is executable
- Hook fires on SessionStart and reads `.ll/ll-continue-prompt.md` if it exists
- Freshness check: only inject if prompt mtime is within `continuation.prompt_expiry_hours` (from `ll-config.json`; default 24h)
- Output format: valid `additionalContext` JSON as required by the Claude Code SessionStart hook protocol
- Injected content includes a `<continue_from>` directive plus the `## Intent`, `## Next Steps`, and `## File Modifications` sections from the prompt
- Hook marks the prompt as consumed (writes a `.ll/ll-session-injected` sentinel) to prevent re-injection within the same session
- Existing `/ll:resume` manual flow continues to work unchanged — if the prompt was already injected, `/ll:resume` is a no-op or notes "already injected"
- `TestSessionStartInject` class added to `scripts/tests/test_hooks_integration.py`
- `hooks/hooks.json` registers the script as a SessionStart entry

## Implementation

### New File: `hooks/scripts/session-start-inject.sh`

- Read stdin JSON, extract `source` field (detect `"compact"` source for priority injection)
- Source `hooks/scripts/lib/common.sh`
- Check `ll_feature_enabled` guard
- Check `.ll/ll-continue-prompt.md` exists and passes freshness check (`get_mtime` vs expiry window)
- Check `.ll/ll-session-injected` sentinel does not exist (idempotency)
- Parse `## Intent`, `## File Modifications`, `## Next Steps` sections from the prompt with awk/grep
- Build `additionalContext` output:
  ```json
  {"additionalContext": "<continue_from>\n## Intent\n...\n## Next Steps\n...\n</continue_from>"}
  ```
- Write `.ll/ll-session-injected` sentinel with timestamp
- On any failure (file missing, parse error), exit 0 silently — must not block session start

### Freshness Check

Use `get_mtime` from `lib/common.sh` on `.ll/ll-continue-prompt.md`. Compare against current time minus `continuation.prompt_expiry_hours` (from `ll_config_value`). Stale prompts are silently skipped.

### Idempotency

`.ll/ll-session-injected` sentinel file (timestamp only). Cleared at session end by `precompact-state.sh` or on next PreCompact event. Do not re-inject if sentinel is present and same-session.

### Registration: `hooks/hooks.json`

Add `session-start-inject.sh` to the SessionStart array.

### Tests: `TestSessionStartInject`

Add to `scripts/tests/test_hooks_integration.py`:
- Fresh prompt → injects `additionalContext` with `<continue_from>` directive
- Stale prompt (mtime > expiry) → no output, exits 0
- Missing prompt file → no output, exits 0
- Sentinel present → no output (idempotency)
- Malformed prompt → exits 0 (failure-safe)
- Compact-source SessionStart injects; non-compact source still injects if prompt is fresh (decide during implementation whether to filter on source)

### `/ll:resume` Compatibility

`commands/resume.md:28-42` reads `ll-continue-prompt.md` directly. This hook does not change that file. If `.ll/ll-session-injected` exists, `/ll:resume` should note "context already injected at session start" rather than re-displaying — update `commands/resume.md` to check the sentinel.

## Files to Modify

- `hooks/hooks.json` — add SessionStart entry for `session-start-inject.sh`
- `scripts/tests/test_hooks_integration.py` — add `TestSessionStartInject` class
- `commands/resume.md` — add sentinel check to avoid duplicate injection message

## New Files

- `hooks/scripts/session-start-inject.sh`
- `.ll/ll-session-injected` (runtime artifact, gitignored)

## Scope Boundary

This issue owns only the injection side. It does NOT modify how `ll-continue-prompt.md` is produced (FEAT-1156 and FEAT-1264 own that). It works with whatever snapshot format FEAT-1156 produces; FEAT-1264's richer format will automatically benefit injection once that issue lands.

FEAT-1116 risk: `session-start-inject.sh` is a SessionStart shell script in the layer FEAT-1116 is migrating. Implement as specified for unblocked delivery; plan follow-up to migrate to the adapter pattern.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/session-start-inject.sh` does not exist ✓
- No `session-start-inject.sh` entry in `hooks/hooks.json` ✓
- Blocked by FEAT-1156 (`ll-continue-prompt.md` must exist before injection) ✓
- Feature not yet implemented ✓

## References

- Parent: FEAT-1159
- Reads from: FEAT-1156 (`precompact-handoff.sh` → `ll-continue-prompt.md`)
- Richer input when available: FEAT-1264 (event-log-driven snapshot)
- Hook utilities: `hooks/scripts/lib/common.sh` (`get_mtime`, `ll_config_value`, `ll_feature_enabled`)
- Consumer compatibility: `commands/resume.md:28-42`, `scripts/little_loops/subprocess_utils.py:31-58`


## Session Log
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
