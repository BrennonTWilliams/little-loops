---
id: ENH-1728
title: Add skill to link parentless open issues to open epics
type: ENH
status: open
priority: P3
captured_at: "2026-05-26T21:00:19Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
---

# ENH-1728: Add skill to link parentless open issues to open epics

## Summary

Add a new skill (e.g., `wire-epics` or `parent-issues`) that scans all open issues lacking a `parent:` frontmatter field, compares them against open epics by semantic title/description similarity, and proposes or applies `parent:` assignments — writing the child ID back into the epic's `relates_to:` list and `## Children` section.

## Current Behavior

There is no dedicated skill for this. The closest options are:
- `/ll:map-dependencies` — handles dependency links (`blocked_by`, `depends_on`) but is not focused on epic parenting
- `/ll:align-issues` — validates issues against documents, not epic relationships
- Manual `--parent EPIC-NNN` flag on `/ll:capture-issue` — works only at creation time, not retroactively

Open issues accumulate without a `parent:` field, making epic rollups incomplete and sprint planning noisier.

## Expected Behavior

Running the skill (e.g., `/ll:wire-epics`) should:
1. Collect all open issues (BUG/FEAT/ENH) with no `parent:` frontmatter field
2. Collect all open EPICs
3. For each orphaned issue, score similarity against each EPIC (title + description overlap)
4. Present proposed parent assignments for user approval (interactive mode) or apply automatically with a `--auto` flag
5. For each accepted assignment: write `parent: EPIC-NNN` into the child issue's frontmatter, append the child ID to the epic's `relates_to:` list, and add a bullet to the epic's `## Children` section

## Motivation

Epic rollup is only useful if child issues are consistently linked. Without automation, new issues captured via `/ll:capture-issue` (without `--parent`) silently accumulate as orphans, reducing the value of epic-level planning and reporting.

## Proposed Solution

New skill `skills/wire-epics/SKILL.md`. Core flow:

1. `ll-issues list --status open --type BUG,FEAT,ENH` → filter to those without `parent:` in frontmatter
2. `ll-issues list --status open --type EPIC` → collect open epics
3. Score each (orphan, epic) pair by Jaccard similarity on significant title words + description keywords
4. Group proposals by confidence tier (high / medium / low)
5. Present for approval via `AskUserQuestion` (multiSelect) or skip prompt if `--auto`
6. Apply accepted assignments using `Edit` on both child and epic files; stage via `git add`

## Integration Map

### Files to Modify
- `skills/wire-epics/SKILL.md` — new skill (create)
- `CLAUDE.md` — add entry under Issue Refinement command list
- `.claude-plugin/plugin.json` — register skill if required

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — may reference `wire-epics` as a follow-up step
- `ll-issues` CLI — used for listing (no changes needed)

### Similar Patterns
- `skills/capture-issue/SKILL.md` Phase 4c — wires `--parent` at creation time; reuse its frontmatter edit + Children section logic
- `skills/map-dependencies/SKILL.md` — scoring + interactive proposal pattern

### Tests
- TBD — unit tests for similarity scoring; integration test applying a known orphan to a known epic

## Implementation Steps

1. Create `skills/wire-epics/SKILL.md` with argument parsing (`--auto`, `--issues`, `--epics`, `--min-score`)
2. Implement orphan discovery (grep for issues missing `parent:` line in frontmatter)
3. Implement scoring (Jaccard on title words; bonus for shared label/component keywords)
4. Implement proposal presentation and approval flow
5. Implement apply step (frontmatter edit on child, `relates_to` + `## Children` edit on epic)
6. Register skill in plugin manifest and CLAUDE.md
7. Write tests

## Impact

- **Priority**: P3 — quality-of-life for issue hygiene; no blocking use cases
- **Effort**: Small/Medium — ~200-300 lines of skill YAML/markdown; reuses capture-issue wiring logic
- **Risk**: Low — read-heavy with targeted `Edit` writes; no destructive operations
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`skill`, `issue-management`, `epics`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-26T21:00:19Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b930ee27-2d55-47e0-828a-6533b49e3b89.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
