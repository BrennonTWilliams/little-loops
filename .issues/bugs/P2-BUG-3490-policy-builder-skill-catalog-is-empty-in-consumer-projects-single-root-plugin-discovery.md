---
id: BUG-3490
type: BUG
title: Policy builder skill catalog is empty in consumer projects (single-root plugin
  discovery)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:14:21Z'
labels:
- policy-builder
relates_to:
- BUG-3486
- BUG-3489
- FEAT-3474
---

# BUG-3490: Policy builder skill catalog is empty in consumer projects (single-root plugin discovery)

## Summary

`_load_skill_catalog()` in `scripts/little_loops/cli/artifact/policy_builder.py` globs only `<project_root>/skills` and `<project_root>/commands`, a source-repo layout. Ordinary consuming projects get an empty skill menu in the policy builder despite an installed little-loops plugin. The same single-root assumption in the shared `_find_plugin_root()` resolver also breaks `ll-help` and `ll-action list` for `pypi` installs.

Split from BUG-3486 (2026-09-16 whole-builder review, defect h).

## Current Behavior

- `_load_skill_catalog(project_root)` (`policy_builder.py:21-53`) reads `project_root/"skills"` and `project_root/"commands"` only and never consults the installed plugin. Its only caller is `cmd_policy_builder()`.
- `_find_plugin_root()` (`scripts/little_loops/skill_expander.py:25-35`, wrapped by `cli/action.py:179-182`) checks `CLAUDE_PLUGIN_ROOT`, else returns three parents up from `skill_expander.py`. `CLAUDE_PLUGIN_ROOT` is set only inside a Claude Code session, not when a user runs `ll-artifact policy-builder` from a shell. For a `pypi` install the fallback resolves to `lib/python3.x/`, which has no skills. The wheel does ship skills at `little_loops/skills/` (`scripts/hatch_build.py`, BUG-3177), but no Python collector reads that packaged copy.
- Consumer projects keep project-local overrides under `.claude/skills/` and `.claude/commands/`, which no collector reads.
- Every existing collector (`cli/help.py::collect_entries`, `cli/action.py::_load_skills`, `tool_catalog.py::assemble_tool_catalog`, `_load_skill_catalog`) resolves exactly one root; none merges roots, applies precedence, or deduplicates by name.

## Expected Behavior

Consumer projects resolve the installed plugin catalog plus project-local overrides regardless of `install_source`, with deterministic deduplication and project-override precedence. The fix lives in the shared resolver so `ll-help` and `ll-action list` benefit too.

## Motivation

A builder whose skill menu is empty for every consumer project is unusable outside this checkout. All consuming projects on this machine are `local-editable`, which masks the defect for `pypi` and marketplace installs.

## Proposed Solution

Extend the shared plugin-root resolution to an ordered list of catalog roots, resolved by `install_source` (`.ll/ll-config.json`) and environment:

1. `CLAUDE_PLUGIN_ROOT` when set (inside a Claude Code session).
2. `local-editable`: the checkout root (current three-parents-up fallback, valid only when `<root>/skills` exists).
3. `pypi`: the packaged `little_loops/skills` and `little_loops/commands` copies inside the installed package (new step; verify `commands/` is also packaged, add it to `hatch_build.py` if not).
4. `global-claude-code` / `project-claude-code`: the marketplace plugin cache under `~/.claude/plugins/` (confirm the exact path used by `init/install_check.py`).
5. Project overrides: `<project_root>/.claude/skills/*/SKILL.md` and `<project_root>/.claude/commands/*.md`, highest precedence.

`collect_entries` gains a multi-root form that merges by entry name with later roots (project overrides) winning; `_load_skill_catalog` becomes a thin projection over it, matching how `_load_skills` already projects `collect_entries`. Keep the never-raises contract: a missing root contributes nothing.

## Implementation Steps

1. Add consumer-root fixtures: a temp project with no root `skills/` and (a) `CLAUDE_PLUGIN_ROOT` pointing at a plugin tree, (b) a packaged-layout tree, (c) a `.claude/skills` override that shadows a plugin skill by name. Assert known lifecycle skills appear, overrides win, and no duplicate names.
2. Implement multi-root resolution and merge in the shared resolver/collector.
3. Repoint `_load_skill_catalog` (and confirm `_load_skills` / `assemble_tool_catalog` inherit the fix or document why not).
4. Update `docs/reference/CONFIGURATION.md` § `artifacts` and `docs/reference/API.md` § `assemble_tool_catalog` (the "single-root, never-raises" citation for `_load_skill_catalog` becomes stale).

## Impact

- **Priority**: P2 - the builder's skill menu is empty for every non-checkout consumer; same root cause affects `ll-help`/`ll-action list` on pypi installs
- **Effort**: Medium - multi-root resolution, merge/precedence, and fixtures for four install layouts
- **Risk**: Medium - touches the shared resolver used by several collectors; preserve single-root behavior for the source checkout
- **Breaking Change**: No

## Program Design

### Types

`CatalogRoot` (dataclass): `path: Path`, `source: str` (`env`, `checkout`, `packaged`, `marketplace`, `project`), `precedence: int`. Later/higher precedence wins on name collision.

### Signatures

- `resolve_catalog_roots(project_root: Path | None = None) -> list[CatalogRoot]` in `scripts/little_loops/skill_expander.py` — ordered roots per `install_source` and environment; missing roots omitted, never raises.
- `collect_entries(plugin_root: Path) -> list[HelpEntry]` in `scripts/little_loops/cli/help.py` — kept; add `collect_entries_multi(roots: list[CatalogRoot]) -> list[HelpEntry]` that merges by `(kind, name)` with highest precedence winning, sorted deterministically.
- `_load_skill_catalog(project_root: Path) -> list[dict[str, str]]` in `scripts/little_loops/cli/artifact/policy_builder.py` — same signature and shape; becomes a projection over `collect_entries_multi(resolve_catalog_roots(project_root))`.
- `_find_plugin_root() -> Path` — retained for single-root callers; its no-env fallback should return the first resolved root rather than the raw three-parents-up path.

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` -> `resolve_catalog_roots` -> `collect_entries_multi` -> `collect_entries` per root.

`_load_skills` (`scripts/little_loops/cli/action.py`) and `main_help` (`scripts/little_loops/cli/help.py`) -> `_find_plugin_root` -> `resolve_catalog_roots` (inherit the fix).

## Acceptance Criteria

- [ ] Consumer-root fixtures with installed plugin content produce known lifecycle skills without root `skills/` or `commands/` directories, for `CLAUDE_PLUGIN_ROOT`, packaged, and marketplace layouts.
- [ ] `.claude/skills` / `.claude/commands` overrides take precedence over plugin entries of the same name; results are deduplicated and deterministically ordered.
- [ ] Missing roots never raise; existing `test_action.py::TestLoadSkills` byte-for-byte contract is preserved.
- [ ] Docs updated; full local suite passes.

## Scope Boundaries

Includes catalog root resolution, merge, precedence, and dedup. Excludes browser/core builder defects (BUG-3486) and runtime fragment defects (BUG-3489).

## Steps to Reproduce

Call `_load_skill_catalog` with a temporary consumer root lacking root-level `skills/` and `commands/`; observe an empty catalog. Run `ll-help` from a `pypi`-installed consumer without `CLAUDE_PLUGIN_ROOT`; observe "No commands or skills found."

## Root Cause

`_load_skill_catalog` does not resolve the installed plugin root, and `_find_plugin_root()`'s no-env fallback assumes the source-checkout layout, which is wrong for site-packages installs.

## Status

**Open** | Created: 2026-09-16 | Priority: P2
