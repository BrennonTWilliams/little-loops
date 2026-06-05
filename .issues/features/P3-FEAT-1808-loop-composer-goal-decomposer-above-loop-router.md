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
blocks: [FEAT-1806, FEAT-1809]
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
- **Plan is inspectable.** A pure-shell executor walks a YAML/JSON manifest. The plan is logged, dumped to `${context.run_dir}/composer-plan.json`, and survives re-runs. This is the deliberate *non*-reactive choice — see FEAT-1809 for the reactive variant.
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
  - **Routing guard (added by `/ll:audit-issue-conflicts` on 2026-06-04):** Encode a dispatch rule in the `loop-router` catalog so `loop-composer` and `goal-cluster` are not both presented as candidates for the same ambiguous input. `loop-composer` MUST NOT call `goal-cluster` as a child; `goal-cluster` MAY call `loop-composer` for an individual oversized goal. Add an allowlist/blocklist guard at the `discover_loops` state that enforces this when the loop catalog is loaded.
- **FEAT-1806 (market strategy loop)** — blocked by this issue; may become a composer plan template rather than a standalone loop YAML once this ships.
  - **Post-implementation checklist (added by `/ll:audit-issue-conflicts` on 2026-06-04):** After FEAT-1808 ships, evaluate FEAT-1806 for re-expression as a `loop-composer` plan template (saved JSON plan: scan → model → analyze → generate → simulate → recommend). If viable: (a) add a deprecation note to FEAT-1806 recommending the template approach, (b) update FEAT-1806's `blocked_by` to reference the composer plan template if it becomes the preferred implementation path.

## Design Constraint: Extension Points for FEAT-1809

**Decision** (resolved by `/ll:audit-issue-conflicts` on 2026-06-04): The fork-vs-flag
question (FEAT-1809 Open Question 1) is resolved in favor of the **Fragment** approach.

FEAT-1808 implementation MUST include:

1. **Shared lib fragment** at `scripts/little_loops/loops/lib/composer.yaml` containing:
   - `discover_loops` — catalog discovery (reused from `loop-router`)
   - `validate_plan` — plan parsing, cycle detection, node-cap enforcement
   - `present_plan` — HITL gate shell action
   These states MUST be `reusable: true` so both `loop-composer.yaml` and
   `loop-composer-adaptive.yaml` reference them via `loop: lib/composer.yaml#<state>`.

2. **Verdict-gate hook pattern** at the `execute_plan` exit point: after each sub-loop
   step completes, a verdict struct `{success, confidence, terminal_state}` is captured
   to `${context.plan_state}`. FEAT-1809 layers onto this by adding a `reassess` state
   that reads `${context.plan_state.last_verdict}` and routes to CONTINUE/REPLAN_TAIL/ABORT.
   FEAT-1808 does NOT implement the reassess logic — it only captures and forwards
   the verdict struct so FEAT-1809 has a clean injection point.

3. **Checkpoint persistence** at `${context.run_dir}/checkpoints/step-<N>.json` so
   FEAT-1809's re-plan can consume completed step outputs without re-running upstream
   states. FEAT-1808 writes checkpoints but doesn't read them (no re-plan path);
   FEAT-1809 adds the read path.

This constraint resolves FEAT-1809 Open Question 1 and ensures FEAT-1808 does not
ship with a monolithic design that FEAT-1809 would need to fork.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — MR-3 violation in FSM design section: artifact path `.loops/tmp/loop-composer-plan.json` must be changed to `${context.run_dir}/loop-composer-plan.json` before the loop YAML is created. Fix this before implementation to avoid `ll-loop validate` MR-3 WARNING.

## Session Log

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:55:12 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T15:34:39 - `6a79563f-0323-4d72-9ccb-855c43c698c9.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
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

**Note** (added by `/ll:audit-issue-conflicts`): Routing decision rule to prevent circular dispatch with FEAT-1810 (`goal-cluster`): a single natural-language goal → `loop-composer` (this issue); a pre-enumerated list of goals → `goal-cluster` (FEAT-1810). `goal-cluster` MAY call `loop-composer` as a child for an individual oversized goal, but `loop-composer` MUST NOT call `goal-cluster`. Encode this as a routing guard in the `loop-router` catalog so the two loops are not both presented as candidates for the same ambiguous input.

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1798 (Variant C specialist-role harness template) and this issue serve distinct use cases. FEAT-1798 generates a static fixed FSM for users who know their workflow phases in advance ("Plan → Research → Implement → Report, ship now"). This issue (`loop-composer`) is for users who need the workflow decomposed from a natural-language goal at runtime. These are complementary, not competing: once this issue ships, the Variant C template (FEAT-1798) should include a comment pointing users toward `loop-composer` when their goal is too open-ended for a fixed template. FEAT-1798 already has `blocked_by: [FEAT-1808]` to capture this ordering.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): Shared integration test requirement with FEAT-1810. Both issues must include a test that verifies `loop-router`'s catalog discovery never returns both `loop-composer` and `goal-cluster` as candidates for the same input: single-goal input must route to composer only; multi-goal input must route to cluster only. Add to FEAT-1808's test plan: `test_loop_router_catalog_exclusivity` in `scripts/tests/test_loop_composer.py`.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): Extension-point requirement for FEAT-1809 compatibility. FEAT-1808's current spec describes a monolithic `loop-composer.yaml` with no extension points, but FEAT-1809 (adaptive re-plan variant) needs to layer onto it. The fork-vs-flag question (FEAT-1809 Open Question 1) MUST be resolved before FEAT-1808 implementation begins. At minimum, FEAT-1808 MUST expose extension points — shared fragments in `loops/lib/composer.yaml` (already referenced in the proposed solution) and a strategy/hook pattern for the verdict-gate/reassess step — so FEAT-1809 can add adaptive behavior without forking the entire loop file. FEAT-1808 already has `blocks: [FEAT-1809]` capturing the ordering dependency; this note adds the design constraint that the ordering alone doesn't capture.

## Verification Notes (2026-06-05)

- **MR-3 violation flag not yet corrected**: Prior verification flagged `.loops/tmp/` path usage
  which violates per-run artifact isolation rules.
- `loop-router.yaml` exists at `scripts/little_loops/loops/loop-router.yaml`.
- `loop-composer.yaml` does not exist (expected).
- Blocks FEAT-1806 and FEAT-1809 (both still open).
