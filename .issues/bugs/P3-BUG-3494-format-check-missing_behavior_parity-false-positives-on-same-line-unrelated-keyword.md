---
id: BUG-3494
type: BUG
title: format-check missing_behavior_parity false-positives on same-line unrelated
  keyword
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T23:50:57Z'
---

# BUG-3494: format-check missing_behavior_parity false-positives on same-line unrelated keyword

## Summary

`format-check`'s `missing_behavior_parity` gap class (`issue_parser.py`) flags a file reference as an unacknowledged replacement whenever a replacement-class keyword (`delete`/`remove`/`replace`/`rewrite`/`supersede`/`delegate`, or an inflection) appears anywhere on the same line as the ref — with no requirement that the keyword actually describes what happens to that ref. A line that both explicitly says a file is untouched and separately uses one of those verbs about something else in the sentence still fires.

## Current Behavior

`_BEHAVIOR_PARITY_KEYWORD_RE` (`scripts/little_loops/issue_parser.py:1990-2000`) is applied with `re.search` against the *entire line* containing the file ref (`scripts/little_loops/issue_parser.py:1135-1141`):

```python
replacement_line = next(
    (
        ln
        for ln in scope_lines
        if ref in ln and _BEHAVIOR_PARITY_KEYWORD_RE.search(ln)
    ),
    None,
)
```

There is no requirement that the matched keyword sit near the ref, refer to the ref, or share a clause with it — only that both appear somewhere in the same line. Confirmed live false positive in `.issues/bugs/P2-BUG-3489-*.md`'s "Proposed Solution" section (in scope per `_BEHAVIOR_PARITY_SCOPE_H2_SECTIONS`):

> "...fabricates evidence of the same class this issue **removes**. ... `lib/rubric-router.yaml`'s separate aggregate-only parser is **untouched**."

`removes` describes an unrelated fabricated default being removed elsewhere in the sentence; the same line explicitly calls `lib/rubric-router.yaml` "untouched." Because `removes` matches the keyword regex and shares the line with the ref, `check_format_gaps` still emits `missing_behavior_parity: lib/rubric-router.yaml`, even though the sentence's own claim about that file is the opposite of a replacement.

Downstream, `/ll:confidence-check`'s Criterion 4 cap (ENH-3047, `rubric.md` "Parity/Claim/Structure Cap") treats any non-empty `missing_behavior_parity` as a hard cap to 10/20 regardless of how well-specified the issue otherwise is, with no way to distinguish this false positive from a genuine unacknowledged replacement.

## Expected Behavior

The keyword match should require some relationship between the keyword and the specific file reference on that line — e.g. the keyword must appear in the same clause/sentence fragment as the ref (split on `.`/`;`/em dash), or within a bounded token window of the ref — not merely co-occur anywhere in a long line. A line where the ref is the *subject* of "is untouched"/"remains unchanged"/similar should not trigger regardless of other keywords appearing elsewhere in the same line.

## Motivation

This gate feeds a hard scoring cap in `/ll:confidence-check` (Criterion 4) that is surfaced as advisory but still distorts the readiness signal for well-specified issues, and will keep false-positiving on any issue whose prose uses a replacement-class verb about one thing while explicitly preserving an unrelated file in the same sentence — a common pattern in issues that scope out adjacent files.

## Steps to Reproduce

1. Author an issue whose `## Proposed Solution` (or `## Summary`) contains a line with two clauses: one clause uses a replacement-class keyword (`delete`/`remove`/`replace`/`rewrite`/`supersede`/`delegate`) about one thing, and a separate clause on the same physical line names an unrelated file ref and says it is untouched/unchanged — e.g. `.issues/bugs/P2-BUG-3489-*.md`'s Proposed Solution: "...fabricates evidence of the same class this issue removes. ... `lib/rubric-router.yaml`'s separate aggregate-only parser is untouched."
2. Run `ll-issues format-check P2-BUG-3489-...` (or call `check_format_gaps` directly) against that issue.
3. Observe: the gap report includes `missing_behavior_parity: lib/rubric-router.yaml`, even though that file's own clause explicitly says it is untouched — the keyword match fired only because it shares a physical line with the ref, not because it describes what happens to that ref.

## Proposed Solution

Narrow `missing_behavior_parity`'s keyword match in `issue_parser.py` from whole-line to same-clause:

1. Add `_behavior_parity_ref_clause(ref: str, line: str) -> str`, splitting `line` on `.`/`;`/em-dash (`—`) and returning the clause that contains `ref` (falling back to the full line if no boundary isolates one).
2. In the `missing_behavior_parity` loop (`check_format_gaps`, `issue_parser.py:1135-1142`), replace `_BEHAVIOR_PARITY_KEYWORD_RE.search(ln)` with `_BEHAVIOR_PARITY_KEYWORD_RE.search(_behavior_parity_ref_clause(ref, ln))` so the keyword must share the ref's own clause, not merely the ref's line.
3. Add `_BEHAVIOR_PARITY_PRESERVATION_RE` (whole-word: `untouched|unchanged|kept|stays|remains|outside this change`) as a secondary guard: if it matches the same clause a keyword hit was found in, suppress the flag — covers phrasing where a clause boundary doesn't fully isolate the keyword from a preservation phrase.

## Program Design

### Types

- No new types — reuses `RefStatus` (`text_utils.py`) and plain `str`.

### Signatures

- `_behavior_parity_ref_clause(ref: str, line: str) -> str` (new, `issue_parser.py`) — returns the clause of `line` containing `ref`, split on `.`/`;`/`—`.
- `_BEHAVIOR_PARITY_PRESERVATION_RE: re.Pattern[str]` (new, `issue_parser.py`, module-level, alongside `_BEHAVIOR_PARITY_KEYWORD_RE` at `issue_parser.py:1990`).

### Call Path

`check_format_gaps` (`issue_parser.py:1119`, `missing_behavior_parity` loop at `issue_parser.py:1135-1146`) -> `_behavior_parity_ref_clause` -> `_BEHAVIOR_PARITY_KEYWORD_RE.search` / `_BEHAVIOR_PARITY_PRESERVATION_RE.search` -> `classify_file_ref` (`text_utils.py:354`)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add `_behavior_parity_ref_clause`, `_BEHAVIOR_PARITY_PRESERVATION_RE`, and rewire the `missing_behavior_parity` loop (lines ~1135-1146, 1990-2000)

### Dependent Files (Callers/Importers)
- None outside `issue_parser.py` — `_BEHAVIOR_PARITY_KEYWORD_RE` and the loop it lives in are private module internals of `check_format_gaps`; no other module imports them (confirmed via `grep -rn _BEHAVIOR_PARITY_KEYWORD_RE scripts/`)

### Similar Patterns
- No existing clause-splitting helper elsewhere in `issue_parser.py` to model after; this is the first clause-scoped (vs. line-scoped) keyword match in the module

### Tests
- `scripts/tests/test_issue_parser.py` — existing `missing_behavior_parity` coverage; add the same-line-different-clause regression fixture from Steps to Reproduce
- `scripts/tests/test_ll_issues_format_check.py` — existing `format-check` CLI-level behavior-parity coverage

### Documentation
- N/A — internal gap-detection heuristic, not part of a documented public contract

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- **Convention for scope-decision comments**: existing gap-class regex constants pair with a comment stating the exact proximity rule chosen (and what was rejected), citing the deciding doc section — e.g. `_BEHAVIOR_PARITY_KEYWORD_RE`'s comment currently reads "matched as whole words, same line as the ref only (Program Design § Decision Rules condition 3; no multi-line proximity window in v1)" (`scripts/little_loops/issue_parser.py:1988-1989`). Narrowing the match to clause-scope must update this comment to state the new scope — leaving it describing whole-line scope after the code changes would contradict the code (compare `_SOFT_DEP_PHRASE_RE`'s comment at `issue_parser.py:1958-1960`, which states its own paragraph-scope rule the same way).
- **Docstring must stay in sync with the gap rule**: `check_format_gaps`'s docstring documents each gap class's exact detection rule in prose; its `missing_behavior_parity` entry states the ref "shares a line with a replacement keyword ... same line only, no multi-line proximity window" (`scripts/little_loops/issue_parser.py:766-777`). This prose must be updated alongside the code change or the docstring will describe stale (whole-line) behavior.
- **Test coverage correction**: the actual `missing_behavior_parity` gap-firing tests live in `scripts/tests/test_ll_issues_format_check.py`'s `TestMissingBehaviorParity` class (`test_ll_issues_format_check.py:1038-1200`), asserted at the CLI level (`ll-issues format-check`), one test method per scenario (e.g. `test_fires_on_resolved_ref_with_replacement_keyword_same_line`, `test_no_gap_without_replacement_keyword`). `scripts/tests/test_issue_parser.py`'s only behavior-parity coverage is `TestBehaviorParityHeadingDetection` (`test_issue_parser.py:6715`), which tests `_heading_bodies()` directly and does not exercise the `missing_behavior_parity` gap-firing path at all — the Tests subsection above overstates test_issue_parser.py's coverage of this gap class.
- **No existing clause/sentence-splitting utility**: a repo-wide search of `scripts/little_loops/` for splitting logic found none — `_behavior_parity_scope_text`, `_paragraph_spans`, and `_symbol_claim_scope_text` all operate on sections/paragraphs, not clauses. A new clause-splitting helper would be the first of its kind in this module.
- **No existing precedent for a two-regex keyword+suppression combo**: searched `issue_parser.py` for an existing "primary keyword regex, secondary negation regex used as a suppression guard" shape — none found. Existing suppression mechanisms in this file are frontmatter escape hatches (`behavior_parity_not_applicable`, `program_design_not_applicable`) or absence-of-heading checks (`_heading_bodies`), not a second regex.

## Implementation Steps

1. Add a regression fixture reproducing the exact BUG-3489 line shape (keyword and ref in the same line but different clauses, ref's own clause saying "untouched"/"unchanged").
2. Narrow the same-line match to a same-clause or bounded-window match around the ref in `issue_parser.py`'s behavior-parity detection.
3. Add a negative-signal check: if the ref's own clause contains a preservation phrase ("untouched", "unchanged", "kept", "stays", "remains", "outside this change") ahead of/near the keyword's clause, do not flag it — or rely solely on the narrowed proximity fix if that alone resolves the case.
4. Re-run `scripts/tests/test_issue_parser*.py` and any `format_check` fixtures covering `missing_behavior_parity`.

## Impact

- **Priority**: P3 - advisory-only false positive (distorts a confidence-score cap but doesn't block anything outright)
- **Effort**: Small - one new helper function, one new regex, and a one-line change to the existing loop in a single file
- **Risk**: Low - narrows an existing gap class; worst case is a rare genuine replacement going undetected if it shares a line but not a clause with its ref
- **Breaking Change**: No

## Root Cause

`_behavior_parity_scope_text` / the keyword-match loop in `check_format_gaps` (`scripts/little_loops/issue_parser.py:1129-1146`) scopes the keyword search to "same line as the ref" (per the ENH-3045 comment at `issue_parser.py:1987-1989`) but never scopes it further to the same clause or a bounded window around the ref. Any keyword hit anywhere on a long line satisfies the check.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-17T00:38:51 - `8d361261-7d23-4528-9cc0-b68e6d88c4d7.jsonl`
- `/ll:format-issue` - 2026-09-17T00:08:07 - `0106b7a1-30c9-493e-b7a3-8ae734b157ea.jsonl`
- `/ll:capture-issue` - 2026-09-16T23:51:04 - `c2d33705-5252-4e88-a51b-055eef4c4dc3.jsonl`
