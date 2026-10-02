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
relates_to:
- ENH-3692
parent: EPIC-3694
epic: EPIC-3694
---

# BUG-3689: Autodev quality gate false-fails on env leakage and pre-existing test failures

## Summary

The autodev quality gate (`code-run-gate` oracle, `run_test` state in `scripts/little_loops/loops/oracles/code-run-gate.yaml`) marked BUG-3688 `quality_failed` on 13 test failures, none caused by the issue's change (implementation commit `7ff23705a` was correct; lint, typecheck and the brainstorm tests passed). Two gaps in this issue produce 11 of the 13 failures: ambient env (`LL_PYTHON`, a wide `COLUMNS`) leaks into the test subprocess, and the test suite is not hermetic against it. The other 2 failures were already red on the base SHA; the gate has no baseline comparison, which is split out to **ENH-3692** (with an explicit go/no-go) and is out of scope here.

## Steps to Reproduce

1. Export the ambient env an FSM shell action provides plus a wide terminal: `export LL_PYTHON=$(command -v python) COLUMNS=150`.
2. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_ll_loop_display.py scripts/tests/test_snapshot_loop_layout.py scripts/tests/test_show.py scripts/tests/test_cli.py scripts/tests/test_issues_cli.py`.
3. Observe the 11 env-sensitive tests fail; unset both vars and they pass.
4. (Baseline gap — tracked in ENH-3692, not fixed here.) On a branch whose only change is unrelated, `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (red on the base SHA) still mark the issue `quality_failed`.

## Current Behavior

Run `.loops/runs/autodev-20261001T141319/` (`ll-loop run autodev BUG-3688`): `quality/BUG-3688/test-results.txt` shows `13 failed, 27560 passed`, verdict `GATE_FAILED`, issue recorded `quality_failed` and the autodev summary says a rerun will not re-gate. The 13 failures split:

1. **Env leakage (11 tests; all pass on a bare terminal run):**
   - `LL_PYTHON` is exported to every FSM shell action (`scripts/little_loops/fsm/runners.py:333`, `scripts/little_loops/runner_spec.py:335`). `test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` uses `${LL_PYTHON:-python3}` in its shell under test, so with `LL_PYTHON` set it bypasses its PATH-stubbed python and fails (BUG-3370 pattern; `worktree_utils.py:744` already pops `LL_PYTHON` for the verify gate, `code-run-gate` does not).
   - `host_runner.py` (`_BASELINE_NAMES`) passes `COLUMNS` / `LINES` through to children. Ten terminal-width tests fail with a wide `COLUMNS` (reproduced with `COLUMNS=150`): `test_ll_loop_display.py` (`TestPrintExecutionPlan::test_long_action_truncated`, `TestAdaptiveLayoutTopologies::test_terminal_width_no_overflow`, `::test_fanout_merged_label_truncated_with_ellipsis`), `test_snapshot_loop_layout.py::TestFSMDiagramSnapshot` (4 tests), `test_show.py::TestRenderCard::test_long_unbreakable_word_truncated_not_extended`, `test_cli.py::TestSprintShowDependencyVisualization::test_render_execution_plan_title_truncation`, `test_issues_cli.py::TestIssuesCLIShow::test_show_with_long_summary`. `conftest.py` has no `COLUMNS` / `LINES` scrub.
2. **Pre-existing failures on base (2 tests; out of scope — ENH-3692):** `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` fail identically at base `077d946ce` in a clean worktree, so they alone would have failed BUG-3688.

The gate fails on any red test; it never compares against the base SHA (ENH-3692).

## Expected Behavior

- `run_test` runs the suite with `LL_PYTHON`, `COLUMNS` and `LINES` removed from the environment.
- The test suite is hermetic against both: `LL_PYTHON` is scrubbed per test and terminal size is pinned, so a bare `pytest` run — including from a wide interactive terminal — or any gate is immune.
- Failing the gate only on failures new relative to the base SHA is **ENH-3692**, not this issue.

## Motivation

A false `quality_failed` verdict blocks an otherwise-correct implementation and, per the autodev summary, is not re-gated on rerun, so it needs manual `--context quality_gate=false` intervention. Because the gate fails on any red test, one pre-existing failure on `main` fails every issue gated against it, and a contributor's wide terminal or a loop-exported `LL_PYTHON` produces red that no change caused. Hermetic tests and a scrubbed gate env remove the 11 env-driven spurious failures on BUG-3688 (0 caused by its change); the 2 pre-existing failures are ENH-3692.

## Proposed Solution

1. **Scrub env in the gate** (consuming projects' only protection): in `run_test`, `unset LL_PYTHON COLUMNS LINES` (or `env -u …`) before `bash -c "$TEST_CMD"`, keeping the `PYTHONPATH` export intact. This also makes terminal width deterministic like CI, since stdout is a file. Mirrors `worktree_utils.py:744` (BUG-3370); where practical share the scrub list as one constant.
2. **Hermetic tests — the root fix for this repo** in `scripts/tests/conftest.py`:
   - add `"LL_PYTHON"` to `_CMD_RUN_ENV_VARS` (line ~1192; scrubbed per test by `_restore_cmd_run_env_vars`). Tests that need it `monkeypatch.setenv` in-body, which wins.
   - add an autouse fixture `pin_terminal_size` that `monkeypatch.setenv`s `COLUMNS=80` and `LINES=24` beside `_restore_cmd_run_env_vars`. Use `setenv`, **not** `delenv`: with the vars unset `shutil.get_terminal_size` falls back to the real tty, so a wide interactive terminal would still break the width tests on a bare `pytest` run. `80x24` equals the non-tty fallback CI sees.
3. **Hermeticity guard test**: a subprocess test running the width tests plus `test_recheck_set_folds_back_abandoned_residual` with `COLUMNS=150` and `LL_PYTHON` set, and a unit test asserting the fixture pins `COLUMNS=80`/`LINES=24`.

Baseline-aware gating (previously item 3) is **ENH-3692**.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` env scrub only; keep the literals pinned by tests (`echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"`, `grep '^pass_rate=' …`) and the `PYTHONPATH` export
- `scripts/tests/conftest.py` — `LL_PYTHON` in `_CMD_RUN_ENV_VARS`; new autouse terminal-size fixture beside `_restore_cmd_run_env_vars`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py:333` and `scripts/little_loops/runner_spec.py:335` — set `LL_PYTHON` for FSM shell actions (no change; the gate scrubs instead)
- `scripts/little_loops/host_runner.py` — `_BASELINE_NAMES` passes `COLUMNS`/`LINES` through to children (no change)
- `scripts/little_loops/loops/rn-remediate.yaml`, `rn-refine.yaml`, `autodev.yaml` — callers of the oracle; the scrub benefits all, contract unchanged
- `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge` scrubs `LL_PYTHON` but not `COLUMNS`/`LINES`; same leak (consistency, optional)

### Similar Patterns
- `scripts/little_loops/worktree_utils.py:744` — `env.pop("LL_PYTHON", None)` (BUG-3370)

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` (LL_PYTHON-sensitive); `TestCodeRunGateOracle` pins the `run_test` literals (`test_run_test_sidecar_declares_exit_code`, `test_run_test_stdout_not_double_prefixed`) — keep them; `MR11_MARKER_ALLOWLIST` and `TestInterpSweepBaseline.test_completeness_guard` — the scrub adds no `${context.*}` refs, so they should be untouched
- `scripts/tests/test_feat3573_quality_gate.py` — `TestOracleWorktreePythonPath._run_test_state` is the template for an env-scrub test (set `LL_PYTHON`/`COLUMNS`/`LINES` in `env=`, assert the `test_cmd` subprocess doesn't see them; `PYTHONPATH` must survive); `TestOracleAggregate` / `TestRecordQualityEvidence` unchanged
- `scripts/tests/test_worktree_utils.py` — `test_ll_python_scrubbed_from_child_env` (probe `sys.exit(1 if 'LL_PYTHON' in os.environ else 0)`) is the pattern to copy
- `scripts/tests/test_hook_session_start.py` — `TestAmbientAutomationEnvHermeticity::test_suite_passes_with_ambient_ll_automation` is the template for the subprocess guard (use `-n 0` and a sentinel env var to avoid recursion)
- `scripts/tests/test_cli_output.py` — `TestTerminalWidth` patches `shutil.get_terminal_size`, so a global `COLUMNS=80` doesn't break it. `scripts/tests/test_cli_loop_layout.py`, `test_cli_loop_lifecycle.py`, `test_state_feed_renderer.py` consume `cli/output.py:terminal_size()` (reads `LINES`) and were not checked for reliance on the real row count — verify after adding the fixture

### Documentation
- `docs/reference/loops.md` — `## oracles/code-run-gate`: one line noting `run_test` runs with `LL_PYTHON`/`COLUMNS`/`LINES` unset (optional)
- `CHANGELOG.md` — do NOT add under `[Unreleased]`; promote during release prep

## Implementation Steps

1. Add `"LL_PYTHON"` to `_CMD_RUN_ENV_VARS` and the `COLUMNS=80`/`LINES=24` autouse fixture in `conftest.py`; verify the 10 width tests and `test_recheck_set_folds_back_abandoned_residual` pass under `COLUMNS=150 LL_PYTHON=$(command -v python) pytest`.
2. Edit `run_test` in `code-run-gate.yaml` to unset `LL_PYTHON`/`COLUMNS`/`LINES` before `bash -c "$TEST_CMD"`; add the env-scrub test modeled on `TestOracleWorktreePythonPath`.
3. Add the subprocess hermeticity guard test; then check `test_cli_loop_layout.py`, `test_cli_loop_lifecycle.py`, `test_state_feed_renderer.py` don't depend on the real row count.
4. Re-run the gate from a wide terminal and confirm only the 2 pre-existing (ENH-3692) failures remain.

## Impact

- **Priority**: P2 - every autodev run from a wide terminal or with an FSM-exported `LL_PYTHON` gets a false `quality_failed`
- **Effort**: Small - a gate env scrub, one conftest tuple entry and one autouse fixture, plus guard tests
- **Risk**: Low - test-env only; a global `COLUMNS=80` could surprise a test that relies on the real tty size (checked in step 3)
- **Breaking Change**: No

## Program Design

### Types

- `HERMETIC_ENV_VARS: tuple[str, ...]` — env vars removed from the `test_cmd` subprocess: `LL_PYTHON`, `COLUMNS`, `LINES`

### Signatures

- `pin_terminal_size(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]` — autouse fixture in `scripts/tests/conftest.py` that `setenv`s `COLUMNS=80` / `LINES=24` for every test
- `test_suite_passes_with_ambient_gate_env() -> None` — subprocess guard: the width tests and `test_recheck_set_folds_back_abandoned_residual` pass with `COLUMNS=150` and `LL_PYTHON` set

### Call Path

`autodev` quality gate -> `code-run-gate` `run_test` (unsets `LL_PYTHON`/`COLUMNS`/`LINES`, then `bash -c "$TEST_CMD"`) -> pytest -> `pin_terminal_size` and `_restore_cmd_run_env_vars` (which now includes `LL_PYTHON`) keep each test hermetic

## Root Cause

- **File**: `scripts/little_loops/loops/oracles/code-run-gate.yaml`, `scripts/tests/conftest.py`
- **Anchor**: `run_test` state (runs the project `test_cmd` via `bash -c`); `_CMD_RUN_ENV_VARS` / `_restore_cmd_run_env_vars`
- **Cause**: `run_test` inherits the runner's ambient env unscrubbed (`LL_PYTHON` from `fsm/runners.py:333`, `COLUMNS`/`LINES` via `host_runner._BASELINE_NAMES`), and `conftest.py` scrubs leaked env via `_CMD_RUN_ENV_VARS` but not `LL_PYTHON` and nothing for terminal size.

## Acceptance Criteria

- With `LL_PYTHON` and a wide `COLUMNS` exported, the code-run-gate `run_test` state reports no failures from the 11 env-sensitive tests listed above.
- `COLUMNS=150 LL_PYTHON=$(command -v python) python -m pytest scripts/tests/` has no terminal-width or `LL_PYTHON` failures, from a bare run as well as via the gate.
- The `test_cmd` subprocess in `run_test` does not see `LL_PYTHON`, `COLUMNS` or `LINES`, and `PYTHONPATH` survives (env-scrub test).
- A subprocess guard test and a fixture unit test pin the hermeticity.

## Out of Scope

- Baseline-aware gating (fail only on failures new relative to the base SHA) — **ENH-3692**.
- Fixing the two pre-existing corpus failures themselves (FEAT-3582 / EPIC-3687 prose-dependency drift; the ENH-3684 unverifiable quote) — track separately. Until `main` is green, this repo's autodev runs still fail the gate on those two (use `--context quality_gate=false`).

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
