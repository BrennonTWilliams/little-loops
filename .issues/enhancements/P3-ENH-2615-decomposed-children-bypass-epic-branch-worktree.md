---
id: ENH-2615
type: enhancement
priority: P3
status: done
captured_at: '2026-07-12T17:56:40Z'
completed_at: '2026-07-12T20:47:37Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to:
- BUG-2614
- ENH-2601
- EPIC-2575
depends_on:
- BUG-2614
decision_needed: false
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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
   scope rather than only resolving once in `resolve_set`. Implement the
   re-check as a **generic per-iteration re-attach primitive in
   `fsm/executor.py`** (extending the existing single-shot `state.worktree`
   attach, lines 823-931, to re-evaluate on each sub-loop cycle-back rather
   than only on entry), not as epic-specific logic folded into
   `autodev.yaml`'s dequeue loop — `autodev` must stay usable as a generic
   loop outside epic-scoped runs. See the Mechanism Decision Addendum below.
2. Alternatively (simpler, less invasive): have the decomposition step
   itself check whether the issue being decomposed is currently being
   worked inside an epic-branch worktree (e.g. via `context.run_dir` /
   captured epic branch name) and, if so, ensure the new issue's file and
   subsequent implementation commits are made against that same worktree.
3. Add regression coverage: an epic-scoped FSM run where one child is
   decomposed mid-run should result in the decomposed follow-up's commits
   also landing on the epic branch, not `base_branch`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

4. Update `scripts/tests/test_sprint.py::
   test_load_or_resolve_nested_epic_grandchild_depth_mismatch` — flip the
   `not in` assertion and rewrite the docstring before/alongside the
   `sprint.py` transitive-walk change, or the test suite breaks on merge.
5. Update `scripts/tests/test_builtin_loops.py::
   test_enqueue_children_moves_parent_to_completed` to assert the
   `ll-issues finalize-decomposition` CLI invocation instead of literal
   `mv`/`completed` shell text once `autodev.yaml` is rewired.
6. Add a CLI-level test for `cmd_finalize_decomposition`'s
   `--children-file` flag path (currently untested) if `autodev.yaml`'s
   `enqueue_children` invokes it that way.
7. Sequence or rebase around `BUG-2614`, which touches overlapping
   regions of the same `auto-refine-and-implement.yaml` file.
8. Update `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`, and
   `docs/ARCHITECTURE.md` per the Documentation subsection above once the
   transitive re-check lands.

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

### Mechanism Decision Addendum

Decided 2026-07-12 (post-confidence-check discussion), resolving the open
plumbing-shape question flagged in Outcome Risk Factors.

Two shapes were considered for where Option A's mid-run re-attach logic
lives:

- **Push into `autodev.yaml`'s dequeue loop**: reuses the existing
  per-issue iteration point (`dequeue_next` → `implement_current` →
  `detect_children`/`enqueue_children`). Rejected — `autodev` is a general-
  purpose loop used outside epic-scoped runs; folding epic-branch
  semantics into it would couple a generic loop to epic-specific state
  (`epic-branch-name.txt`), against this project's stated preference to
  keep general-purpose loop cores decoupled from feature-specific
  integrations.
- **Selected — generic per-iteration re-attach primitive in
  `fsm/executor.py`**: extend the existing single-shot `state.worktree`
  attach (currently bound to sub-loop entry/exit, lines 823-931) to
  re-evaluate on each sub-loop cycle-back, exposed as a primitive any
  `loop:` state can opt into — not epic-specific. `auto-refine-and-implement.yaml`'s
  `delegate` state opts in; `autodev.yaml` remains untouched and reusable.
  Cost: this is new FSM plumbing with no existing precedent (confirmed —
  no `foreach`/`for_each`/iterate state type exists in `schema.py`), so it
  is being built from scratch rather than adapted, which is what the
  Outcome Confidence "Complexity" criterion already scores as Deep/
  architectural for this piece.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `state.worktree` attach
  (~lines 823-931) is currently single-shot per `loop:` sub-loop entry;
  per the Mechanism Decision Addendum, extend it into a generic
  per-iteration re-attach primitive any `loop:` state can opt into.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `resolve_set`
  (lines 90-139) resolves `issue_set` once via `SprintManager.load_or_resolve`;
  `checkout_epic_branch` (lines 142-221) creates the epic branch keyed only
  off `scope`; `delegate` (lines 224-247) opts `delegate`'s `loop:` into the
  new executor re-attach primitive instead of attaching once.
- `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()`
  (lines 286-349); EPIC backward-membership lookup at line 326 is
  `info.parent == epic_id` (direct-only).
- `scripts/little_loops/loops/autodev.yaml` — `detect_children`/
  `enqueue_children` (~lines 525-591): still needs wiring to call
  `ll-issues finalize-decomposition` so decomposed children's `parent:`
  gets repointed to the EPIC (parent-repoint half of Option A). Per the
  Mechanism Decision Addendum, `autodev.yaml` gets **no** epic-branch/
  worktree-awareness changes — that logic lives in the executor primitive
  instead, so `autodev` stays usable as a generic loop.
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` (`_cmd_sprint_run`) — the sole
  production caller of `SprintManager.load_or_resolve`; treats
  `Sprint.issues` as the exhaustive membership set for `ll-sprint run
  <EPIC-ID>`. Switching `load_or_resolve`'s backward lookup from
  direct-only to transitive silently enlarges this set for any EPIC with
  sub-EPIC intermediaries — no code change needed here, but `ll-sprint
  run`'s behavior changes as a side effect of the `sprint.py` fix.
- `scripts/little_loops/loops/rn-decompose.yaml` (lines 214-230,
  `finalize_parent` state) — structural precedent for the new
  `finalize-decomposition` call site: `ll-issues finalize-decomposition
  "$ID" ... || echo "WARN: ... failed"`. `autodev.yaml`'s new call site
  should mirror this bash `||`-fallback, WARN-not-fail shape.

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

### Sequencing Note

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/bugs/P2-BUG-2614-fsm-epic-branch-loop-never-merges-to-base.md`
  (currently open) is a concurrently-scoped fix against the *same loop
  file* (`auto-refine-and-implement.yaml`), touching overlapping regions
  (`checkout_epic_branch` lines 142-221, `finalize` lines 348-531 per
  BUG-2614 vs. `resolve_set`/`delegate` lines 90-139/224-247 per this
  issue) and the same `epic-branch-name.txt` run-dir artifact. Not a code
  dependency, but a same-file merge-conflict risk — sequence the two
  implementations or rebase carefully.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **BUG-2614 is now `status: done`**, resolved today by commit `cb1d2ff2`
  ("fix(loops): merge FSM epic-branch runs back to base on completion"), so
  the merge-conflict-risk framing above is moot — there is nothing left to
  sequence against. All line numbers in this issue's Integration Map are
  stale as a result: `resolve_set` is now **98-148**, `checkout_epic_branch`
  now **150-236**, `delegate` now **238-261**, and a **new
  `merge_epic_branch` state was inserted at line 359** (between `verify` at
  263 and `finalize`, which is now **495-687**), calling a new free function
  `worktree_utils.merge_epic_branch_to_base` to auto-merge the epic branch
  to `base_branch` on completion. `autodev.yaml`'s `detect_children`/
  `enqueue_children` are now at lines 525/563 respectively.
  `parallel/orchestrator.py:_maybe_complete_epic` is now at line 1227
  (called from `_on_worker_complete` at line 1129); its epic-branch-merge
  logic was extracted into the same new `worktree_utils.merge_epic_branch_to_base`.
- **New coupling risk, sharper than the stale merge-conflict note above —
  verified directly against `merge_epic_branch`'s implementation**:
  `merge_epic_branch`'s completion gate (`auto-refine-and-implement.yaml:417-424`)
  calls `issue_progress.py:compute_epic_progress(epic_id, all_issues)`,
  which uses the **already-transitive** `parent:`-chain walk
  (`_issue_descends_to`) — the same helper this issue's Option A proposes
  adopting for `sprint.py`. It does **not** read `resolve_set`'s captured
  `issue_set` output at all; it re-derives EPIC membership fresh from disk
  on every run, so the two fixes are *not* coupled through shared stale
  state as originally hypothesized. The real risk is narrower: the
  `all_done` gate (lines 429-438) only counts issue **status**
  (done/blocked/cancelled via transitive membership) — it has no notion of
  *where* a child's commits actually live. A child bypassed from the
  epic-branch worktree (this issue's core bug) can still be marked `done`
  and will satisfy `all_done` even though its commits landed on
  `base_branch` instead of the epic branch. `merge_epic_branch` will then
  merge-and-delete the epic branch believing the epic is complete, while
  the bypassed child's work is stranded outside it — turning a
  hand-recoverable gap (today) into a race against an automatic branch
  deletion. This does not require sequencing with a shared code path, but
  the regression test in item 3 of Proposed Solution should assert the
  bypassed child's commits land on the epic branch *before* `merge_epic_branch`
  runs, not just eventually.
- **Confirms Outcome Risk Factor #1 (no existing mid-run re-attach hook)**:
  `autodev.yaml` has zero `worktree:` attributes anywhere (grep-confirmed)
  and the FSM schema (`schema.py`) has no `foreach`/`for_each`/`iterate`/
  `dispatch_each` state type — loop-back inside `autodev` is a plain
  `next:` edge with no attachable hook. `delegate` is a single generic
  `loop:` state, not a per-issue primitive; the only per-issue iteration in
  the call chain (`autodev`'s `dequeue_next` → `implement_current` →
  `detect_children`/`enqueue_children` loop-back) is entirely
  worktree-blind. Implementing Option A therefore requires either
  restructuring `delegate` into a per-issue re-attaching loop, or pushing
  worktree-awareness down into `autodev.yaml`'s dequeue loop — both are new
  plumbing, confirming this is being built from scratch rather than adapted
  from a working analog.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `SprintManager` method table entry for
  `load_or_resolve(arg)` documents it as "forward (`relates_to:`) +
  backward (`parent:`) lookup" without specifying depth; update to note
  the lookup is now transitive. Also update the one-line scope description
  for `little_loops.recursive_finalize` ("Powers `ll-issues
  finalize-decomposition`. ... for `rn-implement` loops") once `autodev`
  becomes a second caller.
- `docs/guides/LOOPS_REFERENCE.md` — `auto-refine-and-implement` **Notes**
  paragraph ("the backlog set is resolved once upfront... decomposition
  children created mid-run are still processed depth-first by `autodev`,
  but brand-new unrelated issues... are not picked up") needs a caveat
  once `resolve_set` re-checks before each `delegate` dispatch; the
  adjacent **Epic-branch awareness** paragraph (ENH-2601/ENH-2609) also
  describes `resolve_set` as a single upfront resolution.
- `docs/ARCHITECTURE.md` — § Parallel Mode epic-branches FSM-consumer
  paragraph (~lines 476-481) is the top-level doc for the "everything for
  this epic lands on one branch" guarantee; review for consistency once
  the re-check lands.

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

_Wiring pass added by `/ll:wire-issue`:_

**Will break — must update before merging:**
- `scripts/tests/test_sprint.py::TestSprintManagerLoadOrResolve::
  test_load_or_resolve_nested_epic_grandchild_depth_mismatch` (lines
  2607-2659) explicitly asserts *today's* direct-only semantics by name
  (`assert "FEAT-030" not in result.issues`) and its docstring cites
  FEAT-2449 as documenting the exact depth mismatch this issue closes.
  Once `sprint.py:326`'s `info.parent == epic_id` becomes transitive, this
  assertion flips to `in` and the docstring must be rewritten (it will no
  longer document a mismatch — the fixture, EPIC-800 → EPIC-801 →
  FEAT-030, is directly reusable for a positive-case test instead).
- `scripts/tests/test_builtin_loops.py::test_enqueue_children_moves_parent_to_completed`
  (line 4328) currently asserts literal `mv`/`completed`-directory shell
  text; once `autodev.yaml`'s `enqueue_children` is wired to call
  `ll-issues finalize-decomposition` (which owns the move), this
  assertion needs rewriting to check for the CLI invocation instead
  (mirror `test_rn_decompose.py::test_finalize_parent_writes_decomposed_and_calls_cli`,
  lines 462-467, which asserts `"ll-issues finalize-decomposition" in
  action`).

**New tests to write (no existing coverage found):**
- Transitive multi-hop positive case for `sprint.py`'s new walk — mirror
  `test_issue_progress.py::TestFindNearestEpicAncestor::
  test_find_nearest_epic_ancestor_multi_hop` (3-level chain shape).
- Cycle-guard test for `sprint.py`'s transitive walk — mirror
  `test_find_nearest_epic_ancestor_cycle_guard`.
- Re-resolution-before-each-delegate-dispatch coverage in
  `test_builtin_loops.py::TestAutoRefineAndImplementLoop` — no existing
  test covers re-resolving `issue_set` per dispatch (only the single
  upfront `resolve_set` call is covered today); closest template is
  `test_delegate_uses_autodev_engine` (line 1964).
- `autodev.yaml` `enqueue_children` → `finalize-decomposition` wiring —
  new test class mirroring `test_rn_decompose.py`'s
  `TestDecomposeOutcomeChannel` (lines 454-479), specifically
  `test_finalize_parent_writes_decomposed_and_calls_cli` and
  `test_enqueue_children_routes_to_finalize_parent` as direct templates.
- CLI-level test for `cmd_finalize_decomposition`'s `--children-file` flag
  path — only the underlying `finalize_decomposed_parent()` function is
  unit-tested today (`test_recursive_finalize.py::test_epic_relink`, line
  58, already covers the re-link logic itself); no test exercises the CLI
  wrapper's `--children-file` argparse path, which `autodev.yaml`'s
  `enqueue_children` would need (it writes `autodev-new-children.txt`
  before invoking the CLI).

## Impact

- **Priority**: P3 — real but narrower than BUG-2614; only affects runs
  where mid-run decomposition happens, and the symptom (work on `main`
  instead of the epic branch) is recoverable by hand.
- **Effort**: Medium — depends on how `resolve_set`/`delegate` currently
  track scope membership; may share plumbing with whatever fixes BUG-2614.
- **Risk**: Low — additive scope-tracking, no change to existing
  single-pass runs where no decomposition occurs.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- The core mechanism requires new FSM/executor plumbing: `fsm/executor.py`'s per-state worktree attach (lines 823-931, now the ~843-931 range per the latest refine pass) is single-shot per `loop:` sub-loop entry, and `delegate` (`auto-refine-and-implement.yaml`, now lines 238-261) is a single dispatch rather than a per-issue loop — there is no existing mid-run re-attach hook to extend, so this piece is being built from scratch rather than adapted from a working analog.
- `BUG-2614` is now `status: done` (resolved by commit `cb1d2ff2`), so the same-file merge-conflict risk noted in the prior confidence check is moot. The latest refine pass found a sharper successor risk instead: `merge_epic_branch`'s `all_done` completion gate (`auto-refine-and-implement.yaml` lines 429-438) only checks child issue **status** via the already-transitive `compute_epic_progress`, not *where* a child's commits actually live. A child bypassed from the epic-branch worktree (this issue's core bug) can still be marked `done` and satisfy `all_done`, so `merge_epic_branch` will merge-and-delete the epic branch believing the epic is complete while the bypassed child's work is stranded outside it — turning today's hand-recoverable gap into a race against automatic branch deletion. The regression test in Proposed Solution item 3 should assert the bypassed child's commits land on the epic branch *before* `merge_epic_branch` runs, not just eventually.

## Session Log
- `/ll:manage-issue` - 2026-07-12T20:45:52 - `b31c00f9-985d-45de-aa20-d70f9b50fbc7.jsonl`
- `/ll:ready-issue` - 2026-07-12T20:28:34 - `881a3711-eccb-472f-92ac-c015b72d899a.jsonl`
- `/ll:confidence-check` - 2026-07-12T20:05:00 - `5624c811-df63-4139-960d-93c84c19aa3d.jsonl`
- `/ll:refine-issue` - 2026-07-12T19:57:41 - `162d5b1a-2001-465b-9835-16e49a83f527.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-12T18:59:02 - `a45a3236-b4e2-46cd-877b-3ea30a21a1cb.jsonl`
- `/ll:confidence-check` - 2026-07-12T18:35:00 - `ed5881db-0c47-4ffd-b7ce-e1fc3a469244.jsonl`
- `/ll:wire-issue` - 2026-07-12T18:28:00 - `db791533-d20c-493a-b5e5-1773772b3319.jsonl`
- `/ll:decide-issue` - 2026-07-12T18:18:49 - `7b3fe18c-193f-40f6-8a43-7e55f5445577.jsonl`
- `/ll:refine-issue` - 2026-07-12T18:14:03 - `fd507ca6-f6ac-4d56-a4aa-00d02d4bd4d7.jsonl`
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Resolution

- **Status**: Implemented (Option A per Decision Rationale)
- **Closed**: 2026-07-12
- **Plan**: `thoughts/shared/plans/2026-07-12-ENH-2615-management.md`

**Changes**:
- `scripts/little_loops/sprint.py` — `load_or_resolve`'s backward EPIC lookup
  is now transitive: reuses `issue_progress.build_parent_map` /
  `_issue_descends_to` (the `_maybe_complete_epic` mechanism), with the parent
  map spanning all statuses so done intermediates still chain; membership
  stays active-only. Grandchildren under sub-EPICs/decomposed intermediates
  now resolve into the set.
- `scripts/little_loops/loops/autodev.yaml` — `enqueue_children` and
  `enqueue_or_skip` now close the decomposed parent via
  `ll-issues finalize-decomposition --children-file` (WARN-not-fail, mirroring
  `rn-decompose`'s `finalize_parent`) instead of a raw `git mv`, so children's
  `parent:` is repointed to the EPIC and the EPIC's `relates_to:` stays
  accurate.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — new
  `recheck_set` state: after each `delegate` pass on an EPIC scope, re-resolve
  the descendant set, diff against a cumulative dispatched ledger, and cycle
  new descendants back into `delegate` (capped at 5 re-dispatches); `finalize`
  now sizes `parked_rate` from the ledger. Non-EPIC scopes keep the single
  upfront resolution.
- **Mechanism Decision Addendum deviation (documented)**: no new
  `fsm/executor.py` primitive was needed — the ENH-2609 worktree attach is
  already per-entry (attach on entry, detach in `finally`), so the
  `recheck_set → delegate` cycle-back re-attaches the same epic branch for
  free. Pinned by a new characterization test
  (`TestSubLoopWorktree::test_loop_state_reentry_reattaches_worktree`).
- `skills/issue-size-review/SKILL.md` unchanged: drafting
  `parent: [PARENT-ID]` remains correct as lineage; the autodev path repoints
  at finalize, and standalone decompositions are picked up by the transitive
  walk at the next resolution.
- Tests: flipped `test_load_or_resolve_nested_epic_grandchild_depth_mismatch`
  to a positive transitive test + multi-hop/done-intermediate/cycle-guard
  cases (`test_sprint.py`); finalize-decomposition wiring + `recheck_set`
  structure/routing/ledger tests (`test_builtin_loops.py`); CLI
  `--children-file` coverage (`test_recursive_finalize.py`). Note: the
  issue's pointer to `test_enqueue_children_moves_parent_to_completed` was
  mis-attributed — that test covers `recursive-refine.yaml` (out of scope,
  unchanged).
- Docs: `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/ARCHITECTURE.md` updated for the transitive lookup and per-dispatch
  re-resolution.

**Verification**: full suite 14756 passed / 36 skipped; `ruff check` clean;
mypy clean except a pre-existing unrelated `wcwidth` stubs error;
`ll-loop validate autodev` and `ll-loop validate auto-refine-and-implement`
both valid.

## Status

- [x] Completed
