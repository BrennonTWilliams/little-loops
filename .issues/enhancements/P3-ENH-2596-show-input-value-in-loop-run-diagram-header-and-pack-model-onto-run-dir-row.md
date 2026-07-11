---
id: ENH-2596
title: "Show input value in ll-loop run diagram header; pack model onto run_dir row"
type: ENH
priority: P3
status: open
captured_at: "2026-07-11T02:25:55Z"
discovered_date: "2026-07-11"
discovered_by: capture-issue
labels: [cli, fsm-loops, display]
---

# ENH-2596: Show input value in ll-loop run diagram header; pack model onto run_dir row

## Summary

When `ll-loop run <loop>` renders the FSM Box Diagram header (shown when
`--show-diagrams`/`--clear` or `loops.run_defaults.show_diagrams` is active), the
header currently lists `loop:`, `run_dir:`, and `model:` each on its own line.
Enhance the header so that:

1. **`input:` is displayed** — when a value is passed to the `--input` positional
   argument of `ll-loop run`, render `input: <string>` on the **same line** as the
   `loop:` field, positioned to the right of the `loop:` value, and **truncated to
   the remaining terminal width** so it never wraps or overflows.
2. **`model:` moves up** — render the `model:` field/value on the **same line** as
   `run_dir:`, to the right of the `run_dir:` value, instead of on its own line.

This compresses a 4-line header (`loop`, `run_dir`, `model`, plus separator) into
2 content lines and surfaces the run's input — currently invisible unless it
happens to look like a path.

## Motivation

The `--input` value is the single most important piece of per-run context (it's
what distinguishes one run of a loop from another), yet it is **not shown** in the
diagram header today. `_artifact_lines()` only surfaces context values that look
path-like (start with `.`/`/`/`~` or contain `/`), so a plain-string input is
silently dropped from the header. Operators watching a pinned diagram cannot tell
what input a run is processing.

Meanwhile `model:` occupies a full line for a short value, wasting vertical space
in the pinned pane where rows are scarce.

## Current Behavior

Header renders as (roughly):

```
== loop: rn-implement ==============================================
  loop: loops/rn-implement.yaml
  run_dir: .loops/runs/rn-implement/2026-07-11T02-25
  model: claude-opus-4-8
```

The input string passed to `ll-loop run rn-implement '<some input>'` appears
nowhere.

## Desired Behavior

```
== loop: rn-implement ==============================================
  loop: loops/rn-implement.yaml        input: <some input string, trunc…>
  run_dir: .loops/runs/rn-implement/2026-…    model: claude-opus-4-8
```

- `input:` right of `loop:`, truncated (with ellipsis) at the terminal's right edge.
- `model:` right of `run_dir:` on the same row.
- When no `--input` is passed, the `input:` segment is omitted entirely (no empty
  `input:` label).
- Layout must stay width-safe: the combined line is clamped to terminal columns via
  the existing `_truncate_to_width_ansi` helper (pinned) / width math (non-pinned).

## Root Cause / Where It Lives

The header is rendered in **two parallel paths** in
`scripts/little_loops/cli/loop/_helpers.py` — both must be updated to stay
consistent:

- **Non-pinned (streaming) path** — `StateFeedRenderer.handle_event()`,
  `_helpers.py:988-1009`. Prints `loop:`/`run_dir:` via `_artifact_lines()` then a
  separate `model:` line.
- **Pinned path** (`--clear` + `--show-diagrams` on a TTY) —
  `_build_pinned_pane()`, `_helpers.py:568-586`. Builds the same lines into a list,
  clamping each with `_truncate_to_width_ansi(..., cols)`.

Supporting anchors:
- `_artifact_lines(fsm, loop_path)` — `_helpers.py:1223-1245`. Emits `(key, value)`
  pairs; currently drops non-path-like `input`. It filters `context` for path-like
  strings, so the plain `input` string is excluded.
- Input injection — `cmd_run()` in `scripts/little_loops/cli/loop/run.py:142-156`.
  The `--input` value is stored in `fsm.context[fsm.input_key]` **before** the
  renderer is constructed, so it is available at render time via
  `fsm.context.get(fsm.input_key)`.
- Terminal width — `terminal_width()` / `terminal_size()` in
  `scripts/little_loops/cli/output.py:17-29` (already used at `_helpers.py:896` and
  `_helpers.py:631`).
- `--input` arg definition — `cli/loop/__init__.py:125-130`.

Note: `_artifact_lines()` also surfaces `run_dir` (a path-like context value), so
the `run_dir:` row and the `input:`/`model:` packing must be reconciled with the
generic `(key, value)` loop rather than hard-coded field names.

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchors verified against current tree:_

- **All referenced anchors resolve** (line numbers drifted slightly since capture):
  - Non-pinned render: `_helpers.py:1005-1008` (the `_artifact_lines` loop at 1005-1006
    + the standalone `model:` line at 1007-1008), inside `StateFeedRenderer.handle_event()`.
  - Pinned render: `_helpers.py:583-586` (the `_artifact_lines` loop at 583-584 + the
    standalone `model:` line at 585-586), inside `_build_pinned_pane()`.
  - `_artifact_lines(fsm, loop_path)` — `_helpers.py:1223-1245` (path-like filter at 1243).
  - `fsm.input_key` default is `"input"` — `fsm/schema.py:1100`; loops may override it.
- **Input retrieval caveat (refines Implementation Step 1)**: `cmd_run()` at
  `run.py:143-158` does **not** always store the input under `fsm.input_key`. It tries
  `json.loads(raw)`; if the result is a **dict whose keys match existing `fsm.context`
  keys**, those keys are spread into `fsm.context` and the raw string is **not** stored
  under `input_key`. Only a plain string, a non-dict JSON value, or a dict with **no**
  matching keys lands in `fsm.context[fsm.input_key]`. So `fsm.context.get(fsm.input_key)`
  will be empty for the dict-spread case — the header will legitimately show no `input:`
  segment there, which is acceptable (there's no single scalar to show), but the
  implementation must not assume the key is always populated when `--input` was passed.
- **`_truncate_to_width_ansi` is a locally-imported helper**, not module-level — it's
  imported inside `_build_pinned_pane()` at `_helpers.py:480`. The non-pinned path
  (Step 2) currently does no ANSI-aware truncation, so it must import the same helper
  (or compute remaining width via `terminal_width()` from `cli/output.py:27`) to keep
  the new `loop: … input: …` line width-safe. `terminal_size()`/`terminal_width()` at
  `cli/output.py:17-29` are the width sources both paths already use.
- **No external dependencies** — this is a pure internal-rendering change; no
  learning-test targets apply.

## Implementation Steps

1. **Retrieve the input string** at render time from
   `fsm.context.get(fsm.input_key)` (fall back to `"input"` key). Guard on
   non-empty; omit the segment when absent/empty.
2. **Non-pinned path (`_helpers.py:988-1009`)**: after printing the `loop:` line,
   append ` input: <val>` to that same line, computing remaining width as
   `terminal_width() - len(rendered_loop_segment)` and truncating the input with an
   ellipsis. Likewise, when printing the `run_dir:` line, append ` model: <val>` to
   the right instead of emitting a separate `model:` line.
3. **Pinned path (`_helpers.py:568-586`)**: mirror the same composition, using
   `_truncate_to_width_ansi(line, cols)` on the combined line. Preserve the existing
   width-poisoning guard noted in the code comment (a long path-like value must not
   break `_variant_width`).
4. **Decide the `input:`/`model:` column layout**: either right-align to the column
   width or use a fixed gap after the left field. Match whichever reads cleanly at
   narrow widths; when the left field alone already exceeds columns, drop the right
   segment (don't wrap).
5. **Keep `_artifact_lines()` semantics intact** for other path-like context keys;
   only special-case the `loop`+`input` and `run_dir`+`model` pairings at the
   render sites (or extend `_artifact_lines` to optionally include the raw input —
   but rendering the pairing at the call sites is cleaner and avoids changing the
   path-like contract).

## Acceptance Criteria

- [ ] Running `ll-loop run <loop> '<input>' --show-diagrams` shows `input: <input>`
      to the right of `loop:` on the same line, truncated with an ellipsis at the
      terminal's right edge (no wrap, no overflow past columns).
- [ ] `model:` appears to the right of `run_dir:` on the same line; no standalone
      `model:` line remains.
- [ ] When `--input` is omitted, no `input:` segment (and no empty label) is shown.
- [ ] Both the non-pinned (`_helpers.py:988-1009`) and pinned
      (`_helpers.py:568-586`) rendering paths produce the new layout consistently.
- [ ] Narrow-terminal safety: at small `COLUMNS` (e.g. 40), the header lines are
      clamped to width and the pinned-pane box variants are not collapsed by a long
      input/path value.
- [ ] `python -m pytest scripts/tests/` passes, with coverage for: input present +
      truncation, input absent, and `model` packed onto the `run_dir` row.

## Related

- `scripts/little_loops/cli/loop/_helpers.py` — both header render paths
- `scripts/little_loops/cli/loop/run.py:142-156` — input injection into context
- `scripts/little_loops/cli/output.py:17-29` — terminal width helpers
- ENH-2410 (windowed scroll to active FSM diagram) — same diagram subsystem
- ENH-732 (unicode state-box badges) — same renderer

## Session Log
- `/ll:refine-issue` - 2026-07-11T02:29:26 - `9859904b-114d-493f-9aa2-ecb165d0f2a6.jsonl`
- `/ll:capture-issue` - 2026-07-11T02:25:55Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11ed0446-f871-4a32-8bcc-af7cd8af2d67.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-07-11
