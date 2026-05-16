---
id: ENH-1419
type: ENH
priority: P2
status: done

decision_needed: false
confidence_score: 100
outcome_confidence: 59
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
size: Very Large
parent: ENH-1390
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Summary

Update the `ll-issues` CLI commands, `ll-sync`, sprint runner, parallel orchestrator discovery, and dependency tools to use `status:` frontmatter instead of directory location. Depends on ENH-1417 (IssueInfo.status). Can run in parallel with ENH-1418 and ENH-1421 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Motivation

This enhancement propagates the `status:` frontmatter model (established in ENH-1417) across all user-facing CLI tools, sync, sprint runner, parallel orchestrator, and dependency tools:
- Removes directory-as-status coupling from `ll-issues list/show/count`, `ll-sync`, sprint runner, and `ll-deps`
- Enables issues in any status to live in type-scoped directories (`bugs/`, `features/`, etc.) rather than status-named dirs
- Unblocks ENH-1418 and ENH-1421 from running concurrently once ENH-1417 lands

## Proposed Solution

### Step 3 — `ll-issues list` and display

- `scripts/little_loops/cli/issues/search.py:_load_issues_with_status()`: read `status:` from `IssueInfo.status` instead of mapping directory name; update `cmd_search()` status string values from `"active"/"completed"/"deferred"` to the full vocab (`open|in_progress|blocked|deferred|done|cancelled|all`)
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()`: read `info.status` instead of checking `path.parent.name` (`"completed"` → `"Completed"`, etc.); update `_resolve_issue_id()` to search type dirs only (no separate `completed/` + `deferred/` pass)
- `scripts/little_loops/cli/issues/count_cmd.py`: update `--status active|completed|deferred` choices to align with new enum

### Step 6 — `ll-sync` status field mapping

- `scripts/little_loops/sync.py:GitHubSyncManager._get_local_issues()`: scan all type dirs; use `IssueInfo.status` to map to GitHub open/closed
- Update `close_issues()` and `reopen_issues()` to read `status:` field rather than directory
- `close_issues --all-completed`: scan type dirs for `status: done` instead of `get_completed_dir().glob()`
- `_find_local_issue()`: type-dir-only search

### Sprint runner + parallel discovery

- `scripts/little_loops/cli/sprint/run.py`: pre-validates sprint issues via `get_completed_dir().glob()` — replace with frontmatter `status: done` check
- `scripts/little_loops/cli/sprint/edit.py`: completed issue lookup via `get_completed_dir()` — replace with status field
- `scripts/little_loops/cli/sprint/show.py`: `completed_issues` tracking in sprint summary — replace with frontmatter filter

### Dependency tools

- `scripts/little_loops/cli/deps.py`: excludes `completed/` and `deferred/` dirs from dependency analysis — replace with `status` field filter
- `scripts/little_loops/dependency_mapper/operations.py`: excludes `"completed"` and `"deferred"` dir name strings from file-hint analysis — replace with status check

### `cli/auto.py` validation

- `scripts/little_loops/cli/auto.py`: delegates to `AutoManager` which calls `find_issues()` (directory-scoped) — no additional changes needed here once `find_issues()` is updated in ENH-1418, but verify no direct directory references remain

## Implementation Steps

1. Update `ll-issues list/show/count` — read `status:` from `IssueInfo.status`; align `--status` choices with new enum (Step 3)
2. Update `ll-sync` — scan type dirs; map `IssueInfo.status` to GitHub open/closed instead of directory checks (Step 6)
3. Update sprint runner (`run.py`, `edit.py`, `show.py`) — replace `get_completed_dir()` lookups with frontmatter `status: done` checks
4. Update dependency tools (`deps.py`, `dependency_mapper/operations.py`) — filter by status field instead of dir name
5. Verify `cli/auto.py` has no remaining direct directory references after ENH-1418 lands
6. Update all corresponding tests (list in Tests to Update section)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/parallel/orchestrator.py::_complete_issue_lifecycle_if_needed()` (line 1210) — replace `completed_dir = self.br_config.get_completed_dir()` + `completed_path.exists()` check with `IssueInfo.status == "done"` check; this is the parallel orchestrator's "already completed" guard that must use frontmatter
8. Update `scripts/little_loops/cli/issues/skip.py::cmd_skip()` — replace `if parent_name in ("completed", "deferred")` directory guard with `info.status in ("done", "deferred")` frontmatter check; also update the user-visible error message that currently references `completed/`
9. Update `scripts/tests/test_cli_sync.py` — add `status: done` frontmatter to completed issue fixtures in `mock_config` setup; remove `completed/` directory creation
10. Update `scripts/tests/test_cli.py` — replace hard-coded `"completed_dir": "completed"` config dict entries with `status:` frontmatter in fixture issue files

## Files to Modify

- `scripts/little_loops/cli/issues/search.py` — status from frontmatter; new status vocab
- `scripts/little_loops/cli/issues/show.py` — status from `info.status`; type-dir-only id resolution
- `scripts/little_loops/cli/issues/count_cmd.py` — align `--status` choices with new enum
- `scripts/little_loops/cli/issues/list_cmd.py` — also calls `_load_issues_with_status()` at line 38 (not previously listed)
- `scripts/little_loops/sync.py` — scan type dirs; use IssueInfo.status for open/closed mapping
- `scripts/little_loops/cli/sprint/run.py` — replace completed dir check with status field
- `scripts/little_loops/cli/sprint/edit.py` — replace `get_completed_dir()` lookup
- `scripts/little_loops/cli/sprint/show.py` — **verify-only**: analyzer confirmed no directory-based logic; `completed_issues` tracking comes from `.sprint-state.json`, not directory inspection
- `scripts/little_loops/cli/deps.py` — status field exclusion
- `scripts/little_loops/dependency_mapper/operations.py` — status field exclusion
- `scripts/little_loops/issue_manager.py` — line 783: inline hardcoded path `(config.repo_path or Path.cwd()) / ".issues" / "completed"` bypasses `config.get_completed_dir()`; replace with status field check (not previously listed)

## Tests to Update

- `scripts/tests/test_issues_cli.py` — `ll-issues list` and `ll-issues show`; add `--status open|deferred|done|all` filter tests
- `scripts/tests/test_issues_path.py` — `_resolve_issue_id()` type-dir-only lookup post-migration
- `scripts/tests/test_issues_search.py` — `TestSearchStatusFilter`: update `test_include_completed`, `test_status_all`, `test_status_completed_only`, `test_text_query_with_include_completed` to use `status:` frontmatter in type dirs
- `scripts/tests/test_sprint.py`, `test_sprint_integration.py` — update `get_completed_dir()` pre-validation tests to use `status: done` frontmatter check
- `scripts/tests/test_orchestrator.py` — parallel orchestrator issue-discovery tests; verify status-field filtering works correctly
- `scripts/tests/test_sync.py` — `GitHubSyncManager` directory-to-remote-state mapping → `IssueInfo.status` field mapping
- `scripts/tests/test_cli_output.py` — update/remove `get_completed_dir`/`get_deferred_dir` mocks at line 291–292
- `scripts/tests/test_dependency_mapper.py` — `TestValidateDependencies::test_stale_completed_ref` and `test_valid_with_completed_blocker`: update `completed_ids=` API call after directory-based approach is replaced
- `scripts/tests/conftest.py` — add `status: open` to fixture issue file content; keep `"completed_dir"`/`"deferred_dir"` keys during migration, remove after ENH-1420

## Acceptance Criteria

- `ll-issues list` defaults to showing `open` + `in_progress`; `--status deferred` and `--status done` filters work
- `ll-issues show` displays correct status from frontmatter
- `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- Sprint pre-validation uses `status: done` check
- Dependency tools exclude done/deferred issues via status field
- All updated tests pass

## Success Metrics

- Zero calls to `get_completed_dir()` or `get_deferred_dir()` remain in the listed files after changes
- `ll-issues list` returns correct results for `--status open`, `--status done`, `--status deferred`, and `--status all`
- `ll-sync` correctly maps `status: done` → remote closed and `status: open` → remote open without directory checks
- All updated tests pass without regressions

## Scope Boundaries

- **In scope**: `ll-issues list/show/count`, `ll-sync`, sprint runner (`run.py`/`edit.py`/`show.py`), parallel orchestrator discovery, `ll-deps`, `dependency_mapper/operations.py`, and their tests
- **Out of scope**: Core `IssueInfo.status` model and `find_issues()` (ENH-1417/ENH-1418); command/skill/doc updates (ENH-1421); migration script (ENH-1420); any new status vocab beyond the enum established in ENH-1417

## Integration Map

### Key Anchors (Directory-Based Logic to Replace)

| File | Function/Location | Directory Logic | Line(s) |
|------|-------------------|-----------------|---------|
| `cli/issues/search.py` | `_load_issues_with_status()` | globs `get_completed_dir()` / `get_deferred_dir()`, assigns `"active"`/`"completed"`/`"deferred"` tag by bucket | 106–150 |
| `cli/issues/show.py` | `_parse_card_fields()` | `path.parent.name == "completed"` / `"deferred"` | 138–144 |
| `cli/issues/show.py` | `_resolve_issue_id()` | searches `get_completed_dir()` + `get_deferred_dir()` explicitly | 80–82 |
| `sync.py` | `GitHubSyncManager._get_local_issues()` | globs active dirs + conditionally `get_completed_dir()` | 264–284 |
| `sync.py` | `close_issues()` | globs `get_completed_dir()` when `all_completed=True` | 926–931 |
| `sync.py` | `reopen_issues()` | `issue_path.parent == completed_dir` | 1079 |
| `sync.py` | `_find_local_issue()` | re-globs `get_completed_dir()` unconditionally | 741–761 |
| `sprint/run.py` | `_cmd_sprint_run()` | `completed_dir.glob(f"*-{issue_id}-*.md")` pre-validation | 162–178 |
| `sprint/edit.py` | `_cmd_sprint_edit()` | globs `get_completed_dir()` to build `completed_ids` | 72–89 |
| `cli/deps.py` | `_load_issues()` | globs both `get_completed_dir()` and `get_deferred_dir()` | 47–52 |
| `dependency_mapper/operations.py` | `gather_all_issue_ids()` | hardcodes `"completed"` / `"deferred"` as dir name strings | 266–272 |
| `issue_manager.py` | inline check | `(config.repo_path or Path.cwd()) / ".issues" / "completed"` literal path | 783 |

### Callers of `_load_issues_with_status()`

- `scripts/little_loops/cli/issues/list_cmd.py:38` — calls `_load_issues_with_status()`
- `scripts/little_loops/cli/issues/count_cmd.py:31` — calls `_load_issues_with_status()`
- `scripts/little_loops/cli/issues/search.py:280` — `cmd_search()` calls it

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py` — `_complete_issue_lifecycle_if_needed()` at line 1210: `completed_dir = self.br_config.get_completed_dir()` then checks `completed_path.exists()` to skip already-completed issues; this direct call is not in "Files to Modify" but "parallel orchestrator discovery" is in scope [Agent 1 / Agent 2 finding]
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()` guard: `if parent_name in ("completed", "deferred")` at the top of the function — directory-name-based status check that produces user-visible error message referencing `completed/`; borderline scope but is a user-facing CLI status check [Agent 2 finding]

### Similar Patterns to Follow

- `scripts/tests/test_issue_parser.py:TestIssueInfoStatus` lines 2308–2428 — canonical test pattern; fixture uses `---\nstatus: blocked\n---\n` in file content
- `scripts/tests/test_issue_parser_properties.py:82` — valid status vocabulary defined in hypothesis strategy: `["open", "in_progress", "blocked", "deferred", "done", "cancelled"]`

### Tests

- `scripts/tests/test_issues_search.py:TestSearchStatusFilter` lines 373–461 — `search_issues_dir` fixture (lines 20–72) currently places completed issues in a physical `completed/` dir **without** `status:` frontmatter; tests must be updated to add `status: done` to fixture files in type dirs
- `scripts/tests/test_cli_output.py:291–292` — remove `get_completed_dir`/`get_deferred_dir` mocks
- `scripts/tests/test_dependency_mapper.py:TestValidateDependencies` — `completed_ids=` API param changes after directory approach replaced
- `scripts/tests/conftest.py` — add `status: open` to fixture issue file content

_Wiring pass added by `/ll:wire-issue`:_

**Additional test files to update (not previously listed):**
- `scripts/tests/test_cli_sync.py` — `mock_config` fixture calls `(issues_dir / "completed").mkdir(parents=True)` to set up `GitHubSyncManager` tests; must add `status: done` frontmatter to fixture issue files placed there [Agent 3 finding]
- `scripts/tests/test_cli.py` — hard-codes `"completed_dir": "completed"` in inline config dicts at lines 293, 480, 1471, 1586, 2370; creates `completed/` directories directly in test setup; will need `status:` frontmatter awareness [Agent 3 finding]

**Breaking test functions (specific names not previously listed):**
- `scripts/tests/test_issues_cli.py::test_show_completed_issue` — asserts `"Status: Completed"` string derived from `parent_name == "completed"` in `show.py:139`; will fail when status comes from frontmatter [Agent 3 finding]
- `scripts/tests/test_issues_cli.py::test_count_status_completed` — places files in `completed/` dir with no `status: done` frontmatter; count result breaks after migration [Agent 3 finding]
- `scripts/tests/test_issues_cli.py::test_count_status_deferred` — same pattern for `deferred/` dir / `status: deferred` [Agent 3 finding]
- `scripts/tests/test_dependency_mapper.py::gather_all_issue_ids` tests at lines ~639–647 and ~1113–1151 — create `.issues/completed/` directories and place files there; `gather_all_issue_ids()` hardcodes `"completed"`/`"deferred"` dir name strings today; these will break when `operations.py` switches to status-field filter [Agent 3 finding]

### Key Implementation Notes

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `get_completed_dir()` and `get_deferred_dir()` already emit `DeprecationWarning` pointing to `IssueInfo.status` (`config/core.py:221–237`) — calls produce warnings in test output until replaced
- No formal `IssueStatus` enum class exists; status values are plain string literals (`"open"`, `"in_progress"`, `"blocked"`, `"deferred"`, `"done"`, `"cancelled"`) — use strings directly
- `IssueInfo.status` is populated by `IssueParser.parse_file()` at line 445 via `frontmatter.get("status", "open")` — parsing is already correct; only consumers need updating
- `sprint/show.py` confirmed no directory-based logic — `completed_issues` tracks via `.sprint-state.json`; only verify no regressions
- `parallel/priority_queue.py:scan_issues()` lines 241–253 delegates to `find_issues()` — inherits status filtering gap from ENH-1418 scope, no direct changes needed here

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- Wide change surface: 16+ distinct `get_completed_dir()`/`get_deferred_dir()` call sites across 11 implementation files plus 12+ test files — each requires contextual replacement rather than a uniform text substitution (Pattern A blast radius)
- Breadth penalty dominates Criterion A: per-site depth is local (simple function-body swaps), but the wide enumeration penalizes complexity score; plan for sequential file-by-file verification
- Mitigation: the Integration Map is exhaustive and every call site is mapped with file:function:line — actual implementation risk is lower than score suggests, but budget extra time for test updates across 12+ test files

## Session Log
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f185f31e-2a67-40df-940b-3d6f65f158ab.jsonl`
- `/ll:refine-issue` - 2026-05-10T16:17:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c4155a89-3d63-45f3-aaf4-bfaf4cf33cf7.jsonl`
- `/ll:format-issue` - 2026-05-10T15:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa41123a-15d8-4c8c-adaa-e1f58a46abea.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score 11/11 — Very Large; 11 implementation files, 12+ test files, 5 distinct concerns)

### Decomposed Into
- ENH-1422: Decouple Issue Status — ll-issues CLI (list/show/count/search)
- ENH-1423: Decouple Issue Status — ll-sync
- ENH-1424: Decouple Issue Status — Sprint Runner
- ENH-1425: Decouple Issue Status — Dependency Tools
- ENH-1426: Decouple Issue Status — Parallel Orchestrator, skip.py, and issue_manager

---

**Open** | Created: 2026-05-10 | Priority: P2
