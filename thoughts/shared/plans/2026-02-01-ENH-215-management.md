# ENH-215: Improve error message validation in tests - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-215-improve-error-message-validation-in-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- **Test files with weak exception assertions**:
  - `test_cli.py`: 2x `pytest.raises(SystemExit)` without match
  - `test_sprint.py`: 1x `pytest.raises(SystemExit)` without match
  - `test_git_lock.py`: 1x ValueError, 1x TimeoutExpired without match
  - `test_subprocess_mocks.py`: 1x TimeoutExpired without match
  - `test_fsm_evaluators.py`: 3x KeyError without match (path-based)
  - `test_fsm_schema.py`: 1x FileNotFoundError, 1x YAMLError without match

- **Source code error messages**:
  - `_extract_json_path()` raises `KeyError(path)` at `scripts/little_loops/fsm/evaluators.py:184,186`
  - `load_and_validate()` raises `FileNotFoundError(f"FSM file not found: {path}")` at `scripts/little_loops/fsm/validation.py:309`
  - `load_and_validate()` may raise `yaml.YAMLError` from yaml.safe_load()

### Pattern Discovered in Codebase
- Most existing tests already use `match=` parameter for regex matching
- Pattern: `pytest.raises(ValueError, match="expected message")`
- For SystemExit, tests often check `exc_info.value.code` separately

## Desired End State

### What We're Improving
1. **Add message validation** to exception tests that currently only check exception type
2. **Use `match=` parameter** for regex-based message validation
3. **Validate meaningful content** in error messages
4. **Focus on user-facing errors** first (cli.py, fsm_schema.py)

### How to Verify
- All modified tests continue to pass
- Tests now fail if error messages change unexpectedly
- Error messages contain expected context (paths, relevant info)

## What We're NOT Doing

- Not changing error messages in source code (unless they're clearly broken)
- Not modifying tests that already have `match=` parameter
- Not creating new helper functions (deferred - not critical for this enhancement)
- Not refactoring test structure (only adding message validation)

## Problem Analysis

**Root Issue**: Many tests only validate exception type, not message content. This allows:
- Error messages to become vague over time
- Regression where helpful context is removed
- Poor user experience with uninformative errors

**Impact**: Users see unhelpful error messages and tests don't catch the regression.

## Solution Approach

### Phase 1: Improve user-facing error tests (highest priority)

**Target**: `test_fsm_schema.py`
- Add `match="FSM file not found"` for FileNotFoundError
- For YAMLError, use regex to match YAML error patterns

**Target**: `test_cli.py` and `test_sprint.py`
- These test signal handlers, already check exit code
- Consider adding stderr capture if user-facing

### Phase 2: Improve internal error tests

**Target**: `test_fsm_evaluators.py`
- Add `match=` for KeyError with path information
- Keys contain the path that wasn't found

**Target**: `test_git_lock.py`
- Add context for ValueError and TimeoutExpired

**Target**: `test_subprocess_mocks.py`
- Add match for TimeoutExpired

### Phase 3: Document pattern

**Target**: `docs/TESTING.md`
- Add section on error message validation best practices
- Include examples of `pytest.raises(match=)` usage
- Document quality criteria for error messages

## Implementation Phases

### Phase 1: Improve test_fsm_schema.py (user-facing FSM errors)

#### Overview
Add message validation to FSM loading tests - these are user-facing errors.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add `match=` parameter to exception assertions

```python
# Line 1056: test_file_not_found
# Before:
with pytest.raises(FileNotFoundError):
    load_and_validate(Path("/nonexistent/path.yaml"))

# After:
with pytest.raises(FileNotFoundError, match="FSM file not found"):
    load_and_validate(Path("/nonexistent/path.yaml"))

# Line 1074: test_invalid_yaml_syntax
# Before:
with pytest.raises(yaml.YAMLError):
    load_and_validate(fixture_path)

# After:
with pytest.raises(yaml.YAMLError, match="YAML"):
    load_and_validate(fixture_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- [ ] Specific test: `pytest scripts/tests/test_fsm_schema.py::TestLoadAndValidate -v`

---

### Phase 2: Improve test_fsm_evaluators.py (internal JSON path errors)

#### Overview
Add message validation for JSON path extraction errors - these help debug FSM evaluations.

#### Changes Required

**File**: `scripts/tests/test_fsm_evaluators.py`
**Changes**: Add `match=` for KeyError with path info

```python
# Line 195: test_missing_key_raises
# Before:
with pytest.raises(KeyError):
    _extract_json_path(data, "missing")

# After:
with pytest.raises(KeyError, match="missing"):
    _extract_json_path(data, "missing")

# Line 201: test_missing_nested_key_raises
# Before:
with pytest.raises(KeyError):
    _extract_json_path(data, "a.c")

# After:
with pytest.raises(KeyError, match="a.c"):
    _extract_json_path(data, "a.c")

# Line 207: test_array_index_out_of_range
# Before:
with pytest.raises(KeyError):
    _extract_json_path(data, "items.5")

# After:
with pytest.raises(KeyError, match="items\\.5"):
    _extract_json_path(data, "items.5")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py::TestExtractJsonPath -v`

---

### Phase 3: Improve test_git_lock.py and test_subprocess_mocks.py

#### Overview
Add message validation for git lock and subprocess timeout errors.

#### Changes Required

**File**: `scripts/tests/test_git_lock.py`

```python
# Line 98: test_exit_releases_lock_on_exception
# Before:
with pytest.raises(ValueError):
    with git_lock:
        raise ValueError("test error")

# After:
with pytest.raises(ValueError, match="test error"):
    with git_lock:
        raise ValueError("test error")

# Line 337: test_timeout_releases_lock
# Before:
with pytest.raises(subprocess.TimeoutExpired):
    git_lock.run(["status"], cwd=temp_cwd)

# After:
with pytest.raises(subprocess.TimeoutExpired, match="git status"):
    git_lock.run(["status"], cwd=temp_cwd)
```

**File**: `scripts/tests/test_subprocess_mocks.py`

```python
# Line 118: test_timeout
# Before:
with pytest.raises(subprocess.TimeoutExpired):
    run_claude_command("/ll:test", mock_logger, timeout=1, stream_output=False)

# After:
with pytest.raises(subprocess.TimeoutExpired, match="/ll:test"):
    run_claude_command("/ll:test", mock_logger, timeout=1, stream_output=False)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_git_lock.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_subprocess_mocks.py -v`

---

### Phase 4: Improve test_cli.py and test_sprint.py (signal handler tests)

#### Overview
Signal handler tests check exit codes. These are already well-tested for their purpose - they verify signal handling behavior. Adding message validation here is less critical since the tests already validate the exit code.

For this phase, we'll leave these as-is since:
1. They already validate the important behavior (exit code = 1)
2. The errors are signal-based (SIGTERM/SIGINT), not typical exceptions
3. Error messages come from Python's signal handling, not our code

#### Changes Required

**None** - Mark as out-of-scope. Current tests are appropriate for signal handlers.

#### Success Criteria

**No changes needed** - Existing tests are adequate.

---

### Phase 5: Document error message style guide

#### Overview
Add documentation section to TESTING.md explaining error message validation best practices.

#### Changes Required

**File**: `docs/TESTING.md`
**Changes**: Add new section on exception testing

```markdown
## Exception Testing Best Practices

When testing exception handling, validate both the exception type AND the error message:

### Good: Validate exception type and message
\```python
with pytest.raises(ValueError, match="Pattern cannot be empty"):
    GitignorePattern(pattern="", category="test", description="test")
\```

### Avoid: Only checking exception type
\```python
# This allows error messages to become unhelpful over time
with pytest.raises(ValueError):
    some_function()
\```

### Error Message Quality Criteria
Good error messages should:
1. **Explain what went wrong** - Be specific about the failure
2. **Include relevant context** - Paths, values, names involved
3. **Suggest how to fix** (when possible) - What the user should do
4. **Use consistent style** - Similar errors follow similar patterns

### Examples

#### User-facing errors
\```python
# Good: Includes path and problem
with pytest.raises(FileNotFoundError, match="FSM file not found"):
    load_and_validate(Path("/missing/path.yaml"))

# Good: Explains validation failure
with pytest.raises(ValueError, match="missing required fields.*name"):
    load_and_validate(fixture_path)
\```

#### Internal errors
\```python
# Good: Includes context for debugging
with pytest.raises(KeyError, match="items\\.5"):
    _extract_json_path(data, "items.5")
\```
```

#### Success Criteria

**Manual Verification**:
- [ ] Documentation reads clearly
- [ ] Examples are accurate and runnable
- [ ] Quality criteria are actionable

---

## Testing Strategy

### Regression Tests
- All existing tests must continue to pass
- New `match=` patterns should not be overly restrictive
- Use regex patterns that are flexible but meaningful

### Verification Commands
```bash
# Run all tests
python -m pytest scripts/tests/ -v

# Run specific test files
python -m pytest scripts/tests/test_fsm_schema.py -v
python -m pytest scripts/tests/test_fsm_evaluators.py -v
python -m pytest scripts/tests/test_git_lock.py -v
python -m pytest scripts/tests/test_subprocess_mocks.py -v

# Run with coverage
python -m pytest scripts/tests/ --cov=scripts/little_loops
```

## References

- Original issue: `.issues/enhancements/P3-ENH-215-improve-error-message-validation-in-tests.md`
- Related pattern: `scripts/little_loops/fsm/evaluators.py:184` (KeyError with path)
- Related pattern: `scripts/little_loops/fsm/validation.py:309` (FileNotFoundError)
- Testing docs: `docs/TESTING.md`
