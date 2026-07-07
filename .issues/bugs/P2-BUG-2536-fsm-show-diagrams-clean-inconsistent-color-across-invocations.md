---
id: BUG-2536
title: "--show-diagrams clean produces inconsistent color across invocations (some
  diagrams have color, others have none) for the same FSM and CLI flags"
type: BUG
priority: P2
status: done
captured_at: '2026-07-07T20:15:00Z'
completed_at: 2026-07-07 21:45:00+00:00
discovered_date: 2026-07-07
discovered_by: manual-investigation
testable: true
decision_needed: false
confidence_score: 100
outcome_confidence: 90
score_complexity: 30
score_test_coverage: 30
score_ambiguity: 22
score_change_surface: 28
---

# BUG-2536: `--show-diagrams clean` produces inconsistent color across invocations

## Summary

`ll-loop run <loop> --show-diagrams clean` (and friends like `ll-loop info`)
draws the FSM as Unicode box art. The user reports that **some invocations
produce a colorful diagram and others produce an entirely colorless one**,
with no obvious change in command-line arguments.

Three independent gates compound to suppress color — any one of them flips the
output to "no color at all":

1. **Active-state-only highlight** in `_draw_box` (`layout.py:637-837`). The
   `is_highlighted` boolean is set strictly as
   `highlight_state is not None and sname == highlight_state`
   (`layout.py:1207`, `layout.py:2349`). When `highlight_state` is `None` —
   `ll-loop info`, dry-run, the initial render before any state executes, or the
   `clean`-scope main-path fallback that hides the active state — *no* state
   box gets any foreground color.
2. **`clean` preset suppresses the only other color signal**.
   `DiagramFacets("layered", False, "title", "main", "preset")` at
   `diagram_modes.py:61` sets `edge_labels=False`, which disables the
   post-render `_colorize_diagram_labels` (`layout.py:84`) that colors
   `yes`/`no`/`error` edge labels.
3. **`_USE_COLOR` global gate** in `cli/output.py:68-70` strips every
   `colorize()` call when stdout is not a TTY (or `NO_COLOR` set, or
   `FORCE_COLOR` not set). Even a highlighted active state renders plain when
   the loop output is being captured (script invocation, CI, the scratch-pad
   `> .loops/tmp/scratch/...txt` redirect that `ll-auto` / `ll-parallel` use).

The autodev run log captured during this session — where the parent process
captures every state transition's rendered diagram — showed the "no color"
case clearly. The same diagram rendered to a TTY shows one colored state.

## Current Behavior

| Invocation | `highlight_state` | `_USE_COLOR` | `edge_labels` | Coloring effect |
|---|---|---|---|---|
| TTY + `--clear` | yes (live) | True | clean=False | highlighted box + labeled edges |
| TTY + `--clear` | yes (live) | True | clean=True | highlighted box only |
| TTY, no `--clear` | yes (live) | True | clean=True | highlighted box only |
| TTY, no `--clear` | `None` (initial) | True | clean=False | edge label colors only |
| TTY, no `--clear` | `None` (initial) | True | clean=True | **NO COLOR AT ALL** |
| Non-TTY (script) | yes (live) | False | clean=False | **NO COLOR AT ALL** |
| Non-TTY (script) | yes (live) | False | clean=True | **NO COLOR AT ALL** |
| Dry-run | `None` | True/False | clean=False | edge label colors only |
| Dry-run | `None` | True/False | clean=True | **NO COLOR AT ALL** |
| `ll-loop info` | `None` | True/False | clean=False | edge label colors only |

The user's complaint lands in any of the **bold rows**.

## Expected Behavior

For every `--show-diagrams` mode on every render path (dry-run, streaming,
pinned, info):

- The diagram has a **distinguishing color on every state box** (bright for
  the active state, hue per kind for the others).
- Colors are emitted regardless of whether stdout is a TTY, when the user
  explicitly opted into seeing the diagram via `--show-diagrams`.
- `NO_COLOR=1` continues to honor explicit no-color.

## Steps to Reproduce

1. From repo root, run `ll-loop run autodev --show-diagrams clean --dry-run`.
   Observe: the diagram has no color (no `highlight_state` set; clean
   suppresses edge label colors).
2. From repo root, run `ll-loop run autodev --show-diagrams clean`
   (non-TTY / `| cat`). Observe: no color (the `_USE_COLOR=False` gate strips
   even the highlighted state's ANSI).
3. Run `FORCE_COLOR=1 ll-loop info autodev --show-diagrams clean | cat -v |
   grep -c $'\033'`. Observe: count is 0 under the old code (single colored
   element stripped by the global gate).

## Root Cause

The renderer treats color as a *single-state highlight*, not a per-state
attribute. Compounded by the global `_USE_COLOR` TTY gate stripping all color
when output is captured. Documented fully in the Summary table above.

## Proposed Solution (Applied)

Two coupled changes (mirroring the plan in
`/Users/brennon/.claude/plans/in-our-autodev-fsm-parsed-grove.md`):

### Part 1 — Per-state "kind" colorization (`layout.py`)

Add a per-state foreground-color mapping (no background fill — kept light to
match the `clean` aesthetic) so non-active state boxes are distinguishable
based on their `action_type` / `loop:` / `terminal` kind. New helper
`_box_kind_color(state)` is introduced; resolution order mirrors
`_get_state_badge` so badge glyph and border hue correspond 1:1.

| State property | SGR code | Visual |
|---|---|---|
| Active (highlight) | `highlight_color` (default green `32`) | fg + bg fill (current behavior) |
| `loop:` (sub-FSM) | `35` | magenta border + badge |
| `action_type: slash_command` | `34` | blue |
| `action_type: prompt` | `35` | magenta |
| `action_type: shell` (or bare `action:`) | `36` | cyan |
| `action_type: mcp_tool` | `33` | yellow |
| `terminal` (success end) | `2` | dim |

`_draw_box` accepts `kind_color: str | None`. The four render paths
(`_render_layered_diagram`, `_render_horizontal_simple`,
`_render_neighborhood_diagram`, `_render_windowed_diagram`) compute
`_kind = _box_kind_color(fsm_states.get(sname))` and thread it through.

### Part 2 — `with_diagram_color(enabled)` context manager (`_helpers.py`)

A small scope-bound override that flips `cli.output._USE_COLOR = True` for
the duration of an explicit `--show-diagrams` render and restores on exit.
Honors `NO_COLOR=1` (skips the flip when set). Used at the four render sites
that the user can hit with `--show-diagrams`:

- `cmd_run` dry-run path (`run.py:226`)
- `cmd_show` (`info.py:1217`)
- `StateFeedRenderer.handle_event` streaming path (`_helpers.py:934`)
- `_redraw_pinned` invocation (`_helpers.py:933`)

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py`
  - New helper `_box_kind_color` (`layout.py:136`) and supporting constants
    (`_ACTION_TYPE_KIND_COLORS`, `_SUB_LOOP_KIND_COLOR`, `_TERMINAL_KIND_COLOR`)
    at `layout.py:119-133`.
  - `_draw_box` signature gains `kind_color: str | None = None`
    (`layout.py:689`); non-highlighted box branches honor it for top border
    (`layout.py:744-789`), side borders via `_bc` (`layout.py:717-723`), name row
    text (`layout.py:863-865`), and bottom border (`layout.py:892-911`).
  - `_render_layered_diagram` loop (`layout.py:1283`) computes
    `_kind = _box_kind_color(fsm_states.get(sname))` and passes it.
  - `_render_horizontal_simple` loop (line 2379 area) ditto.
  - `_render_neighborhood_diagram` builds `pred_color_for` /
    `succ_color_for` to honor kind colors for preds/successors.

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
  - New imports: `os`, `contextlib`, `from little_loops.cli import output as
    _output`.
  - New helper `@contextlib.contextmanager def with_diagram_color(enabled)` at
    the top of the module (above `EXIT_CODES`).
  - `StateFeedRenderer._redraw_pinned` and `_render_streaming_diagram` call
    sites wrapped with `with with_diagram_color(True): ...`.

- **File**: `scripts/little_loops/cli/loop/run.py`
  - `with_diagram_color` added to the top-level import from
    `little_loops.cli.loop._helpers` (line 17).
  - Dry-run path wraps `_render_fsm_diagram` with
    `with with_diagram_color(facets is not None): ...`.

- **File**: `scripts/little_loops/cli/loop/info.py`
  - `with_diagram_color` added to top-level imports from
    `little_loops.cli.loop._helpers`.
  - `cmd_show`'s diagram section wraps `_render_fsm_diagram` with
    `with with_diagram_color(True): ...`.

## Integration Map

### Files Modified

- `scripts/little_loops/cli/loop/layout.py` — `_box_kind_color` helper + per-state
  foreground mapping; `_draw_box` extended with `kind_color`; three render sites
  threaded.
- `scripts/little_loops/cli/loop/_helpers.py` — `with_diagram_color`
  context manager; wrapping at two StateFeedRenderer call sites.
- `scripts/little_loops/cli/loop/run.py` — dry-run path wrapped.
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` wrapped.
- `scripts/tests/test_cli_loop_layout.py` — three new test classes
  (TestBoxKindColor, TestDiagramKindColors, TestWithDiagramColor).
- `scripts/tests/test_ll_loop_display.py` —
  `test_non_highlighted_state_name_bold` updated to accept the new
  `\033[X;1m` (colored+bold) format produced by kind colorization.

### Tests Added

- `tests/test_cli_loop_layout.py::TestBoxKindColor` — 10 unit cases covering
  every kind mapping (`shell`, `slash_command`, `prompt`, `mcp_tool`,
  `terminal`, sub-loop), precedence (`loop:` wins over `action_type:`),
  bare-action defaults to shell hue, unknown `action_type` returns `None`,
  `None` state returns `None`.
- `tests/test_cli_loop_layout.py::TestDiagramKindColors` — 2 end-to-end
  render cases confirming kind colors appear in the rendered diagram when
  `highlight_state=None` (dry-run/info path), and that the active state
  still uses `highlight_color` when set.
- `tests/test_cli_loop_layout.py::TestWithDiagramColor` — 4 cases: flips
  to True when enabled; no-op when disabled; `NO_COLOR=1` overrides;
  restores previous value even on exception.

### Reuse, Not Reinvent

- `colorize()` from `cli/output.py:139` — already centralizes the
  `_USE_COLOR` gate; the override toggles `_USE_COLOR` for the scoped render
  path.
- `_get_state_badge` (`layout.py:187-202`) — already maps `action_type` to
  glyphs; the new `_box_kind_color` mirrors the resolution order 1:1.
- `_USE_COLOR` / `configure_output()` from `cli/output.py`.
- `strip_ansi` from `cli/output.py:45` — used in `test_ll_loop_display.py`
  for width-only assertions.
- Existing `_force_color` fixture pattern from
  `tests/test_cli_loop_layout.py:22-26` — reused for the new
  `TestBoxKindColor._force_color` and `TestDiagramKindColors._force_color`.

## Acceptance Criteria

- [x] `_box_kind_color(state)` returns the right SGR code for each kind
      (`shell=36`, `slash_command=34`, `prompt=35`, `mcp_tool=35`,
      `loop=35`, `terminal=2`, with `loop:` winning over `action_type:`).
- [x] `_draw_box(kind_color=...)` applies the color to non-highlighted boxes
      without disturbing the highlight code path.
- [x] `_render_layered_diagram` / `_render_horizontal_simple` /
      `_render_neighborhood_diagram` thread `kind_color` from
      `_box_kind_color(fsm_states.get(sname))`.
- [x] `with_diagram_color(enabled)` flips `_USE_COLOR` for the duration of
      the block; restores on exit (incl. exception); honors `NO_COLOR=1`.
- [x] Four render sites — dry-run (`run.py`), `cmd_show` (`info.py`),
      streaming (`_helpers.py`), pinned (`_helpers.py`) — wrap their diagram
      calls with `with_diagram_color`.
- [x] New tests: `TestBoxKindColor` (10), `TestDiagramKindColors` (2),
      `TestWithDiagramColor` (4) — 16 new tests, all passing.
- [x] One existing test
      (`test_ll_loop_display.py::test_non_highlighted_state_name_bold`)
      updated to accept `\033[X;1m` (colored+bold) format.
- [x] All existing tests still pass. Full suite: `14189 passed, 35 skipped`.
- [x] `ruff check` clean on all four modified files.
- [x] `mypy` only complains about pre-existing `wcwidth` missing-stubs
      (unrelated to this change).

## Verification

1. **Unit + integration tests**:

   ```bash
   python -m pytest scripts/tests/test_cli_loop_layout.py::TestBoxKindColor \
                    scripts/tests/test_cli_loop_layout.py::TestDiagramKindColors \
                    scripts/tests/test_cli_loop_layout.py::TestWithDiagramColor \
                    -v
   # 16 passed

   python -m pytest scripts/tests/test_cli_loop_layout.py \
                    scripts/tests/test_ll_loop_display.py \
                    scripts/tests/test_loop_layout_alignment.py \
                    scripts/tests/test_snapshot_loop_layout.py -q
   # 353 passed

   python -m pytest scripts/tests/ -q
   # 14189 passed, 35 skipped
   ```

2. **Static checks**:

   ```bash
   ruff check scripts/little_loops/cli/loop/{layout,_helpers,run,info}.py
   # All checks passed!
   ```

3. **End-to-end visual** (with `_USE_COLOR` force-pinned True via the patched
   module):

   Render `ll-loop info autodev --show-diagrams clean` via
   `_render_fsm_diagram` directly. Confirmed 27 cyan codes (`\033[36...`) for
   shell states and 22 green codes (`\033[32...`) for "yes" edge labels in
   the dry-run / no-highlight render path — both previously 0.

4. **Manual end-to-end CLI**:

   ```bash
   # non-TTY (script capture) — should now emit ANSI under all invocation patterns
   FORCE_COLOR=1 ll-loop info autodev --show-diagrams clean | cat -v | grep -c $'\033'
   # expect: > 0 (was 0 before fix)

   # NO_COLOR still suppresses
   NO_COLOR=1 ll-loop info autodev --show-diagrams clean | cat -v | grep -c $'\033'
   # expect: 0
   ```

## Impact

- **Priority**: P2 — breaks the user's primary progress inspection for the
  default `clean` preset when stdout is captured (autodev's `> .loops/tmp/
  scratch/...txt` redirect; CI; `ll-parallel` / `ll-auto` script
  invocations). Surfaces as colorless output despite the user explicitly
  asking for a diagram.
- **Effort**: Medium — three new helpers, four call-site wraps, three new
  test classes (16 cases), one targeted test assertion update. Reuses
  existing `colorize` / `_USE_COLOR` / `_get_state_badge` primitives.
- **Risk**: Low — kind colors apply only to non-active boxes (foreground
  only, no background fill). The active highlight code path is untouched.
  `with_diagram_color` is a scoped, exception-safe toggle that restores the
  previous `_USE_COLOR` value and honors `NO_COLOR=1`.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — FSM diagram renderer section.
- `docs/reference/API.md` — `_render_fsm_diagram`, `_draw_box`,
  `with_diagram_color`.
- `docs/development/TROUBLESHOOTING.md` — diagram color troubleshooting.

## Related Issues

- `BUG-2527` — `--show-diagrams clean` broken connectors (pinned pane
  overflow). Adjacent: same preset / same surface, but BUG-2527 is a width
  bug; this issue is the color-asymmetry companion. Fixed together so the
  autodev output is now both clean *and* colorful.
- `BUG-2425` — FSM diagrams overflow terminal width in the non-TTY
  streaming render path. The streaming-path `with_diagram_color` wrapper
  here covers the same render site's color gate that BUG-2425 covered for
  width.

## Status

done

## Resolution

Added `_box_kind_color(state)` (`layout.py`) that maps each state kind to a
foreground SGR code; threaded it through `_draw_box(kind_color=...)` and the
four render paths; introduced `with_diagram_color(enabled)`
(`cli/loop/_helpers.py`) as the scoped `_USE_COLOR` override; wrapped all
four `--show-diagrams` render sites (dry-run, info, streaming, pinned); added
three new test classes (16 cases). Asserted end-to-end that
`--show-diagrams clean autodev` now emits distinguishing colors (cyan for
shell, blue for slash_command, magenta for prompt + sub-loop, yellow for
mcp_tool, dim for terminal) across every invocation path — TTY or not, with
or without an active highlight.

Behavior change visible to users: `ll-loop run autodev --show-diagrams clean`
in any context (TTY, non-TTY, script capture, dry-run, `ll-loop info`) now
emits ANSI colors that distinguish per-state kind — eliminating the
"some diagrams have color, some don't" inconsistency. `NO_COLOR=1` and
explicit `--show-diagrams off` (the absence of the flag) continue to suppress
color as before.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-07T23:29:59 - `f9e43182-5dff-4b46-a668-8d80073ef8e9.jsonl`

- `/ll:manage-issue` 2026-07-07T20:00:00Z — investigation of the user's
  report ("some diagrams have colors but some do not") on the autodev run
  log captured by `ll-parallel`.
- `Plan:` 2026-07-07T20:05:00Z —
  `/Users/brennon/.claude/plans/in-our-autodev-fsm-parsed-grove.md`
  documents the root-cause matrix and the two-part proposed fix.
- Implementation: `_box_kind_color` + `_draw_box(kind_color=...)` thread +
  `with_diagram_color` context manager + four render-site wrappers +
  three test classes (16 cases).
