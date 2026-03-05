# ENH-586: Improve visual polish of `ll-loop show --verbose` output

## Summary

The `ll-loop show <name> --verbose` command produces well-structured content but with poor visual polish and a diagram that is too high-level to be useful. This enhancement covers a set of targeted improvements: fixing a diagram rendering bug, adding color and type context to diagram nodes, introducing a state overview table, and improving metadata layout — all while preserving full content without aggressive truncation.

## Current Behavior

```
── issue-refinement ──────────────────────────────────────────────────────
Paradigm: fsm
Max iterations: 100
On handoff: spawn
Source: .loops/issue-refinement.yaml
  3 states · 5 transitions · fsm paradigm

Diagram:
  ┌────────────┐             ┌────────┐
  │ → evaluate │───success──▶│ done ◉ │
  └────────────┘             └────────┘
        │ ▲
fail/error│pnextal
        ▼ │
      ┌─────┐
      │ fix │
      └─────┘
```

Specific problems:

1. **Rendering bug**: Vertical connector label rows smash `fail/error` and `pnextal` (`partial` + `next`) together — `down_col` and `up_col` are adjacent and both label strings are written into the same `row[]` array, causing overlap (`info.py:_render_2d_diagram`, lines ~447-463).
2. **Diagram is too high-level**: Boxes only contain state names — no type badge (shell/prompt/llm), no action preview. The diagram cannot answer "what does this state do?" without reading the full States section.
3. **Flat metadata header**: All metadata fields (`Paradigm`, `Max iterations`, `On handoff`, `Source`, stats) have identical visual weight — no hierarchy.
4. **No state overview table**: The verbose states section is a dense wall of text with no quick-reference summary.
5. **No color on transition labels**: `success`, `fail`, `error`, `partial` arrows look identical — visual differentiation is lost.
6. **Aggressive truncation**: Prompt-type state actions get truncated aggressively (3-line cap + `...`), making the output less useful in verbose mode. Verbose mode should show more, not just slightly more than non-verbose.

## Expected Behavior

### 1. Fix diagram label collision bug

Separate `down_labels` and `up_labels` text onto distinct rows or push columns far enough apart to prevent character overlap. Labels like `fail/error` and `next` should appear cleanly, one per side.

### 2. State type badges in diagram boxes

Each node box grows from 3 rows to 5 rows, adding a type badge and action preview line:

```
┌──────────────────────────────────┐
│ → evaluate  [shell]              │
│   ll-issues refine-status --no-k │
└──────────────────────────────────┘
```

The action preview should be truncated only to terminal width minus box padding — no hard 70-char limit.

### 3. Action preview in boxes: multi-line support, avoid aggressive truncation

For `prompt`-type states (which have long multi-line actions), show the first **2-3 lines** of the action in the box rather than a single truncated line. This requires the box to expand vertically. In `--verbose` mode, the diagram should show **all action lines** for prompt states, wrapping within the box width.

Example for a prompt state in verbose:
```
┌──────────────────────────────────────────┐
│ fix  [prompt]                            │
│   Run `ll-issues refine-status` to see   │
│   the current refinement state of all    │
│   active issues. Thresholds: readiness=  │
└──────────────────────────────────────────┘
```

The key principle: **never truncate in `--verbose` mode**. If the box becomes tall, that is acceptable and expected.

### 4. Color transition arrows

Use existing `colorize()` from `cli/output.py` to color edge labels:
- `success` → green (`32`)
- `fail` / `error` → orange/red (`38;5;208` or `31`)
- `partial` → yellow (`33`)
- `next` / `_` → dim (`2`)

Color is suppressed automatically when `_USE_COLOR` is false (non-TTY or `NO_COLOR=1`).

### 5. State overview table

Between the diagram and the verbose state detail section, insert a compact summary table:

```
State       Type    Action Preview                       Transitions
──────────  ──────  ───────────────────────────────────  ──────────────────────────
→ evaluate  shell   ll-issues refine-status --no-key     success→done, fail/error→fix
  fix       prompt  Run `ll-issues refine-status`…       next→evaluate
  done      —       (terminal)                           —
```

This table gives quick orientation before diving into the full state detail.

### 6. Compact metadata header

Consolidate identity and configuration into two tiers on the separator line and following compact row:

```
── issue-refinement ─────────────── fsm · 3 states · 5 transitions ──────
   .loops/issue-refinement.yaml · max: 100 iter · handoff: spawn
```

Reduces visual clutter and front-loads the most important identity facts.

### 7. Improved state section headers

Replace the flat `  [evaluate] [INITIAL] (shell)` style with a lightweight horizontal separator that gives each state visual weight:

```
  ── evaluate ───────────────────────────── INITIAL · shell ──
    action: ll-issues refine-status --no-key
```

## Motivation

`ll-loop show --verbose` is used daily — it is the first thing run before executing or debugging any loop. Each session typically involves 1-3 invocations to verify loop state, transitions, and action content.

`ll-loop show --verbose` is the primary diagnostic command for understanding a loop's behavior before running it. The diagram is the first thing a user sees, yet it conveys almost no information about what each state does — forcing the user to scroll through the verbose state section to reconstruct a mental model. The label collision bug actively produces garbled output. Color and table improvements help experienced users scan quickly; the diagram improvements help new users understand a loop at a glance. The anti-truncation principle applies especially in `--verbose` mode, where completeness is the contract.

## Proposed Solution

All changes are localized to `scripts/little_loops/cli/loop/info.py`:

**Bug fix** (`_render_2d_diagram`): In the vertical connector rows (the section rendering `down_labels` / `up_labels`), detect when the two label strings would overlap given `down_col` and `up_col` proximity. Either: (a) push labels to dedicated rows that don't share a character array with the arrow markers, or (b) use separate rows per label direction. Option (a) is simpler.

**Multi-row boxes** (`_render_2d_diagram` / new helper): Add a `_box_rows(state_name, state)` helper that returns a list of text rows for the box body (type badge + action lines). The diagram layout must then account for variable box heights and align rows accordingly. In non-verbose mode, limit to 2 action lines; in verbose mode, include all lines (pass `verbose` flag down to the renderer).

**Overview table** (`cmd_show`): After printing the diagram block and before the `States:` header, iterate `fsm.states` to build the table. Use `colorize()` for the type column. Truncate action preview to terminal width minus ~50 chars.

**Color** (`cmd_show` / `_render_2d_diagram`): Wrap edge labels in `colorize()` calls before writing them to the row array. Note: ANSI escape sequences add invisible characters that affect string length but not display width — must account for this when calculating padding offsets (use `len(label)` for the raw label before colorizing, apply color after position math).

**Header compaction** (`cmd_show`): Merge paradigm + stats onto the separator line; print source + concise config on a single following line.

**State section headers** (`cmd_show`): Replace `print(f"  [{name}]{initial_marker}{terminal_marker}{type_badge}")` with a separator-line pattern using `─` characters.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — all rendering and display logic lives here

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — routes `show` subcommand to `cmd_show`

### Similar Patterns
- `scripts/little_loops/cli/sprint/show.py` — uses `terminal_width()`, similar ASCII art rendering; check for any patterns to share
- `scripts/little_loops/cli/output.py` — `colorize()`, `terminal_width()` — already used in `info.py`

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file for diagram/display logic; needs updates for multi-row boxes, new table, header format, and bug fix
- `scripts/tests/test_ll_loop_commands.py` — CLI integration tests for `show` command

### Documentation
- N/A — no external docs reference the show output format

### Configuration
- N/A — no config changes

## Implementation Steps

1. Fix the label collision bug in `_render_2d_diagram` vertical connector rows
2. Refactor `_render_2d_diagram` to support multi-row boxes: add `_box_content()` helper, accept `verbose` flag, expand diagram grid to variable row heights
3. Add state overview table rendering to `cmd_show` (after diagram, before state detail)
4. Add color to transition edge labels in both the diagram and the state detail transitions list
5. Compact the metadata header and upgrade state section headers
6. Update `test_ll_loop_display.py` for all changed output; verify no regressions in `test_ll_loop_commands.py`

## API/Interface

N/A — No public API changes. All modifications are internal to `cmd_show` and `_render_2d_diagram` in `scripts/little_loops/cli/loop/info.py`. The CLI command signature (`ll-loop show <name> [--verbose]`) is unchanged. The new `_box_content()` helper is a private function.

## Success Metrics

- `ll-loop show issue-refinement --verbose` diagram shows state type badges and action content for each node
- No label collision — `fail/error` and `next`/`partial` labels render on separate, non-overlapping rows
- Overview table appears between diagram and state detail
- Transition labels are colored on a TTY; plain-text when `NO_COLOR=1` or piped
- In `--verbose` mode, `prompt`-type state actions are shown fully (not cut at 3 lines)
- All existing display tests pass; new tests cover multi-row boxes and the overview table

## Scope Boundaries

- No changes to the loop YAML schema or FSM execution logic
- No changes to `ll-loop list`, `ll-loop history`, or `ll-loop status` output
- No changes to `cmd_show` non-verbose output (the compact preview mode stays compact — truncation policy only changes for `--verbose`)
- Do not introduce new Python dependencies — use only stdlib and existing `colorize()` / `terminal_width()` utilities

## Impact

- **Priority**: P3 — Quality-of-life improvement for a frequently used diagnostic command
- **Effort**: Medium — Diagram multi-row boxes require refactoring the 2D renderer; other changes are straightforward
- **Risk**: Low — All changes are in display/formatting code with no effect on FSM execution; existing tests constrain the surface area
- **Breaking Change**: No — output format changes are purely cosmetic

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM architecture and state model |
| `docs/reference/API.md` | CLI module reference |

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06c58b54-ce27-447a-8683-f1add2d8414b.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

---

**Open** | Created: 2026-03-05 | Priority: P3
