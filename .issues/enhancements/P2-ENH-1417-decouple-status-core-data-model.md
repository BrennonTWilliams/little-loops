---
id: ENH-1417
type: ENH
priority: P2
status: open
parent_issue: ENH-1390
---

# ENH-1417: Decouple Issue Status — Core Data Model, IssueInfo, and Config Deprecation

## Summary

Establish the foundational data model changes required by ENH-1390: extend the `status:` enum in schema, add `status` as a first-class field on `IssueInfo`, and deprecate the `completed_dir`/`deferred_dir` config knobs. This child must land before all other ENH-1390 children since every subsequent change depends on `IssueInfo.status` existing.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Proposed Solution

### Step 1 — Extend `status:` enum

- `config-schema.json`: extend `status` enum to `open | in_progress | blocked | deferred | done | cancelled`
- Keep `completed_dir` / `deferred_dir` keys present but mark as deprecated (will be removed in ENH-1420 after migration)

### Step 9 — `config/core.py` config deprecation

- `scripts/little_loops/config/core.py`: deprecate `get_completed_dir()` and `get_deferred_dir()` methods on `BRConfig` (leave stubs that emit a deprecation warning so existing callers don't crash before other children update them)
- Update `create_parallel_config()` to remove `completed_dir`/`deferred_dir` from its serialized output (lines 387–388)

### Step 10 — `config/features.py` field removal

- `scripts/little_loops/config/features.py`: mark `completed_dir: str` and `deferred_dir: str` as deprecated in `IssuesConfig` dataclass and `from_dict()` parsing
- `config-schema.json`: mark both as deprecated/removed

### Step 1 (cont.) — `IssueInfo` dataclass + `parse_file()`

- `scripts/little_loops/issue_parser.py`: add `status: str = "open"` to `IssueInfo` dataclass
- In `IssueParser.parse_file()`, read `frontmatter.get("status", "open")` — follow the same int/bool coercion pattern used for `decision_needed`
- The `update_frontmatter()` function in `scripts/little_loops/frontmatter.py` is the correct write path for all status mutations

## Files to Modify

- `config-schema.json` — extend status enum; deprecate completed_dir/deferred_dir keys
- `scripts/little_loops/issue_parser.py` — add `status` to `IssueInfo`; read in `parse_file()`
- `scripts/little_loops/config/core.py` — deprecate `get_completed_dir()`/`get_deferred_dir()`; update `create_parallel_config()`
- `scripts/little_loops/config/features.py` — deprecate `completed_dir`/`deferred_dir` in `IssuesConfig`

## Tests to Update / Add

- `scripts/tests/test_issue_parser.py` — add `status:` field assertions in `parse_file()` tests; test default `"open"` when field absent
- `scripts/tests/test_config.py` — update `TestBRConfig::test_get_completed_dir` and `test_get_deferred_dir` to expect deprecation warnings; update `TestIssuesConfig::test_from_dict_with_all_fields` and `test_from_dict_with_defaults`

## Acceptance Criteria

- `IssueInfo` has a `status: str` field defaulting to `"open"`
- `IssueParser.parse_file()` reads `status:` from frontmatter
- `config-schema.json` enumerates the full status vocabulary
- `get_completed_dir()` and `get_deferred_dir()` emit deprecation warnings but don't break callers
- All existing tests pass

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
