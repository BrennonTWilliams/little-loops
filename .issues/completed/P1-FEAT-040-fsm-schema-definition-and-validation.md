# FEAT-040: FSM Schema Definition and Validation

## Summary

Create the foundational data structures and validation logic for the FSM loop system. This defines the universal schema that all paradigms compile to and all executors consume.

## Priority

P1 - Critical path for FSM loop system

## Dependencies

None - this is a foundational issue

## Blocked By

None

## Description

The FSM loop system requires a well-defined schema for loop definitions. This issue covers:

1. **Python dataclasses** for type-safe FSM representation
2. **JSON Schema** for YAML file validation
3. **Validation functions** with clear error messages
4. **Schema documentation** inline with code

### Files to Create

```
scripts/little_loops/fsm/
├── __init__.py
├── schema.py          # Dataclasses and types
└── validation.py      # Validation logic
```

## Technical Details

### Core Dataclasses

```python
# schema.py
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class EvaluateConfig:
    type: Literal["exit_code", "output_numeric", "output_json",
                  "output_contains", "convergence", "llm_structured"]
    # Type-specific fields as Optional
    operator: str | None = None
    target: int | float | str | None = None
    tolerance: float | None = None
    pattern: str | None = None
    negate: bool = False
    path: str | None = None
    prompt: str | None = None
    schema: dict | None = None
    min_confidence: float = 0.5
    uncertain_suffix: bool = False
    source: str | None = None
    previous: str | None = None
    direction: Literal["minimize", "maximize"] = "minimize"

@dataclass
class RouteConfig:
    routes: dict[str, str]  # verdict -> state_name
    default: str | None = None  # "_" key
    error: str | None = None    # "_error" key

@dataclass
class StateConfig:
    action: str | None = None
    evaluate: EvaluateConfig | None = None
    route: RouteConfig | None = None
    on_success: str | None = None
    on_failure: str | None = None
    on_error: str | None = None
    next: str | None = None
    terminal: bool = False
    capture: str | None = None
    timeout: int | None = None
    on_maintain: str | None = None

@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 256
    timeout: int = 30

@dataclass
class FSMLoop:
    name: str
    initial: str
    states: dict[str, StateConfig]
    paradigm: str | None = None
    context: dict[str, any] = field(default_factory=dict)
    scope: list[str] = field(default_factory=list)
    max_iterations: int = 50
    backoff: float | None = None
    timeout: int | None = None
    maintain: bool = False
    llm: LLMConfig = field(default_factory=LLMConfig)
```

### JSON Schema for YAML Validation

Create `fsm-loop-schema.json` that can validate `.loops/*.yaml` files:
- Required fields: `name`, `initial`, `states`
- State transition validation (referenced states must exist)
- Evaluator type-specific field validation

### Validation Functions

```python
# validation.py
def validate_fsm(fsm: FSMLoop) -> list[ValidationError]:
    """Validate FSM structure and return list of errors."""
    errors = []

    # Check initial state exists
    if fsm.initial not in fsm.states:
        errors.append(ValidationError(f"Initial state '{fsm.initial}' not found"))

    # Check all referenced states exist
    for name, state in fsm.states.items():
        for ref in _get_state_references(state):
            if ref not in fsm.states and ref != "$current":
                errors.append(ValidationError(f"State '{name}' references unknown state '{ref}'"))

    # Check at least one terminal state
    if not any(s.terminal for s in fsm.states.values()):
        errors.append(ValidationError("No terminal state defined"))

    # Validate evaluator configs
    for name, state in fsm.states.items():
        if state.evaluate:
            errors.extend(_validate_evaluator(name, state.evaluate))

    return errors

def load_and_validate(path: Path) -> FSMLoop:
    """Load YAML and validate, raising on errors."""
    ...
```

## Acceptance Criteria

- [ ] `FSMLoop` dataclass represents all schema fields from design doc
- [ ] `StateConfig` supports both shorthand (`on_success/on_failure`) and full routing
- [ ] `EvaluateConfig` supports all 6 evaluator types with appropriate fields
- [ ] `validate_fsm()` catches: missing initial state, dangling state references, no terminal state
- [ ] `load_and_validate()` loads YAML and returns typed `FSMLoop` or raises with clear errors
- [ ] JSON Schema file validates against all examples in design doc
- [ ] Unit tests cover valid and invalid FSM configurations
- [ ] Type hints pass `mypy --strict`

## Testing Requirements

```python
# tests/unit/test_schema.py
class TestFSMSchema:
    def test_minimal_valid_fsm(self):
        """Two-state FSM with terminal passes validation."""

    def test_missing_initial_state(self):
        """Error when initial state doesn't exist."""

    def test_dangling_state_reference(self):
        """Error when on_success references non-existent state."""

    def test_no_terminal_state(self):
        """Error when no state has terminal=true."""

    def test_shorthand_and_route_mutual_exclusion(self):
        """Warning when both on_success and route defined."""
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` sections "Universal FSM Schema" and "Two-Layer Transition System"

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/__init__.py`: Package exports for FSM module
- `scripts/little_loops/fsm/schema.py`: Core dataclasses (FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig) with full type hints, to_dict(), and from_dict() methods
- `scripts/little_loops/fsm/validation.py`: ValidationError dataclass, validate_fsm() function, load_and_validate() for YAML loading
- `scripts/little_loops/fsm/fsm-loop-schema.json`: JSON Schema for YAML IDE validation
- `scripts/tests/test_fsm_schema.py`: 48 unit tests covering all acceptance criteria

### Verification Results
- Tests: PASS (48 tests for FSM schema, 794 total)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
