---
id: BUG-2275
type: BUG
priority: P2
status: open
captured_at: '2026-06-24T00:00:00Z'
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to:
- BUG-2273
- FEAT-2274
- ENH-2272
- BUG-938
- BUG-885
decision_ref: ARCHITECTURE-053
labels:
- bug
- packaging
- hooks
- host-compat
- cross-host
- install
- path-resolution
confidence_score: 84
outcome_confidence: 65
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 12
score_change_surface: 18
decision_needed: true
---

# BUG-2275: `hooks/` package-data (prompt template + Codex adapter) excluded from the wheel — prompt-optimization hook and Codex onboarding silently break

## Summary

Two pieces of package code under `little_loops/` read assets from the repo-root
`hooks/` tree, which is **not** in the pip wheel (`pyproject.toml` packages only
`little_loops/**` + `LICENSE`). Both degrade silently on every non-editable
install and every non-Claude host:

1. **Prompt-optimization hook** — `hooks/user_prompt_submit.py:37` resolves
   `_PROMPT_FILE = Path(__file__).resolve().parents[3] / "hooks" / "prompts" /
   "optimize-prompt-hook.md"` as a **module-level constant**. In a non-editable
   install this lands above `site-packages/` where `hooks/prompts/` does not
   exist; the handler hits `if not _PROMPT_FILE.is_file(): return exit_code=0`
   and the feature silently never fires. Because the path is a module constant
   with **no `CLAUDE_PLUGIN_ROOT` fallback**, even Claude plugin context cannot
   rescue it from a wheel install.

2. **Codex host adapter** — `init/writers.py:install_codex_adapter()` (line 365)
   reads `plugin_root / "hooks" / "adapters" / "codex" / "hooks.json"`, where
   `plugin_root` comes from the broken `_plugin_root()` (`init/cli.py:42`, the
   BUG-2273 resolver). On a `pip install` Codex user, `template_path.exists()` is
   `False` → the function returns `False` → **Codex gets no hook adapter**, with
   only a missing success line to show for it. This is *the* non-Claude
   onboarding path.

This is the `hooks/` companion to the `templates/` cluster (BUG-2271 / BUG-2273 /
ENH-2272 / FEAT-2274). The same root-cause class — *package code reaches outside
the package via `__file__` traversal to read a repo-root asset the wheel does not
contain and non-Claude hosts never deliver* — but a **different asset tree**
(`hooks/`) that FEAT-2274's scope explicitly **excludes**.

## Motivation

- **Prompt optimization is silently dead** for every `pip install little-loops`
  user and every non-Claude host — the feature reports success (exit 0) while
  doing nothing, so the breakage is invisible.
- **Codex onboarding is silently broken** on the dominant `pip install` path:
  `ll-init` prints no Codex confirmation line and writes no `.codex/hooks.json`,
  but exits 0. This blocks the entire Codex generalization track (EPIC-2257) at
  its first step.
- Both are masked by editable dev installs (`__file__` points into the source
  tree), so they ship undetected.

## Steps to Reproduce

**Prompt hook:**
1. `pip install little-loops` (non-editable) into a fresh venv; enable the
   prompt-optimization hook.
2. Submit a prompt ≥10 chars.
3. Observe: `user_prompt_submit.handle()` returns `exit_code=0` with empty
   stdout — no optimization template is ever rendered (`_PROMPT_FILE.is_file()`
   is `False`).

**Codex adapter:**
1. `pip install little-loops` (non-editable); have `codex` on PATH (or a
   `.codex/` dir present).
2. From a target project, run `ll-init --yes` (Codex auto-detected by
   `_detect_hosts`).
3. Observe: no `.codex/hooks.json` is written and no `[Codex] Hook adapter
   installed` line prints; `install_codex_adapter()` returned `False` because
   `template_path.exists()` is `False`.

## Root Cause

- **File**: `scripts/little_loops/hooks/user_prompt_submit.py`
- **Anchor**: module constant `_PROMPT_FILE` (line 37)

```python
_PROMPT_FILE = Path(__file__).resolve().parents[3] / "hooks" / "prompts" / "optimize-prompt-hook.md"
```

- **File**: `scripts/little_loops/init/writers.py`
- **Anchor**: `install_codex_adapter()` (line 343), `template_path` (line 365)

```python
template_path = plugin_root / "hooks" / "adapters" / "codex" / "hooks.json"
if not template_path.exists():
    return False
```

`plugin_root` is supplied by `init/cli.py:_plugin_root()` (line 42), the same
bare `__file__`×4 traversal BUG-2273 fixes. But fixing that resolver is **not
sufficient**: the assets it would resolve (`hooks/prompts/`, `hooks/adapters/`)
are not in the wheel, and FEAT-2274's packaging scope explicitly lists
`skills/`, `commands/`, `agents/`, `hooks/` as *out* of the wheel. Both delivery
and resolution must change.

## Current Behavior

- Prompt-optimization hook: silent no-op (exit 0, empty stdout) on every
  non-editable install; the module constant cannot be repointed via env var.
- Codex adapter: `install_codex_adapter()` returns `False`; `ll-init` writes no
  `.codex/hooks.json` and prints no Codex confirmation; run reports success.
- Both work in editable dev installs, masking the bug from maintainers.

## Expected Behavior

- `optimize-prompt-hook.md` and `hooks/adapters/codex/hooks.json` are resolvable
  regardless of install mode or host, via a deterministic resolver (the shared
  one introduced by BUG-2271 / BUG-2273 / ENH-2272), with the in-package bundle
  as the primary tier.
- When a required hook asset truly cannot be resolved, surface a **visible
  warning** rather than a silent no-op / skip.

## Proposed Solution

This bug refines the host-plugin-asset-vs-package-data boundary (BUG-938 /
ARCHITECTURE-053). FEAT-2274's own principle — *"data the wheel's code reads
should ship in the wheel"* — applies here: `optimize-prompt-hook.md` and the
Codex adapter template are read by package code, so they are **package data**,
not per-host-adapted plugin assets.

1. **Package the consumed `hooks/` assets into the wheel.** Move (or
   `force-include`) `hooks/prompts/` and `hooks/adapters/` under
   `little_loops/` so `Path(__file__).parent / ...` resolves in every install.
   Keep host-adapted plugin glue (`hooks/hooks.json`, host launcher scripts)
   out of the wheel per BUG-938 — only the assets *package code reads* move in.
2. **Replace `_PROMPT_FILE`'s module-constant traversal** with a lazy lookup via
   the shared resolver (env-var-first / in-package), computed inside `handle()`
   rather than at import time.
3. **Route `install_codex_adapter()`'s `template_path`** through the same shared
   resolver instead of the raw `plugin_root` from `_plugin_root()`, and **warn**
   (not silently return `False`) when the source template is missing — distinct
   from the "destination already exists" skip.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/user_prompt_submit.py` — replace `_PROMPT_FILE`
  module constant with a resolver-backed lazy lookup.
- `scripts/little_loops/init/writers.py` — `install_codex_adapter()`: resolve
  the template via the shared resolver; distinguish source-missing from
  dest-exists; signal the source-missing case to the caller.
- `scripts/little_loops/init/cli.py` — `_dispatch_host_adapters()` (line 57):
  warn when `install_codex_adapter()` skipped due to missing source.
- `scripts/pyproject.toml` — bundle `hooks/prompts/` and `hooks/adapters/` as
  package data (git mv into `little_loops/` per the BUG-885 precedent, or a
  `force-include` stanza).
- `hooks/scripts/user-prompt-check.sh` — **critical wiring gap**: this Bash
  shell script (Claude Code host path) has its own independent
  `SCRIPT_DIR`-relative read of `optimize-prompt-hook.md`
  (`${SCRIPT_DIR}/../prompts/optimize-prompt-hook.md`) that is completely
  separate from the Python `_PROMPT_FILE` fix. If `optimize-prompt-hook.md`
  moves into the Python package, this script's path traversal breaks for the
  Claude Code host entirely. Must be updated alongside the Python fix —
  either redirect to the in-package path via `python -c "import ..."` or
  use the same env-var-first / package-fallback pattern. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/__init__.py` — `main_hooks()` dispatch to
  `user_prompt_submit.handle`.
- `scripts/little_loops/init/cli.py:69` — `install_codex_adapter(project_root,
  plugin_root, ...)` call site.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/__init__.py` — re-exports `install_codex_adapter`
  in `__all__` (line 16, 36); return-type change (None/False/True sentinel) is
  a public API break at this surface. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/init/tui.py` — calls `_dispatch_host_adapters()` at
  line 868 (`_apply_config()`), which internally calls `install_codex_adapter()`.
  Inherits the warning behavior without direct code changes, but must be covered
  in testing. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/hooks/__main__.py` — imports and invokes `main_hooks()`
  as the CLI entry point; no code changes needed, but exercises the dispatch
  path that fires `user_prompt_submit.handle()`. [Agent 1 finding]

### Similar Patterns
- `issue_template._default_templates_dir()` — BUG-2271 (templates consumer).
- `init/cli.py:_plugin_root()` — BUG-2273 (templates consumer, shared resolver).
- `cli/loop/_helpers.py:get_builtin_loops_dir()` — BUG-885 (moved `loops/`
  in-package; the precedent for moving consumed assets into the wheel).
- `logo.py:get_logo()` — BUG-2276 (same class, `assets/`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Canonical resolver to model the lazy lookup after** — `skill_expander._find_plugin_root()` at `scripts/little_loops/skill_expander.py:22`:
```python
def _find_plugin_root() -> Path:
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent
```
For the in-package fix, `handle()` should resolve the prompt file as
`Path(__file__).parent / "prompts" / "optimize-prompt-hook.md"` (one hop, after
moving assets into `little_loops/hooks/prompts/`), with `CLAUDE_PLUGIN_ROOT`
checked first as the override tier.

**BUG-885 move-in-package pattern (exact code)** — `get_builtin_loops_dir()` at `scripts/little_loops/cli/loop/_helpers.py:822`:
```python
def get_builtin_loops_dir() -> Path:
    return Path(__file__).parent.parent.parent / "loops"
```
`loops/` lives at `scripts/little_loops/loops/` — inside the package tree — so
`packages = ["little_loops"]` in `pyproject.toml` picks it up automatically. No
extra `include` stanza needed after git-moving the directory into the package.

**No `importlib.resources` in codebase** — every existing asset resolution uses
raw `Path(__file__).parent...` traversal. Do not introduce `importlib.resources`;
follow the BUG-885 move-in-package pattern instead.

### Tests
- `scripts/tests/` — prompt hook: monkeypatch `__file__`/resolver to a
  non-editable path with no repo `hooks/`; assert the handler still resolves the
  in-package template (and renders), not a silent exit-0.
- `scripts/tests/test_ll_init.py` — Codex adapter: assert `.codex/hooks.json` is
  written from a non-editable resolver path, and that a missing source emits a
  warning rather than a silent `False`.

### Test Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/tests/test_hook_user_prompt_submit.py`** — existing test file for `user_prompt_submit.handle()`; extend here for the non-editable install scenario (patch `_PROMPT_FILE` to a tmp path with no `hooks/prompts/` and assert render still fires from the in-package path).
- **`scripts/tests/test_codex_adapter.py`** — existing test file for the Codex adapter; extend with source-missing warning assertion.
- **`scripts/tests/test_hooks_integration.py`** — existing integration test file; already contains `test_optimization_template_injected_when_claude_plugin_root_set()` at line 1313 which tests the `CLAUDE_PLUGIN_ROOT` env-var path. Add a companion test for the in-package fallback (env var unset; asset moved in-package; assert render fires).
- **`scripts/tests/test_init_core.py`** — primary init test file (not `test_ll_init.py`); contains `_PROJECT_ROOT` constant used by `patch("little_loops.init.cli._plugin_root", return_value=_PROJECT_ROOT)` (line 1104) — the established pattern for patching `_plugin_root` to the real repo root.
- **Test pattern to follow for env-var coverage**: `TestFindPluginRoot` class in `scripts/tests/test_skill_expander.py` uses `monkeypatch.setenv` / `monkeypatch.delenv` to exercise env-var-first and fallback branches independently.

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break and must be updated:**
- `scripts/tests/test_init_core.py:864` — `TestInstallCodexAdapter.test_skips_when_template_missing`: asserts `installed is False` for the missing-template case. After the sentinel change (`None` = source-missing, `False` = dest-exists skip, `True` = installed), this assertion must change to `assert installed is None`. [Agent 2 + Agent 3 finding]
- `scripts/tests/test_codex_adapter.py` — `TestCodexAdapterIntegration`: `ADAPTER_DIR` is hardcoded to `REPO_ROOT / "hooks" / "adapters" / "codex"`. If any of the Codex adapter files move into the package, **all six tests** in this class will break:
  - `test_adapter_files_exist` — asserts shell scripts exist at old path
  - `test_adapter_scripts_are_executable` — asserts executability at old path
  - `test_hooks_json_references_plugin_root_placeholder` — reads `hooks.json` at old path
  - `test_hooks_json_uses_matcher_startup`, `test_hooks_json_has_user_prompt_submit`, `test_hooks_json_has_post_tool_use` — same
  - `test_prompt_submit_sets_ll_hook_host_codex` + `test_adapter_sets_ll_hook_host_codex` + `test_post_tool_use_sets_ll_hook_host_codex` — run shell scripts at old path
  Update `ADAPTER_DIR` to the new in-package location after the move. [Agent 2 + Agent 3 finding]
- `scripts/tests/test_hooks_integration.py:1313` — `test_optimization_template_injected_when_claude_plugin_root_set` runs `user-prompt-check.sh` end-to-end via subprocess; if the Bash script's `SCRIPT_DIR`-relative path to `optimize-prompt-hook.md` is not updated, this assertion fails even with the Python fix applied. [Agent 2 finding]

**New tests to write:**
- `scripts/tests/test_hook_user_prompt_submit.py` — currently no test calls `handle()` with `prompt_optimization.enabled=True` and asserts `result.stdout` contains template content. Add: (a) test for the in-package resolver path (env var unset; assert render fires from `Path(__file__).parent / "prompts" / "..."`); (b) test for env-var override (monkeypatch `CLAUDE_PLUGIN_ROOT`; assert resolver uses env path). Follow `TestFindPluginRoot` pattern from `test_skill_expander.py`. [Agent 3 finding]
- `scripts/tests/test_init_core.py` — add test for the new warning path in `_dispatch_host_adapters()` when `install_codex_adapter()` returns `None` (source-missing). Follow `test_hosts_pi_graceful_unavailable` pattern at line 1504: assert warning string in `capsys.readouterr().err`. [Agent 3 finding]

### Packaging (see FEAT-2274)
- FEAT-2274 owns `templates/`; this bug extends the same wheel-delivery decision
  to the consumed `hooks/` subtrees. Coordinate the packaging mechanism (git mv
  vs force-include) so both land consistently.

### Documentation
- `docs/reference/API.md` — `install_codex_adapter`, `user_prompt_submit`.
- `docs/reference/HOST_COMPATIBILITY.md` — Codex adapter install prerequisites.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — directory tree (lines 85, 102) lists
  `hooks/prompts/optimize-prompt-hook.md` and `hooks/adapters/codex/prompt-submit.sh`
  at repo-root-relative paths; also line 1186 mentions `hooks/prompts/continuation-prompt-template.md`.
  Update if either directory moves in-package. [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — line 1021 instructs `ls -la hooks/prompts/optimize-prompt-hook.md`;
  lines 853-854 have `chmod +x hooks/adapters/codex/session-start.sh` and
  `chmod +x hooks/adapters/codex/pre-compact.sh`. Both become stale if files
  move in-package. [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — line 152 references
  `hooks/prompts/optimize-prompt-hook.md` by path in the `user_prompt_submit`
  description. [Agent 2 finding]
- `docs/codex/getting-started.md` — shows the rendered command string
  `bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/session-start.sh`; becomes
  stale if shell script paths change. [Agent 2 finding]
- `docs/codex/usage.md` — shows an example `hooks.json` fragment with
  `bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/pre-tool-use.sh`. [Agent 2 finding]
- `docs/codex/README.md` — states adapter is at `hooks/adapters/codex/`
  (line 24); update if directory moves. [Agent 2 finding]
- `docs/claude-code/write-a-hook.md` — line 190 references
  `hooks/adapters/codex/{session-start,pre-compact}.sh`; lines 324-325
  link to `hooks/adapters/codex/README.md`. [Agent 2 finding]

### Agents and Skills

_Wiring pass added by `/ll:wire-issue`:_
- `agents/consistency-checker.md` — "Hooks → Prompts" table (line 169) has
  a hardcoded row with `hooks/prompts/optimize-prompt-hook.md` as the resolved
  path. Update if file moves in-package. [Agent 2 finding]
- `.codex/agents/consistency-checker.toml` — mirrors the same table at
  line 143. [Agent 2 finding]
- `skills/audit-claude-config/SKILL.md` — line 44 references
  `hooks/prompts/*.md` and `hooks/adapters/` as canonical audit-scope paths.
  [Agent 2 finding]
- `skills/configure/areas.md` — line 890 references `hooks/adapters/codex/`
  as the Codex adapter location. [Agent 2 finding]
- `skills/audit-claude-config/wave1-prompts.md` — line 111 defines the audit
  scope as `hooks/prompts/*.md`; once `optimize-prompt-hook.md` moves
  in-package, this glob silently stops matching it and the audit no longer
  verifies the optimization template exists. Update to check the in-package
  path or parameterize the glob. [Agent 2 finding — second wiring pass]

### Configuration
- N/A — packaging and source layout changes only; no runtime configuration affected (`pyproject.toml` is listed under Files to Modify as a build-system change, not a runtime config).

## Implementation Steps

1. Move/force-include `hooks/prompts/` + `hooks/adapters/` into the wheel; build
   the wheel and assert `unzip -l dist/*.whl | grep -E 'hooks/(prompts|adapters)'`.
2. Repoint `_PROMPT_FILE` to a lazy, resolver-backed lookup inside `handle()`.
3. Route `install_codex_adapter()`'s `template_path` through the shared resolver;
   return a source-missing signal; warn in `_dispatch_host_adapters()`.
4. Add tests for both consumers on a simulated non-editable path; assert no
   silent degradation.
5. `python -m pytest scripts/tests/`; verify both reproduction steps pass in a
   clean venv with `CLAUDE_PLUGIN_ROOT` unset.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `hooks/scripts/user-prompt-check.sh` — this Bash file (Claude Code
   host) has its own `${SCRIPT_DIR}/../prompts/optimize-prompt-hook.md` path
   that is completely separate from the Python fix. After moving
   `optimize-prompt-hook.md` in-package, update this script to resolve the
   template from the new location (e.g., via
   `python -c "import little_loops.hooks; print(Path(little_loops.hooks.__file__).parent / 'prompts' / 'optimize-prompt-hook.md')"`)
   or consolidate so only the Python dispatcher reads the template file and
   the Bash script never reads it directly.
7. Decide and document the `{{LL_PLUGIN_ROOT}}` substitution for shell script
   paths — the `hooks/adapters/codex/hooks.json` template embeds
   `bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/<script>.sh`. If the shell
   scripts also move in-package, `install_codex_adapter()` must substitute a
   different base path (e.g., `Path(writers.__file__).parent` or the Python
   package install path) rather than `plugin_root`. This decision affects what
   `.codex/hooks.json` files look like for pip-installed users; make it
   explicit before implementing Step 1.
8. Update `scripts/tests/test_codex_adapter.py` — `ADAPTER_DIR` is hardcoded
   to `REPO_ROOT / "hooks" / "adapters" / "codex"`; update to the new path
   (in-package or repo-relative depending on Step 7's decision). Also update
   the 6+ tests that probe file existence, executability, and `hooks.json`
   content at the old path.
9. Update `scripts/tests/test_init_core.py:864` — change
   `assert installed is False` to `assert installed is None` in
   `test_skips_when_template_missing` after the sentinel change.
10. Update docs — `docs/ARCHITECTURE.md` directory tree (lines 85, 102, 1186),
    `docs/development/TROUBLESHOOTING.md` (lines 853-854, 1021),
    `docs/guides/BUILTIN_HOOKS_GUIDE.md` (line 152),
    `docs/codex/getting-started.md`, `docs/codex/usage.md`,
    `docs/codex/README.md`, `docs/claude-code/write-a-hook.md` (lines 190, 324-325)
    to reflect new paths.
11. Update agent/skill files — `agents/consistency-checker.md` (line 169),
    `.codex/agents/consistency-checker.toml` (line 143),
    `skills/audit-claude-config/SKILL.md` (line 44),
    `skills/configure/areas.md` (line 890) to reflect new paths.
12. Update `skills/audit-claude-config/wave1-prompts.md` (line 111) —
    the audit-scope glob `hooks/prompts/*.md` will no longer match
    `optimize-prompt-hook.md` once it moves in-package; update to also
    check `little_loops/hooks/prompts/` or replace with both paths.
    [second wiring pass]
13. If Step 7's decision is to move shell scripts in-package:
    update `hooks/adapters/codex/hooks.json` template body — the
    `{{LL_PLUGIN_ROOT}}/hooks/adapters/codex/<script>.sh` substitution
    pattern must be replaced with the in-package Python package install
    path so installed `.codex/hooks.json` files resolve correctly on
    pip-installed systems. [second wiring pass]

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Import-Time Evaluation of `_PROMPT_FILE`

`_PROMPT_FILE` is evaluated as a **module-level constant** — not inside `handle()`. The evaluation fires when `_dispatch_table()` in `hooks/__init__.py` first imports `user_prompt_submit` (lazy import on first hook dispatch). This means any fix that patches `_PROMPT_FILE` after import is too late; the lazy lookup **must** be inside `handle()` itself (Step 2).

### `install_codex_adapter()` Return-Value Overloading

`install_codex_adapter()` currently returns `False` for two distinct failure modes:
- **Line 368–369**: `template_path.exists()` is `False` → source missing → `return False`
- **Line 371–372**: destination already exists and `force=False` → `return False`

Both return `False`; `_dispatch_host_adapters()` cannot distinguish them. The fix (Step 3) should introduce a sentinel to separate these cases — e.g., `Optional[bool]` where `None` = source missing, `False` = dest-exists skip, `True` = installed — so `_dispatch_host_adapters()` can emit a warning specifically for the source-missing case without conflating it with the idempotent skip.

### Shell Scripts in `hooks/adapters/codex/`

`hooks/adapters/codex/` contains `hooks.json` (read by `install_codex_adapter()`) **and** five shell scripts (`prompt-submit.sh`, `session-start.sh`, `pre-compact.sh`, `post-tool-use.sh`, `README.md`). The `hooks.json` template contains `{{LL_PLUGIN_ROOT}}` substitutions that point to these scripts. If `hooks.json` is moved into `little_loops/hooks/adapters/codex/`, the substituted paths must resolve to the shell scripts at their new in-package location. Decide whether to move the shell scripts alongside `hooks.json` or whether the substituted paths should still reference a repo/plugin-root location (which would require the scripts to remain outside the wheel). This packaging scope question affects Step 1.

### `init/detect.py:_find_templates_dir()` — Out-of-Scope Sibling

`scripts/little_loops/init/detect.py` contains a `_find_templates_dir()` with the same three-levels-up `__file__` traversal pattern as `issue_template._default_templates_dir()`. Not in scope for this bug (no caller in this issue's fix surface) but should be tracked.

### Asset Files Confirmed in `hooks/prompts/`

Two files exist: `optimize-prompt-hook.md` (the one read by `user_prompt_submit.py`) and `continuation-prompt-template.md`. Verify whether `continuation-prompt-template.md` is read by any other Python code before deciding whether to move only `optimize-prompt-hook.md` or the entire `hooks/prompts/` directory.

## Impact

- **Priority**: P2 — a user-facing feature (prompt optimization) is silently
  dead and the entire Codex onboarding path is silently broken on the dominant
  `pip install` distribution, with no error surfaced.
- **Effort**: Small–Medium — packaging change + two resolver swaps + warnings +
  tests; rides on FEAT-2274's mechanism.
- **Risk**: Low — additive resolution + delivery; editable installs unaffected.
- **Breaking Change**: No (internal layout / packaging).

## Related

- BUG-2273 — fixes `_plugin_root()`; necessary but not sufficient here because
  `hooks/` assets aren't in the wheel.
- FEAT-2274 — packages `templates/` into the wheel; this bug extends that
  decision to the consumed `hooks/` subtrees (currently out of its scope).
- ENH-2272 — shared resolver this bug's lookups should consume.
- BUG-938 — closed invalid; this further refines the boundary (host-plugin glue
  out, package-data hooks in).
- BUG-885 — precedent for moving package-consumed assets into the package.
- BUG-2276 — sibling instance for `assets/` (CLI logo).
- ENH-2277 — systemic lint + wheel smoke test that would have caught this.

## Labels

`bug`, `packaging`, `hooks`, `host-compat`, `cross-host`, `install`,
`path-resolution`

## Status

**Open** | Created: 2026-06-24 | Priority: P2


---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers resolver + warning behavior + Bash script path updates (Step 6) and template substitution decisions (Step 7) only. The packaging `git mv` of `hooks/prompts/` and `hooks/adapters/` into the wheel is owned by **FEAT-2274**, which explicitly includes these assets in its scope. Do NOT perform the `git mv` independently here — coordinate with FEAT-2274 to ensure a single packaging move. Related issue: [FEAT-2274].

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-24_

**Readiness Score**: 84/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 65/100 → Below threshold

### Concerns
- Step 7 (`{{LL_PLUGIN_ROOT}}` substitution decision) is explicitly unresolved — the issue says "make it explicit before implementing Step 1"; gates packaging shape, `install_codex_adapter()` substitution, and what pip-installed `.codex/hooks.json` files contain
- FEAT-2274 (open) owns the `git mv`; the lazy resolver code changes in this issue yield a functional no-op until FEAT-2274 lands — sequence implementation accordingly
- Step 6 is likely a false concern: `hooks/scripts/user-prompt-check.sh` delegates entirely to `python -m little_loops.hooks user_prompt_submit` with no direct template read; Agent 2's finding appears stale — confirm before including Step 6 in scope

### Outcome Risk Factors
- **Open design decision in Step 7**: the open decision on whether Codex adapter shell scripts move in-package ripples through `install_codex_adapter()` return contract, `hooks.json` template substitution, and pip-installed user experience — resolve before starting implementation
- **Broad but shallow surface**: 15+ change sites across docs, agents/skills, and test files add coordination overhead; test-update count (~9 required changes) is fully enumerated but warrants careful sweep
- **ENH-2272 dependency mismatch**: ENH-2272 is cited as the "shared resolver this bug's lookups should consume" but is actually about ll-issues sections accessor; the canonical resolver pattern (`skill_expander._find_plugin_root()`) already exists at `skill_expander.py:22` — no need to wait for ENH-2272

## Session Log
- `/ll:confidence-check` - 2026-06-24T00:00:00Z - `77fa73e1-dacb-4249-8a20-ad4d9cb07c09.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-25T01:15:24 - `4d9c6bcd-b580-4f4a-bc4f-3993c0160aa9.jsonl`
- `/ll:wire-issue` - 2026-06-25T00:05:35 - `43ed8b20-75e9-4cc1-9df5-86b5a03e80d8.jsonl`
- `/ll:wire-issue` - 2026-06-24T23:44:40 - `3c0bdb5f-d2f8-4c48-b8d5-26b2377e2af9.jsonl`
- `/ll:refine-issue` - 2026-06-24T23:31:39 - `79c0e758-e055-44ee-9a4e-08b736264d83.jsonl`
- `/ll:format-issue` - 2026-06-24T23:22:53 - `805d4898-1c18-40f2-ad99-fdac06f4d00e.jsonl`
