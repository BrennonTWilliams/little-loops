# ENH-191: Distinguish transient vs real failures - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P1-ENH-191-distinguish-transient-vs-real-failures-in-automation.md
- **Type**: enhancement
- **Priority**: P1
- **Action**: improve

## Current State Analysis

The failure handling logic in `scripts/little_loops/issue_manager.py:462-487` creates bug issues for ALL failures without distinguishing between transient errors (API quota, network issues, timeouts) and real implementation failures (code bugs, validation errors).

### Key Discoveries
- `issue_manager.py:462-487`: Current failure handling calls `create_issue_from_failure()` unconditionally
- `issue_lifecycle.py:313-398`: The `create_issue_from_failure()` function creates P1 bugs with `implementation-failure` label
- Existing pattern: `MatchClassification` enum in `issue_discovery.py:27-38` for classifying findings
- Existing pattern: `EvaluationResult` dataclass in `fsm/evaluators.py:43-54` for returning typed results
- Test patterns: `@pytest.mark.parametrize` extensively used in `test_fsm_evaluators.py`

## Desired End State

The automation tools should:
1. Classify failures as "transient" or "real" based on error output patterns
2. Only create bug issues for "real" failures (code errors, test failures, validation issues)
3. Log transient failures clearly but NOT create bug issues for them
4. Return appropriate failure reasons in `IssueProcessingResult` for both types

### How to Verify
- Tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`
- Lint passes: `ruff check scripts/`
- Types pass: `python -m mypy scripts/little_loops/`
- API quota errors classified as transient
- Network errors classified as transient
- Timeout errors classified as transient
- Real code errors classified as real

## What We're NOT Doing

- Not adding retry logic for transient failures (user/orchestrator decides)
- Not changing the parallel worker path (`worker_pool.py`) - it doesn't call `create_issue_from_failure()`
- Not adding configuration for failure patterns (hardcoded is sufficient for now)
- Not changing the issue template structure
- Not adding recovery mechanisms for transient failures

## Problem Analysis

The recursive automation failure pattern:
1. Tool hits API quota → creates bug issue
2. Tool tries to fix that bug → hits quota again → creates another bug
3. Repeat until context exhausted or limits reached
4. Result: Many fake "implementation-failure" bugs with no value

Root cause: No classification of failure types before creating bug issues.

## Solution Approach

1. Add `FailureType` enum to `issue_lifecycle.py` for type safety
2. Add `classify_failure()` function to detect transient vs real errors
3. Modify `issue_manager.py` to check classification before creating issues
4. Add comprehensive tests with parametrize for all failure patterns

## Implementation Phases

### Phase 1: Add failure classification to issue_lifecycle.py

#### Overview
Add the `FailureType` enum and `classify_failure()` function to `issue_lifecycle.py`.

#### Changes Required

**File**: `scripts/little_loops/issue_lifecycle.py`
**Changes**: Add enum and classification function after imports, before existing functions

```python
from enum import Enum

class FailureType(Enum):
    """Classification of command failure types.

    Used to distinguish between transient errors that should not
    create bug issues and real implementation failures that should.
    """

    TRANSIENT = "transient"  # Temporary error, don't create issue
    REAL = "real"  # Actual bug/error, create issue


def classify_failure(error_output: str, returncode: int) -> tuple[FailureType, str]:
    """Classify a command failure as transient or real.

    Examines error output for patterns indicating transient failures
    (API quota, network errors, timeouts) vs real implementation failures.

    Args:
        error_output: stderr or stdout from failed command
        returncode: Process exit code

    Returns:
        Tuple of (failure_type, reason) where reason explains the classification
    """
    error_lower = error_output.lower()

    # API quota/rate limit patterns
    quota_patterns = [
        "out of extra usage",
        "rate limit",
        "quota exceeded",
        "too many requests",
        "api limit",
        "usage limit",
        "429",  # HTTP Too Many Requests
        "resource exhausted",
    ]
    if any(pattern in error_lower for pattern in quota_patterns):
        return (FailureType.TRANSIENT, "API quota or rate limit exceeded")

    # Network/connectivity patterns
    network_patterns = [
        "connection refused",
        "connection timeout",
        "network error",
        "dns resolution",
        "connection reset",
        "service unavailable",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "econnrefused",
        "enotfound",
        "etimedout",
    ]
    if any(pattern in error_lower for pattern in network_patterns):
        return (FailureType.TRANSIENT, "Network or connectivity error")

    # Timeout patterns
    timeout_patterns = [
        "timeout",
        "timed out",
        "deadline exceeded",
        "operation timed out",
    ]
    if any(pattern in error_lower for pattern in timeout_patterns):
        return (FailureType.TRANSIENT, "Command timeout")

    # Resource/system transient patterns
    resource_patterns = [
        "disk full",
        "no space left",
        "resource temporarily unavailable",
        "too many open files",
        "memory allocation failed",
        "out of memory",
    ]
    if any(pattern in error_lower for pattern in resource_patterns):
        return (FailureType.TRANSIENT, "System resource error")

    # Default: treat as real failure
    return (FailureType.REAL, "Implementation error")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py::TestClassifyFailure -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_lifecycle.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_lifecycle.py`

---

### Phase 2: Update failure handling in issue_manager.py

#### Overview
Modify `process_issue_inplace()` to check failure classification before creating bug issues.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
**Changes**:
1. Add import for `FailureType` and `classify_failure`
2. Modify failure handling block at lines 462-487

Import change at top of file:
```python
from little_loops.issue_lifecycle import (
    FailureType,
    classify_failure,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
```

Replace the failure handling block (lines 462-487) with:
```python
    # Handle implementation failure
    if result.returncode != 0:
        error_output = result.stderr or result.stdout or "Unknown error"
        failure_type, failure_reason_text = classify_failure(error_output, result.returncode)

        if failure_type == FailureType.TRANSIENT:
            logger.warning(f"Transient failure for {info.issue_id}: {failure_reason_text}")
            logger.warning("Not creating bug issue - this is a temporary error")
            logger.info("Error output (first 500 chars):")
            logger.info(error_output[:500])

            return IssueProcessingResult(
                success=False,
                duration=time.time() - issue_start_time,
                issue_id=info.issue_id,
                failure_reason=f"Transient: {failure_reason_text}",
                corrections=corrections,
            )

        # Real failure - create issue as before
        logger.error(f"Implementation failed for {info.issue_id}")

        failure_reason = ""
        if not dry_run:
            # Create new issue for the failure
            new_issue = create_issue_from_failure(
                error_output,
                info,
                config,
                logger,
            )
            failure_reason = str(new_issue) if new_issue else error_output
        else:
            logger.info("Would create new bug issue for this failure")

        return IssueProcessingResult(
            success=False,
            duration=time.time() - issue_start_time,
            issue_id=info.issue_id,
            failure_reason=failure_reason,
            corrections=corrections,
        )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`

---

### Phase 3: Add comprehensive tests

#### Overview
Add tests for the `classify_failure()` function and integration tests for the updated failure handling.

#### Changes Required

**File**: `scripts/tests/test_issue_lifecycle.py`
**Changes**: Add new test class after `TestCreateIssueFromFailure`

```python
# =============================================================================
# Tests: Failure Classification
# =============================================================================


class TestClassifyFailure:
    """Tests for classify_failure function."""

    @pytest.mark.parametrize(
        ("error_output", "expected_type", "expected_reason_contains"),
        [
            # API quota/rate limit patterns
            ("Error: You're out of extra usage · resets 2pm", FailureType.TRANSIENT, "quota"),
            ("Rate limit exceeded. Please retry after 60s", FailureType.TRANSIENT, "quota"),
            ("Error 429: Too many requests", FailureType.TRANSIENT, "quota"),
            ("API quota exceeded for model", FailureType.TRANSIENT, "quota"),
            ("ResourceExhausted: quota limit reached", FailureType.TRANSIENT, "quota"),
            # Network/connectivity patterns
            ("Connection refused: localhost:8080", FailureType.TRANSIENT, "network"),
            ("Error: Connection timeout after 30s", FailureType.TRANSIENT, "network"),
            ("DNS resolution failed for api.example.com", FailureType.TRANSIENT, "network"),
            ("503 Service Unavailable", FailureType.TRANSIENT, "network"),
            ("502 Bad Gateway", FailureType.TRANSIENT, "network"),
            ("Error: ECONNREFUSED", FailureType.TRANSIENT, "network"),
            # Timeout patterns
            ("Command timed out after 3600 seconds", FailureType.TRANSIENT, "timeout"),
            ("Operation timed out waiting for response", FailureType.TRANSIENT, "timeout"),
            ("Deadline exceeded for RPC call", FailureType.TRANSIENT, "timeout"),
            # Resource patterns
            ("Error: No space left on device", FailureType.TRANSIENT, "resource"),
            ("Out of memory while processing", FailureType.TRANSIENT, "resource"),
            ("Too many open files", FailureType.TRANSIENT, "resource"),
            # Real failure patterns
            ("SyntaxError: unexpected token at line 42", FailureType.REAL, "implementation"),
            ("FAILED tests/test_foo.py::test_bar - AssertionError", FailureType.REAL, "implementation"),
            ("ValueError: Invalid input provided", FailureType.REAL, "implementation"),
            ("TypeError: 'NoneType' has no attribute 'foo'", FailureType.REAL, "implementation"),
            ("ModuleNotFoundError: No module named 'missing'", FailureType.REAL, "implementation"),
        ],
    )
    def test_classify_failure_patterns(
        self, error_output: str, expected_type: FailureType, expected_reason_contains: str
    ) -> None:
        """Test that failure patterns are classified correctly."""
        from little_loops.issue_lifecycle import classify_failure

        failure_type, reason = classify_failure(error_output, 1)
        assert failure_type == expected_type, f"Expected {expected_type} for: {error_output[:50]}"
        assert expected_reason_contains in reason.lower(), f"Expected '{expected_reason_contains}' in: {reason}"

    def test_classify_failure_case_insensitive(self) -> None:
        """Test that pattern matching is case insensitive."""
        from little_loops.issue_lifecycle import classify_failure

        # Uppercase
        failure_type, _ = classify_failure("RATE LIMIT EXCEEDED", 1)
        assert failure_type == FailureType.TRANSIENT

        # Mixed case
        failure_type, _ = classify_failure("Connection Timeout occurred", 1)
        assert failure_type == FailureType.TRANSIENT

    def test_classify_failure_empty_output(self) -> None:
        """Test classification of empty error output."""
        from little_loops.issue_lifecycle import classify_failure

        failure_type, reason = classify_failure("", 1)
        assert failure_type == FailureType.REAL
        assert "implementation" in reason.lower()

    def test_classify_failure_unknown_error(self) -> None:
        """Test classification of unknown error types."""
        from little_loops.issue_lifecycle import classify_failure

        failure_type, reason = classify_failure("Some random error message", 1)
        assert failure_type == FailureType.REAL
        assert "implementation" in reason.lower()

    def test_classify_failure_multiline_output(self) -> None:
        """Test pattern matching works on multiline output."""
        from little_loops.issue_lifecycle import classify_failure

        error_output = """Some context here
Traceback (most recent call last):
  File "test.py", line 10
Error: You're out of extra usage · resets 2pm
More context after"""

        failure_type, _ = classify_failure(error_output, 1)
        assert failure_type == FailureType.TRANSIENT
```

**File**: `scripts/tests/test_issue_manager.py`
**Changes**: Add integration test for transient failure handling

```python
class TestProcessIssueInplaceFailureClassification:
    """Tests for failure classification in process_issue_inplace."""

    def test_transient_failure_no_issue_created(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that transient failures don't create bug issues."""
        # Mock the command to return a transient error
        transient_error = "Error: You're out of extra usage · resets 2pm"

        def mock_run_claude(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=["claude"], returncode=1, stdout="", stderr=transient_error
            )

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run_claude),
            patch("little_loops.issue_manager.run_with_continuation", side_effect=mock_run_claude),
        ):
            result = process_issue_inplace(
                sample_issue_info, sample_config, mock_logger, dry_run=False
            )

        assert result.success is False
        assert "Transient" in result.failure_reason
        # No bug issue should have been created
        bugs_dir = sample_config.get_issue_dir("bugs")
        new_bugs = list(bugs_dir.glob("*implementation-failure*"))
        assert len(new_bugs) == 0

    def test_real_failure_creates_issue(
        self,
        tmp_path: Path,
        sample_config: BRConfig,
        sample_issue_info: IssueInfo,
        mock_logger: MagicMock,
    ) -> None:
        """Test that real failures create bug issues."""
        real_error = "SyntaxError: unexpected token at line 42"

        def mock_run_claude(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=["claude"], returncode=1, stdout="", stderr=real_error
            )

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run_claude),
            patch("little_loops.issue_manager.run_with_continuation", side_effect=mock_run_claude),
        ):
            result = process_issue_inplace(
                sample_issue_info, sample_config, mock_logger, dry_run=False
            )

        assert result.success is False
        # Bug issue should have been created
        bugs_dir = sample_config.get_issue_dir("bugs")
        new_bugs = list(bugs_dir.glob("P1-BUG-*.md"))
        assert len(new_bugs) >= 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py::TestClassifyFailure -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestProcessIssueInplaceFailureClassification -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

### Phase 4: Update exports and documentation

#### Overview
Export the new types from the package and update the module docstring.

#### Changes Required

**File**: `scripts/little_loops/__init__.py`
**Changes**: Add exports for `FailureType` and `classify_failure`

**File**: `scripts/little_loops/issue_lifecycle.py`
**Changes**: Update module docstring to mention failure classification

#### Success Criteria

**Automated Verification**:
- [ ] Import works: `python -c "from little_loops import FailureType, classify_failure"`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test each transient pattern individually (API quota, network, timeout, resource)
- Test case insensitivity
- Test multiline error output
- Test empty and unknown errors default to REAL
- Test returncode is available (for future use)

### Integration Tests
- Test `process_issue_inplace()` with mocked transient failure → no bug created
- Test `process_issue_inplace()` with mocked real failure → bug created
- Test failure reason contains classification info

## References

- Original issue: `.issues/enhancements/P1-ENH-191-distinguish-transient-vs-real-failures-in-automation.md`
- Classification pattern: `scripts/little_loops/issue_discovery.py:27-38` (MatchClassification)
- Evaluation pattern: `scripts/little_loops/fsm/evaluators.py:87-106` (evaluate_exit_code)
- Test patterns: `scripts/tests/test_fsm_evaluators.py:42-65` (parametrize usage)
