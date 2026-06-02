---
id: FEAT-1789
title: parallel-safe autodev for disjoint issues
type: FEAT
status: done
priority: P3
captured_at: '2026-05-29T18:45:00Z'
completed_at: '2026-05-31T03:16:06Z'
labels:
- autodev
- ll-loop
- concurrency
- feature
depends_on: ENH-1787
decision_needed: false
relates_to:
- BUG-1760
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1789: parallel-safe autodev for disjoint issues

## Summary

Currently autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. Autodev's refinement phase (format, refine, wire, confidence-check) is mostly read-only per-issue and writes only to disjoint issue files. With per-instance temp files, concurrent refinement of unrelated issues could be safe. Implementation still needs serialization or worktree isolation.

## Current Behavior

Autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. All temp files (e.g., `autodev-queue.txt`, `autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`, `autodev-broke-down`, `autodev-pre-ids.txt`, `autodev-post-ids.txt`, `autodev-diff-ids.txt`, `autodev-new-children.txt`, `autodev-decide-ran`) are scoped under `${context.run_dir}` (`.loops/runs/<instance_id>/`) thanks to ENH-1726 — they do NOT collide across instances. The shared `mkdir -p .loops/tmp` in `init` is harmless. The real blocker is scope `["."]` serializing all instances via `LockManager.acquire()`; the temp files are already isolated.

## Expected Behavior

Multiple `ll-loop run autodev` invocations with disjoint issue sets can run concurrently. Each instance gets isolated temp files scoped by instance ID. Refinement phases (format, refine, wire, confidence-check) operate on disjoint issue files with per-issue scope, allowing concurrent execution. Implementation phases coordinate through either a full-repo lock or worktree isolation.

## Motivation

Running two independent autodev sessions (e.g. `autodev BUG-031` and `autodev ENH-1699,ENH-1700`) concurrently would cut wall-clock time for issue backlogs that contain unrelated work. The refinement pipeline spends significant time waiting on LLM responses — overlapping that wait time across issues is the primary win.

## Use Case

**Who**: Developer or automation pipeline managing a backlog of unrelated issues.

**Context**: The developer has two independent issues (e.g. BUG-031 and ENH-1699,ENH-1700) that need refinement. Each set touches different parts of the codebase and has no overlapping source files.

**Goal**: Run `ll-loop run autodev BUG-031` and `ll-loop run autodev ENH-1699,ENH-1700` concurrently to cut wall-clock time.

**Outcome**: Both autodev sessions complete refinement in parallel, overlapping LLM response wait time. Implementation phases serialize via lock or worktree. Total wall-clock time approaches max(single-instance time) rather than sum(all instances).

## Obstacles

1. **Shared temp files** (RESOLVED — ENH-1726): All temp files already use `${context.run_dir}/autodev-*` (per-instance `.loops/runs/<instance_id>/`). Two concurrent instances write to different paths. The only shared touchpoint is `mkdir -p .loops/tmp` which is harmless.

2. **Git operations**: `enqueue_children` and `enqueue_or_skip` do `git mv` of parent issue files. `implement_current` runs `ll-auto --only` which makes source changes and git commits. Concurrent git operations on the same working tree race.

3. **Disjointness detection**: Two issues targeting different areas can still touch overlapping source files during implementation. Need a way to know they're truly disjoint before allowing parallel implementation.

## Proposed Solution

1. **Scope temp files by instance ID**: Change all `.loops/tmp/autodev-*` paths to `.loops/tmp/autodev-<instance_id>-*` so concurrent instances have isolated state.

2. **Split scope**: Refinement phase uses issue-specific scope (e.g., `.issues/<type>/<issue-file>.md`) so concurrent refinement of disjoint issues doesn't conflict. Implementation phase still requires `["."]` or worktree isolation.

3. **Worktree isolation for implementation**: When an issue reaches `implement_current`, either acquire the full-repo lock, or spawn implementation in an isolated worktree so it doesn't block refinement of other issues.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

- **Approach #1 (temp file scoping)**: Two viable scoping targets. (a) Scope within `.loops/tmp/` as `autodev-{instance_id}-*` — simpler but note that `.loops/tmp/` was intentionally kept as shared cross-run scratch by ENH-1726; scoping here adds clutter to the shared space. (b) Move to `${context.run_dir}` (`.loops/runs/{instance_id}/`) — aligns with ENH-1726's per-run isolation design and uses the already-injected `run_dir` context variable. Does NOT require injecting `instance_id` into `fsm.context` since `run_dir` already derives from it. Trade-off: temp files become subject to `.loops/runs/` cleanup policies.

- **Approach #2 (split scope)**: Requires ENH-1787 (scope template variable support) as implemented dependency. Without `resolve_scope()`, autodev cannot declare per-issue scope — `scope: ["."]` is the only available value. After ENH-1787, refinement phases can use `scope: ["${context.run_dir}"]` so two instances with different `run_dir` values have non-overlapping scopes. Implementation phase retains `["."]` or worktree.

- **Approach #3 (worktree isolation)**: `worktree_utils.py:21` (`setup_worktree()`) already creates isolated git worktrees with per-process markers (`worktree_utils.py:99` writes `.ll-session-{pid}`). Currently used at whole-loop level via `--worktree` flag (`run.py:330`). For per-state use within autodev, `implement_current` (autodev.yaml line 290) would need to wrap `ll-auto --only` in setup/teardown. Alternatively, implement a simpler lock handoff: refinement holds per-issue scope, `implement_current` upgrades to `["."]` scope — serializes implementation but is simpler.

### Codebase Research Findings (2026-05-30 refresh)

_Added by `/ll:refine-issue` — based on re-analysis after dependency completion._

- **Approach #1 update — temp file scoping already resolved**: Reading the actual `autodev.yaml` confirms ALL 11 temp files already use `${context.run_dir}/autodev-*` (e.g., line 39: `> ${context.run_dir}/autodev-passed.txt`). ENH-1726 is `done` — `run_dir` (`.loops/runs/<instance_id>/`) is injected at `run.py:162` and created at `run.py:380`. Two concurrent instances have different `run_dir` values, so temp files do NOT clash. The only shared touchpoint is `mkdir -p .loops/tmp` (line 38) which is harmless. **This obstacle is already resolved.**

- **Approach #2 update — scope split now immediately viable**: ENH-1787 is `done` (completed 2026-05-30T01:02:06Z). `resolve_scope()` at `concurrency.py:31` resolves `${context.*}` template variables. Autodev can now declare `scope: ["${context.run_dir}"]` in its YAML, giving each instance a non-overlapping scope (different `run_dir` values). `_paths_overlap()` at `concurrency.py:276` would return False for sibling paths under `.loops/runs/`. With ENH-1787 and ENH-1726 both done, the scope split for refinement phases is a configuration change, not a development task.

- **Lock upgrade gap identified**: The lock handoff described in Approach #3 (release per-instance scope, re-acquire `["."]` for implementation) cannot be implemented from YAML shell actions alone — `LockManager.acquire()/release()` are Python functions not directly callable from `action_type: shell` states. This requires either: (a) adding `action_type: lock_upgrade` to the FSM framework, (b) using `ll-loop run autodev --worktree` for the outer invocation so implementation already runs in an isolated worktree, or (c) a new CLI-level coordination point where the runner detects `implement_current` and handles the scope transition before state execution.

## Acceptance Criteria

- Two `ll-loop run autodev` invocations with disjoint issue sets can run refinement concurrently
- Temp files already isolated per instance via `${context.run_dir}` (ENH-1726 done)
- Implementation phase coordinates safely (existing `--worktree` flag or new lock upgrade infrastructure)
- Backward compatible: single-issue autodev behavior unchanged
- Stale `loops/README.md:25` note about single-reader access to `.loops/tmp/` updated

## Implementation Steps

1. **Add `scope: ["${context.run_dir}"]` to autodev.yaml**: With ENH-1787 done (`resolve_scope()` at `concurrency.py:31`), add a one-line scope declaration to autodev.yaml. This gives each instance a non-overlapping scope, enabling concurrent lock acquisition. Refinement phases can run in parallel; implementation phase retains `["."]` or uses `--worktree`. (Steps 1-2 from original plan — instance_id plumbing and temp file scoping — are already done via ENH-1354 and ENH-1726.)

2. **Choose and implement implementation-phase coordination**: Three options — (a) use existing `--worktree` flag (zero code changes, `ll-loop run autodev --worktree`), (b) add `action_type: lock_upgrade` to FSM framework for mid-loop scope changes, (c) add CLI-level coordination to detect `implement_current` and handle scope transition.
> **Selected:** Option (a) `--worktree` flag — zero code changes, already implemented at `run.py:331-373`, provides complete git isolation via `setup_worktree()` at `worktree_utils.py:21`

3. **Update `loops/README.md:25`**: Remove stale "single-reader access to `.loops/tmp/`" note about autodev — it now uses per-instance `${context.run_dir}`.

4. **Update tests**: Add concurrent autodev test cases following patterns in `test_concurrency.py:545` (`test_concurrent_same_name_non_overlapping_scopes_both_acquire`). Test: (a) two instances with different `run_dir` values acquire locks concurrently, (b) two instances with same scope (`["."]`) correctly conflict, (c) temp file isolation verified by checking different `run_dir` paths.

5. **Verify backward compatibility**: Run single-issue `ll-loop run autodev` to confirm behavior unchanged after scope addition. Confirm `--worktree` flag works for single-instance autodev.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Update `scripts/little_loops/fsm/__init__.py` and `scripts/little_loops/parallel/__init__.py`**: If any public symbol signatures change (e.g., `LockManager.acquire()`, `resolve_scope()`), the `__all__` exports must stay current. Re-export chains propagate to all consumers.

7. **Audit `scripts/little_loops/loops/rn-refine.yaml`**: Already declares `scope: ["${context.plan_file}"]` using the same `resolve_scope()` template resolution. Verify this loop still works correctly after any concurrency.py changes — it's the only other loop using template-variable scope.

8. **Audit `scripts/little_loops/loops/scan-and-implement.yaml`**: Delegates to autodev as a sub-loop. Verify that autodev's new `scope: ["${context.run_dir}"]` doesn't break scan-and-implement's expected behavior (it snapshots pre/post issue IDs to scope autodev to issues created in that run).

9. **Update `scripts/tests/test_builtin_loops.py`**: Add structural assertion that `autodev.yaml` declares `scope: ["${context.run_dir}"]`. The existing `test_required_top_level_fields` test checks `name` and `initial` — add a `test_scope_field_uses_run_dir_template` assertion.

10. **Verify `scripts/tests/test_cli_loop_queue.py:61`**: `test_retries_acquire_after_losing_race` asserts instance_id consistency across LockManager retries. If the lock upgrade changes how instance_id flows through acquire/release, this test will need updating.

11. **Update `config-schema.json`**: If new config keys are added (e.g., `parallel_autodev_workers`, `disjoint_detection_strategy`), update the schema. Existing `queue_wait_timeout_seconds` description and `worktree_base` docs may need refreshing for new concurrent-autodev semantics.

12. **Update `docs/reference/CLI.md`**: The `--queue`, `--worktree`, and `--no-lock` flag descriptions (lines 399-407) should reflect that autodev now uses per-instance scope by default. The queue entry schema referencing "scope" paths (lines 428-449) may need examples showing `${context.run_dir}`-based scopes.

13. **Update `docs/guides/LOOPS_GUIDE.md`**: The autodev section (lines 528-762) and "Scope-Based Concurrency" section (lines 1743-1754) should document the new concurrent-autodev capability and the `--worktree` option for implementation isolation.

14. **Update `CHANGELOG.md`**: Add entry for parallel-safe autodev — this is a user-visible feature change.

15. **Regenerate site docs**: If any of the above doc changes are made, regenerate `site/reference/API/index.html`, `site/reference/CLI/index.html`, `site/guides/LOOPS_GUIDE/index.html`, `site/generalized-fsm-loop/index.html`, and `site/search/search_index.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

- **Step 1 (instance_id plumbing)**: ENH-1354 already generates `instance_id` via `_make_instance_id()` at `_helpers.py:926` and propagates it through `LockManager.acquire()` and `PersistentExecutor.__init__()`. The gap: `instance_id` is NOT injected into `fsm.context`. ENH-1354 explicitly scoped this out. Two approaches: (a) add `fsm.context["instance_id"] = instance_id` alongside the existing `run_dir` injection at `run.py:162`; (b) use `${context.run_dir}` which already derives from instance_id (the ENH-1726 path). Approach (b) requires moving temp files from `.loops/tmp/` to `${context.run_dir}/`.

- **Step 2 (temp file scoping)**: All 11 hardcoded `autodev-*` paths in `autodev.yaml` with line references: `autodev-queue.txt` (line 46), `autodev-passed.txt` (39, 158, 231, 416, 534), `autodev-skipped.txt` (40, 117, 353, 504, 536), `autodev-broke-down` (41, 130-132, 392), `autodev-inflight` (42, 71, 118, 364, 514, 563), `autodev-decide-ran` (74, 172, 199), `autodev-pre-ids.txt` (83, 252, 376), `autodev-post-ids.txt` (314), `autodev-diff-ids.txt` (318), `autodev-new-children.txt` (328), plus `recursive-refine-broke-down` (cross-loop handshake, line 129). Replace each `${loops.tmp}/autodev-*` with either `${loops.tmp}/autodev-${context.instance_id}-*` (if instance_id added to context) or `${context.run_dir}autodev-*` (using existing run_dir).

- **Step 3 (split scope)**: Requires ENH-1787 (scope template variable support) first. After ENH-1787, autodev can declare `scope: ["${context.run_dir}"]` so concurrent instances with different `run_dir` values get non-overlapping scopes. Only 2 of 20+ existing loops declare `scope:` — `dead-code-cleanup.yaml` (`["scripts/"]`) and `docs-sync.yaml` (`["docs/", "*.md"]`). Implementation phase still serializes on `["."]` or worktree; the split is that refinement lock files live under per-instance paths, while implementation lock uses whole-repo scope.

- **Step 4 (worktree isolation)**: `worktree_utils.py:21` (`setup_worktree()`) already creates isolated git worktrees. The `--worktree` flag at `run.py:330` works at whole-loop level. For per-state isolation, `implement_current` state (autodev.yaml line 290) runs `ll-auto --only ${captured.input.output}` directly on the main working tree. Option (a): wrap that shell command in worktree setup/teardown within the state — requires new worktree orchestration in autodev.yaml. Option (b): implement a lock handoff — refinement releases per-issue scope, `implement_current` acquires `["."]` scope — simpler but serializes implementation.

- **Step 5 (tests)**: Follow concurrent test patterns in `scripts/tests/test_concurrency.py`: `TestLockManagerRaceConditions` (line 256) uses `threading.Barrier` for race-condition tests, `TestMultiInstanceSameName` (line 517) for same-name/different-instance lock isolation, `test_concurrent_same_name_non_overlapping_scopes_both_acquire` (line 545) for non-overlapping scope concurrent acquisition. Also `test_cli_loop_background.py:560` (`test_scope_conflict_returns_1`) for scope conflict behavior. Add temp file isolation tests to `test_builtin_loops.py:1270` (existing `TestAutodevInterleavedLoop` class).

### Codebase Research Findings (2026-05-30 refresh)

_Added by `/ll:refine-issue` — based on re-analysis after dependency completion._

- **Steps 1-2 status — temp file isolation already resolved**: Reading `autodev.yaml` confirms all temp files already use `${context.run_dir}/autodev-*`. ENH-1354 and ENH-1726 are both `done`. The `run_dir` (`.loops/runs/<instance_id>/`) is injected at `run.py:162` and created at `run.py:380`. No changes needed to autodev.yaml for temp file scoping — two concurrent instances already write to different paths. The remaining YAML changes are: (a) add `scope: ["${context.run_dir}"]` to enable concurrent lock acquisition, (b) possibly handle the implementation phase lock upgrade.

- **Step 3 status — scope split is a configuration change now**: ENH-1787 is `done` with `resolve_scope()` at `concurrency.py:31`. Adding `scope: ["${context.run_dir}"]` to autodev.yaml is all that's needed for refinement-phase concurrency. The `_paths_overlap()` check at `concurrency.py:276` would return False for sibling `.loops/runs/<instance_id-1>/` vs `.loops/runs/<instance_id-2>/` paths.

- **Step 4 status — lock upgrade requires new infrastructure**: The lock handoff (release per-instance scope, acquire `["."]` for implementation) cannot be implemented from YAML `action_type: shell` states alone — `LockManager.acquire()/release()` are Python functions, not CLI tools. Three options exist: (a) add an `action_type: lock_upgrade` to the FSM framework, (b) use `--worktree` at loop invocation so all states run in an isolated worktree (already implemented at `run.py:331-373`), (c) add a CLI-level coordination point in the runner to detect state transitions and handle scope changes before state execution. Option (b) is the simplest immediate path — `ll-loop run autodev --worktree` already provides implementation isolation without any code changes.

- **Disjointness verification infrastructure**: `OverlapDetector.check_overlap()` at `overlap_detector.py:106` + `FileHints.extract_file_hints()` at `file_hints.py:339` can verify whether issue sets touch disjoint files (reads "Files to Modify" sections). The detector is in-memory (designed for single-process `ll-parallel` dispatcher). For cross-process autodev instances, options: (a) pre-compute file hints at startup and check disjointness before allowing concurrent implementation, (b) add file-based registration like the LockManager pattern. This is the "nice to have" tier — not blocking refinement concurrency, only blocking OPTIONAL parallel implementation.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-30.

**Selected**: Option (a) — use existing `--worktree` flag

**Reasoning**: The `--worktree` flag at `run.py:331-373` already provides complete git-level isolation via `setup_worktree()` at `worktree_utils.py:21`, with zero code changes required. Option B (`lock_upgrade` action_type) would need 10+ file changes including a new executor dependency on `concurrency.py` and a new `StateConfig` schema field. Option C (CLI coordination) breaks fundamental architectural invariants — the runner is generic and blocked during execution with no synchronous pre-execution hook mechanism. `--worktree` trades whole-loop isolation overhead (wrapping refinement phases that don't need it) for simplicity and immediate availability. The mutually-exclusive `--background` limitation (BUG-1414) and opt-in nature are acceptable trade-offs for a P3 feature.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A: `--worktree` | 3/3 | 3/3 | 3/3 | 1/3 | **10/12** |
| B: `lock_upgrade` | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| C: CLI coordination | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |

**Key evidence**:
- **Option A**: `setup_worktree()` at `worktree_utils.py:21` is production-hardened across 3 call sites (`run.py`, `worker_pool.py`, `merge_coordinator.py`). `implement_current` (`autodev.yaml:290`) inherits worktree isolation automatically via `os.chdir()` at `run.py:373`. Orphan detection at `worktree_utils.py:147` already recognizes loop worktree naming. Trade-off: wraps entire loop (over-isolates refinement), mutually exclusive with `--background`.
- **Option B**: `LockManager.acquire()`/`release()` at `concurrency.py:123,170` are clean APIs. `mcp_tool` precedent at `executor.py:1309-1310` shows the integration pattern. But executor has no `lock_manager` reference, `instance_id` isn't accessible in `_run_action()`, and no per-state scope concept exists in the schema.
- **Option C**: `resolve_scope()` at `concurrency.py:31` and event bus observer registration at `_helpers.py:1145-1150` exist, but the event bus is fire-and-forget (cannot mediate execution flow), `_interceptors` at `executor.py:256` is an empty stub, and mid-execution lock transitions have zero precedent in the codebase.

## API/Interface

No public API changes. Internal contract changes:

- Temp file path convention: Already uses `${context.run_dir}/autodev-*` (per-instance) — no change needed
- Loop scope parameter: Add `scope: ["${context.run_dir}"]` to autodev.yaml (now possible with ENH-1787 done)
- New worktree/lock coordination point: Either use `--worktree` flag (existing) or add lock upgrade infrastructure for `implement_current` state

## Impact

- **Priority**: P3
- **Effort**: Low — temp file isolation already done (ENH-1726). Scope split is a 1-line config change (`scope: ["${context.run_dir}"]`). The remaining design work is the implementation-phase lock upgrade (3 options, see Proposed Solution refresh). Disjointness detection is nice-to-have tier.
- **Risk**: Medium — concurrency bugs are subtle; needs thorough testing of edge cases (child detection across instances, queue file isolation, git state coordination)
- **Breaking Change**: No — single-instance behavior unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — all temp file references, scope definitions, implement_current state
- `scripts/little_loops/fsm/concurrency.py` — lock or worktree coordination for implementation phase
- `scripts/little_loops/cli/loop/run.py` — instance_id plumbing on invocation
- `scripts/little_loops/fsm/__init__.py` — re-exports LockManager, resolve_scope, ScopeLock, PersistentExecutor, _find_instances in `__all__`; any signature change propagates to all consumers
- `scripts/little_loops/parallel/__init__.py` — exports FileHints, extract_file_hints, GitLock, OverlapDetector

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports loop runner, may need instance_id passthrough
- `scripts/little_loops/cli/loop/next_loop.py` — schedules autodev runs
- `scripts/little_loops/subprocess_utils.py` — shared subprocess utilities

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — imports `_process_alive` from concurrency (line 37); defines `PersistentExecutor` and `_find_instances` (line 812)
- `scripts/little_loops/fsm/executor.py` — type-annotation import of `PersistentExecutor` (TYPE_CHECKING); FSMExecutor is wrapped by PersistentExecutor
- `scripts/little_loops/extension.py` — imports `PersistentExecutor` at line 27 (TYPE_CHECKING); used as parameter type in `wire_extensions()` at line 204
- `scripts/little_loops/parallel/orchestrator.py` — imports `OverlapDetector` (line 28) and `GitLock` (line 26); calls `check_overlap()` for sprint wave planning
- `scripts/little_loops/parallel/worker_pool.py` — imports `GitLock` (line 24) and `setup_worktree` (line 544)
- `scripts/little_loops/parallel/merge_coordinator.py` — imports `GitLock` for merge serialization
- `scripts/little_loops/cli/sprint/manage.py` — imports `FileHints`, `extract_file_hints` from `parallel.file_hints` at line 70
- `scripts/little_loops/dependency_graph.py` — imports `FileHints`, `extract_file_hints` at line 409
- `scripts/little_loops/worktree_utils.py` — imports `GitLock` from `parallel.git_lock`

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — multi-item loop that may have similar scope/isolation patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sprint loop with multi-issue coordination

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — add concurrent execution test cases, temp file isolation tests; add `test_scope_field_uses_run_dir_template` assertion on autodev.yaml structure
- `scripts/tests/test_concurrency.py` — existing `TestMultiInstanceSameName` (line 517) and `TestResolveScope` (line 583) cover concurrent lock patterns; add `test_autodev_with_run_dir_scopes_both_acquire_concurrently` and `test_autodev_with_dot_scope_still_conflicts` following `test_concurrent_same_name_non_overlapping_scopes_both_acquire` pattern (line 545)
- `scripts/tests/test_cli_loop_background.py` — `TestRunBackgroundScopeResolution` (line 670) directly exercises template-aware scope resolution in `run_background()`; `test_scope_conflict_returns_1` (line 560) pre-acquires `["."]` lock and asserts conflict
- `scripts/tests/test_cli_loop_queue.py` — mocks `LockManager` for retry behavior; `test_retries_acquire_after_losing_race` (line 61) asserts `instance_id` consistency across retries — **may break** if lock upgrade changes instance_id flow
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree` (line 559) tests `--worktree` flag; `test_worktree_and_background_rejected` (line 670) — **may break** if worktree/scope interaction changes
- `scripts/tests/test_cli_loop_lifecycle.py` — patches `_find_instances` in ~40 tests; dedicated unit tests at line 1793
- `scripts/tests/test_fsm_persistence.py` — `TestPersistentExecutor` (line 628, 30+ instantiations); exercise `PersistentExecutor` state/event file isolation
- `scripts/tests/test_ll_loop_program_md.py` — `TestRunDirInjection` (line 252) verifies `run_dir` injected into `fsm.context` before scope resolution
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdRunPositionalInput` (line 2579) tests `cmd_run` positional input → context injection
- `scripts/tests/test_ll_loop_integration.py` — FSM execution flow with mocked `_process_alive` (line 438)
- `scripts/tests/test_cli.py` — patches `PersistentExecutor` and `_find_instances` across multiple tests (lines 1973-2340)
- `scripts/tests/test_orchestrator.py` — uses `OverlapDetector` and `GitLock`; `OverlapResult` assertions at lines 2202-2279
- `scripts/tests/test_worker_pool.py` — tests `GitLock` and `setup_worktree` usage
- `scripts/tests/test_git_lock.py` — dedicated `GitLock` tests
- `scripts/tests/test_overlap_detector.py` — dedicated `OverlapDetector` tests
- `scripts/tests/test_file_hints.py` — dedicated `FileHints`/`extract_file_hints` tests
- `scripts/tests/test_review_loop.py` — references `_make_instance_id()` at line 1266
- `scripts/tests/test_sprint_integration.py` — uses `OverlapDetector` (line 422)

### Similar Loops (Scope-Aware Peers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-refine.yaml` — declares `scope: ["${context.plan_file}"]` (line 10); uses same `resolve_scope()` template resolution as planned autodev change
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — declares `scope: ["scripts/"]` (line 8); may benefit from explicit scope narrowing when run concurrently with autodev
- `scripts/little_loops/loops/docs-sync.yaml` — declares `scope: ["docs/", "*.md"]` (line 8); disjoint with autodev default scope
- `scripts/little_loops/loops/scan-and-implement.yaml` — delegates to autodev after scanning (line 6); any interface change to autodev affects this parent loop

### Documentation
- `docs/reference/API.md` — document new instance_id conventions if public; concurrency module docs at lines 4806-4846 (ScopeLock, LockManager, resolve_scope)
- `docs/development/TROUBLESHOOTING.md` — add concurrent autodev guidance

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — `scope:` field schema reference (line 339), create-loop template (line 668), full "Concurrency and Locking" section (lines 1411-1451) with template variable resolution examples
- `docs/reference/CLI.md` — `--queue` flag (line 399), `--worktree` flag (line 404), `--no-lock` flag (line 407), queue entry schema referencing scope paths (lines 428-449), lock-file PID cleanup (line 801)
- `docs/guides/LOOPS_GUIDE.md` — autodev description (lines 528-762), "Scope-Based Concurrency" section (lines 1743-1754), foreground queueing scope conflict (line 1767)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `scope:` field documentation for harnessed loops (lines 272, 283)
- `docs/ARCHITECTURE.md` — `concurrency.py` in directory tree (line 291)
- `docs/reference/COMMANDS.md` — cleanup-worktrees skill reference (line 801)
- `.claude/CLAUDE.md` — Loop Authoring rules 2-3 reference `run_dir`, `.loops/tmp/`, and validation rules MR-1/MR-3
- `CHANGELOG.md` — extensive autodev and scope-locking entries throughout; needs entry for this feature
- `README.md` — worktree mentions (lines 33, 35, 44)
- `CONTRIBUTING.md` — `concurrency.py` in directory tree (line 255)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `queue_wait_timeout_seconds` (line 824, description references "conflicting scope lock"); `worktree_base` (lines 258-261, 306-309); `worktree_copy_files` (line 354-356); `loops` config section (lines 815-844). All may need description updates if scope/locking semantics change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

**Additional Files to Modify:**
- `scripts/little_loops/cli/loop/_helpers.py:926` — `_make_instance_id()` generates instance_id; may need to inject into `fsm.context`
- `scripts/little_loops/fsm/concurrency.py:31` — `resolve_scope()` **NOW IMPLEMENTED** (ENH-1787 done). Resolves `${context.*}` template variables in scope paths. Wired into `cmd_run()` at `run.py:265` and `run_background()` at `_helpers.py:983`. This enables `scope: ["${context.run_dir}"]` in autodev.yaml.
- `scripts/little_loops/fsm/concurrency.py:98` — `LockManager.acquire()` already accepts `instance_id` kwarg; lock files at `.loops/.running/{instance_id}.lock` are already per-instance
- `scripts/little_loops/fsm/concurrency.py:276` — `_paths_overlap()` compares normalized absolute paths; sibling dirs like `.loops/runs/<id-1>/` vs `.loops/runs/<id-2>/` return False (no overlap) — the core mechanism that makes per-instance scope work
- `scripts/little_loops/fsm/validation.py:1100` — MR-3 validation rule (`_SHARED_TMP_PATH_RE`) flags bare `.loops/tmp/` writes as WARNING. Autodev already passes this check because it uses `${context.run_dir}`.
- `scripts/little_loops/fsm/persistence.py:538` — `PersistentExecutor.__init__()` accepts `instance_id`; state/events files at `{instance_id}.state.json` already per-instance

**Existing Infrastructure to Leverage:**
- `scripts/little_loops/parallel/overlap_detector.py:42` — `OverlapDetector.check_overlap()` already detects file modification overlaps between issues using `FileHints.extract_file_hints()` (`file_hints.py:339`). Reusable for disjointness verification before allowing parallel implementation. In-memory only (single-process); cross-process would need file-based registration or pre-computed hints.
- `scripts/little_loops/worktree_utils.py:21` — `setup_worktree()` creates isolated git worktrees; currently used at whole-loop level via `--worktree` flag (`run.py:330`), not per-state within autodev. For per-state isolation, `implement_current` would need to wrap `ll-auto --only` in worktree setup/teardown — OR the user invokes `ll-loop run autodev --worktree` and all states already run in isolation (zero code changes).
- `scripts/little_loops/parallel/git_lock.py:28` — `GitLock` provides thread-safe git operations with `index.lock` retry; threading-only (not process-safe for cross-instance coordination).

**New Files Discovered (2026-05-30 refresh):**
- `scripts/little_loops/loops/README.md:25` — Documents autodev as assuming "single-reader access to `.loops/tmp/`" — this is stale (autodev uses `run_dir` now) and should be updated when this feature ships.
- `scripts/tests/test_concurrency.py:583` — `TestResolveScope` class (11 tests) covers the scope template resolution needed for autodev's per-instance scope.
- `scripts/little_loops/cli/loop/run.py:331-373` — Worktree setup for `--worktree` flag. Already creates isolated worktrees with timestamp-based branch names (`YYYYMMDD-HHMMSS-<safe-name>`). Usable immediately for implementation isolation without any autodev changes.
- `scripts/little_loops/fsm/persistence.py:812` — `_find_instances()` discovers all instances by globbing `{loop_name}-*.state.json`. Important for testing concurrent instance behavior.

**ENH-1787 Dependency Detail:**
- Status: **`done`** (completed 2026-05-30T01:02:06Z). `resolve_scope()` is implemented at `concurrency.py:31` and wired into `cmd_run()` (`run.py:265`) and `run_background()` (`_helpers.py:983`). Tests in `test_concurrency.py:583` (class `TestResolveScope`, 11 tests). Autodev can now declare `scope: ["${context.run_dir}"]` for per-instance scope isolation.

**Architectural Note — `.loops/tmp/` vs `${context.run_dir}` (UPDATED):**
- Autodev already uses `${context.run_dir}/autodev-*` for all 11 temp files (verified by reading `autodev.yaml`). ENH-1726 migrated these from `.loops/tmp/`. The MR-3 validation rule at `validation.py:1100` (`_SHARED_TMP_PATH_RE`) would flag bare `.loops/tmp/` writes as WARNING severity.
- `${context.run_dir}` (`.loops/runs/{instance_id}/`) is per-instance and available as `${context.run_dir}` in YAML shell commands
- `instance_id` itself is NOT in `fsm.context` (ENH-1354 explicitly scoped this out); only `run_dir` is injected at `run.py:162`. This is sufficient — `run_dir` derives from `instance_id` and provides per-instance isolation.
- **Scope isolation path**: Adding `scope: ["${context.run_dir}"]` to autodev.yaml (via ENH-1787's `resolve_scope()`) gives each instance a non-overlapping lock scope. Refinement phases can run concurrently. Only the implementation phase needs additional coordination.

## Related Issues

- BUG-1760 (cancelled): original misdiagnosis that led to this feature request
- ENH-1354: multi-instance instance_id generation and runtime file path scoping
- ENH-1726: per-run artifact dirs for built-in loops

**Open** | Created: 2026-05-29 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-30 | Updated 2026-05-31_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Changes Since Prior Check
- ENH-1787 (`resolve_scope()`) is now **done** — template-variable scope resolution is available
- Lock-upgrade decision resolved by `/ll:decide-issue` — Option A (`--worktree`) selected
- Ambiguity eliminated (25/25, up from 10/25): all design decisions are now made
- Dependencies fully satisfied: ENH-1787, ENH-1726, ENH-1354 all done

No concerns, gaps, or risk factors — clean bill of health.

## Session Log
- `/ll:ready-issue` - 2026-05-31T03:12:00 - `3429f501-3e51-46b9-9aec-02bd2b00cdfe.jsonl`
- `/ll:confidence-check` - 2026-05-31T03:15:00Z - `9b7df17f-a880-43b3-bdde-974af6dce947.jsonl`
- `/ll:decide-issue` - 2026-05-31T03:07:36 - `8386755f-dd94-4045-b533-371ffc0ec47d.jsonl`
- `/ll:confidence-check` - 2026-05-30T06:07:00Z - `787ce0c0-e1a8-4c2d-8ef4-89cc995661e7.jsonl`
- `/ll:refine-issue` - 2026-05-31T02:49:59 - `93ce2bb2-a420-4b9e-add7-55f34fb013b6.jsonl`
- `/ll:refine-issue` - 2026-05-30T00:12:15 - `f2bd7f76-b0bd-4154-ac21-38679054df7a.jsonl`
- `/ll:format-issue` - 2026-05-29T18:46:39 - `e778a487-9894-450e-a694-a731058b51d1.jsonl`
- `/ll:wire-issue` - 2026-05-30 - `<session-id>.jsonl`
