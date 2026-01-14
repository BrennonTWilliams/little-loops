# FEAT-043: Tier 1 Deterministic Evaluators - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-043-tier1-deterministic-evaluators.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The FSM module (`scripts/little_loops/fsm/`) already has the foundation for evaluators:

### Key Discoveries
- `EvaluateConfig` dataclass at `schema.py:22-125` defines all evaluator type fields
- `InterpolationContext` at `interpolation.py:36-167` provides variable resolution for convergence evaluator
- `interpolate()` function at `interpolation.py:169-206` handles `${namespace.path}` syntax
- Validation in `validation.py:58-143` already validates required fields per evaluator type
- `VALID_OPERATORS` set at `validation.py:69` defines: eq, ne, lt, le, gt, ge

### Existing Schema Structure
The `EvaluateConfig` dataclass already supports all five Tier 1 evaluator types:
- Type literals at `schema.py:51-58`: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`
- Fields for each evaluator: `operator`, `target`, `tolerance`, `pattern`, `negate`, `path`, `previous`, `direction`

## Desired End State

A complete `evaluators.py` module with:
1. `EvaluationResult` dataclass for standardized results
2. Five evaluator functions (`evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_output_contains`, `evaluate_convergence`)
3. `evaluate()` dispatcher function that routes to the correct evaluator
4. Helper functions for JSON path extraction and value comparison
5. Comprehensive test coverage in `test_fsm_evaluators.py`

### How to Verify
- All tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`
- Type checking passes: `python -m mypy scripts/little_loops/fsm/evaluators.py`
- Lint passes: `ruff check scripts/little_loops/fsm/evaluators.py`

## What We're NOT Doing

- Not implementing Tier 2 LLM evaluator (`llm_structured`) - that's FEAT-044
- Not implementing the FSM executor - that's FEAT-045
- Not modifying the schema dataclasses (already complete)
- Not modifying validation logic (already complete)

## Problem Analysis

The FSM system needs deterministic evaluators to interpret action output and produce verdicts for state routing. These evaluators must:
1. Be fast (no API calls)
2. Be reproducible (deterministic logic)
3. Support variable interpolation for convergence scenarios
4. Return structured results with verdict and details

## Solution Approach

Create `evaluators.py` following patterns from the existing codebase:
- Use dataclass for `EvaluationResult` (like other FSM dataclasses)
- Use dictionary dispatch pattern (like `compile_paradigm` in `compilers.py:51-90`)
- Import and use `InterpolationContext`, `interpolate`, `InterpolationError` from interpolation module
- Follow existing test patterns from `test_fsm_interpolation.py`

## Implementation Phases

### Phase 1: Create EvaluationResult and Core Evaluators

#### Overview
Create the `evaluators.py` file with the `EvaluationResult` dataclass and the three simpler evaluators: `exit_code`, `output_numeric`, and `output_contains`.

#### Changes Required

**File**: `scripts/little_loops/fsm/evaluators.py`
**Changes**: Create new file with core evaluator implementations

```python
"""Tier 1 Deterministic Evaluators for FSM loop execution.

These evaluators interpret action output without any API calls.
They are fast, free, and reproducible.

Supported evaluator types:
    exit_code: Map Unix exit codes to verdicts (0=success, 1=failure, 2+=error)
    output_numeric: Compare numeric output to target value
    output_json: Extract and compare JSON path values
    output_contains: Pattern matching on stdout
    convergence: Track progress toward a target value
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
)
from little_loops.fsm.schema import EvaluateConfig


@dataclass
class EvaluationResult:
    """Result from an evaluator.

    Attributes:
        verdict: The routing key for state transitions
        details: Evaluator-specific metadata for debugging/logging
    """
    verdict: str
    details: dict[str, Any]


# ... evaluator functions follow
```

#### Success Criteria

**Automated Verification**:
- [ ] File created at `scripts/little_loops/fsm/evaluators.py`
- [ ] No syntax errors: `python -c "from little_loops.fsm.evaluators import EvaluationResult"`
- [ ] Type check passes: `python -m mypy scripts/little_loops/fsm/evaluators.py`

---

### Phase 2: Implement JSON Evaluator and Convergence Evaluator

#### Overview
Add the more complex evaluators: `output_json` (requires JSON parsing and path extraction) and `convergence` (requires interpolation integration).

#### Changes Required

**File**: `scripts/little_loops/fsm/evaluators.py`
**Changes**: Add `_extract_json_path()` helper, `evaluate_output_json()`, and `evaluate_convergence()` functions

Key implementation details:
- `_extract_json_path()` handles jq-style dot notation (`.summary.failed`)
- `evaluate_convergence()` uses `interpolate()` to resolve `${prev.output}` references
- Convergence supports both `minimize` and `maximize` directions

#### Success Criteria

**Automated Verification**:
- [ ] Import succeeds with all functions: `python -c "from little_loops.fsm.evaluators import evaluate_output_json, evaluate_convergence"`
- [ ] Type check passes: `python -m mypy scripts/little_loops/fsm/evaluators.py`

---

### Phase 3: Implement Dispatcher and Update Exports

#### Overview
Add the main `evaluate()` dispatcher function that routes to appropriate evaluators based on `EvaluateConfig.type`. Update `__init__.py` to export the new functions.

#### Changes Required

**File**: `scripts/little_loops/fsm/evaluators.py`
**Changes**: Add `evaluate()` dispatcher function

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add evaluator exports

```python
from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_exit_code,
    evaluate_output_numeric,
    evaluate_output_json,
    evaluate_output_contains,
    evaluate_convergence,
)

__all__ = [
    # ... existing exports
    "EvaluationResult",
    "evaluate",
    "evaluate_exit_code",
    "evaluate_output_numeric",
    "evaluate_output_json",
    "evaluate_output_contains",
    "evaluate_convergence",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Import from package succeeds: `python -c "from little_loops.fsm import evaluate, EvaluationResult"`
- [ ] Type check passes: `python -m mypy scripts/little_loops/fsm/`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/`

---

### Phase 4: Create Comprehensive Tests

#### Overview
Create `test_fsm_evaluators.py` with tests for all evaluators following the patterns established in `test_fsm_interpolation.py`.

#### Changes Required

**File**: `scripts/tests/test_fsm_evaluators.py`
**Changes**: Create new test file with comprehensive coverage

Test classes to include:
- `TestEvaluationResult`: Basic dataclass tests
- `TestExitCodeEvaluator`: Parametrized tests for exit code mapping
- `TestOutputNumericEvaluator`: All operators, parse errors
- `TestOutputJsonEvaluator`: Path extraction, operators, error cases
- `TestOutputContainsEvaluator`: Regex, substring, negate
- `TestConvergenceEvaluator`: Target, progress, stall, direction
- `TestEvaluateDispatcher`: Routing to correct evaluators

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`
- [ ] All acceptance criteria from issue are covered

---

### Phase 5: Final Verification

#### Overview
Run full test suite and verification to ensure everything works together.

#### Success Criteria

**Automated Verification**:
- [ ] All FSM tests pass: `python -m pytest scripts/tests/test_fsm*.py -v`
- [ ] Full lint passes: `ruff check scripts/`
- [ ] Full type check passes: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Exit code mapping: 0→success, 1→failure, 2+→error
- Numeric comparison: all six operators (eq, ne, lt, le, gt, ge)
- JSON path extraction: nested paths, array indices
- Pattern matching: regex, substring, negate flag
- Convergence: target reached, progress, stall, direction

### Edge Cases
- Parse errors (non-numeric output, invalid JSON)
- Missing JSON paths
- Invalid operators
- First iteration with no previous value

## References

- Original issue: `.issues/features/P1-FEAT-043-tier1-deterministic-evaluators.md`
- Schema reference: `scripts/little_loops/fsm/schema.py:22-125`
- Interpolation reference: `scripts/little_loops/fsm/interpolation.py:169-206`
- Validation reference: `scripts/little_loops/fsm/validation.py:58-143`
- Test patterns: `scripts/tests/test_fsm_interpolation.py`
