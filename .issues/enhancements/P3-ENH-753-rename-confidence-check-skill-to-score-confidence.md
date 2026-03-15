---
id: ENH-753
priority: P3
status: backlog
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# ENH-753: Rename `/ll:confidence-check` to `/ll:score-confidence`

## Problem Statement

The current skill name `confidence-check` does not clearly convey that it produces a numeric score output. The name `score-confidence` better reflects the skill's primary output (a confidence score) and follows a verb-noun pattern consistent with other scoring commands.

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

---

## Status

**Current**: backlog

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
