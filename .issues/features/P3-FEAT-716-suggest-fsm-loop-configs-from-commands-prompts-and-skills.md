---
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 86
---

# FEAT-716: Suggest FSM loop configs from commands, prompts, and skills

## Summary

Add a workflow that inspects available CLI commands, slash commands (skills), and hook prompts, then suggests relevant FSM loop configurations. After reviewing the suggestions with the user, it creates the chosen loop YAML in `.loops/`.

## Current Behavior

- `/ll:loop-suggester` suggests loops from user message history (behavioral patterns)
- `/ll:create-loop` is a blank-slate interactive wizard
- No tool inspects the _existing command/skill catalog_ to propose loops that orchestrate those commands

## Expected Behavior

A new mode or skill that:
1. Enumerates available inputs: `ll-*` CLI commands, `skills/*.md` (slash commands), and hook prompts in `hooks/`
2. For each command/skill, analyzes its description, arguments, and trigger patterns
3. Proposes FSM loop configurations where the states correspond to natural sequences of those commands (e.g., scan → refine → implement → verify)
4. Presents multiple ranked proposals to the user in a reviewable format
5. On user selection, generates and writes the loop YAML to `.loops/`

## Motivation

The loop-suggester infers automation from _past behavior_; this feature synthesizes automation from _available capabilities_. A user who just installed little-loops has no message history but does have a rich command set — this gives them immediate loop proposals without needing history first.

## Proposed Solution

Extend `/ll:loop-suggester` with a `--from-commands` flag (or create a new skill `ll:suggest-loops-from-commands`) that:

1. Reads `skills/*/SKILL.md` files for skill names, triggers, and descriptions
2. Reads `ll-*` CLI entry points from `scripts/pyproject.toml` or help text
3. Groups by workflow theme (issue management, code quality, git, loops, analysis)
4. Generates FSM loop YAML for the top 3-5 most coherent sequences
5. Uses the existing `create-loop` YAML schema and writes to `.loops/`

## Integration Map

### Files to Modify
- `skills/loop-suggester/SKILL.md` — add `--from-commands` flag documentation
- `skills/loop-suggester/skill.py` (or equivalent) — implement command-source analysis
- OR create `skills/suggest-loops-from-commands/SKILL.md` as a new standalone skill

### Dependent Files (Callers/Importers)
- `skills/create-loop/SKILL.md` — may share YAML schema helpers
- `scripts/little_loops/loops/` — loop schema validation
- `.loops/` — output directory for generated loop configs

### Similar Patterns
- `skills/loop-suggester/SKILL.md` — existing history-based suggestion (same output format)
- `skills/create-loop/SKILL.md` — YAML schema and interactive review pattern

### Tests
- `scripts/tests/` — add test for command enumeration and proposal generation

### Documentation
- `docs/ARCHITECTURE.md` — document new suggestion mode
- `README.md` or plugin docs — mention `--from-commands` flag

### Configuration
- No new config keys expected; respects existing `ll-config.json` `loops.*` settings

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correct implementation target** (Verification Notes confirmed): `commands/loop-suggester.md` — not a skill; extend this command or create a new skill directory. If extending as a skill: create `skills/loop-suggester-from-commands/SKILL.md` (or add `--from-commands` flag handling to `commands/loop-suggester.md`).

**Skill enumeration source** — Glob `skills/*/SKILL.md` (16 files exist); parse YAML frontmatter block. Each SKILL.md has `description` (often includes "Trigger keywords:" inline), `argument-hint`, `allowed-tools`, and `arguments` fields. Command enumeration: Glob `commands/*.md` (similar frontmatter structure).

**CLI entry points** — Parse `scripts/pyproject.toml:47-59` `[project.scripts]` section; 12 `ll-*` entries map to Python callables. No help-text API exists — entry-point names and descriptions must be sourced from `pyproject.toml` and cross-referenced with `commands/*.md` or `CLAUDE.md`.

**FSM schema required fields** (`scripts/little_loops/fsm/schema.py`):
- `FSMLoop` (line 339): requires `name`, `initial`, `states`; optional `max_iterations` (default 50), `timeout`, `on_handoff`, `context`, `scope`, `maintain`
- `StateConfig` (line 167): `action`, `action_type` (`"prompt"/"slash_command"/"shell"`), `on_success`, `on_failure`, `on_error`, `next`, `terminal`, `capture`, `timeout`
- Evaluator types: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `llm_structured`

**Suggestion output format** — `commands/loop-suggester.md:252-284` writes to `.claude/loop-suggestions/suggestions-{timestamp}.yaml` with fields: `analysis_metadata`, `summary`, `suggestions[]`. Each suggestion: `id`, `name`, `loop_type`, `confidence`, `rationale`, `yaml_config` (must be valid FSM YAML), `usage_instructions`. The new `--from-commands` mode should write to the same format/location and set `source: "commands-catalog"` in `analysis_metadata`.

**FSM paradigm templates** (reusable) — `skills/create-loop/loop-types.md` has 4 complete FSM templates: fix-until-clean (lines 152-196), maintain-constraints (lines 265-325), drive-metric (lines 381-428), run-sequence (lines 489-543). These are the target shapes for generated proposals.

**`loops/` vs `.loops/` distinction**:
- `loops/` = 19 built-in YAML definitions (not writable by users)
- `.loops/` = user-created loop configs + `.running/` runtime state
- `resolve_loop_path()` at `scripts/little_loops/cli/loop/_helpers.py:86` checks both; user-generated YAMLs should go to `.loops/` (`config.loops.loops_dir`)

**Validation entry point** — `load_and_validate(path)` at `scripts/little_loops/fsm/validation.py:354`; called by `ll-loop validate <name>`. Returns `(FSMLoop, list[ValidationError])`. Raises `ValueError` on ERROR-severity issues.

**Test files to model after**:
- `scripts/tests/test_loop_suggester.py` — output schema structure and confidence bounds
- `scripts/tests/test_builtin_loops.py:17-43` — bulk validation pattern for generated YAMLs
- `scripts/tests/test_fsm_schema.py:38-65` — `make_state()` / `make_fsm()` helpers
- `scripts/tests/test_create_loop.py` — CLI validate round-trip pattern

## Use Case

A developer installs little-loops on a new project and runs:
```
/ll:suggest-loops-from-commands
```
They see 4 proposals like "issue-lifecycle (scan → refine → implement → verify)" and "code-quality (check-code → run-tests → commit)". They pick one, it's written to `.loops/issue-lifecycle.yaml`, and they can immediately run `ll-loop run issue-lifecycle`.

## Acceptance Criteria

- All `skills/*/SKILL.md` files are enumerated and their names, descriptions, and trigger keywords are extracted
- All `ll-*` CLI entry points from `scripts/pyproject.toml` are enumerated with their descriptions
- Commands/skills are grouped into at least 3 workflow themes (e.g., issue management, code quality, git/release)
- At least 3 FSM loop proposals are generated, each with 3–7 states referencing real command/skill names
- Proposals are presented in a reviewable format (table or list with state details) before any file is written
- On user selection, a valid YAML file is written to `.loops/` and passes existing loop schema validation
- The feature works on a fresh installation with zero Claude Code message history
- Running `/ll:loop-suggester --from-commands` (or equivalent) does not require or read message history files

## API/Interface

```bash
# New flag on existing skill
/ll:loop-suggester --from-commands

# OR new dedicated skill
/ll:suggest-loops-from-commands
```

Proposed output format (same as loop-suggester):
```yaml
# .loops/issue-lifecycle.yaml
name: issue-lifecycle
description: Full issue lifecycle from scan to completion
states:
  - name: scan
    prompt: "Run /ll:scan-codebase and report new issues found"
  - name: refine
    ...
```

## Implementation Steps

1. Enumerate available commands/skills from `skills/*/SKILL.md` and CLI entry points
2. Group by workflow theme using keyword matching on descriptions/triggers
3. Generate candidate FSM sequences per theme (3-7 states each)
4. Render proposals in a user-reviewable table with state details
5. On selection, validate and write YAML to `.loops/` using existing schema
6. Add tests for enumeration and proposal logic

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references for implementers:_

1. **Enumerate skills**: Glob `skills/*/SKILL.md` (16 files) and parse YAML frontmatter — extract `description` (includes "Trigger keywords:"), `argument-hint`, `arguments[].name`. Enumerate commands: Glob `commands/*.md` (same frontmatter). For CLI commands: parse `[project.scripts]` from `scripts/pyproject.toml:47-59`.

2. **Group by theme**: Map each skill/command to one of 5 themes (issue-management, code-quality, git-release, loops, analysis) by matching keywords in `description` and trigger keywords fields. Themes align with the groupings in `CLAUDE.md` and `docs/reference/COMMANDS.md`.

3. **Generate FSM proposals**: Reuse the 4 paradigm templates from `skills/create-loop/loop-types.md` (fix-until-clean, maintain-constraints, drive-metric, run-sequence). Reference real command/skill names as `action` values with `action_type: slash_command` or `action_type: prompt`. Look at `loops/fix-quality-and-tests.yaml` and `loops/issue-refinement.yaml` for production-quality examples.

4. **Render proposals**: Follow `commands/loop-suggester.md:252-284` output schema — write to `.claude/loop-suggestions/suggestions-{timestamp}.yaml` with `id`, `name`, `loop_type`, `confidence`, `rationale`, `yaml_config` (valid FSM YAML), `usage_instructions`. Set `source: "commands-catalog"` in `analysis_metadata` to distinguish from history-based suggestions.

5. **Validate and write**: Call `load_and_validate(path)` at `scripts/little_loops/fsm/validation.py:354` before presenting to user. Write accepted YAML to `{{config.loops.loops_dir}}/<name>.yaml` (resolves to `.loops/<name>.yaml`). Run `ll-loop validate <name>` as a final check (uses `resolve_loop_path()` at `scripts/little_loops/cli/loop/_helpers.py:86`).

6. **Add tests**: Model after `scripts/tests/test_loop_suggester.py` for output schema validation. Use `make_state()` / `make_fsm()` helpers from `scripts/tests/test_fsm_schema.py:38-65`. Add bulk validation test following `scripts/tests/test_builtin_loops.py:17-43` pattern to verify all generated proposals pass `load_and_validate()`.

## Impact

- **Priority**: P3 - Useful onboarding accelerator and discoverability aid
- **Effort**: Medium - Builds on loop-suggester infrastructure, new enumeration logic needed
- **Risk**: Low - Additive feature, no existing behavior changed
- **Breaking Change**: No

## Verification Notes

Verified 2026-03-13 against codebase. Two path inaccuracies in Integration Map:

1. **`skills/loop-suggester/SKILL.md`** — does not exist as a skill. The current implementation is `commands/loop-suggester.md`. If extending it, modify that file (not a skill directory).
2. **`scripts/little_loops/loops/`** — directory does not exist. Loop schema validation lives in `scripts/little_loops/fsm/` (`schema.py`, `validation.py`, `fsm-loop-schema.json`). Generated loop YAMLs are written to `.loops/` (project root), which does exist.

All other claims and references are accurate.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-13 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c4727e9-091f-4035-98d1-bd60d48ebc28.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b28391f-b086-4d28-86cb-448201c8b40e.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
