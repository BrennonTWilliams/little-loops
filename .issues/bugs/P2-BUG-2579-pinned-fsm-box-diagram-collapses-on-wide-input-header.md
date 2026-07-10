---
id: BUG-2579
title: Pinned FSM box diagram collapses to single-line when a header artifact line is wider than the terminal
type: BUG
status: done
priority: P2
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T19:03:40Z'
completed_at: '2026-07-10T19:03:40Z'
labels:
- ll-loop
- cli
- output
- diagram
- pinned-pane
- general-task
- regression-guard
confidence_score: 96
outcome_confidence: 95
---

# BUG-2579: Pinned FSM box diagram collapses to single-line when a header artifact line is wider than the terminal

## Summary

Running `ll-loop run general-task "<task>"` (in the `cards` workspace), the FSM box
diagram was never drawn in the live CLI output — the pinned pane silently degraded to
the one-line `fsm: … → [state] → …` floor on every state transition, regardless of
terminal height. The `--dry-run` diagram (static path) rendered the full box fine, and
the project config was correct (`loops.run_defaults.show_diagrams: "clean"`,
`clear: true`), which localized the failure to the **live pinned-pane path**.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchors**: `_build_pinned_pane()` (header assembly) + `_choose_pinned_layout()`
  (variant width filter) + `_artifact_lines()` (path-like classification)
- **Cause**: The pinned pane is built by `_build_pinned_pane` (header + diagram +
  iteration line + separator); `_choose_pinned_layout` then picks the most-detailed
  rung whose *widest* line fits `cols` — the BUG-2425 width filter
  (`_variant_width(variant) > cols → continue`). The header artifact/model lines were
  appended **untruncated**, while the header separator was already clamped to `cols`.

  `_artifact_lines` classifies any context string containing `/` as a path-like value
  and emits it as a header line. The task input
  `"Audit … in design/ …"` contains `design/`, so it was emitted as a ~146-column
  `input:` header line on a 111-column terminal. Because that one over-wide line is
  present in **every** rung (full / window / neighborhood / single), `_variant_width`
  reported 146 > 111 for all of them, the width filter rejected every box variant, and
  the loop fell through to the unconditional single-line floor. Net effect: no box, at
  any terminal height.

  The BUG-2425 filter was intended to gate on the **diagram's** width; a long
  non-diagram header line poisoned the measurement.

## Steps to Reproduce

1. In a project with `loops.run_defaults` set to `show_diagrams: "clean"` + `clear: true`,
   run a large built-in loop (e.g. `general-task`) whose task `input` both contains a `/`
   and is longer than the terminal is wide, on a normal-width TTY:
   `ll-loop run general-task "Audit codebase vs specs in design/ and fix gaps"`.
2. Watch the live output as states advance.
3. Observe the pinned pane shows only `fsm: … → [state] → …` — the box diagram never appears.

Reproduction proof (terminal width 111, rows 40):

| Task input | `input:` in header? | Pane chosen |
|---|---|---|
| `"…in design/ …"` (146 cols, has `/`) | yes | single-line, **box=False** |
| same task, `/` removed | no (excluded by `_artifact_lines`) | **box drawn**, height 35 |

## Expected Behavior

The pinned pane renders the FSM box diagram (degrading gracefully through the
full → window → neighborhood ladder to fit the viewport). Header metadata length must
not affect whether the diagram is a box.

## Current Behavior

Any pinned rung containing an over-wide header line was rejected by the width filter, so
the pane collapsed to the single-line `fsm:` floor for the entire run, independent of
terminal height. (Fixed — this section describes the pre-fix behavior.)

## Impact

The live FSM box diagram — the primary progress affordance for a running loop — was
invisible for any `general-task` run whose task description was longer than the terminal
width and contained a `/` (extremely common for real tasks that reference a path such as
`design/` or `src/`). Users lost the at-a-glance view of which state the loop was in and
how the graph was progressing, degrading the interactive experience to a single status
line. No data loss or incorrect results — cosmetic/output-fidelity only, hence P2.

## Status

Completed (`done`) on 2026-07-10. Fix and regression test landed; full test suite green.

## Resolution

- **Action**: fix
- **Completed**: 2026-07-10
- **Status**: Completed

### Fix

Clamp the pinned-pane header artifact/model lines to `cols` display columns in
`_build_pinned_pane`, matching how the header separators are already clamped. Reuse the
existing ANSI-aware `_truncate_to_width_ansi` (`scripts/little_loops/cli/loop/layout.py`)
because the values are wrapped in `colorize(value, "2")` (embedded SGR) — plain
truncation would corrupt styling.

```python
for key, value in _artifact_lines(fsm, loop_path):
    lines.append(_truncate_to_width_ansi(f"  {key}: {colorize(value, '2')}", cols))
if model is not None:
    lines.append(_truncate_to_width_ansi(f"  model: {colorize(model, '2')}", cols))
```

Now every header line is ≤ `cols`, so `_variant_width` reflects only the diagram width
(the gate the filter was meant to apply) and box rungs are chosen whenever they fit. The
change is also defensive against any other long path-like artifact value (e.g. a deeply
nested `run_dir`).

Out of scope (deliberately not changed): tightening `_artifact_lines` so free-text
`input` isn't treated as a path — the clamp alone fixes the bug, and a truncated `input:`
line is harmless/informative. The non-pinned header prints (`_helpers.py` streaming intro
and `handle_event` non-pinned branch) do not feed `_choose_pinned_layout`, so they don't
cause the collapse and were left unchanged.

### Files Changed

- `scripts/little_loops/cli/loop/_helpers.py` — `_build_pinned_pane()`: added
  `_truncate_to_width_ansi` to the layout import block and wrapped the header
  artifact/model line appends with a `cols`-width clamp.
- `scripts/tests/test_loop_layout_alignment.py` — added
  `test_pinned_header_wide_input_does_not_collapse_box` (builds a multi-state FSM with a
  `>cols` slash-containing `input`, runs the ladder through `_choose_pinned_layout`, and
  asserts a box border `┌` is chosen and no line exceeds `cols`).

### Verification Results

- New regression test fails on the pre-fix code (pane collapses to the single-line floor,
  no `┌`) and passes after the fix — verified by temporarily reverting the clamp.
- Affected suites: `test_loop_layout_alignment.py`, `test_state_feed_renderer.py`,
  `test_ll_loop_display.py` — 316 passed.
- Full gate `python -m pytest scripts/tests/`: 14506 passed, 36 skipped.
- `ruff check` and `mypy` clean on the edited source file.

### Notes

- `general-task` uses `on_handoff: spawn`, so after a context handoff it continues in a
  detached background session where stdout is not a TTY and no diagram renders at all —
  that is expected and separate from this bug. This fix concerns the foreground portion.

## Acceptance Criteria

- The live pinned pane renders the FSM box diagram when a task `input` (or other
  path-like context value) is longer than the terminal is wide.
- Header artifact/model lines are clamped to the terminal width and never poison the
  pinned-pane width filter.
- A regression test guards box selection under a wide, slash-containing `input`.
- The full `scripts/tests/` suite passes.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-10T19:04:20 - `00128cb8-aae5-408b-a682-0ab0daa9eba4.jsonl`
