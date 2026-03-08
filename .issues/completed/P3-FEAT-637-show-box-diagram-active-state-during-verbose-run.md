---
discovered_date: 2026-03-07T00:00:00Z
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 79
---

# FEAT-637: Show FSM Box Diagram with Active State Highlighted During `ll-loop run --verbose`

## Summary

When `ll-loop run ... --verbose` executes, at each FSM step the terminal output should include the Box Diagram (as produced by `ll-loop show ...`) with the current state rendered using a green fill color, giving the user a live visual of where the loop is in its state machine.

## Current Behavior

`ll-loop run --verbose` prints step-level output (state name, action taken, evaluator result) as plain text. The Box Diagram is only available via `ll-loop show` as a separate command; it is never displayed inline during execution.

## Expected Behavior

At each FSM step during `ll-loop run --verbose`, the terminal prints the Box Diagram for the loop with the current state's box filled in green (e.g., using ANSI background/foreground color codes or Rich panel styling). All other states render with their normal appearance. The diagram is printed before or after the step's action output.

## Motivation

Verbose mode is the primary observability interface for running loops. Text-only step output requires the user to mentally map state names to the FSM diagram. Embedding the diagram with the active state highlighted provides immediate spatial context — users can see not just *what* state they are in but *where* it sits in the overall flow and which transitions come next. This is especially valuable for complex loops with many states.

## Use Case

A developer is debugging a loop that seems to be cycling unexpectedly. They run `ll-loop run myloop --verbose` and watch the terminal. Instead of seeing a stream of state names, they see the full FSM box diagram reprinted at each step with the active state highlighted green. They immediately spot that the loop is re-entering an earlier state on every iteration instead of progressing toward the terminal state.

## Acceptance Criteria

- [ ] `ll-loop run --verbose` prints the Box Diagram at each FSM step transition
- [ ] The current state's box renders using the color from `ll-config.json` at `cli.colors.fsm_active_state` (default: `"32"`, green)
- [ ] Bold variant (`"{color};1"`) is applied to the state name text inside the highlighted box
- [ ] All other state boxes render normally (no color change)
- [ ] Diagram output is identical to `ll-loop show` output except for the active-state color
- [ ] `ll-loop run` without `--verbose` is unaffected (no diagram output)
- [ ] Works for all paradigm types that support `ll-loop show`
- [ ] `CliColorsConfig` exposes `fsm_active_state` with default `"32"` and schema entry in `config-schema.json`

## Proposed Solution

The `ll-loop show` path goes through `cmd_show()` → `_render_fsm_diagram()` in `scripts/little_loops/cli/loop/info.py`. The run executor lives in `scripts/little_loops/cli/loop/run.py` → `run_foreground()` in `_helpers.py`. At each state transition in verbose mode, call a variant of `_render_fsm_diagram()` that accepts a `highlight_state: str | None = None` and `highlight_color: str = "32"` parameter and applies the configured ANSI color to that state's box characters. The highlight color is read from `ll-config.json` at `cli.colors.fsm_active_state` (default `"32"`, green), using the existing `CliColorsConfig` extension pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Color rendering**: The codebase uses `colorize(text, code)` from `scripts/little_loops/cli/output.py:89` as the single ANSI primitive (`"32"` = green, `"32;1"` = bold green). This function is TTY-aware and honors `NO_COLOR`. The diagram already uses this in `_colorize_diagram_labels()` at `info.py:271`.

**Config color system**: `ll-config.json` supports `cli.colors` overrides via `CliColorsConfig` (dataclass at `config.py:557`), which already has sub-configs for logger levels, priority labels, and type labels. The active-state highlight color should be added as `cli.colors.fsm_active_state: str = "32"` (default green) so users can customize it (e.g., `"36"` for cyan, `"38;5;208"` for orange) without modifying code. Bold is derived as `f"{color};1"` for the state name text. The config schema at `config-schema.json:760` defines the `cli.colors` object and must be extended with the new key.

**Box construction approach**: `_render_fsm_diagram()` delegates to `_render_2d_diagram()` at `info.py:450`, which builds a `rows: list[list[str]]` 2D character grid. Box-drawing characters (`┌─┐│└┘`) are placed into grid cells individually. The grid is joined with `"".join(row)` — so inserting ANSI-wrapped cell strings (`colorize("┌", "32")`) preserves correct column indexing while adding visual color. `_colorize_diagram_labels()` runs as a post-processing pass on the assembled string.

**Recommended approach**: Pass `highlight_state` and `highlight_color` (an SGR string, defaulting to `"32"`) into `_render_2d_diagram()` and wrap box-drawing characters with `colorize(char, highlight_color)` when building the highlighted state's box. The state name text uses `colorize(name, f"{highlight_color};1")` (bold variant). The color value comes from `CliColorsConfig.fsm_active_state`, read from `ll-config.json` at call time in `_helpers.py`.

**Injection point in verbose run path**: The `display_progress()` closure at `_helpers.py:296` handles `state_enter` events at lines 302–314. At that point, `event["state"]` (current state name) and `fsm` (full `FSMLoop` with `.states` topology) are both in scope. The diagram call goes **after** the state header print (line 314). Note: the header currently prints with `end=""` — add a newline before printing the diagram or adjust the end character.

**Import needed**: `_render_fsm_diagram` is not currently imported in `_helpers.py`; add `from little_loops.cli.loop.info import _render_fsm_diagram`.

## Integration Map

### Files to Modify
- `scripts/little_loops/config.py` — add `fsm_active_state: str = "32"` field to `CliColorsConfig` (at `config.py:557`); update `CliColorsConfig.from_dict()` to read `data.get("fsm_active_state", "32")`
- `config-schema.json` — add `"fsm_active_state"` string property to `cli.colors` object (at `config-schema.json:760`), with default `"32"` and description `"ANSI SGR code for the active FSM state highlight during verbose run (default: green)"`
- `scripts/little_loops/cli/loop/info.py` — add `highlight_state: str | None = None` and `highlight_color: str = "32"` to `_render_fsm_diagram()` (line 356) and `_render_2d_diagram()` (line 450); apply `colorize(char, highlight_color)` and `colorize(name, f"{highlight_color};1")` to the highlighted state during grid construction
- `scripts/little_loops/cli/loop/_helpers.py` — add `highlight_color: str = "32"` parameter to `run_foreground()`; in `display_progress()` `state_enter` handler (lines 302–314), call `_render_fsm_diagram(fsm, highlight_state=event["state"], highlight_color=highlight_color)`; add import of `_render_fsm_diagram`. Note: `ProjectConfig` is NOT currently in scope here — the caller (`cmd_run` in `run.py`) must pass the color value read from `BRConfig(Path.cwd()).cli.colors.fsm_active_state` as the new `highlight_color` argument.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:1102` — only production caller of `_render_fsm_diagram()`; no changes needed (calls without `highlight_state`, defaults to `None`, default color `"32"` applies)
- `scripts/little_loops/cli/loop/__init__.py:20` — imports `cmd_show` from `info.py`; no changes needed
- `scripts/tests/test_config.py` — imports `CliColorsConfig`; extend `TestCliColorsConfig` with `fsm_active_state` default and override tests

### Similar Patterns
- `_colorize_diagram_labels()` at `info.py:271` — post-processing regex color pass; same `colorize()` primitive
- `colorize(" [TERMINAL]", "32")` at `_helpers.py:172` — green color already used in plan display for terminal state marker
- `colorize(verdict, "32")` at `_helpers.py:377–378` — green checkmark/verdict for success events in same `display_progress` closure
- `colorize(result.final_state, "32")` at `_helpers.py:423` — green final state name on loop completion

### Tests
- `scripts/tests/test_ll_loop_display.py:634` — `TestRenderFsmDiagram` class; add test `test_highlighted_state_uses_green_color()` using `patch.object(output_mod, "_USE_COLOR", True)` pattern from `test_cli_output.py:53`
- `scripts/tests/test_ll_loop_execution.py` — add test asserting diagram appears in verbose run output at each `state_enter` event (mock `_render_fsm_diagram` and assert it is called with correct `highlight_state`)

### Documentation
- N/A — no user-facing docs describe verbose output format

### Configuration
- N/A

## Implementation Steps

1. **`config.py` — extend `CliColorsConfig`**: Add `fsm_active_state: str = "32"` field; update `from_dict()` to read `data.get("fsm_active_state", "32")`
2. **`config-schema.json` — add schema entry**: Inside `cli.colors.properties`, add `"fsm_active_state": { "type": "string", "default": "32", "description": "ANSI SGR code for the active FSM state highlight during verbose run (default: green)" }`
3. **`info.py` — extend `_render_fsm_diagram()`**: Add `highlight_state: str | None = None` and `highlight_color: str = "32"` parameters at `info.py:356`; pass both through to `_render_2d_diagram()` at `info.py:450`
4. **`info.py` — extend `_render_2d_diagram()`**: Add `highlight_state: str | None = None` and `highlight_color: str = "32"` parameters; when placing box-drawing characters (`┌─┐│└┘`) for a state equal to `highlight_state`, wrap each with `colorize(char, highlight_color)`; wrap the state name text with `colorize(name, f"{highlight_color};1")` (bold variant)
5. **`_helpers.py` — import**: Add `from little_loops.cli.loop.info import _render_fsm_diagram` at the top of `_helpers.py`
6. **`_helpers.py` — extend `run_foreground()` signature and inject in `display_progress()`**: Add `highlight_color: str = "32"` parameter to `run_foreground()`. In the `state_enter` handler (lines 302–314), after the header print, add `if verbose: print(_render_fsm_diagram(fsm, highlight_state=event["state"], highlight_color=highlight_color))`. Adjust the header `end=""` to `end="\n"` or prefix the diagram print with a newline. Note: `ProjectConfig` is NOT in scope here — the color must be threaded in from the caller: in `run.py`'s `cmd_run()`, load `highlight_color = BRConfig(Path.cwd()).cli.colors.fsm_active_state` and pass it to `run_foreground(executor, fsm, args, highlight_color=highlight_color)`.
7. **`test_ll_loop_display.py` — new unit test**: Add `test_highlighted_state_uses_configured_color()` in `TestRenderFsmDiagram`; patch `_USE_COLOR=True`, assert ANSI codes for the custom color appear in rendered output for the highlighted state and do not appear for other states; also test default fallback (`highlight_color="32"`)
8. **`test_ll_loop_execution.py` — new integration test**: Assert `_render_fsm_diagram` is called once per `state_enter` in verbose mode with the correct state name and the color from config; assert it is never called when `verbose=False`
9. **`test_config.py` — extend `TestCliColorsConfig`**: Add test asserting `CliColorsConfig()` defaults `fsm_active_state` to `"32"`, and `CliColorsConfig.from_dict({"fsm_active_state": "36"})` yields `"36"`

## Impact

- **Priority**: P3 - Meaningful UX improvement for loop debugging; verbose mode is the primary observability tool
- **Effort**: Medium - Requires extending `_render_fsm_diagram()` with ANSI color support and wiring it into the run executor verbose path
- **Risk**: Low - Additive change; existing diagram output and non-verbose run paths are unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-loop`, `ux`, `verbose`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b751542-8f4b-4928-b4a0-a5d7f5882090.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37fedab8-d671-4d7f-8d39-7b40b4ba403b.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

## Verification Notes
- **Verdict**: VALID
- `_render_fsm_diagram()` confirmed at `scripts/little_loops/cli/loop/info.py:356` with signature `(fsm: FSMLoop, verbose: bool = False)` — no `highlight_state` parameter exists yet
- `cmd_show()` confirmed at `info.py:1019`, calls `_render_fsm_diagram()` at line 1102
- `ll-loop run --verbose` flag confirmed at `scripts/little_loops/cli/loop/__init__.py:113`
- `run_foreground()` in `scripts/little_loops/cli/loop/_helpers.py:276` uses `verbose` flag but does not call `_render_fsm_diagram()` — feature gap is real
- Run executor is `scripts/little_loops/cli/loop/run.py` → `run_foreground()` in `_helpers.py` — file path in issue is accurate

---

## Resolution

**Completed** | 2026-03-07

- Added `highlight_state: str | None` and `highlight_color: str = "32"` params to `_render_fsm_diagram()` and `_render_2d_diagram()` in `info.py`
- Box-drawing characters for the highlighted state are wrapped with `colorize(ch, highlight_color)`; the state name line uses bold variant `f"{highlight_color};1"`
- Added lazy import of `_render_fsm_diagram` in `_helpers.py` `state_enter` handler (avoids circular import); diagram printed before the step header when `verbose=True`
- Extended `run_foreground()` with `highlight_color: str = "32"` param; `cmd_run()` reads color from `BRConfig.cli.colors.fsm_active_state`
- Added `fsm_active_state: str = "32"` to `CliColorsConfig` dataclass and `from_dict()`
- Added `"fsm_active_state"` property to `config-schema.json` `cli.colors.properties`
- Added 9 new tests covering highlight rendering, color default/override, non-verbose no-diagram, and verbose diagram call assertions

## Status

**Completed** | Created: 2026-03-07 | Priority: P3
