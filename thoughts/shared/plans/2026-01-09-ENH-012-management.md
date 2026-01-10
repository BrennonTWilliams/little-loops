# ENH-012: Display CLI Logo on Startup - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-012-display-cli-logo-on-startup.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

CLI tools (`ll-auto` and `ll-parallel`) start without any branding. The logo asset already exists at `assets/ll-cli-logo.txt`:

```
 ╭╮      ╭╮
 ╰┼──────┼╯
  little loops
```

### Key Discoveries
- Logo asset exists at `assets/ll-cli-logo.txt:1-3`
- `main_auto()` entry point: `scripts/little_loops/cli.py:19-106`
- `main_parallel()` entry point: `scripts/little_loops/cli.py:109-275`
- Init completion message: `commands/init.md:541-560`
- Argument parsing completes at line 87 (`main_auto`) and line 220 (`main_parallel`)

## Desired End State

- `ll-auto` displays the logo before processing begins
- `ll-parallel` displays the logo before processing begins (when not in quiet mode)
- `/ll:init` displays the logo in the completion message
- Missing logo file handled gracefully (no crash)

### How to Verify
- Run `ll-auto --dry-run` and verify logo appears
- Run `ll-parallel --dry-run` and verify logo appears
- Run `ll-parallel --dry-run --quiet` and verify logo does NOT appear
- Test with missing logo file (rename temporarily)

## What We're NOT Doing

- Not adding color to the logo - keep it simple ASCII
- Not adding version information to the logo display
- Not creating a configuration option to disable logo display (quiet mode covers this)

## Problem Analysis

The CLI tools lack visual branding, making it harder for users to quickly identify little-loops output in terminal history.

## Solution Approach

1. Create a new `logo.py` module with `get_logo()` and `print_logo()` functions
2. Integrate into CLI entry points after argument parsing
3. Respect quiet mode in `main_parallel()`
4. Update init.md completion message to include logo

## Implementation Phases

### Phase 1: Create logo.py Module

#### Overview
Create a simple utility module to read and display the ASCII logo.

#### Changes Required

**File**: `scripts/little_loops/logo.py` [CREATE]
**Changes**: New file with two functions

```python
"""Logo display utilities for little-loops CLI.

Provides functions to read and display the ASCII art logo.
"""

from __future__ import annotations

from pathlib import Path


def get_logo() -> str | None:
    """Read the CLI logo from assets.

    Returns:
        Logo text content, or None if file not found.
    """
    logo_path = Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"
    if logo_path.exists():
        return logo_path.read_text()
    return None


def print_logo() -> None:
    """Print the CLI logo if available.

    Silent no-op if logo file is not found.
    """
    if logo := get_logo():
        print(logo)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Import works: `python -c "from little_loops.logo import print_logo; print_logo()"`

---

### Phase 2: Integrate with CLI Tools

#### Overview
Add logo display to `main_auto()` and `main_parallel()` entry points.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
1. Add import for logo module
2. Add `print_logo()` call in `main_auto()` after line 87
3. Add `print_logo()` call in `main_parallel()` after line 225 (after logger creation), only if not quiet

**At line 16**, add import:
```python
from little_loops.logo import print_logo
```

**In `main_auto()`, after line 87** (`args = parser.parse_args()`), add:
```python
    print_logo()
```

**In `main_parallel()`, after line 225** (`logger = Logger(verbose=not args.quiet)`), add:
```python
    if not args.quiet:
        print_logo()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `ll-auto --help` shows logo before help text
- [ ] `ll-parallel --dry-run` shows logo
- [ ] `ll-parallel --dry-run --quiet` does NOT show logo

---

### Phase 3: Update Init Command

#### Overview
Add logo display to the init command completion message.

#### Changes Required

**File**: `commands/init.md`
**Changes**: Insert logo display in Section 10 completion message between the header separator and "Created:" line

**At lines 546-548**, update from:
```
================================================================================

Created: .claude/ll-config.json
```

To:
```
================================================================================

 ╭╮      ╭╮
 ╰┼──────┼╯
  little loops

Created: .claude/ll-config.json
```

#### Success Criteria

**Automated Verification**:
- [ ] Command file syntax is valid markdown

**Manual Verification**:
- [ ] Review `commands/init.md` to confirm logo is in the completion message

---

## Testing Strategy

### Unit Tests
- Test `get_logo()` returns string when file exists
- Test `get_logo()` returns None when file missing
- Test `print_logo()` doesn't crash when file missing

### Integration Tests
- Run `ll-auto --help` and verify output contains logo
- Run `ll-parallel --dry-run` and verify output contains logo

## References

- Original issue: `.issues/enhancements/P4-ENH-012-display-cli-logo-on-startup.md`
- Logo asset: `assets/ll-cli-logo.txt`
- CLI entry points: `scripts/little_loops/cli.py:19-106`, `scripts/little_loops/cli.py:109-275`
- Init completion: `commands/init.md:541-560`
