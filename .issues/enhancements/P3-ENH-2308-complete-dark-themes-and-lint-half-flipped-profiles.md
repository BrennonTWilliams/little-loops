---
id: ENH-2308
type: ENH
priority: P3
status: done
title: Complete dark themes in design-token profiles + lint half-flipped themes
captured_at: '2026-06-26T00:00:00Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- FEAT-2301
confidence_score: 93
outcome_confidence: 83
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 21
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

## Motivation

Dark mode is currently unusable for both shipped design-token profiles:
- Both `warm-paper` and `default` profiles override only `surface` and `text` tokens in their dark themes — borders become harsh gridlines, accents are muddy and low-contrast on near-black, and `danger == action.primary` makes error states indistinguishable from primary actions.
- The gap is **systemic**: switching profiles is not a workaround — `default` has the identical structural leak.
- Without a structural lint, any future profile is at risk of shipping the same half-flipped dark theme.

## Current Behavior

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

## Expected Behavior

- `warm-paper/themes/dark.json` and `default/themes/dark.json` each override `border`, `action`, status, and shadow token groups with dark-tuned values.
- `danger` and `action.primary` resolve to distinct colors in dark mode.
- Status colors (`success`, `warning`, `danger`) have bright `*-300` primitive variants consumed in dark themes so they read on near-black surfaces.
- `_wcag_spot_check.dark_mode` in both profiles covers `border`, `action.primary`, and status colors on `surface.primary`.
- A structural lint catches any profile whose dark theme overrides only `surface` + `text`, failing at authoring time before it ships.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/themes/dark.json` — add `border`, `action`, shadow, and `text.muted` overrides (R1, R3)
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/primitives.json` — add `*-300` bright steps for `danger`, `success`, `warning` (R2)
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/semantic.json` — extend `_wcag_spot_check.dark_mode` (R4)
- `scripts/little_loops/templates/design-tokens/profiles/default/themes/dark.json` — mirror dark overrides for neutral-tuned tokens (R1, R3)
- `scripts/little_loops/templates/design-tokens/profiles/default/primitives.json` — add `*-300` bright steps (R2)
- `scripts/little_loops/templates/design-tokens/profiles/default/semantic.json` — extend `_wcag_spot_check.dark_mode` (R4)
- New: structural lint in `scripts/little_loops/design_tokens.py` or a new `ll-verify-*` tool (R5)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `### ll-verify-design-tokens` section after the `### ll-verify-package-data` block (flags table, exit codes, examples) [Agent 2 finding]
- `commands/help.md` — add `ll-verify-design-tokens` one-liner in the `ll-verify-*` block (lines 276-279) [Agent 2 finding]
- `.claude/CLAUDE.md` — add `ll-verify-design-tokens` entry to "CLI Tools" section alongside existing `ll-verify-*` entries [Agent 2 finding]
- `skills/configure/areas.md` — add `ll-verify-design-tokens` to the CLI tool enumeration string; increment count `29 → 30` [Agent 2 finding]
- `README.md` — increment `"35 typed CLI tools"` → `"36"` and `"35 CLI tools"` → `"36"` (two occurrences) [Agent 2 finding]
- `scripts/tests/test_wiring_cli_registry.py` — add 3 `DOC_STRINGS_PRESENT` tuples for `"ll-verify-design-tokens"` targeting `commands/help.md`, `docs/reference/CLI.md`, and `.claude/CLAUDE.md` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/design_tokens.py` — `load_design_tokens()` / `_resolve_token_root()` programmatically loads all profile JSON files; no hardcoded filename references outside this module
- `scripts/tests/test_enh1768_profile_system.py` — `TestBundledProfilesLoadEndToEnd._copy_templates()` copies bundled templates and exercises all 3 profiles end-to-end; `TestBundledProfileTemplates.test_each_profile_has_full_layer()` asserts presence of `themes/dark.json` per profile
- `scripts/tests/test_design_tokens.py` — `TestIntegration.test_round_trip_dark_theme()` exercises the dark-theme merge path against bundled `default` profile templates

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — calls `load_design_tokens(_config)` + `render_as_prompt_context()` in `cmd_run()`; dark-tuned resolved values are injected into `fsm.context["design_tokens_context"]` — no code change required, but confirms dark-mode FSM context improves after R1–R3 [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — identical injection pattern in the resume continuation path [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/templates/design-tokens/profiles/warm-paper/themes/light.json` — structural reference for theme override format

### Tests
- `scripts/tests/test_enh1768_profile_system.py` — `TestBundledProfileTemplates.test_each_profile_has_full_layer()` (structural presence); `TestBundledProfilesLoadEndToEnd` (end-to-end profile loads) — extend with a dark-theme completeness assertion for R5 (model: `PROFILE_NAMES = ("default", "editorial-mono", "warm-paper")` loop)
- `scripts/tests/test_design_tokens.py` — `TestIntegration.test_round_trip_dark_theme()` — extend to assert resolved `color.border.*` and `color.action.*` values differ from their light-tuned `semantic.json` defaults after R1 is applied
- New: `scripts/tests/test_verify_design_tokens.py` — unit tests for R5 `ll-verify-design-tokens` CLI tool; model after `scripts/tests/test_verify_package_data.py` (dataclass violations, text/JSON report formatting, exit codes); use **synthetic temp-dir fixtures only** (not bundled templates) so test pass/fail is independent of `editorial-mono` incomplete state

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py::TestIntegration.test_round_trip_dark_theme()` — currently only asserts `color.surface.primary == "#101214"` for `default`; extend to assert dark-tuned values for `color.border.subtle`, `color.border.strong`, `color.action.primary`, and `shadow.*` after R1 is applied [Agent 3 finding]
- `scripts/tests/test_enh1768_profile_system.py::TestBundledProfilesLoadEndToEnd` — `test_warm_paper_loads()` has no dark-theme token-group assertion; add dark-theme completeness check scoped to `("default", "warm-paper")` only (exclude `editorial-mono`, which remains incomplete pending follow-on) [Agent 2/3 finding]
- **At risk**: `scripts/tests/test_enh1768_profile_system.py::TestBundledProfilesLoadEndToEnd.test_profile_outputs_diverge()` — asserts `color.action.primary` differs across all 3 profiles; verify dark-tuned values (`warm-paper: terracotta-500`, `default: brand step`) remain distinct from each other and from `editorial-mono` before closing [Agent 3 finding]

### Documentation
- N/A — profile JSON files are self-documenting; render-path docs unchanged

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**R3 shadow override technical path**: Shadow tokens (`shadow.*`) live in `spacing.json`, not `semantic.json`. The merge order in `load_design_tokens()` is `**semantic_flat, **typography_flat, **spacing_flat, **theme_flat` — theme wins. Adding `shadow.*` keys directly to `themes/dark.json` (e.g. `"shadow": { "sm": "rgba(0,0,0,0.25)", "md": "rgba(0,0,0,0.4)", "lg": "rgba(0,0,0,0.55)" }`) correctly overrides the warm-brown `spacing.json` values; no changes to `spacing.json` needed.

**R5 lint structure**: Core comparison is `set(semantic["color"].keys()) - set(theme.get("color", {}).keys())` for each `themes/*.json` in every profile directory. Token groups in `semantic.json` are: `surface`, `text`, `border`, `action`. A half-flipped dark theme produces `{"border", "action"}` in the diff set. Implement as `scripts/little_loops/cli/verify_design_tokens.py` → `main_verify_design_tokens()`. Registration: add `ll-verify-design-tokens = "little_loops.cli:main_verify_design_tokens"` to `scripts/pyproject.toml` `[project.scripts]` block; add import + `__all__` entry in `scripts/little_loops/cli/__init__.py`. Entry-point function wraps body in `cli_event_context(DEFAULT_DB_PATH, "ll-verify-design-tokens", sys.argv[1:])` and supports `-C`/`--directory` and `--json` flags (follow `verify_package_data.py:main_verify_package_data()` shape).

**`_wcag_spot_check` is documentation-only**: Nothing in `design_tokens.py` reads or validates this key at runtime. `render_as_prompt_context()` skips `_`-prefixed keys. R4 is pure JSON editing — no Python changes required.

**`ll-artifact` command (acceptance criteria step 7)**: The `ll-artifact policy-builder` command referenced in acceptance criteria does not yet exist as a CLI tool — it is planned in FEAT-2301 but not implemented. The visual diff verification step must be deferred until FEAT-2301 ships. For this issue, dark-theme correctness can be validated by extending `TestIntegration.test_round_trip_dark_theme()` in `test_design_tokens.py` to assert resolved token values.

**`editorial-mono` gap (out of scope but noted)**: `editorial-mono/themes/dark.json` has the identical structural gap. Its `danger.500 == accent.500 = "#991b1b"`. The R5 lint will flag this profile automatically. Fixing `editorial-mono` is out of scope for ENH-2308 but should be tracked as a follow-on.

_Wiring pass added by `/ll:wire-issue`:_

**`editorial-mono` lint impact (R5 scope risk)**: After ENH-2308 completes R1–R4, `ll-verify-design-tokens` will still exit non-zero against the full bundled templates because `editorial-mono/themes/dark.json` remains incomplete. Two mitigations: (a) design `test_verify_design_tokens.py` exclusively around synthetic temp-dir fixtures (per `test_verify_package_data.py` pattern) so pass/fail is independent of bundled template state, and (b) document in the CLI help that `editorial-mono` is a known-incomplete profile. Without (a), the new CLI cannot serve as a CI gate until the `editorial-mono` follow-on resolves. [Agent 2 finding]

**CLI documentation wiring (R5 registration)**: Per `CONTRIBUTING.md` "Documentation wiring for new CLI tools", every new `ll-` tool must appear in 5 locations: `docs/reference/CLI.md`, `commands/help.md`, `.claude/CLAUDE.md`, `skills/configure/areas.md` (count `29 → 30`), `README.md` (counts `35 → 36`). The `ll-verify-package-data` tool (ENH-2277) did not add these — ENH-2308 should complete them for `ll-verify-design-tokens`. Also add 3 `DOC_STRINGS_PRESENT` tuples in `test_wiring_cli_registry.py`. [Agent 2 finding]

**`scripts/little_loops/cli/__init__.py` module docstring**: The module-level docstring (lines 1–36) lists every CLI tool by entry-point name; add a `ll-verify-design-tokens: Structural lint for half-flipped design-token theme profiles` bullet alongside the existing `ll-verify-*` entries (in addition to the import + `__all__` entry already in scope). [Agent 2 finding]

## Proposed Solution

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

## Scope Boundaries

- **In scope**: completing dark themes for `warm-paper` and `default` profiles (R1–R2); adding `*-300` bright primitive steps to both profiles (R2); theme-scoped shadow tokens for dark in both profiles (R3); extending `_wcag_spot_check.dark_mode` (R4); structural lint for half-flipped themes (R5).
- **Out of scope**: `design_tokens.py` render/emit path (verified correct against `policy-router-builder.html`); `cli/artifact/*`; `policy-router-builder.html.tmpl` — no changes to these files.

## Implementation Steps

1. Complete `warm-paper/themes/dark.json` — add `border`, `action`, `text.muted`, and shadow overrides with dark-tuned values (R1, R3)
2. Add `*-300` bright primitive steps to `warm-paper/primitives.json` for `danger`, `success`, `warning` (R2)
3. Mirror R1–R3 changes in `default/themes/dark.json` and `default/primitives.json`
4. Extend `_wcag_spot_check.dark_mode` in both profiles' `semantic.json` to cover `border`, `action.primary`, and status colors on `surface.primary` (R4)
5. Add `scripts/little_loops/cli/verify_design_tokens.py` with `main_verify_design_tokens()`: for each profile under the profiles dir, load `semantic.json` and each `themes/*.json`, compute `set(semantic["color"].keys()) - set(theme.get("color", {}).keys())`, fail on non-empty diff. Register as `ll-verify-design-tokens = "little_loops.cli:main_verify_design_tokens"` in `scripts/pyproject.toml` and add import + `__all__` entry in `scripts/little_loops/cli/__init__.py`. Add unit tests in `scripts/tests/test_verify_design_tokens.py` (model after `test_verify_package_data.py`). (R5)
6. Re-emit and visual-diff: `ll-artifact policy-builder && open policy-router-builder.html` — verify legible borders, distinct accent/danger, and visible card elevation in dark mode

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `### ll-verify-design-tokens` section to `docs/reference/CLI.md` (after `### ll-verify-package-data`); add one-liner to `commands/help.md`; add entry to `.claude/CLAUDE.md` "CLI Tools" section; update `skills/configure/areas.md` enumeration + count (`29 → 30`); increment CLI tool counts in `README.md` (`35 → 36`, two occurrences); add docstring bullet to `scripts/little_loops/cli/__init__.py`
8. Add 3 `DOC_STRINGS_PRESENT` tuples in `scripts/tests/test_wiring_cli_registry.py` for `"ll-verify-design-tokens"` targeting `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md`
9. Extend `TestIntegration.test_round_trip_dark_theme()` in `test_design_tokens.py` to assert `color.border.subtle`, `color.border.strong`, `color.action.primary`, and `shadow.*` contain dark-tuned values after R1; add dark-theme completeness check to `TestBundledProfilesLoadEndToEnd` scoped to `("default", "warm-paper")` only
10. Verify `test_profile_outputs_diverge()` still passes — dark-tuned `action.primary` values must remain distinct across all 3 profiles

## Impact

- **Priority**: P3 — Systemic dark-mode degradation across both shipped profiles; affects users with `active_theme: dark`; deferred over direct user impact because the render path is correct and the defect is profile-authoring-only
- **Effort**: Medium — 6 additive JSON edits across 5 profile files + 1 new lint; no changes to the Python rendering path
- **Risk**: Low — changes are additive and single-purpose per profile; render path verified unchanged; no breaking changes to the token-stamping API
- **Breaking Change**: No

## Notes

- Investigation source: `policy-builder-dark-mode-findings.md` (2026-06-26).
- Low risk: changes are additive and single-purpose per profile; render path unchanged.
- R5 (`default` is "complete, switch to it") from the original findings was
  **dropped** — `default` shares the same gap.

## Labels

`design-tokens`, `dark-mode`, `ux`

## Status

**Open** | Created: 2026-06-26 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-26T22:08:53 - `c619bbe2-2f0b-4c0f-8966-375ca40f0190.jsonl`
- `/ll:ready-issue` - 2026-06-26T22:08:41 - `c619bbe2-2f0b-4c0f-8966-375ca40f0190.jsonl`
- `/ll:ready-issue` - 2026-06-26T22:08:33 - `c619bbe2-2f0b-4c0f-8966-375ca40f0190.jsonl`
- `/ll:wire-issue` - 2026-06-26T21:51:50 - `c41b0be6-447c-4987-a77e-bb93caa058f6.jsonl`
- `/ll:refine-issue` - 2026-06-26T21:39:41 - `a3ad71ec-14e6-4cd4-b1cf-ee8ef18cadb6.jsonl`
- `/ll:format-issue` - 2026-06-26T21:29:57 - `0aa41fec-b43c-4c53-8ca7-f55cef54ee67.jsonl`
