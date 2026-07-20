---
id: ENH-2708
status: open
captured_at: "2026-07-20T19:30:00Z"
discovered_date: 2026-07-20
discovered_by: capture-issue
---

# ENH-2708: plan-node-refine sub-loop outcome durability

## Summary

The `plan-node-refine` sub-loop (`scripts/little_loops/loops/oracles/plan-node-refine.yaml`) only persists its decision (`node_outcome_<id>.txt`) from terminal `emit_*` states. If the sub-loop's runner is killed (e.g. parent `rn-refine` timeout) after the LLM has decided but before it reaches a terminal state, the decision is lost even though the work product (e.g. decomposed child plans) was already written to disk.

## Current Behavior

In the `rn-refine-20260720T002123` run (see `rn-refine-audit-2026-07-20T134636.md`), node `n20`'s sub-loop reached `decide_decompose`, got `DECISION: DECOMPOSE` from the LLM, and wrote 5 child sub-plans to `nodes/n20/children/{1..5}.md` and rewrote the parent index at `nodes/n20/plan.md`. The sub-loop then entered `route_decision` (iter 11) but the parent's 6h wall-clock budget expired before `materialize_children` ran, so:

- `node_outcome_n20.txt` was never written
- The parent's `classify_node` state found no outcome file and fell back to `REFINE_FAILED`
- The 5 child plans were never copied to `nodes/n21..n25` or enqueued
- `nodes/n20/children/` was left orphaned in the run dir with fully complete, scored sub-plans

The decision text itself (`decision.output` in the parent's captured state) shows the LLM's `DECOMPOSE` verdict was already final — only the persistence step was lost.

## Expected Behavior

The sub-loop should persist its decision at decision time, not only in terminal `emit_*` states, so a runner kill between decision and materialization is recoverable:

- Write a provisional outcome marker immediately after `decide_decompose`/`decide_leaf` routes (before `materialize_children` runs), so a killed run can distinguish "decided but not materialized" from "never decided."
- Alternatively, pass a `deadline_epoch` into the sub-loop via `with:` so it can check its own remaining budget and short-circuit cleanly (write the outcome, skip materialization gracefully) instead of being killed mid-`route_decision` by the parent's external timeout.

## Motivation

This is the root cause of the lost work in the 2026-07-20 audit, not just a downstream symptom. Even with the run-dir observability fixes (see companion issue), the underlying loss is real: an LLM decision (2m53s of work) and materialized artifacts are silently discarded because there is no durability boundary between "decided" and "persisted." Any future rn-refine run with a similarly timed timeout will lose work the same way, regardless of what summary.json reports about it afterward.

## Proposed Solution

Two candidate approaches (needs `/ll:refine-issue` codebase research before implementation — the audit's own proposed diffs are rough sketches, not verified against the actual FSM structure):

1. **Provisional sentinel at decision time**: after `decide_decompose`/`decide_leaf` routes but before `materialize_children`, write a provisional `node_outcome_<id>.txt` (e.g. `DECOMPOSE_PENDING` or similar) containing enough info for the parent/resume path to recover the decision even if materialization never completes. The audit's proposed diff (writing a bare timestamp sentinel via `.decide_started_${context.node_id}`) does **not** actually persist the decision — it only marks that the prompt started, which doesn't help `classify_node` recover anything. A working fix needs to persist the decision output itself once it's known.
2. **Deadline propagation**: pass `deadline_epoch` (derived from the parent's `context.timeout_total` and elapsed time) into the sub-loop via `with:`, and have `route_decision` (or the state after the decision prompt) check it and short-circuit to a clean emit state instead of being killed by the parent's external process-timeout.

Requires investigating: how `with:` context propagation works for sub-loop invocation in this FSM engine, and whether `plan-node-refine`'s states have access to `loop.elapsed_ms` equivalent to the parent's.

## Scope Boundaries

In scope: `plan-node-refine.yaml`'s decision-persistence path (decide → materialize → emit). Out of scope: the parent `rn-refine` loop's run-dir observability (summary.json/writeback.json — see companion issue) and the deadline-drain queue-truncation issue (separate, not addressed here).

## Impact

- **Priority**: P2 — this is the actual root cause of lost sub-loop work on a real 6-hour run; will recur on any similarly-timed timeout.
- **Effort**: Medium — requires FSM state/routing changes in `plan-node-refine.yaml` plus verification via a real (non-simulated) sub-loop timeout scenario.
- **Risk**: Medium — touches decision routing in a nested sub-loop; must not regress the normal (non-timeout) decompose/leaf path.

## Related Key Documentation

| Document | Relevance |
|---|---|
| .claude/CLAUDE.md | Loop Authoring meta-loop rules (MR-1 through MR-11) apply to any edit of `plan-node-refine.yaml` |

## Status

- [ ] Not started

## Session Log
- `/ll:capture-issue` - 2026-07-20T19:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e43208e6-cc93-448d-8f8e-8ba33fb2cb7e.jsonl`
