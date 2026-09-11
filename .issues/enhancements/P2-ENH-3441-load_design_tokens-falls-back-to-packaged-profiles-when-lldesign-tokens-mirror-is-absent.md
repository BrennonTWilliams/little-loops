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
confidence_score: 95
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3441: load_design_tokens falls back to packaged profiles when .ll/design-tokens/ mirror is absent

## Summary

Token resolution reads only config.project_root/.ll/design-tokens (design_tokens.py ~433), which is a gitignored local mirror of scripts/little_loops/templates/design-tokens/profiles/ (ENH-3275). Any clean checkout (CI, new contributor, fresh ll-init) silently renders design-token-aware artifacts with no tokens, and test_policy_builder_renders_byte_identically_to_golden_fixture fails at byte 299. Add a packaged-profile fallback as the **last** resort plus a drift-gate test asserting mirror and packaged profiles agree (the objection ENH-3275 raised against committing the mirror). Do NOT regenerate the golden fixture in the degraded state (A5).

**Precedence correction (2026-09-10 confidence check).** Earlier revisions placed the packaged fallback *before* the root-`DESIGN.md` fallback in the `auto` path. That silently replaces a project's own design language with generic built-in defaults and breaks 6 pinned ENH-3264 acceptance criteria — measured, not inferred; see Expected Behavior and the confidence-check research findings below. The packaged fallback is now **last** in the `auto` path. Because this repository has no tracked root `DESIGN.md`, CI still resolves the packaged `default` profile and the byte-299 golden failure is fixed identically.

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
built-in profile of the same name, resolved via `importlib.resources` (same
pattern as `_resolve_export_profile_root`) and loaded through the already
root-agnostic `_load_profile_from_root` (design_tokens.py:357).

Resolution precedence, `source == "auto"`:

1. Materialized project mirror (unchanged — mirror always wins when present,
   preserving local overrides and ENH-3264's empty-mirror guard).
2. Root `DESIGN.md` (unchanged — **the project's own design language outranks
   a generic built-in**).
3. Packaged built-in profile matching `dt_cfg.active` (new, **last resort** —
   engages only when there is neither a mirror nor a root `DESIGN.md`).
4. Degrade-to-`None` warnings (unchanged ordering and wording).

Resolution precedence, `source == "profile"`:

1. Materialized project mirror (unchanged).
2. Packaged built-in profile matching `dt_cfg.active` (new — this path has no
   `DESIGN.md` fallback by design, so the packaged profile is its last resort).
3. `None` (unchanged).

`source == "design_md"` is untouched.

**Why the packaged fallback is last, not second.** `dt_cfg.active` defaults to
`"default"` in both the dataclass and `from_dict`, and the existing `auto`
branch documents this explicitly: resolution is *"keyed on what's on disk, not
on whether `active` is 'set' … so 'unset' is not observable."* An absent mirror
therefore cannot be distinguished from "user asked for `default`", so a
packaged-first ordering would override a real `DESIGN.md` on the strength of a
value nobody chose. Empirically confirmed: a project with `source=auto`, no
mirror, and a `DESIGN.md` carrying `color.primary: '#ff00aa'` resolves
`source='design_md'`, `resolved['color.primary'] == '#ff00aa'` today — it is
**not** tokenless, and packaged-first would silently replace those tokens.

This ordering still fixes the reported CI symptom: this repository tracks no
root `DESIGN.md`, so on a clean checkout steps 1 and 2 both miss and step 3
resolves the packaged `default` profile.

What retires the objection ENH-3275 raised against committing the mirror is
the fallback itself: the packaged profiles become the single load-bearing
token source on a clean checkout, so the (gitignored) mirror is no longer
required for correct rendering. The drift-gate test guards the deploy path,
not mirror drift: `deploy_design_tokens` is a bare `shutil.copytree` from the
in-package `templates/` tree (`init/writers.py:626`) that ll-init resolves
via `Path(__file__).parent / "templates"` (`issue_template.py:21`), so a gate
that materializes the mirror via deploy and byte-compares it against the
packaged profiles is comparing a copy against its own source — it cannot fail
in CI. Its only genuine failure mode is `CLAUDE_PLUGIN_ROOT`-rooted
divergence (`issue_template.py:31-34`), which never occurs in CI. Real
mirror↔packaged drift (a stale or hand-edited local mirror) is detectable
only by the secondary, skip-when-absent case on a developer machine — see the
drift-gate requirement under Program Design. The golden fixture is NOT
regenerated in the degraded state (A5) — it is regenerated only after the
fallback renders token-identical output.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Files to Modify**: `scripts/little_loops/design_tokens.py` only — confirmed anchors: `load_design_tokens` @ :412, `_load_profile_from_root` @ :357, `_materialized_token_root` (nested) @ :438. The resolver currently has zero importlib.resources wiring of its own (verified: no `importlib` hits in the file).
- **Packaged data needs no manifest change**: all 18 profile JSON files (`default`/`warm-paper`/`editorial-mono` × primitives/semantic/typography/spacing/themes) are already registered in `PACKAGE_DATA_ASSETS` (`scripts/little_loops/package_data.py:58-75`, ENH-3268 comment at :52-57) and gated by `scripts/tests/test_package_data_manifest.py` + `test_wheel_smoke.py`.
- **Dependent files (callers of `load_design_tokens`, confirmed)**: `artifact_template_kit.py:38,46` (`_cached_themed_tokens`, light+dark — feeds `policy_builder.py` indirectly via `themed_css_vars`/`stamp_page_shell` import at `policy_builder.py:61`); `cli/artifact/templatize.py:1158,1269`; `cli/artifact/design_md.py:64-92`; `fsm/context_seed.py:94-101` (`design_tokens_context` / `render_as_prompt_context`, consumed by 13+ loop YAMLs); `hooks/session_start.py:315-342`. All call the unchanged signature — no caller changes (matches Program Design's "no caller changes").
- **Doctor/verify periphery (read-only awareness)**: `cli/doctor.py:1061,1088` (`_full_design_tokens_data`/`_full_design_tokens_check`); `cli/verify_design_tokens.py:126,181` — `_find_profiles_dir` there resolves candidates across source-repo, installed, and `.ll/design-tokens/profiles` layouts independently; its `lint_profiles_dir` gates profile content, not mirror/packaged parity.
- **Conventions in force — accessor style**: when filesystem ops (`.is_dir()`/`.glob()`) follow, packaged assets are probed with `importlib.resources.files("little_loops").joinpath(...)` converted via `Path(str(traversable))` (`design_md.py:36-39`; `cli/artifact/dashboard.py:54-59`, docstring cites "D20 — files() yields a Traversable"). Three accessor variants coexist in the codebase; this Variant-A shape is the one for directory probing.
- **Conventions in force — degradation**: every miss path in `load_design_tokens` warns to `sys.stderr` and returns `None`, never raises; probes that must not print take `quiet=True` (`design_tokens.py:171-203`, :525-528, :557-568). Note: `_resolve_export_profile_root` emits no notice when it uses the packaged copy — precedent for a silent fallback, but unspecified either way for `load_design_tokens`.
- **Conventions in force — no shared resolver**: no shared packaged-asset Path helper exists (`dashboard.py::_packaged_path` is module-private; `package_data.check_asset_accessible` returns bool). Consolidation is out of scope per Scope Boundaries.
- **Prior art (both done)**: BUG-3370's stopgap copies `.ll/design-tokens` into verify-gate worktrees (`worktree_utils.py:698-705`, comment self-labels "Stopgap, not the durable fix") — this fallback is the durable fix that stopgap anticipated. ENH-3275 (repo resolves to no tokens) is the original diagnosis.
- **Tests (existing coverage)**: `test_design_tokens.py` (~50 `load_design_tokens` call sites); **`test_enh1768_profile_system.py:305-314` `test_completely_absent_path_returns_none` pins today's None-on-absent contract and must change with this ENH**; tmp-BRConfig construction pattern at `_make_config` (`test_enh1768_profile_system.py:62-71`) — minimal `.ll/ll-config.json` with a `design_tokens` block; `test_enh3268_design_md_export.py:376` `test_packaged_built_in_profile_exports_to_stdout` is the end-to-end packaged-fallback precedent; drift-gate shape precedent: `test_wiring_skills_and_commands.py:590-618` (byte-compare both copies, per-file offenders into one list, failure message names the regen command, skip when mirror absent).
- **Configuration/docs**: `.gitignore:158-163` ignores `.ll/design-tokens/`; `config-schema.json:1924-1935` (`design_tokens` section, default `.ll/design-tokens`); `DesignTokensConfig` fields at `config/features.py:363-401`; `docs/reference/CONFIGURATION.md:794-833` and `docs/reference/CLI.md:4934-4944` describe current resolution and may warrant a fallback note.

_Added by `/ll:confidence-check` — 2026-09-10 — corrections and measured findings. Two claims in the research block above are wrong and are superseded here:_

- **CORRECTION — "every miss path in `load_design_tokens` warns to `sys.stderr`".** False for the `source == "profile"` path, which is the path this ENH changes. Its two miss branches (`if not base_path.exists(): return None` and `if token_root is None: return None`) are **completely silent** — no `sys.stderr` write. Only the `auto` and `design_md` paths warn. So there is no "current ordering and wording" to preserve on the `profile` path, and the ENH must decide explicitly whether the new packaged fallback announces itself there. Recommendation: emit a one-line stderr notice on first packaged fallback use, because a silent substitution of built-in defaults for a project's own tokens is exactly the class of degradation this issue exists to fix.
- **CORRECTION — "existing behavior only changes for projects that currently render tokenless".** False under the packaged-before-`DESIGN.md` ordering the earlier revision specified. Measured on a tmp project root with `{"design_tokens": {"enabled": true}}` (so `source='auto'`, `active='default'`, `path='.ll/design-tokens'`), no mirror, and a root `DESIGN.md` containing `color.primary: '#ff00aa'`: today's result is `source='design_md'`, `source_path=<tmp>/DESIGN.md`, `resolved['color.primary'] == '#ff00aa'`. Packaged-first would silently return the built-in `default` profile instead. Projects with a `DESIGN.md` and no mirror do **not** render tokenless. This is why the precedence moved to last.
- **Test breakage is under-scoped by 7 tests.** The research block names only `test_enh1768_profile_system.py:305-314`. All of the following are **green today** (verified: `7 passed` for the `test_design_tokens.py` set, `2 passed` for `TestMissingProfileFallback`) and break under packaged-before-`DESIGN.md`. Under the corrected packaged-**last** ordering, items 1-5 pass unchanged and only 6-8 require edits:
  1. `test_design_tokens.py:291` `test_no_materialized_profile_still_resolves_tokens` — ENH-3264 **AC 1**, asserts `source == "design_md"`
  2. `test_design_tokens.py:300` `test_vendored_spec_fixture_parses_and_resolves_aliases` — AC 4/4b, asserts DESIGN.md-derived values (`color.action.primary == "#855300"`, `font.display.fontFamily`, `radius.lg`, `space.md`)
  3. `test_design_tokens.py:313` `test_components_dropped_from_resolved` — AC 7b (would pass vacuously if `source` flipped)
  4. `test_design_tokens.py:321` `test_guidance_populated_from_prose` — AC 8, asserts `"Brand & Style" in result.guidance`; the profile path sets `guidance=""`
  5. `test_design_tokens.py:347` `test_auto_falls_through_when_profile_dir_empty` — **AC 2b**, empty mirror + `DESIGN.md` → asserts `source == "design_md"`. The earlier revision's own acceptance criterion ("ENH-3264 empty-mirror guard … still routes to the packaged fallback before root `DESIGN.md`") directly contradicted this pinned test while claiming to preserve it
  6. `test_design_tokens.py:366` `test_auto_neither_present_returns_none` — AC 2d, asserts `None` when nothing exists → **must change** (packaged `default` now resolves). This is the intended behavior change
  7. `test_design_tokens.py:371` `test_source_profile_ignores_root_design_md` — AC 3, `source=profile` + `DESIGN.md` + no mirror → asserts `None` → **must change** (packaged fallback engages). The AC's *semantic* (ignore `DESIGN.md`) is preserved; only the `is None` assertion goes
  8. `test_enh1768_profile_system.py:305` `test_completely_absent_path_returns_none` → **must change** (already named). `test_enh1768_profile_system.py:298` `test_missing_profile_returns_none` (`active="nonexistent"`) survives — the packaged lookup misses too
- **The drift gate as specified has no CI signal.** `.ll/design-tokens/` is gitignored, so the mirror is absent on every clean checkout; a gate that "skips when absent" never runs in CI. It would only ever fire on a developer machine that happens to have a stale mirror — while packaged/mirror divergence introduced by a packaged-profile edit goes undetected in CI, and the local golden-fixture test and the CI golden-fixture test would then be validating different token sources. Fix: have the test **materialize** the mirror itself via `deploy_design_tokens` (`init/writers.py:587-622`) into a `tmp_path` and byte-compare that against the packaged profiles, so the gate runs unconditionally everywhere. Keep the ambient-mirror comparison as a second, skipping case if desired.
- **`importlib.resources` + `Path(str(traversable))` is directory-install-safe, not zip-safe.** `_load_profile_from_root` performs real filesystem reads (`token_root / dt_cfg.primitives_file` → `_load_json`), so the traversable must be an actual directory. This matches the existing `_resolve_export_profile_root` precedent and is fine for editable installs and pip-unpacked wheels (CI installs via `pip install -e "./scripts[dev]"`, `ci.yml:86`), but it will silently resolve to `None` — not raise — if the package is ever consumed straight off a `.whl` on `sys.path`. Worth a one-line comment at the new helper, not a redesign.
- **Unaddressed: a non-default `design_tokens.path`.** If a project points `path` somewhere custom and that directory is absent, falling back to the packaged `default` profile substitutes content the project never asked for and is indistinguishable from the clean-checkout case, because `path`'s default is not observable either. Under packaged-**last** this only bites when there is also no `DESIGN.md`, which limits the damage; still, the stderr notice recommended above is what makes it visible.
- **The golden-fixture test is not hermetic.** `test_policy_builder_renders_byte_identically_to_golden_fixture` (`test_enh3035_artifact_template_kit.py:62`) passes only `output=tmp_path`; the `BRConfig` it renders from is the **ambient repository root**, so the test reads whatever `.ll/design-tokens` the machine happens to have. It passes locally today (`1 passed in 1.23s`, mirror present). The packaged fallback makes it deterministic, which is the fix — but the ambient-state coupling is a latent test-hygiene defect worth noting in the EPIC even if it stays out of scope here.
- **Repo state confirmed**: no tracked root `DESIGN.md`; `.ll/design-tokens/profiles` present locally; packaged profiles `default`/`editorial-mono`/`warm-paper` all present under `scripts/little_loops/templates/design-tokens/profiles/`.

_Added by pre-implementation review — 2026-09-10 — verification of the above claims against `design_tokens.py`, `init/writers.py`, and `issue_template.py`:_

- **CONFIRMED — precedence, insertion points, and the 8-test enumeration are accurate** (`design_tokens.py:412-569` checked directly; every other test file referencing `load_design_tokens` mocks it — `test_cli_loop_lifecycle.py`, `test_ll_loop_program_md.py` patch it; `test_builtin_loops.py` asserts YAML context keys only — so step 7's verification set is complete).
- **CORRECTION — "drift gate runs in CI" overstated the signal.** `deploy_design_tokens` is a bare `shutil.copytree` from the in-package `templates/` tree (`init/writers.py:626`) that ll-init resolves via `Path(__file__).parent / "templates"` (`issue_template.py:21`, with a `CLAUDE_PLUGIN_ROOT` override at :31-34). The primary gate byte-compares a copytree of that tree against the tree — it cannot fail in CI. Expected Behavior, Program Design, step 4, and the drift-gate AC are reworded to claim deploy-path consistency, with mirror-drift detection explicitly local-only.
- **DECIDED — the fallback notice dedupes per `(project_root, active)`.** `artifact_template_kit._cached_themed_tokens` calls `load_design_tokens` twice per render (light + dark); "at most once per call" would double-print the notice in the exact symptom path this issue fixes.
- **EDGE — custom `active_theme` on the packaged fallback silently drops the theme layer.** `_load_json` returns `{}` for missing files (`design_tokens.py:80-82`) and packaged profiles ship only `light`/`dark` themes; a project with `active_theme: "sepia"`, no mirror, and no `DESIGN.md` resolves fallback tokens with no theme overrides and no warning. This matches mirror-path semantics today (same silent `{}`), so no new guard is required — implementer note only; the fallback notice may name the missing theme if cheap, but must not warn separately.
- **Follow-up candidate (out of scope here)**: BUG-3370's stopgap copying `.ll/design-tokens` into verify-gate worktrees (`worktree_utils.py:698-705`) becomes redundant once this fallback lands; capture its retirement as a separate issue so it does not live forever labeled "not the durable fix".

## Program Design

### Types

No new dataclasses; reuses `DesignTokens` (source stays `"profile"`).

### Signatures

- `_resolve_packaged_profile_root(dt_cfg: DesignTokensConfig) -> Path | None`
  (new, design_tokens.py) — mirrors `_resolve_export_profile_root`'s
  importlib.resources probe of
  `little_loops/templates/design-tokens/profiles/<dt_cfg.active>`; returns a
  path only when it would yield ≥1 token file (same strength as
  `_materialized_token_root`, so an empty packaged dir cannot satisfy the
  fallback either).
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None`
  (unchanged signature; new fallback branch in both the `profile` and `auto`
  paths — in `auto`, positioned **after** the root-`DESIGN.md` branch).

### Call Path

`auto` path: `load_design_tokens` → `_materialized_token_root()` → (miss) →
`_find_design_md()` → (miss) → `_resolve_packaged_profile_root(dt_cfg)` →
`_load_profile_from_root(dt_cfg, token_root, theme)` → existing
`render_as_prompt_context` / artifact-template consumers (no caller changes).

`profile` path: `load_design_tokens` → `_resolve_token_root()` → (miss) →
`_resolve_packaged_profile_root(dt_cfg)` → `_load_profile_from_root(...)` →
same consumers.

The packaged branch must be inserted at the end of each path, not woven into
the middle of the existing `active_missing_warning` logic — that logic
(`design_tokens.py` ~:547-568) computes a warning string keyed on
`base_path.exists()` and is emitted on the way to the `DESIGN.md` branch. If
the packaged fallback pre-empts `DESIGN.md`, those warnings would fire for a
resolution that then succeeds, producing a misleading `not found; using root
DESIGN.md instead` message on a run that never reads `DESIGN.md`. Keeping
packaged last leaves that block untouched.

Drift-gate test file (new): `scripts/tests/test_enh3441_packaged_profile_fallback.py`
- **Primary (runs everywhere, never skips)**: materialize the mirror via
  `deploy_design_tokens` into a `tmp_path`, then byte-compare every packaged
  profile's JSON set against that copy. Scope, stated honestly: this verifies
  deploy-path consistency and completeness — deploy is a `shutil.copytree`
  from the same in-package tree the fallback reads (`init/writers.py:626`,
  `issue_template.py:21`), so it cannot detect mirror drift, only divergence
  between the deploy source and the fallback's importlib root (possible only
  under a `CLAUDE_PLUGIN_ROOT` override, `issue_template.py:31-34`). The
  ambient `.ll/design-tokens/` is gitignored and absent on a clean checkout,
  so no CI-runnable comparison can detect a stale mirror.
- **Secondary (skips when absent)**: byte-compare against the ambient
  `.ll/design-tokens/profiles/<name>` when a developer has one, catching a
  stale local mirror.
- Plus a fallback test that constructs a `BRConfig` in a tmp project root with
  no mirror **and no `DESIGN.md`** and asserts `load_design_tokens` returns
  non-empty `resolved` for each packaged profile, and a precedence test
  asserting a root `DESIGN.md` still wins over the packaged fallback.
- Failure message names the mirror-regeneration path
  (`ll-init` deploy / `deploy_design_tokens`); shape per
  `test_wiring_skills_and_commands.py:590-618`.

## Scope Boundaries

- No regeneration of the golden fixture while in the degraded state (A5).
- No auto-creation or sync of the `.ll/design-tokens/` mirror — the fallback
  is read-only; materialization stays wherever it lives today. (The drift gate
  does call `deploy_design_tokens`, but into a pytest `tmp_path`, never into
  the project root — the read-only guarantee is about the project tree.)
- No change to `source == "design_md"` behavior or the DESIGN.md loader.
- No new profiles, themes, or theme-selection logic — only existing packaged
  built-ins participate.
- No changes to `_resolve_export_profile_root` / `design-md export` (it keeps
  its own resolution; unifying is out of scope).

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

1. Outcome — absent-mirror resolution: with `design_tokens.enabled: true`, `.ll/design-tokens/` absent, **and no root `DESIGN.md`**, `load_design_tokens` returns tokens from the packaged profile named by `dt_cfg.active` in both the `source == "profile"` and `source == "auto"` paths; the mirror still wins when present, and a root `DESIGN.md` still wins over the packaged fallback on the `auto` path (`deploy_design_tokens`, `init/writers.py:587-622`, skips silently when the destination exists — no interplay change required).
2. Constraint — **DESIGN.md precedence must not regress**. The five green ENH-3264 tests listed in the research findings above (`test_design_tokens.py:291`, `:300`, `:313`, `:321`, `:347`) must pass **unchanged**. They are the executable form of ACs 1, 4/4b, 7b, 8 and 2b. If any of them needs editing, the packaged fallback has been positioned too early — move it later rather than weakening the test.
3. Constraint — pinned old behavior that *does* change: `test_design_tokens.py:366` (`test_auto_neither_present_returns_none`, AC 2d), `test_design_tokens.py:371` (`test_source_profile_ignores_root_design_md`, AC 3 — semantic preserved, `is None` assertion goes), and `test_enh1768_profile_system.py:305-314` (`test_completely_absent_path_returns_none`). Each must be rewritten to assert the packaged fallback resolves, while retaining coverage of the genuinely-absent-everywhere case (unknown profile name, no mirror, no `DESIGN.md` → still `None`).
4. Outcome — drift gate with honest scope: the primary comparison materializes the mirror via `deploy_design_tokens` into a `tmp_path` and byte-compares it against the packaged profiles unconditionally; because deploy is a `shutil.copytree` from the same in-package tree the fallback reads, this verifies deploy-path consistency and completeness, not mirror drift — a copytree of X cannot diverge from X, and CI has no ambient mirror to be stale. A secondary case compares the ambient `.ll/design-tokens/` mirror and skips when absent; it is the only check that can detect real mirror↔packaged drift and is local-only. Per-file offenders collected into one list; failure message names the mirror-regeneration path. Do not describe the primary gate as retiring the ENH-3275 mirror-drift objection — the fallback's existence does that.
5. Outcome — fallback visibility: the packaged fallback emits a one-line `sys.stderr` notice naming the profile it substituted and why, so a project silently receiving built-in defaults instead of its own tokens is observable. This is a deliberate departure from `_resolve_export_profile_root`'s silent precedent, justified because `design-md export --profile <name>` is an explicit user request whereas `load_design_tokens` is not. Emitted at most once per `(project_root, active)` pair per process (module-level dedupe set): `artifact_template_kit._cached_themed_tokens` calls `load_design_tokens` twice per render (light + dark themes), and the notice is about the fallback source, not the theme — without the dedupe, the policy-builder render that motivated this issue prints the notice twice. Tests get fresh `tmp_path` roots, so per-test assertions on the notice are unaffected by the dedupe.
6. Constraint — golden fixture: `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` is NOT regenerated while the working tree is in the degraded state (A5); after the fallback lands, rendering must be token-identical, making regeneration unnecessary. Note the test is not hermetic (it renders from the ambient repo root), so confirm it passes both with the local mirror present and with the mirror temporarily moved aside.
7. Verification: `python -m pytest scripts/tests/test_design_tokens.py scripts/tests/test_enh1768_profile_system.py scripts/tests/test_enh3441_packaged_profile_fallback.py scripts/tests/test_enh3035_artifact_template_kit.py scripts/tests/test_package_data_manifest.py` exits 0 — **plus** `scripts/tests/test_hook_session_start.py` (ENH-3264 AC 9b pins that DESIGN.md-sourced projects don't trip the missing-token-path warning, `:675`) and `scripts/tests/test_enh3268_design_md_export.py` (packaged-resolution precedent, `:376`). Neither was in the original verification list and both exercise the changed resolver.
8. Verification — CI parity: the reported symptom is CI-only, so a local green run is necessary but not sufficient. Confirm `test_policy_builder_renders_byte_identically_to_golden_fixture` passes in a CI job (no mirror, no root `DESIGN.md`) with the golden fixture byte-identical to `main`.

## Impact

- **Priority**: P2 - Silent degradation on every clean checkout (CI, fresh
  `ll-init`, new contributors) plus a deterministic test failure; no data
  loss, so not P1.
- **Effort**: Small - Reuses the root-agnostic `_load_profile_from_root` and
  the importlib.resources pattern already proven in
  `_resolve_export_profile_root`; net new code is one resolver helper, two
  fallback branches, and one new test file. Larger than the original estimate
  on the test side: three existing tests must be rewritten (not one) and two
  additional test modules join the verification set.
- **Risk**: Low **with the packaged fallback positioned last** - Additive
  fallback; the only behavior that changes is for projects with neither a
  mirror nor a root `DESIGN.md`, which today render tokenless. Mirror-wins and
  `DESIGN.md`-outranks-built-in precedence preserve both local overrides and
  every pinned ENH-3264 acceptance criterion.
  - **Risk of the earlier packaged-*before*-`DESIGN.md` ordering was NOT low.**
    The prior text called the change "purely additive" and claimed behavior
    only changes "for projects that currently render tokenless". Measured
    behavior contradicts both: a `source=auto` project with no mirror and a
    real `DESIGN.md` resolves its own tokens today
    (`resolved['color.primary'] == '#ff00aa'` from the project file), and
    packaged-first silently replaces them with generic built-in defaults —
    a wrong-output regression in rendered artifacts and in
    `design_tokens_context` prompt seeding across 13+ loop YAMLs, with no
    warning on the `profile` path (which is silent today). It would also have
    broken 8 green tests, 6 of them encoding ENH-3264 ACs 1, 2b, 2d, 3, 4/4b
    and 8, while the issue named only 1.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Broad fanout through an unchanged signature (Criterion D, 10/25).** `load_design_tokens` has 6+ direct callers across `artifact_template_kit.py`, `cli/artifact/templatize.py`, `cli/artifact/design_md.py`, `fsm/context_seed.py` and `hooks/session_start.py`, and `context_seed`'s `design_tokens_context` feeds 13+ loop YAMLs. Nothing changes at the call sites, so a precedence error is not caught by a type or signature break — it surfaces only as different rendered output or different prompt context. This is why the precedence decision, not the resolver helper, is the load-bearing risk in this issue.
- **The originally specified precedence was a silent wrong-output regression.** Placing the packaged fallback before the root-`DESIGN.md` fallback would have replaced a project's own design language with generic built-ins. Measured, not inferred: a `source=auto` project with no mirror and a `DESIGN.md` carrying `color.primary: '#ff00aa'` resolves `source='design_md'` and its own value today. Its stated justification — "the config explicitly names an active profile" — is refuted by a comment already in the function (`active` defaults to `"default"`; "unset" is not observable). Corrected to packaged-**last**, which still fixes the CI symptom because this repo tracks no root `DESIGN.md`.
- **Test-rewrite surface was under-scoped 8→1, now enumerated.** Eight green tests break under the original ordering, six of them encoding ENH-3264 ACs 1, 2b, 2d, 3, 4/4b and 8. Under the corrected ordering five pass unchanged and three are intentional edits, all named in the research findings and pinned by an Acceptance Criteria regression guard.
- **The drift gate as originally specified had zero CI signal.** `.ll/design-tokens/` is gitignored, so a gate that skips when the mirror is absent never runs in CI. Redesigned to materialize the mirror via `deploy_design_tokens` into a `tmp_path` and compare unconditionally.
- **Minor open question (Criterion C, 18/25).** The `source == "profile"` miss path is silent today, so there is no existing warning convention to inherit; the stderr-notice wording recommended in step 5 is a judgment call, not a settled convention.


## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-10 (auto mode)_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of what
was wrong and fixed, not an outstanding action item).

Every substantive claim verified against the codebase at HEAD:

- **Anchors confirmed**: `load_design_tokens` @ `design_tokens.py:412`,
  `_load_profile_from_root` @ :357, `_materialized_token_root` nested @ :438 with
  the ≥1-token-file strength; `source == "profile"` miss branches are confirmed
  completely silent (~:514-520); `auto` path is materialized-profile → root
  `DESIGN.md` → `None`, with the `active_missing_warning` block positioned before
  the `DESIGN.md` branch exactly as Program Design describes (packaged-last leaves
  it untouched). `_resolve_export_profile_root` @ `cli/artifact/design_md.py:18`
  probes importlib + `Path(str(traversable))` as claimed; `deploy_design_tokens`
  @ `init/writers.py:587` is a bare `shutil.copytree`; `issue_template.py` bundles
  via `Path(__file__).resolve().parent / "templates"` with the
  `CLAUDE_PLUGIN_ROOT` override.
- **All seven `test_design_tokens.py` line anchors confirmed exactly** (:291, :300,
  :313, :321, :347, :366, :371) and each asserts what the issue says; the
  ENH-1768 and ENH-3268 test anchors (`:305`, `:298`, `:376`) and the wiring
  drift-gate shape precedent (:590-618) confirmed. Golden-fixture test exists at
  `test_enh3035_artifact_template_kit.py:62` and passes locally (`1 passed in
  1.28s`, ambient mirror present).
- **Corrections applied in this pass**: `cli/artifact/templatize.py:1152` →
  **:1158**; `ci.yml:83` → **:86**; `dashboard.py:54-59` →
  **`cli/artifact/dashboard.py:54-59`** (path prefix added).
- **Corroborated via code graph** (`ll-code callers-of load_design_tokens`,
  provider=codegraph, freshness=fresh): caller set matches the Integration Map —
  `artifact_template_kit.py:38,46`, `templatize.py:1158`, plus
  `design_md.py:92`, `fsm/context_seed.py:100` and `hooks/session_start.py:315+`
  confirmed by grep.
- **Check B6 (proposal-vs-code)**: no findings — the packaged-last ordering is
  coherent with the `active_missing_warning` block it leaves untouched, the 8-test
  enumeration matches the pinned assertions read directly, and the ACs cover every
  integration point in the map.
- **Check B7 (`ll-verify-evidence`)**: clean — no unverifiable quoted spans.
- **Decisions**: no active required rules; graceful pass. Dependencies: parent
  `EPIC-3436` exists; no Blocked By/Blocks edges to validate.

## Session Log
- `/ll:confidence-check` - 2026-09-11T04:23:43 - `72bc9566-b5bc-49d6-a785-486d2b2b5e12.jsonl`
- `/ll:verify-issues` - 2026-09-11T04:20:13 - `25b7684d-0d1e-49e4-8ff4-d0d175f721ca.jsonl`
- manual pre-implementation review - 2026-09-10 - applied fixes 1-3 (drift-gate scope, notice dedupe, missing-theme edge)
- `/ll:confidence-check` - 2026-09-11T03:46:23 - `3c54b1f6-0a02-45d5-aeb1-ed084c2c42f8.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:44:34 - `c5c0ddc3-456d-4110-b2d9-428ff5b6b0ce.jsonl`
- `/ll:format-issue` - 2026-09-10T22:08:52 - `2aa5ba7e-e812-413c-8722-f747da598300.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- [ ] Clean-checkout fallback: a `BRConfig` in a tmp project root with no `.ll/design-tokens/`, **no root `DESIGN.md`**, and `active` set to each of `default`/`warm-paper`/`editorial-mono` yields `load_design_tokens` returning non-empty `resolved` tokens, `source == "profile"` (parametrized over all three packaged profiles), on both the `auto` and `profile` source paths.
- [ ] Mirror precedence: when the mirror exists with the active profile, packaged profiles are not consulted — local overrides preserved.
- [ ] **`DESIGN.md` outranks the packaged built-in**: on the `auto` path, a project with no mirror but a root `DESIGN.md` carrying its own tokens still resolves `source == "design_md"` with the project's own values, not the packaged profile. This is the corrected ordering and the single most important criterion in this issue.
- [ ] `auto`-path ordering: mirror → root `DESIGN.md` → packaged built-in → degrade-to-`None`. Existing miss warnings (unknown profile, degrade-to-`None`) keep their current ordering and wording; the `active_missing_warning` block is not triggered on a run that resolves via the packaged fallback.
- [ ] ENH-3264 regression guard: `test_design_tokens.py::test_no_materialized_profile_still_resolves_tokens`, `::test_vendored_spec_fixture_parses_and_resolves_aliases`, `::test_components_dropped_from_resolved`, `::test_guidance_populated_from_prose`, and `::test_auto_falls_through_when_profile_dir_empty` all pass **unchanged**.
- [ ] Intended behavior changes are reflected, not deleted: `test_auto_neither_present_returns_none` (AC 2d), `test_source_profile_ignores_root_design_md` (AC 3), and `test_enh1768_profile_system.py::test_completely_absent_path_returns_none` are rewritten to assert the packaged fallback, and the genuinely-absent-everywhere case (unknown profile, no mirror, no `DESIGN.md`) still returns `None`.
- [ ] Fallback strength: an empty packaged profile dir cannot satisfy the fallback — same ≥1-token-file strength as `_materialized_token_root()` (`design_tokens.py:438-459`).
- [ ] Fallback visibility: resolving via the packaged fallback emits one `sys.stderr` notice naming the substituted profile, so a project receiving built-in defaults instead of its own tokens is observable. Emitted at most once per `(project_root, active)` pair per process (module-level dedupe), so the double `load_design_tokens` call in `artifact_template_kit._cached_themed_tokens` (light + dark) yields exactly one notice per render.
- [ ] Drift gate runs unconditionally (never skips) with its scope stated honestly: the primary byte-compare materializes the mirror via `deploy_design_tokens` into a `tmp_path` and compares it against the packaged profiles — verifying deploy-path consistency/completeness, not mirror drift (a copytree of X cannot diverge from X, and CI has no ambient mirror to be stale); it fails with a per-file offender list naming the regeneration path. The secondary case compares the ambient `.ll/design-tokens/` mirror, skips when absent, and is the only check that detects real mirror↔packaged drift (local-only signal).
- [ ] `test_policy_builder_renders_byte_identically_to_golden_fixture` passes on a clean checkout with the golden fixture unchanged (no regeneration in the degraded state) — verified in a CI job, not only locally, since the local machine has the mirror and the CI runner does not.
- [ ] No `PACKAGE_DATA_ASSETS` changes; `test_package_data_manifest.py` and `test_wheel_smoke.py` stay green.
- [ ] Adjacent suites stay green: `test_hook_session_start.py` (ENH-3264 AC 9b, `:675`) and `test_enh3268_design_md_export.py` (`:376`).
