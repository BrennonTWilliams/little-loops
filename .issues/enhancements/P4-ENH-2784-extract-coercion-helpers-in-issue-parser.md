---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
parent: EPIC-2789
verify_verdict: NON_VALID
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
- **Line(s)**: 1881-1950 (ints at 1881-1914, bools at 1920-1950; refreshed
  2026-08-12, was 756-832 at scan commit fb567390)
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

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: duplicated
coercion logic (8+ isdigit()-guarded int coercions, 5 isinstance(str)
tri-state bool coercions) still present, no helpers extracted yet. Cited line
numbers are stale — code is now around lines 1879-1958, not 756-832 (file has
grown substantially). Core claim accurate.

**2026-08-12** (`/ll:verify-issues`): Re-verified: core claim unchanged, no
extraction helper exists yet. Refreshed the Location citation to the precise
current range (1881-1950) rather than the earlier approximate 1879-1958.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
