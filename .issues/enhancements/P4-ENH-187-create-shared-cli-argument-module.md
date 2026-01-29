---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-187: Create shared CLI argument module

## Summary

Common CLI arguments are duplicated across ll-auto, ll-parallel, and ll-sprint entry points. Extracting these to a shared module would reduce duplication and ensure consistency.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Listed as "Low Priority" standardization opportunity
- Multiple tools define similar arguments: --dry-run, --config, --timeout, etc.

## Current Behavior

Each tool in `cli.py` defines its own arguments:
- `main_auto()` at lines 25-112
- `main_parallel()` at lines 115-299
- `main_sprint()` at lines 1261-1361

Common arguments repeated:
- `--dry-run/-n` - All three tools
- `--config` - All three tools
- `--timeout` - parallel and sprint
- `--max-workers` - parallel and sprint

## Expected Behavior

Shared argument definitions in a dedicated module that each tool imports and uses, ensuring consistent naming, help text, and defaults.

## Proposed Solution

1. Create `scripts/little_loops/cli_args.py`:

```python
"""Shared CLI argument definitions for little-loops tools."""

import argparse
from typing import Callable

def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to all tools."""
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )

def add_parallel_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for parallel execution tools."""
    parser.add_argument(
        "-w", "--max-workers",
        type=int,
        default=2,
        help="Maximum parallel workers (default: 2)"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=3600,
        help="Timeout per issue in seconds (default: 3600)"
    )

def add_issue_filter_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for filtering issues."""
    parser.add_argument(
        "--only",
        nargs="*",
        help="Only process these specific issues"
    )
    parser.add_argument(
        "--skip",
        nargs="*",
        help="Skip these specific issues"
    )

def add_resume_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for resume capability."""
    parser.add_argument(
        "-r", "--resume",
        action="store_true",
        help="Resume from previous state"
    )

def add_verbosity_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for output verbosity."""
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output"
    )
```

2. Update each tool to use shared definitions:

```python
from little_loops.cli_args import add_common_args, add_parallel_args

def main_sprint():
    parser = argparse.ArgumentParser(...)
    add_common_args(parser)
    add_parallel_args(parser)
    # Tool-specific args...
```

## Files to Modify

- Create: `scripts/little_loops/cli_args.py`
- Modify: `scripts/little_loops/cli.py` - Import and use shared args

## Impact

- **Priority**: P4 (Low - code quality improvement)
- **Effort**: Medium (refactoring across multiple entry points)
- **Risk**: Low (no functional change, just reorganization)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| audit | docs/CLI-TOOLS-AUDIT.md | Argument Parsing Comparison |

## Labels

`enhancement`, `refactoring`, `code-quality`, `captured`

---

## Status

**Open** | Created: 2026-01-29 | Priority: P4
