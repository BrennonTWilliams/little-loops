---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# FEAT-558: Expose `overlap_threshold` and `boundary_threshold` via CLI flags and `analyze_workflows()` API

## Summary

`_cluster_by_entities` and `_compute_boundaries` each accept a threshold parameter that meaningfully controls analysis behavior, but both are hardcoded at the `analyze_workflows` call sites (0.3 and 0.6 respectively) with no way to change them via the CLI or the public API. Tests explicitly validate that different thresholds produce different clustering results, confirming these are meaningful knobs.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 484–485 (`_cluster_by_entities` signature), 544–545 (`_compute_boundaries` signature), 754–756 (`analyze_workflows` call sites) (at scan commit: a574ea0)
- **Anchor**: `function _cluster_by_entities`, `function _compute_boundaries`, `function analyze_workflows`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L484)
- **Code**:
```python
def _cluster_by_entities(
    messages: list[dict[str, Any]], overlap_threshold: float = 0.3
) -> list[EntityCluster]: ...

def _compute_boundaries(
    messages: list[dict[str, Any]], boundary_threshold: float = 0.6
) -> list[WorkflowBoundary]: ...

# In analyze_workflows — always uses defaults:
entity_clusters = _cluster_by_entities(messages)
boundaries = _compute_boundaries(messages)
```

## Current Behavior

Both thresholds are effectively hardcoded at `0.3` and `0.6` for all CLI users. Changing them requires editing source code. The tests demonstrate both thresholds can be 0.0 or 0.9 and produce meaningfully different results.

## Expected Behavior

Users can pass `--overlap-threshold` and `--boundary-threshold` CLI flags to tune analysis for their specific message density. The `analyze_workflows()` public API also accepts these as parameters so library callers can control them without subclassing.

## Motivation

Users with different message characteristics (high-frequency dense sessions vs. sparse weekly sessions) need different threshold values to get meaningful clustering results. Currently they must edit source code to change the defaults. Exposing these as CLI flags enables per-run tuning without code changes, consistent with the principle that configuration should not require code modification.

## Use Case

A user with dense, highly-overlapping messages finds that the default 0.3 overlap threshold produces too many small clusters. They run:
```bash
ll-workflows analyze --input msgs.jsonl --patterns p.yaml --overlap-threshold 0.5
```
and get larger, more meaningful clusters without editing source code.

## Acceptance Criteria

- [x] `--overlap-threshold <float>` CLI flag controls entity clustering (default: 0.3)
- [x] `--boundary-threshold <float>` CLI flag controls boundary detection (default: 0.6)
- [x] Both flags validate that the value is in `[0.0, 1.0]` with a clear error for out-of-range input
- [x] `analyze_workflows()` accepts `overlap_threshold` and `boundary_threshold` keyword arguments with the same defaults
- [x] Existing behavior is unchanged when flags are not provided

## Proposed Solution

```python
# CLI additions in main():
analyze_parser.add_argument(
    "--overlap-threshold",
    type=float,
    default=0.3,
    metavar="FLOAT",
    help="Minimum entity overlap to cluster messages together (default: 0.3)",
)
analyze_parser.add_argument(
    "--boundary-threshold",
    type=float,
    default=0.6,
    metavar="FLOAT",
    help="Minimum boundary score to split workflow segments (default: 0.6)",
)

# analyze_workflows signature:
def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
    overlap_threshold: float = 0.3,
    boundary_threshold: float = 0.6,
) -> WorkflowAnalysis:
    ...
    entity_clusters = _cluster_by_entities(messages, overlap_threshold=overlap_threshold)
    boundaries = _compute_boundaries(messages, boundary_threshold=boundary_threshold)
```

## API/Interface

```python
def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
    overlap_threshold: float = 0.3,    # new
    boundary_threshold: float = 0.6,   # new
) -> WorkflowAnalysis: ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows` signature, `main()` arg parser, call sites

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — add tests for non-default threshold values

### Similar Patterns
- N/A

### Tests
- Add tests calling `analyze_workflows` with `overlap_threshold=0.9` and verifying fewer clusters are produced

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `overlap_threshold` and `boundary_threshold` parameters to `analyze_workflows` with current defaults
2. Pass them through to `_cluster_by_entities` and `_compute_boundaries` call sites
3. Add `--overlap-threshold` and `--boundary-threshold` arguments to `analyze_parser` in `main()`
4. Pass CLI values into `analyze_workflows` call in `main()`
5. Add tests for non-default threshold values

## Impact

- **Priority**: P4 - Power-user feature; defaults work fine for most users, but lack of exposure forces source edits
- **Effort**: Small - ~10 lines in two functions plus CLI arg additions
- **Risk**: Low - Additive; defaults unchanged, no existing callers affected
- **Breaking Change**: No

## Verification Notes

- **Verdict**: VALID — issue accurately describes current codebase state
- `_cluster_by_entities` at line 499 (was 484 at scan commit) with `overlap_threshold: float = 0.3` ✓
- `_compute_boundaries` at line 560 (was 544 at scan commit) with `boundary_threshold: float = 0.6` ✓
- `analyze_workflows` at line 747; call sites at lines 779–780 still call both with no threshold arguments ✓
- No dependencies detected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-552
- FEAT-559


## Blocked By

- FEAT-556
- ENH-549
- ENH-550
- ENH-551

## Labels

`feature`, `workflow-analyzer`, `cli`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47b6876a-ac1a-4e7a-a249-39bc456b09d5.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47b6876a-ac1a-4e7a-a249-39bc456b09d5.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47b6876a-ac1a-4e7a-a249-39bc456b09d5.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47b6876a-ac1a-4e7a-a249-39bc456b09d5.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:ready-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd72e0e6-0056-429e-acc1-dfeca54c9cb1.jsonl`

---

## Resolution

Implemented in `scripts/little_loops/workflow_sequence_analyzer.py`:
- Added `overlap_threshold` and `boundary_threshold` parameters to `analyze_workflows()` with defaults 0.3 and 0.6
- Passed both through to `_cluster_by_entities` and `_compute_boundaries` call sites
- Added `--overlap-threshold` and `--boundary-threshold` CLI flags to `analyze_parser` in `main()`
- Added `[0.0, 1.0]` range validation for both CLI flags with clear error messages
- Added 3 integration tests in `test_workflow_sequence_analyzer.py` covering non-default threshold values and regression

## Session Log

- `/ll:manage-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current-session.jsonl`

## Status

**Completed** | Created: 2026-03-04 | Completed: 2026-03-06 | Priority: P4
