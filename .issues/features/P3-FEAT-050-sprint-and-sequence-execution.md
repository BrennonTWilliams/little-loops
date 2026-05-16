---
discovered_commit: d13e53f
discovered_branch: main
discovered_date: 2026-01-14T00:00:00Z
---

# FEAT-050: Sprint and Sequence Execution

## Summary

Add ability to define named "sprints" or "sequences" (predefined groups of issues) and execute them via CLI. This enables planning work in batches (e.g., "sprint-1", "q1-bug-fixes") and executing them as a unit.

## Motivation

Currently, `ll-auto` and `ll-parallel` can only execute issues based on:
- Priority level (P0-P5)
- Category (bugs/features/enhancements)
- Ad-hoc filters (`--only`, `--skip`)

This works for general processing but doesn't support common workflows:
1. **Sprint planning**: Define a sprint with specific issues to complete
2. **Themed batches**: Group issues by theme (e.g., "perf-improvements", "security-audit")
3. **Ad-hoc sequences**: Quick way to create and execute a custom issue list
4. **Replayable runs**: Re-execute the same set of issues later

### Example Use Cases

```bash
# Define a sprint
ll-sprint create sprint-1 --issues BUG-001,BUG-002,FEAT-010,FEAT-015

# Execute a sprint (sequentially)
ll-sprint run sprint-1

# Execute a sprint (in parallel)
ll-sprint run sprint-1 --parallel

# List available sprints
ll-sprint list

# Show sprint contents
ll-sprint show sprint-1
```

## Proposed Implementation

### 1. Sprint Storage Format

**File**: `.sprints/<name>.yaml`

```yaml
name: sprint-1
description: "Q1 Performance and Security Improvements"
created: "2026-01-14T00:00:00Z"
issues:
  - BUG-001
  - BUG-002
  - FEAT-010
  - FEAT-015
options:
  # Optional: default execution options
  max_iterations: 100
  timeout: 3600
  parallel: false  # Use ll-auto or ll-parallel
```

### 2. New CLI: `ll-sprint`

**File**: `scripts/little_loops/cli.py` - Add `main_sprint()` entry point

```python
def main_sprint() -> int:
    """Entry point for ll-sprint command."""
    parser = argparse.ArgumentParser(
        description="Manage and execute sprint/sequence definitions"
    )
    subparsers = parser.add_subparsers(dest="command")

    # create subcommand
    create = subparsers.add_parser("create", help="Create a new sprint")
    create.add_argument("name", help="Sprint name")
    create.add_argument("--issues", help="Comma-separated issue IDs")
    create.add_argument("--description", help="Sprint description")

    # run subcommand
    run = subparsers.add_parser("run", help="Execute a sprint")
    run.add_argument("sprint", help="Sprint name")
    run.add_argument("--dry-run", action="store_true")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List sprints")

    # show subcommand
    show = subparsers.add_parser("show", help="Show sprint details")
    show.add_argument("sprint", help="Sprint name")

    # delete subcommand
    delete = subparsers.add_parser("delete", help="Delete a sprint")
    delete.add_argument("sprint", help="Sprint name")
```

### 3. Sprint Management Module

**File**: `scripts/little_loops/sprint.py` (new)

```python
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class Sprint:
    name: str
    description: str
    issues: list[str]
    created: str
    options: dict | None = None

class SprintManager:
    def __init__(self, sprints_dir: Path = Path(".sprints")):
        self.sprints_dir = sprints_dir
        self.sprints_dir.mkdir(exist_ok=True)

    def create(self, name: str, issues: list[str], description: str = "") -> Sprint:
        """Create a new sprint."""

    def load(self, name: str) -> Sprint | None:
        """Load a sprint by name."""

    def list(self) -> list[Sprint]:
        """List all sprints."""

    def delete(self, name: str) -> bool:
        """Delete a sprint."""

    def validate_issues(self, issues: list[str], config: BRConfig) -> list[str]:
        """Validate that issue IDs exist and return valid ones."""
```

## Location

- **New**: `scripts/little_loops/sprint.py` - Sprint dataclass and SprintManager
- **Modified**: `scripts/little_loops/cli.py` - Add main_sprint() entry point
- **Modified**: `scripts/pyproject.toml` - Add ll-sprint entry point
- **New**: `.claude/commands/ll_create_sprint.md` - Slash command for interactive sprint creation
- **New**: `.sprints/` directory (gitignored? user choice)

## Current Behavior

- No way to define named groups of issues
- Must use ad-hoc filters each time
- Can't save/share execution plans

## Expected Behavior

```bash
# Create a sprint
$ ll-sprint create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
Created sprint: sprint-1
  Issues: BUG-001, FEAT-010

# Run it (sequential mode)
$ ll-sprint run sprint-1
Running sprint: sprint-1
Processing: BUG-001
Processing: FEAT-010

# Run it (parallel mode)
$ ll-sprint run sprint-1 --parallel
Running sprint: sprint-1 (parallel with 4 workers)
Processing: BUG-001, FEAT-010

# List sprints
$ ll-sprint list
Available sprints:
  sprint-1  - Q1 fixes
  perf-work - Performance improvements

# Show details
$ ll-sprint show sprint-1
Sprint: sprint-1
Description: Q1 fixes
Created: 2026-01-14
Issues:
  - BUG-001 (P0): Critical crash bug
  - FEAT-010 (P2): Add user settings
```

## Acceptance Criteria

- [ ] `scripts/little_loops/sprint.py` module created with Sprint dataclass
- [ ] `ll-sprint create` creates `.sprints/<name>.yaml` files
- [ ] `ll-sprint list` lists all available sprints
- [ ] `ll-sprint show <name>` displays sprint details and validates issues exist
- [ ] `ll-sprint run <name>` executes issues in the sprint (sequential mode)
- [ ] `ll-sprint run <name> --parallel` executes issues in parallel
- [ ] `ll-sprint delete <name>` removes sprint files
- [ ] `/ll:create-sprint` slash command creates sprint definitions interactively
- [ ] Sprint YAML format documented in README or docs/
- [ ] Tests for sprint management functions
- [ ] Integration test: create, run, verify sprint execution

## Impact

- **Severity**: Low - Quality of life improvement
- **Effort**: Low - Self-contained feature
- **Risk**: Low - New functionality, doesn't change existing behavior

## Dependencies

None

## Blocked By

None

## Blocks

None

## Related

- ENH-016: Dependency-aware sequencing for ll-auto
- ENH-017: Dependency-aware scheduling for ll-parallel

## Labels

`feature`, `cli`, `sprint`, `workflow`

---

## Status

**Completed** | Created: 2026-01-14 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sprint.py` - Created Sprint dataclass and SprintManager for sprint CRUD operations
- `scripts/little_loops/cli.py` - Added main_sprint() entry point with create, run, list, show, delete subcommands
- `scripts/pyproject.toml` - Added ll-sprint entry point
- `scripts/tests/test_sprint.py` - Added unit tests for sprint module
- `scripts/tests/test_sprint_integration.py` - Added integration tests
- `scripts/tests/test_cli.py` - Added CLI argument parsing tests

### Verification Results
- Tests: PASS (35/35 tests passed)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
