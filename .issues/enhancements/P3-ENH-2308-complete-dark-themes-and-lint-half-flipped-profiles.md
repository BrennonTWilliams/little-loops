---
id: ENH-2308
type: ENH
priority: P3
status: open
title: Complete dark themes in design-token profiles + lint half-flipped themes
captured_at: '2026-06-26T00:00:00Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to: [FEAT-2301]
---

# ENH-2308: Complete dark themes in design-token profiles + lint half-flipped themes

## Summary

Both shipped design-token profiles (`warm-paper` and `default`) have a
"half-flipped" dark theme: `themes/dark.json` overrides only `surface.*` and
`text.*`, leaving `border.*`, `action.*`, status colors, and shadows at their
light-tuned values from `semantic.json`. The token-stamping path (FEAT-2301)
then faithfully renders those light values onto a near-black surface, producing
harsh gridlines, muddy accents, a `danger == action.primary` collision, and
invisible card elevation in dark mode.

This is **not a FEAT-2301 defect** — the emit path was verified correct against
the generated `policy-router-builder.html`. It is a profile-authoring gap, and
it is **systemic**: `default` has the identical structural leak (just less
lurid, because neutral grays degrade more gracefully than warm cream/clay).

Scope: complete the dark themes for both profiles (R1–R3), extend WCAG
spot-check coverage (R4), and add a structural lint that catches half-flipped
themes for any current or future profile.

## Problem

`warm-paper/themes/dark.json` flips only `surface` + `text`:

```json
{
  "color": {
    "surface": { "primary": "{color.paper.950}", "secondary": "{color.paper.900}", "raised": "{color.paper.800}" },
    "text":    { "primary": "{color.paper.0}", "secondary": "{color.paper.300}", "muted": "{color.paper.500}", "inverse": "{color.paper.950}" }
  }
}
```

Everything else falls through to `semantic.json`, which is tuned for light
paper. Concrete consequences on `surface-primary: #0d0b08`:

| Token | Dark value (stamped) | Source | Problem on near-black |
|---|---|---|---|
| `border-subtle` | `#e8dcc4` (paper-200) | `semantic.json` (not flipped) | Faint cream line for white paper → harsh bright gridlines (used 6× in grid) |
| `border-strong` | `#b8a482` (paper-400) | `semantic.json` | Too bright on dark |
| `text-muted` | `#8c7a5e` (paper-500) | flipped to same value | Dim muddy brown on dark |
| `action-primary` | `#9a3812` (terracotta-700) | `semantic.json` | Tuned for 7.57:1 on white; muddy + low-contrast on near-black |
| `danger-500` | `#9a3812` | primitive | **Identical to `action-primary`** → error states indistinguishable from primary actions |
| `success-500` | `#5e7140` (moss) | primitive | Dim moss meant for white paper |
| `warning-500` | `#9a6b12` | primitive | Dim olive meant for white paper |
| `shadow-*` | `rgba(74,64,49,…)` | `semantic`/typography | Warm-brown shadow invisible on near-black → cards lose elevation |

**The tell:** `semantic.json`'s `_wcag_spot_check.dark_mode` validates only
`text.primary` and `text.secondary`. There is no dark-mode contrast entry for
borders, actions, or status colors — because the dark theme never defined them.

**`default` shares the gap:** `default/themes/dark.json` is structurally
identical (only `surface` + `text`), and its `semantic.json` leaks
`border.subtle = neutral.200 (#e9ecef)` onto `neutral.950` — same harsh-gridline
class of bug. Its `dark_mode` spot-check also omits `border`. So the
"switch to the default profile" workaround is **not viable** — both profiles
are affected.

## Affected files

- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/themes/dark.json`
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/primitives.json`
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/semantic.json` (`_wcag_spot_check`)
- `scripts/little_loops/templates/design-tokens/profiles/default/themes/dark.json`
- `scripts/little_loops/templates/design-tokens/profiles/default/semantic.json` (`_wcag_spot_check`)
- New: structural lint (in `design_tokens.py` or a new `ll-verify-*` tool)

**Out of scope (verified correct, no change):** `design_tokens.py` render path,
`cli/artifact/*`, `policy-router-builder.html.tmpl`.

## Proposed fix

### R1 — Complete `warm-paper/themes/dark.json`

Darken borders (recede into surface), brighten accents (read on near-black),
break the `danger == action.primary` collision:

```json
{
  "color": {
    "surface": { "primary": "{color.paper.950}", "secondary": "{color.paper.900}", "raised": "{color.paper.800}" },
    "text":    { "primary": "{color.paper.0}", "secondary": "{color.paper.300}", "muted": "{color.paper.400}", "inverse": "{color.paper.950}" },
    "border":  { "subtle": "{color.paper.800}", "strong": "{color.paper.600}" },
    "action":  { "primary": "{color.terracotta.500}", "primary-hover": "{color.terracotta.300}", "destructive": "{color.danger.300}" }
  }
}
```

- `border.subtle → paper-800 (#2e2820)`, `border.strong → paper-600 (#6b5d47)` — gridlines read as structure, not glare.
- `text.muted → paper-400 (#b8a482)` — legible on `#0d0b08` (paper-500 is too dim).
- `action.primary → terracotta-500 (#c84a1c)`, `hover → terracotta-300 (#f7b886)` — brighter clay accent for dark.

Apply the analogous dark overrides to `default/themes/dark.json` (`border` →
darker neutral steps, `action`/`destructive` → brighter brand/danger steps).

### R2 — Add bright primitive steps for status colors

`danger`/`success`/`warning` only define `500`, so there's no brighter variant
to map to in dark. Add light-end steps to `primitives.json`:

```json
"success": { "300": "#8fae66", "500": "#5e7140" },
"warning": { "300": "#d9a44a", "500": "#9a6b12" },
"danger":  { "300": "#e06b3d", "500": "#9a3812" }
```

Then reference `*-300` in dark (via new `color.status.*` semantic tokens or the
builder's validation palette). This finally breaks the `danger == primary`
collision and makes the live-validation colors (shadow→warning,
missing-catch-all→danger, clean→success) distinguishable in dark mode. Mirror
the equivalent steps in `default/primitives.json`.

### R3 — Theme-scoped shadow tokens (decided)

Define theme-scoped shadow tokens so elevation reads on near-black, e.g.
`rgba(0,0,0,0.5)` in the dark theme rather than the light-tuned warm-brown
`rgba(74,64,49,…)`. (Chosen over the "lean on borders for elevation" fallback.)
Applies to both profiles.

### R4 — Extend WCAG spot-check coverage

After R1–R3, add `dark_mode` entries to `_wcag_spot_check` for `border`,
`action.primary`, and each status color on `surface.primary` in both profiles.
The absence of these entries is precisely what let the gap ship.

### R5 — Structural lint for half-flipped themes (regression guard)

Add a check that, for every profile, each `themes/<theme>.json` overrides the
same semantic token groups that `semantic.json` defines (`border`, `action`,
status) — not just `surface` + `text`. This is the durable fix: it's the only
thing that catches both shipped profiles and any future profile. Wire it as a
`ll-verify-*` tool (and/or a unit test over the profile templates) so the
"half-flipped theme" class is caught at authoring time, not by eye.

## Acceptance criteria

- [ ] `warm-paper/themes/dark.json` overrides `border`, `action`, and status groups with dark-tuned values; `danger != action.primary` in dark.
- [ ] `default/themes/dark.json` likewise completed.
- [ ] `*-300` status steps added to both profiles' `primitives.json` and consumed in dark.
- [ ] Theme-scoped shadow tokens defined for dark in both profiles.
- [ ] `_wcag_spot_check.dark_mode` covers `border`, `action.primary`, and status colors on `surface.primary` for both profiles.
- [ ] New lint/test fails on a profile whose `themes/dark.json` flips only `surface` + `text`, and passes after R1–R4.
- [ ] Re-emit and visually diff: `ll-artifact policy-builder && open policy-router-builder.html` shows legible borders, distinct accent/danger, and visible card elevation in dark mode.

## Notes

- Investigation source: `policy-builder-dark-mode-findings.md` (2026-06-26).
- Low risk: changes are additive and single-purpose per profile; render path unchanged.
- R5 (`default` is "complete, switch to it") from the original findings was
  **dropped** — `default` shares the same gap.
