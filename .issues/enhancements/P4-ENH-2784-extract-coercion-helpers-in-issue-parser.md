---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
---

# ENH-2784: Extract `_coerce_tristate_bool` / `_coerce_optional_int` helpers for 12 copy-pasted coercions in `IssueParser.parse_file`

## Summary

`IssueParser.parse_file()` copy-pastes the same "string → tri-state bool"
coercion four times (`testable`, `decision_needed`, `missing_artifacts`,
`implementation_order_risk`) and the same `isdigit()`-guarded optional-int
coercion eight times (`effort`, `impact`, `confidence_score`,
`outcome_confidence`, `score_complexity`, `score_test_coverage`,
`score_ambiguity`, `score_change_surface`).

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 756-832 (ints at 756-793, bools at 794-832, at scan commit: fb567390)
- **Anchor**: `in method IssueParser.parse_file()`
- **Code**:
```python
testable_raw = frontmatter.get("testable")
if isinstance(testable_raw, str):
    testable_value: bool | None = (
        testable_raw.lower() == "true"
        if testable_raw.lower() in ("true", "false")
        else None
    )
else:
    testable_value = testable_raw
...
effort = int(effort_raw) if effort_raw is not None and str(effort_raw).isdigit() else None
```

## Current Behavior

Twelve inline copies of two coercion rules; any future rule change (e.g.
accepting `"yes"/"no"`) must be made in up to twelve places.

## Expected Behavior

Two module-level helpers — `_coerce_tristate_bool(raw) -> bool | None` and
`_coerce_optional_int(raw) -> int | None` — called once per field.

## Proposed Solution

Add both helpers near the top of `issue_parser.py` and replace all twelve
call sites. Pure refactor; existing parser tests cover behavior.

## Impact

- **Effort**: Small
- Shortens `parse_file()`, single point of change for coercion rules.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
