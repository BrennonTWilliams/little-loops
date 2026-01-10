---
discovered_commit: null
discovered_branch: main
discovered_date: 2026-01-09T00:00:00Z
discovered_by: manual
---

# ENH-012: Display CLI Logo on Startup

## Summary

Display the `ll-cli-logo.txt` ASCII art at startup of CLI tools and at completion of initialization to provide brand recognition and visual confirmation of the little-loops plugin.

## Motivation

- Provides immediate visual feedback that little-loops tools are running
- Reinforces brand identity across CLI interactions
- Creates a polished, professional CLI experience
- Helps users quickly identify little-loops output in terminal history

## Proposed Implementation

### 1. Logo Asset

Use existing logo file at `assets/ll-cli-logo.txt`:

```
╭╮      ╭╮
╰┼──────┼╯
 little loops
```

### 2. Logo Display Helper

Create `scripts/little_loops/logo.py`:

```python
from pathlib import Path

def get_logo() -> str | None:
    """Read the CLI logo from assets, returning None if not found."""
    logo_path = Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"
    if logo_path.exists():
        return logo_path.read_text()
    return None

def print_logo() -> None:
    """Print the CLI logo if available."""
    if logo := get_logo():
        print(logo)
```

### 3. CLI Tools Integration

**`scripts/little_loops/cli.py`**

In `main_auto()` after argument parsing (~line 88):
```python
from little_loops.logo import print_logo
print_logo()
```

In `main_parallel()` after argument parsing (~line 221):
```python
from little_loops.logo import print_logo
print_logo()
```

### 4. Init Command Integration

**`commands/init.md`** - Section 10 (Completion Message)

Add logo display after the "INITIALIZATION COMPLETE" header, before the "Created:" line.

## Location

- **New**: `scripts/little_loops/logo.py`
- **Modified**: `scripts/little_loops/cli.py`
- **Modified**: `commands/init.md`

## Current Behavior

CLI tools start without any branding/logo display.

## Expected Behavior

- `ll-auto` displays the logo before processing begins
- `ll-parallel` displays the logo before processing begins
- `/ll:init` displays the logo in the completion message

## Acceptance Criteria

- [ ] Logo displays at start of `ll-auto`
- [ ] Logo displays at start of `ll-parallel`
- [ ] Logo displays at end of `/ll:init`
- [ ] Missing logo file handled gracefully (no crash)
- [ ] Logo renders correctly in terminal

## Impact

- **Severity**: Low - Cosmetic improvement
- **Effort**: Small - Simple file read and print
- **Risk**: Low - Non-functional change, graceful fallback

## Dependencies

None

## Blocked By

None

## Blocks

None

## Labels

`enhancement`, `cli`, `branding`

---

## Status

**Completed** | Created: 2026-01-09 | Completed: 2026-01-09 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/logo.py`: New module with `get_logo()` and `print_logo()` functions
- `scripts/little_loops/cli.py`: Added logo display in `main_auto()` and `main_parallel()` entry points
- `commands/init.md`: Added logo to completion message in Section 10

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS

### Notes
- Logo displays at startup of `ll-auto` (always) and `ll-parallel` (when not in quiet mode)
- Missing logo file handled gracefully (silent no-op)
- Logo renders correctly in terminal
