---
id: BUG-2424
title: Parallel orchestrator lifecycle completion over-stages the main repo via `git add -A`
type: BUG
priority: P3
status: open
captured_at: "2026-07-01T02:55:19Z"
discovered_date: 2026-07-01
discovered_by: capture-issue
labels: [bug, loop, git, lifecycle, parallel, hygiene]
relates_to: [BUG-2421, BUG-1800, BUG-1976]
---

# BUG-2424: Parallel orchestrator lifecycle completion over-stages the main repo via `git add -A`

## Summary

The `ll-parallel` path has the same `git add -A` over-staging defect as
[[BUG-2421]], but in a **distinct code path** that BUG-2421's fix does not touch.
`ParallelOrchestrator` stages completion/frontmatter commits against the **main
repo** with an unscoped `git add -A` in two places, so any pre-existing dirty or
untracked file in the main working tree can be swept into a worker's completion
commit. This is the `ll-parallel` twin of the `ll-auto`/`issue_lifecycle.py` bug
filed as [[BUG-2421]].

## Current Behavior

Two sites in `scripts/little_loops/parallel/orchestrator.py` stage with an
unscoped sweep against `self.repo_path` (the main repo, not a worktree):

- **`_on_worker_complete()` — line 1024** (feature-branch fallback path): stages
  frontmatter updates via
  `self._git_lock.run(["add", "-A"], cwd=self.repo_path)` before committing.
- **`_complete_issue_lifecycle_if_needed()` — line 1417**: a **separate
  reimplementation** of lifecycle completion (it does NOT call
  `issue_lifecycle.complete_issue_lifecycle()`); it writes frontmatter itself and
  stages with `git add -A` against `self.repo_path`.

Both run in the main repo after a worker's work has (or should have) been merged
back, so an `-A` sweep there absorbs whatever else is dirty/untracked in the main
tree at that moment.

## Steps to Reproduce

1. Leave the main working tree dirty with changes belonging to other issues,
   sessions, or branches (e.g. untracked issue stubs, an in-flight edit).
2. Run issues through `ll-parallel` (or an `ll-sprint` wave that uses the parallel
   orchestrator).
3. Have a worker reach the feature-branch fallback (`_on_worker_complete`) or the
   lifecycle-completion fallback (`_complete_issue_lifecycle_if_needed`).
4. **Observe:** the resulting main-repo commit stages every dirty/untracked file
   in the main tree via `git add -A`, not just the issue's own attributable
   changes — the same provenance corruption documented in [[BUG-2421]].

## Expected Behavior

A worker's completion/frontmatter commit in the main repo should stage **only**
that issue's attributable changes (at minimum the issue `.md` file), never the
entire main working tree. Pre-existing dirty state belonging to other issues or
sessions must remain uncommitted.

## Motivation

Same failure class as [[BUG-2421]] / [[BUG-1800]] / [[BUG-1976]]: `git add -A` in
a shared completion path corrupts commit provenance (poisoned `git bisect`/blame,
premature commit of unrelated WIP), and it happens on the silent
fallback/automation path where no human reviews the result.

**Why lower priority than [[BUG-2421]] (P3, not P2):** the `ll-parallel` path is
partially defended — work happens in isolated worktrees, and
`worker_pool._detect_main_repo_leaks()` exists specifically to catch files that
leak into the main repo. But `_on_worker_complete():1024` stages against the
shared main repo directly, so the mitigation is not complete; the exact ordering
of leak-detection vs. these commits should be verified during implementation.

## Root Cause

`scripts/little_loops/parallel/orchestrator.py` stages with
`self._git_lock.run(["add", "-A"], cwd=self.repo_path)` at lines 1024 and 1417
with no path scoping. Unlike `issue_lifecycle.py:_commit_issue_completion()`
(which runs with no `cwd`), these sites do pass an explicit `cwd=self.repo_path` —
so they are correctly targeting the main repo, but still over-stage within it.

## Proposed Solution

Scope both sites to an explicit path set instead of `-A`. The parallel subsystem
already has the primitive needed:

1. **Reuse the existing baseline/leak primitive.**
   `scripts/little_loops/parallel/worker_pool.py:1386` `_get_main_repo_baseline()`
   captures `git status --porcelain` as a `set[str]`, and `:1218`
   `_detect_main_repo_leaks()` diffs `current - baseline`. Stage only the
   attributable delta (the issue file plus files newly changed by this worker),
   not the pre-existing baseline set.
2. **Minimal floor.** At absolute minimum, stage only the issue file
   (`git add -- <issue-file>`) and log the skipped dirty paths, mirroring
   `scripts/little_loops/hooks/post_tool_use.py:115` `_maybe_auto_commit()` (stage
   one path; bail/warn if `git status --porcelain` shows anything else).

**Shared helper (cross-issue):** if [[BUG-2421]] extracts a
`stage_issue_scoped()` Python helper, reuse it here so both Python over-staging
sites share one implementation. Note this helper can unify only the **Python**
sites — [[BUG-1800]] / [[BUG-1976]] were fixed in Markdown SKILL bash blocks, not
Python.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete()`
  (line 1024) and `_complete_issue_lifecycle_if_needed()` (line 1417): replace
  `self._git_lock.run(["add", "-A"], cwd=self.repo_path)` with scoped staging.

### Dependent Files (Callers/Importers)
- `_complete_issue_lifecycle_if_needed()` is invoked from within
  `orchestrator.py` (call sites near lines 977, 1056, 1198, 1228).
- `scripts/little_loops/parallel/worker_pool.py` — source of the reusable
  `_get_main_repo_baseline()` / `_detect_main_repo_leaks()` primitives.

### Similar Patterns
- [[BUG-2421]] — the `issue_lifecycle.py` (`ll-auto`) twin of this bug; coordinate
  the shared `stage_issue_scoped()` helper if extracted.
- [[BUG-1800]] / [[BUG-1976]] — same `git add -A` class fixed in skill Markdown.
- `worker_pool.py` baseline/leak-diff — the capture-porcelain-then-diff pattern to
  reuse.

### Tests
- `scripts/tests/test_orchestrator.py` — add a regression test that dirties an
  unrelated file in the main repo, drives the worker-complete / lifecycle-fallback
  path, and asserts the resulting commit excludes it.
- `scripts/tests/test_worker_pool.py::test_get_main_repo_baseline` /
  `::test_detect_main_repo_leaks_finds_leaked_files` — existing coverage of the
  primitive to reuse.
- Model real-repo git assertions on
  `scripts/tests/test_hooks_integration.py::TestIssueAutoCommitHook.test_dirty_tree_skips_commit_prints_warning`
  and the `temp_git_repo` fixture in
  `scripts/tests/test_worktree_concurrency.py:25`.

### Documentation
- N/A — internal automation behavior.

### Configuration
- N/A

## Implementation Steps

1. Verify whether `_detect_main_repo_leaks()` already runs before these two commit
   sites; if so, the fix may be as small as staging only the attributable delta it
   computes.
2. Replace `git add -A` at `orchestrator.py:1024` and `:1417` with scoped staging
   (attributable delta, or minimal floor = issue file only + warning on skipped
   dirty paths).
3. If [[BUG-2421]] lands a `stage_issue_scoped()` helper, reuse it here.
4. Add a regression test in `test_orchestrator.py` that dirties an unrelated
   main-repo file and asserts it is excluded from the worker completion commit.

## Acceptance Criteria

- [ ] `_on_worker_complete()` (line 1024) no longer stages files unrelated to the
      issue.
- [ ] `_complete_issue_lifecycle_if_needed()` (line 1417) no longer stages files
      unrelated to the issue.
- [ ] Pre-existing dirty files in the main repo remain uncommitted after a
      worker's fallback completion.
- [ ] A regression test proves an unrelated dirty main-repo file is excluded from
      the parallel completion commit.
- [ ] If a shared `stage_issue_scoped()` helper exists ([[BUG-2421]]), both
      orchestrator sites use it.

## Impact

- **Priority**: P3 — same provenance-corruption class as [[BUG-2421]] but on the
  `ll-parallel` path, which is partially mitigated by worktree isolation and
  `worker_pool` leak detection. Still real because `_on_worker_complete():1024`
  stages against the shared main repo.
- **Effort**: Small — two localized call-site changes plus a regression test; the
  baseline primitive already exists in `worker_pool.py`.
- **Files**: `scripts/little_loops/parallel/orchestrator.py` (primary);
  `scripts/tests/test_orchestrator.py` (test); optional shared helper with
  [[BUG-2421]].
- **Risk**: Low-to-medium — changes commit staging behavior on the parallel
  automation path; the regression test locks in the exclusion.

## Session Log
- `/ll:capture-issue` - 2026-07-01T02:55:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/457ad308-c7c0-49a8-936f-f80f8ed18900.jsonl`
