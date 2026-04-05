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

- `scripts/little_loops/issue_parser.py:612` — `find_issues(config, category=None, skip_ids: set[str] | None = None, ...)` confirmed
- `scripts/little_loops/cli_args.py:57` — `add_skip_arg(parser, help_text=None)` confirmed
- `scripts/little_loops/cli_args.py:197` — `parse_issue_ids(value) -> set[str] | None` confirmed
- `scripts/little_loops/cli/issues/__init__.py:29` — `add_skip_arg` already imported (`from little_loops.cli_args import add_config_arg, add_skip_arg`) — no import change needed

### Similar Patterns

- `scripts/little_loops/cli/issues/__init__.py:342` — `add_skip_arg(na)` for `next-action`; insertion point for `next-issue` is line 353 (before `add_config_arg(nx)`, after `--path` arg)
- `scripts/little_loops/cli/issues/next_action.py:25-29` — exact wiring to replicate:
  ```python
  from little_loops.cli_args import parse_issue_ids
  from little_loops.issue_parser import find_issues, is_formatted
  skip_ids = parse_issue_ids(getattr(args, "skip", None))
  issues = find_issues(config, skip_ids=skip_ids or None)
  ```
- Completed ENH-929 — identical change for `next-action`

### Tests

- `scripts/tests/test_next_issue.py` — add `TestNextIssueSkipFlag` class following existing `TestNextIssueSorting` pattern; helpers `_make_issue`, `_setup_dirs`, `_write_config` already present

### Documentation

- `docs/reference/CLI.md` — update `next-issue` entry to document `--skip / -s` flag

### Loop Callers (context only — no changes needed)

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — calls `ll-issues next-issue`; parent loop would pass `--skip` to prevent starvation
- `scripts/little_loops/loops/prompt-across-issues.yaml` — also references `next-issue`

### Configuration

- N/A

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py:353` — add `add_skip_arg(nx)` before `add_config_arg(nx)` (mirrors the `add_skip_arg(na)` call at line 342 for `next-action`; `add_skip_arg` is already imported at line 29)
2. In `scripts/little_loops/cli/issues/next_issue.py` — add `from little_loops.cli_args import parse_issue_ids` import and replace `issues = find_issues(config)` (line 27) with:
   ```python
   skip_ids = parse_issue_ids(getattr(args, "skip", None))
   issues = find_issues(config, skip_ids=skip_ids or None)
   ```
3. In `scripts/tests/test_next_issue.py` — add `TestNextIssueSkipFlag` class modeled after `TestIssuesCLINextActionSkip` in `test_next_action.py:310-401` with three tests:
   - `test_skip_excludes_top_issue`: two issues, skip the higher-ranked one, assert lower-ranked is returned (exit 0)
   - `test_skip_only_issue_returns_exit_1`: skip the only issue, assert exit code 1 (no issues)
   - `test_skip_multiple_ids`: comma-separated skip list, assert all named IDs excluded
4. In `docs/reference/CLI.md` — update `next-issue` entry to document `--skip / -s`
5. Run `python -m pytest scripts/tests/test_next_issue.py -v` to verify all tests pass

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

## Resolution

**Completed** | Resolved: 2026-04-04 | Priority: P3

### Changes Made

1. `scripts/little_loops/cli/issues/__init__.py` — Added `add_skip_arg(nx)` before `add_config_arg(nx)` on the `next-issue` subparser (line 353)
2. `scripts/little_loops/cli/issues/next_issue.py` — Added `parse_issue_ids` import and wired `skip_ids` through to `find_issues(config, skip_ids=skip_ids or None)`
3. `scripts/tests/test_next_issue.py` — Added `TestNextIssueSkipFlag` class with three tests: skip top issue, skip only issue (exit 1), skip multiple comma-separated IDs
4. `docs/reference/CLI.md` — Documented `--skip / -s` flag in the `next-issue` flag table and added example to the examples block

All 13 tests pass. No infrastructure changes needed — `find_issues()`, `parse_issue_ids()`, and the `add_skip_arg` import were already in place.

## Status

**Completed** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-04-05T00:14:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72c02981-19e5-401b-b374-7664d84df03b.jsonl`
- `/ll:refine-issue` - 2026-04-05T00:09:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae04c79e-46f8-4ca0-b76b-64b7b646d0fc.jsonl`

- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4692f047-3b49-42de-a84b-22a59c6686a8.jsonl`
