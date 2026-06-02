---
id: FEAT-1750
title: Design-tokens init / configure UX and docs integration
status: done
priority: P3
type: FEAT
size: Very Large
parent: EPIC-1751
discovered_date: 2026-05-27
discovered_by: issue-size-review
decision_needed: false
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
confidence_score: 100
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify with Exact Anchors

| File | What to change | Key anchor |
|------|---------------|-----------|
| `skills/init/interactive.md` | Insert new Round 7 at line 469 (between Round 6 transition sentence and current `## Round 7: Extended Configuration Gate`); bump `TOTAL = 7` → `8`; rename current Round 7 → Round 8; renumber downstream round refs | Lines 13, 467–476 |
| `skills/init/SKILL.md` | Add new sub-step 6 after line 331 (after goals-template item 5); add `[write]` entry to dry-run preview at line 282 | Lines 282, 326–331 |
| `skills/configure/SKILL.md` | 5 update points — see table below | Lines 14, 105, 133, 238, 324 |
| `skills/configure/areas.md` | Append `## Area: design_tokens` after last area (`## Area: hooks`, ~line 841); model after `## Area: documents` (lines 437–480) | Line 841+ |
| `docs/reference/CONFIGURATION.md` | Add `### \`design_tokens\`` section (model: `### \`documents\`` at lines 452–477); add `design_tokens` block to Full Configuration Example JSON | Lines 154–157, 452–477 |
| `docs/ARCHITECTURE.md` | One-sentence cross-cutting note in artifact-loops paragraph | — |
| `docs/reference/API.md` | `design_tokens \| DesignTokensConfig` row **already exists** at line 113; add `#### DesignTokensConfig` sub-section after `#### CliConfig` (~line 162) | Lines 113, 162 |
| `README.md` | Single-line feature mention | — |
| `CHANGELOG.md` | Entry covering all four FEAT-1746 children | — |

#### `skills/configure/SKILL.md` — Five Update Points

| # | Line | What to add |
|---|------|------------|
| 1 | 14 | Append `\|design-tokens` to the pipe-delimited `arguments[0].description` value |
| 2 | 105 | Add `\| \`design-tokens\` \| \`design_tokens\` \| Design system token settings \|` row to area mapping table |
| 3 | 133 | Add `  design-tokens   [DEFAULT]    Design system token settings` to `--list` display block |
| 4 | 238 | Add to Page 3 or 4 of the interactive area selection menu (alongside `documents` group) |
| 5 | 324 | Append `  - \`design-tokens\` - Design system token settings` bullet to `## Arguments` list |

#### `DesignTokensConfig` Fields (from `scripts/little_loops/config/features.py:268–289`)

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `enabled` | `bool` | `True` | NOTE: default is `true`, not `false` — different from `documents` |
| `path` | `str` | `".ll/design-tokens"` | |
| `primitives_file` | `str` | `"primitives.json"` | |
| `semantic_file` | `str` | `"semantic.json"` | |
| `themes_dir` | `str` | `"themes"` | |
| `active_theme` | `str` | `"light"` | |

#### Template Files (already exist, from FEAT-1748)

- `templates/design-tokens/primitives.json`
- `templates/design-tokens/semantic.json`
- `templates/design-tokens/themes/light.json`
- `templates/design-tokens/themes/dark.json`

#### Python Infrastructure (already exists, from FEAT-1747)

- `scripts/little_loops/config/features.py:268` — `DesignTokensConfig` dataclass
- `scripts/little_loops/config/core.py:217–219` — BRConfig loads design_tokens; property at line 297–299
- `scripts/little_loops/design_tokens.py` — `DesignTokens` dataclass and `load_design_tokens()` function

### Dependent Files (Callers/Importers)

- `scripts/little_loops/config/core.py:217–219` — instantiates `DesignTokensConfig.from_dict()`
- `scripts/little_loops/design_tokens.py` — consumes `BRConfig.design_tokens` for token loading

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — imports and calls `load_design_tokens()` + `render_as_prompt_context()` at line 177; injects `design_tokens_context` into `fsm.context` at lines 181–183 (FEAT-1749 wiring — no change needed for FEAT-1750)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `load_design_tokens` at line 472; injects into resume path `fsm.context["design_tokens_context"]` at lines 479–481 (FEAT-1749 wiring — no change needed)
- `scripts/little_loops/hooks/session_start.py` — validates `design_tokens.enabled` and path existence at lines 178–189 for feature-flag warnings on session start (no change needed for FEAT-1750)
- `scripts/little_loops/config/__init__.py` — re-exports `DesignTokensConfig` in `__all__` (already complete from FEAT-1747 — no change needed)

### Similar Patterns

- `skills/configure/areas.md:437–480` — `## Area: documents` — exact structural model for new `## Area: design_tokens`
- `docs/reference/CONFIGURATION.md:452–477` — `### documents` section — model for new `### design_tokens` section
- `skills/init/SKILL.md:326–331` — goals-template materialization item 5 — model for design-tokens materialization item 6
- `skills/init/interactive.md:392–467` — Round 6 document tracking — structural model for new Round 7

### Tests

- `scripts/tests/test_design_tokens.py` — existing design token loading/resolution tests (no init/configure skill tests in test suite)
- `scripts/tests/test_config.py` — config parsing tests including DesignTokensConfig

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — `test_design_tokens_in_schema` at lines 136–151 verifies `config-schema.json` has all 6 fields; schema already correct from FEAT-1747 — probably fine
- `scripts/tests/test_hook_session_start.py` — `test_warns_design_tokens_enabled_without_path` at lines 213–216; no behavior change — probably fine
- `scripts/tests/test_ll_loop_program_md.py` — `test_design_tokens_context_injected_into_context` at lines 282–313; no behavior change — probably fine
- `scripts/tests/test_cli_loop_lifecycle.py` — `test_design_tokens_context_injected_via_cmd_resume` at lines 636–662; no behavior change — probably fine
- `scripts/tests/test_ll_logs_wiring.py`, `test_feat1504_doc_wiring.py`, `test_feat1625_doc_wiring.py`, `test_create_extension_wiring.py` — all assert `"Authorize all 26"` in `areas.md`; adding `## Area: design_tokens` is a config-area section, not a CLI tool entry, so count should be unchanged — verify post-implementation
- **NEW (must write)**: `scripts/tests/test_feat1750_doc_wiring.py` — doc-wiring test following the pattern in `test_enh1734_doc_wiring.py`; should assert:
  - `skills/init/interactive.md` contains `Round 7` section mentioning design tokens
  - `skills/init/SKILL.md` mentions `design-tokens` materialization in Step 8
  - `skills/configure/SKILL.md` contains `design_tokens` in area mapping table and argument list
  - `skills/configure/areas.md` contains `## Area: design_tokens`
  - `skills/configure/show-output.md` contains `## design_tokens --show`
  - `docs/reference/CONFIGURATION.md` contains `design_tokens` section
  - `docs/reference/API.md` contains `DesignTokensConfig` sub-section

### Documentation

- `docs/reference/CONFIGURATION.md` — main doc target
- `docs/reference/API.md` — `BRConfig` table already has `design_tokens` row; needs `#### DesignTokensConfig` sub-section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `--interactive` description under `/ll:init` at line 31 lists covered topics; low-priority, but "design tokens" could be added alongside "document tracking" to the topics list

## Files to Modify

- `skills/init/interactive.md` — new Round 7, bump TOTAL `7→8`, rename current Round 7→8 and renumber downstream
- `skills/init/SKILL.md` — new Step 8 sub-step 6 for template materialization; also update "6–7 rounds" → "7–8 rounds" at line 138; add design-tokens line to Step 12 completion message
- `skills/configure/SKILL.md` — five update points at lines 14, 105, 133, 238, 324
- `skills/configure/areas.md` — append `## Area: design_tokens` section (after `## Area: hooks`)
- `skills/configure/show-output.md` — append `## design_tokens --show` section with all 6 fields and defaults (model after `## documents --show` at line 90)
- `docs/reference/CONFIGURATION.md` — new `### design_tokens` section + full-example JSON block entry
- `docs/ARCHITECTURE.md` — cross-cutting note
- `docs/reference/API.md` — **BRConfig row already present**; add `#### DesignTokensConfig` sub-section only
- `CHANGELOG.md` (or equivalent)
- `README.md` — single-line feature mention

## Acceptance Criteria

- [ ] `/ll:init` prompts about design tokens after the document-tracking round and, on accept, materializes `.ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}` and writes `design_tokens` block to `.ll/ll-config.json`.
- [ ] `/ll:init` on decline sets `design_tokens.enabled: false` in config and creates no token files.
- [ ] `/ll:configure design_tokens` shows current values and updates any changed fields.
- [ ] `docs/reference/CONFIGURATION.md` documents all six `design_tokens` config fields with types and defaults.
- [x] `docs/reference/API.md` `BRConfig` properties table includes the `design_tokens | DesignTokensConfig` row. (**Already present at line 113** — added in FEAT-1747.) Add `#### DesignTokensConfig` sub-section with field table instead.
- [ ] README and ARCHITECTURE docs updated.

## Implementation Steps

1. **`skills/init/interactive.md`**: Insert new Round 7 at line 469 (between "After completing Round 6, proceed to Round 7" at line 467 and `## Round 7: Extended Configuration Gate` at line 469). Bump `TOTAL = 7` → `8` at line 13. Rename `## Round 7: Extended Configuration Gate` → `## Round 8: Extended Configuration Gate` and update all downstream cross-references (Rounds 8–10 → 9–11, Round 11 → 12, Round 12 → 13). Update the Interactive Mode Summary table caption from "6–7" to "7–8". Model new round structure after Round 6 document tracking (lines 392–467): transition sentence → `---` → `## Round 7: Design Tokens - MANDATORY, ALWAYS RUNS` → increment STEP → AskUserQuestion YAML → on-Y / on-N prose branches with config JSON shapes → transition to Round 8.
2. **`skills/init/SKILL.md`**: Add new item 6 after line 331 (after the goals-template item 5). Guard: only when `design_tokens.enabled: true` AND `.ll/design-tokens/` does not already exist. Read each of the four template files (`templates/design-tokens/primitives.json`, `semantic.json`, `themes/light.json`, `themes/dark.json`) and Write to `.ll/design-tokens/` (skip-if-exists). Track outcome: `DESIGN_TOKENS_CREATED=true`. Also add `[write] .ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}` to dry-run preview at line 282.
3. **`skills/configure/SKILL.md`**: Update five points — (1) line 14 append `|design-tokens`; (2) line 105 add table row; (3) line 133 add `--list` display row; (4) line 238 add to page 3/4 of interactive menu; (5) line 324 append bullet.
4. **`skills/configure/areas.md`**: Append `## Area: design_tokens` section after last area (`## Area: hooks`, ~line 841). Model after `## Area: documents` (lines 437–480): `### Current Values` block showing all 6 fields with `{{config.design_tokens.*}}` interpolation; `### Round 1 (3 questions)` with enable/path/active_theme AskUserQuestion YAML. Note: `enabled` defaults to `true` (unlike `documents`).
5. **`docs/reference/CONFIGURATION.md`**: Add `### \`design_tokens\`` section modeled after `### \`documents\`` (lines 452–477) — one-line summary, pipe table of all 6 fields with types/defaults, fenced JSON example. Add `design_tokens` block to Full Configuration Example JSON at lines 154–157 (after `"documents"` block).
6. **`docs/reference/API.md`**: `design_tokens | DesignTokensConfig` row already exists at line 113 — skip. Add `#### DesignTokensConfig` sub-section after `#### CliConfig` (~line 162), with a key/type/default/description table for all 6 fields (model after `CliConfig` table at lines 151–156).
7. **`docs/ARCHITECTURE.md`**: Add one-sentence cross-cutting note in the artifact-loops paragraph.
8. **`README.md`**: Single-line feature mention.
9. **`CHANGELOG.md`**: Entry covering all four FEAT-1746 children (FEAT-1747 infra, FEAT-1748 palette, FEAT-1749 loop wiring, FEAT-1750 UX/docs).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **`skills/configure/show-output.md`**: Append `## design_tokens --show` section after `## sync --show` (line 162). Model after `## documents --show` at line 90: show all 6 fields (`enabled`, `path`, `primitives_file`, `semantic_file`, `themes_dir`, `active_theme`) with their current config values and defaults.
11. **`skills/init/SKILL.md:138`**: Change "6–7 rounds" → "7–8 rounds" in the `### 5. Interactive Mode` paragraph (the range shifts because the new mandatory Round 7 raises the minimum from 6 to 7 and the conditional maximum from 7 to 8).
12. **`skills/init/SKILL.md` Step 12 completion message**: Add `Created: .ll/design-tokens/ (four design token files)` line guarded by `# Only show if DESIGN_TOKENS_CREATED=true`, mirroring the existing `Created: .ll/ll-goals.md` entry.
13. **`scripts/tests/test_feat1750_doc_wiring.py`**: Write new doc-wiring test following `test_enh1734_doc_wiring.py` pattern (read file as text, assert literal strings). Cover: Round 7 in `interactive.md`, design-tokens in `SKILL.md` Step 8, `design_tokens` in `configure/SKILL.md` table and argument list, `## Area: design_tokens` in `areas.md`, `## design_tokens --show` in `show-output.md`, `design_tokens` section in `CONFIGURATION.md`, `DesignTokensConfig` sub-section in `API.md`.

## Impact

- **Priority**: P3 — final integration piece; depends on FEAT-1747 and FEAT-1748
- **Effort**: Medium — two skill files, one areas file, three docs, README, changelog; no new Python code
- **Risk**: Low — additive to existing init/configure flows; no breaking changes to current behavior
- **Breaking Change**: No

## Dependencies

- FEAT-1747 must be merged (schema/dataclass needed for configure UX).
- FEAT-1748 must be merged (template files must exist for init materialization).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **Low test coverage for primary artifacts** (10/25 Test Coverage): All 10 modified files are markdown skill files with no automated unit tests. The doc-wiring test (`scripts/tests/test_feat1750_doc_wiring.py`) is a co-deliverable — implement tests first so each assertion acts as a completion gate for the corresponding file change.
- **Round renumbering sweep in `interactive.md`** (Breadth drag in Complexity 14/25): Inserting Round 7 requires renaming Rounds 7→8 through 12→13 across all downstream references, TOTAL counter, cross-reference prose, and the Interactive Mode Summary table. An off-by-one silently breaks the step-counter display. Work top-down and grep-verify each renamed round before moving on.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-27
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1756: Design tokens /ll:init Round 7 and materialization
- FEAT-1757: Design tokens /ll:configure area and show-output wiring
- FEAT-1758: Design tokens documentation, README, and changelog

## Session Log
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-05-27T23:00:00 - `8d8e66f0-d813-4ec6-ab52-6f97ac667a9d.jsonl`
- `/ll:wire-issue` - 2026-05-27T22:52:22 - `5a2c6f28-fb66-4948-ba95-e89448b3cdd7.jsonl`
- `/ll:refine-issue` - 2026-05-27T22:45:47 - `a2c651e2-36b6-4645-a115-fb6e284f5d1f.jsonl`
- `/ll:format-issue` - 2026-05-27T20:25:05 - `652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
