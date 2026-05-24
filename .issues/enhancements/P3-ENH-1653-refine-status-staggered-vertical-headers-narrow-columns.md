---
id: ENH-1653
title: 'll-issues refine-status: staggered vertical headers with leader lines and
  narrow columns'
priority: P3
type: ENH
status: deferred
captured_at: '2026-05-24T02:27:32Z'
discovered_date: '2026-05-23'
discovered_by: capture-issue
labels:
- cli
- ux
- table-rendering
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

> **Gap-factor arithmetic note** (_Wiring pass added by `/ll:wire-issue`_): The column gap is encoded in **two additional sites beyond `_build_row`** — both must change from `2 → 1` in lockstep:
> - `_compute_min_total_width` return: `col_sum + 2 * (n_parts - 1)` drives the `fits()` predicate inside `_elide_columns`
> - `title_w` computation in `cmd_refine_status`: `max(_MIN_TITLE_WIDTH, term_cols - non_title_sum - 2 * (n_parts - 1))`
> Missing either site will cause elision thresholds and title-column widths to be computed as if the gap is still 2 characters.

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

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break and must be updated (additional — beyond lines 97 and 809 already noted):**
- `scripts/tests/test_refine_status.py:1665 TestColumnElision.test_wide_terminal_shows_all_columns` — `header = out.splitlines()[0]` then checks `"ID" in header` etc.; vertical headers split labels across multiple rows, so `[0]` returns only the first stagger row
- `scripts/tests/test_refine_status.py:1754 TestColumnElision.test_pinned_columns_never_elided` — same `splitlines()[0]` single-line header assumption; asserts `"ID" in header`, `"Pri" in header`, `"Title" in header`
- `scripts/tests/test_refine_status.py:1858 TestColumnElision.test_custom_elide_order_respected` — same `splitlines()[0]` pattern; asserts `"norm" in header`
- `scripts/tests/test_refine_status.py:1661 TestColumnElision.test_narrow_terminal_elides_columns` — `len(line) <= terminal_cols` without ANSI stripping; ANSI escape bytes inflate raw `len()`
- `scripts/tests/test_refine_status.py:1750 TestColumnElision.test_medium_terminal_fits` — same `len(line)` ANSI-unsafe pattern

**Pattern to follow for header block assertions:** Use a slice of `out.splitlines()[:max_header_height+1]` and check that each column label character appears somewhere in the block, rather than on `splitlines()[0]`. For ANSI-safe width, import/copy `_strip_ansi` (pattern at `test_ll_loop_display.py:3223`) and assert `len(_strip_ansi(line)) <= terminal_width`.

### Documentation
- `docs/` — none currently describes the table layout; no doc changes required unless screenshots exist (none found).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — "Narrow terminal support" paragraph (around `ll-issues refine-status` section, ~line 702) documents the elision threshold math that assumes a 2-space gap; if the gap becomes 1 space the described thresholds shift and the paragraph should be updated to reflect the new behavior

### Configuration
- None required. New rendering is the default; no new flags or config keys.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact line numbers (confirmed):**
- Module-level width constants (`_MIN_TITLE_WIDTH`, `_ID_WIDTH`, `_CMD_WIDTH = 6`, etc.): `refine_status.py:16–28`
- `_STATIC_COLUMN_SPECS` dict (tuple `(fixed_width, header_text, right_justify)`): `refine_status.py:63–78`
- `_build_row()` join: `refine_status.py:507` — `return "  ".join(parts)` (sole join point; all column groups flatten into one `parts` list)
- Header/separator emission: `refine_status.py:509–511` — `header = _build_row(None)`, `separator = "-" * len(header)`, `rows = [header, separator]`
- `_apply_cell_color()` ANSI-safe pattern: `refine_status.py:168–193` — strips leading/trailing whitespace, colorizes only the visible content, reassembles `leading + colorize(content, code) + trailing`
- Inline ANSI-safe padding pattern: `refine_status.py:493–498` — `colorize(raw, "32") + padded[len(raw):]` (ANSI wraps content only; trailing spaces stay outside escape sequence)

**Reusable ANSI utilities (no changes expected to these files):**
- `show.py:285` — `_ljust(text, width)`: ANSI-safe left-justify using `_strip_ansi()` for visible-length measurement
- `layout.py:21` — `_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")`: shared ANSI-strip regex pattern (used at `layout.py:1534` for max-line-length calculation)
- `show.py:278–288` — `_strip_ansi()` helper (local; could be moved to `output.py` for reuse)

**No vertical text utility exists.** The closest pattern is the FSM character-grid renderer in `layout.py` (`_render_layered_diagram()`), which writes characters cell-by-cell into a `list[list[str]]` grid and joins rows. The vertical header block should follow this grid-writing pattern: one character per header row at fixed column offsets.

**`separator = "-" * len(header)` (line 511) is not ANSI-safe** — currently harmless because header cells have no `colorize()` calls. If vertical header characters are colorized, `len(header)` will be inflated by ANSI escape bytes; replace with `len(_strip_ansi(header))` at that point.

**Existing tests that will break and need updating:**
- `test_refine_status.py:97` — `test_table_has_header_and_separator`: checks `"ID" in ln and "Pri" in ln and "Title" in ln` on a single line; vertical headers split labels across rows, so this assertion will need to check the full header block
- `test_refine_status.py:809` — `test_table_row_width_fits_terminal`: uses plain `len(line)` which is not ANSI-safe; colorized vertical header characters would inflate byte counts; update to `len(_strip_ansi(line)) <= terminal_width`
- Model new vertical-header tests after `_run_refine_status()` helper at `test_refine_status.py:1591` (handles terminal-width mocking and argv patching)

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

**Deferred** | Created: 2026-05-23 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-24T15:08:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22c72bd4-c8c7-425f-955c-8dbd7eb0f95c.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15abbbf2-6861-413e-8b47-a6ce0228b06a.jsonl`
- `/ll:wire-issue` - 2026-05-24T14:56:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce94b2e6-4df8-415c-8a59-89a35be91e9c.jsonl`
- `/ll:refine-issue` - 2026-05-24T14:51:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/328a4c48-a381-4d4a-80fd-aa96016d5660.jsonl`
- `/ll:format-issue` - 2026-05-24T02:31:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a831c57a-345e-49ef-a2f5-c7cd4051eace.jsonl`
- `/ll:capture-issue` - 2026-05-24T02:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b82659fb-64be-4c97-9770-57964db516aa.jsonl`

---

## Resolution

- **Status**: Deferred - Tradeoff Review
- **Completed**: 2026-05-24
- **Reason**: Niche UX polish with ANSI/stagger complexity disproportionate to the narrow-terminal problem; ENH-750 column elision already mitigates the core issue.

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: MEDIUM

### Rationale
Staggered vertical headers add significant ANSI rendering complexity (per-character wrapping, stagger offsets, connector rows) with high regression risk for every `refine-status` user. ENH-750's column elision already handles narrow terminals. Re-evaluate if `refine-status` table rendering becomes a priority focus.
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`
