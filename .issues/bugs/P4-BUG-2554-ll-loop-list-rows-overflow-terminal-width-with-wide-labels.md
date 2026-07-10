---
discovered_commit: c3a7e0ad
discovered_branch: main
discovered_date: 2026-07-08T00:00:00Z
discovered_by: user-report
status: done
completed_at: 2026-07-09T02:16:40Z
---

# BUG-2554: `ll-loop list` rows overflow terminal width when labels are wide

## Summary

`ll-loop list` renders each row with a column-width budget computed once per
render, but `_render_labels` is uncapped and the description budget is not
shrunk to compensate. At narrow terminal widths (e.g., TW=80), a row with two
long labels such as `[experimental] [performance-critical]` renders to
82-94 columns and wraps onto the next terminal line. The user's expectation
was that `ll-loop list` should truncate to fit on a single line, matching
`ll-issues list` behavior.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 307-317 (column-width constants); 354-397 (`_emit_row`)
- **Anchor**: `in cmd_list` (column budget block) and the nested `_emit_row`
- **Code**:
```python
# info.py line 311-317 — column budget computed once per render, applied to
# every row regardless of actual label width.
_MAX_LABEL_COL = 18
_DESC_FLOOR = 20
tw = terminal_width(default=120)
desc_col = max(_DESC_FLOOR, tw - name_col - kind_col - label_col - 6)

# info.py line 383-388 — labels render inline with no width check
label_str = _render_labels(lp.get("labels") or [])
desc_text = lp["description"] or ""
if desc_text and len(desc_text) > desc_col:
    desc_text = _truncate(desc_text, desc_col)
desc_str = f"  {desc_text}" if desc_text else ""
print(f"{indent}{name_str}{kind_str}{label_str}{desc_str}")
```

## Current Behavior

At TW=80 with `labels: [experimental, performance-critical]` the rendered row
is ~105 visible columns (2 indent + 34 name + 10 kind + 38 labels + 21 desc),
overflowing the 80-column terminal by ~25 columns. The overflow happens
because `_render_labels` can produce strings wider than the reserved 18-column
label slot, the 2-space desc gap is not subtracted from the budget, and the
per-render `desc_col` does not shrink when a single row's labels exceed the
reserved slot.

## Expected Behavior

Every entry row fits within the terminal width on a single line, matching
`ll-issues list`'s "compute prefix width, truncate the remainder" pattern.
A `--no-truncate` flag (parity with `ll-issues list`) opts out of truncation
for piping/capturing.

## Motivation

Overflowing rows make `ll-loop list` unreadable in narrow terminals and
inconsistent with `ll-issues list`, which has correctly handled this case
since its introduction. Users expect column-aligned output that wraps cleanly
at the terminal edge.

## Steps to Reproduce

1. Create a loop with wide labels:
   ```yaml
   name: wide
   category: test
   description: A simple description
   labels:
     - experimental
     - performance-critical
   ```
2. Run `ll-loop list` in a terminal with 80 columns.
3. Observe the entry row wraps onto the next line.

## Root Cause

Three independent issues compound in `_emit_row`:

1. **Per-render column budget** (`info.py:307-317`): the description budget
   `desc_col` is computed once and applied to every row, regardless of the
   actual rendered label width.
2. **Uncapped label rendering** (`info.py:489-505`): `_render_labels`
   produces strings wider than the reserved `_MAX_LABEL_COL=18` slot.
3. **Missing desc-gap subtraction**: the 2-space gap between labels and the
   description is not in the budget math.

## Proposed Solution

Replace the closure-captured `desc_col` with a per-row `desc_budget`
computed from the actual rendered prefix, using the existing
`layout._display_width` helper for ANSI-aware display-width measurement.
Add a defense-in-depth ANSI-aware clamp for any edge-case overflow. Wire a
`--no-truncate` flag for parity with `ll-issues list`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — refactor `_emit_row`
  (lines 354-397) for per-row prefix budget; remove dead `desc_col`/`label_col`
  closure variables; add `_display_width` and `_truncate_to_width_ansi` to
  the layout import block.
- `scripts/little_loops/cli/loop/__init__.py` — add `--no-truncate` flag to
  `list_parser` (near line 339, alongside `--json`/`--category`/`--label`).
- `scripts/tests/test_ll_loop_commands.py` — add 5 new tests in
  `TestLoopListFormatting` covering overflow, desc-budget shrinking, label-count
  invariant, `--no-truncate` behavior, and argparse wiring.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` — re-exports `terminal_width`;
  unchanged.
- `scripts/little_loops/cli/loop/layout.py` — already provides
  `_display_width`, `_truncate_to_width`, `_truncate_to_width_ansi`,
  `_wrap_to_width`; reused without modification.

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:14-17` and `:266-277` —
  the `ll-issues list` "compute prefix, truncate the rest" pattern this fix
  mirrors.

### Tests
- `scripts/tests/test_ll_loop_commands.py::TestLoopListFormatting` — add:
  - `test_row_fits_terminal_with_wide_labels` — TW=80, wide labels, asserts
    entry row ≤ 80 cols.
  - `test_desc_budget_shrinks_when_labels_wide` — compares visible desc length
    between wide-labels and no-labels variants.
  - `test_row_width_invariant_across_label_counts` (4 parametrized cases) —
    `labels=[]`, `[a]`, `[a, b]`, `[experimental, performance-critical,
    optimization]`.
  - `test_no_truncate_flag_bypasses_truncation` — TW=60, full desc renders.
  - `test_no_truncate_flag_round_trip_through_argparse` — flag is wired into
    argparse namespace.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `info.py` line 26-36, add `_display_width` and `_truncate_to_width_ansi`
   to the existing `little_loops.cli.loop.layout` import block.
2. In `info.py` line 178 area, add `no_truncate = getattr(args, "no_truncate",
   False)` to capture the argparse flag.
3. In `info.py` lines 310-322, remove the `desc_col` and `label_col`
   assignments (kept unused); update the ENH-2539 comment to describe the
   per-row budget recomputation.
4. In `info.py` lines 369-427 (the `_emit_row` nested function), replace the
   description rendering with:
   - Measure `used = _display_width(indent) + _display_width(name_str) +
     _display_width(kind_str) + _display_width(label_str) + 2`.
   - Compute `desc_budget = max(_DESC_FLOOR, tw - used)`.
   - Branch on `no_truncate`: if set, render full desc; otherwise truncate
     with `_truncate(desc_src, desc_budget)`.
   - After assembling `row_str`, apply `_truncate_to_width_ansi(row_str,
     tw - 1)` as defense in depth (skipped when `no_truncate`).
5. In `cli/loop/__init__.py` after the `--label` argument (line 361), add
   `list_parser.add_argument("--no-truncate", action="store_true", help=...)`.
6. Add the 5 new tests described above.
7. Run `python -m pytest scripts/tests/test_ll_loop_commands.py -q`,
   `ruff check scripts/little_loops/cli/loop/info.py scripts/little_loops/cli/loop/__init__.py scripts/tests/test_ll_loop_commands.py`,
   `python -m mypy scripts/little_loops/cli/loop/info.py`.

## Impact

- **Priority**: P4 — Display bug; rows wrap onto next line at narrow widths
- **Effort**: Small — Refactor of one function plus 5 tests
- **Risk**: Low — Per-row math gives the same or larger desc budget than the
  per-render math in all existing test cases; verified against
  `test_name_column_capped_at_32`, `test_description_truncation_at_narrow_width`,
  and `test_description_not_truncated_at_wide_width`.
- **Breaking Change**: No — Visible output is unchanged when labels fit in the
  reserved slot; only the overflow case changes.

## Related Key Documentation

- `docs/reference/API.md` — `_display_width`, `_truncate_to_width_ansi` already
  documented under layout helpers.

## Labels

`bug`, `cli`, `ll-loop`, `display`, `truncation`

## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T02:18:16 - `12c2737e-c5e0-403a-8147-ae20094826aa.jsonl`
- `claude-code` - 2026-07-08 - planning, implementation, test verification

## Resolution

- Replaced closure-captured `desc_col` with per-row `desc_budget` computed
  from actual rendered prefix via `layout._display_width`.
- Added ANSI-aware defense-in-depth clamp via `_truncate_to_width_ansi` for
  any edge-case overflow.
- Added `--no-truncate` flag to `list_parser` for parity with `ll-issues list`.
- Removed dead `desc_col`/`label_col` closure variables.
- Added 5 tests in `TestLoopListFormatting` (7 cases including parametrized
  variants).
- All 14,402 tests in `scripts/tests/` pass; ruff and mypy clean.
- Manual smoke at TW=80 confirms rows fit on a single line; `--no-truncate`
  opts out as expected.

## Status

**Closed** | Created: 2026-07-08 | Resolved: 2026-07-09T02:16:40Z | Priority: P4
> **Historical duplicate ID (normalize-issues 2026-07-10):** number `2554` is a cross-type duplicate shared with **ENH-2554** (`improve-ll-loop-list-layout`). Both issues are `done` and embedded in shipped code/CHANGELOG/git history, so neither was renumbered — the type prefix disambiguates them. (The four resolvable collisions 2519/2520/2521, 2575/2576/2577, and 2530 were renumbered to 2580–2586 the same day.)
