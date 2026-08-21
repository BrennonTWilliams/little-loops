---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
completed_at: '2026-07-25T05:31:55Z'
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
relates_to:
- ENH-2308
confidence_score: 98
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 22
status: done
priority: P4
---

# ENH-2785: Complete the `editorial-mono` design-token theme so `ll-verify-design-tokens` can gate on exit 0

## Summary

`ll-verify-design-tokens` lints half-flipped themes (inverted
`surface`/`text` with light-tuned `border`/`action` defaults). Its own
docstring records that the bundled `editorial-mono` profile currently fails
this lint, with the fix deferred to a follow-on — but no open issue tracks
that follow-on (ENH-2308, which added the lint and fixed `warm-paper`/
`default`, is done).

## Location

- **File**: `scripts/little_loops/cli/verify_design_tokens.py`
- **Line(s)**: 197-205 (at scan commit: fb567390)
- **Anchor**: `docstring of main_verify_design_tokens`
- **Code**:
```python
    """Entry point for ll-verify-design-tokens.

    Returns 0 when no half-flipped themes are found; 1 otherwise.

    Note: run against the bundled little-loops templates this currently flags
    ``editorial-mono`` (a known-incomplete profile pending a follow-on); fix or
    point ``--profiles-dir`` at a complete profile set to gate CI on exit 0.
    """
```

## Current Behavior

Running the tool against the bundled templates exits 1 because
`editorial-mono` is half-flipped, so the lint cannot be used as a
zero-tolerance gate in the test suite.

## Expected Behavior

`editorial-mono` gets complete dark-tuned `border`/`action` token values;
`ll-verify-design-tokens` exits 0 on the bundled templates and can be wrapped
as a pytest gate.

## Proposed Solution

Flip the remaining `border`/`action` tokens in the `editorial-mono` dark
theme (mirroring the ENH-2308 fixes for `warm-paper`/`default`), update the
docstring note, and add a pytest test asserting exit 0 on bundled templates.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Root cause (exact lint condition)**: `scripts/little_loops/cli/verify_design_tokens.py`
`lint_profile()` computes `_INVERSION_GROUPS = frozenset({"surface", "text"})`.
`editorial-mono/themes/dark.json` overrides only `surface`+`text`, which
satisfies the inversion-subset check and triggers a completeness requirement
against `editorial-mono/semantic.json`'s full `color` group set (`surface`,
`text`, `border`, `action`). The diff is `missing = {"border", "action"}`,
producing `ThemeViolation(profile="editorial-mono", theme="dark",
missing_groups=["action", "border"])`.

**Files to change**:
- `scripts/little_loops/templates/design-tokens/profiles/editorial-mono/themes/dark.json`
  — currently only has `color.surface` and `color.text`; needs `color.border`
  and `color.action` added.
- `scripts/little_loops/templates/design-tokens/profiles/editorial-mono/primitives.json`
  — currently `color.accent` has only `500`/`700` steps and `color.danger` only
  `500`; no bright `*-300` step exists for either. `default`/`warm-paper`
  primitives both carry a `*-300` step used for dark-mode `action.primary`/
  `action.primary-hover`/`action.destructive` (e.g. warm-paper:
  `terracotta.300 = "#f7b886"`, `danger.300 = "#e06b3d"`). Editorial-mono will
  need equivalent `accent.300` and `danger.300` primitives added before
  `dark.json` can reference bright steps the same way.
- `scripts/little_loops/templates/design-tokens/profiles/editorial-mono/semantic.json`
  — `_wcag_spot_check.dark_mode` currently only has 2 entries (`text.primary`,
  `text.secondary`); `default`/`warm-paper` extend this block with
  `border.subtle`/`border.strong`/`action.primary`/`danger.*` contrast-ratio
  entries once those tokens exist (documentation convention, not lint-enforced).
- `scripts/little_loops/cli/verify_design_tokens.py:197-205` — docstring note
  on `main_verify_design_tokens()` currently says editorial-mono is
  "known-incomplete... pending a follow-on"; update once fixed.

**Pattern to mirror** (`default/themes/dark.json` and
`warm-paper/themes/dark.json`, both already passing the lint):
- `border.subtle`/`border.strong` reference a mid-range step of the profile's
  neutral scale, one/two steps lighter than the dark `surface.primary` (e.g.
  warm-paper: `border.subtle: paper.800`, `border.strong: paper.600` against
  `surface.primary: paper.950`). Editorial-mono's `ink` scale is a full 0–950
  ramp already, so the analogous values are `border.subtle: ink.800`,
  `border.strong: ink.600`.
- `action.primary` in dark mode uses a **brighter/lower** accent step than
  light mode (light: `accent.700`; dark: `accent.500`) — same accent primitive
  scale, different step.
- `action.destructive` in dark mode must be a **distinct** bright danger step
  (e.g. a new `danger.300`), never equal to `action.primary` — this breaks the
  `danger == action.primary` collision noted in the module docstring and in
  ENH-2308's issue body (editorial-mono's current light-mode
  `action.destructive = danger.500 = "#991b1b"` already collides with
  `action.primary-hover = accent.500 = "#991b1b"`).
- Both `default`/`warm-paper` dark themes also add a theme-scoped `shadow`
  block (`sm`/`md`/`lg`, high-alpha `rgba(0,0,0,...)`) not present in the
  light-only base — not required by the lint (lint only checks `color` groups)
  but present in both reference profiles for visual completeness.

**Test to add** (`scripts/tests/test_verify_design_tokens.py`): module docstring
notes fixtures are synthetic temp-dir trees specifically so tests are
independent of "the known-incomplete `editorial-mono` profile" — that caveat
should be removed once fixed. Add a bundled-templates gate test modeled on
`TestMain.test_clean_profiles_dir_returns_zero` (line 184) but pointed at the
real bundled dir (no `--profiles-dir` override needed; `_find_profiles_dir()`
auto-discovers `scripts/little_loops/templates/design-tokens/profiles`).
Also update `scripts/tests/test_enh1768_profile_system.py`'s
`_DARK_COMPLETE_PROFILES = ("default", "warm-paper")` (line ~354) to include
`"editorial-mono"` — that tuple already deliberately excludes it with a
comment citing this exact follow-on.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2949` — remove the `> **Note:** Run against the bundled little-loops templates, this currently flags \`editorial-mono\`...` block under the `ll-verify-design-tokens` entry once the theme is complete [Agent 2 finding]
- `.claude/CLAUDE.md:216` — drop the `(exit 1 on any violation; flags bundled \`editorial-mono\` pending its follow-on)` parenthetical from the `ll-verify-design-tokens` bullet [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1768_profile_system.py::TestBundledProfilesLoadEndToEnd::test_profile_outputs_diverge` (line ~331) — asserts `color.action.primary` differs across all 3 profiles in dark mode; verify the new `editorial-mono` dark `action.primary` (`accent.500`) stays distinct from `default`'s and `warm-paper`'s dark `action.primary` values, or this test breaks once editorial-mono's dark tokens are exercised alongside them [Agent 3 finding]
- `scripts/tests/test_enh1768_profile_system.py::TestBundledProfilesLoadEndToEnd::test_dark_theme_overrides_all_semantic_groups` and `::test_dark_theme_breaks_danger_primary_collision` — once `editorial-mono` is added to `_DARK_COMPLETE_PROFILES`, these existing loop-based tests automatically extend to cover it (no new test body needed beyond the tuple edit already scoped) [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/reference/CLI.md` — remove the stale `editorial-mono known-incomplete` note under the `ll-verify-design-tokens` entry
2. Update `.claude/CLAUDE.md` — drop the `flags bundled editorial-mono pending its follow-on` parenthetical
3. Add `"editorial-mono"` to `_DARK_COMPLETE_PROFILES` in `scripts/tests/test_enh1768_profile_system.py` and remove the excluding comment
4. Verify `test_profile_outputs_diverge` still passes given editorial-mono's new dark `action.primary` value

## Impact

- **Effort**: Small
- Unlocks using the verify tool as an enforced local CI gate.

## Resolution

Completed the `editorial-mono` dark theme so `ll-verify-design-tokens` exits 0
on the bundled templates:

- `primitives.json` — added `color.accent.300` (`#dc2626`) and
  `color.danger.300` (`#f87171`) bright steps.
- `themes/dark.json` — added `color.border` (`ink.800`/`ink.600`) and
  `color.action` (`accent.500`/`accent.300`/`danger.300`), plus a `shadow`
  block mirroring `default`/`warm-paper`.
- `semantic.json` — extended `_wcag_spot_check.dark_mode` with the new
  border/action/danger contrast entries.
- Removed the `editorial-mono` known-incomplete note from
  `main_verify_design_tokens()`'s docstring, `docs/reference/CLI.md`, and
  `.claude/CLAUDE.md`.
- Added `"editorial-mono"` to `_DARK_COMPLETE_PROFILES` in
  `test_enh1768_profile_system.py`.
- Added `TestMain::test_bundled_templates_return_zero` in
  `test_verify_design_tokens.py` to gate the bundled templates at exit 0.

## Status

`done` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T05:31:55 - `d71d8980-a554-484e-8f1c-7c7bb2af0be4.jsonl`
- `/ll:ready-issue` - 2026-07-25T05:25:50 - `4ba0412d-1bd8-4820-9c17-963c22513dc7.jsonl`
- `/ll:wire-issue` - 2026-07-25T05:23:52 - `79d20649-4f15-4133-a3f8-7f67f83a8349.jsonl`
- `/ll:refine-issue` - 2026-07-25T05:18:58 - `f599c588-b56e-4a06-a6c8-ed333f331511.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
