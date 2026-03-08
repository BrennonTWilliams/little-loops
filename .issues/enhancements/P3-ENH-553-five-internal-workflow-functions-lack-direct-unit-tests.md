---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 97
---

# ENH-553: 4 internal `workflow_sequence_analyzer` functions lack direct unit tests

## Summary

Four internal functions in `workflow_sequence_analyzer` — `_detect_handoff`, `_group_by_session`, `_load_patterns`, and `_get_message_category` — are not imported or tested directly in `test_workflow_sequence_analyzer.py`. Their edge cases (missing keys, empty inputs, malformed data, non-string values) are only exercised indirectly through end-to-end `analyze_workflows` tests, if at all. (`_load_messages` was added to the import block and is no longer missing.)

## Location

- **File**: `scripts/tests/test_workflow_sequence_analyzer.py`
- **Line(s)**: 14–30 (import block — none of the five functions appear) (at scan commit: a574ea0)
- **Anchor**: module-level import block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/tests/test_workflow_sequence_analyzer.py#L14-L30)
- **Code**:
```python
from little_loops.workflow_sequence_analyzer import (
    EntityCluster, SessionLink, Workflow, WorkflowAnalysis, WorkflowBoundary,
    _cluster_by_entities, _compute_boundaries, _detect_workflows, _link_sessions,
    analyze_workflows, calculate_boundary_weight, entity_overlap,
    extract_entities, get_verb_class, semantic_similarity,
    # Missing: _detect_handoff, _group_by_session,
    #          _load_patterns, _get_message_category
)
```

## Current Behavior

The four remaining untested functions are covered only through `TestAnalyzeWorkflows` integration tests. Untested edge cases include:
- `_detect_handoff`: matching a marker mid-sentence vs. at start of content
- `_group_by_session`: message with no `session_id` key (defaults to `"unknown"`)
- `_load_patterns`: missing YAML keys, empty patterns file
- `_get_message_category`: `category` field is not a `str` (isinstance guard is exercised)

Note: `_load_messages` has been added to the import block and now has direct tests (see 2026-03-06 scope reduction).

## Expected Behavior

Each function has a dedicated test class with at least one test for primary behavior and one for each edge case, parallel to the existing `TestExtractEntities`, `TestLinkSessions`, etc.

## Motivation

BUG-547 (malformed JSONL crash) was only discoverable through code review because no direct test for `_load_messages` exists. Direct unit tests would have caught it at authoring time. Adding tests for these five functions closes the coverage gap and ensures future changes to them are caught by the test suite.

## Proposed Solution

Add the following test classes to `test_workflow_sequence_analyzer.py`:

```python
class TestDetectHandoff:
    def test_handoff_marker_detected(self) -> None: ...
    def test_no_marker_returns_false(self) -> None: ...
    def test_marker_mid_sentence(self) -> None: ...

class TestGroupBySession:
    def test_groups_by_session_id(self) -> None: ...
    def test_missing_session_id_defaults_to_unknown(self) -> None: ...
    def test_empty_messages(self) -> None: ...

class TestLoadPatterns:
    def test_loads_valid_yaml(self) -> None: ...
    def test_missing_file_raises(self) -> None: ...

class TestGetMessageCategory:
    def test_finds_category_by_uuid(self) -> None: ...
    def test_returns_none_for_unknown_uuid(self) -> None: ...
    def test_returns_none_when_category_not_str(self) -> None: ...
```

Note: `TestLoadMessages` is no longer needed — `_load_messages` was added to the test import block and direct tests exist (BUG-547 fix included).

## Scope Boundaries

- In scope: add direct unit tests for the five listed functions
- Out of scope: changing the implementation of the tested functions (unless BUG-547 fix is included)

## Integration Map

### Files to Modify
- `scripts/tests/test_workflow_sequence_analyzer.py` — add ~60–80 lines of test code

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py` — no changes needed

### Similar Patterns
- Existing `TestExtractEntities`, `TestCalculateBoundaryWeight`, `TestEntityOverlap` classes show the pattern

### Tests
- This is the test file itself

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Import the four functions at the top of the test file (`_detect_handoff`, `_group_by_session`, `_load_patterns`, `_get_message_category`)
2. Add `TestDetectHandoff` with 3 test cases
3. Add `TestGroupBySession` with 3 test cases
4. Add `TestLoadPatterns` with 2 test cases
5. Add `TestGetMessageCategory` with 3 test cases

## Impact

- **Priority**: P3 - Coverage gap that allowed BUG-547 to go undetected; closes a risk for future regressions
- **Effort**: Medium - ~80 lines of new test code, no implementation changes
- **Risk**: Low - Additive test additions only
- **Breaking Change**: No

## Verification Notes

- **2026-03-05** — VALID. All five functions (`_detect_handoff` L374, `_group_by_session` L363, `_load_messages` L346, `_load_patterns` L357, `_get_message_category` L611) confirmed present in `workflow_sequence_analyzer.py` at current HEAD. Import block in `test_workflow_sequence_analyzer.py` (L14–30) confirmed: none of the five functions appear. Dependency: FEAT-556 has `Blocked By: ENH-553` ✓ and ENH-553 has `Blocks: FEAT-556` ✓.
- **2026-03-06** — NEEDS_UPDATE. `_load_messages` is now imported in test file (L24). Scope reduced from 5 to 4 functions. Remaining untested: `_detect_handoff`, `_group_by_session`, `_load_patterns`, `_get_message_category`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Blocks

- FEAT-556

## Labels

`enhancement`, `testing`, `workflow-analyzer`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — NEEDS_UPDATE: _load_messages now imported; scope reduced to 4 functions
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `_load_messages` confirmed imported at test file line 24 with tests at 1506+; 4 remaining untested functions confirmed: `_detect_handoff`, `_group_by_session`, `_load_patterns`, `_get_message_category`; issue content updated to reflect scope

## Status

**Open** | Created: 2026-03-04 | Priority: P3
