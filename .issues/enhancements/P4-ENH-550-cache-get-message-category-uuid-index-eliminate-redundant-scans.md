---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# ENH-550: Cache `_get_message_category` UUID→category index to eliminate O(C×E) scans repeated per message

## Summary

`_get_message_category` performs a full nested scan of all categories and their example messages on every call. Inside `_detect_workflows`, it is called twice per workflow message: once when building `segment_categories` and once when constructing the `Workflow.messages` list. Replacing the nested scan with a pre-built flat dict reduces repeated work to O(1) per lookup.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 600–607, 649, 704 (at scan commit: a574ea0)
- **Anchor**: `function _get_message_category`, `_detect_workflows` call sites
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L600-L607)
- **Code**:
```python
def _get_message_category(msg_uuid: str, patterns: dict[str, Any]) -> str | None:
    for category_info in patterns.get("category_distribution", []):
        for example in category_info.get("example_messages", []):
            if example.get("uuid") == msg_uuid:
                category = category_info.get("category")
                return category if isinstance(category, str) else None
    return None
```

Called at line 649 and again at line 704 — twice per message in every matched segment.

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
- `scripts/little_loops/workflow_sequence_analyzer.py` — add `_build_category_index`, update `_detect_workflows`

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — imports `_get_message_category` for testing; may need update if function is removed

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add `TestBuildCategoryIndex` unit test

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_build_category_index(patterns)` near `_get_message_category`
2. At start of `_detect_workflows`, call `category_index = _build_category_index(patterns)`
3. Replace both `_get_message_category(...)` call sites with `category_index.get(...)`
4. Keep or remove `_get_message_category` based on whether it has other callers

## Impact

- **Priority**: P4 - Performance improvement; visible only with large patterns files, but the fix is trivial
- **Effort**: Small - Add one helper, update two call sites
- **Risk**: Low - Pure performance refactor, output unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `workflow-analyzer`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P4
