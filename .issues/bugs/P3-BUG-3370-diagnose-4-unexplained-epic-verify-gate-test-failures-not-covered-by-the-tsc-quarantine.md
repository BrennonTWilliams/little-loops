---
id: BUG-3370
type: BUG
title: Diagnose 4 unexplained epic verify-gate test failures not covered by the tsc
  quarantine
priority: P3
status: done
discovered_by: pre-implementation-review
discovered_date: '2026-08-31'
completed_at: '2026-09-01T02:40:34Z'
relates_to:
- BUG-3368
- BUG-2649
- BUG-3082
decision_needed: false
reconcile_attempted: true
confidence_score: 97
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 21
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

## Important caveat: 3 of 4 mechanisms confirmed deterministic; 1 remains single-observation

Originally all 4 failures were observed exactly once. Since then, code-tracing plus a direct git experiment (2026-08-31, pre-implementation review) confirmed deterministic mechanisms for **three** of the four (`LL_PYTHON` inheritance, missing `.ll/design-tokens/`, missing `postmortems/` — see Root Cause). Only `test_no_new_unverifiable_evidence` remains a single, unexplained observation; the flakiness caveat (concurrent xdist workers, scratch-log clobber risk, ambient-env leaks) now applies to that test alone. Do not env-diff for it before establishing reproducibility — and note the recorded evidence cannot confirm the timeout hypothesis (see Step 3).

## Codebase Research Findings (carried over from BUG-3368)

- All four inherit the gate's full child env (`LL_VERIFY_GATE=1`, a reduced `PYTEST_XDIST_AUTO_NUM_WORKERS`, `LL_FUZZ=full`, a conditional `PYTHONPATH` prepend — built in `verify_epic_branch_before_merge()`, `scripts/little_loops/worktree_utils.py:565-589`) with no per-test override.
- `test_hint_fires_for_root_level_report` specifically depends on `cwd`-relative `git check-ignore` behavior inside the ephemeral worktree path, which could differ from the main checkout.
- Ruled out: none of the four use Hypothesis (`@given`/`@settings`), so the gate's `LL_FUZZ=full` override is not implicated.
- `project_child_env()` (`scripts/little_loops/host_runner.py:1853-1883`) is the chokepoint every subprocess call in this path routes through — it provides no way to clear or deny an inherited variable (tracked separately as ENH-3203).
- No existing subprocess-env capture/diff utility exists in the repo; the `dump_verify_gate_env()` diagnostic below would be new, **temporary tooling only** — not shipped code.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Files to Modify (candidates — mechanism, not a fix, is confirmed for 2 of 4)**: `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge()`'s env build (`:565-589`) and `copy_files=[]` call to `setup_worktree()` (`:555`) are where BUG-2649/BUG-2629's fixes landed and where any new env-scrub or copy-allowlist fix would land too; `scripts/little_loops/host_runner.py` — `project_child_env()` (`:1853-1883`), the single additive-only chokepoint every task-path spawn routes through, with no clear/deny primitive (tracked as ENH-3203); `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` (`:297-306`) is the one call site that injects `LL_PYTHON` into the env chain implicated in `test_recheck_set_folds_back_abandoned_residual`
- **Dependent Files (Callers/Importers)**: `scripts/little_loops/parallel/orchestrator.py:1527` — `ParallelOrchestrator::_verify_epic_branch_before_merge`, the other caller of the gate besides the FSM `verify` state; `scripts/little_loops/prepatch_check.py:31`, `scripts/little_loops/cli/sprint/run.py:27`, `scripts/little_loops/cli/parallel.py:35`, `scripts/little_loops/parallel/orchestrator.py:47` — importers of `worktree_utils.py`
- **Conventions in Force**: env-contamination fixes land inside `verify_epic_branch_before_merge()`'s own env-build block rather than at call sites — evidence: BUG-2649/BUG-2629's PYTHONPATH fix at `worktree_utils.py:565-589`; suite-wide env scrubs (vs. gate-specific ones) go through `conftest.py`'s autouse `_CMD_RUN_ENV_VARS` allowlist, which is unconditional (not gated on `LL_VERIFY_GATE`) — evidence: `conftest.py:1060-1078`; hermeticity regressions are proven by re-spawning the suite as a subprocess with the contaminated condition deliberately set, pinned to `-n 0`, and asserting exit 0 — evidence: `test_hook_session_start.py:667-719` (`TestAmbientAutomationEnvHermeticity`)
- **Tests**: `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (`:956-1282`) — existing gate regression coverage; already includes a BUG-2650-pattern stress-loop test, `test_gate_read_is_deterministic_on_present_needle` (`:1263`); `scripts/tests/spike/epic_verify_gate_doc_flake/{repro_harness.py,test_repro_harness.py}` — BUG-2650's bounded (`MAX_ITERATIONS=25`/`MAX_WORKERS=2`) repeat-loop-through-the-real-gate harness; never promoted out of `scripts/tests/spike/`, and not reused by `test_gate_read_is_deterministic_on_present_needle` above despite driving the same shape

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **Env-scrub landing site precedent conflicts by scope**: gate-specific env fixes land in the gate's own env-build block — evidence: BUG-2649's PYTHONPATH prepend, `worktree_utils.py:583-589`, immediately after `env = project_child_env(extra={"LL_VERIFY_GATE": "1"})` (`:571`); suite-wide scrubs instead go through `conftest.py`'s autouse `_CMD_RUN_ENV_VARS` allowlist (`conftest.py:1060-1078`) — evidence: BUG-3082's LL_AUTOMATION fix. The two prior fixes disagree on location because the failure shapes differ (a value the gate itself injects vs. an ambient var any test's raw `os.environ` read might see); `LL_PYTHON` is a gate-injected value (matches the BUG-2649 shape, not the BUG-3082 shape).
- **`copy_files` directory entries are an exercised code path, not a new capability**: `setup_worktree()` already handles directory entries in `copy_files` via `copytree(..., dirs_exist_ok=True)` (`worktree_utils.py:265-268`). The general worktree flow's configured default (`worktree_copy_files` in `scripts/little_loops/config/automation.py:101-103,141-143` — `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]`) predates and is unrelated to this gap. `verify_epic_branch_before_merge()` and `setup_prepatch_worktree()` both hardcode `copy_files=[]` at their `setup_worktree()` call sites (`worktree_utils.py:555`, `:392`) rather than passing the configured default — no existing call site has ever added an entry to this specific gate's list, and no prior `copy_files` addition anywhere in the codebase was made to fix a gitignored-directory-materialization bug.
- **Hermeticity regression tests follow one of two disagreeing shapes**: (a) re-spawn the *outer test process* as a subprocess with the contaminated condition deliberately set, pinned to `-n 0`, asserting exit 0 — evidence: `TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation` (`test_hook_session_start.py:667-718`), which guards against self-recursion via `_AMBIENT_GUARD_SENTINEL` (`:682-685`); or (b) call `verify_epic_branch_before_merge()` directly in-process against a real scratch git repo and assert on its `(ok, message, returncode)` tuple, optionally stress-looped — evidence: `TestVerifyEpicBranchBeforeMerge` (`test_worktree_utils.py:956-1282`), specifically `test_verify_gate_marker_set_in_child_env` (`:1162-1183`) and the stress-loop `test_gate_read_is_deterministic_on_present_needle` (`:1263-1293`).
- **Searched, no hits**: no existing env-diff/env-dump utility exists anywhere in `scripts/little_loops/` (confirms this issue's own finding that `dump_verify_gate_env()` would be new); no test anywhere in `scripts/tests/` exercises real `git check-ignore` process exit-code behavior against a path that may or may not physically exist (the 3 files matching `check-ignore|check_ignore` don't cover this — `test_audit_loop_run_skill.py:642` only string-matches `"git check-ignore"` inside markdown prose) — the `postmortems/`-absence hypothesis for `test_hint_fires_for_root_level_report` has no established test-pattern precedent to follow.
- Related prior art already on file: `scripts/tests/spike/epic_verify_gate_doc_flake/repro_harness.py`'s `run_gate_n_times()` (BUG-2650) remains unpromoted from `scripts/tests/spike/` and is not reused by `test_gate_read_is_deterministic_on_present_needle` despite the same bounded repeat-loop-through-the-real-gate shape.

## Program Design

### Types

- (none — diagnosis issue; production types TBD once a mechanism is identified)

### Signatures

- `dump_verify_gate_env() -> dict[str, str]` — **temporary diagnostic helper, now scoped to `test_no_new_unverifiable_evidence` only** (the other 3 mechanisms are confirmed without it; removed before close): capture `PATH`, `PYTHONPATH`, cwd, and remaining env vars from inside the verify-gate subprocess for comparison against a direct clean-checkout run. Only build it if Step 3 opts for re-running the gate rather than accepting the flake classification.

### Call Path

`merge_epic_branch` (epic-worktree verify gate, `scripts/little_loops/loops/auto-refine-and-implement.yaml`) -> `verify_epic_branch_before_merge()` (`worktree_utils.py:481-608`) -> (Step 3 only, if pursued) `dump_verify_gate_env()` -> diff against direct `python -m pytest scripts/tests/` on a clean checkout of the same commit

Confirmed mechanism call paths (from codebase-analyzer, this pass):

- `DefaultActionRunner.run()` (`fsm/runners.py:297-306`) spawns the "verify" FSM state's subprocess with `env=project_child_env(extra={"LL_PYTHON": sys.executable})` -> `verify_epic_branch_before_merge()` (`worktree_utils.py:571`) copies that same process's `os.environ` (unscrubbed) into its own child env -> `test_cmd` pytest subprocess -> individual tests' own un-overridden subprocess spawns inherit `LL_PYTHON` verbatim (implicates `test_recheck_set_folds_back_abandoned_residual`)
- `setup_worktree()` (`worktree_utils.py:160-282`, called with `copy_files=[]`) -> `git worktree add` materializes tracked content only -> gitignored `.ll/design-tokens/` and `postmortems/` are absent in the worktree -> `load_design_tokens()` (`design_tokens.py:412`) returns `None` (implicates `test_policy_builder_renders_byte_identically_to_golden_fixture`) / `git check-ignore -q postmortems` (`hooks/scripts/check-private-refs.sh:229`) behavior against a nonexistent path (implicates `test_hint_fires_for_root_level_report`, unconfirmed)

### Decision Rules

N/A — no new decision logic; this issue diagnoses existing verify-gate env-inheritance (`project_child_env()`) and worktree-materialization (`setup_worktree()`) behavior. It does not introduce a new gap kind, gate, threshold, or classification rule.

## Implementation Steps

1. **Two of four mechanisms are already confirmed deterministic — skip reproduction, go straight to Step 4**: `test_recheck_set_folds_back_abandoned_residual` (fails whenever the gate is invoked in-process from an FSM "verify" state action, which sets `LL_PYTHON`) and `test_policy_builder_renders_byte_identically_to_golden_fixture` (fails on every gate run when `design_tokens.enabled: true`, as in this repo) — see Root Cause findings.
2. ~~Confirm the `postmortems/` hypothesis via a direct git experiment~~ **DONE (2026-08-31 pre-implementation review): confirmed.** In a scratch repo with `.gitignore` containing `postmortems/`: `git check-ignore -q postmortems` exits **1** when the directory does not physically exist and **0** when it does — so the hook's hint (`check-private-refs.sh:229`) silently never fires in the ephemeral worktree, failing `test_hint_fires_for_root_level_report`. Bonus finding: `git check-ignore -q postmortems/` (trailing slash) exits **0 regardless of physical existence** — a one-character hook fix that also makes the hint work in fresh downstream clones that lack the directory. Prefer this over materializing `postmortems/` in the worktree. (Verify trailing-slash behavior holds on the CI runner's git version via the regression test.)
3. For `test_no_new_unverifiable_evidence`: no code-traced data/env divergence exists. **Note: the recorded evidence cannot confirm the timeout hypothesis** — `verify-detail.txt` in the run dir is a 26-line tail of pytest output (short-summary lines only, no tracebacks), so whether the failure was a `TimeoutExpired` is unrecoverable. Either re-run the gate with full log capture to catch a recurrence, or accept it as a documented flake class (optionally raising `GATE_TIMEOUT` or self-quarantining under `LL_VERIFY_GATE=1`). Consider a follow-up ENH: the gate should persist the full pytest log per run so future diagnosis issues aren't evidence-starved.
4. Fix each confirmed mechanism at the source: scrub `LL_PYTHON` in `verify_epic_branch_before_merge()`'s env build (`worktree_utils.py:565-589`, BUG-2649/BUG-3082 pattern — BUG-2649's fix lives there, BUG-3082's lives in `scripts/tests/conftest.py:1060-1078`'s suite-wide `_CMD_RUN_ENV_VARS` allowlist) for the `LL_PYTHON` mechanism; use the trailing-slash `git check-ignore -q postmortems/` fix from Step 2 for the hook mechanism; for the design-tokens mechanism, decide between (a) adding `.ll/design-tokens/` to the gate's `copy_files` (`worktree_utils.py:555`) — smallest diff, but copies user-local gitignored state into a gate meant to test the branch, and leaves the golden test dependent on whatever the user's editable `warm-paper` tokens currently say (a local token edit breaks the test on the main checkout too) — or (b) making `test_policy_builder_renders_byte_identically_to_golden_fixture` hermetic by pinning its token inputs to a checked-in fixture directory instead of ambient `.ll/design-tokens/`. **(b) is the durable fix**; (a) is acceptable as a stopgap only.
5. Add a hermeticity regression test per fixed vector, mirroring `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (BUG-2649 pattern) or `scripts/tests/test_hook_session_start.py:667-718` (BUG-3082 pattern: re-spawn the suite as a subprocess with the contaminated condition deliberately set, assert exit 0).

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

3 of 4 confirmed deterministic (see findings below and the 2026-08-31 pre-implementation review): `LL_PYTHON` env inheritance (`test_recheck_set_folds_back_abandoned_residual`), gitignored `.ll/design-tokens/` never materialized in the worktree (`test_policy_builder_renders_byte_identically_to_golden_fixture`), and gitignored `postmortems/` never materialized — `git check-ignore -q postmortems` exits 1 against a physically-absent path, 0 when present, **confirmed by direct git experiment** (`test_hint_fires_for_root_level_report`). `test_no_new_unverifiable_evidence` remains unknown — single observation; best-supported hypothesis is the gate's documented CPU-contention timeout, unconfirmable from the tail-only recorded log.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- `test_recheck_set_folds_back_abandoned_residual` (`scripts/tests/test_builtin_loops.py:4445-4479`): the ambient `LL_PYTHON` env var — set only when the gate itself is invoked in-process by an FSM "verify" state action (`DefaultActionRunner.run()`, `scripts/little_loops/fsm/runners.py:305`, `env=project_child_env(extra={"LL_PYTHON": sys.executable})`) — rides unscrubbed through `verify_epic_branch_before_merge()`'s `env = project_child_env(extra={"LL_VERIFY_GATE": "1"})` (`worktree_utils.py:571`) into the `test_cmd` pytest subprocess, then into this test's own un-overridden `subprocess.run(["bash","-c",script], ...)` (`test_builtin_loops.py:4470`). The test's PATH-stub mock for `python3` (lines 4461-4469) only intercepts when `LL_PYTHON` is unset — the heredoc expands `${LL_PYTHON:-python3}` (`auto-refine-and-implement.yaml:405`), and when `LL_PYTHON` holds an absolute interpreter path, bash execs it directly, bypassing `PATH` and the mock, then fails against the test's bare `tmp_path` fixture (no project config). On a bare terminal `pytest` invocation `LL_PYTHON` is never set, so the mock works. **Deterministic given `LL_PYTHON` is set** (i.e. the gate was invoked from inside an FSM action), not random.
- `test_policy_builder_renders_byte_identically_to_golden_fixture` (`scripts/tests/test_enh3035_artifact_template_kit.py:62-68`): `.ll/design-tokens/` is gitignored (`.gitignore:163`); `setup_worktree()`'s copy step (`worktree_utils.py:160-282`, called with `copy_files=[]` at `worktree_utils.py:555`) only materializes `.claude/` plus an explicit `copy_files` list, and `git worktree add` itself never brings in untracked/gitignored paths. So the ephemeral verify-gate worktree never has `.ll/design-tokens/warm-paper/...` on disk. `load_design_tokens()` (`design_tokens.py:412`) then returns `None`, and `themed_css_vars()` falls back to empty CSS (`artifact_template_kit.py:40-42`) instead of the real `warm-paper` values the golden fixture bakes in (`--color-paper-0: #fdfbf6`, etc.). **This mismatch is deterministic on every gate run** in a repo with `design_tokens.enabled: true` (confirmed active in this repo's `.ll/ll-config.json`) — it reproduces every time, contradicting the issue's "single observation, possibly flaky" framing for this specific test.
- `test_hint_fires_for_root_level_report` (`scripts/tests/test_check_private_refs_hook.py:96-105`): the issue's original cwd-relative-`git check-ignore` hypothesis is refuted in its narrow form — `REPO_ROOT` (`test_check_private_refs_hook.py:32`) and the hook's `git check-ignore -q postmortems` (`hooks/scripts/check-private-refs.sh:229`) both resolve cwd correctly to the worktree root, and the `.gitignore` rule for `postmortems/` (`.gitignore:136`) is tracked and checked out identically into every worktree. The refined candidate: `postmortems/` is a real, non-empty, gitignored directory on disk in the main checkout (11+ files) but does not exist at all in a fresh worktree (same materialization gap as the design-tokens case above). Whether `git check-ignore -q` on a directory-only gitignore pattern returns a different exit code when the target path doesn't physically exist versus when it does is a plausible, code-traced but **not yet confirmed** explanation — the analyzer could not execute `git` to verify the exact exit code in each case.
- `test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951-968`): no code-level data divergence found — `REPO_ROOT` resolves correctly and the evidence baseline (`.ll/evidence-baseline.json`) is git-tracked, not gitignored. The best-supported explanation is the gate's own documented CPU-contention risk (`worktree_utils.py:572-579`: concurrent verify gates can oversubscribe cores) pushing this test's `subprocess.run(..., timeout=GATE_TIMEOUT)` (`test_verify_evidence.py:71`, `GATE_TIMEOUT=120`) past its 120s budget under load, raising `TimeoutExpired` — a resource/scheduling failure, not a data or env-content difference.

## Resolution

Fixed 3 of 4 confirmed mechanisms at the source:

- `test_recheck_set_folds_back_abandoned_residual`: scrubbed `LL_PYTHON` from
  the gate's child env (`env.pop("LL_PYTHON", None)` in
  `verify_epic_branch_before_merge()`, `worktree_utils.py`, immediately after
  the `project_child_env()` call) so it no longer rides through unscrubbed
  from an FSM "verify" state's `DefaultActionRunner.run()` invocation.
- `test_hint_fires_for_root_level_report`: changed `check-private-refs.sh`'s
  `git check-ignore -q postmortems` to `git check-ignore -q postmortems/`
  (trailing slash) — confirmed by direct git experiment that the no-slash
  form's exit code depends on the target's physical existence for a
  directory-only gitignore pattern, while the slash form matches regardless.
- `test_policy_builder_renders_byte_identically_to_golden_fixture`: added
  `.ll/design-tokens` to the gate's `copy_files` list
  (`verify_epic_branch_before_merge()`'s `setup_worktree()` call). This is
  the stopgap (Option a), not the durable fix (Option b, pinning the golden
  test to a checked-in fixture instead of ambient config) — left for a
  follow-up since it requires touching the test's own hermeticity, out of
  this issue's env/worktree-materialization scope.

`test_no_new_unverifiable_evidence` remains unexplained as a *gate-environment*
mechanism (no code-traced env/data divergence — see Root Cause), but while
verifying this fix, the full suite reproduced a failure in this exact test on
plain `python -m pytest`, unrelated to the gate: a stale evidence quote in
`.issues/enhancements/P5-ENH-1722-...md:61` (committed at 6281fa52a) cited
`_config_candidates(project_root, *, host, state_dir)` as a verbatim call
shape, but the real signature spans multiple lines with type annotations, so
the evidence-verification CLI's substring match never held. Fixed the quote to
name the function and describe its parameters in prose instead of a fake
verbatim call-shape quote. This resolves this specific occurrence but does not
confirm or refute the original single-observation CPU-contention-timeout
hypothesis for the gate itself — a stale-evidence-quote failure is a distinct,
real mechanism from a gate-environment artifact, and either can independently
make this test fail. No fix to `verify_epic_branch_before_merge()` itself was
identified or needed for this test.

Added 3 regression tests: `test_ll_python_scrubbed_from_child_env` and
`test_gitignored_design_tokens_dir_materialized_in_worktree` in
`test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge`, and
`test_hint_fires_when_ignored_dir_not_yet_materialized` in
`test_check_private_refs_hook.py` (verified this one fails without the fix,
via `git stash` of the one-line change, and passes with it).

## Status

**Open** | Created: 2026-08-31 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-09-01T02:39:58 - `396b8ad1-2bab-4820-a9f0-118d917e0c37.jsonl`
- `/ll:confidence-check` - 2026-09-01T02:16:55 - `9f6724ff-1c3f-4012-ac09-41f5ef9209f2.jsonl`
- `/ll:confidence-check` - 2026-09-01T00:59:38 - `3beed365-88e1-487d-84de-69cc4b78bd81.jsonl`
- `/ll:reconcile-issue` - 2026-09-01T00:49:29 - `b37471c4-ab88-4161-9264-ab74b2ba17db.jsonl`
- `/ll:refine-issue` - 2026-09-01T00:32:11 - `62ae4509-7f2b-4712-b3d4-4a2a89c6253f.jsonl`
- `/ll:reconcile-issue` - 2026-08-31T23:13:50 - `fabb1894-25ff-4052-aa2b-31f751e64151.jsonl`
- `/ll:format-issue` - 2026-08-31T23:13:12 - `fabb1894-25ff-4052-aa2b-31f751e64151.jsonl`
- `/ll:refine-issue` - 2026-08-31T23:07:36 - `138b65fa-2748-4f37-965e-8ace7ca774da.jsonl`
- pre-implementation review split from BUG-3368 - 2026-08-31
