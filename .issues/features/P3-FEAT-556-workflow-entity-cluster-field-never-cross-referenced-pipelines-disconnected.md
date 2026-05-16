---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
---

# FEAT-556: `Workflow.entity_cluster` / `semantic_cluster` never cross-referenced — entity and workflow pipelines are fully disconnected

## Summary

The `Workflow` dataclass has `entity_cluster` and `semantic_cluster` fields intended to link detected workflows back to the entity clusters they belong to. Both fields are always `null` in output. The entity clustering pipeline (`_cluster_by_entities`) and the workflow detection pipeline (`_detect_workflows`) run as fully independent passes in `analyze_workflows` with no cross-referencing step between them.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 150–178 (`Workflow` dataclass), 630–745 (`_detect_workflows`), 793–803 (`analyze_workflows` pipeline calls) (at verification: 2026-03-14; scan commit: HEAD)
- **Anchor**: `class Workflow`, `in function _detect_workflows`, `in function analyze_workflows`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L158-L175)
- **Code**:
```python
@dataclass
class Workflow:
    ...
    entity_cluster: str | None = None      # always None
    semantic_cluster: str | None = None    # always None
    ...

# In analyze_workflows:
entity_clusters = _cluster_by_entities(messages)       # independent pass
boundaries = _compute_boundaries(messages)             # independent pass
workflows = _detect_workflows(messages, boundaries, patterns)  # independent pass
# No cross-reference step between entity_clusters and workflows
```

## Current Behavior

Each `Workflow` in the output YAML has `entity_cluster: null` and `semantic_cluster: null`. Users cannot tell which entity cluster a detected workflow belongs to, making the two analysis perspectives (entity-based clustering vs. template-based workflow detection) completely siloed.

## Expected Behavior

After both pipelines complete, a cross-reference step in `analyze_workflows` links each `Workflow` to the `EntityCluster` with the highest entity overlap. `workflow.entity_cluster` is populated with the matching cluster's `cluster_id` (or `null` if no cluster reaches the overlap threshold). Similarly, `workflow.handoff_points` is populated by calling `_detect_handoff` on workflow messages (currently only called from `_link_sessions`).

## Motivation

The `Workflow` dataclass was designed with `entity_cluster` and `semantic_cluster` fields to provide a unified view linking template-based workflow detection with entity-based clustering. These fields have never been populated, leaving users with two disconnected analysis perspectives in the output YAML. Anyone consulting `ll-workflows` output to understand session relationships cannot correlate which entity cluster (e.g., `["fsm", "loop", "yaml"]`) was associated with a detected workflow — the two pipelines tell parallel stories with no bridge. The complementary issue FEAT-555 (populating `EntityCluster.inferred_workflow`) confirms this cross-reference was a planned design intent, not an accident.

## Use Case

A developer opens the analysis YAML to understand why two sessions were linked. They see `workflow_id: wf-001, entity_cluster: cluster-003` — clicking through to `cluster-003` shows which entities (e.g., `["fsm", "loop", "yaml"]`) bound those sessions together. Without this cross-reference, the entity cluster and workflow sections tell separate stories with no way to connect them.

## Acceptance Criteria

- [x] After analysis, each `Workflow` with message UUIDs overlapping an `EntityCluster` has `entity_cluster` set to that cluster's `cluster_id`
- [x] When multiple clusters overlap, the cluster with highest entity overlap wins
- [x] Workflows with no cluster overlap have `entity_cluster: null`
- [x] `handoff_points` is populated from `_detect_handoff` on workflow message content
- [x] Output YAML schema is backward compatible

## Proposed Solution

Add a cross-reference step at the end of `analyze_workflows`:

```python
# Cross-reference: link workflows to entity clusters
workflow_uuids_to_cluster: dict[str, str] = {}
for cluster in entity_clusters:
    for msg in cluster.messages:
        uuid = msg.get("uuid", "")
        if uuid:
            workflow_uuids_to_cluster[uuid] = cluster.cluster_id

for workflow in workflows:
    # Find best-matching cluster by UUID intersection
    cluster_votes: dict[str, int] = {}
    for msg in workflow.messages:
        cluster_id = workflow_uuids_to_cluster.get(msg.get("uuid", ""))
        if cluster_id:
            cluster_votes[cluster_id] = cluster_votes.get(cluster_id, 0) + 1
    if cluster_votes:
        workflow.entity_cluster = max(cluster_votes, key=cluster_votes.__getitem__)

    # Populate handoff_points
    for msg in workflow.messages:
        if _detect_handoff(msg.get("content", "")):
            workflow.handoff_points.append({"uuid": msg.get("uuid", ""), "type": "explicit_handoff"})
```

## API/Interface

`Workflow.entity_cluster` changes from always-`None` to `str | None`:
```python
entity_cluster: "cluster-001" | None
```

No schema breaking change.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows`, add cross-reference step after pipeline calls

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — `TestAnalyzeWorkflows` or `TestDetectWorkflows`, add `entity_cluster` assertions

### Similar Patterns
- FEAT-555 populates `EntityCluster.inferred_workflow` — these two features are complementary (each side of the relationship)

### Tests
- Add test asserting `workflow.entity_cluster` is set when messages overlap an entity cluster
- Add test asserting `workflow.handoff_points` is populated when `/ll:handoff` appears in a workflow message

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. After the three pipeline calls in `analyze_workflows`, build a `uuid → cluster_id` index from `entity_clusters`
2. For each `Workflow`, find the cluster with the most UUID matches and assign `workflow.entity_cluster`
3. For each `Workflow`, scan messages with `_detect_handoff` and populate `handoff_points`
4. Add tests for both assignments

## Impact

- **Priority**: P3 - The two main analysis passes produce disconnected output; cross-referencing them was clearly the intent (the fields exist) but was never implemented
- **Effort**: Medium - New cross-reference logic, ~30 lines in `analyze_workflows`
- **Risk**: Low - Additive change; no existing logic modified, only new assignments to always-null fields
- **Breaking Change**: No

## Verification Notes

- **2026-03-05** — VALID. Core claims confirmed accurate: `entity_cluster` and `semantic_cluster` are always `None`; `analyze_workflows` has no cross-reference step (lines 770–772 confirm three independent pipeline calls with no linkage after). `_detect_handoff` exists (line 374) but is only called from `_link_sessions`, not from `_detect_workflows`. Line numbers updated from scan-commit values to current HEAD positions. Dependency: FEAT-558 correctly has `Blocked By: FEAT-556`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-549
- ENH-550
- ENH-551

_(FEAT-558 removed from Blocks — completed)_

## Blocked By

_(None — ENH-553 completed)_

## Labels

`feature`, `workflow-analyzer`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: pipelines completely disconnected
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `entity_cluster` and `semantic_cluster` still always None in `analyze_workflows`; removed stale Blocks: FEAT-558 (completed)
- `/ll:ready-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b42c11f4-0043-41b6-a29a-8101a412d7f5.jsonl` — CORRECTED: updated line numbers (line drift); cleared blocker ENH-553 (completed)

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/077cb097-03ba-4238-821d-bce751e9786d.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/077cb097-03ba-4238-821d-bce751e9786d.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/077cb097-03ba-4238-821d-bce751e9786d.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/077cb097-03ba-4238-821d-bce751e9786d.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

## Resolution

Implemented cross-reference step in `analyze_workflows` (`workflow_sequence_analyzer.py:806–829`):
- Builds a `uuid → cluster_id` index from all entity clusters
- Builds a `uuid → content` index from raw messages for handoff detection
- For each workflow, votes on clusters by UUID intersection and assigns the winner to `entity_cluster`
- For each workflow, scans message content via `_detect_handoff` and appends `{"uuid": ..., "type": "explicit_handoff"}` entries to `handoff_points`

Added two tests to `TestAnalyzeWorkflows` in `test_workflow_sequence_analyzer.py`:
- `test_entity_cluster_cross_referenced_on_workflows` — asserts `workflow.entity_cluster` is set when messages share an entity with a cluster
- `test_workflow_handoff_points_populated` — asserts `handoff_points` contains the UUID of a message with `/ll:handoff`

All 107 tests pass.

## Status

**Completed** | Created: 2026-03-04 | Completed: 2026-03-14 | Priority: P3
