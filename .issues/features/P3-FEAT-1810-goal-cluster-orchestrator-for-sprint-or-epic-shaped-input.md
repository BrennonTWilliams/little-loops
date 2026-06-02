---
id: FEAT-1810
title: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: "2026-05-30T06:48:30Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
relates_to: [FEAT-1808, FEAT-1809, FEAT-1737]
---

# FEAT-1810: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input

## Summary

Add a new built-in FSM loop `goal-cluster` whose input is a *list* of related goals (e.g. a sprint's issues, an EPIC's children, a backlog slice) rather than a single goal. It routes each goal through `loop-router` (or directly to a chosen loop), but adds three behaviors no single-goal router can: (1) deduping/batching across overlapping goals before dispatch, (2) shared-context propagation between sibling goals, (3) cluster-wide synthesis at the end. Distinct from `loop-composer` (FEAT-1808): composer decomposes *one* goal into many loops; cluster fans *many* goals into many loops.

## Motivation

The actual user pain is often sprint-shaped, not single-goal-shaped. `ll-sprint` already walks an issue list and runs `/ll:manage-issue` over each — but it's hardcoded to one downstream skill. A general goal-cluster orchestrator generalizes that pattern to *any* combination of loops, with smarter pre-processing.

**Why:** Users routinely think in batches ("clean up this backlog", "ship this EPIC", "process these scan findings") and the cost of doing N goals separately is higher than doing them together because (a) shared catalog discovery / context is wasted, (b) goals that overlap in scope clobber each other when run independently, and (c) per-goal summaries scattered across N runs don't synthesize what the *batch* accomplished.
**How to apply:** This is the natural home for sprint-style work. `ll-sprint` should probably *become* a thin wrapper around `goal-cluster` long-term, but step 1 is just landing the loop alongside the existing sprint runner without touching it.

## Proposed Solution

`scripts/little_loops/loops/goal-cluster.yaml` with the following state graph:

1. **`load_goals`** — accept input in multiple shapes:
   - Raw multi-line string (one goal per line)
   - Sprint name (read `.sprints/<name>.yaml::issues[]` and treat each issue as a goal)
   - EPIC ID (read EPIC's `relates_to:` and `## Children` section)
   - JSON list of `{goal, hints}` for programmatic callers
   Normalize all forms to `[{goal_id, goal_text, hints}]`.
2. **`dedup_and_batch`** — Tier 2 LLM pass that groups goals by predicted-loop. Goals likely to dispatch to the same loop are batched into one call where possible (e.g. five `/ll:refine-issue` goals can be one batched refinement step, not five separate ones). Goals with obvious overlap (e.g. "fix BUG-X" and "address regression in X module") are surfaced for the user to merge/skip.
3. **`present_plan`** (optional HITL) — show batched plan, allow user to remove/reorder/CANCEL.
4. **`execute_cluster`** — walk the batched plan. Within a batch, sub-loop calls run in topo order (parallelism is a follow-up — see Open Questions). Each batch's output is captured into a shared `${context.cluster_state}` blob.
5. **`propagate_context`** — between batches, an LLM extracts cross-cutting findings ("BUG-42 turned out to be a duplicate of BUG-31, skip the refine") and updates downstream batches' `hints`. This is the load-bearing differentiator vs. running N `loop-router` calls in a shell loop.
6. **`synthesize_cluster_result`** — emit a *cluster-wide* summary: not "what did each step do" but "what did this batch accomplish, what's still open, what's the recommended next batch". Should mirror the shape of `ll-sprint` summaries.
7. **`present_result`** — structured JSON: `{batches, per_goal_outcomes, cluster_summary, recommended_next}`.

**Key design choices:**
- **Goal-list canonicalization.** All input shapes normalize to the same internal list. Sprint/EPIC support is just a loader; the executor doesn't know where the list came from. This makes the loop trivially reusable from `/loop`, scheduled agents, and ad-hoc CLI calls.
- **Dedup is LLM-driven, not regex.** Goals expressed in natural language overlap in ways grep can't see (same bug described two ways, same feature requested with different phrasing). The LLM pass is what makes batching better than a shell loop.
- **Shared context is the differentiator.** If `goal-cluster` doesn't propagate cross-goal findings (step 5), it's just `ll-sprint` for arbitrary loops. The cross-batch hint propagation is what makes it worth building separately.
- **Don't replace `ll-sprint` on day 1.** Land alongside it. The migration question is a follow-up issue once we have evidence the loop is more ergonomic than the Python runner.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/goal-cluster.yaml` (new)
- `scripts/little_loops/loops/README.md` — append cluster entry
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"goal-cluster"` to `expected` set
- `docs/guides/LOOPS_GUIDE.md` — section on cluster vs. composer vs. router (when to use which)

### Similar Patterns
- `scripts/little_loops/ll_sprint/runner.py` — closest existing primitive; cluster is the FSM-loop generalization
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` (FEAT-1063, done) — sprint-scoped FSM loop precedent
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — sprint-shaped loop input precedent for `input_key:`
- FEAT-1737 (accept EPIC issues as sprint arguments) — adjacent loader work, may share code

### Loaders to Reuse
- Sprint loader: `scripts/little_loops/ll_sprint/sprint_loader.py` (or wherever `.sprints/*.yaml` parsing lives)
- EPIC children resolver: `ll-issues show --children EPIC-N` or read EPIC frontmatter `relates_to:` directly

### Tests
- `scripts/tests/test_goal_cluster.py` (new) — input-shape normalization tests, dedup/batch logic, structural FSM tests, optional live-LLM class.

### Configuration
- `orchestration.cluster.max_batch_size` (default 5)
- `orchestration.cluster.enable_dedup` (default true)
- `orchestration.cluster.propagate_context` (default true)

## Open Questions

1. **Parallel batches.** When two batches have no dependency on each other (no shared goals), can they run in parallel? The FSM runner doesn't natively support intra-loop parallelism — this would need either (a) ll-parallel-style worktree dispatch, or (b) explicit fan-out in the YAML using `loop:` dispatch with `&` shell tricks. Probably defer until v2.
2. **Cross-goal artifact conflicts.** If two goals both modify the same file, dispatching them in separate batches without coordination loses one's changes. Need a conflict detector during `dedup_and_batch` — possibly reuse `ll-sprint`'s scope-based concurrency analysis (P3-FEAT-707).
3. **Relationship to `ll-sprint`.** Does cluster eventually replace the Python sprint runner, or stay parallel? Decision deferred until the loop is real and we can compare ergonomics side-by-side.
4. **EPIC-shaped input nuance.** EPICs have a `## Children` body section AND a `relates_to:` frontmatter list; need to pick a source-of-truth (probably `relates_to:` since it's structured, with `## Children` as a fallback).

## Relationship to Sibling Issues

- **FEAT-1808 (loop-composer)** — composer takes *one* goal and produces a DAG of loops; cluster takes *many* goals and produces batched loop calls. Cluster might internally dispatch composer for any goal that's itself too large for one loop. Worth designing the boundary explicitly before either lands.
- **FEAT-1809 (adaptive composer)** — cluster could borrow the `reassess` pattern for per-batch verdict gates ("this batch failed, re-plan the remaining batches").
- **FEAT-1737 (EPIC as sprint argument)** — direct overlap on the EPIC-loader piece; coordinate or share code.

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T06:48:30Z - `6be17ec6-da10-4c91-9b41-f2c0b3be4efb.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-05-30
