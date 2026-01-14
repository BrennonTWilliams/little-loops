"""FSM loop schema, validation, paradigm compilation, variable interpolation, and evaluators.

This module provides the type-safe representation of FSM loop definitions,
validation logic, paradigm compilers, variable interpolation, and deterministic
evaluators for the little-loops FSM system.

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
    EvaluationResult: Result from an evaluator
    evaluate: Main dispatcher for evaluators
    evaluate_exit_code: Exit code to verdict mapping
    evaluate_output_numeric: Numeric comparison evaluator
    evaluate_output_json: JSON path extraction evaluator
    evaluate_output_contains: Pattern matching evaluator
    evaluate_convergence: Progress tracking evaluator
"""

from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_convergence,
    evaluate_exit_code,
    evaluate_output_contains,
    evaluate_output_json,
    evaluate_output_numeric,
)
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
    "EvaluationResult",
    "FSMLoop",
    "InterpolationContext",
    "InterpolationError",
    "LLMConfig",
    "RouteConfig",
    "StateConfig",
    "ValidationError",
    "compile_paradigm",
    "evaluate",
    "evaluate_convergence",
    "evaluate_exit_code",
    "evaluate_output_contains",
    "evaluate_output_json",
    "evaluate_output_numeric",
    "interpolate",
    "interpolate_dict",
    "load_and_validate",
    "validate_fsm",
]
