---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-697: Coupling cluster BFS edge cases untested

## Summary

The `_build_coupling_clusters` BFS implementation in `coupling.py` has tests for the happy path

## Motivation

Graph algorithms have well-known failure modes in edge cases (disconnected components, boundary thresholds, single-node degenerate inputs). Without explicit tests for these, refactoring the BFS implementation risks introducing silent correctness regressions that wouldn't surface through the current happy-path test alone. (two files with coupling_strength >= 0.5 across 2+ issues) but lacks tests for disconnected components, boundary coupling_strength values (exactly 0.5), pairs below threshold (excluded from clusters), and single-node components (filtered out by `len(cluster) >= 2`).

## Location

- **File**: `scripts/little_loops/issue_history/coupling.py`
- **Line(s)**: 99-145 (at scan commit: 3e9beea)
- **Anchor**: `in function _build_coupling_clusters()`
- **Test file**: `scripts/tests/test_issue_history_advanced_analytics.py`

## Current Behavior

`test_cluster_formation` covers only the happy path. The BFS traversal, disconnected subgraphs, the `len(cluster) >= 2` filter, and the 0.5 boundary are not explicitly tested.

## Expected Behavior

Additional test cases in `TestAnalyzeCoupling` for:
- Two independent clusters (disconnected components yield separate clusters)
- `coupling_strength` exactly 0.5 (boundary — included)
- `coupling_strength` below 0.5 (excluded from clusters)
- Single-node component (filtered out)

## Implementation Steps

1. In `scripts/tests/test_issue_history_advanced_analytics.py`, append to `TestAnalyzeCoupling` (after line 531):

   **`test_disconnected_clusters`** — two independent clusters:
   - Build 3 issues with `src/a.py` + `src/b.py` only → Jaccard(a,b)=1.0
   - Build 3 issues with `src/c.py` + `src/d.py` only → Jaccard(c,d)=1.0
   - Assert: `len(result.clusters) == 2`; one cluster is `["src/a.py", "src/b.py"]`, the other is `["src/c.py", "src/d.py"]`

   **`test_boundary_coupling_strength_included`** — strength exactly 0.5 is included:
   - 2 issues with both `src/a.py` + `src/b.py`; 2 issues with only `src/a.py`
   - Jaccard = 2/(2+2+0) = 2/4 = 0.5 → should pass cluster threshold
   - Assert: `len(result.clusters) == 1`; `result.clusters[0] == ["src/a.py", "src/b.py"]`

   **`test_below_threshold_excluded_from_clusters`** — strength < 0.5 not in clusters:
   - 2 issues with both `src/a.py` + `src/b.py`; 2 solo `a.py` issues; 1 solo `b.py` issue
   - Jaccard = 2/(2+2+1) = 2/5 = 0.4 → passes `analyze_coupling` (≥0.3) but fails cluster threshold (<0.5)
   - Assert: `len(result.pairs) >= 1`; `result.clusters == []`

   **`test_single_node_not_in_cluster`** — file below threshold forms no cluster:
   - Same fixture as above (Jaccard=0.4) or any pair with strength < 0.5
   - Assert: neither `src/a.py` nor `src/b.py` appears in any cluster entry

2. Run `python -m pytest scripts/tests/test_issue_history_advanced_analytics.py::TestAnalyzeCoupling -v` to confirm all pass

## Integration Map

- **Modified**: `scripts/tests/test_issue_history_advanced_analytics.py` — `TestAnalyzeCoupling` class (lines 357–572)
- **Under test**: `scripts/little_loops/issue_history/coupling.py` — `_build_coupling_clusters()` (lines 96–142)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key threshold facts** (relevant to test design):
- `coupling.py:108` — cluster threshold is `>= 0.5` (inclusive), so exactly 0.5 is **included**
- `coupling.py:136` — size filter is `>= 2` (inclusive), so 2-file clusters pass
- `coupling.py:63` — upstream filter in `analyze_coupling()` is `>= 0.3`; pairs with 0.3 ≤ strength < 0.5 reach `_build_coupling_clusters` but are skipped there — use this to test the "below threshold excluded" case
- `coupling_strength` is a **computed Jaccard output**, not a direct input — tests must engineer it via issue content (file co-occurrence counts)

**Jaccard formula** (`coupling.py:61`): `len(co_occur) / len(union)`

| Target strength | Co-occurring issues | Solo issues for a | Solo issues for b | Union | Jaccard |
|---|---|---|---|---|---|
| Exactly 0.5 | 2 | 2 | 0 | 4 | 2/4 = 0.5 ✓ |
| Below 0.5 (≈0.4) | 2 | 2 | 1 | 5 | 2/5 = 0.4 ✓ |
| High (1.0) | N | 0 | 0 | N | 1.0 ✓ |

**Fixture pattern** (from `test_cluster_formation` at line 507 and `test_weak_coupling_filtered` at line 407):
```python
# Write file content to control which files co-occur
issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
issue_file.write_text("**File**: `src/a.py`\n**File**: `src/b.py`")  # both files
issue_file.write_text("**File**: `src/a.py`")  # only a.py (solo issue)
issues.append(CompletedIssue(path=issue_file, issue_type="BUG", priority="P1", issue_id=f"BUG-{i:03d}"))
```
Use distinct filename prefixes (e.g. `BUG-AB`, `BUG-A`, `BUG-C`) to avoid collisions in `tmp_path`.

**Single-node note**: By construction, a file only enters `adjacency` (line 106) when it has a partner with strength ≥ 0.5 — so isolated single-node components cannot occur in normal flow. The `len(cluster) >= 2` filter (line 136) guards against it nonetheless. Test the intended behavior: a file whose only pairs have strength < 0.5 appears in **no** cluster (it never enters `adjacency`, so no single-node cluster is created). Assert `result.clusters == []`.

**Existing test methods in `TestAnalyzeCoupling`**: `test_empty_issues` (360), `test_coupling_detected` (367), `test_no_coupling_single_occurrence` (390), `test_weak_coupling_filtered` (407), `test_coupling_hotspot_detection` (458), `test_cluster_formation` (507), `test_coupling_strength_calculation` (533)

## Scope Boundaries

- Test-only changes in `test_issue_history_advanced_analytics.py`

## Impact

- **Priority**: P4 - Improves test coverage for graph algorithm edge cases
- **Effort**: Small - Add 3-4 test cases
- **Risk**: Low - Test-only change
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `issue-history`

## Session Log
- `/ll:refine-issue` - 2026-03-18T01:39:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b2aa1ab-7a2b-4015-8d5b-fef9b7dd4c2e.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/coupling.py` lines 99-145 referenced for `_build_coupling_clusters` exist. `scripts/tests/test_issue_history_advanced_analytics.py` is the referenced test file. The issue describes missing edge case tests (disconnected components, boundary threshold 0.5, single-node filter). These are plausible gaps for a BFS graph algorithm. Enhancement is valid as described.
