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
        pairs: List of producer/consumer pair dicts for contract evaluator
    """

    type: Literal[
        "exit_code",
        "output_numeric",
        "output_json",
        "output_contains",
        "convergence",
        "diff_stall",
        "action_stall",
        "llm_structured",
        "mcp_result",
        "harbor_scorer",
        "comparator",
        "contract",
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
    track: list[str] | None = None  # for action_stall: context keys to track (default: ["action"])
    max_repeat: int = 2  # for action_stall: consecutive identical iterations before failure
    baseline_path: str | None = None  # for comparator: path to .loops/baselines/<loop>/ dir
    auto_promote: bool = False  # for comparator: write output to baseline on yes verdict
    min_pairs: int = 1  # for comparator: number of blind A/B comparisons to run
    pairs: list[dict] | None = None  # for contract: list of producer/consumer pair dicts

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
        if self.track is not None:
            result["track"] = self.track
        if self.max_repeat != 2:
            result["max_repeat"] = self.max_repeat
        if self.baseline_path is not None:
            result["baseline_path"] = self.baseline_path
        if self.auto_promote:
            result["auto_promote"] = self.auto_promote
        if self.min_pairs != 1:
            result["min_pairs"] = self.min_pairs
        if self.pairs is not None:
            result["pairs"] = self.pairs

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
            track=data.get("track"),
            max_repeat=data.get("max_repeat", 2),
            baseline_path=data.get("baseline_path"),
            auto_promote=data.get("auto_promote", False),
            min_pairs=data.get("min_pairs", 1),
            pairs=data.get("pairs"),
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
class ParameterSpec:
    """Specification for a single loop input parameter.

    Declares a typed input that callers bind via the 'with:' block on sub-loop states.

    Attributes:
        type: Parameter type. One of: string, integer, number, boolean, enum, path.
        required: If True, callers must supply this parameter in 'with:' (mutually
            exclusive with 'default').
        default: Default value used when the caller does not bind the parameter.
            Only valid when required is False.
        description: Human-readable description of the parameter.
        values: Allowed values for 'enum' type parameters.
    """

    type: str
    required: bool = False
    default: Any = None
    description: str | None = None
    values: list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {"type": self.type}
        if self.required:
            result["required"] = self.required
        if self.default is not None:
            result["default"] = self.default
        if self.description is not None:
            result["description"] = self.description
        if self.values is not None:
            result["values"] = self.values
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParameterSpec:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            type=data["type"],
            required=data.get("required", False),
            default=data.get("default"),
            description=data.get("description"),
            values=data.get("values"),
        )


@dataclass
class ThrottleConfig:
    """Per-state tool-call progressive throttling configuration.

    Counts successful tool calls within a single state visit and escalates
    restrictions to self-throttle runaway states before provider limits are reached.

    Thresholds fall back to executor module defaults when not set:
      - normal_max: _DEFAULT_THROTTLE_NORMAL_MAX (3) — calls 1..normal_max pass through
      - warn_max: _DEFAULT_THROTTLE_WARN_MAX (8) — calls at warn_max inject a warning event
      - hard_max: _DEFAULT_THROTTLE_HARD_MAX (12) — calls at hard_max route to on_throttle_hard
      - calls > hard_max: hard stop, loop marked stuck

    States with type="learning" (FEAT-1283) are exempt from the hard_max hard-stop because
    they legitimately make N tool calls per visit (one per unproven target). The warn_max
    warning still applies so users can see the state is doing significant work.
    """

    normal_max: int | None = None
    warn_max: int | None = None
    hard_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}
        if self.normal_max is not None:
            result["normal_max"] = self.normal_max
        if self.warn_max is not None:
            result["warn_max"] = self.warn_max
        if self.hard_max is not None:
            result["hard_max"] = self.hard_max
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThrottleConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            normal_max=data.get("normal_max"),
            warn_max=data.get("warn_max"),
            hard_max=data.get("hard_max"),
        )


@dataclass
class LearningConfig:
    """Per-state configuration for FEAT-1283 `type: learning` dispatch.

    Declares the list of external-API/SDK targets a learning state must prove
    against the learning-tests registry (ENH-1282) before advancing. On a
    missing or stale record, the state invokes `/ll:explore-api <target>` up to
    `max_retries` times before transitioning to a blocked target.

    Attributes:
        targets: Ordered list of target identifiers (e.g. "Anthropic SDK
            streaming"). Each is slugified internally when looking up the
            registry record. All targets must reach status="proven" for the
            state to advance via on_yes.
        targets_csv: Runtime-interpolated comma-separated target string (e.g.
            "${context.targets}"). Resolved and CSV-split by the executor at
            execution time. Alternative to the static ``targets`` list for loops
            that receive targets as a context CSV string. Exactly one of
            ``targets`` (non-empty) or ``targets_csv`` must be set.
        max_retries: Maximum number of `/ll:explore-api` invocations per target
            before the state routes to on_blocked / on_no with reason
            ``retries_exhausted``. Counts only re-exploration attempts; the
            initial registry lookup is free. Distinct from ENH-1115's throttle
            counter, which measures tool-call volume; learning states are
            already exempt from throttle hard_max via FSMExecutor._check_throttle.
        max_retries_expr: Runtime-interpolated retry limit (e.g.
            "${context.max_retries}"). Resolved via interpolate() and int()-cast
            at execution time. Takes precedence over ``max_retries`` when set.
    """

    targets: list[str] = field(default_factory=list)
    targets_csv: str | None = None
    max_retries: int = 2
    max_retries_expr: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {"targets": list(self.targets), "max_retries": self.max_retries}
        if self.targets_csv is not None:
            result["targets_csv"] = self.targets_csv
        if self.max_retries_expr is not None:
            result["max_retries_expr"] = self.max_retries_expr
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            targets=list(data.get("targets") or []),
            targets_csv=data.get("targets_csv") or None,
            max_retries=int(data.get("max_retries", 2)),
            max_retries_expr=data.get("max_retries_expr") or None,
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
        max_rate_limit_retries: Max consecutive 429/rate-limit in-place retries for this
            state before transitioning to on_rate_limit_exhausted. Requires
            on_rate_limit_exhausted to also be set.
        on_rate_limit_exhausted: State to transition to when max_rate_limit_retries
            consecutive rate-limit retries are exceeded. Required when
            max_rate_limit_retries is set.
        rate_limit_backoff_base_seconds: Base seconds for exponential backoff between
            rate-limit retries; actual sleep is base * 2^(attempt-1) + uniform(0, base).
            Defaults to 30.
        rate_limit_max_wait_seconds: Total wall-clock budget (seconds) for rate-limit
            handling in this state before routing to on_rate_limit_exhausted. When unset,
            defaults from commands.rate_limits.max_wait_seconds (21600 = 6h).
        rate_limit_long_wait_ladder: Backoff ladder (seconds) for the long-wait tier used
            once the short-tier retry budget is spent. Each entry is the sleep before the
            next retry attempt. When unset, defaults from
            commands.rate_limits.long_wait_ladder ([300, 900, 1800, 3600]).
        loop: Name of a loop YAML to execute as a sub-FSM. Mutually exclusive with action.
        context_passthrough: When True, pass parent context variables to child loop and
            merge child captures back into parent context. Legacy escape hatch; prefer
            'with_' for explicit named bindings.
        with_: Explicit parameter bindings for sub-loop calls (YAML key: 'with'). Maps
            declared child parameter names to parent expressions. Only valid when 'loop'
            is set. Mutually exclusive with context_passthrough.
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
    append_to_messages: str | None = None
    timeout: int | None = None
    on_maintain: str | None = None
    max_retries: int | None = None
    on_retry_exhausted: str | None = None
    retryable_exit_codes: list[int] | None = None
    max_rate_limit_retries: int | None = None
    on_rate_limit_exhausted: str | None = None
    rate_limit_backoff_base_seconds: int | None = None
    rate_limit_max_wait_seconds: int | None = None
    rate_limit_long_wait_ladder: list[int] | None = None
    loop: str | None = None
    context_passthrough: bool = False
    with_: dict[str, Any] = field(default_factory=dict)
    agent: str | None = None
    tools: list[str] | None = None
    extra_routes: dict[str, str] = field(default_factory=dict)
    type: str | None = None
    throttle: ThrottleConfig | None = None
    on_throttle_hard: str | None = None
    learning: LearningConfig | None = None

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
        if self.append_to_messages is not None:
            result["append_to_messages"] = self.append_to_messages
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.on_maintain is not None:
            result["on_maintain"] = self.on_maintain
        if self.max_retries is not None:
            result["max_retries"] = self.max_retries
        if self.on_retry_exhausted is not None:
            result["on_retry_exhausted"] = self.on_retry_exhausted
        if self.retryable_exit_codes is not None:
            result["retryable_exit_codes"] = self.retryable_exit_codes
        if self.max_rate_limit_retries is not None:
            result["max_rate_limit_retries"] = self.max_rate_limit_retries
        if self.on_rate_limit_exhausted is not None:
            result["on_rate_limit_exhausted"] = self.on_rate_limit_exhausted
        if self.rate_limit_backoff_base_seconds is not None:
            result["rate_limit_backoff_base_seconds"] = self.rate_limit_backoff_base_seconds
        if self.rate_limit_max_wait_seconds is not None:
            result["rate_limit_max_wait_seconds"] = self.rate_limit_max_wait_seconds
        if self.rate_limit_long_wait_ladder is not None:
            result["rate_limit_long_wait_ladder"] = self.rate_limit_long_wait_ladder
        if self.loop is not None:
            result["loop"] = self.loop
        if self.context_passthrough:
            result["context_passthrough"] = self.context_passthrough
        if self.with_:
            result["with"] = self.with_
        if self.agent is not None:
            result["agent"] = self.agent
        if self.tools is not None:
            result["tools"] = self.tools
        for verdict, target in self.extra_routes.items():
            result[f"on_{verdict}"] = target
        if self.type is not None:
            result["type"] = self.type
        if self.throttle is not None:
            result["throttle"] = self.throttle.to_dict()
        if self.on_throttle_hard is not None:
            result["on_throttle_hard"] = self.on_throttle_hard
        if self.learning is not None:
            result["learning"] = self.learning.to_dict()

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

        throttle = None
        if "throttle" in data:
            throttle = ThrottleConfig.from_dict(data["throttle"])

        learning = None
        if "learning" in data:
            learning = LearningConfig.from_dict(data["learning"])

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
            "on_rate_limit_exhausted",
            "on_throttle_hard",
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
            append_to_messages=data.get("append_to_messages"),
            timeout=data.get("timeout"),
            on_maintain=data.get("on_maintain"),
            max_retries=data.get("max_retries"),
            on_retry_exhausted=data.get("on_retry_exhausted"),
            retryable_exit_codes=data.get("retryable_exit_codes"),
            max_rate_limit_retries=data.get("max_rate_limit_retries"),
            on_rate_limit_exhausted=data.get("on_rate_limit_exhausted"),
            rate_limit_backoff_base_seconds=data.get("rate_limit_backoff_base_seconds"),
            rate_limit_max_wait_seconds=data.get("rate_limit_max_wait_seconds"),
            rate_limit_long_wait_ladder=data.get("rate_limit_long_wait_ladder"),
            loop=data.get("loop"),
            context_passthrough=data.get("context_passthrough", False),
            with_=data.get("with", {}),
            agent=data.get("agent"),
            tools=data.get("tools"),
            extra_routes=extra_routes,
            type=data.get("type"),
            throttle=throttle,
            on_throttle_hard=data.get("on_throttle_hard"),
            learning=learning,
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
        if self.on_rate_limit_exhausted is not None:
            refs.add(self.on_rate_limit_exhausted)
        if self.on_throttle_hard is not None:
            refs.add(self.on_throttle_hard)
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
class CommandEntry:
    """A single command entry for the loop's Commands display section.

    Attributes:
        cmd: Full command string to display (e.g., "ll-loop run my-loop --param x=1")
        comment: Short description shown as a comment (e.g., "run with parameter x")
    """

    cmd: str
    comment: str


@dataclass
class TargetStateSpec:
    """Per-state targeting specification for harness-optimize APO (ENH-1552).

    Names a single FSM state inside a target loop file and associates it with
    the examples file and eval fragment used during that state's optimization.

    Attributes:
        name: State name within the target loop
        examples_file: Path to the examples YAML file for this state
        eval_fragment: Eval fragment identifier used during optimization
    """

    name: str
    examples_file: str
    eval_fragment: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            "name": self.name,
            "examples_file": self.examples_file,
            "eval": self.eval_fragment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetStateSpec:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            name=data["name"],
            examples_file=data["examples_file"],
            eval_fragment=data["eval"],
        )


@dataclass
class TargetFileSpec:
    """Per-file targeting specification for harness-optimize APO (ENH-1552).

    Associates a loop YAML file (or glob pattern) with the list of states
    to optimize within that file.

    Attributes:
        file: Explicit path to a loop YAML file (mutually exclusive with glob)
        glob: Glob pattern matching one or more loop YAML files
        states: States within the matched file(s) to target
    """

    file: str | None = None
    glob: str | None = None
    states: list[TargetStateSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        result: dict[str, Any] = {}
        if self.file is not None:
            result["file"] = self.file
        if self.glob is not None:
            result["glob"] = self.glob
        if self.states:
            result["states"] = [s.to_dict() for s in self.states]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetFileSpec:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            file=data.get("file"),
            glob=data.get("glob"),
            states=[TargetStateSpec.from_dict(s) for s in (data.get("states") or [])],
        )


@dataclass
class RepeatedFailureConfig:
    """Configuration for the FSM stall detector (FEAT-1637).

    When N consecutive iterations produce an identical
    `(state_name, exit_code, eval_verdict)` triple, the FSM either
    aborts the run or routes to a configured recovery state.

    Attributes:
        window: Consecutive iterations with identical triple required to
            fire (default 3).
        on_repeated_failure: Either the literal ``"abort"`` (terminate
            with ``terminated_by="stall_detected"``) or the name of a
            declared state to route to.
    """

    window: int = 3
    on_repeated_failure: str = "abort"
    progress_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization (skip-if-default)."""
        result: dict[str, Any] = {}
        if self.window != 3:
            result["window"] = self.window
        if self.on_repeated_failure != "abort":
            result["on_repeated_failure"] = self.on_repeated_failure
        if self.progress_paths:
            result["progress_paths"] = self.progress_paths
        if self.exclude_paths:
            result["exclude_paths"] = self.exclude_paths
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepeatedFailureConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            window=data.get("window", 3),
            on_repeated_failure=data.get("on_repeated_failure", "abort"),
            progress_paths=data.get("progress_paths", []),
            exclude_paths=data.get("exclude_paths", []),
        )


@dataclass
class CircuitConfig:
    """Top-level ``circuit:`` block grouping loop-level safety knobs.

    Currently exposes ``repeated_failure`` (the stall detector). Future
    safety knobs (e.g. global timeouts, panic-stop guards) should be
    added here rather than as separate top-level keys.

    Attributes:
        repeated_failure: Stall-detector configuration, or None to disable.
    """

    repeated_failure: RepeatedFailureConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization (skip-if-None)."""
        result: dict[str, Any] = {}
        if self.repeated_failure is not None:
            rf_dict = self.repeated_failure.to_dict()
            # Always emit the key when configured (even if all fields are defaults)
            # so the round-trip preserves "repeated_failure was set" intent.
            result["repeated_failure"] = rf_dict
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        rf = None
        if "repeated_failure" in data and data["repeated_failure"] is not None:
            rf = RepeatedFailureConfig.from_dict(data["repeated_failure"])
        return cls(repeated_failure=rf)


@dataclass
class FSMLoop:
    """Complete FSM loop definition.

    The main dataclass representing a loop configuration.

    Attributes:
        name: Unique loop identifier
        initial: Starting state name
        states: Mapping from state name to StateConfig
        context: User-defined shared variables
        scope: Paths this loop operates on (for concurrency control). Supports ${context.<var>} template variables that are resolved at runtime.
        max_iterations: Safety limit for loop iterations
        backoff: Seconds between iterations
        timeout: Max total runtime in seconds (loop-level)
        maintain: If True, restart after completion
        llm: LLM evaluation configuration
        on_handoff: Behavior when handoff signal detected (pause/spawn/terminate)
        commands: Optional override for the Commands section in ll-loop show
    """

    name: str
    initial: str
    states: dict[str, StateConfig]
    description: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, ParameterSpec] = field(default_factory=dict)
    scope: list[str] = field(default_factory=list)
    max_iterations: int = 50
    on_max_iterations: str | None = None
    max_edge_revisits: int = 100
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
    commands: list[CommandEntry] = field(default_factory=list)
    targets: list[TargetFileSpec] = field(default_factory=list)
    circuit: CircuitConfig | None = None
    meta_self_eval_ok: bool = False
    shared_state_ok: bool = False
    # Populated from the raw `import:` list by from_dict(); not serialized by to_dict()
    imports: list[str] = field(default_factory=list)

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
        if self.parameters:
            result["parameters"] = {name: spec.to_dict() for name, spec in self.parameters.items()}
        if self.scope:
            result["scope"] = self.scope
        if self.max_iterations != 50:
            result["max_iterations"] = self.max_iterations
        if self.max_edge_revisits != 100:
            result["max_edge_revisits"] = self.max_edge_revisits
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
        if self.on_max_iterations is not None:
            result["on_max_iterations"] = self.on_max_iterations
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
        if self.commands:
            result["commands"] = [{"cmd": e.cmd, "comment": e.comment} for e in self.commands]
        if self.targets:
            result["targets"] = [t.to_dict() for t in self.targets]

        if self.circuit is not None:
            circuit_dict = self.circuit.to_dict()
            if circuit_dict:
                result["circuit"] = circuit_dict

        if self.meta_self_eval_ok:
            result["meta_self_eval_ok"] = self.meta_self_eval_ok
        if self.shared_state_ok:
            result["shared_state_ok"] = self.shared_state_ok

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

        circuit = None
        if "circuit" in data and data["circuit"] is not None:
            circuit = CircuitConfig.from_dict(data["circuit"])

        parameters = {
            name: ParameterSpec.from_dict(spec) for name, spec in data.get("parameters", {}).items()
        }

        return cls(
            name=data["name"],
            initial=data["initial"],
            states=states,
            description=data.get("description"),
            context=data.get("context", {}),
            parameters=parameters,
            scope=data.get("scope", []),
            max_iterations=data.get("max_iterations", 50),
            on_max_iterations=data.get("on_max_iterations"),
            max_edge_revisits=data.get("max_edge_revisits", 100),
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
            commands=[CommandEntry(**e) for e in data.get("commands", [])],
            targets=[TargetFileSpec.from_dict(t) for t in (data.get("targets") or [])],
            circuit=circuit,
            meta_self_eval_ok=data.get("meta_self_eval_ok", False),
            shared_state_ok=data.get("shared_state_ok", False),
            imports=data.get("import", []),
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
        if self.on_max_iterations is not None:
            refs.add(self.on_max_iterations)
        return refs
