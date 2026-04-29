# BUG-1306: Issue ID Collapses to Priority Digit When Type Token Omitted From Filename

## Summary

When an issue file is named with a priority prefix but no type token (e.g. `P2-9096-foo.md` instead of the standard `P2-BUG-9096-foo.md`), `IssueParser` generates the issue ID from the wrong number in the filename. Every such issue collapses to the same ID — `BUG-2` — because the parser picks the priority digit instead of the actual issue number.

Reported externally by the blender-agents project, where an FSM loop produced filenames like `P2-9096-eval-specfile-gold-animation-bounce.md` and `ll-issues list` showed every result as `BUG-2`.

## Current Behavior

For a filename like `P2-9096-eval-specfile-gold-animation-bounce.md` placed in the `bugs/` directory:

1. `_parse_type_and_id` (`scripts/little_loops/issue_parser.py:526`) tries to match known prefixes (`BUG-(\d+)`, `FEAT-(\d+)`, `ENH-(\d+)`). None match because the type token is absent.
2. It falls back to inferring the category from the parent directory name (`bugs/`) and calls `_generate_id_from_filename`.
3. `_generate_id_from_filename` runs `re.findall(r"\d+", filename)`, which returns `['2', '9096']`, then returns `f"{prefix}-{numbers[0]}"` — i.e. `BUG-2`.

Result: every priority-prefixed-but-typeless filename in `bugs/` becomes `BUG-2`, regardless of the real number in the filename.

## Expected Behavior

The parser should recognize the standard little-loops priority-prefixed filename shape `P[0-5]-NNN-...` and pair the captured number with the directory-derived prefix, yielding `BUG-9096` (or `FEAT-9096`, `ENH-9096`, etc., depending on the directory).

The fallback ID generator should also be defensive: even if a filename starts with a `P\d+-` priority token, that priority digit must not be picked up as the issue number.

## Root Cause

Two related defects in `scripts/little_loops/issue_parser.py`:

1. `_parse_type_and_id` had no recognition for the `P[0-5]-NNN-...` shape. When the type token was missing, it dropped through to a generic number-scanning fallback.
2. `_generate_id_from_filename` used the *first* digit run in the filename — `re.findall(r"\d+", filename)[0]` — which is the priority digit when a priority prefix is present.

## Affected Files

- `scripts/little_loops/issue_parser.py:526` — `_parse_type_and_id` (added priority-prefix recognition path)
- `scripts/little_loops/issue_parser.py:561` — `_generate_id_from_filename` (strip leading `P\d+-` before digit scan)
- `scripts/tests/test_issue_parser.py` — added 4 regression tests

## Reproduction Steps

1. Create `.issues/bugs/P2-9096-some-description.md` with any content.
2. Run `ll-issues list` (or call `IssueParser(...).parse_file(...)`).
3. Observe the issue is reported as `BUG-2` instead of `BUG-9096`.
4. Create additional similar files (`P2-9097-...md`, `P2-9098-...md`); all collapse to the same `BUG-2`.

## Proposed Solution

In `_parse_type_and_id`, after the explicit-type-token loop, when matching the directory-derived category, attempt a `^P\d+-(\d+)(?:[-.]|$)` match against the filename. If matched, return the directory-derived prefix paired with the captured number.

In `_generate_id_from_filename`, strip a leading `^P\d+-` priority token before running `re.findall(r"\d+", ...)`, so the priority digit can never be selected as the issue number.

Together, these provide a primary fix (recognize the standard shape) plus defense-in-depth (the catch-all helper is no longer fooled by the priority token either).

## Impact

- **Severity**: Medium (P2). Did not affect well-formed little-loops filenames (which include the type token), so most users were unaffected. Critical for external automation that omits the type token.
- **Effort**: Low (two small edits + tests).
- **Risk**: Low. The new recognition path only activates when the filename matches `^P\d+-NNN-...`; it cannot change the result for filenames that already contain `BUG-`/`FEAT-`/`ENH-`. The `_generate_id_from_filename` change only affects filenames that begin with `P\d+-`, and for those it returns the correct number rather than the priority digit.
- **Breaking Change**: No. Behavior changes only for filenames that previously produced incorrect (collision-prone) IDs.

## Labels

`bug`, `issue-parser`, `external-report`

---

## Status

**Completed** | Created: 2026-04-29 | Priority: P2 | Completed: 2026-04-29

---

## Resolution

- **Action**: fix
- **Completed**: 2026-04-29
- **Status**: Completed

### Changes Made

- `scripts/little_loops/issue_parser.py:544-556` — Extended `_parse_type_and_id` directory-fallback branch with a `^P\d+-(\d+)(?:[-.]|$)` recognizer that pairs the captured number with the directory-derived prefix.
- `scripts/little_loops/issue_parser.py:571-576` — Updated `_generate_id_from_filename` to strip a leading `P\d+-` priority token before scanning for digits.
- `scripts/tests/test_issue_parser.py` — Added regression tests:
  - `test_parse_file_priority_prefix_without_type_token` — exact blender-agents case (`P2-9096-...` → `BUG-9096`).
  - `test_parse_file_priority_prefix_features_dir` — same shape in `features/` → `FEAT-NNNN`.
  - `test_generate_id_strips_priority_prefix` — direct helper test, with and without a priority prefix.

### Verification Results

- Tests: PASS (121/121 in `test_issue_parser.py`, including the 4 new tests).
- The exact blender-agents filename `P2-9096-eval-specfile-gold-animation-bounce.md` now resolves to `BUG-9096` instead of `BUG-2`.
- Existing tests covering well-formed `P[0-5]-(BUG|FEAT|ENH)-NNN-...` filenames continue to pass — the explicit-type-token path is unchanged and runs first.
