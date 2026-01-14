# FEAT-042: Variable Interpolation System

## Summary

Implement the `${namespace.path}` variable interpolation system that allows FSM definitions to reference dynamic values at runtime.

## Priority

P1 - Required for convergence paradigm and captured values

## Dependencies

- FEAT-040: FSM Schema Definition and Validation

## Blocked By

- FEAT-040

## Description

Actions, evaluators, and routes can reference dynamic values using `${namespace.path}` syntax. This enables:

- Parameterized actions via `${context.*}`
- Chained states via `${captured.*}` and `${prev.*}`
- Evaluation result access via `${result.*}`
- Runtime metadata via `${state.*}`, `${loop.*}`, `${env.*}`

### Files to Create

```
scripts/little_loops/fsm/
└── interpolation.py
```

## Technical Details

### Namespace Definitions

| Namespace | Description | Lifetime |
|-----------|-------------|----------|
| `context` | User-defined variables from `context:` block | Entire loop |
| `captured` | Values stored via `capture:` in previous states | Entire loop |
| `prev` | Shorthand for previous state's result | Current state only |
| `result` | Current evaluation result | Current state only |
| `state` | Current execution metadata | Current state only |
| `loop` | Loop-level metadata | Entire loop |
| `env` | Environment variables | Entire loop |

### Implementation

```python
# interpolation.py
import os
import re
from dataclasses import dataclass
from typing import Any

VARIABLE_PATTERN = re.compile(r'\$\{([^}]+)\}')
ESCAPED_PATTERN = re.compile(r'\$\$\{')

@dataclass
class InterpolationContext:
    """Runtime context for variable resolution."""
    context: dict[str, Any]        # User-defined context
    captured: dict[str, dict]      # {varname: {output, stderr, exit_code, duration_ms}}
    prev: dict[str, Any] | None    # Previous state result
    result: dict[str, Any] | None  # Current evaluation result
    state_name: str
    iteration: int
    loop_name: str
    started_at: str
    elapsed_ms: int

    def resolve(self, namespace: str, path: str) -> Any:
        """Resolve a namespace.path reference."""
        if namespace == "context":
            return self._get_nested(self.context, path)
        elif namespace == "captured":
            return self._get_nested(self.captured, path)
        elif namespace == "prev":
            if self.prev is None:
                raise InterpolationError(f"No previous state result available")
            return self._get_nested(self.prev, path)
        elif namespace == "result":
            if self.result is None:
                raise InterpolationError(f"No evaluation result available")
            return self._get_nested(self.result, path)
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

    def _get_nested(self, obj: dict, path: str) -> Any:
        """Get nested value from dict using dot notation."""
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise InterpolationError(f"Path '{path}' not found")
        return current

    def _get_state_value(self, key: str) -> Any:
        if key == "name":
            return self.state_name
        elif key == "iteration":
            return self.iteration
        raise InterpolationError(f"Unknown state property: {key}")

    def _get_loop_value(self, key: str) -> Any:
        if key == "name":
            return self.loop_name
        elif key == "started_at":
            return self.started_at
        elif key == "elapsed_ms":
            return self.elapsed_ms
        elif key == "elapsed":
            return _format_duration(self.elapsed_ms)
        raise InterpolationError(f"Unknown loop property: {key}")


def interpolate(template: str, ctx: InterpolationContext) -> str:
    """
    Replace ${namespace.path} variables in template string.

    - Resolves variables at runtime
    - Raises InterpolationError for undefined variables
    - Handles $${...} escaping (becomes literal ${...})
    """
    # First, replace escaped sequences with placeholder
    result = ESCAPED_PATTERN.sub('\x00ESCAPED\x00', template)

    # Replace variables
    def replace_var(match: re.Match) -> str:
        full_path = match.group(1)
        if "." not in full_path:
            raise InterpolationError(f"Invalid variable: ${{{full_path}}} (expected namespace.path)")
        namespace, path = full_path.split(".", 1)
        value = ctx.resolve(namespace, path)
        return str(value)

    result = VARIABLE_PATTERN.sub(replace_var, result)

    # Restore escaped sequences
    result = result.replace('\x00ESCAPED\x00', '${')

    return result


def interpolate_dict(obj: dict, ctx: InterpolationContext) -> dict:
    """Recursively interpolate all string values in a dict."""
    result = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = interpolate(value, ctx)
        elif isinstance(value, dict):
            result[key] = interpolate_dict(value, ctx)
        elif isinstance(value, list):
            result[key] = [
                interpolate(v, ctx) if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


class InterpolationError(Exception):
    """Raised when variable interpolation fails."""
    pass


def _format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}m {seconds}s"
```

### Captured Value Structure

When a state uses `capture: "varname"`:

```python
captured["varname"] = {
    "output": "...",       # stdout
    "stderr": "...",       # stderr
    "exit_code": 0,        # exit code
    "duration_ms": 1234,   # execution time
}
```

### Prev Shorthand Structure

```python
prev = {
    "output": "...",       # stdout from previous state
    "exit_code": 0,        # exit code from previous state
    "state": "check",      # name of previous state
}
```

## Acceptance Criteria

- [x] `${context.*}` resolves user-defined variables
- [x] `${captured.*}` resolves stored action results with nested paths
- [x] `${prev.*}` provides shorthand for previous state result
- [x] `${result.*}` provides access to current evaluation result
- [x] `${state.name}` and `${state.iteration}` resolve correctly
- [x] `${loop.name}`, `${loop.started_at}`, `${loop.elapsed_ms}`, `${loop.elapsed}` resolve
- [x] `${env.*}` resolves environment variables
- [x] `$${...}` escapes to literal `${...}`
- [x] Undefined variables raise `InterpolationError` with clear message
- [x] Empty values interpolate as empty string (not error)
- [x] Nested interpolation is explicitly not supported

## Testing Requirements

```python
# tests/unit/test_interpolation.py
class TestInterpolation:
    def test_context_variable(self):
        """${context.target_dir} resolves from context dict."""

    def test_captured_nested(self):
        """${captured.errors.output} resolves nested path."""

    def test_prev_shorthand(self):
        """${prev.output} equals previous state stdout."""

    def test_env_variable(self):
        """${env.HOME} resolves from environment."""

    def test_undefined_raises(self):
        """Missing variable raises InterpolationError."""

    def test_escape_sequence(self):
        """$${literal} becomes ${literal}."""

    def test_multiple_variables(self):
        """String with multiple variables all resolve."""

    def test_state_iteration(self):
        """${state.iteration} returns current loop iteration."""

    def test_loop_elapsed_formatted(self):
        """${loop.elapsed} returns human-readable duration."""
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Variable Interpolation"

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/interpolation.py`: Created variable interpolation module with `InterpolationContext` dataclass, `interpolate()` and `interpolate_dict()` functions, and `InterpolationError` exception
- `scripts/little_loops/fsm/__init__.py`: Added exports for interpolation components
- `scripts/tests/test_fsm_interpolation.py`: Created 39 unit tests covering all namespaces, error cases, and edge cases

### Verification Results
- Tests: PASS (887 tests, including 39 new interpolation tests)
- Lint: PASS
- Types: PASS
