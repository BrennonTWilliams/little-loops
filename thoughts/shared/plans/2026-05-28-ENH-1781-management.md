# ENH-1781: Create shared output formatting utility - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-1781-create-shared-output-formatting-utility.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

`scripts/little_loops/cli/output.py` (134 lines) is the existing shared output module imported by 34 files. It provides:
- `colorize()` at line 107 — wraps text in ANSI escape codes, respects `_USE_COLOR`
- `configure_output()` at line 59 — one-time color init from `CliConfig`
- `terminal_width()` at line 26 — column count via `shutil.get_terminal_size`
- `terminal_size()` at line 16 — (cols, rows) tuple
- `wrap_text()` at line 31 — textwrap.fill with indent (defined but UNUSED)
- `print_json()` at line 114 — `json.dumps(data, indent=2)` to stdout
- `format_relative_time()` at line 119 — "3m ago" human strings
- `use_color_enabled()` at line 102 — current `_USE_COLOR` accessor
- `PRIORITY_COLOR` / `TYPE_COLOR` at lines 43-56 — module-level SGR code dicts
- `_USE_COLOR` at line 41 — `isatty() and not NO_COLOR`

### Key Discoveries
- **`_strip_ansi()` duplicated in 4 files** at `cli/loop/_helpers.py:58`, `cli/loop/info.py:257`, `cli/issues/show.py:278`, `cli/loop/layout.py:21` — each defines its own `_ANSI_RE` regex and `_strip_ansi()` function
- **Box-drawing characters duplicated in 5+ files** at `cli/issues/show.py:300`, `cli/issues/impact_effort.py:114`, `cli/issues/clusters.py`, `cli/sprint/_helpers.py:73`, `cli/loop/layout.py:612` — `─│┌┐└┘├┤┬┴┼` defined locally in each renderer
- **`_STATUS_SYMBOLS` only in `cli/doctor.py:12`** — ✓/○/✗ mapping used ad-hoc for capability tables
- **`_progress_bar()` only in `cli/ctx_stats.py:92`** — `|####  |` bar with simple scaling, never exported
- **`FORCE_COLOR` NOT checked** — only `NO_COLOR` and `isatty()` control `_USE_COLOR`; the issue requires adding `FORCE_COLOR` support
- **Logger naming overlap** at `logger.py:17` — `Logger` has timestamped `success()`, `error()`, `warning()`, `info()` methods; the new user-facing helpers must be differentiated by omitting timestamps and using direct `sys.stdout`/`sys.stderr`

### Patterns to Follow
- `add_json_arg()` at `cli_args.py:197` — shared argparse helper pattern (take `parser`, add flag, return `None`)
- `TestAddJsonArg` at `test_cli_args.py:482` — test pattern for shared arg helpers (5 test methods)
- `capsys` fixture + `patch.object(output_mod, "_USE_COLOR", bool)` for output tests
- `patch.dict("os.environ", {"NO_COLOR": "1"})` for env-var tests
- `FlushTracker` at `test_logger.py:572` — mock stream duck-type for flush verification
- `CliColorsLoggerConfig` at `config/cli.py:14` — SGR-code-override dataclass pattern
- `PRIORITY_COLOR.update(...)` in `configure_output()` at line 80 — merging config values pattern

## Desired End State

All `ll-*` CLIs use message helpers (`success`, `error`, `warning`, `info`, `hint`) and structured formatters (`table`, `status_block`, `progress`) from the shared `cli/output.py` module, with consistent icons, colors, and `FORCE_COLOR`/`NO_COLOR` awareness.

### How to Verify
- `python -m pytest scripts/tests/test_cli_output.py -v` — all new tests pass
- Visual: `ll-issues list` and `ll-loop info` output uses new message helpers with consistent icons
- `NO_COLOR=1 ll-issues list` produces no ANSI codes
- `FORCE_COLOR=1 ll-issues list | cat` produces ANSI codes despite pipe

## What We're NOT Doing

- Not creating a new module file (Option A already decided — extend `cli/output.py`)
- Not migrating all ~20 CLIs (only `ll-issues`, `ll-loop`, `ll-sprint` per success metrics)
- Not adding JSON output mode (covered by ENH-1780)
- Not changing any CLI's behavior or output structure (only formatting implementation)
- Not refactoring Logger class or its method names
- Not adding `rich`/`colorama`/`termcolor` dependencies (all formatting remains raw ANSI)
- Not adding `add_plain_arg()` helper (deferred — no consumer needs it yet; `--json` flags already work)

## Problem Analysis

~20 CLI entry points each implement their own output formatting, leading to inconsistent UX, duplicated box-drawing/ANSI-stripping code, and varying quality. The existing `cli/output.py` module provides low-level primitives (`colorize`, `terminal_width`) but no high-level helpers (`success`, `table`, `progress`), so every CLI builds these from scratch.

## Solution Approach

Extend `cli/output.py` with five message helpers, three structured formatters, shared constants, and `FORCE_COLOR` support. Follow existing patterns: color code dicts for configurable colors, module-level globals for state, `configure_output()` as the single init point.

## Code Reuse & Integration

- **Reusable existing code**: `colorize()` at `output.py:107`, `terminal_width()` at `output.py:26`, `_USE_COLOR` at `output.py:41`, `configure_output()` at `output.py:59`, `PRIORITY_COLOR`/`TYPE_COLOR` at `output.py:43-56`, `CliColorsConfig` dataclass hierarchy at `config/cli.py:125`, `add_json_arg()` pattern at `cli_args.py:197`
- **Patterns to follow**: `format_result_*()` dispatch convention, `capsys` + `patch.object` test pattern, `CliColorsLoggerConfig` SGR override dataclass pattern
- **New code justification**: Message helpers and structured formatters don't exist anywhere — `Logger.success()` has timestamps and instance-level state; `_progress_bar()`/`_STATUS_SYMBOLS` are unexported local functions

## Implementation Phases

### Phase 0: Write Tests — Red (TDD Mode)

#### Overview
Write tests for all new functions BEFORE implementation. These must FAIL against the current codebase.

#### Test Files
- **Extend `scripts/tests/test_cli_output.py`** with new test classes

#### Test Classes to Add

```python
class TestMessageHelpers:
    """Tests for success(), error(), warning(), info(), hint()."""
    # - Each prints to correct stream (stdout vs stderr)
    # - Each includes icon prefix when color enabled
    # - Plain text when _USE_COLOR is False
    # - Respects set_output_mode("plain") — no icons
    # - Respects set_output_mode("json") — no direct output (not tested here)

class TestStripAnsi:
    """Tests for strip_ansi()."""
    # - Strips SGR escape sequences
    # - Passes through plain text unchanged
    # - Handles empty string

class TestBoxConstants:
    """Tests for box-drawing character constants."""
    # - H, V, TL, TR, BL, BR, ML, MR are single Unicode chars

class TestTable:
    """Tests for table()."""
    # - Returns string with headers and rows
    # - Auto-sizes columns to fit content
    # - Respects max_col_width (truncates with ...)
    # - Handles empty rows gracefully

class TestStatusBlock:
    """Tests for status_block()."""
    # - Returns aligned key-value pairs
    # - Handles varying key lengths

class TestProgress:
    """Tests for progress()."""
    # - Returns "|####  |" style bar
    # - Scales correctly at 0%, 50%, 100%
    # - Handles zero total (empty bar)
    # - Respects custom width

class TestForceColor:
    """Tests for FORCE_COLOR env var support."""
    # - FORCE_COLOR=1 forces color even without TTY
    # - FORCE_COLOR=0 does not force
    # - NO_COLOR overrides FORCE_COLOR

class TestOutputMode:
    """Tests for set_output_mode() / get_output_mode()."""
    # - Default mode is "human"
    # - Changes mode globally
    # - get_output_mode() reflects current mode
```

#### Red Validation
Expected: `python -m pytest scripts/tests/test_cli_output.py -v -k "TestMessage or TestStrip or TestBox or TestTable or TestStatus or TestProgress or TestForce or TestOutput"` returns non-zero with `ImportError` (functions don't exist yet — legitimate red).

---

### Phase 1: Add shared constants and utilities to cli/output.py

#### Overview
Add `strip_ansi()`, `FORCE_COLOR` support in `configure_output()`, and box-drawing constants. No API changes — additive only.

#### Changes Required

**File**: `scripts/little_loops/cli/output.py`
**Changes**:
1. Add `import re` at top
2. Add `_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")` — broad pattern matching all ANSI escape sequences
3. Add `strip_ansi(text: str) -> str` — returns `re.sub(_ANSI_RE, "", text)`
4. Add box-drawing constants: `BOX_H = "─"`, `BOX_V = "│"`, `BOX_TL = "┌"`, `BOX_TR = "┐"`, `BOX_BL = "└"`, `BOX_BR = "┘"`, `BOX_ML = "├"`, `BOX_MR = "┤"`
5. Update `_USE_COLOR` initialization and `configure_output()` to support `FORCE_COLOR`:
   - After NO_COLOR check, add: `force_color = os.environ.get("FORCE_COLOR", "") == "1"`
   - `_USE_COLOR = force_color or (sys.stdout.isatty() and not no_color_env)`

#### Migration of duplicate code
Migrate the 4 `_strip_ansi()`/`_ANSI_RE` definitions to import from `cli.output`:
- `cli/loop/_helpers.py:58` → import `strip_ansi` from `cli.output`
- `cli/loop/info.py:257` → import `strip_ansi` from `cli.output`
- `cli/issues/show.py:278` → import `strip_ansi` from `cli.output`
- `cli/loop/layout.py:21` → import `strip_ansi` from `cli.output`

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli_output.py -v -k "TestStrip or TestBox or TestForce"` passes
- [ ] `python -m pytest scripts/tests/test_cli_output.py -v` — all existing tests still pass
- [ ] `ruff check scripts/` passes

---

### Phase 2: Add message helpers (success, error, warning, info, hint)

#### Overview
Add five message helper functions that print to stdout (or stderr for error) with consistent icons and colors, respecting `_USE_COLOR` and `NO_COLOR`.

#### Changes Required

**File**: `scripts/little_loops/cli/output.py`
**Changes**:

```python
# Icons (no emoji — Unicode symbols only, consistent with existing ✓/✗ pattern)
_ICONS = {
    "success": "✓",  # ✓
    "error": "✗",    # ✗
    "warning": "⚠",  # ⚠
    "info": "ℹ",     # ℹ
    "hint": "›",     # ›
}

def success(msg: str) -> None:
    """Print a success message to stdout."""
    icon = f"{_ICONS['success']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '32')}", flush=True)

def error(msg: str) -> None:
    """Print an error message to stderr."""
    icon = f"{_ICONS['error']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '38;5;208')}", file=sys.stderr, flush=True)

def warning(msg: str) -> None:
    """Print a warning message to stdout."""
    icon = f"{_ICONS['warning']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '33')}", flush=True)

def info(msg: str) -> None:
    """Print an informational message to stdout."""
    icon = f"{_ICONS['info']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '36')}", flush=True)

def hint(msg: str) -> None:
    """Print a hint/dim message to stdout."""
    icon = f"{_ICONS['hint']} " if _USE_COLOR else ""
    print(f"{colorize(icon + msg, '2')}", flush=True)
```

**Key design differences from Logger**:
- No timestamps (Logger adds `[HH:MM:SS]`)
- Icons only when color enabled (plain text otherwise)
- `error()` → stderr; all others → stdout
- Module-level functions (not instance methods)
- Use `flush=True` for non-TTY compatibility (follows BUG-876 pattern)

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli_output.py -v -k "TestMessage"` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes

---

### Phase 3: Add structured formatters (table, status_block, progress)

#### Overview
Add `table()`, `status_block()`, and `progress()` functions. These are pure string-returning functions (no print side effects).

#### Changes Required

**File**: `scripts/little_loops/cli/output.py`
**Changes**:

```python
def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str:
    """Return an auto-width box-drawn table string."""
    pass  # Implementation follows box-drawing patterns from show.py + impact_effort.py

def status_block(items: dict[str, str]) -> str:
    """Return aligned key-value pairs string."""
    pass  # Implementation similar to _render_card metadata lines

def progress(current: int, total: int, width: int = 20) -> str:
    """Return a |####  | progress bar of ``width`` columns."""
    pass  # Implementation generalizes ctx_stats.py:_progress_bar at line 92
```

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli_output.py -v -k "TestTable or TestStatus or TestProgress"` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes

---

### Phase 4: Add set_output_mode() and FORCE_COLOR support

#### Overview
Add `set_output_mode()` / `get_output_mode()` for human/json/plain toggling. Already added FORCE_COLOR in Phase 1.

#### Changes Required

**File**: `scripts/little_loops/cli/output.py`
**Changes**:
```python
from typing import Literal

_OUTPUT_MODE: Literal["human", "json", "plain"] = "human"

def set_output_mode(mode: Literal["human", "json", "plain"]) -> None:
    """Set the global output mode."""
    global _OUTPUT_MODE
    _OUTPUT_MODE = mode

def get_output_mode() -> Literal["human", "json", "plain"]:
    """Return the current global output mode."""
    return _OUTPUT_MODE
```

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli_output.py -v -k "TestOutput"` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes

---

### Phase 5: Migrate CLIs incrementally (proof-of-concept)

#### Overview
Migrate `ll-issues list` as proof-of-concept, replacing direct `colorize()` calls with message helpers where appropriate. Then migrate `ll-loop info` and `ll-sprint show`.

#### Changes Required

**File**: `scripts/little_loops/cli/issues/list_cmd.py`
**Changes**: Replace `colorize()` calls for status messages with message helpers

**File**: `scripts/little_loops/cli/loop/info.py`
**Changes**: Replace `_strip_ansi()` with import from `cli.output`

**File**: `scripts/little_loops/cli/loop/layout.py`
**Changes**: Replace `_ANSI_ESCAPE_RE` with import from `cli.output`

**File**: `scripts/little_loops/cli/issues/show.py`
**Changes**: Replace `_ANSI_RE`/`_strip_ansi()` with import from `cli.output`

**File**: `scripts/little_loops/cli/loop/_helpers.py`
**Changes**: Replace `_ANSI_RE` with import from `cli.output`

#### Success Criteria
- [ ] `python -m pytest scripts/tests/ -v` — all existing tests pass
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes

---

### Phase 6: Documentation

#### Overview
Extend `docs/reference/API.md` and `docs/reference/OUTPUT_STYLING.md` with new function signatures.

#### Changes Required
**File**: `docs/reference/API.md` (lines 111-161) — extend cli.output section
**File**: `docs/reference/OUTPUT_STYLING.md` (319 lines) — add new helper signatures

## Testing Strategy

### Unit Tests
- All new functions (`strip_ansi`, `success`, `error`, `warning`, `info`, `hint`, `table`, `status_block`, `progress`, `set_output_mode`, `get_output_mode`)
- FORCE_COLOR behavior in `configure_output`
- Edge cases: empty strings, zero ceiling, max_col_width truncation, mode transitions

### Integration Tests
- Verify `ll-issues list` works with migrated imports
- Verify `ll-loop info` works with migrated imports

## References

- Original issue: `.issues/enhancements/P3-ENH-1781-create-shared-output-formatting-utility.md`
- Existing module: `cli/output.py` at `scripts/little_loops/cli/output.py:1`
- Test patterns: `test_cli_output.py` at `scripts/tests/test_cli_output.py:1`
- Config dataclasses: `config/cli.py` at `scripts/little_loops/config/cli.py:125`
- Logger (naming overlap): `logger.py` at `scripts/little_loops/logger.py:17`
- add_json_arg pattern: `cli_args.py` at `scripts/little_loops/cli_args.py:197`
- Design tokens format pattern: `design_tokens.py` at `scripts/little_loops/design_tokens.py:201`
