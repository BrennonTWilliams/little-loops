# FEAT-040: FSM Schema Definition and Validation - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-040-fsm-schema-definition-and-validation.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The FSM directory does not exist - this is greenfield implementation. However, the codebase has well-established patterns for dataclasses, JSON serialization, and validation.

### Key Discoveries
- Dataclass patterns with `to_dict()` and `from_dict()` in `scripts/little_loops/parallel/types.py:51-133`
- Enum patterns for state values in `scripts/little_loops/parallel/types.py:135-144`
- Validation with `ValueError` and detailed error messages in `scripts/little_loops/dependency_graph.py:160-214`
- JSON Schema patterns in `config-schema.json` using JSON Schema draft-07
- Test patterns with helper functions in `scripts/tests/test_dependency_graph.py:13-28`
- Test class organization in `scripts/tests/test_dependency_graph.py:31-117`

## Desired End State

A complete FSM schema module that:
1. Provides typed dataclasses (`FSMLoop`, `StateConfig`, `EvaluateConfig`, `RouteConfig`, `LLMConfig`)
2. Supports YAML loading with `load_and_validate()`
3. Validates FSM structure (initial state exists, no dangling refs, at least one terminal)
4. Provides clear error messages via `ValidationError` dataclass
5. Includes JSON Schema (`fsm-loop-schema.json`) for YAML IDE validation
6. Has comprehensive unit tests

### How to Verify
- All unit tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- Type checking passes: `python -m mypy scripts/little_loops/fsm/`
- Linting passes: `ruff check scripts/little_loops/fsm/`
- Can load example FSM YAML and validate

## What We're NOT Doing

- Not implementing evaluators (FEAT-043)
- Not implementing compilers (FEAT-041)
- Not implementing variable interpolation (FEAT-042)
- Not implementing the executor (FEAT-045)
- Not implementing the CLI tool (FEAT-047)
- Not creating `.loops/` directory structure

## Problem Analysis

The FSM loop system needs type-safe representation of loop definitions. The design doc specifies a rich schema with:
- Two-layer transition system (evaluate + route)
- Multiple evaluator types
- Shorthand vs full routing syntax
- Context/captured variable namespaces
- LLM configuration

## Solution Approach

Follow established codebase patterns:
1. Use Python dataclasses with full type hints
2. Include `to_dict()` and `from_dict()` methods for YAML/JSON serialization
3. Use dedicated `ValidationError` dataclass for structured errors
4. Create JSON Schema following `config-schema.json` patterns
5. Write comprehensive tests following `test_dependency_graph.py` patterns

## Implementation Phases

### Phase 1: Create Directory Structure and __init__.py

#### Overview
Create the `scripts/little_loops/fsm/` package structure.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Create package with public exports

```python
"""FSM loop schema and validation.

This module provides the type-safe representation of FSM loop definitions
and validation logic.

Public exports:
- FSMLoop: Main dataclass representing a complete loop definition
- StateConfig: Configuration for a single state
- EvaluateConfig: Evaluator configuration
- RouteConfig: Routing table configuration
- LLMConfig: LLM evaluation settings
- ValidationError: Structured validation error
- validate_fsm: Validate FSM structure
- load_and_validate: Load YAML and validate
"""

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    LLMConfig,
    RouteConfig,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationError,
    load_and_validate,
    validate_fsm,
)

__all__ = [
    "EvaluateConfig",
    "FSMLoop",
    "LLMConfig",
    "RouteConfig",
    "StateConfig",
    "ValidationError",
    "load_and_validate",
    "validate_fsm",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Directory exists: `ls scripts/little_loops/fsm/`
- [ ] Module imports: `python -c "from little_loops.fsm import FSMLoop"`

---

### Phase 2: Implement schema.py with Dataclasses

#### Overview
Create the core dataclasses that represent FSM loop definitions.

#### Changes Required

**File**: `scripts/little_loops/fsm/schema.py`
**Changes**: Create dataclasses matching design doc schema

Key dataclasses:
1. `EvaluateConfig` - Evaluator configuration with type-specific fields
2. `RouteConfig` - Routing table (verdict -> state mapping)
3. `StateConfig` - Single state configuration
4. `LLMConfig` - LLM evaluation settings
5. `FSMLoop` - Complete loop definition

Each dataclass will have:
- Full type hints (Python 3.11+ style with `|` union syntax)
- Docstrings with field descriptions
- `to_dict()` method for JSON serialization
- `from_dict()` classmethod for deserialization

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/schema.py --strict`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/schema.py`
- [ ] Import works: `python -c "from little_loops.fsm.schema import FSMLoop, StateConfig"`

---

### Phase 3: Implement validation.py

#### Overview
Create validation logic with clear error messages.

#### Changes Required

**File**: `scripts/little_loops/fsm/validation.py`
**Changes**: Create validation functions

Key components:
1. `ValidationError` dataclass with `message`, `path` (for nested errors), `severity`
2. `validate_fsm(fsm: FSMLoop) -> list[ValidationError]` - structural validation
3. `load_and_validate(path: Path) -> FSMLoop` - load YAML and validate
4. Helper functions: `_get_state_references()`, `_validate_evaluator()`

Validation checks:
- Initial state exists in states dict
- All referenced states exist (on_success, on_failure, route targets)
- At least one terminal state
- Evaluator config has required fields for its type
- No conflicting routing (both shorthand and route)

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/validation.py --strict`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/validation.py`
- [ ] Import works: `python -c "from little_loops.fsm.validation import validate_fsm, ValidationError"`

---

### Phase 4: Create JSON Schema

#### Overview
Create JSON Schema for IDE validation of `.loops/*.yaml` files.

#### Changes Required

**File**: `scripts/little_loops/fsm/fsm-loop-schema.json`
**Changes**: Create JSON Schema following project patterns

Schema structure:
- Required: `name`, `initial`, `states`
- States validation with state-level properties
- Evaluator type validation with conditional fields
- Route table validation

#### Success Criteria

**Automated Verification**:
- [ ] Valid JSON: `python -c "import json; json.load(open('scripts/little_loops/fsm/fsm-loop-schema.json'))"`
- [ ] Schema validates examples from design doc

---

### Phase 5: Write Unit Tests

#### Overview
Create comprehensive test suite for schema and validation.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Create test suite following project patterns

Test classes:
1. `TestFSMSchema` - dataclass creation and serialization
2. `TestFSMValidation` - validation logic

Test cases per acceptance criteria:
- `test_minimal_valid_fsm` - Two-state FSM with terminal passes
- `test_missing_initial_state` - Error when initial state doesn't exist
- `test_dangling_state_reference` - Error for undefined state refs
- `test_no_terminal_state` - Error when no terminal state
- `test_shorthand_and_route_mutual_exclusion` - Warning for both defined
- `test_roundtrip_serialization` - to_dict/from_dict roundtrip
- `test_evaluator_type_validation` - Type-specific field validation

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- [ ] Coverage adequate: All validation paths covered

---

### Phase 6: Final Verification

#### Overview
Run all verification commands and ensure everything passes.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Dataclass construction with all field combinations
- Serialization roundtrip (to_dict -> from_dict)
- Validation catches all error types
- Edge cases: empty states, self-referential states, $current token

### Integration Tests
- Load actual YAML files (create test fixtures)
- Validate against JSON Schema

## References

- Design doc: `docs/generalized-fsm-loop.md`
- Issue: `.issues/features/P1-FEAT-040-fsm-schema-definition-and-validation.md`
- Pattern reference: `scripts/little_loops/parallel/types.py`
- Test patterns: `scripts/tests/test_dependency_graph.py`
- JSON Schema patterns: `config-schema.json`
