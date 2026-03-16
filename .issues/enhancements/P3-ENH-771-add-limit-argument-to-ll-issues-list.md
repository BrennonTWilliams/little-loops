---
id: ENH-771
title: "Add --limit argument to ll-issues list"
type: ENH
priority: P3
status: backlog
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 93
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — add `--limit`/`-n` argument to the `list` subparser (alongside existing `--type`, `--priority`, `--status`, `--flat`, `--json` args at lines 74–91)
- `scripts/little_loops/cli/issues/list_cmd.py` — apply the limit slice after filtering (lines 36–41) and before output mode dispatch (line 47)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — re-exports `main_issues`; no changes needed
- `scripts/little_loops/cli/issues/search.py:56` — `_load_issues_with_status()` used by `cmd_list`; no changes needed

### Similar Patterns
- `scripts/little_loops/cli/issues/__init__.py:161` — `search --limit` argparse registration: `sr.add_argument("--limit", type=int, metavar="N", help="Cap results at N")`
- `scripts/little_loops/cli/issues/search.py:242-245` — limit guard + slice: `if limit and limit > 0: enriched = enriched[:limit]`
- `scripts/little_loops/cli/messages.py:45-51` — `-n`/`--limit` short alias with `is not None` guard (closest match since this issue also requires `-n`)
- `scripts/little_loops/cli/issues/sequence.py:41-74` — `args.limit` + overflow hint pattern (useful reference if we want to add a "+ N more" hint)

### Tests
- `scripts/tests/test_issues_cli.py` — primary test file; add `--limit` test cases inside `TestListSubcommand` class (see `test_sequence_limit` at line 363 and `test_issues_search.py:718-745` for style reference)
- `scripts/tests/conftest.py:124-157` — `issues_dir` and `sample_config` fixtures used by all `TestListSubcommand` tests

### Documentation
- `docs/reference/CLI.md` — already mentions `--limit` as a planned flag at lines 412 and 421; update to mark it as implemented

## Implementation Steps

1. **Register argument** (`scripts/little_loops/cli/issues/__init__.py`, in the `list` subparser block at ~line 86): add `ls.add_argument("--limit", "-n", type=int, metavar="N", default=None, help="Cap output at N issues (must be ≥ 1)")`. Place after the existing `--flat` argument following the same style as `search --limit` at line 161.

2. **Validate at parse time** (`list_cmd.py:cmd_list`, early in function): read `limit = getattr(args, "limit", None)` then validate:
   ```python
   if limit is not None and limit < 1:
       print(f"Error: --limit must be a positive integer, got {limit}", file=sys.stderr)
       return 1
   ```
   The acceptance criteria requires a clear error for `--limit 0` or negative — the existing `search` pattern silently ignores these, so use an explicit error check instead.

3. **Apply slice** (`list_cmd.py`, after the filtering list comprehension at lines 36–41, before the empty check at line 43): add `if limit: issues_with_status = issues_with_status[:limit]`. Applied after filtering, so it caps the top N by current filesystem-sorted order (alphabetical by filename). Note: if ENH-772 (`--sort`) lands first, apply the slice after the sort step.

4. **Update help text**: the `help=` string added in step 1 is sufficient. `docs/reference/CLI.md` lines 412/421 mention `--limit` as planned — update those to show the actual flag syntax.

5. **Add tests** in `scripts/tests/test_issues_cli.py` inside `TestListSubcommand`, following the pattern at line 718 (`test_issues_search.py`):
   - `test_limit_caps_output`: `["ll-issues", "list", "--limit", "2", ...]` → assert `len(lines) == 2`
   - `test_limit_short_flag`: `["ll-issues", "list", "-n", "2", ...]` → same assertion
   - `test_limit_zero_raises_error`: `["ll-issues", "list", "--limit", "0", ...]` → assert `result == 1` and stderr contains "Error"
   - `test_limit_negative_raises_error`: `["ll-issues", "list", "--limit", "-1", ...]` → assert `result == 1`
   - `test_limit_omitted_returns_all`: no `--limit` → assert all fixture issues returned

## Acceptance Criteria

- `ll-issues list --limit 5` returns at most 5 issues
- `ll-issues list -n 5` works as a short alias
- Omitting the flag returns all issues (unchanged behavior)
- Passing `--limit 0` or a negative value raises a clear error
- `--help` documents the new flag

## Related

- ENH-752: Add `--status` flag to `ll-issues list` (same subcommand)

## Session Log
- `/ll:verify-issues` - 2026-03-16T17:27:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8de8f7f-036d-410c-b49a-697d879afa38.jsonl`
- `/ll:refine-issue` - 2026-03-16T17:20:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef6f9fdc-6be2-4332-a31a-ac306dde4386.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - captured from user description
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef6f9fdc-6be2-4332-a31a-ac306dde4386.jsonl`
