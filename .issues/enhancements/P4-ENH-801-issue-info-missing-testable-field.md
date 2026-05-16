---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-801: IssueInfo dataclass missing `testable` field

## Summary

`scripts/little_loops/issue_parser.py`'s `IssueInfo` dataclass does not include a `testable: bool | None = None` field, so automation tools (`ll-auto`, `ll-sprint`, `ll-parallel`) cannot read or filter issues by `testable: false`. The TDD skip introduced by ENH-800 only works within `manage-issue`'s skill-prompt logic; it cannot be leveraged at the scheduler level.

## Context

**Conversation mode**: Identified from conversation discussing ENH-800 resolution. ENH-800 explicitly deferred this as out of scope: "If `testable` should be queryable by Python CLI tools, add `testable: bool | None = None` here. Scope decision: `manage-issue` reads frontmatter directly from the markdown without going through `IssueInfo`. No Python code change is required for the core fix."

Now that the core fix is in, this follow-up captures the deferred work.

## Motivation

When `ll-auto` or `ll-sprint` process a batch of issues, they have no way to know which ones have `testable: false` without parsing raw YAML themselves. If a future enhancement wanted to skip the TDD phase at the scheduler level or log a warning before invoking `manage-issue` on a non-testable issue, `IssueInfo` would need to expose this field. It also makes the data model complete and consistent with the other runtime fields (`confidence_score`, `outcome_confidence`).

## Current Behavior

`IssueInfo` at `scripts/little_loops/issue_parser.py:201-236` defines fields like `confidence_score: int | None = None` and `outcome_confidence: int | None = None`, but has no `testable` field. Accessing `issue.testable` on any parsed issue raises `AttributeError`.

## Expected Behavior

`IssueInfo` exposes `testable: bool | None = None`. Any Python CLI tool can call `issue.testable` to get `False` (skip TDD), `True` (force testable), or `None` (absent, treated as testable). `docs/reference/API.md` updated to document the new field.

## Proposed Solution

Add `testable: bool | None = None` to the `IssueInfo` dataclass at `scripts/little_loops/issue_parser.py`. Update `docs/reference/API.md`. No behavior change to any CLI tool is required — this is purely a data-model addition.

## Implementation Steps

1. Add `testable: bool | None = None` to `IssueInfo` dataclass at `issue_parser.py:235` (after `outcome_confidence: int | None = None` at line 234)
2. Add `testable_value = frontmatter.get("testable")` in `IssueParser.parse_file()` at `issue_parser.py:348` (after the `outcome_confidence` block ending at line 347) — no coercion guard needed; YAML already delivers `True`/`False`/`None`
3. Add `testable=testable_value` to the `IssueInfo(...)` constructor call at `issue_parser.py:374` (after `outcome_confidence=outcome_confidence` at line 373)
4. Add `"testable": self.testable` to `IssueInfo.to_dict()` at `issue_parser.py:263` (after `"outcome_confidence"` at line 262)
5. Add `testable=data.get("testable")` to `IssueInfo.from_dict()` at `issue_parser.py:284` (after `outcome_confidence=data.get("outcome_confidence")` at line 283)
6. Update `docs/reference/API.md:512` to insert `testable: bool | None = None` after `outcome_confidence` (before `session_commands` at line 512)
7. Add unit tests in `scripts/tests/test_issue_parser.py` following the 5-test pattern at lines 149–208 (default None, True, False, `to_dict`, `from_dict` absent) — see test pattern under Integration Map below

## API/Interface

- `IssueInfo.testable: bool | None` — `None` means field absent (treated as testable); `False` means TDD phase should be skipped

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py:235` — add `testable: bool | None = None` to `IssueInfo` dataclass (after `outcome_confidence` at line 234)
- `scripts/little_loops/issue_parser.py:348` — add `testable_value = frontmatter.get("testable")` in `parse_file`
- `scripts/little_loops/issue_parser.py:374` — add `testable=testable_value` to `IssueInfo(...)` constructor (after `outcome_confidence=outcome_confidence` at line 373)
- `scripts/little_loops/issue_parser.py:263` — add `"testable": self.testable` to `to_dict()`
- `scripts/little_loops/issue_parser.py:284` — add `testable=data.get("testable")` to `from_dict()`
- `docs/reference/API.md:512` — insert `testable: bool | None = None` between `outcome_confidence` and `session_commands`

### Tests
- `scripts/tests/test_issue_parser.py` — add tests following the pattern at lines 149–208:
  - `test_testable_default_none` — `IssueInfo(...)` without `testable` → `info.testable is None`
  - `test_testable_false` — `IssueInfo(..., testable=False)` → `info.testable is False`
  - `test_testable_true` — `IssueInfo(..., testable=True)` → `info.testable is True`
  - `test_testable_in_to_dict` — `info.to_dict()["testable"] == False`
  - `test_testable_from_dict_missing` — `IssueInfo.from_dict(data)` without key → `.testable is None`
  - Integration: `parse_file` on issue with `testable: false` frontmatter → `info.testable is False`
  - Integration: `parse_file` on issue with no `testable` key → `info.testable is None`

### Documentation
- `docs/reference/API.md:490-514` — `IssueInfo` field reference section (section header at line 492)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `parse_file` requires explicit extraction** — `frontmatter.parse_frontmatter()` returns a plain `dict`; `IssueParser.parse_file()` at lines 338–347 explicitly calls `frontmatter.get("key")` for every field. Adding the dataclass field alone is not sufficient — `frontmatter.get("testable")` must also be called in `parse_file`, and `testable=` must be passed to the `IssueInfo(...)` constructor at line 360.

**No conversion guard needed** — Unlike `confidence_score`/`outcome_confidence` (which use `isdigit()` guards), `testable` is already a native Python `bool` from YAML parsing. Direct `frontmatter.get("testable")` is safe.

**`to_dict` and `from_dict` are hand-written** — neither uses introspection. Both must be updated manually (`to_dict` at lines 247-265, `from_dict` at lines 267-286).

**Property-based test** — `test_issue_parser_properties.py:73-115` uses Hypothesis for roundtrip tests. The `testable` field strategy would be `st.one_of(st.none(), st.booleans())`.

**Exact parse_file context** (`issue_parser.py:338-347`):
```python
confidence_raw = frontmatter.get("confidence_score")
outcome_raw = frontmatter.get("outcome_confidence")
confidence_score = (int(confidence_raw) if ... else None)
outcome_confidence = (int(outcome_raw) if ... else None)
# ← insert: testable_value = frontmatter.get("testable")
```

**Exact IssueInfo constructor context** (`issue_parser.py:360-376`):
```python
return IssueInfo(
    ...
    confidence_score=confidence_score,
    outcome_confidence=outcome_confidence,  # line 373
    # ← insert: testable=testable_value,
    session_commands=session_commands,
    ...
)
```

## Scope Boundaries

- **In scope**: Add `testable` field to `IssueInfo`; update API docs; add unit tests
- **Out of scope**: Changing scheduler behavior in `ll-auto`/`ll-sprint` to act on the field (separate issue if needed)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `issue-parser`, `tdd-mode`, `IssueInfo`

---

## Status

**Completed** | Created: 2026-03-17 | Resolved: 2026-03-17 | Priority: P4

## Resolution

Added `testable: bool | None = None` to `IssueInfo` dataclass. Updated `to_dict`, `from_dict`, and `parse_file` to handle the field. `parse_file` coerces the string `"true"`/`"false"` from the custom frontmatter parser to native Python `bool`. Updated `docs/reference/API.md`. Added 8 unit + integration tests (TDD red→green).

## Session Log
- `/ll:confidence-check` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc1ff18-42ef-4540-b785-bc387c36dac3.jsonl`
- `/ll:refine-issue` - 2026-03-18T03:32:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5395d74-c078-4139-90ed-8a907702ecaf.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0873aba7-6e24-4b9d-bf58-565ee42ebe88.jsonl`
- `/ll:manage-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc1ff18-42ef-4540-b785-bc387c36dac3.jsonl`
