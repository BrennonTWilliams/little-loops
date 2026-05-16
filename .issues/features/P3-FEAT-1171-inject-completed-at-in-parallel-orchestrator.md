---
id: FEAT-1171
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Small
depends_on: FEAT-1169
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-04-18T00:00:00Z
---

# FEAT-1171: Inject `completed_at` in Parallel Orchestrator Path

## Summary

Inject `completed_at` ISO 8601 UTC timestamp into issue frontmatter in `scripts/little_loops/parallel/orchestrator.py` before the inline `git mv` at lines 1182-1196, and add assertions to the orchestrator test suite.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Prerequisite

Requires FEAT-1169 (adds `update_frontmatter` utility to `frontmatter.py`).

## Motivation

The parallel orchestrator performs its own inline `git mv` and does NOT call `_move_issue_to_completed()`. It must independently inject `completed_at` to ensure parallel completions are timestamped.

## Implementation Steps

1. **`scripts/little_loops/parallel/orchestrator.py`**:
   - Import `update_frontmatter` from `little_loops.frontmatter` (add to imports)
   - Add `from datetime import UTC, datetime` if not already present (`orchestrator.py:1166` uses naive `datetime.now()` — fix this too)
   - Before the inline `git mv` at lines 1182-1196 in `_complete_issue_lifecycle_if_needed()`:
     - Read file content
     - Call `update_frontmatter(content, {"completed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})`
     - Write updated content back to disk
   - Replace the naive `datetime.now().strftime("%Y-%m-%d")` at line 1166 with `datetime.now(UTC).strftime("%Y-%m-%d")` (fix timezone-naive bug while here)

2. **`scripts/tests/test_orchestrator.py`**:
   - Add `completed_at` assertions to `TestCompleteIssueLifecycle` tests that exercise the parallel `git mv` path
   - See `test_appends_session_log_after_successful_git_mv` (line 1674) as the model
   - Assert `'completed_at:' in completed_path.read_text()`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion point in `orchestrator.py`**:
- `_complete_issue_lifecycle_if_needed()` begins at `scripts/little_loops/parallel/orchestrator.py:1121`
- File content is already loaded into `content` at line 1154 (`content = original_path.read_text()`)
- Resolution markdown is appended to `content` in lines 1157-1179 (guarded by `"## Resolution" not in content`)
- `self._git_lock.run(["mv", ...])` executes at lines 1182-1185
- Both write-back paths (`git mv` failure at lines 1187-1193, success at lines 1194-1197) call `completed_path.write_text(content)` — so injecting into `content` **before** line 1182 is captured by whichever path runs
- **Inject between line 1179 (end of Resolution block) and line 1182 (start of `git mv`)** — this mirrors `issue_lifecycle.py:697-701` exactly

**Imports already in place** (`orchestrator.py:18`):
- `from datetime import UTC, datetime` is already present — no new datetime import needed; only the call site at line 1166 needs the `UTC` argument added
- `from little_loops.frontmatter import update_frontmatter` is **not** currently imported — must be added

**Reusable helper option**:
- `scripts/little_loops/issue_lifecycle.py:32-34` defines `_completed_at_now()` returning `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`
- It is private (`_` prefix) and not exported; implementer can either inline the `strftime` call or import `_completed_at_now` directly. Inlining matches the module-local style of `orchestrator.py`.

**Sibling pattern to mirror** (FEAT-1170, commit f8b2fd74):
- `scripts/little_loops/issue_lifecycle.py:625` (inside `close_issue`):
  ```python
  content = update_frontmatter(content, {"completed_at": _completed_at_now()})
  ```
- `scripts/little_loops/issue_lifecycle.py:698` (inside `complete_issue_lifecycle`): identical shape
- `update_frontmatter()` is defined at `scripts/little_loops/frontmatter.py:106`, signature `(content: str, updates: dict[str, str | int]) -> str`. It gracefully handles content without existing frontmatter (prepends a new block).

**Test pattern to apply** (from `scripts/tests/test_issue_lifecycle.py:896-900` and `:1162-1166`):
```python
# Verify completed_at frontmatter injection
content = completed_path.read_text()
assert "completed_at:" in content
match = re.search(r"completed_at:\s*'?(\S+?)'?\s*$", content, re.MULTILINE)
assert match is not None
assert match.group(1).endswith("Z")
```
Apply inside `TestCompleteIssueLifecycle` tests that exercise a successful `git mv` — the model test at `scripts/tests/test_orchestrator.py:1674` (`test_appends_session_log_after_successful_git_mv`) already performs the physical rename via its `mock_git_lock_run`, so `completed_path.read_text()` will return the written content.

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` before inline git mv; fix naive datetime at line 1166
- `scripts/tests/test_orchestrator.py` — add `completed_at` assertions

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py:18` — imports block (add `update_frontmatter` import)
- `scripts/little_loops/parallel/orchestrator.py:1166` — fix naive `datetime.now()` → `datetime.now(UTC)` in Resolution body (date-only string; independent of frontmatter injection)
- `scripts/little_loops/parallel/orchestrator.py:1179-1182` — insertion point for `content = update_frontmatter(content, {"completed_at": ...})`
- `scripts/tests/test_orchestrator.py` — `TestCompleteIssueLifecycle` class at line 1634; add assertions to / near `test_appends_session_log_after_successful_git_mv` (line 1674)

### Reference Sources (do NOT modify)
- `scripts/little_loops/frontmatter.py:106` — `update_frontmatter()` definition (prerequisite FEAT-1169)
- `scripts/little_loops/issue_lifecycle.py:32-34` — `_completed_at_now()` helper (pattern source)
- `scripts/little_loops/issue_lifecycle.py:625, 698` — sibling injection call sites (FEAT-1170 commit f8b2fd74)
- `scripts/tests/test_issue_lifecycle.py:896-900, 1162-1166` — test assertion pattern
- `scripts/tests/test_frontmatter.py` — `TestUpdateFrontmatter` suite (validates the utility)

### Dependent Files (Callers)
- `_complete_issue_lifecycle_if_needed()` is invoked only from within `orchestrator.py` itself (post-merge fallback) — no external callers require updating
- The parallel path is exercised via `scripts/little_loops/parallel/__init__.py` (exports `ParallelOrchestrator`) and driven by `ll-parallel` CLI — no CLI surface change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py:18` — imports and instantiates `ParallelOrchestrator` for sprint wave execution; no code change required (informational)

### Tests
- Existing: `scripts/tests/test_orchestrator.py::TestCompleteIssueLifecycle` — multiple tests covering the inline git mv path
- Existing: `scripts/tests/test_frontmatter.py::TestUpdateFrontmatter` — validates `update_frontmatter` handles missing / partial frontmatter
- Fixtures to reuse: `temp_repo_with_config`, `br_config`, `mock_git_lock`, `orchestrator`, `mock_issue` (defined in `scripts/tests/conftest.py` and top of `test_orchestrator.py`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:1674` (`test_appends_session_log_after_successful_git_mv`) — update: add `completed_at` assertions after existing `mock_log.assert_called_once()` line; read `completed_path = temp_repo_with_config / ".issues" / "completed" / original_path.name` and apply the standard assertion block
- `scripts/tests/test_orchestrator.py` — new test `test_injects_completed_at_before_git_mv_failure` needed: exercises the git mv failure branch (`returncode != 0`, `orchestrator.py:1187-1193`) where the write fallback path (`completed_path.write_text(content)`) runs without the rename; assert `completed_at:` is present in the written content. The injection point (before line 1182) covers both success and failure branches, but the failure path has zero test coverage currently.

### Documentation
- `docs/reference/API.md` — no change required; `update_frontmatter` entry already added for FEAT-1169
- `docs/ARCHITECTURE.md` — no change required; injection is an internal implementation detail

### Configuration
- No config changes; no new CLI flags

## Acceptance Criteria

- [ ] Issues completed via the parallel path have `completed_at` in frontmatter
- [ ] `completed_at` format is ISO 8601 UTC with `Z` suffix
- [ ] Naive `datetime.now()` at line 1166 replaced with `datetime.now(UTC)`
- [ ] Orchestrator tests assert `completed_at` is present in completed issue frontmatter

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `test_orchestrator.py:1674` (`test_appends_session_log_after_successful_git_mv`) — after `mock_log.assert_called_once()`, derive `completed_path = temp_repo_with_config / ".issues" / "completed" / original_path.name` and assert `"completed_at:" in completed_path.read_text()` with regex match for `Z` suffix
4. Add `test_injects_completed_at_before_git_mv_failure` — set `mock_git_lock_run` to return `returncode = 1` for the `mv` command (without renaming), call `_complete_issue_lifecycle_if_needed("BUG-001")`, and assert `"completed_at:"` is present in whatever file the fallback `write_text` produced

## Resolution

- **Action**: implement
- **Completed**: 2026-04-18
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/orchestrator.py`: imported `update_frontmatter`, injected `completed_at` ISO 8601 UTC (`Z` suffix) into issue frontmatter before the inline `git mv` in `_complete_issue_lifecycle_if_needed()`, and fixed the naive `datetime.now()` in the Resolution body to `datetime.now(UTC)`.
- `scripts/tests/test_orchestrator.py`: added `re` import, extended `test_appends_session_log_after_successful_git_mv` with `completed_at` frontmatter assertions, and added new `test_injects_completed_at_before_git_mv_failure` covering the previously-untested `git mv` failure fallback path.

### Verification Results
- `python -m pytest scripts/tests/` — 4967 passed, 5 skipped
- `ruff check scripts/little_loops/parallel/orchestrator.py scripts/tests/test_orchestrator.py` — clean
- `python -m mypy scripts/little_loops/parallel/orchestrator.py` — clean

## Session Log
- `/ll:manage-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0acc05ca-0e56-4d0d-b243-afd1e09ac0f8.jsonl`
- `/ll:wire-issue` - 2026-04-18T20:51:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe1f263-543e-40fd-838a-107e48c560ab.jsonl`
- `/ll:refine-issue` - 2026-04-18T20:45:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78cf1b63-ee15-475a-9bbd-d4abe407f318.jsonl`
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c5bb8fb-3ecb-45f7-9cd0-f674b644124e.jsonl`
