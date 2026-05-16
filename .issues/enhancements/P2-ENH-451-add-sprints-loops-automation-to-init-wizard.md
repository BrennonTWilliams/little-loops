---
type: ENH
id: ENH-451
title: Add sprints, loops, and automation sections to init interactive wizard
priority: P2
status: completed
created: 2026-02-22
resolved: 2026-02-22
---

# Add sprints, loops, and automation sections to init interactive wizard

## Summary

Three config-schema.json sections are completely absent from the init interactive wizard:

- **`sprints`**: `sprints_dir`, `default_timeout`, `default_max_workers` — users of `ll-sprint` must discover `/ll:configure` independently
- **`loops`**: `loops_dir` — users of `ll-loop` have no init-time configuration path
- **`automation`**: `timeout_seconds`, `max_workers`, `stream_output` — the sequential `ll-auto` counterpart to `parallel` is entirely skipped

## Current Behavior

The init interactive wizard covers `project`, `scan`, `issues` (partial), `parallel`, `context_monitor`, `sync`, `commands.confidence_gate`, and `product` configuration sections. Three sections in `config-schema.json` are entirely absent from the wizard:

- `sprints` section (`sprints_dir`, `default_timeout`, `default_max_workers`)
- `loops` section (`loops_dir`)
- `automation` section (`timeout_seconds`, `max_workers`, `stream_output`)

Users who want to configure these must discover `/ll:configure` independently after init completes.

## Expected Behavior

Users who select sprint management, FSM loops, or sequential automation during init can configure the key settings for those features without needing to separately run `/ll:configure`. At minimum, the completion message mentions these as configurable via `/ll:configure`.

## Motivation

New users following the wizard flow have no discovery path for sprints, loops, and sequential automation configuration. These are core automation capabilities of little-loops but are invisible during onboarding.

## Proposed Solution

Add these as options in Round 3's multi-select "Features" question, or as a new round. Since these are power-user features, the lightest approach would be:

1. Add "Sprint management", "FSM loops", and "Sequential automation (ll-auto)" as options in Round 3's feature multi-select
2. For each selected feature, add a follow-up question in Round 5 (or a new dynamic round) covering the key settings

Alternatively, mention these in the completion message as configurable via `/ll:configure`.

## Scope Boundaries

- **In scope**: Adding sprints, loops, and automation as selectable features in Round 3; adding follow-up questions in Round 5 for each selected feature; or mentioning them in the completion message
- **Out of scope**: Exposing all sub-fields (power-user settings like `p0_sequential`, `stream_subprocess_output` remain configure-only)

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — Round 3 feature multi-select (lines ~128-148); Round 5 dynamic questions (lines ~287-401)
- `skills/init/SKILL.md` — Summary display section (lines ~86-142); completion message
- `config-schema.json` — reference for sprints (lines ~522-546), loops (lines ~547-558), automation (lines ~118-152)

### Similar Patterns
- Existing Round 3 → Round 5 pattern for parallel, context_monitor, sync, confidence_gate features

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add "Sprint management", "FSM loops", "Sequential automation (ll-auto)" as options to Round 3 feature multi-select in `interactive.md`
2. Add conditional Round 5 questions for each new feature (sprints_dir, default_timeout for sprints; loops_dir for loops; timeout_seconds, max_workers for automation)
3. Update SKILL.md summary display to include sprints/loops/automation settings when configured
4. Update completion message to mention `/ll:configure` for remaining power-user settings
5. Verify Round 5 question count stays within 4-question limit (or applies overflow splitting from BUG-449 fix)

## Impact

- **Priority**: P2 — Config sections invisible during onboarding; users of sprint/loop features must discover configuration independently
- **Effort**: Medium — Extends existing Round 3 + Round 5 patterns; no structural changes
- **Risk**: Low — Additive feature questions; existing wizard flow unchanged when features not selected
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `interactive-wizard`, `sprints`, `loops`, `automation`

## Resolution

- Added **Round 3b: Automation Features Selection** to `skills/init/interactive.md` — a new always-run multi-select round with Sprint management, FSM loops, and Sequential automation (ll-auto) options
- Extended Round 5 ordered conditions list from 6 to 8 entries: added `sprints_workers` (condition 7) and `auto_timeout` (condition 8)
- Extended Round 5b to handle positions 5–8 (was 5–6), adding question templates for sprint default_max_workers and ll-auto timeout_seconds
- Added configuration snippets and notes for sprints and automation in the Round 5 config section
- Updated Interactive Mode Summary table to reflect Rounds 3a, 3b, and the extended 5b
- Added `[SPRINTS]`, `[LOOPS]`, and `[AUTOMATION]` sections to the Display Summary in `skills/init/SKILL.md`
- Added completion message next steps and `/ll:configure` mention for automation features

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:manage-issue enh implement ENH-451` - 2026-02-22

## Blocked By

- BUG-449

## Blocks

- ENH-452
- ENH-453
- ENH-454
- ENH-455
- ENH-456
- ENH-458
- ENH-460

---

## Status

**Open** | Created: 2026-02-22 | Priority: P2
