---
id: FEAT-1989
title: "goal-cluster \u2014 create-loop Wizard Extension"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-07T01:51:45Z'
discovered_date: 2026-06-06
discovered_by: issue-size-review
relates_to:
- FEAT-1988
- FEAT-1810
size: Small
confidence_score: 96
outcome_confidence: 79
score_complexity: 23
score_test_coverage: 15
score_ambiguity: 23
score_change_surface: 18
---

# FEAT-1989: goal-cluster — create-loop Wizard Extension

## Summary

Extend the `skills/create-loop/` wizard to surface `goal-cluster` as a 4th orchestration option alongside `loop-composer`, `loop-composer-adaptive`, and other orchestration loops.

## Current Behavior

The `create-loop` wizard offers 3 Orch options (Router, Composer, Supervisor/Adaptive) but has no `goal-cluster` (multi-goal fan-out) option. Users with sprint- or EPIC-shaped input (a *list* of goals) have no guided wizard path; they must author `goal-cluster` invocations manually.

## Expected Behavior

The wizard presents `Orch: Cluster (multi-goal fan-out)` as a 4th orchestration option. Selecting it provides contextual guidance (when to use, config knobs, template stub) so users can set up goal-cluster runs without consulting external docs.

## Use Case

A developer running a sprint review wants to orchestrate 8 open issues as a batch. They invoke `/ll:create-loop`, choose `Orchestration`, and now see `Orch: Cluster` alongside the existing three options. Selecting it shows the 7-state template with `${context.run_dir}/` artifact paths and documents the `orchestration.cluster.*` config knobs — letting them parameterize `max_batch_size` and `enable_dedup` without reading source YAML.

## Parent Issue

Decomposed from FEAT-1810: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input

## Prerequisites

FEAT-1988 (`goal-cluster.yaml` loop) should be merged so the wizard can reference a real loop. However, this skill update is independently shippable and can be done in parallel.

## Proposed Solution

Update the four `skills/create-loop/` skill files to add Goal Cluster as a 4th orchestration wizard option:

### 1. `skills/create-loop/SKILL.md`

Add `Orch: Cluster (multi-goal fan-out)` wizard option (~line 148) and `goal-cluster` type mapping entry in the Type Mapping section (~line 168).

### 2. `skills/create-loop/loop-types.md`

Add `### Orch Cluster` section after `### Orch Supervisor` (~line 1648) in the `## Orchestration Loops` section (~line 1552) describing:
- When to use: user has a *list* of goals (sprint, EPIC, backlog slice), not a single goal
- Differentiators vs. loop-composer: fan-out of many goals vs. decomposition of one goal
- Key states: `load_goals`, `dedup_and_batch`, `propagate_context`, `synthesize_cluster_result`

### 3. `skills/create-loop/templates.md`

Add Goal Cluster shape option in the orchestration options section (~line 455) with a template stub showing the 7-state structure and `${context.run_dir}/` artifact paths.

### 4. `skills/create-loop/reference.md`

Add `orchestration.cluster.*` config-knobs table after the `loop-composer-adaptive` table (~line 1172):

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `orchestration.cluster.max_batch_size` | integer | 5 | Max goals per batch |
| `orchestration.cluster.enable_dedup` | boolean | true | LLM-driven dedup pass |
| `orchestration.cluster.propagate_context` | boolean | true | Cross-batch hint propagation |

### Files to Modify

- `skills/create-loop/SKILL.md`
- `skills/create-loop/loop-types.md`
- `skills/create-loop/templates.md`
- `skills/create-loop/reference.md`

## Impact

- **Priority**: P3 — Minor UX gap; users can work around by authoring goal-cluster manually
- **Effort**: Small — 4 markdown files, additive text insertions only, no code changes
- **Risk**: Low — purely documentation/wizard content; no runtime behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `create-loop`, `wizard`, `orchestration`, `goal-cluster`

## Acceptance Criteria

- `create-loop` wizard presents `Orch: Cluster` as an option when user selects Orchestration loop type
- `loop-types.md` has a `### Orch Cluster` section with when-to-use guidance
- `reference.md` documents all three `orchestration.cluster.*` config keys
- No broken references in updated skill files

---

**Open** | Created: 2026-06-06 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-07T01:49:22 - `24f94034-9d91-4675-84d4-e06bd909fd5c.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `45b701af-a0ad-475b-a0bc-501c4f4df6dc.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `1ccdf13a-9ffb-4c3a-9d3c-5de137803a42.jsonl`
