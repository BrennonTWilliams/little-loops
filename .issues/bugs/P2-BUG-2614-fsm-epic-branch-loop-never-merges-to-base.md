---
id: BUG-2614
type: BUG
priority: P2
status: done
captured_at: '2026-07-12T17:56:40Z'
completed_at: '2026-07-12T19:43:14Z'
discovered_date: 2026-07-12
discovered_by: capture-issue
relates_to:
- ENH-2601
- EPIC-2575
decision_needed: false
confidence_score: 96
outcome_confidence: 66
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

### FSM Plumbing Design

_Added by `/ll:confidence-check` follow-up — resolves the "new FSM-side
plumbing" outcome risk flagged during confidence check, before implementation
starts:_

The orchestrator's two pieces of instance state
(`_merged_epic_branches`, `_epic_branch_verify_failures`) exist to solve
problems specific to `WorkerPool`'s concurrency model, not general merge-back
requirements — the FSM `finalize` state doesn't need equivalents:

- **No idempotency set needed.** `_merged_epic_branches` exists because
  `_maybe_complete_epic` (orchestrator.py:1227) fires once per worker
  completion event, so the same epic branch can be evaluated many times in
  one run and must not be double-merged. `finalize` has no such fan-in — it
  runs exactly once per loop execution, after all resolved children are
  already `done`. Idempotency instead comes for free from git: because
  `_merge_epic_branch_to_base` deletes the branch on success
  (orchestrator.py:1412-1416), the extracted free function (or its caller in
  `finalize`) should `git rev-parse --verify epic/<id>` first and no-op if
  the branch no longer exists — no marker file, no persisted set.
- **No failure-accumulation dict needed.** `_epic_branch_verify_failures`
  exists because the orchestrator runs many workers concurrently and needs
  to accumulate verify failures across the whole run for
  `_report_results()` to report in aggregate at the end. `finalize` is a
  single synchronous shell block, not concurrent — it can capture the
  extracted verify function's result inline and write it straight to a
  run_dir artifact, following the exact convention `verify` already
  established for `verify-verdict.txt` (read back by `finalize` at the
  `VERIFY_VERDICT=$(cat "$RUN_DIR/verify-verdict.txt" ...)` line). Write the
  merge outcome to a sibling `$RUN_DIR/epic-merge-verdict.txt` and fold it
  into `finalize`'s existing `VERDICT` computation the same way
  `VERIFY_VERDICT` is folded in today.

This means the extracted free functions (Option A) should be **stateless** —
no idempotency-set or failure-dict parameters — with `ParallelOrchestrator`
keeping its own instance state as thin wrappers around them, and the FSM
side relying on git branch existence + a run_dir verdict file instead of
replicating the orchestrator's in-memory bookkeeping.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` (~line 835) — lazy-imports `worktree_utils` for
  per-state worktree attach (ENH-2609) and carries a doc-comment referencing
  `_verify_epic_branch_before_merge`'s "explicit-cwd idiom" as design precedent. Once that
  method is renamed/moved to a free function, this comment's symbol name goes stale —
  update it alongside the extraction.
- `scripts/little_loops/parallel/worker_pool.py` (`_ensure_epic_branch`,
  `_setup_worktree`/`_cleanup_worktree`, lines ~684-787, 1619-1743) — the `ll-parallel`
  sibling consumer of `worktree_utils` free functions; not a call site of the two methods
  being extracted, but confirms the free-function shape must keep working for this caller
  too.
- `scripts/little_loops/parallel/merge_coordinator.py` (lines ~625, 879) — uses
  `epic_branch` as a merge base; downstream consumer of the same branch-naming convention,
  worth a sanity check that merge-back doesn't change branch lifecycle assumptions here.
- `scripts/little_loops/parallel/types.py` (`EpicBranchesConfig`, lines 312-338;
  `WorkerResult.epic_branch`, lines 72, 94) and `scripts/little_loops/config/automation.py`
  (`EpicBranchesConfig.from_dict`, lines ~50-129) — the config dataclass/bindings backing
  `merge_to_base_on_complete`/`verify_before_merge`; no field changes expected, but confirm
  the extracted free functions consume this dataclass the same way the current instance
  methods do.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` § `parallel.epic_branches` (~line 412) — the
  block's `"description"` reads "Per-EPIC integration branch configuration for
  ll-parallel/ll-sprint (FEAT-2447)", and `verify_before_merge`'s own description says
  "Inert until ENH-2603 reads it" — both are scoped to the `ll-parallel`/`ll-sprint` path
  only and go stale once the FSM loop also honors `merge_to_base_on_complete`/
  `verify_before_merge`. Update both description strings as part of this fix.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `EpicBranchesConfig` (~line 3300-3329) — names
  `ParallelOrchestrator._verify_epic_branch_before_merge` explicitly and documents
  `_merged_epic_branches`/`epic_branch_verify_failures` as orchestrator-instance state;
  needs updating to reflect the new free-function name/location once extracted.
- `docs/ARCHITECTURE.md` § Parallel Mode (~line 461-481) — the paragraph beginning
  "`epic_branches` also has an FSM-loop-side consumer outside this `WorkerPool` path
  (ENH-2601)" explicitly states the FSM loop only creates the branch and never merges it —
  this asserts the current (buggy) behavior this issue is fixing and must be rewritten.
- `docs/guides/LOOPS_REFERENCE.md` § `auto-refine-and-implement` (~line 903-926) — documents
  the current flow diagram (`checkout_epic_branch → delegate → verify → finalize`) with no
  merge-back step, and frames the FSM path as "a separate, already-wired code path" from
  `ll-parallel`/`ll-sprint` — both the diagram and that framing need revision.
- `docs/development/MERGE-COORDINATOR.md` (~line 149-159) and `docs/guides/SPRINT_GUIDE.md`
  § Per-EPIC Integration Branch (~line 309-349) — document `merge_to_base_on_complete`/
  `verify_before_merge`/`open_pr` behavior scoped to `ll-parallel`/`ll-sprint`; low risk but
  candidates for a cross-reference once the FSM loop path honors the same knobs.
- `CHANGELOG.md` — per project convention (no `[Unreleased]` section; new entries land under
  a concrete version), add an entry for this fix under a future version section during
  release prep, not now.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worktree_utils.py` — the direct test-pattern template for the two
  newly-extracted free functions: real `git init` repos via `_init_repo`/`_git` helpers, one
  class per function, explicit-kwargs calls, plus a `_FakeGitLock` variant for the
  `git_lock`-only path (no real git). No new free-function test module exists yet for
  `_merge_epic_branch_to_base`/`_verify_epic_branch_before_merge` — follow this file's
  class-per-function shape when adding one (either in this file or a sibling).
- **No test currently calls `_merge_epic_branch_to_base`/`_verify_epic_branch_before_merge`
  by name** — `TestEpicCompletionMerge` and `test_report_results_surfaces_epic_verify_gate_failures`
  both go through `_maybe_complete_epic` / direct dict assignment, so a signature change to
  free functions should not break them **provided** the thin wrapper still routes git calls
  through `self._git_lock` (the `_capture_git` monkeypatch target at
  `test_orchestrator.py` line ~1341-1355).
- Two tests assert the exact verify-failure message format verbatim (`"test_cmd failed
  (exit ...)"`, `"verify-gate worktree setup failed: ..."`, `test_orchestrator.py`
  ~line 1613-1660) — preserve these strings verbatim if verify logic moves into a free
  function, or update the assertions in lockstep.
- `scripts/tests/test_builtin_loops.py` `test_verify_attaches_epic_worktree` and
  `test_finalize_computes_closures_from_epic_branch` (~line 2003-2075) assert literal
  substrings (`"epic-branch-name.txt"`, `"checkout_existing=True"`, `"ls-tree"`) inside the
  `verify`/`finalize` action text — these will need updating in lockstep once `verify`'s
  action is simplified to call the shared function and `finalize`'s action gains the
  merge-back step.
- **No `TestFinalizeEpicMergeConfigReadShell`-style test exists** — new coverage needed,
  combining `TestCheckoutEpicBranchConfigReadShell`'s technique (extract `finalize`'s
  `action:` string, substitute `${context.run_dir}`, run via `subprocess.run(["bash", "-c",
  action], ...)` against a real `git init` repo) with `TestEpicCompletionMerge`'s assertions
  (`git branch --list` / `git merge-base --is-ancestor` to confirm merge landed, negative
  cases for hold-open conditions). This directly satisfies Proposed Solution item 4.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update the doc-comment in `scripts/little_loops/fsm/executor.py` (~line 835) that names
   `_verify_epic_branch_before_merge` — keep the symbol reference accurate after extraction.
6. Update `config-schema.json`'s `parallel.epic_branches` description and `verify_before_merge`
   description — both are currently scoped to "ll-parallel/ll-sprint" only and go stale once
   the FSM loop honors these fields too.
7. Update `docs/reference/API.md` § `EpicBranchesConfig`, `docs/ARCHITECTURE.md` § Parallel
   Mode, and `docs/guides/LOOPS_REFERENCE.md` § `auto-refine-and-implement` — all three
   currently document the FSM loop as merge-less; each needs a revision pass once the fix
   lands.
8. Add a `TestFinalizeEpicMergeConfigReadShell`-style test class to `test_builtin_loops.py`
   (hybrid of `TestCheckoutEpicBranchConfigReadShell` + `TestEpicCompletionMerge`, see Tests
   section) — no existing test exercises "FSM loop merges epic branch to base on
   completion" end-to-end.
9. Update the literal substring assertions in `test_builtin_loops.py`'s
   `test_verify_attaches_epic_worktree` / `test_finalize_computes_closures_from_epic_branch`
   in lockstep with the `verify`/`finalize` action-text changes.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 66/100 → MODERATE

### Outcome Risk Factors
- Moderate per-site depth: extracting `_merge_epic_branch_to_base`/`_verify_epic_branch_before_merge` into free functions requires new FSM-side plumbing to replace the instance-bound `_merged_epic_branches` idempotency set and `_epic_branch_verify_failures` reporting dict — this state has no direct precedent in `worktree_utils.py`'s existing extractions, so the shape of that plumbing (marker file vs. run_dir artifact) will likely need a judgment call during implementation.
- Breadth spans 6-15 sites (orchestrator, loop YAML, config-schema, three doc files, two test files) — plan to work through the enumerated Integration Map sequentially rather than attempting a single sweep, to keep the lockstep test/doc updates from drifting.

## Resolution

Implemented BUG-2614 per the decided Option A:

- Extracted `_verify_epic_branch_before_merge`, `_merge_epic_branch_to_base`, and
  `_open_pr_for_epic_branch` out of `ParallelOrchestrator` into stateless free
  functions (`verify_epic_branch_before_merge`, `merge_epic_branch_to_base`,
  `open_pr_for_epic_branch`) in `scripts/little_loops/worktree_utils.py`, following
  the `setup_worktree`/`cleanup_worktree`/`detect_default_branch` precedent.
  `ParallelOrchestrator`'s methods became thin wrappers around them, preserving
  `_merged_epic_branches`/`_epic_branch_verify_failures` instance state.
- Added a new `merge_epic_branch` state to `auto-refine-and-implement.yaml`,
  running between `verify` and `finalize`. It reads `epic-branch-name.txt` (and
  the newly-persisted `base-branch-name.txt`, written by `checkout_epic_branch`),
  gates on `parallel.epic_branches.merge_to_base_on_complete`/`open_pr` and
  `compute_epic_progress`'s all-children-done check, then calls the shared free
  functions directly. Idempotency comes from git branch existence (no persisted
  marker needed, since the state runs once per loop execution) per the issue's
  FSM Plumbing Design. Writes `epic-merge-verdict.txt`, folded into
  `finalize`'s `summary.json` as an additive `epic_merge_verdict` field.
- Simplified the `verify` state to call `verify_epic_branch_before_merge`
  instead of its prior inline reimplementation, resolving the duplication noted
  in the issue's Codebase Research Findings.
- Updated `fsm/executor.py`'s stale doc-comment, `config-schema.json`'s
  `epic_branches`/`verify_before_merge` descriptions, and
  `docs/reference/API.md`, `docs/ARCHITECTURE.md`,
  `docs/guides/LOOPS_REFERENCE.md`, `docs/development/MERGE-COORDINATOR.md`,
  `docs/guides/SPRINT_GUIDE.md` per the Wiring Phase checklist.
- Added direct unit tests for the three free functions
  (`test_worktree_utils.py`), an end-to-end `TestMergeEpicBranchConfigReadShell`
  class exercising `merge_epic_branch` against a real git repo
  (`test_builtin_loops.py`), and updated `test_orchestrator.py`'s
  `TestEpicBranchVerifyGate` patch targets to point at
  `little_loops.worktree_utils` instead of `little_loops.parallel.orchestrator`.

Full test suite: 14744 passed, 36 skipped, 1 pre-existing unrelated failure
(`TestPixiDataVizLoop::test_required_top_level_fields`, confirmed failing on
`main` before this change). `ruff check`/`ruff format --check`/`mypy` clean
(one pre-existing unrelated `mypy` stub warning for `wcwidth`).

## Session Log
- `/ll:manage-issue` - 2026-07-12T19:42:47Z - `000ba01e-76b0-4308-a39e-fdaf76f9715c.jsonl`
- `/ll:ready-issue` - 2026-07-12T19:14:04 - `8da43f9a-1c54-41f1-8035-83a965d9133b.jsonl`
- `/ll:confidence-check` - 2026-07-12T18:40:00Z - `db791533-d20c-493a-b5e5-1773772b3319.jsonl`
- `/ll:wire-issue` - 2026-07-12T18:26:06 - `cdc63a6f-8ccf-4d77-bbb5-c7eb9cd913ec.jsonl`
- `/ll:decide-issue` - 2026-07-12T18:16:47 - `fd507ca6-f6ac-4d56-a4aa-00d02d4bd4d7.jsonl`
- `/ll:refine-issue` - 2026-07-12T18:11:47 - `0cd51379-016c-4304-a451-38c176f37044.jsonl`
- `/ll:capture-issue` - 2026-07-12T17:56:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/655a2464-a4d4-4557-b538-8038528dc56f.jsonl`

---

## Status

- [x] Done
