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
"""

from __future__ import annotations

import os
import re
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
        captured: Stored action results {varname: {output, stderr, exit_code, duration_ms}}
        prev: Previous state result or None if first state
        result: Current evaluation result or None
        state_name: Current state name
        iteration: Current loop iteration (1-based)
        loop_name: FSM loop name
        started_at: ISO timestamp when loop started
        elapsed_ms: Milliseconds since loop started
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


def interpolate(template: str, ctx: InterpolationContext) -> str:
    """Replace ${namespace.path} variables in template string.

    Resolves variables at runtime against the provided context.
    Handles $${...} escaping (becomes literal ${...}).

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
        if "." not in full_path:
            raise InterpolationError(
                f"Invalid variable: ${{{full_path}}} (expected namespace.path)"
            )
        namespace, path = full_path.split(".", 1)
        value = ctx.resolve(namespace, path)
        # Convert to string, handling empty values
        if value is None:
            return ""
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
