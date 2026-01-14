# FEAT-042: Variable Interpolation System - Implementation Plan

## Issue Reference
- **File**: .issues/features/P1-FEAT-042-variable-interpolation-system.md
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The FSM system (FEAT-040, FEAT-041) already generates interpolation strings like `${context.metric_cmd}` and `${prev.output}` in compiled state configurations. These strings are stored as-is in the FSM schema and need runtime resolution.

### Key Discoveries
- FSM schema already supports interpolation strings in `EvaluateConfig` fields (schema.py:61, 69-70)
- Paradigm compilers generate interpolation strings: `scripts/little_loops/fsm/compilers.py:218-224`
- Validation already bypasses numeric validation for interpolation strings: `scripts/little_loops/fsm/validation.py:119-124`
- The `context` dict is stored at FSM level for runtime resolution: `scripts/little_loops/fsm/schema.py:348`

## Desired End State

A complete interpolation module that:
1. Resolves `${namespace.path}` variables at runtime
2. Supports 7 namespaces: context, captured, prev, result, state, loop, env
3. Handles escaping (`$${...}` → literal `${...}`)
4. Provides clear errors for undefined variables
5. Integrates with the FSM executor (FEAT-045)

### How to Verify
- All unit tests pass
- `${context.x}` resolves from user-defined context
- `${captured.varname.output}` resolves nested paths
- `${env.HOME}` reads environment variables
- `$${literal}` produces `${literal}`
- Undefined variables raise `InterpolationError`

## What We're NOT Doing

- Not implementing nested interpolation (resolving variables that contain variables)
- Not implementing runtime context mutation
- Not integrating with executor (deferred to FEAT-045)
- Not adding interpolation validation during schema loading

## Problem Analysis

The FSM system needs runtime variable substitution to enable:
- Parameterized actions via `${context.*}`
- Chained states via `${captured.*}` and `${prev.*}`
- Dynamic evaluation via `${result.*}`
- Runtime metadata via `${state.*}`, `${loop.*}`, `${env.*}`

## Solution Approach

Create `scripts/little_loops/fsm/interpolation.py` following the implementation spec in the issue file, with adjustments based on codebase patterns:
- Use pre-compiled regex patterns (like `output_parsing.py`)
- Use dataclass pattern from existing schema modules
- Follow existing test patterns from `test_fsm_schema.py`

## Implementation Phases

### Phase 1: Create Core Interpolation Module

#### Overview
Implement the `interpolation.py` module with all namespace resolution logic.

#### Changes Required

**File**: `scripts/little_loops/fsm/interpolation.py`
**Changes**: Create new file with complete interpolation implementation

```python
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
VARIABLE_PATTERN = re.compile(r'\$\{([^}]+)\}')
ESCAPED_PATTERN = re.compile(r'\$\$\{')
ESCAPED_PLACEHOLDER = '\x00ESCAPED\x00'


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
                traversed = ".".join(parts[:i + 1])
                raise InterpolationError(
                    f"Path '{traversed}' not found in {namespace}"
                )
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
    result = result.replace(ESCAPED_PLACEHOLDER, '${')

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
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and has no syntax errors: `python -c "from little_loops.fsm.interpolation import interpolate"`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/interpolation.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/interpolation.py`

---

### Phase 2: Update Module Exports

#### Overview
Export the interpolation components from the FSM module.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add interpolation exports

```python
# Add to imports
from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
    interpolate_dict,
)

# Add to __all__
__all__ = [
    # ... existing exports ...
    "InterpolationContext",
    "InterpolationError",
    "interpolate",
    "interpolate_dict",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Imports work: `python -c "from little_loops.fsm import interpolate, InterpolationContext"`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/__init__.py`

---

### Phase 3: Write Unit Tests

#### Overview
Create comprehensive tests for all interpolation functionality.

#### Changes Required

**File**: `scripts/tests/test_fsm_interpolation.py`
**Changes**: Create new test file

```python
"""Unit tests for FSM variable interpolation."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
    interpolate_dict,
    _format_duration,
)


class TestInterpolationContext:
    """Tests for InterpolationContext creation and resolution."""

    def test_default_values(self) -> None:
        """Context has sensible defaults."""
        ctx = InterpolationContext()
        assert ctx.context == {}
        assert ctx.captured == {}
        assert ctx.prev is None
        assert ctx.result is None
        assert ctx.state_name == ""
        assert ctx.iteration == 1

    def test_context_variable(self) -> None:
        """${context.target_dir} resolves from context dict."""
        ctx = InterpolationContext(context={"target_dir": "src/"})
        value = ctx.resolve("context", "target_dir")
        assert value == "src/"

    def test_context_nested(self) -> None:
        """${context.db.host} resolves nested path."""
        ctx = InterpolationContext(
            context={"db": {"host": "localhost", "port": 5432}}
        )
        assert ctx.resolve("context", "db.host") == "localhost"
        assert ctx.resolve("context", "db.port") == 5432

    def test_captured_variable(self) -> None:
        """${captured.errors.output} resolves stored action result."""
        ctx = InterpolationContext(
            captured={
                "errors": {
                    "output": "3 errors found",
                    "exit_code": 1,
                    "duration_ms": 500,
                }
            }
        )
        assert ctx.resolve("captured", "errors.output") == "3 errors found"
        assert ctx.resolve("captured", "errors.exit_code") == 1

    def test_prev_shorthand(self) -> None:
        """${prev.output} resolves previous state result."""
        ctx = InterpolationContext(
            prev={"output": "previous output", "exit_code": 0, "state": "check"}
        )
        assert ctx.resolve("prev", "output") == "previous output"
        assert ctx.resolve("prev", "state") == "check"

    def test_prev_unavailable_raises(self) -> None:
        """Accessing prev when None raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="No previous state result"):
            ctx.resolve("prev", "output")

    def test_result_variable(self) -> None:
        """${result.verdict} resolves evaluation result."""
        ctx = InterpolationContext(
            result={"verdict": "success", "confidence": 0.95}
        )
        assert ctx.resolve("result", "verdict") == "success"
        assert ctx.resolve("result", "confidence") == 0.95

    def test_result_unavailable_raises(self) -> None:
        """Accessing result when None raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="No evaluation result"):
            ctx.resolve("result", "verdict")

    def test_state_name(self) -> None:
        """${state.name} returns current state name."""
        ctx = InterpolationContext(state_name="checking")
        assert ctx.resolve("state", "name") == "checking"

    def test_state_iteration(self) -> None:
        """${state.iteration} returns current iteration."""
        ctx = InterpolationContext(iteration=5)
        assert ctx.resolve("state", "iteration") == 5

    def test_state_unknown_property(self) -> None:
        """Unknown state property raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown state property"):
            ctx.resolve("state", "unknown")

    def test_loop_name(self) -> None:
        """${loop.name} returns loop name."""
        ctx = InterpolationContext(loop_name="fix-types")
        assert ctx.resolve("loop", "name") == "fix-types"

    def test_loop_started_at(self) -> None:
        """${loop.started_at} returns start timestamp."""
        ctx = InterpolationContext(started_at="2026-01-13T10:30:00Z")
        assert ctx.resolve("loop", "started_at") == "2026-01-13T10:30:00Z"

    def test_loop_elapsed_ms(self) -> None:
        """${loop.elapsed_ms} returns raw milliseconds."""
        ctx = InterpolationContext(elapsed_ms=45000)
        assert ctx.resolve("loop", "elapsed_ms") == 45000

    def test_loop_elapsed_formatted(self) -> None:
        """${loop.elapsed} returns formatted duration."""
        ctx = InterpolationContext(elapsed_ms=125000)
        assert ctx.resolve("loop", "elapsed") == "2m 5s"

    def test_loop_unknown_property(self) -> None:
        """Unknown loop property raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown loop property"):
            ctx.resolve("loop", "unknown")

    def test_env_variable(self) -> None:
        """${env.HOME} resolves from environment."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert ctx.resolve("env", "TEST_VAR") == "test_value"

    def test_env_missing_raises(self) -> None:
        """Missing environment variable raises InterpolationError."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(InterpolationError, match="not set"):
                ctx.resolve("env", "NONEXISTENT_VAR_12345")

    def test_unknown_namespace_raises(self) -> None:
        """Unknown namespace raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown namespace"):
            ctx.resolve("unknown", "path")

    def test_path_not_found_raises(self) -> None:
        """Missing path raises InterpolationError."""
        ctx = InterpolationContext(context={"a": {"b": 1}})
        with pytest.raises(InterpolationError, match="Path 'a.c' not found"):
            ctx.resolve("context", "a.c")


class TestInterpolate:
    """Tests for the interpolate function."""

    def test_simple_variable(self) -> None:
        """Single variable resolves correctly."""
        ctx = InterpolationContext(context={"name": "test"})
        result = interpolate("Hello ${context.name}!", ctx)
        assert result == "Hello test!"

    def test_multiple_variables(self) -> None:
        """Multiple variables in one string all resolve."""
        ctx = InterpolationContext(
            context={"cmd": "mypy", "target": "src/"}
        )
        result = interpolate("${context.cmd} ${context.target}", ctx)
        assert result == "mypy src/"

    def test_no_variables(self) -> None:
        """String without variables passes through unchanged."""
        ctx = InterpolationContext()
        result = interpolate("plain text", ctx)
        assert result == "plain text"

    def test_escape_sequence(self) -> None:
        """$${literal} becomes ${literal}."""
        ctx = InterpolationContext()
        result = interpolate("Use $${context.var} syntax", ctx)
        assert result == "Use ${context.var} syntax"

    def test_escape_with_real_variable(self) -> None:
        """Escaped and real variables work together."""
        ctx = InterpolationContext(context={"x": "value"})
        result = interpolate("Literal $${y} and real ${context.x}", ctx)
        assert result == "Literal ${y} and real value"

    def test_invalid_format_no_dot(self) -> None:
        """Variable without namespace.path raises error."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="expected namespace.path"):
            interpolate("${varname}", ctx)

    def test_numeric_value(self) -> None:
        """Numeric values convert to strings."""
        ctx = InterpolationContext(context={"count": 42})
        result = interpolate("Count: ${context.count}", ctx)
        assert result == "Count: 42"

    def test_empty_string_value(self) -> None:
        """Empty string values interpolate as empty."""
        ctx = InterpolationContext(context={"empty": ""})
        result = interpolate("Value: [${context.empty}]", ctx)
        assert result == "Value: []"

    def test_none_value(self) -> None:
        """None values interpolate as empty string."""
        ctx = InterpolationContext(context={"nothing": None})
        result = interpolate("Value: [${context.nothing}]", ctx)
        assert result == "Value: []"

    def test_deep_nested_path(self) -> None:
        """Deeply nested paths resolve correctly."""
        ctx = InterpolationContext(
            context={"a": {"b": {"c": {"d": "deep"}}}}
        )
        result = interpolate("${context.a.b.c.d}", ctx)
        assert result == "deep"


class TestInterpolateDict:
    """Tests for the interpolate_dict function."""

    def test_simple_dict(self) -> None:
        """String values in dict are interpolated."""
        ctx = InterpolationContext(context={"target": "src/"})
        obj = {"action": "mypy ${context.target}"}
        result = interpolate_dict(obj, ctx)
        assert result == {"action": "mypy src/"}

    def test_nested_dict(self) -> None:
        """Nested dicts are recursively processed."""
        ctx = InterpolationContext(context={"x": "value"})
        obj = {"outer": {"inner": "${context.x}"}}
        result = interpolate_dict(obj, ctx)
        assert result == {"outer": {"inner": "value"}}

    def test_list_values(self) -> None:
        """String values in lists are interpolated."""
        ctx = InterpolationContext(context={"a": "1", "b": "2"})
        obj = {"items": ["${context.a}", "${context.b}"]}
        result = interpolate_dict(obj, ctx)
        assert result == {"items": ["1", "2"]}

    def test_non_string_preserved(self) -> None:
        """Non-string values pass through unchanged."""
        ctx = InterpolationContext()
        obj = {"count": 5, "enabled": True, "ratio": 0.5}
        result = interpolate_dict(obj, ctx)
        assert result == {"count": 5, "enabled": True, "ratio": 0.5}

    def test_mixed_values(self) -> None:
        """Mixed value types handled correctly."""
        ctx = InterpolationContext(context={"name": "test"})
        obj = {
            "str_val": "${context.name}",
            "int_val": 42,
            "list_val": ["a", "${context.name}"],
            "dict_val": {"nested": "${context.name}"},
        }
        result = interpolate_dict(obj, ctx)
        assert result == {
            "str_val": "test",
            "int_val": 42,
            "list_val": ["a", "test"],
            "dict_val": {"nested": "test"},
        }

    def test_original_unchanged(self) -> None:
        """Original dict is not modified."""
        ctx = InterpolationContext(context={"x": "y"})
        obj = {"val": "${context.x}"}
        interpolate_dict(obj, ctx)
        assert obj == {"val": "${context.x}"}


class TestFormatDuration:
    """Tests for the _format_duration helper."""

    def test_milliseconds(self) -> None:
        """Sub-second durations show milliseconds."""
        assert _format_duration(0) == "0ms"
        assert _format_duration(500) == "500ms"
        assert _format_duration(999) == "999ms"

    def test_seconds(self) -> None:
        """1-59 seconds show just seconds."""
        assert _format_duration(1000) == "1s"
        assert _format_duration(30000) == "30s"
        assert _format_duration(59000) == "59s"

    def test_minutes(self) -> None:
        """60+ seconds show minutes and seconds."""
        assert _format_duration(60000) == "1m"
        assert _format_duration(90000) == "1m 30s"
        assert _format_duration(125000) == "2m 5s"
        assert _format_duration(3600000) == "60m"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_interpolation.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_interpolation.py`

---

### Phase 4: Run Full Verification

#### Overview
Run complete verification suite to ensure quality.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test each namespace resolution independently
- Test error conditions (missing values, invalid format)
- Test escaping mechanism
- Test nested path traversal
- Test type coercion (numbers to strings)

### Edge Cases
- Empty string values
- None values
- Deeply nested paths
- Multiple variables in one string
- Mixed escaped and real variables

## References

- Original issue: `.issues/features/P1-FEAT-042-variable-interpolation-system.md`
- FSM schema: `scripts/little_loops/fsm/schema.py`
- Paradigm compilers: `scripts/little_loops/fsm/compilers.py:209-224`
- Design doc: `docs/generalized-fsm-loop.md`
