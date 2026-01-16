# ENH-064: Add Tests for --no-llm and --llm-model CLI Flags - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-064-ll-loop-cli-flag-tests.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `ll-loop` CLI defines `--no-llm` and `--llm-model` flags in argparse but they are untested.

### Key Discoveries
- Flags defined at `scripts/little_loops/cli.py:481-482`
- Flags applied to FSM at `scripts/little_loops/cli.py:659-662`
- `--no-llm` sets `fsm.llm.enabled = False`
- `--llm-model` sets `fsm.llm.model` to the specified value
- Executor uses `self.fsm.llm.model` at `executor.py:398` for slash command default evaluation
- Existing test patterns in `test_ll_loop.py` use inline argparse parsers for parsing tests
- Integration tests use `patch.object(sys, "argv", ...)` with actual `main_loop()` calls

### Existing Test Patterns to Follow
- `TestLoopArgumentParsing._create_run_parser()` creates minimal parser for flag tests
- `TestMainLoopIntegration` tests use `tmp_path`, `monkeypatch.chdir()`, and `capsys`
- LLM mocking pattern: `patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE")` and `patch("little_loops.fsm.evaluators.anthropic")`

## Desired End State

Complete test coverage for both CLI flags:
- Parsing tests verify flags are correctly parsed by argparse
- Integration tests verify flag values reach the executor
- Behavior tests verify LLM evaluator respects the flags

### How to Verify
- All new tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- No regressions in existing tests

## What We're NOT Doing

- Not fixing the `--no-llm` flag behavior (the flag sets `enabled=False` but executor ignores it) - that's a separate bug
- Not modifying CLI or executor code, only adding tests
- Not testing the actual Anthropic API calls (mocked)

## Solution Approach

Add tests to `test_ll_loop.py` following existing patterns:
1. Add `--no-llm` to `_create_run_parser()` helper
2. Add parsing tests for both flags in `TestLoopArgumentParsing`
3. Add integration tests in `TestMainLoopIntegration` that verify flag values reach executor

## Implementation Phases

### Phase 1: Add Flag Parsing Tests

#### Overview
Add unit tests that verify `--no-llm` and `--llm-model` flags are correctly parsed by argparse.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Update `_create_run_parser()` to include `--llm-model`, add 4 new tests

```python
# In _create_run_parser(), add:
parser.add_argument("--llm-model", type=str)

# New tests in TestLoopArgumentParsing:
def test_no_llm_flag_parsed_correctly(self) -> None:
    """--no-llm flag sets no_llm to True."""
    parser = self._create_run_parser()
    args = parser.parse_args(["test-loop", "--no-llm"])
    assert args.no_llm is True

def test_no_llm_default_is_false(self) -> None:
    """--no-llm defaults to False when not specified."""
    parser = self._create_run_parser()
    args = parser.parse_args(["test-loop"])
    assert args.no_llm is False

def test_llm_model_flag_parsed_correctly(self) -> None:
    """--llm-model accepts model string."""
    parser = self._create_run_parser()
    args = parser.parse_args(["test-loop", "--llm-model", "claude-opus-4-20250514"])
    assert args.llm_model == "claude-opus-4-20250514"

def test_llm_model_default_is_none(self) -> None:
    """--llm-model defaults to None when not specified."""
    parser = self._create_run_parser()
    args = parser.parse_args(["test-loop"])
    assert args.llm_model is None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestLoopArgumentParsing -v`

---

### Phase 2: Add Integration Tests for --no-llm Flag

#### Overview
Add integration tests that verify `--no-llm` flag is accepted by the CLI and sets `fsm.llm.enabled = False`.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test class `TestLLMFlags` with integration tests

```python
class TestLLMFlags:
    """Tests for --no-llm and --llm-model CLI flags."""

    def test_no_llm_flag_accepted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm flag is accepted by the CLI."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm", "--dry-run"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0

    def test_no_llm_sets_llm_enabled_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm sets fsm.llm.enabled to False."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo test"
    on_success: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        original_executor_init = None
        def capture_fsm(*args, **kwargs):
            nonlocal captured_fsm
            captured_fsm = args[0]
            return original_executor_init(*args, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch("little_loops.fsm.persistence.FSMExecutor") as mock_executor_cls:
                from little_loops.fsm.executor import FSMExecutor
                original_executor_init = FSMExecutor.__init__
                mock_executor_cls.side_effect = capture_fsm
                mock_executor_cls.return_value = MagicMock()

                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    from little_loops.cli import main_loop
                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.enabled is False
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestLLMFlags -v`

---

### Phase 3: Add Integration Tests for --llm-model Flag

#### Overview
Add integration tests that verify `--llm-model` flag is accepted and the model value reaches the executor.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add tests to `TestLLMFlags` class

```python
def test_llm_model_flag_accepted(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--llm-model flag is accepted by the CLI."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
    (loops_dir / "test-loop.yaml").write_text(loop_content)

    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514", "--dry-run"]):
        from little_loops.cli import main_loop
        result = main_loop()

    assert result == 0

def test_llm_model_overrides_default(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--llm-model overrides the default model in fsm.llm.model."""
    # Similar pattern to test_no_llm_sets_llm_enabled_false
    # Capture FSM passed to executor and verify model value
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestLLMFlags -v`

---

### Phase 4: Finalize and Verify

#### Overview
Run full test suite and verify no regressions.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Argument parsing tests verify flags are correctly parsed
- Test default values when flags are omitted
- Test flag values when flags are provided

### Integration Tests
- Verify flags are accepted by actual CLI
- Verify flag values propagate to FSM object
- Mock subprocess/Anthropic to avoid external dependencies

## References

- Original issue: `.issues/enhancements/P2-ENH-064-ll-loop-cli-flag-tests.md`
- CLI flag definitions: `scripts/little_loops/cli.py:481-482`
- Flag application: `scripts/little_loops/cli.py:659-662`
- Existing test patterns: `scripts/tests/test_ll_loop.py:79-204` (parsing), `scripts/tests/test_ll_loop.py:937-1402` (integration)
- LLM mocking pattern: `scripts/tests/test_fsm_executor.py:860-906`
