# FEAT-555: Populate EntityCluster.span and inferred_workflow

**Date**: 2026-03-16  
**Issue**: FEAT-555 — EntityCluster.span and inferred_workflow declared but never populated

## Summary

Two fields on `EntityCluster` (`span`, `inferred_workflow`) are declared but always `None`. We populate them in `_cluster_by_entities` after the cluster-building loop.

## Changes

### `scripts/little_loops/workflow_sequence_analyzer.py`

1. Add `"timestamp": msg.get("timestamp")` to both message dict appends in `_cluster_by_entities`:
   - matched_cluster branch (line ~532–537)
   - new cluster branch (line ~551–556)

2. After the cluster-building loop (before line 562 filter), add a post-processing block that:
   - Computes `span` via `_parse_timestamps(cluster.messages)` when len ≥ 2
   - Infers workflow using `_CONTENT_CATEGORY_MAP` keyword matching against `WORKFLOW_TEMPLATES`

3. Add `_CONTENT_CATEGORY_MAP` module-level constant.

### `scripts/tests/test_workflow_sequence_analyzer.py`

Add to `TestClusterByEntities`:
- `test_span_populated_from_timestamps` — cluster with timestamped messages gets non-null span
- `test_span_null_without_timestamps` — cluster without timestamps has span=None
- `test_inferred_workflow_set_on_category_match` — cluster with matching content gets inferred_workflow
- `test_inferred_workflow_null_on_no_match` — cluster with no matching content has inferred_workflow=None

## Acceptance Criteria

- [ ] Clusters with ≥2 messages and timestamps have non-null span with start/end ISO strings
- [ ] Clusters without timestamp data have span: null
- [ ] Clusters with entity overlap ≥ 0.3 against a WORKFLOW_TEMPLATES entry have inferred_workflow set
- [ ] Clusters with no matching template have inferred_workflow: null
- [ ] All existing tests pass
