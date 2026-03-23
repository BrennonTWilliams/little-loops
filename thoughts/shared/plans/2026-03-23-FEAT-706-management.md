# FEAT-706: Hook Management Tooling — Implementation Plan

## Issue
Hook management tooling for target projects: show/install/validate modes for `/ll:configure hooks`.

## Files to Modify

1. **`skills/configure/SKILL.md`** — 6 targeted edits:
   - Line 10: Append `|hooks` to argument description
   - Line 59: Add `hooks` row to Area Mapping table
   - Line 85: Add `hooks` line to `--list` output block
   - Line 190: Update Batch 3 "More areas..." description
   - Lines 205–207: Add `hooks` option to Batch 4
   - Line 273: Add `hooks` bullet to Arguments list

2. **`skills/configure/areas.md`** — Append new `## Area: hooks` section after line 793 (EOF), following `allowed-tools` pattern

3. **`skills/init/SKILL.md`** — Insert Step 10.5 (Install Hooks) between Step 10 (line 427) and Step 11 (line 428); update Step 11 completion message

4. **`skills/init/interactive.md`** — Append Round 12 (Install Hooks) after Round 11 `---` separator (line 670); update Summary table

## Key Design Decisions

- **No `$CLAUDE_PLUGIN_ROOT` detection**: Use explicit `AskUserQuestion` for plugin vs CLAUDE.md loading (env var unreliable in Bash tool context)
- **`--yes` mode**: Always install to `.claude/settings.local.json` without prompting
- **Inline display in areas.md**: Follow `allowed-tools` pattern — no entry in `show-output.md`
- **Additive merge only**: Never overwrite existing non-ll hooks

## Phase Checkboxes

- [ ] Phase 1: Edit `skills/configure/SKILL.md`
- [ ] Phase 2: Append to `skills/configure/areas.md`
- [ ] Phase 3: Edit `skills/init/SKILL.md`
- [ ] Phase 4: Edit `skills/init/interactive.md`
- [ ] Phase 5: Verify (lint/type check)
- [ ] Phase 6: Complete issue
