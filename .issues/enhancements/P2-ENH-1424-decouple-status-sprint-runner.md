---
id: ENH-1424
type: ENH
priority: P2
status: done

decision_needed: false
confidence_score: 85
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-05-10T18:29:14Z
parent: ENH-1419
---

# ENH-1424: Decouple Issue Status — Sprint Runner

## Summary

Update the sprint runner (`run.py`, `edit.py`) to use `IssueInfo.status` frontmatter instead of `get_completed_dir()` directory lookups for completed-issue tracking and pre-validation. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1423, ENH-1425, ENH-1426 after ENH-1417 lands.

## Current Behavior

The sprint runner (`run.py`) pre-validates issues by globbing `get_completed_dir()` to detect already-completed issues. `edit.py` builds a `completed_ids` set from the same `completed/` directory glob. This breaks when issues live in type-scoped directories (bugs/, features/, etc.) rather than `completed/`.

## Expected Behavior

Sprint pre-validation uses `IssueInfo.status == "done"` (or `"cancelled"`) frontmatter check instead of `completed/` directory globbing. `ll-sprint edit --prune` correctly identifies completed issues via frontmatter status regardless of which directory the issue lives in.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

The sprint runner pre-validates issues by globbing `get_completed_dir()` to detect already-completed issues. `edit.py` builds a `completed_ids` set from the same directory. Removing these directory checks lets sprint operations work correctly when issues live in type-scoped directories.

## Proposed Solution

### `sprint/run.py`

- `_cmd_sprint_run()` (lines 162–178): replace `completed_dir.glob(f"*-{issue_id}-*.md")` pre-validation with a check for `IssueInfo.status == "done"` on the resolved issue file

### `sprint/edit.py`

- `_cmd_sprint_edit()` (lines 72–89): replace `get_completed_dir()` glob to build `completed_ids` with a scan of type dirs filtering for `status: done`

### `sprint/show.py`

- Verify-only: confirmed no directory-based logic; `completed_issues` tracking uses `.sprint-state.json`. Verify no regressions after ENH-1417 changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`run.py` ordering constraint**: The pre-validate block (lines 161–178) runs on raw string IDs *before* `validate_issues()` (line 185) and `load_issue_infos()` (line 194). The replacement approach:
1. Remove the `get_completed_dir()` block (lines 161–178)
2. After `validate_issues()` at line 185 (which returns `dict[str, IssueInfo]`), filter `valid.items()` for `info.status in ("done", "cancelled")` to populate `pre_completed_skipped`
3. Update `issues_to_process` accordingly before passing to `load_issue_infos()`

This reuses the `valid` dict — no additional file I/O needed.

**`edit.py` simplification**: `validate_issues(sprint.issues)` at line 68 already returns `dict[str, IssueInfo]`. Replace the `get_completed_dir()` glob (lines 73–79) with:
```python
completed_ids = {
    issue_id
    for issue_id, info in valid.items()
    if info.status in ("done", "cancelled")
}
```

**`get_completed_dir()` already deprecated** in `scripts/little_loops/config/core.py:get_completed_dir` with `DeprecationWarning("BRConfig.get_completed_dir() is deprecated; use IssueInfo.status instead")`.

## Implementation Steps

1. Update `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` — replace `completed_dir.glob()` pre-validation with `IssueInfo.status == "done"` check
2. Update `scripts/little_loops/cli/sprint/edit.py:_cmd_sprint_edit()` — replace `get_completed_dir()` glob with type-dir scan filtered by status field
3. Verify `scripts/little_loops/cli/sprint/show.py` — no regressions after ENH-1417 changes
4. Update `scripts/tests/test_sprint.py` — update `get_completed_dir()` pre-validation tests to use `status: done` frontmatter check; add `status: done` to completed issue fixture files
5. Update `scripts/tests/test_sprint_integration.py` — same fixture update for integration tests

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/SPRINT_GUIDE.md` — change "already in `completed/`" to "with `status: done` or `status: cancelled` in frontmatter" in the Pre-flight section
7. Update `commands/review-sprint.md` — clarify that `issues.completed_dir` config key is no longer used by sprint edit/prune detection
8. Update `commands/create-sprint.md` — update Step 4 blocker check to use frontmatter status instead of `completed/` directory lookup
9. Add new integration test in `test_sprint_integration.py` — type-dir `status: done` detection path for `_cmd_sprint_run`
10. Add new unit test in `test_sprint.py` — `--prune` with `status: done` in type dir (not `completed/`)

## Scope Boundaries

- `sprint/show.py` is verify-only; no functional changes
- `SprintState.completed_issues` tracking in `.sprint-state.json` is not changed
- `get_completed_dir()` in `config/core.py` is not removed — only removing calls from sprint files
- No changes to `validate_issues()` function signature or behavior
- No changes to issue files or issue management outside the sprint module

## Impact

- **Priority**: P2 — Part of the ENH-1419 decoupling initiative; blocks correct sprint behavior with type-scoped issue directories
- **Effort**: Small — Two functions to update with clear canonical patterns from ENH-1422/ENH-1423; no new logic required
- **Risk**: Low — Limited scope, well-tested paths, canonical patterns exist to follow (sync.py, skip.py)
- **Breaking Change**: No

## Labels

`enhancement`, `sprint-runner`, `status-decoupling`

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py`
- `scripts/little_loops/cli/sprint/edit.py`
- `scripts/little_loops/cli/sprint/show.py` (verify only)
- `scripts/tests/test_sprint.py`
- `scripts/tests/test_sprint_integration.py`

## Acceptance Criteria

- Sprint pre-validation uses `status: done` check; no calls to `get_completed_dir()` in `run.py`
- `ll-sprint edit` correctly identifies completed issues via frontmatter
- `ll-sprint show` continues to work correctly (no regressions)
- Zero calls to `get_completed_dir()` remain in sprint runner files after changes
- All updated tests pass

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `sprint/run.py` | `_cmd_sprint_run()` | `completed_dir.glob(f"*-{issue_id}-*.md")` pre-validation | 162–178 |
| `sprint/edit.py` | `_cmd_sprint_edit()` | globs `get_completed_dir()` to build `completed_ids` | 72–89 |

### Dependent Files (Callers / Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/sprint/__init__.py` — exports `_cmd_sprint_run`, `_cmd_sprint_edit`
- `scripts/little_loops/sprint.py:SprintManager.load_issue_infos()` (lines 349–373) — loads `IssueInfo` from issue ID list; `_find_issue_path()` scans only active type dirs, not `completed/`
- `scripts/little_loops/config/core.py:get_completed_dir` — `get_completed_dir()` deprecated; returns `project_root / base_dir / completed_dir` with `DeprecationWarning`

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/sync.py:_get_local_issues()` (line 264) — canonical ENH-1423 pattern: `fm.get("status", "open") in ("done", "cancelled")` using `parse_frontmatter()`
- `scripts/little_loops/cli/issues/search.py:_load_issues_with_status()` (line 106) — ENH-1422 pattern: `IssueParser(config).parse_file(f)` then `issue.status` branch
- `scripts/little_loops/cli/issues/skip.py:cmd_skip()` (line 38) — comment "check frontmatter status, not directory"; uses `IssueParser(config).parse_file(path)` then `.status in ("done", "cancelled", "deferred")`

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_sprint.py` — unit tests for sprint module; pre-validation logic tests to update
- `scripts/tests/test_sprint_integration.py:test_completed_issues_excluded_from_waves()` (line 1739) — **key test**: currently puts `P1-BUG-001-done.md` in `completed/` dir; after ENH-1424, move to `bugs/` with `status: done` frontmatter
- `scripts/tests/test_sprint_integration.py:test_sprint_resume_skips_completed_waves()` (line 848) — uses `SprintState.completed_issues` list; no change needed
- New test fixture pattern to follow (`test_sync.py:644`): `done_file.write_text("---\nstatus: done\n---\n\n# BUG-002: Done")`

_Wiring pass added by `/ll:wire-issue`:_

**Tests to update in `test_sprint.py`:**
- `TestSprintEdit.test_edit_prune_removes_completed` (line 1690) — currently writes BUG-001 only to `completed/` then unlinks from `bugs/`; after ENH-1424, BUG-001 must stay in `bugs/` with `status: done` frontmatter; the `get_completed_dir()` glob path is replaced by reading `valid.items()` from `validate_issues()`, so the issue will land in `pruned_invalid` (not found in active dirs) unless the fixture keeps it in `bugs/`
- `TestSprintEdit.test_edit_prune_recognizes_epic_in_completed` (line 1728) — same pattern: EPIC-005 is written only to `completed/`; move to `epics/` dir with `status: done` frontmatter
- `TestSprintEdit._setup_edit_project` (line 1451) — creates `completed/` directory; becomes vestigial once tests above are fixed

**Tests to update in `test_sprint_integration.py`:**
- `test_all_completed_issues_returns_zero` (line 1793) — both BUG-001 and BUG-002 are written to `completed/` with no `status:` frontmatter; after the change they will be treated as missing (not-found) rather than status-completed; move both to `bugs/` with `status: done` frontmatter
- `test_sprint_completed_dependencies_satisfied` (line 1267) — writes BUG-001 to `completed/` dir; exercises `DependencyGraph.from_issues()` with `completed_ids`, not the `run.py` pre-validation path; low urgency but should be updated for fixture consistency

**New tests to write:**
- In `test_sprint_integration.py`: test `_cmd_sprint_run` where the "done" issue has `status: done` frontmatter in its type dir (not `completed/`) — directly validates the new detection path
- In `test_sprint.py`: test `_cmd_sprint_edit --prune` where `status: done` is in the type dir, not `completed/` — verifies `pruned_completed` categorization under the new logic

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/SPRINT_GUIDE.md` — Section "Pre-flight" states `"Issues already in completed/ are auto-skipped silently"` — inaccurate after ENH-1424; update to reflect frontmatter-based detection (`status: done` or `status: cancelled`)
- `commands/review-sprint.md` — Section "Configuration" lists `issues.completed_dir` as relevant to sprint edit/prune behavior — stale after ENH-1424 removes `get_completed_dir()` calls from the prune path
- `commands/create-sprint.md` — Step 4 blocker check instructs checking `completed/` directory for resolved blockers — creates behavioral inconsistency with the runner; update to check `status` frontmatter instead

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- **`validate_issues()` return type mismatch**: "Codebase Research Findings" states `validate_issues()` returns `dict[str, IssueInfo]`, but the actual signature is `dict[str, Path]` (`sprint.py:329`). The code snippet for `edit.py` (`info.status in ("done", "cancelled")`) and the `run.py` filter-by-status plan will raise `AttributeError` at runtime — `info` is a `Path`, not an `IssueInfo`. Implementer must call `IssueParser.parse_file(path)` or `parse_frontmatter()` on each path before checking status. Canonical pattern: `sync.py:_get_local_issues()` (~line 264) and `skip.py:cmd_skip()` (~line 38).

## Resolution

Updated `sprint/run.py` and `sprint/edit.py` to use `parse_frontmatter()` status checks instead of `get_completed_dir()` directory globs. Zero calls to `get_completed_dir()` remain in sprint runner files. Updated 3 unit tests and 3 integration tests to use `status: done` frontmatter fixtures. Updated `SPRINT_GUIDE.md`, `review-sprint.md`, and `create-sprint.md` docs. All 108 sprint tests pass.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T18:29:30 - `5e210bd0-aa74-498d-8efc-472d4b6cd3e1.jsonl`
- `/ll:manage-issue` - 2026-05-10T18:29:14Z
- `/ll:ready-issue` - 2026-05-10T18:21:24 - `f78cfa25-2175-41df-8147-46d63f415fd5.jsonl`
- `/ll:wire-issue` - 2026-05-10T18:14:42 - `e8c63034-014a-4035-a422-a7ecec966145.jsonl`
- `/ll:refine-issue` - 2026-05-10T18:08:51 - `86aa4e0d-ce8b-4809-b187-ab9f152feab6.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `ae77d2b6-af7e-4c58-9e31-c1eb4f75e1c9.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
