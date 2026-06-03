---
id: ENH-1884
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T00:00:44Z"
discovered_by: capture-issue
relates_to: [ENH-1883, EPIC-1707]
---

# ENH-1884: Wire `analytics.enabled` into `/ll:init` and `/ll:configure` flows

## Summary

Neither `/ll:init` nor `/ll:configure` prompt for or write the `analytics` config block. New projects won't have analytics enabled unless the user manually edits `.ll/ll-config.json` (as ENH-1883 does for this project). The init and configure flows should offer to enable analytics, lowering the friction for new adopters of EPIC-1707 features.

## Current Behavior

Neither `/ll:init` nor `/ll:configure` prompts for or writes the `analytics` config block. New projects will not have analytics enabled until the user manually edits `.ll/ll-config.json`. There is no guided path to enable analytics during project initialization or reconfiguration.

## Motivation

ENH-1883 resolved the immediate gap by manually adding the `analytics` block to this project's config. But the root cause — that there's no guided path to enable analytics — remains. Any user who initializes a new project or reconfigures an existing one via `/ll:init` or `/ll:configure` will miss out on history.db features (corrections in refine-issue/ready-issue, ctx-stats, skill event tracking) until they discover the manual edit.

## Expected Behavior

- **`/ll:init`**: During project setup, after writing the base config, prompt: "Enable analytics (skill events, corrections, file events)? [Y/n]". If yes, write the full `analytics` block with `enabled: true` and default-inclusive capture settings.
- **`/ll:configure`**: When displaying or editing config, include an `analytics` section that shows current state and allows toggling `enabled` on/off, plus configuring which capture categories are active.

## Scope Boundaries

- **In scope**: Prompting for `analytics.enabled` during init; surfacing the flag in configure
- **Out of scope**: Adding new analytics infrastructure (ENH-1831–1835 done)
- **Out of scope**: Schema changes to `AnalyticsCaptureConfig`

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add analytics prompt step after base config is written
- `skills/configure/SKILL.md` (or relevant configure skill/command) — surface analytics section
- `templates/` — any project-type config templates that serve as the base for init should include the `analytics` block (commented or with `enabled: false` as default, to be flipped by the prompt)

### Dependent Files
- `scripts/little_loops/hooks/user_prompt_submit.py` — reads `analytics.enabled`
- `scripts/little_loops/hooks/post_tool_use.py` — reads `analytics.enabled`
- `.ll/ll-config.json` — destination for the written block

### Similar Patterns
- Other init prompts in `skills/init/SKILL.md` (e.g. prompting for test command, scan dirs) are the model to follow

### Tests
- N/A — skills are prompt-based; verify manually by running `/ll:init` in a scratch project

### Documentation
- N/A — no doc pages document the analytics block for end users yet (EPIC-1707 scope)

### Configuration
- `templates/` — project-type config templates used as the base for `/ll:init`

## Implementation Steps

1. Locate the init skill (`skills/init/SKILL.md`) and find where base config is written
2. Add a Y/n prompt for analytics after the config is written; if yes, merge in the standard analytics block
3. Locate the configure skill/command; add an `analytics` display/edit section alongside existing config sections
4. Update project-type config templates in `templates/` to include a commented-out analytics block so the structure is visible even when disabled
5. Manual verify: run `/ll:init` in a scratch project and confirm the analytics block appears in the generated `.ll/ll-config.json`

## Impact

- **Priority**: P4 — quality-of-life; ENH-1883 is the workaround for existing projects
- **Effort**: Small-medium — skill/command edits + template updates
- **Risk**: Low — additive; no behavior change for projects that already have the key set
- **Breaking Change**: No

## Labels

`analytics`, `init`, `configure`, `ux`, `captured`

## Status

**Open** | Created: 2026-06-03 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-06-03T00:02:41 - `9d48d4a7-c415-4554-9993-3036a70f17e9.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:00:44Z - `9351ec8d-8ce0-495b-85f9-95010ab64ced.jsonl`
