---
id: FEAT-1987
title: "goal-cluster \u2014 Config Schema & ClusterConfig"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-07T00:56:50Z'
discovered_date: 2026-06-06
discovered_by: issue-size-review
size: Small
relates_to:
- FEAT-1810
confidence_score: 96
outcome_confidence: 88
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# FEAT-1987: goal-cluster — Config Schema & ClusterConfig

## Summary

Wire the Python configuration layer for `goal-cluster`: add `ClusterConfig` dataclass, extend `config-schema.json`, export from `__init__.py`, add tests, and update reference docs.

## Parent Issue

Decomposed from FEAT-1810: `goal-cluster` — Multi-Goal Orchestrator for Sprint- or EPIC-Shaped Input

## Proposed Solution

Implement the config infrastructure required before the loop YAML can be authored (FEAT-1988).

### Implementation Steps

1. **Wire config**: Add `ClusterConfig` dataclass to `scripts/little_loops/config/orchestration.py` after `ComposerAdaptiveConfig`:
   ```python
   @dataclass
   class ClusterConfig:
       max_batch_size: int = 5
       enable_dedup: bool = True
       propagate_context: bool = True
   ```
   Wire into `BRConfig.orchestration` alongside the existing composer configs.

2. **Schema**: Add `orchestration.cluster` to `config-schema.json` with properties:
   - `max_batch_size` (integer, default 5)
   - `enable_dedup` (boolean, default true)
   - `propagate_context` (boolean, default true)

3. **Export**: Add `ClusterConfig` to `scripts/little_loops/config/__init__.py` — add to `__all__` and import block alongside `ComposerAdaptiveConfig`.

4. **Tests** (`scripts/tests/test_config.py`): Add `ClusterConfig` import + `TestClusterConfig` class; add `test_orchestration_cluster_*` methods in `TestOrchestrationConfig` and `TestBRConfigOrchestration` (pattern: `test_from_dict_defaults_composer_adaptive` at line 2553).

5. **Schema test** (`scripts/tests/test_config_schema.py`): Add `test_orchestration_cluster_in_schema` following `test_orchestration_host_cli_in_schema` pattern at line 502.

6. **Docs** (`docs/reference/CONFIGURATION.md`): Add `#### orchestration.cluster` subsection after `#### orchestration.composer.adaptive` (line 988) with three-key table.

7. **Docs** (`docs/reference/API.md`): Refresh `BRConfig.orchestration` property description (line 118) to mention cluster config alongside composer config.

### Files to Modify

- `scripts/little_loops/config/orchestration.py` — add `ClusterConfig` dataclass
- `config-schema.json` — add `orchestration.cluster` schema properties
- `scripts/little_loops/config/__init__.py` — export `ClusterConfig`
- `scripts/tests/test_config.py` — add cluster config tests
- `scripts/tests/test_config_schema.py` — add schema test
- `docs/reference/CONFIGURATION.md` — add `orchestration.cluster` subsection
- `docs/reference/API.md` — update `BRConfig.orchestration` description

## Acceptance Criteria

- `ClusterConfig` instantiates with defaults: `max_batch_size=5`, `enable_dedup=True`, `propagate_context=True`
- `config-schema.json` validates `orchestration.cluster` keys
- `ClusterConfig` importable from `scripts/little_loops/config`
- All new tests pass: `python -m pytest scripts/tests/test_config.py scripts/tests/test_config_schema.py -v`

## Session Log
- `/ll:ready-issue` - 2026-06-07T00:52:15 - `ec3d6a5a-d2f3-4580-96de-0c5dd813e5eb.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `45b701af-a0ad-475b-a0bc-501c4f4df6dc.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `16f276d0-67d5-4f48-b7e1-ebaaaff11fd7.jsonl`
