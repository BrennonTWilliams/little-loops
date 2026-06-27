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
learning_tests_required:
- hypothesis
- pytest
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **M4 / `issue_manager` parse↔serialize is already partly covered.**
  `IssueInfo.to_dict()/from_dict()` round-trip already has a Hypothesis test at
  `scripts/tests/test_issue_parser_properties.py:93`
  (`TestIssueInfoProperties.test_roundtrip_serialization`, `max_examples=200`),
  plus `ProductImpact` variants. The remaining gap is **field coverage**: the
  `@given` strategy omits ~18 `IssueInfo` fields — `effort`, `impact`,
  `confidence_score`, `outcome_confidence`, `score_complexity`,
  `score_test_coverage`, `score_ambiguity`, `score_change_surface`, `size`,
  `testable`, `decision_needed`, `missing_artifacts`,
  `implementation_order_risk`, `milestone`, `session_commands`,
  `session_command_counts`, `labels`, `epic`. Scope step 4 as **extending the
  existing strategy** to cover these, not writing a new round-trip from scratch.
  The file-level `IssueParser.parse_file()` (`issue_parser.py:386`) is not
  property-testable directly (reads disk, needs `BRConfig`) — test the pure
  `to_dict/from_dict` pair (`issue_parser.py:287` / `:326`).
- **M4 / config round-trip is an idempotency invariant, not strict equality.**
  `BRConfig` parsing (`config/core.py:_parse_config:192`) applies defaults for
  absent keys, so `BRConfig(path_from_arbitrary_dict).to_dict()` will NOT equal
  the arbitrary input dict. The sound invariant is **dump∘load idempotency**:
  reload `to_dict()` output and assert the second `to_dict()` equals the first
  (`to_dict(load(to_dict(load(d)))) == to_dict(load(d))`). Per-section
  dataclasses expose `from_dict()` only; serialization is centralized in
  `BRConfig.to_dict()` (`config/core.py:517`) — generate inputs as config dicts
  (or via section `from_dict` shapes), not by constructing dataclasses directly.
- **M4 / FSM routing round-trip.** The testable invariant is route-table
  extract↔render↔parse: `RouteTableExtractor.extract()`
  (`fsm/route_table.py:48`) → `RouteTableRenderer.to_markdown()` →
  `RouteTableParser.parse_markdown()` should preserve the state×verdict matrix.
  For evaluator selection, the deterministic evaluators (`exit_code`,
  `output_numeric`, `output_json`, `output_contains` in `fsm/evaluators.py`)
  are pure and property-testable; avoid LLM/subprocess evaluators and
  `FSMExecutor._route()` (`fsm/executor.py:1513`, needs an interpolation
  context) in property tests.
- **Fixture consolidation needs a factory, not one fixed fixture.** The three
  duplicated sites need *different* config shapes: `test_orchestrator.py:50`
  (`temp_repo_with_config`) adds a `completed/` dir + `.worktrees/`;
  `test_cli.py:279` (`TestMainAutoIntegration.temp_project`) uses a minimal
  `{project,issues,automation}` config with `P0–P2` priorities;
  `test_issue_manager.py:179` (`setup_project`) needs an `enhancements` category
  + `completed/`. A single fixed `config_file` fixture cannot serve all three —
  the first two also bypass `temp_project_dir` entirely via raw
  `tempfile.TemporaryDirectory`. Add a **parameterized factory fixture**
  (e.g. `make_project(config_overrides=..., extra_dirs=...)`) modeled on
  `scripts/tests/helpers.py:make_test_fsm` (whose docstring notes it replaced
  builders "previously duplicated across 6 test files"), and have each site call
  it with its specifics.

## Integration Map

_Added by `/ll:refine-issue` — all work is test-only under `scripts/tests/`; the
source files under "Source Under Test" are exercised by the new property tests,
not modified._

### Files to Modify (test-only)
- `scripts/tests/test_config.py` — parametrize bundled-assertion tests (M3) and
  add config round-trip property tests (M4). Bundled-assertion targets:
  - `TestBRConfigEventsIntegration` — `test_events_socket_round_trips_through_to_dict:1820`,
    `test_events_otel_...:1838`, `test_events_webhook_...:1856` (clearest target:
    three structurally identical tests differing only by transport name).
  - `TestBRConfig.test_to_dict:756`, `test_to_dict_parallel_schema_aligned_keys:775`.
  - `TestIssuesConfig.test_from_dict_with_all_fields:136` (10 checks),
    `test_from_dict_with_defaults:185` (13 checks).
  - `TestCommandsConfig.test_from_dict_with_defaults:516`.
  - `TestCliColorsConfig.test_defaults:2055`,
    `TestCliColorsEdgeLabelsConfig.test_defaults:2100`.
- `scripts/tests/test_orchestrator.py:50` — `temp_repo_with_config` hand-rolls
  `tempfile.TemporaryDirectory` + config + issues/worktree dirs; migrate to the
  shared factory.
- `scripts/tests/test_cli.py:279` — `TestMainAutoIntegration.temp_project` (and
  the sibling `TestMainParallelIntegration` fixture) hand-roll the same
  scaffolding; migrate.
- `scripts/tests/test_issue_manager.py:179` — `TestAutoManagerIntegration.setup_project`
  uses conftest `temp_project_dir` but hand-rolls its own `.ll/ll-config.json`;
  migrate.
- `scripts/tests/conftest.py` — add the parameterized project-setup factory
  (extend, don't replace, the existing fixtures).
- `scripts/tests/test_issue_parser_properties.py:93` — extend the existing
  round-trip strategy to the ~18 omitted `IssueInfo` fields (M4).
- New property tests for config round-trip and FSM routing — either new files
  (`test_config_properties.py`, `test_fsm_route_properties.py`) or appended to
  `test_config.py` / `test_fsm_schema_fuzz.py`.

### Source Under Test (targets — do NOT modify)
- Config: `scripts/little_loops/config/core.py` — `BRConfig` (`class:153`),
  load `__init__:169 → _load_config:179 → _parse_config:192`, serialize
  `to_dict:517`.
- FSM routing: `scripts/little_loops/fsm/route_table.py` —
  `RouteTableExtractor.extract:48`, `RouteTableRenderer`, `RouteTableParser`;
  deterministic evaluators in `scripts/little_loops/fsm/evaluators.py`.
- issue_manager: `scripts/little_loops/issue_parser.py` — `IssueInfo` (`244-276`),
  `to_dict:287`, `from_dict:326`.

### Existing Patterns to Follow
- **Parametrize (M3):** `scripts/tests/test_cli.py` `TestAutoArgumentParsing` /
  `TestParallelArgumentParsing` (47–198, flag-tuple parametrization);
  `scripts/tests/test_wiring_init_and_configure.py:20-181` (module-level typed
  data table + bare `@pytest.mark.parametrize`);
  `scripts/tests/test_package_data_manifest.py:31` (`ids=` computed from the
  parameter set).
- **Hypothesis (M4):** `scripts/tests/test_issue_parser_properties.py:93`
  (canonical round-trip); `scripts/tests/test_fsm_schema_fuzz.py` `@st.composite`
  builders (`malformed_*_config`); `@given` + `@settings(max_examples=...,
  deadline=None, suppress_health_check=list(HealthCheck))`, `@pytest.mark.slow`
  on heavy fuzz tests. Strategy vocab in use: `st.text`, `st.sampled_from`,
  `st.from_regex(..., fullmatch=True)`, `st.one_of(st.none(), ...)`, `st.lists`,
  `st.dictionaries`, `st.booleans`, `st.integers`.
- **Builder/factory consolidation:** `scripts/tests/helpers.py` —
  `make_test_state()` / `make_test_fsm()`.

### Existing conftest Fixtures (extend, don't duplicate)
`scripts/tests/conftest.py` — `temp_project_dir:130` (creates `.ll/`, no config,
no issues), `sample_config:140` (fixed dict), `config_file:194` (writes
`sample_config` to `.ll/ll-config.json`), `issues_dir:202` (creates
`bugs/features/epics` + sample `.md`). Respect the autouse DB-isolation stack
(`_isolate_history_db_session:392`, `_isolate_history_db:406`,
`_guard_real_history_db:424`) and `stable_snapshot_env:20`.

### Pre-existing Infrastructure — No Change Needed

_Wiring pass added by `/ll:wire-issue` — negative findings that prevent redundant
or breaking work:_
- `scripts/pyproject.toml` — **do NOT touch.** The `slow` marker is already
  registered (`[tool.pytest.ini_options]` `markers =`, line 147) and `hypothesis>=6.0`
  is already a `dev` dependency (line 99). Because `--strict-markers` is on (line 139),
  the `@pytest.mark.slow` decorator on new property tests is already valid — re-adding
  the marker would be a duplicate [Agent 1 + Agent 2 finding].
- **Test discovery is glob-based.** `testpaths = ["tests"]` (pyproject line 134) plus
  the `test_*_properties.py` naming convention means new files
  (`test_config_properties.py`, `test_fsm_route_properties.py`) are collected
  automatically — no runner/config registration step [Agent 2 finding].
- **No CI workflow exists** (`.github/workflows/` is absent), so there is no
  marker-gating or test-subset config to update for the new `slow` tests [Agent 1 finding].
- `scripts/tests/helpers.py` pattern source (`make_test_fsm`/`make_test_state`)
  is *not* modified — its ~8 consumer test files (`test_ll_loop_*.py`,
  `test_review_loop.py`, `test_snapshot_loop_layout.py`, …) are unaffected [Agent 1 finding].

### Blast Radius — Factory Fixture Is Non-Breaking

_Wiring pass added by `/ll:wire-issue`:_
- **22 test files** inject the conftest fixtures `temp_project_dir` / `config_file` /
  `issues_dir` (beyond the 3 migration targets): `test_issue_parser.py`,
  `test_issue_discovery.py`, `test_decisions.py`, `test_cli_decisions.py`,
  `test_learning_state.py`, `test_learning_tests.py`, `test_next_action.py`,
  `test_next_issue.py`, `test_next_issues.py`, `test_issues_cli.py`,
  `test_issues_path.py`, `test_issues_search.py`, `test_ll_issues_sections.py`,
  `test_ll_issues_fingerprint.py`, `test_set_status_cli.py`, `test_set_scores_cli.py`,
  `test_refine_status.py`, `test_json_output_contracts.py`,
  `integration/test_issue_lifecycle_e2e.py`, `integration/test_init_e2e.py`, et al.
  Because the issue mandates **extend, don't replace** the existing fixtures (and the
  new factory is *additive*), none of these need edits — but the migration must keep
  the existing fixture signatures intact or they break [Agent 1 + Agent 3 finding].
- **No test imports `conftest` directly** — every fixture is consumed via pytest
  injection (`grep "from conftest"/"import conftest"` → 0 hits). Adding `make_project`
  to `conftest.py` therefore cannot create an import cycle or name collision [Agent 3 finding].
- Note: `config_file` / `issues_dir` (the conftest fixtures) are consumed narrowly —
  mostly within the ENH-2329 targets plus `test_config.py`. Several other files
  (`test_orchestrator.py`, `test_hooks_integration.py`) define *local* same-named
  variables, not the fixtures — don't conflate them when migrating [Agent 3 finding].
- The conformance suite has its **own** `scripts/tests/conformance/conftest.py`
  (independent `isolated_env` fixture + `--conformance-host` option) — the root-conftest
  factory does not reach it [Agent 1 finding].

### Tests / Verification
```bash
python -m pytest scripts/tests/test_config.py scripts/tests/test_cli.py \
  scripts/tests/test_orchestrator.py scripts/tests/test_issue_manager.py \
  scripts/tests/test_issue_parser_properties.py -v
```
Gate slow fuzz tests with `-m slow`.

_Wiring pass added by `/ll:wire-issue`:_ after the factory migration, run the full
suite (`python -m pytest scripts/tests/`) — the 22 fixture-consumer files above are
the regression surface that proves the `conftest.py` change is additive, not breaking.

### Documentation
- `docs/development/TESTING.md` — note the new property-test surfaces and the
  shared project-setup factory.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` § **Running Property-Based Tests** — the "Run
  specific property test file" example names only `test_issue_parser_properties.py`;
  add `test_config_properties.py` and `test_fsm_route_properties.py` as named
  examples [Agent 2 finding].
- `docs/development/TESTING.md` § **Test Suite Organization** → "Test File Naming
  Conventions" table — `test_<module>_properties.py` row shows only the issue-parser
  example; add the two new property files [Agent 2 finding].
- `docs/development/TESTING.md` § **Quick Reference** → "Key Fixtures" table — add a
  row for the new `make_project` factory fixture (alongside `temp_project_dir`,
  `sample_config`, `fixtures_dir`, …). The "Test Markers" table already lists
  `@pytest.mark.slow`, so no marker-doc change is needed [Agent 2 finding].
- No change needed: `docs/reference/API.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md`,
  `commands/*.md`, `skills/*/SKILL.md`, `config-schema.json` — none reference the
  test fixtures, hypothesis strategies, or parametrize patterns being changed; the
  `CLAUDE.md` test command is glob-based and auto-discovers the new files [Agent 2 finding].

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included:_

7. Update `docs/development/TESTING.md` at the three specific anchors — "Running
   Property-Based Tests" example, the "Test File Naming Conventions" table, and the
   "Key Fixtures" table (add the `make_project` row). Do **not** add a `slow`-marker
   doc note (already present).
8. Do **not** edit `scripts/pyproject.toml` — the `slow` marker (line 147) and
   `hypothesis>=6.0` (line 99) are already in place; the new property files are
   auto-discovered via `testpaths`/glob.
9. Run the **full** suite (`python -m pytest scripts/tests/`), not just the
   five-file subset, to prove the additive `conftest.py` factory does not regress the
   22 existing fixture-consumer files.

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
- `/ll:verify-issues` - 2026-06-27T19:13:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:wire-issue` - 2026-06-26T23:07:53 - `9c00279d-038d-48ea-b8a2-3f7902367e8a.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:59:23 - `613d5df7-a8ed-405a-928c-ec037815b530.jsonl`
- `/ll:format-issue` - 2026-06-26T22:49:17 - `c946e127-c3f4-47cf-9f6e-d8296756e75a.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:35:39Z - test-suite audit remediation Phase 3

---

## Status

- **Status**: open
- **Priority**: P4
