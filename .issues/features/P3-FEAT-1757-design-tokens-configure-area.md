---
id: FEAT-1757
title: Design tokens /ll:configure area and show-output wiring
status: open
priority: P3
type: FEAT
parent: FEAT-1750
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- config
- design-system
relates_to:
- FEAT-1750
- FEAT-1747
- EPIC-1751
---

# FEAT-1757: Design tokens /ll:configure area and show-output wiring

## Summary

Add a `design_tokens` area to `/ll:configure` by updating five points in `SKILL.md`, appending an `## Area: design_tokens` section to `areas.md`, and adding a `## design_tokens --show` section to `show-output.md`.

## Parent Issue
Decomposed from FEAT-1750: Design-tokens init / configure UX and docs integration

## Current Behavior

`/ll:configure` has no `design_tokens` area. Users who want to update token settings must hand-edit `.ll/ll-config.json`.

## Expected Behavior

`/ll:configure design_tokens` shows all six current field values (`enabled`, `path`, `primitives_file`, `semantic_file`, `themes_dir`, `active_theme`) and updates any that change.

## Proposed Solution

### 1. `skills/configure/SKILL.md` — five update points

Follow the precedent set by the most recently added config area:

| # | Line | What to add |
|---|------|------------|
| 1 | 14 | Append `\|design-tokens` to the pipe-delimited `arguments[0].description` value |
| 2 | 105 | Add `\| \`design-tokens\` \| \`design_tokens\` \| Design system token settings \|` row to area mapping table |
| 3 | 133 | Add `  design-tokens   [DEFAULT]    Design system token settings` to `--list` display block |
| 4 | 238 | Add to Page 3 or 4 of the interactive area selection menu (alongside `documents` group) |
| 5 | 324 | Append `  - \`design-tokens\` - Design system token settings` bullet to `## Arguments` list |

### 2. `skills/configure/areas.md` — new area section

Append `## Area: design_tokens` after the last area (`## Area: hooks`, ~line 841). Model after `## Area: documents` (lines 437–480):

```markdown
## Area: design_tokens

### Current Values
- `enabled`: {{config.design_tokens.enabled}}
- `path`: {{config.design_tokens.path}}
- `primitives_file`: {{config.design_tokens.primitives_file}}
- `semantic_file`: {{config.design_tokens.semantic_file}}
- `themes_dir`: {{config.design_tokens.themes_dir}}
- `active_theme`: {{config.design_tokens.active_theme}}

### Round 1 (3 questions)
- "Enable design tokens? (current: {{config.design_tokens.enabled}})" [boolean]
- "Design tokens directory path (current: {{config.design_tokens.path}}):" [string]
- "Active theme (current: {{config.design_tokens.active_theme}}):" [string, e.g. light / dark]
```

Note: `enabled` defaults to `true` (unlike `documents`).

### 3. `skills/configure/show-output.md` — new show section

Append `## design_tokens --show` after `## sync --show` (~line 162). Model after `## documents --show` at line 90. Show all 6 fields (`enabled`, `path`, `primitives_file`, `semantic_file`, `themes_dir`, `active_theme`) with their current config values and defaults.

### 4. `scripts/tests/test_feat1757_configure_wiring.py`

Doc-wiring test following `test_enh1734_doc_wiring.py` pattern. Assert:
- `skills/configure/SKILL.md` contains `design_tokens` in the area mapping table
- `skills/configure/SKILL.md` contains `design-tokens` in the arguments list
- `skills/configure/areas.md` contains `## Area: design_tokens`
- `skills/configure/show-output.md` contains `## design_tokens --show`

## Files to Modify

- `skills/configure/SKILL.md` — five update points at lines 14, 105, 133, 238, 324
- `skills/configure/areas.md` — append `## Area: design_tokens` section (after `## Area: hooks`)
- `skills/configure/show-output.md` — append `## design_tokens --show` section (after `## sync --show`)
- `scripts/tests/test_feat1757_configure_wiring.py` — new doc-wiring test (create)

## Key Anchors

- `skills/configure/SKILL.md:14` — pipe-delimited arguments description
- `skills/configure/SKILL.md:105` — area mapping table
- `skills/configure/SKILL.md:133` — `--list` display block
- `skills/configure/SKILL.md:238` — interactive area selection menu
- `skills/configure/SKILL.md:324` — `## Arguments` bullet list
- `skills/configure/areas.md:437–480` — `## Area: documents` (structural model)
- `skills/configure/areas.md:841+` — append point (after `## Area: hooks`)
- `skills/configure/show-output.md:90` — `## documents --show` (structural model)
- `skills/configure/show-output.md:162` — append point (after `## sync --show`)
- `DesignTokensConfig` fields (from `scripts/little_loops/config/features.py:268–289`):
  `enabled` (bool, default `True`), `path` (str, `".ll/design-tokens"`), `primitives_file` (str, `"primitives.json"`), `semantic_file` (str, `"semantic.json"`), `themes_dir` (str, `"themes"`), `active_theme` (str, `"light"`)

## Acceptance Criteria

- [ ] `/ll:configure design_tokens` is recognized and routed to the new area handler
- [ ] Area handler shows all six current field values and prompts for changes
- [ ] `--list` output includes `design-tokens` entry
- [ ] `areas.md` has a complete `## Area: design_tokens` section with all 6 fields
- [ ] `show-output.md` has `## design_tokens --show` section with all 6 fields
- [ ] `test_feat1757_configure_wiring.py` passes

## Dependencies

- FEAT-1747 (schema/dataclass) — must be merged
- Can run in parallel with FEAT-1756 (init round) and FEAT-1758 (docs)

## Session Log
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
