---
id: BUG-2275
type: BUG
priority: P2
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2257
relates_to: [BUG-2273, FEAT-2274, ENH-2272, BUG-938, BUG-885]
decision_ref: ARCHITECTURE-053
labels: [bug, packaging, hooks, host-compat, cross-host, install, path-resolution]
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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/__init__.py` — `main_hooks()` dispatch to
  `user_prompt_submit.handle`.
- `scripts/little_loops/init/cli.py:69` — `install_codex_adapter(project_root,
  plugin_root, ...)` call site.

### Similar Patterns
- `issue_template._default_templates_dir()` — BUG-2271 (templates consumer).
- `init/cli.py:_plugin_root()` — BUG-2273 (templates consumer, shared resolver).
- `cli/loop/_helpers.py:get_builtin_loops_dir()` — BUG-885 (moved `loops/`
  in-package; the precedent for moving consumed assets into the wheel).
- `logo.py:get_logo()` — BUG-2276 (same class, `assets/`).

### Tests
- `scripts/tests/` — prompt hook: monkeypatch `__file__`/resolver to a
  non-editable path with no repo `hooks/`; assert the handler still resolves the
  in-package template (and renders), not a silent exit-0.
- `scripts/tests/test_ll_init.py` — Codex adapter: assert `.codex/hooks.json` is
  written from a non-editable resolver path, and that a missing source emits a
  warning rather than a silent `False`.

### Packaging (see FEAT-2274)
- FEAT-2274 owns `templates/`; this bug extends the same wheel-delivery decision
  to the consumed `hooks/` subtrees. Coordinate the packaging mechanism (git mv
  vs force-include) so both land consistently.

### Documentation
- `docs/reference/API.md` — `install_codex_adapter`, `user_prompt_submit`.
- `docs/reference/HOST_COMPATIBILITY.md` — Codex adapter install prerequisites.

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


## Session Log
- `/ll:format-issue` - 2026-06-24T23:22:53 - `805d4898-1c18-40f2-ad99-fdac06f4d00e.jsonl`
