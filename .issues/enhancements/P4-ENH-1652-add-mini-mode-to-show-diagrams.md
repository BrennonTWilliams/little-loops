---
discovered_commit: a91f22d573a72b5bb9b0aeff14de3102ab3dfdd8
discovered_branch: main
discovered_date: 2026-05-23
captured_at: '2026-05-24T02:16:50Z'
discovered_by: capture-issue
status: open
---

# ENH-1652: Add `mini` Mode to `--show-diagrams`

## Summary

Extend `ll-loop run` (and `ll-loop resume`) `--show-diagrams` to accept a
third mode value: `mini`. In `mini`, each FSM state box renders only its
title (no body lines / verdict descriptions) and edges between states
render without their text labels. The result is a compact "skeleton" view
useful for very large loops where even `main` mode is too dense.

## Current Behavior

`--show-diagrams` (added in FEAT-642, expanded in ENH-1641) accepts two
modes:

- `main` (default) — happy-path edges only; full state box contents.
- `full` — every edge (including error / blocked / retry_exhausted /
  rate_limit_exhausted / throttle_hard / partial); full state box contents.

Both modes render the same per-state box content (state name + body lines)
and the same edge label text (`yes`, `no`, `next`, verdict keys, etc.).
There is no rendering mode that strips visual detail for skeleton viewing.

## Expected Behavior

`--show-diagrams=mini` produces a maximally compact diagram:

- Each FSM state box contains only the state's title (state name / key) —
  no body lines, no verdict listings, no inner content.
- Edges between states render as plain connector lines/arrows with no
  text labels (no `yes` / `no` / `next` / verdict-key strings on the
  connectors).
- Active-state highlighting still applies (consistent with `main` / `full`).
- Edge-set semantics: `mini` follows the same happy-path filter as
  `main` by default (off-happy-path edges hidden) — see Open Questions.

## Motivation

- For large loops with many states, even `main` mode can wrap or scroll.
  `mini` gives a "map view" suitable for orienting before zooming in.
- Useful when sharing or screenshotting an FSM shape without leaking
  verdict / route details.
- Cheap to add: builds directly on ENH-1641's mode plumbing — argparse
  already accepts a `choices=` list, the layout pipeline already has a
  `mode` parameter, and the body-line / edge-label render points are
  localized in `layout.py`.

## Use Case

```bash
ll-loop run big-loop.yaml --show-diagrams=mini
# tight skeleton: just state-title boxes connected by unlabeled arrows
```

## Acceptance Criteria

- [ ] `--show-diagrams=mini` is accepted on both `run` and `resume`
      subparsers (added to argparse `choices`)
- [ ] In `mini`, each rendered FSM state box shows only the state title
      (no body lines / verdict listings)
- [ ] In `mini`, edges render without label text (just connectors/arrows)
- [ ] Active-state highlight still applies in `mini`
- [ ] `main` and `full` outputs are unchanged
- [ ] Help text on `--show-diagrams` lists `mini` alongside `main`/`full`
- [ ] CHANGELOG entry under the next release notes the new mode
- [ ] Tests cover: mini argparse parse, mini state-box title-only render,
      mini edges-without-labels render, mini active-state highlight

## API/Interface

```
ll-loop run    <config> [--show-diagrams[=main|full|mini]] ...
ll-loop resume <config> [--show-diagrams[=main|full|mini]] ...
```

- `--show-diagrams=mini` — title-only boxes, unlabeled edges.
- Bare `--show-diagrams` still defaults to `main` (unchanged from ENH-1641).

## Implementation Steps

1. `scripts/little_loops/cli/loop/__init__.py` (lines 143 and 262) —
   add `"mini"` to the `choices=["main", "full"]` list on both `run` and
   `resume` subparsers. Update each entry's `help=` text.
2. `scripts/little_loops/cli/loop/layout.py` — extend `_render_fsm_diagram`
   to handle `mode == "mini"`:
   - Reuse `_filter_main_path_graph` (or document the decision in
     Open Questions if `mini` should show all edges) to pick the edge set.
   - When `mode == "mini"`, suppress per-state body lines so each box
     contains only the state title.
   - When `mode == "mini"`, render edges without their label text (the
     existing `_colorize_label` / label-printing path should be skipped
     or routed to an empty-string variant).
3. `scripts/little_loops/cli/loop/_helpers.py` — no logic change needed;
   subprocess re-emission already forwards the raw mode string verbatim.
4. Update `docs/reference/CLI.md` and `docs/guides/LOOPS_GUIDE.md` flag
   tables to list `mini` alongside `main`/`full`.
5. Update `CHANGELOG.md` "Added" entry.
6. Add tests in `scripts/tests/test_ll_loop_display.py`:
   - `test_show_diagrams_mini_argparse_accepts_mini`
   - `test_show_diagrams_mini_box_contains_only_state_title`
   - `test_show_diagrams_mini_edges_have_no_labels`
   - `test_show_diagrams_mini_active_state_still_highlighted`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete edit points** (supersedes the abstract sketches above where they conflict):

- **Step 1** (`__init__.py`) — extend the `choices` list and the `help=` string on both subparsers.
  The `help=` change is *required* for `mini` to show up in `--help`, because `metavar="MODE"`
  suppresses the auto-generated choices listing.
- **Step 2** (`layout.py`) requires three coordinated edits, not two:
  1. **Edge filter** — at `layout.py:1582`, change `if mode == "main":` to
     `if mode in ("main", "mini"):` so `mini` inherits `main`'s `_filter_main_path_graph` edge set
     (per Open Question #1's tentative resolution).
  2. **Body-line suppression** — thread a flag (`title_only: bool` or `mode: str`) through
     `_compute_box_sizes` (`:518`) into `_box_inner_lines` (`:150-188`). In `_box_inner_lines`,
     gate the action-row loop (lines 168-188) on `not title_only` so only `name_line` (line 163)
     is appended for `mini`.
  3. **Label suppression** — in `_render_layered_diagram`, guard the two label grid-writes at
     `:1147-1154` (forward arrows) and `:1370-1374` (back-edge margin) on `mode != "mini"`.
     Audit `_render_horizontal_simple` (`:1611+`) for an equivalent grid-write site and suppress
     there too. `_colorize_diagram_labels` (`:1512`) needs no change — it's a no-op on absent
     labels.
- **Step 3** (`_helpers.py`) — **logic change IS required**. At `_helpers.py:638-644`, extend the
  whitelist tuple in `run_foreground` from `("main", "full")` to `("main", "full", "mini")`,
  otherwise `mini` is silently coerced to `None`. The `verbose = show_diagrams_mode == "full"`
  coupling at `:274` already produces the right value (`False`) for `mini` without change.

**Test patterns to mirror** (all in `scripts/tests/test_ll_loop_display.py`):

- **`test_show_diagrams_mini_argparse_accepts_mini`** goes in the existing
  `TestShowDiagramsArgparse` class (`:3188`), mirroring `test_show_diagrams_equals_full` (`:3215-3217`).
  Reuse the `_parse_run_args` helper (`:3192`).
- The three render tests go in a new `TestShowDiagramsMiniMode` class alongside the existing
  `TestShowDiagramsMode` class (`:3078`). Call `_render_fsm_diagram(fsm, mode="mini")` directly
  (no CLI layer); strip ANSI with `plain = re.compile(r"\033\[[0-9;]*m").sub("", result)` for
  substring assertions.
- **`test_show_diagrams_mini_edges_have_no_labels`** mirrors `test_show_diagrams_main_hides_error_edges`
  (`:3098-3125`), but asserts absence of *all* labels: `assert "yes" not in plain`,
  `"no" not in plain`, `"next" not in plain`.
- **`test_show_diagrams_mini_active_state_still_highlighted`** mirrors
  `test_highlighted_state_default_green` (`:1281-1289` in `TestRenderFsmDiagram`). Patch
  `output_mod._USE_COLOR=True`, call with `highlight_state=...`, and assert both border color
  (`"\033[32m" in result`) and the `dd99eeda`-added background fill (`"\033[42m " in result`).
- For **box-content** assertions, the `TestRenderFsmDiagram.test_main_flow_order` pattern (`:779`)
  isolates box-interior lines with `[ln for ln in lines if state in ln and "│" in ln]`.

## Scope Boundaries

- **Out of scope**: New edge-set semantics. `mini` reuses `main`'s edge
  filter unless Open Questions resolves otherwise — no new filter rules.
- **Out of scope**: `ll-loop info` static diagram dumps — keep defaulting
  to `full` (matches ENH-1641's scope decision).
- **Out of scope**: Sub-loop child diagrams — mode propagation to children
  is tracked under ENH-846 / FEAT-1311.
- **Out of scope**: A `display.default_diagram_mode` config key.

## Open Questions

1. **Edge set for `mini`** — Should `mini` inherit `main`'s happy-path-only
   filter (recommended for visual consistency with the "compact view"
   intent), or render the full edge set with no labels? Tentative default:
   inherit `main`'s filter.
2. **Box border style** — Should `mini` use a thinner / single-line border
   to further reduce visual weight, or keep the existing box style? Default
   recommendation: keep existing border to preserve active-state highlight
   semantics already wired in.
3. **Neighborhood-diagram mode propagation** — `_render_neighborhood_diagram`
   (`layout.py:1707-1708`) has its own `if mode == "main":` branch and is reached
   when `_build_pinned_pane` (`_helpers.py:292`) falls back because the active
   state is unreachable under `main`'s filter. Should `mini` also be wired
   through the neighborhood path (suppressing labels + body lines there too), or
   should the neighborhood path always render `full`-style detail since it's
   already a zoomed-in fallback? Default recommendation: treat the neighborhood
   path as full-detail (it's already focused on a small subgraph), and document
   this limitation in `mini`'s help text. _(Discovered during refinement; not
   in original capture.)_

## Impact

- **Priority**: P4 — UX polish on an opt-in display flag. No automation
  depends on it.
- **Effort**: Small — argparse `choices` extension + two localized render
  branches in `layout.py` + tests / docs.
- **Risk**: Low — purely additive. Existing `main` / `full` rendering
  untouched.
- **Breaking Change**: None.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `"mini"` to `choices=` on
  `--show-diagrams` (lines ~143 and ~262 on `run`/`resume` subparsers).
- `scripts/little_loops/cli/loop/layout.py` — handle `mode == "mini"` in
  `_render_fsm_diagram` (title-only box content + unlabeled edges).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` — forwards raw mode string verbatim;
  no logic change needed (noted in Implementation Steps).

### Similar Patterns
- `main` / `full` mode branches already in `_render_fsm_diagram` — `mini` follows
  the same conditional structure using `_filter_main_path_graph` for edge selection.

### Tests
- `scripts/tests/test_ll_loop_display.py` — new `TestShowDiagramsMiniMode`
  class with the four tests listed in Implementation Steps.

### Documentation
- `CHANGELOG.md` — "Added" entry.
- `docs/reference/CLI.md` — `ll-loop run` / `ll-loop resume` flag tables.
- `docs/guides/LOOPS_GUIDE.md` — flag listing.

### Configuration
- N/A — no config key added (per Scope Boundaries: `display.default_diagram_mode` is out of scope).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Argparse lines verified** — `choices=["main", "full"]` is at `scripts/little_loops/cli/loop/__init__.py:143`
  (`run`) and `:262` (`resume`), exactly as the issue claims. `metavar="MODE"` is set on both, which
  suppresses `choices=` from `--help` auto-output, so the `help=` prose must be updated manually for
  `mini` to appear in help text.
- **`_helpers.py` claim is INCOMPLETE** — the issue's step 3 says "no logic change needed". This is
  wrong for `cmd_run` / `run_foreground` at `_helpers.py:638-644`, which whitelist-filters the mode
  string: `elif raw_show_diagrams in ("main", "full"): show_diagrams_mode = raw_show_diagrams; else: show_diagrams_mode = None`.
  A new `"mini"` value would silently fall through to `None` and disable diagrams entirely. The
  whitelist tuple at line 641 **must** be extended to `("main", "full", "mini")`. (The other
  forwarding site — `run_background:567-569` — does pass the raw string verbatim and needs no change.)
- **Single mode branch in `_render_fsm_diagram`** — the only `mode` consumer is one `if mode == "main"`
  at `layout.py:1582-1583` (which calls `_filter_main_path_graph` to drop off-happy-path edges). To
  inherit `main`'s edge set per Open Question #1, this becomes `if mode in ("main", "mini")`.
- **Edge labels are NOT routed through `_colorize_label`** — the issue's Implementation Steps step 2
  suggests skipping the `_colorize_label` path. Reality: `_colorize_label` (`layout.py:41`) is not
  called from either render path. Labels are written directly into the character grid at
  `_render_layered_diagram` lines 1147-1154 (forward inter-layer arrows) and 1370-1374 (back-edge
  margin labels), then ANSI-colorized post-hoc via `_colorize_diagram_labels` (line 1512). For `mini`,
  the suppression points are the two grid-write blocks at 1147-1154 and 1370-1374.
- **Body-line render point** — per-state box body lines are built in `_box_inner_lines`
  (`layout.py:150-188`), called via `_compute_box_sizes` (`layout.py:518`) from both `_render_layered_diagram`
  and `_render_horizontal_simple`. For `mini`, suppression needs to skip lines 168-188 (action rows),
  keeping only line 163 (`name_line`). Threading a `mode` (or a new `body_lines: bool`) parameter
  through `_compute_box_sizes` → `_box_inner_lines` is the cleanest plumbing path.
- **Active-state highlighting is independent of `mode`** — `_render_layered_diagram:1024` uses
  `is_highlighted = highlight_state is not None and sname == highlight_state`, and `_draw_box`
  applies ANSI to border + name row regardless of body content. `mini` will get highlighting for free
  without any change. (The recent `dd99eeda` background-fill commit hooks into the same path.)
- **`verbose` is already correctly coupled** — `_helpers.py:274` sets `verbose = show_diagrams_mode == "full"`,
  so `mini` (and `main`) will already evaluate to `verbose=False`. No change needed here.
- **Second render path** — `_render_horizontal_simple` (`layout.py:1611+`) is the alternate renderer
  used for small/horizontal layouts. It shares `_compute_box_sizes` (so body-line suppression carries
  over) but its label-drawing path is separate from the layered renderer and must also be audited
  for `mini` label suppression.
- **`_render_neighborhood_diagram` also has a `mode == "main"` branch** at `layout.py:1707-1708`. The
  issue does not mention this. It's reached when `_build_pinned_pane` (`_helpers.py:292`) falls back
  because the active state is unreachable under `main`'s filter. See new Open Question #3.

## Labels

`enhancement`, `cli`, `loop`, `ux`, `diagram`

## Related Key Documentation

- ENH-1641 (done) — added `main` / `full` modes; this builds on the same
  argparse + `_render_fsm_diagram(mode=...)` plumbing.
- FEAT-642 (done) — original `--show-diagrams` flag.
- BUG-1499, BUG-1500, BUG-1651 — label-positioning bugs in the labeled
  render path; `mini` sidesteps these by suppressing labels.
- ENH-846 / FEAT-1311 — sub-loop diagram propagation; mode forwarding to
  child diagrams is tracked there.
- `docs/ARCHITECTURE.md` — system design context for the loop runtime.

## Session Log
- `/ll:refine-issue` - 2026-05-24T02:43:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9eaefb33-d00d-4955-9bd3-f90c748f44ef.jsonl`
- `/ll:format-issue` - 2026-05-24T02:24:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11a32bd-ee0b-4bc3-aa81-bbd2c70eaca5.jsonl`
- `/ll:capture-issue` - 2026-05-24T02:16:50Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/facffb2c-69ed-4e7f-9785-031798b54171.jsonl`

---

**Status**: open | Created: 2026-05-23 | Priority: P4
