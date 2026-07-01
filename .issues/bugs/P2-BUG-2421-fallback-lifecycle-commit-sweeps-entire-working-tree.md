---
id: BUG-2421
title: Fallback lifecycle completion commits entire working tree via git add -A
type: BUG
priority: P2
status: open
captured_at: "2026-07-01T02:00:57Z"
discovered_date: 2026-07-01
discovered_by: capture-issue
labels: [bug, loop, git, lifecycle, hygiene]
relates_to: [BUG-1800, BUG-1976, BUG-2424]
decision_needed: true
---

# BUG-2421: Fallback lifecycle completion commits entire working tree via `git add -A`

## Summary

When an issue's `/ll:manage-issue` subloop exits before cleanly completing (host
CLI crash, timeout, or context exhaustion), the lifecycle safety-net
`complete_issue_lifecycle()` marks the issue `done` and commits — but it stages
the change with `git add -A`, sweeping **every** untracked and modified file in
the working tree into the issue's "completion" commit. Unrelated in-flight work
from other sessions/branches gets entangled into a single issue's commit under a
misleading message.

## Current Behavior

`_commit_issue_completion()` (`scripts/little_loops/issue_lifecycle.py:369`)
runs:

```python
subprocess.run(["git", "add", "-A"], ...)
```

This stages the whole tree, then commits with the issue-scoped message. All four
completion paths call this helper:

- `complete_issue_lifecycle()` — line 705 (fallback / early-exit)
- close path — line 632
- defer path — line 797
- undefer path — line 947

**Observed instance:** in `rn-implement` run `rn-implement-20260630T193234`, the
ENH-2411 subloop exited before completion. The fallback commit `642e8e82`
("improve(enhancements): implement ENH-2411 — Automated fallback commit -
command exited before completion") swept up ~11 unrelated files that happened to
be dirty in the tree: `BUG-2417/2418/2419`, `ENH-2408/2415`, `EPIC-2412`,
`FEAT-2413/2414/2416` issue stubs, and a **372-line `FEAT-2390` policy-rubric
issue-file change** — none of which belong to ENH-2411. The genuine ENH-2411
code (`_helpers.py` +132, `test_ll_loop_display.py` +162) was correct, but it is
now indistinguishable in history from the swept-in noise.

## Steps to Reproduce

1. Leave the working tree dirty with changes that belong to other issues,
   sessions, or branches (e.g. untracked issue stubs, an in-flight edit on a
   different feature branch).
2. Run an issue through the automation path (`ll-auto` / `rn-implement` →
   `/ll:manage-issue` subloop) and have that subloop exit **before** it completes
   cleanly — host CLI crash, timeout, or context exhaustion.
3. The lifecycle safety-net `complete_issue_lifecycle()` fires and calls
   `_commit_issue_completion()`, which runs `git add -A`.
4. **Observe:** the issue's "completion" commit contains every dirty/untracked
   file in the tree, not just the issue's own `.md` file and its source/test
   changes. (Real occurrence: commit `642e8e82` for ENH-2411 swept in ~11
   unrelated files, including a 372-line FEAT-2390 change.)

## Expected Behavior

A fallback/close/defer completion commit should contain **only** the issue's own
changes:

1. The issue `.md` file itself (status/frontmatter/resolution edits).
2. The source + test changes produced while working that issue.

Pre-existing dirty state belonging to other issues, sessions, or branches must
NOT be swept into the commit. If the lifecycle helper cannot reliably attribute
which working-tree changes belong to the current issue, it should stage a
conservative, explicit path set (at minimum the issue file) and leave unrelated
changes uncommitted rather than absorbing them.

## Motivation

`git add -A` in a shared completion helper corrupts commit provenance:

- **Poisoned history / bisect** — an ENH commit that silently carries 372 lines
  of an unrelated feature breaks `git bisect` and blame attribution.
- **Premature commit of half-done work** — WIP from another session (e.g. the
  active `feat-2390-policy-rubric-engine` branch work) gets committed in a
  possibly-broken intermediate state under someone else's issue ID.
- **Silent** — the fallback path is exactly when no human is watching, so the
  pollution ships unreviewed.

This is the same failure class already filed for two other commands
([[BUG-1800]] audit-issue-conflicts, [[BUG-1976]] issue-size-review), but in a
distinct code path (`issue_lifecycle.py`) that those fixes did not touch. Worth
checking whether a single shared "stage only these paths" helper should back all
three.

## Root Cause

`scripts/little_loops/issue_lifecycle.py` → `_commit_issue_completion()` uses
`git add -A` (line 369) with no path scoping. The helper has access to
`info.path` (the issue file) but does not track the set of source/test files
touched during the issue's work, so it falls back to staging everything.

### Codebase Research Findings

_Added by `/ll:refine-issue`:_ `_commit_issue_completion()` also **returns
`True` unconditionally** on every branch — including outright `git commit`
failure and `git add` timeout — and its return value is **discarded by all four
callers**. So a mis-staged or failed commit is invisible to the lifecycle logic;
the over-staging ships silently. The same `git add -A` anti-pattern recurs at
`scripts/little_loops/parallel/orchestrator.py:1024` and `:1417` in the
`ll-parallel` path (see the Integration Map findings) — not just the one site
named here.

## Proposed Solution

Scope staging to an explicit path set instead of `-A`. Options, roughly in order
of preference:

1. **Capture-then-restore isolation.** Before the subloop runs an issue, record
   the pre-existing dirty set (`git status --porcelain`). At completion time,
   stage only paths that are (a) the issue file or (b) newly changed since the
   subloop started — i.e. `new_dirty - pre_existing_dirty`. Requires threading a
   baseline snapshot into `IssueInfo`/lifecycle context.
2. **Explicit path list.** Have the manage-issue subloop report the files it
   edited and pass them to `_commit_issue_completion()` so it can
   `git add <paths...>` precisely.
3. **Minimal floor.** At absolute minimum, when no attribution data is
   available, stage only `info.path` (`git add -- <issue file>`) and log a
   warning listing the unstaged dirty files so the operator can commit them
   deliberately — never `-A`.

Consider extracting a shared `stage_issue_scoped()` helper reused by the
audit-issue-conflicts and issue-size-review paths ([[BUG-1800]], [[BUG-1976]]) so
the fix lands once.

### Codebase Research Findings

_Added by `/ll:refine-issue` — grounding each option in existing code:_

- **Option 3 (minimal floor) is implementable today with zero threading.**
  `info.path` is already available at every call site and `_commit_issue_completion()`
  uses `info` only for `info.issue_type`. Change `git add -A` →
  `git add -- <info.path>` and log skipped dirty paths via `git status --porcelain`.
  This directly mirrors the proven idiom in
  `scripts/little_loops/hooks/post_tool_use.py:115` `_maybe_auto_commit()` (stage one
  path, then bail/warn if `git status --porcelain` shows anything else dirty). Lowest
  risk landing.
- **Option 1 (capture-then-restore) should reuse an existing primitive, not build
  a new one.** `scripts/little_loops/parallel/worker_pool.py:1386`
  `_get_main_repo_baseline()` already captures `git status --porcelain` as a `set[str]`
  and `:1218` `_detect_main_repo_leaks()` diffs `current - baseline`. Thread the
  snapshot in at `process_issue_inplace()` (`scripts/little_loops/issue_manager.py:560`),
  next to the existing `_baseline_sha` capture at `:883` (which today records only a
  commit SHA via `git rev-parse HEAD`, **not** a dirty-tree snapshot).
- **Option 2 (explicit path list) has a partial primitive.**
  `scripts/little_loops/work_verification.py:44` `verify_work_was_done()` already
  enumerates tracked changed files (`git diff --name-only`, `--cached`,
  `baseline..HEAD`) but returns only `bool` and **ignores untracked (`??`) files**.
  Extend it to also collect `git status --porcelain` untracked entries and return the
  attributable set.
- **The shared-helper suggestion is Python-only.** [[BUG-1800]] and [[BUG-1976]] were
  fixed in **Markdown SKILL bash blocks**, not Python (see Integration Map findings), so
  a `stage_issue_scoped()` helper could unify only the Python sites
  (`issue_lifecycle.py` + `orchestrator.py`), never the skill files.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()`
  (replace `git add -A` at line 369 with scoped staging); likely thread a
  pre-work dirty-tree snapshot through `complete_issue_lifecycle()`.

### Dependent Files (Callers/Importers)
- All four completion paths call `_commit_issue_completion()` within
  `issue_lifecycle.py` and must pass the scoped path set: close (line 632),
  complete/fallback (line 705), defer (line 797), undefer (line 947).
- The manage-issue subloop entry point (automation orchestrator) if a baseline
  dirty snapshot must be captured before the subloop runs.

### Similar Patterns
- [[BUG-1800]] (audit-issue-conflicts) and [[BUG-1976]] (issue-size-review)
  fixed the same `git add -A` over-staging class in other code paths. Evaluate
  extracting a shared `stage_issue_scoped()` helper backing all three.

### Tests
- `scripts/tests/test_issue_lifecycle.py` — add a regression test that dirties an
  unrelated file, runs fallback completion, and asserts the commit excludes it.

### Documentation
- N/A — internal automation behavior; no user-facing docs describe the staging
  mechanism.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**All line numbers in this issue verified accurate** against the current file —
nothing has drifted: `_commit_issue_completion()` at `issue_lifecycle.py:349`,
`git add -A` at `:369`, and the four callers at `:632` (close), `:705`
(complete/fallback), `:797` (defer), `:947` (undefer).

**Two additional `git add -A` sites exist in the `ll-parallel` path — not listed
in the Files-to-Modify above:**
- `scripts/little_loops/parallel/orchestrator.py:1024` — in `_on_worker_complete()`
  (feature-branch fallback); stages via
  `self._git_lock.run(["add", "-A"], cwd=self.repo_path)` against the **main** repo.
- `scripts/little_loops/parallel/orchestrator.py:1417` — in
  `_complete_issue_lifecycle_if_needed()`, a **separate reimplementation** of lifecycle
  completion that does NOT call `issue_lifecycle.complete_issue_lifecycle()`; also uses
  `git add -A`. (Unlike `_commit_issue_completion`, both orchestrator sites pass an
  explicit `cwd`.)
- **Scope decision for the implementer:** fix only `issue_lifecycle.py` (the ll-auto
  path this issue names) or also the two `orchestrator.py` ll-parallel sites. The
  parallel path partially mitigates via isolated worktrees + `worker_pool` leak
  detection, but `_on_worker_complete():1024` runs against the shared main repo.

**No existing Python scoped-staging helper to share.** [[BUG-1800]] and [[BUG-1976]]
were fixed in **Markdown SKILL bash blocks** — `skills/audit-issue-conflicts/SKILL.md`
(Phase 4b `MODIFIED_FILES` accumulator + Phase 5 `for f in ...; git add "$f"`) and
`skills/issue-size-review/SKILL.md` (explicit per-file `git add "<path>"`) — not Python.
A new `stage_issue_scoped()` helper would unify only the Python sites, never the skills.

**Directly reusable primitives already in the codebase:**
- `scripts/little_loops/hooks/post_tool_use.py:115` `_maybe_auto_commit()` — canonical
  "stage one path (`git add <abs-path>`), then `git status --porcelain` and bail if any
  line other than the target is dirty." Bash twin: `hooks/scripts/issue-auto-commit.sh:59`.
- `scripts/little_loops/parallel/worker_pool.py:1386` `_get_main_repo_baseline()` +
  `:1218` `_detect_main_repo_leaks()` — the capture-`porcelain`-set-then-diff pattern
  (this issue's Option 1), already implemented and tested.

**Regression-test surface (correcting/expanding the Tests entry above):**
- The existing `scripts/tests/test_issue_lifecycle.py::TestCommitIssueCompletion.test_successful_commit`
  (lines 236–263) asserts `["git", "add", "-A"]` is invoked exactly once — **this test
  will break** and must be updated as part of the fix.
- Model the new regression test on
  `scripts/tests/test_hooks_integration.py::TestIssueAutoCommitHook.test_dirty_tree_skips_commit_prints_warning`
  (init real repo → write issue file → add an unrelated dirty file → run → assert the
  commit excludes it) rather than the mocked-subprocess style; reuse the `temp_git_repo`
  real-repo fixture from `scripts/tests/test_worktree_concurrency.py:25`.
- The `worker_pool` baseline pattern is already covered by
  `scripts/tests/test_worker_pool.py::test_get_main_repo_baseline` and
  `::test_detect_main_repo_leaks_finds_leaked_files` — reuse if Option 1 is chosen.

## Implementation Steps

1. Add a pre-work dirty-tree snapshot to the lifecycle/subloop entry point.
2. Change `_commit_issue_completion()` to accept an explicit `paths` argument (or
   derive the issue-attributable set) and replace `git add -A` with a scoped
   `git add -- <paths>`.
3. Update all four callers (complete/close/defer/undefer) to pass the scoped set.
4. Fall back to staging only the issue file + a warning when no snapshot exists.
5. Add a regression test that dirties an unrelated file, runs the fallback
   completion, and asserts the commit does NOT include the unrelated file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete additions to the steps above:_

- **Update the now-failing existing test in Step 5.**
  `test_issue_lifecycle.py::TestCommitIssueCompletion.test_successful_commit:236`
  asserts `["git", "add", "-A"]`; it must change to the scoped `git add -- <path>`
  invocation.
- **New step — decide `orchestrator.py` scope.** Either fix the two ll-parallel sites
  (`orchestrator.py:1024`, `:1417`) in the same pass or file a follow-up; they are the
  `ll-parallel` twin of this bug.
- **If Option 3 (recommended minimal landing) is chosen, Step 1 is unnecessary** — no
  pre-work snapshot is needed because `info.path` is already in hand. Replace
  `git add -A` with `git add -- <info.path>` and log skipped dirty files via
  `git status --porcelain`.
- **Write the regression test against a real temp git repo** (assert on actual commit
  contents), not mocked subprocess — see `test_dirty_tree_skips_commit_prints_warning`
  and the `temp_git_repo` fixture.

## Acceptance Criteria

- [ ] `complete_issue_lifecycle()` no longer stages files unrelated to the issue.
- [ ] Pre-existing dirty files present before the subloop started remain
      uncommitted after fallback completion.
- [ ] Close/defer/undefer completion paths are equally scoped (no `git add -A`).
- [ ] A regression test proves an unrelated dirty file is excluded from the
      fallback commit.
- [ ] When attribution is unavailable, the helper stages only the issue file and
      logs the skipped dirty paths.

## Impact

- **Priority**: P2 — corrupts commit provenance (poisoned `git bisect`/blame,
  premature commit of unrelated WIP) in the *silent* fallback path where no human
  reviews the result. Not P0/P1 because it only triggers on abnormal subloop exit
  (crash/timeout/context exhaustion), not the normal path, and causes no data loss
  (swept files are committed, not destroyed).
- **Effort**: Small-to-medium (~half a day) — the staging change is localized to
  `_commit_issue_completion()`, but threading a pre-work dirty snapshot through the
  subloop entry and covering all four callers adds surface area.
- **Files**: `scripts/little_loops/issue_lifecycle.py` (primary);
  possibly the manage-issue subloop entry to thread the baseline snapshot;
  shared helper if unified with [[BUG-1800]] / [[BUG-1976]].
- **Risk**: Low-to-medium — changes commit staging behavior in the automation
  path; needs the regression test to lock in the exclusion.

## Session Log
- `/ll:refine-issue` - 2026-07-01T02:51:07 - `457ad308-c7c0-49a8-936f-f80f8ed18900.jsonl`
- `/ll:format-issue` - 2026-07-01T02:06:15 - `94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`
- `/ll:capture-issue` - 2026-07-01T02:00:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0404997b-7d45-4f5a-890b-78aa2a96c306.jsonl`
