---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 90
outcome_confidence: 100
---

# ENH-551: Pre-compute entity sets in `_compute_boundaries` to avoid re-extracting per sliding-window pair

## Summary

`_compute_boundaries` iterates N-1 consecutive message pairs and calls `extract_entities` on both messages in each pair. Because the window slides by one, every interior message is processed twice — once as `msg_b` and once as `msg_a` in the next iteration. Pre-computing all entity sets before the loop halves the `extract_entities` call count for any input with 3+ messages.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 636–637 (was 551–574 at scan commit: a574ea0)
- **Anchor**: `in function _compute_boundaries`, sliding window loop
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L551-L574)
- **Code**:
```python
sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", ""))

for i in range(len(sorted_msgs) - 1):
    msg_a = sorted_msgs[i]
    msg_b = sorted_msgs[i + 1]
    ...
    entities_a = extract_entities(msg_a.get("content", ""))  # re-computed each pair
    entities_b = extract_entities(msg_b.get("content", ""))  # re-computed each pair
```

## Current Behavior

For N messages, `extract_entities` is called 2*(N-1) times. Every interior message (indices 1 through N-2) has its entities extracted twice.

## Expected Behavior

`extract_entities` is called exactly N times — once per message — by pre-computing the full list before the loop.

## Motivation

`extract_entities` scans message content for entity patterns on each call. For large JSONL inputs (hundreds of messages), the redundant extractions are proportional to input size. The fix is trivial and makes `_compute_boundaries` O(N) in `extract_entities` calls rather than O(2N).

## Proposed Solution

```python
sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", ""))
all_entities = [extract_entities(m.get("content", "")) for m in sorted_msgs]  # once per message

for i in range(len(sorted_msgs) - 1):
    msg_a = sorted_msgs[i]
    msg_b = sorted_msgs[i + 1]
    ...
    entities_a = all_entities[i]    # O(1) lookup
    entities_b = all_entities[i + 1]
```

## Scope Boundaries

- In scope: pre-compute entity list in `_compute_boundaries`
- Out of scope: changes to `extract_entities` itself or other functions

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_compute_boundaries` loop setup

### Dependent Files (Callers/Importers)
- N/A — internal change only

### Similar Patterns
- Check `_cluster_by_entities` for similar patterns (it also calls `extract_entities` per message)

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — existing `TestComputeBoundaries` tests cover the change

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `all_entities = [extract_entities(m.get("content", "")) for m in sorted_msgs]` after the sort in `_compute_boundaries`
2. Replace `entities_a = extract_entities(msg_a.get("content", ""))` and `entities_b = ...` with index lookups
3. Confirm existing tests pass

## Impact

- **Priority**: P4 - Minor performance improvement; the fix is 2 lines and has zero behavior change
- **Effort**: Small - 2-line change
- **Risk**: Low - No semantic change, covered by existing tests
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


_(FEAT-558 removed from Blocks — completed; ENH-554 removed — does not exist in active or completed issues)_

## Blocked By

- ENH-550

## Labels

`enhancement`, `performance`, `workflow-analyzer`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-23T03:43:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11c70934-6502-4380-92e1-3f88c099af60.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: sliding-window redundancy at lines 592-593
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `extract_entities` called twice per interior message in `_compute_boundaries` loop; removed stale Blocks: FEAT-558 (completed)

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c738121d-b426-4f59-8942-86c5b0459be3.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/workflow_sequence_analyzer.py` lines 592-593 confirm `extract_entities(msg_a.get("content", ""))` and `extract_entities(msg_b.get("content", ""))` are both called inside the sliding-window loop in `_compute_boundaries`, causing every interior message to be processed twice. No pre-computed entity list exists. Enhancement not yet applied.
- **Date**: 2026-03-21 — DEP_ISSUES → VALID. Removed broken `Blocks: ENH-554` reference — ENH-554 does not exist in active or completed issues.
- **Date**: 2026-03-22 — OUTDATED. Lines shifted: `extract_entities` calls in `_compute_boundaries` were at 551–574 (scan commit a574ea0); now at **636–637**. No pre-computed entity list exists. Enhancement not yet applied. Updated Location section.

## Status

**Open** | Created: 2026-03-04 | Priority: P4
