---
discovered_commit: 325fd14
discovered_branch: main
discovered_date: 2026-02-26
discovered_by: manual-audit
focus_area: dependency-mapping
---

# ENH-514: Make overlap and conflict thresholds configurable in ll-config.json

## Summary

All dependency mapping thresholds are hardcoded constants scattered across `file_hints.py` and `dependency_mapper.py`. Projects should be able to tune aggressiveness via `ll-config.json` to match their codebase structure.

## Current Behavior

The following thresholds are hardcoded with no configuration:

| Threshold | Location | Value | Effect |
|---|---|---|---|
| Overlap detection | `file_hints.py:35-37,80` | `MIN_OVERLAP_FILES=2`, `OVERLAP_RATIO_THRESHOLD=0.25`, `MIN_DIRECTORY_DEPTH=2` | Thresholds for overlap triggering |
| Conflict score cutoff | `dependency_mapper.py:370` | `0.4` | Below = parallel-safe, above = dependency proposed |
| High conflict level | `dependency_mapper.py:573` | `0.7` | Above = HIGH conflict label |
| Confidence modifier | `dependency_mapper.py:421` | `0.5` | Applied when direction is ambiguous |
| Scoring weights | `dependency_mapper.py:311` | `0.5/0.3/0.2` | Semantic/section/type signal weights |

There is no way to adjust these per-project. A CLI tool project (like little-loops) has very different overlap characteristics than a UI component project the scoring was designed for.

## Expected Behavior

Add a `dependency_mapping` section to `ll-config.json`:

```json
{
  "dependency_mapping": {
    "overlap_min_files": 2,
    "overlap_min_ratio": 0.25,
    "conflict_threshold": 0.4,
    "high_conflict_threshold": 0.7,
    "scoring_weights": {
      "semantic": 0.5,
      "section": 0.3,
      "type": 0.2
    },
    "exclude_common_files": ["__init__.py", "pyproject.toml", "setup.py"],
    "min_directory_depth": 2
  }
}
```

Defaults should match current behavior for backwards compatibility, but users can tune.

## Location

- `scripts/little_loops/parallel/file_hints.py` — overlap detection (no config)
- `scripts/little_loops/dependency_mapper.py` — conflict score thresholds (hardcoded)
- `config-schema.json` — config schema (no dependency_mapping section)
- `scripts/little_loops/config.py` — config loading (no dependency_mapping)

## Proposed Solution

1. Add `DependencyMappingConfig` dataclass to `config.py`
2. Add `dependency_mapping` section to `config-schema.json`
3. Thread config through to `file_hints.py` and `dependency_mapper.py`
4. Default values preserve current behavior

### Suggested Approach

1. Define `DependencyMappingConfig` in `scripts/little_loops/config.py` with all threshold fields and sensible defaults matching current hardcoded values
2. Add `dependency_mapping` to `BRConfig` as an optional field
3. Update `config-schema.json` to include the new section
4. Update `extract_file_hints()` and `overlaps_with()` to accept optional config
5. Update `compute_conflict_score()` and `find_file_overlaps()` to accept optional config
6. Update callers in `dependency_graph.py` and `cli/sprint/run.py` to pass config through

## Scope Boundaries

- **In scope**: Adding config schema, dataclass, threading config to existing functions
- **Out of scope**: Changing default behavior, implementing new threshold logic (that's BUG-511)

## Integration Map

### Files to Modify
- `scripts/little_loops/config.py` — add `DependencyMappingConfig` dataclass
- `config-schema.json` — add schema section
- `scripts/little_loops/parallel/file_hints.py` — accept config parameter
- `scripts/little_loops/dependency_mapper.py` — accept config parameter
- `scripts/little_loops/dependency_graph.py` — pass config through `refine_waves_for_contention()`

### Tests
- `scripts/tests/test_config.py` — test new config section parsing
- `scripts/tests/test_file_hints.py` — test with custom thresholds
- `scripts/tests/test_dependency_mapper.py` — test with custom thresholds

## Impact Assessment

- **Severity**: Medium — enables per-project tuning
- **Effort**: Medium
- **Risk**: Low (additive, defaults preserve current behavior)
- **Breaking Change**: No

## Blocked By

- ~~BUG-511~~ (completed — thresholds now exist as hardcoded constants)

## Labels

`enhancement`, `configuration`, `dependency-mapping`

---

## Status

**Completed** | Created: 2026-02-26 | Resolved: 2026-02-26 | Priority: P3

## Resolution

Added `DependencyMappingConfig` and `ScoringWeightsConfig` dataclasses to `config.py`, with JSON schema in `config-schema.json`. Threaded optional config through `file_hints.py` (overlap detection), `dependency_mapper.py` (conflict scoring), `dependency_graph.py`, all sprint CLI modules, and `overlap_detector.py`/`orchestrator.py`. All functions fall back to module-level constants when config is not provided, preserving backward compatibility. Tests added to `test_config.py`, `test_file_hints.py`, and `test_dependency_mapper.py`.

## Session Log
- manual audit - 2026-02-26 - Identified during exhaustive dependency mapping system audit
- manage-issue - 2026-02-26 - Implemented: config dataclasses, schema, threaded config through all callers, tests
