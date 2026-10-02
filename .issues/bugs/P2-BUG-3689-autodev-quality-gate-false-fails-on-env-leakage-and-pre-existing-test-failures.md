---
id: BUG-3689
type: BUG
title: Autodev quality gate false-fails on env leakage and pre-existing test failures
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T21:02:05Z'
reconcile_attempted: true
verify_verdict: NON_VALID
learning_tests_required:
- pytest
- pytest-json-report
---

# BUG-3689: Autodev quality gate false-fails on env leakage and pre-existing test failures

## Summary

The autodev quality gate (`code-run-gate` oracle, `run_test` state in `scripts/little_loops/loops/oracles/code-run-gate.yaml`) marked BUG-3688 `quality_failed` on 13 test failures, none caused by the issue's change (implementation commit `7ff23705a` was correct; lint, typecheck and the brainstorm tests passed). Three gaps combine to produce this false negative: ambient env leaks into the test subprocess, the test suite is not hermetic against a wide `COLUMNS`, and the gate has no baseline comparison.

## Steps to Reproduce

1. Export the ambient env an FSM shell action provides plus a wide terminal: `export LL_PYTHON=$(command -v python) COLUMNS=150`.
2. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_ll_loop_display.py scripts/tests/test_snapshot_loop_layout.py scripts/tests/test_show.py scripts/tests/test_cli.py scripts/tests/test_issues_cli.py`.
3. Observe the 11 env-sensitive tests fail; unset both vars and they pass.
4. For the baseline gap: on a branch whose only change is unrelated to the failing tests, run `ll-loop run autodev <ID>`. Observe `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (red on the base SHA) mark the issue `quality_failed`.

## Current Behavior

Run `.loops/runs/autodev-20261001T141319/` (`ll-loop run autodev BUG-3688`): `quality/BUG-3688/test-results.txt` shows `13 failed, 27560 passed`, verdict `GATE_FAILED`, issue recorded `quality_failed` and the autodev summary says a rerun will not re-gate. The 13 failures split:

1. **Env leakage (11 tests; all pass on a bare terminal run):**
   - `LL_PYTHON` is exported to every FSM shell action (`fsm/runners.py:333`, `runner_spec.py:335`). `test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` uses `${LL_PYTHON:-python3}` in its shell under test, so with `LL_PYTHON` set it bypasses its PATH-stubbed python and fails (BUG-3370 pattern; `worktree_utils.py:744` already pops `LL_PYTHON` for the verify gate, `code-run-gate` does not).
   - `host_runner.py` (`_BASELINE_NAMES`) passes `COLUMNS` / `LINES` through to children. Ten terminal-width tests fail with a wide `COLUMNS` (reproduced with `COLUMNS=150`): `test_ll_loop_display.py` (`TestPrintExecutionPlan::test_long_action_truncated`, `TestAdaptiveLayoutTopologies::test_terminal_width_no_overflow`, `::test_fanout_merged_label_truncated_with_ellipsis`), `test_snapshot_loop_layout.py::TestFSMDiagramSnapshot` (4 tests), `test_show.py::TestRenderCard::test_long_unbreakable_word_truncated_not_extended`, `test_cli.py::TestSprintShowDependencyVisualization::test_render_execution_plan_title_truncation`, `test_issues_cli.py::TestIssuesCLIShow::test_show_with_long_summary`. `conftest.py` has no `COLUMNS` / `LINES` scrub.
2. **Pre-existing failures on base (2 tests):** `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` fail identically at base `077d946ce` in a clean worktree, so they alone would have failed BUG-3688.

The gate fails on any red test; it never compares against the base SHA.

## Expected Behavior

- `run_test` runs the suite with `LL_PYTHON`, `COLUMNS` and `LINES` removed from the environment.
- The test suite pins terminal size itself, so a bare `pytest` run or any gate is immune to an exported `COLUMNS`.
- The gate fails an issue only on failures **new relative to the base SHA**; pre-existing red on base is reported but does not mark the issue `quality_failed`.

## Motivation

A false `quality_failed` verdict blocks an otherwise-correct implementation and, per the autodev summary, is not re-gated on rerun, so it needs manual `--context quality_gate=false` intervention. Because the gate fails on any red test, one pre-existing failure on `main` fails every issue gated against it, and a contributor's wide terminal or a loop-exported `LL_PYTHON` produces red that no change caused. Hermetic tests and a baseline-aware gate remove those spurious failures (13 on BUG-3688, 0 caused by its change).

## Proposed Solution

1. **Scrub env in the gate**: run `test_cmd` as `env -u LL_PYTHON -u COLUMNS -u LINES bash -c "$TEST_CMD"` in `run_test`.
2. **Hermetic terminal size in tests**: add an autouse fixture in `scripts/tests/conftest.py` that sets `COLUMNS=80` and `LINES=24` via `monkeypatch.setenv`, beside `_restore_cmd_run_env_vars` (which scrubs `_CMD_RUN_ENV_VARS`, including the leaked `LL_AUTOMATION`).
3. **Baseline-aware gate**: record the failing test ids of the run, compare against a run at the recorded base SHA (or a cached baseline keyed by base SHA), and report `GATE_FAILED` only for ids not failing on base. Keep the existing `--context quality_gate=false` escape hatch and its hint.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` (env scrub; failing-id capture) and `aggregate` (baseline comparison, verdict)
- `scripts/tests/conftest.py` — new autouse terminal-size fixture beside `_restore_cmd_run_env_vars`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — `run_quality_gate` (`with:` block, `min_pass_rate: 1.0`) must pass the base SHA / base file path to the oracle (new optional parameter); `record_quality_evidence` (`stage("test-results.txt", "test_cmd")`) derives `"test": "fail"` from the last `exit_code=` line, so a baseline-tolerated pass would otherwise record `"test": "fail"` beside `"verdict": "GATE_PASS"` — extend it to honor the baseline result [Agent 2 finding]
- `scripts/little_loops/autodev_summary.py` — `format_report` user-facing strings ("marked done but gate failed … rerun will not re-gate", "Hint: every gated issue failed the quality gate — if the base branch is already red, re-run with --context quality_gate=false") describe the exact pre-existing-red failure mode this fixes; reword if the hint's premise changes (regenerate goldens via `scripts/tests/fixtures/autodev_summary/_generate.py`) [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml` — `context:` header comment (~lines 56-62, "e.g. a repo whose base branch is already red … `--context quality_gate=false`") [Agent 2 finding]
- `scripts/pyproject.toml` — `pytest-json-report` is NOT a declared dev dependency and neither `.ll/ll-config.json` `test_cmd` (`python -m pytest scripts/tests/`) nor `[tool.pytest.ini_options] addopts` emits `--json-report`, so `run_test`'s existing `[ -f pytest.json ]` branch never fires for this repo. Either add the dep with a justification comment (CLAUDE.md "minimize third-party dependencies") plus `--json-report` wiring, or use the stdlib `--junit-xml` route (see `prepatch_check._parse_junit`) [Agent 1/2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — invokes the gate; records `<ID>.base` before `implement_current` (`QDIR/$ID.base`) and reads it back at gating, the base SHA the baseline run would use
- `scripts/little_loops/host_runner.py` — `_BASELINE_NAMES` passes `COLUMNS`/`LINES` through to children (no change expected; the gate scrubs instead)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — `run_code_gate` (`loop: oracles/code-run-gate`, no base SHA available); `record_gate_failure` rewrites `subloop_outcome_<ID>.txt` to `GATE_FAILED`. Shares one un-ID'd `run_dir`, so any new baseline artifact must be named per ID [Agent 1/2 finding]
- `scripts/little_loops/loops/rn-refine.yaml` — `verify_leaf` delegates to the oracle with a per-leaf `gate-<NID>` run_dir and no base SHA; needs the no-baseline fallback [Agent 1 finding]
- `scripts/little_loops/loops/rn-implement.yaml` — `route_rem_gate_failed` / `record_failure` consume `GATE_FAILED` / `GATE_FAILED_CODE_QUALITY` tokens (indirect via `rn-remediate`; contract unchanged) [Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — greps the autodev ledger for `quality_gate_(failed|infra)` and forwards `quality_gate` context; unaffected unless ledger reasons change [Agent 1 finding]
- `scripts/little_loops/prepatch_check.py` — `_run_pytest` / `_parse_junit` (returns `{nodeid: (category, error_kind)}`) is the existing junit nodeid parser and base-ref pytest runner; reuse candidate for `failing_test_ids` instead of a new parser [Agent 1/3 finding]
- `scripts/little_loops/history_reader/runs.py` — `read_base_sha` (advisory, `None` when unstamped) is an alternative base-SHA source; `record_quality_evidence` already calls it [Agent 2 finding]
- `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge` scrubs `LL_PYTHON` but not `COLUMNS`/`LINES`; same env leak (consistency, optional) [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py` — comment-only references to the oracle; no change [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/worktree_utils.py:744` — `env.pop("LL_PYTHON", None)` for the verify gate (BUG-3370 pattern)

### Tests
- `scripts/tests/test_feat3573_quality_gate.py`, `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — structural/behavioral tests of the oracle; extend for env scrub and baseline verdicts
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` (LL_PYTHON-sensitive)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestPrePatchCheckReachability.CODE_RUN_GATE_STATES` + `test_code_run_gate_state_set_unchanged` freeze the exact oracle state set; adding a baseline state breaks them (re-read ENH-2997 first), and `test_gate_gains_exactly_one_prepatch_check_key` pins `guarded == {"run_test": "fail"}`. Prefer folding the baseline into `run_test`/`aggregate` over a new state; loop `max_steps: 10` is also nearly exhausted [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestCodeRunGateOracle`: `test_run_states_chain_forward_and_terminate_at_aggregate` (pinned chain), `test_run_test_sidecar_declares_exit_code` (literal `echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"`), `test_run_test_stdout_not_double_prefixed` (literal `grep '^pass_rate=' …`), `_run_test_and_aggregate` + `test_aggregate_detects_pytest_json_pass_rate_below_threshold` (hand-made `pytest.json` has only `summary`, no per-test `tests` array) — keep those literals; add a failing-id extraction case [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` (exact-set equality on `# ll-lint: mr11-ok(...)` markers for `oracles/code-run-gate.yaml`) and `TestInterpSweepBaseline.test_completeness_guard` (`scripts/tests/data/loop_interpolation_baseline.json`): any new bare `${context.*}` ref (e.g. a base-sha parameter) needs `:default=`/`:shell` binding or a marker + allowlist row; new `python3 -c`/heredoc bodies interpolating `context.*` add an unbaselined site. `TestNoContextParameterKeyDuplication` forbids declaring a key in both `context:` and `parameters:` [Agent 2/3 finding]
- `scripts/tests/test_feat3573_quality_gate.py` — `TestOracleFormatStage.test_state_timeout_and_budget`: sum of state timeouts (1770) must stay `< ORACLE["timeout"]` (1800); a baseline run needs the loop `timeout:` raised. `TestOracleAggregate` (`test_pass`, `test_killed_stage_without_exit_code_fails`) must still pass with no baseline files present; add baseline cases here (all-failing-on-base → `GATE_PASS`, one new id → `GATE_FAILED`, missing/truncated baseline, base-run infra failure). `TestOracleWorktreePythonPath._run_test_state` is the template for an env-scrub test (set `LL_PYTHON`/`COLUMNS`/`LINES` in `env=`, assert the `test_cmd` subprocess doesn't see them; `PYTHONPATH` must survive). `TestRecordQualityEvidence` asserts `rec["test"] == "fail"` for `exit_code=1` — pins the stage derivation [Agent 2/3 finding]
- `scripts/tests/test_autodev_summary.py` + `scripts/tests/fixtures/autodev_summary/*` (`quality_all_gated_failed_hint/expected_stdout.txt`) and `test_feat3573_quality_gate.py` lines asserting `"rerun will not re-gate"` / `"quality_gate=false"` — update only if `autodev_summary.format_report` strings change [Agent 2 finding]
- `scripts/tests/test_worktree_utils.py` — BUG-3370 `test_ll_python_scrubbed_from_child_env` (probe `sys.exit(1 if 'LL_PYTHON' in os.environ else 0)`) is the pattern to copy for the oracle scrub test [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py` — `TestAmbientAutomationEnvHermeticity::test_suite_passes_with_ambient_ll_automation` is the template for a subprocess guard test ("width tests pass with `COLUMNS=150` and `LL_PYTHON` set"; use `-n 0` and a sentinel env var to avoid recursion) [Agent 3 finding]
- `scripts/tests/test_prepatch_check.py` — `TestJunitParsing` (`_write_junit`) is the pattern for testing `failing_test_ids` / `new_failures`; new tests for those helpers go in a new module [Agent 3 finding]
- `scripts/tests/test_cli_output.py` — `TestTerminalWidth` patches `shutil.get_terminal_size`, so a global `COLUMNS=80` doesn't break it; `scripts/tests/test_cli_loop_layout.py`, `test_cli_loop_lifecycle.py`, `test_state_feed_renderer.py` (consumers of `cli/loop/feed.py:terminal_size()`, which reads `LINES`) were not checked for reliance on the real row count — verify after adding the fixture [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` (`TestRunCodeGate`), `test_rn_refine.py` (`test_verify_leaf_delegates_to_code_run_gate`), `test_rn_implement.py` (`TestRouteRemGateFailed`), `test_ll_logs.py` (`_validate_builtin_loop("code-run-gate")` must stay valid) — regression checks only [Agent 1/3 finding]
- `scripts/tests/autodev_harness.py` sets `quality_gate=false`, so no characterization test exercises the oracle; the baseline path is covered only by the oracle-level tests above [Agent 3 finding]

### Documentation
- `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` — `code-run-gate` verdict semantics (new baseline-aware behavior)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — autodev "Post-implementation quality gate (FEAT-3573)" paragraph (~line 1090) says "Set `--context quality_gate=false` when the base branch is already red, since every issue … would otherwise fail on the same pre-existing failures", "a rerun skips it as already_done, so it is not re-gated", and "The gate runs the full suite once more per implemented issue" — all three are affected (the first becomes obsolete, the third gains a baseline run); also the `rn-remediate` row (~239) and `on_failure (GATE_FAILED)` comment (~533) [Agent 2 finding]
- `docs/reference/loops.md` — `## oracles/code-run-gate`: intro verdict paragraph, `### Parameters` table (new baseline parameter), `### Internal state machine` diagram, and the MR-3 bullet enumerating artifact filenames (add the failing-id / baseline sidecars) [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — token table rows for `GATE_FAILED` ("non-skip failure (build / test / typecheck / lint / format-check / health)") ~lines 252-254 [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — `oracles/code-run-gate` row (~line 195) [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~line 692, MR-11 exemption note only), `docs/reference/CONFIGURATION.md` (`test_cmd` row ~302-303; no toggle exists), `docs/reference/API.md` (`--quality-gate` rows ~12329-12338) — no change expected unless a toggle or summary keys are added [Agent 2 finding]
- `CHANGELOG.md` — do NOT add under `[Unreleased]`; promote during release prep [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` `parameters:` — new optional parameter for the base SHA / baseline-failing-ids path (must be optional: `rn-remediate`/`rn-refine`/direct `ll-loop run oracles/code-run-gate` callers have no base and must fall back to today's binary behavior). Not a `config-schema.json` key — `quality_gate` is a loop `context:` key, not a config key [Agent 2 finding]
- `scripts/little_loops/config-schema.json` / `scripts/tests/test_config_schema.py` — no change; only a `health_url` description mentions the oracle [Agent 2 finding]
- `scripts/tests/data/loop_interpolation_baseline.json` — update only if the oracle gains unbaselined `${context.*}`/`${captured.*}` sites in embedded Python bodies [Agent 2 finding]

## Implementation Steps

1. Edit `run_test` in `code-run-gate.yaml` (item 1); extend the loop's existing structural test if one pins the action text.
2. Add the `conftest.py` fixture (item 2); verify the 10 width tests pass under `COLUMNS=150 pytest`.
3. Design and implement the baseline comparison (item 3): decide where the base run executes (worktree at `base_sha`) and how failing ids are extracted (junit XML the gate already uploads in CI is one source); add tests with a stubbed base-failure set.
4. Re-run `ll-loop run autodev BUG-3688`-style gate from a wide terminal and confirm only genuinely new failures fail the gate.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide the failing-id source first: `pytest-json-report` is undeclared and not emitted by `test_cmd`/`addopts`, so either declare it (dev extra + justification comment + `--json-report` wiring) or emit `--junit-xml` and reuse `prepatch_check._parse_junit`; under `addopts` `-n logical --dist loadfile` the controller writes the XML, and the baseline run needs the same worker cap as `verify_epic_branch_before_merge`
- Keep `aggregate` fully backward compatible when no baseline input is passed (`TestOracleAggregate` fixtures, `rn-remediate`/`rn-refine` callers); define fallback for missing/empty/unresolvable `<ID>.base` (autodev's `route_quality_gate` already treats a missing base as infra)
- Reconcile new-ids-only with `min_pass_rate` (`run_test` `evaluate.target` and `aggregate` `PASS_RATE` check) so a pre-existing-red pass is not rejected by the pass-rate threshold
- Fold the baseline into existing `run_test`/`aggregate` states if possible (state-set freeze in `CODE_RUN_GATE_STATES`, `max_steps: 10`); if a state is added, update `CODE_RUN_GATE_STATES` and raise the loop `timeout:` above the 1770s state-timeout sum
- Update `autodev.yaml` `run_quality_gate` `with:` to pass the base SHA/file, and `record_quality_evidence` so `"test"` stage reflects baseline-tolerated failures instead of the raw last `exit_code=`
- Name any baseline sidecar per ID (rn-remediate shares a single un-ID'd `run_dir`) and list it in the `docs/reference/loops.md` MR-3 artifact bullet
- Add a hermeticity guard: a subprocess test running the 10 width tests with `COLUMNS=150` and `LL_PYTHON` set, plus a unit test asserting the new conftest fixture sets `COLUMNS=80`/`LINES=24`; then verify tests importing `cli/loop/feed.py:terminal_size()` don't depend on the real row count
- Update `docs/guides/LOOPS_REFERENCE.md` (autodev quality-gate paragraph), `docs/reference/loops.md`, `docs/guides/RECURSIVE_LOOPS_GUIDE.md`, `scripts/little_loops/loops/README.md`, the `autodev.yaml` `context:` comment, and `autodev_summary.format_report` hint strings (regenerate `fixtures/autodev_summary` goldens if changed)

## Impact

- **Priority**: P2 - every autodev run that gates against a red base or a wide terminal gets a false `quality_failed`
- **Effort**: Medium - items 1-2 are small; the baseline comparison (item 3) needs a base-SHA run and failing-id extraction
- **Risk**: Medium - baseline logic could mask a real regression if failing-id matching is too loose
- **Breaking Change**: No

## Program Design

### Types

- `base_failing_ids: set[str]` — pytest node ids failing at the recorded base SHA
- `new_failing_ids: set[str]` — ids failing in the gated run minus `base_failing_ids`

### Signatures

- `failing_test_ids(pytest_json_path: str) -> set[str]` — node ids with outcome `failed`/`error` from pytest-json-report
- `new_failures(current: set[str], base: set[str]) -> set[str]` — ids red now but not on base

### Call Path

`autodev` quality gate -> `code-run-gate` `run_test` (scrubbed env, writes `pytest.json`) -> `aggregate` (`new_failures`) -> `GATE_FAILED` only when non-empty

## Root Cause

- **File**: `scripts/little_loops/loops/oracles/code-run-gate.yaml`
- **Anchor**: `run_test` state (runs the project `test_cmd` via `bash -c`) and the `aggregate` verdict logic
- **Cause**: `run_test` inherits the runner's ambient env unscrubbed, and aggregation treats `test` result as binary pass/fail with no baseline. `scripts/tests/conftest.py` scrubs leaked env via `_CMD_RUN_ENV_VARS` / `_restore_cmd_run_env_vars` but nothing for terminal size.

## Acceptance Criteria

- With `LL_PYTHON` and a wide `COLUMNS` exported, the code-run-gate `run_test` state reports no failures from the 11 env-sensitive tests listed above.
- `COLUMNS=150 python -m pytest scripts/tests/` has no terminal-width failures.
- A gate run where all failing test ids also fail on the base SHA yields a passing verdict (with the pre-existing failures listed), and a run with at least one new failing id yields `GATE_FAILED`.

## Out of Scope

Fixing the two pre-existing corpus failures themselves (FEAT-3582 / EPIC-3687 prose-dependency drift; the ENH-3684 unverifiable quote) — track separately.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-10-01T21:31:21 - `6aa5587a-18d6-457b-930d-4a16b529f58a.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T21:29:38 - `b2628e12-0ee9-430f-aae0-6c0fc3dc7bf2.jsonl`
- `/ll:verify-issues` - 2026-10-01T21:28:29 - `a5679a98-af15-46a9-af52-92fc245da95a.jsonl`
- `/ll:reconcile-issue` - 2026-10-01T21:26:32 - `a3e28191-5ebe-4216-a1f4-a1c1385490ab.jsonl`
- `/ll:verify-issues` - 2026-10-01T21:25:46 - `44c84aaa-df89-416c-b02c-7317107a5150.jsonl`
- `/ll:wire-issue` - 2026-10-01T21:22:51 - `f86b49b5-4077-4c02-a97a-dc276b6588cc.jsonl`
- `/ll:refine-issue` - 2026-10-01T21:14:19 - `1d21e852-a25d-445f-aa12-6d1f47709472.jsonl`
- `/ll:format-issue` - 2026-10-01T21:13:42 - `0cf2c9fd-b82b-411d-99fa-51ff90db0e06.jsonl`
- `/ll:capture-issue` - 2026-10-01T21:02:10 - `bb30f6cf-829a-4e1c-90a3-72171102a54b.jsonl`
