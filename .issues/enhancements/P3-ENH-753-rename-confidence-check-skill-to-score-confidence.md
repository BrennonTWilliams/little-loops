---
id: ENH-753
priority: P3
status: backlog
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 53
---

# ENH-753: Rename `/ll:confidence-check` to `/ll:score-confidence`

## Summary

The current skill name `confidence-check` does not clearly convey that it produces a numeric score output. The name `score-confidence` better reflects the skill's primary output (a confidence score) and follows a verb-noun pattern consistent with other scoring commands.

## Current Behavior

The skill is invocable as `/ll:confidence-check` from a directory named `skills/confidence-check/`. The name describes a "check" action but does not convey that the skill produces a numeric score as its primary output.

## Expected Behavior

The skill is invocable as `/ll:score-confidence`. All internal references, documentation, cross-skill invocations, and the plugin manifest reflect the new name `score-confidence`.

## Motivation

A more descriptive name improves discoverability and self-documents what the skill does at a glance. Users scanning the command list will immediately understand that `score-confidence` produces a score, rather than needing to read the description to understand what "check" means in this context.

## Proposed Solution

Rename the skill from `confidence-check` to `score-confidence` across all relevant files:

1. Rename the skill directory: `skills/confidence-check/` → `skills/score-confidence/`
2. Update `SKILL.md` frontmatter `name` field
3. Update all trigger keyword references in the skill definition
4. Update `skills/score-confidence/SKILL.md` description and invocation examples
5. Update `.claude-plugin/plugin.json` if the skill is registered there
6. Update `CLAUDE.md` command listing
7. Update any cross-references in other skills/commands that invoke `confidence-check`
8. Update `README.md` and `docs/` references

## Integration Map

### Files to Modify
- `skills/confidence-check/` → `skills/score-confidence/` (rename directory)
- `skills/confidence-check/SKILL.md` (update name field, trigger keywords, invocation examples)
- `.claude-plugin/plugin.json` (update registered skill name if present)
- `.claude/CLAUDE.md` (update command listing)
- `README.md` and `docs/` (update references)

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` - invokes `skill: "ll:confidence-check"` and references `/ll:confidence-check` in gate messages
- `loops/issue-refinement.yaml` - references `/ll:confidence-check` in two states
- `loops/sprint-build-and-validate.yaml` - references `/ll:confidence-check` in two states
- `commands/help.md` - lists skill in command table
- `skills/create-loop/reference.md` - references skill

### Similar Patterns
- Other recently-renamed skills for naming convention reference

### Tests
- N/A - skill rename does not require test changes unless tests reference the skill name

### Documentation
- `docs/` references to `confidence-check`
- `README.md` skill listing

### Configuration
- `.claude-plugin/plugin.json` - skill registry

## Implementation Steps

1. Find all references to `confidence-check` in the codebase
2. Rename the skill directory
3. Update internal references in the skill file
4. Update cross-skill references (e.g., `manage-issue` may invoke `confidence-check`)
5. Update documentation and plugin manifest
6. Verify no broken references remain with a grep check

## Acceptance Criteria

- [ ] Skill is invocable as `/ll:score-confidence`
- [ ] Old name `/ll:confidence-check` no longer exists or redirects appropriately
- [ ] All documentation and cross-references updated
- [ ] No dangling references to `confidence-check` in the codebase

## Scope Boundaries

- **In scope**: Renaming the skill directory, updating the skill's `SKILL.md` frontmatter and body, updating all cross-references in other skills/commands, plugin manifest, CLAUDE.md, README, and docs
- **Out of scope**: Changing the skill's functionality, logic, or behavior; adding a backwards-compatibility alias for the old name; renaming any other skills

## Impact

- **Priority**: P3 - Low urgency; naming clarity improvement with no functional impact
- **Effort**: Small - File rename + grep-and-replace across known locations
- **Risk**: Low - Internal rename only; no public API or external interfaces affected
- **Breaking Change**: Yes - Users invoking `/ll:confidence-check` directly will need to update to `/ll:score-confidence`

## Verification Notes

_Verified 2026-03-15 against codebase:_
- `skills/confidence-check/` directory confirmed present
- Skill invocable as `/ll:confidence-check` — confirmed in `skills/confidence-check/SKILL.md`
- `.claude-plugin/plugin.json` does **not** register the skill — Proposed Solution step 5 is N/A
- Cross-references confirmed in: `skills/manage-issue/SKILL.md`, `loops/issue-refinement.yaml`, `loops/sprint-build-and-validate.yaml`, `commands/help.md`, `.claude/CLAUDE.md`, `README.md`, `docs/`

## Labels

`enhancement`, `ux`, `rename`, `skill`

---

## Status

**Current**: backlog

## Session Log
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:verify-issues` - 2026-03-15T19:14:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T19:12:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
