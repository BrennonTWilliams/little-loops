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
  - **Routing guard (added by `/ll:audit-issue-conflicts` on 2026-06-04):** Encode a dispatch allowlist in the `load_goals` or `dedup_and_batch` state: when a single goal within the cluster is too large for one loop, `goal-cluster` is permitted to dispatch `loop-composer` as a child. The reverse (`loop-composer` → `goal-cluster`) is blocked. Ensure `loop-router` catalog respects this guard so the two loops are not both presented for ambiguous multi-goal input. Coordinate with FEAT-1808's matching guard.
- **FEAT-1809 (adaptive composer)** — cluster could borrow the `reassess` pattern for per-batch verdict gates ("this batch failed, re-plan the remaining batches").
  - **Coordination note (added by `/ll:audit-issue-conflicts` on 2026-06-04):** FEAT-1809's `reassess` state is being designed as a reusable fragment in `loops/lib/composer.yaml` (see FEAT-1809 § Proposed Solution §2 design note). When implementing `goal-cluster`'s per-batch verdict gates, consume this fragment rather than re-implementing. The fragment accepts `{goal, plan, completed_steps, failing_verdict}` and returns `{decision, new_tail_plan, reason}` — directly applicable to batch-failure re-planning.
- **FEAT-1737 (EPIC as sprint argument)** — direct overlap on the EPIC-loader piece; coordinate or share code.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map references non-existent paths: `scripts/little_loops/ll_sprint/sprint_loader.py` and `scripts/little_loops/ll_sprint/runner.py`. Sprint runner code is actually at `scripts/little_loops/sprint.py` and `scripts/little_loops/cli/sprint/run.py`. Correct these before implementation.

## Session Log

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:55:12 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:07 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T06:48:30Z - `6be17ec6-da10-4c91-9b41-f2c0b3be4efb.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-05-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Routing decision rule to prevent circular dispatch with FEAT-1808 (`loop-composer`): a pre-enumerated list of goals → `goal-cluster` (this issue); a single natural-language goal → `loop-composer` (FEAT-1808). `goal-cluster` MAY call `loop-composer` as a child for an individual goal that is itself too large for one loop, but `loop-composer` MUST NOT call `goal-cluster`. Encode this constraint as a routing guard in the `loop-router` catalog so the two loops are not both presented as candidates for the same ambiguous input.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): Shared integration test requirement with FEAT-1808. Both issues must include a test that verifies `loop-router`'s catalog discovery never returns both `loop-composer` and `goal-cluster` as candidates for the same input: single-goal input must route to composer only; multi-goal input must route to cluster only. Add to FEAT-1810's test plan: `test_loop_router_catalog_exclusivity` in `scripts/tests/test_goal_cluster.py`.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): After EPIC-1811 orchestration loops ship, ensure `goal-cluster`'s `load_goals` input shapes and batch API are general enough that domain-specific loops (FEAT-1806 market-strategy, future analysis loops) can be re-expressed as cluster input batches. The cluster's dedup/batching + shared-context propagation is the orchestration-layer primitive most likely to absorb standalone domain loops. Design the `goal_text` schema and `hints` mechanism with this forward-compatibility in mind.

## Verification Notes (2026-06-05)

- **Path correction from prior verification applied**: `ll_sprint/` → `sprint.py` and `cli/sprint/run.py` is now accurate.
- `sprint.py` exists at correct path.
- `goal-cluster.yaml` does not exist (expected).
