---
id: ENH-2862
title: "Add rn-stepwise FSM loop \u2014 implement and verify each leaf before continuing\
  \ refinement"
type: ENH
priority: P2
status: done
discovered_by: user
discovered_date: 2026-07-27
labels:
- automation
- loops
confidence_score: 98
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-07-27T23:39:45Z'
---

# ENH-2862: Add rn-stepwise FSM loop — implement and verify each leaf before continuing refinement

## Summary

`rn-refine` (`scripts/little_loops/loops/rn-refine.yaml`) recursively decomposes a plan document into a tree, refines every node to convergence, then rolls the tree back up into a single reassembled plan — all before any implementation happens. For large inputs this can run for hours and produce dozens of leaf plan files. Implementing and verifying that many plans afterward often takes longer than the planning pass itself, and if implementation deviates from a leaf's plan at all, every sibling/ancestor plan that assumed it may now be stale — with no mechanism to catch or propagate the drift.

Add `rn-stepwise`: the same recursive decomposition walk, but where each LEAF is implemented and verified immediately after it is refined, before the walk continues to the next node — so drift is caught and corrected per-leaf instead of compounding across an entire tree of unimplemented plans.

## Current Behavior

`rn-refine.yaml` walks the whole decomposition tree to convergence — refining every node — before any implementation begins. All leaves are refined into `nodes/<id>/final.md` plan files first; implementation and verification of those plans happen only afterward, as a separate pass outside this loop. There is no mechanism during the refine walk to catch drift between a leaf's plan and what implementation later actually produces, so a deviation discovered late can invalidate sibling/ancestor plans that assumed the original leaf content.

## Expected Behavior

A new `rn-stepwise` entry point (delegating into `rn-refine.yaml` via a `${context.stepwise}` flag) implements and verifies each leaf immediately after it is refined, before the tree walk advances to the next queued node. Verified leaves are committed per-leaf; failed leaves are reverted and recorded without aborting the run. Deviations between a leaf's plan and its actual implementation are captured in `deviations.md` and folded back into `final.md` so later `refine_node` passes see reality, not the original aspiration.

## Motivation

- **Cost asymmetry.** Planning N leaves up front, then implementing all N afterward, defers the expensive and error-prone part (implementation + verification) to the end, where a single early misjudgment invalidates everything planned after it.
- **Faster feedback loop.** Implementing a leaf immediately surfaces integration problems (wrong assumptions about a sibling, a missing dependency) while the sibling context is still fresh in the run, instead of hours later during a separate implementation pass.
- **The walk order itself prevents most staleness.** In stepwise mode, at any moment the only plans in existence are (a) already-implemented leaves and (b) not-yet-refined queued nodes. Group (b) needs no reconciliation machinery: their `refine_node` pass has not run yet, and when it runs it refines against the actual repo — which now contains earlier leaves' *real* implementations, not their aspirational plans. The stale-plan cascade that motivates this issue largely cannot form under stepwise ordering; what remains is the narrow deviation case handled below.

## Proposed Change

**Do not fork `rn-refine.yaml`.** An 880-line fork of the tree walk would drift immediately (the ENH-2707 comments already warn that `timeout_total` must be hand-synced *within one file*; a cross-file fork is worse). Instead:

1. **`${context.stepwise:default=0}` flag in `rn-refine.yaml`.** `record_leaf` gains a routing branch: when `stepwise` is set, route to the implement/verify chain instead of `next: dequeue_next`. When unset, behavior is byte-for-byte today's.
2. **`rn-stepwise.yaml` as a thin named entry point** (~20–30 lines): sets `stepwise: 1` (plus stepwise-specific budget defaults, below) and delegates to `rn-refine` via a `loop:` state. This satisfies "no duplicated tree-walk logic split across two loop files" while still giving users a `ll-loop run rn-stepwise` name.
3. **`implement_leaf`** (new, in the shared chain) — implements the leaf scoped to its own `nodes/<id>/final.md` as the task input. Direct prompt/skill invocation on the plan file, **not** routed through the Issue system, per `feedback_general_purpose_loop_decoupling` (a general-purpose loop must not couple its core to the Issue system — Issue integration, if any, is an optional adapter).
4. **`verify_leaf`** (new) — runs `${config.project.test_cmd}`/`lint_cmd`/`type_cmd` scoped to the files touched by this leaf's commit range (see tree hygiene below); on failure, a bounded repair cycle back into `implement_leaf` (repair counter kept under `${context.run_dir}/`, per MR-3/MR-5). `exit_code` evaluation gives the generator its non-LLM evaluator (MR-1) natively.
5. **`record_deviation`** (new; replaces the earlier `reconcile_siblings` concept) — when the implementation deviates from the leaf's plan (explicit deviation note written by the implementer, or diff against `final.md`):
   - append a deviation note to `${context.run_dir}/deviations.md`, and
   - rewrite the leaf's own `final.md` to match what was actually built, so `build_synth` later integrates reality, not the original aspiration.
   The `oracles/plan-node-refine` refine prompt for subsequent nodes reads `deviations.md` as context. No `needs_reconcile` flagging, no reopening of visited nodes — unvisited nodes reconcile for free by refining against the post-implementation repo (see Motivation).
6. **`record_leaf_done`** (new) — writes a **separate** per-leaf implementation marker `leaf_impl_<id>.txt` (implemented / verified / deviated / IMPLEMENT_FAILED), then `next: dequeue_next`. This must NOT reuse `node_outcome_<id>.txt` — see resume semantics below.

Bottom-up integration (`build_synth`/`synth_dispatch`/`assemble`) and the final write-back (`preflight_check`/`finalize`) stay unchanged — the plan document produced at the end now already matches implemented, verified code (via the `final.md` rewrites in step 5) rather than being an aspirational document that implementation must still catch up to.

## Design Notes

- **Per-leaf tree hygiene (commit-or-revert) — required, not optional.** Without a rollback boundary, a failed leaf's half-implemented edits sit in the working tree, contaminate the next leaf's implementation context, and can fail the next leaf's verify gate for this leaf's sins. Policy: **commit on verified success** (one commit per leaf; the commit range is also what computes the "files touched" set for scoped verification via `git diff` — no separate tracking needed), **hard-revert to the last leaf commit on `IMPLEMENT_FAILED`** after the repair budget is exhausted. The run must start from a clean tree (preflight check) so the revert baseline is well-defined.
- **Resume semantics.** `check_resume` treats a present `node_outcome_<id>.txt` as "node complete." A leaf refined but killed mid-implementation would otherwise resume as done. Hence the separate `leaf_impl_<id>.txt` marker: in stepwise mode, `check_resume`/`rebuild` must re-enqueue any leaf that has a `node_outcome` marker but no `leaf_impl` marker (implementation resumes from the leaf's committed baseline thanks to the hygiene rule above).
- **Verification scope — decided here, not deferred:** scoped per-leaf (touched files from the leaf's commit range) for the inner verify/repair cycle, **plus one full-suite gate before `finalize`**. Pure scoping leaves cross-leaf regressions open; a single full run at the end caps that risk without paying full-suite cost × N leaves.
- **Error routing.** `record_leaf`'s existing `on_error: dequeue_next` habit is correct for bookkeeping states but must NOT be inherited by the implement/verify chain — an implement crash silently skipping to the next node with a dirty tree is the worst failure mode. `implement_leaf`/`verify_leaf` errors route to the revert path, record `IMPLEMENT_FAILED` in `leaf_impl_<id>.txt` (and `failed_nodes.txt`), and only then continue the walk. Failure isolation is preserved: a failed leaf does not abort the tree walk, and is surfaced in the final `report` alongside the existing `capped.txt`/`failed_nodes.txt` reporting.
- **Budget.** `rn-refine`'s `max_steps: 300` / `timeout: 21600` was sized for planning-only work. Rather than only inflating the timeout, `rn-stepwise.yaml`'s entry point sets a **lower default `max_nodes`** (implementation dominates runtime; 40 implemented-and-verified leaves in one run is unrealistic) and the ENH-2707 soft-deadline drain (`dequeue_next`'s elapsed-vs-`timeout_total`-minus-`synth_reserve` check) is extended with a per-leaf implement-time estimate so the drain triggers early enough to still synthesize.
- **Naming.** `rn-stepwise` was chosen over `rn-build` (taken), `rn-realize`, `rn-land`, `rn-plan-and-build`, etc. — it unambiguously signals "same recursive walk as `rn-refine`, stepped through implementation one leaf at a time" without colliding with existing loop/CLI names.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/rn-refine.yaml:348-354` — current `record_leaf`:
  ```yaml
  record_leaf:
    action_type: shell
    action: |
      echo "${captured.input.output}" >> "${captured.run_dir.output}/leaves.txt"
      echo "[LEAF] ${captured.input.output}"
    next: dequeue_next
    on_error: dequeue_next
  ```
  Both branches converge unconditionally on `dequeue_next`. This is the splice point: a new state (e.g. `implement_and_verify_leaf`) goes between `route_leaf`'s `on_yes` and `record_leaf`, gated by `${context.stepwise}`. `dequeue_next` (lines 220-262) is the single control-flow hub every leaf-processing state funnels back into (`record_leaf`, `record_capped`, `record_failure`, `record_node_crash`) — the stepwise chain must preserve this single-hub property or the queue-draining invariant breaks.
- `node_outcome_<id>.txt` lives at `${context.run_dir}/node_outcome_<id>.txt` (run-dir root, not nested under `nodes/<id>/`), written by `oracles/plan-node-refine.yaml` at `emit_decomposed:366`, `emit_leaf:378`, `emit_capped:389`, `refine_failed:397`, and read back by `rn-refine.yaml`'s `classify_node:316`. `check_resume` (lines 123-166) treats a `visited.txt` node with no matching `node_outcome_<id>.txt` as incomplete. Stepwise needs a **parallel** marker (issue already specifies `leaf_impl_<id>.txt`) since `check_resume`/`resume_reconcile` (lines 180-218) only understand refinement completion today — they have no concept of "refined but not yet implemented."
- ENH-2707 soft-deadline drain (`dequeue_next:220-262`) uses `${loop.elapsed_ms}` vs. `BUDGET_MS = (${context.timeout_total:default=21600} - ${context.synth_reserve:default=3600}) * 1000`; `max_steps: 300`/`timeout: 21600` are separate engine-level limits (lines 34-35) that must stay hand-synced with `timeout_total` (no `${loop.timeout}` interpolation exists — see comment at lines 55-59). `rn-stepwise.yaml`'s lower `max_nodes` default and extended per-leaf time estimate both need to reference these same variable names.
- `build_synth` (lines 380-435) only ever reads `nodes/<id>/final.md` (backfilling from `plan.md` if missing) — nothing today reads a `deviations.md`. Folding deviation context into subsequent `refine_node` calls means adding a new `parameters:` entry (e.g. `deviations_path`) to `oracles/plan-node-refine.yaml`'s existing `parameters:` block (lines 56-86) and threading it through the `with:` block at `refine_node:291-310` (which currently passes `run_dir`, `node_id`, `depth`, `max_depth`, `max_node_iters`, `max_nodes`, `deadline_epoch` — no verification/deviation field exists yet).
- `failed_nodes.txt`/`capped.txt` (written by `record_failure:364-370`, `record_node_crash:372-378`, `record_capped:356-362`) are read only by the final `report` prompt state (lines 816-862, `action_type: prompt`), not by any gating logic. A `verify_failed.txt`-style counter in the same append-only convention is the natural way to surface implement/verify failures without new gating machinery.

**Delegation pattern to copy** — `scripts/little_loops/loops/issue-refinement.yaml` (full file) is the closest existing "thin entry point delegates via `loop:` state" precedent for `rn-stepwise.yaml`:
```yaml
states:
  run_all:
    loop: recursive-refine
    with_:
      order: next-action
      commit_every: 5
      no_recursion: true
    on_success: done
    on_failure: failed
    on_error: failed
```
Note: this file uses `with_:` while `rn-refine.yaml`/`rn-implement.yaml`/`oracles/plan-node-refine.yaml` all use `with:` — verify which key the FSM engine's parameter binding actually expects before copying verbatim. `scripts/little_loops/loops/auto-refine-and-implement.yaml`'s `delegate` state (line 258) shows the same shape reading a sub-loop's shared-`run_dir` artifacts (`subloop_outcome_<token>.txt`) after delegation rather than re-deriving them — the pattern `rn-stepwise.yaml`'s terminal state should follow when reporting on `rn-refine`'s `summary.json`.

**Flag-gated branch pattern** — `scripts/little_loops/loops/recursive-refine.yaml`'s `gate_recursion` state (line 281) is a near-exact template for the `${context.stepwise}` branch in `record_leaf`:
```yaml
gate_recursion:
  action: |
    NO_RECURSION="${context.no_recursion:default=false}"
    if [ "$NO_RECURSION" = "true" ]; then
      echo "${captured.input.output}" >> ${context.run_dir}/recursive-refine-skipped.txt
      exit 0
    fi
    exit 1
  fragment: shell_exit
  on_yes: maybe_commit
  on_no: detect_children
  on_error: detect_children
```

**Per-leaf commit/revert hygiene** — `scripts/little_loops/loops/harness-optimize.yaml`'s `commit_and_log`/`revert_and_log` states are the only existing git-commit/revert idiom in a built-in loop: `commit_and_log` scopes `git add`/`git commit` to `${context.targets}` (not `-A`) and captures `git rev-parse HEAD` as `last_commit`; `revert_and_log` uses path-scoped `git restore ${context.targets}` (no loop currently uses `git reset --hard` or `git revert`, so the ENH's specified hard-revert-to-last-leaf-commit is new territory, not a copy of an existing state).

**Bounded repair cycle with a run-dir counter** — `scripts/little_loops/loops/autodev.yaml`'s `count_repair_cycle_refine` (line 311) is the closest precedent for `verify_leaf`'s repair counter:
```yaml
count_repair_cycle_refine:
  action: |
    N=$(cat ${context.run_dir}/autodev-repair-cycle-count.txt 2>/dev/null || echo 0)
    N=$((N + 1))
    printf '%s' "$N" > ${context.run_dir}/autodev-repair-cycle-count.txt
  action_type: shell
  next: copy_broke_down
  on_error: copy_broke_down
```
Reset-per-item (at `dequeue_next`), incremented-per-attempt, read by a later gate — same shape needed for the per-leaf implement→verify→repair bound.

**`exit_code` evaluator + generator (MR-1 shape)** — `scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_build`/`run_typecheck`/`run_lint` states (lines 169/251/281) pair a shell generator with `evaluate: {type: exit_code}` and route every branch (`on_yes`/`on_no`/`on_error`) to the same next state — the template for `verify_leaf`'s scoped-test-command generator/evaluator pairing.

**Test precedent** — `scripts/tests/test_rn_refine.py`'s `TestRecursiveStructure` class (line 84) uses structural graph assertions (`fsm.states["record_leaf"].on_yes == "..."`) plus a `_render()` helper (interpolates a raw state action then runs it via `subprocess.run(["bash", "-c", rendered], ...)` against a seeded `tmp_path` run_dir) — see `test_synth_dispatch_empty_queue_short_circuits` (line 133) for the closest existing shape to model a new stepwise-branch test after.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No Python loader changes needed — `resolve_loop_path()` (`scripts/little_loops/cli/loop/_helpers.py`) resolves `rn-stepwise` purely by filename lookup in `scripts/little_loops/loops/`; dropping the new YAML there is sufficient for `ll-loop run rn-stepwise` / `ll-loop validate rn-stepwise` to work with no registry edit. [Agent 1 finding]
- `rn-stepwise.yaml` needs `category:`/`visibility:` frontmatter matching `rn-refine.yaml`'s (`category: planning`) so it sorts correctly in `ll-loop list`'s public-tier grouping (`cmd_list()`, `scripts/little_loops/cli/loop/info.py:103`) — confirm intended visibility (public entry point vs. internal like `plan-node-refine.yaml`'s `visibility: internal`). [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — canonical rn-* family narrative; TOC and family list (line 4+) enumerate `rn-plan, rn-refine, rn-implement, rn-remediate, rn-decompose` and would need an `rn-stepwise` entry if it's a user-facing entry point rather than an internal branch of `rn-refine`. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — per-loop catalog entry format; `rn-refine`'s entry is at line 293-317 (context vars table, invocation example, `run_dir` semantics). A new `rn-stepwise` catalog entry follows this template if it's independently invocable. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — Planning section (line 55+) lists `rn-plan`, `rn-refine`; line 1296 references the rn-refine/rn-plan tip callout that cross-links `LOOPS_REFERENCE.md`. [Agent 1/2 finding]
- `scripts/little_loops/loops/README.md` (lines 55-62) — built-in loops listing; needs an `rn-stepwise` line. [Agent 1 finding]
- Confirm `rn-stepwise.yaml` is a **data-operating loop**, not a meta-loop under the MR-1..MR-13 "Loop Authoring" rules in `.claude/CLAUDE.md` (it doesn't modify loop YAMLs/skills/agents/CLAUDE.md itself) — the rules still apply to validate the YAML via `ll-loop validate`, but no CLAUDE.md table update is needed unless a new rule is being proposed. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — add MR-1/MR-3/MR-5/MR-13 positive-control tests for the new `implement_leaf`/`verify_leaf`/`record_deviation` states, mirroring the existing whole-loop-passes-clean pattern (e.g. `test_mr13_auto_refine_and_implement_yaml_passes_clean`, line 5351-5358; `test_mr5_does_not_fire_for_loop_delegation`, line 2706, relevant since `rn-stepwise.yaml` delegates via a `loop:` state). [Agent 3 finding]
- `scripts/tests/test_rn_refine.py` — `record_leaf` (rn-refine.yaml:348-354) currently has **zero** existing routing assertions; add baseline tests for its current unconditional `next`/`on_error: dequeue_next` shape *before* introducing the `${context.stepwise}` conditional branch, so the diff is provably additive (pattern: `TestRecursiveStructure`'s per-edge assertions, e.g. `test_decomposed_node_loops_back_to_dequeue`, line 90-93), plus new `test_record_leaf_routes_to_stepwise_when_enabled` / `test_record_leaf_routes_to_dequeue_when_disabled` pair. [Agent 3 finding]
- `scripts/tests/test_harness_optimize.py:70-148` (`test_gate_routes_correctly`, `test_revert_uses_scoped_targets`) — closest existing pattern for the per-leaf commit/revert hygiene gate; model `implement_leaf`/`verify_leaf`'s commit-or-revert routing and scoped-revert-target assertions after this file, since no rn-refine/rn-stepwise test currently covers commit/revert behavior. [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py:296-343` (`TestRepairCycleCounterStates`) — model the per-leaf repair-cycle counter test after this class's three-part shape (counter-state existence + filename assertion, monotonic-increment subprocess test, routing-through-counter assertion) if `verify_leaf`'s repair budget uses a dedicated counter file. [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- No `config-schema.json` / `.ll/ll-config.json` entries needed — `max_nodes`/`timeout_total`/`synth_reserve` are loop-local `context:`/`parameters:` defaults declared inline in the loop YAML (confirmed via grep: no global config keys exist for these), following `rn-refine.yaml`'s existing pattern (`timeout_total: 21600`, `synth_reserve: 3600` at lines 60-61, manually kept in sync with the top-level `timeout:` field per the comment at lines 55-59 — no `${loop.timeout}` interpolation exists). [Agent 2 finding]

## Scope Boundaries

- **Not this issue**: forking or rewriting `rn-refine.yaml`'s tree-walk logic — the shared refine/decompose/synth machinery stays a single file, gated by `${context.stepwise}`.
- **Not this issue**: reopening or re-refining already-visited nodes to reconcile drift — unvisited nodes reconcile for free by refining against the post-implementation repo (see Motivation); only `deviations.md` context is threaded forward.
- **Not this issue**: changing `build_synth`/`synth_dispatch`/`assemble` or the final write-back (`preflight_check`/`finalize`) beyond consuming the deviation-updated `final.md` files — bottom-up integration stays as-is.

## Impact

- **Priority**: P2 — improves feedback latency and reduces compounding-staleness risk for large recursive-refine runs, but is not blocking active work; `rn-refine` remains fully usable unchanged.
- **Effort**: Large — new `implement_leaf`/`verify_leaf`/`record_deviation`/`record_leaf_done` states, a per-leaf commit/revert hygiene mechanism, a parallel resume marker, and a new `rn-stepwise.yaml` entry point, each requiring dedicated tests per the Integration Map.
- **Risk**: Medium — the new stepwise branch is additive and gated behind `${context.stepwise:default=0}`, so unset behavior stays byte-identical to today's `rn-refine`; risk is contained to the new branch and its interaction with `dequeue_next`'s single-hub control flow and the ENH-2707 soft-deadline drain.
- **Breaking Change**: No — `rn-refine.yaml` is unchanged when `stepwise` is unset; `rn-stepwise` is a new, separately invoked loop.

## Acceptance Criteria

- [ ] `rn-refine.yaml` gains the `${context.stepwise:default=0}` branch with byte-identical behavior when unset; `scripts/little_loops/loops/rn-stepwise.yaml` exists as a thin entry point delegating to `rn-refine`, and both pass `ll-loop validate` (no duplicated tree-walk logic across the two files).
- [ ] In stepwise mode, a leaf is implemented and verified before the walk proceeds to the next queued node (observable via per-run ordering in `events.jsonl` or the `leaf_impl_<id>.txt` markers).
- [ ] Per-leaf tree hygiene is enforced: verified success produces one commit per leaf; a leaf failing verification after its repair budget is hard-reverted to the prior leaf commit, recorded as `IMPLEMENT_FAILED`, and does not abort the run.
- [ ] Deviation handling: a deviating implementation appends to `${context.run_dir}/deviations.md` AND rewrites the leaf's `final.md` to match what was built; subsequent `refine_node` passes receive `deviations.md` as context. No silent-unimplemented reconciliation.
- [ ] Resume: a leaf with a `node_outcome_<id>.txt` marker but no `leaf_impl_<id>.txt` marker is re-enqueued for implementation on resume, not treated as complete.
- [ ] Verification runs scoped per leaf (commit-range diff) with one full-suite gate before `finalize`.
- [ ] `scripts/tests/test_builtin_loops.py` (or equivalent) covers the stepwise branch and `rn-stepwise.yaml` the way it covers `rn-refine`.

## Status

**Open** | Created: 2026-07-27 | Priority: P2

## Session Log
- `ll-auto` - 2026-07-27T23:39:45 - `d7f3ae1a-7899-45a2-a693-45b8ddfcd96c.jsonl`
- `/ll:ready-issue` - 2026-07-27T23:28:26 - `a58446c8-51ca-4bec-9116-30c08e7ca3a2.jsonl`
- `/ll:confidence-check` - 2026-07-27T23:25:45 - `eb8cadc8-11ab-4f93-b644-9a459cfeefc5.jsonl`
- `/ll:wire-issue` - 2026-07-27T23:23:51 - `b7b153bd-bb61-4187-8a43-395315f0bf52.jsonl`
- `/ll:refine-issue` - 2026-07-27T23:17:24 - `a0177914-b3e8-413f-86b1-6554ca17359b.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-27
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
