# ENH-184: Standardize CLI argument flags across tools - Implementation Plan

## Issue Reference

- **File**: .issues/enhancements/P3-ENH-184-standardize-cli-argument-flags.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The ll-sprint CLI tool is missing short flags for several arguments that are available in ll-parallel. Current inconsistencies:

### Key Discoveries

- `cli.py:1340-1345` - `--timeout` has no short flag (ll-parallel has `-t` at line 198)
- `cli.py:1334-1339` - `--max-workers` has no short flag (ll-parallel uses `--workers/-w` at line 159)
- ll-sprint has no `--skip` argument (ll-auto has it at line 100, ll-parallel at line 248)
- ll-sprint uses `--issues` (line 1328) instead of `--only` pattern used elsewhere

### Consistent Arguments (no changes needed)

- `--resume/-r` - Already consistent across all three tools
- `--dry-run/-n` - Already consistent across all three tools
- `--verbose/-v` - Already consistent where used

## Desired End State

ll-sprint arguments standardized with ll-parallel:

1. `--timeout/-t` - Short flag added to both create and run subcommands
2. `--max-workers/-w` - Short flag added to both create and run subcommands
3. `--skip` - New argument added to create and run subcommands for skipping issues

### How to Verify

- All short flags work: `ll-sprint create test -t 1800 -w 4 --issues BUG-001`
- `--skip` excludes specified issues from sprint creation
- Tests pass covering new short flags
- No breaking changes to existing long flags

## What We're NOT Doing

- Not renaming `--issues` to `--only` - This is a different semantic (sprint creation requires issues, not filtering)
- Not adding `--quiet/-q` to sprint - Deferred to ENH-189
- Not adding `--timeout` or `--workers` to ll-auto - Out of scope for this enhancement
- Not changing ll-parallel argument names - Already standardized

## Problem Analysis

Users switching between ll-parallel and ll-sprint must remember different flag patterns:
- `ll-parallel --timeout 3600` or `ll-parallel -t 3600` (both work)
- `ll-sprint run sprint-1 --timeout 3600` (only long form works)

This creates cognitive friction and reduces command-line efficiency.

## Solution Approach

Add short flags `-t` and `-w` to ll-sprint's existing arguments, and add `--skip` argument following the pattern from ll-auto and ll-parallel. All changes are additive and backward-compatible.

## Implementation Phases

### Phase 1: Add Short Flags to ll-sprint

#### Overview

Add `-t` short flag to `--timeout` and `-w` short flag to `--max-workers` in both create and run subcommands.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Change 1**: Add `-t` to `--timeout` in create subcommand (lines 1340-1345)

```python
# Before
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Default timeout in seconds (default: 3600)",
    )

# After
    create_parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=3600,
        help="Default timeout in seconds (default: 3600)",
    )
```

**Change 2**: Add `-w` to `--max-workers` in create subcommand (lines 1334-1339)

```python
# Before
    create_parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Max workers for parallel execution within waves (default: 2)",
    )

# After
    create_parser.add_argument(
        "-w",
        "--max-workers",
        type=int,
        default=2,
        help="Max workers for parallel execution within waves (default: 2)",
    )
```

**Change 3**: Add `-t` to `--timeout` in run subcommand (line 1358)

```python
# Before
    run_parser.add_argument("--timeout", type=int, help="Override timeout in seconds")

# After
    run_parser.add_argument("-t", "--timeout", type=int, help="Override timeout in seconds")
```

**Change 4**: Add `-w` to `--max-workers` in run subcommand (lines 1353-1357)

```python
# Before
    run_parser.add_argument(
        "--max-workers",
        type=int,
        help="Override max workers for parallel mode",
    )

# After
    run_parser.add_argument(
        "-w",
        "--max-workers",
        type=int,
        help="Override max workers for parallel mode",
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py::TestSprintArgumentParsing -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

---

### Phase 2: Add --skip Argument to ll-sprint

#### Overview

Add `--skip` argument to create and run subcommands, following the pattern from ll-auto (line 100-105) and ll-parallel (line 248-253).

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Change 1**: Add `--skip` to create subcommand (after line 1345)

```python
    create_parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to exclude from sprint (e.g., BUG-003,FEAT-004)",
    )
```

**Change 2**: Add `--skip` to run subcommand (after line 1365)

```python
    run_parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)",
    )
```

**Change 3**: Update `_cmd_sprint_create` to handle `--skip` (around line 1412)

```python
def _cmd_sprint_create(args: argparse.Namespace, manager: SprintManager) -> int:
    """Create a new sprint."""
    logger = Logger()
    issues = [i.strip().upper() for i in args.issues.split(",")]

    # Apply skip filter if provided
    if args.skip:
        skip_ids = {s.strip().upper() for s in args.skip.split(",")}
        issues = [i for i in issues if i not in skip_ids]
        if skip_ids:
            logger.info(f"Skipping issues: {', '.join(sorted(skip_ids))}")
    # ... rest of function
```

**Change 4**: Update `_cmd_sprint_run` to handle `--skip` (around line 1619)

The sprint run command needs to pass skip list to the sprint execution. Check how the existing `SprintManager.run_sprint()` handles issue filtering.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py::TestSprintArgumentParsing -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

---

### Phase 3: Update Tests

#### Overview

Update the test helper in `test_cli.py` to include the new short flags and `--skip` argument, then add tests for the new functionality.

#### Changes Required

**File**: `scripts/tests/test_cli.py`

**Change 1**: Update `_parse_sprint_args` helper (lines 672-701)

Add short flags and `--skip` to match the updated cli.py:

```python
def _parse_sprint_args(self, args: list[str]) -> argparse.Namespace:
    """Parse arguments using the same parser as main_sprint."""
    parser = argparse.ArgumentParser(prog="ll-sprint")
    subparsers = parser.add_subparsers(dest="command")

    # create
    create = subparsers.add_parser("create")
    create.add_argument("name")
    create.add_argument("--issues", required=True)
    create.add_argument("--description", "-d", default="")
    create.add_argument("-w", "--max-workers", type=int, default=4)
    create.add_argument("-t", "--timeout", type=int, default=3600)
    create.add_argument("--skip", type=str, default=None)

    # run
    run = subparsers.add_parser("run")
    run.add_argument("sprint")
    run.add_argument("--dry-run", "-n", action="store_true")
    run.add_argument("-w", "--max-workers", type=int)
    run.add_argument("-t", "--timeout", type=int)
    run.add_argument("--config", type=Path)
    run.add_argument("--resume", "-r", action="store_true")
    run.add_argument("--skip", type=str, default=None)
    # ... rest unchanged
```

**Change 2**: Add tests for short flags

```python
def test_create_with_short_flags(self) -> None:
    """create subcommand accepts short flags."""
    args = self._parse_sprint_args(
        ["create", "sprint-1", "--issues", "BUG-001", "-w", "4", "-t", "1800"]
    )
    assert args.max_workers == 4
    assert args.timeout == 1800

def test_run_with_short_flags(self) -> None:
    """run subcommand accepts short flags."""
    args = self._parse_sprint_args(
        ["run", "sprint-1", "-w", "4", "-t", "1800"]
    )
    assert args.max_workers == 4
    assert args.timeout == 1800

def test_create_with_skip(self) -> None:
    """create subcommand accepts --skip."""
    args = self._parse_sprint_args(
        ["create", "sprint-1", "--issues", "BUG-001,BUG-002", "--skip", "BUG-002"]
    )
    assert args.skip == "BUG-002"

def test_run_with_skip(self) -> None:
    """run subcommand accepts --skip."""
    args = self._parse_sprint_args(
        ["run", "sprint-1", "--skip", "BUG-002,BUG-003"]
    )
    assert args.skip == "BUG-002,BUG-003"
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli.py`

---

### Phase 4: Update Documentation

#### Overview

Update the CLI tools audit document to reflect the standardized arguments.

#### Changes Required

**File**: `docs/CLI-TOOLS-AUDIT.md`

Update the argument parsing comparison table (lines 123-136):

```markdown
## Argument Parsing Comparison

| Argument | ll-auto | ll-parallel | ll-sprint |
|----------|---------|-------------|-----------|
| `--dry-run/-n` | ✅ | ✅ | ✅ (run only) |
| `--resume/-r` | ✅ | ✅ | ✅ (run only) |
| `--max-issues/-m` | ✅ | ✅ | ❌ |
| `--only` | ✅ | ✅ | Uses `--issues` |
| `--skip` | ✅ | ✅ | ✅ |
| `--config` | ✅ | ✅ | ✅ (partial) |
| `--quiet/-q` | ❌ | ✅ | ❌ |
| `--timeout/-t` | ❌ | ✅ | ✅ |
| `--workers/-w` | ❌ | ✅ | ✅ (`--max-workers/-w`) |
```

#### Success Criteria

**Automated Verification**:
- [ ] Markdown lint passes: `markdownlint docs/CLI-TOOLS-AUDIT.md`

---

## Testing Strategy

### Unit Tests

- Test short flag parsing (`-t`, `-w`)
- Test `--skip` argument parsing
- Test combined flags (e.g., `-w 4 -t 1800`)

### Integration Tests

- Create sprint with short flags: `ll-sprint create test --issues BUG-001 -w 4 -t 1800`
- Create sprint with skip: `ll-sprint create test --issues BUG-001,BUG-002 --skip BUG-002`
- Run sprint with skip: `ll-sprint run test --skip BUG-002`

## References

- Original issue: `.issues/enhancements/P3-ENH-184-standardize-cli-argument-flags.md`
- CLI audit: `docs/CLI-TOOLS-AUDIT.md:123-136`
- ll-parallel timeout pattern: `scripts/little_loops/cli.py:198-204`
- ll-parallel workers pattern: `scripts/little_loops/cli.py:159-165`
- ll-auto skip pattern: `scripts/little_loops/cli.py:100-105`
