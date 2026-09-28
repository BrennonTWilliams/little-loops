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
---

# ENH-3639: Pin unapplied_decision corpus test to a frozen fixture corpus instead of live .issues/

## Summary

`TestBug3295ContainmentCorpusDifferential` in `scripts/tests/test_issue_parser.py` runs `_unapplied_decision` over every `.md` file in the live `.issues/` tree and asserts the total report count stays at or below a pinned ceiling (`_ENH_3602_TOTAL_REPORTS`). Because its input is developer-edited data, ordinary issue refinement trips it and turns main red, with a failure message that blames the detector. Replace the live-tree ratchet with an exact per-file pin against a frozen fixture corpus, so the test fails only when detector behaviour changes.

## Current Behavior

- `test_total_report_count_does_not_exceed_post_bug_3448_baseline` sums `_unapplied_decision(...)` reports over `.issues/**/*.md` and asserts `total <= _ENH_3602_TOTAL_REPORTS`. On failure it reports the total "exceeds post-ENH-3449 baseline ... -- detector regressed".
- Refining or deciding an issue adds backticked identifiers to directive sections, which can add a report. The test then fails with the detector code unchanged.
- The ceiling's own comment history records it moving upward eight times (535 -> 562 -> 569 -> 573 -> 574 -> 578 -> 585 -> 594 -> 595), each explained as "not a detector regression", then down once to 410 (PR #37, a real detector fix). Closed PR #36 was another of these one-line bumps.
- The ceiling is set exactly to the measured count (410), so there is zero headroom: the next issue edit that adds one report turns main red again.
- Each upward bump widens the gap a real regression could hide in, which defeats the test's purpose.
- `test_previously_spurious_files_now_clear` shares the dependency: it asserts named files in `_PINNED_CLEARED` exist in the live corpus and report nothing, so renaming, deleting, or editing one of those issues breaks it.

## Expected Behavior

- The corpus-regression test reads a frozen, checked-in set of issue files, not the working tree.
- It pins the exact report count (or the exact report strings) per fixture file. Any change, up or down, fails the test and requires an intentional re-pin, so detector fixes are visible as well as regressions.
- Editing, adding, or deleting files under `.issues/` never fails this test.
- Stale decisions in real issues stay a per-issue concern for `ll-issues format-check` (the `unapplied_decision` gap class), not a suite-wide count.

## Motivation

The guard mixes two concerns, detector correctness (code) and corpus hygiene (data), so it fires on the wrong one. The result is repeated red-main events, test-only bump PRs, and a ceiling that drifts upward until it no longer catches regressions.

## Proposed Solution

1. Build a fixture corpus under `scripts/tests/fixtures/issues/` (that directory already holds `_unapplied_decision` golden fixtures such as `BUG-3413-fixture-multi-decision-point.md`). Seed it with the historically tricky shapes: the `_PINNED_CLEARED` files, the largest sites from the PR #37 A/B (P2-FEAT-3308, P3-BUG-3380, P3-FEAT-2576, P3-ENH-3346), P2-ENH-2657 (the detection PR #37 surfaced), and a sample of zero-report files as negative controls.
2. Replace the total-count ceiling with a dict of `{fixture_name: expected_report_count}` (or expected report lists), asserted exactly.
3. Point `test_previously_spurious_files_now_clear` at the fixture copies.
4. Optionally keep a live-corpus scan as a non-failing report (for example, a `ll-issues format-check` summary), never as a pass/fail ceiling.

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_parser.py` — `TestBug3295ContainmentCorpusDifferential` (`_PINNED_CLEARED`, `_ENH_3602_TOTAL_REPORTS`, both test methods)
- `scripts/tests/fixtures/issues/` — new frozen fixture files

### Dependent Files (Callers/Importers)
- N/A — test-only change; `little_loops.issue_parser._unapplied_decision` is exercised, not modified

### Similar Patterns
- `scripts/tests/test_decide_issue_skill.py` `TestPhase7cFixtures` — already runs `_unapplied_decision_pairs()` against golden fixtures in `scripts/tests/fixtures/issues/`

### Tests
- `scripts/tests/test_issue_parser.py` (the change itself)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Copy the selected issue files into the fixtures directory, frozen at their current content.
2. Measure per-file report counts with the current detector and pin them.
3. Rewrite both tests in `TestBug3295ContainmentCorpusDifferential` to read the fixtures; remove `_ENH_3602_TOTAL_REPORTS` and its bump-history comment (the history lives in git).
4. Confirm the tests stay green after an unrelated edit to a live `.issues/` file, and go red when the PR #37 boundary fix in `_option_block_spans` is reverted.

## Program Design

### Types

- `EXPECTED_REPORT_COUNTS: dict[str, int]` — replaces `_ENH_3602_TOTAL_REPORTS`; maps each frozen fixture filename to its exact pinned `_unapplied_decision` report count

### Signatures

- `_unapplied_decision(content: str) -> list[str]` — existing detector, unchanged; called once per frozen fixture file instead of once per live `.issues/**/*.md` file
- `test_total_report_count_does_not_exceed_post_bug_3448_baseline(self) -> None` — rewritten to iterate `EXPECTED_REPORT_COUNTS` and assert `len(_unapplied_decision(fixture_text)) == expected` per fixture, replacing the summed ceiling
- `test_previously_spurious_files_now_clear(self) -> None` — rewritten to read `_PINNED_CLEARED` files from the fixtures directory instead of the live `.issues/` tree

### Call Path

`pytest` -> `TestBug3295ContainmentCorpusDifferential.test_total_report_count_does_not_exceed_post_bug_3448_baseline` -> `_unapplied_decision` -> per-fixture exact-count assertion against `EXPECTED_REPORT_COUNTS`

## Impact

- **Priority**: P3 - recurring red-main and bump-PR churn, but no user-facing defect
- **Effort**: Small - one test class plus fixture files
- **Risk**: Low - test-only; the detector is untouched
- **Breaking Change**: No

## Acceptance Criteria

- No test in `scripts/tests/test_issue_parser.py` reads `.issues/` for the `_unapplied_decision` corpus check.
- Reverting the `_LABELLED_PARAGRAPH_RE` boundary in `_option_block_spans` makes the new test fail.
- Adding a new report-producing issue under `.issues/` does not fail any test.
- `python -m pytest scripts/tests/test_issue_parser.py` passes.

## Scope Boundaries

- No change to `_unapplied_decision` detector logic.
- No change to how `ll-issues format-check` reports `unapplied_decision` on real issues.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-28T19:21:18 - `ddc7b8ed-4e52-4365-b63d-32d433349fbb.jsonl`
- `/ll:capture-issue` - 2026-09-28T19:18:10 - `71f8d034-e0e5-4531-a9b5-d0d92b80145c.jsonl`
