---
id: ENH-1727
type: ENH
priority: P3
status: open
captured_at: "2026-05-26T20:32:38Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
---

# ENH-1727: Add `--group-by epic` option to `ll-issues list`

## Summary

`ll-issues list` currently groups issues by type (BUG / FEAT / ENH / EPIC). Add a `--group-by epic` flag that instead groups child issues under their parent epic, with an "Unparented" bucket for issues that have no `parent:` set. The `parent` field is already parsed on `IssueFile` — this is a display-only change.

## Current Behavior

`ll-issues list` always outputs four fixed type buckets (Bugs, Features, Enhancements, Epics). There is no way to see which issues belong to a given epic without opening each file individually or using `ll-deps`.

## Expected Behavior

`ll-issues list --group-by epic` outputs issues grouped by their parent epic:

```
EPIC-1663: Sprint Runner Improvements (3)
  P3  ENH-1727  Add --group-by epic option to ll-issues list
  ...

Unparented (12)
  P2  BUG-1700  ...
```

## Motivation

Developers working within an epic want a quick way to see the full scope of child issues without switching to `ll-deps`. Grouping by epic gives a natural project-plan view alongside the existing type-grouped view.

## Proposed Solution

1. Add `--group-by {type,epic}` argument to the `list` subparser (default: `type` to preserve existing behaviour).
2. In `cmd_list`, branch on `args.group_by`:
   - `"type"` — existing logic unchanged.
   - `"epic"` — bucket issues by `issue.parent`, with `None` → "Unparented". Sort buckets so named epics come first (alphabetically by EPIC ID), unparented last.
3. For each epic bucket header, optionally resolve the epic title by looking up the matching EPIC issue file.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — add grouping branch
- `scripts/little_loops/cli/issues/__init__.py` (or wherever the `list` subparser is registered) — add `--group-by` argument

### Dependent Files (Callers/Importers)
- `scripts/tests/test_issues_list.py` (if exists) — add test for `--group-by epic`

### Similar Patterns
- `list_cmd.py:134–155` — existing type-bucket grouping to model the new branch after

### Tests
- Unit test: issues with `parent: EPIC-NNN` appear under the correct epic bucket
- Unit test: issues with no `parent:` appear under "Unparented"
- Unit test: `--group-by type` (default) still produces the same output as before

## Implementation Steps

1. Add `--group-by` choice argument to the list subparser
2. Implement epic-grouping branch in `cmd_list` after the sort/limit step
3. Add EPIC title resolution (read matching EPIC file, extract `# EPIC-NNN: Title` header)
4. Write/update tests
5. Verify `--flat` and `--json` flags still work (they bypass the grouping display, so they should be unaffected)

## Impact

- **Priority**: P3 - Quality-of-life for epic-centric workflows
- **Effort**: Small — data already available, pure display change
- **Risk**: Low — new flag with default preserving existing behaviour
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `issues`, `epics`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-26T20:32:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b05a1db1-f9bd-43eb-b427-427c3cdbc0ac.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
