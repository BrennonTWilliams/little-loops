---
discovered_date: 2026-02-12
discovered_by: capture-issue
---

# ENH-387: Add --type flag to ll-parallel, ll-sprint, and ll-auto

## Summary

Add a `--type` flag to the CLI processing tools (`ll-auto`, `ll-parallel`, `ll-sprint`) that filters issues by type (BUG, FEAT, ENH). Currently the only way to filter is by specific issue IDs via `--only`, which requires knowing exact IDs upfront. A `--type` flag enables broader filtering like "process all bugs" without enumerating them.

## Current Behavior

The CLI tools support `--only` for filtering specific issue IDs (e.g., `--only BUG-001,FEAT-002`) and `--skip` for excluding specific IDs, but there is no way to filter by issue type. To process only bugs, a user must manually list every bug ID.

## Expected Behavior

A new `--type` flag accepts a comma-separated list of issue types:

```bash
ll-auto --type BUG              # process only bugs
ll-parallel --type BUG,ENH      # process bugs and enhancements
ll-sprint run my-sprint --type FEAT  # only features from sprint
```

The flag composes naturally with existing flags:
```bash
ll-auto --type BUG --skip BUG-003    # all bugs except BUG-003
ll-parallel --type ENH --max-issues 5  # first 5 enhancements
```

## Motivation

When running batch processing, users frequently want to target a specific issue type — e.g., "fix all bugs first" or "process enhancements only." Currently this requires manually collecting IDs with `--only`, which is tedious and error-prone. A `--type` flag makes the common case easy.

## Proposed Solution

1. Add `add_type_arg()` to `scripts/little_loops/cli_args.py`:
   ```python
   VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH"}

   def add_type_arg(parser: argparse.ArgumentParser) -> None:
       parser.add_argument(
           "--type",
           type=str,
           default=None,
           help="Comma-separated issue types to process (e.g., BUG,ENH)",
       )

   def parse_issue_types(value: str | None) -> set[str] | None:
       if value is None:
           return None
       types = {t.strip().upper() for t in value.split(",")}
       invalid = types - VALID_ISSUE_TYPES
       if invalid:
           raise argparse.ArgumentTypeError(f"Invalid issue types: {invalid}. Valid: {VALID_ISSUE_TYPES}")
       return types
   ```

2. Include `add_type_arg` in `add_common_auto_args()` and `add_common_parallel_args()`

3. Apply the type filter in issue discovery/collection logic — filter issue files by checking if the filename prefix matches a requested type before processing

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` - Add `add_type_arg()`, `parse_issue_types()`, update common arg bundles
- `scripts/little_loops/cli/auto.py` - Apply type filter during issue collection
- `scripts/little_loops/cli/parallel.py` - Apply type filter during issue collection
- `scripts/little_loops/cli/sprint.py` - Apply type filter during sprint issue processing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_discovery.py` or equivalent issue collection module - where type filtering should be applied

### Similar Patterns
- `--only` / `parse_issue_ids()` in `cli_args.py` - follows same pattern (comma-separated, uppercased, parsed to set)

### Tests
- `scripts/tests/test_cli_args.py` - Add tests for `parse_issue_types()` and `add_type_arg()`
- `scripts/tests/test_cli.py` - Integration tests for `--type` flag with each CLI tool

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `add_type_arg()` and `parse_issue_types()` to `cli_args.py`
2. Include in `add_common_auto_args()` and `add_common_parallel_args()`
3. Add type filtering to issue collection in `auto.py`, `parallel.py`, and `sprint.py`
4. Add unit tests for parsing and integration tests for filtering
5. Verify composability with `--only`, `--skip`, and `--max-issues`

## Scope Boundaries

- **In scope**: Adding `--type` flag to `ll-auto`, `ll-parallel`, `ll-sprint`; parsing and validation; filtering logic
- **Out of scope**: Adding `--skip-type` (can be added later if needed); changing `--only` behavior; UI/display changes

## Impact

- **Priority**: P3 - Quality-of-life improvement for batch processing workflows
- **Effort**: Small - Follows established `--only`/`--skip` pattern exactly
- **Risk**: Low - Additive flag, no existing behavior changes
- **Breaking Change**: No

## Blocked By

- ENH-352: batch git log calls in files_modified_since_commit (shared issue_discovery.py)
- BUG-403: dependency graph renders empty nodes without edges (shared sprint.py)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | CLI development conventions |
| architecture | docs/API.md | CLI module reference |

## Labels

`enhancement`, `cli`, `captured`

---

## Session Log
- `/ll:capture-issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8142cb6f-4f83-42f3-9389-72d5e0cf1e75.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
