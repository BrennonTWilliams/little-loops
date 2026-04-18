---
id: FEAT-1155
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
---

# FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Summary

Record a `captured_at` ISO timestamp in issue frontmatter when `/ll:capture-issue` creates a new issue, and record a `completed_at` ISO timestamp when an issue is moved to `.issues/completed/`.

## Motivation

Issues currently have `discovered_date` (date-only), but no machine-readable record of the exact moment capture happened or when the issue was completed. Without precise timestamps, velocity metrics from `ll-history` and other analysis tools can only resolve to day granularity. Capture and completion times are the two most analytically useful moments in an issue's lifecycle — both should be persisted where they're discovered, not reconstructed from git blame.

## Implementation Steps

1. **`/ll:capture-issue` skill** (`skills/capture-issue/SKILL.md`): After writing the issue file, add `captured_at: <ISO 8601 datetime>` to its YAML frontmatter (alongside existing `discovered_date`).

2. **Issue completion paths** — all places that move a file into `completed/` must append `completed_at: <ISO 8601 datetime>` to the frontmatter before or immediately after the move:
   - `/ll:manage-issue` skill (`skills/manage-issue/`)
   - `ll-auto` CLI (`scripts/little_loops/auto.py` or equivalent)
   - `ll-parallel` CLI (`scripts/little_loops/parallel.py` or equivalent)
   - `ll-sprint` CLI
   - Any `git mv` wrapper that targets the completed dir

3. **Schema**: Add both fields to `config-schema.json` issue frontmatter documentation; update `ll-issues show` to display them.

4. **`ll-history` / analytics**: Use `captured_at` and `completed_at` where available for sub-day resolution; fall back to `discovered_date` / file mtime when absent.

## API/Interface

New frontmatter fields:

```yaml
captured_at: "2026-04-18T14:32:07Z"   # set by capture-issue
completed_at: "2026-05-01T09:15:44Z"  # set when moved to completed/
```

Format: ISO 8601 UTC (`datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")` in Python, or `date -u +"%Y-%m-%dT%H:%M:%SZ"` in shell).

## Acceptance Criteria

- [ ] New issues created by `/ll:capture-issue` contain `captured_at` in frontmatter
- [ ] Issues moved to `completed/` via any path contain `completed_at` in frontmatter
- [ ] `captured_at` and `completed_at` are valid ISO 8601 UTC strings
- [ ] `ll-issues show` displays both fields when present
- [ ] Existing issues without these fields continue to work without errors

## Session Log
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a073fd14-d01d-4031-914c-a939a2a2d07d.jsonl`
