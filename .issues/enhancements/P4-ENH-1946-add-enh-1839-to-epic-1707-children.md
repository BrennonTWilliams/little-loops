---
id: ENH-1946
title: Add ENH-1839 to EPIC-1707 children list
type: ENH
priority: P4
status: open
discovered_date: 2026-06-04
captured_at: "2026-06-04T19:18:32Z"
discovered_by: capture-issue
parent: EPIC-1707
labels:
  - enh
  - captured
  - bookkeeping
---

# ENH-1946: Add ENH-1839 to EPIC-1707 children list

## Summary

ENH-1839 (`populate captured_at in live-emitted issue events`) declares `parent: EPIC-1707` in its frontmatter but is not listed in the EPIC's `## Children` section or `relates_to:` frontmatter. Add it to both so tooling and reviewers see the complete child set.

## Current Behavior

- ENH-1839 is `done` and correctly parented to EPIC-1707 in its own frontmatter.
- EPIC-1707's `relates_to:` list (line 13) includes 28 child IDs but not ENH-1839.
- EPIC-1707's `## Children` section (lines 58-89) lists 29 children but not ENH-1839.
- `ll-issues epic-progress EPIC-1707` may undercount completed children or miss the relationship.

## Expected Behavior

- ENH-1839 appears in EPIC-1707's `relates_to:` frontmatter list.
- ENH-1839 appears as a bullet in EPIC-1707's `## Children` section.
- Tooling (`ll-issues epic-progress`, scope-epic, review-epic) sees the complete parent→child graph.

## Motivation

Minor bookkeeping gap found during the EPIC-1707 multi-host alignment review. Doesn't affect functionality but causes incomplete tooling output. Low effort to fix.

## Proposed Solution

1. Append `ENH-1839` to the `relates_to:` list in EPIC-1707's frontmatter.
2. Append a bullet `- **ENH-1839** — Populate captured_at in live-emitted issue events` to the `## Children` section.

## Integration Map

### Files to Modify

- `.issues/epics/P2-EPIC-1707-history-db-as-agent-context-layer.md` — frontmatter `relates_to:` + body `## Children`

### Dependent Files (Callers/Importers)

- N/A

### Similar Patterns

- N/A

### Tests

- N/A

### Documentation

- N/A

### Configuration

- N/A

## Implementation Steps

1. Edit EPIC-1707 frontmatter: append `ENH-1839` to `relates_to:` list.
2. Edit EPIC-1707 body: append bullet for ENH-1839 in `## Children` section.
3. Stage the EPIC file.

## Impact

- **Priority**: P4 — Purely cosmetic; no functional impact.
- **Effort**: Small — Two-line edit to one file.
- **Risk**: Low — No code changes.
- **Breaking Change**: No

## Labels

`enh`, `captured`, `bookkeeping`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log

- `/ll:capture-issue` - 2026-06-04T19:18:32Z - `15020717-6ee7-4d89-bd61-d70602429425.jsonl`

---

**Open** | Created: 2026-06-04 | Priority: P4
