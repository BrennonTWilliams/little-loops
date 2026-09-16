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

## Integration Map

### Dependent Files (Callers/Importers)
- Callers of `_find_plugin_root`: `cli/adapt.py:92`, `cli/generate_skill_descriptions.py:189`, `cli/help.py:277` (`main_help`), `cli/queue.py:197`, `cli/harness.py:177`, `cli/action.py:208`, `cli/verify_host_map.py:69`, `cli/verify_cli_allowlist.py:45`, `cli/adapt_agents_for_codex.py:108`, `cli/adapt_skills_for_codex.py:98`, `mcp_server/server.py:71`, `mcp_server/tools.py:583`, and `skill_expander.py:145` itself (`expand_skill`) — all of these inherit whatever `_find_plugin_root`'s no-env fallback resolves to
- Callers of `collect_entries`: `cli/help.py:291` (`main_help`), `cli/action.py:209` (`_load_skills`)
- `scripts/little_loops/tool_catalog.py:assemble_tool_catalog` (line 152) — its docstring (line 156) explicitly cites the `_load_skills()`/`_load_skill_catalog()` "never raises" precedent this issue says is going stale; called from `cli/doctor.py:260-264` and `mcp_server/tools.py:581,587`
- `scripts/little_loops/init/install_check.py:detect_installation()` (lines 60-96) is the sole producer of the `install_source` values (`local-editable`, `pypi`, `global-claude-code`, `project-claude-code`) that `resolve_catalog_roots()` is proposed to branch on

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/skill_expander.py` — `_find_plugin_root()` (line 25) currently checks only `CLAUDE_PLUGIN_ROOT` then falls back to three-parents-up; this is where `resolve_catalog_roots()` is proposed to live
- `scripts/little_loops/cli/help.py` — `collect_entries()` (line 212, single-root) is where `collect_entries_multi()` is proposed to be added
- `scripts/little_loops/cli/artifact/policy_builder.py` — `_load_skill_catalog()` (line 21) globs `project_root/"skills"` and `project_root/"commands"` only, with no call into `skill_expander` at all today
- `scripts/little_loops/cli/action.py` — `_load_skills()` (line 197) and its own `_find_plugin_root` wrapper (lines 179-182) already project `collect_entries`, the shape `_load_skill_catalog` is proposed to match

**Conventions in Force**
- Every existing collector this issue lists follows a "resolve exactly one root, never raise on a missing one" contract (stated explicitly in `tool_catalog.py:156`); `resolve_catalog_roots`/`collect_entries_multi` are proposed to preserve the never-raises half while dropping the single-root half
- `_load_skills` already exists as a projection over `collect_entries` (`cli/action.py:197`) — the same shape this issue proposes for `_load_skill_catalog` over `collect_entries_multi`

**Tests**
- `scripts/tests/test_skill_expander.py` — `TestFindPluginRoot` (`test_uses_env_var_when_set` line 43, `test_falls_back_to_package_parent` line 47) is the existing single-root contract that must keep passing alongside any new multi-root behavior
- `scripts/tests/test_action.py::TestLoadSkills` — this issue's Acceptance Criteria names this suite's byte-for-byte contract as one that must be preserved
- `scripts/tests/test_help.py` — `TestCollectEntries` (several cases) and `TestCatalogDriftGate::test_collect_entries_covers_real_plugin_root`
- `scripts/tests/test_tool_catalog.py` — exercises `assemble_tool_catalog` end-to-end (lines 67-176)
- `scripts/tests/test_enh_3444_mcp_skills_list.py` — exercises both `tool_catalog.assemble_tool_catalog` and `skill_expander._find_plugin_root()` together
- `scripts/tests/test_cli_doctor_install_checks.py` — patches `assemble_tool_catalog` at its `cli/doctor.py` call site
- `scripts/tests/test_init_core.py` — covers `install_source` values including the `project-claude-code` / `.claude/plugins/ll` path this issue's Proposed Solution names as needing confirmation

**Documentation**
- `docs/reference/API.md` (line 11078) — the `assemble_tool_catalog` section explicitly cites `_load_skills()`/`_load_skill_catalog()` as the "single-root, never-raises" precedent; this is the citation this issue's Implementation Steps says becomes stale
- `docs/reference/CONFIGURATION.md` § `artifacts` (lines 948-987) — covers `default_output_dir`/`templates_dir`, the config surface `cmd_policy_builder` already reads
- `docs/reference/CLI.md` (lines 5061-5092) — documents the `ll-artifact policy-builder` subcommand this bug affects
- `.claude/CLAUDE.md` — Distribution section is the canonical description of the four `install_source` values this issue's resolution order branches on

**Configuration**
- `.ll/ll-config.json` / `scripts/little_loops/config-schema.json` — where `install_source` is recorded and schema-validated per project
- `scripts/hatch_build.py` (`SkillsForceIncludeHook`) — force-includes `skills/` into the wheel as `little_loops/skills`; this is the packaged-layout root this issue's Proposed Solution step 3 targets, and the resolved precedent from the related, already-completed BUG-3177 (`_find_plugin_root` site-packages fallback)
- `scripts/little_loops/package_data.py` (lines 94-102) — comment documents that `skills/` is force-included rather than a `PACKAGE_DATA_ASSETS` entry; this issue's Proposed Solution step 3 also asks whether `commands/` is packaged the same way, which this file does not currently document

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


## Session Log
- `/ll:refine-issue` - 2026-09-16T22:24:05 - `c7278f1b-df03-4464-a3c5-e94aa066b201.jsonl`
