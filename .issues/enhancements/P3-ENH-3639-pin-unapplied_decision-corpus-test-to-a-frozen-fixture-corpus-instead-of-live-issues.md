---
id: ENH-3639
type: ENH
title: Pin unapplied_decision corpus test to a frozen fixture corpus instead of live
  .issues/
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T19:18:02Z'
confidence_score: 100
outcome_confidence: 95
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3639: Pin unapplied_decision corpus test to a frozen fixture corpus instead of live .issues/

## Summary

`TestBug3295ContainmentCorpusDifferential` in `scripts/tests/test_issue_parser.py` runs `_unapplied_decision` over every `.md` file in the live `.issues/` tree and asserts the total report count stays at or below a pinned ceiling (`_ENH_3602_TOTAL_REPORTS`). Because its input is developer-edited data, ordinary issue refinement trips it and turns main red, with a failure message that blames the detector. Replace the live-tree ratchet with an exact per-file pin against a frozen fixture corpus, so the test fails only when detector behaviour changes.

Two sibling classes in the same file pin exact values against named live `.issues/` files and share the same fragility: `TestBug3285CorpusDifferential` and `TestBug3293DecisionRulesCorpusDifferential`. They get the same move here.

## Current Behavior

- `test_total_report_count_does_not_exceed_post_bug_3448_baseline` sums `_unapplied_decision(...)` reports over `.issues/**/*.md` and asserts `total <= _ENH_3602_TOTAL_REPORTS`. On failure it reports the total "exceeds post-ENH-3449 baseline ... -- detector regressed".
- Refining or deciding an issue adds backticked identifiers to directive sections, which can add a report. The test then fails with the detector code unchanged.
- The ceiling's own comment history records it moving upward eight times (535 -> 562 -> 569 -> 573 -> 574 -> 578 -> 585 -> 594 -> 595), each explained as "not a detector regression", then down once to 410 (PR #37, a real detector fix). Closed PR #36 was another of these one-line bumps.
- The ceiling is set exactly to the measured count (410), so there is zero headroom: the next issue edit that adds one report turns main red again.
- Each upward bump widens the gap a real regression could hide in, which defeats the test's purpose.
- `test_previously_spurious_files_now_clear` shares the dependency: it asserts named files in `_PINNED_CLEARED` exist in the live corpus and report nothing, so renaming, deleting, or editing one of those issues breaks it.
- `TestBug3285CorpusDifferential` asserts exact `==` values (`_LOCATE_PINS`, `_UNCHANGED_LOCATE_PINS`, `_UNAPPLIED_PINS`, `_UNRESOLVED_PINS`) against 11 named live `.issues/` files. Editing any of them fails the test; deleting one silently skips it (`_read` calls `pytest.skip` on a missing path).
- `TestBug3293DecisionRulesCorpusDifferential.test_only_pinned_files_gain_program_design_options` sweeps the whole live tree and fails if any *unpinned* file resolves to `decision_rules_numbered` or a `provisional_e` "Program Design" match. Capturing a new issue with that shape turns main red, the same corpus-hygiene failure mode as the ceiling.

## Expected Behavior

- Every value-asserting corpus-differential test in `test_issue_parser.py` reads a frozen, checked-in set of issue files, not the working tree.
- `TestBug3295ContainmentCorpusDifferential` pins the exact `_unapplied_decision` report **count** per fixture file. Any change, up or down, fails the test and requires an intentional re-pin, so detector fixes are visible as well as regressions.
- Editing, adding, or deleting files under `.issues/` never fails these tests.
- Crash-only live-corpus sweeps (`TestUnappliedDecisionLiveCorpusSweep` and similar) stay as they are: they assert no exception, not a value.
- Stale decisions in real issues stay a per-issue concern for `ll-issues format-check` (the `unapplied_decision` gap class), not a suite-wide count.

## Motivation

The guard mixes two concerns, detector correctness (code) and corpus hygiene (data), so it fires on the wrong one. The result is repeated red-main events, test-only bump PRs, and a ceiling that drifts upward until it no longer catches regressions.

## Proposed Solution

1. Build three frozen fixture corpora, one subdirectory per originating class, under `scripts/tests/fixtures/issues/`. Name the files by bare ID (`FEAT-3308.md`), matching the `bug3287_corpus/` precedent. Do **not** put them flat in `fixtures/issues/`: `TestParseFrontmatterCorpus._fixture_files` (`scripts/tests/test_frontmatter.py:291`) globs `fixtures/issues/*.md` non-recursively and would pick them up.
   - `bug3295_corpus/` (8 files): BUG-1616, ENH-1717, ENH-3292 (the `_PINNED_CLEARED` set); FEAT-3308, BUG-3380, FEAT-2576, ENH-3346 (the largest sites from the PR #37 A/B); ENH-2657 (the detection PR #37 surfaced). The five zero-report members serve as negative controls, so no separate zero-report sample is needed.
   - `bug3285_corpus/` (11 files): the union of `TestBug3285CorpusDifferential`'s four pin dicts: BUG-1484, ENH-2967, ENH-1555, FEAT-1244, FEAT-2186, BUG-3177, BUG-3253, FEAT-2339, BUG-2735, ENH-2226, FEAT-1076.
   - `bug3293_corpus/` (5 files): BUG-3232, BUG-3285, BUG-3293, ENH-3045, BUG-3356.
2. `TestBug3295ContainmentCorpusDifferential`: replace the total-count ceiling with a `_PINNED: dict[str, int]` of `{fixture_id: exact_report_count}`, asserted with `==` in a test parametrized per fixture. Pin counts, not report strings: string pins would force a re-pin on any change to message wording, and the A/B below shows the regression under test moves counts sharply.
3. Point `test_previously_spurious_files_now_clear` at the `bug3295_corpus/` copies.
4. `TestBug3285CorpusDifferential`: point `_ISSUES_ROOT` (renamed `_FIXTURE_DIR`) at `bug3285_corpus/` and rekey the four dicts to bare IDs. Change `_read` from `pytest.skip` to a failing `assert path.exists()`, because a missing frozen fixture is a defect, not an absent corpus.
5. `TestBug3293DecisionRulesCorpusDifferential`: rewrite as a per-fixture pin of `(pattern, count)` over `bug3293_corpus/`. Drop the "no unpinned file gains a match" half. It is a whole-live-corpus assertion, the same shape as the ceiling. The additive-only property it guarded is structural (documented in the class docstring) and was checked by the one-time sweep at fix time.
6. The optional live-corpus non-failing scan is **already satisfied** by `TestUnappliedDecisionLiveCorpusSweep` (`scripts/tests/test_issue_parser.py:6009`). Add no new test.

**Measured A/B (2026-09-28 review, live files, `_LABELLED_PARAGRAPH_RE` boundary in place vs disabled):**

| File | Fixed | Boundary reverted |
|---|---|---|
| BUG-1616 / ENH-1717 / ENH-3292 | 0 / 0 / 0 | 0 / 0 / 0 |
| FEAT-3308 | 0 | 36 |
| BUG-3380 | 10 | 42 |
| FEAT-2576 | 0 | 31 |
| ENH-3346 | 6 | 25 |
| ENH-2657 | 1 | 0 |

Re-measure the pins from the frozen copies at implementation time (Implementation Step 2). These numbers only confirm that the seed set can meet the revert criterion.

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_parser.py` — `TestBug3295ContainmentCorpusDifferential` (`_PINNED_CLEARED`, all five `_*_TOTAL_REPORTS` constants, class docstring, both test methods); `TestBug3285CorpusDifferential` (`_ISSUES_ROOT`, four pin dicts, `_read`); `TestBug3293DecisionRulesCorpusDifferential` (`_PINNED`, `test_only_pinned_files_gain_program_design_options`)
- `scripts/tests/fixtures/issues/bug3295_corpus/`, `bug3285_corpus/`, `bug3293_corpus/` — new frozen fixture files (24 total)

### Dependent Files (Callers/Importers)
- N/A — test-only change; `little_loops.issue_parser._unapplied_decision`, `locate_enumerable_options`, and `count_unresolved_options` are exercised, not modified

### Similar Patterns
- `scripts/tests/test_bug_3287_option_patterns_widening.py` `TestCorpusDifferentialFrozenFixtures` — the closest precedent: frozen `bug3287_corpus/`, bare-ID filenames, exact `_PINNED` dict, parametrized per fixture
- `scripts/tests/test_decide_issue_skill.py` `TestPhase7cFixtures` — already runs `_unapplied_decision_pairs()` against golden fixtures in `scripts/tests/fixtures/issues/`

### Tests
- `scripts/tests/test_issue_parser.py` (the change itself)
- `scripts/tests/test_frontmatter.py` `TestParseFrontmatterCorpus` — must stay unaffected (reason for the subdirectory layout)

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- `scripts/tests/test_issue_parser.py:5783` — `TestBug3295ContainmentCorpusDifferential` class start; `_PINNED_CLEARED` frozenset at `:5797` (3 entries), `_ENH_3602_TOTAL_REPORTS = 410` at `:5869`, `test_previously_spurious_files_now_clear` at `:5871`, `test_total_report_count_does_not_exceed_post_bug_3448_baseline` at `:5886` (the `<=` ceiling assertion is at `:5910`) — these are the exact anchors the Files to Modify entry above refers to.
- An existing module, `scripts/tests/test_bug_3287_option_patterns_widening.py`, already implements the shape this issue proposes end-to-end for a sibling detector: `TestCorpusDifferentialFrozenFixtures` (`:83`) reads a frozen fixture directory (`FIXTURE_DIR` at `:33`, `fixtures/issues/bug3287_corpus/`), pins exact per-issue-ID `(before, after)` tuples in a `_PINNED` dict (`:97`), and asserts equality (not a ceiling) in `test_pinned_before_after` (`:150`). Its module docstring (`:1-25`) states the rule this issue's Motivation also states — "The live `.issues/` corpus is not a stable fixture -- it grows and edits daily, so a full corpus-wide before/after diff cannot be a permanent, pinned assertion" — and documents that a full live-corpus differential was run once as a manual landing-gate check during implementation and deliberately not committed. This is a closer precedent than `TestPhase7cFixtures` for the specific "replace a live ceiling with a frozen exact-pin dict" move.
- That same module also already carries the "optional live-corpus scan as a non-failing report" this issue's Proposed Solution point 6 asks for: `TestOptionPatternsLiveCorpusSweepDoesNotCrash` (`:173`), mirroring `TestUnappliedDecisionLiveCorpusSweep.test_corpus_sweep_does_not_crash` (`scripts/tests/test_issue_parser.py:6009`) — both assert only that the detector does not raise over the live tree, no value comparison, so ordinary issue edits cannot turn them red. `TestUnappliedDecisionLiveCorpusSweep` already exists today as a class separate from `TestBug3295ContainmentCorpusDifferential`, so Proposed Solution point 6 is already satisfied by existing code for `_unapplied_decision` specifically — no new sweep test is needed for that observable.
- Three other test methods in the same file read the live `.issues/` tree with the same exact-per-file-pin shape and share the identical developer-edit fragility this issue targets: `TestBug3285CorpusDifferential` (`:6324`) — `_UNAPPLIED_PINS` (`:6387`, 4 entries) drives `test_unapplied_decision_pins` (`:6436`, `_unapplied_decision`, exact `==` at `:6444`), `_UNRESOLVED_PINS` (`:6403`, 4 entries) drives `test_count_unresolved_options_pins` (`:6446`, `count_unresolved_options`, exact `==` at `:6453`); and `TestBug3293DecisionRulesCorpusDifferential` (`:5916`) whose `_PINNED` dict (`:5934`) drives `test_only_pinned_files_gain_program_design_options` (`:5957`) against live-tree content by filename. None of these three pinned dicts' filenames overlap with `_PINNED_CLEARED` or with the five files this issue names for seeding (P2-FEAT-3308, P3-BUG-3380, P3-FEAT-2576, P3-ENH-3346, P2-ENH-2657) — none of those five are pinned by any existing test today. _Folded into scope 2026-09-28 (review): `test_unapplied_decision_pins` is itself an `_unapplied_decision` corpus check reading `.issues/`, so Acceptance Criterion 1 could not hold with these classes left out._

## Implementation Steps

1. Copy the 24 selected issue files verbatim into `bug3295_corpus/`, `bug3285_corpus/`, and `bug3293_corpus/` under bare-ID names. Do not edit fixture content after copying.
2. Measure per-file values with the current detector from the fixture copies (not the live files), and pin them.
3. Rewrite `TestBug3295ContainmentCorpusDifferential`:
   - Remove all five ceiling constants (`_PRE_FIX_TOTAL_REPORTS`, `_POST_BUG_3413_TOTAL_REPORTS`, `_POST_BUG_3448_TOTAL_REPORTS`, `_ENH_3449_TOTAL_REPORTS`, `_ENH_3602_TOTAL_REPORTS`) and their bump-history comments. The history lives in git.
   - Rewrite the class docstring. Drop "measured as a report-count ceiling" and describe the frozen per-file pin.
   - Rename `test_total_report_count_does_not_exceed_post_bug_3448_baseline` to `test_pinned_report_counts`, parametrized over `sorted(_PINNED)`, so a failure names the fixture.
4. Rewrite `TestBug3285CorpusDifferential` and `TestBug3293DecisionRulesCorpusDifferential` as in Proposed Solution 4–5.
5. Verify:
   - (a) An unrelated edit to a live `.issues/` file (including one of the 24 source files) leaves all three classes green.
   - (b) Disabling the `_LABELLED_PARAGRAPH_RE` boundary in `_option_block_spans` makes `test_pinned_report_counts` fail.
   - (c) Reverting the BUG-3295 subsumption filter (ahead of `discriminating = rej_ids - sel_ids` in `_unapplied_decision`) makes `test_previously_spurious_files_now_clear` fail. If it stays green, the ENH-3623 boundary now clears those files on its own. In that case, record it in the class docstring and either reseed with files that only the subsumption filter clears, or drop the test as vacuous.
   - (d) BUG-3413 per-decision-point grouping was also guarded by the old ceiling. Confirm that `TestPhase7cFixtures` (`scripts/tests/test_decide_issue_skill.py`, over `BUG-3413-fixture-multi-decision-point.md`) fails when grouping is reverted. Cite it in the class docstring as the grouping guard.

## Program Design

### Types

- `_PINNED: dict[str, int]` — on `TestBug3295ContainmentCorpusDifferential`; replaces the five `_*_TOTAL_REPORTS` constants; maps each bare fixture ID to its exact pinned `_unapplied_decision` report count
- `_FIXTURE_DIR: Path` — per class; replaces the live `.issues/` root (`TestBug3285CorpusDifferential._ISSUES_ROOT`, and the inline `issues_dir` in the other two classes)

### Signatures

- `_unapplied_decision(content: str) -> list[str]` — existing detector, unchanged; called once per frozen fixture file instead of once per live `.issues/**/*.md` file
- `test_pinned_report_counts(self, fixture_id: str) -> None` — replaces `test_total_report_count_does_not_exceed_post_bug_3448_baseline`; asserts `len(_unapplied_decision(fixture_text)) == _PINNED[fixture_id]`
- `test_previously_spurious_files_now_clear(self) -> None` — rewritten to read `_PINNED_CLEARED` files from `bug3295_corpus/` instead of the live `.issues/` tree
- `test_pinned_program_design_surfaces(self, fixture_id: str) -> None` — replaces `test_only_pinned_files_gain_program_design_options`; asserts `(located.pattern, located.count) == _PINNED[fixture_id]` per fixture

### Call Path

`pytest` -> `TestBug3295ContainmentCorpusDifferential.test_pinned_report_counts` -> `_unapplied_decision` -> per-fixture exact-count assertion against `_PINNED`

## Impact

- **Priority**: P3 - recurring red-main and bump-PR churn, but no user-facing defect
- **Effort**: Small - three test classes plus 24 verbatim fixture files
- **Risk**: Low - test-only; the detectors are untouched
- **Breaking Change**: No

## Acceptance Criteria

- No value-asserting test in `scripts/tests/test_issue_parser.py` reads `.issues/`. Crash-only sweeps such as `TestUnappliedDecisionLiveCorpusSweep` are exempt.
- None of the five `_*_TOTAL_REPORTS` constants remain.
- Disabling the `_LABELLED_PARAGRAPH_RE` boundary in `_option_block_spans` makes `test_pinned_report_counts` fail.
- Adding a new report-producing issue under `.issues/`, or editing or deleting any of the 24 source issues, does not fail any test.
- `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_frontmatter.py` passes.

## Scope Boundaries

- No change to `_unapplied_decision`, `locate_enumerable_options`, or `count_unresolved_options` logic.
- No change to how `ll-issues format-check` reports `unapplied_decision` on real issues.
- Crash-only live-corpus sweeps stay as they are.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-28T20:06:36 - `17025306-364a-4143-b659-80dee88f61b2.jsonl`
- `/ll:refine-issue` - 2026-09-28T19:30:00 - `f3afff3d-0f77-4821-a4f6-45be74a7a00e.jsonl`
- `/ll:format-issue` - 2026-09-28T19:21:18 - `ddc7b8ed-4e52-4365-b63d-32d433349fbb.jsonl`
- `/ll:capture-issue` - 2026-09-28T19:18:10 - `71f8d034-e0e5-4531-a9b5-d0d92b80145c.jsonl`
