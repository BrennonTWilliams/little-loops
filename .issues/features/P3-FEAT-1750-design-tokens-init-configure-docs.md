---
id: FEAT-1750
title: Design-tokens init / configure UX and docs integration
status: open
priority: P3
type: FEAT
parent: EPIC-1751
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- config
- design-system
- init
- docs
relates_to:
- EPIC-1751
- FEAT-1747
- FEAT-1748
---

# FEAT-1750: Design-tokens init / configure UX and docs integration

## Summary

Wire design-token setup into `/ll:init` (new interactive round + materialization step) and `/ll:configure` (new `design_tokens` area), then write the accompanying docs and changelog entry. Depends on FEAT-1747 (schema/dataclass) and FEAT-1748 (template files must exist to be copied).

## Parent Issue
Decomposed from FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Current Behavior

`/ll:init` has no design-token setup round. `/ll:configure` has no `design_tokens` area. `docs/reference/CONFIGURATION.md` has no `design_tokens` section. Users who want design tokens must hand-edit `.ll/ll-config.json` and manually copy template files with no guided UX.

## Expected Behavior

`/ll:init` includes a new Round 7 (after document-tracking) that asks whether to initialize design tokens; on accept it materializes four token files from templates and writes the `design_tokens` block to config; on decline it sets `enabled: false`. `/ll:configure design_tokens` shows all six current field values and updates any that change. `docs/reference/CONFIGURATION.md` documents all six fields with types and defaults.

## Motivation

- Completes the design-token feature for end users: FEAT-1747 (infra), FEAT-1748 (palette), and FEAT-1749 (loop wiring) are all useless without a discoverable setup path
- `/ll:init` is the primary onboarding surface; a Round 7 ensures new users encounter design tokens by default rather than discovering them through docs
- Docs surface all six config fields so existing users can hand-configure without running init again

## Use Case

**Who**: A new ll user running `/ll:init` on a fresh project

**Context**: Going through the guided init flow for the first time

**Goal**: Accept or opt out of design tokens in one round without leaving the init flow

**Outcome**: On accept — four token files materialized at `.ll/design-tokens/` and `design_tokens` block written to config, ready for immediate use with built-in loops; on decline — `enabled: false` set, no files created, no friction

## Proposed Solution

### 1. `/ll:init` — `skills/init/interactive.md`

Add a new **Round 7** between current Round 6 (Document Tracking) and current Round 7 (Extended Config Gate):

```
Round 7: Design Tokens
  Question: "Initialize default design tokens at `.ll/design-tokens/`? (Y/n)"
  Sub-question on N: "Point at an existing design-tokens directory (leave blank to skip):"
  On Y: set design_tokens.enabled = true, design_tokens.path = ".ll/design-tokens"
  On custom path: set design_tokens.path = <entered path>
  On skip: set design_tokens.enabled = false
```

Bump the `TOTAL` counter and renumber all rounds after the new Round 7.

### 2. `/ll:init` — `skills/init/SKILL.md`

Add a new sub-step inside **Step 8** (mirror the `ll-goals-template.md` materialization at Step 8 item 5: Read template, Write to `.ll/`):

On accept (design_tokens.enabled = true, path = ".ll/design-tokens"):

```
Read  templates/design-tokens/primitives.json
Write .ll/design-tokens/primitives.json (skip-if-exists)

Read  templates/design-tokens/semantic.json
Write .ll/design-tokens/semantic.json (skip-if-exists)

Read  templates/design-tokens/themes/light.json
Write .ll/design-tokens/themes/light.json (skip-if-exists)

Read  templates/design-tokens/themes/dark.json
Write .ll/design-tokens/themes/dark.json (skip-if-exists)
```

Alternative: `Bash "mkdir -p .ll/design-tokens/themes && cp -r <plugin-root>/templates/design-tokens/* .ll/design-tokens/"` — resolving `<plugin-root>` follows the existing Codex hook adapter install precedent (Step 8.5).

Whichever approach: skip-if-exists, and write the `design_tokens` block to `.ll/ll-config.json`.

### 3. `/ll:configure` — `skills/configure/SKILL.md`

Five distinct update points within this file (follow the precedent set by the most recently added config area):

1. **Frontmatter `arguments[0].description`** pipe-separated list: add `design_tokens`
2. **Step 2 Area Mapping table**: add `design_tokens` row
3. **`--list` output display block**: add `design_tokens` entry
4. **Step 1 interactive menu chain** (paginated): add to the appropriate group
5. **`## Arguments` area description bullet list**: add `design_tokens` bullet

### 4. `/ll:configure` — `skills/configure/areas.md`

Add `## Area: design_tokens` section following the `## Area: documents` structure (closest structural match):

```markdown
## Area: design_tokens

### Current Values
- `enabled`: {{config.design_tokens.enabled}}
- `path`: {{config.design_tokens.path}}
- `primitives_file`: {{config.design_tokens.primitives_file}}
- `semantic_file`: {{config.design_tokens.semantic_file}}
- `themes_dir`: {{config.design_tokens.themes_dir}}
- `active_theme`: {{config.design_tokens.active_theme}}

### Round Questions
- "Enable design tokens? (current: {{config.design_tokens.enabled}})" [boolean]
- "Design tokens directory path (current: {{config.design_tokens.path}}):" [string]
- "Active theme (current: {{config.design_tokens.active_theme}}):" [string, e.g. light / dark]
```

### 5. Docs

**`docs/reference/CONFIGURATION.md`**:
- Add `### Design tokens` section (follow `### documents` or `### loops` heading + key table pattern).
- Add `design_tokens` block to the "Full Configuration Example" JSON at the top of the file.

**`docs/ARCHITECTURE.md`**:
- Note design tokens as a cross-cutting input to artifact-generating loops (one sentence under the artifact-loops paragraph).

**`docs/reference/API.md`**:
- Add `design_tokens | DesignTokensConfig` row to the `BRConfig #### Properties` table.

**README**:
- Single-line mention in the feature list.

### 6. Changelog entry

Add a changelog entry for this feature set (covering all four FEAT-1746 children) under the appropriate release section.

## Files to Modify

- `skills/init/interactive.md` — new Round 7, bump TOTAL, renumber subsequent rounds
- `skills/init/SKILL.md` — new Step 8 sub-step for template materialization
- `skills/configure/SKILL.md` — five update points
- `skills/configure/areas.md` — new `## Area: design_tokens` section
- `docs/reference/CONFIGURATION.md` — new section + full-example block
- `docs/ARCHITECTURE.md` — cross-cutting note
- `docs/reference/API.md` — `BRConfig` properties table row
- `CHANGELOG.md` (or equivalent)
- `README.md` — single-line feature mention

## Acceptance Criteria

- [ ] `/ll:init` prompts about design tokens after the document-tracking round and, on accept, materializes `.ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}` and writes `design_tokens` block to `.ll/ll-config.json`.
- [ ] `/ll:init` on decline sets `design_tokens.enabled: false` in config and creates no token files.
- [ ] `/ll:configure design_tokens` shows current values and updates any changed fields.
- [ ] `docs/reference/CONFIGURATION.md` documents all six `design_tokens` config fields with types and defaults.
- [ ] `docs/reference/API.md` `BRConfig` properties table includes the `design_tokens | DesignTokensConfig` row.
- [ ] README and ARCHITECTURE docs updated.

## Implementation Steps

1. Add Round 7 to `skills/init/interactive.md`; bump TOTAL counter and renumber all rounds after 7
2. Add Step 8 sub-step for template file materialization (skip-if-exists copy) to `skills/init/SKILL.md`
3. Update `skills/configure/SKILL.md` at all five points: frontmatter arguments description, Step 2 area mapping table, `--list` display block, interactive menu chain, `## Arguments` bullet list
4. Add `## Area: design_tokens` section to `skills/configure/areas.md` with Current Values and Round Questions
5. Update docs: add `### Design tokens` section + full-example block to `CONFIGURATION.md`; add one-sentence cross-cutting note to `ARCHITECTURE.md`; add `design_tokens | DesignTokensConfig` row to `API.md` `BRConfig` properties table; add single-line feature mention to `README.md`; add changelog entry covering all four FEAT-1746 children

## Impact

- **Priority**: P3 — final integration piece; depends on FEAT-1747 and FEAT-1748
- **Effort**: Medium — two skill files, one areas file, three docs, README, changelog; no new Python code
- **Risk**: Low — additive to existing init/configure flows; no breaking changes to current behavior
- **Breaking Change**: No

## Dependencies

- FEAT-1747 must be merged (schema/dataclass needed for configure UX).
- FEAT-1748 must be merged (template files must exist for init materialization).

## Session Log
- `/ll:format-issue` - 2026-05-27T20:25:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
