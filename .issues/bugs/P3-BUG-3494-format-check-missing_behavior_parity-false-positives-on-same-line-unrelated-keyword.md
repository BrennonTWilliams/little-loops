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

Narrow `missing_behavior_parity`'s keyword match in `issue_parser.py` from whole-line to same-clause. Clause scoping alone resolves the BUG-3489 case; no secondary preservation-phrase guard ships in this fix (see Decision Rules below).

1. Add `_behavior_parity_ref_clauses(ref: str, line: str) -> list[str]`, splitting `line` on **sentence/clause boundaries** and returning every clause that contains `ref` (falling back to `[line]` if no boundary isolates one). A boundary is a `.` or `;` followed by whitespace or end-of-line, or a spaced em-dash (` — `). **Never split on a bare `.`**: every file ref contains a dot (`rubric-router.yaml`, `session_store.py`), so a bare-dot split would yield fragments that never contain `ref`, hit the fallback for every ref, and silently restore whole-line behavior — the fix would be a no-op.
2. In the `missing_behavior_parity` loop (`check_format_gaps`, `issue_parser.py:1135-1142`), replace `_BEHAVIOR_PARITY_KEYWORD_RE.search(ln)` with `any(_BEHAVIOR_PARITY_KEYWORD_RE.search(c) for c in _behavior_parity_ref_clauses(ref, ln))` so the keyword must share one of the ref's own clauses, not merely the ref's line. The return type is a list because the same ref can appear twice on one line ("replace `x.py`; the tests for `x.py` are untouched") and the flag must fire if *any* clause containing the ref carries a keyword.
3. Keep passing the **full line** (not the clause) as `line=` to `classify_file_ref`: that argument drives the `(new)` planned-file marker, which may sit outside the ref's clause. Clause scoping applies to the keyword match only, not to ref classification.

### Decision Rules

- **No preservation-phrase suppression regex in this fix.** An earlier draft proposed `_BEHAVIOR_PARITY_PRESERVATION_RE` (`untouched|unchanged|kept|stays|remains|outside this change`) to suppress a keyword hit sharing the ref's clause. Rejected: the motivating case is fully handled by clause scoping, and the guard introduces genuine false negatives — "`foo.py` is replaced and the old module kept as a shim for one release" puts keyword and preservation word in one clause and would suppress a real replacement; `kept`/`stays`/`remains` are especially loose ("remains to be deleted"). If a real case surfaces that clause scoping does not cover, revisit as a follow-up with a narrow list (`untouched|unchanged|not modified|out of scope`) and a requirement that the ref precede the phrase in the clause.
- **Accepted false negative: verb in a different sentence from the ref.** "Remove these two files. `a.py` and `b.py` go away." escapes detection after this change because the keyword sits in a separate sentence. This is the same limitation v1 already has for intro-line-plus-bullet-list phrasing (keyword on the intro line, refs on following lines) and is consistent with the "no proximity window" design; it is not a regression to reopen.

## Program Design

### Types

- No new types — reuses `RefStatus` (`text_utils.py`) and plain `str`.

### Signatures

- `_behavior_parity_ref_clauses(ref: str, line: str) -> list[str]` (new, `issue_parser.py`) — returns every clause of `line` containing `ref`, split on `[.;]` followed by whitespace/end-of-line or on ` — `; `[line]` if no boundary isolates one.
- `_BEHAVIOR_PARITY_CLAUSE_SPLIT_RE: re.Pattern[str]` (new, `issue_parser.py`, module-level, alongside `_BEHAVIOR_PARITY_KEYWORD_RE` at `issue_parser.py:1990`) — the boundary pattern above; comment must state why a bare `.` is not a boundary.

### Call Path

`check_format_gaps` (`issue_parser.py:1119`, `missing_behavior_parity` loop at `issue_parser.py:1135-1146`) -> `_behavior_parity_ref_clauses` -> `_BEHAVIOR_PARITY_KEYWORD_RE.search` (per clause) -> `classify_file_ref` (`text_utils.py:354`, still receives the full line)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add `_behavior_parity_ref_clauses`, `_BEHAVIOR_PARITY_CLAUSE_SPLIT_RE`, and rewire the `missing_behavior_parity` loop (lines ~1135-1146, 1990-2000)

### Dependent Files (Callers/Importers)
- None outside `issue_parser.py` — `_BEHAVIOR_PARITY_KEYWORD_RE` and the loop it lives in are private module internals of `check_format_gaps`; no other module imports them (confirmed via `grep -rn _BEHAVIOR_PARITY_KEYWORD_RE scripts/`)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/confidence-check/SKILL.md:194` — Phase 1.8 extracts `missing_behavior_parity` from `$FC_JSON` into shell variable `PARITY_GAP`. Informational only, no code change needed: the JSON key and contract are unchanged, this consumer simply sees fewer entries post-fix. [Agent 1 finding]
- `skills/confidence-check/rubric.md:247,251-254` — Criterion 4 "Parity/Claim/Structure Cap": any non-empty `PARITY_GAP` caps the score at 10 regardless of the row that would otherwise apply. This is the consumer whose distorted signal motivates this bug (see Motivation) — cases that previously tripped the cap on this false positive will stop doing so once the fix lands. No code/prose change required here. [Agent 1 finding]

### Similar Patterns
- No existing clause-splitting helper elsewhere in `issue_parser.py` to model after; this is the first clause-scoped (vs. line-scoped) keyword match in the module

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py:1287` (`TestSoftDepHardEdge.test_no_gap_when_soft_language_in_different_paragraph`) — closest existing precedent for a narrowed-scope negative test: docstring names the exact scope boundary, fixture body intentionally places the phrase outside the scoped unit, asserts the gap does not fire. Model the new same-clause regression test's shape after this one (scope unit differs: paragraph via `_paragraph_spans()` there, vs. clause via `.`/`;`/em-dash split here). [Agent 3 finding]

### Tests
- `scripts/tests/test_issue_parser.py` — existing `missing_behavior_parity` coverage; add the same-line-different-clause regression fixture from Steps to Reproduce
- `scripts/tests/test_ll_issues_format_check.py` — existing `format-check` CLI-level behavior-parity coverage

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py` — add `test_no_gap_when_keyword_and_ref_in_different_clauses_same_line` to `TestMissingBehaviorParity` (after line 1200), using the `_write_bug_with_summary` helper with body `"This fabricates evidence of the same class this issue removes. \`scripts/little_loops/session_store.py\`'s separate aggregate-only parser is untouched."` (use `session_store.py`, not `lib/rubric-router.yaml`, so the ref classifies as `resolved` via the existing `_RESOLVED_GIT_LS_FILES` fixture at line 1030); assert `result == 0` and `"missing_behavior_parity" not in out`. Confirmed no existing test in this class breaks under the narrowing (both "fires" tests keep keyword+ref in one clause; all "no gap" tests short-circuit before the keyword loop). [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py` — also add to `TestMissingBehaviorParity`:
  - `test_fires_when_dotted_ref_and_keyword_share_clause` — body like `"Replace \`scripts/little_loops/session_store.py\` with a thin shim."`; asserts the gap **fires**. Guards against the bare-`.` split bug: a wrong split would drop the ref from every clause, fall back to the whole line, and this test would still pass — so pair it with a direct unit test of `_behavior_parity_ref_clauses("a/b.py", "Replace \`a/b.py\` now. Other text.")` asserting the returned clause contains the dotted ref and not `"Other text"`.
  - `test_fires_when_ref_appears_twice_and_one_clause_has_keyword` — body `"Replace \`scripts/little_loops/session_store.py\`; the tests for \`scripts/little_loops/session_store.py\` are untouched."`; asserts the gap fires (multi-occurrence cardinality).
  - `test_no_gap_when_new_marker_outside_ref_clause` — a `(new)` marker elsewhere on the line must still classify the ref as `planned_new` (full line passed to `classify_file_ref`), so no gap.

### Documentation
- N/A — internal gap-detection heuristic, not part of a documented public contract

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2470-2473` — `ll-issues format-check` reference prose states the keyword match is "same line only" — must update in lockstep with the clause-scoping code change or this doc goes stale. [Agent 2 finding]
- `docs/reference/API.md:910` — `check_format_gaps()` reference entry states "same line only, no multi-line proximity window" — same staleness risk as CLI.md above. [Agent 2 finding]

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
2. Add `_BEHAVIOR_PARITY_CLAUSE_SPLIT_RE` and `_behavior_parity_ref_clauses` in `issue_parser.py` (boundary = `[.;]` + whitespace/EOL, or ` — `; never a bare `.`), returning all clauses containing the ref.
3. Rewire the `missing_behavior_parity` loop to `any(keyword in clause for clause in ref_clauses)`; keep passing the full line to `classify_file_ref`.
4. Update the `_BEHAVIOR_PARITY_KEYWORD_RE` comment, the `check_format_gaps` docstring, `docs/reference/CLI.md`, and `docs/reference/API.md` from "same line only" to the clause-scoped rule (see Wiring Phase).
5. Add the positive dotted-ref, multi-occurrence, and `(new)`-marker tests listed under Tests, then re-run `scripts/tests/test_ll_issues_format_check.py` and `scripts/tests/test_issue_parser.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:2470-2473` — replace "same line only" with the new clause-scoped rule (mirror whatever phrasing the code comment settles on)
- Update `docs/reference/API.md:910` — replace "same line only, no multi-line proximity window" with the new clause-scoped rule
- Add `test_no_gap_when_keyword_and_ref_in_different_clauses_same_line` to `TestMissingBehaviorParity` in `scripts/tests/test_ll_issues_format_check.py`, modeled on `TestSoftDepHardEdge.test_no_gap_when_soft_language_in_different_paragraph` (line 1287) — see Tests subsection for the exact fixture body and assertion

## Impact

- **Priority**: P3 - advisory-only false positive (distorts a confidence-score cap but doesn't block anything outright)
- **Effort**: Small - one new helper function, one new regex, and a one-line change to the existing loop in a single file
- **Risk**: Low - narrows an existing gap class; the accepted false negative is a genuine replacement whose verb sits in a different sentence from its ref on the same line (see Decision Rules), which mirrors v1's existing intro-line-plus-bullet-list blind spot. The dotted-ref positive test guards the one implementation hazard (bare-`.` split silently reverting to whole-line matching)
- **Breaking Change**: No

## Root Cause

`_behavior_parity_scope_text` / the keyword-match loop in `check_format_gaps` (`scripts/little_loops/issue_parser.py:1129-1146`) scopes the keyword search to "same line as the ref" (per the ENH-3045 comment at `issue_parser.py:1987-1989`) but never scopes it further to the same clause or a bounded window around the ref. Any keyword hit anywhere on a long line satisfies the check.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-17T00:46:52 - `be8b47b1-6882-43b4-b784-fa09f67d3d72.jsonl`
- `/ll:refine-issue` - 2026-09-17T00:38:51 - `8d361261-7d23-4528-9cc0-b68e6d88c4d7.jsonl`
- `/ll:format-issue` - 2026-09-17T00:08:07 - `0106b7a1-30c9-493e-b7a3-8ae734b157ea.jsonl`
- `/ll:capture-issue` - 2026-09-16T23:51:04 - `c2d33705-5252-4e88-a51b-055eef4c4dc3.jsonl`
