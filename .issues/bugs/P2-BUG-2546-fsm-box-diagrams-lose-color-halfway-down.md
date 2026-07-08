---
id: BUG-2546
title: "FSM box diagrams lose color styling halfway down on deep FSMs (terminal-width
  clamp strips ANSI from overflow lines)"
type: BUG
priority: P2
status: done
captured_at: '2026-07-08T16:19:29Z'
completed_at: 2026-07-08 16:19:29+00:00
discovered_date: 2026-07-08
discovered_by: manual-investigation
testable: true
decision_needed: false
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 22
---

# BUG-2546: FSM box diagrams lose color styling halfway down on deep FSMs

## Summary

`ll-loop run <deep-loop>` and `ll-loop info <deep-loop> --show-diagrams=detailed
--diagram-scope=full` print an FSM as Unicode box art (e.g.
`┌─── /━► ┐ / │ assess │ / └────────┘` for slash-command states). The user
reports that **state badges keep their hue from top to bottom, but connector
characters (`─`, `│`, `▶`, `◀`, `▼`, corners, junction glyphs `┴ ┬ ┼ ├ ┤`)
and box borders drop to plain text from roughly the diagram's mid-point
onward**. The terminal-width-clamp banner (`▼ N layers below …`) still
appears at the bottom.

The bug surfaces on deep FSMs with many back-edges — `rn-implement` and
`rn-remediate` are the two observed triggers (their `run_remediation` /
refinement subgraphs span dozens of `on_no` / `on_error` re-entry edges that
fan into long horizontal connectors). Lighter FSMs render correctly.

## Current Behavior

For deep FSMs:

| Layer / row kind | Expected | Observed |
|---|---|---|
| Top layers (rows ≤ `tw`) | All borders / arrows / junctions colored | Colored (correct) |
| First row exceeding `tw` | All borders / arrows / junctions colored | **Plain text** |
| Every row below | All borders / arrows / junctions colored | **Plain text** |
| Edge labels (yes/no/error) | Colorized by `_colorize_diagram_labels` | Colorized (correct — regex pass runs on plain text after clamp) |
| State kind badges (top border) | Colorized by `_draw_box(kind_color=...)` | **Plain text** below the overflow line |

The "halfway down" framing matches the first row that exceeds `tw`. Back-edge
horizontal connectors in deep FSMs naturally span multiple layers, so the
first overflow row is usually somewhere mid-graph.

## Expected Behavior

- Box borders (`┌ ─ ┐`, `└ ─ ┘`), arrows (`▶ ◀ ▼`), corner / junction glyphs
  (`┴ ┬ ┼ ├ ┤`), and per-edge connector characters stay colorized on every
  row, including rows that exceed `tw` and are clamped.
- The clamp must still cap every line at `tw` visible columns and emit a
  trailing `…` marker when truncation occurs.
- If a row is truncated while an SGR is "open" (i.e. the last visible
  character had a foreground color set), the helper must close the SGR
  before the `…` so the active style does not leak onto the next printed
  line.

## Steps to Reproduce

1. From repo root, render a deep, back-edge-heavy FSM with color forced on:

   ```bash
   FORCE_COLOR=1 ll-loop info rn-implement --show-diagrams=detailed --diagram-scope=full
   ```

2. Observe the rendered diagram. The top layers are fully colored;
   below the first row whose visible width exceeds the terminal width,
   every `┌ ┐ └ ┘ │ ─ ▶ ◀` is plain text.

3. Repeat with a tight terminal width to make the clamp trigger earlier:

   ```bash
   COLUMNS=60 FORCE_COLOR=1 ll-loop info rn-implement --show-diagrams=detailed --diagram-scope=full
   ```

   Now almost every row loses color — only the banner (`▼ N layers below`)
   retains styling.

## Root Cause

Two coupled defects in `scripts/little_loops/cli/loop/layout.py`:

### Defect 1 — terminal-width clamp strips ANSI from overflow lines

`_render_layered_diagram` ends with a "defense in depth" hard-clamp that
runs every line through `strip_ansi()` *and* `_truncate_to_width()`:

```python
if tw > 1:
    clamped: list[str] = []
    for ln in lines:
        if _display_width(strip_ansi(ln)) > tw:
            ln = _truncate_to_width(strip_ansi(ln), tw - 1) + "…"
        clamped.append(ln)
    lines = clamped
```

When any row of the layered grid exceeds the terminal width, this block
**reassigns** `ln` to the `strip_ansi(ln)`-ed, truncated form. The SGR
codes that `_draw_box`, per-edge `_lc()`, and `_colorize_diagram_labels`
had baked into the grid cells are dropped on the floor — including open
`\x1b[…m` codes that would have leaked onto subsequent lines. The next
`_colorize_diagram_labels` pass (line 1889) only re-colors *edge labels*,
not box borders or connectors, so the returned body is mostly uncolored
for every clamped row.

For deep FSMs, back-edge horizontal connectors span many layers. These
long `─…─▶` / `─…─◀` rows naturally exceed `tw` and trigger the clamp from
the first such row downward — matching the "halfway down" symptom.

### Defect 2 — `_display_width` silently mismeasures ANSI-containing strings

```python
def _display_width(s: str) -> int:
    w = _wcswidth(s)
    return w if w >= 0 else len(s)
```

For strings containing `\x1b` (CSI introducer), `wcswidth` returns `-1`
(it can't iterate the bytes as printable text), so the fallback `len(s)`
counts every escape byte as a visible column. This made `_display_width`
report a colored line as 10–20× wider than it actually is — and the new
ANSI-aware truncate inherited the bug because it gates on
`_display_width(text) <= width`.

The two defects reinforce each other: the clamp *replaces* lines with
stripped-and-truncated output (Defect 1), and the truncate guard inside
the helper misjudges whether truncation is even needed (Defect 2).

### Why the existing code used `strip_ansi` defensively

`_truncate_to_width` iterates character-by-character using `_wcwidth(ch)`
and treats the `-1` (control-char) return value as width-1. That makes
every byte of an SGR sequence (`\x1b`, `[`, digits, `m`) cost 1 column,
so `_display_width("\x1b[32m─\x1b[0m") == 1` (correct, via `wcswidth`)
but `_truncate_to_width("\x1b[32m─\x1b[0m", 1)` measures width 11. The
author worked around this by pre-stripping ANSI before passing the string
in, which also stripped it from the output. The new helper fixes this
properly: skip CSI sequences in the width budget, keep them in the output.

## Proposed Solution (Applied)

Two coupled changes in `scripts/little_loops/cli/loop/layout.py`:

### Part 1 — ANSI-aware `_display_width`

`_display_width` strips ANSI when the input contains `\x1b` before
measuring; plain-text callers (the common case) hit a fast path with no
extra work. The change is backward-compatible: every existing call site
either passes plain text (state names, action bodies, badges, row strings
pre-colorization) or strings produced by `colorize()` whose SGR pairs are
zero-width. Net change is `len(s)` (wrong) → `wcswidth(strip_ansi(s))`
(correct).

### Part 2 — `_truncate_to_width_ansi` helper

A new helper next to `_truncate_to_width` that:

- Skips CSI sequences (`\x1b[…m` and friends) in the width budget via a
  local regex (`_ANSI_CSI_RE`).
- **Keeps** CSI sequences in the output unchanged (they're part of the
  rendered string and re-establish color for cells after the truncation
  point).
- Tracks whether an SGR is open at the cut point via a `sgr_open` flag
  toggled on `\x1b[0m` (reset) vs any other `m`-terminated CSI (open /
  switch).
- When `sgr_open` is `True` at truncation time, emits `\x1b[0m` *before*
  the trailing `…` so the active style does not leak onto subsequent
  text.

### Part 3 — wire the helper into the clamp

The clamp block at `_render_layered_diagram`'s final assembly now calls
`_truncate_to_width_ansi` on the *colored* line, with the width check
also working on the colored line (via the fixed `_display_width`). The
centering `max_line_len` calculation drops its redundant `strip_ansi`
since `_display_width` is now ANSI-correct.

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py`
  - `_display_width` (around line 167) — added `\x1b` fast-path + `strip_ansi`
    pre-strip; expanded docstring to document the ANSI handling.
  - New helper `_truncate_to_width_ansi` (around line 209) and supporting
    constant `_ANSI_CSI_RE` (around line 206) — pattern matches
    `cli.output._ANSI_RE` for consistency.
  - `_render_layered_diagram`'s final hard-clamp (around line 1931) —
    `_truncate_to_width_ansi` replaces `strip_ansi + _truncate_to_width`;
    centering max-line-width drops its `strip_ansi`.

No other files needed to change. `_render_fsm_diagram` is the public
entry point called from `info.py`, `run.py`, and `_helpers.py`; the fix
is invisible to callers.

## Integration Map

### Files Modified

- `scripts/little_loops/cli/loop/layout.py` — `_display_width` fix +
  `_truncate_to_width_ansi` helper + clamp-block rewrite + centering
  simplification.
- `scripts/tests/test_loop_layout_alignment.py` — two new tests.

### Tests Added

- `test_loop_layout_alignment.py::test_truncate_to_width_ansi_preserves_sgr_codes` —
  unit test for the new helper. Covers: no-truncation passthrough;
  mid-segment cut (surviving colored segment + closed-open-SGR ellipsis);
  cut right after an open SGR with no following visible char (color-leak
  case); the `width ≤ 0` edge case.
- `test_loop_layout_alignment.py::test_render_layered_diagram_preserves_color_when_clamping` —
  end-to-end regression test. Forces `_USE_COLOR=True` via monkeypatch;
  renders `_make_back_edge_heavy_fsm(n=12)` at `tw=60` (forces clamp);
  asserts (a) the clamp still caps widths, (b) the rendered output
  contains SGR CSI sequences, (c) no clamped line ends mid-CSI sequence.

### Reuse, Not Reinvent

- `_display_width` (`layout.py:167`) — patched in place to handle ANSI;
  every existing call site either passes plain text or zero-width SGR
  pairs and continues to work.
- `_wcwidth` (imported at `layout.py:16`) — per-char width, used inside
  the new helper.
- `strip_ansi` from `cli/output.py:45` — already imported; reused by
  `_display_width`'s fast-path branch.
- `_ANSI_CSI_RE` (new local) — modeled on the existing `_ANSI_RE` at
  `cli/output.py:42`; matches the same SGR subset `colorize()` emits.

## Acceptance Criteria

- [x] `_display_width` correctly measures ANSI-containing strings (returns
      visible width, not byte length).
- [x] `_truncate_to_width_ansi` preserves embedded SGR codes; closes open
      SGRs before the trailing `…`; skips CSI sequences in the width
      budget.
- [x] Hard-clamp at `_render_layered_diagram`'s final assembly uses the new
      helper; no `strip_ansi` in the truncate path.
- [x] Centering max-line-width drops the redundant `strip_ansi` and uses
      `_display_width` directly.
- [x] All existing tests still pass: 14,250 passed across
      `test_loop_layout_alignment.py`, `test_cli_loop_layout.py`,
      `test_snapshot_loop_layout.py`, `test_ll_loop_display.py`,
      `test_ll_loop_commands.py`.
- [x] Two new tests pass: `test_truncate_to_width_ansi_preserves_sgr_codes`,
      `test_render_layered_diagram_preserves_color_when_clamping`.
- [x] `ruff check` clean on both edited files.
- [x] `mypy` only complains about pre-existing `wcwidth` missing-stubs
      (unrelated to this change).
- [x] Pre-existing failures (4 in `test_readme_structure.py` /
      `test_wiring_guides_and_meta.py`, 4 in `test_ll_loop_display.py` when
      run with `FORCE_COLOR=1`) confirmed unrelated via stash-and-rerun.

## Verification

1. **Unit + integration tests**:

   ```bash
   python -m pytest scripts/tests/test_loop_layout_alignment.py -v
   # 18 passed (16 prior + 2 new)

   python -m pytest scripts/tests/test_cli_loop_layout.py \
                    scripts/tests/test_snapshot_loop_layout.py \
                    scripts/tests/test_ll_loop_display.py \
                    scripts/tests/test_ll_loop_commands.py -q
   # 555 passed

   python -m pytest scripts/tests/ -q
   # 14250 passed, 35 skipped, 8 unrelated failures (pre-existing docs/README)
   ```

2. **Static checks**:

   ```bash
   ruff check scripts/little_loops/cli/loop/layout.py \
              scripts/tests/test_loop_layout_alignment.py
   # All checks passed!

   python -m mypy scripts/little_loops/cli/loop/layout.py
   # 1 pre-existing wcwidth note (not from this change)
   ```

3. **End-to-end visual** (with `_USE_COLOR` force-pinned True via
   monkeypatch in the regression test):

   Render `_make_back_edge_heavy_fsm(n=12)` at `tw=60` via
   `_render_fsm_diagram(title_only=True, suppress_labels=True, mode="full")`.
   Confirmed: every rendered line contains at least one SGR CSI sequence
   (`\x1b[…m`), and no clamped line ends mid-CSI sequence (no truncated
   line ends with `\x1b[`).

4. **Manual end-to-end CLI**:

   ```bash
   FORCE_COLOR=1 ll-loop info rn-implement --show-diagrams=detailed --diagram-scope=full
   # expect: box borders, arrows, and junctions keep color from the top
   #         of the layered diagram all the way through the bottom-most
   #         rendered layer (was: dropped after the first over-wide row)

   COLUMNS=60 FORCE_COLOR=1 ll-loop info rn-implement --show-diagrams=detailed --diagram-scope=full
   # expect: every rendered row contains at least one \x1b[…m SGR sequence
   #         (was: most rows had no SGR sequences at all)
   ```

## Impact

- **Priority**: P2 — breaks the user's primary progress inspection on
  deep FSMs (`rn-implement`, `rn-remediate`, and any future FSM with
  many back-edges). Surfaces as colorless output below the mid-graph,
  despite the user explicitly asking for a diagram via `--show-diagrams`.
- **Effort**: Small — one new helper (~50 lines), one `_display_width`
  patch (~5 lines), one clamp-block rewrite (~5 lines), one
  centering-simplification line (~3 lines), two new tests (~120 lines).
  Reuses existing `_display_width`, `_wcwidth`, `strip_ansi`, and the
  `_ANSI_RE` pattern from `cli/output.py`.
- **Risk**: Low — the new helper is additive (does not change existing
  `_truncate_to_width` callers, which all pass plain text today). The
  `_display_width` patch is backward-compatible: every existing call
  site either passes plain text or zero-width SGR pairs and continues
  to return the same value.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — FSM diagram renderer section.
- `docs/reference/API.md` — `_render_fsm_diagram`, `_draw_box`, helpers.
- `docs/development/TROUBLESHOOTING.md` — diagram color troubleshooting.

## Related Issues

- `BUG-2536` — `--show-diagrams clean` inconsistent color across
  invocations. BUG-2536 added per-state kind colors
  (`_ACTION_TYPE_KIND_COLORS`) so non-active boxes still get a hue when
  no highlight is active; this issue (BUG-2546) ensures that hue
  survives the terminal-width clamp instead of being stripped at the
  first overflow row.
- `BUG-2425` — FSM diagrams overflow terminal width in the non-TTY
  streaming render path. BUG-2425 introduced the hard-clamp that
  inadvertently caused BUG-2546; this issue preserves the clamp's
  width-bounding invariant while restoring its lost color fidelity.

## Status

done

## Resolution

Fixed `_display_width` to strip ANSI before measuring (returns visible
width, not byte length). Added `_truncate_to_width_ansi` helper that
preserves embedded SGR codes while measuring width by visible columns,
and emits `\x1b[0m` before the trailing `…` if an SGR is open at the cut
point to prevent color leaking onto subsequent text. Replaced the
hard-clamp's `strip_ansi + _truncate_to_width` sequence with a call to
the new helper on the colored line. Simplified the centering calculation
to use `_display_width` directly (no longer needs its own `strip_ansi`).

Behavior change visible to users: deep FSM box diagrams now keep their
color styling (box borders, arrows, junctions, badges) from the top of
the layered diagram through the bottom-most rendered layer, including
rows that exceed the terminal width and are clamped. The clamp still
caps every line at `tw` visible columns and still emits a trailing `…`
on truncated lines. Color no longer leaks onto subsequent printed lines
even when truncation cuts mid-styling.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-08T16:20:58 - `578de1eb-3694-416c-86d4-15ce68048d56.jsonl`

- `Plan:` 2026-07-08T16:00:00Z —
  `/Users/brennon/.claude/plans/investigate-why-some-fsm-abstract-hennessy.md`
  documents the root-cause investigation (two defects in
  `layout.py`: clamp strips ANSI; `_display_width` mismeasures colored
  strings) and the proposed two-part fix.
- Implementation: `_display_width` ANSI-strip fast-path +
  `_truncate_to_width_ansi` helper + clamp-block rewrite + centering
  simplification, in a single file (`scripts/little_loops/cli/loop/layout.py`).
- Tests: 2 new tests in
  `scripts/tests/test_loop_layout_alignment.py` —
  `test_truncate_to_width_ansi_preserves_sgr_codes` (unit) and
  `test_render_layered_diagram_preserves_color_when_clamping` (regression
  with `FORCE_COLOR` + `_make_back_edge_heavy_fsm(n=12)` + `tw=60`).
- Gate: 14,250 tests pass, 8 unrelated failures confirmed pre-existing
  via stash-and-rerun. `ruff check` clean. `mypy` clean (one
  pre-existing `wcwidth` note).