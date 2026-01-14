"""FSM loop schema and validation.

This module provides the type-safe representation of FSM loop definitions
and validation logic for the little-loops FSM system.

Public exports:
    FSMLoop: Main dataclass representing a complete loop definition
    StateConfig: Configuration for a single state
    EvaluateConfig: Evaluator configuration
    RouteConfig: Routing table configuration
    LLMConfig: LLM evaluation settings
    ValidationError: Structured validation error
    validate_fsm: Validate FSM structure
    load_and_validate: Load YAML and validate
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
