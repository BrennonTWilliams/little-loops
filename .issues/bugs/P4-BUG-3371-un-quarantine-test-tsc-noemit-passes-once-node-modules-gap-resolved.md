---
id: BUG-3371
type: BUG
title: "Un-quarantine test_tsc_noemit_passes once the verify gate's node_modules gap is resolved"
priority: P4
status: cancelled
cancelled_reason: "Option B chosen: the epic-worktree verify gate's scope deliberately excludes JS/TS type-checking of worktree checkouts. Materializing node_modules (Option A) was already rejected in BUG-3368's decision record (novel network-dependent, non-hermetic step with zero gate-code precedent), and no concrete driver emerged. The tsc --noEmit assertion remains fully exercised by the standard `python -m pytest scripts/tests/` run off the gate, so coverage is unchanged; the LL_VERIFY_GATE skipif quarantine is now permanent by design."
discovered_by: manage-issue
discovered_date: '2026-08-31'
relates_to:
- BUG-3368
decision_needed: false
program_design_not_applicable: true
---

# BUG-3371: Un-quarantine `test_tsc_noemit_passes` once the verify gate's node_modules gap is resolved

## Summary

BUG-3368 quarantined `test_tsc_noemit_passes` (`scripts/tests/test_opencode_adapter.py`
and `scripts/tests/test_omp_adapter.py`) under the `LL_VERIFY_GATE=1` self-detection
marker, because the epic-worktree verify gate's ephemeral `git worktree add` checkout
only materializes git-tracked content — the gitignored `node_modules/@types/bun`
devDependency is never installed there, so `tsc --noEmit` fails on a missing type
definition regardless of the commit under test.

This mirrors the BUG-2649→BUG-2650 lifecycle: quarantine now, track removal once the
underlying gap is closed (or the gate's scope is deliberately revisited).

## Current Behavior

`test_tsc_noemit_passes` in both files carries a permanent
`@pytest.mark.skipif(os.environ.get("LL_VERIFY_GATE") == "1", ...)` decorator, so it
never runs the real `tsc --noEmit` check under the gate. No tooling enforces
un-quarantine — this bug is the only tracking mechanism.

## Steps to Reproduce

1. Run the verify gate against a worktree checkout with `LL_VERIFY_GATE=1` set:
   `LL_VERIFY_GATE=1 python -m pytest scripts/tests/test_opencode_adapter.py::test_tsc_noemit_passes scripts/tests/test_omp_adapter.py::test_tsc_noemit_passes -v`
2. Observe both tests are skipped (the `skipif` quarantine from BUG-3368 fires),
   confirming the gate never exercises the real `tsc --noEmit` check.
3. To see the underlying gap directly: run `git worktree add` for the same commit,
   then `tsc --noEmit` inside that worktree without first installing
   `node_modules` — it fails on the missing `@types/bun` devDependency, which is
   why the skip exists.

## Expected Behavior

Either:
- The verify gate's worktree setup materializes `node_modules` (e.g. a `bun install`
  step) before running tests, making the quarantine unnecessary and this skipif
  removable, or
- The gate's scope is deliberately redefined to exclude JS/TS type-checking from
  worktree-based verification, and this bug is closed as won't-fix with that
  rationale recorded.

## Proposed Solution

Revisit once there is a concrete driver (e.g. another false-negative from Option A's
absence, or a deliberate decision to make the gate hermetic for JS toolchains).
Not urgent — filed per BUG-2650 precedent to keep the quarantine auditable, not
because removal is expected soon.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- A formal decision record already exists rejecting Option A: `.ll/decisions.d/509372bd-43b5-4997-abf8-5dc1337a293c.json` (from BUG-3368, 2026-08-31) scored Option A 2/12 vs. Option B 11/12 across Consistency/Simplicity/Testability/Risk axes, citing "zero codebase precedent for automated dependency-install steps in worktree/CI/gate code." Reopening Option A means overturning that decision, not merely supplying new information — no `bun install`/`npm install`/`npm ci` step exists anywhere in `scripts/little_loops/` gate/worktree/CI code today (confirmed repo-wide).
- The precedent this issue cites (BUG-2649→BUG-2650) was resolved as an active code fix within roughly a day of the quarantine landing: root cause was determined deterministic, proven via a 60x stress-repro harness, the `skipif` was deleted, and a permanent regression test was added (`test_gate_read_is_deterministic_on_present_needle` in `test_worktree_utils.py`). That precedent is not an example of indefinite deferral — it is the opposite outcome (a same-cycle un-quarantine). Noted so a future reader doesn't read "mirrors BUG-2649→BUG-2650" as implying comparable resolution speed for this P4, deliberately-not-urgent tracking bug.
- If this issue is ever closed won't-fix instead (Option B's alternate resolution — permanently redefine gate scope), this codebase's convention for that closure shape is `status: cancelled` + a `cancelled_reason:` frontmatter field (e.g. `.issues/enhancements/P3-ENH-2582-analytics-auto-collect-opt-in-background-summarization.md`), not a `## Resolution` narrative alone.

## Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/worktree_utils.py:388` — `setup_prepatch_worktree()` calls `setup_worktree()`
- `scripts/little_loops/worktree_utils.py:551` — `verify_epic_branch_before_merge()` calls `setup_worktree()` (the epic-worktree verify gate itself)
- `scripts/little_loops/worktree_utils.py:841` — `ensure_epic_branch()` calls `setup_worktree()`
- `scripts/tests/test_worktree_utils.py` — multiple existing tests call `setup_worktree()` directly (`:148,168,189,225,248,271,294,330,367,412`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:1036` — `FSMExecutor` calls `worktree_utils.setup_worktree()` directly for the ENH-2609 per-state `worktree:` sub-loop attach path
- `scripts/little_loops/parallel/worker_pool.py:808-828` — `WorkerPool._setup_worktree()` wraps `setup_worktree()` for `ll-parallel`'s per-issue worktree creation
- `scripts/little_loops/parallel/orchestrator.py:47-52,1502-1528` — `ParallelOrchestrator._verify_epic_branch_before_merge()` wraps `verify_epic_branch_before_merge()`
- `scripts/little_loops/cli/loop/run.py:451,480` — `ll-loop run --worktree` calls `setup_worktree()` directly
- `scripts/little_loops/prepatch_check.py:31,446` — calls `setup_prepatch_worktree()` (one level removed from `setup_worktree()`)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:218,525,542,738` — inline FSM shell-action blocks import `worktree_utils` symbols directly

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_worktree.py::TestSetupWorktree` (12 call sites: `:68,97,125,159,192,222,253,280,310,343,380,413`) — direct unit coverage of `setup_worktree()`, distinct from `test_worktree_utils.py`'s 10 sites
- `scripts/tests/test_worktree_concurrency.py::TestWorktreeConcurrency` (`:66`, `pytest.mark.integration`) — real-git multi-threaded regression guard exercising the actual `git worktree add` checkout step
- `scripts/tests/test_orchestrator.py:1787-1947` — patches `little_loops.worktree_utils.setup_worktree` and exercises `_verify_epic_branch_before_merge`
- `scripts/tests/test_test_tamper_guard.py:333,342,356` — calls `setup_prepatch_worktree()` / `cleanup_worktree()`
- `scripts/tests/test_worktree_utils.py::TestVerifyEpicBranchBeforeMerge::test_verify_gate_marker_set_in_child_env:1162-1183` — asserts `LL_VERIFY_GATE=1` propagates into the gate's child env, the exact mechanism this issue's quarantine decorator relies on

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/WORKTREES.md` — the primary reference doc for `setup_worktree()`'s copy-semantics contract; its "## Verify-gate exception" section (`:26-32`) documents `verify_epic_branch_before_merge()`'s `copy_files=[]` call
- `docs/reference/EVENT-SCHEMA.md` (`sub_loop_worktree_attached` `:778`, `sub_loop_worktree_error` `:810`) — events tied to `setup_worktree()`'s success/failure outcome on the FSM sub-loop path
- `docs/ARCHITECTURE.md:462-473` — describes the `merge_epic_branch` FSM state and the free functions it calls
- `docs/development/MERGE-COORDINATOR.md:147-167` — fullest prose description of `verify_epic_branch_before_merge()`'s routing logic
- `docs/reference/HOST_COMPATIBILITY.md:589` — documents `setup_worktree()` exporting `LL_HISTORY_DB` into the orchestrator's own env (BUG-3112)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **Files to Modify (none planned by this issue — deferred; listed as the surface a future resolution would touch)**: if Option A is ever revisited, `scripts/little_loops/worktree_utils.py` (`setup_worktree()` `:160-281`, `verify_epic_branch_before_merge()` `:481-610`); either option requires removing the `skipif` decorators in `scripts/tests/test_opencode_adapter.py:192-215` and `scripts/tests/test_omp_adapter.py:170-192`.
- **Conventions in Force**: the `LL_VERIFY_GATE` self-detection marker idiom mirrors the `LL_NON_INTERACTIVE` marker idiom (`host_runner.py`/`session_start.py`) — evidence: `worktree_utils.py:565-571` comment.
- **Conventions in Force**: this codebase's quarantine-then-track lifecycle files the quarantine and its removal-tracking as two separate, cross-referenced issues (never one issue reopened) — evidence: BUG-2649 (quarantine) / BUG-2650 (removal), linked via prose in BUG-2649's `## Resolution`, not a structured field.
- **Tests**: `scripts/tests/test_worktree_utils.py` already exercises `setup_worktree()` directly at 10 call sites (e.g. `:148,168,189,225,248,271,294,330,367,412`) — any future change to `setup_worktree()` should extend this file's coverage rather than adding a new test module.
- **Documentation**: `docs/reference/API.md:4023-4038`, `hooks/adapters/opencode/README.md`, `hooks/adapters/omp/README.md`, and `CHANGELOG.md` (`## [1.160.0]`) already document the quarantine (added by BUG-3368) and would need a follow-up entry when un-quarantined.
- **Configuration**: `hooks/adapters/opencode/package.json` and `scripts/little_loops/hooks/adapters/omp/package.json` each declare exactly 1 runtime dependency + 1 devDependency (`@types/bun`) — minimal install scope if Option A were ever implemented, though no install-time cost is measured anywhere in the repo.

## Impact

- **Priority**: P4 — tracking-only; no active harm while quarantined.
- **Effort**: Unknown — depends on which resolution path is chosen.
- **Risk**: Low.

## Status

**Cancelled** (won't-fix, Option B) | Created: 2026-08-31 | Cancelled: 2026-08-31 | Priority: P4

## Resolution

Closed won't-fix per Option B: the verify gate's scope is deliberately redefined to
exclude JS/TS type-checking of ephemeral worktree checkouts. Rationale:

- BUG-3368's decision record (`.ll/decisions.d/509372bd-43b5-4997-abf8-5dc1337a293c.json`)
  already rejected the dependency-install path (Option A) as a novel network-dependent,
  non-hermetic step with zero precedent in gate/worktree/CI code.
- No concrete driver (e.g. a false negative traceable to the missing gate coverage)
  materialized after the quarantine landed.
- Coverage is unchanged in practice: `test_tsc_noemit_passes` still runs the real
  `tsc --noEmit` check in every standard `python -m pytest scripts/tests/` run
  wherever Bun is available — only the gate's worktree run skips it.

The `LL_VERIFY_GATE=1` skipif decorators in `scripts/tests/test_opencode_adapter.py`
and `scripts/tests/test_omp_adapter.py` are permanent by design; their reason strings
point here for the rationale. A hermetic alternative (vendoring a minimal git-tracked
`@types/bun` stub or a gate-specific tsconfig) was noted but not pursued — file a new
issue against this one if gate-side type-check coverage is ever actually needed.


## Session Log
- `/ll:wire-issue` - 2026-09-01T02:40:09 - `396b8ad1-2bab-4820-a9f0-118d917e0c37.jsonl`
- `/ll:refine-issue` - 2026-09-01T02:25:22 - `db36f084-b57f-4f2f-9793-def924e148e3.jsonl`
- `/ll:format-issue` - 2026-09-01T02:11:59 - `d8c43b11-c63e-40e3-b48e-79de7f7bd724.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **File**: `scripts/little_loops/worktree_utils.py`
- **Anchor**: `setup_worktree()` (`:160-281`) — performs only `git worktree add`/`git worktree add -b`, a git-identity copy, a `.claude/` copytree, and a caller-supplied `copy_files` copy loop. No subprocess call in this function materializes any package-manager dependency; `copy_files` only copies paths that already exist in `repo_path`, and the gitignored `node_modules` tree never exists there either (`.gitignore:29`).
- **Anchor**: `verify_epic_branch_before_merge()` (`:481-610`) — the epic-worktree verify gate itself. Sets `LL_VERIFY_GATE=1` unconditionally via `project_child_env(extra={"LL_VERIFY_GATE": "1"})` at `:571`, then runs the project's test/lint commands against the worktree at `:592-602`.
- **Cause**: No hook point exists inside `setup_worktree()` for injecting a post-checkout install step. The only place such a step could be added is by wrapping the `setup_worktree()` call at each caller site (`verify_epic_branch_before_merge` `:551-559`, `setup_prepatch_worktree` `:388`, `ensure_epic_branch` `:841`) — none of which do this today. Confirmed repo-wide: no `bun install`/`npm install`/`npm ci` step exists anywhere in `scripts/little_loops/` gate/worktree/CI code.
