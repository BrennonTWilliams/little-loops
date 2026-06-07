---
id: FEAT-1988
title: "goal-cluster — Core FSM Loop, Loaders, and Integration"
type: FEAT
priority: P3
status: open
parent: FEAT-1810
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: issue-size-review
relates_to:
- FEAT-1987
- FEAT-1808
- FEAT-1809
- FEAT-1737
size: Large
---

# FEAT-1988: goal-cluster — Core FSM Loop, Loaders, and Integration

## Summary

Author the `goal-cluster.yaml` FSM loop (7 states), wire all input loaders (sprint/EPIC/raw/JSON), reuse `lib/composer.yaml::reassess` and `lib/common.yaml` fragments, update routing exclusions, write all core tests, and update loop documentation.

## Parent Issue

Decomposed from FEAT-1810: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input

## Prerequisites

Assumes FEAT-1987 (`ClusterConfig` + schema) is merged, or at minimum `config-schema.json` has the `orchestration.cluster.*` keys so loop YAML validation passes.

## Proposed Solution

### 1. Create loop YAML

Author `scripts/little_loops/loops/goal-cluster.yaml` with 7 states:

1. **`load_goals`** — accept input shapes (raw multi-line, sprint name, EPIC ID, JSON list); normalize to `[{goal_id, goal_text, hints}]`. Shell out to `SprintManager.load_or_resolve()` for sprint-name and EPIC-NNN shapes. Write normalized list to `${context.run_dir}/goals.json` (MR-3).
   - Sprint loader: `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()` for sprint-name input
   - EPIC children resolver: `SprintManager.load_or_resolve(epic_id)` — forward lookup via `epic_info.relates_to` + backward scan for `info.parent == epic_id`; intersect with active-status issues
   - EPIC source-of-truth: `relates_to:` frontmatter list is primary; `## Children` body section is fallback when `relates_to:` is empty

2. **`dedup_and_batch`** — LLM structured-output pass grouping goals by predicted loop. Goals likely for the same loop are batched. Overlapping goals surfaced for merge/skip. Dispatch allowlist guard: individual goals too large for one loop may dispatch `loop-composer` as child; reverse (`loop-composer` → `goal-cluster`) is blocked. Write batch plan to `${context.run_dir}/batch-plan.json`.

3. **`present_plan`** (optional HITL) — show batched plan, allow remove/reorder/CANCEL.

4. **`execute_cluster`** — walk batched plan in topo order. Capture each batch output to `${context.run_dir}/cluster-state.json`.

5. **`propagate_context`** — between batches, LLM extracts cross-cutting findings and updates downstream batch `hints`. Consume `fragment: reassess` from `lib/composer.yaml` for per-batch verdict gates. Use `queue_track` fragment from `lib/common.yaml` for skip-list tracking.

6. **`synthesize_cluster_result`** — emit cluster-wide summary: what accomplished, what's still open, recommended next batch.

7. **`present_result`** — structured JSON output: `{batches, per_goal_outcomes, cluster_summary, recommended_next}`.

All intermediate artifacts written under `${context.run_dir}/` (MR-3 compliance). Import `lib/common.yaml` and `lib/composer.yaml`.

### 2. Wire loaders

In `load_goals`, shell out to `SprintManager.load_or_resolve()` via Python inline script for sprint-name / EPIC-NNN input shapes; handle raw multi-line and JSON list shapes inline.

### 3. Reuse fragments

- `fragment: reassess` from `lib/composer.yaml` (CONTINUE/REPLAN_TAIL/ABORT verdict gate) — accepts `captured.last_verdict.output`, `captured.completed_step_summaries.output`, `context.goal`
- `queue_pop` and `queue_track` from `lib/common.yaml` for skip-list / queue walking

### 4. Update loop-router exclusion

Add `goal-cluster` to the hard-exclude set in `loop-router.yaml::discover_loops` catalog Python inline script alongside `loop-router`, `loop-composer`, `loop-composer-adaptive`.

### 5. Update composer lib exclusion

Add `excludes.add('goal-cluster')` to `scripts/little_loops/loops/lib/composer.yaml::discover_loops` fragment (shell action lines 32–36) — prevents `loop-composer` from presenting `goal-cluster` as a candidate sub-loop.

### 6. Write tests

Create `scripts/tests/test_goal_cluster.py` following `scripts/tests/test_loop_composer.py` pattern:
- File-exists check
- YAML parse
- FSM validate
- Required states (all 7)
- Description field
- Input-shape normalization tests
- Dedup/batch logic tests
- `test_loop_router_catalog_exclusivity`: verify `loop-router` catalog never returns both `loop-composer` and `goal-cluster` for the same input (single-goal → composer only; multi-goal → cluster only)
- Optional live-LLM class

Update `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` (line 73): add `"goal-cluster"` to `expected` set.

Update `scripts/tests/test_loop_composer.py`:
- Add `test_loop_router_excludes_goal_cluster` to `TestCatalogExclusivity` (line 282)
- Add `test_discover_loops_fragment_excludes_goal_cluster` to `TestComposerLibFragment` (mirrors `test_discover_loops_fragment_excludes_adaptive_composer` at line 275)

### 7. Update docs

- `scripts/little_loops/loops/README.md` — append `goal-cluster` entry
- `docs/guides/LOOPS_GUIDE.md` — add section on cluster vs. composer vs. router (when to use which)

### Files to Modify

- `scripts/little_loops/loops/goal-cluster.yaml` (new)
- `scripts/little_loops/loops/README.md`
- `scripts/little_loops/loops/loop-router.yaml`
- `scripts/little_loops/loops/lib/composer.yaml`
- `scripts/tests/test_goal_cluster.py` (new)
- `scripts/tests/test_builtin_loops.py`
- `scripts/tests/test_loop_composer.py`
- `docs/guides/LOOPS_GUIDE.md`

### Key Design Choices from Parent

- **Goal-list canonicalization**: all input shapes normalize to same internal list; executor is input-shape-agnostic
- **Dedup is LLM-driven**: goals overlap in natural language ways grep can't see
- **Shared context is the differentiator**: cross-batch hint propagation (`propagate_context`) is what makes this worth building vs. a shell loop
- **Tier 2 LLM pass clarification**: `dedup_and_batch` uses structured-output (JSON-schema-constrained) with explicit reasoning step, not a separate model tier — use `check_semantic: type: llm_structured` with a JSON schema for `{batches, overlaps}` output
- **`propagate_context` hints schema**: `{hint_type: str, affected_goal_ids: list[str], hint_text: str}` (array of these per propagation step)

## Acceptance Criteria

- `ll-loop validate loops/goal-cluster.yaml` passes (no MR-1/MR-3 errors)
- `ll-loop list` includes `goal-cluster`
- `python -m pytest scripts/tests/test_goal_cluster.py scripts/tests/test_builtin_loops.py scripts/tests/test_loop_composer.py -v` all pass
- `loop-router` catalog never returns both `loop-composer` and `goal-cluster` for the same input

## Session Log
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `45b701af-a0ad-475b-a0bc-501c4f4df6dc.jsonl`
