---
id: FEAT-1758
title: Design tokens documentation, README, and changelog
status: open
priority: P3
type: FEAT
parent: FEAT-1750
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- docs
- design-system
relates_to:
- FEAT-1750
- FEAT-1747
- FEAT-1748
- EPIC-1751
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

## Key Anchors

- `docs/reference/CONFIGURATION.md:154–157` — Full Configuration Example JSON (insert design_tokens block after documents block)
- `docs/reference/CONFIGURATION.md:452–477` — `### documents` section (structural model)
- `docs/reference/API.md:113` — existing `design_tokens | DesignTokensConfig` row
- `docs/reference/API.md:151–156` — `CliConfig` table (structural model for DesignTokensConfig table)
- `docs/reference/API.md:162` — append `#### DesignTokensConfig` after `#### CliConfig`
- `DesignTokensConfig` fields (from `scripts/little_loops/config/features.py:268–289`):
  `enabled` (bool, default `True`), `path` (str, `".ll/design-tokens"`), `primitives_file` (str, `"primitives.json"`), `semantic_file` (str, `"semantic.json"`), `themes_dir` (str, `"themes"`), `active_theme` (str, `"light"`)

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
- `/ll:issue-size-review` - 2026-05-27T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
