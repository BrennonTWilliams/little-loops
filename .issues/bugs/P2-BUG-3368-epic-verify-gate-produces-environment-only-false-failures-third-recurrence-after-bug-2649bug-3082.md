---
id: BUG-3368
type: BUG
title: "Epic verify gate produces environment-only false failures \u2014 third recurrence\
  \ after BUG-2649/BUG-3082"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-31'
captured_at: '2026-08-31T21:18:18Z'
relates_to: [BUG-2649, BUG-3082]
decision_needed: false
reconcile_attempted: true
---

# BUG-3368: Epic verify gate produces environment-only false failures — third recurrence after BUG-2649/BUG-3082

## Summary

During `ll-loop run sprint-refine-and-implement EPIC-1463` (run dir `.loops/runs/sprint-refine-and-implement-20260831T135628/`), the epic-worktree verify gate reported 6 test failures on commit d8e8b9ed1 (ENH-1718, Codex PreToolUse adapter parity — see verify-detail.txt, verify-returncode.txt, summary.json):

- test_recheck_set_folds_back_abandoned_residual (scripts/tests/test_builtin_loops.py)
- test_no_new_unverifiable_evidence (scripts/tests/test_verify_evidence.py)
- test_hint_fires_for_root_level_report (scripts/tests/test_check_private_refs_hook.py)
- test_policy_builder_renders_byte_identically_to_golden_fixture (scripts/tests/test_enh3035_artifact_template_kit.py)
- test_tsc_noemit_passes (scripts/tests/test_opencode_adapter.py)
- test_tsc_noemit_passes (scripts/tests/test_omp_adapter.py)

The tsc failures were `Cannot find type definition file for 'bun'`.

## Note for triage

This bug did NOT actually block ENH-1718's merge in this run. The run's `epic_merge_verdict` was `held_open`, but that traces to a separate defect in the epic-merge `all_done` completion gate (EPIC-1463 has 5 cancelled children, which permanently blocks the `all_done` check regardless of verify outcome — filed separately). The verify failure and the `held_open` verdict were coincidentally co-occurring, not causally linked, in this run. ENH-1718 was merged to main by hand (commit 6e158e703) after confirming the 6 failures were environment-only.

## Current Behavior

The epic-worktree verify gate runs the test suite inside a subprocess/worktree environment as part of epic-merge completion. That environment sometimes diverges from a direct clean-checkout test run, producing test failures that do not reflect real regressions in the commit under test. This has now happened three times (BUG-2649, BUG-3082, this bug), each from a different contamination vector.

## Expected Behavior

The verify gate's subprocess/worktree environment should reproduce the same test results as running the same tests directly on the same commit outside that environment. Environment-only failures should not block epic merges or require manual hand-merging.

## Motivation

This is the third recurrence of the same failure class. Each occurrence silently blocks automated epic merges, requires a human to manually confirm the failures are environment-only and hand-merge (as happened here with commit 6e158e703), and erodes trust in the verify gate as an automated safety check.

## Proposed Solution

TBD — root cause is unidentified (see Root Cause below). Once found, the fix should follow the established pattern from BUG-2649 (hermeticity regression test + scrubbing the offending environment difference) and BUG-3082 (scrub the leaking variable in `scripts/tests/conftest.py`'s env-scrub list): diagnose the concrete environment divergence first (see Implementation Steps), then scrub/normalize it at the source and add a regression test.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

**Option A**: Add a dependency-materialization step (e.g. `bun install`) to the verify gate's worktree setup (`setup_worktree()` / `verify_epic_branch_before_merge()`, `scripts/little_loops/worktree_utils.py`) so `node_modules/@types/bun` exists before `tsc --noEmit` runs — matching Expected Behavior's goal that the gate's environment should reproduce a direct clean-checkout run. This only closes the gap for the 2 tsc failures; the other 4 remain unexplained and need separate diagnosis.

**Option B**: Quarantine the two `test_tsc_noemit_passes` tests under the gate via the established `LL_VERIFY_GATE=1` self-detection marker (the same idiom previously used for `test_wiring_skills_and_commands.py`'s BUG-2649 quarantine), on the grounds that an ephemeral `git worktree add` checkout never has locally-installed JS dependencies for *any* fresh clone, not just under this gate — so this may not be an "environment-only false failure" of the BUG-2649/BUG-3082 kind (an env-var leak), but an inherent limitation of type-checking a JS toolchain from a git-tracked-only worktree.

> **Selected:** Option B — quarantine via `LL_VERIFY_GATE=1`, per the BUG-2649/BUG-2650 precedent; zero codebase precedent exists for an automated dependency-install step in worktree/CI/gate code, and Option A would introduce a network-dependent, non-hermetic step into a gate whose only prior fixes were pure env-scrubbing.

**Recommended**: Undetermined from the code alone — the choice depends on whether the epic-worktree verify gate is meant to fully mirror a real CI/dev checkout (favoring Option A) or only to catch regressions in git-tracked source (favoring Option B, since JS type-checking was never truly hermetic across any fresh checkout). This is a scope decision, not something derivable from research.

### Decision Rationale

**Selected**: Option B — quarantine `test_tsc_noemit_passes` (both `test_opencode_adapter.py` and `test_omp_adapter.py`) under `LL_VERIFY_GATE=1`, mirroring the `test_wiring_skills_and_commands.py` BUG-2649→BUG-2650 lifecycle (add with issue-cited comment + CHANGELOG entry, file a dedicated follow-up bug to track un-quarantine, remove once independently root-caused/fixed).

**Reasoning**: A parallel codebase-evidence pass for each option found zero precedent anywhere in `scripts/little_loops/` — worktree setup, CI (`.github/workflows/ci.yml`), or any gate code — for an automated `bun install`/`npm install`/`npm ci` step; the only place dependency install is discussed automation-adjacent (BUG-2922) treats it as a manual, human-supervised, network-risk-flagged action, not something safe to embed unattended in a merge gate. Both prior fixes for this exact failure class (BUG-2649, BUG-3082) were pure environment-scrubbing with no new external calls or network dependencies — Option A breaks that pattern, while Option B extends it using a marker (`LL_VERIFY_GATE=1`) already set unconditionally at `worktree_utils.py:571` for precisely this self-quarantine purpose, with a directly transplantable one-precedent lifecycle to follow.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — `bun install` step | 0 | 1 | 1 | 0 | 2/12 |
| B — quarantine via `LL_VERIFY_GATE=1` | 3 | 3 | 3 | 2 | 11/12 |

**Key evidence**: `worktree_utils.py:571` sets `LL_VERIFY_GATE=1` unconditionally in the gate's child env; the removed `test_wiring_skills_and_commands.py:322-330` quarantine (BUG-2649→BUG-2650) is the direct precedent to mirror; `test_verify_gate_marker_set_in_child_env` (`test_worktree_utils.py:1162-1183`) is the existing regression test asserting the marker reaches the child subprocess. Both target files already carry an orthogonal module-level `pytestmark = pytest.mark.skipif(_BUN is None, ...)` (bun-on-PATH check) — the new `LL_VERIFY_GATE`-aware skip must be additive (function-level on `test_tsc_noemit_passes`), not a replacement. No tooling enforces un-quarantine, so implementation must file a dedicated follow-up bug (BUG-2650 pattern) to track removal once the missing-`node_modules` gap is otherwise resolved or the gate's scope is revisited.

**Note**: this decision resolves only the 2 confirmed tsc failures (Implementation Step 1). The other 4 failures (`test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, `test_policy_builder_renders_byte_identically_to_golden_fixture`) remain unresolved and require separate diagnosis per Implementation Step 2.

## Integration Map

### Files to Modify
- `scripts/tests/test_opencode_adapter.py` / `scripts/tests/test_omp_adapter.py` — add a `LL_VERIFY_GATE=1` skipif quarantine on `test_tsc_noemit_passes` (Option B, selected), mirroring the `test_wiring_skills_and_commands.py` BUG-2649 precedent
- `scripts/tests/conftest.py` — env-scrub list (`_CMD_RUN_ENV_VARS`, BUG-3082 pattern), if the remaining 4 unresolved failures trace to an inherited env var

### Dependent Files (Callers/Importers)
- `auto-refine-and-implement.yaml`'s `verify` state (line 449, unconditional) and `merge_epic_branch` state's fallback re-check (lines 610-807, only when the cached verdict/SHA is stale) — both call `verify_epic_branch_before_merge()`
- `scripts/little_loops/parallel/orchestrator.py`'s `ParallelOrchestrator._verify_epic_branch_before_merge` (lines 1514-1535) — third caller outside the FSM path

### Similar Patterns
- BUG-2649's PYTHONPATH hermeticity regression tests and BUG-3082's LL_AUTOMATION env-scrub fix are the two prior fixes for this same failure class

### Tests
- New regression test(s) for each fixed contamination vector, mirroring `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge` (BUG-2649 pattern) or `scripts/tests/test_hook_session_start.py:667-718` (BUG-3082 pattern)
- Re-verify the 6 originally-failing tests pass under the gate: `test_tsc_noemit_passes` (`test_opencode_adapter.py`, `test_omp_adapter.py` — confirmed mechanism) and `test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, `test_policy_builder_renders_byte_identically_to_golden_fixture` (unresolved mechanism)

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- The verify gate's subprocess/worktree environment is assembled in exactly one place: `verify_epic_branch_before_merge()` (`scripts/little_loops/worktree_utils.py:481-608`), called from both the `verify` state (`auto-refine-and-implement.yaml:449`, unconditional) and the `merge_epic_branch` state's fallback re-check (`auto-refine-and-implement.yaml:610-807`, only when the cached verdict/SHA is stale). A third caller exists outside the FSM path: `ParallelOrchestrator._verify_epic_branch_before_merge` (`scripts/little_loops/parallel/orchestrator.py:1514-1535`).
- `project_child_env()` (`scripts/little_loops/host_runner.py:1853-1883`) is the chokepoint every subprocess call in this path routes through — default behavior is `os.environ.copy()` merged with caller-supplied `extra`; per its own docstring it provides no way to clear or deny an inherited variable (tracked separately as ENH-3203).
- Established convention for hermeticity fixes in this codebase (both BUG-2649 and BUG-3082): each pairs (a) a scrub/normalize of the diverging value at its source with (b) a dedicated regression test that deliberately re-creates the contaminated condition and asserts it no longer breaks. BUG-2649's fix lives in production code (`worktree_utils.py`'s own env-build, guarded `PYTHONPATH` prepend at lines 583-589) with tests in `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge`. BUG-3082's fix lives in test infrastructure (`scripts/tests/conftest.py:1060-1078`'s `_CMD_RUN_ENV_VARS` allowlist + autouse `_restore_cmd_run_env_vars` fixture) with a regression test in `scripts/tests/test_hook_session_start.py:667-718` that re-spawns the suite as a subprocess under a deliberately-set ambient var. Neither prior fix's scrub list touches `PATH`, `node_modules`, or bun/node toolchain resolution.
- Established fallback when a gate-sensitive test's non-determinism can't be root-caused: quarantine via the `LL_VERIFY_GATE=1` self-detection marker (set unconditionally in `verify_epic_branch_before_merge()`, `worktree_utils.py:571`) rather than a scrub — e.g. `test_wiring_skills_and_commands.py`'s prior `skipif(os.environ.get("LL_VERIFY_GATE") == "1")` guard (later removed under BUG-2650 once that test's flake was independently proven deterministic).

## Program Design

### Types

- (none yet — root cause unidentified; see Implementation Steps)

### Signatures

- `dump_verify_gate_env() -> dict[str, str]` — diagnostic helper added temporarily to the verify-gate subprocess invocation to capture `PATH`, node/bun toolchain resolution, `PYTHONPATH`, and other env vars for comparison against a direct clean-checkout run

### Call Path

`merge_epic_branch` (epic-worktree verify gate, `scripts/little_loops/loops/auto-refine-and-implement.yaml`) -> `dump_verify_gate_env()` -> diff against direct `python -m pytest scripts/tests/` on a clean checkout of the same commit

## Implementation Steps

1. Implement Option B (selected) for the 2 confirmed tsc failures: add a `LL_VERIFY_GATE=1` skipif quarantine on `test_tsc_noemit_passes` in `test_opencode_adapter.py`/`test_omp_adapter.py`, mirroring the `test_wiring_skills_and_commands.py` BUG-2649→BUG-2650 precedent (issue-cited comment, CHANGELOG entry, and a dedicated follow-up bug to track un-quarantine).
2. Diagnose the remaining 4 failures (`test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, `test_policy_builder_renders_byte_identically_to_golden_fixture`), which do not share the missing-node_modules mechanism — investigate the gate's full child env build (`verify_epic_branch_before_merge()`, `worktree_utils.py:565-589`), and for `test_hint_fires_for_root_level_report` specifically, cwd-relative `git check-ignore` behavior inside the ephemeral worktree path.
3. Fix each identified contamination vector at the source (scrub/normalize the diverging env value, or the chosen tsc fix), following the BUG-2649/BUG-3082 pattern.
4. Add a hermeticity regression test asserting each contamination vector stays fixed, mirroring the existing BUG-2649/BUG-3082 tests.

## Impact

- **Priority**: P2 - third recurrence of a failure class that silently blocks automated epic merges and requires manual investigation/hand-merge every time it happens.
- **Effort**: Medium - investigation-heavy since the root cause is unidentified; the fix itself is likely small once found, per the BUG-2649/BUG-3082 precedent.
- **Risk**: Low - the fix targets test/gate infrastructure, not production code paths.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-31 | Priority: P2

## Steps to Reproduce

1. Run `ll-loop run sprint-refine-and-implement EPIC-1463` (or any epic run whose verify gate covers commit d8e8b9ed1 / ENH-1718).
2. Observe the epic-worktree verify gate report the 6 test failures listed in Summary (see `verify-detail.txt`, `verify-returncode.txt`, `summary.json` under the run's `.loops/runs/sprint-refine-and-implement-20260831T135628/` directory).
3. Run the same 6 tests directly on a clean checkout of the same commit (e.g. `python -m pytest scripts/tests/`) and observe they pass in ~5.5s — confirming the failures are environment-only, not real regressions.

## Root Cause

Unknown — this is a false-failure report, not yet root-caused.

- **File**: Unknown — see Implementation Steps for the diagnostic plan
- **Anchor**: N/A (root cause not yet identified)
- **Cause**: All 6 tests pass on clean main in ~5.5s when run directly, outside the verify gate's worktree/subprocess environment. Commit d8e8b9ed1's diff (Codex adapter shell script, hooks.json entry, docs) is completely disjoint from all 6 failing tests' code paths. This is the third instance of the epic-worktree verify gate producing environment-only false failures, after BUG-2649 (PYTHONPATH injection non-hermeticity) and BUG-3082 (ambient LL_AUTOMATION leaking into the subprocess tree). Neither prior fix covers this new set of 6 tests, so a third, distinct contamination vector is implicated — the bun-types tsc failures specifically suggest a PATH or node-module-resolution difference specific to the verify gate's subprocess/worktree environment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Confirmed mechanism for 2 of the 6 failures** (`test_tsc_noemit_passes` in `test_opencode_adapter.py` and `test_omp_adapter.py`): a third, distinct contamination vector from BUG-2649 (PYTHONPATH) and BUG-3082 (LL_AUTOMATION) — a missing-dependency-install gap, not a PATH/env-var divergence. `setup_worktree()` (`scripts/little_loops/worktree_utils.py`) materializes the epic branch tip via `git worktree add`, which only checks out git-tracked content; `node_modules/` is gitignored (`.gitignore:29`) and is never installed by `verify_epic_branch_before_merge()` or any of its callers (repo-wide search for `bun install`/`npm install`/`npm ci` under `scripts/little_loops/` finds no install step anywhere in this code path). Each adapter's own `package.json` pins `@types/bun` as a `devDependency`, and each `tsconfig.json` sets `"types": ["bun"]` — so `tsc --noEmit` fails with "Cannot find type definition file for 'bun'" because `node_modules/@types/bun` was never materialized in the ephemeral worktree, while the `bun` binary itself resolves fine on the inherited `PATH` (confirmed: the tests reported `FAILED`, not the `skipif`-triggered `SKIPPED` that fires when `bun` isn't found on `PATH`).
- **Unresolved for the other 4 failures**: `test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, and `test_policy_builder_renders_byte_identically_to_golden_fixture` do not share the missing-node_modules mechanism above. Traced but not conclusively root-caused: all four inherit the gate's full child env (`LL_VERIFY_GATE=1`, a reduced `PYTEST_XDIST_AUTO_NUM_WORKERS`, `LL_FUZZ=full`, a conditional `PYTHONPATH` prepend — built in `verify_epic_branch_before_merge()`, `worktree_utils.py:565-589`) with no per-test override; `test_hint_fires_for_root_level_report` specifically depends on `cwd`-relative `git check-ignore` behavior inside the ephemeral worktree path, which could differ from the main checkout. Ruled out: none of the four use Hypothesis (`@given`/`@settings`), so the gate's `LL_FUZZ=full` override is not implicated for these four specifically.
- No precedent exists for the issue's proposed `dump_verify_gate_env()` diagnostic helper — searched repo-wide; no existing subprocess-env capture/diff utility distinct from `project_child_env()` (`scripts/little_loops/host_runner.py:1853`, which builds env, not diffs it).

## Error Messages

The tsc failures were `Cannot find type definition file for 'bun'`.

## Environment

## Frequency

## Session Log
- `/ll:decide-issue` - 2026-08-31T22:02:05 - `37ee9921-5737-4ac0-9e3a-27926a3278f3.jsonl`
- `/ll:reconcile-issue` - 2026-08-31T21:55:00 - `10ac5aa7-c8d4-4c48-94b7-5c6942cffbd5.jsonl`
- `/ll:refine-issue` - 2026-08-31T21:40:31 - `a39b473b-2472-40a4-90ee-2531e40475f9.jsonl`
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:00 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`
