---
id: ENH-2604
title: Merge ll-loop run header lines onto one line when terminal width allows
type: ENH
status: done
priority: P4
size: Small
discovered_date: '2026-07-11'
discovered_by: user-report
captured_at: '2026-07-11T15:29:58Z'
completed_at: '2026-07-11T15:29:58Z'
---

# ENH-2604: Merge `ll-loop run` header lines onto one line when width allows

## Summary

In `show_diagrams: clean` mode, `ll-loop run` printed its artifact header
(`loop:`, `input:`, `run_dir:`, `model:`) across a fixed two-line layout —
`loop:`/`input:` on line 1, `run_dir:`/`model:` on line 2 — regardless of
terminal width. On wide terminals this wasted a line for no reason.

## Change

`_render_artifact_header_lines` in
`scripts/little_loops/cli/loop/_helpers.py:1277` now greedily merges the
existing rows (built with the same fixed pairing as before — `input` always
stays with `loop`, `model` always stays with `run_dir`) onto a single line
front-to-back as long as the combined line still fits within the terminal's
display-column width (measured via the existing ANSI/wcwidth-aware
`_display_width` helper in `scripts/little_loops/cli/loop/layout.py:167`).
When everything fits, all four label/value pairs print on one line. When
they don't, the row(s) that don't fit spill to a second line, each kept
whole (no reflow-induced truncation) — `_truncate_to_width_ansi` truncation
still applies only as a last resort for a single value too long to fit even
alone (e.g. an oversized `input:` string), same as before.

No call-site changes were needed — both the pinned/alt-screen renderer
(`_helpers.py:583-587`) and the non-pinned streaming renderer
(`_helpers.py:1011-1018`) already passed `cols`/`tw` through.

## Tests

Added 3 new cases to `TestRenderArtifactHeaderLines` in
`scripts/tests/test_state_feed_renderer.py`:
- all four pairs merge onto one line at a width that fits everything, with
  no truncation ellipsis
- both pairs spill onto two untruncated lines at a width that fits neither
  pair merged nor holds them both
- both pairs truncated independently (each ending in `…`) at a very narrow
  width, matching prior behavior

All 6 pre-existing tests in that class continued to pass unchanged (traced
individually — each either already produced a single row, or used a width
wide enough that substring assertions hold regardless of the merge).

## Verification

- `python -m pytest scripts/tests/test_state_feed_renderer.py -k ArtifactHeaderLines -v` — 9/9 passed
- `python -m pytest scripts/tests/` — full suite passed except 3 pre-existing,
  unrelated failures in `test_check_decisions_yaml_hook.py` (a shell-syntax
  bug in `hooks/scripts/check-decisions-yaml.sh`), confirmed present on
  `main` before this change via `git stash`
- `ruff check` on the two touched files — clean
- Manual: called `_render_artifact_header_lines` directly at cols
  200/70/65/60/50/30/10 against a fixture with all four fields populated and
  confirmed the exact expected collapse/reflow/truncate behavior at each
  width

## Impact

- **Priority**: P4 — cosmetic CLI output improvement, no functional risk.
- **Effort**: Small — one function changed, no new dependencies or
  call-site changes.
- **Risk**: Low — purely additive line-packing logic; existing truncation
  safety net unchanged.

## Files Changed

- `scripts/little_loops/cli/loop/_helpers.py` — `_render_artifact_header_lines`
- `scripts/tests/test_state_feed_renderer.py` — `TestRenderArtifactHeaderLines`

---

## Resolution

- **Status**: Done
- **Completed**: 2026-07-11
- **Reason**: Implemented, tested, and verified in-session; no further work needed.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-11T15:30:23 - `1cb9ffb9-9344-4f25-9315-0e6c8c39283f.jsonl`

---

## Status

- [x] Done
