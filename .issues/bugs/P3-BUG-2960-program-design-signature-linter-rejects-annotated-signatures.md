---
id: BUG-2960
title: Program Design signature linter rejects trailing prose, comma-bearing annotations,
  and keyword-only markers
type: BUG
priority: P3
status: done
captured_at: '2026-08-01T04:12:30Z'
completed_at: '2026-08-01T06:54:33Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
labels:
- issues
- format-check
- program-design
- lint
confidence_score: 100
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 24
score_change_surface: 24
---

# BUG-2960: Program Design signature linter rejects annotated/documented signatures

## Summary

`parse_signature_lines()` (`scripts/little_loops/issues/program_design.py`) backs the `program_design_nonspecific` gate in `ll-issues format-check`. It is whole-line anchored on purpose — an English sentence containing parentheses must not count as a signature — but the anchoring is tight enough to also reject three shapes that are *more* precise than the bare form it accepts. The practical effect is inverted incentives: to pass the gate an author must strip type detail and trailing explanation from a signature line.

Found while editing ENH-2941, where the section passed on exactly one bare line (`batch_similarity(threshold: float, issues_dir: Path) -> list[SimilarityPair]`); annotating that line flipped the issue to non-compliant.

## Current Behavior

Three false-negative classes, reproduced directly against the parser:

```python
from little_loops.issues.program_design import parse_signature_lines as p
p('- `foo(a: int) -> Bar`')                        # ['- `foo(a: int) -> Bar`']  MATCH
p('- `foo(a: int) -> Bar` — does a thing')         # []  MISS
p('- `foo(a: Literal["x", "y"]) -> Bar`')          # []  MISS
p('- `foo(a: int, *, b: str) -> Bar`')             # []  MISS
```

Causes, all in the same module:

1. **Trailing prose** — `_TAIL = r"`?[ \t]*[.:;]?[ \t]*$"` requires end-of-line right after the closing backtick, so the common `` - `sig` — explanation `` bullet never matches. This is the highest-frequency miss: describing a signature inline is the natural way to write the section.
2. **Comma inside an annotation** — `_params_are_signature_like()` splits `params` on a bare `,`, so `Literal["x", "y"]`, `dict[str, int]` as a *parameter* type, or `Callable[[int], str]` yields fragments (`Literal["x"`) that fail `_PARAM`. Note `_TYPE`/`_SUBSCRIPT` already handle nested subscripts correctly for *return* types — only the parameter split is naive.
3. **Bare `*` keyword-only marker** — `_PARAM` is `^[ \t]*(?:\*{0,2})[A-Za-z_]\w*...`, requiring an identifier after the stars, so a standalone `*` separator fails. `**kwargs` and `*args` are fine; only the marker form breaks.

## Expected Behavior

All four lines above are recognized as signature-shaped, while the gate keeps rejecting prose. The docstring's stated contract — "an English sentence that merely contains parentheses or a colon does not match" — is preserved; these fixes narrow what counts as prose, they do not loosen the anchor.

Specifically:
- A recognized signature followed by a separator (`—`, `--`, `:`) and free text still counts, anchored on the signature part.
- Parameter lists split at top-level commas only (bracket/paren depth aware), matching how `_SUBSCRIPT` already treats return types.
- A bare `*` (and `/`, the positional-only marker) is accepted as a parameter-list entry.

## Steps to Reproduce

1. From the repo root, run:

   ```bash
   python3 -c "
   from little_loops.issues.program_design import parse_signature_lines as p
   for c in ['- \`foo(a: int) -> Bar\`',
             '- \`foo(a: int) -> Bar\` — does a thing',
             '- \`foo(a: Literal[\"x\", \"y\"]) -> Bar\`',
             '- \`foo(a: int, *, b: str) -> Bar\`']:
       print(('MATCH ' if p(c) else 'MISS  '), c)
   "
   ```

2. Observe the first line matches and the other three return `[]`.
3. End-to-end equivalent: take any issue whose `## Program Design` passes `ll-issues format-check <ID>`, append ` — explanation` to its only bare signature line, and re-run — the issue now reports `program_design_nonspecific`.

## Root Cause

`scripts/little_loops/issues/program_design.py`:

- `_TAIL` (module constant) — anchors to `$` with no allowance for a description clause.
- `_params_are_signature_like()` — `all(_PARAM.match(part) for part in stripped.split(","))`; the naive `str.split(",")`.
- `_PARAM` (module constant) — `(?:\*{0,2})[A-Za-z_]\w*` mandates an identifier.

## Motivation

The gate is meant to push authors from prose toward real signatures. Today it does the reverse at the margin: the workaround applied to ENH-2941 was to write `against: str = "open"` in the graded line and move the true `Literal["open", "all"]` plus the keyword-only intent into a separate paragraph the linter ignores. Every issue that documents its signatures well pays this tax, and the recorded design is less precise than the author intended — which degrades exactly the artifact ENH-2852 introduced the section to produce.

## Proposed Solution

Three contained changes, each independently testable:

1. **Depth-aware parameter split** — replace `stripped.split(",")` in `_params_are_signature_like()` with a scanner that only splits at bracket/paren/brace depth 0. Reuses the same nesting assumption `_SUBSCRIPT` already encodes.
2. **Marker params** — extend `_PARAM` to accept a lone `*` or `/` entry: `^[ \t]*(?:[*/]|(?:\*{0,2})[A-Za-z_]\w*(?:[ \t]*:[ \t]*TYPE)?(?:[ \t]*=[ \t]*\S+)?)[ \t]*$`.
3. **Optional trailing description** — allow `_TAIL` to be followed by a separator + free text, e.g. append `(?:[ \t]*(?:—|--|–|:)[ \t]*\S.*)?` before `$`. Keep the separator mandatory so a bare sentence with parens still fails; the existing negative fixture ("It returns a verdict (specific or not) to the caller.") must stay rejected.

Fix 3 carries the only real regression risk — it is what keeps the gate honest — so gate it on the existing negative cases plus new ones.

## Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issues/program_design.py` — `grade_program_design()` consumes `parse_signature_lines()`; no signature change needed
- `scripts/little_loops/issue_parser.py` — `check_format_gaps()` surfaces the verdict as `program_design_nonspecific`
- `scripts/little_loops/cli/issues/format_check.py` — reports the gap; unaffected
- Any issue currently passing the gate must keep passing — the changes are strictly widening except where the negative fixtures pin behavior

### Tests

- `scripts/tests/` — locate the existing `program_design` test module and add positive cases for all three shapes plus negative cases asserting prose is still rejected (sentence-with-parens, prose containing a colon, a bullet of plain English ending in a period)
- Corpus regression check: run `ll-issues format-check` across `.issues/` before and after; the set of issues reporting `program_design_nonspecific` should only shrink

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_program_design_gate.py`, class `TestSignatureShape` — add new methods after `test_rejects_prose_that_merely_contains_parentheses` (lines 161–172), following the class's existing conventions (no `@pytest.mark.parametrize`, import inside method, `"\n".join([...])` for multi-line bodies): `test_split_top_level_respects_bracket_depth`, `test_split_top_level_empty_and_single`, `test_accepts_keyword_only_and_positional_only_markers`, `test_accepts_trailing_description_after_signature`, `test_accepts_comma_bearing_annotation_in_params`, `test_reproduction_lines_from_bug_2960` [Agent 3 finding]
- Re-run unmodified as regression pins after the widening: `test_accepts_varied_real_signature_shapes` (lines 136–153, must still return `len(found) == 7`), `test_accepts_nested_generic_return_types` (lines 155–159), `TestGrading.test_prose_only_section_is_not_specific` (lines 189–195, uses the `_PROSE_SECTION` fixture — full sentences with colons/parens that must stay non-specific) [Agent 3 finding]
- `scripts/tests/spike/program_design_specificity/test_program_design.py` — confirmed *actually collected* by `python -m pytest scripts/tests/` (no `norecursedirs`/`collect_ignore` excludes `spike/`; matching `-pytest-*.pyc` assertion-rewrite cache present), but it imports its own local `spike/program_design_specificity/program_design.py` copy via relative import, not `little_loops.issues.program_design` — so it cannot regress from this fix and needs no changes. The issue's own note to "ignore" it refers to relevance, not exclusion from the test run [Agent 3 finding]
- No update needed in `scripts/tests/test_ll_issues_format_check.py` or `scripts/tests/test_autodev_loop.py` — both assert only on the `program_design_nonspecific` key's presence/wiring (e.g. `assert "program_design_nonspecific" in action`), not on which specific inputs populate it; their fixtures contain no signature-shaped substrings and are unaffected by the regex widening [Agent 2 finding, confirmed by Agent 3]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The canonical test module is `scripts/tests/test_program_design_gate.py`, class `TestSignatureShape` (line ~133) — the pinned negative fixture `test_rejects_prose_that_merely_contains_parentheses` (lines 161–172) is the exact regression to re-run first per Implementation Step 3, and `test_accepts_varied_real_signature_shapes` (lines 136–153) is the sibling positive-case test to extend. Ignore `scripts/tests/spike/program_design_specificity/test_program_design.py` — it's a superseded spike copy of the same test class, not the live suite.
- Test-writing conventions in this module (for consistency): no `@pytest.mark.parametrize`, one plainly-named `test_...` method per shape with a short rationale docstring; imports (`from little_loops.issues.program_design import parse_signature_lines`) are done inside each test method, not at module top; multi-line bodies are built with `"\n".join([...])` bullet lists.
- Confirmed no reusable depth-aware/bracket-balance comma splitter exists elsewhere in `scripts/little_loops/**` to import for `_split_top_level()` — the nearest precedent is the string/escape-aware brace-depth scan in `scripts/little_loops/output/parse.py:87-119` (tracks `in_string`/`escaped` so quoted braces don't perturb depth, single bracket kind only). `_split_top_level()` is genuinely new code, not a refactor-to-reuse; it should track `()[]{}` together plus quoted-string state, following that scan's string-awareness since parameter annotations contain quoted literals (`Literal["x", "y"]`).
- Exact current line numbers confirmed by direct read of `scripts/little_loops/issues/program_design.py`: `_SUBSCRIPT`/`_TYPE` at lines 58–59, `_TAIL` at line 63, `_SIG_CALL` at lines 66–71, `_SIG_FIELD` at lines 74–76, `_PARAM` at lines 81–85, `_params_are_signature_like()` at lines 117–122, `parse_signature_lines()` at lines 168–186.

## Implementation Steps

1. Add the depth-aware comma splitter and unit-test it in isolation.
2. Widen `_PARAM` for `*` / `/` markers.
3. Widen `_TAIL` for separator-delimited trailing prose; re-run the negative fixtures first, then the positives.
4. Add the four reproduction lines from Current Behavior as explicit test cases.
5. Re-run the full-corpus format-check diff to confirm no issue newly fails.

## Program Design

### Types

No new types. All three changes are to module-level regex constants and one private helper in `scripts/little_loops/issues/program_design.py`.

### Signatures

One new private helper; the two public entry points keep their current signatures.

- `_split_top_level(params: str) -> list[str]`
  - Splits a parameter list at commas that sit at bracket/paren/brace depth 0, leaving `Literal["x", "y"]` and `dict[str, int]` intact. Called only from `_params_are_signature_like()`.
- `_PARAM`, `_TAIL` — widened in place (module constants, not functions).

### Call Path

- `parse_signature_lines()` -> `_params_are_signature_like()` -> `_split_top_level()`
- `grade_program_design()` -> `parse_signature_lines()`
- `check_format_gaps()` -> `grade_program_design()`

## Scope Boundaries

- In scope: `_split_top_level()`, the `_PARAM` marker widening, the `_TAIL` trailing-description widening, and tests covering all three plus the existing negative cases.
- Out of scope: `_SIG_FIELD` / dataclass-field matching (unaffected), `extract_call_path_anchors()` and anchor resolution, the `program_design_not_applicable` opt-out (BUG-2956), and any change to the deprecation-warning noise in `format-check` (ENH-2961).

## Impact

- **Priority**: P3 - Not blocking; the workaround is to write a bare signature line, at the cost of precision in the recorded design
- **Effort**: Small - three regex/parsing changes in one module, plus tests
- **Risk**: Medium - the trailing-prose relaxation is the mechanism that keeps the gate from going inert; needs negative-case coverage before it lands

## Status

**Open** | Created: 2026-08-01 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-01T06:54:07 - `6201bfcb-a642-4fa9-90f4-f799a05797ec.jsonl`
- `/ll:ready-issue` - 2026-08-01T06:46:18 - `72978efa-333a-49fd-a66c-935d119e23be.jsonl`
- `/ll:confidence-check` - 2026-08-01T06:44:39 - `508988ab-ad5a-4a77-b3db-641b11464771.jsonl`
- `/ll:wire-issue` - 2026-08-01T06:42:39 - `3007eb33-75db-4f3e-8a15-7b99beef78db.jsonl`
- `/ll:refine-issue` - 2026-08-01T06:36:16 - `78c31198-5245-4b8f-8499-1d2db98b1459.jsonl`
- `/ll:capture-issue` - 2026-08-01T04:14:35 - `955e48a5-4e30-44bc-914f-c2bd87008116.jsonl`
