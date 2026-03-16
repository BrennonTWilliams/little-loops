---
id: ENH-771
title: "Add --limit argument to ll-issues list"
type: ENH
priority: P3
status: backlog
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# ENH-771: Add --limit argument to ll-issues list

## Summary

Add an optional `--limit` (or `-n`) integer argument to the `ll-issues list` subcommand that caps the number of issues returned. Useful for quick overviews and script pipelines.

## Motivation

`ll-issues list` returns all matching issues. When a backlog is large, users often only want the top N issues (e.g., top 5 by priority). Without a limit flag, users must pipe to `head`, which is less ergonomic and doesn't compose cleanly with other flags.

## Proposed Change

```
ll-issues list [--limit N] [other flags]
```

- `--limit N` / `-n N`: Return at most N issues (integer, must be ≥ 1)
- Applied after sorting/filtering, so it returns the top N by the active sort order
- No change to default behavior when flag is omitted

## Implementation Steps

1. Locate the `list` subcommand definition in `scripts/little_loops/cli/issues/`
2. Add `--limit` / `-n` argument via `argparse` (type=int, default=None)
3. Slice the results list to `[:limit]` after filtering and sorting
4. Update `--help` text for the subcommand

## Acceptance Criteria

- `ll-issues list --limit 5` returns at most 5 issues
- `ll-issues list -n 5` works as a short alias
- Omitting the flag returns all issues (unchanged behavior)
- Passing `--limit 0` or a negative value raises a clear error
- `--help` documents the new flag

## Related

- ENH-752: Add `--status` flag to `ll-issues list` (same subcommand)

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - captured from user description
