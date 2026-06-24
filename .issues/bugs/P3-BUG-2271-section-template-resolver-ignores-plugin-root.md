---
id: BUG-2271
type: BUG
priority: P3
status: open
captured_at: "2026-06-24T22:17:07Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [ENH-2272, BUG-2273, FEAT-2274]
---

# BUG-2271: Section-template resolver ignores CLAUDE_PLUGIN_ROOT and project-local templates

## Summary

`issue_template._default_templates_dir()` resolves the per-type section JSON
directory **only** relative to the installed Python package location
(`Path(__file__).resolve().parent.parent.parent / "templates"`). In a
non-editable install (`pip install little-loops`), this points at
`site-packages/templates`, which does not exist — even though the plugin's
`templates/` directory *does* exist at `${CLAUDE_PLUGIN_ROOT}/templates`. Unlike
`skill_expander._find_plugin_root()`, the resolver never consults the
`CLAUDE_PLUGIN_ROOT` env var, and it has no awareness of a project-local
template directory. Python code paths that load section definitions therefore
fail or fall back incorrectly when run from a non-editable install.

This bug is the resolver-side fix; the structural cross-host fix is **FEAT-2274**
(package `templates/` into the wheel). Under the **Both (wheel + deploy)**
decision (ARCHITECTURE-053), the resolver's primary tier becomes the in-package
`templates/` (always present via the wheel), and the `CLAUDE_PLUGIN_ROOT` /
`__file__` tiers this bug adds are fallbacks. This refines BUG-938 (closed
invalid): host-plugin assets stay out of the wheel, but package-data templates
the CLIs import go into it.

## Steps to Reproduce

1. `pip install little-loops` (non-editable) into a fresh venv, and install the
   `ll@little-loops` Claude Code plugin.
2. From a plain shell (no `CLAUDE_PLUGIN_ROOT` exported), in a project that has
   issues synced from GitHub, run `ll-sync pull` (or `ll-issues refine-status`).
3. Observe: `load_issue_sections()` resolves `base = site-packages/little_loops/../../templates`,
   which does not exist → `FileNotFoundError` (sync pull) or a degraded
   `is_formatted()` result (refine-status), depending on the caller's error handling.

## Root Cause

- **File**: `scripts/little_loops/issue_template.py`
- **Anchor**: `_default_templates_dir()` (line 15)

```python
def _default_templates_dir() -> Path:
    """Return the bundled templates/ directory relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "templates"
```

In an editable install, `__file__` is `scripts/little_loops/issue_template.py`,
so three parents up + `/templates` lands on the repo-root `templates/` (exists).
In a non-editable install, `__file__` is
`site-packages/little_loops/issue_template.py`, so the same traversal lands on
`site-packages/templates` (does not exist).

The sibling resolver `skill_expander._find_plugin_root()` already solves this
correctly by checking `CLAUDE_PLUGIN_ROOT` first, then falling back to
`__file__`-relative. `_default_templates_dir()` predates / does not reuse that
convention.

## Current Behavior

- `load_issue_sections()` (`issue_template.py:33`) — used by:
  - `sync.py:700` (`ll-sync pull` building local issue files) → `FileNotFoundError`
  - `issue_parser.is_formatted()` (`issue_parser.py:80`) → used by `ll-issues show`,
    `refine-status`, `next-action`; a missing templates dir degrades the
    formatted/unformatted signal across the CLI.
- All of the above work in editable dev installs, masking the bug from
  maintainers.

## Expected Behavior

`_default_templates_dir()` (or a replacement resolver) locates the section
templates regardless of install mode, using a deterministic precedence that
mirrors the established `skill_expander` convention:

1. `CLAUDE_PLUGIN_ROOT` env var, if set → `${CLAUDE_PLUGIN_ROOT}/templates`
2. `__file__`-relative fallback (editable dev installs)

(ENH-2272 extends this precedence with an explicit config override and a
project-local `.ll/templates/` directory, which is the fully robust fix when no
env var is present. This bug covers only restoring correctness for the existing
Python loaders.)

## Proposed Solution

Make `_default_templates_dir()` honor `CLAUDE_PLUGIN_ROOT` before the
`__file__`-relative fallback, reusing the same logic as
`skill_expander._find_plugin_root()` (factor the shared lookup into one helper
rather than duplicating it). No behavior change for editable installs; fixes
non-editable installs that have `CLAUDE_PLUGIN_ROOT` available.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_template.py` — `_default_templates_dir()` consults
  `CLAUDE_PLUGIN_ROOT` before the `__file__` fallback.
- `scripts/little_loops/skill_expander.py` — source of the existing
  `_find_plugin_root()` pattern; candidate home for a shared helper.

### Similar Patterns
- `skill_expander._find_plugin_root()` (`skill_expander.py:22`) — the correct
  env-var-first resolution to mirror.
- `cli/loop/_helpers.py:get_builtin_loops_dir()` — BUG-885 hit the same
  `__file__`-traversal-breaks-in-wheel class of bug for `loops/`.

### Packaging (see FEAT-2274)
- The robust cross-host fix is **FEAT-2274**: package `templates/` into the wheel
  so the resolver's in-package tier (`Path(__file__).parent / "templates"`)
  always resolves, with no `CLAUDE_PLUGIN_ROOT` dependency. Once FEAT-2274 lands,
  this bug's env-var-first change is a fallback tier, not the primary fix. The
  earlier "do not bundle (BUG-938 stance)" note is superseded for package-data
  templates by the **Both (wheel + deploy)** decision (ARCHITECTURE-053).

## Implementation Steps

1. Extract a shared `find_plugin_root()` helper (env-var-first, `__file__`
   fallback) or have `_default_templates_dir()` call the existing one.
2. Add a unit test that monkeypatches `CLAUDE_PLUGIN_ROOT` to a temp dir
   containing `templates/bug-sections.json` and asserts `load_issue_sections`
   resolves it.
3. Add a test asserting the `__file__` fallback still works when the env var is
   unset (editable-install path).
4. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — Silent/degraded behavior for non-editable installs in the
  specific `ll-sync pull` / `refine-status` paths; editable dev installs and the
  common skill-driven flow (where `${CLAUDE_PLUGIN_ROOT}` is set) are unaffected.
- **Effort**: Small — mirror an existing resolver; add two tests.
- **Risk**: Low — additive precedence; fallback path unchanged.
- **Breaking Change**: No.

## Related

- ENH-2272 — adds the `ll-issues sections` accessor, full resolver precedence
  (config → `.ll/templates/` → `CLAUDE_PLUGIN_ROOT` → `__file__`), `ll-init`
  template deploy, and the 6 skill/command callsite rewrites that this bug's
  resolver underpins.
- FEAT-2274 — packages `templates/` into the wheel (the **Both** decision); the
  in-package tier this bug's resolver should prefer once it lands.
- BUG-938 — Plugin assets missing from pip wheel (closed **invalid**); FEAT-2274
  refines its rule (host-plugin assets out, package-data templates in).
- BUG-885 — Built-in loops missing after pip install; same `__file__`-traversal
  failure class.

## Labels

`bug`, `templates`, `install`, `path-resolution`

## Session Log
- `/ll:capture-issue` - 2026-06-24T22:17:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d34d610-c8b9-4a5e-82c8-191296760b6d.jsonl`
