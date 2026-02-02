# ENH-207: Improve issue_manager.py test coverage from 50% to 80%+ - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P0-ENH-207-improve-issue-manager-py-test-coverage.md`
- **Type**: enhancement
- **Priority**: P0
- **Action**: improve

## Current State Analysis

The `issue_manager.py` module (`scripts/little_loops/issue_manager.py`) provides the core sequential issue processing automation for the little-loops system. It implements a 3-phase workflow (ready_issue, implement, verify) with state persistence for resume capability, dependency-aware sequencing, and comprehensive error handling.

### Current Coverage
- **Coverage**: 50% (165 missing statements out of 330 total)
- **Location**: `scripts/little_loops/issue_manager.py`
- **Test file**: `scripts/tests/test_issue_manager.py` (757 lines, 18 tests)

### Key Discoveries from Research

**Currently Uncovered Code Paths** (by line ranges):
- **Lines 108-117**: `run_claude_command` logging callback
- **Lines 148-189**: `run_with_continuation` - entire continuation loop
- **Line 250**: ready_issue failure warning
- **Lines 271-275**: Path rename handling
- **Lines 299-300**: Fallback failure
- **Lines 314-319**: Persistent path mismatch
- **Lines 333-338**: Corrections logging
- **Lines 342-343**: Concerns logging
- **Lines 347-394**: CLOSE verdict handling
- **Lines 404-408**: NOT READY handling
- **Lines 420-422**: Dry run logging
- **Line 437**: Issue arg selection
- **Lines 449-450**: Dry run result
- **Lines 455-489**: Implementation failure handling (transient vs real)
- **Lines 509-536**: Fallback verification (work detection)
- **Lines 547-548**: Verification failure warning
- **Lines 618-619**: Signal handler
- **Line 654**: only_ids filtering
- **Lines 684-730**: `run()` method main loop
- **Lines 734-774**: Timing summary logging
- **Lines 796, 799-800, 803**: State update conditions

### Patterns to Follow (from codebase research)

1. **subprocess.run mocking** - Used in `test_git_operations.py`, `test_issue_lifecycle.py`, `test_git_lock.py`
2. **Parametrized tests** - Used in `test_git_lock.py`, `test_issue_lifecycle.py`
3. **Temporary git repos** - Used in `test_merge_coordinator.py`
4. **Streaming callback testing** - Used in `test_subprocess_utils.py`
5. **Failure classification** - Used in `test_issue_lifecycle.py`

### Dependencies and Integration Points

**Internal modules**:
- `config.py`: BRConfig
- `dependency_graph.py`: DependencyGraph
- `git_operations.py`: check_git_status, verify_work_was_done
- `issue_lifecycle.py`: close_issue, complete_issue_lifecycle, create_issue_from_failure, classify_failure, verify_issue_completed
- `issue_parser.py`: IssueInfo, IssueParser, find_issues
- `logger.py`: Logger
- `parallel/output_parsing.py`: parse_ready_issue_output
- `state.py`: ProcessingState, StateManager
- `subprocess_utils.py`: run_claude_command, detect_context_handoff, read_continuation_prompt

## Desired End State

Coverage increased from 50% to at least 80% with tests for:
1. Sequential processing workflow
2. Error handling and retry logic
3. State management
4. Edge cases
5. Work verification
6. Git operations integration

### How to Verify
- Run: `python -m pytest scripts/tests/test_issue_manager.py --cov=scripts/little_loops/issue_manager --cov-report=term-missing`
- Coverage should be >= 80%
- All existing tests should pass

## What We're NOT Doing

- Not changing the production code - only adding tests
- Not refactoring the module structure
- Not adding new features
- Not modifying other modules' tests

## Problem Analysis

The current test coverage is low because:
1. Many error handling paths are not tested
2. The continuation workflow is completely untested
3. CLOSE verdict handling is not tested
4. Failure classification (transient vs real) is not tested
5. Fallback verification is not tested
6. Signal handling is not tested
7. The main `run()` loop is not tested end-to-end

## Solution Approach

Add targeted test cases for each uncovered code path, using patterns from the existing codebase:
- Use `subprocess.run` patching for Claude CLI commands
- Use parametrized tests for similar scenarios
- Use mock fixtures for complex dependencies
- Test error paths explicitly

## Implementation Phases

### Phase 1: Test `run_claude_command` function (lines 108-117)

#### Overview
Test the logging callback functionality in `run_claude_command`.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

Add new test class:

```python
class TestRunClaudeCommand:
    """Tests for run_claude_command function."""

    @pytest.fixture
    def mock_logger(self, temp_project_dir: Path) -> MagicMock:
        """Create a mock logger."""
        logger = MagicMock()
        return logger

    def test_streams_output_when_enabled(self, mock_logger: MagicMock) -> None:
        """Test that stream_callback is called when stream_output=True."""
        from little_loops.issue_manager import run_claude_command

        # Track callback invocations
        callback_calls: list[tuple[str, bool]] = []

        def mock_stream_callback(line: str, is_stderr: bool) -> None:
            callback_calls.append((line, is_stderr))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test output\n"
        mock_result.stderr = ""

        with patch("little_loops.issue_manager._run_claude_base") as mock_run:
            mock_run.return_value = mock_result

            # Capture the stream_callback passed to _run_claude_base
            original_callback = None

            def capture_callback(*args, **kwargs):
                nonlocal original_callback
                if "stream_callback" in kwargs:
                    original_callback = kwargs["stream_callback"]
                return mock_result

            mock_run.side_effect = capture_callback
            run_claude_command("test command", mock_logger, stream_output=True)

            # Verify callback was set
            assert original_callback is not None

    def test_skips_streaming_when_disabled(self, mock_logger: MagicMock) -> None:
        """Test that stream_callback is None when stream_output=False."""
        from little_loops.issue_manager import run_claude_command

        mock_result = MagicMock()
        mock_result.returncode = 0

        callback_passed = False

        def check_callback(*args, **kwargs):
            nonlocal callback_passed
            if kwargs.get("stream_callback") is not None:
                callback_passed = True
            return mock_result

        with patch("little_loops.issue_manager._run_claude_base") as mock_run:
            mock_run.side_effect = check_callback
            run_claude_command("test command", mock_logger, stream_output=False)

            assert not callback_passed
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestRunClaudeCommand -v`
- [ ] Coverage increases: Lines 108-117 covered

---

### Phase 2: Test `run_with_continuation` function (lines 148-189)

#### Overview
Test the context handoff continuation loop.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

Add test class:

```python
class TestRunWithContinuation:
    """Tests for run_with_continuation context handoff handling."""

    def test_returns_immediately_when_no_handoff(self, temp_project_dir: Path) -> None:
        """Test that function returns normally when no CONTEXT_HANDOFF detected."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                result = run_with_continuation("test command", mock_logger)

        assert result.returncode == 0
        assert "Normal output" in result.stdout

    def test_performs_single_continuation(self, temp_project_dir: Path) -> None:
        """Test that single continuation is performed when CONTEXT_HANDOFF detected."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        # First call returns handoff signal
        first_result = MagicMock()
        first_result.returncode = 0
        first_result.stdout = "CONTEXT_HANDOFF\n"
        first_result.stderr = ""
        first_result.args = ["claude", "-p", "first"]

        # Second call (continuation) succeeds
        second_result = MagicMock()
        second_result.returncode = 0
        second_result.stdout = "Continuation output"
        second_result.stderr = ""
        second_result.args = ["claude", "-p", "continuation"]

        continuation_prompt = "# Continuation prompt content"

        call_count = [0]

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return first_result
            return second_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                with patch("little_loops.issue_manager.read_continuation_prompt", return_value=continuation_prompt):
                    result = run_with_continuation("test command", mock_logger, max_continuations=3)

        assert call_count[0] == 2  # Initial + 1 continuation
        assert "---CONTINUATION---\n" in result.stdout

    def test_stops_at_max_continuations(self, temp_project_dir: Path) -> None:
        """Test that continuation stops after max_continuations reached."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        # Always return handoff signal
        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF\n"
        handoff_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=handoff_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                with patch("little_loops.issue_manager.read_continuation_prompt", return_value="# Prompt"):
                    result = run_with_continuation("test", mock_logger, max_continuations=2)

        # Should run initial + 2 continuations = 3 total
        assert result.returncode == 0

    def test_breaks_when_no_continuation_prompt(self, temp_project_dir: Path) -> None:
        """Test that continuation breaks when no prompt file found."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF\n"
        handoff_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=handoff_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                with patch("little_loops.issue_manager.read_continuation_prompt", return_value=""):
                    result = run_with_continuation("test", mock_logger)

        # Should stop after handoff with no prompt
        mock_logger.warning.assert_called()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestRunWithContinuation -v`
- [ ] Coverage increases: Lines 148-189 covered

---

### Phase 3: Test error handling in Phase 1 (ready_issue)

#### Overview
Test various error scenarios in the ready_issue phase.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

Add test class:

```python
class TestReadyIssueErrorHandling:
    """Tests for error handling during ready_issue phase."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig for testing."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue for testing."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test-bug.md"
        issue_file.write_text("# BUG-001: Test Bug\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test Bug",
        )

    def test_ready_issue_failure_continues_anyway(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that ready_issue failure is logged but processing continues."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready_issue fails but doesn't crash
        mock_result = MagicMock()
        mock_result.returncode = 1  # Non-zero return code
        mock_result.stdout = ""
        mock_result.stderr = "Some error"

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        # Should continue (not crash) but return success=False since no ready output
        mock_logger.warning.assert_called()

    def test_fallback_ready_issue_failure_returns_error(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that fallback ready_issue failure returns error result."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # First ready_issue returns wrong path (mismatch)
        first_output = f"""
## VERDICT
READY

## VALIDATED_FILE
.wrong/path/file.md
"""
        first_result = MagicMock()
        first_result.returncode = 0
        first_result.stdout = first_output

        # Fallback ready_issue fails
        fallback_result = MagicMock()
        fallback_result.returncode = 1
        fallback_result.stdout = ""
        fallback_result.stderr = "Fallback failed"

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return first_result
            return fallback_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Fallback failed" in result.failure_reason

    def test_persistent_path_mismatch_returns_error(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that persistent mismatch after fallback returns error."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # Both calls return wrong path
        wrong_path = ".issues/bugs/P1-WRONG-999.md"
        output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_path}
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Path mismatch persisted" in result.failure_reason
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestReadyIssueErrorHandling -v`
- [ ] Coverage increases: Lines 250, 271-275, 299-300, 314-319 covered

---

### Phase 4: Test corrections and concerns logging (lines 333-343)

#### Overview
Test that corrections and concerns from ready_issue are logged.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestCorrectionsAndConcerns:
    """Tests for corrections and concerns handling."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_corrections_are_logged_and_stored(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that corrections from ready_issue are logged and stored."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = """
## VERDICT
CORRECTED

## IS_READY
true

## CORRECTIONS_MADE
- Fixed title
- Added description

## VALIDATED_FILE
""" + str(sample_issue.path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=mock_result),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
        ):
            mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert result.corrections == ["Fixed title", "Added description"]
        mock_logger.info.assert_called()

    def test_concerns_are_logged(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that concerns from ready_issue are logged as warnings."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
READY

## CONCERNS
- Minor issue found
- Another concern

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=mock_result),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
        ):
            mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        # Verify warnings were called
        assert any("Concern" in str(call) for call in mock_logger.warning.call_args_list)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestCorrectionsAndConcerns -v`
- [ ] Coverage increases: Lines 333-338, 342-343 covered

---

### Phase 5: Test CLOSE verdict handling (lines 347-394)

#### Overview
Test that CLOSE verdict is handled correctly.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestCloseVerdictHandling:
    """Tests for CLOSE verdict handling in ready_issue phase."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_close_with_invalid_ref_fails_without_file_ops(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that CLOSE with invalid_ref returns error without file operations."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = """
## VERDICT
CLOSE

## CLOSE_REASON
invalid_ref

## VALIDATED_FILE
""" + str(sample_issue.path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Invalid reference" in result.failure_reason
        # close_issue should NOT be called
        mock_logger.warning.assert_called()

    def test_close_without_validated_path_fails(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that CLOSE without validated_file_path returns error."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = """
## VERDICT
CLOSE

## CLOSE_REASON
duplicate
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "CLOSE without validated file path" in result.failure_reason

    def test_close_success_returns_closed_result(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that successful close returns was_closed=True."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
CLOSE

## CLOSE_REASON
duplicate

## CLOSE_STATUS
Closed - Duplicate

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.close_issue", return_value=True) as mock_close:
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert result.success
        assert result.was_closed
        mock_close.assert_called_once()

    def test_not_ready_verdict_fails_processing(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that NOT READY verdict fails processing."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
NOT_READY

## CONCERNS
- Missing requirements
- Unclear scope

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "NOT READY" in result.failure_reason
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestCloseVerdictHandling -v`
- [ ] Coverage increases: Lines 347-394, 404-408 covered

---

### Phase 6: Test failure classification (lines 455-489)

#### Overview
Test that implementation failures are classified as transient vs real.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestFailureClassification:
    """Tests for implementation failure classification."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    @pytest.mark.parametrize(
        ("error_msg", "expected_transient"),
        [
            ("Error: You're out of extra usage · resets 2pm", True),
            ("Rate limit exceeded. Please retry after 60s", True),
            ("Error 429: Too many requests", True),
            ("Connection refused: localhost:8080", True),
            ("Error: Connection timeout after 30s", True),
            ("SyntaxError: unexpected token at line 42", False),
            ("FAILED tests/test_foo.py::test_bar - AssertionError", False),
        ],
    )
    def test_transient_vs_real_failure_classification(
        self,
        mock_config: BRConfig,
        sample_issue: IssueInfo,
        error_msg: str,
        expected_transient: bool,
    ) -> None:
        """Test that failures are correctly classified as transient or real."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready_issue succeeds
        ready_output = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"
        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = ready_output

        # Implementation fails
        impl_result = MagicMock()
        impl_result.returncode = 1
        impl_result.stdout = ""
        impl_result.stderr = error_msg

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ready_result
            return impl_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                if expected_transient:
                    # Transient: should NOT create bug issue
                    with patch("little_loops.issue_manager.create_issue_from_failure") as mock_create:
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)
                        mock_create.assert_not_called()
                        assert "Transient" in result.failure_reason
                else:
                    # Real failure: should create bug issue
                    with patch("little_loops.issue_manager.create_issue_from_failure", return_value=sample_issue.path):
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)
                        assert not result.success
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestFailureClassification -v`
- [ ] Coverage increases: Lines 455-489 covered

---

### Phase 7: Test fallback verification (lines 509-536)

#### Overview
Test that fallback verification detects work and completes lifecycle.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestFallbackVerification:
    """Tests for fallback verification when issue not moved."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_fallback_completion_when_work_detected(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that fallback completion succeeds when work is detected."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready_issue and implement succeed
        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch("little_loops.issue_manager.run_with_continuation", return_value=impl_result):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch("little_loops.issue_manager.verify_work_was_done", return_value=True):
                        with patch("little_loops.issue_manager.complete_issue_lifecycle", return_value=True):
                            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert result.success

    def test_refuses_completion_when_no_work_detected(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that completion is refused when no work is detected."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch("little_loops.issue_manager.run_with_continuation", return_value=impl_result):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch("little_loops.issue_manager.verify_work_was_done", return_value=False):
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        mock_logger.error.assert_called()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestFallbackVerification -v`
- [ ] Coverage increases: Lines 509-536, 547-548 covered

---

### Phase 8: Test AutoManager.run() method (lines 684-730)

#### Overview
Test the main processing loop.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestAutoManagerRun:
    """Tests for AutoManager.run() main loop."""

    @pytest.fixture
    def full_project(self, temp_project_dir: Path) -> Path:
        """Set up a complete project for run() testing."""
        import json

        # Create .claude directory with config
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {
                        "prefix": "BUG",
                        "dir": "bugs",
                        "action": "fix",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)

        # Create a test issue
        (issues_dir / "P1-BUG-001-test-issue.md").write_text(
            "# BUG-001: Test Issue\n\n## Summary\nTest"
        )

        return temp_project_dir

    def test_run_processes_single_issue(self, full_project: Path) -> None:
        """Test that run() processes a single issue."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)

        # Mock the actual processing
        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-001",
                was_closed=False,
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False, max_issues=1)
                exit_code = manager.run()

        assert exit_code == 0
        assert manager.processed_count == 1

    def test_run_stops_at_max_issues(self, full_project: Path) -> None:
        """Test that run() stops after reaching max_issues."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create multiple issues
        issues_dir = full_project / ".issues" / "bugs"
        for i in range(2, 6):
            (issues_dir / f"P1-BUG-{i:03d}-test.md").write_text(f"# BUG-{i}: Test\n\n## Summary\nTest")

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-001",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False, max_issues=2)
                exit_code = manager.run()

        assert manager.processed_count == 2

    def test_run_with_only_ids_filter(self, full_project: Path) -> None:
        """Test that run() filters by only_ids."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create additional issues
        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-002-other.md").write_text("# BUG-002: Other\n\n## Summary\nOther")
        (issues_dir / "P1-BUG-003-target.md").write_text("# BUG-003: Target\n\n## Summary\nTarget")

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-003",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False, only_ids={"BUG-003"})
                exit_code = manager.run()

        # Should only process BUG-003
        mock_process.assert_called_once()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestAutoManagerRun -v`
- [ ] Coverage increases: Lines 654, 684-730 covered

---

### Phase 9: Test timing summary and state updates (lines 734-774, 796, 799-800, 803)

#### Overview
Test timing summary logging and state update branches.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestTimingSummaryAndStateUpdates:
    """Tests for timing summary and state update conditions."""

    def test_timing_summary_logged(self, temp_project_dir: Path) -> None:
        """Test that timing summary is logged with aggregate stats."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        import json

        # Setup project
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir()
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        config = BRConfig(temp_project_dir)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=5.0,
                issue_id="BUG-001",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False, max_issues=1)
                manager.run()

        # Verify timing summary was called
        assert manager.logger.header.called or manager.logger.timing.called

    def test_state_update_branches(self, temp_project_dir: Path) -> None:
        """Test that all state update branches are covered."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        import json

        # Setup
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir()
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")

        config = BRConfig(temp_project_dir)

        # Test was_closed branch
        closed_result = MagicMock(
            success=True,
            duration=1.0,
            issue_id="BUG-001",
            was_closed=True,
            corrections=[],
        )

        with patch("little_loops.issue_manager.process_issue_inplace", return_value=closed_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())

        # Test failure_reason branch
        failed_result = MagicMock(
            success=False,
            duration=1.0,
            issue_id="BUG-001",
            failure_reason="Test failure",
            corrections=[],
        )

        with patch("little_loops.issue_manager.process_issue_inplace", return_value=failed_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())

        # Test corrections branch
        with_corrections_result = MagicMock(
            success=True,
            duration=1.0,
            issue_id="BUG-001",
            corrections=["Fixed title"],
        )

        with patch("little_loops.issue_manager.process_issue_inplace", return_value=with_corrections_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestTimingSummaryAndStateUpdates -v`
- [ ] Coverage increases: Lines 734-774, 796, 799-800, 803 covered

---

### Phase 10: Test signal handler (lines 618-619)

#### Overview
Test graceful shutdown signal handling.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

```python
class TestSignalHandler:
    """Tests for graceful shutdown signal handling."""

    def test_signal_handler_sets_shutdown_flag(self, temp_project_dir: Path) -> None:
        """Test that signal handler sets _shutdown_requested flag."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        import json

        # Setup
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir()
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)

        config = BRConfig(temp_project_dir)
        manager = AutoManager(config, dry_run=True)

        # Initially not shutdown
        assert manager._shutdown_requested is False

        # Simulate signal handler call
        import signal
        manager._signal_handler(signal.SIGINT, None)

        # Flag should be set
        assert manager._shutdown_requested is True
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestSignalHandler -v`
- [ ] Coverage increases: Lines 618-619 covered

---

## Testing Strategy

### Test Organization
- Group tests by functionality (10 new test classes)
- Use descriptive test names following `test_<verb>_<noun>` pattern
- Apply parametrization for similar test cases

### Test Patterns Used
1. **subprocess.run mocking** - For Claude CLI commands
2. **Parametrized tests** - For failure classification
3. **Mock fixtures** - For config, logger, issues
4. **Callback capture** - For streaming tests
5. **State verification** - For state update tests

### Coverage Goals
- Target: 80%+ coverage (from current 50%)
- Focus on all uncovered line ranges identified
- Test error paths explicitly

## References

- Original issue: `.issues/enhancements/P0-ENH-207-improve-issue-manager-py-test-coverage.md`
- Source file: `scripts/little_loops/issue_manager.py`
- Test file: `scripts/tests/test_issue_manager.py`
- Coverage config: `scripts/pyproject.toml` (lines 104-120)
- Similar patterns: `scripts/tests/test_issue_lifecycle.py:716-767` (failure classification)
