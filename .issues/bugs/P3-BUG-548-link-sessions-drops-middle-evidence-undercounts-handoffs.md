---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# BUG-548: `_link_sessions` drops middle evidence entries — handoff count under-reported

## Summary

When building a `SessionLink`, `_link_sessions` assigns only `evidence[0]` to session A and `evidence[-1]` to session B. When all three evidence signals are present (`"shared_branch"`, `"handoff_detected"`, `"entity_overlap"`), the middle entry `"handoff_detected"` is silently dropped. The `handoff_analysis` block in `analyze_workflows` checks `link_evidence == "handoff_detected"` to count handoffs, so any link with three evidence types is miscounted as a non-handoff link.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 460–470 (at scan commit: a574ea0)
- **Anchor**: `in function _link_sessions`, `SessionLink` construction
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L460-L470)
- **Code**:
```python
sessions=[
    {
        "session_id": session_a_id,
        "position": 1,
        "link_evidence": evidence[0] if evidence else "score",   # only first
    },
    {
        "session_id": session_b_id,
        "position": 2,
        "link_evidence": evidence[-1] if evidence else "score",  # only last
    },
],
```

## Current Behavior

When a session pair has three evidence signals (`["shared_branch", "handoff_detected", "entity_overlap"]`), the `SessionLink` stores `"shared_branch"` for session A and `"entity_overlap"` for session B. `"handoff_detected"` is lost. The `handoff_count` computation in `analyze_workflows` (which scans `link.sessions` for `link_evidence == "handoff_detected"`) therefore misses this pair and under-reports handoffs.

## Expected Behavior

All evidence signals are preserved in the output. The `handoff_analysis.handoff_count` correctly counts all pairs where `"handoff_detected"` was observed.

## Motivation

`handoff_count` in the `handoff_analysis` block is used to determine whether to recommend adding `/ll:handoff` markers to sessions. Undercounting handoffs leads to incorrect recommendations — suggesting to add markers to sessions that already used them. The bug specifically affects the most-evidenced session pairs (those with all three signals), which are exactly the pairs most likely to be genuine handoffs.

## Steps to Reproduce

1. Create two sessions where:
   - They share a git branch (adds `"shared_branch"`)
   - Session A ends with a `/ll:handoff` marker (adds `"handoff_detected"`)
   - They have >50% entity overlap (adds `"entity_overlap"`)
2. Run `ll-workflows analyze`.
3. Check `handoff_analysis.total_handoffs` — it will be 0 for this pair despite the handoff marker.

## Actual Behavior

`handoff_count` is under-reported. The `recommendations` block may incorrectly suggest adding `/ll:handoff` markers to a session that already used one.

## Root Cause

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Anchor**: `in function _link_sessions`
- **Cause**: `evidence[0]` and `evidence[-1]` are stored in separate per-session `link_evidence` fields. When `len(evidence) > 2`, interior entries are not stored anywhere. The consumer code only checks the per-session `link_evidence` string, not a list.

## Proposed Solution

Store the full evidence list in a top-level field on the link's `unified_workflow`, or change `link_evidence` to a list:

**Option A — add `evidence` list to `unified_workflow` dict:**
```python
links.append(
    SessionLink(
        ...
        sessions=[
            {"session_id": session_a_id, "position": 1, "link_evidence": evidence[0] if evidence else "score"},
            {"session_id": session_b_id, "position": 2, "link_evidence": evidence[-1] if evidence else "score"},
        ],
        unified_workflow={
            ...,
            "evidence": evidence,          # full list preserved here
        },
    )
)
```

Then update `handoff_count` logic to check `link.unified_workflow.get("evidence", [])` for `"handoff_detected"`.

**Option B — change `link_evidence` to a list (more consistent):**
Change both per-session `link_evidence` values to the full `evidence` list. Update consumer checks accordingly.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_link_sessions` and `analyze_workflows` handoff_count logic

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows` reads `link.sessions[*]["link_evidence"]`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — `TestLinkSessions` class, add three-evidence test case

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `evidence` field to `unified_workflow` dict in `SessionLink` construction in `_link_sessions`
2. Update `handoff_count` in `analyze_workflows` to check `unified_workflow["evidence"]` instead of (or in addition to) per-session `link_evidence`
3. Add regression test with a three-evidence session pair and verify `handoff_count == 1`

## Impact

- **Priority**: P3 - Produces silently incorrect analytical output; no crash but handoff metrics are wrong for the most-evidenced session pairs
- **Effort**: Small - Two-site change in one file
- **Risk**: Low - Well-contained; existing tests cover two-evidence cases
- **Breaking Change**: No (adds data to output, doesn't remove)

## Labels

`bug`, `workflow-analyzer`, `data-correctness`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
