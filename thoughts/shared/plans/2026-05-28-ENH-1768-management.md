# ENH-1768: Multi-profile design-tokens system — Implementation Plan

**Date**: 2026-05-28
**Issue**: `.issues/enhancements/P3-ENH-1768-design-tokens-originality-friendly-defaults.md`
**Mode**: `--quick` (deep research subagents skipped; direct codebase reads used instead)

## Goal

Generalize the design-tokens system into a **multi-profile** system. Ship 3 starter profiles (`default`, `editorial-mono`, `warm-paper`), each WCAG AA verified, each with a typography + spacing layer. Add a one-line `design_tokens.active` selector. Loops unchanged.

## Approach

Additive change with a legacy-flat-layout fallback. Loader checks `<path>/profiles/<active>/` first; if absent, falls back to the flat `<path>/` layout (existing projects). No loop YAML edits.

## Phase 0: Write Tests (Red) — TDD

(`tdd_mode` is enabled in `.ll/ll-config.json`.) Tests written first:

1. `test_enh1768_profile_system.py` (new) — profile resolution, missing-profile warning, switching active, legacy fallback, typography+spacing layer loads.
2. `test_config_schema.py` — extend `test_design_tokens_in_schema` with `active`, `profiles_dir`.
3. `test_config.py` — extend `TestDesignTokensConfig` with `active`, `profiles_dir` fields; round-trip in `to_dict`.
4. `test_design_tokens.py` integration block — switch to profile layout.
5. `test_feat1756_init_wiring.py` — assert init copies profiles and writes `active`.
6. `test_feat1757_configure_wiring.py` — assert configure exposes `active`/`profiles_dir`.

## Phase 1: Schema + Dataclass

- `config-schema.json` `design_tokens` block: add `active` (string, default `"default"`) and `profiles_dir` (string|null, default `null` → derived as `<path>/profiles`).
- `scripts/little_loops/config/features.py` `DesignTokensConfig`: add `active: str = "default"` and `profiles_dir: str | None = None`. Update `from_dict`.
- `scripts/little_loops/config/core.py` `to_dict()`: include `active` and `profiles_dir`.

## Phase 2: Loader

- `scripts/little_loops/design_tokens.py` `load_design_tokens`:
  - Compute candidate profile root: `<path>/<profiles_dir or "profiles">/<active>/`.
  - If profile root exists → use it as the token directory; also load optional `typography.json`/`spacing.json` from it and merge into resolved tokens.
  - Else if `<path>/<profiles_dir or "profiles">/` exists (meaning multi-profile installed but `<active>` missing) → log warning and return None.
  - Else if `<path>/<primitives_file>` exists (legacy flat layout) → use legacy path.
  - Else → return None.
- `scripts/little_loops/hooks/session_start.py`: extend warning to detect missing active profile.

## Phase 3: Bundle Profiles

- Restructure `templates/design-tokens/` → `templates/design-tokens/profiles/default/{primitives,semantic,typography,spacing}.json` and `themes/{light,dark}.json`. Colors unchanged.
- Author `templates/design-tokens/profiles/editorial-mono/` — editorial serif + grayscale + single accent (WCAG AA verified).
- Author `templates/design-tokens/profiles/warm-paper/` — warm cream surfaces + soft brown text + terracotta accent (WCAG AA verified).
- Each profile ships all 6 files (primitives, semantic, typography, spacing, themes/light, themes/dark).

## Phase 4: Init Wiring

- `skills/init/SKILL.md` Step 8 item 6 — copy `templates/design-tokens/profiles/` into `.ll/design-tokens/profiles/`; write `design_tokens.active: <chosen>`.
- `skills/init/interactive.md` Round 7 — after "Yes, initialize", show 3-choice profile picker.

## Phase 5: Configure Area

- `skills/configure/areas.md` `## Area: design_tokens` — show installed profile list, allow switching `active`.
- `skills/configure/show-output.md` `## design_tokens --show` — display `active`, `profiles_dir`.
- `skills/configure/SKILL.md` — keep existing mapping references.

## Phase 6: Verify

- `python -m pytest scripts/tests/test_design_tokens.py scripts/tests/test_config.py scripts/tests/test_config_schema.py scripts/tests/test_enh1768_profile_system.py scripts/tests/test_feat1756_init_wiring.py scripts/tests/test_feat1757_configure_wiring.py scripts/tests/test_builtin_loops.py -v`
- `ruff check scripts/` + `ruff format --check scripts/` + `mypy scripts/little_loops/`

Out-of-scope (per issue): per-loop overrides, profile inheritance, runtime WCAG validation, softening the no-new-colors clamp.
