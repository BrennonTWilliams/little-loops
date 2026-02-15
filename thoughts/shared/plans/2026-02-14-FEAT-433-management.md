# FEAT-433: Sprint Conflict Analysis CLI (ll-sprint analyze)

## Plan

### Phase 1: Add `analyze` subcommand to sprint CLI

**File**: `scripts/little_loops/cli/sprint.py`

1. Add `analyze` subparser (after `delete` subparser, ~line 159):
   - Positional arg: `sprint` (sprint name)
   - `--config` via `add_config_arg()`
   - `--format` with choices `["text", "json"]` default `"text"` (for CI/programmatic use)
   - `--skip-analysis` via `add_skip_analysis_arg()` (skip dep discovery, only show overlap)

2. Add routing in dispatch block (~line 186):
   - `if args.command == "analyze": return _cmd_sprint_analyze(args, manager)`

3. Update epilog examples to include `analyze` subcommand

### Phase 2: Implement `_cmd_sprint_analyze()` handler

**File**: `scripts/little_loops/cli/sprint.py`

Core logic (reuses existing infrastructure from `_cmd_sprint_show` and `_cmd_sprint_run`):

1. Load sprint, validate issues, load IssueInfo objects
2. Gather `all_known_ids` via `gather_all_issue_ids()`
3. Build `DependencyGraph.from_issues()`
4. Check for cycles → report and return 1
5. Call `get_execution_waves()` then `refine_waves_for_contention()`
6. Build conflict report:
   - Issue pairs with overlapping files (from FileHints pairwise comparison)
   - Recommended serialization order (from wave/sub-wave structure)
   - Parallel-safe groups (issues in same wave with no conflicts)
7. Output report in text or JSON format
8. Return exit code: 0 if no conflicts, 1 if conflicts found

### Phase 3: Format the conflict report

**Text output structure**:
```
Sprint: <name>
Issues: <count>

CONFLICT ANALYSIS
======================================================================

Conflicts Found: N pair(s)

  1. BUG-001 <-> FEAT-010
     Overlapping files: scripts/config.py, scripts/utils.py
     Recommendation: Serialize (wave ordering handles this)

  2. ENH-020 <-> FEAT-030
     Overlapping files: scripts/api/
     Recommendation: Serialize

Execution Plan:
  Wave 1 (parallel): BUG-001, ENH-050
  Wave 2 (serialized — file overlap): FEAT-010, then ENH-020
  Wave 3 (after Wave 2): FEAT-030

Parallel-Safe Groups:
  - BUG-001, ENH-050 (no shared files)
```

**JSON output**: Structured dict with `conflicts`, `waves`, `parallel_safe` keys.

### Phase 4: Add tests

**File**: `scripts/tests/test_sprint.py`

1. `TestSprintAnalyze` class with:
   - `_setup_analyze_project()` — creates issues with known file overlaps
   - `test_analyze_no_conflicts()` — sprint with non-overlapping issues → exit 0
   - `test_analyze_with_conflicts()` — sprint with overlapping issues → exit 1
   - `test_analyze_sprint_not_found()` → exit 1
   - `test_analyze_json_format()` — verify JSON output structure
   - `test_analyze_with_dependencies()` — issues with blocked_by relationships

### Success Criteria

- [x] `analyze` subparser registered
- [ ] `_cmd_sprint_analyze()` implemented
- [ ] Text report format working
- [ ] JSON report format working
- [ ] Exit code 0 for no conflicts, 1 for conflicts
- [ ] Tests passing
- [ ] Lint/type checks passing
