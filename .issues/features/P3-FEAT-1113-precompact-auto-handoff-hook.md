---
id: FEAT-1113
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
blocked_by: [FEAT-1112]
related: [ENH-152, ENH-495, FEAT-150]
---

# FEAT-1113: PreCompact Auto-Handoff Hook

## Summary

Trigger an implicit, priority-tiered handoff snapshot (≤2KB) automatically on Claude Code's PreCompact event, so long-running loops don't lose active files, tasks, and decisions when the context window compacts.

## Motivation

`/ll:handoff` today is a manual step users invoke when they remember to. Completed work already flagged the cost of missing it: BUG-866 (handoff complete state lost on restart), BUG-982 (handoff reminder silenced by stale prompt), ENH-495 (structured handoff with anchored summarization).

Context-mode (github.com/mksglu/context-mode) runs a PreCompact hook that builds a priority-tiered XML snapshot — active files, tasks, decisions — capped at 2KB, dropping lower-priority metadata if space is tight. This turns handoff from a skill you must remember into a guarantee.

## Current Behavior

- `/ll:handoff` is user-invoked or recommended by `context_monitor` at 40% threshold (see `.ll/ll-config.json:context_monitor.auto_handoff_threshold`)
- Missed handoffs silently continue as "success" (BUG-819, completed)
- Structured handoff ENH-495 landed but still runs on explicit invocation
- Claude Code exposes a PreCompact hook type we don't currently use

## Expected Behavior

- New `hooks/scripts/precompact-handoff.sh` registered as PreCompact in `hooks/hooks.json`
- Hook writes a tiered snapshot to `.ll/ll-continue-prompt.md` with sections ordered:
  1. Active issue + loop state (always kept)
  2. Files edited this session (always kept)
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- Total output capped at 2KB; priorities dropped LIFO until under cap
- Integrates with FEAT-1112 session store to pull file/loop/issue state without re-parsing
- Works alongside existing `/ll:handoff` skill — skill becomes a manual override that produces the richer version

## Acceptance Criteria

- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority-tier dropping tested with synthetic large inputs
- No duplicate handoff when user already ran `/ll:handoff` in same session (idempotency marker)
- Integration test verifies continuation prompt is picked up by SessionStart hook on next run
- CLAUDE.md / handoff docs updated

## References

- Inspiration: context-mode PreCompact snapshots
- Related (completed): ENH-152 persistent handoff reminder, FEAT-150 continuation prompt integration, ENH-495 structured handoff, BUG-819 missed handoff silently continues
- Depends on: FEAT-1112 unified session store (for efficient state reconstruction)
