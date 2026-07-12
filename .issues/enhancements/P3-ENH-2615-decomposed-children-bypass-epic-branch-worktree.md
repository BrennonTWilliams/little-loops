---
id: ENH-2615
type: enhancement
priority: P3
status: open
captured_at: '2026-07-12T17:56:40Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to: [BUG-2614, ENH-2601, EPIC-2575]
decision_needed: false
---

# ENH-2615: Mid-run decomposed children bypass the epic-branch worktree

## Summary

`auto-refine-and-implement.yaml` resolves an EPIC's child issue set once, in
`resolve_set` (lines 90-139), and captures it as `issue_set` for the rest of
the run. If `/ll:refine-issue` (or the loop's own refine sub-pass) decomposes
one of those children into a new follow-up issue mid-run, the new issue has
no mechanism attaching it to the epic-branch worktree that `delegate`
(lines 224-247) set up for the original `issue_set` — its work lands wherever
the ambient checkout/working tree happens to be (typically `base_branch`)
instead of on `epic/<EPIC-ID>-<slug>`.

Confirmed on `EPIC-2575`: ENH-2612 ("code_query config block") was
decomposed from ENH-2577 (a declared EPIC-2575 child) during a run, but its
implementation commit (`4c4dcc79`) landed directly on `main`, not on the
epic branch — even though ENH-2577 was actively part of the resolved
`issue_set` on that run.

## Current Behavior

A child decomposed mid-run has `parent:` set to the original child (e.g.
`parent: ENH-2577`) but is otherwise treated as an untracked, unscoped issue
by the epic-branch machinery — its `relates_to`/scope membership isn't
re-derived from its `parent` chain, so `delegate`/worktree routing has no
way to know it belongs to the in-progress epic run.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The proximate cause is narrower than "no worktree attachment mechanism":
  `autodev.yaml`'s own decomposition path (`detect_children`/`enqueue_children`,
  `scripts/little_loops/loops/autodev.yaml` ~lines 525-591) already re-folds
  newly-discovered children into the active processing queue *within* the
  same `delegate`-attached worktree — children decomposed **inside** the
  single `autodev` sub-loop call already land on the epic branch. The actual
  gap is (a) `parent:` on those children is never repointed to the EPIC
  (only `rn-decompose.yaml`'s `finalize_parent` state, ~lines 218-232, calls
  `ll-issues finalize-decomposition` →
  `scripts/little_loops/recursive_finalize.py:finalize_decomposed_parent`,
  lines 110-210, which `autodev.yaml` never invokes), and (b) any
  decomposition/resolution that happens *outside* that one `delegate` call
  (e.g. a standalone `/ll:refine-issue`/`/ll:issue-size-review` run against a
  child between runs) has no epic-branch attachment step at all.
- `resolve_set`'s EPIC membership resolution
  (`scripts/little_loops/sprint.py:SprintManager.load_or_resolve`, backward
  lookup at line 326) is a **direct-only** backward scan
  (`info.parent == epic_id`), unlike the transitive `parent:`-chain walk
  already implemented in `scripts/little_loops/issue_progress.py`
  (`find_nearest_epic_ancestor` line 80, `_issue_descends_to` line 104) and
  used by `ll-parallel`'s `_maybe_complete_epic`
  (`scripts/little_loops/parallel/orchestrator.py` lines 1256-1279). Even a
  naive "re-run resolve_set mid-loop" fix would miss grandchildren unless
  it's switched to the transitive helper.

## Expected Behavior

When a child of an in-progress epic-scoped run is decomposed into a new
issue, that new issue's own implementation work should also land on the
epic branch — either by re-resolving `issue_set` to include newly-discovered
descendants before each `delegate` iteration, or by having decomposition
itself detect an active epic-branch context and route the new issue's work
into the same worktree.

## Motivation

This is the same class of gap as [[BUG-2614]] (epic-branch work not making
it back to base) but on the other end: pre-declared children get *into* the
branch correctly; children created by decomposition after the run starts do
not. Because decomposition is a normal, expected part of `/ll:refine-issue`
(splitting an underspecified issue into a scoped-down original plus
follow-ups), this isn't a rare edge case — it's likely to recur on every
epic run where a child needs decomposition, silently fragmenting the
"everything for this epic lands on one branch" guarantee the feature exists
to provide.

## Proposed Solution

1. In `auto-refine-and-implement.yaml`, re-check for new children with
   `parent:` pointing into the resolved `issue_set` (transitively) before
   each `delegate` dispatch, and fold them into the active worktree/branch
   scope rather than only resolving once in `resolve_set`.
2. Alternatively (simpler, less invasive): have the decomposition step
   itself check whether the issue being decomposed is currently being
   worked inside an epic-branch worktree (e.g. via `context.run_dir` /
   captured epic branch name) and, if so, ensure the new issue's file and
   subsequent implementation commits are made against that same worktree.
3. Add regression coverage: an epic-scoped FSM run where one child is
   decomposed mid-run should result in the decomposed follow-up's commits
   also landing on the epic branch, not `base_branch`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: In `auto-refine-and-implement.yaml`, re-check for new children
with `parent:` pointing into the resolved `issue_set` (transitively) before
each `delegate` dispatch, and fold them into the active worktree/branch
scope rather than only resolving once in `resolve_set`.

> **Selected:** Option A — single re-check point reusing the proven
> transitive-walk pattern from `_maybe_complete_epic`; Option B is scattered
> across four non-uniform decomposition entry points.

**Option B**: Have the decomposition step itself check whether the issue
being decomposed is currently being worked inside an epic-branch worktree
(e.g. via `context.run_dir` / captured epic branch name) and, if so, ensure
the new issue's file and subsequent implementation commits are made against
that same worktree.

**Recommended**: Option A, implemented by reusing
`scripts/little_loops/issue_progress.py`'s existing transitive walk
(`find_nearest_epic_ancestor`/`_issue_descends_to`) instead of
`sprint.py`'s direct-only backward lookup — this is the same mechanism
`ll-parallel`'s `_maybe_complete_epic` already uses to re-derive an EPIC's
live descendant set on every worker-completion event
(`scripts/little_loops/parallel/orchestrator.py:_on_worker_complete`, line
1129). Pair this with wiring `autodev.yaml`'s existing `enqueue_children`
path to call `ll-issues finalize-decomposition` (currently only invoked
from `rn-decompose.yaml`) so decomposed children's `parent:` gets repointed
to the EPIC and `relates_to:` stays accurate — without that, even a
re-resolved `issue_set` would not recognize the new child as EPIC-scoped.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option A

**Reasoning**: Option A's core scope-membership mechanism (the transitive
`parent:`-chain walk in `issue_progress.py`) is a proven, already-reused
pattern — `_maybe_complete_epic` in `parallel/orchestrator.py` solves the
structurally identical problem for `ll-parallel` runs by re-deriving an
EPIC's live descendant set from disk on every completion event. Option B's
only reusable artifact is the `epic-branch-name.txt` marker file as a read
signal, but it requires independently wiring the same check into four
non-uniform decomposition entry points (`rn-decompose.yaml`,
`autodev.yaml`'s inline states, `issue-size-review/SKILL.md`, and standalone
`/ll:refine-issue`, which has no guaranteed `context.run_dir` at all) —
scattered logic vs. Option A's single re-check point. Both options require
new FSM/executor plumbing (neither has a mid-run worktree re-attach hook
today), but Option A's gap is narrower and its non-worktree half
(scope-membership + parent-repoint via `finalize-decomposition`) is directly
reusable now.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B | 1/3 | 0/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Option A: `issue_progress.py`'s transitive walk (`find_nearest_epic_ancestor`/`_issue_descends_to`) is already used by `parallel/orchestrator.py:_maybe_complete_epic` (lines 1227-1299) for the same class of problem; `finalize-decomposition` CLI already does the parent-repoint half. Gap: `fsm/executor.py`'s `state.worktree` attach (lines 823-931) is single-shot per `loop:` sub-loop entry with no mid-run re-attach hook, and `delegate` is a single dispatch, not a per-issue loop.
- Option B: `epic-branch-name.txt` (`auto-refine-and-implement.yaml:216`) is a real, reusable read signal, but `rn-decompose.yaml`, `autodev.yaml`, `issue-size-review/SKILL.md`, and standalone `/ll:refine-issue` are four independent call sites with no shared decomposition code path — `/ll:refine-issue` has no guaranteed `run_dir` to check at all.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `resolve_set`
  (lines 90-139) resolves `issue_set` once via `SprintManager.load_or_resolve`;
  `checkout_epic_branch` (lines 142-221) creates the epic branch keyed only
  off `scope`; `delegate` (lines 224-247) attaches the worktree to `autodev`
  for the whole `issue_set` in one call — no re-resolution/re-attach hook
  exists after `delegate` starts.
- `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()`
  (lines 286-349); EPIC backward-membership lookup at line 326 is
  `info.parent == epic_id` (direct-only).
- `scripts/little_loops/loops/autodev.yaml` — `detect_children`/
  `enqueue_children` (~lines 525-591) and `enqueue_or_skip` (~lines
  699-753): re-folds new children into the flat processing queue
  (`autodev-queue.txt`) but never repoints `parent:` to the EPIC and has no
  epic-branch/worktree awareness of its own.
- `skills/issue-size-review/SKILL.md` — Phase 4 step 5 (lines 210-228)
  drafts new child frontmatter as `parent: [PARENT-ID]` where `PARENT-ID`
  is the issue being decomposed, not the EPIC.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/finalize_decomposition.py`
  (`cmd_finalize_decomposition`) → `recursive_finalize.py:
  finalize_decomposed_parent` (lines 110-210) — the only code path that
  repoints a decomposed child's `parent:` to the EPIC and updates the
  EPIC's `relates_to:` (lines 176-202). Called exclusively from
  `loops/rn-decompose.yaml`'s `finalize_parent` state (~lines 218-232), not
  from `autodev`/`auto-refine-and-implement`.
- `scripts/little_loops/fsm/executor.py` (~lines 823-931, `# ENH-2609:
  per-state worktree attach`) — interpolates `state.worktree` once on
  `loop:` sub-loop entry, tears down in a `finally` after the child FSM
  returns; no mid-child re-attach hook.

### Similar Patterns
- `scripts/little_loops/issue_progress.py` — `build_parent_map()` (line
  67), `find_nearest_epic_ancestor()` (line 80), `_issue_descends_to()`
  (line 104) implement a cycle-safe **transitive** `parent:`-chain walk
  used by `compute_epic_progress()` (line 120) and
  `parallel/orchestrator.py:_maybe_complete_epic` (lines 1256-1279) to
  re-derive an EPIC's live descendant set fresh from disk on every
  worker-completion event — directly reusable in place of `sprint.py`'s
  direct-only lookup.
- `scripts/little_loops/loops/autodev.yaml` `detect_children` (line 525) is
  the existing "snapshot pre-ids, diff post-ids, re-fold into the active
  set" shape — the queue-level analog of the scope/worktree re-check this
  issue needs, not yet wired to epic-branch scoping.
- `scripts/little_loops/parallel/orchestrator.py:_on_worker_complete` (line
  1129) → `_maybe_complete_epic` (line 1227) is the re-check-per-completion
  pattern already proven on the `ll-parallel` path (BUG-2614's counterpart).

### Tests
- `scripts/tests/test_issue_progress.py::TestComputeEpicProgress` (line 71,
  incl. `test_transitive_chain_includes_grandchildren`) and
  `TestFindNearestEpicAncestor` (line 281) — model for asserting a
  decomposed grandchild is correctly attributed to the EPIC.
- `scripts/tests/test_fsm_executor.py::TestSubLoopWorktree` (line 4872) —
  closest existing model for testing FSM-level worktree attach/detach
  behavior; a regression test for mid-run re-attach would extend this
  class.
- `scripts/tests/test_builtin_loops.py::TestAutoRefineAndImplementLoop`
  (lines 1877-2421) — existing coverage for `resolve_set`/`delegate`/
  `finalize` routing in this loop; new regression coverage belongs here.

## Impact

- **Priority**: P3 — real but narrower than BUG-2614; only affects runs
  where mid-run decomposition happens, and the symptom (work on `main`
  instead of the epic branch) is recoverable by hand.
- **Effort**: Medium — depends on how `resolve_set`/`delegate` currently
  track scope membership; may share plumbing with whatever fixes BUG-2614.
- **Risk**: Low — additive scope-tracking, no change to existing
  single-pass runs where no decomposition occurs.

## Session Log
- `/ll:decide-issue` - 2026-07-12T18:18:49 - `7b3fe18c-193f-40f6-8a43-7e55f5445577.jsonl`
- `/ll:refine-issue` - 2026-07-12T18:14:03 - `fd507ca6-f6ac-4d56-a4aa-00d02d4bd4d7.jsonl`
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Status

- [ ] Not started
