---
id: BUG-3689
type: BUG
title: Autodev quality gate false-fails on inherited LL_PYTHON and terminal size
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T21:02:05Z'
reconcile_attempted: true
verify_verdict: VALID
relates_to:
- ENH-3697
parent: EPIC-3694
epic: EPIC-3694
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-3689: Autodev quality gate false-fails on inherited LL_PYTHON and terminal size

## Summary

The autodev quality gate (`code-run-gate` oracle, `run_test` state in `scripts/little_loops/loops/oracles/code-run-gate.yaml`) marked BUG-3688 `quality_failed` on 13 test failures (implementation commit `7ff23705a`; lint, typecheck and the brainstorm tests passed). Two gaps in this issue account for 11 failures: ambient env (`LL_PYTHON`, a wide `COLUMNS`) leaks into the test subprocess, and the test suite does not isolate itself from it. Pre-implementation review reproduced all 11 failures on the unchanged code with the variables set, and all 11 pass with them removed. The other 2 failures were transient corpus-ratchet failures from live `.issues/` working-tree reads, covered by **ENH-3697**; baseline-aware gating (ENH-3692) was evaluated and cancelled. Both are out of scope here.

## Steps to Reproduce

1. Export the ambient interpreter an FSM shell action provides plus terminal overrides: `export LL_PYTHON=$(command -v python) COLUMNS=150 LINES=60`.
2. Run `python -m pytest -n 0 scripts/tests/test_builtin_loops.py scripts/tests/test_ll_loop_display.py scripts/tests/test_snapshot_loop_layout.py scripts/tests/test_show.py scripts/tests/test_cli.py scripts/tests/test_issues_cli.py`. For a narrow reproduction, select only the 11 node IDs listed in Current Behavior; select the four individual snapshot methods, not their entire module.
3. Observe the 11 env-sensitive tests fail; unset all three vars and they pass. `LINES` is included for terminal-height coverage; the original 11 failures were attributable to `LL_PYTHON` and `COLUMNS`.
4. (Not fixed here — ENH-3697.) While autodev has uncommitted `.issues/` edits in flight, `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` can go red from working-tree state alone (both pass on a clean `main`, verified 2026-10-02 with `-n 0`).

## Current Behavior

Run `.loops/runs/autodev-20261001T141319/` (`ll-loop run autodev BUG-3688`): `quality/BUG-3688/test-results.txt` shows `13 failed, 27560 passed`, verdict `GATE_FAILED`, issue recorded `quality_failed` and the autodev summary says a rerun will not re-gate. The 13 failures split:

1. **Env leakage (11 tests; all pass on a bare terminal run):**
   - `LL_PYTHON` is exported to every FSM shell action (`scripts/little_loops/fsm/runners.py:333`, `scripts/little_loops/runner_spec.py:335`). `test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` uses `${LL_PYTHON:-python3}` in its shell under test, so with `LL_PYTHON` set it bypasses its PATH-stubbed python and fails (BUG-3370 pattern; `worktree_utils.py:744` already pops `LL_PYTHON` for the verify gate, `code-run-gate` does not).
   - `scripts/little_loops/host_runner.py` (`_BASELINE_NAMES`) passes the COLUMNS / LINES environment variables through to children. Ten terminal-width tests fail with a wide inherited width (reproduced with `COLUMNS=150`): `scripts/tests/test_ll_loop_display.py` (`TestPrintExecutionPlan::test_long_action_truncated`, `TestAdaptiveLayoutTopologies::test_terminal_width_no_overflow`, `TestAdaptiveLayoutTopologies::test_fanout_merged_label_truncated_with_ellipsis`), `scripts/tests/test_snapshot_loop_layout.py::TestFSMDiagramSnapshot` (`test_linear_two_state_fsm`, `test_branching_three_state_fsm`, `test_linear_fsm_with_highlight`, `test_suppress_labels_mode`), `scripts/tests/test_show.py::TestRenderCard::test_long_unbreakable_word_truncated_not_extended`, `scripts/tests/test_cli.py::TestSprintShowDependencyVisualization::test_render_execution_plan_title_truncation`, `scripts/tests/test_issues_cli.py::TestIssuesCLIShow::test_show_with_long_summary`. `scripts/tests/conftest.py` has no terminal-size isolation.
2. **Corpus-ratchet failures (2 tests; out of scope — ENH-3697):** `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` were red in the gate, but they read the live `.issues/` working tree, which autodev mutates (BUG-3688's `<ID>.base-dirty` listed ~20 uncommitted `.issues` files). They pass on a clean `main` (verified 2026-10-02, `-n 0`), so these were transient, not failures on the base SHA.

The gate fails on any red test. Baseline-aware gating (ENH-3692) was evaluated and cancelled; the corpus-test cause is ENH-3697.

## Expected Behavior

- `run_test` runs the suite with `LL_PYTHON`, `COLUMNS` and `LINES` removed from the environment.
- The test suite isolates these three variables: `LL_PYTHON` is scrubbed per test and terminal size is pinned to `80x24`, including when capture is disabled. Tests can explicitly override those defaults in their body.
- The scrub removes inherited overrides; explicit assignments inside a consuming project's `test_cmd` still take effect. `PYTHONPATH`, `PATH`, verification markers and the gate's failure policy are preserved.
- Transient corpus-ratchet failures are **ENH-3697**, not this issue (ENH-3692's baseline-aware gating was cancelled).

## Motivation

A false `quality_failed` verdict blocks an otherwise-correct implementation and, per the autodev summary, is not re-gated on rerun, so it needs manual intervention. A wide inherited `COLUMNS` or an FSM-exported `LL_PYTHON` produces red that no implementation change caused. Isolated tests and a scrubbed gate env remove the 11 demonstrated env-driven failures; the 2 corpus-ratchet failures remain ENH-3697. Keep the existing any-red failure policy.

## Proposed Solution

1. **Remove inherited overrides at the test-command boundary.** In `run_test`, insert `unset LL_PYTHON COLUMNS LINES` immediately before `bash -c "$TEST_CMD"`, keeping `RC=$?` immediately after the command. Preserve the linked-worktree `PYTHONPATH` prepend, inherited `PYTHONPATH` suffix, `PATH`, verification markers, null-command SKIP and sidecar/stdout contract. Removing terminal vars removes inherited overrides; it is not a guarantee about tools that query `/dev/tty` themselves. This boundary also protects consuming projects, which do not have this repo's conftest. Document that an explicit assignment inside `test_cmd` still wins; do not add a new configuration option or broaden the scrub to other `LL_*` variables.
2. **One bounded scrub set shared by the Python paths.** Define `HERMETIC_ENV_VARS: tuple[str, ...] = ("LL_PYTHON", "COLUMNS", "LINES")` in `scripts/little_loops/worktree_utils.py`. Replace its existing `env.pop("LL_PYTHON", None)` with a loop over this tuple. The epic-verify env is shared by `test_cmd` **and** `lint_cmd`, so both lose these inherited overrides. Preserve `LL_VERIFY_GATE`, `LL_FUZZ`, worker-budget defaults and `PYTHONPATH`. Import the tuple into `scripts/tests/conftest.py` and append it to `_CMD_RUN_ENV_VARS` using tuple expansion; do not maintain a second scrub list. A structural test asserts the YAML `unset` names exactly the tuple's members. Keep the YAML literal static so the gate introduces no additional Python import at runtime.
3. **Pin the suite's terminal defaults after the scrub.** Add autouse `pin_terminal_size` beside `_restore_cmd_run_env_vars`, with an **explicit fixture dependency** on `_restore_cmd_run_env_vars`. It sets `COLUMNS=80` / `LINES=24` after the shared scrub, so the fixtures cannot undo each other in an unspecified order. Keep the existing `setenv("")` then `delenv()` pattern in the scrub fixture so direct `os.environ` writes are also restored. Tests needing another interpreter, width or height can `monkeypatch.setenv` in their body, which runs after both fixtures. Pin with `setenv`, not deletion alone: `shutil.get_terminal_size` may query a real tty when capture is disabled; `80x24` matches its non-tty fallback. Existing mocks of `shutil.get_terminal_size` continue to work.
4. **Narrow, behavioral regression coverage.** Add a subprocess guard that selects the **11 exact node IDs** in Current Behavior, sets `LL_PYTHON=sys.executable`, `COLUMNS=150`, `LINES=60`, and uses `sys.executable -m pytest -n 0`. Clear inherited `PYTEST_ADDOPTS` and xdist worker-identity variables from the child env. Use an explicit `timeout=60`, below the suite's outer 120-second per-test timeout; capture bounded output on failure. Measure the guard's wall time before pinning the value: the child collects `test_builtin_loops.py`, which can be slow on a loaded machine. If the measured time is near 60 s, raise the timeout, but keep it below 120 s. Assert all 11 selected cases actually passed with none skipped/deselected (prefer stdlib parsing of `--junitxml`), not merely exit 0. The guard does not select itself, so it needs no recursion sentinel. Add ordinary fixture behavior tests for the default env and explicit in-body overrides. Execute the real `run_test` action with a non-pytest env probe so conftest cannot conceal a missing gate scrub, and include a failing command followed by `aggregate` to prove real failures still produce `GATE_FAILED`.

Baseline-aware gating (previously item 3, ENH-3692) was cancelled; corpus-test transience is **ENH-3697**.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` env scrub only; keep the literals pinned by tests (`echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"`, `grep '^pass_rate=' …`) and the `PYTHONPATH` export
- `scripts/little_loops/worktree_utils.py` — shared `HERMETIC_ENV_VARS` constant (new); replace the epic-verify single-var pop with the shared loop (required, affects test and lint child env)
- `scripts/tests/conftest.py` — import/expand `HERMETIC_ENV_VARS` into `_CMD_RUN_ENV_VARS`; autouse `pin_terminal_size` (new) explicitly depends on the scrub fixture
- `scripts/tests/test_bug3689_gate_env.py` (new) — narrow subprocess guard, fixture behavior/override assertions and shared-list/YAML consistency check
- `scripts/tests/test_feat3573_quality_gate.py` — actual `run_test`/`aggregate` env probe, explicit-command override and genuine-failure coverage
- `scripts/tests/test_worktree_utils.py` — extend epic-verify env-scrub coverage to all three variables for both test and lint commands
- `docs/reference/loops.md` — document the three removed inherited variables and explicit `test_cmd` assignments
- `docs/reference/API.md` — update the existing epic-verify single-variable scrub description to name the shared three-variable policy for test/lint children

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py:333` and `scripts/little_loops/runner_spec.py:335` — set `LL_PYTHON` for FSM shell actions (no change; the gate scrubs instead)
- `scripts/little_loops/host_runner.py` — `_BASELINE_NAMES` passes `COLUMNS`/`LINES` through to children (no change)
- `scripts/little_loops/loops/rn-remediate.yaml`, `rn-refine.yaml`, `autodev.yaml` — callers of the oracle; the scrub benefits all, contract unchanged
- `scripts/little_loops/parallel/orchestrator.py` and `scripts/little_loops/loops/auto-refine-and-implement.yaml` — epic-verify callers (no change); use the shared env policy through `verify_epic_branch_before_merge`

### Similar Patterns
- `scripts/little_loops/worktree_utils.py:744` — `env.pop("LL_PYTHON", None)` (BUG-3370)

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` (LL_PYTHON-sensitive); `TestCodeRunGateOracle` pins the `run_test` literals (`test_run_test_sidecar_declares_exit_code`, `test_run_test_stdout_not_double_prefixed`) — keep them; `MR11_MARKER_ALLOWLIST` and `TestInterpSweepBaseline.test_completeness_guard` — the scrub adds no `${context.*}` refs, so they should be untouched
- `scripts/tests/test_feat3573_quality_gate.py` — `TestOracleWorktreePythonPath._run_test_state` is the template for the real-action env probe. Test main and linked worktrees; assert all three vars are absent in a plain subprocess, `PYTHONPATH` is retained/prepended correctly, and `PATH` / `LL_VERIFY_GATE` survive. Explicit `test_cmd` assignments must win. A deliberately failing command must record nonzero `exit_code`, fallback `pass_rate=0.0` and `GATE_FAILED` through `aggregate`; do not use the shell action's own rc as the test verdict. Retain existing SKIP, aggregate and quality-evidence coverage.
- `scripts/tests/test_worktree_utils.py` — `TestVerifyEpicBranchBeforeMerge.test_ll_python_scrubbed_from_child_env` is the behavioral probe to extend to all three names. Cover test-only and lint-only invocations because both consume the scrubbed env. Keep marker, worker-budget, fuzz-depth and worktree `PYTHONPATH` coverage.
- `scripts/tests/test_hook_session_start.py` — `TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation` provides the subprocess pattern, but do not copy its whole-module selection, 300-second timeout or recursion sentinel into the new narrow guard
- `scripts/tests/test_cli_output.py` — `TestTerminalWidth` patches `shutil.get_terminal_size`, so a global `COLUMNS=80` does not break it. Recheck this module plus `scripts/tests/test_cli_loop_layout.py`, `scripts/tests/test_cli_loop_lifecycle.py` and `scripts/tests/test_state_feed_renderer.py` after implementation; their 349 cases passed in the temporary fixture experiment. Terminal-size behavior is defined by `scripts/little_loops/cli/output.py`'s `terminal_size()`.

### Documentation
- `docs/reference/loops.md` — `## oracles/code-run-gate`: required note naming `LL_PYTHON`/`COLUMNS`/`LINES` as removed inherited overrides, with an explicit assignment inside `test_cmd` as the supported way to request a value
- `docs/reference/API.md` — `verify_epic_branch_before_merge`: replace the current single-variable description with the shared three-variable scrub for both test and lint commands
- `CHANGELOG.md` — do NOT add under `[Unreleased]`; promote during release prep

## Implementation Steps

1. Define `HERMETIC_ENV_VARS` in `scripts/little_loops/worktree_utils.py` and use it for the epic-verify env loop. Extend the existing behavioral probe for test and lint invocations; preserve the other env controls.
2. Expand that tuple into `_CMD_RUN_ENV_VARS` in `scripts/tests/conftest.py` and add the dependent `pin_terminal_size` fixture. Verify the 11 named tests pass under `COLUMNS=150 LINES=60 LL_PYTHON=$(command -v python)`; add default/override fixture behavior tests.
3. Insert the bounded `unset` before the oracle's `bash -c "$TEST_CMD"`. Add shared-list consistency and actual-action env/override/failure tests, preserving worktree imports and output contracts.
4. Add the 11-case subprocess guard with the measured timeout (60 s by default, always below 120 s) and explicit passed-count assertion. Check `scripts/tests/test_cli_loop_layout.py`, `scripts/tests/test_cli_loop_lifecycle.py`, `scripts/tests/test_state_feed_renderer.py` and `scripts/tests/test_cli_output.py` with the defaults pinned. Add the consumer-facing loops note and update the epic-verify API description.
5. Run the authoritative suite, `python -m pytest scripts/tests/`, with `COLUMNS=150 LINES=60 LL_PYTHON=$(command -v python)` inherited; run the configured lint/type checks. Exercise `run_test` on the same 11 named tests under that env. The two corpus-ratchet tests are independently vulnerable to uncommitted `.issues/` edits until ENH-3697 lands; report such failures rather than bypassing the quality gate or claiming this issue makes the full suite green.

## Impact

- **Priority**: P2 - inherited `LL_PYTHON` / wide `COLUMNS` reproducibly make otherwise-passing tests fail; FSM shell actions set `LL_PYTHON`, exposing autodev's test gate to this trigger
- **Effort**: Small - bounded gate/epic-verify env scrub, shared conftest policy and terminal fixture, plus regression coverage and a docs note
- **Risk**: Low - fixed defaults require tests of other sizes to override them explicitly; both consumer test commands and epic-verify lint commands lose the three inherited overrides
- **Breaking Change**: No CLI/config schema change; the inherited subprocess environment changes as documented, with explicit assignments inside `test_cmd` preserved

## Program Design

### Types

- `HERMETIC_ENV_VARS: tuple[str, ...]` (new) — shared constant in `scripts/little_loops/worktree_utils.py`: exactly `LL_PYTHON`, `COLUMNS`, `LINES`. Drives epic-verify removal and conftest's initial scrub; a test checks the static YAML list against it. This name denotes the bounded fix, not a full environment allowlist.

### Signatures

- `pin_terminal_size(monkeypatch: pytest.MonkeyPatch, _restore_cmd_run_env_vars: None) -> None` (new) — autouse fixture in `scripts/tests/conftest.py`; explicit dependency guarantees the shared scrub runs before `COLUMNS=80` / `LINES=24` are set
- `test_suite_passes_with_ambient_gate_env(tmp_path: Path) -> None` (new) — narrow subprocess guard in `scripts/tests/test_bug3689_gate_env.py`; checks all 11 named tests pass with polluted interpreter/width/height values

### Call Path

`autodev` quality gate -> `code-run-gate` `run_test` (unsets the three inherited overrides, then `bash -c "$TEST_CMD"`) -> pytest -> `_restore_cmd_run_env_vars` (includes the shared tuple) -> dependent `pin_terminal_size` -> test body, whose explicit overrides win. Separately, `verify_epic_branch_before_merge` removes the same tuple from the env used by its test/lint subprocesses.

## Root Cause

- **File**: `scripts/little_loops/loops/oracles/code-run-gate.yaml`, `scripts/tests/conftest.py`
- **Anchor**: `run_test` state (runs the project `test_cmd` via `bash -c`); `_CMD_RUN_ENV_VARS` / `_restore_cmd_run_env_vars`
- **Cause**: `run_test` inherits the runner's ambient env unscrubbed (`LL_PYTHON` from `fsm/runners.py:333`, `COLUMNS`/`LINES` via `host_runner._BASELINE_NAMES`), and `conftest.py` scrubs leaked env via `_CMD_RUN_ENV_VARS` but not `LL_PYTHON` and nothing for terminal size.

## Acceptance Criteria

- All 11 env-sensitive tests listed under Current Behavior pass with `LL_PYTHON=sys.executable`, `COLUMNS=150`, `LINES=60` inherited, both via bare pytest and via the real code-run-gate `run_test` action. Corpus-ratchet behavior remains ENH-3697.
- A non-pytest subprocess probe through `run_test` sees none of the three inherited variables; `PATH`, inherited/linked-worktree `PYTHONPATH`, and `LL_VERIFY_GATE` survive. Explicit assignments inside `test_cmd` override the scrub.
- One shared `HERMETIC_ENV_VARS` tuple drives conftest's scrub and the epic-verify test/lint scrub; a structural test fails if YAML's static `unset` names differ from it. Other automation variables are not added to this policy.
- Per-test defaults are `LL_PYTHON` absent, `COLUMNS=80`, `LINES=24`; fixture ordering is explicit, in-body env overrides and existing terminal-size mocks still work, and the scrub's raw-write teardown behavior is retained.
- The narrow guard runs exactly the 11 named cases with `-n 0`, an explicit timeout below 120 s (60 s unless the measured wall time requires more) and a count assertion proving 11 passes without skips/deselection. It does not recursively select itself or rerun entire modules.
- A deliberately failing test command still records its original nonzero exit code and fallback `pass_rate=0.0`; `aggregate` produces `GATE_FAILED`. Null-command SKIP and existing output/quality-evidence contracts still pass their tests.
- `docs/reference/loops.md` documents the consumer environment change and explicit-command override behavior; `docs/reference/API.md` reflects the epic-verify test/lint scrub. No new dependencies, CLI options or schema fields are added.

## Out of Scope

- Baseline-aware gating (fail only on failures new relative to the base SHA) — ENH-3692, **cancelled** (won't-do).
- Making the two corpus-ratchet tests (`test_no_prose_dependency_drift_in_repo`, `TestRepoGate::test_no_new_unverifiable_evidence`) read the committed tree — **ENH-3697**. Until it lands, an autodev gate run with uncommitted `.issues/` edits can still false-fail on them; this issue does not authorize bypassing that gate.
- Changing `scripts/little_loops/host_runner.py`'s general child-env baseline, scrubbing other oracle stages, adding a general environment allowlist, or changing how autodev retries `quality_failed` issues.

## Related Key Documentation

- `docs/reference/loops.md` — `oracles/code-run-gate` contract and consumer-facing test-command behavior
- `docs/reference/API.md` — `little_loops.worktree_utils` epic-verify behavior

## Pre-Implementation Review

Reviewed 2026-10-02 with `ll-advise --signal user_requested --host claude-code --model opus`.

- **Recommendation:** proceed with the bounded scrub plus suite isolation after reconciling the issue directives. Opus confidence was `0.8`; its principal risks were consumer env compatibility, incomplete guard execution and guard timeouts. Its dissent questioned whether a shared constant was worth the coupling; retain it to satisfy the existing epic design, with conftest expanding the tuple and pinning terminal defaults only after its scrub.
- **Verified reproduction:** unchanged code, 11 exact test IDs: clean env `11 passed`; `LL_PYTHON=sys.executable COLUMNS=150 LINES=60` env `11 failed`.
- **Fixture experiment:** a temporary pytest plugin outside production/test sources applied the proposed dependent scrub/pin fixtures. The same 11 tests plus the four terminal/layout modules named in Implementation Steps passed: `360 passed`, four snapshots passed. This supports the design; it is not a full-suite implementation check.
- **Gate experiment:** inserting the proposed `unset` into an in-memory copy of the real `run_test` action removed all three inherited variables, preserved `PYTHONPATH` / `LL_VERIFY_GATE`, honored explicit command assignments, and recorded `exit_code=7` / `pass_rate=0.0` for a failing command; the real `aggregate` action then produced `GATE_FAILED`. Implementation must retain this regression assertion.
- Production code remains unchanged by this review. Implementation still needs the regression tests and authoritative full-suite validation above.

## Status

**Open** | Created: 2026-10-01 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-02T20:44:07 - `87a65a08-ddb3-4e8a-b852-af350980921a.jsonl`
- `/ll:verify-issues` - 2026-10-02T20:41:17 - `cd5e1b5d-cfd5-4657-840b-466941684a3e.jsonl`
- `/ll:verify-issues` - 2026-10-01T21:31:21 - `6aa5587a-18d6-457b-930d-4a16b529f58a.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T21:29:38 - `b2628e12-0ee9-430f-aae0-6c0fc3dc7bf2.jsonl`
- `/ll:verify-issues` - 2026-10-01T21:28:29 - `a5679a98-af15-46a9-af52-92fc245da95a.jsonl`
- `/ll:reconcile-issue` - 2026-10-01T21:26:32 - `a3e28191-5ebe-4216-a1f4-a1c1385490ab.jsonl`
- `/ll:verify-issues` - 2026-10-01T21:25:46 - `44c84aaa-df89-416c-b02c-7317107a5150.jsonl`
- `/ll:wire-issue` - 2026-10-01T21:22:51 - `f86b49b5-4077-4c02-a97a-dc276b6588cc.jsonl`
- `/ll:refine-issue` - 2026-10-01T21:14:19 - `1d21e852-a25d-445f-aa12-6d1f47709472.jsonl`
- `/ll:format-issue` - 2026-10-01T21:13:42 - `0cf2c9fd-b82b-411d-99fa-51ff90db0e06.jsonl`
- `/ll:capture-issue` - 2026-10-01T21:02:10 - `bb30f6cf-829a-4e1c-90a3-72171102a54b.jsonl`
