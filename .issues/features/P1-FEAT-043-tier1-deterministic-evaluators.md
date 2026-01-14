# FEAT-043: Tier 1 Deterministic Evaluators

## Summary

Implement the five deterministic evaluators that interpret action output without any API calls. These are fast, free, and reproducible.

## Priority

P1 - Core execution functionality

## Dependencies

- FEAT-040: FSM Schema Definition and Validation

## Blocked By

- FEAT-040

## Description

Tier 1 evaluators produce verdicts from action output using deterministic logic:

| Evaluator | Purpose | Verdicts |
|-----------|---------|----------|
| `exit_code` | Unix exit codes | success, failure, error |
| `output_numeric` | Compare numeric output | success, failure, error |
| `output_json` | Extract and compare JSON fields | success, failure, error |
| `output_contains` | Pattern matching | success, failure |
| `convergence` | Track progress toward target | target, progress, stall |

### Files to Create

```
scripts/little_loops/fsm/
└── evaluators.py
```

## Technical Details

### Evaluator Interface

All evaluators return a standard result structure:

```python
@dataclass
class EvaluationResult:
    verdict: str           # The routing key
    details: dict[str, Any]  # Evaluator-specific data
```

### exit_code Evaluator (Default for Shell Commands)

```python
def evaluate_exit_code(exit_code: int) -> EvaluationResult:
    """
    Map Unix exit code to verdict.

    | Exit Code | Verdict |
    |-----------|---------|
    | 0 | success |
    | 1 | failure |
    | 2+ | error |
    """
    if exit_code == 0:
        verdict = "success"
    elif exit_code == 1:
        verdict = "failure"
    else:
        verdict = "error"

    return EvaluationResult(
        verdict=verdict,
        details={"exit_code": exit_code}
    )
```

### output_numeric Evaluator

```python
def evaluate_output_numeric(
    output: str,
    operator: str,
    target: float,
) -> EvaluationResult:
    """
    Parse stdout as number and compare.

    Operators: eq, ne, lt, le, gt, ge

    | Comparison Result | Verdict |
    |-------------------|---------|
    | Condition met | success |
    | Condition not met | failure |
    | Parse error | error |
    """
    try:
        value = float(output.strip())
    except ValueError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Cannot parse as number: {output[:100]}"}
        )

    operators = {
        "eq": lambda v, t: v == t,
        "ne": lambda v, t: v != t,
        "lt": lambda v, t: v < t,
        "le": lambda v, t: v <= t,
        "gt": lambda v, t: v > t,
        "ge": lambda v, t: v >= t,
    }

    if operator not in operators:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Unknown operator: {operator}"}
        )

    condition_met = operators[operator](value, target)
    return EvaluationResult(
        verdict="success" if condition_met else "failure",
        details={"value": value, "target": target, "operator": operator}
    )
```

### output_json Evaluator

```python
import json

def evaluate_output_json(
    output: str,
    path: str,
    operator: str,
    target: Any,
) -> EvaluationResult:
    """
    Parse JSON and extract value at path, then compare.

    Path uses jq-style dot notation: ".summary.failed"
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Invalid JSON: {e}"}
        )

    try:
        value = _extract_json_path(data, path)
    except KeyError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Path not found: {path}"}
        )

    # Reuse numeric comparison logic
    if isinstance(value, (int, float)) and isinstance(target, (int, float)):
        return _compare_values(value, operator, target, path)
    elif operator == "eq":
        verdict = "success" if value == target else "failure"
    elif operator == "ne":
        verdict = "success" if value != target else "failure"
    else:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Operator {operator} not supported for non-numeric values"}
        )

    return EvaluationResult(
        verdict=verdict,
        details={"value": value, "path": path, "target": target}
    )


def _extract_json_path(data: dict, path: str) -> Any:
    """Extract value from dict using jq-style path like '.summary.failed'."""
    if path.startswith("."):
        path = path[1:]
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current
```

### output_contains Evaluator

```python
import re

def evaluate_output_contains(
    output: str,
    pattern: str,
    negate: bool = False,
) -> EvaluationResult:
    """
    Check if pattern exists in output.

    Pattern can be substring or regex.

    | Match Result | negate=False | negate=True |
    |--------------|--------------|-------------|
    | Found | success | failure |
    | Not found | failure | success |
    """
    # Try regex first, fall back to substring
    try:
        matched = bool(re.search(pattern, output))
    except re.error:
        matched = pattern in output

    if negate:
        verdict = "failure" if matched else "success"
    else:
        verdict = "success" if matched else "failure"

    return EvaluationResult(
        verdict=verdict,
        details={"matched": matched, "pattern": pattern, "negate": negate}
    )
```

### convergence Evaluator

```python
def evaluate_convergence(
    current: float,
    previous: float | None,
    target: float,
    tolerance: float = 0,
    direction: str = "minimize",
) -> EvaluationResult:
    """
    Compare current value to target and previous.

    | Scenario | Verdict |
    |----------|---------|
    | Value within tolerance of target | target |
    | Value improved toward target | progress |
    | Value unchanged or worsened | stall |
    """
    # Check if target reached
    if abs(current - target) <= tolerance:
        return EvaluationResult(
            verdict="target",
            details={"current": current, "target": target, "delta": 0}
        )

    # First iteration has no previous value
    if previous is None:
        return EvaluationResult(
            verdict="progress",
            details={"current": current, "previous": None, "target": target, "delta": None}
        )

    # Calculate progress
    delta = current - previous

    if direction == "minimize":
        # For minimizing, negative delta is progress
        made_progress = delta < 0
    else:
        # For maximizing, positive delta is progress
        made_progress = delta > 0

    verdict = "progress" if made_progress else "stall"

    return EvaluationResult(
        verdict=verdict,
        details={
            "current": current,
            "previous": previous,
            "target": target,
            "delta": delta,
            "direction": direction,
        }
    )
```

### Evaluator Dispatch

```python
def evaluate(
    config: EvaluateConfig,
    output: str,
    exit_code: int,
    context: InterpolationContext,
) -> EvaluationResult:
    """Dispatch to appropriate evaluator based on config type."""
    eval_type = config.type

    if eval_type == "exit_code":
        return evaluate_exit_code(exit_code)

    elif eval_type == "output_numeric":
        return evaluate_output_numeric(
            output=output,
            operator=config.operator,
            target=config.target,
        )

    elif eval_type == "output_json":
        return evaluate_output_json(
            output=output,
            path=config.path,
            operator=config.operator,
            target=config.target,
        )

    elif eval_type == "output_contains":
        return evaluate_output_contains(
            output=output,
            pattern=config.pattern,
            negate=config.negate,
        )

    elif eval_type == "convergence":
        # Resolve previous value from interpolation
        previous = None
        if config.previous:
            try:
                previous = float(interpolate(config.previous, context))
            except (InterpolationError, ValueError):
                pass

        return evaluate_convergence(
            current=float(output.strip()),
            previous=previous,
            target=float(config.target),
            tolerance=config.tolerance or 0,
            direction=config.direction,
        )

    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")
```

## Acceptance Criteria

- [x] `evaluate_exit_code()` maps 0→success, 1→failure, 2+→error
- [x] `evaluate_output_numeric()` supports eq, ne, lt, le, gt, ge operators
- [x] `evaluate_output_json()` extracts values using jq-style paths
- [x] `evaluate_output_contains()` supports regex and substring matching with negate
- [x] `evaluate_convergence()` detects target/progress/stall with direction support
- [x] All evaluators return `EvaluationResult` with verdict and details
- [x] Parse errors produce `error` verdict with descriptive details
- [x] `evaluate()` dispatcher routes to correct evaluator

## Testing Requirements

```python
# tests/unit/test_evaluators.py
class TestExitCodeEvaluator:
    @pytest.mark.parametrize("exit_code,expected", [
        (0, "success"),
        (1, "failure"),
        (2, "error"),
        (127, "error"),
    ])
    def test_exit_code_mapping(self, exit_code, expected):
        result = evaluate_exit_code(exit_code)
        assert result.verdict == expected

class TestOutputNumericEvaluator:
    def test_less_than_passes(self):
        result = evaluate_output_numeric("3", "lt", 5)
        assert result.verdict == "success"

    def test_parse_error(self):
        result = evaluate_output_numeric("not a number", "eq", 5)
        assert result.verdict == "error"

class TestOutputJsonEvaluator:
    def test_nested_path(self):
        output = '{"summary": {"failed": 0}}'
        result = evaluate_output_json(output, ".summary.failed", "eq", 0)
        assert result.verdict == "success"

class TestOutputContainsEvaluator:
    def test_regex_pattern(self):
        result = evaluate_output_contains("Error: 5 failures", r"\d+ failures")
        assert result.verdict == "success"

    def test_negate(self):
        result = evaluate_output_contains("All tests passed", "Error", negate=True)
        assert result.verdict == "success"

class TestConvergenceEvaluator:
    def test_target_reached(self):
        result = evaluate_convergence(0, 5, 0)
        assert result.verdict == "target"

    def test_progress(self):
        result = evaluate_convergence(3, 5, 0)
        assert result.verdict == "progress"

    def test_stall(self):
        result = evaluate_convergence(5, 5, 0)
        assert result.verdict == "stall"

    def test_maximize_direction(self):
        result = evaluate_convergence(8, 5, 10, direction="maximize")
        assert result.verdict == "progress"
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Evaluator Types" - "Tier 1: Deterministic Evaluators"

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/evaluators.py`: Created new module with all five Tier 1 evaluators:
  - `EvaluationResult` dataclass for standardized results
  - `evaluate_exit_code()` - Unix exit code mapping
  - `evaluate_output_numeric()` - Numeric comparison with six operators
  - `evaluate_output_json()` - JSON path extraction and comparison
  - `evaluate_output_contains()` - Pattern matching with regex/substring and negate
  - `evaluate_convergence()` - Progress tracking with interpolation support
  - `evaluate()` - Main dispatcher routing to appropriate evaluator
  - `_extract_json_path()` - Helper for jq-style path extraction
  - `_compare_values()` - Helper for numeric comparisons
- `scripts/little_loops/fsm/__init__.py`: Added exports for all evaluator functions
- `scripts/tests/test_fsm_evaluators.py`: Created comprehensive test suite (75 tests)

### Verification Results
- Tests: PASS (75 tests in test_fsm_evaluators.py, 216 total FSM tests)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
