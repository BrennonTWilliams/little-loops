---
discovered_commit: 18968323
discovered_branch: main
discovered_date: 2026-07-09T00:00:00Z
discovered_by: user-report
status: done
completed_at: 2026-07-10T00:26:13Z
relates_to: BUG-2554
labels: [bug, cli, ll-loop, display, truncation]
---

# BUG-2566: `ll-loop list` multi-line descriptions still overflow terminal width

## Summary

BUG-2554 ("truncate `ll-loop list` rows to terminal width", commit `398148f4`)
was implemented and closed, but the user reported that `ll-loop list` output
was still not cut off at the available width the way `ll-issues list` is.

The BUG-2554 fix correctly truncated each loop's **primary row**, but it never
touched the **`description_line2` continuation-line block** in
`scripts/little_loops/cli/loop/info.py` — a feature added earlier by a separate
commit (`ed7c1548 feat(loop): surface line-2 descriptions`). For any loop whose
YAML `description:` was a multi-line block, that block dumped the entire
remaining description as wrapped continuation lines below the row.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 418-426 (pre-fix) — the continuation-line block in the nested
  `_emit_row` function
- **Anchor**: `_emit_row` in `cmd_list`

## Steps to Reproduce

1. Ensure a loop has a multi-line YAML `description:` block (many built-in
   loops do, e.g. `apo-beam`).
2. Run `ll-loop list` in a terminal ~80 columns wide (or `COLUMNS=60 ll-loop
   list`).
3. Observe the loop's description spilling onto wrapped continuation lines
   below the row, some of which exceed the terminal width.

## Current Behavior

Two independent problems resulted from the untouched continuation block:

1. **Not single-line.** Multi-line YAML descriptions spilled their full text
   across several rows — the opposite of the "cut off at width, like
   `ll-issues list`" behavior the user asked for.
2. **Overflowed the width.** The wrap width was `wrap_w = max(20, tw - 4)`, but
   each continuation line was printed with a `{indent}    ` prefix (6 cols for
   flat rows, 8 for subgrouped rows), so continuation lines rendered at `tw+2`
   to `tw+4` columns. A `COLUMNS=60` run produced 64-col continuation lines.

The primary-row truncation from BUG-2554 (`desc_budget` +
`_truncate_to_width_ansi` clamp) was verified working — only the continuation
lines were the defect.

## Expected Behavior

Each loop renders as exactly one row, truncated with `…`, literally matching
`ll-issues list`. Multi-line YAML descriptions are not spilled onto wrapped
continuation lines.

## Root Cause

BUG-2554 was implemented after the line-2 continuation feature (`ed7c1548`) but
did not account for it. It truncated `row_str` only; the separate
continuation-line block below the row was left intact, so the full description
still reached the terminal (and overflowed it).

## Resolution

Decision (confirmed with user): **one line per loop.**

1. `scripts/little_loops/cli/loop/info.py` — removed the continuation-line
   rendering block in `_emit_row`; each loop now prints exactly one
   already-truncated row. Removed the now-orphaned `_wrap_to_width` import.
2. Kept `description_line2` in `_load_loop_meta` (info.py:72-92) and in the
   `--json` output (info.py:288-289) as backward-compatible data — no consumer
   or JSON contract test depends on removing it.
3. `scripts/tests/test_ll_loop_commands.py` — replaced
   `test_description_line2_wraps_below_row` with
   `test_multiline_description_no_continuation_row`, which locks in the
   single-line invariant (asserts a multi-line description produces no
   4-space-indented continuation row). Existing main-row truncation tests
   (`test_row_fits_terminal_with_wide_labels`,
   `test_desc_budget_shrinks_when_labels_wide`,
   `test_no_truncate_flag_bypasses_truncation`) were left untouched.

## Verification

- `python -m pytest scripts/tests/test_ll_loop_commands.py` — 204 passed.
- `python -m pytest scripts/tests/test_cli_loop_layout.py
  scripts/tests/test_json_output_contracts.py
  scripts/tests/test_cli_loop_background.py` — 155 passed.
- `ruff check` and `python -m mypy scripts/little_loops/cli/loop/info.py` clean.
- `COLUMNS=80 ll-loop list` — zero real display-width overflows (measured via
  `layout._display_width`; the awk "82-col" reports were a byte-vs-column
  artifact of the 3-byte `…` glyph, not a real overflow).
- `COLUMNS=60 ll-loop list` — one truncated line per loop, no wrapped body.
- `ll-loop list --no-truncate` — still renders full first-line descriptions.

## Follow-up: width-fill concern (investigated 2026-07-09)

At handoff a concern was raised that single-line truncation might now be *too
aggressive* — that rows leave usable horizontal space unused (descriptions cut
earlier than the terminal edge, unlike `ll-issues list`). **Investigated and
found already-correct: no fix needed.**

- Every row with a description longer than its budget fills to *exactly* `tw` at
  widths 80/100/120/160/200 (measured via `layout._display_width`). The engine
  allots `desc_budget = tw - used`, so a long description consumes all remaining
  columns up to `tw`.
- The rows that render *shorter* than `tw` (e.g. the `Generator-evaluator
  harness for …` cluster at ~110-119 cols) have **genuinely short** descriptions
  — their truncated and `--no-truncate` output is byte-identical, so nothing is
  being cut early. This matches `ll-issues list`, where short titles also end
  before the terminal edge.
- Added a regression guard,
  `test_long_description_row_fills_to_terminal_width`, asserting a long-desc row
  lands on `width == tw` (not merely `<= tw`) across TW=80/100/120/160. This
  locks in the fill property the concern was about. Suite now 205 passed
  (was 204).

## Impact

- **Priority**: P4 — Display bug; multi-line descriptions wrapped/overflowed at
  narrow widths
- **Effort**: Small — removal of one rendering block plus one test swap
- **Risk**: Low — single-line output for multi-line descriptions is the only
  visible change; single-line descriptions and `--json` are unaffected
- **Breaking Change**: No

## Related

- BUG-2554 — the prior fix that truncated the primary row but missed the
  continuation-line interaction.
- `ed7c1548 feat(loop): surface line-2 descriptions` — introduced the
  continuation-line block this issue removes.

## Status

**Closed** | Created: 2026-07-09 | Resolved: 2026-07-10T00:26:13Z | Priority: P4


## Session Log
- `hook:posttooluse-status-done` - 2026-07-10T00:26:45 - `3529d64f-997b-40d8-9db0-bb5ce0e1c7ca.jsonl`
