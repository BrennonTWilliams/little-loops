---
id: FEAT-1762
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T23:57:00Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 61
score_complexity: 18
score_test_coverage: 0
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1762: Redesign Command Center section cards with solid, visible borders

## Summary

Replace the current callout-based section cards in `_Vault/MOC-Command-Center.md` with `div`-based solid cards that have clear, visible borders. The current design uses `> [!panel-*]` callout hacks which are nearly invisible in dark theme — only the thin top accent bar distinguishes sections. Switch to bounded cards with a 1-2px border matching each section's accent color, a slightly darker background than the page, and consistent padding (like GitHub issue panels).

## Current Behavior

The dashboard uses five `> [!panel-secondary|...]` callouts styled via CSS classes:
- Inbox Status (orange) — file count
- Project Status (blue) — active project list with stale indicators
- Activity (no accent) — 5-tab switcher
- System (purple) — 2-tab (Knowledge & Health / Icons)
- Vault Graph (no accent) — canvas-based force-directed graph

Each card is structurally a callout: thin top accent stripe, subtle background tint, no visible left/right/bottom borders. In Obsidian's dark theme, the cards visually blend together — the only differentiation is the colored stripe.

## Expected Behavior

Each section renders as a properly bounded card with:
- **Visible border** — 1-2px solid in the section's accent color (full rectangle, not just top)
- **Card background** — slightly darker than the page background, clearly distinct from the page surface
- **Consistent padding** — uniform internal spacing across all sections
- **Header inside the card** — section title with accent-colored icon, flush within the card bounds
- **Hover state** — subtle glow or border-lighten on hover for interactivity cues
- **Grid layout preserved** — keep the current 5-panel grid arrangement

Rendering approach: replace `> [!panel-*]` callout wrappers with DataviewJS `container.createEl('div', ...)` calls that build structured cards, giving full CSS control.

## Motivation

- Current callout-based cards lack visual definition; the dashboard feels like a flat list of content rather than a structured workspace
- The accent-bar-only pattern relies too heavily on color to differentiate sections, which fails when themes change or colors are similar
- Solid borders with proper backgrounds make the dashboard scannable at a glance
- Removing callout hacks eliminates CSS-class overrides that may conflict with theme updates

## Use Case

**Who**: Obsidian vault user / dashboard maintainer

**Context**: When viewing the Command Center dashboard (`_Vault/MOC-Command-Center.md`) in Obsidian, especially in dark theme where current callout-based cards visually blend together

**Goal**: Quickly distinguish between section cards (Inbox Status, Project Status, Activity, System, Vault Graph) at a glance

**Outcome**: Dashboard renders as a structured workspace with visually bounded cards, scannable without relying solely on colored accent stripes

## Acceptance Criteria

- [ ] Each section card has a visible 1-2px solid border matching its accent color (full rectangle border, not just top accent bar)
- [ ] Card background is slightly darker than the page background, clearly distinct from the page surface
- [ ] All sections have consistent internal padding
- [ ] Section title with accent-colored icon renders inside the card bounds
- [ ] Hover state adds subtle glow or border-lighten for interactivity cues
- [ ] Current 5-panel grid layout is preserved
- [ ] Cards render via DataviewJS `container.createEl('div', ...)`, not `> [!panel-*]` callouts
- [ ] Works across Obsidian theme variants (dark, light, gruvbox)

## Implementation Steps

1. Define CSS for `.dashboard-card` class: border, background, padding, header layout, hover state in `.obsidian/snippets/dashboard-panels.css` (use `--db-*` variable namespace with `--pp-*` fallback chain for theme compatibility)
2. Replace each `> [!panel-*]` callout with a DataviewJS-rendered `div.dashboard-card` wrapper
3. Move each section's header into the card div with appropriate accent styling
4. Port existing card content (inbox count, project list, tabs, graph) into the new structure
5. Update `_Vault/Dashboard-Redesign-Plan.md` — reflect new card-based panel architecture in participating files list and verification checklist
6. Update `.obsidian/snippets/dashboard-layouts.css` header comment block — update participating files list
7. Test across Obsidian theme variants (dark/light/gruvbox), including regression tests on:
   - `Personal/_Meta/MOC-Personal-Home.md` — uses `panel-secondary` callouts via shared CSS system
   - `Personal/_Reading/YouTube/_YouTube-Dashboard.md` — passive `cssclasses: [dashboard]` consumer

## API/Interface

No public API changes. CSS changes go into the vault's existing snippet system at `.obsidian/snippets/dashboard-panels.css` (not `_Vault/Assets/css/dashboard.css` — that path does not exist in the vault; Obsidian loads snippets exclusively from `.obsidian/snippets/` registered via `appearance.json`).

## Integration Map

### Files to Modify
- `_Vault/MOC-Command-Center.md` — Replace `> [!panel-*]` callout wrappers with DataviewJS `container.createEl('div', ...)` structured cards
- `.obsidian/snippets/dashboard-panels.css` — Add `.dashboard-card` CSS class with border, background, padding, header layout, and hover state. Current border styles are at lines 180, 207, 215, 224, 723, 762, 785 (1px `var(--db-panel-border)` with 3px top accent stripe per panel type).
- `.obsidian/appearance.json` — If adding a new snippet file (e.g., `dashboard-card.css`), register it in the `enabledCssSnippets` array (currently: `["preprint-theme", "dashboard-panels", "svg-buttons", "dashboard-layouts"]`). If adding `.dashboard-card` styles directly to `dashboard-panels.css`, no change needed here.

_Wiring pass added by `/ll:wire-issue`:_
- `_Vault/Dashboard-Redesign-Plan.md` — Update architecture documentation (participating files list, verification checklist) — current design uses callout-based panels
- `.obsidian/snippets/dashboard-layouts.css` — Update header comment block (lines 1-24) if participating files change
- `_Vault/scripts/toggle-preprint-theme.py` and `_Vault/scripts/toggle-gruvbox-theme.py` — Verify no conflicts; both toggle scripts manipulate `enabledCssSnippets` array in `appearance.json`

### Dependent Files (Callers/Importers)
- N/A — no callers or importers affected
  
_Wiring pass added by `/ll:wire-issue`:_
- `Personal/_Meta/MOC-Personal-Home.md` — **HIGH regression risk**. Uses `cssclasses: [dashboard]` frontmatter and 3 `panel-secondary` callouts (lines 105, 135, 160) plus 1 `panel-primary` callout (line 53), sharing the same CSS snippet system. Any `.dashboard`-scoped CSS changes affect this page.
- `Personal/_Reading/YouTube/_YouTube-Dashboard.md` — Low regression risk, uses `cssclasses: [dashboard]` but no panel callouts (raw Dataview queries only)
- `.obsidian/plugins/cmdr/data.json` — Registers "Command Center" command in Cmdr plugin
- `.obsidian/plugins/quickadd/data.json` — Registers "Open Command Center" quick action via `_Vault/scripts/quickadd/open-command-center.js`

### Similar Patterns
- `Personal/_Meta/MOC-Personal-Home.md` — Highest-risk regression target, uses same `panel-secondary` callout pattern and `cssclasses: [dashboard]`

_Wiring pass added by `/ll:wire-issue`:_
- `.obsidian/snippets/dashboard-panels.css` — Existing border patterns at lines 207/215 use 3px top accent bar variant; current callout borders at line 180 use `1px solid var(--db-panel-border)`
- `.obsidian/snippets/dashboard-layouts.css` — Companion layout file, grid-template-areas defined here
- `.obsidian/snippets/preprint-theme.css` — Defines `--pp-accent-*` variables (lines 63-68) that `dashboard-panels.css` references as fallback chain; defines both `:root` (light, lines 24-84) and `.theme-dark` (lines 90+) values

### Tests
- N/A — no automated visual test infrastructure exists in the vault (no CSS linting, no DataviewJS validation, no visual regression testing). Validate manually.
  
_Wiring pass added by `/ll:wire-issue`:_
- **Regression test**: Verify `Personal/_Meta/MOC-Personal-Home.md` renders correctly after CSS changes (uses `panel-secondary` callouts via `cssclasses: [dashboard]`)
- **Regression test**: Verify `Personal/_Reading/YouTube/_YouTube-Dashboard.md` renders correctly (passive `cssclasses: [dashboard]` consumer)
- **Existing safeguards**: Vault health check (`sync-vault-health.sh`), wikilink checker (`check_wikilinks.py`), and frontmatter validator (`frontmatter_cli.py`) guard non-CSS content regressions in `MOC-Command-Center.md`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `_Vault/Dashboard-Redesign-Plan.md` — Architecture document for the current dashboard layout; participating files list and verification checklist (lines 19-24, 34-39, 349-359) must be updated to reflect new panel/card structure
- `.obsidian/snippets/dashboard-layouts.css` — Header comment block (lines 1-24) lists participating files; update if file list changes
- `CLAUDE.md` — Does not currently document CSS snippet conventions; consider adding note about the new card approach

### Configuration
- N/A

## Impact

- **Priority**: P3 — Visual enhancement; improves dashboard scannability but not blocking functionality
- **Effort**: Small — CSS snippet changes + DataviewJS updates to a single file
- **Risk**: Low — CSS and DataviewJS changes only, no functional logic affected
- **Breaking Change**: No

## Labels

`FEAT`, `captured`, `status/open`

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- **Zero automated test coverage (0/25)** — CSS and DataviewJS changes have no automated validation. Regression detection on `Personal/_Meta/MOC-Personal-Home.md` (HIGH risk, shares `panel-secondary` callout pattern and `cssclasses: [dashboard]`) relies entirely on manual visual verification across theme variants. Manual testing checklist in the Acceptance Criteria mitigates this partially but is not automated.
- **Moderate complexity (18/25)** — changes span CSS snippet additions (new `.dashboard-card` class) and DataviewJS restructuring (replacing 5 callout wrappers with `container.createEl` divs) across 3-5 files. The DataviewJS port is well-patterned against 17 existing `container.createEl` usages in the same file, but the CSS change shares a snippet system consumed by 3 dashboard pages.

## Session Log
- `/ll:confidence-check` - 2026-05-28T04:20:00Z - `91ecdbf4-21ef-4028-8788-a1a80719b749.jsonl`
- `/ll:confidence-check` - 2026-05-27T23:50:00Z - `e466a2d0-577e-4da7-a068-d69e9f7ee93a.jsonl`
- `/ll:wire-issue` - 2026-05-28T04:15:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-MC-vault/26e1f473-85d2-45e1-8a33-0eac6ed0c6f7.jsonl`
- `/ll:format-issue` - 2026-05-28T04:03:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e4c4580-ff53-491f-b559-91a0d8e16e9f.jsonl`
- `/ll:capture-issue` - 2026-05-27T23:57:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-MC-vault/31d98260-ce88-4511-81e8-2d957e4dc435.jsonl`
