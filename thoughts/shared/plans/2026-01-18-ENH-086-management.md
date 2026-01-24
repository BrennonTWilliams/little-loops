# ENH-086: Add fsm subpackage to CONTRIBUTING.md project structure - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-086-add-fsm-subpackage-to-contributing-structure.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

The CONTRIBUTING.md project structure (lines 69-111) documents the `little_loops/` package but is missing the `fsm/` subpackage.

### Key Discoveries
- `fsm/` subpackage exists at `scripts/little_loops/fsm/` with 8 Python source files
- Project structure is in CONTRIBUTING.md lines 69-113
- Current structure ends with `parallel/` as the last subpackage (line 103-110)

### Actual fsm/ Contents
- `__init__.py`
- `schema.py`
- `compilers.py`
- `evaluators.py`
- `executor.py`
- `interpolation.py`
- `validation.py`
- `persistence.py`
- `fsm-loop-schema.json` (schema file - can be omitted from structure)

## Desired End State

The `fsm/` subpackage should be documented in CONTRIBUTING.md alongside `parallel/`, following the same format and style conventions.

### How to Verify
- Visual inspection of CONTRIBUTING.md shows fsm/ subpackage
- Documentation accurately reflects actual directory structure

## What We're NOT Doing

- Not adding `__init__.py` to the docs (following convention - it's implicit)
- Not adding `fsm-loop-schema.json` (the existing docs focus on Python files)
- Not updating other documentation files

## Solution Approach

Insert the `fsm/` subpackage between `user_messages.py` (line 102) and `parallel/` (line 103). This requires:
1. Changing `└── parallel/` to `├── parallel/` (no longer last item)
2. Adding `├── fsm/` and its contents
3. Making `fsm/` the new last item with `└──`

Actually, looking at the alphabetical order and existing structure, `fsm` comes before `parallel`, so:
- `fsm/` should use `├──`
- `parallel/` stays as `└──` (last item)

## Implementation Phases

### Phase 1: Update CONTRIBUTING.md

#### Overview
Add fsm/ subpackage to the project structure section.

#### Changes Required

**File**: `CONTRIBUTING.md`
**Lines**: 102-103

Replace:
```
        ├── user_messages.py     # User message extraction
        └── parallel/     # Parallel processing module
```

With:
```
        ├── user_messages.py     # User message extraction
        ├── fsm/                  # FSM loop system
        │   ├── schema.py
        │   ├── compilers.py
        │   ├── evaluators.py
        │   ├── executor.py
        │   ├── interpolation.py
        │   ├── validation.py
        │   └── persistence.py
        └── parallel/     # Parallel processing module
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/` (not relevant to this doc change)
- [ ] No broken markdown links

**Manual Verification**:
- [ ] fsm/ subpackage appears in project structure
- [ ] Files listed match actual fsm/ directory contents
- [ ] Formatting is consistent with existing structure

## Testing Strategy

This is a documentation-only change. Verification is visual inspection.

## References

- Original issue: `.issues/enhancements/P4-ENH-086-add-fsm-subpackage-to-contributing-structure.md`
- FSM subpackage: `scripts/little_loops/fsm/`
