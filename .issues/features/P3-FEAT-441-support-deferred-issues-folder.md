---
discovered_date: 2026-02-18
discovered_by: capture-issue
confidence_score: 85
outcome_confidence: 56
---

# FEAT-441: Support Deferred Issues Folder

## Summary

Add a `.issues/deferred/` folder as a holding ground for issues that are intentionally set aside — not ready for active work but not closed. Deferred issues must not be counted in Open/Active Issues or Completed Issues by any CLI tool or skill that aggregates issue counts.

## Current Behavior

Issues can only exist in three active directories (`bugs/`, `features/`, `enhancements/`) or `completed/`. There is no intermediate state for issues that are intentionally set aside. Users who want to "park" an issue must either close it (falsely implying resolution) or leave it in the active backlog, where it pollutes sprint planning, prioritization runs, and issue counts.

## Expected Behavior

A `.issues/deferred/` directory serves as a holding ground for parked issues. All CLI tools, skills, and count-reporting commands treat `deferred/` as non-active (same pattern as `completed/`): skipped by `ll-auto`, `ll-sprint`, `ll-parallel`, and all issue enumeration. Users can move issues to deferred via `manage-issue defer [ID]` and restore them via `manage-issue undefer [ID]`.

## Motivation

Currently, there is no way to "park" an issue without either closing it (implying it's resolved) or leaving it in an active folder (implying it's ready to work on). A deferred state lets users set aside low-priority, blocked, or uncertain issues without polluting the active backlog or losing the context they've captured.

## Use Case

A user discovers a potential improvement but cannot work on it until a dependency ships. They want to keep the issue for reference without it appearing in sprint planning, prioritization runs, or active issue counts. They run `/ll:manage-issue defer FEAT-441` and the issue moves to `.issues/deferred/` where it's ignored by `ll-auto`, `ll-sprint`, `ll-parallel`, and all count-reporting tools.

## Acceptance Criteria

- [ ] `.issues/deferred/` directory is created (with `.gitkeep`) as part of this feature
- [ ] `ll-auto`, `ll-sprint`, `ll-parallel` skip issues in `deferred/` by default
- [ ] All skill/command issue enumeration excludes `deferred/` (same pattern as `completed/`)
- [ ] `manage-issue defer [ID]` moves an issue from its active directory to `deferred/`
- [ ] `manage-issue undefer [ID]` moves an issue from `deferred/` back to its original category directory
- [ ] `capture-issue` duplicate detection optionally surfaces deferred issues as candidates for un-deferral
- [ ] `ll-history`, `ll-next-id`, and count-reporting tools exclude deferred from active counts
- [ ] Documentation updated in `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `README.md`

## Architecture Notes

_Added by `/ll:refine-issue` — based on codebase analysis:_

The exclusion of non-active directories is **NOT a single mechanism** — it works through two complementary patterns:

1. **Implicit exclusion by omission**: `find_issues()` iterates only `config.issue_categories` (bugs, features, enhancements). Any directory NOT in categories is automatically excluded from active scanning. This means `deferred/` gets excluded from `ll-auto`, `ll-parallel`, `ll-sprint`, and all `find_issues()` callers without any code change — simply by not adding it to categories.

2. **Explicit add-back for ID uniqueness**: `get_next_issue_number()` and `gather_all_issue_ids()` explicitly add `completed/` back to their scan lists to ensure ID uniqueness and dependency validation. `deferred/` **must be added to these same explicit lists** — otherwise deferred issue IDs could be reassigned to new issues.

This dual-mechanism pattern means the implementation has two tiers of changes:
- **Tier 1 (Automatic)**: Any tool using `find_issues()` already excludes deferred — no change needed
- **Tier 2 (Explicit)**: Functions that manually build directory lists to scan must add `deferred/`

## Proposed Solution

1. Create `.issues/deferred/` as a recognized issue directory (alongside `bugs/`, `features/`, `enhancements/`, `completed/`).
2. Update all CLI tools and skills that enumerate active issues to exclude `deferred/` (same pattern used to exclude `completed/`).
3. Add a `defer` action to `manage-issue` (and optionally `ll-auto`/`ll-sprint`) to move an issue into `deferred/`.
4. Add an `undefer` action to move an issue back to its original category directory.
5. Update count-reporting commands (`ll-history`, `capture-issue` duplicate scan, `prioritize-issues`, etc.) to exclude the deferred folder.
6. Document the deferred state in `docs/ARCHITECTURE.md` and `CONTRIBUTING.md`.

## Implementation Steps

### Phase 1: Config & Directory Setup

1. **Create `.issues/deferred/` directory** with `.gitkeep`.
2. **Add `deferred_dir` field to `IssuesConfig`** — `config.py:101`: add `deferred_dir: str = "deferred"` after `completed_dir`. Update `from_dict()` at line 126: `deferred_dir=data.get("deferred_dir", "deferred")`.
3. **Add `get_deferred_dir()` method to `BRConfig`** — `config.py:503-505`: add method mirroring `get_completed_dir()`: `return self.project_root / self._issues.base_dir / self._issues.deferred_dir`.
4. **Add `deferred_dir` to `to_dict()` serialization** — `config.py:651-660`: add `"deferred_dir": self._issues.deferred_dir` alongside `"completed_dir"`.
5. **Update `config-schema.json`** — add `deferred_dir` field with default `"deferred"`.

### Phase 2: ID Uniqueness & Dependency Scanning (Tier 2 explicit add-backs)

6. **Update `get_next_issue_number()`** — `issue_parser.py:62-64`: add `dirs_to_scan.append(config.get_deferred_dir())` after the completed dir line.
7. **Update `gather_all_issue_ids()`** — `dependency_mapper.py:1005-1008`: add `config.get_deferred_dir().name` to the config-driven subdirs list; add `"deferred"` to the hardcoded fallback list.
8. **Update `_load_issues()`** — `dependency_mapper.py:1053-1064`: add deferred dir scanning alongside completed dir scanning for dependency validation.

### Phase 3: Active Issue Exclusion (Tier 1 — mostly automatic)

9. **Update `find_issues()` pre-flight check** — `issue_parser.py:526-529`: add deferred pre-flight check alongside completed check (skip if `deferred_path.exists()`).
10. **Update `_get_all_issue_files()`** — `issue_discovery/search.py:57-61`: add `include_deferred` parameter and deferred dir scanning branch (for duplicate detection / un-deferral candidates).

### Phase 4: Defer/Undefer Actions

11. **Add `defer_issue()` function** — `issue_lifecycle.py`: model after `close_issue()` at line 524. Pattern: resolve deferred path → safety checks → append `## Deferred` section → `git mv` → commit.
12. **Add `undefer_issue()` function** — `issue_lifecycle.py`: model after `reopen_issue()` at `issue_discovery/search.py:294-371`. Pattern: determine target category via `_get_category_from_issue_path()` → safety check → append `## Undeferred` section → `git mv` back → commit.
13. **Add `defer`/`undefer` actions to `skills/manage-issue/SKILL.md`** — add to Arguments section alongside existing actions; update directory structure diagram to include `deferred/`.

### Phase 5: Hook & Skill Updates

14. **Update `hooks/scripts/check-duplicate-issue-id.sh`** — this shell hook independently scans issue directories for duplicate IDs; must include `deferred/` in its scan.
15. **Update `skills/init/SKILL.md`** — project initialization must create `.issues/deferred/` alongside other directories.
16. **Update `skills/capture-issue/SKILL.md`** — bash loop at line 149-156 already skips `completed_dir` by name; add parallel skip for `deferred_dir`. Optionally surface deferred issues as un-deferral candidates.
17. **Update commands with bash issue-enumeration loops** — `commands/normalize-issues.md`, `commands/prioritize-issues.md`, `commands/verify-issues.md`, `commands/scan-codebase.md`: each has a directory loop that needs `deferred/` added to skip logic.

### Phase 6: Tests

18. **Add config tests** — `test_config.py`: add `test_get_deferred_dir()` mirroring `test_get_completed_dir()` at line 375-383. Update `sample_config` fixture to include `deferred_dir`.
19. **Add lifecycle tests** — `test_issue_lifecycle.py`: add `TestDeferIssue` and `TestUndeferIssue` test classes mirroring `TestMoveIssueToCompleted` at line 264-435 and `TestCloseIssue`.
20. **Add parser tests** — `test_issue_parser.py`: verify `get_next_issue_number()` includes deferred dir; verify `find_issues()` excludes deferred issues.

### Phase 7: Documentation & Templates

21. **Update documentation** — `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`.
22. **Optionally update template files** — 9 files in `templates/*.json` define default configs; consider adding `deferred_dir` default.
23. **Run `python -m pytest scripts/tests/ -v`** to verify all tests pass.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — exclude deferred from active issue enumeration
- `scripts/little_loops/cli.py` / CLI entry points — add defer/undefer subcommands
- `scripts/little_loops/sprint_manager.py` — skip deferred issues
- `scripts/little_loops/orchestrator.py` — skip deferred issues
- `skills/capture-issue/SKILL.md` — update duplicate scan logic
- `skills/manage-issue/SKILL.md` — add defer/undefer actions
- `config-schema.json` — document deferred dir
- `docs/ARCHITECTURE.md` — document issue lifecycle states
- `CONTRIBUTING.md` — document deferred folder

### Dependent Files (Callers/Importers)

**Core exclusion via `config.get_completed_dir()` — add parallel `get_deferred_dir()` and update all callers:**
- `scripts/little_loops/config.py:101` — `IssuesConfig.completed_dir` field (default `"completed"`); add `deferred_dir: str = "deferred"` here; add `get_deferred_dir()` at line ~503 alongside `get_completed_dir()`
- `scripts/little_loops/issue_parser.py:62` — builds `dirs_to_scan` using `get_completed_dir()`; add `get_deferred_dir()` exclusion here
- `scripts/little_loops/issue_lifecycle.py:418,550,620` — three calls to `get_completed_dir()` for issue completion/archival; add `defer`/`undefer` actions here
- `scripts/little_loops/dependency_mapper.py:1006,1054` — uses `get_completed_dir()` in `gather_all_issue_ids` and `_load_issues`; also hardcoded fallback at line 1008: `subdirs = ["bugs", "features", "enhancements", "completed"]` — add `"deferred"` to exclusion, not to `subdirs`
- `scripts/little_loops/parallel/orchestrator.py:1028` — calls `get_completed_dir()` when moving completed issues
- `scripts/little_loops/sync.py:284` — calls `get_completed_dir()` during sync; line 645 has hardcoded `category_map` (`"BUG": "bugs"`, etc.) — deferred is not a category so no change needed here
- `scripts/little_loops/issue_discovery/search.py:58` — uses `get_completed_dir()` in `include_completed` guard
- `scripts/little_loops/cli/sprint/edit.py:74` — calls `manager.config.get_completed_dir()`

**Hardcoded fallback lists (must be updated alongside config changes):**
- `scripts/little_loops/issue_history/parsing.py:343` — `for category_dir in category_dirs or ["bugs", "features", "enhancements"]` — deferred should not be added here (active-only fallback is correct)
- `scripts/little_loops/cli/history.py:105` — `completed_dir = issues_dir / "completed"` hardcoded (bypasses config) — low priority, deferred not a concern here

**New skill actions (defer/undefer):**
- `skills/manage-issue/SKILL.md` — add `defer` and `undefer` action handling

**Hooks (independently scans issue directories):**
- `hooks/scripts/check-duplicate-issue-id.sh` — reads `issues.base_dir` from config, scans all issue directories for duplicate IDs; must include `deferred/` in its scan

**Project initialization:**
- `skills/init/SKILL.md` — sets up `.issues/` directory structure during `/ll:init`; must create `deferred/` alongside other directories
- `skills/init/interactive.md` — interactive init flow, references directory creation

**Config serialization:**
- `scripts/little_loops/config.py:651-660` — `to_dict()` must include `"deferred_dir": self._issues.deferred_dir`

**Undefer template (existing inverse pattern):**
- `scripts/little_loops/issue_discovery/search.py:294-371` — `reopen_issue()` moves from `completed/` back to active category; exact template for `undefer_issue()`, uses `_get_category_from_issue_path()` to determine target directory

**Commands with bash issue-enumeration loops:**
- `commands/normalize-issues.md` — normalizes issues across directories; bash loop needs `deferred/` skip
- `commands/prioritize-issues.md` — scans issue directories for prioritization; bash loop needs `deferred/` skip
- `commands/verify-issues.md` — scans all directories for verification; bash loop needs `deferred/` skip
- `commands/scan-codebase.md` — references `.issues/` structure; bash loop needs `deferred/` skip

**Template files (optional — default config for new projects):**
- `templates/generic.json`, `templates/python-generic.json`, `templates/javascript.json`, `templates/typescript.json`, `templates/rust.json`, `templates/go.json`, `templates/java-gradle.json`, `templates/java-maven.json`, `templates/dotnet.json` — 9 templates define default issue config; consider adding `deferred_dir` default

### Similar Patterns
- `completed/` exclusion logic throughout codebase — see Architecture Notes for the dual-mechanism pattern
- `reopen_issue()` at `search.py:294-371` — direct template for `undefer_issue()` implementation
- `close_issue()` at `issue_lifecycle.py:524-600` — direct template for `defer_issue()` implementation
- `_move_issue_to_completed()` at `issue_lifecycle.py:285-346` — generalize to `_move_issue()` for both defer and complete

### Tests
- `scripts/tests/test_config.py:375-383` — `test_get_completed_dir()` fixture and assertion pattern to model `test_get_deferred_dir()`
- `scripts/tests/test_issue_lifecycle.py:264-435` — `TestMoveIssueToCompleted` class to model `TestDeferIssue`
- `scripts/tests/test_issue_lifecycle.py:68-100` — `sample_config` fixture needs `deferred_dir` added
- `scripts/tests/test_issue_parser.py` — add tests for `get_next_issue_number()` including deferred; `find_issues()` excluding deferred
- `scripts/tests/test_dependency_mapper.py` — verify `gather_all_issue_ids()` includes deferred dir

### Documentation
- `docs/ARCHITECTURE.md` — issue lifecycle and directory structure
- `docs/reference/CONFIGURATION.md` — configuration reference for `deferred_dir`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — issue management workflow
- `CONTRIBUTING.md` — development guidelines

### Configuration
- `config-schema.json` — add `deferred_dir` field (default: `deferred`)

## API/Interface

```python
# Issue lifecycle: open -> deferred -> open (undefer) | open -> completed
# New CLI usage:
#   ll-auto --exclude-deferred  (default behavior)
#   manage-issue defer FEAT-441
#   manage-issue undefer FEAT-441
```

## Impact

- **Priority**: P3 — Reduces backlog noise; no blocking impact on current work
- **Effort**: Medium — Touches multiple CLI tools, skills, and documentation
- **Risk**: Low — Additive change; deferred folder is simply excluded like completed
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Issue lifecycle and directory structure |
| `CONTRIBUTING.md` | Development guidelines |
| `.claude/CLAUDE.md` | Issue file format and directory layout |

## Labels

`feature`, `issue-management`, `cli`, `backlog`

---

## Verification Notes

_Verified: 2026-02-22_

**Integration Map file paths corrected:**

Three paths listed under "Files to Modify" do not exist at the stated locations:

| Listed Path | Actual Path |
|-------------|-------------|
| `scripts/little_loops/cli.py` | `scripts/little_loops/cli/` (package directory — entry points are `cli/auto.py`, `cli/sprint.py`, `cli/parallel.py`, etc.) |
| `scripts/little_loops/sprint_manager.py` | `scripts/little_loops/sprint.py` (core sprint logic) + `scripts/little_loops/cli/sprint.py` (CLI entry point) |
| `scripts/little_loops/orchestrator.py` | `scripts/little_loops/parallel/orchestrator.py` |

All other referenced files exist at their stated paths.

## Session Log
- `/ll:capture-issue` - 2026-02-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28564d89-65ed-40b1-b496-7da3bcf0a373.jsonl`
- `/ll:verify-issues` - 2026-02-22 - verification pass
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl`
- `/ll:refine-issue` - 2026-02-25T22:34:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf1e5cf2-abf0-465a-9c17-15531b269901.jsonl`
- `/ll:manage-issue` - 2026-02-25 - implementation

## Resolution

**Status**: Completed
**Date**: 2026-02-25
**Action**: implement

### Changes Made

**Core Python (6 files)**:
- `config.py`: Added `deferred_dir` field to `IssuesConfig`, `get_deferred_dir()` to `BRConfig`, `to_dict()` serialization
- `issue_parser.py`: Added deferred dir to `get_next_issue_number()` scan, deferred pre-flight check in `find_issues()`
- `issue_lifecycle.py`: Added `defer_issue()` and `undefer_issue()` functions with `_build_deferred_section()` and `_build_undeferred_section()` helpers
- `dependency_mapper.py`: Added deferred to `gather_all_issue_ids()` (config path + hardcoded fallback), `_load_issues()` scanning
- `issue_discovery/search.py`: Added `include_deferred` parameter to `_get_all_issue_files()`
- `parallel/merge_coordinator.py`: Added deferred dir patterns for stash/merge exclusion

**Config & Directory**:
- Created `.issues/deferred/.gitkeep`
- Updated `config-schema.json` with `deferred_dir` field

**Skills & Commands (12 files)**:
- Updated manage-issue, capture-issue, init, format-issue, issue-workflow, confidence-check skills
- Updated normalize-issues, prioritize-issues, verify-issues, refine-issue, align-issues, sync-issues, tradeoff-review-issues, create-sprint commands

**Tests (4 files, 13 new tests)**:
- `test_config.py`: 3 new tests for deferred_dir config
- `test_issue_lifecycle.py`: 9 new tests (TestDeferIssue, TestUndeferIssue)
- `test_issue_parser.py`: 2 new tests (deferred in ID scan, deferred exclusion from find_issues)
- Updated `conftest.py` shared fixtures

**Documentation (5 files)**:
- Updated ARCHITECTURE.md, CONFIGURATION.md, API.md, ISSUE_MANAGEMENT_GUIDE.md

### Verification
- 2954 tests pass, 0 failures
- mypy: 0 issues across 87 source files
- Pre-existing ruff lint (quoted type annotation in dependency_mapper.py) unrelated to changes

---

## Status

**Completed** | Created: 2026-02-18 | Completed: 2026-02-25 | Priority: P3

## Blocks

- ENH-485

- ENH-497
- ENH-504
- FEAT-490
- ENH-459
- FEAT-440

- ENH-494
- FEAT-488
- ENH-502
- ENH-496
- ENH-492
- ENH-470
## Blocked By

- ENH-491

- FEAT-503
- ENH-481
- ENH-498