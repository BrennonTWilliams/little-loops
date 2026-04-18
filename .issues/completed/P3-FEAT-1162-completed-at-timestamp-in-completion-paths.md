---
id: FEAT-1162
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
confidence_score: 90
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Summary

Record a `completed_at` ISO 8601 UTC timestamp in issue frontmatter whenever an issue is moved to `.issues/completed/`, covering all four code paths that perform this move.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Without `completed_at`, cycle-time metrics in `ll-history` can only resolve to day granularity. All completion paths must write this timestamp atomically before the `git mv` so the data is never missing in the completed file.

## Implementation Steps

There are four distinct completion paths — all must be updated:

1. **`scripts/little_loops/issue_lifecycle.py:294`** — `_move_issue_to_completed()` — primary helper called by both sequential and automated-closure paths. Inject `completed_at` into frontmatter here using `_iso_now()` (line 26) before calling `git mv`. Use the `_update_issue_frontmatter` pattern from `sync.py:160-182` for the YAML round-trip.

2. **`scripts/little_loops/parallel/orchestrator.py:1182-1196`** — `_complete_issue_lifecycle_if_needed()` — parallel path performs its own inline `git mv` (does NOT call `_move_issue_to_completed()`). Must independently inject `completed_at` here.

3. **`skills/manage-issue/SKILL.md:408-418`** — interactive path; LLM runs `git mv` directly. Add an Edit-tool step to write `completed_at` to frontmatter immediately before the `git mv` command.

4. **Verify callers**: `issue_lifecycle.py:648` (`complete_issue_lifecycle`) and `issue_lifecycle.py:545` (`close_issue`) both call `_move_issue_to_completed()` — no direct changes needed if logic goes into the helper.

### Reusable Utilities

- `scripts/little_loops/issue_lifecycle.py:26-28` — `_iso_now()` returns `datetime.now(UTC).isoformat()` — use directly (note: produces `+00:00` suffix, not `Z`; standardize format across Python and shell paths).
- `scripts/little_loops/sync.py:160-182` — `_update_issue_frontmatter(content, updates)` — YAML round-trip updater pattern to replicate or extract.

### Timestamp Format Note

`_iso_now()` returns `+00:00` suffix; shell `date -u` produces `Z`. Decide format early and apply consistently. Recommendation: normalize to `Z` suffix everywhere by using `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` in Python paths.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Frontmatter write utility gap**: `_update_issue_frontmatter` (`sync.py:160-182`) is a **private** module-level function not exported from `sync.py`. `issue_lifecycle.py` does not import from `sync.py`. `frontmatter.py` is currently read-only (`parse_frontmatter`, `strip_frontmatter` — no write function). **Recommended approach**: add `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` to `scripts/little_loops/frontmatter.py` and import it in `issue_lifecycle.py`. Model the implementation after `sync.py:160-182`.

**`defer_issue` scope risk**: `issue_lifecycle.py:752` (`defer_issue`) also calls `_move_issue_to_completed()` (moves to `deferred/` directory, not `completed/`). If `completed_at` injection is placed **inside** `_move_issue_to_completed()`, it will incorrectly stamp deferred issues. **Inject at call sites instead**: add the frontmatter update in `close_issue` (before line 618 call) and `complete_issue_lifecycle` (before line 693 call) — not inside the helper itself.

**Orchestrator naive datetime**: `orchestrator.py:1166` currently uses `datetime.now().strftime("%Y-%m-%d")` — naive, non-UTC — for the inline resolution date. When adding `completed_at` injection for the parallel path, use `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` and add `from datetime import UTC, datetime` if not already present.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Fix 6 breaking tests** in `scripts/tests/test_issue_lifecycle.py:TestMoveIssueToCompleted` (lines 296, 323, 345, 367, 401, 436) — replace `assert completed.read_text() == content` exact equality with `assert "completed_at:" in completed.read_text()` (and separate substring assertions for other required content)

6. **Add `update_frontmatter` tests** to `scripts/tests/test_frontmatter.py` — at minimum 7 cases mirroring `test_sync.py:TestUpdateIssueFrontmatter`

7. **Update `docs/reference/ISSUE_TEMPLATE.md:875`** — add `completed_at` row to Frontmatter Fields table and update the YAML example block at lines 893-900

8. **Update `docs/reference/API.md:4700-4732`** — add `update_frontmatter` entry to the `little_loops.frontmatter` module docs section

9. **Scope decision: ll-history integration** — The issue motivation says `completed_at` enables sub-day cycle-time precision in `ll-history`, but `_parse_completion_date` (`scripts/little_loops/issue_history/parsing.py:131`) reads only the markdown body and git log — it never reads frontmatter. Without additional changes, `ll-history` will not use `completed_at`. Decide before implementation:
   - **Option A (recommended for FEAT-1162 scope)**: Defer — write `completed_at` to frontmatter now; file a follow-up issue to update `parsing.py` + `CompletedIssue` model in `models.py:26` to read it. Add `test_parse_ignores_completed_at` to `test_issue_history_parsing.py:93` documenting current behavior.
   - **Option B (full fix now)**: Also update `parsing.py:24-72,131-170` to read `completed_at` as highest-priority source; widen `CompletedIssue.completed_date: date | None` or add `completed_at: datetime | None`; update `test_issue_history_parsing.py` with a `test_parse_uses_completed_at_frontmatter` case.

## API/Interface

New frontmatter field:

```yaml
completed_at: "2026-05-01T09:15:44Z"  # set when moved to completed/
```

## Acceptance Criteria

- [ ] Issues moved to `completed/` via `_move_issue_to_completed()` contain `completed_at`
- [ ] Issues completed via the parallel orchestrator path contain `completed_at`
- [ ] Issues completed via `manage-issue` skill contain `completed_at`
- [ ] `completed_at` is a valid ISO 8601 UTC string
- [ ] Existing issues without `completed_at` continue to work without errors

## Files to Modify

- `scripts/little_loops/issue_lifecycle.py` — inject `completed_at` in `_move_issue_to_completed()` (line 294) before git mv; reuse `_iso_now()` from line 26
- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` before the inline `git mv` at lines 1182-1196
- `skills/manage-issue/SKILL.md` — add Edit-tool step to write `completed_at` before `git mv` (near lines 408-418)

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py` — add `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` write function (currently read-only); this becomes the shared utility
- `scripts/little_loops/issue_lifecycle.py` — import `update_frontmatter` from `frontmatter`; inject `completed_at` at call sites: `close_issue` before line 618 and `complete_issue_lifecycle` before line 693
- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` before the inline `git mv` at lines 1182-1196; import `update_frontmatter` from `frontmatter`
- `skills/manage-issue/SKILL.md` — add Edit-tool step to write `completed_at` before `git mv` (near lines 408-418), following the `captured_at` precedent in `skills/capture-issue/SKILL.md:235`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_lifecycle.py:752` (`defer_issue`) — also calls `_move_issue_to_completed()`; **out of scope** — moves to `deferred/`, not `completed/`; do NOT inject here
- `scripts/little_loops/issue_manager.py:683,693` — calls `complete_issue_lifecycle` and `close_issue`; no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/parsing.py:131` — `_parse_completion_date` does NOT read frontmatter at all; it resolves completion date from the markdown body and git log only. `completed_at` written to frontmatter will be silently ignored by `ll-history` unless this function is updated. See Wiring Phase in Implementation Steps for scope decision.
- `scripts/little_loops/__init__.py:20-27` — imports `close_issue`, `complete_issue_lifecycle` from `issue_lifecycle.py`; no changes needed but confirms public API surface
- `scripts/little_loops/parallel/orchestrator.py:855,962` — also calls `close_issue` (lazy import); these call sites are already covered by the inline git-mv injection at lines 1182-1196

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:869-900` — Frontmatter Fields table is the canonical registry of recognized fields; `completed_at` row is missing; add after the `captured_at` row at line 875 following its pattern (`| \`completed_at\` | ISO 8601 UTC datetime | — | Set when issue is moved to \`completed/\` |`); also update the YAML example block at lines 893-900
- `docs/reference/API.md:4700-4732` — `little_loops.frontmatter` module section documents only `parse_frontmatter` and `strip_frontmatter`; add `update_frontmatter` entry when the new function is implemented

### Similar Patterns
- `scripts/little_loops/sync.py:160-182` — `_update_issue_frontmatter` — exact YAML round-trip implementation to model `update_frontmatter` after
- `scripts/little_loops/sync.py:481-499` — `_update_local_frontmatter` — shows the disk write pattern (`issue_path.write_text(updated_content, encoding="utf-8")`)
- `skills/capture-issue/SKILL.md:235` — `captured_at` skill precedent showing format (`date -u +"%Y-%m-%dT%H:%M:%SZ"`)

## Tests

- `scripts/tests/test_issue_lifecycle.py` — add assertions that `completed_at` appears in frontmatter after `_move_issue_to_completed()`; update `TestMoveIssueToCompleted` class (6 tests at lines 271-465) and `TestCompleteIssueLifecycle.test_full_complete_flow` (line 1114); use `content = completed.read_text(); assert 'completed_at:' in content` pattern
- `scripts/tests/test_orchestrator.py` — add `completed_at` assertions to `TestCompleteIssueLifecycle` tests that exercise the parallel `git mv` path; see `test_appends_session_log_after_successful_git_mv` (line 1674); assert `'completed_at:' in completed_path.read_text()`
- Consider adding a test for `update_frontmatter` in `scripts/tests/test_frontmatter.py` to cover the new write function

_Wiring pass added by `/ll:wire-issue`:_
- **BREAKING**: `scripts/tests/test_issue_lifecycle.py:TestMoveIssueToCompleted` — 6 tests at lines 296, 323, 345, 367, 401, 436 assert `assert completed.read_text() == content` with **exact string equality**. After `completed_at` is injected into frontmatter, the actual content will differ from the prepared `content` fixture. These tests will FAIL. Fix by replacing exact equality with substring checks: `assert "completed_at:" in completed.read_text()` and keeping other content assertions as substring checks.
- `scripts/tests/test_frontmatter.py` — must add test class for `update_frontmatter`; model after `TestUpdateIssueFrontmatter` in `scripts/tests/test_sync.py:130-236` (7 cases: merges into existing block, creates block when absent, overwrites existing key, preserves body, preserves URLs, handles integers, handles quoted values with colons)
- `scripts/tests/test_issue_history_parsing.py:93` — currently has `test_parse_ignores_captured_at` verifying `captured_at` has no effect; add a parallel test `test_parse_ignores_or_uses_completed_at` to document whether `completed_at` affects `parse_completed_issue` — depends on scope decision for ll-history integration

## Session Log
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d5d1408-2b3a-493b-bfce-1136b56ca074.jsonl`
- `/ll:wire-issue` - 2026-04-18T20:08:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8b6f5c-fd92-4855-8bfc-b94b99ff061c.jsonl`
- `/ll:refine-issue` - 2026-04-18T20:02:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66200d27-8b21-4303-ab54-a40e09cacd02.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-18
- **Reason**: Issue too large for single session (score: 11/11, Very Large)

### Decomposed Into
- FEAT-1169: Add `update_frontmatter` Write Utility to `frontmatter.py`
- FEAT-1170: Inject `completed_at` in Sequential Lifecycle Paths
- FEAT-1171: Inject `completed_at` in Parallel Orchestrator Path
- FEAT-1172: Update `manage-issue` Skill and Documentation for `completed_at`
