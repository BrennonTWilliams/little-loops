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

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Anchors**: `_emit_row` in `cmd_list`, and `_load_loop_meta`

## Steps to Reproduce

1. Ensure a loop has a multi-line YAML `description:` block (many built-in
   loops do, e.g. `apo-beam`).
2. Run `ll-loop list` in a terminal ~80 columns wide (or `COLUMNS=60 ll-loop
   list`).
3. Observe the loop's description spilling onto wrapped continuation lines
   below the row, some of which exceed the terminal width.

## Current Behavior

Two independent problems together left `ll-loop list` not behaving like
`ll-issues list`:

1. **Not single-line.** Multi-line YAML descriptions spilled their full text
   across several rows — the opposite of the "cut off at width" behavior the
   user asked for.
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
continuation lines, and rows fully fill the terminal width when the
description has enough content.

## Root Cause (composite)

Two separate defects needed to be fixed; each on its own would have left the
user-visible symptom.

### Root cause A — `_emit_row` continuation block (close-at-symptom fix)

BUG-2554 was implemented after the line-2 continuation feature (`ed7c1548
feat(loop): surface line-2 descriptions`) but did not account for it. It
truncated `row_str` only; the separate continuation-line block below the row
was left intact, so the full description still reached the terminal (and
overflowed it).

### Root cause B — `_load_loop_meta` first-line-only split (the deeper bug)

Even after the continuation block was removed, multi-line YAML descriptions
rendered *short* of the terminal edge. `_load_loop_meta` was extracting only
`raw_lines[0]` from the YAML `description:` block scalar:

```python
description = raw_lines[0].rstrip()
```

For the 92 of 102 loop descriptions that start on line 1 and continue on
lines 2+, this discarded every subsequent line. Because `desc_budget = tw -
used` is recomputed from the actual rendered prefix, a short (line-1-only)
description simply had nothing to fill the rest of the row with — the row
ended as soon as the line-1 text ran out, leaving the right side of the
terminal empty.

The existing regression guard
`test_long_description_row_fills_to_terminal_width` (`test_ll_loop_commands.py:1730`)
used a hand-written `long_desc = "word " * 60` which has no embedded
newlines, so it didn't exercise the load-time split and passed while the bug
was live.

## Resolution

Two fixes, applied in order:

### Fix 1 — remove the continuation-line block (closes the visible symptom)

1. `scripts/little_loops/cli/loop/info.py` — removed the continuation-line
   rendering block in `_emit_row`; each loop now prints exactly one
   already-truncated row. Removed the now-orphaned `_wrap_to_width` import.
2. `scripts/tests/test_ll_loop_commands.py` — replaced
   `test_description_line2_wraps_below_row` with
   `test_multiline_description_no_continuation_row`, which locks in the
   single-line invariant (asserts a multi-line description produces no
   4-space-indented continuation row).

### Fix 2 — collapse newlines at load time (closes the depth gap)

1. `scripts/little_loops/cli/loop/info.py` — replaced the
   `desc = raw_lines[0].rstrip()` extraction in `_load_loop_meta` with a
   space-join of all non-empty lines, so the full YAML description flows onto
   one line regardless of how the block scalar was wrapped. No rendering
   changes were needed in `_emit_row`; the existing `desc_budget = tw - used`
   already fills correctly when the description is long enough.
2. `scripts/tests/test_ll_loop_commands.py` — renamed
   `test_multiline_description_gets_ellipsis` to
   `test_multiline_description_collapsed_to_single_line` and rewrote its
   asserts: `description == "First line. Second line."`,
   `"\n" not in description`. The old test asserted the obsolete split (line 1
   in `description`, line 2 in a separate `description_line2` field).

### Cleanup — prune the now-unused `description_line2` field

After Fix 2, every consumer of `description_line2` either no longer existed
(the renderer that used it was removed in Fix 1) or always emitted `""` (the
loader and `--json` output). The field was removed in commit `b8823ca3`
follow-up:

- `scripts/little_loops/cli/loop/info.py` — dropped `description_line2` from
  the `_load_loop_meta` return dict (both success and exception branches) and
  from the `cmd_list --json` item assembly. Updated the comment in `_emit_row`
  to reflect that the entire description is now collapsed upstream.
- `scripts/tests/test_ll_loop_commands.py` — dropped the
  `meta["description_line2"] == ""` assertion from
  `test_multiline_description_collapsed_to_single_line` and removed the
  `description_line2` mention from its docstring.

The legacy `description_line2` contract is recorded in the originating issue
`P3-ENH-2555` and was tracked as an additive key by `OTHE-201` (advisory); a
new decisions.yaml entry records the field's withdrawal.

## Verification

- `python -m pytest scripts/tests/test_ll_loop_commands.py` — 205 passed.
- `python -m pytest scripts/tests/test_cli_loop_layout.py
  scripts/tests/test_json_output_contracts.py
  scripts/tests/test_cli_loop_background.py` — 155 passed.
- `ruff check` and `python -m mypy scripts/little_loops/cli/loop/info.py` clean.
- `COLUMNS=80 ll-loop list` — zero real display-width overflows (measured via
  `layout._display_width`; the `awk`-reported "82-col" lines were a
  byte-vs-column artifact of the 3-byte `…` glyph, not a real overflow).
- `COLUMNS=60 ll-loop list` — one truncated line per loop, no wrapped body.
- `ll-loop list --no-truncate` — still renders full descriptions.
- 92 multi-line descriptions now contribute their full text to the row
  budget, so rows with those descriptions fill out to `width == tw` instead
  of stopping at line-1 length.

## Follow-up: width-fill concern (investigated 2026-07-09)

At handoff a concern was raised that single-line truncation might now be *too
aggressive* — that rows leave usable horizontal space unused (descriptions cut
earlier than the terminal edge, unlike `ll-issues list`). **Investigated and
found already-correct: no fix needed.**

- Every row with a description longer than its budget fills to *exactly* `tw` at
  widths 80/100/120/160/200 (measured via `layout._display_width`). The engine
  allots `desc_budget = tw - used`, so a long description consumes all remaining
  columns up to `tw`.
- Rows that render *shorter* than `tw` (e.g. the `Generator-evaluator
  harness for …` cluster at ~110-119 cols) have **genuinely short** descriptions
  — their truncated and `--no-truncate` output is byte-identical, so nothing is
  being cut early. This matches `ll-issues list`, where short titles also end
  before the terminal edge.
- Added a regression guard,
  `test_long_description_row_fills_to_terminal_width`, asserting a long-desc
  row lands on `width == tw` (not merely `<= tw`) across TW=80/100/120/160.

## Impact

- **Priority**: P4 — Display bug; multi-line descriptions wrapped/overflowed at
  narrow widths and left terminal space unused.
- **Effort**: Small — removal of one rendering block, one load-time collapse,
  one test swap, and one field cleanup.
- **Risk**: Low — single-line output for multi-line descriptions is the only
  visible change; single-line descriptions and `--json` keep the same shape
  minus the always-empty `description_line2` key (now removed).
- **Breaking Change**: Removing `description_line2` from `--json` output
  breaks any external consumer that read it. Investigation found no in-tree
  consumer, and the originating ENH-2555 explicitly framed the field as
  additive (set `OTHE-201` to advisory).

## Related

- BUG-2554 — the prior fix that truncated the primary row but missed the
  continuation-line interaction.
- `ed7c1548 feat(loop): surface line-2 descriptions` — introduced the
  continuation-line block and `description_line2` field that this issue
  fully withdraws.
- ENH-2555 — originating enhancement whose "line-2 continuation display"
  feature this issue replaces with "single-line collapsed description".

## Status

**Closed** | Created: 2026-07-09 | Resolved: 2026-07-10T00:26:13Z (Fix 1);
follow-up fixes (load-time collapse, field cleanup) committed 2026-07-09 in
`b8823ca3` | Priority: P4


## Session Log
- `hook:posttooluse-status-done` - 2026-07-10T01:32:50 - `9a0c62e4-5e40-470c-bc99-7b0f1713dc24.jsonl`
- `hook:posttooluse-status-done` - 2026-07-10T00:26:45 - `3529d64f-997b-40d8-9db0-bb5ce0e1c7ca.jsonl`
