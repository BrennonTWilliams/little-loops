---
id: BUG-3370
type: BUG
title: Diagnose 4 unexplained epic verify-gate test failures not covered by the tsc quarantine
priority: P3
status: open
discovered_by: pre-implementation-review
discovered_date: '2026-08-31'
relates_to: [BUG-3368, BUG-2649, BUG-3082]
decision_needed: false
---

# BUG-3370: Diagnose 4 unexplained epic verify-gate test failures not covered by the tsc quarantine

## Summary

Split out of BUG-3368 during pre-implementation review. During `ll-loop run sprint-refine-and-implement EPIC-1463` (run dir `.loops/runs/sprint-refine-and-implement-20260831T135628/`), the epic-worktree verify gate reported 6 test failures on commit d8e8b9ed1. Two (`test_tsc_noemit_passes` in `test_opencode_adapter.py`/`test_omp_adapter.py`) were root-caused to missing `node_modules` in the ephemeral worktree and are quarantined under BUG-3368. The remaining 4 have no identified mechanism:

- `test_recheck_set_folds_back_abandoned_residual` (`scripts/tests/test_builtin_loops.py`)
- `test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py`)
- `test_hint_fires_for_root_level_report` (`scripts/tests/test_check_private_refs_hook.py`)
- `test_policy_builder_renders_byte_identically_to_golden_fixture` (`scripts/tests/test_enh3035_artifact_template_kit.py`)

All 4 pass in ~5.5s when run directly on a clean checkout of the same commit. Commit d8e8b9ed1's diff is disjoint from all 4 tests' code paths.

## Current Behavior

The verify gate's subprocess/worktree environment sometimes produces failures in these 4 tests that do not reflect real regressions in the commit under test. This is the third recurrence of the environment-only-false-failure class (after BUG-2649 PYTHONPATH, BUG-3082 LL_AUTOMATION); neither prior fix's mechanism covers these 4 tests.

## Expected Behavior

The verify gate's environment reproduces the same results for these 4 tests as a direct run on the same commit — or, if a test is inherently non-deterministic under the gate's invocation, it self-quarantines via `LL_VERIFY_GATE=1` with a tracked un-quarantine path.

## Important caveat: single observation, possibly flaky

These 4 failures have been observed **exactly once**, during a run with concurrent xdist workers, a reduced `PYTEST_XDIST_AUTO_NUM_WORKERS`, and `LL_FUZZ=full`. Known prior false signals in this environment class: a pytest log redirected to a fixed `.loops/tmp/scratch/` name being clobbered by a concurrent run, and ambient `LL_AUTOMATION` leaking into descendants. Do not begin env-diffing before establishing reproducibility (Implementation Step 1).

## Codebase Research Findings (carried over from BUG-3368)

- All four inherit the gate's full child env (`LL_VERIFY_GATE=1`, a reduced `PYTEST_XDIST_AUTO_NUM_WORKERS`, `LL_FUZZ=full`, a conditional `PYTHONPATH` prepend — built in `verify_epic_branch_before_merge()`, `scripts/little_loops/worktree_utils.py:565-589`) with no per-test override.
- `test_hint_fires_for_root_level_report` specifically depends on `cwd`-relative `git check-ignore` behavior inside the ephemeral worktree path, which could differ from the main checkout.
- Ruled out: none of the four use Hypothesis (`@given`/`@settings`), so the gate's `LL_FUZZ=full` override is not implicated.
- `project_child_env()` (`scripts/little_loops/host_runner.py:1853-1883`) is the chokepoint every subprocess call in this path routes through — it provides no way to clear or deny an inherited variable (tracked separately as ENH-3203).
- No existing subprocess-env capture/diff utility exists in the repo; the `dump_verify_gate_env()` diagnostic below would be new, **temporary tooling only** — not shipped code.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

### Files to Modify (candidates — mechanism, not a fix, is confirmed for 2 of 4)
- `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge()`'s env build (`:565-589`) and `copy_files=[]` call to `setup_worktree()` (`:555`) are where BUG-2649/BUG-2629's fixes landed and where any new env-scrub or copy-allowlist fix would land too
- `scripts/little_loops/host_runner.py` — `project_child_env()` (`:1853-1883`), the single additive-only chokepoint every task-path spawn routes through; per its own docstring, it has no clear/deny primitive (tracked as ENH-3203)
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` (`:297-306`) is the one call site that injects `LL_PYTHON` into the env chain implicated in `test_recheck_set_folds_back_abandoned_residual`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py:1527` — `ParallelOrchestrator::_verify_epic_branch_before_merge`, the other caller of the gate besides the FSM `verify` state
- `scripts/little_loops/prepatch_check.py:31`, `scripts/little_loops/cli/sprint/run.py:27`, `scripts/little_loops/cli/parallel.py:35`, `scripts/little_loops/parallel/orchestrator.py:47` — importers of `worktree_utils.py`

### Conventions in Force
- Env-contamination fixes land inside `verify_epic_branch_before_merge()`'s own env-build block rather than at call sites — evidence: BUG-2649/BUG-2629's PYTHONPATH fix at `worktree_utils.py:565-589`
- Suite-wide env scrubs (vs. gate-specific ones) go through `conftest.py`'s autouse `_CMD_RUN_ENV_VARS` allowlist, which is unconditional (not gated on `LL_VERIFY_GATE`) — evidence: `conftest.py:1060-1078`
- Hermeticity regressions are proven by re-spawning the suite as a subprocess with the contaminated condition deliberately set, pinned to `-n 0`, and asserting exit 0 — evidence: `test_hook_session_start.py:667-719` (`TestAmbientAutomationEnvHermeticity`)

### Tests
- `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (`:956-1282`) — existing gate regression coverage; already includes a BUG-2650-pattern stress-loop test, `test_gate_read_is_deterministic_on_present_needle` (`:1263`)
- `scripts/tests/spike/epic_verify_gate_doc_flake/{repro_harness.py,test_repro_harness.py}` — BUG-2650's bounded (`MAX_ITERATIONS=25`/`MAX_WORKERS=2`) repeat-loop-through-the-real-gate harness; never promoted out of `scripts/tests/spike/`, and not reused by `test_gate_read_is_deterministic_on_present_needle` above despite driving the same shape

## Program Design

### Types

- (none — diagnosis issue; production types TBD once a mechanism is identified)

### Signatures

- `dump_verify_gate_env() -> dict[str, str]` — **temporary diagnostic helper** (Step 2 only, removed before close): capture `PATH`, node/bun toolchain resolution, `PYTHONPATH`, cwd, and remaining env vars from inside the verify-gate subprocess for comparison against a direct clean-checkout run.

### Call Path

`merge_epic_branch` (epic-worktree verify gate, `scripts/little_loops/loops/auto-refine-and-implement.yaml`) -> `verify_epic_branch_before_merge()` (`worktree_utils.py:481-608`) -> `dump_verify_gate_env()` -> diff against direct `python -m pytest scripts/tests/` on a clean checkout of the same commit

Confirmed mechanism call paths (from codebase-analyzer, this pass):

- `DefaultActionRunner.run()` (`fsm/runners.py:297-306`) spawns the "verify" FSM state's subprocess with `env=project_child_env(extra={"LL_PYTHON": sys.executable})` -> `verify_epic_branch_before_merge()` (`worktree_utils.py:571`) copies that same process's `os.environ` (unscrubbed) into its own child env -> `test_cmd` pytest subprocess -> individual tests' own un-overridden subprocess spawns inherit `LL_PYTHON` verbatim (implicates `test_recheck_set_folds_back_abandoned_residual`)
- `setup_worktree()` (`worktree_utils.py:160-282`, called with `copy_files=[]`) -> `git worktree add` materializes tracked content only -> gitignored `.ll/design-tokens/` and `postmortems/` are absent in the worktree -> `load_design_tokens()` (`design_tokens.py:412`) returns `None` (implicates `test_policy_builder_renders_byte_identically_to_golden_fixture`) / `git check-ignore -q postmortems` (`hooks/scripts/check-private-refs.sh:229`) behavior against a nonexistent path (implicates `test_hint_fires_for_root_level_report`, unconfirmed)

### Decision Rules

N/A — no new decision logic; this issue diagnoses existing verify-gate env-inheritance (`project_child_env()`) and worktree-materialization (`setup_worktree()`) behavior. It does not introduce a new gap kind, gate, threshold, or classification rule.

## Implementation Steps

1. **Reproduce first**: re-run the verify gate on commit d8e8b9ed1 (or current main) 2–3 times, serially (no concurrent gates), and record whether any of the 4 failures recur. If none reproduce, close this issue as a flake (likely concurrent-run interference — e.g. scratch-file collision) with the evidence recorded; steps 2–4 evaporate.
2. If reproducible: diagnose via the temporary `dump_verify_gate_env()` diff, plus for `test_hint_fires_for_root_level_report` specifically, cwd-relative `git check-ignore` behavior inside the ephemeral worktree path.
3. Fix each identified contamination vector at the source (scrub/normalize the diverging env value), following the BUG-2649/BUG-3082 pattern — BUG-2649's fix lives in `worktree_utils.py`'s env build; BUG-3082's lives in `scripts/tests/conftest.py:1060-1078`'s `_CMD_RUN_ENV_VARS` allowlist. Note that list is suite-wide (autouse, not gated on `LL_VERIFY_GATE`) — adding a var there scrubs it for the entire suite.
4. Add a hermeticity regression test per fixed vector, mirroring `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (BUG-2649 pattern) or `scripts/tests/test_hook_session_start.py:667-718` (BUG-3082 pattern: re-spawn the suite as a subprocess with the contaminated condition deliberately set, assert exit 0).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- Two of the four mechanisms are now code-traced and **deterministic**, not flaky — see Root Cause findings above. `test_policy_builder_renders_byte_identically_to_golden_fixture` fails on every gate run when `design_tokens.enabled: true` (confirmed active in this repo); the mechanism (`.ll/design-tokens/` is gitignored and never worktree-materialized) does not require a reproduction attempt to establish reproducibility. `test_recheck_set_folds_back_abandoned_residual` fails specifically when the gate is invoked in-process from an FSM "verify" state action (which sets `LL_PYTHON`), not from a bare `python -m pytest` run — a blind repeat-run per Step 1 only reproduces it if that exact invocation path is exercised.
- `test_hint_fires_for_root_level_report`'s cwd-relative-`git check-ignore` hypothesis (as originally framed) is refuted — cwd resolves correctly in both environments. The refined candidate is `postmortems/`'s physical absence in the worktree affecting `git check-ignore -q`'s exit code for a directory-only gitignore pattern against a nonexistent path; confirming this needs a direct git experiment, not a gate re-run.
- `test_no_new_unverifiable_evidence` has no code-traced data-divergence candidate; the best-supported explanation is the gate's own documented concurrent-CPU-contention timeout risk (`worktree_utils.py:572-579`), not a fixable data/env vector.
- Existing prior art for a bounded repeat-loop-through-the-real-gate reproduction approach: `scripts/tests/spike/epic_verify_gate_doc_flake/repro_harness.py`'s `run_gate_n_times()` (BUG-2650, `MAX_ITERATIONS=25`/`MAX_WORKERS=2`) already proves this shape is safe against the suite's beachball/CPU-starvation constraint; it was never promoted out of `scripts/tests/spike/`, and `test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge::test_gate_read_is_deterministic_on_present_needle` (`:1263`) already contains an independently-written near-duplicate of the same stress-loop shape without reusing it.

## Impact

- **Priority**: P3 — observed once; not currently blocking (the co-occurring merge block traced to BUG-3369, and the confirmed tsc mechanism is handled by BUG-3368). Escalate to P2 if Step 1 reproduces.
- **Effort**: Unknown until Step 1 — bounded-small if it's a flake; investigation-heavy if reproducible.
- **Risk**: Low — targets test/gate infrastructure.
- **Breaking Change**: No

## Steps to Reproduce

1. Run the epic-worktree verify gate against commit d8e8b9ed1 (via `verify_epic_branch_before_merge()` or a full `ll-loop run sprint-refine-and-implement` epic run).
2. Compare the 4 tests' outcomes against a direct `python -m pytest scripts/tests/` on the same commit (all pass directly).
3. Original evidence: `verify-detail.txt`, `verify-returncode.txt`, `summary.json` under `.loops/runs/sprint-refine-and-implement-20260831T135628/`.

## Root Cause

Unknown — single observation, not yet reproduced. Candidate classes: a third env contamination vector (BUG-2649/BUG-3082 precedent), worktree-cwd-sensitive behavior (`git check-ignore`), or concurrent-run interference making this a flake rather than a deterministic divergence.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- `test_recheck_set_folds_back_abandoned_residual` (`scripts/tests/test_builtin_loops.py:4445-4479`): the ambient `LL_PYTHON` env var — set only when the gate itself is invoked in-process by an FSM "verify" state action (`DefaultActionRunner.run()`, `scripts/little_loops/fsm/runners.py:305`, `env=project_child_env(extra={"LL_PYTHON": sys.executable})`) — rides unscrubbed through `verify_epic_branch_before_merge()`'s `env = project_child_env(extra={"LL_VERIFY_GATE": "1"})` (`worktree_utils.py:571`) into the `test_cmd` pytest subprocess, then into this test's own un-overridden `subprocess.run(["bash","-c",script], ...)` (`test_builtin_loops.py:4470`). The test's PATH-stub mock for `python3` (lines 4461-4469) only intercepts when `LL_PYTHON` is unset — the heredoc expands `${LL_PYTHON:-python3}` (`auto-refine-and-implement.yaml:405`), and when `LL_PYTHON` holds an absolute interpreter path, bash execs it directly, bypassing `PATH` and the mock, then fails against the test's bare `tmp_path` fixture (no project config). On a bare terminal `pytest` invocation `LL_PYTHON` is never set, so the mock works. **Deterministic given `LL_PYTHON` is set** (i.e. the gate was invoked from inside an FSM action), not random.
- `test_policy_builder_renders_byte_identically_to_golden_fixture` (`scripts/tests/test_enh3035_artifact_template_kit.py:62-68`): `.ll/design-tokens/` is gitignored (`.gitignore:163`); `setup_worktree()`'s copy step (`worktree_utils.py:160-282`, called with `copy_files=[]` at `worktree_utils.py:555`) only materializes `.claude/` plus an explicit `copy_files` list, and `git worktree add` itself never brings in untracked/gitignored paths. So the ephemeral verify-gate worktree never has `.ll/design-tokens/warm-paper/...` on disk. `load_design_tokens()` (`design_tokens.py:412`) then returns `None`, and `themed_css_vars()` falls back to empty CSS (`artifact_template_kit.py:40-42`) instead of the real `warm-paper` values the golden fixture bakes in (`--color-paper-0: #fdfbf6`, etc.). **This mismatch is deterministic on every gate run** in a repo with `design_tokens.enabled: true` (confirmed active in this repo's `.ll/ll-config.json`) — it reproduces every time, contradicting the issue's "single observation, possibly flaky" framing for this specific test.
- `test_hint_fires_for_root_level_report` (`scripts/tests/test_check_private_refs_hook.py:96-105`): the issue's original cwd-relative-`git check-ignore` hypothesis is refuted in its narrow form — `REPO_ROOT` (`test_check_private_refs_hook.py:32`) and the hook's `git check-ignore -q postmortems` (`hooks/scripts/check-private-refs.sh:229`) both resolve cwd correctly to the worktree root, and the `.gitignore` rule for `postmortems/` (`.gitignore:136`) is tracked and checked out identically into every worktree. The refined candidate: `postmortems/` is a real, non-empty, gitignored directory on disk in the main checkout (11+ files) but does not exist at all in a fresh worktree (same materialization gap as the design-tokens case above). Whether `git check-ignore -q` on a directory-only gitignore pattern returns a different exit code when the target path doesn't physically exist versus when it does is a plausible, code-traced but **not yet confirmed** explanation — the analyzer could not execute `git` to verify the exact exit code in each case.
- `test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951-968`): no code-level data divergence found — `REPO_ROOT` resolves correctly and the evidence baseline (`.ll/evidence-baseline.json`) is git-tracked, not gitignored. The best-supported explanation is the gate's own documented CPU-contention risk (`worktree_utils.py:572-579`: concurrent verify gates can oversubscribe cores) pushing this test's `subprocess.run(..., timeout=GATE_TIMEOUT)` (`test_verify_evidence.py:71`, `GATE_TIMEOUT=120`) past its 120s budget under load, raising `TimeoutExpired` — a resource/scheduling failure, not a data or env-content difference.

## Status

**Open** | Created: 2026-08-31 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-08-31T23:07:36 - `138b65fa-2748-4f37-965e-8ace7ca774da.jsonl`
- pre-implementation review split from BUG-3368 - 2026-08-31
