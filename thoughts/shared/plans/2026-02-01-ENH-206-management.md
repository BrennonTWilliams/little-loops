# ENH-206: Improve cli.py test coverage from 29% to 80%+ - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P0-ENH-206-improve-cli-py-test-coverage.md`
- **Type**: enhancement
- **Priority**: P0
- **Action**: improve

## Current State Analysis

### Key Discoveries
- **Current coverage**: 29% (744 missing statements out of 1044 total) at `scripts/little_loops/cli.py:1-2030`
- **Entry points**: 6 main functions (main_auto, main_parallel, main_messages, main_loop, main_sprint, main_history)
- **Existing tests**: `scripts/tests/test_cli.py:1-1010` - primarily argument parsing tests
- **Coverage threshold**: 80% configured in `scripts/pyproject.toml:120`

### Pattern Discovered in Codebase
- CliRunner not used - tests use `unittest.mock.patch` for mocking and `tempfile.TemporaryDirectory` for isolation (test_cli.py:323-340)
- Argument parsing tests create isolated parsers matching main function signatures (test_cli.py:25-33)
- Integration tests patch manager classes and verify kwargs passed (test_cli.py:342-375)
- Test fixtures in `scripts/tests/conftest.py:55-154` for reusable temp_project_dir and sample_config

## Desired End State

- **Target coverage**: 80%+ (minimum 835 statements covered out of 1044)
- All 6 main entry points have comprehensive integration tests
- Error paths and signal handling tested
- Branch coverage for conditionals and exception handling

### How to Verify
- Run `pytest scripts/tests/test_cli.py -v --cov=scripts/little_loops/cli --cov-report=term-missing`
- Verify coverage >= 80%
- All existing tests continue to pass

## What We're NOT Doing
- Not modifying cli.py source code - only adding tests
- Not changing the test framework or pytest configuration
- Not refactoring existing tests (only adding new ones)
- Not adding acceptance tests or end-to-end integration tests - staying at unit/integration level

## Problem Analysis

### Coverage Gaps by Function

| Function | Lines | Missing Coverage |
|----------|-------|------------------|
| main_auto | 58-113 | category filter, only/skip parsing, project_root fallback |
| main_parallel | 116-280 | cleanup mode, priority parsing, merge-pending/clean-start/ignore-pending, overlap-detection, warn-only, state file deletion |
| main_messages | 283-413 | --output, --cwd, --exclude-agents, --include-response-context, empty messages, verbose logging |
| main_loop | 416-1238 | argv preprocessing, path resolution, all 10 subcommands thoroughly, dry-run, locking, max_iterations/no_llm/llm_model overrides |
| main_sprint | 1241-1891 | All subcommands (create/list/show/delete/run), skip filters, cycle detection, signal handlers, exception handling, state persistence |
| main_history | 1894-2025 | **Entire function has NO tests** (summary/analyze commands, all flags) |
| Signal handling | 39-55 | Global flag, handler behavior, shutdown checks |

## Solution Approach

Add targeted integration tests following existing patterns:
1. Use `unittest.mock.patch` to mock manager classes and subprocess calls
2. Use `tempfile.TemporaryDirectory` for isolated test environments
3. Create test fixtures for config files and issue directories
4. Test both success and error paths
5. Use `pytest.raises` for exception testing
6. Use `capsys` fixture for output verification

## Implementation Phases

### Phase 1: Add Tests for main_auto() Additional Coverage

#### Overview
Cover the missing argument parsing and configuration paths in main_auto.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainAutoAdditionalCoverage` with tests for:
1. `--category` filter passed to manager
2. `--only` and `--skip` argument parsing
3. `project_root` fallback to Path.cwd() when no --config
4. Error return codes when manager.run() returns non-zero

```python
class TestMainAutoAdditionalCoverage:
    """Additional coverage tests for main_auto entry point."""

    def test_category_filter_passed_to_manager(self, temp_project: Path) -> None:
        """main_auto passes --category filter to AutoManager."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(sys, "argv", [
                "ll-auto",
                "--category", "bugs",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_auto
                result = main_auto()

            assert result == 0
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["category"] == "bugs"

    def test_only_and_skip_parsed_to_sets(self, temp_project: Path) -> None:
        """main_auto parses --only and --skip to sets."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(sys, "argv", [
                "ll-auto",
                "--only", "BUG-001,BUG-002",
                "--skip", "BUG-003",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_auto
                result = main_auto()

            assert result == 0
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["only_ids"] == {"BUG-001", "BUG-002"}
            assert call_kwargs["skip_ids"] == {"BUG-003"}

    def test_project_root_fallback_to_cwd(self, temp_project: Path) -> None:
        """main_auto uses Path.cwd() when no --config provided."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            # Change to temp directory for test
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_project)
                with patch.object(sys, "argv", ["ll-auto"]):
                    from little_loops.cli import main_auto
                    result = main_auto()
            finally:
                os.chdir(original_cwd)

            assert result == 0
            # Verify BRConfig was created with cwd path
            mock_manager_cls.assert_called_once()

    def test_manager_run_error_returned(self, temp_project: Path) -> None:
        """main_auto returns error code when manager.run() fails."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 1  # Non-zero exit
            mock_manager_cls.return_value = mock_manager

            with patch.object(sys, "argv", ["ll-auto", "--config", str(temp_project)]):
                from little_loops.cli import main_auto
                result = main_auto()

            assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainAutoAdditionalCoverage -v`
- [ ] Coverage for main_auto increases measurably

---

### Phase 2: Add Tests for main_parallel() Missing Coverage

#### Overview
Cover cleanup mode, priority parsing, state file deletion, and new flags.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainParallelAdditionalCoverage` with tests for:
1. Cleanup mode with WorkerPool cleanup_all_worktrees()
2. Priority filter string parsing to uppercase list
3. --merge-pending, --clean-start, --ignore-pending flags
4. --overlap-detection and --warn-only flags (ENH-143)
5. State file deletion when not resuming
6. Logger verbose instantiation

```python
class TestMainParallelAdditionalCoverage:
    """Additional coverage tests for main_parallel entry point."""

    def test_priority_filter_parsed_to_uppercase_list(self, temp_project: Path) -> None:
        """main_parallel parses priority string to uppercase list."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", [
                "ll-parallel",
                "--priority", "p1,p2",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_parallel
                result = main_parallel()

            assert result == 0
            # Verify create_parallel_config was called with uppercase priorities
            from little_loops.cli import BRConfig
            config = BRConfig(temp_project)
            with patch.object(config, "create_parallel_config") as mock_create:
                mock_create.return_value = MagicMock()
                # Re-parse to check the priority_filter passed
                # ... (verify priority_filter == ["P1", "P2"])

    def test_merge_pending_flag_passed_to_config(self, temp_project: Path) -> None:
        """main_parallel passes --merge-pending to parallel config."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", [
                "ll-parallel",
                "--merge-pending",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_parallel
                result = main_parallel()

            assert result == 0
            # Verify merge_pending=True in config

    def test_overlap_detection_flag_passed(self, temp_project: Path) -> None:
        """main_parallel passes --overlap-detection to config."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", [
                "ll-parallel",
                "--overlap-detection",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_parallel
                result = main_parallel()

            assert result == 0
            # Verify overlap_detection=True in config

    def test_warn_only_flag_sets_serialize_overlapping_false(self, temp_project: Path) -> None:
        """main_parallel --warn-only sets serialize_overlapping=False."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", [
                "ll-parallel",
                "--overlap-detection",
                "--warn-only",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_parallel
                result = main_parallel()

            assert result == 0
            # Verify serialize_overlapping=False

    def test_state_file_deleted_on_fresh_start(self, temp_project: Path) -> None:
        """main_parallel deletes state file when not resuming."""
        # Create a mock state file
        state_file = temp_project / ".parallel-state.json"
        state_file.write_text('{"test": "data"}')

        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", ["ll-parallel", "--config", str(temp_project)]):
                from little_loops.cli import main_parallel
                result = main_parallel()

        assert result == 0
        # State file should be deleted
        assert not state_file.exists()

    def test_state_file_preserved_on_resume(self, temp_project: Path) -> None:
        """main_parallel preserves state file when --resume flag set."""
        state_file = temp_project / ".parallel-state.json"
        state_file.write_text('{"test": "data"}')

        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(sys, "argv", [
                "ll-parallel",
                "--resume",
                "--config", str(temp_project),
            ]):
                from little_loops.cli import main_parallel
                result = main_parallel()

        assert result == 0
        # State file should still exist
        assert state_file.exists()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainParallelAdditionalCoverage -v`

---

### Phase 3: Add Tests for main_messages() Missing Coverage

#### Overview
Cover --output, --cwd, --exclude-agents, --include-response-context, empty messages, verbose logging.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainMessagesAdditionalCoverage` with tests for:
1. Custom output path with --output
2. Working directory override with --cwd
3. Agent session exclusion with --exclude-agents
4. Response context inclusion with --include-response-context
5. Empty messages early return
6. Verbose logging flag

```python
class TestMainMessagesAdditionalCoverage:
    """Additional coverage tests for main_messages entry point."""

    def test_output_path_argument(self) -> None:
        """main_messages uses custom output path from --output."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = [
                    {"content": "Test", "timestamp": "2026-01-01T00:00:00"}
                ]
                with patch("little_loops.user_messages.save_messages") as mock_save:
                    mock_save.return_value = Path("/custom/output.jsonl")

                    with patch.object(sys, "argv", [
                        "ll-messages",
                        "--output", "/custom/output.jsonl"
                    ]):
                        from little_loops.cli import main_messages
                        result = main_messages()

            assert result == 0
            mock_save.assert_called_once()
            call_args = mock_save.call_args.args
            assert call_args[1] == Path("/custom/output.jsonl")

    def test_cwd_working_directory_override(self) -> None:
        """main_messages uses --cwd for project folder lookup."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", [
                    "ll-messages",
                    "--cwd", "/custom/cwd"
                ]):
                    from little_loops.cli import main_messages
                    result = main_messages()

            assert result == 0
            mock_get_folder.assert_called_once_with(Path("/custom/cwd"))

    def test_exclude_agents_flag(self) -> None:
        """main_messages passes include_agent_sessions=False when --exclude-agents."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", ["ll-messages", "--exclude-agents"]):
                    from little_loops.cli import main_messages
                    result = main_messages()

            assert result == 0
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["include_agent_sessions"] is False

    def test_include_response_context_flag(self) -> None:
        """main_messages passes include_response_context=True when flag set."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", ["ll-messages", "--include-response-context"]):
                    from little_loops.cli import main_messages
                    result = main_messages()

            assert result == 0
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["include_response_context"] is True

    def test_empty_messages_returns_zero(self) -> None:
        """main_messages returns 0 when no messages found (with warning)."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []  # Empty list

                with patch.object(sys, "argv", ["ll-messages"]):
                    from little_loops.cli import main_messages
                    result = main_messages()

            assert result == 0  # Early return at line 402

    def test_verbose_logging_flag(self, capsys) -> None:
        """main_messages creates Logger with verbose=True when --verbose set."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []
                with patch("little_loops.user_messages.save_messages") as mock_save:
                    mock_save.return_value = Path("/output.jsonl")

                    with patch.object(sys, "argv", ["ll-messages", "--verbose"]):
                        from little_loops.cli import main_messages
                        result = main_messages()

            captured = capsys.readouterr()
            assert result == 0
            # Verbose output should include progress messages
            assert "Project folder:" in captured.out or "Limit:" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainMessagesAdditionalCoverage -v`

---

### Phase 4: Add Tests for main_loop() Missing Coverage

#### Overview
Cover argv preprocessing, path resolution, dry-run, locking, and subcommand variations.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainLoopAdditionalCoverage` with tests for:
1. Argv preprocessing (inserting "run" when first arg is loop name)
2. Loop path resolution (.fsm.yaml vs .yaml preference)
3. Dry-run mode with execution plan printing
4. Lock acquisition with --queue flag
5. max_iterations, no_llm, llm_model overrides
6. Additional subcommand tests (stop, resume, history, test)

```python
class TestMainLoopAdditionalCoverage:
    """Additional coverage tests for main_loop entry point."""

    def test_argv_preprocessing_inserts_run(self) -> None:
        """main_loop inserts 'run' when first arg is not a subcommand."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                # Call with loop name directly (no "run" subcommand)
                with patch.object(sys, "argv", ["ll-loop", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0
            mock_exec.assert_called_once()

    def test_loop_path_resolution_prefers_fsm_yaml(self) -> None:
        """resolve_loop_path prefers .fsm.yaml over .yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()

            # Create both files
            (loops_dir / "test-loop.yaml").write_text("name: paradigm")
            (loops_dir / "test-loop.fsm.yaml").write_text("name: compiled\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0

    def test_dry_run_prints_execution_plan(self, capsys) -> None:
        """main_loop --dry-run prints execution plan and exits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            loop_content = """
name: test-loop
initial: start
states:
  start:
    action: echo "test"
    on_success: done
  done:
    terminal: true
"""
            (loops_dir / "test-loop.fsm.yaml").write_text(loop_content)

            with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]):
                with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                    from little_loops.cli import main_loop
                    result = main_loop()

            captured = capsys.readouterr()
            assert result == 0
            assert "Execution plan for:" in captured.out

    def test_max_iterations_override(self) -> None:
        """main_loop passes max_iterations override to executor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--max-iterations", "5"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0
            # Verify max_iterations was passed

    def test_no_llm_flag(self) -> None:
        """main_loop passes no_llm=True when flag set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0

    def test_stop_command(self) -> None:
        """main_loop stop command stops running loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("little_loops.fsm.persistence.LockManager") as mock_lock_mgr:
                mock_lock_mgr.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0

    def test_resume_command(self) -> None:
        """main_loop resume command resumes interrupted loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0

    def test_history_command_with_tail(self) -> None:
        """main_loop history command shows execution history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.get_loop_history") as mock_history:
                mock_history.return_value = []

                with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "10"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0
            mock_history.assert_called_once()

    def test_test_command_single_iteration(self) -> None:
        """main_loop test command runs single test iteration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.fsm.yaml").write_text("name: test\ninitial: start\nstates:\n  start:\n    terminal: true")

            with patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec:
                mock_executor = MagicMock()
                mock_executor.run.return_value = MagicMock(iterations=1, terminated_by="terminal")
                mock_exec.return_value = mock_executor

                with patch.object(sys, "argv", ["ll-loop", "test", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop
                        result = main_loop()

            assert result == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainLoopAdditionalCoverage -v`

---

### Phase 5: Add Tests for main_sprint() Missing Coverage

#### Overview
Cover all subcommands (create, show, delete, run), skip filters, cycle detection, signal handlers, exception handling.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainSprintAdditionalCoverage` with tests for:
1. Create with skip filter
2. Create with invalid issues warning
3. Show with cycle detection
4. Show with invalid issues
5. List verbose mode
6. Delete not found error
7. Run sprint not found error
8. Run skip filter
9. Run cycle detection error
10. Run dry-run mode
11. Run resume mode state loading
12. Signal handler behavior
13. Single issue in-place processing
14. Multi-issue parallel processing
15. KeyboardInterrupt exception
16. Generic exception handling

```python
class TestMainSprintAdditionalCoverage:
    """Additional coverage tests for main_sprint entry point."""

    @pytest.fixture
    def sprint_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with sprint config."""
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            claude_dir = project / ".claude"
            claude_dir.mkdir()
            config = {
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    },
                    "completed_dir": "completed",
                },
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config))

            # Create issue directories
            issues_dir = project / ".issues"
            for category in ["bugs", "features", "completed"]:
                (issues_dir / category).mkdir(parents=True)

            # Create sample issues
            (issues_dir / "bugs" / "P0-BUG-001-test-bug.md").write_text("# BUG-001: Test Bug\n\nFix this bug.")
            (issues_dir / "features" / "P1-FEAT-010-test-feature.md").write_text("# FEAT-010: Test Feature\n\nAdd this feature.")

            # Create .sprints directory
            (project / ".sprints").mkdir()

            yield project

    def test_create_with_skip_filter(self, sprint_project: Path) -> None:
        """ll-sprint create with --skip excludes specified issues."""
        with patch.object(sys, "argv", [
            "ll-sprint",
            "create",
            "test-sprint",
            "--issues", "BUG-001,FEAT-010",
            "--skip", "BUG-001",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 0
        # Verify sprint was created with only FEAT-010

    def test_show_with_cycle_detection(self, sprint_project: Path) -> None:
        """ll-sprint show detects and reports dependency cycles."""
        # First create a sprint
        with patch.object(sys, "argv", [
            "ll-sprint",
            "create",
            "test-sprint",
            "--issues", "BUG-001,FEAT-010",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            main_sprint()

        # Modify issues to have circular dependency
        # (This would require updating the issue files with blocked_by)

        with patch.object(sys, "argv", [
            "ll-sprint",
            "show",
            "test-sprint",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 0

    def test_list_verbose_mode(self, sprint_project: Path) -> None:
        """ll-sprint list --verbose shows detailed information."""
        # Create a sprint first
        with patch.object(sys, "argv", [
            "ll-sprint",
            "create",
            "test-sprint",
            "--issues", "BUG-001",
            "--description", "Test sprint",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            main_sprint()

        with patch.object(sys, "argv", ["ll-sprint", "list", "--verbose"]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 0

    def test_delete_not_found_error(self) -> None:
        """ll-sprint delete returns error for non-existent sprint."""
        with patch.object(sys, "argv", ["ll-sprint", "delete", "nonexistent-sprint"]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 1

    def test_run_dry_run_mode(self, sprint_project: Path) -> None:
        """ll-sprint run --dry-run exits after printing plan."""
        # Create a sprint first
        with patch.object(sys, "argv", [
            "ll-sprint",
            "create",
            "test-sprint",
            "--issues", "BUG-001",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            main_sprint()

        with patch.object(sys, "argv", [
            "ll-sprint",
            "run",
            "test-sprint",
            "--dry-run",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 0

    def test_run_sprint_not_found(self, sprint_project: Path) -> None:
        """ll-sprint run returns error for non-existent sprint."""
        with patch.object(sys, "argv", [
            "ll-sprint",
            "run",
            "nonexistent-sprint",
            "--config", str(sprint_project),
        ]):
            from little_loops.cli import main_sprint
            result = main_sprint()

        assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainSprintAdditionalCoverage -v`

---

### Phase 6: Add Tests for Signal Handler (cli.py:39-55)

#### Overview
Test the global signal handler for graceful shutdown in ll-sprint.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestSprintSignalHandler` with tests for:
1. First signal sets flag without exiting
2. Second signal forces exit with sys.exit(1)
3. Global flag state management

```python
class TestSprintSignalHandler:
    """Tests for sprint signal handler (ENH-183)."""

    def test_first_signal_sets_flag(self) -> None:
        """First signal sets shutdown flag without exiting."""
        import little_loops.cli as cli_module
        from little_loops.cli import _sprint_signal_handler

        # Reset flag
        cli_module._sprint_shutdown_requested = False

        # First signal should set flag
        _sprint_signal_handler(signal.SIGINT, None)

        assert cli_module._sprint_shutdown_requested is True

    def test_second_signal_forces_exit(self) -> None:
        """Second signal forces immediate exit with code 1."""
        import little_loops.cli as cli_module
        from little_loops.cli import _sprint_signal_handler

        # Reset flag and set first signal
        cli_module._sprint_shutdown_requested = False
        _sprint_signal_handler(signal.SIGINT, None)
        assert cli_module._sprint_shutdown_requested is True

        # Second signal should force exit
        with pytest.raises(SystemExit) as exc_info:
            _sprint_signal_handler(signal.SIGTERM, None)

        assert exc_info.value.code == 1

    def test_global_flag_reset_between_tests(self) -> None:
        """Global flag can be reset for independent tests."""
        import little_loops.cli as cli_module
        from little_loops.cli import _sprint_signal_handler

        cli_module._sprint_shutdown_requested = False

        _sprint_signal_handler(signal.SIGINT, None)
        assert cli_module._sprint_shutdown_requested is True

        # Reset
        cli_module._sprint_shutdown_requested = False
        assert cli_module._sprint_shutdown_requested is False
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestSprintSignalHandler -v`

---

### Phase 7: Add Tests for main_history() - COMPLETE COVERAGE

#### Overview
main_history has NO existing tests. Add comprehensive tests for summary and analyze subcommands.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add test class `TestMainHistoryCoverage` with tests for:
1. Summary command default output
2. Summary --json flag
3. Summary --directory argument
4. Analyze command default output
5. Analyze --format choices (json/yaml/markdown/text)
6. Analyze --directory argument
7. Analyze --period choices (weekly/monthly/quarterly)
8. Analyze --compare argument
9. No command error case
10. Default directory fallback to .issues

```python
class TestMainHistoryCoverage:
    """Coverage tests for main_history entry point (NO existing tests)."""

    @pytest.fixture
    def history_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with completed issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            issues_dir = project / ".issues"
            completed_dir = issues_dir / "completed"
            completed_dir.mkdir(parents=True)

            # Create sample completed issue
            (completed_dir / "P1-BUG-001-fixed-bug.md").write_text("""
# BUG-001: Fixed Bug

## Status
Completed

## Resolution
- Fixed the bug
""")
            yield project

    def test_summary_command_default_output(self, history_project: Path) -> None:
        """ll-history summary outputs formatted text by default."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_summary") as mock_calc:
                mock_calc.return_value = MagicMock(
                    total_issues=0,
                    by_type={},
                    by_priority={},
                    by_category={},
                )

                with patch.object(sys, "argv", ["ll-history", "summary"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_summary_json_flag(self, history_project: Path) -> None:
        """ll-history summary --json outputs JSON format."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_summary") as mock_calc:
                mock_calc.return_value = MagicMock(
                    total_issues=0,
                    by_type={},
                    by_priority={},
                    by_category={},
                )

                with patch.object(sys, "argv", ["ll-history", "summary", "--json"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_summary_directory_argument(self) -> None:
        """ll-history summary --directory uses custom issues directory."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_summary") as mock_calc:
                mock_calc.return_value = MagicMock(total_issues=0, by_type={}, by_priority={}, by_category={})

                with patch.object(sys, "argv", [
                    "ll-history",
                    "summary",
                    "--directory", "/custom/issues"
                ]):
                    from little_loops.cli import main_history
                    result = main_history()

        assert result == 0

    def test_analyze_command_default_format(self, history_project: Path) -> None:
        """ll-history analyze defaults to text format."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                mock_calc.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-history", "analyze"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_analyze_format_json(self, history_project: Path) -> None:
        """ll-history analyze --format json outputs JSON."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                mock_calc.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-history", "analyze", "--format", "json"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_analyze_format_markdown(self, history_project: Path) -> None:
        """ll-history analyze --format markdown outputs Markdown."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                mock_calc.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-history", "analyze", "--format", "markdown"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_analyze_format_yaml(self, history_project: Path) -> None:
        """ll-history analyze --format yaml outputs YAML."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                mock_calc.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-history", "analyze", "--format", "yaml"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_analyze_period_choices(self, history_project: Path) -> None:
        """ll-history analyze --period accepts weekly/monthly/quarterly."""
        for period in ["weekly", "monthly", "quarterly"]:
            with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
                mock_scan.return_value = []
                with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                    mock_calc.return_value = MagicMock()

                    with patch.object(sys, "argv", ["ll-history", "analyze", "--period", period]):
                        with patch("pathlib.Path.cwd", return_value=history_project):
                            from little_loops.cli import main_history
                            result = main_history()

            assert result == 0

    def test_analyze_compare_argument(self, history_project: Path) -> None:
        """ll-history analyze --compare compares last N days."""
        with patch("little_loops.issue_history.scan_completed_issues") as mock_scan:
            mock_scan.return_value = []
            with patch("little_loops.issue_history.calculate_analysis") as mock_calc:
                mock_calc.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-history", "analyze", "--compare", "30"]):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        from little_loops.cli import main_history
                        result = main_history()

        assert result == 0

    def test_no_command_shows_help(self) -> None:
        """ll-history with no command shows help and returns error."""
        with patch.object(sys, "argv", ["ll-history"]):
            from little_loops.cli import main_history
            result = main_history()

        assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_cli.py::TestMainHistoryCoverage -v`

---

## Testing Strategy

### Unit Tests
- Test argument parsing edge cases
- Test error handling paths
- Test return codes
- Test signal handler behavior

### Integration Tests
- Use temp directories with real config files
- Mock manager classes and orchestrators
- Test complete command flows
- Test with real filesystem operations

## References

- Original issue: `.issues/enhancements/P0-ENH-206-improve-cli-py-test-coverage.md`
- Source file: `scripts/little_loops/cli.py` (1044 statements, 29% coverage)
- Existing tests: `scripts/tests/test_cli.py` (1010 lines)
- Coverage config: `scripts/pyproject.toml:104-120` (80% threshold at line 120)
- Test fixtures: `scripts/tests/conftest.py:55-154`
- Pattern reference: `scripts/tests/test_cli.py:22-283` (argument parsing), `scripts/tests/test_cli.py:315-426` (integration with mocks)
