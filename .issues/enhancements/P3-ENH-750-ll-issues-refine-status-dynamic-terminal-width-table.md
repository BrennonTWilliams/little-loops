---
id: ENH-750
title: "ll-issues refine-status: dynamic terminal width table rendering"
priority: P3
type: ENH
status: backlog
discovered_date: "2026-03-15"
discovered_by: capture-issue
labels: [cli, ux, table-rendering]
---

# ENH-750: ll-issues refine-status: dynamic terminal width table rendering

## Summary

`ll-issues refine-status` renders a table that overflows narrow terminal windows. The title column already adapts dynamically via `terminal_width()`, but static columns have fixed widths that never shrink. When several command columns are active, the total table width routinely exceeds 80 columns, requiring the user to widen their terminal to read the output clearly.

## Current Behavior

- Static columns (`id`, `priority`, `source`, `norm`, `fmt`, `ready`, `confidence`, `total`) have fixed widths defined in `_STATIC_COLUMN_SPECS` / `_*_WIDTH` constants.
- Each active command column adds `_CMD_WIDTH = 6` characters.
- The title column shrinks to accommodate all other columns, but is floored at `_MIN_TITLE_WIDTH = 20`, so the table can still overflow.
- With the default column set plus 4–6 command columns, total width easily reaches 100–120 characters, requiring a wide terminal.

## Expected Behavior

The table should degrade gracefully as the terminal narrows:

1. **Column elision**: When total width would exceed `terminal_width()`, drop lower-priority columns first (suggested drop order: `source`, `norm`, `fmt`, then optional score columns, then command columns from rightmost first).
2. **Minimum-width floor**: Keep a configurable minimum (e.g. `id` + `priority` + `title`) always visible.
3. **Overflow indicator**: Optionally show a `…cols` suffix in the header to indicate elided columns.
4. No behavior change when terminal is wide enough for the full table.

## Motivation

Users running `ll-issues refine-status` in a split-pane, IDE terminal, or CI log viewer see a garbled or horizontally scrolling table. The feature becomes unusable without manual column configuration via `ll-config.json`. Dynamic adaptation removes the need for this workaround and makes the command reliable across all terminal environments.

## Proposed Solution

In `refine_status.py`, after computing `term_cols`, calculate the total table width needed. If it exceeds `term_cols`, progressively drop columns (by a priority-ordered elision list) until the table fits or only the minimum required columns remain. The elision list should be configurable in `ll-config.json` under `refine_status.elide_order`.

**Elision semantics:**
- `elide_order` lists columns in drop-first order. Columns absent from the list are treated as **pinned** and will never be elided regardless of terminal width.
- `id`, `priority`, and `title` are always pinned by the implementation and must never appear in `elide_order` (the implementation should warn or ignore if they do).
- Command columns not explicitly listed in `elide_order` are dropped right-to-left (rightmost first) after all listed columns have been dropped.

**Scope boundary — `--json` mode:**
- Elision must **not** apply when `--json` is active. JSON output represents the full data set and must remain stable regardless of terminal width. Silently dropping fields from JSON output would break downstream consumers (scripts, pipes, CI).
- The `_elide_columns` helper should be gated by a check for JSON mode before it is called, or accept a `json_mode: bool` guard parameter.

Key files:
- `scripts/little_loops/cli/issues/refine_status.py` — `_STATIC_COLUMN_SPECS`, width constants, rendering loop (lines 14–88, 245–298)
- `scripts/little_loops/cli/output.py` — `terminal_width()` helper
- `config-schema.json` — add optional `elide_order` field under `refine_status`

## Integration Map

- `refine_status.py`: add `_elide_columns(active_cols, term_cols, …) -> list[str]` helper called before the render loop; skip entirely when `--json` is active
- `config-schema.json` / `ll-config.json`: optional `refine_status.elide_order: list[str]` (default: see Implementation Steps); columns absent from list are pinned
- No changes required to other CLI commands

## Implementation Steps

1. Define a default elision order constant in `refine_status.py` (e.g. `_ELIDE_ORDER = ["source", "norm", "fmt", "confidence", "ready", "total", ...]`). `id`, `priority`, `title` must not appear here.
2. After computing active columns and command columns, sum their widths (re-use logic near line 260).
3. If total > `term_cols` **and not in `--json` mode**, remove columns from `_ELIDE_ORDER` one at a time until the table fits or only the minimum set remains. Command columns not in the list are dropped rightmost-first after the list is exhausted.
4. Expose `elide_order` in `config-schema.json` and read it in `refine_status.py` (override default if set). Document that omitting a column from `elide_order` pins it.
5. Add unit tests in `scripts/tests/test_refine_status.py` covering:
   - Narrow (60-col), medium (80-col), and wide (160-col) table scenarios
   - Pinned columns are never dropped regardless of width
   - `--json` mode is unaffected by terminal width / elision logic

## Impact

- **Scope**: Single CLI command (`ll-issues refine-status`)
- **Risk**: Low — purely additive; existing wide-terminal behavior unchanged
- **Affected users**: Anyone using split-pane terminals, IDE terminals, or CI log output

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/issues/refine_status.py` | Primary implementation file |
| `scripts/little_loops/cli/output.py` | `terminal_width()` utility |
| `scripts/tests/test_refine_status.py` | Existing test suite to extend |

## Status

- [ ] Implementation (`_elide_columns` helper + render loop integration)
- [ ] JSON mode guard (elision bypassed when `--json` active)
- [ ] Config schema update (`refine_status.elide_order` in `config-schema.json`)
- [ ] Tests (narrow/medium/wide, pinned columns, JSON mode unaffected)

---

## Session Log
- `/ll:capture-issue` - 2026-03-15T04:11:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0e4ff8a-9271-4c55-a606-a120317ccfad.jsonl`
