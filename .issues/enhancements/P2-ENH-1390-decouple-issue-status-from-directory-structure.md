---
id: ENH-1390
type: ENH
priority: P2
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [FEAT-1389, ENH-1391, ENH-1392, ENH-1393]
decision_needed: false
---

# ENH-1390: Decouple Issue Status from Directory Structure

## Summary

Remove `deferred/` and `completed/` as lifecycle-state directories. Encode status exclusively in issue frontmatter (`status:` field). Keep type directories (`features/`, `bugs/`, `enhancements/`) since type is stable and aids human navigation. This eliminates the fundamental mixing of *type* and *state* in the directory structure that breaks sync compatibility with all major platforms.

## Current Behavior

The `.issues/` directory mixes two orthogonal concerns:

- **Type directories** (stable): `features/`, `bugs/`, `enhancements/`
- **State directories** (volatile): `deferred/`, `completed/`

Moving an issue to `deferred/` or `completed/` requires a file rename/move, which: (a) breaks git blame/log continuity, (b) requires sync tools to detect moves rather than status field changes, and (c) is inconsistent with how every major platform represents state (GitHub open/closed, JIRA status field, ADO state field, Linear status field).

## Expected Behavior

- `deferred/` and `completed/` directories are removed as active-use state containers
- All issues live in their type directory (`features/`, `bugs/`, `enhancements/`, `epics/`) for their entire lifecycle
- Status is tracked exclusively via `status: open | in_progress | blocked | deferred | done | cancelled` in frontmatter
- `ll-issues list` supports `--status deferred` and `--status done` filters
- `ll-auto`, `ll-sprint`, and `ll-parallel` filter by `status: open` rather than directory inclusion
- Existing files in `deferred/` and `completed/` are migrated to their type directories with `status:` set appropriately

## Motivation

- **Git history**: A status change should be a frontmatter edit, not a file move. `git log --follow` can track renames but it's lossy and tooling-dependent.
- **Sync compatibility**: All platforms (GitHub, JIRA, ADO, Linear) represent status as a field, never as a file location. `ll-sync` currently has to detect directory moves to update remote status; with status in frontmatter it becomes a simple field diff.
- **Consistency**: The current model is internally inconsistent — issues start in a type directory, get moved to a state directory, and there's no single canonical location. "Where is issue 1073?" requires checking multiple directories.
- **EPIC support**: With the addition of EPIC type (FEAT-1389), epics need their own lifecycle (deferred epics should stay in `epics/`, not move to `deferred/`).

## Proposed Solution

1. Extend the `status:` frontmatter field with the full vocabulary: `open | in_progress | blocked | deferred | done | cancelled`
2. Update all tooling to filter by `status:` instead of directory:
   - `ll-auto` and `ll-sprint`: process issues where `status: open`
   - `ll-issues list`: default to showing `open` + `in_progress`; `--status all` shows everything
3. Migrate existing files: move all files from `deferred/` into their type directories with `status: deferred`; move `completed/` files with `status: done`
4. Keep `completed/` and `deferred/` as empty archived directories (or remove entirely) after migration
5. Update all documentation, skills, and commands that reference `deferred/` or `completed/` paths

## API/Interface

Extension to issue frontmatter `status:` field vocabulary:

```yaml
# Extended status enum (new values: in_progress, blocked, done, cancelled)
status: open | in_progress | blocked | deferred | done | cancelled
```

`ll-issues list` CLI argument:

```
ll-issues list [--status <open|in_progress|blocked|deferred|done|cancelled|all>]
# Default (no flag): shows open + in_progress
```

## Scope Boundaries

- **In scope**: Extending `status:` frontmatter enum; updating issue discovery in `issue_manager.py`, `ll-auto`, `ll-sprint`, `ll-parallel` to filter by `status:` field; migrating existing files from `deferred/` and `completed/`; updating `ll-issues list` with `--status` filter; updating docs, skills, and commands referencing state directories
- **Out of scope**: Changing type directories (`features/`, `bugs/`, `enhancements/`) or their role; redesigning `ll-sync` protocol beyond status field mapping; building a status visualization UI; changing issue filename format or ID scheme

## Success Metrics

- **Migration**: 0 files lost from `deferred/` or `completed/` during migration; all migrated files have correct `status:` set (`deferred` or `done`)
- **Discovery**: `ll-auto`, `ll-sprint`, and `ll-parallel` process `status: open` issues and skip `status: deferred` / `status: done` issues
- **Sync**: `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- **Regression**: All existing tests pass; no issue discovery regressions across tools

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — filter by `status:` field, not directory
- `scripts/little_loops/cli/issues.py` — `list` command status filtering
- `scripts/little_loops/parallel/` — worktree/parallel runner issue discovery
- `skills/capture-issue/SKILL.md` — remove `deferred/` reopen flow (replace with status field update)
- `scripts/little_loops/cli/sync.py` — status mapping from field instead of directory
- `docs/ARCHITECTURE.md`, `docs/reference/API.md` — update directory structure docs
- `config-schema.json` — add `status` enum to issue schema

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `get_completed_dir()` and `get_deferred_dir()` methods on `BRConfig` must be deprecated/removed; `create_parallel_config()` serializes `completed_dir`/`deferred_dir` at lines 387-388
- `scripts/little_loops/config/features.py` — `IssuesConfig.completed_dir` and `IssuesConfig.deferred_dir` fields and `from_dict()` parsing must be removed/deprecated
- `scripts/little_loops/issue_history/parsing.py` — `scan_completed_issues()` and `_batch_completion_dates()` take `completed_dir: Path`; completion-date strategy (git-log on file moves) is fundamentally incompatible with frontmatter-only approach — needs redesign

### Migration Script Needed
- One-time script to move files from `deferred/` and `completed/` into type directories with correct `status:` frontmatter

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_parser.py` — `find_issues()` builds frozensets of filenames in `completed/`/`deferred/` dirs to exclude; `get_next_issue_number()` scans all dirs including those two; `IssueParser.parse_file()` does **not** read `status:` field — `IssueInfo` dataclass has no `status` attribute
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()` all move files physically to `completed/` or `deferred/` dirs; each calls `config.get_completed_dir()` / `config.get_deferred_dir()`
- `scripts/little_loops/issue_discovery/search.py` — `_get_all_issue_files()` returns `(Path, is_completed: bool)` tuples derived from which directory a file was loaded from (not from frontmatter)
- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields()` derives status from `path.parent.name` (`"completed"` → `"Completed"`, `"deferred"` → `"Deferred"`, else `"Open"`); `_resolve_issue_id()` searches active → completed → deferred dirs in sequence
- `scripts/little_loops/cli/issues/search.py` — `_load_issues_with_status()` maps directory location to status string (`"active"`, `"completed"`, `"deferred"`); `cmd_search()` accepts `--status active|completed|deferred|all`
- `scripts/little_loops/cli/auto.py` — delegates to `AutoManager` which calls `find_issues()` (directory-scoped); no additional status filter
- `scripts/little_loops/cli/sprint/run.py` — pre-validates each sprint issue by checking `config.get_completed_dir().glob(f"*-{issue_id}-*.md")` before processing
- `scripts/little_loops/cli/sprint/edit.py` — completed issue lookup via `get_completed_dir()`
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator` moves completed issues to `completed/` dir after worker merge (lines 1210-1289); tracks `_deferred_issues` for in-progress deferral (lines 127-128, 1000-1017)
- `scripts/little_loops/sync.py` — `GitHubSyncManager._get_local_issues()`, `close_issues()`, `reopen_issues()`, `_find_local_issue()` all determine status from directory location; `close_issues --all-completed` scans `get_completed_dir()` directly
- `scripts/little_loops/cli/deps.py` — excludes `completed/` and `deferred/` dirs from dependency analysis
- `scripts/little_loops/dependency_mapper/operations.py` — excludes `"completed"` and `"deferred"` dir name strings from file-hint analysis
- `scripts/little_loops/issue_manager.py:783` — **hardcoded** `(config.repo_path or Path.cwd()) / ".issues" / "completed"` glob (bypasses `get_completed_dir()`)
- `scripts/little_loops/cli/history.py:199` — **hardcoded** `issues_dir / "completed"` path (bypasses `get_completed_dir()`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/show.py` — tracks `completed_issues` in sprint summary data; will need frontmatter-based filtering
- `scripts/little_loops/cli/issues/count_cmd.py` — `--status active|completed|deferred` choices reference old directory vocabulary; must align with new status enum

### Similar Patterns
- `ll-issues path` and `ll-issues show` — may use directory-based lookups; check for consistency
- Any skill referencing `config.issues.completed_dir` or `config.issues.deferred_dir` config keys

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_issue_parser.py` — `TestIssueParser` uses `temp_project_dir` + `sample_config` fixtures; will need `status:` field assertions in `parse_file()` tests and `find_issues()` filtering tests
- `scripts/tests/test_issue_lifecycle.py` — `TestCloseIssue`, `TestCompleteIssueLifecycle` — `sample_config` fixture creates `completed_dir`/`deferred_dir`; extensive updates needed to assert on frontmatter writes instead of file moves
- `scripts/tests/test_issue_discovery.py` — `issues_with_content` fixture creates files in both `bugs/` and `completed/`; tests directory-based discovery; needs refactoring to test status-field-based discovery from type dirs only
- `scripts/tests/test_issues_cli.py` — `ll-issues list` and `ll-issues show` tests; needs `--status open|deferred|done|all` filter tests
- `scripts/tests/test_issues_path.py` — `_resolve_issue_id()` path lookup across active → completed → deferred; must handle type-dir-only lookups post-migration
- `scripts/tests/test_sprint.py`, `test_sprint_integration.py` — cover sprint runner's `get_completed_dir()` pre-validation; update to test `status: done` frontmatter check
- `scripts/tests/test_orchestrator.py` — parallel orchestrator completion move tests (lines 1210-1289 coverage); update to assert frontmatter write, not file move
- `scripts/tests/test_sync.py` — `GitHubSyncManager` directory-to-remote-state mapping; update to test `IssueInfo.status` field mapping
- `scripts/tests/conftest.py` — `temp_project_dir` + `sample_config` fixtures include `"completed_dir": "completed"` and `"deferred_dir": "deferred"` keys; add `status: open` to fixture issue file content
- **New**: add migration script test in `scripts/tests/test_issue_migration.py` — fixture with files in `deferred/` and `completed/`; assert all files land in type dirs with correct `status:` frontmatter

_Wiring pass added by `/ll:wire-issue`:_

**Tests to update (not in prior known list — will break):**
- `scripts/tests/test_config.py` — `TestBRConfig::test_get_completed_dir` and `test_get_deferred_dir` assert on removed methods; `TestIssuesConfig::test_from_dict_with_all_fields` and `test_from_dict_with_defaults` assert on `completed_dir`/`deferred_dir` fields; update or remove
- `scripts/tests/test_issues_search.py` — `TestSearchStatusFilter::test_include_completed`, `test_status_all`, `test_status_completed_only`, `test_text_query_with_include_completed` use directory placement with no `status:` frontmatter; will break after status moves to frontmatter
- `scripts/tests/test_issue_history_parsing.py` — `scan_completed_issues()` coupling; also provides migration test pattern in `TestParseCompletedIssue::test_parse_with_frontmatter`; update for new frontmatter-based completion-date strategy
- `scripts/tests/test_issue_history_cli.py` — ~40 references to `completed/` directory; every test creates `tmp_path / ".issues" / "completed"` to populate `scan_completed_issues()`; update for new approach
- `scripts/tests/test_merge_coordinator.py` — uses `git mv` to simulate parallel orchestrator completion flow; ~15 references to `completed/` dir; update to assert frontmatter write
- `scripts/tests/test_cli_output.py` — mocks `get_completed_dir` and `get_deferred_dir` as lambdas at line 291-292; update or remove mocks
- `scripts/tests/test_feat1172_doc_wiring.py` — `test_completed_at_row_describes_completed_dir` asserts docs mention `completed` directory; update for new status field documentation
- `scripts/tests/test_issue_manager.py` — `TestPathRenameHandling::test_path_rename_updates_tracking` constructs `IssueInfo` without `status` field; update when field is added to dataclass
- `scripts/tests/test_dependency_mapper.py` — `TestValidateDependencies::test_stale_completed_ref` and `test_valid_with_completed_blocker` call `validate_dependencies(issues, completed_ids={"FEAT-001"})`; update API call after directory-based `completed_ids` is replaced
- `scripts/tests/test_refine_status.py` — ~20 test methods create `completed/`/`deferred/` dirs in setup (dead code after directories are eliminated); clean up setup blocks

### Documentation
- `docs/ARCHITECTURE.md` — remove state directories from directory structure diagram
- `docs/reference/API.md` — update `status` field documentation and valid values
- `skills/format-issue/SKILL.md`, `skills/ready-issue/SKILL.md` — remove references to `completed_dir`/`deferred_dir`

_Wiring pass added by `/ll:wire-issue`:_

**From codebase research findings — present in step 7 but missing from Integration Map docs section:**
- `docs/reference/CONFIGURATION.md` — documents `completed_dir`/`deferred_dir` in the `issues` section table with example JSON; update to document new `status` field approach
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — CRITICAL: contains "Directory location determines CLI bucketing. Tools like `ll-issues list`, `ll-auto`, and `ll-sprint` filter issues by directory … not by the `status` field" — directly contradicts ENH-1390's goal; lifecycle diagram and frontmatter status table both need full rewrites
- `skills/manage-issue/SKILL.md` — CRITICAL: lines 450-466 have `CRITICAL: Move to {{config.issues.completed_dir}}/` with `git mv` examples; replace with frontmatter update instructions
- `skills/init/SKILL.md` — line 148 references `issues.completed_dir` in config generation logic
- `skills/init/interactive.md` — lines 248, 342 reference `completed_dir` in config generation instructions

**Commands with directory-based shell patterns (not previously listed — all need updating):**
- `commands/normalize-issues.md` — ~30 references to `completed/`/`deferred/` directories throughout checks and auto-fix scripts; foundational to ENH-1390's goal
- `commands/manage-release.md` — CRITICAL: uses `git log --diff-filter=A … -- .issues/completed/` to enumerate issues in a release; must change to frontmatter-based approach after file moves are eliminated
- `commands/review-sprint.md` — `completed/` directory glob references; update to frontmatter filter
- `commands/tradeoff-review-issues.md` — 6 references to `{{config.issues.completed_dir}}/` for exclusion and as destination for closed issues
- `commands/align-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"` shell exclusion pattern
- `commands/create-sprint.md` — excludes `/completed/` and `/deferred/` path segments; checks blocker membership in completed dir
- `commands/prioritize-issues.md` — excludes `completed/`/`deferred/` from scanning
- `commands/verify-issues.md` — shell `find` with `-not -path "*/completed/*"`; move instructions to `completed/`
- `commands/sync-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"`
- `commands/ready-issue.md` — checks blocker membership in `completed/` directory
- `commands/audit-architecture.md` — references `completed/` directory in shell patterns
- `commands/refine-issue.md` — line 29 reference to `{{config.issues.completed_dir}}`
- `.claude/CLAUDE.md` — Key Directories section shows `completed/` as a routing subdirectory

### Configuration
- `config-schema.json` — extend `status` enum; deprecate or remove `completed_dir` and `deferred_dir` keys
- `.ll/ll-config.json` — `issues.completed_dir` and `issues.deferred_dir` settings become obsolete post-migration

## Implementation Steps

1. Extend `status:` enum in schema and validation: `open | in_progress | blocked | deferred | done | cancelled`
2. Update `issue_manager.py` issue discovery to filter on `status: open` instead of excluding `deferred/` and `completed/` directories
3. Update `ll-issues list` to support `--status <value>` filter; default view shows open/in_progress
4. Write and run migration script for existing `deferred/` and `completed/` files
5. Update `capture-issue` skill: "reopen completed issue" becomes a `status:` field update, not a file move
6. Update `ll-sync` to read `status:` field for open/closed mapping
7. Remove `deferred/` and `completed/` from ARCHITECTURE.md and other docs
8. Update tests that assert on directory paths

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors for each step above:_

- **Step 1 — schema + `IssueInfo`**: Add `status: str = "open"` field to `IssueInfo` dataclass in `issue_parser.py`; read `frontmatter.get("status", "open")` in `IssueParser.parse_file()` (same int/bool coercion pattern used for `decision_needed`). Extend `status` enum in `config-schema.json`. The `update_frontmatter()` function in `scripts/little_loops/frontmatter.py` is the correct write path.
- **Step 2 — `find_issues()` filter**: In `issue_parser.py:find_issues()`, replace the frozenset-based filename exclusion (`completed_names`, `deferred_names`) with a post-parse filter: `if info.status in ("done", "deferred", "cancelled"): continue`. Also fix the **hardcoded** `".issues/completed"` path at `issue_manager.py:783` to use `info.status == "done"` instead.
- **Step 3 — `ll-issues list`**: Update `cli/issues/search.py:_load_issues_with_status()` to read `status:` from parsed frontmatter instead of deriving from directory. Update `cmd_search()` status string values from `"active"/"completed"/"deferred"` to the full vocab. Update `cli/issues/show.py:_parse_card_fields()` to read `info.status` instead of checking `path.parent.name`.
- **Step 4 — migration**: Call `update_frontmatter(path, {"status": "done"})` for files in `completed/`; `update_frontmatter(path, {"status": "deferred"})` for files in `deferred/`; then move each file into its type dir. ~60 files at risk. Also fix **hardcoded** `cli/history.py:199` path to not rely on `completed/` dir.
- **Step 5 — lifecycle operations**: Update `issue_lifecycle.py:close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()` to write `status:` via `update_frontmatter()` instead of `shutil.move`. Update `parallel/orchestrator.py` completion path (lines 1210-1289) the same way.
- **Step 6 — sync**: Update `sync.py:GitHubSyncManager._get_local_issues()` to scan all type dirs; use `IssueInfo.status` to map to GitHub open/closed. Update `close_issues()` and `reopen_issues()` to read `status:` field rather than directory.
- **Step 7 — docs**: `docs/ARCHITECTURE.md` (lines 41-59), `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `skills/capture-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/init/SKILL.md`, `config-schema.json` (`completed_dir`/`deferred_dir` deprecation).
- **Step 8 — tests**: Core files requiring updates: `test_issue_parser.py`, `test_issue_lifecycle.py`, `test_issue_discovery.py`, `test_issues_cli.py`, `test_orchestrator.py`, `test_sync.py`. Shared fixture in `conftest.py:sample_config` adds `"completed_dir"`/`"deferred_dir"` to fixture data — keep during migration, remove after. Test pattern: use `temp_project_dir` + inline frontmatter with `status: open` field (see `test_issue_history_parsing.py:TestParseCompletedIssue` for the `tmp_path` write pattern).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/config/core.py` — deprecate/remove `get_completed_dir()` and `get_deferred_dir()` methods; update `create_parallel_config()` to remove `completed_dir`/`deferred_dir` from serialized output (lines 387-388)
10. Update `scripts/little_loops/config/features.py` — remove/deprecate `completed_dir: str` and `deferred_dir: str` from `IssuesConfig` dataclass and `from_dict()` parsing; update `config-schema.json` to mark both as deprecated/removed
11. Update `scripts/little_loops/issue_history/parsing.py` — redesign `scan_completed_issues()` and `_batch_completion_dates()` to use frontmatter `status: done` rather than directory location; the completion-date strategy (reading git log on file moves into `completed/`) must be replaced with a frontmatter-based approach (e.g., `completed_at:` frontmatter field)
12. Update all commands in `commands/` that reference `completed/`/`deferred/` shell paths — 13 command files identified; `commands/normalize-issues.md` and `commands/manage-release.md` require the most significant logic changes
13. Update `skills/manage-issue/SKILL.md` — replace `git mv` to `completed/` instructions (lines 450-466) with frontmatter `status: done` update instructions; similarly update `skills/init/SKILL.md` and `skills/init/interactive.md`
14. Update additional test files not in the original test plan: `test_config.py`, `test_issues_search.py`, `test_issue_history_parsing.py`, `test_issue_history_cli.py`, `test_merge_coordinator.py`, `test_cli_output.py`, `test_feat1172_doc_wiring.py`, `test_issue_manager.py`, `test_dependency_mapper.py`, `test_refine_status.py`

## Impact

- **Priority**: P2 — prerequisite for meaningful `ll-sync` and EPIC support
- **Effort**: Medium — code changes are straightforward; migration of ~60 existing files is the main risk
- **Risk**: Medium — touches all tooling that does issue discovery; comprehensive test coverage needed before migration

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `migration`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-05-10T14:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a376d2-9151-49b7-8e68-34248e20fb85.jsonl`
- `/ll:refine-issue` - 2026-05-10T14:40:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a256e37f-c7eb-492b-a32d-7b20fd8a9be6.jsonl`
- `/ll:format-issue` - 2026-05-09T20:39:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf87852d-ec5b-4a4d-959f-57a040534f19.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
