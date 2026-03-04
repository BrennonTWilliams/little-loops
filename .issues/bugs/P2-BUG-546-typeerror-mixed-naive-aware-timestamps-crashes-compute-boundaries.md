---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# BUG-546: `TypeError` on mixed naive/aware timestamps crashes `_compute_boundaries`

## Summary

`_compute_boundaries` catches `(ValueError, AttributeError)` when parsing timestamps but does not catch `TypeError`. Subtracting a timezone-naive `datetime` from a timezone-aware `datetime` (or vice versa) raises `TypeError`, which propagates uncaught through the entire analysis pipeline, crashing `ll-workflows analyze` with no output.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 561–566 (at scan commit: a574ea0)
- **Anchor**: `in function _compute_boundaries`, `try:` block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L561-L566)
- **Code**:
```python
try:
    ts_a = datetime.fromisoformat(ts_a_str.replace("Z", "+00:00"))
    ts_b = datetime.fromisoformat(ts_b_str.replace("Z", "+00:00"))
    gap_seconds = int((ts_b - ts_a).total_seconds())
except (ValueError, AttributeError):   # TypeError NOT caught
    gap_seconds = 0
```

## Current Behavior

If any message has a naive ISO timestamp (e.g., `"2026-01-15T10:00:00"` — no timezone suffix) while an adjacent message has an aware timestamp (e.g., `"2026-01-15T10:05:00Z"`), the subtraction `ts_b - ts_a` raises `TypeError: can't subtract offset-naive and offset-aware datetimes`. This exception propagates uncaught out of `_compute_boundaries`, crashing the analysis.

## Expected Behavior

Mixed naive/aware timestamps are handled gracefully. Either both timestamps are normalized to UTC before subtraction, or the pair is treated as `gap_seconds = 0` (same as the existing `ValueError` fallback).

## Steps to Reproduce

1. Create a JSONL input file where one message has timestamp `"2026-01-15T10:00:00"` (no tz) and an adjacent message has `"2026-01-15T10:05:00Z"`.
2. Run `ll-workflows analyze --input <file> --patterns <patterns.yaml>`.
3. Observe `TypeError: can't subtract offset-naive and offset-aware datetimes` crash.

## Actual Behavior

`ll-workflows analyze` crashes with an unhandled `TypeError`. The outer `except Exception as e` in `main()` catches it and prints a terse error, but no partial results are written.

## Root Cause

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Anchor**: `in function _compute_boundaries`
- **Cause**: The `except` clause lists `(ValueError, AttributeError)` but not `TypeError`. Subtracting mixed-awareness datetimes raises `TypeError` in CPython, which is not a subclass of either caught exception type.

## Proposed Solution

Add `TypeError` to the except clause, or normalize both timestamps to UTC before subtracting:

**Option A — add TypeError to except (minimal):**
```python
except (ValueError, AttributeError, TypeError):
    gap_seconds = 0
```

**Option B — normalize to UTC before subtract (preferred, also fixes related ENH-549):**
```python
def _parse_timestamps(messages: list[dict]) -> list[datetime]:
    result = []
    for msg in messages:
        ts_str = msg.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                # Normalize naive datetimes to UTC
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                result.append(ts)
            except (ValueError, AttributeError):
                pass
    return result
```

Note: This issue is related to ENH-549 (consolidate timestamp parsing), which could incorporate Option B as part of the refactor.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_compute_boundaries` except clause

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows` calls `_compute_boundaries`

### Similar Patterns
- `_link_sessions` has similar timestamp parsing (lines 443–455) — same fix may be needed there
- `_detect_workflows` also re-sorts by timestamp string (line 620)

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add test with mixed naive/aware timestamps

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `TypeError` to the `except` tuple in `_compute_boundaries`
2. Optionally normalize naive datetimes to UTC in all three timestamp-parsing sites (see ENH-549)
3. Add regression test with mixed naive/aware timestamp input

## Impact

- **Priority**: P2 - Crashes the entire analysis pipeline; any log file with mixed timestamp formats (common in cross-session JSONL) triggers the crash
- **Effort**: Small - One-word fix for Option A; small refactor for Option B
- **Risk**: Low - Narrowly scoped fix; existing tests still pass
- **Breaking Change**: No

## Labels

`bug`, `workflow-analyzer`, `crash`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P2
