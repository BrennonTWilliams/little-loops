---
id: ENH-1653
title: "ll-issues refine-status: staggered vertical headers with leader lines and narrow columns"
priority: P3
type: ENH
status: open
captured_at: "2026-05-24T02:27:32Z"
discovered_date: "2026-05-23"
discovered_by: capture-issue
labels: [cli, ux, table-rendering]
---

# ENH-1653: ll-issues refine-status: staggered vertical headers with leader lines and narrow columns

## Summary

Re-render the `ll-issues refine-status` table so all columns fit in narrow terminals by (a) shrinking column widths further, (b) using a 1-character gap between columns instead of 2, and (c) printing column headers vertically/staggered with a leader line (`|`) connecting each header label down to its column.

This builds on ENH-676 (width reduction) and ENH-750 (column elision) by making the *headers themselves* narrow rather than the *data* — the bottleneck on column width today is the header label, not the cell value (e.g. `cmplx`, `chsrf`, `tradeoff` set the floor).

## Current Behavior

- Column separator is 2 spaces: `"  ".join(parts)` at `scripts/little_loops/cli/issues/refine_status.py:507`.
- Headers are rendered horizontally on a single row, so column width is forced to be ≥ the header label length (e.g. `tradeoff` → 8 chars even though the data cell is `✓` / `✗` / a 2-digit number).
- When many command/score columns are active, the table still overflows in narrow terminals even after ENH-676 reductions, triggering ENH-750's elision and hiding columns the user wanted to see.

## Expected Behavior

```
                                    s        s s s s
                                    o        c c c c
                                    u        o o o o
        P                           r n f r c r r r r t
        r                           c o m e o e e e e o
I       i                           e r t a n _ _ _ _ t
D       . s Title                   . . . d f c t a c a
|       | | |    |                  | | | | | | | | | |
BUG-001 P2 S Short issue title      cap ✓ ✓ 85 80 60 70 45 50 90
ENH-002 P3 M Another issue here     scan ✓ ✗ 70 65 50 60 55 40 75
```

Each character of the header label is stacked on its own row above the column, then a single connector row of `|` characters joins the bottom of each header stack to the top of its data column. Column gap is 1 character throughout (header rows, connector row, data rows). Data cells use the natural minimum width (typically 1–5 chars), independent of the header label length.

## Motivation

The current floor for column width is the header label, not the data. Vertical/staggered headers decouple these: a column with a 7-char header (`tradeoff`) and a 2-char value (`✓ `) can render in 2 chars wide instead of 7. Combined with a 1-char gap, this lets the full table (id + priority + size + title + source + norm/fmt + ready + conf + 4 score cols + total + N command cols) fit in standard 80–100 column terminals without elision, so users in split panes / IDE terminals see every column without configuration.

## Proposed Solution

In `scripts/little_loops/cli/issues/refine_status.py`:

1. **Compute per-column minimum width from data**, not header text. Width = max(longest data value rendered in column, configured floor). Header label no longer participates in width.
2. **Render headers as a staggered vertical block** above the data rows:
   - Determine `max_header_height = max(len(label) for label in column_labels)`.
   - For each row `r` in `0..max_header_height`, emit one line where each column prints either the `r`-th character of its header label (with offset so labels bottom-align) or a space.
   - Stagger by giving each column a small vertical offset (e.g. `r % 2`) so adjacent single-char labels don't collide and remain visually distinguishable when columns are 1 char wide.
3. **Emit a connector row** of `|` characters (one `|` per column, gap-separated) immediately below the header block and immediately above the first data row.
4. **Change the column separator** from `"  "` (2 chars) to `" "` (1 char) in the `_render_row()` join logic (line 507) and in all corresponding header / connector / separator-line generators so spacing stays consistent across all rows.
5. **Pin pre-existing wide headers** (`id`, `priority`, `title`, `source`) horizontally — they already match their column width and don't benefit from stacking. Apply vertical rendering only to columns where `len(label) > column_data_width`.
6. **Disable vertical headers for non-TTY / `--json` output** so piped consumers still get a parseable single-line header (or no header for JSON, as today).

### Edge cases / design questions to resolve during implementation

- **Color**: Today `colorize()` wraps the header text once; with vertical rendering each character must carry the ANSI escapes, OR the whole vertical block is wrapped column-wise. Pick the simpler path and document it.
- **Stagger offset rule**: `r % 2` is a starting suggestion. Implementer may pick `idx % 2` or `idx % 3` based on visual testing — the requirement is "labels remain readable when columns are 1 char wide", not a specific formula.
- **Truncation**: If a data cell exceeds its computed column width (rare but possible for `size` = `Very Large`), truncate with ellipsis rather than widening the column. Long size values are already a known constraint.
- **Interaction with ENH-750 elision**: With narrower columns the elision threshold should rarely trigger; keep the elision logic intact as a fallback for extremely narrow terminals (< 60 cols).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/refine_status.py` — column-width computation (lines ~60–96 width constants, `_STATIC_COLUMN_SPECS`), `_render_row()` (line ~500), header emission (around line ~505–515 where `header` and `separator` are built)

### Dependent Files (Callers/Importers)
- N/A — `refine_status.py` is a standalone CLI command

### Similar Patterns
- `scripts/little_loops/cli/output.py` — `terminal_width()`, `colorize()`, `print_json()` (no changes expected, but vertical-color rendering may need a helper here)

### Tests
- `scripts/tests/test_refine_status.py` — extend with:
  - Header block shape test (height, stagger offsets, `|` connector row)
  - 1-char gap assertion (no `"  "` in rendered output where columns meet)
  - Column-width-from-data test (width matches longest cell, not header label)
  - Non-TTY / `--json` mode: vertical headers disabled
  - Wide terminal: full table still fits and remains readable

### Documentation
- `docs/` — none currently describes the table layout; no doc changes required unless screenshots exist (none found).

### Configuration
- None required. New rendering is the default; no new flags or config keys.

## Implementation Steps

1. Add `_compute_column_data_width(rows, col_name)` helper that returns the max data-cell width across all rows for a given column.
2. Replace header-driven widths in `_STATIC_COLUMN_SPECS` with data-driven widths at render time (keep the spec for header text + justify; drop the fixed `width` field or treat it as a floor only).
3. Implement `_render_vertical_header_block(columns)` returning a list of strings (one per stack row + one connector `|` row).
4. Change `"  ".join(parts)` → `" ".join(parts)` in `_render_row()` and any matching header/separator joiners.
5. Bypass the vertical block when output is non-TTY or `--json` (re-use existing JSON guard from ENH-750).
6. Add tests in `scripts/tests/test_refine_status.py` covering the cases listed in **Integration Map → Tests** above.
7. Manual verification at 60 / 80 / 100 / 120 column widths with a representative `.issues/` set.

## Scope Boundaries

- **In scope**: `ll-issues refine-status` table rendering only
- **Out of scope**: `--json` output format — unchanged
- **Out of scope**: Other CLI commands' tables (e.g. `ll-issues list`)
- **Out of scope**: Color-scheme changes beyond what's needed to make vertical rendering work
- **Out of scope**: New CLI flags or configuration keys — this is a pure rendering rework

## Impact

- **Priority**: P3 — Quality-of-life improvement; CLI is functional today but cramped/elided in narrow terminals
- **Effort**: Medium — header rendering is a non-trivial layout change; tests need to cover the visual block, not just text matching
- **Risk**: Medium — visual change affects every user of `refine-status`; care needed for color and edge cases (single-char data, very long size strings)
- **Breaking Change**: No (output format change only; no API/JSON change)

## Related Issues

- [[P3-ENH-676-reduce-column-widths-in-ll-issues-refine-status-table]] — done; reduced fixed widths
- [[P3-ENH-750-ll-issues-refine-status-dynamic-terminal-width-table]] — done; added column elision for narrow terminals
- [[P3-ENH-596-colorize-ll-issues-refine-status-output]] — interacts with header rendering (color must survive vertical layout)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `table-rendering`

## Status

**Open** | Created: 2026-05-23 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-24T02:31:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a831c57a-345e-49ef-a2f5-c7cd4051eace.jsonl`
- `/ll:capture-issue` - 2026-05-24T02:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b82659fb-64be-4c97-9770-57964db516aa.jsonl`
