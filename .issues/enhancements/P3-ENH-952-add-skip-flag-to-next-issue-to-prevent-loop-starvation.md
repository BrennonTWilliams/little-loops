---
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# ENH-952: Add `--skip` flag to `ll-issues next-issue` to prevent loop starvation

## Summary

`ll-issues next-issue` always returns the highest-ranked issue by outcome confidence and readiness, with no mechanism to skip issues that have already failed. When the top-ranked issue's sub-loop fails repeatedly (e.g., in `auto-issue-processor`), all lower-ranked issues are never processed. Adding a `--skip` flag and skip-list tracking in the parent loop prevents this starvation. This is the `next-issue` counterpart to completed ENH-929 (which added `--skip` to `next-action`).

## Current Behavior

`ll-issues next-issue` always returns the top-ranked issue by `(outcome_confidence, confidence_score, priority)`. There is no mechanism to exclude specific issues from consideration. When the top-ranked issue fails repeatedly in the `auto-issue-processor` loop, the loop continues selecting the same issue on every iteration, permanently blocking all lower-ranked issues from being processed.

## Expected Behavior

`ll-issues next-issue --skip FEAT-007,FEAT-123` excludes the specified issue IDs and returns the next eligible issue. The `auto-issue-processor` loop tracks failed issues in an ephemeral skip list and passes it to each `next-issue` call, ensuring lower-ranked issues are not starved by a single perpetually-failing issue.

## Motivation

The `auto-issue-processor` loop is designed to refine issues sequentially. Issue starvation defeats its purpose: one perpetually failing issue prevents all lower-ranked issues from being touched. The `find_issues()` function already has the `skip_ids` parameter and `add_skip_arg()` helper already exists — this enhancement just surfaces it through the `next-issue` subcommand CLI. The `next-action` subcommand already has `--skip` (ENH-929); this closes the parity gap.

## Proposed Solution

Two small changes:

1. **`scripts/little_loops/cli/issues/__init__.py`** — Add `add_skip_arg(nx)` to the `next-issue` subparser (line ~353, directly after the `--path` arg, matching the pattern on line 342 for `next-action`).

2. **`scripts/little_loops/cli/issues/next_issue.py`** — Wire `skip_ids` through to `find_issues()`:

```python
from little_loops.cli_args import parse_issue_ids

skip_ids = parse_issue_ids(getattr(args, "skip", None))
issues = find_issues(config, skip_ids=skip_ids)
```

No changes to `find_issues()` or `parse_issue_ids()` — both already handle this correctly.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/__init__.py` — Add `add_skip_arg(nx)` to `next-issue` subparser
- `scripts/little_loops/cli/issues/next_issue.py` — Pass `skip_ids` to `find_issues()`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_parser.py:612` — `find_issues()` already accepts `skip_ids: set[str] | None`
- `scripts/little_loops/cli_args.py:57` — `add_skip_arg()` already exists
- `scripts/little_loops/cli_args.py:197` — `parse_issue_ids()` already exists

### Similar Patterns

- `scripts/little_loops/cli/issues/__init__.py:342` — `add_skip_arg(na)` for `next-action` (exact pattern to copy)
- `scripts/little_loops/cli/issues/next_action.py` — reference impl for wiring `skip_ids`
- Completed ENH-929 — identical change for `next-action`

### Tests

- `scripts/tests/cli/issues/` — add test for `next-issue --skip FEAT-NNN` verifying the skipped issue is excluded

### Documentation

- N/A

### Configuration

- N/A

## Implementation Steps

1. Add `add_skip_arg(nx)` to `next-issue` subparser in `__init__.py`
2. Wire `parse_issue_ids` + `find_issues(config, skip_ids=skip_ids)` in `next_issue.py`
3. Add a unit test: `next-issue --skip <top-issue-id>` returns the second-ranked issue
4. Verify `next-issue` (no `--skip`) is unchanged

## Impact

- **Priority**: P3 — Needed to fix loop starvation in `auto-issue-processor` but no users are currently blocked
- **Effort**: Small — Two files, ~4 lines of code total; all infrastructure already exists
- **Risk**: Low — `find_issues` and `parse_issue_ids` already tested; adding a pass-through flag
- **Breaking Change**: No

## API/Interface

```python
# Before
ll-issues next-issue
ll-issues next-issue --json
ll-issues next-issue --path

# After (new flag)
ll-issues next-issue --skip FEAT-007
ll-issues next-issue --skip FEAT-007,FEAT-123
ll-issues next-issue --skip FEAT-007 --json
```

## Labels

`cli`, `issues`, `enhancement`, `captured`

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4692f047-3b49-42de-a84b-22a59c6686a8.jsonl`
