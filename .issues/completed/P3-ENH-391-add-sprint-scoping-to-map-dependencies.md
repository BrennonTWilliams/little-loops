---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-391: Add sprint-scoping option to map-dependencies / ll-deps

## Summary

Add a `--sprint` flag to `ll-deps` (and the `/ll:map-dependencies` skill) that restricts dependency analysis to only the issues included in a named sprint. Currently `ll-deps analyze` always operates on all active issues, with no way to scope analysis to a specific sprint's issue set.

## Current Behavior

`ll-deps analyze` scans all active issues in the issues directory. The only scoping mechanism is `-d` to change the issues directory path. There is no integration with the sprint system — users cannot run dependency analysis for just the issues in a specific sprint.

The original FEAT-261 spec mentioned `/ll:map_dependencies --sprint sprint-name` as a planned capability (line 43), but this was not implemented during that feature's resolution.

## Expected Behavior

A new `--sprint` flag accepts a sprint name and filters dependency analysis to only the issues defined in that sprint:

```bash
ll-deps analyze --sprint my-sprint        # analyze only sprint issues
ll-deps analyze --sprint my-sprint --graph # with dependency graph
ll-deps validate --sprint my-sprint       # validate only sprint deps
```

The flag reads the sprint definition YAML from the sprints directory (configured via `sprints.sprints_dir` in `ll-config.json`) and extracts the issue list, then passes only those issues to the analysis/validation pipeline.

## Motivation

During sprint planning, dependency analysis on the full backlog produces noise — users only care about relationships between the issues they're about to execute. Sprint-scoped analysis would:

- Reduce output to only actionable dependencies within the sprint
- Surface missing dependencies between sprint issues before execution starts
- Integrate naturally with the existing `ll-sprint` workflow (`create_sprint` -> `map-dependencies --sprint` -> `ll-sprint run`)

## Proposed Solution

1. Add `--sprint` argument to both `analyze` and `validate` subcommand parsers in `dependency_mapper.py`
2. When `--sprint` is provided, load the sprint YAML file and extract the issue ID list
3. Filter the discovered issue files to only those matching sprint issue IDs before passing to `analyze_dependencies()` or `validate_dependencies()`

```python
# In dependency_mapper.py (entry point for ll-deps)
def load_sprint_issues(sprint_name: str, sprints_dir: str) -> set[str]:
    """Load issue IDs from a sprint definition YAML."""
    sprint_path = Path(sprints_dir) / f"{sprint_name}.yaml"
    # parse and return issue IDs
```

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` - Add `--sprint` argument to subparsers, load sprint YAML, filter issues (this is the `ll-deps` entry point)
- `skills/map-dependencies/SKILL.md` - Document sprint-scoping option

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` - `Sprint.load()` and `SprintManager` provide sprint YAML loading utility to reuse

### Similar Patterns
- `ll-sprint run` already loads sprint YAML and extracts issue lists — reuse that parsing logic
- ENH-387 adds `--type` flag to CLI tools — follows same additive flag pattern

### Tests
- `scripts/tests/test_dependency_mapper.py` - Add tests for `--sprint` flag parsing and issue filtering

### Documentation
- N/A

### Configuration
- Uses `sprints.sprints_dir` from `ll-config.json` (default: `.sprints`)

## Implementation Steps

1. Reuse `Sprint.load()` from `scripts/little_loops/sprint.py` for sprint YAML parsing
2. Add `--sprint` argument to `analyze` and `validate` subparsers in `dependency_mapper.py`
3. Filter issue files to sprint set before calling `analyze_dependencies()` / `validate_dependencies()`
4. Update `skills/map-dependencies/SKILL.md` to document the new flag
5. Add tests for sprint-scoped analysis in `test_dependency_mapper.py`

## Scope Boundaries

- **In scope**: Adding `--sprint` flag to `ll-deps analyze` and `ll-deps validate`; loading sprint YAML; filtering issues
- **Out of scope**: Changes to `dependency_mapper.py` analysis logic; adding sprint awareness to other `ll-deps` features; auto-running dependency analysis during `ll-sprint run` (already handled by ENH-301)

## Impact

- **Priority**: P3 - Quality-of-life improvement for sprint planning workflow
- **Effort**: Small - Reuses existing sprint YAML parsing and issue filtering; additive flag
- **Risk**: Low - No existing behavior changes; flag is purely additive
- **Breaking Change**: No

## Builds On

- FEAT-261: Issue Dependency Mapping (completed — original spec planned this but didn't implement it)
- ENH-301: Integrate dependency mapper into sprint system (completed — related integration)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint and dependency system design |
| architecture | docs/API.md | ll-deps and sprint module APIs |

## Labels

`enhancement`, `cli`, `dependency-management`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/dependency_mapper.py`: Added `--sprint` argument to both `analyze` and `validate` subparsers, sprint loading logic in `main()`, and `only_ids` parameter to `_load_issues()`
- `scripts/tests/test_dependency_mapper.py`: Added 5 tests for sprint-scoped analysis (filter, validate, not-found, empty, unchanged default)
- `skills/map-dependencies/SKILL.md`: Documented `--sprint` flag with usage examples

### Verification Results
- Tests: PASS (68/68)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:capture-issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab030831-19f7-4fb7-8753-c1c282a30c99.jsonl`
- `/ll:manage-issue` - 2026-02-12

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P3
