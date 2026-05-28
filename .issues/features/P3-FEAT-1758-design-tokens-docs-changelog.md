---
id: FEAT-1758
title: Design tokens documentation, README, and changelog
status: done
priority: P3
type: FEAT
parent: FEAT-1750
discovered_date: 2026-05-27
discovered_by: issue-size-review
completed_at: 2026-05-28 00:00:43+00:00
decision_needed: false
labels:
- feat
- docs
- design-system
relates_to:
- FEAT-1750
- FEAT-1747
- FEAT-1748
- EPIC-1751
confidence_score: 100
outcome_confidence: 78
testable: false
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1758: Design tokens documentation, README, and changelog

## Summary

Write the `design_tokens` documentation section in `CONFIGURATION.md`, add a `DesignTokensConfig` API sub-section to `API.md`, add a cross-cutting note to `ARCHITECTURE.md`, update `README.md`, and write a changelog entry covering all four FEAT-1746 children (FEAT-1747 infra, FEAT-1748 palette, FEAT-1749 loop wiring, FEAT-1750 UX/docs).

## Parent Issue
Decomposed from FEAT-1750: Design-tokens init / configure UX and docs integration

## Current Behavior

`docs/reference/CONFIGURATION.md` has no `design_tokens` section. `docs/reference/API.md` has the `design_tokens | DesignTokensConfig` row in the `BRConfig` table but no `#### DesignTokensConfig` sub-section. `README.md` does not mention design tokens. No changelog entry exists for the feature set.

## Expected Behavior

All six `design_tokens` config fields are documented with types and defaults. The API reference has a full `#### DesignTokensConfig` sub-section. Architecture docs note design tokens as a cross-cutting input. README lists design tokens as a feature. Changelog captures the full feature set.

## Proposed Solution

### 1. `docs/reference/CONFIGURATION.md`

Add `### \`design_tokens\`` section modeled after `### \`documents\`` (lines 452–477):
- One-line summary sentence
- Pipe table of all 6 fields (name, type, default, description)
- Fenced JSON example block

Add `design_tokens` block to the "Full Configuration Example" JSON at the top of the file (lines 154–157, after the `"documents"` block):

```json
"design_tokens": {
  "enabled": true,
  "path": ".ll/design-tokens",
  "primitives_file": "primitives.json",
  "semantic_file": "semantic.json",
  "themes_dir": "themes",
  "active_theme": "light"
}
```

### 2. `docs/reference/API.md`

`design_tokens | DesignTokensConfig` row already exists at line 113 — skip that row.

Add `#### DesignTokensConfig` sub-section after `#### CliConfig` (~line 162), with a key/type/default/description table for all 6 fields (model after `CliConfig` table at lines 151–156).

### 3. `docs/ARCHITECTURE.md`

Add one-sentence cross-cutting note in the artifact-loops paragraph noting that design tokens serve as a cross-cutting input to artifact-generating loops.

### 4. `README.md`

Single-line feature mention in the feature list.

### 5. `CHANGELOG.md`

Add a changelog entry (under the appropriate release section) covering all four FEAT-1746 children:
- FEAT-1747: Design-tokens config schema and dataclass infrastructure
- FEAT-1748: Default four-file WCAG AA palette template set
- FEAT-1749: Design-tokens context pre-injection into FSM at run/resume
- FEAT-1750: Design-tokens init / configure UX and docs integration (FEAT-1756 + FEAT-1757 + FEAT-1758)

### 6. `scripts/tests/test_feat1758_docs_wiring.py`

Doc-wiring test following `test_enh1734_doc_wiring.py` pattern. Assert:
- `docs/reference/CONFIGURATION.md` contains `design_tokens` section header
- `docs/reference/CONFIGURATION.md` contains `design_tokens` block in full-example JSON
- `docs/reference/API.md` contains `#### DesignTokensConfig`
- `docs/ARCHITECTURE.md` contains `design.token` or `design_token` reference in artifact-loops paragraph
- `README.md` contains `design` token mention

## Files to Modify

- `docs/reference/CONFIGURATION.md` — new `### design_tokens` section + full-example JSON entry
- `docs/reference/API.md` — `#### DesignTokensConfig` sub-section (BRConfig row already present)
- `docs/ARCHITECTURE.md` — one-sentence cross-cutting note
- `README.md` — single-line feature mention
- `CHANGELOG.md` — entry covering all four FEAT-1746 children
- `scripts/tests/test_feat1758_docs_wiring.py` — new doc-wiring test (create)

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

This is a docs-only issue — no implementation files require changes. The following files have existing `design_tokens` references that become cross-linkable once `CONFIGURATION.md#design_tokens` exists; they are **not required** for acceptance criteria but are optional follow-ups:

- `docs/guides/LOOPS_GUIDE.md` — 6 state-type context-variable tables reference `design_tokens_context` and `design_tokens.enabled`; no link to `CONFIGURATION.md#design_tokens` currently [Agent 1]
- `docs/reference/COMMANDS.md` — `design-tokens` listed as a valid `/ll:configure` area slug without a link to the new config section [Agent 2]
- `skills/configure/SKILL.md` — `design-tokens` row in the Area table without a link to the new config section [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_feat1758_docs_wiring.py` — new test (already in Files to Modify); follow `test_enh1734_doc_wiring.py` exactly: one `Path` constant per target file, one class per file, one assertion per method, no fixtures, each method calls `.read_text()` independently
- **CHANGELOG assertion gap**: Acceptance criterion 6 requires a CHANGELOG entry but the 5 proposed assertions exclude CHANGELOG. Per codebase convention, no `test_*_doc_wiring.py` asserts CHANGELOG content — this gap is intentional; CHANGELOG correctness is verified during release [Agent 3]
- **Per-field coverage (optional)**: Proposed test checks section headers only; the ENH-1734 pattern supports per-field test methods (`test_enabled_field_present`, etc.). Adding per-field assertions for all 6 `DesignTokensConfig` fields would strengthen regression protection [Agent 3]

### Wiring Phase (added by `/ll:wire-issue`)

_Optional touchpoints identified by wiring analysis — not required for acceptance criteria:_

- **Optional**: In `docs/guides/LOOPS_GUIDE.md`, update the 6 `design_tokens_context` context-variable table rows to cross-reference `CONFIGURATION.md#design_tokens` — helps users connect the injected context variable to its underlying config settings.

## Key Anchors

- `docs/reference/CONFIGURATION.md:154–157` — Full Configuration Example JSON (`"documents"` block; `"loops"` block starts at line 159; insert `design_tokens` between lines 157 and 159)
- `docs/reference/CONFIGURATION.md:452–477` — `### documents` section (structural model); note this section uses 3-column `Key | Default | Description` table, but **use 4-column `Key | Type | Default | Description`** for `design_tokens` — consistent with newer CONFIGURATION.md sections at lines 727, 780, 808, 825, 850, 879
- `docs/reference/API.md:113` — existing `design_tokens | DesignTokensConfig` row in BRConfig table
- `docs/reference/API.md:151–156` — `CliConfig` table (`Key | Type | Default | Description`, 4 columns — structural model for DesignTokensConfig table)
- `docs/reference/API.md:162–163` — line 162 is blank (end of CliConfig Notes block); line 163 is `#### Methods`; insert `#### DesignTokensConfig` at line 162 (before `#### Methods`)
- `docs/ARCHITECTURE.md:714` — end of `## Configuration Flow` mermaid diagram; insert the design-tokens cross-cutting note here, before the `---` separator at line 716 (no existing "artifact-loops paragraph"; this is the nearest prose anchor for a cross-cutting config note)
- `docs/ARCHITECTURE.md:189` — `│   ├── design-tokens/` already appears in the directory tree (no change needed there)
- `README.md:163–168` — `## What's in the box` bullet list; add design tokens near the `**Configuration system**` bullet (line 168)
- `CHANGELOG.md:8` — `## [Unreleased]` section (at line 8) exists but must NOT be used; `## [1.111.0]` is at line 15 (current latest); create new `## [1.112.0] - 2026-05-27` section between lines 14–15 (blank line before `[1.111.0]`); follow format `### Added` / `- **\`feature\`** — description. (FEAT-NNNN)`
- `DesignTokensConfig` fields (confirmed from `scripts/little_loops/config/features.py:268–289`):
  `enabled` (bool, default `True`), `path` (str, `".ll/design-tokens"`), `primitives_file` (str, `"primitives.json"`), `semantic_file` (str, `"semantic.json"`), `themes_dir` (str, `"themes"`), `active_theme` (str, `"light"`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CONFIGURATION.md — column format clarification:**
The `### documents` structural model (lines 452–477) uses a 3-column `Key | Default | Description` table. However, the issue specifies a 4-column table including `Type`, which is consistent with newer sections of `CONFIGURATION.md` (lines 727, 780, 808, 825, 850, 879 all use `Key | Type | Default | Description`). Use 4 columns for `design_tokens` — the type distinction (bool vs str) adds meaningful information here.

**API.md — exact insertion point:**
Line 162 is blank (end of the `**Notes:**` block following `#### CliConfig`); line 163 is `#### Methods`. Insert `#### DesignTokensConfig` at line 162 so it appears between CliConfig and Methods.

**ARCHITECTURE.md — no existing "artifact-loops paragraph":**
There is no standalone "artifact-loops paragraph" in `ARCHITECTURE.md`. The closest existing section is `## Configuration Flow` (lines 681–715) followed by `---` at line 716. Add the design-tokens cross-cutting note as a prose sentence after the mermaid diagram (line 714), before the `---` separator. Suggested text: *"Design tokens (`DesignTokensConfig`) serve as a cross-cutting input to artifact-generating loops: `ll-loop run` and `ll-loop resume` pre-inject the resolved token set into the FSM initial context before the first state is entered."*

**CHANGELOG.md — version to use:**
Current latest release is `## [1.111.0] - 2026-05-27`. The `## [Unreleased]` section exists but per project convention must not be used for new entries. Create `## [1.112.0] - 2026-05-27` (or the next appropriate version) above `[1.111.0]`. Entry format: `- **\`design-tokens\`** — description. (FEAT-NNNN)`.

**Test pattern (from `scripts/tests/test_enh1734_doc_wiring.py`):**
```python
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIGURATION_MD = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"

class TestConfigurationMd:
    def test_design_tokens_section_header(self) -> None:
        content = CONFIGURATION_MD.read_text()
        assert "### `design_tokens`" in content, (
            "CONFIGURATION.md must include a ### `design_tokens` section header"
        )
```
Each target file gets its own `Path` constant and class; each assertion is a single `in content` check.

## Acceptance Criteria

- [ ] `docs/reference/CONFIGURATION.md` documents all six `design_tokens` config fields with types and defaults
- [ ] `docs/reference/CONFIGURATION.md` full-example JSON includes `design_tokens` block
- [ ] `docs/reference/API.md` has `#### DesignTokensConfig` sub-section with all 6 fields
- [ ] `docs/ARCHITECTURE.md` mentions design tokens in the artifact-loops paragraph
- [ ] `README.md` lists design tokens as a feature
- [ ] `CHANGELOG.md` has an entry covering the full FEAT-1746 feature set
- [ ] `test_feat1758_docs_wiring.py` passes

## Dependencies

- Can run in parallel with FEAT-1756 (init round) and FEAT-1757 (configure area)
- Changelog entry should mention FEAT-1756 and FEAT-1757 outcomes; best written last

## Session Log
- `/ll:ready-issue` - 2026-05-27T23:58:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/112e2a30-c9a6-423b-a8f6-6378ccb07daf.jsonl`
- `/ll:confidence-check` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11ecacf-9e2d-4d24-af2b-ff630ba1eb3d.jsonl`
- `/ll:wire-issue` - 2026-05-27T23:53:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7649778c-9578-4167-b94a-9d44421b6bef.jsonl`
- `/ll:refine-issue` - 2026-05-27T23:48:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3eb92b60-b471-4c74-afcb-29035af4b912.jsonl`
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
