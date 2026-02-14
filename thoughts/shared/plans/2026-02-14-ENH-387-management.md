# ENH-387: Add --type flag to CLI processing tools

## Plan

### Overview
Add a `--type` flag to `ll-auto`, `ll-parallel`, and `ll-sprint` that filters issues by type prefix (BUG, FEAT, ENH). This follows the exact same pattern as `--only`/`--skip`.

### Key Insight
The `IssueInfo.issue_id` field contains the type prefix (e.g., "BUG-001", "ENH-387"). So type filtering can be applied post-collection by checking if an issue's ID starts with a requested type prefix. This is simpler than mapping through categories.

However, for proper validation we should use the config's `IssuesConfig.get_prefixes()` method (config.py:159-164) which returns configured prefixes like `['BUG', 'FEAT', 'ENH']`.

### Approach: Filter in `find_issues()`

Add a `type_prefixes` parameter to `find_issues()` (issue_parser.py:469) alongside `skip_ids` and `only_ids`. This centralizes the filtering and benefits all callers (auto, parallel, sprint).

### Changes

#### 1. `scripts/little_loops/cli_args.py`
- Add `VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH"}`
- Add `add_type_arg(parser)` — adds `--type` argument (str, default None)
- Add `parse_issue_types(value)` — validates and parses comma-separated types to `set[str] | None`
- Add `add_type_arg` call to `add_common_auto_args()` and `add_common_parallel_args()`
- Update docstrings for both bundle functions
- Update `__all__`

#### 2. `scripts/little_loops/issue_parser.py`
- Add `type_prefixes: set[str] | None = None` parameter to `find_issues()`
- Add filter: `if type_prefixes is not None and not any(info.issue_id.startswith(t + "-") for t in type_prefixes): continue`
- Apply after skip/only filters

#### 3. `scripts/little_loops/cli/auto.py`
- Import `parse_issue_types`
- Parse `args.type` with `parse_issue_types()`
- Pass `type_prefixes` to `AutoManager` constructor
- Update epilog examples

#### 4. `scripts/little_loops/issue_manager.py`
- Add `type_prefixes: set[str] | None = None` to `AutoManager.__init__()`
- Pass to `find_issues()` in dependency graph build
- Apply in `_get_next_issue()` candidate filtering

#### 5. `scripts/little_loops/cli/parallel.py`
- Import `parse_issue_types`
- Parse `args.type` with `parse_issue_types()`
- Pass to `parallel_config` (need to add to ParallelConfig)
- Update epilog examples

#### 6. `scripts/little_loops/parallel/types.py`
- Add `type_prefixes: set[str] | None = None` to `ParallelConfig`

#### 7. `scripts/little_loops/config.py`
- Add `type_prefixes` parameter to `create_parallel_config()`

#### 8. `scripts/little_loops/parallel/orchestrator.py`
- Pass `type_prefixes` through to `IssuePriorityQueue.scan_issues()`

#### 9. `scripts/little_loops/parallel/priority_queue.py`
- Pass `type_prefixes` through to `find_issues()`

#### 10. `scripts/little_loops/cli/sprint.py`
- Add `add_type_arg` to `run` and `create` subparsers
- Parse `args.type` and apply type filter to issues list

#### 11. Tests
- `test_cli_args.py`: Tests for `parse_issue_types()` and updated bundle tests
- `test_cli_args.py`: Test `add_type_arg()` function

### Success Criteria
- [x] `parse_issue_types()` validates and parses types correctly
- [ ] `--type BUG` filters to only bugs in all three tools
- [ ] `--type BUG,ENH` filters to bugs and enhancements
- [ ] `--type` composes with `--only`, `--skip`, `--max-issues`
- [ ] Invalid types produce clear error message
- [ ] All existing tests pass
- [ ] New tests cover parse_issue_types and type filtering
