---
id: FEAT-1789
title: parallel-safe autodev for disjoint issues
type: FEAT
status: open
priority: P3
captured_at: '2026-05-29T18:45:00Z'
labels:
- autodev
- ll-loop
- concurrency
- feature
depends_on: ENH-1787
relates_to:
- BUG-1760
---

# FEAT-1789: parallel-safe autodev for disjoint issues

## Summary

Currently autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. Autodev's refinement phase (format, refine, wire, confidence-check) is mostly read-only per-issue and writes only to disjoint issue files. With per-instance temp files, concurrent refinement of unrelated issues could be safe. Implementation still needs serialization or worktree isolation.

## Current Behavior

Autodev serializes all runs via scope `["."]` — only one autodev instance can run at a time regardless of which issues it targets. All temp files (`.loops/tmp/autodev-queue.txt`, `autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`, `autodev-broke-down`, `autodev-pre-ids.txt`, `autodev-post-ids.txt`, `autodev-diff-ids.txt`, `autodev-new-children.txt`, `autodev-decide-ran`) are hardcoded paths shared across instances. Git operations (`git mv` of parent issue files, `ll-auto --only` for implementation) all operate on the same working tree.

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

1. **Shared temp files**: `.loops/tmp/autodev-queue.txt`, `autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`, `autodev-broke-down`, `autodev-pre-ids.txt`, `autodev-post-ids.txt`, `autodev-diff-ids.txt`, `autodev-new-children.txt`, `autodev-decide-ran` — all hardcoded paths shared across instances.

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

## Acceptance Criteria

- Two `ll-loop run autodev` invocations with disjoint issue sets can run refinement concurrently
- Shared temp files are fully isolated per instance
- Implementation phase coordinates safely (lock or worktree)
- Backward compatible: single-issue autodev behavior unchanged

## Implementation Steps

1. **Add instance_id plumbing**: Ensure every autodev invocation gets a unique instance ID, building on ENH-1354 and ENH-1726 for runtime file path scoping.

2. **Scope temp files by instance ID**: Change all hardcoded `.loops/tmp/autodev-*` paths to `.loops/tmp/autodev-<instance_id>-*` in `scripts/little_loops/loops/autodev.yaml`.

3. **Split scope for refinement vs implementation**: Refinement phase uses issue-specific scope (`.issues/<type>/<issue-file>.md`). Implementation phase retains `["."]` or acquires worktree isolation.

4. **Add worktree isolation or lock for implementation**: When an issue reaches `implement_current`, either acquire a full-repo lock or spawn implementation in an isolated worktree.

5. **Update tests**: Add concurrent execution test cases to `scripts/tests/test_builtin_loops.py`. Verify temp file isolation and disjointness detection.

6. **Verify backward compatibility**: Run single-issue autodev to confirm behavior is unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

- **Step 1 (instance_id plumbing)**: ENH-1354 already generates `instance_id` via `_make_instance_id()` at `_helpers.py:926` and propagates it through `LockManager.acquire()` and `PersistentExecutor.__init__()`. The gap: `instance_id` is NOT injected into `fsm.context`. ENH-1354 explicitly scoped this out. Two approaches: (a) add `fsm.context["instance_id"] = instance_id` alongside the existing `run_dir` injection at `run.py:162`; (b) use `${context.run_dir}` which already derives from instance_id (the ENH-1726 path). Approach (b) requires moving temp files from `.loops/tmp/` to `${context.run_dir}/`.

- **Step 2 (temp file scoping)**: All 11 hardcoded `autodev-*` paths in `autodev.yaml` with line references: `autodev-queue.txt` (line 46), `autodev-passed.txt` (39, 158, 231, 416, 534), `autodev-skipped.txt` (40, 117, 353, 504, 536), `autodev-broke-down` (41, 130-132, 392), `autodev-inflight` (42, 71, 118, 364, 514, 563), `autodev-decide-ran` (74, 172, 199), `autodev-pre-ids.txt` (83, 252, 376), `autodev-post-ids.txt` (314), `autodev-diff-ids.txt` (318), `autodev-new-children.txt` (328), plus `recursive-refine-broke-down` (cross-loop handshake, line 129). Replace each `${loops.tmp}/autodev-*` with either `${loops.tmp}/autodev-${context.instance_id}-*` (if instance_id added to context) or `${context.run_dir}autodev-*` (using existing run_dir).

- **Step 3 (split scope)**: Requires ENH-1787 (scope template variable support) first. After ENH-1787, autodev can declare `scope: ["${context.run_dir}"]` so concurrent instances with different `run_dir` values get non-overlapping scopes. Only 2 of 20+ existing loops declare `scope:` — `dead-code-cleanup.yaml` (`["scripts/"]`) and `docs-sync.yaml` (`["docs/", "*.md"]`). Implementation phase still serializes on `["."]` or worktree; the split is that refinement lock files live under per-instance paths, while implementation lock uses whole-repo scope.

- **Step 4 (worktree isolation)**: `worktree_utils.py:21` (`setup_worktree()`) already creates isolated git worktrees. The `--worktree` flag at `run.py:330` works at whole-loop level. For per-state isolation, `implement_current` state (autodev.yaml line 290) runs `ll-auto --only ${captured.input.output}` directly on the main working tree. Option (a): wrap that shell command in worktree setup/teardown within the state — requires new worktree orchestration in autodev.yaml. Option (b): implement a lock handoff — refinement releases per-issue scope, `implement_current` acquires `["."]` scope — simpler but serializes implementation.

- **Step 5 (tests)**: Follow concurrent test patterns in `scripts/tests/test_concurrency.py`: `TestLockManagerRaceConditions` (line 256) uses `threading.Barrier` for race-condition tests, `TestMultiInstanceSameName` (line 517) for same-name/different-instance lock isolation, `test_concurrent_same_name_non_overlapping_scopes_both_acquire` (line 545) for non-overlapping scope concurrent acquisition. Also `test_cli_loop_background.py:560` (`test_scope_conflict_returns_1`) for scope conflict behavior. Add temp file isolation tests to `test_builtin_loops.py:1270` (existing `TestAutodevInterleavedLoop` class).

## API/Interface

No public API changes. Internal contract changes:

- Temp file path convention: `.loops/tmp/autodev-*` → `.loops/tmp/autodev-<instance_id>-*`
- Loop scope parameter: refinement phase accepts issue-specific scope in addition to full-repo `["."]`
- New worktree/lock coordination point in `implement_current` state

## Impact

- **Priority**: P3
- **Effort**: Medium — requires touching all temp file references in autodev.yaml, adding instance_id plumbing, and designing the split-scope or worktree handoff
- **Risk**: Medium — concurrency bugs are subtle; needs thorough testing of edge cases (child detection across instances, queue file isolation, git state coordination)
- **Breaking Change**: No — single-instance behavior unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — all temp file references, scope definitions, implement_current state
- `scripts/little_loops/fsm/concurrency.py` — lock or worktree coordination for implementation phase
- `scripts/little_loops/cli/loop/run.py` — instance_id plumbing on invocation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports loop runner, may need instance_id passthrough
- `scripts/little_loops/cli/loop/next_loop.py` — schedules autodev runs
- `scripts/little_loops/subprocess_utils.py` — shared subprocess utilities

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — multi-item loop that may have similar scope/isolation patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sprint loop with multi-issue coordination

### Tests
- `scripts/tests/test_builtin_loops.py` — add concurrent execution test cases, temp file isolation tests

### Documentation
- `docs/reference/API.md` — document new instance_id conventions if public
- `docs/development/TROUBLESHOOTING.md` — add concurrent autodev guidance

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

**Additional Files to Modify:**
- `scripts/little_loops/cli/loop/_helpers.py:926` — `_make_instance_id()` generates instance_id; may need to inject into `fsm.context`
- `scripts/little_loops/fsm/concurrency.py:98` — `LockManager.acquire()` already accepts `instance_id` kwarg; lock files at `.loops/.running/{instance_id}.lock` are already per-instance
- `scripts/little_loops/fsm/concurrency.py:243` — `_scopes_overlap()` determines lock conflicts; ENH-1787's `resolve_scope()` would insert at `run.py:270` before `acquire()`
- `scripts/little_loops/fsm/persistence.py:538` — `PersistentExecutor.__init__()` accepts `instance_id`; state/events files at `{instance_id}.state.json` already per-instance

**Existing Infrastructure to Leverage:**
- `scripts/little_loops/parallel/overlap_detector.py:42` — `OverlapDetector.check_overlap()` already detects file modification overlaps between issues using `FileHints.extract_file_hints()` (`file_hints.py:339`). Reusable for disjointness verification before allowing parallel implementation.
- `scripts/little_loops/worktree_utils.py:21` — `setup_worktree()` creates isolated git worktrees; currently used at whole-loop level via `--worktree` flag (`run.py:330`), not per-state within autodev. For per-state isolation, `implement_current` would need to wrap `ll-auto --only` in worktree setup/teardown.
- `scripts/little_loops/parallel/git_lock.py:28` — `GitLock` provides thread-safe git operations with `index.lock` retry; threading-only (not process-safe for cross-instance coordination).

**ENH-1787 Dependency Detail:**
- Status: `open`. Adds `resolve_scope()` to resolve `${context.*}` template variables in scope paths before `LockManager.acquire()`. Resolution happens at CLI layer (`cmd_run()` in `run.py`) after context population but before lock acquisition. Without this, autodev cannot declare per-issue scope paths — `scope: ["."]` is all that's available.

**Architectural Note — `.loops/tmp/` vs `${context.run_dir}`:**
- `.loops/tmp/` was intentionally kept as shared cross-run scratch by ENH-1726
- `${context.run_dir}` (`.loops/runs/{instance_id}/`) already exists, is per-instance, and is available as `${context.run_dir}` in YAML shell commands
- `instance_id` itself is NOT in `fsm.context` (ENH-1354 explicitly scoped this out); only `run_dir` is injected at `run.py:162`
- Two isolation approaches: (a) scope paths within `.loops/tmp/` as `autodev-{instance_id}-*` — works but adds clutter to shared space; (b) move autodev temp files to `${context.run_dir}/` — aligns with existing per-run isolation design

## Related Issues

- BUG-1760 (cancelled): original misdiagnosis that led to this feature request
- ENH-1354: multi-instance instance_id generation and runtime file path scoping
- ENH-1726: per-run artifact dirs for built-in loops

**Open** | Created: 2026-05-29 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-05-30T00:12:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2bd7f76-b0bd-4154-ac21-38679054df7a.jsonl`
- `/ll:format-issue` - 2026-05-29T18:46:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e778a487-9894-450e-a694-a731058b51d1.jsonl`
