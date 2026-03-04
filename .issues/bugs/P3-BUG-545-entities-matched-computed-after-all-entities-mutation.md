---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# BUG-545: `entities_matched` computed after `all_entities` is mutated — always shows full entity set

## Summary

In `_cluster_by_entities`, `matched_cluster.all_entities.update(msg_entities)` runs before `msg_entities & matched_cluster.all_entities` is evaluated for the `entities_matched` field. Because the mutation happens first, the intersection always equals `sorted(msg_entities)` — every new entity the incoming message contributes is counted as already having matched, defeating the purpose of recording which entities *caused* the match.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 509–514 (at scan commit: a574ea0)
- **Anchor**: `in function _cluster_by_entities`, `if matched_cluster:` block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L509-L514)
- **Code**:
```python
matched_cluster.all_entities.update(msg_entities)          # mutation happens here
matched_cluster.messages.append(
    {
        "uuid": msg.get("uuid", ""),
        "content": content[:80] + "..." if len(content) > 80 else content,
        "entities_matched": sorted(msg_entities & matched_cluster.all_entities),  # always == sorted(msg_entities)
    }
)
```

## Current Behavior

`entities_matched` in the output YAML always reports all entities from the incoming message, not just those that were already present in the cluster at the time of matching.

## Expected Behavior

`entities_matched` should report only the entities that existed in `all_entities` *before* the incoming message was added — i.e., the entities that actually triggered the cluster match.

## Motivation

This bug silently corrupts analytical output: every `entities_matched` field in the entity cluster YAML always reports all entities from the incoming message instead of only the pre-existing ones that triggered the cluster match. Users relying on `entities_matched` to understand why a message joined a cluster receive misleading data, making the entity clustering output unreliable for downstream analysis.

## Steps to Reproduce

1. Build a two-message cluster where the second message adds new entities beyond those in the first message.
2. Run `ll-workflows analyze` on the input.
3. Inspect the second message's `entities_matched` in the output YAML — it includes the newly-added entities even though they were not in the cluster at match time.

## Actual Behavior

`entities_matched` equals `sorted(msg_entities)` for every message appended to an existing cluster. The intersection `msg_entities & matched_cluster.all_entities` always equals `msg_entities` because `all_entities` was already updated to include all of `msg_entities`.

## Root Cause

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Anchor**: `in function _cluster_by_entities`
- **Cause**: `matched_cluster.all_entities.update(msg_entities)` is called on line 509 before `msg_entities & matched_cluster.all_entities` is evaluated on line 514. The fix is to compute the intersection before updating: `entities_matched = sorted(msg_entities & matched_cluster.all_entities)`, then call `.update()`.

## Proposed Solution

Compute the intersection before mutating `all_entities`:

```python
# Compute intersection BEFORE mutation
entities_matched = sorted(msg_entities & matched_cluster.all_entities)
matched_cluster.all_entities.update(msg_entities)
matched_cluster.messages.append(
    {
        "uuid": msg.get("uuid", ""),
        "content": content[:80] + "..." if len(content) > 80 else content,
        "entities_matched": entities_matched,
    }
)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — swap mutation/intersection order in `_cluster_by_entities`

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py:770` — `TestClusterByEntities` class (callers test `_cluster_by_entities` indirectly via `analyze_workflows`)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py:770` — `TestClusterByEntities` EXISTS — add assertion checking `entities_matched` only contains pre-existing cluster entities (entities that were in `all_entities` before the incoming message was appended)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `_cluster_by_entities`, capture `entities_matched = sorted(msg_entities & matched_cluster.all_entities)` before the `.update()` call
2. Use the captured value in the `messages.append()` dict
3. Add a regression test verifying `entities_matched` excludes newly-contributed entities

## Impact

- **Priority**: P3 - Logic error producing misleading output data; not a crash but silently corrupts analytical results
- **Effort**: Small - One-line reorder in a single function
- **Risk**: Low - Change is contained to `_cluster_by_entities`, test coverage exists
- **Breaking Change**: No (output field values change but schema stays the same)

## Labels

`bug`, `workflow-analyzer`, `data-correctness`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:refine-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a020aaf9-77a1-4304-b1e8-283c2006ae91.jsonl` — Confirmed source at `workflow_sequence_analyzer.py:484`; updated `TestClusterByEntities:770` as existing test class target

---

**Open** | Created: 2026-03-04 | Priority: P3
