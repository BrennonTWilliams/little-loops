# ENH-391: Add Sprint-Scoping to map-dependencies / ll-deps - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-391-add-sprint-scoping-to-map-dependencies.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

`ll-deps` CLI (`dependency_mapper.py:main()` at line 943) has two subcommands (`analyze` and `validate`), both of which call `_load_issues()` at line 1015, which calls `find_issues(config)` with no filtering. There is no sprint awareness anywhere in `dependency_mapper.py`.

### Key Discoveries
- `find_issues()` already has an `only_ids: set[str] | None` parameter (`issue_parser.py:473`) that filters issues by ID set
- `Sprint.load(sprints_dir, name)` (`sprint.py:184-200`) loads a sprint YAML and returns a `Sprint` with `.issues: list[str]`
- `_load_issues()` (`dependency_mapper.py:902`) internally creates a `BRConfig` — the sprint loading also needs `BRConfig` to resolve `sprints_dir`
- The validate subparser is currently anonymous (not assigned to a variable, line 998)

## Desired End State

Both `analyze` and `validate` subcommands accept `--sprint <name>` to restrict analysis to only the issues in that sprint. The `--sprint` flag is optional — when omitted, behavior is unchanged (all active issues).

### How to Verify
- `ll-deps analyze --sprint bug-fixes` only analyzes issues listed in `.sprints/bug-fixes.yaml`
- `ll-deps validate --sprint bug-fixes` only validates those issues
- `ll-deps analyze` (without `--sprint`) works as before
- Non-existent sprint name prints error and returns exit code 1
- Tests pass for all new and existing scenarios

## What We're NOT Doing

- Not changing analysis logic in `analyze_dependencies()` or `validate_dependencies()`
- Not adding sprint awareness to other `ll-deps` features beyond `analyze`/`validate`
- Not auto-running dependency analysis during `ll-sprint run` (separate concern)
- Not adding `--sprint` to the top-level parser (it belongs on subcommands)

## Solution Approach

1. Add `--sprint` argument to both subparsers
2. After argument parsing, if `--sprint` is set, load the sprint YAML via `Sprint.load()` to get issue IDs
3. Pass `only_ids` into `_load_issues()` (new parameter) which forwards it to `find_issues()`
4. Update skill documentation

## Code Reuse & Integration

- **Reuse as-is**: `Sprint.load(sprints_dir, name)` from `sprint.py:184` — direct call
- **Reuse as-is**: `find_issues(config, only_ids=...)` from `issue_parser.py:469` — already supports the filter
- **Pattern to follow**: `_cmd_sprint_run()` in `cli/sprint.py:533` loads sprint and handles not-found error
- **New code**: Only ~20 lines of glue in `main()` and a small signature change to `_load_issues()`

## Implementation Phases

### Phase 1: Add --sprint argument and filtering logic

#### Overview
Add the `--sprint` flag to both subparsers, load sprint YAML when provided, and pass filtered IDs through `_load_issues()`.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py`

1. Add `--sprint` argument to both `analyze_parser` and the validate subparser (assign validate parser to a variable)
2. Add sprint loading logic between argument parsing (line 1003) and `_load_issues()` call (line 1015)
3. Modify `_load_issues()` to accept an optional `only_ids` parameter and forward it to `find_issues()`

```python
# 1. Add --sprint to both subparsers (after existing args)
analyze_parser.add_argument(
    "--sprint",
    type=str,
    default=None,
    help="Restrict analysis to issues in the named sprint",
)

validate_parser = subparsers.add_parser(
    "validate",
    help="Validate existing dependency references only",
)
validate_parser.add_argument(
    "--sprint",
    type=str,
    default=None,
    help="Restrict validation to issues in the named sprint",
)

# 2. Sprint loading logic (after issues_dir resolution, before _load_issues)
only_ids: set[str] | None = None
if getattr(args, "sprint", None):
    from little_loops.config import BRConfig as _BRConfig
    from little_loops.sprint import Sprint

    project_root = issues_dir.resolve().parent
    if issues_dir.name != ".issues":
        project_root = issues_dir.parent
    _config = _BRConfig(project_root)
    sprints_dir = Path(_config.sprints.sprints_dir)
    if not sprints_dir.is_absolute():
        sprints_dir = project_root / sprints_dir

    sprint = Sprint.load(sprints_dir, args.sprint)
    if sprint is None:
        print(f"Error: Sprint not found: {args.sprint}", file=sys.stderr)
        return 1
    only_ids = set(sprint.issues)
    if not only_ids:
        print(f"Sprint '{args.sprint}' has no issues.")
        return 0

# 3. Pass only_ids to _load_issues
issues, issue_contents, completed_ids = _load_issues(issues_dir, only_ids=only_ids)
```

```python
# Modified _load_issues signature
def _load_issues(
    issues_dir: Path,
    only_ids: set[str] | None = None,
) -> tuple[list[IssueInfo], dict[str, str], set[str]]:
    # ... existing code ...
    issues = find_issues(config, only_ids=only_ids)
    # ... rest unchanged ...
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 2: Add tests

#### Overview
Add tests for the new `--sprint` flag in `test_dependency_mapper.py`.

#### Changes Required

**File**: `scripts/tests/test_dependency_mapper.py`

Add tests to `TestMainCLI`:
1. `test_analyze_with_sprint` — sprint filters to specific issues
2. `test_validate_with_sprint` — sprint filters validation
3. `test_sprint_not_found` — non-existent sprint returns error
4. `test_sprint_empty_issues` — sprint with no issues returns 0
5. `test_analyze_without_sprint_unchanged` — existing behavior preserved

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v -k sprint`
- [ ] All existing tests still pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`

---

### Phase 3: Update skill documentation

#### Overview
Update `skills/map-dependencies/SKILL.md` to document the `--sprint` flag.

#### Changes Required

**File**: `skills/map-dependencies/SKILL.md`

Add sprint-scoped usage examples and update the examples table.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Full test suite: `python -m pytest scripts/tests/ -v`

## Testing Strategy

### Unit Tests
- Sprint loading + ID extraction via `Sprint.load()`
- `_load_issues()` with `only_ids` parameter
- CLI argument parsing with `--sprint` flag

### Integration Tests (via CLI)
- Full `main()` call with `--sprint` flag and tmp_path sprint YAML
- Verify only sprint issues appear in output
- Error handling for missing sprint

## References

- Issue: `.issues/enhancements/P3-ENH-391-add-sprint-scoping-to-map-dependencies.md`
- `dependency_mapper.py:943-1117` — `main()` entry point
- `dependency_mapper.py:902-940` — `_load_issues()`
- `issue_parser.py:469-521` — `find_issues()` with `only_ids`
- `sprint.py:184-200` — `Sprint.load()`
- `sprint.py:292-307` — `SprintsConfig`
