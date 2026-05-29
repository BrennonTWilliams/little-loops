---
id: ENH-1781
title: Create shared output formatting utility for ll-* CLIs
type: enh
status: open
priority: P3
captured_at: "2026-05-29T02:23:45Z"
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - cli
  - ux
  - captured
---

# ENH-1781: Create shared output formatting utility for ll-* CLIs

## Summary

Create a shared `ll_output` module providing consistent colored messages, tables, progress bars, and status blocks across all `ll-*` CLIs. Modeled after CLI-Anything's `repl_skin.py` which gives 42+ generated CLIs a unified look and feel.

## Current Behavior

Each `ll-*` CLI implements its own output formatting — colors, table rendering, status messages, progress indicators — leading to:
- Inconsistent UX across tools
- Duplicated formatting code
- Varying quality of terminal output

## Expected Behavior

All `ll-*` CLIs use a shared `scripts/little_loops/output.py` module providing:
- **Colored messages**: `success()`, `error()`, `warning()`, `info()`, `hint()` — each with consistent icons, colors, and stream routing (stdout vs stderr)
- **Table rendering**: auto-width columns, box-drawing separators, optional JSON mode
- **Progress bars**: 20-char bar with configurable width
- **Status blocks**: key-value pairs with aligned labels
- **Environment awareness**: respects `NO_COLOR`, `FORCE_COLOR`, terminal detection

## Motivation

CLI-Anything's `repl_skin.py` demonstrates that a single shared output module eliminates inconsistency across a family of related CLIs. Little-loops has ~20 CLIs with varying output quality. A shared utility:
- Makes all tools feel like one product
- Eliminates duplication (each CLI shouldn't reinvent table rendering)
- Makes it trivial to add `--json` / `--plain` mode switching globally

## Success Metrics

- All new CLI output uses the shared utility (0 ad-hoc formatting in new or refactored code)
- At least 3 core CLIs migrated (`ll-issues`, `ll-loop`, `ll-sprint`)
- Consistent icon and color scheme across all migrated tools (visual audit passes)

## Scope Boundaries

- **In scope**: Creating `scripts/little_loops/output.py` with message, table, progress, and status helpers; incremental CLI migration starting with highest-use CLIs; respecting `NO_COLOR`/`FORCE_COLOR`; tests for each formatter
- **Out of scope**: Rewriting all ~20 CLIs at once; changing any CLI's behavior or output structure (only the formatting implementation); adding new output features beyond the five helpers defined in Proposed Solution; JSON output mode (covered by ENH-1780)

## Proposed Solution

Create `scripts/little_loops/output.py` with:

```python
# Core message helpers
def success(msg: str) -> None: ...
def error(msg: str) -> None: ...
def warning(msg: str) -> None: ...
def info(msg: str) -> None: ...
def hint(msg: str) -> None: ...

# Structured output
def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str: ...
def status_block(items: dict[str, str]) -> str: ...
def progress(current: int, total: int, width: int = 20) -> str: ...

# Mode toggling
def set_output_mode(mode: "human" | "json" | "plain") -> None: ...
```

Refactor existing CLIs to use it incrementally, starting with the most frequently used: `ll-issues`, `ll-loop`, `ll-sprint`.

## API/Interface

```python
# Core message helpers
def success(msg: str) -> None: ...
def error(msg: str) -> None: ...
def warning(msg: str) -> None: ...
def info(msg: str) -> None: ...
def hint(msg: str) -> None: ...

# Structured output
def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str: ...
def status_block(items: dict[str, str]) -> str: ...
def progress(current: int, total: int, width: int = 20) -> str: ...

# Mode toggling
def set_output_mode(mode: Literal["human", "json", "plain"]) -> None: ...
```

## Integration Map

### Files to Modify
- New file: `scripts/little_loops/output.py`
- Each `scripts/little_loops/*.py` CLI — replace ad-hoc formatting with shared utility calls

### Similar Patterns
- CLI-Anything `repl_skin.py` — the reference implementation for unified CLI output

### Tests
- `scripts/tests/test_output.py` — unit tests for each formatter

### Documentation
- `docs/reference/API.md` — document the output module

### Configuration
- N/A

## Implementation Steps

1. Create `scripts/little_loops/output.py` with message, table, progress, and status helpers
2. Add tests for each formatter
3. Migrate one CLI as proof-of-concept (e.g., `ll-issues list`)
4. Incrementally migrate remaining CLIs
5. Document in API reference

## Impact

- **Priority**: P3 — Not blocking, quality-of-life improvement across all CLIs
- **Effort**: Medium — New module is small; refactoring ~20 CLIs is the bulk
- **Risk**: Low — Additive; existing output unchanged until each CLI is explicitly migrated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-29T02:28:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e23d1bf-3385-43d7-80c9-602fafbaf867.jsonl`
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
