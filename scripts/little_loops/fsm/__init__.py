"""FSM loop schema, validation, interpolation, evaluators, and execution.

This module provides the type-safe representation of FSM loop definitions,
validation logic, variable interpolation, evaluators, and the execution engine
for the little-loops FSM system.

Public exports:
    # Schema
    FSMLoop: Main dataclass representing a complete loop definition
    CommandEntry: A single entry in the loop's Commands display section
    StateConfig: Configuration for a single state
    EvaluateConfig: Evaluator configuration
    RouteConfig: Routing table configuration
    LLMConfig: LLM evaluation settings
    DEFAULT_LLM_MODEL: Default LLM model identifier

    # Validation
    ValidationError: Structured validation error
    validate_fsm: Validate FSM structure
    load_and_validate: Load YAML and validate

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
    RESUMABLE_STATUSES: Set of loop status strings that can be resumed
    LoopState: Persistent state for loop execution
    StatePersistence: File I/O for state and events
    PersistentExecutor: Executor wrapper with persistence
    list_running_loops: List all loops with saved state
    get_loop_history: Get event history for a loop

    # Signal Detection
    SignalDetector: Detect signals in command output
    SignalPattern: Configurable signal pattern for detection
    DetectedSignal: A signal detected in command output
    HANDOFF_SIGNAL: Built-in handoff signal pattern
    ERROR_SIGNAL: Built-in error signal pattern
    STOP_SIGNAL: Built-in stop signal pattern

    # Handoff Handling
    HandoffHandler: Handle context handoff signals
    HandoffBehavior: Enum for handoff behaviors (pause/spawn/terminate)
    HandoffResult: Result from handling a handoff signal

    # Concurrency Control
    ScopeLock: Dataclass representing a scope lock
    LockManager: Manager for acquiring/releasing scope locks
    resolve_scope: Resolve ${context.<var>} templates in scope paths

    # Circuit Breaker
    RateLimitCircuit: Shared circuit-breaker state for cross-worktree 429 coordination
"""

from little_loops.ab_writer import ABResults, calculate_ab_summary, write_ab_json
from little_loops.fsm.concurrency import (
    LockManager,
    ScopeLock,
    resolve_scope,
)
from little_loops.fsm.evaluators import (
    DEFAULT_LLM_PROMPT,
    DEFAULT_LLM_SCHEMA,
    EvaluationResult,
    evaluate,
    evaluate_blind_comparator,
    evaluate_comparator,
    evaluate_contract,
    evaluate_convergence,
    evaluate_exit_code,
    evaluate_llm_structured,
    evaluate_output_contains,
    evaluate_output_json,
    evaluate_output_numeric,
)
from little_loops.fsm.executor import (
    PROMPT_SIZE_WARN_EVENT,
    RATE_LIMIT_EXHAUSTED_EVENT,
    RATE_LIMIT_STORM_EVENT,
    RATE_LIMIT_WAITING_EVENT,
    STALL_DETECTED_EVENT,
    THROTTLE_HARD_EVENT,
    THROTTLE_STOP_EVENT,
    THROTTLE_WARN_EVENT,
    ActionResult,
    ActionRunner,
    EventCallback,
    ExecutionResult,
    FSMExecutor,
    RouteContext,
    RouteDecision,
)
from little_loops.fsm.handoff_handler import (
    HandoffBehavior,
    HandoffHandler,
    HandoffResult,
)
from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
    interpolate_dict,
)
from little_loops.fsm.persistence import (
    RESUMABLE_STATUSES,
    LoopState,
    PersistentExecutor,
    StatePersistence,
    get_loop_history,
    list_running_loops,
)
from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
from little_loops.fsm.schema import (
    DEFAULT_LLM_MODEL,
    CircuitConfig,
    CommandEntry,
    EvaluateConfig,
    FSMLoop,
    LearningConfig,
    LLMConfig,
    ParameterSpec,
    PromptSizeGuardConfig,
    RepeatedFailureConfig,
    RouteConfig,
    StateConfig,
    TargetFileSpec,
    TargetStateSpec,
    ThrottleConfig,
)
from little_loops.fsm.signal_detector import (
    ERROR_SIGNAL,
    HANDOFF_SIGNAL,
    STOP_SIGNAL,
    DetectedSignal,
    SignalDetector,
    SignalPattern,
)
from little_loops.fsm.stall_detector import Stall, StallDetector
from little_loops.fsm.types import Evaluator
from little_loops.fsm.validation import (
    ValidationError,
    is_runnable_loop,
    load_and_validate,
    validate_fsm,
)

__all__ = [
    "ABResults",
    "ActionResult",
    "ActionRunner",
    "CircuitConfig",
    "CommandEntry",
    "PROMPT_SIZE_WARN_EVENT",
    "RATE_LIMIT_EXHAUSTED_EVENT",
    "RATE_LIMIT_STORM_EVENT",
    "RATE_LIMIT_WAITING_EVENT",
    "STALL_DETECTED_EVENT",
    "DEFAULT_LLM_MODEL",
    "Evaluator",
    "EventCallback",
    "DEFAULT_LLM_PROMPT",
    "DEFAULT_LLM_SCHEMA",
    "DetectedSignal",
    "ERROR_SIGNAL",
    "EvaluateConfig",
    "EvaluationResult",
    "ExecutionResult",
    "FSMExecutor",
    "FSMLoop",
    "HANDOFF_SIGNAL",
    "HandoffBehavior",
    "HandoffHandler",
    "HandoffResult",
    "InterpolationContext",
    "InterpolationError",
    "LearningConfig",
    "LLMConfig",
    "LockManager",
    "ParameterSpec",
    "PromptSizeGuardConfig",
    "resolve_scope",
    "LoopState",
    "PersistentExecutor",
    "RESUMABLE_STATUSES",
    "RateLimitCircuit",
    "RepeatedFailureConfig",
    "RouteConfig",
    "RouteContext",
    "RouteDecision",
    "STOP_SIGNAL",
    "ScopeLock",
    "SignalDetector",
    "SignalPattern",
    "Stall",
    "StallDetector",
    "StateConfig",
    "StatePersistence",
    "TargetFileSpec",
    "TargetStateSpec",
    "THROTTLE_HARD_EVENT",
    "THROTTLE_STOP_EVENT",
    "THROTTLE_WARN_EVENT",
    "ThrottleConfig",
    "ValidationError",
    "calculate_ab_summary",
    "evaluate",
    "evaluate_blind_comparator",
    "evaluate_comparator",
    "evaluate_contract",
    "evaluate_convergence",
    "evaluate_exit_code",
    "evaluate_llm_structured",
    "evaluate_output_contains",
    "evaluate_output_json",
    "evaluate_output_numeric",
    "write_ab_json",
    "get_loop_history",
    "interpolate",
    "interpolate_dict",
    "is_runnable_loop",
    "list_running_loops",
    "load_and_validate",
    "validate_fsm",
]
