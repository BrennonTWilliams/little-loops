---
id: ENH-3441
type: ENH
title: load_design_tokens falls back to packaged profiles when .ll/design-tokens/
  mirror is absent
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# ENH-3441: load_design_tokens falls back to packaged profiles when .ll/design-tokens/ mirror is absent

## Summary

Token resolution reads only config.project_root/.ll/design-tokens (design_tokens.py ~433), which is a gitignored local mirror of scripts/little_loops/templates/design-tokens/profiles/ (ENH-3275). Any clean checkout (CI, new contributor, fresh ll-init) silently renders design-token-aware artifacts with no tokens, and test_policy_builder_renders_byte_identically_to_golden_fixture fails at byte 299. Add a packaged-profile fallback plus a drift-gate test asserting mirror and packaged profiles agree (the objection ENH-3275 raised against committing the mirror). Do NOT regenerate the golden fixture in the degraded state (A5).

## Current Behavior

`load_design_tokens` (design_tokens.py:412) resolves tokens exclusively from
`config.project_root / dt_cfg.path` (default `.ll/design-tokens/`):

- `source == "profile"`: returns `None` immediately when `base_path` does not
  exist (design_tokens.py:514-520).
- `source == "auto"`: `_materialized_token_root()` returns `None` when
  `base_path` is absent, then falls back to a root `DESIGN.md`, then `None`.

The packaged built-ins (`default`/`warm-paper`/`editorial-mono`) ship in
`scripts/little_loops/templates/design-tokens/profiles/` (declared in
package_data.py:58-73), but only `ll-artifact design-md export --profile`
can reach them (`_resolve_export_profile_root`,
cli/artifact/design_md.py:18). Every other consumer — artifact rendering,
`ll-doctor`-adjacent checks, tests — degrades silently to no tokens on a
clean checkout (CI, new contributor, fresh `ll-init`), where the gitignored
mirror (ENH-3275) is absent. Concrete symptom:
`test_policy_builder_renders_byte_identically_to_golden_fixture`
(tests/test_enh3035_artifact_template_kit.py:62) fails at byte 299 in that
environment.

## Expected Behavior

When the project mirror is absent (or its active profile is missing) and
`design_tokens.enabled` is true, token resolution falls back to the packaged
built-in profile of the same name, resolved wheel-safely via
`importlib.resources` (same pattern as `_resolve_export_profile_root`) and
loaded through the already root-agnostic `_load_profile_from_root`
(design_tokens.py:357). Resolution precedence:

1. Materialized project mirror (unchanged — mirror always wins when present,
   preserving local overrides and ENH-3264's empty-mirror guard).
2. Packaged built-in profile matching `dt_cfg.active` (new fallback; in the
   `auto` path it engages before the root-`DESIGN.md` fallback, since the
   config explicitly names an active profile).
3. Root `DESIGN.md` / degrade-to-`None` warnings (unchanged ordering and
   wording after that).

A drift-gate test asserts the packaged profiles and the mirror agree, which
retires the objection ENH-3275 raised against committing the mirror. The
golden fixture is NOT regenerated in the degraded state (A5) — it is
regenerated only after the fallback renders token-identical output.

## Program Design

### Types

No new dataclasses; reuses `DesignTokens` (source stays `"profile"`).

### Signatures

- `_resolve_packaged_profile_root(dt_cfg: DesignTokensConfig) -> Path | None`
  (new, design_tokens.py) — mirrors `_resolve_export_profile_root`'s
  importlib.resources probe of
  `little_loops/templates/design-tokens/profiles/<dt_cfg.active>`; returns a
  path only when it would yield ≥1 token file (same strength as
  `_materialized_token_root`, so an empty dir cannot beat `DESIGN.md`).
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None`
  (unchanged signature; new fallback branch in both the `profile` and `auto`
  paths).

### Call Path

`load_design_tokens` → `_resolve_packaged_profile_root(dt_cfg)` →
`_load_profile_from_root(dt_cfg, token_root, theme)` → existing
`render_as_prompt_context` / artifact-template consumers (no caller changes).

Drift-gate test file (new): `scripts/tests/test_enh3441_packaged_profile_fallback.py`
`_resolve_packaged_profile_root` vs `.ll/design-tokens/profiles/<name>` —
byte-compare every packaged profile's JSON set against the mirror when the
mirror exists; plus a fallback test that constructs a `BRConfig` in a tmp
project root with no mirror and asserts `load_design_tokens` returns
non-empty `resolved` for each packaged profile.

## Scope Boundaries

- No regeneration of the golden fixture while in the degraded state (A5).
- No auto-creation or sync of the `.ll/design-tokens/` mirror — the fallback
  is read-only; materialization stays wherever it lives today.
- No change to `source == "design_md"` behavior or the DESIGN.md loader.
- No new profiles, themes, or theme-selection logic — only existing packaged
  built-ins participate.
- No changes to `_resolve_export_profile_root` / `design-md export` (it keeps
  its own resolution; unifying is out of scope).

## Impact

- **Priority**: P2 - Silent degradation on every clean checkout (CI, fresh
  `ll-init`, new contributors) plus a deterministic test failure; no data
  loss, so not P1.
- **Effort**: Small - Reuses the root-agnostic `_load_profile_from_root` and
  the importlib.resources pattern already proven in
  `_resolve_export_profile_root`; net new code is one resolver helper, two
  fallback branches, and two tests.
- **Risk**: Low - Purely additive fallback; existing behavior only changes
  for projects that currently render tokenless, where any correct output is
  an improvement. Mirror-wins precedence preserves local overrides.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-10T22:08:52 - `2aa5ba7e-e812-413c-8722-f747da598300.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
