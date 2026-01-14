"""FSM loop schema, validation, paradigm compilation, and variable interpolation.

This module provides the type-safe representation of FSM loop definitions,
validation logic, paradigm compilers, and variable interpolation for the
little-loops FSM system.

Public exports:
    FSMLoop: Main dataclass representing a complete loop definition
    StateConfig: Configuration for a single state
    EvaluateConfig: Evaluator configuration
    RouteConfig: Routing table configuration
    LLMConfig: LLM evaluation settings
    ValidationError: Structured validation error
    validate_fsm: Validate FSM structure
    load_and_validate: Load YAML and validate
    compile_paradigm: Compile high-level paradigm spec to FSMLoop
    InterpolationContext: Runtime context for variable resolution
    InterpolationError: Exception for interpolation failures
    interpolate: Resolve variables in a string
    interpolate_dict: Recursively resolve variables in a dict
"""

from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
    interpolate_dict,
)
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
    "InterpolationContext",
    "InterpolationError",
    "LLMConfig",
    "RouteConfig",
    "StateConfig",
    "ValidationError",
    "compile_paradigm",
    "interpolate",
    "interpolate_dict",
    "load_and_validate",
    "validate_fsm",
]
