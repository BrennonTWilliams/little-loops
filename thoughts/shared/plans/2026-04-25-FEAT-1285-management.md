# FEAT-1285: Learning Test Registry Python Module — Implementation Plan

**Date**: 2026-04-25  
**Issue**: FEAT-1285  
**Action**: implement  
**Mode**: TDD (tdd_mode=true)

## Decision Confirmed

**Option A** (yaml.safe_load for nested assertions) was selected by `/ll:decide-issue`.

## Implementation Approach

### `read_record` / `write_record` strategy

- **write_record**: `yaml.dump(record.to_dict())` to build full frontmatter, write fresh `.md` file
- **read_record**: `re.match(r"^---\n(.*?)\n---", content, re.DOTALL)` then `yaml.safe_load(fm_match.group(1))`  
  (mirrors the pattern at `frontmatter.py:130` and `sync.py:179`)
- **mark_stale**: `update_frontmatter(content, {"status": "stale"})` — safe because `update_frontmatter` uses `yaml.safe_load` internally, preserving nested assertions on round-trip
- **base_dir**: Functions accept `base_dir: Path | None = None`, defaulting to `Path.cwd() / ".ll" / "learning-tests"` — needed for testability with `temp_project_dir` fixture

## Files to Create

- [ ] `scripts/tests/test_learning_tests.py` — Red phase tests
- [ ] `scripts/little_loops/learning_tests.py` — Core module

## Files to Modify

- [ ] `scripts/little_loops/config/features.py` — add `LearningTestsConfig` after `SprintsConfig` (~line 253)
- [ ] `scripts/little_loops/config/core.py` — import + wire `_learning_tests` in `_parse_config()` + `@property` + `to_dict()`
- [ ] `scripts/little_loops/config/__init__.py` — import + re-export `LearningTestsConfig`
- [ ] `scripts/little_loops/__init__.py` — export `check_learning_test`, `LearnTestRecord`
- [ ] `config-schema.json` — add `learning_tests` after `loops` block (~line 787)
- [ ] `scripts/tests/test_config.py` — add `TestLearningTestsConfig` and `TestBRConfigLearningTestsIntegration`
- [ ] `scripts/tests/test_config_schema.py` — add `test_learning_tests_in_schema`
- [ ] `scripts/tests/test_extension.py` — add two smoke import tests in `TestNewProtocols`
- [ ] `docs/reference/API.md` — add `learning_tests` module entry
- [ ] `docs/ARCHITECTURE.md` — add `learning_tests.py` to dir tree
- [ ] `CONTRIBUTING.md` — add `learning_tests.py` to dir tree
- [ ] `docs/reference/CONFIGURATION.md` — add `learning_tests` config section

## TDD Sequence

### Phase 3a: Write tests (Red)
1. Write `test_learning_tests.py` — CRUD tests
2. Add `TestLearningTestsConfig` + `TestBRConfigLearningTestsIntegration` to `test_config.py`
3. Add `test_learning_tests_in_schema` to `test_config_schema.py`
4. Add smoke imports to `test_extension.py`
5. Run tests → must FAIL (module doesn't exist yet)

### Phase 3b: Implement (Green)
6. Create `learning_tests.py`
7. Add `LearningTestsConfig` to `features.py`
8. Wire in `core.py`
9. Update `config/__init__.py` and `__init__.py`
10. Update `config-schema.json`
11. Run tests → must PASS
12. Update docs (API.md, ARCHITECTURE.md, CONTRIBUTING.md, CONFIGURATION.md)

## Acceptance Criteria

- `write_record()` creates a valid frontmatter `.md` file in `.ll/learning-tests/`
- `read_record()` deserializes back to identical `LearnTestRecord`
- `mark_stale()` updates `status: stale` without losing other fields
- `list_records()` returns all records in the directory
- `LearningTestsConfig` parses from `ll-config.json` with sensible defaults
- `config-schema.json` validates a config containing `learning_tests.stale_after_days`
- All tests pass
