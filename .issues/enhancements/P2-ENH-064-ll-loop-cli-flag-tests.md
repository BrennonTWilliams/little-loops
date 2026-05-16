# ENH-064: Add Tests for --no-llm and --llm-model CLI Flags

## Summary

The `ll-loop` CLI defines `--no-llm` and `--llm-model` flags in argparse but they are never tested. These flags control LLM evaluator behavior, and their absence in tests means the feature could break silently.

## Current State

- **CLI File**: `scripts/little_loops/cli.py`
- **Flags**: `--no-llm` (disable LLM evaluators), `--llm-model` (specify model)
- **Test Coverage**: None

### Argparse Definition (Untested)

```python
# scripts/little_loops/cli.py:481-482
run_parser.add_argument("--no-llm", action="store_true", help="Disable LLM evaluation")
run_parser.add_argument("--llm-model", type=str, help="Override LLM model")
```

Note: `--llm-model` has no default in argparse; the default model is applied elsewhere in the executor.

### What's Missing

Tests that verify:
- `--no-llm` flag is parsed and passed to executor
- `--no-llm` causes LLM evaluators to be skipped/fail gracefully
- `--llm-model` changes the model used for LLM evaluation
- Default model is used when `--llm-model` not specified

## Proposed Tests

### --no-llm Flag Tests

```python
class TestLLMFlags:
    """Tests for --no-llm and --llm-model CLI flags."""

    def test_no_llm_flag_disables_llm_evaluator(self, tmp_path, monkeypatch):
        """--no-llm should skip or fail LLM evaluators gracefully."""
        loop_with_llm = """
        states:
          analyze:
            action: 'echo "test output"'
            evaluator:
              type: llm_structured
              prompt: "Is this good?"
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text(loop_with_llm)

        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["ll-loop", "run", "test", "--no-llm"]):
            from little_loops.cli import main_loop
            # Should not call Anthropic API
            # Should handle gracefully (skip or use fallback)

    def test_no_llm_flag_parsed_correctly(self):
        """Verify --no-llm sets correct attribute."""
        # Create parser matching cli.py structure
        parser = argparse.ArgumentParser(prog="ll-loop")
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("loop")
        run_parser.add_argument("--no-llm", action="store_true")

        args = parser.parse_args(["run", "test-loop", "--no-llm"])
        assert args.no_llm is True

    def test_no_llm_default_is_false(self):
        """Default should allow LLM evaluators."""
        parser = argparse.ArgumentParser(prog="ll-loop")
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("loop")
        run_parser.add_argument("--no-llm", action="store_true")

        args = parser.parse_args(["run", "test-loop"])
        assert args.no_llm is False
```

### --llm-model Flag Tests

```python
    def test_llm_model_flag_changes_model(self, tmp_path, monkeypatch):
        """--llm-model should use specified model for LLM calls."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            # Setup loop with llm_structured evaluator
            # Run with --llm-model opus
            # Verify Anthropic called with model="opus"

    def test_llm_model_parsed_correctly(self):
        """--llm-model should accept model string."""
        parser = argparse.ArgumentParser(prog="ll-loop")
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("loop")
        run_parser.add_argument("--llm-model", type=str)

        args = parser.parse_args(["run", "test-loop", "--llm-model", "claude-opus-4-20250514"])
        assert args.llm_model == "claude-opus-4-20250514"

    def test_llm_model_passed_to_executor(self, tmp_path):
        """--llm-model value should reach executor."""
        # Verify executor receives correct model parameter
```

## Implementation Approach

Add tests to `test_ll_loop.py` under existing `TestMainLoopIntegration` or new `TestLLMFlags` class:

1. Test argument parsing for both flags
2. Test flag values reach executor (mock executor to verify)
3. Test behavior with loop containing `llm_structured` evaluator
4. Mock Anthropic client to verify model parameter

## Impact

- **Priority**: P2 (High)
- **Effort**: Low
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `--no-llm` flag is parsed correctly
- [ ] `--no-llm` disables or gracefully handles LLM evaluators
- [ ] `--llm-model` flag is parsed correctly
- [ ] `--llm-model` value reaches the executor/Anthropic client
- [ ] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `cli`, `llm`

---

## Status

**Completed** | Created: 2026-01-15 | Completed: 2026-01-15 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `--llm-model` to `_create_run_parser()` helper (line 96)
- `scripts/tests/test_ll_loop.py`: Added 4 parsing tests in `TestLoopArgumentParsing`:
  - `test_no_llm_flag_parsed_correctly` - verifies --no-llm sets no_llm to True
  - `test_no_llm_default_is_false` - verifies default is False
  - `test_llm_model_flag_parsed_correctly` - verifies --llm-model accepts model string
  - `test_llm_model_default_is_none` - verifies default is None
- `scripts/tests/test_ll_loop.py`: Added new `TestLLMFlags` class with 7 integration tests:
  - `test_no_llm_flag_accepted_with_dry_run` - CLI accepts --no-llm flag
  - `test_llm_model_flag_accepted_with_dry_run` - CLI accepts --llm-model flag
  - `test_no_llm_and_llm_model_combined` - both flags can be used together
  - `test_no_llm_sets_fsm_llm_enabled_false` - verifies --no-llm sets fsm.llm.enabled=False
  - `test_llm_model_sets_fsm_llm_model` - verifies --llm-model sets fsm.llm.model
  - `test_llm_model_overrides_default_model` - verifies CLI overrides YAML config
  - `test_no_llm_preserves_other_llm_config` - verifies --no-llm only changes enabled

### Verification Results
- Tests: PASS (114 tests passed)
- Lint: PASS
- Types: PASS

---

## Validation Notes

*Auto-corrected 2026-01-15:*
- Updated argparse code snippet to match actual cli.py:481-482 (corrected help text)
- Removed incorrect claim that `--llm-model` has a default value in argparse
- Fixed proposed tests to use inline parser creation instead of non-existent `build_parser` function
- Removed acceptance criterion for "default model value" (no default set in argparse)
