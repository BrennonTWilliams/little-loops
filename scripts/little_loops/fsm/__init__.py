"""FSM loop schema, validation, compilation, interpolation, evaluators, and execution.

This module provides the type-safe representation of FSM loop definitions,
validation logic, paradigm compilers, variable interpolation, evaluators,
and the execution engine for the little-loops FSM system.

Public exports:
    # Schema
    FSMLoop: Main dataclass representing a complete loop definition
    StateConfig: Configuration for a single state
    EvaluateConfig: Evaluator configuration
    RouteConfig: Routing table configuration
    LLMConfig: LLM evaluation settings

    # Validation
    ValidationError: Structured validation error
    validate_fsm: Validate FSM structure
    load_and_validate: Load YAML and validate

    # Compilation
    compile_paradigm: Compile high-level paradigm spec to FSMLoop

    # Interpolation
    InterpolationContext: Runtime context for variable resolution
    InterpolationError: Exception for interpolation failures
    interpolate: Resolve variables in a string
    interpolate_dict: Recursively resolve variables in a dict

    # Evaluation
    EvaluationResult: Result from an evaluator
    evaluate: Main dispatcher for evaluators
    evaluate_exit_code: Exit code to verdict mapping (Tier 1)
    evaluate_output_numeric: Numeric comparison evaluator (Tier 1)
    evaluate_output_json: JSON path extraction evaluator (Tier 1)
    evaluate_output_contains: Pattern matching evaluator (Tier 1)
    evaluate_convergence: Progress tracking evaluator (Tier 1)
    evaluate_llm_structured: LLM structured output evaluator (Tier 2)
    DEFAULT_LLM_SCHEMA: Default schema for LLM evaluation
    DEFAULT_LLM_PROMPT: Default prompt for LLM evaluation

    # Execution
    FSMExecutor: Runtime engine for FSM loop execution
    ExecutionResult: Result from FSM execution
    ActionResult: Result from action execution
    ActionRunner: Protocol for action execution (for testing/customization)

    # Persistence
    LoopState: Persistent state for loop execution
    StatePersistence: File I/O for state and events
    PersistentExecutor: Executor wrapper with persistence
    list_running_loops: List all loops with saved state
    get_loop_history: Get event history for a loop
"""

from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.evaluators import (
    DEFAULT_LLM_PROMPT,
    DEFAULT_LLM_SCHEMA,
    EvaluationResult,
    evaluate,
    evaluate_convergence,
    evaluate_exit_code,
    evaluate_llm_structured,
    evaluate_output_contains,
    evaluate_output_json,
    evaluate_output_numeric,
)
from little_loops.fsm.executor import (
    ActionResult,
    ActionRunner,
    ExecutionResult,
    FSMExecutor,
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
from little_loops.fsm.persistence import (
    LoopState,
    PersistentExecutor,
    StatePersistence,
    get_loop_history,
    list_running_loops,
)
from little_loops.fsm.validation import (
    ValidationError,
    load_and_validate,
    validate_fsm,
)

__all__ = [
    "ActionResult",
    "ActionRunner",
    "DEFAULT_LLM_PROMPT",
    "DEFAULT_LLM_SCHEMA",
    "EvaluateConfig",
    "EvaluationResult",
    "ExecutionResult",
    "FSMExecutor",
    "FSMLoop",
    "InterpolationContext",
    "InterpolationError",
    "LLMConfig",
    "LoopState",
    "PersistentExecutor",
    "RouteConfig",
    "StateConfig",
    "StatePersistence",
    "ValidationError",
    "compile_paradigm",
    "evaluate",
    "evaluate_convergence",
    "evaluate_exit_code",
    "evaluate_llm_structured",
    "evaluate_output_contains",
    "evaluate_output_json",
    "evaluate_output_numeric",
    "get_loop_history",
    "interpolate",
    "interpolate_dict",
    "list_running_loops",
    "load_and_validate",
    "validate_fsm",
]
