---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# FEAT-555: `EntityCluster.span` and `inferred_workflow` declared but never populated

## Summary

The `EntityCluster` dataclass declares two output fields — `span` (intended to hold start/end timestamps for the cluster's message range) and `inferred_workflow` (intended to name the matching workflow pattern) — that always serialize as `null` in the YAML output. The data needed to populate both fields is available from the cluster's `messages` list and `WORKFLOW_TEMPLATES`, but no code path assigns them.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 107–119 (`EntityCluster` dataclass), 521–538 (`_cluster_by_entities` new-cluster construction) (at scan commit: a574ea0)
- **Anchor**: `class EntityCluster`, `in function _cluster_by_entities`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L107-L119)
- **Code**:
```python
@dataclass
class EntityCluster:
    cluster_id: str
    primary_entities: list[str]
    all_entities: set[str] = field(default_factory=set)
    messages: list[dict[str, Any]] = field(default_factory=list)
    span: dict[str, Any] | None = None          # always None in output
    inferred_workflow: str | None = None         # always None in output
    cohesion_score: float = 0.0
```

## Current Behavior

All `EntityCluster` objects in the output YAML have `span: null` and `inferred_workflow: null`. Users cannot tell from the output when a cluster's messages occurred or whether the cluster matches a known workflow pattern.

## Expected Behavior

- `span` is populated with `{"start": "<iso-timestamp>", "end": "<iso-timestamp>"}` derived from the min/max timestamps of `cluster.messages`.
- `inferred_workflow` is populated with the name of the closest matching `WORKFLOW_TEMPLATES` entry (by entity overlap), or `null` if no template matches above a threshold.

## Use Case

A developer runs `ll-workflows analyze` after a busy week. In the output, they see entity clusters with `span` showing which days the cluster was active and `inferred_workflow: "bug_fix_workflow"` — telling them at a glance what kind of work each cluster represents. Currently both fields are always `null`, making the cluster output much less useful.

## Acceptance Criteria

- [ ] After analysis, each `EntityCluster` with at least 2 messages has a non-null `span` with `start` and `end` ISO timestamps
- [ ] Each cluster with entity overlap ≥ 0.3 against a `WORKFLOW_TEMPLATES` entry has `inferred_workflow` set to the template name
- [ ] Clusters with no timestamp data have `span: null`
- [ ] Clusters with no matching template have `inferred_workflow: null`
- [ ] Output YAML schema is backward compatible (fields were already present, just always null)

## Proposed Solution

After building each cluster in `_cluster_by_entities`, populate the fields:

```python
# Compute span from message timestamps
timestamps = _parse_timestamps(cluster.messages)   # reuse ENH-549 helper
if len(timestamps) >= 2:
    cluster.span = {
        "start": min(timestamps).isoformat(),
        "end": max(timestamps).isoformat(),
    }

# Infer workflow from entity overlap with templates
best_name, best_score = None, 0.0
for template in WORKFLOW_TEMPLATES:
    template_entities = set(template.get("entities", []))
    if template_entities:
        overlap = len(cluster.all_entities & template_entities) / len(template_entities)
        if overlap > best_score:
            best_score, best_name = overlap, template.get("name")
if best_score >= 0.3:
    cluster.inferred_workflow = best_name
```

## API/Interface

`EntityCluster.span` changes from always-`None` to `dict[str, str] | None`:
```python
span: {"start": "2026-03-01T09:00:00+00:00", "end": "2026-03-01T17:00:00+00:00"} | None
inferred_workflow: "bug_fix_workflow" | None
```

No schema breaking change — the fields already existed in the YAML output.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_cluster_by_entities`, populate fields after cluster construction

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — `TestClusterByEntities` class, add span/workflow assertions

### Similar Patterns
- `_link_sessions` computes `span_hours` from timestamps — reuse the same approach

### Tests
- Add assertions in `TestClusterByEntities` for non-null `span` and `inferred_workflow` when data is available

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. After cluster construction in `_cluster_by_entities`, compute `span` from message timestamps using `_parse_timestamps` (ENH-549)
2. Compute `inferred_workflow` by matching `cluster.all_entities` against `WORKFLOW_TEMPLATES`
3. Add tests asserting the fields are populated for clusters with sufficient data

## Impact

- **Priority**: P3 - Currently the YAML output has two declared-but-useless fields; populating them makes entity cluster output actionable
- **Effort**: Medium - Requires accessing `WORKFLOW_TEMPLATES` from `_cluster_by_entities` and integrating timestamp helper
- **Risk**: Low - Fields already exist in output, no schema change; only value changes from null to data
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `workflow-analyzer`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
