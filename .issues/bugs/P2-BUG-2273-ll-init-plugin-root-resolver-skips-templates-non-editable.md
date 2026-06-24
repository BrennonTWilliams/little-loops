---
id: BUG-2273
type: BUG
priority: P2
status: open
captured_at: "2026-06-24T22:25:58Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [BUG-2271, ENH-2272, FEAT-2274, BUG-885, BUG-938]
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
- `scripts/little_loops/init/detect.py` — `detect_project_type()` (line 115):
  optional warning when template source is unresolved.

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

## Session Log
- `/ll:capture-issue` - 2026-06-24T22:25:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4149029-8124-4b7f-a1de-e3e84bc0d161.jsonl`
