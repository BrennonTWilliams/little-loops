---
id: ENH-1884
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T00:00:44Z"
discovered_by: capture-issue
relates_to: [ENH-1883, EPIC-1707]
decision_needed: false
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
- `skills/init/interactive.md` — add Round 9 (analytics Y/n) between `## Round 8: Learning Tests` and the Extended Config Gate; update `TOTAL` counter from 9 → 10 in Progress Tracking Setup
- `skills/init/SKILL.md` — add `[ANALYTICS]` block to `### 6. Display Summary`; add analytics write rule to `### 8. Write Configuration` item 3 (following the `learning_tests` always-write policy)
- `skills/configure/SKILL.md` — add `analytics` row to `### 2. Area Mapping` table; add to `argument-hint` frontmatter; add to `## Mode: --list` output; add option to `### Step 1: Area Selection` paginated menus
- `skills/configure/areas.md` — add `## Area: analytics` section with Enable/Disable/Keep-current question (3-way, following `## Area: learning_tests` pattern)
- `skills/configure/show-output.md` — add `## analytics --show` section displaying `enabled` and `capture.*` fields (following `## context --show` pattern)

### Dependent Files (No Changes)
- `scripts/little_loops/hooks/user_prompt_submit.py` — reads `analytics.enabled` via `feature_enabled(config, "analytics.enabled")` at line 70 in `handle()`
- `scripts/little_loops/hooks/post_tool_use.py` — reads `analytics.enabled` via `feature_enabled(config, "analytics.enabled")` at line 151 in `handle()`
- `scripts/little_loops/config/features.py` — `feature_enabled()` at line 14; dot-path traversal function consumed by both hooks
- `.ll/ll-config.json` — destination for the written block (example at lines 51–59)

### Similar Patterns
- `skills/init/interactive.md` — `## Round 8: Learning Tests` — canonical pattern: both yes/no paths write to config (explicit `enabled: false` on opt-out); analytics should follow this same always-write policy
- `skills/init/interactive.md` — `## Round 4: Product Analysis` — simpler pattern: "No" omits section entirely (only use if we want analytics to be omit-on-no)
- `skills/configure/areas.md` — `## Area: learning_tests` — three-way Enable/Disable/Keep toggle, with `capture.*` sub-options; direct structural model for analytics area
- `skills/configure/show-output.md` — `## context --show` and `## documents --show` — boolean-enabled section display format with defaults shown

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1743_init_wiring.py` — **will break**: `TestFeat1743InitWiring.test_total_is_nine` asserts `"TOTAL = 9"` and `test_skill_md_round_count_updated` asserts `"8–9 rounds"` — both must be updated to `"TOTAL = 10"` and `"9–10 rounds"` [Agent 2 + 3 finding]
- `scripts/tests/test_feat1756_init_wiring.py` — **will break**: `TestFeat1756InitWiring.test_total_is_eight` (body asserts `"TOTAL = 9"`) and `test_skill_md_round_count_updated` asserts `"8–9 rounds"` — same pair of updates required [Agent 2 + 3 finding]
- `scripts/tests/test_enh1884_analytics_wiring.py` — **new file to create**: follow `test_feat1743_init_wiring.py` + `test_feat1743_configure_wiring.py` patterns; assert `"## Round 9: Analytics"` in `interactive.md`, `"TOTAL = 10"`, analytics row in configure SKILL.md, `"## Area: analytics"` in areas.md, `"## analytics --show"` in show-output.md [Agent 3 finding]
- Regression pattern: `scripts/tests/test_feat1743_init_wiring.py` — model for init wiring test class structure (4 assertions: round header, TOTAL counter, feature keyword in SKILL.md, round-range string)
- Regression pattern: `scripts/tests/test_feat1743_configure_wiring.py` — model for configure wiring test (3 classes: `TestConfigureSkillMd`, `TestConfigureAreasMd`, `TestConfigureShowOutputMd`)
- Regression pattern: `scripts/tests/test_enh1836_configure_scaffold_wiring.py` — model for configure areas.md scaffold materialization wiring

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:configure` section has a static pipe-separated enumeration of valid area argument values; `analytics` must be appended alongside `learning-tests` (which is also absent) [Agent 2 finding]
- N/A for conceptual analytics docs — no end-user analytics doc pages exist yet (EPIC-1707 scope)

### Configuration
- `templates/*.json` — **No changes needed**: all 9 project-type templates (`python-generic.json`, `generic.json`, `typescript.json`, `javascript.json`, `go.json`, `rust.json`, `java-maven.json`, `java-gradle.json`, `dotnet.json`) already contain `"analytics": { "enabled": false }` between `"product"` and `"context_monitor"` keys
- `config-schema.json` — analytics schema at lines 1340–1380; `enabled` default is `false`; `capture.*` fields (`skills: ["*"]`, `cli_commands: ["*"]`, `corrections: true`, `file_events: true`) default to permissive when absent

## Proposed Solution

Follow the `learning_tests` round pattern throughout: always write the analytics section regardless of yes/no (explicit opt-out recorded), use a Y/n AskUserQuestion in the init wizard, and add a three-way Enable/Disable/Keep toggle in configure.

**Init wizard** (`skills/init/interactive.md`):
- Add `## Round 9: Analytics` between `## Round 8: Learning Tests` and the Extended Config Gate round
- Prompt: "Enable analytics? Tracks skill events, corrections, and file ops into `.ll/history.db` for use by `/ll:ctx-stats` and context-aware features."
- Option A (Yes/Recommended): write `"analytics": { "enabled": true, "capture": { "skills": ["*"], "cli_commands": ["*"], "corrections": true, "file_events": true } }`
- Option B (No): write `"analytics": { "enabled": false }` (explicit opt-out always written, matching `learning_tests` policy)
- Increment `TOTAL` from 9 → 10

**Init skill** (`skills/init/SKILL.md`):
- `### 6. Display Summary`: add `[ANALYTICS]` conditional block showing `analytics.enabled: true` when opted in
- `### 8. Write Configuration` item 3: add rule — always include the analytics section (with or without `capture` sub-object depending on yes/no)

**Configure skill** (`skills/configure/`):
- `SKILL.md` `### 2. Area Mapping`: add `| analytics | analytics | Analytics capture: enabled, skills, corrections, file_events |`
- `areas.md`: add `## Area: analytics` with three-way Enable/Disable/Keep-current question (follow `## Area: learning_tests`)
- `show-output.md`: add `## analytics --show` block listing `enabled`, `capture.skills`, `capture.cli_commands`, `capture.corrections`, `capture.file_events` with defaults (follow `## context --show`)

**Templates**: No changes. All 9 templates already have `"analytics": { "enabled": false }`.

## Acceptance Criteria

- [ ] Running `/ll:init` on a new project presents an analytics prompt (Round 9) in the wizard
- [ ] Selecting "Yes" writes `"analytics": { "enabled": true, "capture": { ... } }` to `.ll/ll-config.json`
- [ ] Selecting "No" writes `"analytics": { "enabled": false }` (explicit opt-out, section not omitted)
- [ ] Running `/ll:configure analytics` opens an Enable/Disable/Keep-current toggle
- [ ] Running `/ll:configure analytics --show` displays all analytics fields with current values and defaults
- [ ] Running `/ll:configure --list` shows `analytics` in the area list with `[CONFIGURED]` or `[DEFAULT]` status
- [ ] Post-init: the two hook consumers (`post_tool_use.py`, `user_prompt_submit.py`) behave correctly based on the written value (no code changes to hooks required)

## Implementation Steps

1. **`skills/init/interactive.md`** — after `## Round 8: Learning Tests`, insert `## Round 9: Analytics` using the same AskUserQuestion structure; update `TOTAL` counter in Progress Tracking Setup from 9 to 10; add analytics row to Interactive Mode Summary table
2. **`skills/init/SKILL.md`** — in `### 6. Display Summary`, add `[ANALYTICS] # Only show if enabled` block; in `### 8. Write Configuration` item 3, add: "Always include `analytics` section with `enabled: true/false` based on Round 9 selection (and full `capture` sub-object when yes)"
3. **`skills/configure/SKILL.md`** — add `analytics` to `### 2. Area Mapping` table; add to `argument-hint` frontmatter; add to `## Mode: --list` block; add `analytics` option to page 4 of `### Step 1: Area Selection` paginated menus
4. **`skills/configure/areas.md`** — append `## Area: analytics` section at end; three-way question (Enable / Disable / Keep current `{{config.analytics.enabled}}`); add sub-questions for `capture.*` fields when enabling (optional, follow `learning_tests` sub-option pattern)
5. **`skills/configure/show-output.md`** — append `## analytics --show` section; list all fields from `config-schema.json` lines 1340–1380 with schema defaults; follow `## context --show` pattern (fenced code block), NOT `## learning_tests --show` (missing opening fence)
6. **`docs/reference/COMMANDS.md`** — add `analytics` to the `### /ll:configure` area argument enumeration (pipe-separated list); also add `learning-tests` which is missing from the same list [wiring pass finding]
7. **Manual verify**: run `/ll:init` in a scratch project, choose "Yes" for analytics, confirm block appears in `.ll/ll-config.json`; run `/ll:configure analytics --show` in this project to confirm display

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_feat1743_init_wiring.py` — change `TestFeat1743InitWiring.test_total_is_nine` assertion from `"TOTAL = 9"` → `"TOTAL = 10"` and `test_skill_md_round_count_updated` from `"8–9 rounds"` → `"9–10 rounds"` (tests will fail otherwise)
9. Update `scripts/tests/test_feat1756_init_wiring.py` — same two assertion updates (`test_total_is_eight` body and `test_skill_md_round_count_updated`)
10. Create `scripts/tests/test_enh1884_analytics_wiring.py` — new regression test; class `TestEnh1884InitWiring` (4 assertions against interactive.md + SKILL.md) and `TestEnh1884ConfigureWiring` (3 sub-classes covering SKILL.md, areas.md, show-output.md); follow `test_feat1743_init_wiring.py` + `test_feat1743_configure_wiring.py` patterns exactly

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
- `/ll:wire-issue` - 2026-06-03T01:15:30 - `8ec4fac1-2d16-4aea-837a-70e1536cd194.jsonl`
- `/ll:refine-issue` - 2026-06-03T01:10:48 - `3a0b09f9-ee68-4e79-af7f-259373dea049.jsonl`
- `/ll:format-issue` - 2026-06-03T00:02:41 - `9d48d4a7-c415-4554-9993-3036a70f17e9.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:00:44Z - `9351ec8d-8ce0-495b-85f9-95010ab64ced.jsonl`
