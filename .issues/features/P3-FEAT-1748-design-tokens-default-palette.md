---
id: FEAT-1748
title: Design-tokens default palette — four-file high-contrast template set
status: open
priority: P3
type: FEAT
parent: EPIC-1751
relates_to: [EPIC-1751]
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- design-system
---

# FEAT-1748: Design-tokens default palette — four-file high-contrast template set

## Summary

Author the four semantically layered JSON token files that ship as the built-in default palette under `templates/design-tokens/`. All semantic text-on-surface color pairings must clear WCAG AA contrast (4.5:1 body, 3:1 large text) — verified at author time.

This child can be worked in parallel with FEAT-1747 (core infrastructure); no code dependency.

## Parent Issue
Decomposed from FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Current Behavior

No built-in design token template files exist. Users who configure `design_tokens` must author all four JSON files (`primitives.json`, `semantic.json`, `themes/light.json`, `themes/dark.json`) from scratch with no guidance on accessible contrast ratios.

## Expected Behavior

Four semantically layered JSON token files ship with ll under `templates/design-tokens/`. `primitives.json` defines the raw palette; `semantic.json` maps purpose names via `{dot.path}` references; `themes/light.json` and `themes/dark.json` provide theme overrides. All text-on-surface pairings in both themes clear WCAG AA (4.5:1 body, 3:1 large text). All four files parse as valid JSON.

## Motivation

- Lowers the barrier to design-token adoption: users get a working, accessible palette on day one without researching WCAG contrast ratios
- Required by FEAT-1750 (`/ll:init` materializes these files on accept) — without the templates, the init flow has nothing to copy
- Can be worked in parallel with FEAT-1747 (no code dependency)

## Use Case

**Who**: A new ll user running `/ll:init` who accepts the design-tokens prompt

**Context**: First-time project setup on a brand-new project

**Goal**: Receive a ready-to-use, accessible default palette without hand-authoring token files

**Outcome**: Four JSON files materialized at `.ll/design-tokens/`; the palette passes WCAG AA in both light and dark themes; the user can extend or replace individual tokens without touching the others

## Proposed Solution

### File structure

```
templates/design-tokens/
  primitives.json      # raw colors, spacing, type scale, radii, shadows
  semantic.json        # purpose-mapped references into primitives
  themes/
    light.json         # default theme (overrides for light)
    dark.json          # dark theme (~20 lines remapping semantic tokens)
```

### `primitives.json`

Raw palette values — no semantic meaning, just named slots:

```json
{
  "color": {
    "neutral": {
      "0":   "#ffffff",
      "50":  "#f8f9fa",
      "100": "#f1f3f5",
      "200": "#e9ecef",
      "300": "#dee2e6",
      "400": "#ced4da",
      "500": "#adb5bd",
      "600": "#868e96",
      "700": "#495057",
      "800": "#343a40",
      "900": "#212529",
      "950": "#101214"
    },
    "brand": {
      "100": "#dbeafe",
      "300": "#93c5fd",
      "500": "#3b82f6",
      "700": "#1d4ed8",
      "900": "#1e3a5f"
    },
    "accent": {
      "300": "#fed7aa",
      "500": "#f97316",
      "700": "#c2410c"
    },
    "success": { "500": "#16a34a" },
    "warning": { "500": "#ca8a04" },
    "danger":  { "500": "#dc2626" }
  }
}
```

(Spacing, type-scale, radii, shadows can be minimal for the initial palette — focus on color correctness.)

### `semantic.json`

Purpose-mapped aliases into primitives using `{dot.path}` references:

```json
{
  "color": {
    "surface": {
      "primary":   { "$value": "{color.neutral.0}" },
      "secondary": { "$value": "{color.neutral.50}" },
      "raised":    { "$value": "{color.neutral.100}" }
    },
    "text": {
      "primary":   { "$value": "{color.neutral.900}" },
      "secondary": { "$value": "{color.neutral.700}" },
      "muted":     { "$value": "{color.neutral.500}" },
      "inverse":   { "$value": "{color.neutral.0}" }
    },
    "border": {
      "subtle": { "$value": "{color.neutral.200}" },
      "strong": { "$value": "{color.neutral.400}" }
    },
    "action": {
      "primary":       { "$value": "{color.brand.700}" },
      "primary-hover": { "$value": "{color.brand.900}" },
      "destructive":   { "$value": "{color.danger.500}" }
    }
  }
}
```

### `themes/light.json`

No overrides needed for light (semantic.json defaults are light-mode values). Keep as an explicit identity to signal the theme layer is real:

```json
{
  "color": {
    "surface": {
      "primary": { "$value": "{color.neutral.0}" }
    }
  }
}
```

### `themes/dark.json`

Remap surface and text tokens (~20 lines):

```json
{
  "color": {
    "surface": {
      "primary":   { "$value": "{color.neutral.950}" },
      "secondary": { "$value": "{color.neutral.900}" },
      "raised":    { "$value": "{color.neutral.800}" }
    },
    "text": {
      "primary":   { "$value": "{color.neutral.0}" },
      "secondary": { "$value": "{color.neutral.300}" },
      "muted":     { "$value": "{color.neutral.500}" },
      "inverse":   { "$value": "{color.neutral.950}" }
    }
  }
}
```

### WCAG AA verification

At author time, verify all text-on-surface pairings meet:
- 4.5:1 contrast ratio for body text (`color.text.primary` / `color.text.secondary` on any surface)
- 3:1 for large text / UI components

Key pairings to verify for light mode:
- `text.primary (#212529)` on `surface.primary (#ffffff)` — must be ≥4.5:1
- `text.secondary (#495057)` on `surface.primary (#ffffff)` — must be ≥4.5:1
- `text.muted (#adb5bd)` on `surface.primary` — may fall below 4.5:1; document if so (muted text is decorative)
- `action.primary (#1d4ed8)` on `surface.primary (#ffffff)` — must be ≥3:1 for interactive elements

Tools: https://webaim.org/resources/contrastchecker/ or the `wcag-contrast` npm package. Record results in a comment block at the top of `semantic.json`.

## Files to Create

- `templates/design-tokens/primitives.json`
- `templates/design-tokens/semantic.json`
- `templates/design-tokens/themes/light.json`
- `templates/design-tokens/themes/dark.json`

## Acceptance Criteria

- [ ] All four files exist at `templates/design-tokens/`.
- [ ] `primitives.json` contains at minimum: neutral scale (0–950), brand (5 stops), accent, success, warning, danger.
- [ ] `semantic.json` defines `color.surface.{primary,secondary,raised}`, `color.text.{primary,secondary,muted,inverse}`, `color.border.{subtle,strong}`, `color.action.{primary,primary-hover,destructive}` using `{dot.path}` references into primitives.
- [ ] `themes/dark.json` remaps at minimum surface and text tokens.
- [ ] `text.primary` and `text.secondary` on each surface color clear WCAG AA 4.5:1 in both light and dark themes (verified at author time; spot check documented in a comment or PR description).
- [ ] The four files are parseable by `json.loads()` with no errors.

## Implementation Steps

1. Author `templates/design-tokens/primitives.json` with neutral (0–950), brand (5 stops), accent, success, warning, danger color scales
2. Author `templates/design-tokens/semantic.json` with `{dot.path}` references mapping `color.surface.*`, `color.text.*`, `color.border.*`, `color.action.*`
3. Author `templates/design-tokens/themes/light.json` (identity overrides) and `themes/dark.json` (~20-line surface/text remaps)
4. Verify all text-on-surface pairings against WCAG AA 4.5:1 (body) and 3:1 (large/UI); document spot-check results in a comment block at the top of `semantic.json`

## Impact

- **Priority**: P3 — parallel with FEAT-1747; required by FEAT-1750 for init materialization
- **Effort**: Small — JSON file authoring with WCAG spot-check verification; no code changes
- **Risk**: Low — new files only; no existing code modified
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-05-27T20:25:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
