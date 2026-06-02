---
id: ENH-1549
type: enhancement
priority: P3
status: done
completed_at: 2026-05-17T08:38:48Z
parent: ENH-1539
size: Medium
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1549: Status synonym normalization — code implementation and tests

## Summary

Implement parser-level coercion that maps non-canonical `status:` synonyms (`complete`, `completed`, `finished`, `closed`, `in-progress`, `in progress`, `wip`) to their canonical equivalents on read. Place normalization inside `parse_frontmatter()` so all callers benefit automatically, then remove now-dead `"completed"` arms from three terminal-state tuples, and add the full test suite (unit + lifecycle regression guard).

## Parent Issue

Decomposed from ENH-1539: Normalize status synonyms and document canonical enum

## Current Behavior

`parse_frontmatter()` returns status values verbatim. Files written with `status: completed`, `finished`, `closed`, `in-progress`, `in progress`, or `wip` are not recognized as canonical by callers, causing `verify_issue_completed()`, `find_issues()`, `cmd_skip()`, and `_load_issues_with_status()` to miss or misroute those issues.

## Expected Behavior

`parse_frontmatter()` normalizes every synonym to its canonical equivalent on read (`complete`/`completed`/`finished`/`closed` → `"done"`, `in-progress`/`in progress`/`wip` → `"in_progress"`). Unknown values pass through unchanged. All callers automatically benefit without individual changes.

## Proposed Solution

### 1. Normalization level decision

Place the `STATUS_SYNONYMS` map inside `parse_frontmatter()` (in `scripts/little_loops/frontmatter.py` or the equivalent low-level parse function), **not** inside `IssueParser.parse_file()`. This ensures all direct `parse_frontmatter()` callers — `verify_issue_completed()`, `cli/sprint/edit.py`, `cli/sprint/run.py`, `issue_manager.py:process_issue_inplace()` — benefit without individual updates.

### 2. Synonym map

```python
STATUS_SYNONYMS = {
    "complete": "done",
    "completed": "done",
    "finished": "done",
    "closed": "done",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "wip": "in_progress",
}
raw_status = frontmatter.get("status", "open")
status = STATUS_SYNONYMS.get(raw_status, raw_status)
frontmatter["status"] = status
```

The existing narrow normalization at `issue_parser.py:487-489` can remain as-is or be removed once `parse_frontmatter()` handles the general case.

### 3. Dead-code cleanup

Once normalization runs upstream, remove the now-unreachable `"completed"` arms from:
- `issue_parser.py:find_issues()` (~line 872): `("done", "cancelled", "deferred", "completed")` → remove `"completed"`
- `cli/issues/skip.py:cmd_skip()`: same pattern → remove `"completed"`
- `cli/issues/search.py:_load_issues_with_status()` (~line 134): `("done", "cancelled", "completed")` → remove `"completed"`

### 4. Tests

**Write the regression guard first (TDD gate):**

In `scripts/tests/test_issue_lifecycle.py` — add to `TestVerifyIssueCompleted`:
```python
def test_verify_issue_completed_synonym_completed(tmp_path, ...):
    # Write status: completed to fixture file
    # Call verify_issue_completed()
    # Assert returns True
```
This test must FAIL until normalization is placed in `parse_frontmatter()`. It acts as a gate confirming the normalization level is correct.

In `scripts/tests/test_issue_parser.py` — add to `TestFindIssues` (modeled after `test_find_issues_skips_status_done`):
- One test per synonym: write frontmatter with `status: completed`, parse, assert `info.status == "done"`
- One test: unknown value passes through unchanged (e.g., `status: future-value` → `info.status == "future-value"`)

In `scripts/tests/test_issue_parser_properties.py` — verify after adding `STATUS_SYNONYMS` that none of the canonical values (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`) accidentally appear in the synonym map keys (which would be a logic error). A simple `assert` at module level or a dedicated test case suffices.

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py:18` — `parse_frontmatter()` is the normalization site; add `STATUS_SYNONYMS` map and apply to every call
- `scripts/little_loops/issue_parser.py:872` — remove `"completed"` from `("done", "cancelled", "deferred", "completed")` terminal tuple in issue loader
- `scripts/little_loops/cli/issues/skip.py:40` — remove `"completed"` from `("done", "cancelled", "deferred", "completed")` terminal tuple in `cmd_skip()`
- `scripts/little_loops/cli/issues/search.py:138` — remove `"completed"` from `("done", "cancelled", "completed")` in `_load_issues_with_status()`
- `scripts/tests/test_issue_parser.py` — add synonym unit tests to `TestFindIssues`
- `scripts/tests/test_issue_lifecycle.py` — add synonym regression guard to `TestVerifyIssueCompleted`
- `scripts/tests/test_issue_parser_properties.py` — add `STATUS_SYNONYMS` key-collision sanity check

### Narrow Normalization (Leave or Remove)
- `scripts/little_loops/issue_parser.py:487-489` — existing single-alias block (`"open"` + `completed_at` → `"done"`); can stay as-is once `parse_frontmatter()` handles the general case

### `verify_issue_completed()` — Indirect Beneficiary
- `scripts/little_loops/issue_lifecycle.py:369` — `verify_issue_completed()` re-reads `info.path` and calls `parse_frontmatter()` directly; its `("done", "cancelled")` tuple at line 400 does NOT need updating because `parse_frontmatter()` normalization will coerce `"completed"` → `"done"` before it is checked

### Tests — Existing Coverage
- `scripts/tests/test_issue_parser.py:984` — `TestFindIssues` class (pattern model for new synonym tests)
- `scripts/tests/test_issue_parser.py:1056` — `test_find_issues_skips_status_done` (canonical pattern to follow)
- `scripts/tests/test_issue_parser.py:1081` — `test_find_issues_skips_status_completed` **already exists** (skip writing this one; verify it passes after `parse_frontmatter()` change)
- `scripts/tests/test_issue_lifecycle.py:303` — `TestVerifyIssueCompleted` class with `done`/`cancelled`/`open`/missing-file tests (add synonym test here)

### Test Fixtures to Use
- `TestFindIssues` synonym tests: `temp_project_dir` (`conftest.py:56`) + `sample_config` dict (`conftest.py:66`) — write config to disk, build `BRConfig`, create issues inline
- `TestVerifyIssueCompleted` synonym test: `tmp_path` + `sample_config` (`test_issue_lifecycle.py:71`, returns `BRConfig`) + `mock_logger` (`test_issue_lifecycle.py:48`, `MagicMock(spec=Logger)`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The following files import `parse_frontmatter()` and will **automatically benefit** from normalization without requiring code changes. They are listed here for awareness — no edits needed in these files:
- `scripts/little_loops/issue_discovery/search.py` — `_get_all_issue_files()` uses `status in ("done", "cancelled")`: `status: completed` will now correctly resolve to `done` [Agent 1]
- `scripts/little_loops/sync.py` — `get_local_issues()` and `close_issues()` use the same pattern: files with `status: completed` will now be correctly excluded from active sync [Agent 1/2]
- `scripts/little_loops/issue_history/parsing.py` — scan functions use `fm.get("status") != "done"`: files with `status: completed` now correctly included in history [Agent 1/2]
- `scripts/little_loops/cli/sprint/run.py` — pre-completion skip guard: `status: completed` now correctly skips the issue [Agent 1/2]

**Event state namespace — DO NOT CHANGE:** `state.py:mark_completed()`, `fsm/persistence.py` (lines 529, 567), `docs/reference/EVENT-SCHEMA.md` (lines 591, 595), and `docs/reference/schemas/state_issue_completed.json` all use `"completed"` as an FSM loop event/state value — this is a completely separate namespace from issue frontmatter status and must not be modified. [Agent 2]

### Files to Modify (Original List)

- `scripts/little_loops/frontmatter.py` (preferred normalization site) — add `STATUS_SYNONYMS` map + apply on every `parse_frontmatter()` call
- `scripts/little_loops/issue_parser.py` (~line 487-489, ~line 872) — extend narrow block if not fully subsumed; remove `"completed"` from terminal tuple
- `scripts/little_loops/cli/issues/skip.py` — remove `"completed"` from terminal tuple
- `scripts/little_loops/cli/issues/search.py` (~line 138) — remove `"completed"` from tuple
- `scripts/tests/test_issue_parser.py` — add synonym unit tests
- `scripts/tests/test_issue_lifecycle.py` — add `TestVerifyIssueCompleted` synonym regression guard
- `scripts/tests/test_issue_parser_properties.py` — add sanity check that canonical values aren't in synonym map keys

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New test file to add tests to:**
- `scripts/tests/test_frontmatter.py` — `TestParseFrontmatter` class exists but has no `status:` tests. Add one test per synonym (`complete`, `completed`, `finished`, `closed`, `in-progress`, `in progress`, `wip`) verifying `result["status"]` equals the canonical value, plus one passthrough test for unknown values. This is the primary normalization site and must be covered here. Pattern: `content = "---\nstatus: completed\n---\n\n# Title\n"` → `assert parse_frontmatter(content)["status"] == "done"` [Agent 1/3]

**Test that will break and must be updated:**
- `scripts/tests/test_issues_cli.py` — `test_skip_completed_issue_returns_error` writes `status: completed` to a fixture file and calls `cmd_skip()` via `main_issues()`. After normalization, `cmd_skip()` sees `status == "done"` and the error message will say `"has status 'done'"` — the existing assertion `assert "completed" in captured.err.lower()` will fail. Update to `assert "done" in captured.err.lower()` (or check for the generic "not an active issue" phrase). [Agent 2]

**Optional integration gap:**
- `scripts/tests/test_issues_search.py` — `TestSearchStatusFilter` — no fixture currently uses `status: completed`. Adding one case would confirm the `_load_issues_with_status()` dead-code removal works end-to-end (not required for this issue but closes the coverage gap). [Agent 3]

## Scope Boundaries

- **In scope**: Normalization in `parse_frontmatter()` only; dead-code removal of `"completed"` arms from three terminal-state tuples; test suite additions.
- **Out of scope**: Migrating existing issue files on disk (no bulk rewrite of `status: completed` files); changing FSM loop event/state values (`state.py`, `fsm/persistence.py`) which use `"completed"` in a separate namespace; adding new canonical status values.

## Acceptance Criteria

1. `verify_issue_completed()` returns `True` for a file containing `status: completed`
2. `parse_frontmatter()` output has `status == "done"` for every synonym in the map
3. Unknown status values pass through unchanged
4. All three dead-code `"completed"` arms removed
5. Full test suite passes

## Impact

- **Effort**: Small — ~40 lines of parser code, ~30 lines of tests
- **Risk**: Low — additive normalization; existing callers already work with canonical values

## Labels

- parser
- code-quality
- testing

## Status

**Open** | Created: 2026-05-17 | Priority: P3

## Resolution

Implemented `STATUS_SYNONYMS` map in `scripts/little_loops/frontmatter.py` as a module-level constant applied in `parse_frontmatter()`. Removed dead `"completed"` arms from `issue_parser.py`, `cli/issues/skip.py`, and `cli/issues/search.py`. Added full test suite: synonym parametrize tests in `test_frontmatter.py`, regression guard in `test_issue_lifecycle.py`, sanity checks in `test_issue_parser_properties.py`, and updated `test_issues_cli.py` to expect `"done"` error message. All 7024 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-17T08:38:48Z - `8b1164e0-6366-41c0-8bc7-414b81b8fe85.jsonl`
- `/ll:ready-issue` - 2026-05-17T08:33:48 - `8b1164e0-6366-41c0-8bc7-414b81b8fe85.jsonl`
- `/ll:wire-issue` - 2026-05-17T08:28:35 - `eed74e85-8b30-4e8a-9587-0adf8cb755dc.jsonl`
- `/ll:refine-issue` - 2026-05-17T08:22:52 - `f43d242c-55ef-4f4f-bf5d-7c2c581de27f.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
