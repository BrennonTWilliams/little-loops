---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 93
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
- `scripts/little_loops/workflow_sequence_analyzer.py:387` — `_link_sessions`: preserve full evidence list in `SessionLink`
- `scripts/little_loops/workflow_sequence_analyzer.py:773-777` — `analyze_workflows` `handoff_count` logic: `sum(1 for link in session_links if any(s.get("link_evidence") == "handoff_detected" for s in link.sessions))` — update to check `unified_workflow.get("evidence", [])` instead

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py:428` — `"handoff_detected"` is appended to `evidence` list inside `_link_sessions` here
- `scripts/little_loops/workflow_sequence_analyzer.py:776` — predicate: `any(s.get("link_evidence") == "handoff_detected" for s in link.sessions)` — this is the consumer that needs updating
- `scripts/little_loops/workflow_sequence_analyzer.py:788` — `if len(session_links) > handoff_count:` — recommendation branch uses the count

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py:653` — `TestLinkSessions` EXISTS — add three-evidence test case verifying `unified_workflow["evidence"]` contains all signals and `handoff_count` is correct

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

## Resolution

**Status**: Fixed
**Date**: 2026-03-04
**Approach**: Option A — added `"evidence": evidence` to `unified_workflow` dict in `_link_sessions`, updated `handoff_count` in `analyze_workflows` to check `link.unified_workflow.get("evidence", [])` for `"handoff_detected"`.

**Changes**:
- `scripts/little_loops/workflow_sequence_analyzer.py`: Added `"evidence"` field to `unified_workflow` in `SessionLink` construction; updated `handoff_count` predicate to check `unified_workflow["evidence"]`
- `scripts/tests/test_workflow_sequence_analyzer.py`: Added `test_three_evidence_all_preserved_in_unified_workflow` regression test

**Verification**: All 77 tests pass, lint clean.

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:refine-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a020aaf9-77a1-4304-b1e8-283c2006ae91.jsonl` — Added exact line refs for `_link_sessions:387`, evidence append at `:428`, `handoff_count` sum at `:759-763`, predicate at `:762`; confirmed `TestLinkSessions:653` as existing test target
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f6adf0d-6067-4c75-9095-ec0406748646.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00Z - Fixed and completed

---

**Completed** | Created: 2026-03-04 | Priority: P3
