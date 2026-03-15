---
discovered_commit: 1cc2673
discovered_branch: main
discovered_date: 2026-03-13T21:11:34Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# FEAT-728: Add `ll-issues search` subcommand with filters and sorting

## Summary

Add a dedicated `ll-issues search` subcommand that enables rich querying across all issue files — active and completed — with filters for status, type, priority, labels, and dates, plus configurable sort order. Provides a single ergonomic entry point for finding issues without manually scanning directories or grepping filenames.

## Current Behavior

`ll-issues list` shows only active issues. There is no search subcommand. Finding issues requires manually browsing `.issues/` directories or grepping filenames. There is no way to filter by date range, combine multiple filter criteria, sort by field, or include completed issues in a single command.

## Expected Behavior

`ll-issues search [QUERY] [OPTIONS]` subcommand is available with text search across titles and bodies, type/priority/status/label/date filters, configurable sort order, and JSON output. When called without arguments it lists all active issues (same as `ll-issues list`). With `--status all` or `--include-completed` it searches completed issues too.

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

## API/Interface

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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `search` subcommand

### New Files
- `scripts/little_loops/cli/issues/search.py` — search subcommand implementation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/list_cmd.py` — reuse or reference issue-parsing logic
- `scripts/little_loops/issue_discovery/` — reuse issue metadata loading utilities

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — direct template to follow for subcommand structure

### Tests
- `scripts/tests/test_issues_search.py` (new) — test filter chain, sort behavior, and JSON output

### Documentation
- `docs/reference/API.md` — add `ll-issues search` to CLI reference

### Configuration
- N/A

## Related

- FEAT-704: `--search` flag for `ll-issues list` (narrower scope — this supersedes or subsumes it)
- FEAT-703: `--type` filter for `ll-issues impact-effort` (could share filter parsing logic)

## Acceptance Criteria

- [x] `ll-issues search` without arguments lists all active issues (same as `ll-issues list`)
- [x] Text query matches issue title and body (case-insensitive substring)
- [x] `--type`, `--priority`, `--status`, `--label`, `--since`, `--until` filters all work independently and in combination
- [x] `--sort` and direction flags produce correctly ordered output
- [x] `--json` outputs a valid JSON array with all relevant fields
- [x] `--include-completed` (or `--status all`) searches completed issues too
- [x] Existing `ll-issues list` behavior is unchanged

## Impact

- **Priority**: P3 - Ergonomic improvement for issue management; useful but not blocking any workflows
- **Effort**: Medium - New subcommand following `list_cmd.py` pattern; requires filter chain, sort logic, and multiple output modes
- **Risk**: Low - Purely additive subcommand; existing `ll-issues list` behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`, `search`, `captured`

---

**Completed** | Created: 2026-03-13 | Closed: 2026-03-14 | Priority: P3

## Resolution

Implemented `ll-issues search` as a new subcommand in `scripts/little_loops/cli/issues/search.py` following the `list_cmd.py` pattern.

- New file: `scripts/little_loops/cli/issues/search.py` — filter chain (text, type, priority, status, label, date), sort logic, three output modes (table, list, ids), plus `--json`
- Updated: `scripts/little_loops/cli/issues/__init__.py` — registered `search` (alias `sr`) subcommand
- New tests: `scripts/tests/test_issues_search.py` — 28 tests covering all filters, sorts, and output formats
- Updated: `docs/reference/API.md` — added `search` to the `ll-issues` sub-commands table with full option reference

## Verification Notes

- **Verified**: No `ll-issues search` subcommand registered in `scripts/little_loops/cli/issues/__init__.py` — feature is genuinely missing.
- **Verified**: `ll-issues list` has no `--include-completed`, `--status`, `--since`, `--until`, or `--sort` flags — confirms the gap.
- **Update**: `scripts/little_loops/issue_discovery/search.py` already exists with directly reusable functions:
  - `_get_all_issue_files(config, include_completed, include_deferred)` — loads all issue paths with status
  - `search_issues_by_content(config, search_terms, include_completed)` — content search with relevance scoring
  - Implementation Step 3 should reference these instead of "reuse issue-parsing logic from `list_cmd.py` / `issue_discovery/`"

## Session Log
- `/ll:manage-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-03-15T00:24:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e9fb4fb-f33a-414f-a38a-7ab5c2d50836.jsonl`
- `/ll:capture-issue` - 2026-03-13T21:11:34Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3b3d882-e2fb-41a6-9b04-cfc872701991.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de0aec6f-4d8a-4d72-9519-a12883d491ba.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de0aec6f-4d8a-4d72-9519-a12883d491ba.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
