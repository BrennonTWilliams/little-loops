"""FSM loop schema dataclasses.

This module defines the type-safe dataclasses that represent FSM loop
definitions. These match the universal FSM schema described in the
design documentation.

The schema supports:
- Multiple evaluator types (exit_code, output_numeric, etc.)
- Two-layer transition system (evaluate + route)
- Both shorthand (on_success/on_failure) and full routing syntax
- Context variables and captured values
- LLM evaluation configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class EvaluateConfig:
    """Evaluator configuration for action result interpretation.

    The evaluator determines how to interpret an action's output and
    produce a verdict string for routing.

    Attributes:
        type: Evaluator type. One of:
            - exit_code: Map exit codes to verdicts (default for shell)
            - output_numeric: Compare numeric output to target
            - output_json: Extract and compare JSON path value
            - output_contains: Pattern matching on stdout
            - convergence: Compare current vs previous value toward target
            - llm_structured: Use LLM with structured output (default for slash)
        operator: Comparison operator (eq, ne, lt, le, gt, ge)
        target: Target value for comparison
        tolerance: Acceptable distance from target (for convergence)
        pattern: Pattern string for output_contains
        negate: If True, invert the match result (output_contains)
        path: JSON path for output_json (jq-style)
        prompt: Custom prompt for llm_structured
        schema: Custom JSON schema for llm_structured response
        min_confidence: Minimum confidence threshold for llm_structured
        uncertain_suffix: If True, append _uncertain to low-confidence verdicts
        source: Override default source (current action output)
        previous: Previous value reference for convergence
        direction: Optimization direction for convergence (minimize/maximize)
    """

    type: Literal[
        "exit_code",
        "output_numeric",
        "output_json",
        "output_contains",
        "convergence",
        "llm_structured",
    ]
    operator: str | None = None
    target: int | float | str | None = None
    tolerance: float | None = None
    pattern: str | None = None
    negate: bool = False
    path: str | None = None
    prompt: str | None = None
    schema: dict[str, Any] | None = None
    min_confidence: float = 0.5
    uncertain_suffix: bool = False
    source: str | None = None
    previous: str | None = None
    direction: Literal["minimize", "maximize"] = "minimize"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {"type": self.type}

        # Only include non-None optional fields
        if self.operator is not None:
            result["operator"] = self.operator
        if self.target is not None:
            result["target"] = self.target
        if self.tolerance is not None:
            result["tolerance"] = self.tolerance
        if self.pattern is not None:
            result["pattern"] = self.pattern
        if self.negate:
            result["negate"] = self.negate
        if self.path is not None:
            result["path"] = self.path
        if self.prompt is not None:
            result["prompt"] = self.prompt
        if self.schema is not None:
            result["schema"] = self.schema
        if self.min_confidence != 0.5:
            result["min_confidence"] = self.min_confidence
        if self.uncertain_suffix:
            result["uncertain_suffix"] = self.uncertain_suffix
        if self.source is not None:
            result["source"] = self.source
        if self.previous is not None:
            result["previous"] = self.previous
        if self.direction != "minimize":
            result["direction"] = self.direction

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluateConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            type=data["type"],
            operator=data.get("operator"),
            target=data.get("target"),
            tolerance=data.get("tolerance"),
            pattern=data.get("pattern"),
            negate=data.get("negate", False),
            path=data.get("path"),
            prompt=data.get("prompt"),
            schema=data.get("schema"),
            min_confidence=data.get("min_confidence", 0.5),
            uncertain_suffix=data.get("uncertain_suffix", False),
            source=data.get("source"),
            previous=data.get("previous"),
            direction=data.get("direction", "minimize"),
        )


@dataclass
class RouteConfig:
    """Routing table configuration for verdict-to-state mapping.

    Maps verdict strings from evaluators to next state names.

    Attributes:
        routes: Mapping from verdict string to next state name
        default: Default state for unmatched verdicts (the "_" key)
        error: State for evaluation/execution errors (the "_error" key)
    """

    routes: dict[str, str] = field(default_factory=dict)
    default: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result = dict(self.routes)
        if self.default is not None:
            result["_"] = self.default
        if self.error is not None:
            result["_error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        routes = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls(
            routes=routes,
            default=data.get("_"),
            error=data.get("_error"),
        )


@dataclass
class StateConfig:
    """Configuration for a single FSM state.

    States can have actions, evaluators, and routing. Supports both
    shorthand (on_success/on_failure) and full routing table syntax.

    Attributes:
        action: Command to execute (shell or slash command)
        evaluate: Evaluator configuration for result interpretation
        route: Full routing table (verdict -> state mapping)
        on_success: Shorthand for success verdict routing
        on_failure: Shorthand for failure verdict routing
        on_error: Shorthand for error verdict routing
        next: Unconditional transition (no evaluation)
        terminal: If True, this is an end state
        capture: Variable name to store action output
        timeout: Action-level timeout in seconds
        on_maintain: State to transition to when maintain=True and loop completes
    """

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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}

        if self.action is not None:
            result["action"] = self.action
        if self.evaluate is not None:
            result["evaluate"] = self.evaluate.to_dict()
        if self.route is not None:
            result["route"] = self.route.to_dict()
        if self.on_success is not None:
            result["on_success"] = self.on_success
        if self.on_failure is not None:
            result["on_failure"] = self.on_failure
        if self.on_error is not None:
            result["on_error"] = self.on_error
        if self.next is not None:
            result["next"] = self.next
        if self.terminal:
            result["terminal"] = self.terminal
        if self.capture is not None:
            result["capture"] = self.capture
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.on_maintain is not None:
            result["on_maintain"] = self.on_maintain

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        evaluate = None
        if "evaluate" in data:
            evaluate = EvaluateConfig.from_dict(data["evaluate"])

        route = None
        if "route" in data:
            route = RouteConfig.from_dict(data["route"])

        return cls(
            action=data.get("action"),
            evaluate=evaluate,
            route=route,
            on_success=data.get("on_success"),
            on_failure=data.get("on_failure"),
            on_error=data.get("on_error"),
            next=data.get("next"),
            terminal=data.get("terminal", False),
            capture=data.get("capture"),
            timeout=data.get("timeout"),
            on_maintain=data.get("on_maintain"),
        )

    def get_referenced_states(self) -> set[str]:
        """Get all state names referenced by this state configuration.

        Returns:
            Set of state names that this state can transition to.
        """
        refs: set[str] = set()

        if self.on_success is not None:
            refs.add(self.on_success)
        if self.on_failure is not None:
            refs.add(self.on_failure)
        if self.on_error is not None:
            refs.add(self.on_error)
        if self.next is not None:
            refs.add(self.next)
        if self.on_maintain is not None:
            refs.add(self.on_maintain)
        if self.route is not None:
            refs.update(self.route.routes.values())
            if self.route.default is not None:
                refs.add(self.route.default)
            if self.route.error is not None:
                refs.add(self.route.error)

        return refs


@dataclass
class LLMConfig:
    """LLM evaluation configuration.

    Settings for the llm_structured evaluator.

    Attributes:
        enabled: If False, disable LLM evaluation entirely
        model: Model identifier for LLM calls
        max_tokens: Maximum tokens for evaluation response
        timeout: Timeout for LLM calls in seconds
    """

    enabled: bool = True
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 256
    timeout: int = 30

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}

        if not self.enabled:
            result["enabled"] = self.enabled
        if self.model != "claude-sonnet-4-20250514":
            result["model"] = self.model
        if self.max_tokens != 256:
            result["max_tokens"] = self.max_tokens
        if self.timeout != 30:
            result["timeout"] = self.timeout

        return result if result else {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            enabled=data.get("enabled", True),
            model=data.get("model", "claude-sonnet-4-20250514"),
            max_tokens=data.get("max_tokens", 256),
            timeout=data.get("timeout", 30),
        )


@dataclass
class FSMLoop:
    """Complete FSM loop definition.

    The main dataclass representing a loop configuration. This matches
    the universal FSM schema that all paradigms compile to.

    Attributes:
        name: Unique loop identifier
        initial: Starting state name
        states: Mapping from state name to StateConfig
        paradigm: Source paradigm (for reference, e.g., "goal", "convergence")
        context: User-defined shared variables
        scope: Paths this loop operates on (for concurrency control)
        max_iterations: Safety limit for loop iterations
        backoff: Seconds between iterations
        timeout: Max total runtime in seconds (loop-level)
        maintain: If True, restart after completion
        llm: LLM evaluation configuration
    """

    name: str
    initial: str
    states: dict[str, StateConfig]
    paradigm: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    scope: list[str] = field(default_factory=list)
    max_iterations: int = 50
    backoff: float | None = None
    timeout: int | None = None
    maintain: bool = False
    llm: LLMConfig = field(default_factory=LLMConfig)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "initial": self.initial,
            "states": {name: state.to_dict() for name, state in self.states.items()},
        }

        if self.paradigm is not None:
            result["paradigm"] = self.paradigm
        if self.context:
            result["context"] = self.context
        if self.scope:
            result["scope"] = self.scope
        if self.max_iterations != 50:
            result["max_iterations"] = self.max_iterations
        if self.backoff is not None:
            result["backoff"] = self.backoff
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.maintain:
            result["maintain"] = self.maintain

        llm_dict = self.llm.to_dict()
        if llm_dict:
            result["llm"] = llm_dict

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FSMLoop:
        """Create from dictionary (JSON/YAML deserialization)."""
        states = {
            name: StateConfig.from_dict(state_data)
            for name, state_data in data.get("states", {}).items()
        }

        llm = LLMConfig()
        if "llm" in data:
            llm = LLMConfig.from_dict(data["llm"])

        return cls(
            name=data["name"],
            initial=data["initial"],
            states=states,
            paradigm=data.get("paradigm"),
            context=data.get("context", {}),
            scope=data.get("scope", []),
            max_iterations=data.get("max_iterations", 50),
            backoff=data.get("backoff"),
            timeout=data.get("timeout"),
            maintain=data.get("maintain", False),
            llm=llm,
        )

    def get_all_state_names(self) -> set[str]:
        """Get all defined state names.

        Returns:
            Set of all state names in this FSM.
        """
        return set(self.states.keys())

    def get_terminal_states(self) -> set[str]:
        """Get all terminal state names.

        Returns:
            Set of state names where terminal=True.
        """
        return {name for name, state in self.states.items() if state.terminal}

    def get_all_referenced_states(self) -> set[str]:
        """Get all state names referenced by transitions.

        This includes the initial state and all states referenced
        in routing configurations.

        Returns:
            Set of all referenced state names.
        """
        refs: set[str] = {self.initial}
        for state in self.states.values():
            refs.update(state.get_referenced_states())
        return refs
