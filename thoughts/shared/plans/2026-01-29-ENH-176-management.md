# ENH-176: Reduce ll-sprint default max workers to 2 - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-176-reduce-ll-sprint-default-max-workers-to-2.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `ll-sprint` CLI uses `max_workers` defaults in multiple locations with inconsistent values:

### Key Discoveries
- `sprint.py:27` - `SprintOptions.max_workers: int = 3` (dataclass default)
- `sprint.py:52` - `data.get("max_workers", 3)` in `from_dict()` fallback
- `config.py:291` - `SprintsConfig.default_max_workers: int = 3` (config default)
- `config.py:299` - `data.get("default_max_workers", 3)` in `from_dict()` fallback
- `cli.py:1298` - CLI `--max-workers` default is 4 (inconsistent!)
- `cli.py:1675` - Runtime fallback is 3

### Test State
Tests in `test_sprint.py` expect 4, but code defaults to 3:
- Line 18: `assert options.max_workers == 4`
- Line 56: `assert options.max_workers == 4`
- Line 144: `assert sprint.options.max_workers == 4`

## Desired End State

All `max_workers` defaults should be 2 for consistency:
- All hardcoded defaults in sprint.py, config.py, and cli.py are 2
- CLI help text reflects the default of 2
- All tests expect default of 2

### How to Verify
- Tests pass with expected default of 2
- `ll-sprint create --help` shows default: 2

## What We're NOT Doing

- Not changing the `ll-parallel` tool defaults (already uses 2)
- Not modifying config-schema.json (schema documents but doesn't enforce runtime defaults)
- Not changing existing sprints in `.sprints/` directory

## Solution Approach

Change all hardcoded `max_workers` defaults from 3 (or 4) to 2, ensuring consistency across:
1. SprintOptions dataclass and from_dict
2. SprintsConfig dataclass and from_dict
3. CLI argument defaults and help text
4. CLI runtime fallback
5. Test expectations

## Implementation Phases

### Phase 1: Update sprint.py

#### Overview
Change SprintOptions defaults from 3 to 2.

#### Changes Required

**File**: `scripts/little_loops/sprint.py`
**Changes**: Update max_workers default in dataclass field and from_dict fallback

Line 27: Change `max_workers: int = 3` to `max_workers: int = 2`
Line 52: Change `data.get("max_workers", 3)` to `data.get("max_workers", 2)`

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/sprint.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/sprint.py`

---

### Phase 2: Update config.py

#### Overview
Change SprintsConfig default_max_workers from 3 to 2.

#### Changes Required

**File**: `scripts/little_loops/config.py`
**Changes**: Update default_max_workers in dataclass field and from_dict fallback

Line 291: Change `default_max_workers: int = 3` to `default_max_workers: int = 2`
Line 299: Change `data.get("default_max_workers", 3)` to `data.get("default_max_workers", 2)`

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/config.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/config.py`

---

### Phase 3: Update cli.py

#### Overview
Change CLI argument default and runtime fallback from 4/3 to 2.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
- Line 1298: Change `default=4` to `default=2`
- Line 1299: Update help text from "(default: 4)" to "(default: 2)"
- Line 1675: Change fallback `3` to `2`

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

---

### Phase 4: Update Tests

#### Overview
Update test expectations from 4 to 2.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`
**Changes**:
- Line 18: Change `assert options.max_workers == 4` to `assert options.max_workers == 2`
- Line 56: Change `assert options.max_workers == 4` to `assert options.max_workers == 2`
- Line 144: Change `assert sprint.options.max_workers == 4` to `assert sprint.options.max_workers == 2`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`

---

### Phase 5: Full Verification

#### Overview
Run complete test suite, lint, and type checks.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- SprintOptions() default values
- SprintOptions.from_dict(None) returns defaults
- Sprint.from_dict() with missing options uses defaults

### Integration Tests
- No changes needed - existing tests cover round-trip serialization

## References

- Original issue: `.issues/enhancements/P4-ENH-176-reduce-ll-sprint-default-max-workers-to-2.md`
- Related pattern: `scripts/little_loops/parallel/types.py:286` (ParallelConfig already uses max_workers=2)
