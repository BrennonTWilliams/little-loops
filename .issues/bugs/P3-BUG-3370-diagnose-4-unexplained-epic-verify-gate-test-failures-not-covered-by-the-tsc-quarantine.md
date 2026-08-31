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

## Program Design

### Types

- (none — diagnosis issue; production types TBD once a mechanism is identified)

### Signatures

- `dump_verify_gate_env() -> dict[str, str]` — **temporary diagnostic helper** (Step 2 only, removed before close): capture `PATH`, node/bun toolchain resolution, `PYTHONPATH`, cwd, and remaining env vars from inside the verify-gate subprocess for comparison against a direct clean-checkout run.

### Call Path

`merge_epic_branch` (epic-worktree verify gate, `scripts/little_loops/loops/auto-refine-and-implement.yaml`) -> `verify_epic_branch_before_merge()` (`worktree_utils.py:481-608`) -> `dump_verify_gate_env()` -> diff against direct `python -m pytest scripts/tests/` on a clean checkout of the same commit

## Implementation Steps

1. **Reproduce first**: re-run the verify gate on commit d8e8b9ed1 (or current main) 2–3 times, serially (no concurrent gates), and record whether any of the 4 failures recur. If none reproduce, close this issue as a flake (likely concurrent-run interference — e.g. scratch-file collision) with the evidence recorded; steps 2–4 evaporate.
2. If reproducible: diagnose via the temporary `dump_verify_gate_env()` diff, plus for `test_hint_fires_for_root_level_report` specifically, cwd-relative `git check-ignore` behavior inside the ephemeral worktree path.
3. Fix each identified contamination vector at the source (scrub/normalize the diverging env value), following the BUG-2649/BUG-3082 pattern — BUG-2649's fix lives in `worktree_utils.py`'s env build; BUG-3082's lives in `scripts/tests/conftest.py:1060-1078`'s `_CMD_RUN_ENV_VARS` allowlist. Note that list is suite-wide (autouse, not gated on `LL_VERIFY_GATE`) — adding a var there scrubs it for the entire suite.
4. Add a hermeticity regression test per fixed vector, mirroring `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (BUG-2649 pattern) or `scripts/tests/test_hook_session_start.py:667-718` (BUG-3082 pattern: re-spawn the suite as a subprocess with the contaminated condition deliberately set, assert exit 0).

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

## Status

**Open** | Created: 2026-08-31 | Priority: P3

## Session Log
- pre-implementation review split from BUG-3368 - 2026-08-31
