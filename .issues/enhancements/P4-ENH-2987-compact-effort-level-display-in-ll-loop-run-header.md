---
id: ENH-2987
title: Compact the effort-level display in ll-loop run's model header
type: ENH
priority: P4
status: done
discovered_date: '2026-08-02'
discovered_by: user
labels:
- cli
- loop-runner
- display
program_design_not_applicable: true
completed_at: '2026-08-02T02:46:26Z'
---

# ENH-2987: Compact the effort-level display in `ll-loop run`'s model header

## Summary

`ll-loop run`'s header line displayed the reasoning effort next to the model
name as `model: <model> [<EFFORT>]` (e.g. `claude-opus-4-8 [LOW]`). The user
asked for a more compact form: no brackets, and the effort word abbreviated
to a 1-2 letter code, still separated from the model name by a single space
(e.g. `claude-opus-4-8 L`).

## Current Behavior

Two call sites in `scripts/little_loops/cli/loop/_helpers.py` independently
built the bracketed, upper-cased suffix inline:

- `_render_artifact_header_lines` (diagram/artifact header) —
  `f"{model} [{effort.upper()}]"`
- the live progress header printed at the top of `ll-loop run` —
  `f"{model} [{effort.upper()}]"`

## Expected Behavior

Both sites render `<model> <CODE>` with no brackets, where `<CODE>` is a
1-2 letter abbreviation of the effort level:

| effort  | code |
|---------|------|
| low     | L    |
| medium  | M    |
| high    | H    |
| xhigh   | XH   |
| max     | MX   |

(MAX was clarified with the user as `MX` rather than `M`, to avoid colliding
with MEDIUM's code.)

## Program Design

Deduplicated the two inline literals into one helper instead of just
editing both format strings in place:

```python
_EFFORT_CODES = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "MX"}

def _effort_code(effort: str) -> str:
    return _EFFORT_CODES.get(effort.lower(), effort.upper())
```

Both call sites now read `f"{model} {_effort_code(effort)}"`. Falling back to
`effort.upper()` for an unrecognized effort value keeps the display sane
instead of silently dropping the suffix.

### Call Path

- `scripts/little_loops/cli/loop/_helpers.py:_render_artifact_header_lines` —
  new `_effort_code()` helper added just above it; `model_display` line
  updated
- `scripts/little_loops/cli/loop/_helpers.py` — live progress header's
  `model_line` assignment updated to call the same helper
- Docstring on `_render_artifact_header_lines` updated to describe the new
  no-bracket, abbreviated-code format

## Implementation Steps

1. Add the `_EFFORT_CODES` mapping and `_effort_code()` helper.
2. Update both format-string call sites to use the helper.
3. Update the `_render_artifact_header_lines` docstring.
4. Update the two `test_state_feed_renderer.py` assertions pinned to the old
   bracketed format.
5. Run the full test suite.

## Test Plan

Updated the two existing tests that asserted the old bracketed format
(`scripts/tests/test_state_feed_renderer.py`):

- `test_effort_appended_as_code_to_model_value` (was
  `test_effort_appended_bracketed_upper_to_model_value`) — asserts
  `"claude-opus-4-8 L" in model_line` for `effort="low"`
- `test_effort_suffix_on_run_dir_packed_model_line` — asserts
  `"claude-opus-4-8 XH" in run_dir_line` for `effort="xhigh"`

No new tests were added; this is a display-format change to existing,
already-covered behavior.

## Acceptance Criteria

- [x] `model:` header shows `<model> <CODE>` with no brackets, for both the
      live progress header and the diagram/artifact header
- [x] Effort codes match the table above (`L`/`M`/`H`/`XH`/`MX`)
- [x] `effort.upper()` fallback preserved for unrecognized effort strings
- [x] `python -m pytest scripts/tests/test_state_feed_renderer.py` passes
- [x] Full suite (`python -m pytest scripts/tests/`) passes with no other
      test asserting on the old bracketed format

## Impact

**Who is affected:** anyone running `ll-loop run` with `--effort` set (or a
loop/state default effort) — a purely cosmetic, non-breaking display change.

**Blast radius:** contained to the two header-rendering call sites in
`_helpers.py`; no change to loop execution, effort resolution, or FSM
semantics.

## Scope Boundaries

**In scope:** the two `model:` header format strings and their tests.

**Out of scope:** any other place effort/severity/priority tags use a
similar `[UPPER]` bracket convention (e.g. `pii.py`, `issue_history/
formatting.py`, `fsm/validation/_base.py`) — unrelated domains, not touched.

## Notes

Requested interactively in the same session as BUG-2981 follow-up work. The
MEDIUM/MAX code collision (both naively abbreviate to `M`) was caught during
planning and resolved by asking the user directly rather than guessing.

## Resolution

- **Action**: implemented
- **Completed**: 2026-08-02
- **Status**: Done

### Files Changed

- `scripts/little_loops/cli/loop/_helpers.py` — added `_EFFORT_CODES`/
  `_effort_code()`, updated both `model:` header format strings and the
  `_render_artifact_header_lines` docstring
- `scripts/tests/test_state_feed_renderer.py` — updated two assertions
  (and one test name) pinned to the old bracketed format

### Verification Results

- `python -m pytest scripts/tests/test_state_feed_renderer.py -v` — 48
  passed
- `python -m pytest scripts/tests/` — 17783 passed, 42 skipped


## Session Log
- `hook:posttooluse-status-done` - 2026-08-02T02:46:56 - `b360f77a-8b84-4f44-8f4a-b5a73e38f270.jsonl`
