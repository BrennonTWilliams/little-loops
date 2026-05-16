---
id: FEAT-1170
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Medium
depends_on: FEAT-1169
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-04-18T00:00:00Z
---

# FEAT-1170: Inject `completed_at` in Sequential Lifecycle Paths

## Summary

Inject `completed_at` ISO 8601 UTC timestamp into issue frontmatter at the two call sites in `scripts/little_loops/issue_lifecycle.py` that invoke `_move_issue_to_completed()`, and fix the 6 breaking tests in `TestMoveIssueToCompleted`.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Prerequisite

Requires FEAT-1169 (adds `update_frontmatter` utility to `frontmatter.py`).

## Motivation

Issues completed via `close_issue` and `complete_issue_lifecycle` need a precise completion timestamp. Injecting at the call sites (not inside `_move_issue_to_completed()`) avoids stamping deferred issues (see `defer_issue` at `issue_lifecycle.py:752`).

## Implementation Steps

1. **`scripts/little_loops/issue_lifecycle.py`**:
   - Import `update_frontmatter` from `little_loops.frontmatter`
   - At `close_issue` (line 618): `_prepare_issue_content()` (called at line 615) already returns the full file content as a string. Inject by replacing the `content` variable in-memory: `content = update_frontmatter(content, {"completed_at": <z_suffix_timestamp>})` — then pass to `_move_issue_to_completed()`. No separate disk write needed; `_move_issue_to_completed` writes `content` to the destination at lines 318/343/348/352.
   - At `complete_issue_lifecycle` (line 693): same in-memory pattern after `_prepare_issue_content()` call at line 690.
   - Use `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` format (normalize to `Z` suffix, not `+00:00`). Do NOT reuse `_iso_now()` — it produces `+00:00` and is already used for event bus `ts` fields at lines 533, 635, 711, 810.

2. **Fix 6 breaking tests in `scripts/tests/test_issue_lifecycle.py:TestMoveIssueToCompleted`**:
   - Lines 296, 323, 345, 367, 401, 436: replace `assert completed.read_text() == content` exact equality checks
   - Replace with: `assert "completed_at:" in completed.read_text()` plus separate substring assertions for required content
   - Add assertions to `TestCompleteIssueLifecycle.test_full_complete_flow` (line 1114) verifying `completed_at` is present

3. **Timestamp format**:
   - `_iso_now()` at line 26 uses `datetime.now(UTC).isoformat()` which produces `+00:00` suffix
   - For `completed_at`, use `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` directly to produce `Z` suffix

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Fix `test_source_deleted_by_concurrent_worker` at `scripts/tests/test_issue_lifecycle.py:464` — same exact-equality pattern as the 6 known-breaking tests; loosen with same substring assertion approach (7th breaking test, not in original issue)
5. (Optional) Add test in `scripts/tests/test_issue_history_parsing.py` verifying `completed_at` frontmatter field is preserved through `parse_completed_issue` — closes a coverage gap with no blocking risk

## Files to Modify

- `scripts/little_loops/issue_lifecycle.py` — inject `completed_at` at `close_issue` and `complete_issue_lifecycle` call sites
- `scripts/tests/test_issue_lifecycle.py` — fix 6 breaking tests + add assertions to full flow test

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — add `from little_loops.frontmatter import update_frontmatter` (top-of-file import); inject `completed_at` in-memory on `content` between `_prepare_issue_content()` and `_move_issue_to_completed()` at call sites `close_issue` (line 618) and `complete_issue_lifecycle` (line 693).
- `scripts/tests/test_issue_lifecycle.py` — loosen exact-equality assertions at lines 296, 323, 345, 367, 401, 436 (in `TestMoveIssueToCompleted`); add `completed_at` presence assertion in `TestCompleteIssueLifecycle.test_full_complete_flow` (line 1114).

### Key Code Locations
- `_move_issue_to_completed()` definition: `issue_lifecycle.py:294` — accepts pre-assembled `content` string, does NOT read from disk. Writes `content` to destination at lines 318 (pre-existing dest), 343 (git mv fail path), 348 (git mv success path), 352 (manual copy path).
- `close_issue()`: `issue_lifecycle.py:545–645` — call to `_prepare_issue_content` at line 615; call to `_move_issue_to_completed` at line 618.
- `complete_issue_lifecycle()`: `issue_lifecycle.py:648–720` — call to `_prepare_issue_content` at line 690; call to `_move_issue_to_completed` at line 693.
- `defer_issue()`: `issue_lifecycle.py:752–810` — calls `_move_issue_to_completed` at line 797 but with `deferred_path` (not `completed_path`); content is built inline without `_prepare_issue_content`. Since injection is at `close_issue`/`complete_issue_lifecycle` call sites (NOT inside `_move_issue_to_completed`), `defer_issue` is not affected. No additional guard needed.
- `_iso_now()`: `issue_lifecycle.py:26` — existing helper uses `datetime.now(UTC).isoformat()` → `+00:00` suffix. Used by event bus `ts` fields at lines 533, 635, 711, 810. Do NOT use for `completed_at` (issue requires `Z` suffix for consistency with `captured_at` convention).

### Dependent Files (Callers)
- `scripts/little_loops/cli/sync.py:160-166` — `close_issues()` → invokes `close_issue()`.
- `scripts/little_loops/cli/auto.py` — `AutoManager` invokes completion functions during automation runs.
- `scripts/little_loops/issue_manager.py` — orchestrates lifecycle via `close_issue`/`complete_issue_lifecycle`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py:20-27,63-69` — re-exports `close_issue` and `complete_issue_lifecycle`; signatures unchanged so no edit needed, but confirms the public API surface.
- `scripts/tests/test_interceptor_extension.py:122,171` — calls `close_issue()` but mocks `_move_issue_to_completed` away entirely; not at risk of breaking.

### Patterns to Follow
- `scripts/little_loops/sync.py:486-498` — canonical `update_frontmatter` call-site pattern (build `updates` dict, pass content in, capture return value). This implementation uses `isoformat(timespec="seconds")` → `+00:00`; FEAT-1170 diverges to `strftime("%Y-%m-%dT%H:%M:%SZ")` for `Z` suffix.
- `skills/capture-issue/SKILL.md:235` and `scripts/tests/test_frontmatter.py:57` — establish `Z` suffix as the repo convention for `*_at` frontmatter fields (e.g., `captured_at: 2026-04-18T10:30:00Z`).
- `scripts/tests/test_frontmatter.py:195-198, 220-222` — substring assertion style (`assert "key: value" in result`) to model for loosened test assertions.
- `scripts/tests/test_issue_lifecycle.py:196-201` — existing `_prepare_issue_content` tests already use substring assertions; consistent with proposed change.

### Tests
- `scripts/tests/test_issue_lifecycle.py` — `TestMoveIssueToCompleted` (line 268) and `TestCompleteIssueLifecycle` (line 1111).
- `scripts/tests/test_frontmatter.py` — `TestUpdateFrontmatter` validates the `update_frontmatter` dependency (from FEAT-1169). No changes needed.
- Note per `scripts/tests/test_issue_lifecycle.py` grep: `completed_at` is not yet asserted anywhere. This issue introduces the first such assertions.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_lifecycle.py:464` — `test_source_deleted_by_concurrent_worker` has the same `assert completed.read_text() == new_content` exact-equality pattern — a **7th breaking test** not listed in the issue; must be loosened alongside lines 296, 323, 345, 367, 401, 436 [Agent 3 finding]
- `scripts/tests/test_issue_history_parsing.py` — no test currently verifies that `completed_at` survives a `parse_completed_issue` round-trip; consider a new test to verify the field is present after frontmatter injection (optional but closes a coverage gap) [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — already updated in FEAT-1169 to document `update_frontmatter`. No additional changes needed for FEAT-1170.
- Skill-level docs (`skills/manage-issue/*`) are covered by sibling issue FEAT-1172.

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — needs a versioned feature entry for `completed_at` injection (covering FEAT-1169, FEAT-1170, FEAT-1171, FEAT-1172 as a group); no `[Unreleased]` section — add directly under the next release version header [Agent 2 finding]

### Out of Scope
- Parallel completion path (`scripts/little_loops/parallel/orchestrator.py`) — sibling issue FEAT-1171.
- Interactive skill docs updates — sibling issue FEAT-1172.
- Migration of `sync.py:_update_issue_frontmatter` to public `update_frontmatter` — intentionally deferred per FEAT-1169.

## Acceptance Criteria

- [ ] Issues completed via `close_issue` have `completed_at` in frontmatter
- [ ] Issues completed via `complete_issue_lifecycle` have `completed_at` in frontmatter
- [ ] `completed_at` format is ISO 8601 UTC with `Z` suffix
- [ ] Deferred issues (via `defer_issue`) do NOT get `completed_at`
- [ ] All 6 previously-breaking tests pass with updated assertions
- [ ] `test_full_complete_flow` asserts `completed_at` is present

## Resolution

**Action**: implement
**Status**: Completed

### Changes
- `scripts/little_loops/issue_lifecycle.py` — added `update_frontmatter` import; added `_completed_at_now()` helper producing `Z`-suffixed ISO 8601 UTC; injected `completed_at` into `content` between `_prepare_issue_content()` and `_move_issue_to_completed()` at both `close_issue` and `complete_issue_lifecycle` call sites.
- `scripts/tests/test_issue_lifecycle.py` — added `re` import; added `completed_at:` presence + `Z`-suffix assertions to `TestCloseIssue.test_full_close_flow` and `TestCompleteIssueLifecycle.test_full_complete_flow`.

### Notes
- Tests in `TestMoveIssueToCompleted` were not affected (they invoke `_move_issue_to_completed` directly with a pre-built content string; injection happens upstream at the call sites). The "6 breaking tests" prediction in the original plan did not materialize because injection lives at the call sites, not inside the move helper.
- `defer_issue` is unaffected as designed — it does not call `_prepare_issue_content` and the injection sites are outside its path.
- Verification: `pytest scripts/tests/` → 4966 passed; `ruff check` → clean; `mypy issue_lifecycle.py` → clean.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T20:42:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a75fe13-432f-44a5-b549-c98802511776.jsonl`
- `/ll:manage-issue feature implement FEAT-1170` - 2026-04-18T15:42:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a75fe13-432f-44a5-b549-c98802511776.jsonl`
- `/ll:ready-issue` - 2026-04-18T20:38:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ed9e6fc-2d18-420f-a807-31f739df2b00.jsonl`
- `/ll:wire-issue` - 2026-04-18T20:35:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab781961-a8c6-4915-8190-7c4fd3723052.jsonl`
- `/ll:refine-issue` - 2026-04-18T20:29:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b5a7a59-b5d5-44a8-af5a-690d44a1c6ff.jsonl`
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f11142c9-e79d-4054-a925-d11c083c2885.jsonl`
