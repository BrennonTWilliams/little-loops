---
id: FEAT-2940
title: "ll-help: generate the command/skill catalog from frontmatter, retire hardcoded help.md"
type: FEAT
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- skills
- docs-drift
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

- New module `scripts/little_loops/cli/help.py`; reuse frontmatter enumeration from `little_loops/frontmatter.py::parse_skill_frontmatter` and the skill-dir resolver used by `ll-verify-skills` (wheel-vs-repo path handling).
- Grouping by area can derive from the existing area taxonomy in `skills/configure/areas.md` or a simple frontmatter/prefix heuristic.
- **Triple registration required (BUG-2764 gate)**: `scripts/pyproject.toml` `[project.scripts]`, `skills/configure/areas.md` "All ll- commands" preset, `little_loops/init/writers.py::_LL_PERMISSIONS` (`Bash(ll-help:*)`). `ll-verify-cli-allowlist` must pass. This is the only new entry point in EPIC-2938.

## Implementation Steps

1. Implement `ll-help` with md + json output and `--area` filtering.
2. Register the entry point in all three locations.
3. Rewrite `commands/help.md` to invoke `ll-help` (~20 lines).
4. Tests: catalog includes every `commands/*.md` and non-stub skill; `--json` schema stable; a drift test asserting the generated catalog covers all entries (replacing the hand-maintenance burden).

## Use Case

A user (or the `/ll:help` command itself) runs `ll-help` and gets an always-current catalog of every `/ll:` command and skill with descriptions and argument hints — no hand-maintained table to fall out of date when commands are added or renamed.

## Program Design

### Types

- `HelpEntry: dataclass` — `name: str`, `kind: Literal["command", "skill"]`, `description: str`, `argument_hint: str | None`, `area: str`

### Signatures

- `collect_entries(plugin_root: Path) -> list[HelpEntry]` — scan `commands/*.md` + `skills/*/SKILL.md` frontmatter via `frontmatter.parse_skill_frontmatter`
- `render_catalog(entries: list[HelpEntry], area: str | None, fmt: str) -> str`
- `main_help(argv: list[str] | None = None) -> int` — entry point in `scripts/little_loops/cli/help.py`

### Call Path

- `main_help()` -> `collect_entries()` -> `parse_skill_frontmatter()` (existing, `little_loops/frontmatter.py`)
- `main_help()` -> `render_catalog()`

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
- [ ] pytest coverage in `scripts/tests/`
