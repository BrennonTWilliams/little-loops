# ENH-125: Add test iteration after loop creation - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-125-add-test-iteration-after-loop-creation.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The create_loop wizard (`commands/create_loop.md:1-686`) guides users through creating FSM loop configurations across 5 steps:
1. Paradigm selection (lines 26-50)
2. Paradigm-specific questions (lines 52-344)
3. Loop name (lines 414-434)
4. Preview and confirm (lines 436-538)
5. Save and validate (lines 540-596)

### Key Discoveries
- After saving, `ll-loop validate <name>` is called at line 573 to validate schema but not test execution
- Success message at lines 578-588 reports file saved but no execution test
- The FSM executor (`scripts/little_loops/fsm/executor.py:182-630`) can execute loops
- Evaluators at `scripts/little_loops/fsm/evaluators.py:500-611` determine verdicts from output
- The `ll-loop` CLI has a `run` subcommand that could be leveraged

## Desired End State

After the loop is validated and before the final success message, the wizard offers to run a single test iteration:

1. Ask user if they want to test the loop
2. If yes, run the initial state's check action once
3. Show the command output, evaluator type, verdict, and intended transition
4. Report success or warn about issues (parse errors, command failures)

### How to Verify
- Create a loop with a known-working check command; test iteration shows success
- Create a loop with a failing check command; test iteration shows failure verdict
- Create a loop with an unparseable output; test iteration shows error with helpful message
- Create a loop and skip test; wizard completes normally without running test

## What We're NOT Doing

- Not implementing full dry-run mode (separate issue ENH-127)
- Not invoking Claude CLI for slash command actions (would require API call, keep it simple)
- Not implementing retries or iterative fixes during test
- Not modifying the FSM executor or evaluators (use existing functionality via CLI)

## Problem Analysis

Users create loops via the wizard, assume they work, then discover issues when running them for real. Common problems include:
- Check command path or syntax errors
- Output format not matching evaluator expectations (e.g., output_numeric expecting a number)
- jq/awk commands failing silently

A test iteration would catch these problems immediately after creation.

## Solution Approach

Add a new Step 5.5 between validation and final success report:
1. After `ll-loop validate <name>` succeeds, ask if user wants a test iteration
2. If yes, run `ll-loop test <name>` (new CLI subcommand) or use `--dry-run --max-iterations=1`
3. Parse and display the output in a user-friendly format
4. Continue to success message regardless of test result (but warn if issues found)

Since implementing a new CLI subcommand is more robust and reusable, I'll add a `test` subcommand to `ll-loop` that runs a single state and outputs structured results.

## Implementation Phases

### Phase 1: Add ll-loop test subcommand

#### Overview
Add a `test` subcommand to `ll-loop` that runs just the initial state and reports structured results without proceeding through the full loop.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `cmd_test()` function and wire it to argparse

The test subcommand will:
1. Load and validate the FSM
2. Create executor with max_iterations=1
3. Execute just the initial state
4. Output structured results (command, exit_code, output snippet, evaluator, verdict, next state)

```python
def cmd_test(args: argparse.Namespace) -> int:
    """Run a single test iteration of a loop.

    Executes the initial state's action and evaluation, then reports
    what the loop would do without actually transitioning.
    """
    # Load FSM
    name = args.name
    fsm = load_and_validate(name)
    if fsm is None:
        return 1

    # Get initial state
    initial = fsm.initial
    state_config = fsm.states[initial]

    # If no action, report and exit
    if not state_config.action:
        print(f"Initial state '{initial}' has no action to test")
        return 0

    # Run action
    from little_loops.fsm.executor import DefaultActionRunner, ActionResult
    from little_loops.fsm.evaluators import evaluate, evaluate_exit_code
    from little_loops.fsm.interpolation import InterpolationContext

    runner = DefaultActionRunner()
    action = state_config.action
    is_slash = action.startswith("/") or state_config.action_type in ("prompt", "slash_command")

    print(f"## Test Iteration: {name}")
    print()
    print(f"State: {initial}")
    print(f"Action: {action}")

    if is_slash:
        print("\nNote: Slash commands require Claude CLI; skipping actual execution.")
        print("Verdict: SKIPPED (slash command)")
        return 0

    result = runner.run(action, timeout=state_config.timeout or 120, is_slash_command=False)

    print(f"Exit code: {result.exit_code}")

    # Truncate output for display
    output_preview = result.output[:500] + ("..." if len(result.output) > 500 else "")
    print(f"Output: {output_preview or '(empty)'}")

    if result.stderr:
        stderr_preview = result.stderr[:200] + ("..." if len(result.stderr) > 200 else "")
        print(f"Stderr: {stderr_preview}")

    # Evaluate
    ctx = InterpolationContext(prev_result={}, captured={}, env=os.environ.copy())

    if state_config.evaluate:
        eval_result = evaluate(
            config=state_config.evaluate,
            output=result.output,
            exit_code=result.exit_code,
            context=ctx,
        )
        evaluator_type = state_config.evaluate.type
    else:
        # Default to exit_code
        eval_result = evaluate_exit_code(result.exit_code)
        evaluator_type = "exit_code (default)"

    print()
    print(f"Evaluator: {evaluator_type}")
    print(f"Verdict: {eval_result.verdict.upper()}")

    if eval_result.details:
        for key, value in eval_result.details.items():
            print(f"  {key}: {value}")

    # Determine next state
    next_state = None
    verdict = eval_result.verdict

    if state_config.route:
        routes = state_config.route.routes
        if verdict in routes:
            next_state = routes[verdict]
        elif state_config.route.default:
            next_state = state_config.route.default
    else:
        if verdict == "success" and state_config.on_success:
            next_state = state_config.on_success
        elif verdict == "failure" and state_config.on_failure:
            next_state = state_config.on_failure
        elif verdict == "error" and state_config.on_error:
            next_state = state_config.on_error

    if next_state:
        print(f"Would transition: {initial} → {next_state}")
    else:
        print(f"Would transition: {initial} → (no transition configured for {verdict})")

    # Summary
    print()
    if eval_result.verdict == "error" or "error" in eval_result.details:
        print("⚠ Loop has issues - review the error details above")
        return 1
    else:
        print("✓ Loop appears to be configured correctly")
        return 0
```

Also add the subparser:

```python
# In setup_parser() or main()
test_parser = subparsers.add_parser("test", help="Run a single test iteration")
test_parser.add_argument("name", help="Loop name")
test_parser.set_defaults(func=cmd_test)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] New test: `pytest scripts/tests/test_ll_loop.py -k test_cmd_test`

**Manual Verification**:
- [ ] `ll-loop test` with no args shows help
- [ ] `ll-loop test nonexistent` shows error
- [ ] `ll-loop test <valid-loop>` runs and shows structured output

---

### Phase 2: Update create_loop.md wizard

#### Overview
Add Step 5.5 after validation to offer test iteration using the new `ll-loop test` command.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Insert new step between validation (line 573-574) and success report (lines 578-596)

After the validation step and before reporting success, add:

```markdown
5. **Offer test iteration:**

   After validation succeeds, use AskUserQuestion:
   ```yaml
   questions:
     - question: "Would you like to run a test iteration to verify the loop works?"
       header: "Test run"
       multiSelect: false
       options:
         - label: "Yes, run one iteration (Recommended)"
           description: "Execute check command and verify evaluation works"
         - label: "No, I'll test manually"
           description: "Skip test iteration"
   ```

   If "Yes":
   ```bash
   ll-loop test <name>
   ```

   Display the test output directly. The test command provides structured feedback:
   - Check command and exit code
   - Output preview
   - Evaluator type and verdict
   - Would-transition target
   - Success indicator or warning

   Continue to success report regardless of test result. If test showed issues,
   add a note to the success message:
   ```
   Loop created successfully!

   File: .loops/<name>.yaml
   ...

   Note: Test iteration found issues - see output above.
   ```
```

Also update the allowed-tools to include the test command:

```yaml
allowed-tools:
  - Bash(mkdir:*, test:*, ll-loop:*)
```

This already covers `ll-loop test` since it matches `ll-loop:*`.

Also update the step numbering in the header (line 14) to reflect the new step:
```markdown
5. Saving and validating
6. Optional test iteration
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: No markdown linting configured, manual review
- [ ] The allowed-tools pattern still matches ll-loop commands

**Manual Verification**:
- [ ] Run `/ll:create_loop`, complete wizard, accept test iteration - see test output
- [ ] Run `/ll:create_loop`, complete wizard, skip test iteration - no test run
- [ ] Test iteration shows helpful output for both working and failing loops

---

### Phase 3: Add unit tests for cmd_test

#### Overview
Add tests for the new `ll-loop test` subcommand.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add test class for cmd_test functionality

```python
class TestCmdTest:
    """Tests for ll-loop test subcommand."""

    def test_test_nonexistent_loop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with non-existent loop shows error."""
        monkeypatch.chdir(tmp_path)
        # Create empty .loops dir
        (tmp_path / ".loops").mkdir()

        args = argparse.Namespace(name="nonexistent")
        result = cmd_test(args)

        assert result == 1

    def test_test_shell_action_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with successful shell command."""
        monkeypatch.chdir(tmp_path)
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create a simple loop that echoes and succeeds
        loop_yaml = """
name: test-echo
paradigm: goal
goal: echo works
tools:
  - "echo hello"
  - "echo fixed"
max_iterations: 5
"""
        (loops_dir / "test-echo.yaml").write_text(loop_yaml)

        args = argparse.Namespace(name="test-echo")
        # Would need to capture stdout and verify output
        result = cmd_test(args)

        assert result == 0

    def test_test_slash_command_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with slash command action is skipped."""
        monkeypatch.chdir(tmp_path)
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
name: test-slash
paradigm: goal
goal: slash command works
tools:
  - "/ll:check_code"
  - "/ll:check_code fix"
max_iterations: 5
"""
        (loops_dir / "test-slash.yaml").write_text(loop_yaml)

        args = argparse.Namespace(name="test-slash")
        result = cmd_test(args)

        assert result == 0  # Should succeed but skip execution
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdTest -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

**Manual Verification**:
- [ ] Tests cover success, failure, and skip cases

---

## Testing Strategy

### Unit Tests
- `test_cmd_test` function with mock FSM and action runner
- Test verdict display for different evaluator types (exit_code, output_numeric)
- Test slash command skip behavior
- Test error handling for invalid loops

### Integration Tests
- Create a real loop file, run `ll-loop test`, verify output format
- Test with a loop that produces parse errors

## References

- Original issue: `.issues/enhancements/P3-ENH-125-add-test-iteration-after-loop-creation.md`
- Create loop wizard: `commands/create_loop.md:540-596`
- FSM executor: `scripts/little_loops/fsm/executor.py:182-630`
- Evaluators: `scripts/little_loops/fsm/evaluators.py:500-611`
- Existing ll-loop tests: `scripts/tests/test_ll_loop.py`
- Similar completed: `.issues/completed/P3-ENH-123-preview-compiled-fsm-before-saving.md`
