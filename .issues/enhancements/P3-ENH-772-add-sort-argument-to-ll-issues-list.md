---
id: ENH-772
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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

**`scripts/little_loops/cli/issues/__init__.py`** (lines 72–93)
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
- `_parse_discovered_date(content)` — `search.py:17-30` (takes raw file content, regex-parses frontmatter)
- `_parse_completion_date(content, file_path)` — `issue_history/parsing.py:80-103` (not `~54`; returns `None` only on OSError)
- `_sort_issues(items, sort_field, descending)` — `search.py:103-128` (extend, don't duplicate)
  - Current signature: `list[tuple[IssueInfo, str, date | None]]` → `list[tuple[IssueInfo, str, date | None]]`
  - Adding `completed` key requires expanding to a 4-tuple: `(IssueInfo, str, date | None, date | None)` (disc_date, completed_date)
- `IssueInfo.confidence_score`, `IssueInfo.outcome_confidence` — `issue_parser.py:233-234`, already populated by `IssueParser`
- `IssueInfo.session_command_counts` — `issue_parser.py:236`, `dict[str, int]`, populated via `count_session_commands(content)`
- `need_content` flag pattern — `search.py:172`; set `True` when sort key requires file content reads

### Grouped Rendering Caveat (Critical)
`cmd_list` in non-flat mode re-buckets issues into `{"BUG": [], "FEAT": [], "ENH": []}` at `list_cmd.py:78-82` before rendering. This means sort keys other than `type` will only have visible effect with `--flat` output. Two implementation options:
1. **Simplest**: Apply sort within each type bucket (sort happens before the re-bucket, output is sorted within each group)
2. **Alternative**: Document that `--sort` is only meaningful with `--flat` in list mode

Option 1 is recommended for consistency with user expectations.

## Implementation Steps

1. **Extend `_sort_issues()` in `search.py:103`** — expand tuple to 4-tuple `(IssueInfo, str, date|None, date|None)`, add branches for `created` (alias `date`), `completed`, `confidence` (sentinel `9999`), `outcome` (sentinel `9999`), `refinement` (sum of refinement command counts); update `key()` unpacking from `issue, _status, disc_date = item` to include `comp_date`
2. **Update `__init__.py:72-92`** (list parser) — add `--sort choices=[...]`, `--asc`, `--desc` mirroring search parser at lines `147-153`; extend `search --sort` choices at line `147` with new keys
3. **Update `list_cmd.py`** — after filter comprehension, set `need_content = sort_key in {"created", "completed", "confidence", "outcome", "refinement"}`; load content on demand; build 4-tuple enriched list; call `_sort_issues()`; update JSON output to include `discovered_date`
4. **Update `cmd_search` in `search.py`** — expand enriched tuples from 3-tuple to 4-tuple, populating `comp_date` when `sort_field == "completed"` via `_parse_completion_date()` from `issue_history/parsing.py:80`; update default-descending logic to include `"created"` alongside existing `"date"` check
5. **Tests** — add `TestListSorting` class in `scripts/tests/test_issues_cli.py` following `TestSearchSorting` pattern at `test_issues_search.py:534-619`; use `--flat --sort <key> --format ids` (or check output order); extend `search_issues_dir` fixture or create `list_sort_issues_dir` with frontmatter fields `confidence_score`, `outcome_confidence`, session log entries; use `lines.index("ID-NNN") < lines.index("ID-NNN")` assertion idiom

## Resolution

**Completed**: 2026-03-16

Implemented `--sort`, `--asc`, and `--desc` arguments for `ll-issues list`. Extended `_sort_issues()` in `search.py` to a 4-tuple with `comp_date` and added branches for `created`, `completed`, `confidence`, `outcome`, and `refinement` sort keys. Updated `cmd_search` to resolve `sort_field` early and populate `comp_date` for `completed` sort. Extended `search --sort` choices with all new keys. Added `TestListSorting` with 4 tests.

## Session Log
- `/ll:manage-issue` - 2026-03-16T00:00:00Z - current session
- `/ll:ready-issue` - 2026-03-16T17:45:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/215bd8fd-d4ba-434a-81e8-f9dcc6feb4a9.jsonl`
- `/ll:verify-issues` - 2026-03-16T17:27:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:refine-issue` - 2026-03-16T17:21:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04f3d100-af21-43e6-8a78-b678385890bf.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef26d0b4-df23-48b7-b46f-a500ba15fda8.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9a440ea-dc3a-4df6-95fd-943f0b4536ac.jsonl`
