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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Files to Modify**: `scripts/little_loops/design_tokens.py` only — confirmed anchors: `load_design_tokens` @ :412, `_load_profile_from_root` @ :357, `_materialized_token_root` (nested) @ :438. The resolver currently has zero importlib.resources wiring of its own (verified: no `importlib` hits in the file).
- **Packaged data needs no manifest change**: all 18 profile JSON files (`default`/`warm-paper`/`editorial-mono` × primitives/semantic/typography/spacing/themes) are already registered in `PACKAGE_DATA_ASSETS` (`scripts/little_loops/package_data.py:58-75`, ENH-3268 comment at :52-57) and gated by `scripts/tests/test_package_data_manifest.py` + `test_wheel_smoke.py`.
- **Dependent files (callers of `load_design_tokens`, confirmed)**: `artifact_template_kit.py:38,46` (`_cached_themed_tokens`, light+dark — feeds `policy_builder.py` indirectly via `themed_css_vars`/`stamp_page_shell` import at `policy_builder.py:61`); `cli/artifact/templatize.py:1152,1269`; `cli/artifact/design_md.py:64-92`; `fsm/context_seed.py:94-101` (`design_tokens_context` / `render_as_prompt_context`, consumed by 13+ loop YAMLs); `hooks/session_start.py:315-342`. All call the unchanged signature — no caller changes (matches Program Design's "no caller changes").
- **Doctor/verify periphery (read-only awareness)**: `cli/doctor.py:1061,1088` (`_full_design_tokens_data`/`_full_design_tokens_check`); `cli/verify_design_tokens.py:126,181` — `_find_profiles_dir` there resolves candidates across source-repo, installed, and `.ll/design-tokens/profiles` layouts independently; its `lint_profiles_dir` gates profile content, not mirror/packaged parity.
- **Conventions in force — accessor style**: when filesystem ops (`.is_dir()`/`.glob()`) follow, packaged assets are probed with `importlib.resources.files("little_loops").joinpath(...)` converted via `Path(str(traversable))` (`design_md.py:36-39`; `dashboard.py:54-59`, docstring cites "D20 — files() yields a Traversable"). Three accessor variants coexist in the codebase; this Variant-A shape is the one for directory probing.
- **Conventions in force — degradation**: every miss path in `load_design_tokens` warns to `sys.stderr` and returns `None`, never raises; probes that must not print take `quiet=True` (`design_tokens.py:171-203`, :525-528, :557-568). Note: `_resolve_export_profile_root` emits no notice when it uses the packaged copy — precedent for a silent fallback, but unspecified either way for `load_design_tokens`.
- **Conventions in force — no shared resolver**: no shared packaged-asset Path helper exists (`dashboard.py::_packaged_path` is module-private; `package_data.check_asset_accessible` returns bool). Consolidation is out of scope per Scope Boundaries.
- **Prior art (both done)**: BUG-3370's stopgap copies `.ll/design-tokens` into verify-gate worktrees (`worktree_utils.py:698-705`, comment self-labels "Stopgap, not the durable fix") — this fallback is the durable fix that stopgap anticipated. ENH-3275 (repo resolves to no tokens) is the original diagnosis.
- **Tests (existing coverage)**: `test_design_tokens.py` (~50 `load_design_tokens` call sites); **`test_enh1768_profile_system.py:305-314` `test_completely_absent_path_returns_none` pins today's None-on-absent contract and must change with this ENH**; tmp-BRConfig construction pattern at `_make_config` (`test_enh1768_profile_system.py:62-71`) — minimal `.ll/ll-config.json` with a `design_tokens` block; `test_enh3268_design_md_export.py:376` `test_packaged_built_in_profile_exports_to_stdout` is the end-to-end packaged-fallback precedent; drift-gate shape precedent: `test_wiring_skills_and_commands.py:590-618` (byte-compare both copies, per-file offenders into one list, failure message names the regen command, skip when mirror absent).
- **Configuration/docs**: `.gitignore:158-163` ignores `.ll/design-tokens/`; `config-schema.json:1924-1935` (`design_tokens` section, default `.ll/design-tokens`); `DesignTokensConfig` fields at `config/features.py:363-401`; `docs/reference/CONFIGURATION.md:794-833` and `docs/reference/CLI.md:4934-4944` describe current resolution and may warrant a fallback note.

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

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

1. Outcome — absent-mirror resolution: with `design_tokens.enabled: true` and `.ll/design-tokens/` absent, `load_design_tokens` returns tokens from the packaged profile named by `dt_cfg.active` in both the `source == "profile"` and `source == "auto"` paths, mirror still winning when present (`deploy_design_tokens`, `init/writers.py:587-622`, skips silently when the destination exists — no interplay change required).
2. Constraint — pinned old behavior: `test_enh1768_profile_system.py:305-314` asserts the current None-on-absent contract; the change is not complete until that test reflects the fallback while still covering the genuinely-absent-everywhere case (unknown profile name with no mirror).
3. Outcome — drift gate: a test byte-compares every packaged profile JSON against the `.ll/design-tokens/` mirror when the mirror exists, skips when absent, collects per-file offenders, and its failure message names the mirror-regeneration path (`ll-init` deploy / `deploy_design_tokens`) — shape per `test_wiring_skills_and_commands.py:590-618`.
4. Constraint — golden fixture: `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` is NOT regenerated while the working tree is in the degraded state (A5); after the fallback lands, rendering must be token-identical, making regeneration unnecessary.
5. Verification: `python -m pytest scripts/tests/test_design_tokens.py scripts/tests/test_enh1768_profile_system.py scripts/tests/test_enh3441_packaged_profile_fallback.py scripts/tests/test_enh3035_artifact_template_kit.py scripts/tests/test_package_data_manifest.py` exits 0.

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
- `/ll:refine-issue` - 2026-09-10T23:44:34 - `c5c0ddc3-456d-4110-b2d9-428ff5b6b0ce.jsonl`
- `/ll:format-issue` - 2026-09-10T22:08:52 - `2aa5ba7e-e812-413c-8722-f747da598300.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- [ ] Clean-checkout fallback: a `BRConfig` in a tmp project root with no `.ll/design-tokens/` and `active` set to each of `default`/`warm-paper`/`editorial-mono` yields `load_design_tokens` returning non-empty `resolved` tokens, `source == "profile"` (parametrized over all three packaged profiles).
- [ ] Mirror precedence: when the mirror exists with the active profile, packaged profiles are not consulted (local overrides preserved; ENH-3264 empty-mirror guard on the `auto` path still routes to the packaged fallback before root `DESIGN.md`, not to tokenless).
- [ ] `auto`-path ordering: packaged fallback engages before the root-`DESIGN.md` fallback; post-fallback miss warnings (unknown profile, degrade-to-`None`) keep their current ordering and wording.
- [ ] Fallback strength: an empty packaged profile dir cannot satisfy the fallback — same ≥1-token-file strength as `_materialized_token_root()` (`design_tokens.py:438-459`).
- [ ] Drift gate: mirror-vs-packaged byte-compare passes on a fresh `deploy_design_tokens` copy, skips when no mirror exists, and fails with a per-file offender list naming the regeneration path.
- [ ] `test_policy_builder_renders_byte_identically_to_golden_fixture` passes on a clean checkout with the golden fixture unchanged (no regeneration in the degraded state).
- [ ] No `PACKAGE_DATA_ASSETS` changes; `test_package_data_manifest.py` and `test_wheel_smoke.py` stay green.
