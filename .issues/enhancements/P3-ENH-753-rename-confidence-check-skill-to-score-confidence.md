---
id: ENH-753
priority: P3
status: backlog
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 45
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key architectural insight**: The skill invocation name `/ll:<name>` is derived **solely from the directory name** under `skills/`. The `SKILL.md` frontmatter has no `name:` field — confirmed across all 18 skills. Renaming the directory is the single change that updates the invocation name; all other edits are reference updates only.

**Complete reference map with line numbers:**

| File | Line(s) | Occurrence |
|---|---|---|
| `skills/confidence-check/SKILL.md` | 61 | Error message: `Usage: /ll:confidence-check --all` |
| `skills/confidence-check/SKILL.md` | 400 | Session log template reference |
| `skills/confidence-check/SKILL.md` | 540–553 | Six usage pattern invocation examples |
| `skills/manage-issue/SKILL.md` | 116, 120, 170, 180 | Prose + Skill tool call (`skill: "ll:confidence-check"`) + two halt messages |
| `skills/issue-workflow/SKILL.md` | 115, 159 | Workflow stage table entries |
| `skills/create-loop/reference.md` | 715 | Example loop action string |
| `loops/issue-refinement.yaml` | 81, 89 | Two `action:` strings |
| `loops/sprint-build-and-validate.yaml` | 38, 68 | Two `action:` strings |
| `commands/help.md` | 75 | Skills listing |
| `commands/create-sprint.md` | 369 | Warning message reference |
| `.claude/CLAUDE.md` | 53 | Planning & Implementation skill list |
| `README.md` | 131, 208 | Command table + skill table |
| `CONTRIBUTING.md` | 131 | Directory tree entry |
| `docs/ARCHITECTURE.md` | 113 | Directory tree entry |
| `docs/reference/COMMANDS.md` | 15, 17, 164, 432 | Flag tables + section header + skill table |
| `docs/reference/API.md` | 507–508 | Field-level doc comments |
| `docs/guides/LOOPS_GUIDE.md` | 334 | Skill name in `--check` flag description |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | 264–266 | Three invocation examples |
| `docs/demo/scenarios.md` | 99 | Demo scenario invocation example |
| `scripts/tests/test_refine_status.py` | 267, 816 | Test data: session command strings referencing skill name |
| `scripts/little_loops/issue_parser.py` | 216–217 | Docstring references in `confidence_score`/`outcome_confidence` field docs |

**No prior skill renames found** in the codebase or issue history. This is the first skill directory rename in this project.

### Similar Patterns
- No prior skill directory renames exist in this codebase — the pattern for this rename is: `git mv skills/confidence-check skills/score-confidence`, then grep-replace `confidence-check` → `score-confidence` across all files listed above

### Tests
- `scripts/tests/test_refine_status.py:267,816` — references `"/ll:confidence-check"` as session command strings in test data; must be updated to `"/ll:score-confidence"`
- `scripts/little_loops/issue_parser.py:216–217` — docstring references only; update to reflect new skill name

### Documentation
- `docs/` references to `confidence-check`
- `README.md` skill listing

### Configuration
- `.claude-plugin/plugin.json` - skill registry

## Implementation Steps

1. Rename the skill directory: `git mv skills/confidence-check skills/score-confidence`
2. Update internal self-references in `skills/score-confidence/SKILL.md` at lines 61, 400, 540–553 (description text, error message, session log template, usage examples) — **no frontmatter `name:` field exists; directory name is the invocation name**
3. Update cross-skill callers:
   - `skills/manage-issue/SKILL.md:116,120,170,180` — prose reference, Skill tool call (`"ll:confidence-check"` → `"ll:score-confidence"`), and two halt messages
   - `skills/issue-workflow/SKILL.md:115,159` — workflow stage table entries
   - `skills/create-loop/reference.md:715` — example action string
4. Update FSM loop files:
   - `loops/issue-refinement.yaml:81,89` — two `action:` strings
   - `loops/sprint-build-and-validate.yaml:38,68` — two `action:` strings
5. Update commands and CLAUDE.md:
   - `commands/help.md:75` — skills listing
   - `commands/create-sprint.md:369` — warning message
   - `.claude/CLAUDE.md:53` — Planning & Implementation skill list
6. Update documentation:
   - `README.md:131,208`
   - `CONTRIBUTING.md:131`
   - `docs/ARCHITECTURE.md:113`
   - `docs/reference/COMMANDS.md:15,17,164,432`
   - `docs/reference/API.md:507-508`
   - `docs/guides/LOOPS_GUIDE.md:334`
   - `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:264-266`
   - `docs/demo/scenarios.md:99`
7. Update Python files:
   - `scripts/tests/test_refine_status.py:267,816` — update session command strings
   - `scripts/little_loops/issue_parser.py:216–217` — update docstring references
8. Verify no dangling references: `grep -r "confidence-check" . --include="*.md" --include="*.yaml" --include="*.json" --include="*.py" -l`

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
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:refine-issue` - 2026-03-15T19:39:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:confidence-check` - 2026-03-15T19:37:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:refine-issue` - 2026-03-15T19:34:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:confidence-check` - 2026-03-15T19:27:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:refine-issue` - 2026-03-15T19:23:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:confidence-check` - 2026-03-15T19:22:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:refine-issue` - 2026-03-15T19:20:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:verify-issues` - 2026-03-15T19:14:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T19:12:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-15T19:39:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
