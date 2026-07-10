---
id: ENH-2565
type: ENH
priority: P3
status: open
discovered_date: 2026-07-09
discovered_by: manual
decision_needed: false
confidence_score: 98
outcome_confidence: 66
score_complexity: 12
score_test_coverage: 14
score_ambiguity: 21
score_change_surface: 19
---

# ENH-2565: rn-refine — parallelize bottom-up integration and support resume from interrupted integration

## Summary

A `rn-refine` run against a 24-node, 3-deep tree timed out (4h wall-clock cap)
during the final root-node integration step. All 23 non-root nodes had already
produced a `final.md`; the timeout hit while `synth_pop` was serially
integrating internal nodes bottom-up, one node at a time. The refinement work
was fully intact but unreachable without hand-executing the remaining
integration steps. See `rn-refine-timeout-finalize-2026-07-09.md` (root of
repo, from `/ll:debug-loop-run rn-refine`) for the full incident writeup.

Immediate mitigations (timeout bump to 21600s, a `RECOVERY_NEEDED` marker when
`assemble` falls back to an un-integrated root, and per-node `final.md`
snapshots to `.loops/diagnostics/`) have already landed in `rn-refine.yaml`.
This issue tracks the two structural fixes that need real design work.

## Current Behavior

`synth_pop`/`integrate_node` (`rn-refine.yaml` ~line 264-315) dequeue and
integrate exactly one internal node per cycle, serially, even when multiple
internal nodes at the same depth have no dependency on each other. There is
also no resume path: any interruption after refinement completes but before
integration finishes forces a full re-run from `init`.

## Expected Behavior

Internal nodes whose children are all already integrated should integrate
concurrently. A run interrupted mid-integration should be resumable straight
into `synth_pop` without redoing the (potentially hours-long) refinement
phase.

## Impact

On a 24-node, 3-deep tree, serial integration (n10→n12→n1→n3, ~1,222s
cumulative) combined with a lack of resume turned a single dropped timeout
into a total loss of the integration phase's progress — the operator had to
re-run the entire loop, discarding a completed refinement tree, just to get
the last bottom-up rollup step. Any `rn-refine` run whose integration phase
alone approaches the timeout has the same failure mode.

## Scope Boundaries

In scope: `rn-refine.yaml`'s `synth_pop`/`integrate_node` states and queue
bookkeeping. Out of scope: changes to the per-node refinement phase
(`oracles/plan-node-refine`), to `ll-parallel` (issue-worktree parallelism,
not sub-loop parallelism), or to other loops.

## Problem

`scripts/little_loops/loops/rn-refine.yaml`'s `synth_pop` → `integrate_node`
flow dequeues and integrates exactly one internal node at a time
(`synth_pop`/`integrate_node` states, ~line 264-315). Internal nodes at the
same depth have disjoint children by construction, so they're independent and
safe to integrate concurrently — but the current FSM has no concurrency
primitive to express that (`ll-parallel` is the repo's only parallel
substrate today, and it's issue-worktree-shaped, not sub-loop-shaped).

Separately, there is no way to resume a run that died mid-integration. A
timeout (or any interruption) after refinement completes but before
integration finishes forces a full re-run from `init`, discarding a queue
whose refinement phase can take hours.

## Proposed Direction

1. **Parallel integration**: fan out `integrate_node` across all
   currently-poppable internal nodes (those whose children are all already
   integrated) instead of one per `synth_pop` cycle — either a worker-pool
   dispatch over `synth_queue.txt`, or multiple sub-loop workers coordinating
   through the same queue file with locking. Depth-first ordering must still
   guarantee a child is integrated before its parent is dequeued.
2. **Resume from interrupted integration**: detect (or accept a `--resume`
   flag) that `nodes/*/final.md` already exist for a completed refinement
   phase, rebuild `synth_queue.txt` from whichever internal nodes still lack a
   `final.md`, and jump straight to `synth_pop` — skipping `dequeue_next`/
   `refine_node` entirely.

Both should go through `ll:loop-specialist` for FSM design (this is a
meta-loop change to `rn-refine.yaml`) rather than being hand-patched, per the
project's meta-loop authoring rules (diagnosis-first scaffolding, non-LLM
evaluator, per-run artifact isolation).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — the integration-phase states.
  Relevant states: `init` (~line 47), `build_synth` (~line 207, the one-time
  deepest-first toposort that writes `synth_queue.txt`), `synth_pop` (~line 264,
  the flat-file dequeue), `integrate_node` (~line 285, one LLM prompt per node),
  `snapshot_node` (~line 317, durable copy to `.loops/diagnostics/`), `assemble`
  (~line 334, the `RECOVERY_NEEDED` fallback). `required_inputs: ["plan_file"]`
  (line 35) and top-of-file header flags are also in play (see Findings).
- `scripts/tests/test_rn_refine.py` — add execution-based shell tests (see Tests
  below) for both the resume queue-rebuild and the parallel-integration ordering.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/<integrate-node>.yaml` — **NEW FILE**. The
  per-node integrate-node worker sub-loop that Parallel Option B background-spawns
  (`ll-loop run oracles/<integrate-node>`). The Decision Rationale references "one
  new oracle sub-loop" but it was never listed as a deliverable. Model it on the
  sibling `oracles/plan-node-refine.yaml` shape; it is discovered by directory scan
  (no CLI/manifest registration needed) but MUST be added to `test_rn_refine.py`'s
  validates-cleanly gate (see Tests). [Agent 1 finding]

### Engine Touchpoints (potential; scope-dependent — see decision points)
- `scripts/little_loops/fsm/persistence.py` — `RESUMABLE_STATUSES` (line 46,
  `{user_stopped, running, awaiting_continuation, interrupted}`) and
  `PersistentExecutor.resume()` (line 944). A wall-clock timeout is persisted as
  `status="timed_out"` (persistence.py:917) which is **not** in
  `RESUMABLE_STATUSES`, so `ll-loop resume rn-refine` returns `None` for the exact
  incident scenario. `max_steps`/`interrupted` runs (persistence.py:913) *are*
  resumable.
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` (line 410)
  re-derives `run_dir` from the *same* `instance_id` and restores persisted
  `current_state` + `captured` + `context`.
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.__init__`
  (`self.current_state = fsm.initial`, line 193: no `--start-at`/`--from-state`
  override exists); `_execute_sub_loop` (~line 744: sub-loops run **synchronously
  inline**, one child `FSMExecutor(...).run()` on the same thread);
  `_execute_with_baseline` (~line 1831: the *only* real concurrency —
  `ThreadPoolExecutor(max_workers=2)` for the fixed harness-vs-baseline A/B arms,
  not a general fan-out).
- `scripts/little_loops/fsm/schema.py` — `StateConfig.loop` is a scalar (no
  list/`parallel:`/`fan_out:` key); a general parallel state type does not exist.
- `scripts/little_loops/fsm/concurrency.py` — `LockManager` / `ScopeLock` (~line
  124) is `fcntl.flock`-based *inter-run* mutual exclusion over `scope:` paths,
  the opposite of an intra-run fan-out primitive, but its flock idiom is the
  reusable reference if `synth_queue.txt` ever needs multi-writer locking.

### Similar Patterns / Precedents (reuse these — do not invent a new shape)
- **Loop-level resume via context-knob + init-routing** (the canonical repo
  pattern; both precedents chose this over an `--initial <state>` CLI flag):
  - `scripts/little_loops/loops/rn-build.yaml` — `context.resume_epic`/
    `resume_harness` (lines ~40), `init` emits a `RESUME_MODE:` marker routed via
    `output_contains` to a `resume` state (lines 186-205), with a multi-source
    artifact-discovery fallback in `resume_read_harness` (207-260). Rationale in
    `.issues/enhancements/P4-ENH-2016-rn-build-resume-from-epic-path.md`.
  - `scripts/little_loops/loops/rn-implement.yaml` — `context.resume` knob; `init`
    guard `[ -n "$RESUME" ] && [ -s "$RUN_DIR/queue.txt" ]` preserves an in-flight
    queue instead of re-seeding (lines 57-115).
- **Queue-file bookkeeping**: `rn-refine.yaml` `synth_pop`/`dequeue_next` already
  use the `head -1` + `tail -n +2 > tmp && mv tmp orig` pop idiom (single-writer,
  no locking today).
- **List-iteration loop shape**: `scripts/little_loops/loops/harness-multi-item.yaml`
  is the repo's discover→execute→evaluate→advance cycle over a work-list — the
  closest existing template if the integration phase is restructured around a
  readiness-checked queue.
- **Engine-level resume flag helper**: `scripts/little_loops/cli_args.py`
  `add_resume_arg()` — if Direction 2 goes the engine-level route (Option A), this
  is where a `timed_out`-aware resume flag would attach.

### Tests
- Existing coverage: `scripts/tests/test_rn_refine.py` renders each state's real
  `action:` via `little_loops.fsm.interpolation.interpolate` (`_render()`, ~line
  25) and runs it through `bash -c` against a `tmp_path` fixture tree (`_bash()`),
  asserting on resulting files/stdout — e.g. `TestBuildSynthOrder.
  test_deepest_first_order_and_leaf_backfill` (~line 333). **This is the non-LLM
  verification path AC #2/#3 require** — a synthetic `edges.tsv`/`depth_map.txt`
  tree + rendered-shell execution, no LLM self-report.
- Resume-knob structural tests to mirror: `test_rn_build.py`
  `TestRnBuildResumeState` (context knobs exist; `resume` state uses an
  `exit_code` evaluator for MR-1); `test_rn_implement.py::test_init_supports_resume`
  (~line 946, asserts `${context.resume}` and `queue.txt` in the rendered `init`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **WILL BREAK, must update.**
  `TestRnRefineRecursiveDecomposition.test_has_bottom_up_synthesis_chain` (~line
  7880) hard-asserts `for s in ("build_synth", "synth_pop", "integrate_node",
  "assemble", "final_score"): assert s in states`. If the fan-out conversion
  renames/removes `synth_pop`/`integrate_node`, this test fails.
  `test_empty_queue_routes_to_bottom_up_synthesis` (~line 7877) asserts
  `dequeue_next.on_yes == "build_synth"` — the new `resume_build_synth` entry must
  not bypass this route. This file is separate from `test_rn_refine.py` and was
  **not** in the issue's original test list. [Agent 2 finding]
- `scripts/tests/test_rn_refine.py` — add a `TestLoadsClean`-style
  validates-without-errors check for the **new** `oracles/<integrate-node>.yaml`
  (mirror `test_node_oracle_validates_without_errors`, ~line 53) via a new module
  `Path` constant; plus a `TestSynthPopReadinessGate` mirroring
  `TestBuildSynthOrder`'s `_render()`+`_bash()` shape (~line 333) with `edges.tsv` +
  partial `final.md` fixtures, and a `TestRnRefineResumeState` mirroring
  `TestRnBuildResumeState` but in this file's FSM-object attribute style
  (`_load_rn_refine().states[...]`). [Agent 3 finding]
- `scripts/tests/test_file_utils.py` — `test_concurrent_writers_via_acquire_lock`
  (~line 152, a `ThreadPoolExecutor` contention pattern) is the closest precedent
  for unit-testing the locked readiness-gated pop. **Gap:** no existing test
  exercises an FSM `shell` state that background-spawns N OS subprocesses with `&`
  plus a `wait`-barrier — `test_cli_loop_background.py::TestRunBackground` mocks a
  single `Popen`, not a real N-worker fan-out. AC #2's concurrency verification
  must be authored from scratch. [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — MR-1..MR-10 enforcement suite; re-run
  after edits to confirm the new states pass `ll-loop validate`. Note: Agent 2
  argues `rn-refine` is a **data-operating** loop (edits user plan docs), not a
  meta-loop, so MR-1..MR-10 may be inert for it — this is a scoping tension with the
  issue's "Meta-loop compliance" Findings section; confirm with
  `ll-loop validate rn-refine` rather than assuming either reading. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the canonical documented contract for
  `rn-refine` (~lines 280-347): the **context-variable table** needs a new `resume`
  row (mirror `rn-build`'s "Resume only" annotation + usage-block precedent, ~lines
  658-675); the **FSM flow ASCII diagram** hardcodes the serial
  `synth_pop → integrate_node → snapshot_node → …` chain and must show the
  fan-out/barrier shape plus the `resume_build_synth` entry point; the **Notes**
  bullet on bottom-up synthesis describes strictly sequential reassembly. Line 197
  one-line catalog entry also describes serial synthesis. [Agent 2 finding]
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — the narrative `rn-refine` prose section
  (~lines 109-125) and the family pipeline diagram (~line 63) describe bottom-up
  behavior with no resume/parallel mention. [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — line 1491 has a `name: "rn-refine"` example
  block; verify it isn't rendered stale by new state names. [Agent 2 finding]
- `CHANGELOG.md` — add an entry for this ENH under a **concrete version section**
  (not `[Unreleased]`, per project convention). [Agent 2 finding]
- `docs/reference/CLI.md` — advisory only: `ll-loop resume` / `calibrate-budget
  rn-refine` examples (~lines 736, 916-918) are generic, no functional change, but
  keep referenced state names accurate. [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_Touchpoints identified by wiring analysis that the implementation must include
beyond the primary `rn-refine.yaml` + `test_rn_refine.py` edits:_

1. Create the new `oracles/<integrate-node>.yaml` worker sub-loop and wire it into
   `test_rn_refine.py`'s validates-cleanly gate (new `Path` constant + `TestLoadsClean`
   check).
2. Update `scripts/tests/test_builtin_loops.py::TestRnRefineRecursiveDecomposition`
   — reconcile `test_has_bottom_up_synthesis_chain`'s hardcoded state-name list and
   `test_empty_queue_routes_to_bottom_up_synthesis`'s `build_synth` route assertion
   with the fan-out/resume restructure (this test breaks otherwise).
3. Update `docs/guides/LOOPS_REFERENCE.md` (context-var table + FSM flow diagram +
   Notes) and `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (prose + pipeline diagram) for
   the `resume` knob and parallel integration.
4. Add a `CHANGELOG.md` entry under a concrete version section.
5. Run `ll-loop validate rn-refine` (and validate the new oracle) to resolve the
   meta-loop-applicability question empirically before finalizing.

## Codebase Research Findings

_Added by `/ll:refine-issue` — analysis that reframes both proposed directions.
Decision points below are why `decision_needed: true`._

> **Selected (Resume, Direction 2):** Option B — loop-level `context.resume` knob + `init` routing. Loop-level is the only option that can reconcile the popped-but-not-integrated edge case; engine-level `timed_out` resume can't see loop data.

### Resume (Direction 2): native infra already exists — decide engine-level vs loop-level
The FSM engine **already** has a resume mechanism (`ll-loop resume <loop>` →
`cmd_resume` → `PersistentExecutor.resume()`) that restores `current_state`,
`captured`, `context`, and `run_dir` (same `instance_id`). If a run dies with a
*resumable* status (e.g. `max_steps` → `interrupted`), `ll-loop resume rn-refine`
already re-enters at the persisted `current_state` (e.g. `synth_pop`) with
`synth_queue.txt` and `nodes/*/final.md` intact on disk — **no new code**.

The gap the incident exposes is narrow and specific:
- **Option A (engine-level):** the 4h wall-clock timeout persists as
  `status="timed_out"`, deliberately excluded from `RESUMABLE_STATUSES`. Making
  `timed_out` conditionally resumable (or adding a `--force`-style resume for it)
  would let native resume cover the incident with no rn-refine YAML change — but
  it's a cross-cutting engine change affecting *every* loop, arguably outside this
  issue's "rn-refine.yaml only" Scope Boundaries.
- **Option B (loop-level, matches Direction 2 as written):** add a
  `context.resume` knob + `init` routing (the rn-build/rn-implement pattern) that,
  on resume, rebuilds `synth_queue.txt` from internal nodes still lacking a
  `final.md` and jumps to `synth_pop`. This is more robust than native resume for
  the **popped-but-not-integrated edge case** (a node `synth_pop` removed from the
  queue but whose `integrate_node` never wrote `final.md` before the kill — native
  resume would silently skip it), and it stays inside the issue's scope. Native
  resume + `build_synth`'s one-time toposort never reconcile the queue against
  existing `final.md` after the initial pass.
- **Pitfall (BUG-2025):** `required_inputs: ["plan_file"]` (line 35) is enforced
  *before* `init`'s guard runs, so a resume invocation that omits `plan_file` is
  rejected pre-flight. Either exempt the resume knob or keep passing `plan_file`.

> **Selected (Parallel, Direction 1):** Option B — in-loop shell dispatch (background workers + barrier + `flock`-guarded pop). The engine-primitive route (Option A) was already scoped as FEAT-1072 and deferred "Won't Do — superseded by multi-loop parallel approach."

### Parallel integration (Direction 1): no FSM-native fan-out — decide primitive vs shell-dispatch
There is **no author-facing FSM concurrency primitive**. Sub-loops execute
synchronously inline (`_execute_sub_loop`), the schema has no `parallel:`/list
`loop:` form, and the only `ThreadPoolExecutor` is hardwired to the 2-arm
`--baseline` comparator. So Direction 1 needs one of:
- **Option A (new engine primitive):** a real parallel/fan-out state type in
  `schema.py` + `executor.py`. Powerful and reusable, but a large cross-cutting
  engine change well beyond "rn-refine.yaml only" — would itself warrant a
  separate FEAT/EPIC.
- **Option B (in-loop shell dispatch):** a `shell` state that background-spawns N
  `ll-loop run oracles/<integrate-node-subloop>` workers, each popping from
  `synth_queue.txt` under an `fcntl.flock` (the `concurrency.py` idiom), then a
  barrier state that waits for all workers before `assemble`. Keeps the change
  inside rn-refine + a small new oracle sub-loop, but requires adding locking the
  current single-writer `synth_pop` pop-idiom lacks, and the deepest-first
  ordering must become a *readiness* check (a node is poppable only once **all**
  its children have a `final.md`), not just a static depth sort — `build_synth`
  currently trusts ordering without re-verifying child completion at pop time.

### Meta-loop compliance for this change
`rn-refine.yaml` currently declares **no** `meta_self_eval_ok:`/`shared_state_ok:`
header flags (unlike `rn-implement`/`rn-decompose`, which set them `false` to opt
into stricter enforcement). Any new resume/parallel states with LLM-judged
`integrate_node` output must keep a non-LLM evaluator in the routing chain (MR-1),
write intermediates under `${context.run_dir}/` (MR-3), and the AC's
concurrency/resume verification must be the `_render()`+`bash` execution test
above — not an LLM self-report. Run `ll-loop validate rn-refine` after edits.

## Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-09. This issue carries two independent
decision axes; both were scored separately against parallel codebase-evidence
agents. Both resolve to the **in-loop / loop-level** posture, keeping the change
inside `rn-refine.yaml` (+ one new oracle sub-loop) per the issue's "rn-refine.yaml
only" Scope Boundaries — no FSM engine change.

### Resume (Direction 2)

**Selected**: Option B — loop-level `context.resume` knob + `init` routing.

**Reasoning**: The `context.resume` + `init`-guard shape is twice-precedented in the
same loop family (`rn-build.yaml`'s `RESUME_MODE:` marker + `output_contains`
routing; `rn-implement.yaml`'s `[ -n "$RESUME" ] && [ -s queue.txt ]` guard), and
the queue-write mechanics already exist in rn-refine's own `build_synth`
(`write_text("".join(f"{n}\n" ...))`). Decisively, engine-level Option A restores
`current_state` verbatim with **no reconciliation hook**, so the popped-but-not-
integrated race (a node `synth_pop` removed from the queue whose `integrate_node`
never wrote `final.md`) stays silently broken — that is structurally a loop-YAML
data-integrity problem the engine layer has no visibility into. Option A also
touches `RESUMABLE_STATUSES`, reachable by 74 of 98 loops, well outside scope.

**Implementation note (decided: keep `required_inputs`, re-pass `plan_file` on
resume)**: BUG-2025 was an input-*mismatch* problem — rn-build's resume passes
`resume_epic` *instead of* the `spec` it no longer has, so `required_inputs: ["spec"]`
blocked it. rn-refine's resume runs against the **same run** with the **same**
`plan_file`, so there is no mismatch and BUG-2025 does not apply. Two reasons to keep
it required rather than drop it: (1) `scope: - "${context.plan_file}"` (line 30) binds
the inter-run write-lock to the plan path — dropping `required_inputs` and letting
`plan_file` go empty on resume loses the scope lock guarding the in-place write-back
exactly when a recovering run is about to overwrite the user's source file; (2)
`init` already stores `realpath ... > $RUN_DIR/.source-path` (line 63), so write-back
is recoverable regardless, which makes the live scope lock a thing to preserve, not
discard. Resume invocation re-passes the same path:
`ll-loop run rn-refine "path/to/plan.md" --context resume=1 --context run_dir=<prior>`.
`init`'s existing `[ ! -f "${context.plan_file}" ]` check (line 54) passes, then a
resume guard *after* it (`[ -n "$RESUME" ] && [ -d "$DIR/nodes" ]` → emit `RESUME_MODE`)
short-circuits seeding and routes via `output_contains` to a `resume_build_synth`
state. That state is `build_synth` with one filter change — `synth_queue = internal
nodes lacking nodes/<id>/final.md` — reusing build_synth's existing `python3 << PYEOF`
shape. This queue-rebuild-from-`final.md`-absence membership logic is the new part (no
existing resume path reconciles against on-disk completion markers) and is what fixes
the popped-but-not-integrated edge case.

### Parallel integration (Direction 1)

**Selected**: Option B — in-loop shell dispatch: a `shell` state background-spawning
N `ll-loop run oracles/<integrate-node>` workers popping `synth_queue.txt` under an
`fcntl.flock`, plus a barrier state before `assemble`.

**Reasoning**: The engine-primitive route (Option A) is not a greenfield idea — it
was fully scoped as **FEAT-1072** (`ParallelStateConfig` + `_execute_parallel_state`
+ `parallel_runner.py`), sized `Very Large` (complexity 18), decomposed into 20+
children, and then **deferred with an explicit "Won't Do — superseded by multi-loop
parallel approach (simpler, no inter-loop coordination needed)"** verdict
(ENH-1073/1164/1186). Option B *is* that superseded-to approach. It reuses the
`oracles/plan-node-refine.yaml` sub-loop template and `file_utils.acquire_lock()` /
`concurrency.py` flock idioms, and stays inside rn-refine's scope, versus Option A's
~22-file cross-cutting change with 83-loop `validate_fsm` regression exposure.

**Implementation note (fix the pop, not the sort)**: `synth_pop`'s blind `head -1`
(line 274) is safe serially only because it honors `build_synth`'s deepest-first order
(line 256); N concurrent workers break the children-before-parent invariant. Convert
the pop, not the ordering:
- **Readiness predicate (deterministic, non-LLM):** node `N` is poppable iff every
  child of `N` in `edges.tsv` has `nodes/<child>/final.md`. This is the MR-1 evaluator
  that pairs with `integrate_node`'s LLM prompt — keep it in the routing chain.
- **Locked pop:** under `file_utils.acquire_lock()` on `synth_queue.txt`, scan for the
  *first ready* node (not `head -1`) and remove it with `grep -vxF` (the idiom
  `select_next` already uses), then release. `build_synth`'s deepest-first order stays
  as a scan *hint* but is no longer load-bearing — correctness rests on the predicate.
  Implement as a `python3 << PYEOF` heredoc (like `build_synth`) so it is unit-testable
  via the existing `_render()`+`bash` harness.
- **Deadlock-free:** it is a tree, and `build_synth` already backfills `final.md` for
  every non-internal node (lines 243-253), so the deepest internal nodes are ready from
  the start and each completion unblocks its parent. A worker that finds the queue
  non-empty but no ready node must **sleep-and-retry, not exit** — exit only on an empty
  queue. (This is the easy thing to get wrong.)
- **Barrier:** the fan-out `shell` state spawns N workers with `&`; a barrier state
  `wait`s (or polls until the queue is empty and no in-flight sentinel remains) before
  `assemble`. `snapshot_node`'s durable copy still fires per integration.

The background-spawn + barrier + multi-writer-locked pop pattern has **no precedent** in
any loop YAML; verify concurrency via explicit markers/timing in the `_render()`+`bash`
execution tests (AC #2), not an LLM self-report. Write intermediates under
`${context.run_dir}/` (MR-3); run `ll-loop validate rn-refine` after edits.

#### Scoring Summary

| Decision / Option | Consistency | Simplicity | Testability | Risk | Total |
|-------------------|-------------|------------|-------------|------|-------|
| Resume — A (engine `timed_out` resumable) | 1/3 | 1/3 | 2/3 | 0/3 | 4/12 |
| **Resume — B (loop-level `context.resume`)** | 3/3 | 2/3 | 3/3 | 2/3 | **10/12** |
| Parallel — A (new engine `parallel:` state) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| **Parallel — B (in-loop shell dispatch)** | 2/3 | 2/3 | 2/3 | 1/3 | **7/12** |

**Key evidence**:
- Resume A: `RESUMABLE_STATUSES` is one global frozenset (persistence.py:46) checked at two call sites; `timed_out` is deliberately terminal + archived like `completed`/`failed` (persistence.py:917, 547-590); `resume()` restore has no reconciliation hook (persistence.py:944-1011). Reuse 0.
- Resume B: rn-build.yaml:34-205 + rn-implement.yaml:27-132 provide the copy-adaptable knob/guard; `build_synth` (rn-refine.yaml:207-262) already writes the queue file in the needed format; BUG-2025 is the closed precedent for the `required_inputs` fix. Reuse 2.
- Parallel A: FEAT-1072 + FEAT-1074-1078 + ENH-1073/1164/1186 all `deferred`/"Won't Do"; ~22 files, 83-loop regression via `test_builtin_loops.py`. Reuse 1.
- Parallel B: `file_utils.acquire_lock()` (file_utils.py:60-96) + `concurrency.py` flock idiom + `oracles/plan-node-refine.yaml` template reusable; background-spawn+barrier and multi-writer shared-`run_dir` access are novel (no loop-YAML precedent). Reuse 1.

## Acceptance Criteria

- [ ] `ll-loop validate rn-refine` passes with the new states/routing.
- [ ] A synthetic tree with ≥2 same-depth internal nodes integrates them
      concurrently (verified via timing or explicit concurrent-execution
      markers, not just an LLM self-report).
- [ ] A run resumed after an integration-phase interruption reuses existing
      `nodes/*/final.md` and does not re-run refinement for already-refined
      nodes.
- [ ] The readiness-gated pop never dequeues a node before **all** its children
      have a `final.md` (assert in a `_render()`+`bash` test with a synthetic
      `edges.tsv` where a parent precedes an unfinished child in `synth_queue.txt`);
      a worker facing a non-empty queue with no ready node waits rather than exits.
- [ ] Resume re-passes `plan_file` (so `scope`/write-lock and `required_inputs`
      stay satisfied) and rebuilds `synth_queue.txt` from internal nodes lacking a
      `final.md` — covering the popped-but-not-integrated node whose `synth_pop`
      removed it from the queue but whose `integrate_node` never completed.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-09_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 66/100 → Moderate risk

### Outcome Risk Factors
- Deep per-site complexity: the background-spawn + barrier + `flock`-guarded readiness-gated pop has no precedent in any existing loop YAML (the issue's own Findings note this explicitly) — the concurrency mechanics must be designed from scratch rather than adapted from a template.
- Test coverage gap: no existing test exercises an FSM `shell` state that background-spawns N OS subprocesses with a `wait`-barrier (`test_cli_loop_background.py` only mocks a single `Popen`); the concurrency-verification test for AC #2 must be authored from scratch, not copied.

## Status

**Open** | Created: 2026-07-09 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-07-10T02:17:59 - `037d4ae5-b67e-4463-a5bf-9a1c03596b53.jsonl`
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b668b0f3-a45c-4815-91f8-a1d71d08236d.jsonl`
- `/ll:wire-issue` - 2026-07-10T00:37:19 - `3269a790-eef3-4c84-8afd-7b51d3cecfac.jsonl`
- `/ll:decide-issue` - 2026-07-10T00:22:00 - `3529d64f-997b-40d8-9db0-bb5ce0e1c7ca.jsonl`
- `/ll:refine-issue` - 2026-07-10T00:15:31 - `57e29d35-072c-4e13-841b-c2772ed77ded.jsonl`
