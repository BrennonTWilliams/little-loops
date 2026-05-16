---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# ENH-550: Cache `_get_message_category` UUID→category index to eliminate O(C×E) scans repeated per message

## Summary

`_get_message_category` performs a full nested scan of all categories and their example messages on every call. Inside `_detect_workflows`, it is called twice per workflow message: once when building `segment_categories` and once when constructing the `Workflow.messages` list. Replacing the nested scan with a pre-built flat dict reduces repeated work to O(1) per lookup.

## Location

- **File**: `scripts/little_loops/workflow_sequence/analysis.py`
- **Line(s)**: 484 (function), 533, 583 (call sites) — updated 2026-03-23 after ENH-840 split `workflow_sequence_analyzer.py` into the `workflow_sequence/` package; was 664, 713, 763 prior to split
- **Anchor**: `function _get_message_category`, `_detect_workflows` call sites
- **Code**:
```python
def _get_message_category(msg_uuid: str, patterns: dict[str, Any]) -> str | None:
    """Look up message category from Step 1 patterns."""
    for category_info in patterns.get("category_distribution", []):
        for example in category_info.get("example_messages", []):
            if example.get("uuid") == msg_uuid:
                category = category_info.get("category")
                return category if isinstance(category, str) else None
    return None
```

Called at line 533 (building `segment_categories`) and line 583 (inside `Workflow(...)` messages list comprehension) — twice per message in every matched segment.

## Current Behavior

For each detected workflow, every message in each matched segment triggers two full O(C×E) scans (C = number of categories, E = example messages per category). With large patterns files the same scan work is repeated for every message in every workflow.

## Expected Behavior

A UUID→category dict is built once from `patterns` at the start of `_detect_workflows`. All lookups are O(1) dict accesses. The two call sites are replaced with direct dict lookups.

## Motivation

The function name and structure imply it is a pure lookup, but the implementation is a nested linear scan. As the patterns file grows (more categories, more examples), the cost grows multiplicatively per workflow message. Pre-building the index makes the cost proportional to the size of the patterns file, not to the number of messages analyzed.

## Proposed Solution

Add a builder helper and use it at the top of `_detect_workflows`:

```python
def _build_category_index(patterns: dict[str, Any]) -> dict[str, str]:
    """Build a flat UUID → category mapping from patterns category_distribution."""
    index: dict[str, str] = {}
    for category_info in patterns.get("category_distribution", []):
        category = category_info.get("category")
        if not isinstance(category, str):
            continue
        for example in category_info.get("example_messages", []):
            uuid = example.get("uuid")
            if uuid:
                index[uuid] = category
    return index

def _detect_workflows(...):
    category_index = _build_category_index(patterns)   # built once
    ...
    # Replace: _get_message_category(msg.get("uuid", ""), patterns)
    # With:    category_index.get(msg.get("uuid", ""))
```

## Scope Boundaries

- In scope: add `_build_category_index`, replace two call sites in `_detect_workflows`, keep `_get_message_category` if used elsewhere or remove if not
- Out of scope: changing how categories are structured in the patterns YAML

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence/analysis.py` — add `_build_category_index` near `_get_message_category` (line 484), update `_detect_workflows` (line 494)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py:35` — imports `_get_message_category` from `little_loops.workflow_sequence.analysis`; add `_build_category_index` to the same import line
- `scripts/tests/test_workflow_sequence_analyzer.py:1819` — `TestGetMessageCategory` class tests `_get_message_category` directly; **do not remove the function** (it has direct test coverage at lines 1836, 1841, 1845, 1857)

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/workflow_sequence/analysis.py:507-509` — `boundary_before: dict[str, bool]` is built at the top of `_detect_workflows` using the same build-once/query-N-times pattern. Follow this convention exactly: typed annotation on empty dict, plain `for` loop to populate, `.get(key, default)` at call sites.

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add `TestBuildCategoryIndex` unit test; follow the `TestGetMessageCategory` structure (lines 1819–1862): stateless class, private `_patterns()` helper method (not a `@pytest.fixture`), single-verb docstrings, edge cases: empty input, non-str category, UUID collision

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/workflow_sequence/analysis.py`, add `_build_category_index(patterns)` near `_get_message_category` (line 484)
2. At the start of `_detect_workflows` (line 494), add `category_index = _build_category_index(patterns)` following the `boundary_before` pattern at lines 507–509
3. Replace the call at line 533 and line 583 with `category_index.get(msg.get("uuid", ""))`
4. Keep `_get_message_category` — it has no production callers after this change, but `TestGetMessageCategory` (test_workflow_sequence_analyzer.py:1819) tests it directly; removing it would break existing tests without benefit
5. In `scripts/tests/test_workflow_sequence_analyzer.py`, add `_build_category_index` to the import at line 35 and add `TestBuildCategoryIndex` following the `TestGetMessageCategory` structure

## Impact

- **Priority**: P4 - Performance improvement; visible only with large patterns files, but the fix is trivial
- **Effort**: Small - Add one helper, update two call sites
- **Risk**: Low - Pure performance refactor, output unchanged
- **Breaking Change**: No

## Verification Notes

- **2026-03-05** — VALID. `_get_message_category` confirmed at line 611 (was 600–607 at scan commit a574ea0); two call sites in `_detect_workflows` at lines 660 and 720 (was 649, 704). Function body unchanged. No `_build_category_index` exists yet. Dependency backlinks verified: FEAT-558 and ENH-551 both list `Blocked By: ENH-550`; FEAT-556 lists `Blocks: ENH-550`.
- **2026-03-21** — DEP_ISSUES → VALID. Removed broken `Blocks: ENH-554` reference — ENH-554 does not exist in active or completed issues.
- **2026-03-22** — VALID. Location section updated to line 664 (function), 713 and 763 (call sites in `_detect_workflows`). No `_build_category_index` exists. ENH-551 `Blocked By: ENH-550` backlink confirmed. Enhancement not yet applied.
- **2026-03-23** — VALID (BLOCKER RESOLVED). ENH-840 completed (commit 97870cfd). `workflow_sequence_analyzer.py` is now the `workflow_sequence/` package; `_get_message_category` is at `analysis.py:484`, `_detect_workflows` at `analysis.py:494`, call sites at lines 533 and 583. No `_build_category_index` exists. Test file unchanged at `test_workflow_sequence_analyzer.py`; `TestGetMessageCategory` at line 1819; import from `little_loops.workflow_sequence.analysis` at line 35. All file paths and line numbers updated. Blocked By: ENH-840 removed.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-551

_(FEAT-558 removed from Blocks — completed; ENH-554 removed — does not exist in active or completed issues)_

## Blocked By

_(ENH-840 removed — completed via commit 97870cfd; `workflow_sequence_analyzer.py` is now the `workflow_sequence/` package)_

## Labels

`enhancement`, `performance`, `workflow-analyzer`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-03-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a33da7f-6dc1-4101-a62c-c07c4786fb89.jsonl`
- `/ll:ready-issue` - 2026-03-23T05:43:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/117eda3f-f381-423a-a235-0a8dda325b52.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6a36166-5e73-45bb-938b-edeb0b423ed7.jsonl`
- `/ll:refine-issue` - 2026-03-23T05:38:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37e2d58e-d5ca-4ed9-a92e-52148240513f.jsonl`
- `/ll:go-no-go` - 2026-03-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a632870-cb24-4a1a-8138-d42ee91025d7.jsonl` — NO-GO: ENH-840 (P3) remains open with zero implementation commits; implementing ENH-550 now guarantees rework when ENH-840 splits the monolith; previous NO-GO verdict unchanged.
- `/ll:refine-issue` - 2026-03-23T03:54:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9de232c9-07da-4ba3-978b-405f2c3dd345.jsonl`
- `/ll:verify-issues` - 2026-03-23T03:43:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11c70934-6502-4380-92e1-3f88c099af60.jsonl`
- `/ll:go-no-go` - 2026-03-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dae687ee-b9b3-4550-a249-d0875a127443.jsonl` — NO-GO: ENH-840 (P3) is a higher-priority open refactor that moves `_detect_workflows` to its final location; implement ENH-550 after ENH-840.
- `/ll:verify-issues` - 2026-03-23T00:58:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a5c131f-cda7-4559-9788-d72a050aa303.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: no _build_category_index helper exists
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: no `_build_category_index` exists; two `_get_message_category` call sites still in `_detect_workflows`; removed stale Blocks: FEAT-558 (completed)

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

---

## Resolution

**Completed**: 2026-03-23

### Changes Made

- `scripts/little_loops/workflow_sequence/analysis.py`: Added `_build_category_index(patterns)` after `_get_message_category`; updated `_detect_workflows` to build the index once at the top (following the `boundary_before` pattern) and replaced the two `_get_message_category` call sites (lines 533, 583) with `category_index.get(msg.get("uuid", ""))`.
- `scripts/tests/test_workflow_sequence_analyzer.py`: Added `_build_category_index` to import; added `TestBuildCategoryIndex` class with 5 tests (flat index, empty patterns, non-str category, empty uuid, uuid collision).

### Verification

- TDD Red → Green: 2 assertion failures on stub, all 9 tests pass on implementation
- Full suite: 3846 passed, 4 skipped
- `ruff check`: all checks passed
- `mypy`: no new errors (pre-existing wcwidth issue unrelated)

## Status

**Completed** | Created: 2026-03-04 | Priority: P4
