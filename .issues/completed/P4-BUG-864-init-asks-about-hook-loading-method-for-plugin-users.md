---
discovered_date: 2026-03-23T00:00:00Z
discovered_by: user-report
confidence_score: 100
outcome_confidence: 100
---

# BUG-864: `/ll:init` asks about hook loading method even for plugin users

## Summary

`/ll:init` always prompted the user to select a hook loading method ("Via CLAUDE.md" vs "As a registered Claude Code plugin") during Step 10.5 and interactive Round 12. For users who installed little-loops as a registered Claude Code plugin, hooks are already active via the plugin system — the question is irrelevant and confusing.

## Location

- **File**: `skills/init/SKILL.md` — Step 10.5 ("Install Hooks")
- **File**: `skills/init/interactive.md` — Round 12 ("Install Hooks")

## Current Behavior

During non-`--yes` init, Step 10.5 presented an `AskUserQuestion` with three options:
1. "Via CLAUDE.md (install hooks)" — merged hook entries into a settings file
2. "As a registered Claude Code plugin (skip)" — no-op
3. "Skip" — deferred to `/ll:configure hooks install`

During interactive mode, Round 12 always ran as the final wizard step with the same question.

## Expected Behavior

No hook installation question at all. Plugin users already have hooks active; the CLAUDE.md loading path is a legacy/non-standard setup that shouldn't be surfaced during normal init.

## Steps to Reproduce

1. Have little-loops installed as a Claude Code plugin
2. Run `/ll:init` in any project
3. Observe "Hook Loading Method" question during Step 10.5

## Resolution

Removed Step 10.5 entirely from `skills/init/SKILL.md` — the `AskUserQuestion`, merge logic, and `HOOKS_INSTALLED` tracking are gone.

Removed Round 12 entirely from `skills/init/interactive.md`. Updated the wizard summary table (Round 12 row removed) and total round count (`6–7` → `5–6`). Added a comment to the `TOTAL` progress tracker noting hooks are always active via the plugin system.

Cleaned up downstream references:
- Removed `Updated: .claude/settings.json (added ll- hooks)` line from the Step 11 completion message
- Removed `9. Configure hooks: /ll:configure hooks` from the next-steps list

## Impact

- **Priority**: P4 - UX friction; confusing question for all plugin users
- **Effort**: Small — file edits only, no code changes
- **Risk**: None — removes a no-op path for plugin users; CLAUDE.md loading is unsupported going forward
- **Breaking Change**: No

## Labels

`bug`, `init`, `ux`, `hooks`

## Status

**Resolved** | Created: 2026-03-23 | Resolved: 2026-03-23 | Priority: P4
