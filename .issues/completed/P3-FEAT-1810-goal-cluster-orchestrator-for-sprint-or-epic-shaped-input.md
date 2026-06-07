---
id: FEAT-1810
title: "goal-cluster \u2014 Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-05-30T06:48:30Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
relates_to:
- FEAT-1808
- FEAT-1809
- FEAT-1737
decision_needed: false
confidence_score: 87
outcome_confidence: 59
score_complexity: 12
score_test_coverage: 15
score_ambiguity: 17
score_change_surface: 15
size: Very Large
completed_at: '2026-06-07T00:49:11Z'
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
- `scripts/little_loops/config/orchestration.py` — add `ClusterConfig` dataclass after `ComposerAdaptiveConfig` for `orchestration.cluster.*` settings
- `config-schema.json` — add `orchestration.cluster` schema properties (`max_batch_size`, `enable_dedup`, `propagate_context`)
- `scripts/little_loops/loops/loop-router.yaml` — add `goal-cluster` to the hard-exclude list in `discover_loops` catalog (alongside `loop-router`, `loop-composer`, `loop-composer-adaptive`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — add `ClusterConfig` to `__all__` export and import block [Agent 1 finding]
- `scripts/little_loops/loops/lib/composer.yaml` — add `excludes.add('goal-cluster')` in `discover_loops` fragment (prevents `loop-composer` from presenting `goal-cluster` as a sub-loop candidate) [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/ll_sprint/runner.py` — closest existing primitive; cluster is the FSM-loop generalization
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` (FEAT-1063, done) — sprint-scoped FSM loop precedent
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — sprint-shaped loop input precedent for `input_key:`
- FEAT-1737 (accept EPIC issues as sprint arguments) — adjacent loader work, may share code

### Loaders to Reuse
- Sprint loader: `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()` parses `.sprints/<name>.yaml` for sprint-name input; returns dependency-ordered `Sprint.issues` list
- EPIC children resolver: `SprintManager.load_or_resolve(epic_id)` in `scripts/little_loops/sprint.py` — forward lookup via `epic_info.relates_to` + backward scan for `info.parent == epic_id`; union-deduped, intersected with active-status issues (`open`/`in_progress`/`blocked`), returned as ephemeral `Sprint` with topo-ordered `issues`
- Sprint execution engine: `scripts/little_loops/cli/sprint/run.py` — `_cmd_sprint_run()` for reference on wave-walking and per-issue dispatch patterns

### Tests
- `scripts/tests/test_goal_cluster.py` (new) — input-shape normalization tests, dedup/batch logic, structural FSM tests, optional live-LLM class.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add `ClusterConfig` import + `TestClusterConfig` class; add `test_orchestration_cluster_*` methods in `TestOrchestrationConfig` and `TestBRConfigOrchestration` (pattern: `test_from_dict_defaults_composer_adaptive` at line 2553) [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_orchestration_cluster_in_schema` following `test_orchestration_host_cli_in_schema` pattern at line 502 [Agent 3 finding]
- `scripts/tests/test_loop_composer.py` — add `test_loop_router_excludes_goal_cluster` to `TestCatalogExclusivity` (line 282); add `test_discover_loops_fragment_excludes_goal_cluster` to `TestComposerLibFragment` (pattern: `test_discover_loops_fragment_excludes_adaptive_composer` at line 275) [Agent 2/3 finding]

### Configuration
- `orchestration.cluster.max_batch_size` (default 5)
- `orchestration.cluster.enable_dedup` (default true)
- `orchestration.cluster.propagate_context` (default true)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — add `#### orchestration.cluster` subsection after `#### orchestration.composer.adaptive` (line 988) with three-key table [Agent 2 finding]
- `docs/reference/API.md` — update `BRConfig` properties table row for `orchestration` (line 118); current description "host CLI selection" omits composer and cluster config [Agent 2 finding]
- `skills/create-loop/SKILL.md` — add 4th `Orch: Cluster (multi-goal fan-out)` wizard option and `goal-cluster` type mapping entry (wizard options ~line 148, Type Mapping ~line 168) [Agent 2 finding]
- `skills/create-loop/loop-types.md` — add `### Orch Cluster` section after `### Orch Supervisor` in `## Orchestration Loops` section (line 1552) [Agent 2 finding]
- `skills/create-loop/templates.md` — add Goal Cluster shape option and substitution instruction (orchestration options ~line 455) [Agent 2 finding]
- `skills/create-loop/reference.md` — add `orchestration.cluster.*` config-knobs table after `loop-composer-adaptive` table (~line 1172) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-06-06 — based on codebase analysis:_

- `SprintManager.load_or_resolve()` at `scripts/little_loops/sprint.py` is the single correct entry point for both sprint-name and EPIC-NNN input shapes; `_EPIC_ID_RE` pattern matches case-insensitively
- Sprint YAML format: `{name, description, created, issues: [IDs], options: {max_iterations, timeout, max_workers}}`; sprint FSM loops parse issues via shell `grep '^ *-' "$SPRINT_FILE" | sed 's/^ *- *//'` idiom (see `sprint-refine-and-implement.yaml:get_next_issue`)
- `lib/composer.yaml` provides the `reassess` fragment (CONTINUE/REPLAN_TAIL/ABORT) for per-batch verdict gates — accepts `captured.last_verdict.output`, `captured.completed_step_summaries.output`, `context.goal`; consume this rather than re-implementing (see FEAT-1809 coordination note)
- `lib/common.yaml` provides `queue_pop` and `queue_track` fragments for skip-list / queue walking
- `loop-composer-adaptive.yaml` already excludes `goal-cluster` from its decomposed-plan loop names (forward reference in `decompose_goal` prompt: "NEVER include 'goal-cluster' as a loop_name") — the inverse exclusion in `loop-router.yaml` is still missing and must be added
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` (line 73) uses exact set equality on `glob("*.yaml")` in `scripts/little_loops/loops/`; adding the YAML without updating the `expected` set causes a set-difference assertion failure
- Pattern to follow for `test_goal_cluster.py`: `scripts/tests/test_loop_composer.py` — file-exists check, YAML parse, FSM validate, required states, description field

## Implementation Steps

1. **Wire config**: Add `ClusterConfig` dataclass to `scripts/little_loops/config/orchestration.py` (after `ComposerAdaptiveConfig`); add `orchestration.cluster` keys to `config-schema.json`
2. **Create loop YAML**: Author `scripts/little_loops/loops/goal-cluster.yaml` with 7 states (`load_goals`, `dedup_and_batch`, `present_plan`, `execute_cluster`, `propagate_context`, `synthesize_cluster_result`, `present_result`); import `lib/common.yaml`; write all intermediate artifacts to `${context.run_dir}/` (MR-3)
3. **Wire loaders**: In `load_goals`, shell out to `SprintManager.load_or_resolve()` via Python inline script for sprint-name / EPIC-NNN input shapes; handle raw multi-line and JSON list shapes inline
4. **Reuse fragments**: For per-batch verdict gates, use `fragment: reassess` from `lib/composer.yaml`; use `queue_track` fragment for skip-list tracking between batches
5. **Update loop-router exclusion**: Add `goal-cluster` to the hard-exclude set in `loop-router.yaml::discover_loops` catalog Python inline script
6. **Write tests**: Create `scripts/tests/test_goal_cluster.py` following `scripts/tests/test_loop_composer.py`; add `"goal-cluster"` to `expected` in `test_builtin_loops.py::test_expected_loops_exist`; add `test_loop_router_catalog_exclusivity` per Scope Boundary note
7. **Update docs**: Append entry to `scripts/little_loops/loops/README.md`; add cluster-vs-composer-vs-router section to `docs/guides/LOOPS_GUIDE.md`
8. **Verify**: `python -m pytest scripts/tests/test_goal_cluster.py scripts/tests/test_builtin_loops.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Export `ClusterConfig` from `scripts/little_loops/config/__init__.py` — add to `__all__` and import block alongside `ComposerAdaptiveConfig`
10. Add `excludes.add('goal-cluster')` to `scripts/little_loops/loops/lib/composer.yaml::discover_loops` fragment (shell action lines 32–36) — prevents `loop-composer` from presenting `goal-cluster` as a candidate sub-loop
11. Update `scripts/tests/test_loop_composer.py` — add `test_loop_router_excludes_goal_cluster` to `TestCatalogExclusivity` (line 282); add `test_discover_loops_fragment_excludes_goal_cluster` to `TestComposerLibFragment` (mirrors pattern at line 275)
12. Update `scripts/tests/test_config.py` — add `ClusterConfig` import + cluster-specific test methods in `TestOrchestrationConfig` and `TestBRConfigOrchestration` (pattern: `test_from_dict_defaults_composer_adaptive` at line 2553)
13. Add `test_orchestration_cluster_in_schema` to `scripts/tests/test_config_schema.py` (pattern: `test_orchestration_host_cli_in_schema` at line 502)
14. Update `docs/reference/CONFIGURATION.md` — add `orchestration.cluster` subsection after `orchestration.composer.adaptive`
15. Update `docs/reference/API.md` — refresh `BRConfig.orchestration` property description (line 118)
16. Update `skills/create-loop/` files (SKILL.md, loop-types.md, templates.md, reference.md) — add Goal Cluster as 4th orchestration wizard option

## Open Questions

1. **Parallel batches.** When two batches have no dependency on each other (no shared goals), can they run in parallel? The FSM runner doesn't natively support intra-loop parallelism — this would need either (a) ll-parallel-style worktree dispatch, or (b) explicit fan-out in the YAML using `loop:` dispatch with `&` shell tricks. Deferred to v2 — out of scope for this issue.
2. **Cross-goal artifact conflicts.** If two goals both modify the same file, dispatching them in separate batches without coordination loses one's changes. Need a conflict detector during `dedup_and_batch` — possibly reuse `ll-sprint`'s scope-based concurrency analysis (P3-FEAT-707).
3. **Relationship to `ll-sprint`.** Does cluster eventually replace the Python sprint runner, or stay parallel? Decision deferred until the loop is real and we can compare ergonomics side-by-side.
4. **EPIC-shaped input nuance.** EPICs have a `## Children` body section AND a `relates_to:` frontmatter list. `relates_to:` is the source-of-truth (structured, machine-readable); `## Children` body section is the fallback when `relates_to:` is empty.

## Relationship to Sibling Issues

- **FEAT-1808 (loop-composer)** — composer takes *one* goal and produces a DAG of loops; cluster takes *many* goals and produces batched loop calls. Cluster might internally dispatch composer for any goal that's itself too large for one loop. Worth designing the boundary explicitly before either lands.
  - **Routing guard (added by `/ll:audit-issue-conflicts` on 2026-06-04):** Encode a dispatch allowlist in the `load_goals` or `dedup_and_batch` state: when a single goal within the cluster is too large for one loop, `goal-cluster` is permitted to dispatch `loop-composer` as a child. The reverse (`loop-composer` → `goal-cluster`) is blocked. Ensure `loop-router` catalog respects this guard so the two loops are not both presented for ambiguous multi-goal input. Coordinate with FEAT-1808's matching guard.
- **FEAT-1809 (adaptive composer)** — cluster could borrow the `reassess` pattern for per-batch verdict gates ("this batch failed, re-plan the remaining batches").
  - **Coordination note (added by `/ll:audit-issue-conflicts` on 2026-06-04):** FEAT-1809's `reassess` state is being designed as a reusable fragment in `loops/lib/composer.yaml` (see FEAT-1809 § Proposed Solution §2 design note). When implementing `goal-cluster`'s per-batch verdict gates, consume this fragment rather than re-implementing. The fragment accepts `{goal, plan, completed_steps, failing_verdict}` and returns `{decision, new_tail_plan, reason}` — directly applicable to batch-failure re-planning.
- **FEAT-1737 (EPIC as sprint argument)** — direct overlap on the EPIC-loader piece; coordinate or share code.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map references non-existent paths: `scripts/little_loops/ll_sprint/sprint_loader.py` and `scripts/little_loops/ll_sprint/runner.py`. Sprint runner code is actually at `scripts/little_loops/sprint.py` and `scripts/little_loops/cli/sprint/run.py`. Correct these before implementation.

- `/ll:verify-issues` - 2026-06-05 - Feature not implemented. Integration Map still references non-existent paths: `scripts/little_loops/ll_sprint/runner.py` (actual: `cli/sprint/run.py`) and `sprint_loader.py` (actual: `sprint.py`). This was flagged in prior verification but never corrected. Fix these paths before starting implementation.

_Paths corrected by `/ll:refine-issue` on 2026-06-06: `scripts/little_loops/ll_sprint/sprint_loader.py` → `scripts/little_loops/sprint.py` (`SprintManager.load_or_resolve()`); `scripts/little_loops/ll_sprint/runner.py` → `scripts/little_loops/cli/sprint/run.py` (`_cmd_sprint_run()`). Additional integration points added: `orchestration.py` config pattern, loop-router exclusion, `lib/composer.yaml::reassess` fragment, `test_loop_composer.py` test pattern._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-06; updated 2026-06-06 after `/ll:refine-issue` and `/ll:wire-issue` passes (EPIC Q4 source-of-truth resolved; 2 authoring gaps remain)_

**Readiness Score**: 87/100 → PROCEED
**Outcome Confidence**: 59/100 → MODERATE

### Outcome Risk Factors
- **Wide change surface across 19 files** — dominant risk is missed wiring rather than incorrect logic; use the 16-step implementation checklist as a literal checklist and verify each wiring file in order before running tests.
- **Undefined "Tier 2 LLM pass"** — `dedup_and_batch` action refers to a "Tier 2 LLM" but that term is not defined in the codebase; specify whether this means Haiku-tier, structured-output, or explicit reasoning step before authoring — prompt design and timeout strategy differ significantly.
- **`propagate_context` hints schema unspecified** — the state is described conceptually but the `hints` schema is not defined; specify `{hint_type, affected_goal_ids, hint_text}` or equivalent before authoring the `propagate_context` state.

## Session Log
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `45b701af-a0ad-475b-a0bc-501c4f4df6dc.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00 - `af591d07-71da-45fa-bdbc-cb85524ba64d.jsonl`
- `/ll:decide-issue` - 2026-06-07T00:39:46 - `620fb97a-1f61-47ba-8f5e-d14d9494cd15.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `0871bb56-70d4-42fa-ac92-8862394b87b1.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:32:28Z - `fd17f8bb-6401-4ac3-8487-d82887cca677.jsonl`
- `/ll:decide-issue` - 2026-06-07T00:28:37 - `3312de92-7550-4fbf-ba34-e739ef5b3709.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00 - `92ae2590-8ccf-4009-8a3a-7cb12a6914db.jsonl`
- `/ll:wire-issue` - 2026-06-07T00:22:28 - `6333fd1a-7244-4ce7-985e-49def1c743cf.jsonl`
- `/ll:refine-issue` - 2026-06-07T00:15:03 - `3ef5e5ff-396a-45d8-8efc-c8219339de36.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:33 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

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

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-06
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1987: goal-cluster — Config Schema & ClusterConfig
- FEAT-1988: goal-cluster — Core FSM Loop, Loaders, and Integration
- FEAT-1989: goal-cluster — create-loop Wizard Extension

---

## Status

- **State**: done
- **Created**: 2026-05-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Routing decision rule to prevent circular dispatch with FEAT-1808 (`loop-composer`): a pre-enumerated list of goals → `goal-cluster` (this issue); a single natural-language goal → `loop-composer` (FEAT-1808). `goal-cluster` MAY call `loop-composer` as a child for an individual goal that is itself too large for one loop, but `loop-composer` MUST NOT call `goal-cluster`. Encode this constraint as a routing guard in the `loop-router` catalog so the two loops are not both presented as candidates for the same ambiguous input.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): Shared integration test requirement with FEAT-1808. Both issues must include a test that verifies `loop-router`'s catalog discovery never returns both `loop-composer` and `goal-cluster` as candidates for the same input: single-goal input must route to composer only; multi-goal input must route to cluster only. Add to FEAT-1810's test plan: `test_loop_router_catalog_exclusivity` in `scripts/tests/test_goal_cluster.py`.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): After EPIC-1811 orchestration loops ship, ensure `goal-cluster`'s `load_goals` input shapes and batch API are general enough that domain-specific loops (FEAT-1806 market-strategy, future analysis loops) can be re-expressed as cluster input batches. The cluster's dedup/batching + shared-context propagation is the orchestration-layer primitive most likely to absorb standalone domain loops. Design the `goal_text` schema and `hints` mechanism with this forward-compatibility in mind.

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-06-07
- **Decomposed into**: FEAT-1987, FEAT-1988, FEAT-1989

Work for FEAT-1810 is now carried by its child issues; this parent was closed by rn-decompose.
