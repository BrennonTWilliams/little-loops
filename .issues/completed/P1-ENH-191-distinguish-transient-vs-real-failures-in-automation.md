---
discovered_date: 2026-01-31
discovered_by: capture_issue
---

# ENH-191: Distinguish transient vs real failures in automation tools

## Summary

Automation tools (`/ll:manage_issue`, `ll-auto`, `ll-parallel`, `ll-sprint`) currently create "implementation-failure" bug issues for ALL failures, including transient failures like API quota limits, network errors, and timeouts. This can cause recursive automation failures that flood the project with non-actionable bug issues.

## Context

User description: We need to fix `/ll:manage_issue` and related systems in this project to not create "implementation-failure" issues when fixing an issues fails. This can cause a recursive automation failure that floods the project with `implementation-failure` issues when the problem was merely being out of AI Provider Usage.

**Root cause pattern observed in external project:**

1. Automated issue management tool (`/ll:manage_issue`) attempted to fix real bugs (BUG-1810, BUG-1811)
2. Hit Claude API quota limit: "You're out of extra usage · resets 2pm"
3. Tool created "implementation failure" bugs for each failed attempt
4. Tool then tried to fix those implementation failure bugs
5. Hit quota limit again, creating MORE implementation failure bugs (recursive loop)
6. Result: 8 fake "implementation failure" bugs with no diagnostic value, only 2 real bugs

## Current Behavior

In `scripts/little_loops/issue_lifecycle.py:313-399`, the `create_issue_from_failure()` function is called for ANY non-zero returncode from `/ll:manage_issue`:

```python
# Handle implementation failure
if result.returncode != 0:
    logger.error(f"Implementation failed for {info.issue_id}")

    if not dry_run:
        # Create new issue for the failure
        new_issue = create_issue_from_failure(
            result.stderr or result.stdout or "Unknown error",
            info,
            config,
            logger,
        )
```

The function creates a P1 bug issue with label `implementation-failure` for every failure, regardless of whether it's:
- **Real failure**: Code errors, validation failures, logic bugs
- **Transient failure**: API quota, network errors, timeouts, rate limits

## Expected Behavior

The automation tool should distinguish between failure types:

**Real failures** (CREATE ISSUE):
- Syntax errors, type errors, test failures
- Validation failures from `/ll:ready_issue`
- Logic bugs during implementation
- Missing dependencies or files
- Git merge conflicts that can't be resolved

**Transient failures** (LOG AND EXIT):
- API quota exceeded ("out of extra usage", "rate limit")
- Network errors (connection timeout, DNS failure)
- Timeout errors (command timeout, hung process)
- Temporary file system issues (disk full, permissions)
- Claude Code service unavailable

For transient failures:
1. Log the error with clear message
2. Exit with appropriate error code
3. DO NOT create bug issue
4. DO NOT attempt retry (let user/orchestrator decide)

## Proposed Solution

### Phase 1: Add failure classification function

Add to `scripts/little_loops/issue_lifecycle.py`:

```python
def classify_failure(error_output: str, returncode: int) -> tuple[str, str]:
    """Classify a command failure as transient or real.

    Args:
        error_output: stderr or stdout from failed command
        returncode: Process exit code

    Returns:
        Tuple of (failure_type, reason) where failure_type is:
        - "transient": Temporary failure, don't create issue
        - "real": Actual bug/error, create issue
    """
    error_lower = error_output.lower()

    # API quota/rate limit patterns
    if any(pattern in error_lower for pattern in [
        "out of extra usage",
        "rate limit",
        "quota exceeded",
        "too many requests",
        "api limit",
        "usage limit",
    ]):
        return ("transient", "API quota or rate limit exceeded")

    # Network/connectivity patterns
    if any(pattern in error_lower for pattern in [
        "connection refused",
        "connection timeout",
        "network error",
        "dns resolution",
        "connection reset",
        "service unavailable",
        "502 bad gateway",
        "503 service unavailable",
    ]):
        return ("transient", "Network or connectivity error")

    # Timeout patterns
    if any(pattern in error_lower for pattern in [
        "timeout",
        "timed out",
        "deadline exceeded",
    ]):
        return ("transient", "Command timeout")

    # File system transient issues
    if any(pattern in error_lower for pattern in [
        "disk full",
        "no space left",
        "permission denied",  # Often temporary
        "resource temporarily unavailable",
    ]):
        return ("transient", "File system or resource error")

    # Default: treat as real failure
    return ("real", "Implementation error")
```

### Phase 2: Update failure handling in `issue_manager.py`

Modify `scripts/little_loops/issue_manager.py:462-487`:

```python
# Handle implementation failure
if result.returncode != 0:
    error_output = result.stderr or result.stdout or "Unknown error"
    failure_type, failure_reason_text = classify_failure(error_output, result.returncode)

    if failure_type == "transient":
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
    logger.error(f"Real implementation failure for {info.issue_id}")

    failure_reason = ""
    if not dry_run:
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

### Phase 3: Add tests

Add to `scripts/tests/test_issue_lifecycle.py`:

```python
def test_classify_failure_api_quota():
    """API quota failures are classified as transient."""
    error = "Error: You're out of extra usage · resets 2pm"
    failure_type, reason = classify_failure(error, 1)
    assert failure_type == "transient"
    assert "quota" in reason.lower() or "rate limit" in reason.lower()

def test_classify_failure_network_error():
    """Network errors are classified as transient."""
    error = "Error: Connection timeout after 30s"
    failure_type, reason = classify_failure(error, 1)
    assert failure_type == "transient"
    assert "network" in reason.lower() or "connectivity" in reason.lower()

def test_classify_failure_syntax_error():
    """Real code errors are classified as real."""
    error = "SyntaxError: unexpected token at line 42"
    failure_type, reason = classify_failure(error, 1)
    assert failure_type == "real"

def test_classify_failure_test_failure():
    """Test failures are classified as real."""
    error = "FAILED tests/test_foo.py::test_bar - AssertionError"
    failure_type, reason = classify_failure(error, 1)
    assert failure_type == "real"
```

### Phase 4: Update labels

Update `create_issue_from_failure()` to add classification label:

```python
## Labels
`bug`, `high-priority`, `auto-generated`, `implementation-failure`, `real-failure`
```

## Files to Modify

- `scripts/little_loops/issue_lifecycle.py` - Add `classify_failure()` function
- `scripts/little_loops/issue_manager.py` - Update failure handling logic
- `scripts/tests/test_issue_lifecycle.py` - Add classification tests
- `scripts/tests/test_issue_manager.py` - Add integration tests

## Impact

- **Priority**: P1 (High - prevents recursive automation failures)
- **Effort**: Medium (3-4 functions to modify, ~100 lines of code, tests)
- **Risk**: Low (defensive change, only affects failure handling)
- **Breaking Change**: No (changes error handling behavior, not API)

## Benefits

1. **Prevents recursive failures**: Quota limits won't spawn infinite bug issues
2. **Reduces noise**: Issue backlog stays focused on real bugs
3. **Better diagnostics**: Transient failures logged clearly, not buried in bug issues
4. **Saves time**: Users can quickly identify quota/network issues vs code bugs

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Automation layer design |
| guidelines | .claude/CLAUDE.md | Development guidelines |

## Labels

`enhancement`, `error-handling`, `automation`, `ll-auto`, `ll-parallel`, `ll-sprint`, `captured`

---

## Status

**Open** | Created: 2026-01-31 | Priority: P1

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-31
- **Status**: Completed

### Changes Made

1. **scripts/little_loops/issue_lifecycle.py**:
   - Added `FailureType` enum (TRANSIENT, REAL) for type-safe classification
   - Added `classify_failure()` function with pattern matching for:
     - API quota/rate limits (including gRPC "ResourceExhausted")
     - Network/connectivity errors (with word-boundary aware matching)
     - Timeout errors
     - System resource errors (disk full, OOM, too many files)
   - Default classification: REAL (implementation error)

2. **scripts/little_loops/issue_manager.py**:
   - Updated failure handling in `process_issue_inplace()` to:
     - Classify failures before creating bug issues
     - Log transient failures with clear warning (no bug issue created)
     - Only create bug issues for real implementation failures
     - Include classification in `IssueProcessingResult.failure_reason`

3. **scripts/little_loops/__init__.py**:
   - Exported `FailureType` and `classify_failure` for public use

4. **scripts/tests/test_issue_lifecycle.py**:
   - Added `TestClassifyFailure` class with 26 parametrized tests covering:
     - API quota patterns (5 variants)
     - Network patterns (6 variants)
     - Timeout patterns (3 variants)
     - Resource patterns (3 variants)
     - Real failure patterns (5 variants)
     - Edge cases (case insensitivity, empty output, multiline)

### Verification Results
- All 2109 tests pass
- Linter: clean
- Type checker: no issues
- Classification tests: 26/26 passing

### Implementation Notes
- Used word-boundary regex (`\b`) for Node.js-style error codes (ECONNREFUSED, ENOTFOUND) to avoid false positives like "ModuleNotFoundError" matching "enotfound"
- Added "resourceexhausted" (no space) pattern for gRPC-style errors
- Removed "permission denied" from transient patterns as it's often a real configuration issue
