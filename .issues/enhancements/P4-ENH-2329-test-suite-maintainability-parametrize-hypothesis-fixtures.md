---
id: ENH-2329
title: 'Test-suite maintainability: parametrize duplicated bodies, extend hypothesis,
  consolidate setup fixtures'
type: ENH
status: open
priority: P4
captured_at: '2026-06-26T22:35:39Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
labels:
- testing
- maintainability
---

# ENH-2329: Test-suite maintainability — parametrize, property-test, consolidate

## Summary

Phase 3 (Maintainability) of the test-suite quality remediation
(`thoughts/audits/2026-06-26-test-suite-audit.md`). Reduce duplication and widen
property-based testing: convert copy-pasted test bodies to
`@pytest.mark.parametrize`, extend `hypothesis` to currently-untested fuzzable
surfaces, and consolidate repeated project-setup scaffolding into shared
`conftest.py` fixtures.

Phase 1 (depth) is complete; Phase 2 (breadth) is tracked in ENH-2328. This issue
is independent of both and can be done in parallel.

## Motivation

Low parametrization (0.7% of tests) means duplicated bodies and weak failure
messages — a bundled assertion that "passes if any subset is right" hides which
case actually broke. Property testing is proven on 4 parsers but absent from
equally fuzzable surfaces. Duplicated `.ll/ll-config.json` + issues-dir
scaffolding across test files drifts over time. All three are maintainability
debt, not correctness gaps — hence P4.

## Current Behavior

- **M3 — Under-applied parametrization (0.7%).** Duplicated test bodies and weak
  failure messages, e.g. config-category checks bundled into one test in
  `test_config.py` that passes if any subset is right. (`test_cli.py`
  flag-parsing is a good counter-example of parametrization done well.)
- **M4 — Property testing is narrow.** `hypothesis` is proven on 4 parsers
  (`test_issue_parser_fuzz.py`, `test_issue_parser_properties.py`,
  `test_fsm_schema_fuzz.py`, `test_goals_parser_fuzz.py`) but absent from: config
  (de)serialization round-trips, FSM routing/evaluator selection, and
  `issue_manager` parse↔serialize.
- **Duplicated setup.** The repeated `.ll/ll-config.json` + issues-dir
  scaffolding recurs across `test_orchestrator.py`, `test_cli.py`,
  `test_issue_manager.py` rather than reusing the existing `conftest.py`
  fixtures (`temp_project_dir`, `config_file`, `issues_dir`).

## Expected Behavior

- Copy-pasted config/flag/category test bodies are parametrized, giving one
  failing case per parameter with a clear per-case message.
- `hypothesis` round-trip/invariant tests exist for config (de)serialization, FSM
  routing-table validity, and `issue_manager` parse↔serialize.
- Common project-setup scaffolding is centralized in `conftest.py` fixtures and
  reused, building on the existing `temp_project_dir` / `config_file` /
  `issues_dir` fixtures.

## Proposed Solution

1. **Parametrize duplicated bodies (M3).** Start with `test_config.py` category
   checks and the flag-parsing tests, converting bundled assertions to
   `@pytest.mark.parametrize` so each case fails independently with its own id.
2. **Extend property-based testing (M4).** Using the existing fuzz/property
   pattern, add `hypothesis` tests for:
   - config (de)serialization round-trips (`BRConfig` load↔dump invariants),
   - FSM routing-table validity (generated state maps validate / route
     deterministically),
   - `issue_manager` parse↔serialize (parse(serialize(x)) == x for valid issues).
3. **Consolidate setup.** Factor the repeated config + issues-dir scaffolding in
   `test_orchestrator.py`, `test_cli.py`, `test_issue_manager.py` into shared
   `conftest.py` fixtures (extend, don't duplicate, the existing ones).

## Scope Boundaries

- Test-only refactor; behavior under test must not change (same assertions, fewer
  bodies). A parametrization that changes what is asserted is out of scope —
  preserve coverage exactly.
- Property tests target invariants only; no flaky time/network-dependent
  generators. Respect the existing snapshot-stability and DB-isolation fixtures.
- Out of scope: CI/coverage gates; Phase 2 breadth work (ENH-2328); replacing
  correct `MagicMock(spec=...)` usages (spec is fine — only faking the unit under
  test is the L2 concern, tracked separately if pursued).

## Implementation Steps

1. Parametrize `test_config.py` category checks; then the duplicated flag tests.
2. Add `hypothesis` config round-trip property tests.
3. Add `hypothesis` FSM routing-table validity property tests.
4. Add `hypothesis` `issue_manager` parse↔serialize property tests.
5. Extract shared project-setup fixtures into `conftest.py`; migrate
   `test_orchestrator.py` / `test_cli.py` / `test_issue_manager.py` to use them.
6. Verify the full affected set is green and parametrized ids read clearly.

## Impact

- **Priority**: P4 — Maintainability debt; reduces duplication and sharpens
  failure messages, but closes no correctness gap on its own.
- **Effort**: Medium — mechanical parametrization + a handful of property tests +
  a fixture-consolidation pass.
- **Risk**: Low — test-only; coverage preserved by construction.
- **Breaking Change**: No

## Labels

- testing, maintainability

## Session Log
- `/ll:capture-issue` - 2026-06-26T22:35:39Z - test-suite audit remediation Phase 3

---

## Status

- **Status**: open
- **Priority**: P4
