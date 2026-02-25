# FEAT-441: Support Deferred Issues Folder — Implementation Plan

**Date**: 2026-02-25
**Issue**: P3-FEAT-441-support-deferred-issues-folder.md
**Confidence**: 85/100 (well-researched issue with clear patterns)

## Approach Summary

Add `.issues/deferred/` directory support by mirroring the `completed/` directory dual-mechanism pattern. The key insight: most tools already exclude deferred via Tier 1 implicit exclusion (they iterate `config.issue_categories` which won't include deferred). Only Tier 2 explicit-addback sites need code changes.

## Implementation Phases

### Phase 1: Config & Directory Setup
- [x] Create `.issues/deferred/.gitkeep`
- [x] Add `deferred_dir: str = "deferred"` field to `IssuesConfig` dataclass (`config.py:101`)
- [x] Add `from_dict()` deserialization (`config.py:126`)
- [x] Add `get_deferred_dir()` method to `BRConfig` (`config.py:505`)
- [x] Add `deferred_dir` to `to_dict()` serialization (`config.py:658`)
- [x] Add `deferred_dir` field to `config-schema.json` (`config-schema.json:103`)

### Phase 2: ID Uniqueness & Dependency Scanning
- [x] Add deferred to `dirs_to_scan` in `get_next_issue_number()` (`issue_parser.py:62`)
- [x] Add deferred pre-flight check in `find_issues()` (`issue_parser.py:526-529`)
- [x] Add deferred to `gather_all_issue_ids()` config path + hardcoded fallback (`dependency_mapper.py:1005-1008`)
- [x] Add deferred scanning in `_load_issues()` (`dependency_mapper.py:1053-1062`)

### Phase 3: Defer/Undefer Actions
- [x] Add `defer_issue()` function to `issue_lifecycle.py` (modeled after `close_issue`)
- [x] Add `undefer_issue()` function to `issue_lifecycle.py` (modeled after `reopen_issue`)

### Phase 4: Issue Discovery & Search
- [x] Add `include_deferred` parameter to `_get_all_issue_files()` (`search.py:34`)

### Phase 5: Merge Coordinator
- [x] Add deferred dir patterns alongside completed dir patterns (`merge_coordinator.py:178-182, 389-393`)

### Phase 6: Skill & Command Updates
- [x] Update `skills/manage-issue/SKILL.md` — add defer/undefer actions, update directory diagram
- [x] Update `skills/capture-issue/SKILL.md` — add deferred skip + candidate surfacing
- [x] Update `skills/init/SKILL.md` — add deferred dir creation
- [x] Update commands with bash loops: normalize-issues, prioritize-issues, verify-issues, refine-issue, etc.

### Phase 7: Tests
- [x] Add `test_get_deferred_dir()` to `test_config.py`
- [x] Add `TestDeferIssue` and `TestUndeferIssue` to `test_issue_lifecycle.py`
- [x] Add deferred to `conftest.py` `sample_config` fixture
- [x] Add deferred to `conftest.py` `issues_dir` fixture
- [x] Verify `get_next_issue_number()` includes deferred
- [x] Verify `find_issues()` excludes deferred

### Phase 8: Documentation
- [ ] Update `docs/ARCHITECTURE.md`
- [ ] Update `CONTRIBUTING.md`
- [ ] Update `docs/reference/CONFIGURATION.md`
- [ ] Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- [ ] Update `docs/reference/API.md`

## Design Decisions

1. **`deferred_dir` as peer to `completed_dir`** — not a category, same structural pattern
2. **`defer_issue()` modeled on `close_issue()`** — appends `## Deferred` section, uses `_move_issue_to_completed` helper generalized to `_move_issue_to_dir`
3. **`undefer_issue()` modeled on `reopen_issue()`** — uses `_get_category_from_issue_path()`, appends `## Undeferred` section
4. **No new CLI subcommands needed** — defer/undefer handled through `manage-issue` skill actions

## Success Criteria
- [ ] All existing tests pass
- [ ] New tests pass for defer/undefer
- [ ] `find_issues()` excludes deferred
- [ ] `get_next_issue_number()` includes deferred
- [ ] Issue can be deferred and undeferred
