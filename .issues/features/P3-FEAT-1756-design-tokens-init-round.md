---
id: FEAT-1756
title: Design tokens /ll:init Round 7 and materialization
status: done
priority: P3
type: FEAT
parent: FEAT-1750
discovered_date: 2026-05-27
completed_at: 2026-05-27 23:19:18+00:00
discovered_by: issue-size-review
labels:
- feat
- init
- design-system
relates_to:
- FEAT-1750
- FEAT-1747
- FEAT-1748
- EPIC-1751
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1756: Design tokens /ll:init Round 7 and materialization

## Summary

Add a new Round 7 (Design Tokens) to `/ll:init`'s interactive flow and wire the template-materialization step into SKILL.md so that users can accept or decline design token setup during guided project initialization.

## Parent Issue
Decomposed from FEAT-1750: Design-tokens init / configure UX and docs integration

## Current Behavior

`/ll:init` has no design-token setup round. Users who want design tokens must hand-edit `.ll/ll-config.json` and manually copy template files.

## Expected Behavior

`/ll:init` includes a new Round 7 (after document-tracking, before Extended Config Gate) that asks whether to initialize design tokens. On accept: materializes four token files from templates and writes the `design_tokens` block to config. On decline: sets `enabled: false`. Round numbering throughout `interactive.md` is updated accordingly.

## Proposed Solution

### 1. `skills/init/interactive.md`

Insert new **Round 7** at line 469 (between current Round 6 transition sentence and `## Round 7: Extended Configuration Gate`):

```
Round 7: Design Tokens — MANDATORY, ALWAYS RUNS
  Question: "Initialize default design tokens at `.ll/design-tokens/`? (Y/n)"
  Sub-question on N: "Point at an existing design-tokens directory (leave blank to skip):"
  On Y: set design_tokens.enabled = true, design_tokens.path = ".ll/design-tokens"
  On custom path: set design_tokens.path = <entered path>
  On skip: set design_tokens.enabled = false
```

Model after Round 6 document tracking (lines 392–467): transition sentence → `---` → `## Round 7: Design Tokens - MANDATORY, ALWAYS RUNS` → increment STEP → AskUserQuestion YAML → on-Y / on-N prose branches with config JSON shapes → transition to Round 8.

Bump `TOTAL = 7` → `8` at line 13.

Rename current `## Round 7: Extended Configuration Gate` → `## Round 8: Extended Configuration Gate` and update all downstream cross-references (Rounds 8–10 → 9–11, Round 11 → 12, Round 12 → 13). Update the Interactive Mode Summary table caption from "6–7" to "7–8".

### 2. `skills/init/SKILL.md` — materialization sub-step

Add new item 6 after line 331 (after the goals-template item 5):

Guard: only when `design_tokens.enabled: true` AND `.ll/design-tokens/` does not already exist.

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

Track outcome: `DESIGN_TOKENS_CREATED=true`.

Add `[write] .ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}` to dry-run preview at line 282.

### 3. `skills/init/SKILL.md` — round count and completion message

- Line 138: Change "6–7 rounds" → "7–8 rounds" in `### 5. Interactive Mode` paragraph.
- Step 12 completion message: Add `Created: .ll/design-tokens/ (four design token files)` line guarded by `# Only show if DESIGN_TOKENS_CREATED=true`, mirroring the existing `Created: .ll/ll-goals.md` entry.

### 4. `scripts/tests/test_feat1756_init_wiring.py`

Doc-wiring test following `test_enh1734_doc_wiring.py` pattern. Assert:
- `skills/init/interactive.md` contains `## Round 7:` with design tokens content
- `skills/init/interactive.md` contains `TOTAL = 8`
- `skills/init/SKILL.md` mentions `design-tokens` or `design_tokens` in the Step 8 materialization block
- `skills/init/SKILL.md` contains `7–8 rounds`

## Files to Modify

- `skills/init/interactive.md` — new Round 7, TOTAL 7→8, renumber Rounds 7-12 → 8-13
- `skills/init/SKILL.md` — materialization sub-step, round count "6-7"→"7-8", completion message
- `scripts/tests/test_feat1756_init_wiring.py` — new doc-wiring test (create)

## Key Anchors

- `skills/init/interactive.md:13` — `TOTAL = 7` (bump to 8)
- `skills/init/interactive.md:467–476` — insert new Round 7 here; current Round 7 becomes Round 8
- `skills/init/SKILL.md:138` — "6–7 rounds"
- `skills/init/SKILL.md:282` — dry-run preview block
- `skills/init/SKILL.md:326–331` — goals-template item 5 (new item 6 goes after)
- Template files (from FEAT-1748, already exist):
  - `templates/design-tokens/primitives.json`
  - `templates/design-tokens/semantic.json`
  - `templates/design-tokens/themes/light.json`
  - `templates/design-tokens/themes/dark.json`

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — new Round 7 block, TOTAL 7→8, renumber all downstream rounds and table
- `skills/init/SKILL.md` — materialization item 6, `"6–7 rounds"` → `"7–8 rounds"`, dry-run preview entry, completion message line
- `scripts/tests/test_feat1756_init_wiring.py` — new doc-wiring test file (create)

### All Cross-References Requiring Update in `interactive.md`

_Added by `/ll:refine-issue` — based on codebase analysis:_

| Line | Current Text | Must Become |
|------|-------------|-------------|
| 13 | `TOTAL = 7     # Working total (mandatory rounds: 1, 2, 3a, 4, 6, 11, 12)` | `TOTAL = 8     # Working total (mandatory rounds: 1, 2, 3a, 4, 6, 7, 11, 12)` |
| 17 | `# Round 7 is silent (advanced settings always skipped)` | `# Round 8 is silent (advanced settings always skipped)` |
| 229 | `# Rounds 11 (Allowed Tools) and 12 (CLAUDE.md Docs) are always shown — already counted in TOTAL = 7` | `# Rounds 12 (Allowed Tools) and 13 (CLAUDE.md Docs) are always shown — already counted in TOTAL = 8` |
| 467 | `**After completing Round 6, proceed to Round 7 (Extended Config Gate).**` | `**After completing Round 6, proceed to Round 7 (Design Tokens).** [new Round 7 block here] **After completing Round 7, proceed to Round 8 (Extended Config Gate).**` |
| 469 | `## Round 7: Extended Configuration Gate (Auto-Skipped)` | `## Round 8: Extended Configuration Gate (Auto-Skipped)` |
| 474 | `Proceed to Round 11 (Allowed Tools). Rounds 8–10 are never shown during init.` | `Proceed to Round 12 (Allowed Tools). Rounds 9–11 are never shown during init.` |
| 477 | `## Round 8: Project Advanced (Optional)` | `## Round 9: Project Advanced (Optional)` |
| 545 | `## Round 9: Continuation Behavior (Optional)` | `## Round 10: Continuation Behavior (Optional)` |
| 596 | `## Round 10: Prompt Optimization (Optional)` | `## Round 11: Prompt Optimization (Optional)` |
| 636 | `## Round 11: Allowed Tools — ALWAYS RUNS` | `## Round 12: Allowed Tools — ALWAYS RUNS` |
| 703 | `## Round 12: CLAUDE.md Documentation — ALWAYS RUNS` | `## Round 13: CLAUDE.md Documentation — ALWAYS RUNS` |
| 754 | `Total interaction rounds: 6–7 (7 only if parallel processing selected)` | `Total interaction rounds: 7–8 (8 only if parallel processing selected)` |
| 764 | `\| 7 \| Extended Config Gate \| Silent — always skips… \|` | Insert new `\| **7** \| **Design Tokens** \| **design_tokens (enabled/path)** \| **Always** \|` row before renaming old row to 8 |
| 765–769 | Rows for Rounds 8–12 | Renumber to Rounds 9–13 |

### Config JSON Shapes for Round 7 (Design Tokens)

_Added by `/ll:refine-issue` — based on `DesignTokensConfig` in `scripts/little_loops/config/features.py`:_

**On "Yes" (accept default path):**
```json
{"design_tokens": {"enabled": true, "path": ".ll/design-tokens"}}
```

**On custom path entered:**
```json
{"design_tokens": {"enabled": true, "path": "<entered-path>"}}
```

**On "No" / skip:**
```json
{"design_tokens": {"enabled": false}}
```

### Dependent Files (read-only, no change needed)
- `scripts/little_loops/config/features.py` — `DesignTokensConfig` dataclass (six fields: `enabled`, `path`, `primitives_file`, `semantic_file`, `themes_dir`, `active_theme`)
- `scripts/little_loops/config/core.py` — `BRConfig.design_tokens` property wired
- `config-schema.json:1203–1240` — JSON Schema for the `design_tokens` block

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1401_doc_wiring.py` — `TestInitInteractiveProductRound::test_total_is_seven` asserts `"TOTAL = 7"` in `interactive.md`; **will break** after FEAT-1756 bumps to `TOTAL = 8` — update assertion to `"TOTAL = 8"` and revise the failure message from "adding mandatory Round 4" to "after adding mandatory Round 7 (design tokens)" [Agent 2+3 finding]

### Test Pattern References
- `scripts/tests/test_enh1734_doc_wiring.py` — primary model: `PROJECT_ROOT` constant, one pytest class per file, one method per assertion, no fixtures
- `scripts/tests/test_feat1625_doc_wiring.py` — precedent for `skills/init/SKILL.md` assertions; uses `count()` when a token must appear in multiple places

### Templates (from FEAT-1748, confirmed present)
- `templates/design-tokens/primitives.json` ✓
- `templates/design-tokens/semantic.json` ✓
- `templates/design-tokens/themes/light.json` ✓
- `templates/design-tokens/themes/dark.json` ✓

## Implementation Steps

_Added by `/ll:refine-issue` — concrete steps with file and line references:_

1. **`interactive.md:13`** — Change `TOTAL = 7` to `TOTAL = 8`; update parenthetical comment to list Round 7 (design tokens) and note Round 8 (not 7) is silent
2. **`interactive.md:17`** — Change `# Round 7 is silent` → `# Round 8 is silent`
3. **`interactive.md:229`** — Change `TOTAL = 7` → `TOTAL = 8`; Rounds `11`/`12` → `12`/`13`
4. **`interactive.md:467`** — Change transition sentence to "proceed to Round 7 (Design Tokens)"; after it insert the full new Round 7 block (separator, heading, STEP increment, AskUserQuestion YAML, on-Y/on-N branches, transition to Round 8) following the Round 6 structural template at lines 392–467
5. **`interactive.md:469`** — Rename `## Round 7: Extended Configuration Gate (Auto-Skipped)` → `## Round 8:` and update its body: line 474 change `Round 11 (Allowed Tools). Rounds 8–10` → `Round 12 (Allowed Tools). Rounds 9–11`
6. **`interactive.md:477,545,596,636,703`** — Rename round headings +1 (Rounds 8→9, 9→10, 10→11, 11→12, 12→13)
7. **`interactive.md:754`** — Update caption from `6–7 (7 only if…)` → `7–8 (8 only if…)`
8. **`interactive.md:764`** — Insert new `| **7** | **Design Tokens** | **design_tokens (enabled/path)** | **Always** |` row; rename old row 7 → 8 and body text `Rounds 8–10` → `Rounds 9–11`; renumber rows 8→9, 9→10, 10→11, 11→12, 12→13
9. **`SKILL.md:138`** — Change `"6–7 rounds"` → `"7–8 rounds"`
10. **`SKILL.md:283`** — Add `[write]  .ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}  # Only if design tokens enabled and dir absent` after the `[write] .ll/ll-goals.md` line
11. **`SKILL.md:332`** — Add item 6 after end of item 5 (goals template), following the same `If enabled AND dir absent → Read template → Write → Skip silently if exists → Track outcome: DESIGN_TOKENS_CREATED=true` shape
12. **`SKILL.md:643`** — Add `Created: .ll/design-tokens/ (four design token files)  # Only show if DESIGN_TOKENS_CREATED=true` after the `CODEX_HOOKS_INSTALLED` completion line
13. **Create `scripts/tests/test_feat1756_init_wiring.py`** — one class `TestFeat1756InitWiring`, four methods asserting: `"## Round 7: Design Tokens"` in interactive.md, `"TOTAL = 8"` in interactive.md, `"design_tokens"` or `"design-tokens"` in SKILL.md Step 8 block, `"7–8 rounds"` in SKILL.md; run with `python -m pytest scripts/tests/test_feat1756_init_wiring.py -v`
14. **Update `scripts/tests/test_enh1401_doc_wiring.py`** — `TestInitInteractiveProductRound::test_total_is_seven`: change `assert "TOTAL = 7"` → `assert "TOTAL = 8"` and update the failure message to reference Round 7 (design tokens) instead of Round 4 (wiring pass: this test will fail without this change)

## Acceptance Criteria

- [x] `/ll:init` prompts about design tokens after the document-tracking round
- [x] On accept: materializes `.ll/design-tokens/{primitives.json,semantic.json,themes/light.json,themes/dark.json}` and writes `design_tokens` block to `.ll/ll-config.json`
- [x] On decline: sets `design_tokens.enabled: false` in config, creates no token files
- [x] Round numbering in `interactive.md` is consistent end-to-end (no off-by-one in references)
- [x] `skills/init/SKILL.md` says "7–8 rounds" and lists the design-tokens write in dry-run preview
- [x] `test_feat1756_init_wiring.py` passes

## Resolution

Implemented all changes described in the Proposed Solution:

- `skills/init/interactive.md`: Added Round 7 (Design Tokens — MANDATORY, ALWAYS RUNS) between Round 6 and the old Round 7 (now Round 8). Updated TOTAL from 7 → 8, renumbered all downstream rounds (8→9, 9→10, 10→11, 11→12, 12→13), updated all cross-references and the summary table.
- `skills/init/SKILL.md`: Added item 6 (design-tokens template materialization), updated "6–7 rounds" → "7–8 rounds", added dry-run preview entry, added completion message line guarded by DESIGN_TOKENS_CREATED.
- `scripts/tests/test_feat1756_init_wiring.py`: Created new doc-wiring test (4 assertions, all pass).
- `scripts/tests/test_enh1401_doc_wiring.py`: Updated `test_total_is_seven` assertion from `TOTAL = 7` → `TOTAL = 8`.

## Dependencies

- FEAT-1747 (schema/dataclass) — must be merged
- FEAT-1748 (template files) — must be merged

## Session Log
- `/ll:ready-issue` - 2026-05-27T23:14:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8aa268c3-56f7-4b5e-95a9-5e1b84cb1f8e.jsonl`
- `/ll:wire-issue` - 2026-05-27T23:09:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc0a22cb-7cd9-43c7-968b-d20455bd229d.jsonl`
- `/ll:refine-issue` - 2026-05-27T23:05:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1431281-3fdf-4a89-b828-ff33a60689e6.jsonl`
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/279bbdbf-5ea0-4a25-9a30-82b6f7b098b0.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
