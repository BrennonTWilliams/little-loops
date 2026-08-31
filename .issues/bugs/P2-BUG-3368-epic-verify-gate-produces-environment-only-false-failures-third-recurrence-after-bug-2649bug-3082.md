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
relates_to:
- BUG-2649
- BUG-3082
- BUG-3369
- BUG-3370
decision_needed: false
reconcile_attempted: true
confidence_score: 98
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
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

This bug did NOT actually block ENH-1718's merge in this run. The run's `epic_merge_verdict` was `held_open`, but that traces to a separate defect in the epic-merge `all_done` completion gate (EPIC-1463 has 5 cancelled children, which permanently blocks the `all_done` check regardless of verify outcome — filed as BUG-3369). The verify failure and the `held_open` verdict were coincidentally co-occurring, not causally linked, in this run. ENH-1718 was merged to main by hand (commit 6e158e703) after confirming the 6 failures were environment-only.

**Scope (narrowed 2026-08-31 pre-implementation review)**: this issue now covers only the 2 confirmed-mechanism tsc failures (the Option B quarantine, former Step 1). Diagnosis of the other 4 failures — observed once, mechanism unknown, possibly a flake — is split out to BUG-3370.

## Current Behavior

The epic-worktree verify gate runs the test suite inside a subprocess/worktree environment as part of epic-merge completion. That environment sometimes diverges from a direct clean-checkout test run, producing test failures that do not reflect real regressions in the commit under test. This has now happened three times (BUG-2649, BUG-3082, this bug), each from a different contamination vector.

## Expected Behavior

The verify gate's subprocess/worktree environment should reproduce the same test results as running the same tests directly on the same commit outside that environment. Environment-only failures should not block epic merges or require manual hand-merging.

## Motivation

This is the third recurrence of the same failure class. Each occurrence silently blocks automated epic merges, requires a human to manually confirm the failures are environment-only and hand-merge (as happened here with commit 6e158e703), and erodes trust in the verify gate as an automated safety check.

## Proposed Solution

Option B (selected below): quarantine `test_tsc_noemit_passes` (both `test_opencode_adapter.py` and `test_omp_adapter.py`) under the `LL_VERIFY_GATE=1` self-detection marker, per the BUG-2649→BUG-2650 precedent. The 4 remaining failures with unidentified mechanism are out of scope here — split to BUG-3370.

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

**Note**: this decision resolves only the 2 confirmed tsc failures. The other 4 failures (`test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, `test_policy_builder_renders_byte_identically_to_golden_fixture`) are tracked in BUG-3370 (reproduce-first, then diagnose) — out of scope for this issue.

## Integration Map

### Files to Modify
- `scripts/tests/test_opencode_adapter.py` / `scripts/tests/test_omp_adapter.py` — add a `LL_VERIFY_GATE=1` skipif quarantine on `test_tsc_noemit_passes` (Option B, selected), mirroring the `test_wiring_skills_and_commands.py` BUG-2649 precedent

### Dependent Files (Callers/Importers)
- `auto-refine-and-implement.yaml`'s `verify` state (line 449, unconditional) and `merge_epic_branch` state's fallback re-check (lines 610-807, only when the cached verdict/SHA is stale) — both call `verify_epic_branch_before_merge()`
- `scripts/little_loops/parallel/orchestrator.py`'s `ParallelOrchestrator._verify_epic_branch_before_merge` (lines 1514-1535) — third caller outside the FSM path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/spike/epic_verify_gate_doc_flake/repro_harness.py:16,114` — a fourth caller of `verify_epic_branch_before_merge()`, outside the FSM/orchestrator paths: a stress-repro harness built for the BUG-2649/BUG-2650 doc-flake investigation. Not touched by this fix, but confirms no other caller exists beyond the 3 already known.

### Similar Patterns
- BUG-2649's PYTHONPATH hermeticity regression tests and BUG-3082's LL_AUTOMATION env-scrub fix are the two prior fixes for this same failure class

### Tests
- Re-verify `test_tsc_noemit_passes` (`test_opencode_adapter.py`, `test_omp_adapter.py`) reports SKIPPED (not FAILED) under the gate after the quarantine lands. The 4 unresolved-mechanism tests are BUG-3370's scope.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_opencode_adapter.py:184-203` (`TestOpenCodeAdapterTypecheck.test_tsc_noemit_passes`) / `scripts/tests/test_omp_adapter.py:167-181` (`TestOmpAdapterTypecheck.test_tsc_noemit_passes`) — both modules already carry a module-level `pytestmark = pytest.mark.skipif(_BUN is None, ...)`; the new `LL_VERIFY_GATE` skip must be a second, additive function-level `@pytest.mark.skipif` decorator, not a replacement. Precedent for stacking two independent skipif marks on one function: `scripts/tests/test_fsm_persistence.py:2778-2785`.
- `scripts/tests/test_orchestrator.py:1782` (`class TestEpicBranchVerifyGate`) — indirect gate coverage that patches `setup_worktree`/`cleanup_worktree`/`subprocess.run` and drives the gate through `ParallelOrchestrator`, without calling `verify_epic_branch_before_merge` by name; unaffected by this fix but should be re-run to confirm.
- `scripts/tests/test_worktree_utils.py:1162-1183` (`test_verify_gate_marker_set_in_child_env`) — existing guard that `LL_VERIFY_GATE=1` reaches the child subprocess; not affected by adding a consumer of that marker, but is the test this fix's skip logic depends on staying green.
- (Guidance about `_CMD_RUN_ENV_VARS` diagnosis for the 4 unresolved failures moved to BUG-3370.)

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — documents the `LL_VERIFY_GATE` marker/idiom in prose (narrative section + a "**Behavior:**" bullet); BUG-2649's fix updated this same doc when the marker was introduced. Add a corroborating clause noting `test_tsc_noemit_passes` as a second consumer.
- `hooks/adapters/opencode/README.md` § Smoke Test — states the typecheck gate "runs as part of `python -m pytest scripts/tests/`"; add a caveat that it's skipped under `LL_VERIFY_GATE=1`.
- `hooks/adapters/omp/README.md` § Smoke Test — same sentence pattern, same caveat needed.
- `CHANGELOG.md` — add an entry under the current top `### Fixed` section, standalone-bullet format (not narrative-paragraph), mirroring `CHANGELOG.md:1437-1448`'s BUG-2650 entry exactly, per the decision's explicit instruction to follow that precedent's format.

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

- (none — this fix adds two `@pytest.mark.skipif` decorators; no new types)

### Signatures

- (none — no new functions; the fix is decorator-only. The `dump_verify_gate_env()` diagnostic helper formerly listed here belonged to the 4-failure diagnosis and now lives in BUG-3370 as explicitly temporary tooling.)

### Call Path

`verify_epic_branch_before_merge()` (`worktree_utils.py:571`) sets `LL_VERIFY_GATE=1` in the child env -> pytest collects `test_tsc_noemit_passes` in the gate subprocess -> new function-level `skipif(os.environ.get("LL_VERIFY_GATE") == "1")` fires -> test reports SKIPPED instead of FAILED

## Implementation Steps

1. Implement Option B (selected) for the 2 confirmed tsc failures: add a `LL_VERIFY_GATE=1` skipif quarantine on `test_tsc_noemit_passes` in `test_opencode_adapter.py`/`test_omp_adapter.py`, mirroring the `test_wiring_skills_and_commands.py` BUG-2649→BUG-2650 precedent (issue-cited comment, CHANGELOG entry, and a dedicated follow-up bug to track un-quarantine).

(Former Steps 2–4 — diagnosing and fixing the 4 unresolved failures — moved to BUG-3370, which adds a reproduce-first gate before any diagnosis.)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/API.md` — add `test_tsc_noemit_passes` as a second documented consumer of the `LL_VERIFY_GATE` marker idiom, alongside the existing narrative section and "**Behavior:**" bullet.
- Update `hooks/adapters/opencode/README.md` and `hooks/adapters/omp/README.md` § Smoke Test — caveat that the typecheck gate is skipped under `LL_VERIFY_GATE=1`.
- Update `CHANGELOG.md` — add a standalone `### Fixed` bullet mirroring the BUG-2650 entry format (`CHANGELOG.md:1437-1448`), under the current top version section.
- File a dedicated follow-up bug to track un-quarantine (BUG-2650 precedent): new issue with `relates_to: [BUG-3368]` in its own frontmatter; add a prose pointer to that new bug ID in this issue's eventual `## Resolution` section (no structured cross-reference field is used for this pattern elsewhere in the repo). Note: this is **distinct from BUG-3370** — 3370 tracks diagnosing the 4 unrelated failures; the un-quarantine bug tracks removing the tsc skipif once the missing-`node_modules` gap is otherwise resolved or the gate's scope is revisited.
- Add the new `LL_VERIFY_GATE`-keyed `@pytest.mark.skipif` as a second, function-level decorator stacked on `test_tsc_noemit_passes` in both `test_opencode_adapter.py` and `test_omp_adapter.py` — additive to the existing module-level `_BUN is None` skip, not a replacement.

## Impact

- **Priority**: P2 - third recurrence of a failure class that silently blocks automated epic merges and requires manual investigation/hand-merge every time it happens.
- **Effort**: Small — two stacked skipif decorators plus docs/CHANGELOG updates and filing one follow-up bug; the open-ended investigation was split to BUG-3370.
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

Root-caused for the 2 in-scope tsc failures (missing-dependency gap, see Codebase Research Findings below); unknown for the 4 out-of-scope failures (tracked in BUG-3370).

- **File**: `scripts/little_loops/worktree_utils.py` (`setup_worktree()` materializes only git-tracked content; `node_modules/` is gitignored and never installed)
- **Anchor**: `verify_epic_branch_before_merge()` / `setup_worktree()`
- **Cause**: All 6 tests pass on clean main in ~5.5s when run directly, outside the verify gate's worktree/subprocess environment. Commit d8e8b9ed1's diff (Codex adapter shell script, hooks.json entry, docs) is completely disjoint from all 6 failing tests' code paths. This is the third instance of the epic-worktree verify gate producing environment-only false failures, after BUG-2649 (PYTHONPATH injection non-hermeticity) and BUG-3082 (ambient LL_AUTOMATION leaking into the subprocess tree). Neither prior fix covers this new set of 6 tests, so a third, distinct contamination vector is implicated — the bun-types tsc failures specifically suggest a PATH or node-module-resolution difference specific to the verify gate's subprocess/worktree environment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Confirmed mechanism for 2 of the 6 failures** (`test_tsc_noemit_passes` in `test_opencode_adapter.py` and `test_omp_adapter.py`): a third, distinct contamination vector from BUG-2649 (PYTHONPATH) and BUG-3082 (LL_AUTOMATION) — a missing-dependency-install gap, not a PATH/env-var divergence. `setup_worktree()` (`scripts/little_loops/worktree_utils.py`) materializes the epic branch tip via `git worktree add`, which only checks out git-tracked content; `node_modules/` is gitignored (`.gitignore:29`) and is never installed by `verify_epic_branch_before_merge()` or any of its callers (repo-wide search for `bun install`/`npm install`/`npm ci` under `scripts/little_loops/` finds no install step anywhere in this code path). Each adapter's own `package.json` pins `@types/bun` as a `devDependency`, and each `tsconfig.json` sets `"types": ["bun"]` — so `tsc --noEmit` fails with "Cannot find type definition file for 'bun'" because `node_modules/@types/bun` was never materialized in the ephemeral worktree, while the `bun` binary itself resolves fine on the inherited `PATH` (confirmed: the tests reported `FAILED`, not the `skipif`-triggered `SKIPPED` that fires when `bun` isn't found on `PATH`).
- **Unresolved for the other 4 failures** (now tracked in BUG-3370): `test_recheck_set_folds_back_abandoned_residual`, `test_no_new_unverifiable_evidence`, `test_hint_fires_for_root_level_report`, and `test_policy_builder_renders_byte_identically_to_golden_fixture` do not share the missing-node_modules mechanism above. Traced but not conclusively root-caused: all four inherit the gate's full child env (`LL_VERIFY_GATE=1`, a reduced `PYTEST_XDIST_AUTO_NUM_WORKERS`, `LL_FUZZ=full`, a conditional `PYTHONPATH` prepend — built in `verify_epic_branch_before_merge()`, `worktree_utils.py:565-589`) with no per-test override; `test_hint_fires_for_root_level_report` specifically depends on `cwd`-relative `git check-ignore` behavior inside the ephemeral worktree path, which could differ from the main checkout. Ruled out: none of the four use Hypothesis (`@given`/`@settings`), so the gate's `LL_FUZZ=full` override is not implicated for these four specifically.
- No precedent exists for the issue's proposed `dump_verify_gate_env()` diagnostic helper — searched repo-wide; no existing subprocess-env capture/diff utility distinct from `project_child_env()` (`scripts/little_loops/host_runner.py:1853`, which builds env, not diffs it).

## Error Messages

The tsc failures were `Cannot find type definition file for 'bun'`.

## Environment

## Frequency

## Confidence Check Notes

**Verdict**: STOP — ADDRESS GAPS (Program Design Hard Override, ENH-2852/ENH-2967) | Readiness: 98/100 | Outcome Confidence: 84/100

### Gaps to Address
- `ll-issues check-design BUG-3368` fails: "Program Design: no signature-shaped line found in Types, Signatures, Call Path, or the section preamble." The section's Types/Signatures entries are prose stating "(none — ... decorator-only)" rather than a signature-shaped line, so the linter finds nothing to anchor on even though the Call Path line does name `verify_epic_branch_before_merge()`. Remedy: since this fix genuinely adds no new types or functions (two stacked `@pytest.mark.skipif` decorators only), set `program_design_not_applicable: true` in this issue's frontmatter rather than fabricating a signature — this is the skill's documented remedy path for genuinely trivial work.

### Outcome Risk Factors (informational, non-blocking — outcome confidence 84 clears the 65 threshold)
- `format-check`'s `unapplied_decision` check flags `verify_epic_branch_before_merge()` in Program Design as a "rejected option" identifier. This reads as a linter false-positive — that function is the shared gate entry point referenced by both Option A and Option B (not something Option B rejected) — but is worth a quick sanity check before implementation since it capped Criterion C (Ambiguity) in this scoring pass.

## Session Log
- `/ll:confidence-check` - 2026-08-31T22:31:20 - `a1600312-93ed-46f3-9d4c-f81445a303c2.jsonl`
- `/ll:wire-issue` - 2026-08-31T22:11:27 - `c4a9442e-319b-44f7-a243-d71188c2e525.jsonl`
- `/ll:decide-issue` - 2026-08-31T22:02:05 - `37ee9921-5737-4ac0-9e3a-27926a3278f3.jsonl`
- `/ll:reconcile-issue` - 2026-08-31T21:55:00 - `10ac5aa7-c8d4-4c48-94b7-5c6942cffbd5.jsonl`
- `/ll:refine-issue` - 2026-08-31T21:40:31 - `a39b473b-2472-40a4-90ee-2531e40475f9.jsonl`
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:00 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`
