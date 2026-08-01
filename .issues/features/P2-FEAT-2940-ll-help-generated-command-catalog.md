---
id: FEAT-2940
title: 'll-help: generate the command/skill catalog from frontmatter, retire hardcoded
  help.md'
type: FEAT
priority: P2
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T10:45:27Z'
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- skills
- docs-drift
confidence_score: 96
outcome_confidence: 67
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 15
score_change_surface: 17
---

# FEAT-2940: ll-help — generate the command/skill catalog from frontmatter

## Summary

`commands/help.md` is 373 lines, ~330 of which are a hardcoded ASCII catalog of every command/skill that the LLM's only job is to echo (L14: "Output the following command reference:"). It drifts on every new command and requires zero reasoning. Replace it with a runtime generator CLI.

## Current Behavior

`/ll:help` loads a static catalog that must be hand-edited whenever a command, skill, or flag changes. There is no `ll-help` entry point; `skills/ll-help/SKILL.md` is a 12-line bridge stub.

## Expected Behavior

`ll-help [--json] [--area <name>] [--format md|json]` scans `commands/*.md` and `skills/*/SKILL.md` frontmatter (`description`, `argument-hint`/`args`), groups by area, and prints the catalog. `commands/help.md` shrinks to ~20 lines: run `ll-help`, render its output verbatim.

**Design decision**: runtime generation via a new entry point, not a release-time static file — static regeneration just moves the drift to publish time. Precedents: `ll-action list --output json` already enumerates skill frontmatter; `ll-generate-skill-descriptions` parses the same fields.

## Proposed Solution

- New module `scripts/little_loops/cli/help.py`; reuse frontmatter enumeration from `little_loops/frontmatter.py::parse_skill_frontmatter`.
- **Do not add a 9th plugin-root resolver.** `_find_plugin_root` is already duplicated across `skill_expander.py`, `cli/action.py:174`, `cli/adapt.py`, `cli/adapt_skills_for_codex.py`, `cli/adapt_agents_for_codex.py`, `cli/generate_skill_descriptions.py`, `init/cli.py`, and `hooks/user_prompt_submit.py`. Delegate to `skill_expander._find_plugin_root` the way `cli/action.py` and `cli/verify_cli_allowlist.py:34` already do.
- **Share one enumeration with `ll-action list`.** `cli/action.py::_load_skills` (L192+) already walks `skills/*/SKILL.md` and reads `description`/`args` frontmatter. Extract that into a shared collector both consume — otherwise this issue creates exactly the drift the epic exists to delete.
- **Pip-only installs have no catalog.** The wheel ships `little_loops/**` only (`scripts/pyproject.toml:154–155`); a project with `install_source: pypi` and no Claude Code plugin has no `skills/`/`commands/` directory. `ll-help` must detect this and exit with a clear "plugin not installed; catalog unavailable" message rather than tracebacking on a missing dir.
- Grouping by area can derive from the existing area taxonomy in `skills/configure/areas.md` or a simple frontmatter/prefix heuristic.
- **Triple registration required (BUG-2764 gate)**: `scripts/pyproject.toml` `[project.scripts]`, `skills/configure/areas.md` "All ll- commands" preset, `little_loops/init/writers.py::_LL_PERMISSIONS` (`Bash(ll-help:*)`). `ll-verify-cli-allowlist` must pass. This is the only new entry point in EPIC-2938.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_load_skills` (`cli/action.py:192`) is skills-only today** — it globs `skills/*/SKILL.md` and does not walk `commands/*.md` at all. The shared collector this issue asks for needs a second glob arm (or a merged `collect_entries()` that takes both dirs), not a straight extraction of the existing function.
- **`parse_skill_frontmatter` (`frontmatter.py:371`) returns a flat `dict[str, str]` and silently drops non-scalar values.** Skills use a flat `args:`/`argument-hint:` string, which this parser handles fine. But some `commands/*.md` files (e.g. `commands/normalize-issues.md:6-9`) use a structured `arguments:` YAML list instead — `parse_skill_frontmatter` drops that field entirely (non-string → discarded), so a naive reuse would silently lose per-arg descriptions for those commands. `collect_entries()` needs to handle both the flat-string and list `arguments:` shapes when building `argument_hint`.
- **No category/area frontmatter field exists anywhere.** Grepped `commands/*.md` and `skills/*/SKILL.md` for `category:`/`group:`/`section:` keys — zero hits. The category groupings shown in current `commands/help.md` (Issue Discovery, Planning & Implementation, etc., matching `.claude/CLAUDE.md`'s "Commands & Skills" section) exist only as hand-written prose; there is no structured source to derive them from. `render_catalog`'s `area` grouping will need either a new frontmatter convention (adds a maintenance burden the issue is trying to remove) or a hardcoded name→area lookup table seeded from the current `help.md` categories — the latter is simpler and matches the issue's "simple frontmatter/prefix heuristic" fallback already called out above.
- **51 `skills/*/SKILL.md` files are `disable-model-invocation: true` Codex-bridge stubs** (e.g. `skills/ll-help/SKILL.md` itself — "Bridged from `commands/help.md` for Codex Skills API discovery"). These duplicate the command they bridge from and should likely be excluded from the catalog to avoid double-listing every command/skill pair; not currently addressed by the Program Design.
- **`_find_plugin_root` (`skill_expander.py:25`) gives no pip-only signal** — it unconditionally returns a `Path` whether or not `skills/`/`commands/` exist under it. The established graceful-degrade pattern is `verify_cli_allowlist.py::_run` (lines 84-106): check `areas_md.is_file()` (or here, `(plugin_root / "skills").is_dir()`) and emit a `SKIP:`-prefixed message rather than crashing.
- **Structural template**: `cli/verify_triggers.py::main_verify_triggers` (line 647) is the closest existing CLI to model `main_help` after — `@dataclass` result types, dual `--json`/text output via separate `_format_text_report`/`_format_json_report` functions, `-C`/`--directory` override defaulting to `Path.cwd()`, `RawDescriptionHelpFormatter` with an epilog. It also demonstrates the standard `with cli_event_context(DEFAULT_DB_PATH, "ll-help", sys.argv[1:]):` wrapper used by every `main_*` CLI entry point (also in `verify_cli_allowlist.py:111`, `action.py:379`) — not currently mentioned in Program Design's Call Path.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — **missing from the issue and required for the entry point to work**: must add `from little_loops.cli.help import main_help` (pattern at line ~67, e.g. `from little_loops.cli.harness import main_harness`) and add `"main_help"` to `__all__`. The `pyproject.toml` entry point target is `little_loops.cli:main_help` (module `cli/__init__.py`, not `cli/help.py` directly) — without this import, `ll-help` raises `ImportError` at invocation. [Agent 2 finding]
- `scripts/tests/test_action.py::TestLoadSkills` (L124-196, 6 tests) — imports `_load_skills` directly from `little_loops.cli.action` and patches `_find_plugin_root`; asserts a flat `name`/`description`/`args` dict shape. If `_load_skills` is reimplemented as a filter over the new `collect_entries()`, it must stay a thin wrapper preserving this exact shape (not `HelpEntry`'s `argument_hint`/`kind`/`area` fields), or these tests and `ll-action list --output json`'s documented JSON contract break. [Agent 2/3 finding]
- `scripts/little_loops/tool_catalog.py::assemble_tool_catalog()` (`_skill_entries`/`_command_entries`, L95-126) — a **third**, functionally near-identical skills+commands(+agents) frontmatter enumeration, consumed by `ll-doctor`'s `_skills_commands_check()` (`cli/doctor.py:245-270`) and `cli/artifact.py`. Not in this issue's scope to consolidate, but after this lands there will be three parallel enumerations (`_load_skills`, `assemble_tool_catalog`, `collect_entries`) instead of the two the issue currently targets — flag as follow-on debt, don't silently let it happen unnoticed. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` (`DOC_STRINGS_PRESENT`, ~20 tuples, L20-155; `DOC_STRINGS_ABSENT`, L173) — asserts literal substrings (`"ll-doctor"`, `"/ll:review-epic"`, `"decisions"`, etc.) are present/absent inside `commands/help.md`'s raw text. These break once `help.md` shrinks to ~20 lines and stops containing the catalog verbatim — must be removed or retargeted at `ll-help`'s generated stdout instead of the static file. **Not covered by AC #99** (that AC only checks `ll-verify-docs`, a separate gate). [Agent 2 finding]
- `scripts/tests/test_wiring_skills_and_commands.py:202` — same pattern, `("commands/help.md", "spike", "FEAT-2567")`. Same breakage/retarget need. [Agent 2 finding]
- `scripts/tests/test_cli_learning_tests.py::TestDocWiring.test_help_md_lists_ll_learning_tests` (L609-616) — direct `HELP_MD.read_text()` + `assert "ll-learning-tests" in content`. Same breakage/retarget need. [Agent 2 finding]
- `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" (L416-430) — instructs contributors to hand-edit `help.md`'s "CLI TOOLS block" and add a presence test in `test_wiring_cli_registry.py`; this process guidance becomes stale/actively wrong once `help.md` is a generated wrapper and needs updating as part of this issue. [Agent 2 finding]
- `docs/reference/API.md`, `docs/ARCHITECTURE.md` — mention `parse_skill_frontmatter`/`_find_plugin_root`/skill-expansion infra; lower priority, verify no stale cross-references after the refactor. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_triggers.py::TestMainVerifyTriggers` — structural template for `main_help`'s dual `--json`/text CLI shape (`-C`/`--directory` override, `sys.argv` patch + `capsys` JSON/text assertions). [Agent 3 finding]
- `scripts/tests/test_verify_cli_allowlist.py::TestRun` — drift-check pattern template for the "catalog covers all entries" gate test this issue calls for (real-filesystem comparison, no mocks). [Agent 3 finding]
- No `test_help.py` exists yet (new file). Recommended shape: `TestHelpEntry`, `TestCollectEntries`, `TestRenderCatalog`, `TestMainHelp`, `TestCatalogDriftGate` (the last modeled on `test_verify_cli_allowlist.py`'s `TestRun`, comparing `collect_entries()`'s count against actual on-disk skill+command files). [Agent 3 finding]

### Scope Gap (flag for implementation time — not a Program Design change)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` contains a second, structurally distinct "CLI TOOLS (pip install little-loops)" block (~40 `ll-*` console-script entries, hand-written one-line descriptions) with **no** corresponding `commands/*.md` or `skills/*/SKILL.md` file for most entries — `collect_entries(plugin_root)` as specified (frontmatter-only) cannot regenerate this block. AC "`commands/help.md` ≤ ~30 lines and contains no hardcoded catalog rows" is unsatisfiable for this block without either a second data source (parsing `pyproject.toml [project.scripts]` or CLI docstrings) or dropping the block from `help.md` — resolve this scope question before/during implementation. [Agent 2 finding]

## Implementation Steps

1. Implement `ll-help` with md + json output and `--area` filtering.
2. Register the entry point in all three locations, **plus** `scripts/little_loops/cli/__init__.py` (`main_help` import + `__all__`) — required for the `pyproject.toml` entry point to resolve at all.
3. Rewrite `commands/help.md` to invoke `ll-help` (~20 lines). Resolve the "CLI TOOLS" pip-only block scope gap (see Integration Map) as part of this step.
4. Update or retarget the doc-wiring tests that assert literal `commands/help.md` substrings (`test_wiring_cli_registry.py`, `test_wiring_skills_and_commands.py:202`, `test_cli_learning_tests.py::TestDocWiring`) and the `CONTRIBUTING.md` process guidance they're based on.
5. Tests: catalog includes every `commands/*.md` and non-stub skill; `--json` schema stable; a drift test asserting the generated catalog covers all entries (replacing the hand-maintenance burden). Verify `_load_skills`'s refactor preserves `ll-action list --output json`'s existing `name`/`description`/`args` shape.

## Use Case

A user (or the `/ll:help` command itself) runs `ll-help` and gets an always-current catalog of every `/ll:` command and skill with descriptions and argument hints — no hand-maintained table to fall out of date when commands are added or renamed.

## Program Design

### Types

- `HelpEntry: dataclass` — `name: str`, `kind: Literal["command", "skill"]`, `description: str`, `argument_hint: str | None`, `area: str`

### Signatures

- `collect_entries(plugin_root: Path) -> list[HelpEntry]` — scan `commands/*.md` + `skills/*/SKILL.md` frontmatter via `frontmatter.parse_skill_frontmatter`; shared with `cli/action.py::_load_skills` rather than reimplemented
- `render_catalog(entries: list[HelpEntry], area: str | None, fmt: str) -> str`
- `main_help(argv: list[str] | None = None) -> int` — entry point in `scripts/little_loops/cli/help.py`

### Call Path

- `main_help()` -> `_find_plugin_root()` (existing, `skill_expander.py` — reused, not reimplemented)
- `main_help()` -> `collect_entries()` -> `parse_skill_frontmatter()` (existing, `little_loops/frontmatter.py`)
- `main_help()` -> `render_catalog()`
- `_load_skills()` (existing, `cli/action.py`) -> `collect_entries()` — the shared enumeration

## Impact

- **Priority**: P2 - Retires the repo's largest pure-drift hazard (hand-edited 330-line catalog)
- **Effort**: Small-Medium - New but simple CLI; triple registration overhead
- **Risk**: Low - Read-only generation; drift test replaces manual upkeep

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-help` lists every command and skill with description + argument hint, grouped by area
- [ ] `ll-help --json` emits machine-readable output
- [ ] `commands/help.md` ≤ ~30 lines and contains no hardcoded catalog rows
- [ ] `ll-verify-cli-allowlist` passes with the new entry point
- [ ] Confirm `ll-verify-docs` targets: retiring help.md's catalog must not trip or orphan any count-verified doc gate (no hard-coded coupling found in `cli/docs.py`, but verify at implementation time)
- [ ] `ll-help` on a pip-only install (no `skills/`/`commands/` on disk) exits with a clear message and a non-crashing status — test simulates the missing-plugin case
- [ ] `ll-help` adds no new `_find_plugin_root` copy; it calls `skill_expander._find_plugin_root`
- [ ] `ll-help` and `ll-action list --output json` derive their skill list from one shared collector (test asserts identical skill sets)
- [ ] pytest coverage in `scripts/tests/`
- [ ] `scripts/little_loops/cli/__init__.py` imports and exports `main_help` — `ll-help` is invocable, not just importable
- [ ] `test_wiring_cli_registry.py`, `test_wiring_skills_and_commands.py:202`, and `test_cli_learning_tests.py::TestDocWiring` no longer assert on hardcoded `commands/help.md` substrings that the generated catalog invalidates (removed or retargeted at `ll-help`'s output)


## Session Log
- `/ll:manage-issue` - 2026-08-01T10:45:16 - `b0c66672-d42f-49a3-93de-de0101a10b99.jsonl`
- `/ll:confidence-check` - 2026-08-01T10:32:00 - `070aac4f-19af-414b-90e4-e44c8a0af118.jsonl`
- `/ll:wire-issue` - 2026-08-01T10:31:00 - `94125df5-52a4-4130-b59d-a2ecb6075234.jsonl`
- `/ll:refine-issue` - 2026-08-01T10:25:20 - `e3816438-1a05-44fc-8704-4f91e9106094.jsonl`
