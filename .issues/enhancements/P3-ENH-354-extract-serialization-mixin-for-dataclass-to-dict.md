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

---

**Open** | Created: 2026-02-12 | Priority: P3
