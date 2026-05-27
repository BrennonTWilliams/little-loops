---
id: FEAT-1757
title: Design tokens /ll:configure area and show-output wiring
status: done
priority: P3
type: FEAT
parent: FEAT-1750
discovered_date: 2026-05-27
completed_at: 2026-05-27 23:40:58+00:00
discovered_by: issue-size-review
decision_needed: false
labels:
- feat
- config
- design-system
relates_to:
- FEAT-1750
- FEAT-1747
- EPIC-1751
confidence_score: 90
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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
- `docs/reference/COMMANDS.md` — append `design-tokens` to area argument list at line 42
- `scripts/tests/test_feat1757_configure_wiring.py` — new doc-wiring test (create)

## Integration Map

### Files to Modify
- `skills/configure/SKILL.md` (368 lines) — five named update points; all append after the current last entry (`hooks`)
- `skills/configure/areas.md` (939 lines) — append `## Area: design_tokens` after line 939 (end of file)
- `skills/configure/show-output.md` (176 lines) — append `## design_tokens --show` after line 176 (end of file)

### New Files to Create
- `scripts/tests/test_feat1757_configure_wiring.py` — doc-wiring regression test

### Similar Tests/Patterns (Follow These)
- `scripts/tests/test_feat1756_init_wiring.py` — sibling test for `design_tokens` in init skill; use OR-pattern: `assert "design_tokens" in content or "design-tokens" in content`
- `scripts/tests/test_feat1625_doc_wiring.py:44-55` — already declares a `CONFIGURE_AREAS` constant pointing at `skills/configure/areas.md`; shows multi-class-per-surface pattern
- `scripts/tests/test_enh1734_doc_wiring.py` — canonical doc-wiring template (212 lines): `PROJECT_ROOT = Path(__file__).parent.parent.parent`, one class per file surface, one `assert` per test method

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `area` argument enumeration at line 42 lists 13 areas; `design-tokens` is absent and will be stale after FEAT-1757 ships [Agent 2 finding]

### Config System (Read-Only, No Changes Needed)
- `scripts/little_loops/config/features.py:268-289` — `DesignTokensConfig` dataclass (all 6 fields + defaults)
- `scripts/little_loops/config/core.py:217-219` — `BRConfig` loads `design_tokens` block
- `scripts/little_loops/config/core.py:296-299` — `BRConfig.design_tokens` property
- `scripts/little_loops/config/core.py:575-582` — `BRConfig.to_dict()` serializes `design_tokens`

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current file state (SKILL.md: 368 lines, areas.md: 939 lines, show-output.md: 176 lines):_

**Corrected SKILL.md positions** (issue line numbers are approximations):
- Line 14: pipe-delimited description — **accurate**
- "Line 105" (area mapping table): `hooks` row is at **line 113** (table spans lines 99–113)
- "Line 133" (--list block): block spans **lines 125–145**; `hooks` is last entry at ~line 140
- "Line 238" (interactive menus): pages span **lines 196–264**; page 4 ends at line 264 with `hooks` at line 263
- "Line 324" (arguments list): list spans **lines 318–331**; `hooks` bullet at **line 331**

**Interactive menu page 4 overflow — design change required:**
Page 4 currently has exactly 4 options (`context`, `prompt`, `allowed-tools`, `hooks`) — at max capacity (`AskUserQuestion` supports at most 4 options). Adding `design-tokens` requires one of:
- Restructuring Page 4 to move `hooks` to a new Page 5, then add `design-tokens` on Page 4
- Or moving `design-tokens` onto Page 3 (which currently has 3 named areas + "More"), displacing some other area

**areas.md corrected append point:**
- File is **939 lines** total; `## Area: hooks` begins at line 840 and ends at line 939
- Append `## Area: design_tokens` after line 939 (end of file)

**show-output.md corrected append point:**
- File is **176 lines** total; `## sync --show` heading is at line 162 but the section ends at line 176
- Append `## design_tokens --show` after line 176 (end of file)

**Round 2 gap — 3 fields not covered by proposed Round 1:**
The proposed Round 1 covers `enabled`, `path`, `active_theme` (3 of 6). The remaining fields `primitives_file`, `semantic_file`, `themes_dir` have no round. Add a `### Round 2 (3 questions)` block for these file-path settings, following the same `AskUserQuestion` pattern as Round 1 (keep/change options for each).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/COMMANDS.md` — append `design-tokens` to the `area` argument enumeration at line 42 (current value ends with `hooks`; append `| design-tokens`)

## Acceptance Criteria

- [x] `/ll:configure design_tokens` is recognized and routed to the new area handler
- [x] Area handler shows all six current field values and prompts for changes
- [x] `--list` output includes `design-tokens` entry
- [x] `areas.md` has a complete `## Area: design_tokens` section with all 6 fields
- [x] `show-output.md` has `## design_tokens --show` section with all 6 fields
- [x] `test_feat1757_configure_wiring.py` passes

## Dependencies

- FEAT-1747 (schema/dataclass) — must be merged
- Can run in parallel with FEAT-1756 (init round) and FEAT-1758 (docs)

## Session Log
- `/ll:ready-issue` - 2026-05-27T23:36:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdf71221-6071-432b-bbc4-72085ee3754e.jsonl`
- `/ll:confidence-check` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a3bf84b-0618-4238-b6f3-19ba2f11ad0f.jsonl`
- `/ll:wire-issue` - 2026-05-27T23:31:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/abbb0cb3-8584-4f07-b7ef-bf61d783adb6.jsonl`
- `/ll:refine-issue` - 2026-05-27T23:26:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04d2ea8a-a459-4950-b030-01540e95e237.jsonl`
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
