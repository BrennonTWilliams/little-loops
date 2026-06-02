---
id: FEAT-1808
title: `loop-composer` — Goal Decomposer Built-in FSM Loop (One Level Above `loop-router`)
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: "2026-05-30T06:48:30Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
---

# FEAT-1808: `loop-composer` — Goal Decomposer Built-in FSM Loop (One Level Above `loop-router`)

## Summary

Add a new built-in FSM loop `loop-composer` that accepts a natural-language goal too large for a single existing loop, decomposes it into an ordered DAG of `loop-router` calls (or direct sub-loop invocations), then walks the plan to execution. Each node in the plan is an existing loop; the composer is purely an orchestration layer that turns "I want to ship feature X" into "refine → wire → plan → implement → review → PR".

## Motivation

`loop-router` (FEAT-1654, done) solved *one-goal → one-loop*. The next layer up is *one-goal → many-loops*. Today users compose multi-loop workflows manually by chaining slash commands, calling `ll-sprint`, or wiring a bespoke loop for each recurring multi-step pattern. The catalog has the right *primitives* but no composer to sequence them from intent.

**Why:** Plenty of real goals ("ship the auth migration", "audit and harden the loops directory") naturally fan out across 3–6 existing loops; there is no general entry point for them.
**How to apply:** This is purely an orchestration layer — the composer never *does* work, it only sequences other loops. All actual work stays in the leaf loops `loop-router` already knows how to dispatch.

## Proposed Solution

`scripts/little_loops/loops/loop-composer.yaml` with a `decompose → plan → execute → review` shape:

1. **`discover_loops`** — same catalog discovery as `loop-router` (reuse the shell heredoc; consider extracting to `loops/lib/`).
2. **`decompose_goal`** — Tier 2 LLM prompt that emits a JSON plan: an ordered list of `{step_id, loop_name, input, depends_on: [step_ids]}` entries forming a DAG. Prompt instructs the model to prefer `loop-router` as the leaf when uncertain (let router pick), and to use direct loop names when the fit is obvious.
3. **`validate_plan`** — `action_type: shell` that parses the plan, checks loop names exist in the catalog, detects cycles, enforces a per-plan node cap (e.g. ≤8 nodes to start). Exits non-zero on invalid plan → re-decompose (bounded retries).
4. **`present_plan`** (HITL gate) — if `${context.auto}` is `false` or plan cost-estimate exceeds threshold, show the plan and ask the user to approve/edit/CANCEL. (Mirrors `loop-router::present_choices`.)
5. **`execute_plan`** — walk the DAG. For the MVP, execute sequentially in topological order (parallelism is FEAT-1809 territory). Each node is a sub-loop dispatch (`loop: <node.loop_name>`, `with: {input: <node.input>}`, `capture: step_N_output`). Step outputs are stored in `${context.plan_state}` (JSON blob) so later step `input` strings can interpolate prior results.
6. **`review_chain`** — synthesize a summary across all step outputs (similar to `loop-router::review` but multi-step).
7. **`present_result`** — emit structured JSON: `{plan, step_results, success, summary}`.

**Key design choices that need calling out:**
- **Plan is inspectable.** A pure-shell executor walks a YAML/JSON manifest. The plan is logged, dumped to `.loops/tmp/loop-composer-plan.json`, and survives re-runs. This is the deliberate *non*-reactive choice — see FEAT-1809 for the reactive variant.
- **Sequential MVP, DAG semantics in the schema.** Plan entries carry `depends_on:` from day 1 even though the executor walks them in topo order; this leaves room for parallel fan-out without a plan-format change.
- **`loop-router` as the universal leaf.** The composer's prompt is biased toward emitting `loop-router` nodes when the model is uncertain about loop choice. This pushes uncertainty to the routing layer where it already has a confidence/HITL gate, instead of duplicating that logic at the composer level.
- **State interpolation between steps.** Step N+1's `input` string can reference `${plan_state.step_3.output}` so plans can express "feed step 3's output into step 5". This is the load-bearing part — without it, the composer is just a fancy `ll-sprint`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-composer.yaml` (new)
- `scripts/little_loops/loops/README.md` — append composer entry
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"loop-composer"` to the `expected` set
- `docs/guides/LOOPS_GUIDE.md` — note composer as the multi-loop entry point sitting above `loop-router`

### Similar Patterns
- `scripts/little_loops/loops/loop-router.yaml` — direct ancestor; reuse catalog discovery and HITL shape
- `scripts/little_loops/loops/outer-loop-eval.yaml` — orchestrating-loop pattern (FEAT-933)
- `scripts/little_loops/loops/recursive-refine.yaml` — multi-state loop with sub-loop dispatch
- `ll-sprint` runner — closest existing multi-issue orchestrator (different shape: it walks issues, not loops)

### Tests
- `scripts/tests/test_loop_composer.py` (new) — schema validation, plan-parsing tests, structural assertions on the state graph, optional `@pytest.mark.slow` live-LLM class.

### Configuration
- Consider `orchestration.composer.max_plan_nodes` (default 8) and `orchestration.composer.auto` (default false — composer should HITL by default given blast radius).

## Open Questions

1. **Plan schema format.** YAML inline vs. dedicated JSON blob. Probably JSON because the LLM emits it and we already have JSON tooling.
2. **Failure semantics.** When step 4 of 6 fails, do we stop, continue, or re-plan the tail? For the MVP: stop and report. Re-planning is FEAT-1809.
3. **Reusing `recursive-refine`'s shape?** That loop already does "decompose → recurse → terminate" with sub-loops. Worth a side-by-side comparison before committing to a brand-new state graph.

## Relationship to Sibling Issues

- **FEAT-1809 (adaptive composer)** — natural v2 evolution: same plan-then-execute spine but adds re-plan-on-failure. Start with this issue (1808), graduate to 1809 once the static planner is solid.
- **FEAT-1810 (goal-cluster orchestrator)** — different input shape (a *list* of goals, e.g. a sprint), not a single goal. Composer might dispatch goal-cluster as a child, or vice versa. Worth checking before either lands.

## Session Log
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:44:01 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:33 - `922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T06:48:30Z - `6be17ec6-da10-4c91-9b41-f2c0b3be4efb.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-05-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1809 both spec intermediate artifacts using bare `.loops/tmp/` paths (e.g. `loop-composer-plan.json`). Per MR-3 (`ll-loop validate` WARNING), all intermediate artifacts MUST be written under `${context.run_dir}/` to prevent state corruption on concurrent runs. All artifact paths in the Implementation Steps for this issue MUST be updated to use `${context.run_dir}/` (e.g. `${context.run_dir}/composer-plan.json`) before implementation begins. Add `shared_state_ok: true` at the loop top-level ONLY if cross-run sharing is intentional and explicitly justified. This constraint is shared with FEAT-1809, which inherits the path convention established here — address it in FEAT-1808 first.

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1798 (Variant C specialist-role harness template) and this issue serve distinct use cases. FEAT-1798 generates a static fixed FSM for users who know their workflow phases in advance ("Plan → Research → Implement → Report, ship now"). This issue (`loop-composer`) is for users who need the workflow decomposed from a natural-language goal at runtime. These are complementary, not competing: once this issue ships, the Variant C template (FEAT-1798) should include a comment pointing users toward `loop-composer` when their goal is too open-ended for a fixed template. FEAT-1798 already has `blocked_by: [FEAT-1808]` to capture this ordering.
