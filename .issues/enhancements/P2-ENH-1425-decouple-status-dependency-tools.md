---
id: ENH-1425
type: ENH
priority: P2
status: open
parent_issue: ENH-1419
---

# ENH-1425: Decouple Issue Status — Dependency Tools

## Summary

Update `ll-deps` (`deps.py`) and `dependency_mapper/operations.py` to filter issues by `IssueInfo.status` frontmatter instead of excluding `completed/` and `deferred/` directories by name. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1423, ENH-1424, ENH-1426 after ENH-1417 lands.

## Current Behavior

`deps.py:_load_issues()` globs `get_completed_dir()` and `get_deferred_dir()` separately to discover completed/deferred issues. `dependency_mapper/operations.py:gather_all_issue_ids()` hardcodes `"completed"` and `"deferred"` as directory name strings when checking `path.parent.name`, creating tight coupling to the directory-based issue layout.

## Expected Behavior

Both `deps.py:_load_issues()` and `dependency_mapper/operations.py:gather_all_issue_ids()` filter issues by `IssueInfo.status` frontmatter field (`done`/`deferred`) instead of checking directory names. No references to `get_completed_dir()`, `get_deferred_dir()`, or hardcoded `"completed"`/`"deferred"` directory strings remain in either file.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

`deps.py` globs both `get_completed_dir()` and `get_deferred_dir()` separately; `dependency_mapper/operations.py` hardcodes `"completed"` and `"deferred"` as directory name strings. Switching to status-field filtering removes the directory coupling and makes both tools work with type-scoped directories.

## Proposed Solution

### `cli/deps.py`

- `_load_issues()` (lines 47–52): replace globs of `get_completed_dir()` and `get_deferred_dir()` with scanning type dirs and filtering by `IssueInfo.status` field to exclude `done` and `deferred` issues (or include them based on the `--include-completed` flag if applicable)

### `dependency_mapper/operations.py`

- `gather_all_issue_ids()` (lines 266–272): replace hardcoded `"completed"` / `"deferred"` dir name string checks with a status-field filter; scan type dirs and check `IssueInfo.status` instead of matching `path.parent.name`

## Implementation Steps

1. Update `scripts/little_loops/cli/deps.py:_load_issues()` — scan type dirs; filter by `IssueInfo.status` instead of directory globs
2. Update `scripts/little_loops/dependency_mapper/operations.py:gather_all_issue_ids()` — replace `"completed"` / `"deferred"` dir name strings with status-field check
3. Update `scripts/tests/test_dependency_mapper.py`:
   - `TestValidateDependencies::test_stale_completed_ref` — add `status: done` frontmatter to completed-issue fixture files placed in type dirs; remove `completed/` dir setup
   - `TestValidateDependencies::test_valid_with_completed_blocker` — same fixture update
   - `gather_all_issue_ids` tests at lines ~639–647 and ~1113–1151 — remove `.issues/completed/` directory creation; place files in type dirs with `status: done` frontmatter

## Files to Modify

- `scripts/little_loops/cli/deps.py`
- `scripts/little_loops/dependency_mapper/operations.py`
- `scripts/tests/test_dependency_mapper.py`

## Acceptance Criteria

- `ll-deps` excludes done/deferred issues via status field without reading `completed/` or `deferred/` dirs
- `gather_all_issue_ids()` uses status-field filter; zero hardcoded `"completed"` / `"deferred"` dir strings remain
- All updated tests pass

## Scope Boundaries

- **In scope**: `cli/deps.py:_load_issues()`, `dependency_mapper/operations.py:gather_all_issue_ids()`, and associated tests in `test_dependency_mapper.py`
- **Out of scope**: Other CLI tools (covered by parallel ENH-1422, ENH-1423, ENH-1424, ENH-1426); ENH-1417 `IssueInfo.status` infrastructure this depends on; sprint runner, sync, parallel, and capture tools

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `cli/deps.py` | `_load_issues()` | globs `get_completed_dir()` and `get_deferred_dir()` | 47–52 |
| `dependency_mapper/operations.py` | `gather_all_issue_ids()` | hardcodes `"completed"` / `"deferred"` dir name strings | 266–272 |

### Breaking Tests

- `scripts/tests/test_dependency_mapper.py` — `completed_ids=` API call changes after directory approach replaced; tests at lines ~639–647 and ~1113–1151 create `.issues/completed/` directories

### Dependent Files (Callers/Importers)

- `scripts/tests/test_dependency_mapper.py` — tests exercising `_load_issues()` and `gather_all_issue_ids()`

### Similar Patterns

- `scripts/little_loops/cli/issues.py` — ENH-1418 applied the same status-field filter pattern; follow that implementation
- `scripts/little_loops/sprint_runner/` — ENH-1424 applied the same decoupling pattern for sprint runner

### Documentation

- N/A — no user-facing docs reference dependency tool directory structure

### Configuration

- N/A

## Impact

- **Priority**: P2 — Part of ENH-1419 decoupling initiative; unblocked once ENH-1417 lands
- **Effort**: Small — Two targeted function rewrites plus test fixture updates; pattern established by ENH-1418/ENH-1424
- **Risk**: Low — Internal refactor; public CLI behavior unchanged; comprehensive test coverage exists
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `decoupling`, `dependencies`

## Session Log
- `/ll:format-issue` - 2026-05-10T20:35:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0612cbb2-b886-45d0-8bec-88f7ba66f6e5.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
