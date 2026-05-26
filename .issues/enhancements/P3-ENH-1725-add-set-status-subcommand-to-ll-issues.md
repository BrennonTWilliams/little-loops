---
id: ENH-1725
title: "Add set-status subcommand to ll-issues"
type: ENH
status: open
priority: P3
captured_at: "2026-05-26T20:15:32Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
---

# ENH-1725: Add set-status subcommand to ll-issues

## Summary

`ll-issues` currently has no CLI subcommand to change the `status:` frontmatter field of an issue file. Users must edit frontmatter manually or use a `sed` one-liner. Adding a `set-status` subcommand would provide a first-class, safe way to transition issue status from the command line.

## Current Behavior

There is no `ll-issues set-status` command. Changing status requires either:
- Direct file edit
- `sed -i '' 's/^status: open/status: in_progress/' "$(ll-issues path FEAT-123)"`

## Expected Behavior

```bash
ll-issues set-status ENH-1725 in_progress
ll-issues set-status BUG-042 done
ll-issues ss ENH-1725 blocked   # short alias
```

The command should:
1. Resolve the issue file path via the existing `path` logic
2. Validate the new status value against the canonical enum (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`)
3. Edit the `status:` frontmatter field in-place
4. Print the result (e.g., `ENH-1725: open → in_progress`)
5. Exit non-zero on invalid status or unknown issue ID

## Motivation

Status changes are frequent during sprint execution and issue triage. Today they require knowing the file path and using shell incantations. A `set-status` subcommand makes the operation scriptable, safe (validated enum), and consistent with the rest of the `ll-issues` surface area. It would also enable automation loops and hooks to update status without fragile sed calls.

## Proposed Solution

Add a `set-status` (alias `ss`) subparser to `scripts/little_loops/cli/issues.py` following the same pattern as `set-scores` and `skip`. Use the existing `read_issue_file` / `write_issue_frontmatter` utilities (or equivalent) to update only the `status:` key without touching other frontmatter fields.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues.py` — add `set-status` subparser and handler
- `scripts/little_loops/issue_utils.py` (or equivalent) — reuse or extend frontmatter write helpers

### Dependent Files (Callers/Importers)
- Any automation loops or hooks that currently use `sed` to change status can be updated to use `ll-issues set-status`

### Similar Patterns
- `set-scores` subcommand in `scripts/little_loops/cli/issues.py` — same write-frontmatter pattern
- `skip` subcommand — reads file path, mutates frontmatter, prints result

### Tests
- `scripts/tests/` — add test for valid status transition, invalid status rejection, unknown ID

### Documentation
- `CLAUDE.md` CLI Tools section — add `set-status` to `ll-issues` description

### Configuration
- Status enum is defined in `CLAUDE.md` § Issue File Format; validation should use same canonical list

## Implementation Steps

1. Add `set-status` / `ss` subparser to `issues.py` with `id` and `status` positional args
2. Implement handler: resolve path → read frontmatter → validate status → write → print diff
3. Add tests covering happy path, invalid status, unknown ID
4. Update `CLAUDE.md` CLI Tools description for `ll-issues`

## Impact

- **Priority**: P3 - Quality-of-life; frequent friction point during sprint work
- **Effort**: Small - ~1 hour; follows established `set-scores` pattern exactly
- **Risk**: Low - isolated frontmatter write, no side effects
- **Breaking Change**: No

## API/Interface

```python
# Proposed CLI surface
ll-issues set-status <ISSUE_ID> <status>
ll-issues ss <ISSUE_ID> <status>

# Output
ENH-1725: open → in_progress

# Error cases
Error: unknown status 'wip'. Valid values: open, in_progress, blocked, deferred, done, cancelled
Error: issue not found: ENH-9999
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `captured`

## Status

**Open** | Created: 2026-05-26 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-26T20:15:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
