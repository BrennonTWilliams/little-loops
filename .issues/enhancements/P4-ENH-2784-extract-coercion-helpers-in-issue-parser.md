---
id: ENH-2784
type: ENH
title: Extract _coerce_tristate_bool / _coerce_optional_int helpers for 12 copy-pasted
  coercions in IssueParser.parse_file
priority: P4
status: open
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
parent: EPIC-2789
verify_verdict: VALID
confidence_score: 97
outcome_confidence: 82
score_complexity: 24
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 20
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
- **Line(s)**: 1968-2054 (ints at 1968-2005, bools at 2006-2044; refreshed
  2026-08-16 via `/ll:refine-issue`, was 1881-1950 as of 2026-08-12, was
  756-832 at scan commit fb567390)
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

Two bound helper methods on `IssueParser` — `self._coerce_tristate_bool(raw)`
and `self._coerce_optional_int(raw)` — called once per field.

**Shape decision (resolved 2026-08-16):** bound instance methods, not
module-level free functions. `issue_parser.py`'s own convention for every
prior extraction out of `parse_file()` is `self._parse_*` (see *Conventions in
Force* below), even where the body never touches `self`. The
`program_design.py` free-function precedent is a different module's habit and
loses to local consistency. This decision is closed — do not re-litigate it
during implementation.

## Proposed Solution

Add both methods to `IssueParser` and replace all twelve call sites.

This is a pure refactor, but **existing parser tests do not fully cover the
behavior being preserved** — the invalid-string fallback branch is untested at
the `parse_file()` level (see *Dependent Files (Tests)*). Characterization
tests for that branch are step 1, not a follow-up.

### Implementation Steps

1. **Add characterization tests first**, against the *current* code, and
   confirm they pass before touching `parse_file()`:
   - a non-digit int string (`effort: "abc"`) → `None`
   - a negative int (`effort: -1`) → `None` (see anti-goals)
   - a non-`true`/`false` bool string (`testable: "maybe"`) → `None`
   - a native YAML bool (`testable: true`) → `True` (pass-through path)
2. Add `_coerce_optional_int` and `_coerce_tristate_bool` as methods on
   `IssueParser`, reproducing the existing expressions verbatim.
3. Replace all 12 call sites.
4. Re-run the step-1 tests plus `scripts/tests/test_issue_parser.py` — all must
   pass unchanged.

### Anti-Goals — behavior that must NOT change

These are the quirks of the current expressions most likely to be "fixed" by
accident. Preserving them is the point of the refactor:

- `str(raw).isdigit()` rejects **negatives** (`-1` → `None`), **floats**
  (`"3.0"` → `None`), **signed strings** (`"+3"` → `None`), and any value with
  surrounding whitespace. A `try: int(raw) / except: None` rewrite — the
  obvious way to write this helper — silently changes all four. Keep the
  `isdigit()` guard.
- `_coerce_tristate_bool` **passes non-`str` values through unchanged**. A YAML
  `testable: 5` currently yields `5`, not `True` and not `None`. This means the
  literal return type is not `bool | None`; annotate honestly (accept `Any` in,
  and either return `Any` or `cast` at the boundary with a docstring note)
  rather than tightening the annotation and coercing to match it. Normalizing
  non-bool scalars is a behavior change and is out of scope.
- Case-insensitivity (`.lower()`) on the bool strings is load-bearing —
  `testable: "True"` must stay `True`.

### Acceptance Criteria

- [ ] `IssueParser` has exactly two new coercion methods; `parse_file()` has
      zero remaining inline `isdigit()`-guarded int coercions and zero
      remaining inline `isinstance(str)` tri-state-bool blocks.
- [ ] All 12 call sites (8 int, 4 bool — enumerated in *Files to Modify*) go
      through the helpers.
- [ ] `learning_tests_required` is left alone (13th coercion, different shape).
- [ ] New characterization tests from step 1 exist and pass both before and
      after the extraction.
- [ ] `python -m pytest scripts/tests/test_issue_parser.py` passes with no test
      modified — only additions.
- [ ] `python -m mypy scripts/little_loops/` is clean.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- Naming-convention note: `issue_parser.py` has no existing precedent for bare module-level `_coerce_*` functions on `IssueParser` — every other extraction from `parse_file()` (`_parse_priority`, `_parse_type_and_id`, `_read_content`, `_parse_product_impact`) is a bound instance method (`self._parse_*`). Elsewhere in the codebase, `scripts/little_loops/issues/program_design.py:363,375` (`_is_true`, `_coerce_date`) are bare module-level `_coerce_*` functions — one different module's convention, not this file's. The issue's originally proposed module-level-function shape was a valid choice either way; flagging the disagreement so the implementer picks knowingly rather than by accident. **Resolved 2026-08-16 in favor of bound instance methods** — see *Expected Behavior*.
- Test-coverage note: no existing test exercises the `else: None` fallback branch for a non-digit int string (e.g. `effort: "abc"`) or a non-`"true"/"false"` bool string (e.g. `testable: "maybe"`) at the `parse_file()` integration level. Confirming this branch's behavior is unchanged post-extraction (via existing or new tests) is part of verifying "pure refactor" holds, since it's the one behavior most likely to silently drift under a naive rewrite.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issue_parser.py` — coercion block to extract sits at lines 1968-2054 (not 1881-1950 as the Location section states; verified 2026-08-16). Refreshed count: exactly 8 `isdigit()`-guarded optional-int sites (`effort` 1970, `impact` 1971, `confidence_score` 1974-1978, `outcome_confidence` 1979-1981, `score_complexity` 1986-1990, `score_test_coverage` 1991-1995, `score_ambiguity` 1996-2000, `score_change_surface` 2001-2005) and exactly 4 `isinstance(str)`-guarded tri-state-bool sites (`testable` 2006-2014, `decision_needed` 2016-2024, `missing_artifacts` 2026-2034, `implementation_order_risk` 2036-2044) — 12 total, matching the issue title.
- A 13th, adjacent coercion — `learning_tests_required` (lines 2046-2054) — is comma-string-or-list → `list[str] | None` and does not match either the int or bool shape; out of scope for `_coerce_tristate_bool`/`_coerce_optional_int` as named.
- All 12 coerced locals flow unmodified into a single `IssueInfo(...)` constructor call (`scripts/little_loops/issue_parser.py:2139-2170`); no further transformation happens between coercion and that call.

### Conventions in Force
- Every other extraction from `IssueParser.parse_file()` on this same class is a bound instance method (`self._parse_priority`, `self._parse_type_and_id`, `self._read_content`, `self._parse_product_impact` — `issue_parser.py:2177,2203,2260,2440`), never a bare module-level function, even where the method body never touches `self`. `issue_parser.py` has no existing precedent for a module-level `_coerce_*` free function.
- Elsewhere in `scripts/little_loops/` (a different module), `scripts/little_loops/issues/program_design.py:363` (`_is_true`) and `:375` (`_coerce_date`) are bare module-level `_coerce_*`-style functions — `_is_true`'s docstring (366-368) explicitly names the `testable` flag in `issue_parser.py` as the coercion it mirrors, but returns `bool` (not `bool | None`) and is not reused by `issue_parser.py`. The two files disagree on bound-method vs free-function extraction; there is no single codebase-wide convention to defer to for this decision.
- `scripts/little_loops/frontmatter.py:parse_frontmatter()` (line 255) already has a `coerce_types: bool = False` flag that performs digit-string→int coercion internally (`_normalize_loaded_mapping` line 141, `_parse_frontmatter_lines` line 356). `issue_parser.py:1963` calls it with the default `coerce_types=False`, so the 8 int coercions are hand-rolled in `parse_file()` rather than delegated to this existing flag — a fact about current behavior, not a recommendation.

### Dependent Files (Tests)
- `scripts/tests/test_issue_parser.py` is the sole test file exercising these fields, in two tiers per field: dataclass-level tests (construct `IssueInfo(...)` directly, assert `to_dict()`/`from_dict()` round-trip) and integration tests through `parse_file()` (write a real issue file, call `parser.parse_file()`, assert the resulting field). Per-field locations: `testable` 2363-2490 (`test_parse_file_testable_false` 2438, `test_parse_file_testable_absent` 2465), `decision_needed` 2494-2621 (`test_parse_file_decision_needed_true` 2569, `_absent` 2596), `missing_artifacts` 2790-2917 (`test_parse_file_missing_artifacts_true` 2865, `_absent` 2892), `implementation_order_risk` 2921-3048 (`test_parse_file_implementation_order_risk_true` 2996, `_absent` 3023), score dimensions 3195-3364 (`test_parse_file_score_dimensions_present` 3298, `test_parse_file_score_dimensions_absent` 3336).
- `effort`/`impact`/`confidence_score`/`outcome_confidence` have no dedicated `test_parse_file_*` test directly exercising the `isdigit()` branch in `test_issue_parser.py`; their only coverage is indirect, through consumer-focused tests (`test_set_scores_cli.py`, `test_confidence_check_skill.py`, `test_check_readiness.py`, `test_issue_size_review_skill.py`).
- No existing test at the `parse_file()` integration level exercises a non-digit int string (e.g. `effort: "abc"`) or a non-`"true"/"false"` bool string (e.g. `testable: "maybe"`) for any of these 12 fields — only the "present as valid value" and "absent" branches are locked in by name. A pure refactor should add or confirm this branch is still covered before/after extraction, since it is the one behavior most likely to silently change under a naive rewrite.
- `scripts/tests/test_issue_parser_properties.py:95-213` is a Hypothesis round-trip test that constructs `IssueInfo` directly with already-typed values — it exercises dataclass serialization, not the frontmatter-string coercion path in `parse_file()`, so it does not cover this refactor.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- No new data shape introduced. `IssueInfo` (dataclass, `scripts/little_loops/issue_parser.py:1759`) already declares the target field types the two helpers must preserve exactly: `effort: int | None`, `impact: int | None`, `confidence_score: int | None`, `outcome_confidence: int | None`, `score_complexity: int | None`, `score_test_coverage: int | None`, `score_ambiguity: int | None`, `score_change_surface: int | None`, `testable: bool | None`, `decision_needed: bool | None`, `missing_artifacts: bool | None`, `implementation_order_risk: bool | None`.

### Signatures
- `IssueParser._coerce_optional_int(self, raw: Any) -> int | None` — must reproduce `int(raw) if raw is not None and str(raw).isdigit() else None` for all 8 int sites. The `isdigit()` guard is load-bearing, not incidental (see *Anti-Goals*).
- `IssueParser._coerce_tristate_bool(self, raw: Any) -> Any` — must reproduce `raw.lower() == "true" if isinstance(raw, str) and raw.lower() in ("true", "false") else (None if isinstance(raw, str) else raw)` for all 4 bool sites (non-string values, including native YAML `bool`/`None`, pass through unchanged; a string outside `{"true","false"}` collapses to `None`).
  - Return annotation is deliberately **not** `bool | None`: the non-`str` pass-through branch can return any YAML scalar (`testable: 5` → `5`). Annotating `bool | None` would be a false narrowing that mypy cannot catch (`frontmatter.get()` returns `Any`) and would invite a "fix" that changes behavior. If a `bool | None` signature is preferred at the call site for `IssueInfo` field typing, apply a `cast` at the call site and document why — do not coerce inside the helper.
- `IssueParser.parse_file(self, issue_path: Path) -> IssueInfo` — sole caller; no signature change to `parse_file` itself (`issue_parser.py:1942`).

### Call Path
`IssueParser.parse_file()` -> `frontmatter.get(<key>)` -> (new) `self._coerce_optional_int(raw)` / `self._coerce_tristate_bool(raw)` -> local variable -> `IssueInfo(...)` constructor call (`issue_parser.py:2139-2170`)

### Decision Rules
N/A — no new decision logic; this is a pure refactor of existing coercion rules, not a new gap kind, gate, or threshold.

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
- `/ll:confidence-check` - 2026-08-16T19:41:27 - `a441e649-6a94-4074-a117-b8df44bd2807.jsonl`
- `/ll:refine-issue` - 2026-08-16T19:32:45 - `b080f785-a1cd-46f7-b48c-7d2d05c3e170.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
