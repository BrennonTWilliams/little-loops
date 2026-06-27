---
id: ENH-2328
title: 'Test-suite breadth: dedicated tests for incidental-only modules + executor
  coverage spot-check'
type: ENH
status: open
priority: P3
captured_at: '2026-06-26T22:35:39Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
labels:
- testing
- coverage
relates_to:
- ENH-2325
depends_on:
- ENH-2329
---

# ENH-2328: Test-suite breadth — dedicated tests for incidental-only modules

## Summary

Phase 2 (Breadth) of the test-suite quality remediation
(`thoughts/audits/2026-06-26-test-suite-audit.md`). Several non-trivial source
modules have only incidental coverage (exercised indirectly, never pinned by a
dedicated test of intent). Add dedicated `test_<module>.py` files for them, then
a coverage-guided spot-check of the genuinely uncovered branches in
`fsm/executor.py`.

Phase 1 (depth: vacuous-pass guard + integration layer + no-assert hardening) is
already complete (`scripts/tests/integration/`); this issue tracks Phase 2 only.
Phase 3 (maintainability) is tracked separately.

## Motivation

A module with only incidental coverage passes as long as its *callers* pass —
its own edge cases (long names, empty fields, error propagation) are never
asserted. That is exactly where regressions hide. The audit graded breadth as
otherwise excellent, so this is targeted gap-closing, not a broad rewrite.

## Current Behavior

No dedicated test module exists for these (audit findings M5 and L1):

- `cli/issues/show.py` (~509 loc) — **highest value**: summary-card formatting
  edge cases (long names, empty/missing fields) untested.
- `cli/parallel.py` (~290 loc) — worker spawn / cleanup / error propagation.
- `config/automation.py` (~283 loc) — rule-matching / false-positive logic.
- `dependency_mapper/formatting.py` (~296 loc) — graph-traversal edge cases
  (likely some indirect coverage via `test_dependency_mapper.py`'s 146 tests;
  confirm with coverage before adding).
- Smaller (L1): `worktree_utils.py` (~170 loc, highest value of this group),
  `decisions_sync.py` (~41 loc), `sft_formatter.py` (~56 loc), and the
  `analytics/` package (~295 loc, referenced incidentally in 11 test files).

`fsm/executor.py` (2,141 loc) is well covered for evaluator types and routing
(see audit §2), so the only remaining gap is specific uncovered branches inside
the file — not a systemic hole.

## Expected Behavior

- Each listed module has a dedicated `test_<module>.py` (or `test_analytics_*.py`
  for the package) asserting its own edge cases, not just smoke coverage.
- `fsm/executor.py` has tests added only for the branches a coverage report shows
  as genuinely uncovered (error/interpolation paths), avoiding redundant tests
  where coverage is already strong.

## Proposed Solution

1. **`cli/issues/show.py` (start here).** Add `test_show.py` covering card
   formatting: long titles, empty/missing frontmatter fields, absent optional
   sections, and ID resolution via `_resolve_issue_id`. Model on the existing
   integration-style fixtures (`temp_project_dir`, `config_file`, `issues_dir`).
2. **`cli/parallel.py`.** Add `test_parallel_cli.py` for worker spawn/cleanup and
   error propagation (mock only the host-CLI/subprocess boundary, real config).
3. **`config/automation.py`.** Add `test_config_automation.py` for rule-matching
   and false-positive logic, parametrized over rule cases.
4. **L1 modules.** Add `test_worktree_utils.py` (highest value), then
   `test_decisions_sync.py`, `test_sft_formatter.py`, and a focused
   `test_analytics_*.py` covering the capture paths.
5. **Coverage-guided executor spot-check.** Run
   `pytest --cov=little_loops.fsm.executor --cov-report=term-missing`, take the
   reported missing lines, and add tests only for the genuinely uncovered
   error/interpolation branches.

## Scope Boundaries

- New test modules only; no source changes unless a test surfaces a real bug
  (file that separately).
- `dependency_mapper/formatting.py`: confirm the coverage gap before adding — it
  may already be covered indirectly by `test_dependency_mapper.py`.
- The executor work is a *spot-check* of uncovered branches, not a rewrite of the
  already-strong evaluator/routing coverage.
- Out of scope: standing up CI / coverage gates (explicitly excluded from the
  remediation); Phase 3 maintainability work (tracked separately).

## Implementation Steps

1. Add `test_show.py` for `cli/issues/show.py` formatting edge cases.
2. Add `test_parallel_cli.py` for `cli/parallel.py` worker lifecycle.
3. Add `test_config_automation.py` for `config/automation.py` rule matching.
4. Confirm `dependency_mapper/formatting.py` coverage; add `test_formatting.py`
   only if a real gap exists.
5. Add L1 module tests (`worktree_utils.py`, `decisions_sync.py`,
   `sft_formatter.py`, `analytics/`).
6. Run the executor coverage report; add tests for uncovered branches only.
7. Verify the affected files are green and report new coverage deltas.

## Impact

- **Priority**: P3 — Closes real dedicated-test gaps in non-trivial modules; no
  user-facing change, but reduces regression risk in CLI/config/parallel paths.
- **Effort**: Medium — several focused test modules; each is independently
  shippable.
- **Risk**: Low — additive tests; no production code changes expected.
- **Breaking Change**: No

## Labels

- testing, coverage

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): New test modules added under this issue should use ENH-2329's project-setup factory fixture (from `conftest.py`) rather than the raw `tempfile.TemporaryDirectory` + hand-rolled config patterns referenced in the "Proposed Solution." ENH-2329 consolidates those raw fixtures into a stable parameterized factory; test files written before ENH-2329 lands will immediately become refactoring targets. Implement ENH-2329 first (hence `depends_on: ENH-2329`), then write test modules once in the stable fixture pattern. Related issue: ENH-2329.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:57 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T01:23:43 - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:35:39Z - test-suite audit remediation Phase 2

---

## Status

- **Status**: open
- **Priority**: P3
