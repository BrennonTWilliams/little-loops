---
id: ENH-1730
title: "Add link-epics skill: wiring and documentation updates"
type: ENH
status: done
priority: P3
parent: ENH-1728
---

# ENH-1730: Add link-epics skill: wiring and documentation updates

## Summary

Update all existing files that reference the skill catalog to include `link-epics`: CLAUDE.md, capture-issue, issue-workflow, help.md, COMMANDS.md, and the three count-tracking docs (README, CONTRIBUTING, ARCHITECTURE).

## Parent Issue

Decomposed from ENH-1728: Add skill to link parentless open issues to open epics

## Prerequisites

ENH-1729 must be complete (skill file at `skills/link-epics/SKILL.md` must exist) before these documentation updates can be applied.

## Scope

This child covers **Implementation Steps 8–12** from the parent:

8. Update `skills/capture-issue/SKILL.md` — add `link-epics` as a follow-up in `## Integration` section ("After capturing issues, run `/ll:link-epics` to assign parentless issues to epics")
9. Update `skills/issue-workflow/SKILL.md` — add `link-epics` to `### 2. Refinement Phase` command sequence and `## Related Skills` table
10. Update `commands/help.md` — add `link-epics` stanza to `ISSUE REFINEMENT` block (static file; not auto-discovered by `/ll:help`)
11. Update `docs/reference/COMMANDS.md` — add `### /ll:link-epics` section with `--auto`/`--min-score` flags, Quick Reference table row, and append `link-epics` to the `--auto`-supported skills row in the Flag Conventions table
12. Increment skill counts in count-tracking docs (all enforced by `ll-verify-docs` CI gate via `scripts/little_loops/doc_counts.py`):
    - `README.md`: `30 skills` → `31 skills`
    - `CONTRIBUTING.md`: `30 skill definitions` → `31`
    - `docs/ARCHITECTURE.md`: `SKL[Skills<br/>30 composable skills]` → `31` (Mermaid) AND `30 skill definitions` → `31` (directory tree)

Also update `docs/reference/CLI.md` — add `link-epics` skill invocation example (identified in the parent's "Files to Modify" list).

## Files to Modify

- `skills/capture-issue/SKILL.md` — `## Integration` section
- `skills/issue-workflow/SKILL.md` — Refinement Phase + Related Skills
- `commands/help.md` — ISSUE REFINEMENT block
- `docs/reference/COMMANDS.md` — new section + Quick Reference row + Flag Conventions table
- `docs/reference/CLI.md` — invocation example
- `README.md` — skill count 30 → 31
- `CONTRIBUTING.md` — skill count 30 → 31
- `docs/ARCHITECTURE.md` — Mermaid SKL node + directory tree count 30 → 31

## Acceptance Criteria

- `ll-verify-docs` exits 0 (skill count in README/CONTRIBUTING/ARCHITECTURE matches actual `skills/` directory count)
- `/ll:help` shows `link-epics` in the Issue Refinement section
- `commands/help.md` contains a `link-epics` entry in the ISSUE REFINEMENT block

## Session Log
- `/ll:issue-size-review` - 2026-05-26T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2480abd-758c-47ca-aa87-454ae8a76200.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
