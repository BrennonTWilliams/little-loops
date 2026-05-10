---
id: ENH-1425
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T21:05:25Z
parent_issue: ENH-1419
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `scripts/little_loops/dependency_mapper/operations.py:gather_all_issue_ids()` docstring — correct the fallback list (drop `"completed"` and `"deferred"`, confirm `"epics"` is present)
5. Update `scripts/tests/test_dependency_mapper.py` — remove `(issues_dir / "completed").mkdir()` from `TestMainCLI::test_analyze_no_issues`, `test_validate_no_issues`, `test_analyze_with_issues`, `_setup_sprint_project`; and from `TestMainCLIFix::_setup_fix_project`, `test_fix_no_issues`; and from `TestMainCLIApply::_setup_apply_project`, `_setup_apply_sprint_project`
6. Update `skills/map-dependencies/SKILL.md` — remove or annotate `issues.completed_dir` in "Configuration" section; after ENH-1425 the dependency tools no longer read that config key

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

_Wiring pass added by `/ll:wire-issue`:_
- `TestMainCLI::test_analyze_no_issues` (line ~1108) — creates `(issues_dir / "completed").mkdir()`; remove after refactor
- `TestMainCLI::test_validate_no_issues` (line ~1126) — same
- `TestMainCLI::test_analyze_with_issues` (line ~1143) — same
- `TestMainCLI::_setup_sprint_project` (line ~1165) — same
- `TestMainCLIFix::_setup_fix_project` (line ~1491) — creates `completed/` dir in fixture setup; remove after refactor
- `TestMainCLIFix::test_fix_no_issues` (line ~1556) — same inline `completed/` dir creation
- `TestMainCLIApply::_setup_apply_project` (line ~1589) — same
- `TestMainCLIApply::_setup_apply_sprint_project` (line ~1612) — same

### Dependent Files (Callers/Importers)

- `scripts/tests/test_dependency_mapper.py` — tests exercising `_load_issues()` and `gather_all_issue_ids()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — calls `gather_all_issue_ids()` in `IssueManager.__init__()`; behavior change is transparent, no code change needed
- `scripts/little_loops/cli/sprint/run.py` — calls `gather_all_issue_ids()` in `run_sprint()`; transparent
- `scripts/little_loops/cli/sprint/manage.py` — calls `gather_all_issue_ids()` in `manage_sprint()`; transparent
- `scripts/little_loops/cli/sprint/edit.py` — calls `gather_all_issue_ids()`; transparent
- `scripts/little_loops/cli/sprint/show.py` — calls `gather_all_issue_ids()`; transparent
- `scripts/little_loops/cli/issues/clusters.py` — calls `gather_all_issue_ids()` via direct `dependency_mapper.operations` import; transparent

### Similar Patterns

- `scripts/little_loops/cli/issues/search.py:106-150` — `_load_issues_with_status()` is the canonical ENH-1418 implementation; iterates `config.issue_categories`, calls `config.get_issue_dir(category)`, reads `issue.status` from parsed `IssueInfo`
- `scripts/little_loops/issue_parser.py:774-814` — `find_active_issues()` inline status check pattern: `if info.status in ("done", "cancelled", "deferred"): continue`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/map-dependencies/SKILL.md` — "Configuration" section lists `issues.completed_dir` as a config key for the skill; after ENH-1425 `gather_all_issue_ids()` no longer reads that config key — remove or annotate the entry
- `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()` docstring cites incorrect fallback list (missing `"epics"`, includes `"completed"`); update as part of Step 2

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### `_load_issues()` — exact current code for the section to rewrite (`cli/deps.py:43–52`)

```python
completed_ids: set[str] = set()
for non_active_dir in [config.get_completed_dir(), config.get_deferred_dir()]:
    if non_active_dir.exists():
        for f in non_active_dir.glob("*.md"):
            match = _re.search(r"(BUG|FEAT|ENH|EPIC)-(\d+)", f.name)
            if match:
                completed_ids.add(f"{match.group(1)}-{match.group(2)}")
```

The active-issues part above this (via `find_issues()`) is already status-aware — only lines 43–52 need replacing. Replacement needs `IssueParser` (or lightweight frontmatter parse) to read `status` from type-dir files; `find_issues()` is not the right tool here since it excludes done issues by design.

#### `gather_all_issue_ids()` — both branches need updating (`dependency_mapper/operations.py:266–272`)

```python
# config-aware branch (line 267–269) — also uses deprecated methods:
subdirs = config.issue_categories + [
    config.get_completed_dir().name,    # ← emits DeprecationWarning
    config.get_deferred_dir().name,     # ← emits DeprecationWarning
]
# no-config fallback (line 271):
subdirs = ["bugs", "features", "enhancements", "epics", "completed", "deferred"]
```

**Important**: this function's purpose is to collect ALL known issue IDs (including done ones) to prevent false "nonexistent" warnings — it does **not** need to filter by status. The fix is just changing *which dirs* are scanned: replace `config.issue_categories + [completed_dir, deferred_dir]` with just `config.issue_categories`. Done issues are already in type dirs with `status: done` frontmatter, so scanning type dirs finds them. The no-config fallback should become `["bugs", "features", "enhancements", "epics"]`.

#### Additional test to update — `test_config_includes_completed_dir` (`test_dependency_mapper.py:696–724`)

This test creates an `archive/` directory (via `completed_dir: "archive"` config) and puts a done-issue file there. After the refactor it needs to put the done file in a type dir with `status: done` frontmatter instead. Not mentioned in the issue's current test list.

#### Test fixture pattern for done issues in type dirs (from `test_sprint.py:1702`)

```python
(tmp_path / ".issues" / "bugs" / "P1-BUG-001-test-bug.md").write_text(
    "---\nstatus: done\n---\n\n# BUG-001: Done"
)
```

Use this pattern when rewriting `test_scans_all_categories` (line 635), the `TestMainCLI` setup blocks (lines ~1108–1163), and `test_config_includes_completed_dir` (line 696).

## Impact

- **Priority**: P2 — Part of ENH-1419 decoupling initiative; unblocked once ENH-1417 lands
- **Effort**: Small — Two targeted function rewrites plus test fixture updates; pattern established by ENH-1418/ENH-1424
- **Risk**: Low — Internal refactor; public CLI behavior unchanged; comprehensive test coverage exists
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `decoupling`, `dependencies`

## Session Log
- `/ll:manage-issue` - 2026-05-10T21:05:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0101930c-df19-4f81-9d12-75e7fa7087b2.jsonl`
- `/ll:ready-issue` - 2026-05-10T21:00:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0101930c-df19-4f81-9d12-75e7fa7087b2.jsonl`
- `/ll:confidence-check` - 2026-05-10T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0101930c-df19-4f81-9d12-75e7fa7087b2.jsonl`
- `/ll:wire-issue` - 2026-05-10T20:55:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0101930c-df19-4f81-9d12-75e7fa7087b2.jsonl`
- `/ll:refine-issue` - 2026-05-10T20:49:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b00184a9-4790-43b5-863b-e3a2d2a0c1ff.jsonl`
- `/ll:format-issue` - 2026-05-10T20:35:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0612cbb2-b886-45d0-8bec-88f7ba66f6e5.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
