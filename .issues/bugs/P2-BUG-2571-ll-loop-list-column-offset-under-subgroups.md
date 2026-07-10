---
id: BUG-2571
title: ll-loop list columns misalign for rows under subgroup subheads
type: BUG
status: done
priority: P2
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T02:10:14Z'
completed_at: '2026-07-10T02:10:14Z'
labels:
- ll-loop
- cli
- output
- alignment
- regression-guard
confidence_score: 96
outcome_confidence: 95
---

# BUG-2571: ll-loop list columns misalign for rows under subgroup subheads

## Summary

In `ll-loop list`, when a category contains an auto-detected subgroup (a `▸`-prefix
cluster such as `spike-*` with ≥3 members that dominates the category), the leaf
rows under that subgroup subhead are indented 4 spaces to show nesting, while
flat-tail rows and rows in categories without subgroups use a 2-space indent. The
loop-name column, however, was padded to a *fixed* width (`ljust(name_col)`)
regardless of that indent, so every column after the name — kind, labels, and
description — started 2 columns further right on subgrouped rows than on flat rows.
Within a single listing the columns fell out of vertical alignment.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Anchor**: `cmd_list()` → inner `_emit_row()`
- **Cause**: `_emit_row` built the row as `f"{indent}{name_str}{kind_str}{label_str}{desc_str}"`
  where `name_str = _truncate(_display_name(lp["name"]), _MAX_NAME_COL).ljust(name_col)`.
  The name field is a fixed `name_col` (34) wide, so the kind column always began at
  absolute position `len(indent) + 34`. Subgroup leaf rows pass `leaf_indent = "    "`
  (4 spaces) while flat-tail / no-subgroup rows pass `"  "` (2 spaces), shifting the
  kind/labels/desc columns 2 positions right for subgrouped rows only.

## Steps to Reproduce

1. Create a project with a category whose loops form a dominant prefix cluster
   (e.g. `spike-alpha`, `spike-beta`, `spike-gamma`) plus at least one non-clustered
   loop in the same category (e.g. `other`).
2. Run `ll-loop list`.
3. Observe that the `▸`-clustered rows (indented under `· spike-* (3)`) have their
   kind/description columns shifted 2 columns to the right of the `other` row.

## Expected Behavior

The kind, labels, and description columns begin at a single, constant absolute
column for every leaf row in the listing, whether the row sits under a subgroup
subhead or in a category's flat tail.

## Actual Behavior

Kind column starts at column 38 for subgrouped rows but 36 for flat-tail rows; the
description column is likewise offset (measured 50 vs 48 in the regression fixture).
The two indent levels never line up.

## Resolution

- **Action**: fix
- **Completed**: 2026-07-10
- **Status**: Completed

### Fix

In `_emit_row`, absorb the extra subgroup indent into the name field so the kind
column begins at a constant absolute column for every row. The name-field width and
the truncation cap are both reduced by however much the row's indent exceeds the
2-space base:

```python
_base_indent = 2
_extra_indent = max(0, _display_width(indent) - _base_indent)
_name_field = max(1, name_col - _extra_indent)
_name_cap = max(1, _MAX_NAME_COL - _extra_indent)
name_str = colorize(
    _truncate(_display_name(lp["name"]), _name_cap).ljust(_name_field),
    "1",
)
```

Flat rows (indent 2) are unchanged (`_extra_indent == 0`). Subgroup rows (indent 4)
get a name field narrowed by 2, so the kind column lands at the same absolute
position as flat rows. Long names still truncate cleanly within the narrower field
and retain the 2-column gap before the kind label.

### Files Changed

- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` → `_emit_row()`: indent-aware
  name field width + truncation cap.
- `scripts/tests/test_ll_loop_commands.py` — added
  `test_column_alignment_across_subgroups_and_flat_tail` (asserts the description
  column starts at the same position for a subgrouped row and a flat-tail row).
  Also corrected the stale `test_multiline_description_no_continuation_row`: replaced
  a width-dependent, design-contradicting assertion with the real single-line
  collapse invariant and pinned `terminal_width` so it is deterministic.

### Verification Results

- New regression test fails on the pre-fix code (desc columns at 50 vs 48) and
  passes after the fix.
- Full `scripts/tests/test_ll_loop_commands.py` suite: 206 passed, at both
  `COLUMNS=80` and the 120-column default (verified on Python 3.12).

## Acceptance Criteria

- `ll-loop list` renders the kind/labels/description columns at a single constant
  column across subgrouped and flat-tail rows in the same category.
- A regression test guards the alignment across the subgroup vs flat-tail boundary.
- The full `test_ll_loop_commands.py` suite passes.

## Session Log
- manual session - 2026-07-10T02:10:14Z - investigate + fix ll-loop list column offset
