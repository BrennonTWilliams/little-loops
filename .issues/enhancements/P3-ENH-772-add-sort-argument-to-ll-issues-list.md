---
id: ENH-772
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# ENH-772: Add --sort Argument to ll-issues list

## Summary

`ll-issues list` has no sort control — issues always render grouped by type in filename order. Add a `--sort` argument (plus `--asc`/`--desc`) so users can order by date created, date completed, type, refinement depth, confidence score, and outcome confidence, matching what `ll-issues search` already supports (partially).

## Motivation

`ll-issues search` already supports `--sort priority|id|date|type|title` but `ll-issues list` offers none. As backlogs grow, users need to surface high-confidence ready issues, recently created issues, or issues by refinement depth without switching to search. Sorting is the most common ordering need and is currently missing from the primary listing command.

## Proposed Behavior

Add to `ll-issues list`:

```
--sort {priority,id,type,title,created,completed,confidence,outcome,refinement}
--asc     Sort ascending
--desc    Sort descending
```

| Key | Field | Source |
|---|---|---|
| `priority` | `IssueInfo.priority_int` | filename |
| `id` | numeric part of `issue_id` | filename |
| `type` | `BUG`/`FEAT`/`ENH` | filename |
| `title` | `IssueInfo.title` | header |
| `created` | `discovered_date` | frontmatter (parse on demand) |
| `completed` | completion date | `## Status` section (parse on demand, only relevant with `--status completed`) |
| `confidence` | `IssueInfo.confidence_score` | frontmatter (already parsed) |
| `outcome` | `IssueInfo.outcome_confidence` | frontmatter (already parsed) |
| `refinement` | count of refinement-related commands in session log | `IssueInfo.session_command_counts` |

Default sort when `--sort` is omitted: `priority` (existing behavior, no behavior change).
Default direction: ascending for most fields; descending for `created` and `completed` (newest first).

Also extend `ll-issues search --sort` choices with: `created`, `completed`, `confidence`, `outcome`, `refinement` (same logic, consolidating `date` → `created` alias).

## Integration Map

### Files to Modify

**`scripts/little_loops/cli/issues/__init__.py`** (lines 73–91)
- Add `--sort`, `--asc`, `--desc` arguments to the `list` subparser (currently missing)
- Extend `search` subparser `--sort` choices from `["priority", "id", "date", "type", "title"]` to include `["created", "completed", "confidence", "outcome", "refinement"]`

**`scripts/little_loops/cli/issues/list_cmd.py`** (`cmd_list`)
- After filtering, load dates/scores from frontmatter on demand (similar to `search.py` `need_content` pattern)
- Build enriched tuples `(IssueInfo, str, date|None, date|None)` with created + completed dates
- Call shared `_sort_issues()` before rendering
- Update JSON output to include `discovered_date`

**`scripts/little_loops/cli/issues/search.py`** (`_sort_issues`)
- Add new branches for `created` (alias for `date`), `completed`, `confidence`, `outcome`, `refinement`
- `completed`: import `_parse_completion_date` from `issue_history/parsing.py`
- `confidence`: `issue.confidence_score` (None → sentinel `9999`)
- `outcome`: `issue.outcome_confidence` (None → sentinel `9999`)
- `refinement`: sum counts for `/ll:verify-issues`, `/ll:refine-issue`, `/ll:tradeoff-review-issues`, `/ll:map-dependencies`, `/ll:ready-issue` from `issue.session_command_counts`

### Key Existing Code to Reuse
- `_parse_discovered_date(content)` — `search.py:17`
- `_parse_completion_date(content, file_path)` — `issue_history/parsing.py:~54`
- `_sort_issues()` — `search.py:103` (extend, don't duplicate)
- `IssueInfo.confidence_score`, `IssueInfo.outcome_confidence` — already populated by `IssueParser`
- `IssueInfo.session_command_counts` — already populated, used by `refine-status` command

## Implementation Steps

1. **Extend `_sort_issues()`** in `search.py` — add `created`/`completed`/`confidence`/`outcome`/`refinement` branches; update tuple signature to include completed date
2. **Update `__init__.py`** — add `--sort`/`--asc`/`--desc` to `list` parser; extend `search --sort` choices
3. **Update `list_cmd.py`** — load content on demand when sort key needs it; build enriched tuples; call `_sort_issues()`; update JSON output
4. **Update `search.py cmd_search`** — pass completed date in enriched tuples when needed
5. **Tests** — add cases in `scripts/tests/` for new sort keys on both `list` and `search`

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef26d0b4-df23-48b7-b46f-a500ba15fda8.jsonl`
