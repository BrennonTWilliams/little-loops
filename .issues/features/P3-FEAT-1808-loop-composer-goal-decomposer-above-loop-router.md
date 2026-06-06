---
id: FEAT-1808
title: "loop-composer \u2014 Goal Decomposer Built-in FSM Loop (One Level Above loop-router)"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-05-30T06:48:30Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
blocks:
- FEAT-1806
- FEAT-1809
confidence_score: 89
outcome_confidence: 72
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 18
score_change_surface: 22
implementation_order_risk: true
---

# FEAT-1808: `loop-composer` — Goal Decomposer Built-in FSM Loop (One Level Above `loop-router`)

## Summary

Add a new built-in FSM loop `loop-composer` that accepts a natural-language goal too large for a single existing loop, decomposes it into an ordered DAG of `loop-router` calls (or direct sub-loop invocations), then walks the plan to execution. Each node in the plan is an existing loop; the composer is purely an orchestration layer that turns "I want to ship feature X" into "refine → wire → plan → implement → review → PR".

## Motivation

`loop-router` (FEAT-1654, done) solved *one-goal → one-loop*. The next layer up is *one-goal → many-loops*. Today users compose multi-loop workflows manually by chaining slash commands, calling `ll-sprint`, or wiring a bespoke loop for each recurring multi-step pattern. The catalog has the right *primitives* but no composer to sequence them from intent.

**Why:** Plenty of real goals ("ship the auth migration", "audit and harden the loops directory") naturally fan out across 3–6 existing loops; there is no general entry point for them.
**How to apply:** This is purely an orchestration layer — the composer never *does* work, it only sequences other loops. All actual work stays in the leaf loops `loop-router` already knows how to dispatch.

## Use Case

**Who**: Developer using the ll-loop orchestration system

**Context**: When they have a complex natural-language goal ("ship feature X", "audit and harden the loops directory") that naturally spans 3–6 existing loops — too large for a single loop dispatch

**Goal**: Turn a high-level intent into an ordered, executable sequence of existing loops without manually chaining slash commands or writing a bespoke loop YAML for each recurring multi-step pattern

**Outcome**: `loop-composer` decomposes the goal, presents an inspectable plan for approval (HITL gate), then walks the DAG sequentially — returning a structured summary of all step results when complete

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL: Fragment sharing does NOT use `loop: lib/composer.yaml#<state>` syntax.**
`scripts/little_loops/fsm/fragments.py:resolve_fragments()` resolves fragments via a `fragments:` top-level mapping in lib YAML files. The `loop:` key dispatches a whole child FSM — `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py` has no `#state` extraction logic. The `reusable: true` key is not recognized anywhere in the engine. The correct sharing mechanism: define `discover_loops`, `validate_plan`, and `present_plan` under a `fragments:` mapping in `lib/composer.yaml`, then reference them via `fragment: discover_loops` (etc.) inside the loop YAML states. All six existing lib files (`common.yaml`, `cli.yaml`, `harness.yaml`, etc.) follow this `fragments:` mapping pattern — none use `reusable: true`.

**CRITICAL: `${plan_state.step_N.output}` interpolation requires dict-typed context values.**
`scripts/little_loops/fsm/interpolation.py:_get_nested()` walks dot-separated paths through Python dicts. Context values are string-typed from the YAML `context:` block. If `plan_state` is stored as a JSON string (`'{"step_1": {"output": "..."}}'`), `_get_nested` will fail on `plan_state.step_1` because it tries to subscript a string, not a dict. Implementation options: (a) use shell states to write per-step output to `${context.run_dir}/checkpoints/step-N.json` and read them back with shell `cat` (the pattern used by `general-task.yaml` and `rn-decompose.yaml`), rather than relying on `${plan_state.step_N.output}` context interpolation; or (b) understand that context values set programmatically during execution (not from the YAML `context:` block) can be dict-typed. Option (a) is the safe, proven path.

**Sub-loop dispatch routing verbs:** use `on_yes`/`on_no`/`on_error` when `capture:` is set on the dispatch state (the `loop-router` pattern); use `on_success`/`on_failure`/`on_error` when `context_passthrough: true` is set (the `recursive-refine` pattern). For `execute_plan`'s per-node dispatch, the `capture:` variant is appropriate since step outputs need to be persisted.

**`discover_loops` shell pattern from `loop-router.yaml`:** the excludes logic is an inline Python block that (1) splits `${context.exclude}` on commas for user-configurable exclusions, then (2) unconditionally calls `excludes.add('loop-router')`. FEAT-1808's `discover_loops` fragment must add `excludes.add('loop-composer')` in the same inline Python, and the copy in `loop-router.yaml` must add `excludes.add('loop-composer')` to its inline Python (wiring step 8).

**`test_expected_loops_exist` currently has 69 loops** in its `expected` set; `loop-composer` will be the 70th. The test glob is `*.yaml` (top-level only), so `lib/composer.yaml` is not in scope.

## Acceptance Criteria

- [ ] `loop-composer.yaml` accepts a natural-language goal and decomposes it into an ordered DAG of ≤8 `{step_id, loop_name, input, depends_on}` nodes
- [ ] Plan validation rejects: unknown loop names, cyclic dependencies, and plans exceeding the configured node cap
- [ ] HITL gate (`present_plan`) blocks execution when `${context.auto}` is false or cost-estimate exceeds threshold; user can approve, edit, or CANCEL
- [ ] Sequential execution walks the plan in correct topological order
- [ ] Plan JSON is persisted to `${context.run_dir}/composer-plan.json` and survives re-runs
- [ ] Step outputs stored in `${context.plan_state}` and interpolatable by later steps via `${plan_state.step_N.output}`
- [ ] `lib/composer.yaml` exposes `discover_loops`, `validate_plan`, `present_plan` under a top-level `fragments:` mapping, referenced from loop states via `fragment: <name>` (NOT `reusable: true` / `loop: lib/composer.yaml#<state>` — neither is recognized by the engine; see Codebase Research Findings)
- [ ] Verdict struct `{success, confidence, terminal_state}` captured per step in `${context.plan_state.last_verdict}`
- [ ] Checkpoints written to `${context.run_dir}/checkpoints/step-<N>.json` after each sub-loop completes
- [ ] `ll-loop validate` reports no MR-3 violations; all intermediate artifacts use `${context.run_dir}/`
- [ ] `test_loop_router_catalog_exclusivity` passes: single-goal input routes to `loop-composer` only; multi-goal input routes to `goal-cluster` only
- [ ] `loop-composer` never dispatches `goal-cluster` as a child node

## API/Interface

`loop-composer` is an FSM loop artifact, not a Python module. Its public interface is the `ll-loop` invocation contract:

```yaml
# Invocation
# ll-loop run loop-composer --input "natural-language goal string"

# Context flags
# context.auto: false  (default — requires HITL approval before execution)
# orchestration.composer.max_plan_nodes: 8  (default node cap)
# orchestration.composer.auto: false  (config-level override)
```

Output (structured JSON from `present_result` state):
```json
{
  "plan": [{"step_id": "...", "loop_name": "...", "input": "...", "depends_on": []}],
  "step_results": {"step_id": {"output": "...", "success": true, "confidence": 0.9}},
  "success": true,
  "summary": "prose summary of all step results"
}
```

## Implementation Steps

1. Create `scripts/little_loops/loops/lib/composer.yaml` with `discover_loops`, `validate_plan`, and `present_plan` defined under a top-level `fragments:` mapping (mirroring `lib/common.yaml`, `lib/cli.yaml`, etc.) — do NOT mark them `reusable: true` (unrecognized key)
2. Create `scripts/little_loops/loops/loop-composer.yaml` with `decompose_goal → validate_plan → present_plan → execute_plan → review_chain → present_result` FSM; reference the shared states via `fragment: discover_loops` / `fragment: validate_plan` / `fragment: present_plan` keys inside the loop states (resolved by `fsm/fragments.py:resolve_fragments()`)
3. Implement `execute_plan` with topological DAG walk, verdict-gate hook capturing `{success, confidence, terminal_state}` per step, and checkpoint writes to `${context.run_dir}/checkpoints/step-<N>.json`
4. Implement state interpolation so step N+1 `input` can reference `${plan_state.step_N.output}`
5. Add `scripts/tests/test_loop_composer.py`: schema validation, plan-parsing, cycle-detection, and `test_loop_router_catalog_exclusivity`
6. Update `docs/guides/LOOPS_GUIDE.md`, `scripts/little_loops/loops/README.md`, and add `"loop-composer"` to `test_builtin_loops.py::test_expected_loops_exist`
7. Run `ll-loop validate loop-composer` — confirm no MR-1 or MR-3 violations

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/loops/loop-router.yaml` — add `excludes.add('loop-composer')` to the inline Python in `discover_loops`, parallel to the existing `excludes.add('loop-router')` (blocking routing guard per Scope Boundary)
9. Update `config-schema.json` — add `"composer"` nested object under `"orchestration"` with `"max_plan_nodes"` (type: integer, default: 8) and `"auto"` (type: boolean, default: false) before any user sets these config keys (`"additionalProperties": false` is set on the `orchestration` object)
10. Update `scripts/little_loops/loops/README.md` — add `lib/composer.yaml` row to the Fragment Libraries table (~lines 179–186); this is a second distinct edit from the loop catalog entry in step 6
11. Update `skills/create-loop/templates.md` — replace Composer "Forthcoming" label with `ll-loop run loop-composer` instruction and remove "not yet available" prose at line 467
12. Update `skills/create-loop/loop-types.md` — add Orch Composer branch alongside Orch Router to distinguish single-goal routing from multi-loop DAG decomposition
13. Verify `lib/composer.yaml` omits `initial:` so `test_doc_counts.py::test_lib_fragments_are_not_runnable` continues to pass
14. Verify all five parametrized sweep tests in `test_builtin_loops.py` pass with the new `loop-composer.yaml` before opening the PR

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-composer.yaml` (new)
- `scripts/little_loops/loops/README.md` — append composer entry
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"loop-composer"` to the `expected` set
- `docs/guides/LOOPS_GUIDE.md` — note composer as the multi-loop entry point sitting above `loop-router`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/lib/composer.yaml` (new) — shared fragment library exposing `discover_loops`, `validate_plan`, `present_plan` under a top-level `fragments:` mapping, referenced via `fragment: <name>` (in impl steps but absent from this map) [Agent 1 finding]
- `scripts/little_loops/loops/loop-router.yaml` — add `excludes.add('loop-composer')` to the inline Python in `discover_loops` state, parallel to `excludes.add('loop-router')` (blocking routing guard per Scope Boundary) [Agent 2 finding]
- `config-schema.json` — add `"composer"` nested object under `"orchestration"` with `max_plan_nodes` (integer, default 8) and `auto` (boolean, default false); required before any user sets these keys because `"additionalProperties": false` is set on the `orchestration` object [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/loop-router.yaml` — direct ancestor; reuse catalog discovery and HITL shape
- `scripts/little_loops/loops/outer-loop-eval.yaml` — orchestrating-loop pattern (FEAT-933)
- `scripts/little_loops/loops/recursive-refine.yaml` — multi-state loop with sub-loop dispatch
- `ll-sprint` runner — closest existing multi-issue orchestrator (different shape: it walks issues, not loops)

### Tests
- `scripts/tests/test_loop_composer.py` (new) — schema validation, plan-parsing tests, structural assertions on the state graph, optional `@pytest.mark.slow` live-LLM class.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py` — `test_lib_fragments_are_not_runnable` auto-sweeps `loops/lib/`; `lib/composer.yaml` must omit `initial:` to pass (verify, no code change needed) [Agent 3 finding]
- `test_builtin_loops.py` sweep tests — five parametrized checks (`test_all_validate_as_valid_fsm`, `test_all_have_description_field`, `test_no_bare_pass_token_in_output_contains`, `test_no_bare_bash_variable_in_shell_actions`, `test_all_failure_terminals_have_diagnostic_action`) auto-pick up `loop-composer.yaml`; verify all pass before merging [Agent 3 finding]
- Suggested test class structure for `test_loop_composer.py`: `TestLoopComposerFile` (file/parse/validate/fields), `TestLoopComposerStates` (required states, per-state assertions), `TestComposerLibFragment` (reusable fragment states), `TestComposerPlanParsing` (valid plan, missing step_id, cycle in depends_on, unknown loop_name, node cap), `TestCatalogExclusivity` (`test_loop_router_catalog_exclusivity`), `TestLoopComposerLive` (`@pytest.mark.slow` + `@pytest.mark.skipif` guard) — follow pattern from `scripts/tests/test_loop_router.py` [Agent 3 finding]

### Configuration
- Consider `orchestration.composer.max_plan_nodes` (default 8) and `orchestration.composer.auto` (default false — composer should HITL by default given blast radius).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/templates.md` — Orchestration shape menu marks Composer as "Forthcoming (see FEAT-1808)"; update to active (`ll-loop run loop-composer`) and remove "not yet available" prose after ship [Agent 2 finding]
- `skills/create-loop/loop-types.md` — Orch Router section directs users to clone `loop-router`; add guidance distinguishing router (single goal → best existing loop) vs. composer (complex goal → ordered DAG of loops) [Agent 2 finding]
- `skills/create-loop/reference.md` — Dispatch-state documentation references only `loop-router` as the canonical sub-loop dispatch example; add `loop-composer` as a second canonical DAG-walk dispatch pattern [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — loop type classification table (~line 144) needs a Composer row (distinct from the routing section update already in Files to Modify) [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — Fragment Libraries table (~lines 179–186) needs a `lib/composer.yaml` entry; distinct from the loop catalog entry already listed [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` resolves `fragment: <name>` keys against the `fragments:` mapping in lib files (NOT `lib/composer.yaml#<state>` syntax, which is unsupported); no code changes expected, but verify existing fragment resolution handles the new lib file [Agent 1 finding, corrected]
- `scripts/little_loops/fsm/interpolation.py` — resolves `${plan_state.step_N.output}` references; verify nested plan_state path interpolation is supported before implementing the state interpolation step [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/fragments.py:resolve_fragments()` — the fragment system resolves `fragment: <name>` keys in states against a `fragments:` top-level mapping in lib files. `lib/composer.yaml` must use a `fragments:` mapping (NOT `states:` + `reusable: true`). The `#state` reference syntax in `loop:` is not supported — `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py` resolves whole loop files, not individual states within them.
- `scripts/little_loops/fsm/interpolation.py:_get_nested()` — nested dot-path traversal works on Python dicts. `plan_state` context values must be dict-typed (set programmatically by the executor) for `${plan_state.step_N.output}` to work; string-serialized JSON stored in the YAML `context:` block will NOT be traversable. Recommend using shell checkpoint files at `${context.run_dir}/checkpoints/step-N.json` instead of context-level interpolation for step output passing.
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` — sub-loop dispatch routing: states with `capture:` key route via `on_yes`/`on_no`/`on_error`; states with `context_passthrough: true` route via `on_success`/`on_failure`/`on_error`. Use `on_yes`/`on_no` for the per-node dispatch states in `execute_plan`.
- `scripts/little_loops/loops/general-task.yaml` — checkpoint write/read/delete lifecycle pattern: `printf '{"step":"%s","timestamp":"%s"}' > "${context.run_dir}/checkpoints/step-N.json"`. Follow this exact shape for FEAT-1808's per-step checkpoint writes.
- `scripts/little_loops/loops/lib/common.yaml` — provides `queue_pop`, `queue_track`, `shell_exit`, `retry_counter` fragments directly usable in `loop-composer`. Consider `retry_counter` for bounded decompose retries.

## Open Questions

1. **Plan schema format.** YAML inline vs. dedicated JSON blob. Probably JSON because the LLM emits it and we already have JSON tooling.
2. **Failure semantics.** When step 4 of 6 fails, do we stop, continue, or re-plan the tail? For the MVP: stop and report. Re-planning is FEAT-1809.
3. ~~**Reusing `recursive-refine`'s shape?**~~ **CLOSED** — `recursive-refine` (`scripts/little_loops/loops/recursive-refine.yaml`) uses a queue+depth-tracking shape designed for *unknown-boundary recursive discovery*: it dequeues one item, runs a sub-loop, and if the sub-loop decomposes the item it enqueues children at `parent_depth + 1`. The plan queue is open-ended; the loop terminates when the queue empties or budget exhausts. `loop-composer` is structurally different: the plan is bounded and fully known before execution begins (`decompose_goal` emits a complete JSON DAG), nodes are walked in topological order, and there is no child-enqueue step. The state graphs do not overlap. Do NOT adapt `recursive-refine`'s shape — use `loop-router.yaml` as the ancestor (HITL + dispatch pattern) and `general-task.yaml` for the checkpoint read/write lifecycle.

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
   These MUST be defined under a top-level `fragments:` mapping (the pattern used by
   every existing `lib/*.yaml`) so both `loop-composer.yaml` and
   `loop-composer-adaptive.yaml` reference them via a `fragment: <name>` key in their
   states. Do NOT use `reusable: true` or `loop: lib/composer.yaml#<state>` — neither is
   recognized by the engine (`fsm/fragments.py:resolve_fragments()` resolves the
   `fragments:` mapping; `resolve_loop_path()` has no `#state` extraction). See the
   CRITICAL note in Codebase Research Findings.

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

- `/ll:verify-issues` - 2026-06-05 - Feature not implemented. Body contains conflicting references: some sections use `context.run_dir/` (correct per MR-3) while scope boundary notes still reference stale `.loops/tmp/` paths. Resolve this contradiction in the body before starting implementation. `loop-composer.yaml` does not exist yet.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-06 (post refine-issue + wire-issue pass)_

**Readiness Score**: 89/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors

- ~~**`reusable: true` spec contradiction in acceptance criteria**~~ **RESOLVED** (2026-06-06): AC-7, Implementation Steps 1–2, the Integration Map, and the Design Constraint section previously specified `reusable: true` states referenced via `loop: lib/composer.yaml#<state>`. Both mechanisms are unrecognized by the engine (CRITICAL research finding). All four sections now prescribe the `fragments:` top-level mapping + `fragment: <name>` reference pattern used by every existing `lib/*.yaml`. No remaining `reusable: true` references in the spec.
- **Tests are co-deliverables**: `execute_plan`, `validate_plan`, and `decompose_goal` states live in YAML and are not directly unit-testable. Tests are co-deliverables — write `test_loop_composer.py` cycle-detection and plan-parsing tests alongside YAML authoring, not after.
- **HITL cost-estimate threshold unspecified**: `present_plan` condition references a cost-estimate threshold that is not defined in `config-schema.json` or the config interface section. Define or drop it before implementing the HITL gate condition.

## Session Log
- `/ll:confidence-check` - 2026-06-06T22:00:00Z - `8ca99a59-7946-4709-b040-2d8d0c6a144b.jsonl`
- `/ll:refine-issue` - 2026-06-06T21:26:33 - `e5ece679-fa95-499d-831d-5b8f7df99a47.jsonl`
- `/ll:wire-issue` - 2026-06-06T21:20:10 - `b909cf61-8cbb-4e9e-bd01-7eb935601be7.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `d0f98747-4363-4b4e-b794-19c4467e0b49.jsonl`
- `/ll:format-issue` - 2026-06-06T21:09:52 - `14697907-ef57-4058-9a37-92c45ac2362d.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

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
