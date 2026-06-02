---
id: ENH-1418
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T20:30:19Z

decision_needed: false
confidence_score: 100
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1390
---

# ENH-1418: Decouple Issue Status — Discovery, Lifecycle, and History Redesign

## Summary

Update issue discovery (`find_issues()`), lifecycle operations (`close_issue`, `defer_issue`, etc.), the parallel orchestrator, and the issue history parser to use `status:` frontmatter instead of directory location. Depends on ENH-1417 (IssueInfo.status must exist first). Can run in parallel with ENH-1419 and ENH-1421 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Current Behavior

Issue discovery (`find_issues()`) uses frozenset-based filename exclusion to filter completed/deferred issues — checking if filenames match patterns derived from `completed/` and `deferred/` directory names. Lifecycle operations (`close_issue`, `defer_issue`, `undefer_issue`) call `shutil.move` to physically relocate files into `completed/` or `deferred/` directories. The parallel orchestrator tracks completion by moving files (lines 1210–1289). Issue history parsing (`scan_completed_issues`) targets the `completed/` directory directly. Several files hardcode `".issues/completed"` path references (`issue_manager.py:783`, `cli/history.py:199`).

## Expected Behavior

- `find_issues()` returns issues with `status: open` (or `in_progress`/`blocked`) by filtering frontmatter — files remain in their type directories regardless of lifecycle state
- `close_issue()`, `defer_issue()`, `undefer_issue()` write `status:` frontmatter via `update_frontmatter()` — no `shutil.move` calls
- `scan_completed_issues()` scans type directories and filters on `status: done` from frontmatter
- No hardcoded `completed/` or `deferred/` directory paths remain in the above files

## Motivation

This enhancement is part of ENH-1390 (Decouple Issue Status from Directory Structure). Using directory location as the status indicator:
- Forces expensive filesystem moves on every status transition, creating race conditions in parallel orchestration
- Prevents multiple automation tools from tracking issue state simultaneously without filesystem conflicts
- Couples history parsing to physical file location rather than data, complicating backfill and migration workflows

## Proposed Solution

### Step 2 — `find_issues()` status filter

- `scripts/little_loops/issue_parser.py:find_issues()`: replace frozenset-based filename exclusion (`completed_names`, `deferred_names`) with a post-parse filter: `if info.status in ("done", "deferred", "cancelled"): continue`
- Fix hardcoded `".issues/completed"` path at `issue_manager.py:783`: replace glob with `info.status == "done"` check
- Fix hardcoded `cli/history.py:199` path: stop relying on `completed/` dir

### Step 5 — `capture-issue` skill reopen flow

- `skills/capture-issue/SKILL.md`: replace "reopen completed issue" flow (which currently does a file move from `completed/`) with a `status:` field update via `update_frontmatter()`

### Step 11 — `issue_history/parsing.py` redesign (Sub-decision 1 from ENH-1390)

- `scripts/little_loops/issue_history/parsing.py`: redesign `scan_completed_issues()` to scan type directories (`features/`, `bugs/`, `enhancements/`, `epics/`) and filter on `status: done` from frontmatter
- Redesign `_batch_completion_dates()`: replace git-log file-move approach with `completed_at:` frontmatter field as primary source of truth (already the priority-1 path in `_parse_completion_date()` at lines 185–190); git-log fallback tiers can be removed once ENH-1420 backfills old files
- `scripts/little_loops/cli/history.py:199`: remove hardcoded `completed/` path dependency

### Step 5 (cont.) — `issue_lifecycle.py` + `orchestrator.py`

- `scripts/little_loops/issue_lifecycle.py`: rewrite `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()` to call `update_frontmatter(path, {"status": ...})` instead of `shutil.move`; each currently calls `config.get_completed_dir()` / `config.get_deferred_dir()` — replace those calls
- `scripts/little_loops/parallel/orchestrator.py`: update completion path (lines 1210–1289) to write `status: done` to frontmatter instead of moving file; update `_deferred_issues` tracking (lines 127–128, 1000–1017) to use frontmatter reads

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-10.

**Selected**: Option A — Regex-based frontmatter write detection

**Reasoning**: Option A is fully consistent with the existing hook architecture — `check-duplicate-issue-id-post.sh` provides a directly reusable PostToolUse Write path-filter idiom, and `hooks-reference.md` confirms `tool_input.content` is present in the stdin payload. Option B requires building a non-existent IPC bridge between the Python `EventBus` and Claude Code's harness, plus custom event type support that `hooks.json` has no mechanism for — `hooks/hooks.json` accepts only native Claude Code SDK lifecycle events and has no extensibility point for application-defined events.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (frontmatter write detection) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |
| Option B (dedicated hook event) | 0/3 | 0/3 | 1/3 | 0/3 | 1/12 |

**Key evidence**:
- Option A: `check-duplicate-issue-id-post.sh:30–44` provides exact reusable path-filter idiom; `hooks.json:77–84` shows PostToolUse Write is already used; `hooks-reference.md:725–731` confirms `tool_input.content` is in stdin payload; `TestDuplicateIssueIdPost` is a direct test template
- Option B: `events.py` EventBus and `issue_lifecycle.py:close_issue()` emit `"issue.closed"` internally, but there is zero IPC bridge from Python EventBus to Claude Code harness; `hooks.json` has no custom event type mechanism; would require SDK-level changes

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — find_issues() status filter
- `scripts/little_loops/issue_manager.py` — fix hardcoded `".issues/completed"` at line 783
- `scripts/little_loops/issue_lifecycle.py` — rewrite close/defer/undefer to use frontmatter
- `scripts/little_loops/parallel/orchestrator.py` — completion path (lines 1210–1289), deferred tracking
- `scripts/little_loops/issue_history/parsing.py` — redesign scan_completed_issues, _batch_completion_dates
- `scripts/little_loops/cli/history.py` — fix hardcoded completed/ path at line 199
- `skills/capture-issue/SKILL.md` — reopen flow → status field update

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/orchestrator.py` — calls `issue_lifecycle.close_issue()` and `find_issues()`
- `scripts/little_loops/cli/auto.py` — calls `find_issues()` to build work queue
- `scripts/little_loops/cli/sprint.py` — calls `find_issues()` for sprint execution

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py:verify_issue_completed()` — checks `get_completed_dir() / info.path.name` file existence; will always return `False` after `close_issue()` stops moving files; must be rewritten alongside `close_issue()` in Step 3 to check `IssueInfo.status == "done"` via frontmatter (called by `issue_manager.py:_process_single_issue()` line 840 as Phase 3 verification gate — if left broken, every successful run fires `complete_issue_lifecycle` as fallback, double-completing)
- `scripts/little_loops/issue_discovery/search.py:_get_category_from_issue_path()` — resolves target category for file move during `undefer_issue()`; uses `get_completed_dir()` / `get_deferred_dir()` path membership (lines 61, 68) to classify files; must be updated as part of the `undefer_issue()` rewrite since undefer no longer moves files
- `scripts/little_loops/issue_discovery/search.py:_get_all_issue_files()` — gathers issues from `completed/` and `deferred/` dirs directly (lines 61, 68); used by discovery search; will miss done issues sitting in type dirs after the change
- `scripts/little_loops/parallel/merge_coordinator.py:_is_lifecycle_file_move()` — detects `git mv` renames to `completed/`/`deferred/` (line 364); will never return `True` after frontmatter-only completion; drives `_commit_pending_lifecycle_moves()` (line 402) and `_stash_local_changes()` exclusion (line 168) — all three become dead code; add to scope for dead-code removal (confirmed: coordinator does NOT independently move issue files to `completed/` — only `orchestrator.py` lines 1210–1289 do that)
- `scripts/little_loops/parallel/priority_queue.py:scan_issues()` — calls `find_issues(config, ...)` (line 242); behavior change is transparent but this caller is affected by the filter change

### Similar Patterns

- `update_frontmatter()` in `scripts/little_loops/frontmatter.py` is the established pattern for all frontmatter writes — use it consistently (signature: `update_frontmatter(content: str, updates: dict[str, str | int]) -> str`)
- `scripts/little_loops/learning_tests.py:mark_learning_test_stale()` is the **only existing call site that writes a `status:` field** via `update_frontmatter` — use this as the direct pattern reference:
  ```python
  updated = update_frontmatter(path.read_text(), {"status": "stale"})
  path.write_text(updated)
  ```

### Tests

- `scripts/tests/test_issue_lifecycle.py` — `TestCloseIssue`, `TestCompleteIssueLifecycle`: assert on frontmatter writes instead of file moves; update `sample_config` fixture usage. **Also remove the `suppress_deprecation_warnings` autouse fixture** (lines 71–76) — it exists solely to silence `get_completed_dir()`/`get_deferred_dir()` DeprecationWarnings and becomes unnecessary after the rewrite.
- `scripts/tests/test_issue_discovery.py` — `issues_with_content` fixture: refactor from directory-based to status-field-based discovery
- `scripts/tests/test_issue_history_parsing.py` — `scan_completed_issues()` coupling; update for frontmatter-based completion-date strategy
- `scripts/tests/test_issue_history_cli.py` — ~40 references to `completed/` directory; update all to create files in type dirs with `status: done`
- `scripts/tests/test_issue_manager.py` — `TestPathRenameHandling::test_path_rename_updates_tracking`: update `IssueInfo` construction for new `status` field
- `scripts/tests/test_merge_coordinator.py` — ~15 references to `completed/` dir; update `git mv` simulation to assert frontmatter write
- `scripts/tests/test_refine_status.py` — ~20 test methods with `completed/`/`deferred/` setup blocks; clean up setup

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — **WILL BREAK**: `TestGetNextIssueNumber` (6 tests write files into `completed/` and `deferred/` dirs); `TestFindIssues::test_find_issues_skips_duplicates_in_completed/deferred` (2 tests); `test_find_issues_skip_check_uses_two_globs_not_stat_per_file` calls `config.get_completed_dir()`/`get_deferred_dir()` inside a warnings suppressor — update all to use status-field-based logic; this file is NOT in the existing test list but directly tests `find_issues()` and `get_next_issue_number()`
- `scripts/tests/test_orchestrator.py` — **WILL BREAK**: `TestCompleteIssueLifecycle` (line 1926+) hardcodes `temp_repo_with_config / ".issues" / "completed"` as assertion path (lines 1944–1945, 2001, 2038); update to assert frontmatter write instead
- `scripts/tests/test_issue_workflow_integration.py` — **WILL BREAK**: `project_setup` fixture creates `completed_dir = issues_base / "completed"` and `.mkdir()`; `TestSequentialWorkflowIntegration` and `TestParallelWorkflowIntegration` assert directory-based completion; update for frontmatter-based state
- `scripts/tests/test_cli.py` — **WILL BREAK**: nine `scan_completed_issues` patches (lines 2688–2820) in `TestMainHistoryCoverage`; `history_project` fixture creates `completed_dir = issues_dir / "completed"` with a file; update to place files in type dirs with `status: done`
- `scripts/tests/test_issues_cli.py` — **WILL BREAK**: `test_show_completed_issue` (line 1228) places file in `completed/` and asserts `"Status: Completed"` via parent dir name; `test_count_status_completed`, `test_count_status_deferred`, `test_count_status_all` (lines 2232–2320) use filesystem dirs; update all
- `scripts/tests/test_issues_path.py` — **WILL BREAK**: `test_finds_issue_in_completed`, `test_finds_issue_in_deferred` write files to `completed_dir` / `deferred_dir`; update to place files in type dirs with `status:` field
- `scripts/tests/test_issues_search.py` — **WILL BREAK**: `search_issues_dir` fixture (line 19) creates `completed_dir = issues_base / "completed"` and writes a completed issue there; update for frontmatter-based discovery
- `scripts/tests/conftest.py` — **SHARED FIXTURE IMPACT**: `issues_dir` fixture (line 126) creates `completed/` and `deferred/` directories and calls `.mkdir()`; consumed by `TestGetNextIssueNumber` and `TestFindIssues`; update shared fixture or individual tests that rely on it to avoid broken state for all consuming tests

### Documentation

- `docs/ARCHITECTURE.md` — update status transition diagrams if present
- `docs/reference/API.md` — `find_issues()` signature and behavior changes

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/issue-completion-log.sh` — PostToolUse trigger regex `git mv .+ completed/` (line 26) will **silently never fire** after the rewrite; the session log auto-linking feature (appending session JSONL path to issue files on completion) will stop working entirely without any error; update trigger to detect frontmatter write instead of git mv — **this is a functional regression, not a doc-only change**
- `skills/manage-issue/SKILL.md` — "CRITICAL" section (lines 450–466) instructs users to `git mv` issue files to `completed/`; `defer`/`undefer` action descriptions (lines 506–507) describe directory moves; these user-facing instructions will conflict with the new model and cause incorrect manual completions (ENH-1421 scope but high-visibility risk)

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`get_completed_dir()` and `get_deferred_dir()` are already deprecated**: Both methods in `scripts/little_loops/config/core.py` already emit `DeprecationWarning` with message `"use IssueInfo.status instead"` — ENH-1417 wired the deprecation as part of adding the `status` field. All call sites in `issue_lifecycle.py`, `issue_parser.py`, and the orchestrator are already flagged.

- **`get_next_issue_number()` in `issue_parser.py` line ~133** also calls deprecated `get_completed_dir()`. This call site is not listed under "Files to Modify" but must be updated in Step 2 alongside `find_issues()`.

- **`_move_issue_to_completed()` helper in `issue_lifecycle.py`** becomes dead code after the lifecycle rewrite — delete it as part of Step 3.

- **Orchestrator `_deferred_issues` (lines 127–128) is in-memory only**: This field tracks overlap-deferred issues (issues held back due to file-scope conflicts in parallel runs). It has no interaction with the filesystem `deferred/` directory — it is populated and cleared entirely in-memory by `_process_issue_parallel()`, `_on_worker_complete()`, and `_requeue_deferred_issues()`. It does **not** need frontmatter reads as part of this issue. The Step 4 orchestrator work is limited to the completion path (lines 1210–1289).

- **`parallel/merge_coordinator.py`** also contains `shutil.move`-equivalent calls for issue movement. Review whether it duplicates the completion path in `orchestrator.py` or is a distinct code path — if it moves issues to `completed/`, it falls in scope.

- **`_batch_completion_dates()` replacement strategy**: This function uses `git log --diff-filter=A` to detect when files were first *added* to the `completed/` directory (i.e., the move commit). Once files no longer move, this approach yields no results. Replacement: use `completed_at:` frontmatter as primary (already priority-1 in `_parse_completion_date()` lines 185–190), with git log on the file itself (without `--diff-filter=A`) as fallback. ENH-1420 handles backfilling old files without `completed_at`.

### Codebase Research Findings — Pass 2 (2026-05-10)

_Added by `/ll:refine-issue` — based on analysis of ENH-1423 and ENH-1424 sibling implementations (both confirmed landed):_

- **Factual correction to Wiring Step 9**: The prior analysis stated `_get_category_from_issue_path()` "uses `get_completed_dir()` / `get_deferred_dir()` path membership (lines 61, 68)". Lines 61 and 68 belong to `_get_all_issue_files()`, not `_get_category_from_issue_path()`. The current `_get_category_from_issue_path()` (`scripts/little_loops/issue_discovery/search.py:312`) uses **filename-prefix matching only** — it is already directory-agnostic. Wiring step 9 scope is therefore limited to `_get_all_issue_files()` only; `_get_category_from_issue_path()` requires no changes.

- **Consequence for `undefer_issue()`**: The call to `_get_category_from_issue_path()` at `issue_lifecycle.py:952` was used to determine where to `git mv` the file. With the frontmatter-only model, there is no file move — `undefer_issue()` becomes `update_frontmatter(path.read_text(), {"status": "open"})` + `path.write_text(...)`. Remove the `_get_category_from_issue_path()` call and the `git mv` at line 976; no replacement needed since the file already lives in its type dir.

- **Canonical implementation patterns from ENH-1423/1424**:
  - Inline filter (use for `find_issues()` and `_get_all_issue_files()`):
    ```python
    fm = parse_frontmatter(issue_file.read_text(encoding="utf-8"))
    if fm.get("status", "open") in ("done", "cancelled", "deferred", "completed"):
        continue
    ```
    See `scripts/little_loops/sync.py:_get_local_issues()` and `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` (lines 173–190).
  - Status write (use for `close_issue()`, `defer_issue()`, `undefer_issue()`):
    ```python
    new_content = update_frontmatter(content, {"status": "done"})
    path.write_text(new_content, encoding="utf-8")
    ```
    See `scripts/little_loops/sync.py:reopen_issues()` (~line 1075) for the confirmed module-level import form.
  - Test fixture (use for all test file updates):
    ```python
    (type_dir / "P1-BUG-001-done.md").write_text("---\nstatus: done\n---\n\n# BUG-001: Done")
    ```
    No `completed/` directory creation. See `scripts/tests/test_sync.py:TestGetLocalIssues` and `scripts/tests/test_sprint_integration.py`.

- **`test_cli.py` partial cleanup by ENH-1423**: ENH-1423 already removed 5 `"completed_dir": "completed"` config dict entries from `test_cli.py`. Only 3 `completed/` references remain (in `TestMainHistoryCoverage` history fixture, lines ~2594–2598) — these are in ENH-1418's history subsystem scope.

- **`conftest.py` shared `issues_dir` fixture confirmed unchanged**: `issues_dir` at line 126 still calls `completed_dir.mkdir()` (line 138) and `deferred_dir.mkdir()` (line 139). ENH-1423 and ENH-1424 did not touch this file. The ENH-1418 scope note in the Tests section remains accurate.

## Scope Boundaries

- **In scope**: `find_issues()` status filter; `close_issue()` / `defer_issue()` / `undefer_issue()` rewrites; parallel orchestrator completion/deferred tracking; `scan_completed_issues()` and `_batch_completion_dates()` redesign; hardcoded `completed/` path fixes in `issue_manager.py` and `cli/history.py`; `capture-issue` skill reopen flow
- **Out of scope**: Core `IssueInfo.status` data model field (ENH-1417 — prerequisite); migration script to backfill `status:` into existing files (ENH-1420); CLI/commands/docs updates (ENH-1421); GitHub sync and sprint orchestration (ENH-1419)

## Implementation Steps

1. Verify ENH-1417 has landed: `IssueInfo.status` field and `DeprecationWarning` on `get_completed_dir()`/`get_deferred_dir()` in `config/core.py` confirm the prerequisite is satisfied.
2. In `issue_parser.py`: replace frozenset-based exclusion in `find_issues()`; also fix `get_next_issue_number()` (~line 133) which calls deprecated `get_completed_dir()`. Import `update_frontmatter` from `scripts/little_loops/frontmatter.py`.
3. **[Atomic commit — do not split]** Rewrite `issue_lifecycle.py` — `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()` — to call `update_frontmatter(path.read_text(), {"status": ...}); path.write_text(...)` (follow pattern in `learning_tests.py:mark_learning_test_stale()`). Delete `_move_issue_to_completed()` helper once all callers are removed. **In the same commit**: rewrite `verify_issue_completed()` to check `IssueInfo.status == "done"` via frontmatter read (see wiring step 8); if these two land separately, `issue_manager.py:_process_single_issue()` will always trigger the fallback double-completion path. Add a test asserting `verify_issue_completed()` returns `True` for an issue with `status: done` frontmatter in its type dir (not in `completed/`) — this test enforces the coupling and will fail if the two are ever separated.
4. Update parallel orchestrator **completion path only** (lines 1210–1289) to write `status: done` to frontmatter instead of moving file. The `_deferred_issues` field (lines 127–128) is in-memory overlap tracking — it does not interact with the filesystem `deferred/` directory and requires no changes here.
5. Redesign `issue_history/parsing.py`: `scan_completed_issues()` → scan type dirs and filter `status: done`; `_batch_completion_dates()` → replace `git log --diff-filter=A` approach with `completed_at:` frontmatter as primary, git log on file (without `--diff-filter=A`) as fallback.
6. Fix hardcoded `completed/` paths in `issue_manager.py:783` and `cli/history.py:199`; update `capture-issue` skill reopen flow to write `status: open` via `update_frontmatter` instead of `git mv`.
7. Update all 7 test files (including removing `suppress_deprecation_warnings` autouse in `test_issue_lifecycle.py`); run `python -m pytest scripts/tests/ -v` to verify no regressions.

## Impact

- **Priority**: P2 — second-priority in ENH-1390 decomposition; blocks full decoupling but can run in parallel with ENH-1419/1421 after ENH-1417 lands
- **Effort**: Large — 7 source files + 7 test files; rewrites core lifecycle, discovery, and history subsystems
- **Risk**: High — rewrites `close_issue()` and `defer_issue()` used by all automation tools; a regression would corrupt issue state during parallel runs
- **Breaking Change**: Yes — files no longer move on status change; any external tooling relying on directory-based status must be updated

## Acceptance Criteria

- `find_issues()` returns only issues with `status: open` (or `in_progress`/`blocked`) regardless of which type dir they live in
- `close_issue()`, `defer_issue()`, `undefer_issue()` write frontmatter, no longer move files
- `scan_completed_issues()` finds done issues by frontmatter in type dirs
- No hardcoded `completed/` or `deferred/` directory paths remain in the above files
- All updated tests pass

## Labels

`enhancement`, `refactor`, `issue-management`, `status-decoupling`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. In `issue_lifecycle.py:verify_issue_completed()`: rewrite to check `IssueInfo.status == "done"` via frontmatter read instead of `get_completed_dir() / file.name` directory existence check — **must be committed atomically with Step 3** (`close_issue()` rewrite); splitting these two causes every successful run to trigger the double-completion fallback in `issue_manager.py:_process_single_issue()` (see Step 3 for the required test that enforces this coupling)
9. In `issue_discovery/search.py:_get_category_from_issue_path()` and `_get_all_issue_files()`: update directory-based status detection (lines 61, 68) — `_get_category_from_issue_path()` is called by `undefer_issue()` and assumes file is physically in `deferred/`; replace with `IssueInfo.status` read; `_get_all_issue_files()` gathers from `completed/`/`deferred/` dirs directly — update to scan type dirs
10. In `parallel/merge_coordinator.py`: remove dead-code paths `_is_lifecycle_file_move()` (line 364), the `_stash_local_changes()` exclusion guard (line 168), and `_commit_pending_lifecycle_moves()` (line 402) — none will ever trigger once the orchestrator completion path uses frontmatter instead of `git mv`
11. Update `hooks/scripts/issue-completion-log.sh`: change PostToolUse trigger from `git mv .+ completed/` pattern to a frontmatter-write detection approach (e.g., write detection on issue files with `status: done`), or trigger via a dedicated hook event — required to preserve session log auto-linking

> **Selected:** Option A (regex-based frontmatter write detection) — reuse the PostToolUse Write pattern from `check-duplicate-issue-id-post.sh`; detect `status: done` in `tool_input.content` via `jq` + `grep`; no IPC bridge required
12. Update 8 additional test files identified in the Tests section above (test_issue_parser.py, test_orchestrator.py, test_issue_workflow_integration.py, test_cli.py, test_issues_cli.py, test_issues_path.py, test_issues_search.py, conftest.py) — all will break due to directory-based test fixtures

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-10 — Pass 3 (ENH-1423 landed; Criterion D upgraded 10→18 as 4 out-of-scope callers eliminated; outcome 62→70)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Wide breadth: 22+ distinct change sites across source, test, hook, and skill files — Breadth sub-criterion 0/12; coordinating 9+ test file updates is the primary execution risk.
- `verify_issue_completed()` serialization constraint: must be rewritten atomically with `close_issue()` (wiring step 8); if decoupled, `issue_manager.py:_process_single_issue()` will always trigger the fallback double-completion path.
- 2 out-of-scope callers remain (`dependency_mapper/operations.py`, `cli/deps.py`) — ENH-1421 scope; will scan `completed/` silently for nothing after ENH-1418 lands. Coordinate landing order with ENH-1421.

## Resolution

Completed 2026-05-10. Issue status decoupled from directory location across discovery, lifecycle, history parsing, and the parallel orchestrator. Issue files now stay in their type directories; status transitions are encoded as `status: <open|done|deferred>` in YAML frontmatter.

**Source changes**:
- `issue_discovery/search.py` — `_get_all_issue_files` scans type dirs and reads frontmatter; `find_issues()` filter switched from filename-pattern exclusion to status-frontmatter filter; `reopen_issue()` writes `status: open` in place (legacy git-mv fallback retained for back-compat).
- `issue_lifecycle.py` — `close_issue`, `complete_issue_lifecycle`, `defer_issue`, `undefer_issue` write `status:` via `update_frontmatter`; `_move_issue_to_completed` and `_cleanup_stale_source` deleted; `verify_issue_completed` reads `status: done` from frontmatter atomically with `close_issue`.
- `issue_parser.py` — `get_next_issue_number` scans only type dirs (legacy `completed/`/`deferred/` ignored for ID allocation); duplicate-skip checks switched from per-file stat to two glob calls.
- `parallel/orchestrator.py` — `_complete_issue_lifecycle_if_needed` writes `status: done` in place; no git mv.
- `parallel/merge_coordinator.py` — `_is_lifecycle_file_move` and `_commit_pending_lifecycle_moves` removed; stash filter cleaned up.
- `issue_history/parsing.py` — `scan_completed_issues(issues_dir, category_dirs=None)` scans type dirs filtered by `status: done`; legacy `completed/` still surfaced; `_batch_completion_dates` stubbed to `{}`; `_parse_completion_date` drops `--diff-filter=A`.
- `issue_manager.py:783`, `cli/history.py` — hardcoded `".issues/completed"` references removed.
- `hooks/scripts/issue-completion-log.sh` — rewritten as PostToolUse Write detector: filters by issue filename pattern, inspects `tool_input.content` for `status: done` in frontmatter, calls `append_session_log_entry` with `hook:posttooluse-status-done` reason. Matcher in `hooks/hooks.json` switched from `Bash` to `Write`.

**Test changes**: 16 test files updated to write `status:` frontmatter in place of physical file moves; classes asserting old move/git-mv behavior were deleted or rewritten. Final tally: 6009 pass, 5 skipped. The 2 pre-existing `test_update_skill::TestMarketplaceVersionSync` failures are unrelated to ENH-1418 (version-sync drift).

**Verification**:
- `python -m pytest scripts/tests/ -q --no-cov` → 6009 pass, 5 skipped, 2 pre-existing unrelated failures.
- `ruff check` on modified Python files → all checks passed.

**Backwards compatibility**: legacy `completed/` and `deferred/` directory paths are still recognized on read paths (`scan_completed_issues`, `reopen_issue`) so projects mid-migration remain queryable. ENH-1420 will backfill old files with `completed_at` and `status:` frontmatter; ENH-1421 will retire the 2 remaining out-of-scope `get_completed_dir`/`get_deferred_dir` callers in `dependency_mapper/operations.py` and `cli/deps.py`.

## Session Log
- `/ll:manage-issue enhancement implement ENH-1418` - 2026-05-10T20:30:19Z - `06a08234-7cc0-4921-8333-cac311b14aae.jsonl`
- `/ll:ready-issue` - 2026-05-10T19:39:55 - `352776de-104b-4d04-8f03-9bcc30f6ad6a.jsonl`
- `/ll:ready-issue` - 2026-05-10T19:39:47 - `6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:confidence-check` - 2026-05-10T21:00:00 - `f40524ce-2922-413f-a399-279fedc232ed.jsonl`
- `/ll:confidence-check` - 2026-05-10T19:20:00 - `ed9a9795-a7b0-47a3-97cf-548f6a30ffc0.jsonl`
- `/ll:refine-issue` - 2026-05-10T19:16:56 - `74aeeec5-fc5d-4f88-a949-3a7e09578427.jsonl`
- `/ll:confidence-check` - 2026-05-10T16:15:00 - `7b93d10a-1270-495b-8f3d-ce1762741200.jsonl`
- `/ll:decide-issue` - 2026-05-10T16:07:06 - `d0789119-e04f-48b3-b529-bba840aad2c2.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `b13a1909-3e87-4e90-8703-a8986abba494.jsonl`
- `/ll:wire-issue` - 2026-05-10T15:59:57 - `1627752a-c16c-41da-904e-698f0b8696ed.jsonl`
- `/ll:refine-issue` - 2026-05-10T15:49:34 - `dfe609fd-21c3-4081-be18-b955d37bfbac.jsonl`
- `/ll:format-issue` - 2026-05-10T15:19:42 - `a80bb47e-7a06-453e-a016-be6695656fd0.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Done** | Created: 2026-05-10 | Completed: 2026-05-10 | Priority: P2
