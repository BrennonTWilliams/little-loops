---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# ENH-549: Consolidate 3 copies of timestamp-parsing try/except into `_parse_timestamps` helper

## Summary

The pattern of iterating messages, normalizing `"Z"` suffixes, calling `datetime.fromisoformat`, catching `ValueError`, and collecting valid timestamps into a list is duplicated verbatim in three private functions (`_link_sessions`, `_detect_workflows`, `_compute_boundaries`). Extracting a `_parse_timestamps` helper eliminates the duplication and provides a single place to fix related bugs (see BUG-546).

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 443–455 (`_link_sessions`), 561–566 (`_compute_boundaries`), 679–690 (`_detect_workflows`) (at scan commit: a574ea0)
- **Anchor**: Three separate `try: datetime.fromisoformat(...)` blocks
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L443)

## Current Behavior

The same ~12-line parse-normalize-collect block is copied in three functions. A fix to the parsing logic (e.g., handling naive/aware datetime mixing per BUG-546) must be applied to all three copies independently.

## Expected Behavior

A single `_parse_timestamps(messages: list[dict]) -> list[datetime]` helper owns all timestamp parsing. Each caller uses the helper and converts the result to its needed unit (hours, seconds, minutes).

## Motivation

Any bug fix to timestamp parsing (e.g., BUG-546's missing `TypeError` catch) currently requires three coordinated edits. As the number of functions that need timestamps grows, the duplication compounds. The helper also provides a natural place to add timezone normalization.

## Proposed Solution

```python
def _parse_timestamps(messages: list[dict[str, Any]]) -> list[datetime]:
    """Parse valid ISO timestamps from a list of messages, normalizing to UTC."""
    timestamps = []
    for msg in messages:
        ts_str = msg.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)  # normalize naive to UTC
                timestamps.append(ts)
            except (ValueError, AttributeError, TypeError):
                pass
    return timestamps
```

Each of the three call sites is replaced with a one-liner:
```python
timestamps = _parse_timestamps(session_a + session_b)   # _link_sessions
timestamps = _parse_timestamps([msg_a, msg_b])           # _compute_boundaries
timestamps = _parse_timestamps(segment)                  # _detect_workflows
```

## Scope Boundaries

- In scope: extract helper, update three call sites, add TypeError catch (per BUG-546)
- Out of scope: changing what callers do with the parsed timestamps (unit conversion stays in callers)

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — add `_parse_timestamps`, update three call sites

### Dependent Files (Callers/Importers)
- All three callers are internal to the same module

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add `TestParseTimestamps` unit tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Define `_parse_timestamps` near the top of the private function block, incorporating TypeError fix from BUG-546
2. Replace the three inline timestamp-parsing loops with calls to the helper
3. Verify unit tests for all three parent functions still pass

## Impact

- **Priority**: P4 - Code quality / maintainability improvement; also closes the BUG-546 TypeError surface when combined
- **Effort**: Small - Mechanical extraction with test addition
- **Risk**: Low - Pure refactor, behavior-equivalent for valid inputs
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- FEAT-558

## Labels

`enhancement`, `refactor`, `workflow-analyzer`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P4
