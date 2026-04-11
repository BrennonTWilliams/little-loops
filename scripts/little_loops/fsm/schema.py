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

# Default LLM model for structured evaluation
DEFAULT_LLM_MODEL: str = "sonnet"


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
        scope: Paths to limit git diff to for diff_stall evaluator
        max_stall: Consecutive no-change iterations before failure (diff_stall)
    """

    type: Literal[
        "exit_code",
        "output_numeric",
        "output_json",
        "output_contains",
        "convergence",
        "diff_stall",
        "llm_structured",
        "mcp_result",
    ]
    operator: str | None = None
    target: int | float | str | None = None
    tolerance: float | str | None = None  # str for interpolation (e.g., "${context.tolerance}")
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
    scope: list[str] | None = None  # for diff_stall: limit git diff to these paths
    max_stall: int = 1  # for diff_stall: consecutive no-change iterations before failure

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
        if self.scope is not None:
            result["scope"] = self.scope
        if self.max_stall != 1:
            result["max_stall"] = self.max_stall

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
            scope=data.get("scope"),
            max_stall=data.get("max_stall", 1),
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
        action: Command to execute (shell, slash command, or "server/tool-name" for mcp_tool)
        action_type: How to execute the action (prompt, slash_command, shell, mcp_tool).
            If None, uses heuristic: / prefix = slash_command, else = shell.
        params: MCP tool arguments (only used with action_type: mcp_tool). Supports
            ${variable} interpolation in string values.
        evaluate: Evaluator configuration for result interpretation
        route: Full routing table (verdict -> state mapping)
        on_yes: Shorthand for yes verdict routing
        on_no: Shorthand for no verdict routing
        on_error: Shorthand for error verdict routing
        on_partial: Shorthand for partial verdict routing
        next: Unconditional transition (no evaluation)
        terminal: If True, this is an end state
        capture: Variable name to store action output
        timeout: Action-level timeout in seconds
        on_maintain: State to transition to when maintain=True and loop completes
        max_retries: Max consecutive re-entries before transitioning to on_retry_exhausted.
            A value of N allows N retries after the initial execution (N+1 total entries).
            Requires on_retry_exhausted to also be set.
        on_retry_exhausted: State to transition to when max_retries consecutive re-entries
            are exceeded. Required when max_retries is set.
        loop: Name of a loop YAML to execute as a sub-FSM. Mutually exclusive with action.
        context_passthrough: When True, pass parent context variables to child loop and
            merge child captures back into parent context.
    """

    action: str | None = None
    action_type: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    evaluate: EvaluateConfig | None = None
    route: RouteConfig | None = None
    on_yes: str | None = None
    on_no: str | None = None
    on_error: str | None = None
    on_partial: str | None = None
    on_blocked: str | None = None
    next: str | None = None
    terminal: bool = False
    capture: str | None = None
    timeout: int | None = None
    on_maintain: str | None = None
    max_retries: int | None = None
    on_retry_exhausted: str | None = None
    loop: str | None = None
    context_passthrough: bool = False
    agent: str | None = None
    tools: list[str] | None = None
    extra_routes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}

        if self.action is not None:
            result["action"] = self.action
        if self.action_type is not None:
            result["action_type"] = self.action_type
        if self.params:
            result["params"] = self.params
        if self.evaluate is not None:
            result["evaluate"] = self.evaluate.to_dict()
        if self.route is not None:
            result["route"] = self.route.to_dict()
        if self.on_yes is not None:
            result["on_yes"] = self.on_yes
        if self.on_no is not None:
            result["on_no"] = self.on_no
        if self.on_error is not None:
            result["on_error"] = self.on_error
        if self.on_partial is not None:
            result["on_partial"] = self.on_partial
        if self.on_blocked is not None:
            result["on_blocked"] = self.on_blocked
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
        if self.max_retries is not None:
            result["max_retries"] = self.max_retries
        if self.on_retry_exhausted is not None:
            result["on_retry_exhausted"] = self.on_retry_exhausted
        if self.loop is not None:
            result["loop"] = self.loop
        if self.context_passthrough:
            result["context_passthrough"] = self.context_passthrough
        if self.agent is not None:
            result["agent"] = self.agent
        if self.tools is not None:
            result["tools"] = self.tools
        for verdict, target in self.extra_routes.items():
            result[f"on_{verdict}"] = target

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

        _known_on_keys = {
            "on_yes",
            "on_success",
            "on_no",
            "on_failure",
            "on_error",
            "on_partial",
            "on_blocked",
            "on_maintain",
            "on_retry_exhausted",
        }
        extra_routes = {
            key[3:]: val
            for key, val in data.items()
            if key.startswith("on_") and key not in _known_on_keys and isinstance(val, str)
        }

        return cls(
            action=data.get("action"),
            action_type=data.get("action_type"),
            params=data.get("params", {}),
            evaluate=evaluate,
            route=route,
            on_yes=data.get("on_yes") or data.get("on_success"),
            on_no=data.get("on_no") or data.get("on_failure"),
            on_error=data.get("on_error"),
            on_partial=data.get("on_partial"),
            on_blocked=data.get("on_blocked"),
            next=data.get("next"),
            terminal=data.get("terminal", False),
            capture=data.get("capture"),
            timeout=data.get("timeout"),
            on_maintain=data.get("on_maintain"),
            max_retries=data.get("max_retries"),
            on_retry_exhausted=data.get("on_retry_exhausted"),
            loop=data.get("loop"),
            context_passthrough=data.get("context_passthrough", False),
            agent=data.get("agent"),
            tools=data.get("tools"),
            extra_routes=extra_routes,
        )

    def get_referenced_states(self) -> set[str]:
        """Get all state names referenced by this state configuration.

        Returns:
            Set of state names that this state can transition to.
        """
        refs: set[str] = set()

        if self.on_yes is not None:
            refs.add(self.on_yes)
        if self.on_no is not None:
            refs.add(self.on_no)
        if self.on_error is not None:
            refs.add(self.on_error)
        if self.on_partial is not None:
            refs.add(self.on_partial)
        if self.on_blocked is not None:
            refs.add(self.on_blocked)
        if self.next is not None:
            refs.add(self.next)
        if self.on_maintain is not None:
            refs.add(self.on_maintain)
        if self.on_retry_exhausted is not None:
            refs.add(self.on_retry_exhausted)
        if self.route is not None:
            refs.update(self.route.routes.values())
            if self.route.default is not None:
                refs.add(self.route.default)
            if self.route.error is not None:
                refs.add(self.route.error)
        refs.update(self.extra_routes.values())

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
    model: str = DEFAULT_LLM_MODEL
    max_tokens: int = 256
    timeout: int = 1800

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}

        if not self.enabled:
            result["enabled"] = self.enabled
        if self.model != DEFAULT_LLM_MODEL:
            result["model"] = self.model
        if self.max_tokens != 256:
            result["max_tokens"] = self.max_tokens
        if self.timeout != 1800:
            result["timeout"] = self.timeout

        return result if result else {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            enabled=data.get("enabled", True),
            model=data.get("model", DEFAULT_LLM_MODEL),
            max_tokens=data.get("max_tokens", 256),
            timeout=data.get("timeout", 1800),
        )


@dataclass
class LoopConfigOverrides:
    """Per-loop ll-config overrides embedded in the loop YAML definition.

    All fields are optional (None = use global ll-config default).
    Precedence: CLI flags > YAML config block > global ll-config > schema defaults.

    Attributes:
        handoff_threshold: Override for LL_HANDOFF_THRESHOLD env var (1-100)
        readiness_threshold: Override for commands.confidence_gate.readiness_threshold (1-100)
        outcome_threshold: Override for commands.confidence_gate.outcome_threshold (1-100)
        max_continuations: Override for automation.max_continuations (>=1)
    """

    handoff_threshold: int | None = None
    readiness_threshold: int | None = None
    outcome_threshold: int | None = None
    max_continuations: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization (skip-if-None)."""
        result: dict[str, Any] = {}

        if self.handoff_threshold is not None:
            result["handoff_threshold"] = self.handoff_threshold

        confidence_gate: dict[str, Any] = {}
        if self.readiness_threshold is not None:
            confidence_gate["readiness_threshold"] = self.readiness_threshold
        if self.outcome_threshold is not None:
            confidence_gate["outcome_threshold"] = self.outcome_threshold
        if confidence_gate:
            result["commands"] = {"confidence_gate": confidence_gate}

        if self.max_continuations is not None:
            result["automation"] = {"max_continuations": self.max_continuations}

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopConfigOverrides:
        """Create from dictionary (JSON/YAML deserialization)."""
        commands = data.get("commands", {})
        confidence_gate = commands.get("confidence_gate", {}) if isinstance(commands, dict) else {}
        automation = data.get("automation", {})
        continuation = data.get("continuation", {})

        max_continuations = None
        if isinstance(automation, dict) and "max_continuations" in automation:
            max_continuations = automation["max_continuations"]
        elif isinstance(continuation, dict) and "max_continuations" in continuation:
            max_continuations = continuation["max_continuations"]

        return cls(
            handoff_threshold=data.get("handoff_threshold"),
            readiness_threshold=confidence_gate.get("readiness_threshold")
            if isinstance(confidence_gate, dict)
            else None,
            outcome_threshold=confidence_gate.get("outcome_threshold")
            if isinstance(confidence_gate, dict)
            else None,
            max_continuations=max_continuations,
        )


@dataclass
class FSMLoop:
    """Complete FSM loop definition.

    The main dataclass representing a loop configuration.

    Attributes:
        name: Unique loop identifier
        initial: Starting state name
        states: Mapping from state name to StateConfig
        context: User-defined shared variables
        scope: Paths this loop operates on (for concurrency control)
        max_iterations: Safety limit for loop iterations
        backoff: Seconds between iterations
        timeout: Max total runtime in seconds (loop-level)
        maintain: If True, restart after completion
        llm: LLM evaluation configuration
        on_handoff: Behavior when handoff signal detected (pause/spawn/terminate)
    """

    name: str
    initial: str
    states: dict[str, StateConfig]
    description: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    scope: list[str] = field(default_factory=list)
    max_iterations: int = 50
    backoff: float | None = None
    timeout: int | None = None
    default_timeout: int | None = None
    maintain: bool = False
    llm: LLMConfig = field(default_factory=LLMConfig)
    on_handoff: Literal["pause", "spawn", "terminate"] = "pause"
    input_key: str = "input"
    config: LoopConfigOverrides | None = None
    category: str = ""
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "initial": self.initial,
            "states": {name: state.to_dict() for name, state in self.states.items()},
        }

        if self.description is not None:
            result["description"] = self.description
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
        if self.default_timeout is not None:
            result["default_timeout"] = self.default_timeout
        if self.maintain:
            result["maintain"] = self.maintain
        if self.on_handoff != "pause":
            result["on_handoff"] = self.on_handoff
        if self.input_key != "input":
            result["input_key"] = self.input_key

        llm_dict = self.llm.to_dict()
        if llm_dict:
            result["llm"] = llm_dict

        if self.config is not None:
            config_dict = self.config.to_dict()
            if config_dict:
                result["config"] = config_dict

        if self.category:
            result["category"] = self.category
        if self.labels:
            result["labels"] = self.labels

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

        loop_config = None
        if "config" in data:
            loop_config = LoopConfigOverrides.from_dict(data["config"])

        return cls(
            name=data["name"],
            initial=data["initial"],
            states=states,
            description=data.get("description"),
            context=data.get("context", {}),
            scope=data.get("scope", []),
            max_iterations=data.get("max_iterations", 50),
            backoff=data.get("backoff"),
            timeout=data.get("timeout"),
            default_timeout=data.get("default_timeout"),
            maintain=data.get("maintain", False),
            llm=llm,
            on_handoff=data.get("on_handoff", "pause"),
            input_key=data.get("input_key", "input"),
            config=loop_config,
            category=data.get("category", ""),
            labels=data.get("labels", []),
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
