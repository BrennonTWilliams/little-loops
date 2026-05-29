---
id: ENH-1802
type: ENH
priority: P3
status: open
captured_at: "2026-05-29T20:55:00Z"
discovered_date: "2026-05-29"
discovered_by: capture-issue
labels: [enhancement, skills, audit-issue-conflicts, idempotency]
parent: EPIC-1745
---

# ENH-1802: audit-issue-conflicts re-appends Scope Boundary section on every run

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 4b's `split / update_scope` action appends a `## Scope Boundary` section to affected issue files without checking whether a prior audit run already added one. Repeated runs that surface the same scope-overlap conflict accumulate duplicate sections.

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md` Phase 4b unconditionally appends `## Scope Boundary` and `## Scope Addition` sections to affected issue files. When the same scope-overlap conflict resurfaces on a later audit run, a second identical section is appended, bloating the issue file with duplicate content.

## Reproduction

1. Run `/ll:audit-issue-conflicts`, approve a `split/update_scope` recommendation on ISSUE-X — appends a `## Scope Boundary` section
2. On a later run, the same conflict re-surfaces (because neither issue changed enough to dissolve it)
3. Approve again — a second identical `## Scope Boundary` section is appended

Observed in this run on 2026-05-29: ENH-1617 already had a Scope Boundaries section from a 2026-05-23 audit run with verbatim the recommendation this run produced. I detected the duplicate manually and skipped the body edit. Following the skill spec would have appended a second copy.

## Expected Behavior

Before appending, the skill scans the target file for an existing audit-authored Scope Boundary / Scope Addition note. If found and the proposed content matches (or is a superset), the skill skips the edit and logs `[idempotent: ScopeBoundary already present from <prior-audit-date>]`.

## Motivation

This enhancement would:
- Prevent issue file bloat from repeated `/ll:audit-issue-conflicts` runs on the same backlog
- Improve audit reliability by making Phase 4b actions safe to re-run
- Reduce manual cleanup effort — users shouldn't need to check for and remove duplicate sections

## Root Cause

`skills/audit-issue-conflicts/SKILL.md` Phase 4b lines 326–333 unconditionally append:

```markdown
---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): …
```

No pre-check. The `merge / deprecate` path has the same issue (appends `## Scope Addition` unconditionally).

## Proposed Solution

Before each Phase 4b append, grep the target file for an existing `## Scope Boundary` / `## Scope Addition` section authored by `/ll:audit-issue-conflicts`. If present:
- If the body of that section already mentions the conflicting issue ID → skip the append, log "idempotent skip"
- If not → append a follow-up paragraph inside the existing section instead of opening a duplicate section

Same logic for `## Scope Addition`, `## Resolution`, and any other audit-authored body section.

## Implementation Steps

1. Extract a `check_existing_audit_section()` helper in the skill (awk/grep)
2. Wire the helper into each Phase 4b action (merge, split, deprecate)
3. Decide: skip vs paragraph-append for the conflict-already-noted case
4. Add a regression test: run the audit twice over the same fixture; assert only one Scope Boundary section results

## Acceptance Criteria

- Running `/ll:audit-issue-conflicts` twice on an unchanged backlog produces zero duplicate Scope Boundary / Scope Addition sections
- Final report distinguishes "Applied" from "Skipped (idempotent)" outcomes
- Pytest fixture covers the double-run case

## Scope Boundaries

- **In scope**: Add idempotency pre-check to Phase 4b append operations (`split/update_scope`, `merge/deprecate`), covering Scope Boundary, Scope Addition, and Resolution sections
- **Out of scope**: Full deduplication of all audit-authored content across all phases; changes to non-audit skills

## Success Metrics

- Duplicate Scope Boundary/Scope Addition sections after 2 audit runs on unchanged backlog: **0**
- Final report distinguishes "Applied" from "Skipped (idempotent)" outcomes
- Pytest fixture covers the double-run idempotency case

## API/Interface

N/A — No public API changes. Internal skill logic update only.

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 4b add pre-check helper

### Similar Patterns
- `ll-issues append-log` is idempotent on session-log entries — review its dedupe heuristic for reuse

### Tests
- `scripts/tests/test_skill_audit_issue_conflicts.py` — add double-run idempotency case

## Impact

- **Priority**: P3 — quality-of-life; doesn't break the issue but bloats files over time
- **Effort**: Small — helper + pre-check in 2–3 Phase 4b sites
- **Risk**: Low
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:format-issue` - 2026-05-29T21:12:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d42814df-045f-41ae-b065-5f4d670ef04d.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P3
