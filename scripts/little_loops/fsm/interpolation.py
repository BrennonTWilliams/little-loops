"""Variable interpolation for FSM loop definitions.

This module provides runtime variable substitution using ${namespace.path}
syntax. Variables are resolved against an InterpolationContext that holds
runtime state including user context, captured values, and metadata.

Supported namespaces:
    context: User-defined variables from FSM context block
    captured: Values stored via capture: in previous states
    prev: Previous state's result (shorthand)
    result: Current evaluation result
    state: Current state metadata (name, iteration)
    loop: Loop-level metadata (name, started_at, elapsed_ms, elapsed)
    env: Environment variables
    messages: Shared append-only message log (${messages}, ${messages.last(N)}, ${messages.summary})
    param: Per-state parameter bindings for fragment references
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

# Pre-compiled patterns for performance
VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")
ESCAPED_PATTERN = re.compile(r"\$\$\{")
ESCAPED_PLACEHOLDER = "\x00ESCAPED\x00"


class InterpolationError(Exception):
    """Raised when variable interpolation fails."""

    pass


@dataclass
class InterpolationContext:
    """Runtime context for variable resolution.

    Holds all namespace data needed to resolve ${namespace.path} variables
    during FSM execution.

    Attributes:
        context: User-defined variables from FSM context block
        captured: Stored action results {varname: {output, stderr, exit_code,
            duration_ms, timeout_kind}} (FEAT-3033: timeout_kind is "idle",
            "wall", or None — access with :default= since older checkpoints
            lack the key)
        prev: Previous state result or None if first state (FEAT-3033: also
            carries "timeout_kind" — access via
            ${prev.timeout_kind:default=} since pre-change checkpoints lack
            the key)
        result: Current evaluation result or None
        state_name: Current state name
        iteration: Current loop iteration (1-based)
        loop_name: FSM loop name
        started_at: ISO timestamp when loop started
        elapsed_ms: Milliseconds since loop started
        param: Per-state parameter bindings for fragment references (resolved from fragment_bindings)
    """

    context: dict[str, Any] = field(default_factory=dict)
    captured: dict[str, dict[str, Any]] = field(default_factory=dict)
    prev: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    state_name: str = ""
    iteration: int = 1
    loop_name: str = ""
    started_at: str = ""
    elapsed_ms: int = 0
    messages: list[str] = field(default_factory=list)
    messages_summary: str = ""
    param: dict[str, Any] = field(default_factory=dict)

    def resolve(self, namespace: str, path: str) -> Any:
        """Resolve a namespace.path reference to its value.

        Args:
            namespace: The namespace identifier (context, captured, etc.)
            path: The dot-separated path within the namespace

        Returns:
            The resolved value

        Raises:
            InterpolationError: If namespace unknown or path not found
        """
        if namespace == "context":
            return self._get_nested(self.context, path, "context")
        elif namespace == "captured":
            return self._get_nested(self.captured, path, "captured")
        elif namespace == "prev":
            if self.prev is None:
                raise InterpolationError("No previous state result available")
            return self._get_nested(self.prev, path, "prev")
        elif namespace == "result":
            if self.result is None:
                raise InterpolationError("No evaluation result available")
            return self._get_nested(self.result, path, "result")
        elif namespace == "state":
            return self._get_state_value(path)
        elif namespace == "loop":
            return self._get_loop_value(path)
        elif namespace == "env":
            value = os.environ.get(path)
            if value is None:
                raise InterpolationError(f"Environment variable '{path}' not set")
            return value
        elif namespace == "messages":
            return self._get_messages_value(path)
        elif namespace == "param":
            return self._get_nested(self.param, path, "param")
        else:
            raise InterpolationError(f"Unknown namespace: {namespace}")

    def _get_nested(self, obj: dict[str, Any], path: str, namespace: str) -> Any:
        """Get nested value from dict using dot notation.

        Args:
            obj: Dictionary to traverse
            path: Dot-separated path (e.g., "errors.output")
            namespace: Namespace name for error messages

        Returns:
            The value at the path

        Raises:
            InterpolationError: If path not found
        """
        parts = path.split(".")
        current: Any = obj
        for i, part in enumerate(parts):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                traversed = ".".join(parts[: i + 1])
                raise InterpolationError(f"Path '{traversed}' not found in {namespace}")
        return current

    def _get_state_value(self, key: str) -> Any:
        """Get state metadata value.

        Args:
            key: State property name (name or iteration)

        Returns:
            The state property value

        Raises:
            InterpolationError: If key unknown
        """
        if key == "name":
            return self.state_name
        elif key == "iteration":
            return self.iteration
        else:
            raise InterpolationError(f"Unknown state property: {key}")

    def _get_messages_value(self, path: str) -> str:
        """Get value from the shared messages log.

        Args:
            path: Empty string or "output" for full log; "last(N)" for last N entries;
                  "summary" for the pre-computed summary string.

        Returns:
            The resolved messages string

        Raises:
            InterpolationError: If path is unrecognised
        """
        if not path or path == "output":
            return "\n".join(self.messages)
        m = re.match(r"^last\((\d+)\)$", path)
        if m:
            n = int(m.group(1))
            return "\n".join(self.messages[-n:])
        if path == "summary":
            return self.messages_summary
        raise InterpolationError(f"Unknown messages property: {path!r}")

    def _get_loop_value(self, key: str) -> Any:
        """Get loop metadata value.

        Args:
            key: Loop property name

        Returns:
            The loop property value

        Raises:
            InterpolationError: If key unknown
        """
        if key == "name":
            return self.loop_name
        elif key == "started_at":
            return self.started_at
        elif key == "elapsed_ms":
            return self.elapsed_ms
        elif key == "elapsed":
            return _format_duration(self.elapsed_ms)
        else:
            raise InterpolationError(f"Unknown loop property: {key}")


def parse_interpolation_suffixes(full_path: str) -> tuple[str, str | None, bool, bool]:
    """Parse the ``:default=``, ``?``, and ``:shell`` suffix chain off a raw
    ``${...}`` path, order-independently.

    ``:shell`` is recognized in exactly two positions: immediately before
    ``:default=`` (``...:shell:default=value``), or at the very end of the
    chain — alone (``...:shell``), after a default value
    (``...:default=value:shell``), or after ``?`` (``...?:shell``). A
    ``:shell`` embedded inside a default's literal text (not at one of these
    boundaries) is left untouched. The one genuine ambiguity —
    ``${x:default=v:shell}``, where ``:shell`` could be read as a literal
    suffix of the default text ``"v:shell"`` instead — is resolved in favor
    of treating it as the suffix.

    Args:
        full_path: The captured ``namespace.path`` plus suffix chain, with
            the outer ``${`` / ``}`` already stripped.

    Returns:
        ``(var_path, default_value, nullable, shell_quote)`` — ``var_path``
        is the bare ``namespace.path`` with all suffixes removed;
        ``default_value`` is the literal fallback text or ``None``;
        ``nullable`` is whether a trailing ``?`` was present; ``shell_quote``
        is whether ``:shell`` was present.

    Raises:
        InterpolationError: ``?`` and ``:default=`` are both present, or a
            ``:default=`` value contains ``{`` — a literal ``}`` in a default
            cannot be represented (``VARIABLE_PATTERN`` stops at the first
            unescaped ``}``), so it is rejected rather than silently
            truncated.
    """
    default_value: str | None = None
    nullable = False
    shell_quote = False

    if ":shell:default=" in full_path:
        full_path = full_path.replace(":shell:default=", ":default=", 1)
        shell_quote = True
    elif full_path.endswith(":shell?"):
        full_path = full_path[: -len(":shell?")] + "?"
        shell_quote = True
    elif full_path.endswith(":shell"):
        full_path = full_path[: -len(":shell")]
        shell_quote = True

    if ":default=" in full_path:
        var_part, default_value = full_path.split(":default=", 1)
        if var_part.endswith("?"):
            raise InterpolationError(
                f"Ambiguous suffix: ${{{full_path}}} (:default=... and ? are mutually exclusive)"
            )
        if "{" in default_value:
            raise InterpolationError(
                f"':default=' value must not contain '{{' or '}}' "
                f"(the interpolation pattern stops at the first '}}'): ${{{full_path}}}"
            )
        full_path = var_part
    elif full_path.endswith("?"):
        nullable = True
        full_path = full_path[:-1]

    return full_path, default_value, nullable, shell_quote


def interpolate(template: str, ctx: InterpolationContext) -> str:
    """Replace ${namespace.path} variables in template string.

    Resolves variables at runtime against the provided context.
    Handles $${...} escaping (becomes literal ${...}).
    Supports ``:default=value``, ``?`` (nullable), and ``:shell``
    (``shlex.quote()`` the resolved value, for safe use in a bash token
    position) suffixes, composable in any order (see
    ``parse_interpolation_suffixes``). ``?`` and ``:default=`` remain
    mutually exclusive. Evaluation order is resolve → apply fallback →
    ``shlex.quote()`` — the fallback is quoted too when ``:shell`` is
    present, and a resolved ``None`` becomes ``""`` before quoting (so
    ``${x:shell}`` on a ``None`` value emits ``''``, a valid empty token,
    not nothing). ``:default=`` does not fire on a resolved ``None`` — only
    on a missing path.

    Args:
        template: String containing variable references
        ctx: Runtime context for resolution

    Returns:
        String with all variables resolved

    Raises:
        InterpolationError: If variable format invalid or value not found
    """
    # Replace escaped sequences with placeholder
    result = ESCAPED_PATTERN.sub(ESCAPED_PLACEHOLDER, template)

    def replace_var(match: re.Match[str]) -> str:
        full_path = match.group(1)

        # Parse optional fallback suffixes
        #   ${namespace.path:default=value} → use "value" on missing path
        #   ${namespace.path?}              → use "" on missing path
        #   ${namespace.path:shell}         → shlex.quote() the resolved value
        full_path, default_value, nullable, shell_quote = parse_interpolation_suffixes(full_path)

        if full_path == "messages":
            # Bare ${messages} is shorthand for the full message log
            namespace, path = "messages", ""
        elif "." not in full_path:
            raise InterpolationError(
                f"Invalid variable: ${{{full_path}}} (expected namespace.path)"
            )
        else:
            namespace, path = full_path.split(".", 1)

        try:
            value = ctx.resolve(namespace, path)
        except InterpolationError:
            if default_value is not None:
                return shlex.quote(default_value) if shell_quote else default_value
            if nullable:
                return shlex.quote("") if shell_quote else ""
            raise
        if value is None:
            value = ""
        if shell_quote:
            return shlex.quote(str(value))
        return str(value)

    result = VARIABLE_PATTERN.sub(replace_var, result)

    # Restore escaped sequences as literal ${
    result = result.replace(ESCAPED_PLACEHOLDER, "${")

    return result


def interpolate_dict(obj: dict[str, Any], ctx: InterpolationContext) -> dict[str, Any]:
    """Recursively interpolate all string values in a dict.

    Only string values are interpolated. Non-string values (int, float,
    bool, None) are passed through unchanged. Nested dicts and lists
    are recursively processed.

    Args:
        obj: Dictionary to process
        ctx: Runtime context for resolution

    Returns:
        New dictionary with interpolated string values

    Raises:
        InterpolationError: If any variable resolution fails
    """
    result: dict[str, Any] = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = interpolate(value, ctx)
        elif isinstance(value, dict):
            result[key] = interpolate_dict(value, ctx)
        elif isinstance(value, list):
            result[key] = _interpolate_list(value, ctx)
        else:
            result[key] = value
    return result


def _interpolate_list(items: list[Any], ctx: InterpolationContext) -> list[Any]:
    """Interpolate string values in a list.

    Args:
        items: List to process
        ctx: Runtime context for resolution

    Returns:
        New list with interpolated string values
    """
    result: list[Any] = []
    for item in items:
        if isinstance(item, str):
            result.append(interpolate(item, ctx))
        elif isinstance(item, dict):
            result.append(interpolate_dict(item, ctx))
        elif isinstance(item, list):
            result.append(_interpolate_list(item, ctx))
        else:
            result.append(item)
    return result


def _format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration.

    Args:
        ms: Duration in milliseconds

    Returns:
        Formatted string like "500ms", "30s", or "2m 15s"
    """
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if remaining_seconds == 0:
        return f"{minutes}m"
    return f"{minutes}m {remaining_seconds}s"
