# CLI Output Styling Reference

This document covers all CLI output styling, formatting, and rendering code in little-loops.

**Design philosophy**: No third-party styling libraries. All formatting uses Python stdlib (`textwrap`, `shutil`) plus manual ANSI escape codes. `NO_COLOR` env var is respected everywhere. Terminal width is always queried dynamically.

---

## Core Module: `scripts/little_loops/cli/output.py`

The central styling utility imported by most CLI commands.

### Terminal width and size

```python
from little_loops.cli.output import terminal_size, terminal_width, wrap_text

w = terminal_width()                  # int, falls back to 80
cols, rows = terminal_size()          # (int, int), falls back to (80, 24)
text = wrap_text(text, indent="  ", width=None)  # wraps at terminal width
```

`terminal_width()` is a thin wrapper around `terminal_size()` (which calls
`shutil.get_terminal_size((default_cols, default_rows))` and returns
`(columns, lines)`). Prefer `terminal_size()` whenever a layout decision
needs the **rows** dimension — e.g. the pinned-pane fallback ladder in
`ll-loop run --show-diagrams --clear`. Use `terminal_width()` for the
column-only case (the vast majority of callers).

### ANSI color

```python
from little_loops.cli.output import colorize, PRIORITY_COLOR, TYPE_COLOR

colored = colorize("P1", PRIORITY_COLOR["P1"])   # ANSI-wrapped or passthrough
```

`colorize(text, code)` wraps text in `\033[{code}m...\033[0m`. Returns text unchanged when color is disabled.

Color is enabled when `sys.stdout.isatty()` is `True` and `NO_COLOR` env var is absent or empty. Setting `FORCE_COLOR=1` bypasses the TTY check and forces color on. This is evaluated at import time into `_USE_COLOR`.

#### Default color codes

| Key | ANSI Code | Appearance |
|-----|-----------|------------|
| `P0` | `38;5;208;1` | Bold orange |
| `P1` | `38;5;208` | Orange |
| `P2` | `33` | Yellow |
| `P3` | `0` | Default |
| `P4` | `2` | Dim |
| `P5` | `2` | Dim |
| `BUG` | `38;5;208` | Orange |
| `FEAT` | `32` | Green |
| `ENH` | `34` | Blue |
| `EPIC` | `35` | Purple-magenta |

Edge colors (used in FSM diagrams — applied to both label text and connector line characters):

| Label | ANSI Code | Appearance |
|-------|-----------|------------|
| `yes` | `32` | Green |
| `no` | `38;5;208` | Orange |
| `error` | `31` | Red |
| `blocked` | `31` | Red |
| `partial` | `33` | Yellow |
| `retry_exhausted` | `38;5;208` | Orange |
| `rate_limit_exhausted` | `38;5;214` | Amber |
| `throttle_hard` | `38;5;196` | Bold red |
| `next`, `_` | `2` | Dim |

### Startup configuration

Call once after loading config to apply user-defined colors:

```python
from little_loops.cli.output import configure_output
configure_output(config.cli)   # or configure_output(None) for defaults
```

`configure_output` merges `config.cli.colors.priority` and `config.cli.colors.type` into the module-level dicts. `NO_COLOR` env var always takes precedence over config.

---

## Logo: `scripts/little_loops/logo.py`

Reads and prints ASCII art from `scripts/little_loops/assets/ll-cli-logo.txt` (in-package since FEAT-2274). Silent no-op if the file is missing.

```python
from little_loops.logo import print_logo, get_logo

print_logo()          # prints logo with surrounding blank lines
logo = get_logo()     # returns str | None
```

---

## Issue Card: `scripts/little_loops/cli/issues/show.py`

`_render_card(fields)` renders a Unicode box-drawing character summary card for `ll-issues show`.

### Box-drawing characters used

| Char | Unicode | Role |
|------|---------|------|
| `─` | U+2500 | Horizontal border |
| `│` | U+2502 | Vertical border |
| `┌` | U+250C | Top-left corner |
| `┐` | U+2510 | Top-right corner |
| `└` | U+2514 | Bottom-left corner |
| `┘` | U+2518 | Bottom-right corner |
| `├` | U+251C | Left mid-border |
| `┤` | U+2524 | Right mid-border |

### Layout

```
┌──────────────────────────────────────────────────┐
│ FEAT-518: Issue title                            │
├──────────────────────────────────────────────────┤
│ Priority: P3  │  Status: Open                    │
│ Confidence: 85  │  Outcome: 78                   │
│ Cmplx: 22  │  Tcov: 24  │  Ambig: 25  │  Chsrf: 22│
├──────────────────────────────────────────────────┤
│ Summary text wrapped to content                  │
│ width...                                         │
├──────────────────────────────────────────────────┤
│ Source: capture  │  Norm: ✓  │  Fmt: ✗           │
│ Integration: 4 files  │  Labels: cli, ll-issues  │
│ Captured at: 2026-04-18T14:32:07Z                │
│ Completed at: 2026-05-01T09:15:44Z               │
│ History: /ll:capture-issue, /ll:refine-issue     │
├──────────────────────────────────────────────────┤
│ Path: .issues/features/...                       │
└──────────────────────────────────────────────────┘
```

**Detail line fields:**

| Field | Source | Display |
|-------|--------|---------|
| `Source` | `discovered_by` frontmatter | Short alias (`capture`, `scan`, `audit`, `format`) or first 7 chars; omitted if absent |
| `Norm` | Filename pattern check | `✓` if matches `P[0-5]-TYPE-NNN-desc.md`, `✗` otherwise |
| `Fmt` | Required sections check | `✓` if file has all required template sections, `✗` otherwise |
| `Captured at` | `captured_at` frontmatter | ISO 8601 UTC timestamp of issue capture; omitted if absent |
| `Discovered` | `discovered_date` frontmatter | YYYY-MM-DD date when the bug/feature was *observed*; distinct from `captured_at` (ENH-2535) |
| `Discovered commit` | `discovered_commit` frontmatter | First 7 chars of the git SHA (short-form to avoid right-border bleed); omitted if absent (ENH-2535) |
| `Discovered branch` / `Discovered source` / `Upstream` | `discovered_branch` / `discovered_source` / `discovered_external_repo` frontmatter | BUGs benefit most (gives the git-bisect anchor); omitted if absent (ENH-2535) |
| `Completed at` | `completed_at` frontmatter | ISO 8601 UTC timestamp of issue completion; omitted if absent |
| `Decision needed` / `Decision ref` | `decision_needed` + `decision_ref` frontmatter | Coupled form: `Decision needed → <decision_ref>` when both set; explicit `no` when `decision_needed: false`; standalone `Decision ref:` when only `decision_ref` is set (ENH-2535) |
| `Parent` | `parent` frontmatter | `EPIC-NNN (Title)` when epic is resolvable; ID-only when not (ENH-2535) |
| `Blocks` / `Blocked by` / `Depends on` / `Relates to` / `Supersedes` / `Decomposed into` / `Affects` / `Focus area` | relationship edge frontmatter | Comma-joined IDs (ENH-2535) |
| `History` | `## Session Log` body section | Distinct `/ll:*` commands with occurrence counts; omitted if absent |
| `Closing note` / `Cancellation reason` / `Deferral reason` / `Closed by` / `Closed at` / `Deferred at` | closure context frontmatter | Rendered only when status is `done` / `cancelled` / `deferred` (ENH-2535) |

Width is computed dynamically: the maximum of all content line lengths plus 2 padding, with a minimum of 62 characters. The summary section is wrapped with `textwrap.wrap()` to fit the structural width.

---

## Issue List: `scripts/little_loops/cli/issues/list_cmd.py`

`cmd_list` groups issues by type (BUG/FEAT/ENH/EPIC) and colorizes each row:

- Type group headers: bold + type color
- Issue IDs: type color
- Priority labels: priority color

---

## FSM Diagram: `scripts/little_loops/cli/loop/layout.py`

`_render_fsm_diagram(fsm, verbose)` produces a 2D box-drawing ASCII diagram for `ll-loop show`.

### Diagram structure

The renderer produces three sections:

1. **Main flow** — the primary (happy-path) traversal rendered as a horizontal row of boxes connected by labeled arrows
2. **Branches** — alternate forward transitions rendered below with vertical connectors
3. **Back-edges** — transitions to earlier states (cycles) rendered below with U-routing

### State box format

```
┌──[type]──────────────┐
│ → state_name         │
│ action preview...    │
└──────────────────────┘
```

- `→` prefix marks the initial state
- `◉` suffix marks terminal states
- `[type]` badge appears in the **top border row** (not the content area) — e.g., `──[prompt]──`
- The state name in the first content row is rendered **bold** for visual hierarchy
- In non-verbose mode, action is truncated to the first non-empty line with `…`
- Box widths are computed per-state, capped by `max_box_inner` derived from terminal width

### Edge arrows

Main-path arrows between boxes:
```
──label──▶
```

U-route for back-edges (main-to-main):
```
└──────────────────┘
    label text
```

Vertical connectors for off-path states use `│`, `▲`, `▼`, with separate label rows for down/up directions to prevent overlap.

Self-loops render as `↺ label` below the box row.

### Centering

The entire diagram is center-indented: `indent = (terminal_width - total_diagram_width) // 2`

### Edge colorization

Transition edges are colored by semantic type — both connector line characters (`│`, `─`, `▼`, `▶`, corner chars) and label text:

- Color is applied **at draw time**: each grid character (pipe, dash, arrowhead, corner) is wrapped in `colorize(ch, code)` via the `_edge_line_color(label)` helper.
- `_colorize_diagram_labels(diagram)` additionally post-processes the rendered string to colorize label words when bounded by box-drawing or whitespace characters.
- `_collect_edges()` includes `on_blocked` (`"blocked"`), `on_retry_exhausted` (`"retry_exhausted"`), `on_rate_limit_exhausted` (`"rate_limit_exhausted"`), and `on_throttle_hard` (`"throttle_hard"`) transitions in addition to the standard fields.

Default edge color mapping (see `Output Color Reference > Edge colors` above for ANSI codes):

| Label keyword | Color |
|---------------|-------|
| `yes` | Green |
| `no` | Orange |
| `error` | Red |
| `blocked` | Red |
| `partial` | Yellow |
| `retry_exhausted` | Orange |
| `rate_limit_exhausted` | Amber |
| `throttle_hard` | Bold red |
| `next` / `_` (default) | Dim |

Edge label colors are **user-configurable** via `cli.colors.fsm_edge_labels` in `ll-config.json`. See [`CONFIGURATION.md → cli.colors.fsm_edge_labels`](CONFIGURATION.md#clicolorsfsm_edge_labels).

> **Note:** `rate_limit_waiting` is a heartbeat event emitted during rate-limit backoff, not an FSM transition edge label. It does not appear in the `_EDGE_LABEL_COLORS` dict and is not colorized in diagrams. Rate-limit activity is visually indicated by the `rate_limit_exhausted` edge (Amber) when the retry budget runs out.

> **Note:** `cli.colors.fsm_edge_labels` governs more than diagram arrows. As of ENH-1050, the same config key also controls:
> - The `✓`/`✗` verdict symbol colors in `StateFeedRenderer.handle_event()` (the `yes`, `no`, and `error` keys map to checkmark and x-mark colors during evaluate events)
> - The `[TERMINAL]` marker color in `print_execution_plan()` (uses the `yes` key, defaulting to green)

The active state highlight color is configurable via `cli.colors.fsm_active_state` (default: green `32`). The same value drives both border coloring and interior background fill: the fg color code is automatically converted to its bg equivalent (e.g. `"32"` → bg `"42"`) so all interior cells are filled with the highlight color. Border glyphs (`┌ ─ ┐ │ └ ┘`) also carry the bg fill (e.g. `\033[32;42m│`) so the colored region runs edge-to-edge with no visible gap between the fill and the border. The state name and content lines render with a bright white foreground (`97`) over the colored background for legibility across light and dark terminal themes. Compound ANSI codes (e.g. `"38;5;208"`) cannot be auto-converted and fall back to border-only coloring. See [`CONFIGURATION.md → cli.colors.fsm_active_state`](CONFIGURATION.md#clicolorsfsm_active_state).

### State overview table

`_print_state_overview_table(fsm)` (`cli/loop/info.py`) renders a compact aligned table below the diagram:

```
  State          Type    Action Preview                   Transitions
  ─────────────  ──────  ───────────────────────────────  ──────────────────
  → run          prompt  Analyze the current issue and…   success──→ verify
    verify       shell   python -m pytest scripts/...     success/fail──→ ...
```

Column widths adapt to terminal width. Long values are truncated with `…` (U+2026).

---

## Sprint Visualization: `scripts/little_loops/cli/sprint/show.py`

`_render_dependency_graph(waves, dep_graph)` renders an ASCII dependency graph:

```
  FEAT-100 ──→ FEAT-200 ──→ BUG-300
  FEAT-100 ──→ ENH-400

Legend: ──→ blocks (must complete before)
```

`_render_health_summary(...)` produces a single-line sprint health status:

```
OK -- 8 issues in 3 waves, overlap serialized
BLOCKED -- dependency cycles detected
REVIEW -- 2 potential dependency(ies) to review
```

---

## Dependency Map: `scripts/little_loops/dependency_mapper/formatting.py`

`format_report(report)` renders a Markdown dependency analysis report with tables.

`format_text_graph(issues, proposals)` renders an ASCII dependency graph with three arrow styles:

| Arrow | Meaning |
|-------|---------|
| `──→` | Existing `blocked_by` dependency |
| `-->` | Soft `depends_on` prerequisite |
| `-.→` | Proposed dependency |

`format_epic_tree(root_id, root_info, child_map, graph, use_color)` renders an EPIC child hierarchy as a Unicode box-drawing tree. Children appear with `├──`/`└──` connectors, status badges (`[done]`, `[blocked]`), and `⮡ blocks ISSUE-NNN` annotations under each blocker. Ordered via `DependencyGraph.topological_sort()`.

---

## Issue History: `scripts/little_loops/issue_history/formatting.py`

Multiple output format functions for `ll-history`:

| Function | Output format |
|----------|--------------|
| `format_summary_text(summary)` | Plain text with `=`/`-` headers and aligned columns |
| `format_summary_json(summary)` | JSON |
| `format_analysis_text(analysis)` | Plain text with unicode trend arrows (`↑↓→`) |
| `format_analysis_json(analysis)` | JSON |
| `format_analysis_yaml(analysis)` | YAML (falls back to JSON if `pyyaml` not installed) |
| `format_analysis_markdown(analysis)` | Markdown with tables and emoji badges (🔥⚡🔴🟠🟡✓⚠️) |

The Markdown formatter uses emoji only for machine-rendered output (files/PRs), not for TTY display.

---

## Adding New Styled Output

1. Import from `little_loops.cli.output`:
   ```python
   from little_loops.cli.output import colorize, terminal_width, wrap_text
   ```
2. Use `terminal_width()` for any layout calculations — never hardcode widths.
3. Call `colorize(text, code)` for color — it automatically no-ops when color is disabled.
4. For new color mappings, add to `PRIORITY_COLOR` or `TYPE_COLOR` in `output.py`, or define a local dict following the same ANSI code format.
5. Respect `NO_COLOR` by routing all color through `colorize()` rather than embedding raw ANSI escapes inline.
