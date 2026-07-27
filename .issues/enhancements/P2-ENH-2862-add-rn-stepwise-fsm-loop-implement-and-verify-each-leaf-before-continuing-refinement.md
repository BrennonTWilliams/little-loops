---
id: 2862
title: Add rn-stepwise FSM loop — implement and verify each leaf before continuing refinement
type: ENH
priority: P2
status: open
discovered_by: user
discovered_date: 2026-07-27
labels:
- automation
- loops
---

# ENH-2862: Add rn-stepwise FSM loop — implement and verify each leaf before continuing refinement

## Summary

`rn-refine` (`scripts/little_loops/loops/rn-refine.yaml`) recursively decomposes a plan document into a tree, refines every node to convergence, then rolls the tree back up into a single reassembled plan — all before any implementation happens. For large inputs this can run for hours and produce dozens of leaf plan files. Implementing and verifying that many plans afterward often takes longer than the planning pass itself, and if implementation deviates from a leaf's plan at all, every sibling/ancestor plan that assumed it may now be stale — with no mechanism to catch or propagate the drift.

Add `rn-stepwise`: the same recursive decomposition walk, but where each LEAF is implemented and verified immediately after it is refined, before the walk continues to the next node — so drift is caught and corrected per-leaf instead of compounding across an entire tree of unimplemented plans.

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

## Acceptance Criteria

- [ ] `rn-refine.yaml` gains the `${context.stepwise:default=0}` branch with byte-identical behavior when unset; `scripts/little_loops/loops/rn-stepwise.yaml` exists as a thin entry point delegating to `rn-refine`, and both pass `ll-loop validate` (no duplicated tree-walk logic across the two files).
- [ ] In stepwise mode, a leaf is implemented and verified before the walk proceeds to the next queued node (observable via per-run ordering in `events.jsonl` or the `leaf_impl_<id>.txt` markers).
- [ ] Per-leaf tree hygiene is enforced: verified success produces one commit per leaf; a leaf failing verification after its repair budget is hard-reverted to the prior leaf commit, recorded as `IMPLEMENT_FAILED`, and does not abort the run.
- [ ] Deviation handling: a deviating implementation appends to `${context.run_dir}/deviations.md` AND rewrites the leaf's `final.md` to match what was built; subsequent `refine_node` passes receive `deviations.md` as context. No silent-unimplemented reconciliation.
- [ ] Resume: a leaf with a `node_outcome_<id>.txt` marker but no `leaf_impl_<id>.txt` marker is re-enqueued for implementation on resume, not treated as complete.
- [ ] Verification runs scoped per leaf (commit-range diff) with one full-suite gate before `finalize`.
- [ ] `scripts/tests/test_builtin_loops.py` (or equivalent) covers the stepwise branch and `rn-stepwise.yaml` the way it covers `rn-refine`.
