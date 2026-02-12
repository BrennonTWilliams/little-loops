---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-354: Extract serialization mixin for dataclass to_dict boilerplate

## Summary

Over 20 dataclasses in `issue_history.py` have hand-written `to_dict()` methods that manually map fields to dict entries with custom serialization for dates, paths, and nested objects. This is ~400 lines of boilerplate that could be a shared mixin.

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Line(s)**: 90-100, 128-139, 167-180 (and 20+ more) (at scan commit: be30013)
- **Anchor**: All `to_dict` methods in issue_history dataclasses

## Current Behavior

Each dataclass has a hand-written `to_dict()` with manual serialization for `date.isoformat()`, `Path` to str, nested `to_dict()` calls, and list truncation.

## Expected Behavior

A shared mixin or decorator provides generic `to_dict()` with type-aware serialization.

## Proposed Solution

Create a `SerializableMixin` using `dataclasses.fields()` and `isinstance` checks to auto-generate `to_dict()`. Custom serialization (like list truncation) can use field metadata: `field(metadata={"max_items": 10})`.

## Scope Boundaries

- Only apply to `issue_history.py` dataclasses initially
- Do not change JSON output format (must be backward compatible)

## Impact

- **Priority**: P3 - Significant code reduction, easier maintenance
- **Effort**: Medium - Need to handle all serialization edge cases
- **Risk**: Medium - Must preserve exact JSON output format
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P3

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-12
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: MEDIUM
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: MEDIUM

### Rationale
While reducing ~400 lines of boilerplate is appealing, the medium risk of breaking JSON compatibility and the complexity of handling all edge cases (dates, paths, nested objects, list truncation) make this lower priority. Higher complexity and risk for a code cleanup that doesn't directly improve functionality.
