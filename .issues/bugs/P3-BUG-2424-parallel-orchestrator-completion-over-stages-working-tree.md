---
id: BUG-2424
title: Parallel orchestrator lifecycle completion over-stages the main repo via `git
  add -A`
type: BUG
priority: P3
status: done
captured_at: '2026-07-01T02:55:19Z'
completed_at: '2026-07-01T04:04:06Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
labels:
- bug
- loop
- git
- lifecycle
- parallel
- hygiene
relates_to:
- BUG-2421
- BUG-1800
- BUG-1976
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — codebase analysis (all line anchors below verified
current as of this pass):_

- **Leak detection does NOT guard these commit sites — resolves Implementation
  Step 1.** `_get_main_repo_baseline()` (`worker_pool.py:352`, captured at worker
  start) and `_detect_main_repo_leaks()` (`worker_pool.py:535`) + `_cleanup_leaked_files()`
  (`:543`) run **inside** `WorkerPool._process_issue()` on the worker thread and finish
  **before** the `WorkerResult` is returned. `_on_worker_complete()` fires via
  `future.add_done_callback` strictly **after** that, and neither the baseline capture
  nor the leak diff re-runs at the two `git add -A` sites (`orchestrator.py:1024`,
  `:1417`). The fix therefore **cannot rely on the leak pass** — it must scope staging
  directly at the commit site.
- **No `stage_issue_scoped()` helper exists yet, and [[BUG-2421]] has not landed.**
  `git grep stage_issue_scoped` matches only the BUG-2421 / BUG-2424 markdown; there is
  no implementation to reuse. `issue_lifecycle.py:_commit_issue_completion()` still
  stages with a bare `git add -A` (`:369`, no `cwd`). AC #5 ("both sites use the shared
  helper") is thus **currently unsatisfiable by reuse** — this issue must either land
  the helper itself (which [[BUG-2421]] then adopts) or scope inline. Coordinate ordering
  with BUG-2421.
- **Canonical idiom to mirror:** `post_tool_use.py:_maybe_auto_commit()` (lines 91–134):
  `git add <abs-path>` (one explicit path) → re-run `git status --porcelain` →
  `other = [ln for ln in out.splitlines() if filename not in ln]` → bail before
  committing if `other` is non-empty. Bash twin at `hooks/scripts/issue-auto-commit.sh:59`.
  Both `info.path` (site 1) and `original_path` (site 2) are already in scope at the
  commit sites but currently unused for staging — the scoped path is readily available.
- **Correction:** `_get_main_repo_baseline()` returns a `set[str]` of **bare file
  paths** (`line[3:].strip()`, rename-arrow handled), not full `--porcelain` lines — the
  two-char status codes are stripped during parsing, so a delta reuse must compare on
  paths, not raw porcelain.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-30.

**Selected**: Option 2 — minimal floor (stage only the issue file, modeled on
`_maybe_auto_commit()`).

**Reasoning**: The worker's actual code diff is already merged/committed by
`merge_coordinator` *before* `_complete_issue_lifecycle_if_needed()` runs, so both
completion commits are genuinely frontmatter-only follow-ups — there is no multi-file
"attributable delta" left to preserve, which removes Option 1's only completeness
advantage. `info.path` / `original_path` are already in scope at both sites, so Option 2
is a localized two-call-site swap; Option 1 would require a new `WorkerResult` field plus
`to_dict`/`from_dict` changes and a `MergeCoordinator` change (one of four call sites,
`_wait_for_completion():1228`, holds only a bare issue-ID string), and its "recompute at
commit time" fallback is semantically broken under concurrent workers sharing one
`GitLock`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 — attributable delta | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |
| Option 2 — minimal floor | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option 1: `_get_main_repo_baseline()` / `_detect_main_repo_leaks()` exist verbatim
  (`worker_pool.py:1386` / `:1218`), but the baseline `set[str]` never reaches
  `WorkerResult` today — threading it needs a new serialized field plus a
  `MergeCoordinator` retention change, and a recompute cannot reconstruct a pre-worker
  baseline under concurrency (shared `GitLock`, other workers' uncommitted state leaks in).
- Option 2: mirrors the tested `_maybe_auto_commit()` idiom (`post_tool_use.py:91-134`)
  and its bash twin (`issue-auto-commit.sh:59-69`); `info.path` / `original_path` are
  already bound at both sites; because the lifecycle commit is frontmatter-only,
  issue-file-only staging is exactly the correct scope.

**Implementation note**: model the *actual* `_maybe_auto_commit()` precedent —
`git add -- <path>` → `git status --porcelain` filtered by filename → warn/skip on other
dirty paths. Do **not** implement the stricter `git diff --cached` + `git reset HEAD --`
mechanism described earlier in this issue: the evidence agents confirmed that verify/reset
form has zero precedent in the codebase.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` imports
  `ParallelOrchestrator` (line 301) and constructs it (lines 207, 309). This is the
  **`ll-parallel` CLI entry point**, so both patched sites (`:1024`, `:1417`) run on
  every `ll-parallel` invocation. [Agent 1 finding]
- `scripts/little_loops/cli/sprint/run.py` — imports `ParallelOrchestrator` (line 20)
  and constructs it (line 606) inside `_cmd_sprint_run()` for **multi-issue sprint
  waves**; `ll-sprint run` multi-issue waves therefore exercise both patched sites too
  (single-issue waves take the sequential `process_issue_inplace()` path and do not).
  [Agent 1 finding]
- `scripts/little_loops/parallel/__init__.py` — re-exports `ParallelOrchestrator`
  (line 19) as public API; import-surface only, no change needed. [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._handle_completion()`
  (`:288–322`) is what actually **invokes `_on_worker_complete` as a callback**
  (`callback(result)` at `:317`) inside a `try/except Exception` that only logs and
  **never re-raises** (`:318–319`); the callback's return is discarded. Implication for
  the fix: a new "skip + warn on unexpected dirty state" branch (mirroring
  `_maybe_auto_commit`) cannot propagate an exception past this wrapper — it degrades to
  a log line exactly as today, and no caller relies on `_on_worker_complete()`
  raising/returning. Likewise all four callers of `_complete_issue_lifecycle_if_needed()`
  discard its `bool` return, and the current impl already returns `True` unconditionally
  even when the commit `returncode != 0` (`orchestrator.py:1451`, only a warning at
  `:1441`) — so "skip-and-warn" fits the existing caller-observable contract with zero
  downstream changes. [Agent 2 finding]

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

  _Added by `/ll:refine-issue` — codebase analysis:_
  - Existing `test_orchestrator.py` tests will **not** catch this bug as written: the
    `temp_repo_with_config` fixture (`test_orchestrator.py:50`, via the `make_project`
    factory in `conftest.py:140`) is plain filesystem with **no `git init`**, and current
    orchestrator tests stub `orchestrator._git_lock.run` with a fixed return value — none
    assert on the actual `git add` argument list. The new regression test must `git init`
    its own repo (mirror the `temp_git_repo` fixture at
    `test_worktree_concurrency.py:26`, or `_init_git_repo()` at
    `test_hooks_integration.py:3190`) and assert on real `git status --porcelain` /
    `git log --oneline`.
  - `test_issue_lifecycle.py::TestCommitIssueCompletion.test_successful_commit:236`
    currently asserts `["git", "add", "-A"]` is invoked — that assertion will break when
    [[BUG-2421]] lands its scoped fix; coordinate the two changes.
  - All git calls in this subsystem go through `GitLock.run()` (`git_lock.py:81`), which
    serializes on an `RLock` and retries on `index.lock` contention — scoped staging must
    keep using `self._git_lock.run([...], cwd=self.repo_path)`, not bare `subprocess.run`.

  _Wiring pass added by `/ll:wire-issue`:_
  - **Closest in-file real-git template to mirror:**
    `scripts/tests/test_orchestrator.py::TestCleanupOrphanedWorktrees::test_prunes_ghost_worktree_refs`
    (~`:701`, class ~`:660–813`) is the **one existing test in `test_orchestrator.py`
    that builds a real `git init` repo and a real `ParallelOrchestrator` inline**
    (patching `WorkerPool` / `MergeCoordinator` / `IssuePriorityQueue`). Mirror its
    scaffolding for the new git-backed regression test instead of the plain-filesystem
    `temp_repo_with_config` fixture, or lift `temp_git_repo`
    (`test_worktree_concurrency.py:25`) / `_init_git_repo()`
    (`test_hooks_integration.py:3190`). [Agent 3 finding]
  - **Assertion convention for exact `git add` argv (vs `-A`):** the `captured_commands`
    idiom at `test_issue_lifecycle.py:236` (append each `cmd` to a list, then filter with
    list-equality) is the established pattern; combine it with the
    `mock_git_run(args, cwd, **kwargs)` stub shape at `test_orchestrator.py:356` (which
    branches on `args`) — the current `test_on_worker_complete_*` /
    `test_complete_issue_lifecycle_if_needed_*` suites stub `_git_lock.run` with an
    **args-blind `lambda *a, **kw: git_ok`**, so none assert on the `git add` argument
    list today; that is the gap to close. [Agent 3 finding]
  - **Two viable test levels:** (a) *args-capture* (cheap, no real git) — assert
    `["add", "-A"]` never appears in captured commands and the scoped
    `["add", "--", "<issue-file>"]` appears exactly once; (b) *real-git* (stronger,
    catches actual over-staging) — dirty an unrelated tracked file, run the **un-stubbed**
    `_git_lock` through the completion path, then assert via `git status --porcelain` /
    `git diff --cached --name-only` that the dirty file is excluded. [Agent 3 finding]
  - **Correction to the model test cited above:**
    `test_hooks_integration.py::TestIssueAutoCommitHook::test_dirty_tree_skips_commit_prints_warning`
    asserts via `git log --oneline` commit-count `== 1` (that hook blocks **any** commit
    on a dirty tree), **not** via `git show --name-only`. The orchestrator's minimal-floor
    fix still *commits* (just scoped), so model the "which files are staged" assertion on
    `git diff --cached --name-only` / `git status --porcelain` (as used in
    `test_git_operations.py:176`, `test_worker_pool.py:1256+`), not on that hook test's
    no-commit assertion. [Agent 3 finding]
  - **Integration suites to re-run after the fix** (exercise the orchestrator through the
    CLI / sprint waves and would surface a completion-path regression):
    `scripts/tests/test_parallel_cli.py`, `scripts/tests/test_sprint.py`,
    `scripts/tests/test_sprint_integration.py`. [Agent 1 finding]

### Documentation
- N/A — internal automation behavior.

_Wiring pass added by `/ll:wire-issue`:_ confirmed **no doc requires updating** — a broad
sweep of `docs/ARCHITECTURE.md`, `docs/development/MERGE-COORDINATOR.md`,
`docs/reference/{API,CLI,COMMANDS,HOST_COMPATIBILITY}.md`, `docs/guides/{SPRINT_GUIDE,BUILTIN_HOOKS_GUIDE}.md`,
`docs/development/TROUBLESHOOTING.md`, all 7 `commands/*.md` that mention `ll-parallel`, and
`skills/*/SKILL.md` found none describing the
`_on_worker_complete()` / `_complete_issue_lifecycle_if_needed()` staging behavior. Two
**do-not-conflate non-targets** (leave unchanged): [Agent 2 finding]
- `docs/development/MERGE-COORDINATOR.md` § "Lifecycle File Move Coordination" narrates an
  illustrative `_commit_pending_lifecycle_moves()` (pseudo-code — the name is not in
  `merge_coordinator.py`; the real mechanism is stash-exclusion pathspecs in
  `MergeCoordinator`, not `git add -A` in `ParallelOrchestrator`). Unrelated to this fix.
- `commands/commit.md:76` already says "Use `git add` with specific files (never use `-A`
  or `.`)" for the **interactive** `/ll:commit` flow — a pre-existing, already-aligned
  precedent to cite, not a code path this fix changes.

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_ confirmed **no schema/config change needed** —
`config-schema.json`'s `parallel` block (~`:305–380`) has no key governing git-staging
scope or commit strictness, and `issues.auto_commit` / `issues.auto_commit_prefix`
(`:240`, `:245`) gate a **different** mechanism (`post_tool_use.py::_maybe_auto_commit()`
for interactive issue-file edits), not `ll-parallel` worker-completion commits. [Agent 2 finding]

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

_Added by `/ll:refine-issue`:_ Step 1 is **resolved** — the leak pass runs per-worker
**before** `_on_worker_complete()` and does not re-run at the commit sites (see the
Proposed Solution research findings), so skip the "verify ordering" question and scope
the two `git add -A` calls directly. For Step 4, note the existing `test_orchestrator.py`
fixture is not a real git repo (see Tests findings) — the regression test must stand up
its own `git init` repo to make real `git status` / `git log` assertions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be accounted for in the
implementation:_

5. **Scope-gap — the `should_close` branch also over-stages via the BUG-2421 defect.**
   `_on_worker_complete()` has a **third branch, `if result.should_close:`
   (`orchestrator.py:934`), evaluated *before* the `elif result.success:` branch that
   contains the `:1024` site**. It lazily imports `close_issue` (`:936`) and calls it
   (`:942–949`); `close_issue()` (`issue_lifecycle.py:555`) calls `_commit_issue_completion()`
   (`:632`) → the **unscoped `git add -A` at `issue_lifecycle.py:369`** that [[BUG-2421]]
   targets. The **same pattern repeats in `_merge_sequential()`'s `should_close` branch
   (`orchestrator.py:1170–1183`, the P0-sequential path)**. **Consequence:** scoping only
   `:1024` and `:1417` does **not** fully close `_on_worker_complete()`'s (or
   `_merge_sequential()`'s) own exposure to unscoped staging — the close-issue path stays
   vulnerable until [[BUG-2421]] lands. Resolve one of two ways: **(a)** sequence/land
   [[BUG-2421]] together so the `close_issue → _commit_issue_completion` path is scoped
   too, or **(b)** explicitly narrow AC #1's wording to the frontmatter-fallback path and
   note the close-issue path is covered by [[BUG-2421]] (see the amended AC #1 below).
6. Add the regression test using the **args-capture** and/or **real-git** models in the
   Tests section (mirror `test_prunes_ghost_worktree_refs` for the real-git fixture;
   assert scoped `git add -- <issue-file>` and the absence of `add -A`).
7. Re-run the integration suites listed in Tests (`test_parallel_cli.py`,
   `test_sprint.py`, `test_sprint_integration.py`) after the change.

## Acceptance Criteria

- [x] `_on_worker_complete()` (feature-branch frontmatter fallback) no longer stages
      files unrelated to the issue — now routes through `_stage_and_commit_issue_scoped()`.
- [x] `_complete_issue_lifecycle_if_needed()` no longer stages files unrelated to the
      issue — now routes through `_stage_and_commit_issue_scoped()`.
- [x] Pre-existing dirty files in the main repo remain uncommitted after a
      worker's fallback completion (proven by `test_..._excludes_unrelated_dirty_file`).
- [x] A regression test proves an unrelated dirty main-repo file is excluded from
      the parallel completion commit (`TestScopedCompletionStaging`, real-git fixture).
- [x] Both orchestrator sites use one shared implementation — the new private
      `_stage_and_commit_issue_scoped()` helper. (A cross-file helper shared with
      [[BUG-2421]]'s `_commit_issue_completion()` is a future consolidation; the two
      call git differently — `GitLock.run` here vs bare `subprocess.run` there.)

_Wiring pass added by `/ll:wire-issue`:_
- [x] **AC #1 scope caveat** — resolved by scoping. AC #1 is read as scoped to the
      frontmatter-fallback path (the two `self.repo_path` `git add -A` sites in
      `orchestrator.py`), which this fix closes. The `should_close` branch's residual
      exposure via `close_issue → _commit_issue_completion` (`issue_lifecycle.py`'s
      unscoped `git add -A`) is **out of scope here and delegated to [[BUG-2421]]**;
      the regression test asserts only the fallback path is scoped. A full "no unrelated
      staging on *any* `_on_worker_complete()` branch" guarantee lands with [[BUG-2421]].

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

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-06-30). Anchors
cross-verified by two independent research agents against current
`orchestrator.py` / `worker_pool.py`._

### Anchors verified (still accurate)
- `orchestrator.py:1024` — `self._git_lock.run(["add", "-A"], cwd=self.repo_path)`
  in `_on_worker_complete()` feature-branch path. **Confirmed.**
- `orchestrator.py:1417` — the `["add", "-A"]` token of the multi-line call
  spanning `1416–1419` in `_complete_issue_lifecycle_if_needed()`. **Confirmed.**
- `_complete_issue_lifecycle_if_needed()` is a **self-contained reimplementation**
  (does NOT delegate to `issue_lifecycle.complete_issue_lifecycle()`): it appends
  its own `## Resolution` block, writes frontmatter via `update_frontmatter`, calls
  `append_session_log_entry(..., "ll-parallel")`, then stages `-A`. **Confirmed.**
- Call sites of `_complete_issue_lifecycle_if_needed()` — all four reach the single
  `add -A` at `:1417`: `:977` (feature-branch, `terminal_status="in_progress"`),
  `:1056` (non-feature-branch merge success), `:1198` (`_merge_sequential()`, P0
  sequential path), `:1228` (`_wait_for_completion()` drain). **Confirmed.**
- The issue-file path is already in scope at both sites: `info.path` at `:1024`,
  `original_path` at `:1417` — so the minimal-floor fix (`git add -- <issue-file>`)
  needs no new plumbing.

### Resolves Implementation Step 1 — leak detection does NOT guard these commits
`_get_main_repo_baseline()` (`worker_pool.py:1386`) and `_detect_main_repo_leaks()`
(`worker_pool.py:1218`) run **only inside `WorkerPool._process_issue()`** (baseline
capture at `:352`, leak-detect at `:535`, cleanup at `:543`) — on the background
worker thread, **before** the `WorkerResult` is returned. `_on_worker_complete()`
fires via `future.add_done_callback` strictly **after** that result exists, so both
orchestrator `add -A` sites (`:1024`, `:1417`) execute *after* leak detection has
already finished, and it does **not** re-run. **The fix therefore cannot rely on
leak detection — it must scope staging directly at the two commit sites.**

### Constraint on reusing the baseline primitive (Proposed Solution §1)
`_get_main_repo_baseline()` returns a `set[str]` of **bare file paths** (status
codes stripped via `line[3:].strip()`, rename-arrows resolved), not raw porcelain
lines. It is captured in `worker_pool` (a different component/thread), so computing
an "attributable delta" in the orchestrator would require **threading the baseline
set through `WorkerResult` or recomputing it** at commit time. This makes the
delta-based approach meaningfully more work than the minimal-floor approach — see
`decision_needed` below.

### Shared-helper status (Proposed Solution / AC #5)
**No `stage_issue_scoped()` helper exists yet** — [[BUG-2421]] has not landed;
`issue_lifecycle.py:_commit_issue_completion()` (`:349`, `add -A` at `:369`) still
uses the unscoped sweep (with no `cwd`). If the helper is later extracted, note the
two sites invoke git differently: the orchestrator uses `self._git_lock.run(...)`
(`GitLock`, thread-serialized via `RLock`) while `issue_lifecycle.py` uses bare
`subprocess.run(...)`. A shared helper must accept a **runner callable** to bridge
both.

### Strongest fix pattern to model
`hooks/post_tool_use.py:_maybe_auto_commit()` (`:91–155`): stage one path with
`git add -- <path>`, verify with `git diff --cached --name-only` that *only* that
path is staged, `git reset HEAD -- <path>` and bail if the scope is violated, then
`git commit -- <path>`. This is the concrete minimal-floor implementation for both
orchestrator sites.

### Regression-test model
Model on `test_hooks_integration.py::TestIssueAutoCommitHook::test_dirty_tree_skips_commit_prints_warning`
plus the `temp_git_repo` fixture at `test_worktree_concurrency.py:25`. Assert commit
contents via `git show --name-only --format= HEAD`: the unrelated dirty file absent,
the issue file present. Extend the existing `test_on_worker_complete_*`
(~`test_orchestrator.py:1687+`) and `test_complete_issue_lifecycle_if_needed_*`
(~`:2742`) suites.

### Decision resolved (`decision_needed: false`)
The Proposed Solution presented two genuinely distinct options with a real
cost/completeness tradeoff, sharpened by the ordering finding above:
- **Option 1 — attributable delta** (Proposed Solution §1): completeness win, but
  requires threading `_get_main_repo_baseline()`'s set through `WorkerResult` (or a
  recompute) since leak detection doesn't guard these sites.
- **Option 2 — minimal floor** (Proposed Solution §2): trivial (`info.path` /
  `original_path` already in hand), models `_maybe_auto_commit()`, but stages only
  the issue file rather than the full attributable delta.

> **Selected:** Option 2 — minimal floor — both completion commits are frontmatter-only
> (the code diff is already merged by `merge_coordinator` beforehand), so the issue file
> is the complete attributable change set and Option 1's threading cost buys nothing here.

Decided by `/ll:decide-issue` on 2026-06-30 — see the **### Decision Rationale** block
at the end of `## Proposed Solution` for scoring and evidence.

## Resolution

- **Action**: fix
- **Completed**: 2026-07-01
- **Status**: done (implemented via `/ll:manage-issue`)
- **Approach**: Option 2 — minimal floor, per the recorded decision.

### Changes Made
- `scripts/little_loops/parallel/orchestrator.py`
  - Added private helper `_stage_and_commit_issue_scoped(issue_id, issue_path, commit_msg)`
    that stages **only** the issue file (`git add -- <path>`), then checks
    `git status --porcelain` for any *other* dirty/staged path and **skips the commit
    with a warning** if found — mirroring `hooks/post_tool_use.py:_maybe_auto_commit`.
    Returns the commit `CompletedProcess`, or `None` when skipped. The skip is
    self-protecting under concurrent workers sharing one `GitLock`.
  - `_on_worker_complete()` feature-branch frontmatter fallback: replaced
    `git add -A` + commit with a call to the helper (guards the `None`/`returncode`
    branches).
  - `_complete_issue_lifecycle_if_needed()`: replaced `git add -A` + commit with a call
    to the helper; returns `True` on skip (frontmatter is still written to the file),
    preserving the existing caller-observable contract.
  - The third `git add -A` at the interrupted-worktree recovery site was **left
    unchanged** — it stages against an isolated `info.worktree_path`, not the main repo,
    so recovering all of that worktree's WIP is the intended behavior.

### Verification Results
- New regression coverage in `scripts/tests/test_orchestrator.py`
  (`TestScopedCompletionStaging`, backed by a new `real_git_orchestrator` fixture that
  stands up a **real** `git init` repo with an un-stubbed `GitLock`):
  - `test_complete_lifecycle_commit_excludes_unrelated_dirty_file` — an unrelated dirty
    main-repo file is never committed (fails Red on `git add -A`).
  - `test_on_worker_complete_feature_branch_excludes_unrelated_dirty_file` — same for the
    feature-branch fallback path.
  - `test_complete_lifecycle_commit_is_scoped_to_issue_file` — clean tree still produces a
    commit containing **only** the issue file.
- TDD Red→Green confirmed (2 tests failed with `AssertionError` before the fix, all pass
  after).
- `test_orchestrator.py`, `test_parallel_cli.py`, `test_sprint.py`,
  `test_sprint_integration.py` — all pass (277).
- Full suite: 13298 passed; the single failure (`test_all_skills_within_limit`:
  `skills/manage-issue/SKILL.md` = 523 > 500 lines) is **pre-existing and unrelated** (no
  skill file was touched by this fix).
- `ruff check`, `ruff format --check`, `mypy` clean on changed files.

### Commits
- See `git log --oneline` for the scoped completion commit (source + test + this issue
  file only; the sibling [[BUG-2421]] changes present in the working tree were
  deliberately **not** swept in — the very hygiene this fix enforces).

## Session Log
- `/ll:manage-issue` - 2026-07-01T04:04:06Z - `3d7d4b7c-0998-4d5d-89d0-05189e85c357.jsonl`
- `/ll:ready-issue` - 2026-07-01T03:44:57 - `f2b563fe-acae-472f-942a-b6cf769740e2.jsonl`
- `/ll:confidence-check` - 2026-07-01T03:41:54 - `cbb70290-2b30-4d37-91f5-4b7f426bbf3d.jsonl`
- `/ll:wire-issue` - 2026-07-01T03:33:44 - `9e29c6de-af90-4630-8aa9-6f566215bf87.jsonl`
- `/ll:decide-issue` - 2026-07-01T03:19:59 - `b1d80d1f-950b-4ab3-8971-1af05b6c69db.jsonl`
- `/ll:refine-issue` - 2026-07-01T03:09:31 - `cf5f2bcf-d3a5-4187-8235-a0ad5fd723e0.jsonl`
- `/ll:refine-issue` - 2026-07-01T03:07:55 - `55bf24de-5192-4d0e-ba1f-250ed1f1abb1.jsonl`
- `/ll:format-issue` - 2026-07-01T03:00:50 - `b9ed8d80-9a10-4d8a-a32b-74c42018cb90.jsonl`
- `/ll:capture-issue` - 2026-07-01T02:55:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/457ad308-c7c0-49a8-936f-f80f8ed18900.jsonl`
