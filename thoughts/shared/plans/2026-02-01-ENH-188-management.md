# ENH-188: Add quiet mode to ll-auto and ll-sprint - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-188-add-quiet-mode-to-auto-and-sprint.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

### Existing Quiet Mode Implementation
ll-parallel already implements quiet mode as the reference pattern:
- `cli.py:206` - Uses `add_quiet_arg(parser)` from cli_args
- `cli.py:224` - Creates `Logger(verbose=not args.quiet)`
- Logger class checks `if self.verbose:` before all output

### Current State of Affected Tools

**ll-auto** (`cli.py:58-112`):
- Uses `add_common_auto_args(parser)` at line 82
- `add_common_auto_args` does NOT include quiet (cli_args.py:162-173)
- AutoManager created without quiet parameter (cli.py:102-110)
- AutoManager hard-codes `Logger(verbose=True)` (issue_manager.py:594)

**ll-sprint run** (`cli.py:1322-1333`):
- Missing `add_quiet_arg(run_parser)` call
- `_cmd_sprint_run` creates hard-coded `Logger()` (cli.py:1692)
- Logger defaults to `verbose=True`

### Key Discoveries
- `add_quiet_arg()` already exists in cli_args.py:121-128
- Logger class supports `verbose` parameter controlling all output
- ll-parallel provides the exact pattern to follow at cli.py:206-224
- `add_common_parallel_args` already includes quiet (cli_args.py:184)

## Desired End State

Both ll-auto and ll-sprint support `--quiet/-q` flag that:
- Suppresses progress/info messages (Logger uses `verbose=False`)
- Still shows errors and warnings (when verbose=False, ALL logger output is suppressed)
- Still shows final summary

### How to Verify
- Run `ll-auto --quiet` and observe minimal output
- Run `ll-sprint run my-sprint --quiet` and observe minimal output
- Verify `--help` shows the new flag

## What We're NOT Doing

- Not changing Logger class behavior (already supports verbose)
- Not modifying ll-parallel (already has quiet mode)
- Not adding quiet to ll-sprint subcommands other than "run" (create, list, show, delete don't need it)
- Not implementing different verbosity levels (only quiet vs verbose)

## Problem Analysis

The issue is simple: ll-auto and ll-sprint lack consistency with ll-parallel by missing the `--quiet/-q` flag. This is useful for CI/CD and scripted environments where verbose output is undesirable.

## Solution Approach

Follow the established ll-parallel pattern:

1. **Add quiet to add_common_auto_args**: Add `add_quiet_arg(parser)` to include quiet in ll-auto automatically
2. **Pass quiet to AutoManager**: Add `verbose` parameter to AutoManager.__init__
3. **Create Logger with verbose flag**: AutoManager uses `Logger(verbose=verbose)` instead of hard-coded True
4. **Add quiet to ll-sprint run**: Call `add_quiet_arg(run_parser)` for the run subcommand
5. **Pass quiet through to _cmd_sprint_run**: Use `args.quiet` when creating Logger

## Implementation Phases

### Phase 1: Add quiet mode to ll-auto

#### Overview
Add `--quiet/-q` flag to ll-auto command and pass through to AutoManager.

#### Changes Required

**File**: `scripts/little_loops/cli_args.py:162-173`
**Changes**: Add `add_quiet_arg(parser)` to `add_common_auto_args`

```python
def add_common_auto_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to ll-auto command.

    Adds: --resume, --dry-run, --max-issues, --quiet, --only, --skip, --config
    """
    add_resume_arg(parser)
    add_dry_run_arg(parser)
    add_max_issues_arg(parser)
    add_quiet_arg(parser)  # <-- ADD THIS LINE
    add_only_arg(parser)
    add_skip_arg(parser)
    add_config_arg(parser)
```

**File**: `scripts/little_loops/cli.py:58-112`
**Changes**: Pass quiet flag to AutoManager (already available via args.quiet after above change)

```python
# In main_auto function, line 102-110
manager = AutoManager(
    config=config,
    dry_run=args.dry_run,
    max_issues=args.max_issues,
    resume=args.resume,
    category=args.category,
    only_ids=only_ids,
    skip_ids=skip_ids,
    quiet=args.quiet,  # <-- ADD THIS PARAMETER
)
```

**File**: `scripts/little_loops/issue_manager.py:565-594`
**Changes**: Add `verbose` parameter to AutoManager and use it for Logger

```python
def __init__(
    self,
    config: BRConfig,
    dry_run: bool = False,
    max_issues: int = 0,
    resume: bool = False,
    category: str | None = None,
    only_ids: set[str] | None = None,
    skip_ids: set[str] | None = None,
    verbose: bool = True,  # <-- ADD THIS PARAMETER
) -> None:
    """Initialize the auto manager.

    Args:
        config: Project configuration
        dry_run: If True, only preview what would be done
        max_issues: Maximum issues to process (0 = unlimited)
        resume: Whether to resume from previous state
        category: Optional category to filter (e.g., "bugs")
        only_ids: If provided, only process these issue IDs
        skip_ids: Issue IDs to skip (in addition to attempted issues)
        verbose: Whether to output progress messages (default: True)  # <-- ADD THIS DOC
    """
    self.config = config
    self.dry_run = dry_run
    self.max_issues = max_issues
    self.resume = resume
    self.category = category
    self.only_ids = only_ids
    self.skip_ids = skip_ids or set()

    self.logger = Logger(verbose=verbose)  # <-- CHANGE FROM verbose=True
    # ... rest of init
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py tests/test_issue_manager.py -v -k "auto or AutoManager"`
- [ ] Lint passes: `ruff check scripts/little_loops/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run `ll-auto --help` and verify `--quiet/-q` appears in usage
- [ ] Run `ll-auto --dry-run --quiet` and verify minimal output
- [ ] Run `ll-auto` without `--quiet` and verify normal verbose output

---

### Phase 2: Add quiet mode to ll-sprint run

#### Overview
Add `--quiet/-q` flag to ll-sprint run subcommand and pass through to Logger.

#### Changes Required

**File**: `scripts/little_loops/cli.py:1322-1333`
**Changes**: Add `add_quiet_arg(run_parser)` to the run subcommand

```python
# run subcommand
run_parser = subparsers.add_parser("run", help="Execute a sprint")
run_parser.add_argument("sprint", help="Sprint name to execute")
add_dry_run_arg(run_parser)
add_max_workers_arg(run_parser)
add_timeout_arg(run_parser)
add_config_arg(run_parser)
add_resume_arg(run_parser)
add_quiet_arg(run_parser)  # <-- ADD THIS LINE
add_skip_arg(
    run_parser,
    help_text="Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)",
)
```

**File**: `scripts/little_loops/cli.py:1684-1692`
**Changes**: Create Logger with verbose based on args.quiet

```python
def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint with dependency-aware scheduling."""
    from datetime import datetime

    logger = Logger(verbose=not args.quiet)  # <-- CHANGE FROM Logger()

    # Setup signal handlers for graceful shutdown (ENH-183)
    # ... rest of function
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py tests/test_sprint.py tests/test_sprint_integration.py -v -k "sprint or SprintManager"`
- [ ] Lint passes: `ruff check scripts/little_loops/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run `ll-sprint run --help` and verify `--quiet/-q` appears in usage
- [ ] Run `ll-sprint run my-sprint --dry-run --quiet` and verify minimal output
- [ ] Run `ll-sprint run my-sprint` without `--quiet` and verify normal verbose output

---

### Phase 3: Add tests for quiet mode

#### Overview
Add tests to verify quiet mode works correctly for both tools.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add tests for quiet flag parsing and behavior

```python
def test_main_auto_quiet_flag():
    """Test that --quiet flag is parsed correctly for ll-auto."""
    # Test quiet flag is recognized
    parser = create_auto_parser()
    args = parser.parse_args(['--quiet'])
    assert args.quiet is True

def test_main_sprint_run_quiet_flag():
    """Test that --quiet flag is parsed correctly for ll-sprint run."""
    # Test quiet flag is recognized
    parser = create_sprint_parser()
    args = parser.parse_args(['run', 'my-sprint', '--quiet'])
    assert args.quiet is True
```

**File**: `scripts/tests/test_issue_manager.py`
**Changes**: Add tests for AutoManager verbose parameter

```python
def test_auto_manager_verbose_false():
    """Test AutoManager with verbose=False creates quiet logger."""
    manager = AutoManager(
        config=test_config,
        verbose=False,
    )
    assert manager.logger.verbose is False

def test_auto_manager_verbose_true():
    """Test AutoManager with verbose=True creates verbose logger (default)."""
    manager = AutoManager(
        config=test_config,
    )
    assert manager.logger.verbose is True
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_cli.py scripts/tests/test_issue_manager.py -v`
- [ ] All existing tests still pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- Test CLI argument parsing for `--quiet/-q` flag
- Test AutoManager respects `verbose` parameter
- Test Logger output is suppressed when `verbose=False`

### Integration Tests
- Run ll-auto with `--dry-run --quiet` and verify output
- Run ll-sprint run with `--dry-run --quiet` and verify output
- Verify normal behavior without `--quiet` is unchanged

### Test Data
- Use existing test issues in test fixtures
- Use existing sprint definitions or create test sprint

## References

- Original issue: `.issues/enhancements/P4-ENH-188-add-quiet-mode-to-auto-and-sprint.md`
- ll-parallel reference: `scripts/little_loops/cli.py:206-224`
- add_quiet_arg definition: `scripts/little_loops/cli_args.py:121-128`
- Logger class: `scripts/little_loops/logger.py:12-90`
- Related: `.issues/completed/P4-ENH-187-create-shared-cli-argument-module.md`
