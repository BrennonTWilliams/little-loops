---
id: BUG-2614
type: BUG
priority: P2
status: open
captured_at: '2026-07-12T17:56:40Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to: [ENH-2601, EPIC-2575]
decision_needed: false
---

# BUG-2614: FSM epic-branch loop never merges the epic branch back to base

## Summary

`auto-refine-and-implement.yaml` (and its callers `sprint-refine-and-implement.yaml`
/ `autodev.yaml`) create and commit to the `epic/<EPIC-ID>-<slug>` integration
branch when `parallel.epic_branches.enabled` is `true`, but no state in that
loop ever merges the branch back to `base_branch`. The merge-back logic
(`_merge_epic_branch_to_base`, `scripts/little_loops/parallel/orchestrator.py:1388`)
exists and is fully wired for the `ll-parallel` worker-pool path
(`_maybe_complete_epic` → `_on_worker_complete`,
`scripts/little_loops/parallel/orchestrator.py:1129,1227`), but the FSM loop
path never calls it. `finalize` in `auto-refine-and-implement.yaml`
(lines 348-531) only reads from the branch (`git ls-tree` / `git grep`
against ledgers/snapshots) — it has no merge step.

Confirmed empirically on `EPIC-2575`: FEAT-2576 was implemented and marked
`done` entirely inside
`epic/epic-2575-code-knowledge-graph-adapter-query-protocol-providers-skill-integration`
(commit `53512663`), but the branch was never merged and is now several
commits behind `main` with no automatic path back.

## Current Behavior

With `parallel.epic_branches.merge_to_base_on_complete: true`:
- `ll-parallel` runs: epic branch merges to base once all children are `done`.
- `auto-refine-and-implement` / `autodev` FSM runs: epic branch is created,
  committed to, and left open indefinitely. The config flag is silently
  unhonored on this path.

## Expected Behavior

When an epic-scoped `auto-refine-and-implement` run finishes (all resolved
children `done`, per whatever gate `finalize` already uses to decide the run
is complete) and `parallel.epic_branches.merge_to_base_on_complete` is
`true`, the loop should invoke the same merge-back (and, if
`verify_before_merge` is set, the same verify gate) that `ll-parallel`
already uses, rather than leaving the branch to merge manually or never.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: `finalize` state (lines 348-531)
- **Cause**: ENH-2601 (which added epic-branch awareness to this loop) scoped
  only "checkout epic branch before delegating" + "add a post-implement
  verify state" — merge-back to base was never part of its Expected
  Behavior and no follow-up issue was filed for it. `_merge_epic_branch_to_base`
  in `scripts/little_loops/parallel/orchestrator.py:1388` is reachable only
  from `WorkerPool`'s completion callback, not from the FSM executor, so
  there is no code path connecting FSM-loop completion to the existing
  merge logic.

## Motivation

Epic branches created by `ll-parallel` self-heal (merge automatically once
children finish); epic branches created by the FSM loop path do not, and
nothing surfaces that difference to the user. The branch silently
accumulates completed work that never reaches `main`, and by the time
someone notices (as happened with EPIC-2575), the branch has drifted stale
against unrelated `main` commits, turning a simple fast-forward-able merge
into a manual reconciliation. This defeats the stated purpose of
`merge_to_base_on_complete: true` for an entire class of runs.

## Proposed Solution

Add a merge-back step to the FSM epic-branch path, reusing the existing
orchestrator logic rather than reimplementing it:

1. Extract (or directly call) `_merge_epic_branch_to_base` /
   `_verify_epic_branch_before_merge` from
   `scripts/little_loops/parallel/orchestrator.py` so both `WorkerPool` and
   the FSM `finalize` state can invoke the same merge/verify code.
2. In `auto-refine-and-implement.yaml`'s `finalize` state (or a new state
   immediately before it), when scope resolved to an EPIC and
   `parallel.epic_branches.merge_to_base_on_complete` is `true`, call that
   shared merge function once all resolved children are `done`.
3. On merge failure (or verify failure, if `verify_before_merge` is set),
   surface it the same way `orchestrator.py` does today (flag needing manual
   attention) rather than silently leaving the branch unmerged with no
   signal.
4. Add regression coverage: an FSM-driven epic run with
   `merge_to_base_on_complete: true` should end with the epic branch's
   commits present on `base_branch`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Item 1 above ("Extract (or directly call)") resolves to two concrete, mutually
exclusive shapes once `_merge_epic_branch_to_base` is confirmed to be a private
`ParallelOrchestrator` instance method with no standalone entry point today
(see Integration Map):

**Option A**: Extract `_merge_epic_branch_to_base` / `_verify_epic_branch_before_merge`
into free functions in a shared module (explicit `repo_path`, `git_lock`,
`base_branch`, `epic_branch` params, no `self`), following the precedent already
set by `setup_worktree`/`cleanup_worktree`/`detect_default_branch` in
`scripts/little_loops/worktree_utils.py`. `ParallelOrchestrator` methods become
thin wrappers calling the free functions; `finalize` (or a new pre-finalize
state) imports and calls them directly in its Python heredoc, the same way
`checkout_epic_branch` and `verify` already import `GitLock`/`setup_worktree`.

> **Selected:** Option A — matches the loop's existing free-function import
> style (`checkout_epic_branch`/`verify` already do this) and resolves the
> `verify`-state duplication in the same change; scored 10/12 vs. Option B's
> 8/12.

**Option B**: Add a new `ll-parallel` CLI flag (e.g. `--merge-epic-branch
<EPIC-ID>`) that instantiates `ParallelOrchestrator` and calls the existing
private methods directly, following the precedent of `--cleanup-orphans` /
`--prune-merged-branches` in `scripts/little_loops/cli/parallel.py:211-225,280-300`.
`finalize` would then shell out to this new flag instead of importing Python
directly.

**Recommended**: Option A — it also lets the `verify` state (which already
duplicates `_verify_epic_branch_before_merge` inline per its own code comment)
be simplified to call the extracted function instead of maintaining a second
copy, fixing an existing duplication in the same change rather than adding a
third. Option B is lower-risk (no signature changes to `ParallelOrchestrator`)
but leaves the `verify`-state duplication unresolved and adds a CLI flag whose
only caller is this loop.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option A — extract `_merge_epic_branch_to_base` /
`_verify_epic_branch_before_merge` into free functions.

**Reasoning**: Both options reuse the target orchestrator methods and have a
structural precedent elsewhere in the codebase, but Option A matches the
*target loop's own local convention*: `checkout_epic_branch` and `verify` in
`auto-refine-and-implement.yaml` already import free functions
(`detect_default_branch`, `setup_worktree`/`cleanup_worktree`) directly into
inline Python heredocs — no FSM loop anywhere shells out to `ll-parallel`
today, so Option B would introduce a third, unprecedented invocation style
into a loop where the two sibling epic-branch states already agree on
direct-import. Option A also collapses the `verify` state's self-documented
duplicate reimplementation of `_verify_epic_branch_before_merge` into the
same extracted function, fixing an existing duplication instead of leaving
it (as Option B does, by its own author's admission in this issue's text).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (extract free functions) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (CLI flag) | 1/3 | 2/3 | 2/3 | 3/3 | 8/12 |

**Key evidence**:
- Option A: `worktree_utils.py`'s `setup_worktree`/`cleanup_worktree`/
  `detect_default_branch` is the direct, already-applied precedent for this
  exact extraction shape, and `checkout_epic_branch`/`verify` already import
  those free functions into this loop's heredocs. Gap: no existing analog
  for dropping `ParallelOrchestrator`'s instance-bound
  `_merged_epic_branches` idempotency set and `_epic_branch_verify_failures`
  reporting dict into a stateless function — new FSM-side plumbing (marker
  file, run_dir artifact) is needed for those.
- Option B: `--cleanup-orphans`/`--prune-merged-branches` in
  `cli/parallel.py:211-225,280-300` is a clean structural precedent with an
  existing test template, and needs no `ParallelOrchestrator` signature
  changes (lowest risk) — but zero FSM loops shell out to `ll-parallel`
  today, it doesn't match this loop's direct-import sibling states, and it
  leaves the `verify`-state duplication unresolved.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_merge_epic_branch_to_base` (line 1388),
  `_verify_epic_branch_before_merge` (line 1323), and `_open_pr_for_epic_branch` (line 1429) are
  all **instance methods of `ParallelOrchestrator`** (`class ParallelOrchestrator:` at line 65),
  not standalone functions and not `WorkerPool` methods. They are bound to `self._git_lock`,
  `self.repo_path`, `self.parallel_config`, `self.br_config`, `self.logger`, and the
  `self._merged_epic_branches` idempotency set — none can be imported and called with just
  `(epic_id, epic_branch, repo_path, base_branch)` today. Extracting them into free functions
  (explicit `repo_path`/`git_lock`/`base_branch` params, no `self`) is the same shape already
  used for `setup_worktree`/`cleanup_worktree`/`detect_default_branch` in
  `scripts/little_loops/worktree_utils.py:21,63,178` — see Similar Patterns below.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` state (lines 348-531)
  is a pure `shell` action (bash + Python heredoc), not `check_semantic`/`llm_structured`, with no
  explicit `on_error:`/routing shown; it only reads closure state via `git ls-tree`/`git grep`
  against the epic branch — it contains **no `git merge` or `git push` call anywhere**. A new
  state (or an addition to `finalize`) is needed to actually perform the merge.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `checkout_epic_branch` state
  (lines 142-222) computes `base = cfg.parallel.base_branch or detect_default_branch(...)`
  locally (line 200) and **never persists it** to a run_dir artifact or FSM `capture` — later
  states (`verify`, `finalize`) only read the epic branch name back via
  `run_dir / "epic-branch-name.txt"` (written at line 216). A merge step needs `base_branch`
  threaded forward the same way (e.g. write it into `epic-branch-name.txt` alongside the branch
  name, or a sibling `base-branch-name.txt`).

#### Dependent Files (Callers)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:19-32` — `delegate` state passes
  `scope: "${context.sprint_name}"` into `auto-refine-and-implement`, so a fix to `finalize`
  automatically covers this caller.
- `scripts/little_loops/loops/autodev.yaml` — sequential automation loop that also delegates into
  `auto-refine-and-implement`.
- `scripts/little_loops/parallel/orchestrator.py:1128-1129` — inside `_on_worker_complete`
  (starts line 967), the existing `ll-parallel` trigger:
  `if self.parallel_config.epic_branches.enabled and result.epic_branch: self._maybe_complete_epic(...)`
  — this is the logic the FSM path needs an equivalent of.

#### Similar Patterns (Extraction Precedent)
- `scripts/little_loops/worktree_utils.py:1-5` (module docstring: "Used by ll-parallel, ll-sprint,
  and ll-loop to create and remove isolated git worktrees") — `setup_worktree`, `cleanup_worktree`,
  `detect_default_branch` were previously pulled out of `WorkerPool`/`ParallelOrchestrator` into
  free functions taking explicit params, precisely so both class-based callers and FSM shell-state
  heredocs could use them without instantiating the class. This is the direct precedent for
  extracting `_merge_epic_branch_to_base` / `_verify_epic_branch_before_merge` the same way.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `verify` state (lines 249-336)
  already **reimplements** (rather than calls) `_verify_epic_branch_before_merge` — its comment
  explicitly says it "mirrors orchestrator._verify_epic_branch_before_merge" and imports
  `GitLock`, `setup_worktree`/`cleanup_worktree` directly in an inline Python heredoc. This is the
  same duplication class this bug's merge gap continues; fixing both by extraction (rather than
  patching `finalize` with another parallel reimplementation) avoids a third copy of this logic.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `checkout_epic_branch` state
  (line 144 comment) similarly documents "mirrors `WorkerPool._ensure_epic_branch`,
  `worker_pool.py:1707-1743`" rather than calling it — a third instance of the same pattern.
- `scripts/little_loops/cli/parallel.py:211-225,280-300` — `--cleanup-orphans` and
  `--prune-merged-branches` CLI flags already construct `ParallelOrchestrator`/`WorkerPool`
  outside the normal `.run()` loop purely to invoke one internal method
  (`orchestrator._cleanup_orphaned_worktrees`, `pool.prune_merged_feature_branches`) as a
  standalone operation — the closest existing precedent for exposing
  `_merge_epic_branch_to_base` via a CLI entry point callable from a `shell` state, if extraction
  into a free function is not preferred.
- `scripts/little_loops/cli/loop/info.py:1272-1324` (`cmd_promote_baseline`) +
  `scripts/little_loops/cli/loop/__init__.py:837-843,928-929` — shows the `ll-loop <subcommand>`
  shape for exposing standalone Python logic to shell states, as an alternative CLI surface if a
  new subcommand is preferred over adding to `ll-parallel`.

#### Tests
- `scripts/tests/test_orchestrator.py` `TestEpicCompletionMerge` (lines 1331-1530) and its
  `make_epic_orchestrator` fixture (line 150) — existing coverage for the `ll-parallel` merge
  path: all-children-done merge, child-not-done holds branch open, blocked/cancelled-child
  gating, partial-failure gate scoping, `merge_to_base_on_complete=False` no-op, PR-vs-merge
  branching, idempotency across repeated calls. Use as the template for the new FSM-side test's
  assertions.
- `scripts/tests/test_orchestrator.py` `test_report_results_surfaces_epic_verify_gate_failures`
  (line 2829) — models the "flag, don't silently fail" surfacing pattern
  (`self._epic_branch_verify_failures[epic_id]`, flushed via `logger.warning` in `_report_results`
  at lines 1668-1674) that item 3 of the Proposed Solution should mirror on the FSM side.
- `scripts/tests/test_builtin_loops.py` `TestCheckoutEpicBranchConfigReadShell` (lines 2600-2679)
  — the model for the new regression test in item 4 of the Proposed Solution: loads the loop
  YAML, extracts a state's `action:` string, substitutes `${context.*}` placeholders, runs it with
  `bash -c` against a real `tmp_path` git repo, and asserts on real `git branch`/`git log` output.
  Sibling class `TestAutoRefineAndImplementLoop` (line 1878) covers YAML-parse-only routing
  assertions (no subprocess) for the same loop — useful for asserting the new merge state's
  wiring without executing git.

## Impact

- **Priority**: P2 — the config flag is silently non-functional for an
  entire, real execution path (any epic worked via the FSM loop rather than
  `ll-parallel`), and the failure mode is "completed work quietly never
  reaches base" rather than a loud error.
- **Effort**: Medium — the merge/verify logic already exists and is proven;
  this is primarily plumbing a call from the FSM `finalize` state plus
  extracting the orchestrator functions into a shared location.
- **Risk**: Low-medium — touches the epic-completion path for both
  `ll-parallel` and FSM loops if the extraction isn't careful to preserve
  existing `ll-parallel` behavior exactly.

## Session Log
- `/ll:decide-issue` - 2026-07-12T18:16:47 - `fd507ca6-f6ac-4d56-a4aa-00d02d4bd4d7.jsonl`
- `/ll:refine-issue` - 2026-07-12T18:11:47 - `0cd51379-016c-4304-a451-38c176f37044.jsonl`
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Status

- [ ] Not started
