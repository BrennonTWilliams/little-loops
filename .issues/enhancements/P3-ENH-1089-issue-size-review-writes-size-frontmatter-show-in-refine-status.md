---
id: ENH-1089
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1089: issue-size-review writes size frontmatter, show in refine-status

## Summary

Two related improvements to surface issue size data across the toolchain: (1) `/ll:issue-size-review` should persist its size assessment by writing a `size` field to each issue's YAML frontmatter after review, and (2) `ll-issues refine-status` should display a `Size` column in its tabular CLI output using that frontmatter field.

## Current Behavior

- `/ll:issue-size-review` analyzes issue complexity and outputs a size recommendation (XS/S/M/L/XL) to the conversation, but does not write the result back to the issue file's frontmatter.
- `ll-issues refine-status` renders a table of issues with refinement status but has no `Size` column, so the size data is invisible in CLI workflows.

## Expected Behavior

- After `/ll:issue-size-review` assesses an issue, it writes `size: <XS|S|M|L|XL>` to the YAML frontmatter of the issue file.
- `ll-issues refine-status` reads the `size` frontmatter field and renders it as a `Size` column in the table (empty/`-` when not yet reviewed).

## Motivation

Size data is only useful if it persists and is visible. Right now the assessment is ephemeral — it disappears when the conversation ends. Persisting it to frontmatter makes it available to sprint planning, dependency analysis, and CLI reporting. Showing it in `refine-status` closes the feedback loop for users doing issue triage.

## Proposed Solution

**Part 1 — `issue-size-review` skill writes frontmatter:**

After computing the size label, use a frontmatter update pattern consistent with how other skills write back to issue files (e.g., how `confidence-check` writes `confidence` or `concerns`). The `size` field should be added/updated under the YAML `---` block.

```yaml
# Expected frontmatter after review
size: M
```

**Part 2 — `ll-issues refine-status` column:**

In `scripts/little_loops/issues.py` (or wherever `refine-status` is rendered), read `size` from the issue's parsed frontmatter and include it as a column. When the field is absent, display `-`.

Example output:
```
 ID       | Priority | Size | Confidence | Status
----------+----------+------+------------+--------
 ENH-1089 | P3       | M    | -          | active
 BUG-1079 | P3       | S    | high       | active
```

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — add frontmatter write step after size determination
- `scripts/little_loops/issues.py` — add `size` column to `refine-status` table renderer

### Dependent Files (Callers/Importers)
- Any code that parses issue frontmatter (shared frontmatter utilities if they exist)

### Similar Patterns
- `skills/confidence-check/SKILL.md` — writes `confidence` + `concerns` to frontmatter (reference implementation)
- `ll-issues show` command — already reads and displays frontmatter fields

### Tests
- `scripts/tests/` — add/update tests for `refine-status` column rendering with and without `size` field
- Test that `issue-size-review` skill instructions correctly specify the write-back step

### Documentation
- `docs/reference/API.md` — if `size` becomes a documented frontmatter field, add it to the schema

### Configuration
- N/A

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md` to understand the existing frontmatter write-back pattern.
2. Update `skills/issue-size-review/SKILL.md` to write `size: <label>` to the issue's YAML frontmatter after determining the size.
3. Locate the `refine-status` rendering logic in `scripts/little_loops/issues.py`.
4. Add `size` field extraction from parsed frontmatter.
5. Insert `Size` column into the `refine-status` table (display `-` when absent).
6. Add/update tests for the new column.

## Impact

- **Scope**: Small — two files modified (SKILL.md + issues.py), additive changes only
- **Risk**: Low — purely additive; missing `size` field gracefully shows `-`
- **Users**: Anyone using `ll-issues refine-status` for issue triage or sprint prep

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/confidence-check/SKILL.md` | Reference pattern for frontmatter write-back |
| `scripts/little_loops/issues.py` | Target file for CLI column change |
| `docs/reference/API.md` | Frontmatter field documentation |

## Labels

`enhancement`, `issue-size-review`, `ll-issues`, `refine-status`, `frontmatter`

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46a03127-ab0d-49ea-90a5-3516db3882e6.jsonl`

---

## Status

**State**: active
