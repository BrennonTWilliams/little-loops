---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-188: Add quiet mode to ll-auto and ll-sprint

## Summary

ll-parallel supports `--quiet/-q` for suppressing non-essential output, but ll-auto and ll-sprint lack this option. Adding quiet mode improves consistency and is useful for CI/scripted environments.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Listed as "Low Priority" standardization opportunity
- Consistency Matrix shows only ll-parallel has quiet mode

## Current Behavior

| Tool | Quiet Mode |
|------|------------|
| ll-auto | ❌ Always verbose |
| ll-parallel | ✅ `--quiet/-q` |
| ll-sprint | ❌ Always verbose |

## Expected Behavior

All three tools support `--quiet/-q` flag that:
- Suppresses progress messages
- Suppresses informational logging
- Still shows errors and warnings
- Still shows final summary

## Proposed Solution

1. Add `--quiet/-q` to ll-auto:
   - Import `add_quiet_arg` from `cli_args` (already imported)
   - Add to `add_common_auto_args` function or add separately to `main_auto`
   - Pass `quiet=args.quiet` to `AutoManager` (or create logger with `verbose=not args.quiet`)

2. Add `--quiet/-q` to ll-sprint:
   - Add `add_quiet_arg(run_parser)` to the run subcommand
   - Pass quiet flag to SprintManager or execution context

3. Integration pattern (following ll-parallel example at `cli.py:224`):

```python
# In main_auto after args.parse_args()
logger = Logger(verbose=not args.quiet)
# Or pass to AutoManager and let it create logger
```

Note: Logger class uses `verbose` bool, not log levels. Quiet mode = `verbose=False`.

## Files to Modify

- `scripts/little_loops/cli_args.py:162-173` - Add `add_quiet_arg` call to `add_common_auto_args`
- `scripts/little_loops/cli.py:82-93` - Add quiet arg to ll-auto (via `add_common_auto_args`)
- `scripts/little_loops/cli.py:102-110` - Pass quiet flag to AutoManager
- `scripts/little_loops/issue_manager.py` - Add quiet parameter to AutoManager, pass to Logger
- `scripts/little_loops/cli.py:1322-1333` - Add quiet arg to ll-sprint run subcommand
- `scripts/little_loops/cli.py` - Pass quiet flag to SprintManager/execution

Note: `add_quiet_arg` already exists in `cli_args.py:121-128`. The Logger class already supports verbose control.

## Impact

- **Priority**: P4 (Low - nice to have feature)
- **Effort**: Low (simple argument and logging level change)
- **Risk**: Very Low (additive feature)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| audit | docs/CLI-TOOLS-AUDIT.md | Consistency Matrix |

## Labels

`enhancement`, `ll-auto`, `ll-sprint`, `consistency`, `cli`, `captured`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli_args.py` - Added `add_quiet_arg(parser)` to `add_common_auto_args` function
- `scripts/little_loops/cli.py` - Added `add_quiet_arg(run_parser)` to ll-sprint run subcommand
- `scripts/little_loops/cli.py` - Pass `verbose=not args.quiet` to AutoManager
- `scripts/little_loops/cli.py` - Pass `verbose=not args.quiet` to Logger in `_cmd_sprint_run`
- `scripts/little_loops/issue_manager.py` - Added `verbose: bool = True` parameter to AutoManager.__init__
- `scripts/tests/test_cli.py` - Added tests for quiet flag parsing in ll-auto and ll-sprint
- `scripts/tests/test_issue_manager.py` - Added tests for AutoManager verbose parameter

### Verification Results
- Tests: PASS (all 6 new tests pass)
- Lint: PASS (ruff check passed)
- Types: PASS (mypy check passed)

---

## Status

**Completed** | Created: 2026-01-29 | Priority: P4
