# ENH-514: Make Overlap and Conflict Thresholds Configurable

## Summary

Add `dependency_mapping` section to `ll-config.json` with all overlap/conflict thresholds currently hardcoded across `file_hints.py` and `dependency_mapper.py`.

## Implementation Steps

### Step 1: Add config dataclasses (`config.py`)
- [x] Create `ScoringWeightsConfig` dataclass
- [x] Create `DependencyMappingConfig` dataclass
- [x] Wire into `BRConfig._parse_config()`, property, `to_dict()`, `__all__`

### Step 2: Add JSON schema (`config-schema.json`)
- [x] Add `dependency_mapping` section with all properties

### Step 3: Thread config through `file_hints.py`
- [x] Add optional `config` param to `overlaps_with()`, `get_overlapping_paths()`
- [x] Add optional `min_directory_depth` param to `_directories_overlap()`, `_file_in_directory()`
- [x] Add optional `exclude_files` param to `_is_common_file()`

### Step 4: Thread config through `dependency_mapper.py`
- [x] Add optional `config` param to `compute_conflict_score()`
- [x] Add optional `config` param to `find_file_overlaps()`
- [x] Add optional `config` param to `analyze_dependencies()`
- [x] Add optional `config` param to `format_report()`

### Step 5: Thread config through callers
- [x] `dependency_graph.py`: `refine_waves_for_contention()` accepts optional config
- [x] `cli/sprint/_helpers.py`: `_log_dependency_report()` accepts optional config
- [x] `cli/sprint/run.py`: Pass `br_config.dependency_mapping` through call chain
- [x] `cli/sprint/manage.py`: Pass config to `overlaps_with()`
- [x] `cli/sprint/show.py`: Pass config through
- [x] `parallel/overlap_detector.py`: Pass config to `overlaps_with()`

### Step 6: Tests
- [x] `test_config.py`: Test `DependencyMappingConfig` from_dict, defaults, BRConfig integration
- [x] `test_file_hints.py`: Test overlaps with custom config thresholds
- [x] `test_dependency_mapper.py`: Test with custom config thresholds
