# ENH-186: Harmonize timeout defaults - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-186-harmonize-timeout-defaults.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The three CLI tools have inconsistent default timeout values:

| Tool | Setting | Default | Location |
|------|---------|---------|----------|
| ll-auto | `timeout_seconds` | 3600 (1h) | `config.py:174` |
| ll-parallel | `timeout_per_issue` | **7200 (2h)** | `parallel/types.py:295` |
| ll-sprint | `default_timeout` | 3600 (1h) | `config.py:290`, `sprint.py:26` |

The config-schema.json also documents `parallel.timeout_per_issue` with a default of 7200 at line 183.

### Key Discoveries
- `ParallelConfig.timeout_per_issue = 7200` at `parallel/types.py:295`
- `config-schema.json` has `"default": 7200` at line 183
- Test `test_parallel_types.py:724` asserts `config.timeout_per_issue == 7200`
- All other timeout defaults are consistently 3600 (1 hour)

## Desired End State

All CLI tools use the same default timeout of 3600 seconds (1 hour):
- `ParallelConfig.timeout_per_issue = 3600`
- `config-schema.json` parallel.timeout_per_issue default = 3600

### How to Verify
- All tests pass after change
- `ParallelConfig()` creates instance with `timeout_per_issue == 3600`
- Running `ll-parallel --help` or checking defaults shows 3600s

## What We're NOT Doing

- Not changing `orchestrator_timeout` behavior (remains `timeout_per_issue * max_workers`)
- Not changing CLI argument behavior (users can still override with `--timeout`)
- Not changing any ll-auto or ll-sprint code (already at 3600)
- Not adding new documentation beyond the audit file update

## Problem Analysis

The ll-parallel tool defaults to 2 hours while other tools default to 1 hour. This inconsistency:
1. Confuses users who expect uniform behavior
2. Creates unexpected wait times when issues get stuck
3. Makes the "timeout" concept inconsistent across the toolset

## Solution Approach

Align ll-parallel's default to match ll-auto and ll-sprint at 3600 seconds:
1. Change `ParallelConfig.timeout_per_issue` default from 7200 to 3600
2. Update `config-schema.json` to reflect new default
3. Update the test assertion that checks this default

## Implementation Phases

### Phase 1: Update ParallelConfig Default

#### Overview
Change the dataclass default value for `timeout_per_issue`.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Update default from 7200 to 3600

Line 295:
```python
# Before:
timeout_per_issue: int = 7200

# After:
timeout_per_issue: int = 3600
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Tests pass (initially will fail due to assertion): `python -m pytest scripts/tests/test_parallel_types.py -v`

---

### Phase 2: Update Config Schema

#### Overview
Update JSON schema to document the new default value.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Change default from 7200 to 3600 on line 183

```json
// Before:
"timeout_per_issue": {
  "type": "integer",
  "description": "Timeout per issue in seconds",
  "default": 7200,
  "minimum": 60
}

// After:
"timeout_per_issue": {
  "type": "integer",
  "description": "Timeout per issue in seconds",
  "default": 3600,
  "minimum": 60
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Schema is valid JSON

---

### Phase 3: Update Test Assertions

#### Overview
Fix the test that asserts the old default value.

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Update assertion on line 724 from 7200 to 3600

```python
# Before:
assert config.timeout_per_issue == 7200

# After:
assert config.timeout_per_issue == 3600
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Verify `ParallelConfig()` creates instance with `timeout_per_issue == 3600`
- Existing tests should pass after assertion update

### Integration Tests
- No integration changes needed - this is a default value change only

## References

- Original issue: `.issues/enhancements/P4-ENH-186-harmonize-timeout-defaults.md`
- CLI Tools Audit: `docs/CLI-TOOLS-AUDIT.md`
- ParallelConfig dataclass: `scripts/little_loops/parallel/types.py:255-310`
