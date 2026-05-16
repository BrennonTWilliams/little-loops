---
id: ENH-1417
type: ENH
priority: P2
status: done

decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-10T15:44:53Z
parent: ENH-1390
---

# ENH-1417: Decouple Issue Status — Core Data Model, IssueInfo, and Config Deprecation

## Summary

Establish the foundational data model changes required by ENH-1390: extend the `status:` enum in schema, add `status` as a first-class field on `IssueInfo`, and deprecate the `completed_dir`/`deferred_dir` config knobs. This child must land before all other ENH-1390 children since every subsequent change depends on `IssueInfo.status` existing.

## Current Behavior

Issue status is inferred solely from filesystem directory location: issues in `completed_dir` are treated as "done", issues in `deferred_dir` as "deferred", all others as "open". `IssueInfo` has no `status` field — callers must compare file paths against `BRConfig.get_completed_dir()` or `BRConfig.get_deferred_dir()` to determine status. The `config-schema.json` `status` enum is incomplete (missing `in_progress`, `blocked`, `cancelled`).

## Expected Behavior

- `IssueInfo` gains `status: str = "open"` populated from frontmatter by `IssueParser.parse_file()`
- `config-schema.json` enumerates the full status vocabulary: `open | in_progress | blocked | deferred | done | cancelled`
- `BRConfig.get_completed_dir()` and `get_deferred_dir()` emit `DeprecationWarning` but remain callable so existing callers don't break before sibling issues update them
- `IssuesConfig` marks `completed_dir`/`deferred_dir` as deprecated fields; `create_parallel_config()` stops serializing them

## Motivation

All ENH-1390 children depend on `IssueInfo.status` existing as a first-class frontmatter field. Without this foundational change, status-aware CLI filtering, directory-independent status queries, and frontmatter-driven status transitions cannot be built. This is the data contract that unblocks every sibling issue in the ENH-1390 decomposition.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact anchors for all 4 files to modify:**
- `issue_parser.py:202` — `IssueInfo` dataclass (add `status: str = "open"` field here)
- `issue_parser.py:347` — `IssueParser.parse_file()` (add `status = frontmatter.get("status", "open")` before the `IssueInfo(...)` constructor)
- `issue_parser.py:478–503` — `IssueInfo(...)` constructor call (add `status=status` keyword arg)
- `issue_parser.py:295` — `IssueInfo.from_dict()` also needs `status=data.get("status", "open")` — **not mentioned in Proposed Solution above**
- `config/core.py:220` — `get_completed_dir()`, `config/core.py:224` — `get_deferred_dir()`
- `config/core.py:387–388` — `create_parallel_config()` serializes `completed_dir`/`deferred_dir` here
- `config/features.py:126` — `IssuesConfig` dataclass (`completed_dir: str = "completed"`, `deferred_dir: str = "deferred"` at lines 131–132)
- `config/features.py:139` — `IssuesConfig.from_dict()`, reads these fields at lines 160–161

**DeprecationWarning pattern (no existing examples in codebase):**
```python
import warnings
# In BRConfig.get_completed_dir() and get_deferred_dir():
warnings.warn(
    "BRConfig.get_completed_dir() is deprecated; use IssueInfo.status instead",
    DeprecationWarning,
    stacklevel=2,
)
```
The only `warnings.warn()` call in the codebase is in `issues/anchor_sweep.py:77` without a category — this deprecation should be the first to use `DeprecationWarning` explicitly.

## Implementation Steps

1. **`config-schema.json`**: Add `status` enum property under `issues.properties`; add `deprecated` descriptions to `completed_dir` and `deferred_dir` entries
2. **`issue_parser.py:202`**: Add `status: str = "open"` field to `IssueInfo` dataclass
3. **`issue_parser.py:347`** (`parse_file()`): Add `status = frontmatter.get("status", "open")` (plain string, no coercion needed)
4. **`issue_parser.py:478–503`** (constructor): Add `status=status` to `IssueInfo(...)` keyword args
4a. **`issue_parser.py`** (`to_dict()`): Add `"status": self.status` to the returned dict — **this step was missing from the original plan; without it, serialization round-trips lose the status value and `QueuedIssue.to_dict()` in `parallel/types.py` will produce incomplete state JSON**
5. **`issue_parser.py:295`** (`from_dict()`): Add `status=data.get("status", "open")` to `IssueInfo.from_dict()`
6. **`config/core.py:220,224`**: Add `import warnings`; wrap `get_completed_dir()` and `get_deferred_dir()` bodies with `warnings.warn(..., DeprecationWarning, stacklevel=2)` before returning
7. **`config/core.py:387–388`** (`create_parallel_config()`): Remove `completed_dir`/`deferred_dir` from serialized output
8. **`config/features.py:126,131–132`**: Update docstrings/comments on `completed_dir`/`deferred_dir` to mark as deprecated; keep fields functional
9. **`config/features.py:139`** (`from_dict()`): Keep parsing these fields (callers still provide them); add inline deprecation note in comment
10. **Tests**: Add `status: "open"` default assertion in `test_issue_parser.py`; update `test_config.py` to assert `DeprecationWarning` is emitted by `test_get_completed_dir` and `test_get_deferred_dir`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Add 8 new `status`-field test cases to `scripts/tests/test_issue_parser.py` following the `test_epic_*` pattern
12. Update `scripts/tests/test_config.py` — convert `test_get_completed_dir` and `test_get_deferred_dir` to use `pytest.warns(DeprecationWarning)`; add `test_create_parallel_config_excludes_deprecated_dirs`
13. Update `scripts/tests/test_issue_lifecycle.py` — suppress or expect `DeprecationWarning` from the ~18 `get_completed_dir()`/`get_deferred_dir()` calls
14. Update `scripts/tests/test_issue_parser.py::TestFindIssues::test_find_issues_skip_check_uses_two_globs_not_stat_per_file` — suppress or expect deprecation warning for its `config.get_completed_dir()` / `config.get_deferred_dir()` calls
15. Add `status` to the Hypothesis strategy and assertion list in `scripts/tests/test_issue_parser_properties.py` roundtrip tests
16. Update `docs/reference/API.md` — add `status: str` to `IssueInfo` field list; add deprecation notices to `get_completed_dir()`, `get_deferred_dir()`, and `IssuesConfig.completed_dir`/`deferred_dir`
17. Update `docs/ARCHITECTURE.md` — add `status` to `IssueInfo` class diagram block; note deprecations on `BRConfig` block
18. Update `docs/reference/CONFIGURATION.md` — add deprecation notes to `completed_dir`/`deferred_dir` table rows

## Integration Map

### Files to Modify
- `config-schema.json` — extend status enum; deprecate completed_dir/deferred_dir keys
- `scripts/little_loops/issue_parser.py` — add `status` to `IssueInfo`; read in `parse_file()`
- `scripts/little_loops/config/core.py` — deprecate `get_completed_dir()`/`get_deferred_dir()`; update `create_parallel_config()`
- `scripts/little_loops/config/features.py` — deprecate `completed_dir`/`deferred_dir` in `IssuesConfig`

### Dependent Files (Callers/Importers)

All 22+ call sites for `get_completed_dir()` / `get_deferred_dir()` — these will receive `DeprecationWarning` after this change but require no modifications in this issue (addressed in ENH-1418/ENH-1419):

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/types.py` — `QueuedIssue.to_dict()` delegates to `self.issue_info.to_dict()`; `status` will automatically flow into parallel state JSON once added to `IssueInfo.to_dict()`
- `scripts/little_loops/issue_history/parsing.py` — accesses `completed_dir`/`deferred_dir` from config (not through deprecated methods; no change needed here)
- `scripts/little_loops/cli/issues/show.py:138-144` — hardcodes `path.parent.name == "completed"/"deferred"` comparison to derive display status (ENH-1418 scope, not affected by this change)
- `scripts/little_loops/cli/issues/skip.py:38-39` — hardcodes `parent_name in ("completed", "deferred")` guard (ENH-1418 scope)
- `scripts/little_loops/issue_manager.py:783` — hardcodes `".issues" / "completed"` path entirely, bypassing `get_completed_dir()` — will not receive deprecation warning, out of ENH-1417 scope
- `scripts/little_loops/cli/history.py:199` — hardcodes `issues_dir / "completed"` string concat, bypassing config — out of ENH-1417 scope

**`get_completed_dir()` callers:**
- `scripts/little_loops/issue_parser.py:133` — `get_next_issue_number()` builds `dirs_to_scan`
- `scripts/little_loops/issue_parser.py:760` — `find_issues()` builds `completed_names` frozenset
- `scripts/little_loops/issue_lifecycle.py:465` — `verify_issue_completed()`
- `scripts/little_loops/issue_lifecycle.py:615` — `close_issue()`
- `scripts/little_loops/issue_lifecycle.py:706` — `complete_issue_lifecycle()`
- `scripts/little_loops/issue_discovery/search.py:61` — `discover_issues()`
- `scripts/little_loops/dependency_mapper/operations.py:268` — `build_dependency_map()`
- `scripts/little_loops/parallel/orchestrator.py:1210` — completion handler
- `scripts/little_loops/sync.py:279,756,926,1078` — 4 calls in `_collect_local_issues()` and helpers
- `scripts/little_loops/cli/issues/search.py:133` — `_load_issues_with_status()`
- `scripts/little_loops/cli/issues/show.py:81` — `run_show()`
- `scripts/little_loops/cli/sprint/edit.py:74` — `_get_completed_issue_ids()`
- `scripts/little_loops/cli/sprint/run.py:164` — `run_sprint()`
- `scripts/little_loops/cli/deps.py:47` — `run_deps()`

**`get_deferred_dir()` callers:**
- `scripts/little_loops/issue_parser.py:761` — `find_issues()` builds `deferred_names` frozenset
- `scripts/little_loops/issue_lifecycle.py:811` — `defer_issue()`
- `scripts/little_loops/issue_discovery/search.py:68` — `discover_issues()`
- `scripts/little_loops/dependency_mapper/operations.py:269` — `build_dependency_map()`
- `scripts/little_loops/cli/issues/search.py:142` — `_load_issues_with_status()`
- `scripts/little_loops/cli/issues/show.py:82` — `run_show()`
- `scripts/little_loops/cli/deps.py:47` — `run_deps()`

**Key downstream integration point (ENH-1418 scope):**
- `scripts/little_loops/cli/issues/search.py:106` — `_load_issues_with_status()` derives status as `'active'/'completed'/'deferred'` purely from directory location. After ENH-1418, it should read `IssueInfo.status` instead.

### Similar Patterns
- `decision_needed` field on `IssueInfo` (lines 421–429 in `issue_parser.py`) — but **`status` is a plain string, not bool**: use `frontmatter.get("status", "open")` directly, no coercion needed
- `update_frontmatter()` in `scripts/little_loops/frontmatter.py` (write path for all frontmatter mutations)

### Tests
- `scripts/tests/test_issue_parser.py` — add `status:` field assertions in `parse_file()` tests; test default `"open"` when field absent
- `scripts/tests/test_config.py` — update `TestBRConfig::test_get_completed_dir` and `test_get_deferred_dir` to expect deprecation warnings; update `TestIssuesConfig::test_from_dict_with_all_fields` and `test_from_dict_with_defaults`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — 8 new test cases to write (follow `test_epic_*` pattern at lines 327–374 for structure):
  - `test_status_default_open` — `IssueInfo` without `status` kwarg defaults to `"open"`
  - `test_status_value` — `IssueInfo(…, status="blocked")` stores the value
  - `test_status_in_to_dict` — `to_dict()` includes `"status"` key
  - `test_status_from_dict` — `from_dict({…, "status": "blocked"})` restores value
  - `test_status_from_dict_missing` — `from_dict({})` defaults to `"open"`
  - `test_status_roundtrip` — `from_dict(original.to_dict())` round-trips value
  - `test_parse_file_status_from_frontmatter` — `parse_file()` reads `status:` key; follow `test_parse_discovered_by_from_frontmatter` pattern
  - `test_parse_file_status_default_open` — `parse_file()` defaults to `"open"` when key absent
- `scripts/tests/test_config.py` — new test: `test_create_parallel_config_excludes_deprecated_dirs` asserts neither `completed_dir` nor `deferred_dir` appears in `create_parallel_config()` serialized output; use `pytest.warns(DeprecationWarning, match="get_completed_dir")` pattern (no existing `pytest.warns` usage in suite — establish it here)
- `scripts/tests/test_issue_lifecycle.py` — ~18 calls to `sample_config.get_completed_dir()` / `get_deferred_dir()` will emit `DeprecationWarning` on every run; update tests to either suppress with `warnings.filterwarnings("ignore", category=DeprecationWarning)` in the relevant fixtures/teardown, or wrap with `pytest.warns` where the deprecation is the assertion focus
- `scripts/tests/test_issue_parser.py::TestFindIssues::test_find_issues_skip_check_uses_two_globs_not_stat_per_file` (lines 1160–1198) — calls `config.get_completed_dir()` / `config.get_deferred_dir()` directly; will emit warnings — suppress or expect
- `scripts/tests/test_issue_parser_properties.py` — Hypothesis roundtrip at lines 106, 322, 371 does not cover `status`; add `status` to the `@given` strategy and the assertion list

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `IssueInfo` class block (line ~549) missing `status: str` in field list; `BRConfig.get_completed_dir()` (line ~180) and `get_deferred_dir()` (line ~188) entries need deprecation notices; `IssuesConfig` fields (line ~334) `completed_dir`/`deferred_dir` need deprecation marking; line ~1667 usage example shows bare `config.get_completed_dir()` call
- `docs/ARCHITECTURE.md` — class diagram (lines 548–566): `BRConfig` block shows `get_completed_dir()` / `get_deferred_dir()` without deprecation note; `IssueInfo` block has no `status` field
- `docs/reference/CONFIGURATION.md` — lines 254–255: table rows document `completed_dir` and `deferred_dir` as active config keys; add deprecation note pointing to `IssueInfo.status`

Note: `commands/` and `skills/*/SKILL.md` templates that use `{{config.issues.completed_dir}}` / `{{config.issues.deferred_dir}}` template variables are **not** affected by this issue — `BRConfig.to_dict()` still serializes these fields; template breakage is deferred to the removal phase (ENH-1420).

### Configuration
- `config-schema.json` — schema change; `.ll/ll-config.json` files with `completed_dir`/`deferred_dir` will continue to work but produce deprecation warnings

## Scope Boundaries

Out of scope for this child issue:
- CLI command changes or new status-filtering flags (ENH-1418+)
- Physical directory migration or moving issue files (later child)
- Removing deprecated `completed_dir`/`deferred_dir` config fields (reserved for post-migration cleanup, ENH-1420)
- Status transition logic or validation rules
- Changes to how issues are listed or displayed in ll-issues

## Acceptance Criteria

- `IssueInfo` has a `status: str` field defaulting to `"open"`
- `IssueParser.parse_file()` reads `status:` from frontmatter
- `config-schema.json` enumerates the full status vocabulary
- `get_completed_dir()` and `get_deferred_dir()` emit deprecation warnings but don't break callers
- All existing tests pass

## Impact

- **Priority**: P2 — Foundational blocker; all other ENH-1390 children depend on `IssueInfo.status` existing
- **Effort**: Small — 4 files, ~50 lines; patterns directly follow existing `decision_needed` field handling
- **Risk**: Medium — Modifies core `IssueInfo` dataclass used throughout codebase; deprecation stubs prevent breakage
- **Breaking Change**: No — deprecated methods remain callable; config fields remain parseable

## Labels

`enhancement`, `data-model`, `status-decoupling`, `enh-1390-child`, `captured`

## Resolution

Implemented all foundational data model changes per the issue specification:

- `IssueInfo.status: str = "open"` field added to the dataclass, `to_dict()`, and `from_dict()`
- `IssueParser.parse_file()` reads `status` from frontmatter (plain string, no coercion)
- `config-schema.json` enumerates full status vocabulary: `open | in_progress | blocked | deferred | done | cancelled`; `completed_dir`/`deferred_dir` descriptions marked deprecated
- `BRConfig.get_completed_dir()` and `get_deferred_dir()` emit `DeprecationWarning` with `stacklevel=2`
- `BRConfig.to_dict()` no longer serializes `completed_dir`/`deferred_dir` in the `issues` section
- `IssuesConfig` fields marked deprecated via inline comments; `from_dict()` kept functional for backward compat
- 8 new `TestIssueInfoStatus` tests; deprecation assertions in `TestBRConfig`; Hypothesis roundtrip tests updated; lifecycle and parser tests suppress deprecation warnings

## Session Log
- `/ll:ready-issue` - 2026-05-10T15:34:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c248d48-1fe8-4886-a6e5-367cab86121e.jsonl`
- `/ll:wire-issue` - 2026-05-10T15:28:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
- `/ll:refine-issue` - 2026-05-10T15:21:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ef2c075-8981-478d-a20e-ac74e296f30e.jsonl`
- `/ll:format-issue` - 2026-05-10T15:17:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a80bb47e-7a06-453e-a016-be6695656fd0.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`
- `/ll:confidence-check` - 2026-05-10T16:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdd93a3b-a3e2-4f8e-8544-faa16506a581.jsonl`
- `/ll:manage-issue` - 2026-05-10T15:44:53Z - current session

---

**Done** | Created: 2026-05-10 | Completed: 2026-05-10 | Priority: P2
