---
discovered_date: 2026-03-21T00:00:00Z
discovered_by: manual
---

# ENH-856: Apply docs-theme color/styling to MkDocs site

## Summary

The user added brand-aligned theme configuration to `docs/docs-theme/` (custom CSS with amber color palette, light/dark mode variables, and font selections). The root `mkdocs.yml` was not wired up to use any of it. This change connects the theme to the live site.

## Current Behavior

Root `mkdocs.yml` had:
- No custom primary/accent colors (defaulted to Material blue)
- No font configuration
- No `extra_css` reference
- Missing three navigation features from the theme template
- No system dark mode preference detection (`media` queries absent)

## Expected Behavior

The docs site renders with:
- Amber primary (`#d97706` light / `#fbbf24` dark) and warm neutral backgrounds
- Inter body font, JetBrains Mono code font
- System dark mode preference respected via `prefers-color-scheme` media queries
- `navigation.instant`, `navigation.tracking`, `navigation.top` features active

## Impact

- **Severity**: Low (cosmetic/branding)
- **Effort**: Minimal (single file, four targeted edits)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `theme`

---

## Status

**Completed** | Created: 2026-03-21 | Completed: 2026-03-21 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-03-21
- **Status**: Completed

### Changes Made

- `mkdocs.yml`: Updated `theme.palette` to add `media` queries for system dark mode detection and set `primary: custom` + `accent: custom` on both schemes
- `mkdocs.yml`: Added `theme.font` block — `text: Inter`, `code: JetBrains Mono`
- `mkdocs.yml`: Added `navigation.instant`, `navigation.tracking`, `navigation.top` to `theme.features`
- `mkdocs.yml`: Added `extra_css` block pointing to `docs-theme/stylesheets/little-loops.css`

No new files created. CSS file was already at `docs/docs-theme/stylesheets/little-loops.css`.

### Verification Results

- `mkdocs serve` built successfully with no errors
- HTML response confirmed `fonts.googleapis.com/css?family=Inter` and `JetBrains` font references
- CSS file served at `docs-theme/stylesheets/little-loops.css` with expected `--md-primary-fg-color: #d97706` (light) and `#fbbf24` (dark) variables present
- Tests: N/A (config/styling change)
