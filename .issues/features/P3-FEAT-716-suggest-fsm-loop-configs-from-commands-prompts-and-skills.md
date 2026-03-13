---
discovered_date: 2026-03-13
discovered_by: capture-issue
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

## Use Case

A developer installs little-loops on a new project and runs:
```
/ll:suggest-loops-from-commands
```
They see 4 proposals like "issue-lifecycle (scan → refine → implement → verify)" and "code-quality (check-code → run-tests → commit)". They pick one, it's written to `.loops/issue-lifecycle.yaml`, and they can immediately run `ll-loop run issue-lifecycle`.

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

## Impact

- **Priority**: P3 - Useful onboarding accelerator and discoverability aid
- **Effort**: Medium - Builds on loop-suggester infrastructure, new enumeration logic needed
- **Risk**: Low - Additive feature, no existing behavior changed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-13 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c4727e9-091f-4035-98d1-bd60d48ebc28.jsonl`
