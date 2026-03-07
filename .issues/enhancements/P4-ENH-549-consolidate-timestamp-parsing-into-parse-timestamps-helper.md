---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_compute_boundaries` adaptation**: The current pair-wise parsing at `workflow_sequence_analyzer.py:564–577` uses a single outer `try/except (ValueError, AttributeError, TypeError)` around both parses. The `AttributeError` catch covers the `None`-valued timestamp edge case (`msg.get("timestamp", "")` can return `None` if the key exists with a `None` value). The helper's `if ts_str:` guard handles this equivalently — `if None:` is falsy, so no `AttributeError` is possible. The caller should check `len(timestamps) == 2` and fall back to `gap_seconds = 0` to preserve current semantics. Use positional indexing `timestamps[0]`, `timestamps[1]` for the subtraction (not `max/min`) to preserve the "later minus earlier" ordering guarantee from the pre-sorted message list at `line:560`.

**Timezone convention confirmed**: All three functions use the identical strip-to-naive pattern (`if ts.tzinfo is not None: ts = ts.replace(tzinfo=None)`). The helper should do the same. Secondary `try/except TypeError` guards around `max(ts) - min(ts)` in `_link_sessions:457–459` and `_detect_workflows:703–705` exist as backstops but are unreachable after stripping; retain them in callers unchanged.

**Test class model**: Follow `TestComputeBoundaries` at `test_workflow_sequence_analyzer.py:922` — each method is `def test_<behavior>(self) -> None:` with a docstring. Key cases to add in `TestParseTimestamps`: empty list, Z-suffix input, naive input, `None` timestamp value, mixed valid/invalid messages, all-invalid messages.

## Scope Boundaries

- In scope: extract helper, update three call sites, add TypeError catch (per BUG-546)
- Out of scope: changing what callers do with the parsed timestamps (unit conversion stays in callers)

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — add `_parse_timestamps`, update three call sites

### Dependent Files (Callers/Importers)
- All three callers are internal to the same module

### Similar Patterns
- `scripts/little_loops/user_messages.py:524` and `:619` — identical `.replace("Z", "+00:00")` + `fromisoformat` + tzinfo-strip pattern in `_parse_command_record` and `_parse_user_record` (out of scope for this issue but future consolidation candidate; these also need `AttributeError` vs. `if ts_str:` consideration)
- `scripts/little_loops/issue_discovery/extraction.py:69` — `_extract_completion_date()` is the canonical private-helper extraction model: module-level `_helper()`, single `try/except ValueError`, `None` as failure sentinel

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add `TestParseTimestamps` unit tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Define `_parse_timestamps` near the top of the private function block in `workflow_sequence_analyzer.py` (before `_link_sessions` at line ~387); use `if ts_str:` guard and `except (ValueError, AttributeError, TypeError)` to cover all three original except-clause variants
2. Replace `_link_sessions:443–454` and `_detect_workflows:689–700` inline loops with `timestamps = _parse_timestamps(messages)`
3. Replace `_compute_boundaries:564–577` pair-wise block with `timestamps = _parse_timestamps([msg_a, msg_b])`; check `len(timestamps) == 2` before `timestamps[0]`, `timestamps[1]` subtraction
4. Add `TestParseTimestamps` class in `test_workflow_sequence_analyzer.py` following the pattern of `TestComputeBoundaries:922` — cover: empty list, Z-suffix, naive, `None` value, mixed valid/invalid, all-invalid
5. Run `python -m pytest scripts/tests/test_workflow_sequence_analyzer.py -v` — verify all existing tests still pass

## Impact

- **Priority**: P4 - Code quality / maintainability improvement; also closes the BUG-546 TypeError surface when combined
- **Effort**: Small - Mechanical extraction with test addition
- **Risk**: Low - Pure refactor, behavior-equivalent for valid inputs
- **Breaking Change**: No

## Verification Notes

Verified 2026-03-05 against current codebase (HEAD):

- **Duplicate code confirmed**: Three timestamp-parsing blocks still exist in `_link_sessions`, `_compute_boundaries`, and `_detect_workflows` in `workflow_sequence_analyzer.py`. Core enhancement remains valid.
- **BUG-546 already resolved**: TypeError catch was added to all three blocks as part of BUG-546 fix (completed 2026-03-04). The proposed helper's `except (ValueError, AttributeError, TypeError)` clause reflects already-fixed state.
- **Line numbers shifted** since scan commit `a574ea0`: current approximate positions are lines 443–459 (`_link_sessions`), 560–579 (`_compute_boundaries`), 688–706 (`_detect_workflows`).
- **`_compute_boundaries` uses pair-wise parsing**: unlike the other two functions that build a list from a sequence of messages, `_compute_boundaries` parses two adjacent messages to compute a gap. The proposed `_parse_timestamps(messages) -> list[datetime]` helper applies directly to `_link_sessions` and `_detect_workflows`; `_compute_boundaries` would need a wrapper or separate call.
- **Dependencies**: All Blocked By / Blocks references verified — FEAT-556, FEAT-558, ENH-550, ENH-551 all exist and have correct backlinks.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- FEAT-558
- ENH-550
- ENH-551

## Blocked By

- FEAT-556

## Labels

`enhancement`, `refactor`, `workflow-analyzer`, `captured`

## API/Interface

N/A - No public API changes. `_parse_timestamps` is a private helper function internal to `workflow_sequence_analyzer.py`.

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: 3 duplicate try/except blocks confirmed

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:refine-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

---

## Status

**Open** | Created: 2026-03-04 | Priority: P4
