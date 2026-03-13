---
discovered_commit: 1cc2673
discovered_branch: main
discovered_date: 2026-03-13T21:11:34Z
discovered_by: capture-issue
---

# FEAT-728: Add `ll-issues search` subcommand with filters and sorting

## Summary

Add a dedicated `ll-issues search` subcommand that enables rich querying across all issue files — active and completed — with filters for status, type, priority, labels, and dates, plus configurable sort order. Provides a single ergonomic entry point for finding issues without manually scanning directories or grepping filenames.

## Motivation

Currently the only way to find issues is `ll-issues list` (which shows active issues) or browsing `.issues/` directories manually. There is no way to:
- Search across both active and completed issues at once
- Filter by creation or updated date
- Sort results by any field
- Combine multiple filter criteria in a single command

This gaps make it hard to answer questions like "what P2 bugs were completed last month?" or "which FEAT issues mention caching?".

## Use Case

```bash
# Find all active P2 BUG issues
ll-issues search --type BUG --priority P2

# Search issue titles/bodies for a keyword, include completed
ll-issues search "caching" --include-completed

# Filter by date range and sort by priority
ll-issues search --since 2026-01-01 --sort priority

# Show only features with a specific label
ll-issues search --type FEAT --label "api"

# JSON output for scripting
ll-issues search --type BUG --json
```

## Proposed Interface

```
ll-issues search [QUERY] [OPTIONS]

Arguments:
  QUERY             Optional text to match against title and body (case-insensitive)

Filters:
  --type TYPE       Filter by issue type: BUG, FEAT, ENH (repeatable)
  --priority P      Filter by priority: P0-P5 (repeatable; supports ranges e.g. P0-P2)
  --status STATUS   Filter by status: active, completed, deferred, all (default: active)
  --label LABEL     Filter by label tag in frontmatter (repeatable)
  --since DATE      Only issues discovered/updated on or after DATE (YYYY-MM-DD)
  --until DATE      Only issues discovered/updated on or before DATE (YYYY-MM-DD)
  --date-field      Which date field to filter on: discovered, updated (default: discovered)

Sorting:
  --sort FIELD      Sort by: priority (default), id, date, type, title
  --asc / --desc    Sort direction (default: asc for priority/id, desc for date)

Output:
  --json            Output as JSON array
  --format FORMAT   Output format: table (default), list, ids
  --limit N         Cap results at N (default: unlimited)
```

## Implementation Steps

1. Add `search.py` to `scripts/little_loops/cli/issues/` following the pattern of `list_cmd.py`
2. Register `search` subcommand in `scripts/little_loops/cli/issues/__init__.py`
3. Reuse issue-parsing logic from `list_cmd.py` / `issue_discovery/` to load issue metadata
4. Implement filter chain: text search → type → priority → status → label → date range
5. Implement sort: parse priority as numeric (P0=0), fall back to string comparison for others
6. Output modes: table (rich/plain), JSON, ids-only
7. Update `ll-issues` help text and docs

## Related

- FEAT-704: `--search` flag for `ll-issues list` (narrower scope — this supersedes or subsumes it)
- FEAT-703: `--type` filter for `ll-issues impact-effort` (could share filter parsing logic)

## Acceptance Criteria

- [ ] `ll-issues search` without arguments lists all active issues (same as `ll-issues list`)
- [ ] Text query matches issue title and body (case-insensitive substring)
- [ ] `--type`, `--priority`, `--status`, `--label`, `--since`, `--until` filters all work independently and in combination
- [ ] `--sort` and direction flags produce correctly ordered output
- [ ] `--json` outputs a valid JSON array with all relevant fields
- [ ] `--include-completed` (or `--status all`) searches completed issues too
- [ ] Existing `ll-issues list` behavior is unchanged

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T21:11:34Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3b3d882-e2fb-41a6-9b04-cfc872701991.jsonl`
