---
id: BUG-2597
title: windowed-diagram stub-pipe terminators still used the pre-decision filled-semicircle glyphs
type: BUG
status: done
priority: P4
discovered_date: '2026-07-11'
discovered_by: user-report
captured_at: '2026-07-11T13:20:58Z'
completed_at: '2026-07-11T13:20:58Z'
labels:
- cli
- ll-loop
- diagram
---

# BUG-2597: windowed-diagram stub-pipe terminators still used the pre-decision filled-semicircle glyphs

## Summary

`ll-loop run` output (and any `--show-diagrams` windowed preset) was rendering
stub-pipe cut-boundary terminators as the filled semicircles `◓`/`◒`
(U+25D3/U+25D2), even though the glyph choice had already been changed to the
open half-circle arcs `◠`/`◡` (U+25E0/U+25E1). The user flagged this from
actual `ll-loop run` output pasted into the session ("why is our ll-loop run
output showing the old top and bottom connector font glyphs ... We updated
these glyphs - Investigate and fix.").

## Steps to Reproduce

1. Configure `.ll/ll-config.json` with `loops.run_defaults.show_diagrams: "clean"`
   (or pass `--show-diagrams clean`/any preset that resolves to the window
   rung) against an FSM tall enough to crop above or below the active state.
2. Run `ll-loop run <loop> <input>`.
3. Observe the stub-pipe terminator glyph at the top/bottom cut boundary row.

## Current Behavior

Terminators rendered as the filled semicircles `◓` (top cut) / `◒` (bottom
cut) — the original ENH-2593 glyph choice, superseded by a later decision
that was never implemented.

## Expected Behavior

Terminators render as the open half-circle arcs `◠` (top cut) / `◡` (bottom
cut).

## Impact

- **Priority**: P4 — cosmetic display glyph mismatch, no functional impact
  on loop execution.
- **Effort**: Trivial — two character literals plus matching test/doc
  updates.
- **Risk**: None — purely visual; guarded by the existing
  `TestWindowedDiagramStubTerminators` suite.

## Root Cause

ENH-2593 ("windowed-diagram stub-pipe terminator glyphs at cut boundaries"),
completed earlier the same day (commit `159c3d09`), shipped with `◓` (top
cut) / `◒` (bottom cut) in `_render_layered_diagram`
(`scripts/little_loops/cli/loop/layout.py:1917-1936`). A follow-on decision
to use `◠`/`◡` instead was made but never implemented — a repo-wide grep for
`U+25E0`/`U+25E1`/`◠`/`◡` turned up zero matches (code, `.ll/decisions.yaml`,
git stash, or any other branch) before this fix, confirming the change was
never landed.

## Resolution

- `scripts/little_loops/cli/loop/layout.py:1917-1936` — swapped the two
  terminator literals (`◓`→`◠` for top cuts, `◒`→`◡` for bottom cuts) and
  updated the block comment describing them.
- `scripts/tests/test_ll_loop_display.py` —
  `TestWindowedDiagramStubTerminators` (3 tests: top-stub, bottom-stub,
  full-span-pipe-stays-blanked) updated to assert the new glyphs.
- `.issues/enhancements/P3-ENH-2593-windowed-diagram-stub-pipe-terminator-glyphs.md`
  — corrected all glyph/codepoint references (Summary, Expected Behavior,
  Proposed Solution, Acceptance Criteria, visual-confirmation examples) to
  match what actually ships, without reopening/changing its `done` status.

No config, badge-merge, or call-path changes were needed — this was a
two-character literal swap plus the tests/docs describing them.

## Verification

- `python -m pytest scripts/tests/test_ll_loop_display.py::TestWindowedDiagram scripts/tests/test_ll_loop_display.py::TestWindowedDiagramPassThroughPipes scripts/tests/test_ll_loop_display.py::TestWindowedDiagramStubTerminators scripts/tests/test_ll_loop_display.py::TestWindowedLadderIntegration scripts/tests/test_ll_loop_display.py::TestWindowTopologyValue -n 0` — 18 passed.
- Full suite: `python -m pytest scripts/tests/ -n auto` — 14587 passed, 36
  skipped, 3 failed. The 3 failures
  (`test_check_decisions_yaml_hook.py::test_hook_blocks_othe_203_write`,
  `test_hook_blocks_othe_203_edit`, `test_hook_skips_when_validator_missing`)
  are a pre-existing, unrelated syntax bug in
  `hooks/scripts/check-decisions-yaml.sh:176` — confirmed present on `main`
  via `git stash` before this change, not caused by it.

## Status

**Done** | Completed: 2026-07-11 | Priority: P4

## Session Log
- `hook:posttooluse-status-done` - 2026-07-11T13:21:22 - `68fc7658-0e11-482c-835a-e5321340a519.jsonl`
- manual session - 2026-07-11T13:20:58Z - diagnosed via plan-mode investigation of `ll-loop run` output, glyph literal swap, test/doc corrections
