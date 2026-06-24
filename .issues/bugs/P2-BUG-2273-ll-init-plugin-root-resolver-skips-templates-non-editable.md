---
id: BUG-2273
type: BUG
priority: P2
status: open
captured_at: '2026-06-24T22:25:58Z'
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to:
- BUG-2271
- ENH-2272
- FEAT-2274
- BUG-885
- BUG-938
confidence_score: 87
outcome_confidence: 72
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 20
---

# BUG-2273: ll-init `_plugin_root()` resolver silently skips design-token / goals / project-type templates on non-editable installs

## Summary

`ll-init`'s `_plugin_root()` (`init/cli.py:41`) resolves the bundled
`templates/` directory **only** as `Path(__file__).parent.parent.parent.parent`
— a four-level traversal that lands on the repo root in an *editable* dev
install but on a non-existent path in a *non-editable* install
(`pip install little-loops`). The resulting `templates_dir` feeds
`detect_project_type()`, `deploy_goals()`, and `deploy_design_tokens()`. When
the directory does not resolve, project-type detection falls back to generic and
both deploy functions **silently return `False`** (skip-if-source-missing). So
the dominant onboarding path — `pip install little-loops` → `ll-init` in a target
project — runs, reports success, and quietly never deploys design tokens or the
goals template, and misdetects the project type.

This is the `ll-init`-side companion to **BUG-2271** (which fixes the
`issue_template._default_templates_dir()` resolver for the section-template
loaders) and **ENH-2272** (which adds the `ll-issues sections` accessor and
`.ll/templates/` deploy). Those two cover the *issue-section-template* consumer;
this bug covers the *`ll-init` template consumer* (design tokens, goals,
project-type detection), which goes through a **different resolver**
(`init/cli.py:_plugin_root()`) that has **no `CLAUDE_PLUGIN_ROOT` awareness at
all**. Crucially, `ll-init` runs as a standalone CLI in a plain shell where
`CLAUDE_PLUGIN_ROOT` is typically unset — so even BUG-2271's env-var-first fix
would not reach this path on its own.

Cross-host context: `ll-init` runs on every host via `pip install`, but the wheel
does not currently contain `templates/`, and non-Claude hosts never set
`CLAUDE_PLUGIN_ROOT` — so the structural fix is **FEAT-2274** (package
`templates/` into the wheel). Under the **Both (wheel + deploy)** decision
(ARCHITECTURE-053), `ll-init` should resolve the in-package `templates/` first;
this bug's job is to (a) consume that shared resolver instead of the bare
`__file__`×4 traversal and (b) surface a warning instead of a silent no-op when
no source resolves. This refines BUG-938: host-plugin assets stay out of the
wheel, package-data templates go in.

## Motivation

Silently breaks the dominant `pip install little-loops` → `ll-init` onboarding path:
- Affects every non-editable install — the expected production use case for external users
- Design tokens are never deployed, `.ll/ll-goals.md` is never written, and project-type detection always falls back to `generic`, all without any error or warning
- Users receive a success exit from `ll-init` but arrive at a misconfigured project
- Blocks downstream features (design tokens, goals templates, project-type-specific configuration) from working correctly on first install

## Steps to Reproduce

1. `pip install little-loops` (non-editable) into a fresh venv.
2. From a plain shell (no `CLAUDE_PLUGIN_ROOT` exported), `cd` into a target
   project that is **not** the little-loops repo.
3. Run `ll-init --yes` (or the interactive flow), selecting the `design_tokens`
   feature.
4. Observe: `ll-init` reports success, but `.ll/design-tokens/profiles/` is never
   created, `.ll/ll-goals.md` is never deployed, and project-type detection
   silently falls back to `generic` regardless of the project's actual stack.

## Root Cause

- **File**: `scripts/little_loops/init/cli.py`
- **Anchor**: `_plugin_root()` (line 41) → `templates_dir = plug_root / "templates"` (line 573)

```python
def _plugin_root() -> Path:
    """Return the little-loops project root (four parents above this file)."""
    return Path(__file__).parent.parent.parent.parent
```

In an editable install, `__file__` is `scripts/little_loops/init/cli.py`, so four
parents up is the repo root and `repo/templates/` exists. In a non-editable
install, `__file__` is `site-packages/little_loops/init/cli.py`, so four parents
up is somewhere above `site-packages/` and `<that>/templates/` does not exist.

Downstream, the missing directory degrades silently:
- `deploy_design_tokens()` (`init/writers.py:289`) returns `False` when
  `src_profiles.exists()` is `False`.
- `deploy_goals()` (`init/writers.py:240`) uses the same `templates_dir` and the
  same skip-if-source-missing shape.
- `detect_project_type()` (`init/detect.py:115`) cannot read the per-type config
  templates and falls back to generic.

Unlike `skill_expander._find_plugin_root()` (env-var-first), `_plugin_root()`
never consults `CLAUDE_PLUGIN_ROOT` — and because `ll-init` is a standalone CLI,
that env var is usually absent in its shell anyway.

## Current Behavior

`ll-init` from a non-editable install in a standalone shell:
- `detect_project_type()` → generic fallback (wrong template selection).
- `deploy_goals()` → no-op (returns `False`), `.ll/ll-goals.md` not written.
- `deploy_design_tokens()` → no-op (returns `False`), no `.ll/design-tokens/`.
- No warning or error surfaced; the run reports success.

Editable dev installs (`pip install -e ./scripts`) mask the bug because
`__file__` still points into the source tree.

## Expected Behavior

`ll-init` locates the bundled `templates/` directory regardless of install mode,
using a deterministic precedence and surfacing a clear warning when no source is
found (rather than silently skipping). Suggested precedence (aligned with
BUG-2271 / ENH-2272 so all template consumers share one resolver):

1. `config.issues.templates_dir` — explicit override, if set
2. `.ll/templates/` — project-local copy (where ENH-2272 deploys section
   templates; design-token/goals sources could live alongside)
3. `${CLAUDE_PLUGIN_ROOT}/templates` — plugin-distributed bundle, when the env
   var is set
4. `__file__`-relative — editable-dev fallback

When none resolve and a template-dependent feature was requested, emit a visible
warning instead of a silent no-op.

## Proposed Solution

1. Replace `_plugin_root()`'s bare `__file__`×4 traversal with a shared resolver
   (the same one BUG-2271 / ENH-2272 introduce), so `ll-init`, the section-
   template loaders, and `skill_expander` all agree on how `templates/` is found.
2. In the `ll-init` flow, when `deploy_design_tokens()` / `deploy_goals()` return
   `False` *because the source was missing* (distinct from "destination already
   exists"), surface a warning so the skipped deploy is visible.
3. Optionally have `detect_project_type()` warn (not error) when its template
   source is unresolved and it falls back to generic.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_plugin_root()` / `templates_dir`
  resolution (lines 41–42, 573); warn on missing-source skips.
- `scripts/little_loops/init/writers.py` — `deploy_design_tokens()` (line 265)
  and `deploy_goals()` (line 240): distinguish "source missing" from
  "destination exists" in the return/log so callers can warn.
- `scripts/little_loops/init/detect.py` — `_find_templates_dir()` (~line 31): identical four-parent traversal bug site (`Path(__file__).parent.parent.parent.parent / "templates"`) that **must also be replaced with the shared resolver** (not just given a warning); and `detect_project_type()` (line 115): warn when template source is unresolved.

### Similar Patterns
- `skill_expander._find_plugin_root()` (`skill_expander.py:22`) — the env-var-
  first resolution to mirror / share.
- `cli/loop/_helpers.py:get_builtin_loops_dir()` — BUG-885 fixed the identical
  `__file__`-traversal-breaks-in-wheel class for `loops/`.
- `issue_template._default_templates_dir()` — BUG-2271's target; same class,
  different consumer.

### Packaging (see FEAT-2274)
- `scripts/pyproject.toml` packaging is changed by **FEAT-2274** (package
  `templates/` into the wheel), which is the structural prerequisite for this
  fix on non-Claude hosts. This bug owns the `ll-init` resolver + warning
  behavior, not the packaging change itself. The earlier "do not bundle (BUG-938
  stance)" note is superseded for package-data templates by ARCHITECTURE-053.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py` — `_plugin_root()` derives `templates_dir` (consumed inline); callers of `templates_dir`: `detect_project_type()`, `deploy_goals()`, `deploy_design_tokens()`
- `scripts/little_loops/init/writers.py` — `deploy_design_tokens()` and `deploy_goals()` receive `templates_dir` from `cli.py`
- `scripts/little_loops/init/detect.py` — `detect_project_type()` reads per-type config templates via `templates_dir`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/tui.py` — `_apply_writes()` (line 843) calls `deploy_goals(ll_dir, templates_dir)` and `deploy_design_tokens(ll_dir, templates_dir, ...)` (line 847), discarding both returns; `run_tui()` (line 239) calls `detect_project_type()` with `templates_dir`; verify whether `templates_dir` is passed from `cli.py`'s resolver or resolved independently — if independently resolved, `tui.py` has the same `_plugin_root()` bug and must also consume the shared resolver
- `scripts/little_loops/init/__init__.py` — re-exports `deploy_design_tokens`, `deploy_goals`, `detect_project_type` in `__all__`; this is the public API boundary — if return-value semantics change (e.g., `False` split into two distinct states), this marks the scope of the API change (no code edit needed here, but signals the change is public)

### Tests
- `scripts/tests/test_init_core.py` — primary init test file (not `test_ll_init.py`); existing `TestDeployGoals.test_skips_if_template_missing` already tests the source-missing path but only asserts `False` — extend to also assert warning emitted; add: (a) resolver finds bundled `templates/` when `_plugin_root` is patched to a non-editable path; (b) missing source emits a visible warning instead of silent skip; (c) editable-install fallback still resolves.
- See `test_skill_expander.py:TestFindPluginRoot` for the `monkeypatch.setenv`/`monkeypatch.delenv` env-var test pattern to follow.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py` — `generic_template` fixture (lines 461–464, 968–971) calls `detect_project_type(tmp_path, _TEMPLATES_DIR)` directly; review for breakage if `detect_project_type()` gains a warning when template source is unresolved
- New `TestPluginRoot` class in `test_init_core.py` (to write) — dedicated unit tests for `cli._plugin_root()` itself; no such class exists; follow `TestFindPluginRoot` pattern in `test_skill_expander.py` (lines 37–50): `monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", ...)` for env-var path, `monkeypatch.delenv(...)` for fallback
- New `TestFindTemplatesDir` class in `test_init_core.py` (to write) — `detect._find_templates_dir()` has **zero test coverage**; same `TestFindPluginRoot` structure; verify the four-parent traversal resolves to the correct path and that the fixed resolver handles the non-editable case
- `TestDeployDesignTokens.test_skips_if_source_missing` (new test to write) — parallel to the existing `TestDeployGoals.test_skips_if_template_missing`; currently `TestDeployDesignTokens` has NO source-missing test; assert both `created is False` and warning emission via `capsys`; the `test_skips_if_already_exists` test only covers the "dest exists" early-return path
- Tests that may break if `deploy_design_tokens()` / `deploy_goals()` return-value semantics change: `TestDeployDesignTokens` (all 3), `TestDeployGoals.test_skips_if_already_exists` — review these if `False` is split into distinct states

### Documentation
- `docs/reference/CLI.md` — `ll-init` command docs; verify `--design-tokens` flag description reflects actual deployment behavior
- `docs/reference/API.md` — if `_plugin_root()` or template resolution is documented, update to reflect the new shared resolver

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — section "Auto-scaffolding built-in profiles" → "Case B" (line ~685) currently describes the silent-skip when no profiles directory exists; update to reflect that missing template source now emits a visible warning instead of a silent no-op

### Configuration
- N/A — no config file changes; the shared resolver will honor `config.issues.templates_dir` as an optional override without requiring a new config key

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`detect_project_type()` actual behavior (correction):** The issue summary and Current Behavior section say "falls back to generic." Research shows `detect_project_type()` calls `_load_templates(templates_dir)` which calls `templates_dir.glob("*.json")` — on a non-existent directory this **raises `FileNotFoundError`**, not a graceful fallback. The exception is uncaught by `_run_yes()`. Verify empirically before implementing; if the outer `main_init()` has a catch-all, behavior may differ.

**`detect.py` dual resolver:** `detect.py` has two path-resolution functions — `_find_templates_dir()` (~line 31, same buggy four-parent pattern) and `detect_project_type(templates_dir=None)`. `main_init()` always passes a `templates_dir` argument so `_find_templates_dir()` is never called in practice; but both must be fixed to avoid the same latent bug if `detect_project_type` is ever called without an argument.

**Warning emission pattern:** Established in `init/cli.py`: `print(f"  Warning: ...", file=sys.stderr)`. Structured warnings use the `DepWarning` dataclass (`init/validate.py`) collected into a list and printed by the caller. Either pattern is valid; the inline `print` to stderr is simpler for the missing-source case.

**Existing test coverage:**
- `test_init_core.py:TestDeployGoals.test_skips_if_template_missing` — already asserts `deploy_goals()` returns `False` for missing source; extend to `capsys`-assert the warning is printed.
- `test_init_core.py:TestMainInit` — already patches `_plugin_root` via `patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT)`; use the same pattern for non-editable-path simulation.
- `test_skill_expander.py:TestFindPluginRoot` — env-var test pattern: `monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))` / `monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)`.

**`install_check.py` editable detection:** Contains `detect_installation()` which can determine whether the package is an editable install; could augment warning messages with install-mode context if desired (non-blocking enhancement).

**No `importlib.resources` usage exists** in the codebase yet — the package-data access path (for FEAT-2274's wheel bundling) will need to introduce it; this bug's resolver fix should remain `__file__`-based for the editable fallback and env-var / config for the non-editable path.

## Implementation Steps

1. Factor / reuse the shared template resolver (config → `.ll/templates/` →
   `CLAUDE_PLUGIN_ROOT` → `__file__`) introduced by BUG-2271 / ENH-2272 and call
   it from `init/cli.py` instead of `_plugin_root() / "templates"`.
2. Make `deploy_design_tokens()` / `deploy_goals()` report *why* they returned
   `False` (source-missing vs. dest-exists); have the `ll-init` flow warn on the
   source-missing case.
3. Add tests: monkeypatch the resolver to a temp `templates/` and assert deploys
   land; assert that an unresolved source produces a warning, not a silent skip;
   assert the editable-install `__file__` fallback still works.
4. Run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Audit `scripts/little_loops/init/tui.py` — check whether `_apply_writes()` and `run_tui()` resolve `templates_dir` independently of `cli.py`'s `_plugin_root()` call; if yes, replace with the same shared resolver (same bug, different call site)
6. Write `TestPluginRoot` test class in `test_init_core.py` — unit-test `cli._plugin_root()` resolver directly (env-var path + `__file__` fallback), following `TestFindPluginRoot` pattern in `test_skill_expander.py`
7. Write `TestFindTemplatesDir` test class in `test_init_core.py` — unit-test `detect._find_templates_dir()` (zero coverage today)
8. Write `TestDeployDesignTokens.test_skips_if_source_missing` — assert `False` return AND warning emission via `capsys` (parallel to existing `TestDeployGoals.test_skips_if_template_missing`)
9. Update `docs/reference/CONFIGURATION.md` — revise "Case B" description to reflect that missing template source now warns instead of silently no-oping

## Impact

- **Priority**: P2 — Silently degrades `ll-init`, the primary onboarding command
  for the dominant `pip install little-loops` → `ll-init` path; design tokens and
  goals never deploy and project-type detection is wrong, with no error surfaced.
- **Effort**: Small–Medium — share an existing resolver; thread a "source
  missing" signal into two deploy functions; add tests.
- **Risk**: Low — additive precedence + warnings; editable installs unaffected.
- **Breaking Change**: No.

## Related

- BUG-2271 — fixes `issue_template._default_templates_dir()` (env-var-first) for
  the section-template loaders; this bug is the `ll-init`/`_plugin_root` companion
  for design-token / goals / project-type consumers.
- ENH-2272 — `ll-issues sections` accessor + `.ll/templates/` deploy + unified
  resolver precedence; this bug should consume that same resolver.
- FEAT-2274 — packages `templates/` into the wheel (the **Both** decision); the
  structural prerequisite this `ll-init` fix relies on for non-Claude hosts.
- BUG-938 — Plugin assets missing from pip wheel (closed **invalid**); FEAT-2274
  refines its rule (host-plugin assets out, package-data templates in).
- BUG-885 — Built-in loops missing after pip install; same `__file__`-traversal
  failure class (fixed by moving `loops/` into the package).

## Labels

`bug`, `ll-init`, `templates`, `design-tokens`, `install`, `path-resolution`

## Status

**Open** | Created: 2026-06-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-24_

**Readiness Score**: 87/100 → PROCEED
**Outcome Confidence**: 72/100 → Moderate risk

### Outcome Risk Factors
- **Soft dependency coupling on 3 open issues**: BUG-2271, ENH-2272, and FEAT-2274 are all open. Step 1 says "reuse the shared resolver introduced by BUG-2271/ENH-2272" — without coordination, both issues could introduce incompatible independent resolver implementations. Resolve who owns the shared resolver function before starting.
- **Behavior verification before implementing warning strategy**: Codebase research found that `detect_project_type()` calls `templates_dir.glob("*.json")` on a non-existent directory, which raises `FileNotFoundError` — not a graceful fallback. The warning must be placed upstream of the load call. Verify empirically before writing the `detect.py` warning code.
- **Return-value semantics for deploy functions**: Distinguishing "source missing" from "destination exists" in `deploy_goals()`/`deploy_design_tokens()` affects ~5 call sites in `cli.py`/`tui.py` plus 3–4 test methods. Using a side-effect warning (`print` to stderr inside the function) avoids this cost; decide which approach before implementation begins.

## Session Log
- `/ll:confidence-check` - 2026-06-24T23:30:00Z - `f4b1792d-435d-44eb-b05e-5ac1ba224be4.jsonl`
- `/ll:wire-issue` - 2026-06-24T23:18:11 - `f4b1792d-435d-44eb-b05e-5ac1ba224be4.jsonl`
- `/ll:refine-issue` - 2026-06-24T23:07:14 - `cdada0da-4753-458e-a13a-508a5ae683e0.jsonl`
- `/ll:format-issue` - 2026-06-24T22:57:31 - `cd6e14d6-0ccd-4ef9-8c5e-8b0a2f72105e.jsonl`
- `/ll:capture-issue` - 2026-06-24T22:25:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4149029-8124-4b7f-a1de-e3e84bc0d161.jsonl`
