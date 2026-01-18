# ENH-085: Document FSM modules in docs/API.md - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-085-document-fsm-modules-in-api-md.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The API.md documents core modules but is missing documentation for:
- `little_loops.fsm` package (schema, compilers, evaluators, executor, interpolation, validation, persistence)
- `little_loops.sprint` module

### Key Discoveries
- FSM package is well-organized with clear module boundaries (`scripts/little_loops/fsm/`)
- Each module has comprehensive docstrings and type hints
- The `__init__.py` exports 33 public symbols organized by category
- Sprint module provides batch execution of issues

## Desired End State

API.md contains complete documentation for:
1. FSM module overview table in the main Module Overview section
2. `little_loops.fsm` section with overview and per-module documentation
3. `little_loops.sprint` section with Sprint and SprintManager classes

### How to Verify
- Read API.md and verify FSM modules are documented
- Ensure documentation matches actual API signatures
- Verify examples are accurate and runnable

## What We're NOT Doing

- Not changing any Python code
- Not adding new functionality
- Not modifying other documentation files

## Solution Approach

Add documentation following the existing API.md format:
- Module overview tables with Purpose column
- Dataclass documentation with attributes
- Function signatures with Parameters and Returns
- Usage examples

## Implementation Phases

### Phase 1: Add FSM to Module Overview Table

Add entries for fsm subpackage and sprint module to the main overview table.

**File**: `docs/API.md`
**Changes**: Add rows to Module Overview table

### Phase 2: Document little_loops.fsm Package

Add comprehensive section covering:
- Package overview with submodule table
- Schema: FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig
- Compilers: compile_paradigm and paradigm-specific functions
- Evaluators: All evaluate_* functions and EvaluationResult
- Executor: FSMExecutor, ExecutionResult, ActionResult, ActionRunner
- Interpolation: InterpolationContext, interpolate, interpolate_dict
- Validation: ValidationError, validate_fsm, load_and_validate
- Persistence: LoopState, StatePersistence, PersistentExecutor

### Phase 3: Document little_loops.sprint Module

Add section covering:
- Sprint dataclass
- SprintOptions dataclass
- SprintManager class

### Phase 4: Verify

**Automated Verification**:
- [ ] Lint passes: `ruff check docs/`
- [ ] No broken markdown: basic structure check

**Manual Verification**:
- [ ] Documentation is complete and accurate
- [ ] Examples are correct
- [ ] Formatting matches existing sections

## References

- Original issue: `.issues/enhancements/P3-ENH-085-document-fsm-modules-in-api-md.md`
- FSM package: `scripts/little_loops/fsm/`
- Sprint module: `scripts/little_loops/sprint.py`
