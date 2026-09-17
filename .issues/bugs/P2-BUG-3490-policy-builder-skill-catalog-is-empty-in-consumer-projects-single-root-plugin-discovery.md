---
id: BUG-3490
parent: EPIC-3493
epic: EPIC-3493
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
- `_find_plugin_root()` (`scripts/little_loops/skill_expander.py:25-35`, wrapped by `cli/action.py:179-182`) checks `CLAUDE_PLUGIN_ROOT`, else returns three parents up from `skill_expander.py`. `CLAUDE_PLUGIN_ROOT` is set only inside a Claude Code session, not when a user runs `ll-artifact policy-builder` from a shell. For a `pypi` install the fallback resolves to `lib/python3.x/`, which has no skills. The wheel does ship skills at `little_loops/skills/` (`scripts/hatch_build.py`, BUG-3177). Exactly one collector reads that packaged copy: `mcp_server/server.py:60-77` builds a candidate list (`LL_SKILLS_DIR` override, `CLAUDE_PLUGIN_ROOT/skills`, `importlib.resources.files("little_loops")/"skills"`, `_find_plugin_root()/skills`) and takes the first that exists. That is the precedent to generalize; BUG-3177 fixed only this MCP call site and left `_find_plugin_root()` itself unchanged.
- Consumer projects keep their own skills under `.claude/skills/` and `.claude/commands/`. No ll collector reads them, and they are the user's skills, not ll overrides (this checkout has `.claude/skills/{excalidraw-diagram,scrape-docs}` and `.claude/commands/{analyze_log,publish}.md`).
- Every existing collector (`cli/help.py::collect_entries`, `cli/action.py::_load_skills`, `tool_catalog.py::assemble_tool_catalog`, `_load_skill_catalog`) resolves exactly one root; none merges roots, applies precedence, or deduplicates by name.

## Expected Behavior

Consumer projects resolve the installed plugin catalog regardless of `install_source`, with deterministic deduplication and precedence. The fix lives in the shared resolver so `ll-help` and `ll-action list` benefit too. The policy builder additionally lists the project's own `.claude/skills` and `.claude/commands` entries (explicit opt-in), with project entries winning on name collision.

## Motivation

A builder whose skill menu is empty for every consumer project is unusable outside this checkout. All consuming projects on this machine are `local-editable`, which masks the defect for `pypi` and marketplace installs.

## Proposed Solution

Extend the shared plugin-root resolution to an ordered candidate list, generalizing the `mcp_server/server.py:60-77` pattern. **Do not branch on `install_source`**: existence checks already discriminate every layout, `_find_plugin_root()` takes no project argument and is called from contexts with no project (`ll-mcp`, `harness.py`), and config branching adds a stale-config failure mode (config says `pypi` after the user switched to editable). Candidates, highest precedence first; the first that contains `skills/` is the plugin root:

1. `CLAUDE_PLUGIN_ROOT` when set (inside a Claude Code session).
2. The checkout root (current three-parents-up path) when `<root>/skills` exists. This keeps the source checkout single-root and byte-identical.
3. The packaged copy: `importlib.resources.files("little_loops")` (which contains `skills/` and, after this fix, `commands/`).
4. The marketplace plugin path, read from `install_path` persisted in `.ll/ll-config.json` (new field, written by `ll-init` from `detect_installation()`, which already returns it but discards it today). Fall back to `install_check._probe_plugin()` only when the field is absent; **never spawn that subprocess on every call** (10s timeout, 13 `_find_plugin_root` callers). Memoize the resolved list with `functools.lru_cache`.

Project-local skills (`<project_root>/.claude/skills/*/SKILL.md`, `.claude/commands/*.md`) are **not** part of the shared resolver. They are the user's own skills, and merging them would change `ll-help` (which prefixes `/ll:`), `ll-action list`, and `TestCatalogDriftGate` output on this checkout. They are included only by the policy builder, via an explicit `include_project_skills=True` argument on the multi-root collector, because routing prompts to user skills is legitimately useful there. Project entries win on name collision.

`collect_entries` gains a multi-root form that merges by `(kind, name)` with higher-precedence roots winning; `_load_skill_catalog` becomes a thin projection over it, matching how `_load_skills` already projects `collect_entries`. Keep the never-raises contract: a missing root contributes nothing.

## Implementation Steps

1. Add consumer-root fixtures: a temp project with no root `skills/` and (a) `CLAUDE_PLUGIN_ROOT` pointing at a plugin tree, (b) a packaged-layout tree (monkeypatch `importlib.resources.files`), (c) a config-cached `install_path` marketplace tree, (d) a `.claude/skills` entry that shadows a plugin skill by name. Assert known lifecycle skills appear, the shadow wins only when `include_project_skills=True`, no duplicate names, and no subprocess is spawned when `install_path` is cached (patch `_probe_plugin` to fail the test if called).
2. Persist `install_path` in `.ll/ll-config.json` from `ll-init` (schema + `init/core.py` writer), for `global-claude-code` / `project-claude-code` installs.
3. Implement `resolve_catalog_roots()` and `collect_entries_multi()`; repoint `_find_plugin_root()`'s no-env fallback at the first resolved plugin root.
4. Add `commands/` to the wheel via the existing `SkillsForceIncludeHook` (registered for both wheel and sdist targets, `pyproject.toml:218,220`); update the `package_data.py:94-102` comment.
5. Repoint `_load_skill_catalog` (with `include_project_skills=True`); confirm `_load_skills` / `main_help` / `assemble_tool_catalog` inherit the fix through `_find_plugin_root`.
6. Update `docs/reference/CONFIGURATION.md` § `artifacts` (plus the new `install_path` field) and `docs/reference/API.md` § `assemble_tool_catalog` (the "single-root, never-raises" citation for `_load_skill_catalog` becomes stale).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/hatch_build.py` — add a force-include hook (or extend `SkillsForceIncludeHook`) for `commands/` → `little_loops/commands`; confirmed absent from the wheel today, not merely unverified
- Update `scripts/pyproject.toml` (packages/include config, lines 202-203) — add the packaged `commands/` path alongside `skills/`
- Update `scripts/tests/test_policy_builder_emit.py` and `scripts/tests/test_enh3035_artifact_template_kit.py` — extend or confirm coverage for multi-root catalog resolution
- Point `resolve_catalog_roots()`'s marketplace-root step at `init/install_check.py:_probe_plugin()`'s `installPath` (host-supplied via `<binary> plugin list --json`), not a hardcoded `~/.claude/plugins/...` literal

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/install_check.py:_probe_plugin()` (lines 97-132) — reads `installPath` from `<binary> plugin list --json` output (line 125); confirms the marketplace/plugin root is host-supplied at runtime, not a hardcoded path under `~/.claude/plugins/`. `resolve_catalog_roots()`'s marketplace step should call into this rather than constructing a literal path — the Proposed Solution's "confirm the exact path" ask resolves to "there is no fixed path; it comes from the host CLI"

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/skill_expander.py` — `_find_plugin_root()` (line 25) currently checks only `CLAUDE_PLUGIN_ROOT` then falls back to three-parents-up; this is where `resolve_catalog_roots()` is proposed to live
- `scripts/little_loops/cli/help.py` — `collect_entries()` (line 212, single-root) is where `collect_entries_multi()` is proposed to be added
- `scripts/little_loops/cli/artifact/policy_builder.py` — `_load_skill_catalog()` (line 21) globs `project_root/"skills"` and `project_root/"commands"` only, with no call into `skill_expander` at all today
- `scripts/little_loops/cli/action.py` — `_load_skills()` (line 197) and its own `_find_plugin_root` wrapper (lines 179-182) already project `collect_entries`, the shape `_load_skill_catalog` is proposed to match

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/hatch_build.py` — confirmed gap: `SkillsForceIncludeHook` (lines 31-36) force-includes only `skills/` into the wheel as `little_loops/skills`; `commands/` is not packaged for pip installs today and must be added, not merely "verified" [Agent 1 finding]
- `scripts/pyproject.toml` (lines 202-203) — `packages = ["little_loops"]` / `include = ["little_loops/**", ...]` has no `commands/` entry; needs updating alongside `hatch_build.py` [Agent 1 finding]

**Conventions in Force**
- Every existing collector this issue lists follows a "resolve exactly one root, never raise on a missing one" contract (stated explicitly in `tool_catalog.py:156`); `resolve_catalog_roots`/`collect_entries_multi` are proposed to preserve the never-raises half while dropping the single-root half
- `_load_skills` already exists as a projection over `collect_entries` (`cli/action.py:197`) — the same shape this issue proposes for `_load_skill_catalog` over `collect_entries_multi`

**Tests**
- `scripts/tests/test_skill_expander.py` — `TestFindPluginRoot` (`test_uses_env_var_when_set` line 43, `test_falls_back_to_package_parent` line 47) asserts the exact three-parents-up path; it stays true unchanged because the checkout root is candidate 2 and always has `skills/` on this repo
- `scripts/tests/test_action.py::TestLoadSkills` — this issue's Acceptance Criteria names this suite's byte-for-byte contract as one that must be preserved
- `scripts/tests/test_help.py` — `TestCollectEntries` (several cases) and `TestCatalogDriftGate::test_collect_entries_covers_real_plugin_root`
- `scripts/tests/test_tool_catalog.py` — exercises `assemble_tool_catalog` end-to-end (lines 67-176)
- `scripts/tests/test_enh_3444_mcp_skills_list.py` — exercises both `tool_catalog.assemble_tool_catalog` and `skill_expander._find_plugin_root()` together
- `scripts/tests/test_cli_doctor_install_checks.py` — patches `assemble_tool_catalog` at its `cli/doctor.py` call site
- `scripts/tests/test_init_core.py` — covers `install_source` values including the `project-claude-code` / `.claude/plugins/ll` path this issue's Proposed Solution names as needing confirmation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_policy_builder_emit.py:43,50,83,231-235` — calls `cmd_policy_builder` / `main_artifact` CLI dispatch directly, exercising `_load_skill_catalog`; must keep passing under multi-root resolution [Agent 3 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py:62-65` — calls `cmd_policy_builder` against the golden template-kit fixture; existing coverage to preserve [Agent 3 finding]

**Documentation**
- `docs/reference/API.md` (line 11078) — the `assemble_tool_catalog` section explicitly cites `_load_skills()`/`_load_skill_catalog()` as the "single-root, never-raises" precedent; this is the citation this issue's Implementation Steps says becomes stale
- `docs/reference/CONFIGURATION.md` § `artifacts` (lines 948-987) — covers `default_output_dir`/`templates_dir`, the config surface `cmd_policy_builder` already reads
- `docs/reference/CLI.md` (lines 5061-5092) — documents the `ll-artifact policy-builder` subcommand this bug affects
- `.claude/CLAUDE.md` — Distribution section is the canonical description of the four `install_source` values this issue's resolution order branches on

**Configuration**
- `.ll/ll-config.json` / `scripts/little_loops/config-schema.json` — where `install_source` is recorded and schema-validated per project
- `scripts/hatch_build.py` (`SkillsForceIncludeHook`) — force-includes `skills/` into the wheel as `little_loops/skills`; this is the packaged-layout root this issue's Proposed Solution step 3 targets, and the precedent from the already-completed BUG-3177 (which packaged `skills/` and fixed only `mcp_server/server.py`'s candidate list; `_find_plugin_root` itself was left unchanged)
- `scripts/little_loops/package_data.py` (lines 94-102) — comment documents that `skills/` is force-included rather than a `PACKAGE_DATA_ASSETS` entry; this issue's Proposed Solution step 3 also asks whether `commands/` is packaged the same way, which this file does not currently document

## Program Design

### Types

`CatalogRoot` (dataclass): `path: Path`, `source: str` (`env`, `checkout`, `packaged`, `marketplace`, `project`), `precedence: int`. Higher precedence wins on name collision. `project` roots are produced only when `include_project_skills=True`.

### Signatures

- `resolve_catalog_roots(project_root: Path | None = None, *, include_project_skills: bool = False) -> list[CatalogRoot]` in `scripts/little_loops/skill_expander.py` — ordered by existence-checked candidates (env, checkout, packaged, cached marketplace path), plus the project `.claude/` root only when opted in; missing roots omitted, never raises, memoized, no subprocess when `install_path` is cached.
- `collect_entries(plugin_root: Path) -> list[HelpEntry]` in `scripts/little_loops/cli/help.py` — kept; add `collect_entries_multi(roots: list[CatalogRoot]) -> list[HelpEntry]` that merges by `(kind, name)` with highest precedence winning, sorted deterministically.
- `_load_skill_catalog(project_root: Path) -> list[dict[str, str]]` in `scripts/little_loops/cli/artifact/policy_builder.py` — same signature and shape; becomes a projection over `collect_entries_multi(resolve_catalog_roots(project_root, include_project_skills=True))`.
- `_find_plugin_root() -> Path` — retained for single-root callers; its no-env fallback returns the highest-precedence resolved *plugin* root (never a `project` root, since `cli/adapt.py`, `generate_skill_descriptions.py`, and the `adapt_*_for_codex` CLIs write into it) rather than the raw three-parents-up path; when nothing resolves, keep returning three-parents-up so behavior is unchanged.

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` -> `resolve_catalog_roots` -> `collect_entries_multi` -> `collect_entries` per root.

`_load_skills` (`scripts/little_loops/cli/action.py`) and `main_help` (`scripts/little_loops/cli/help.py`) -> `_find_plugin_root` -> `resolve_catalog_roots` (inherit the fix).

## Acceptance Criteria

- [ ] Consumer-root fixtures with installed plugin content produce known lifecycle skills without root `skills/` or `commands/` directories, for `CLAUDE_PLUGIN_ROOT`, packaged, and marketplace layouts.
- [ ] On a packaged layout with no `CLAUDE_PLUGIN_ROOT`, `ll-help` and `ll-action list` are non-empty; `ll-help -C` still overrides.
- [ ] With `include_project_skills=True`, `.claude/skills` / `.claude/commands` entries take precedence over plugin entries of the same name; results are deduplicated and deterministically ordered. Without it, project entries are absent, so `ll-help` / `ll-action list` / `TestCatalogDriftGate` output on the source checkout is byte-identical.
- [ ] Resolution spawns no subprocess when `install_path` is present in config; `ll-init` writes `install_path` for marketplace installs.
- [ ] `commands/` ships in the wheel (`little_loops/commands`), from both full-checkout and unpacked-sdist builds.
- [ ] Missing roots never raise; existing `test_action.py::TestLoadSkills` byte-for-byte contract and `test_skill_expander.py::TestFindPluginRoot` are preserved.
- [ ] Docs updated; full local suite passes.

## Scope Boundaries

Includes catalog root resolution, merge, precedence, and dedup, plus packaging `commands/`. Excludes browser/core builder defects (BUG-3486), runtime fragment defects (BUG-3489), and packaging `agents/` (also unpackaged; `assemble_tool_catalog` and therefore `ll-doctor` / `ll-mcp` will still miss agents on pypi installs, which is not a regression of this fix).

## Steps to Reproduce

Call `_load_skill_catalog` with a temporary consumer root lacking root-level `skills/` and `commands/`; observe an empty catalog. Run `ll-help` from a `pypi`-installed consumer without `CLAUDE_PLUGIN_ROOT`; observe "No commands or skills found."

## Root Cause

`_load_skill_catalog` does not resolve the installed plugin root, and `_find_plugin_root()`'s no-env fallback assumes the source-checkout layout, which is wrong for site-packages installs.

## Status

**Open** | Created: 2026-09-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-17T03:10:39 - `62feba6c-702f-4140-917b-5a2b05ea6c40.jsonl`
- `/ll:wire-issue` - 2026-09-17T01:06:16 - `9edbdbb5-9660-42b5-a715-69e61709aaa6.jsonl`
- `/ll:refine-issue` - 2026-09-16T22:24:05 - `c7278f1b-df03-4464-a3c5-e94aa066b201.jsonl`
