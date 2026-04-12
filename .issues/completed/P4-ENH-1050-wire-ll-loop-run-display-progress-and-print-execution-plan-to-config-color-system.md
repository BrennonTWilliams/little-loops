---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-1050: Wire ll-loop run display_progress and print_execution_plan to config-driven color system

## Summary

Two output paths in `scripts/little_loops/cli/loop/_helpers.py` bypass the config-driven color system and hardcode ANSI SGR codes directly. `display_progress()` (evaluate event) hardcodes verdict symbol colors, and `print_execution_plan()` hardcodes the `[TERMINAL]` marker color. Both should read from the `edge_label_colors` dict already built from `BRConfig.cli.colors.fsm_edge_labels` — the infrastructure is in place, the wiring is missing.

## Motivation

ENH-595 added `colorize()` to `_helpers.py` and ENH-815 made FSM edge label colors configurable in `ll-config.json`. The pipeline is almost complete — `run.py` loads `BRConfig`, extracts `edge_label_colors`, and passes it to `run_foreground()` → `_render_fsm_diagram()`. But `display_progress()` and `print_execution_plan()` never receive or use those colors. Users who configure custom colors in `ll-config.json` see no effect on verdict checkmarks, x-marks, or the `[TERMINAL]` execution-plan marker.

## Current Behavior

- `display_progress()` evaluate event (`_helpers.py:459–468`): hardcodes `"32"` (green) for yes/target/progress verdicts and `"38;5;208"` (orange) for no/error verdicts.
- `print_execution_plan()` (`_helpers.py:155`): hardcodes `"32"` for the `[TERMINAL]` marker; no `edge_label_colors` parameter exists.
- Signal handler messages (`_helpers.py:49, 52`): plain strings, no `colorize()` applied.
- `run.py` loads `BRConfig` a second time in the foreground `try` block; the dry-run path never passes `edge_label_colors` to `print_execution_plan()`.

## Expected Behavior

- `display_progress()` reads verdict colors from the `edge_label_colors` closure variable (already in scope), with hardcoded SGR codes as fallbacks.
- `print_execution_plan()` accepts `edge_label_colors: dict[str, str] | None = None` and uses `_elc.get("yes", "32")` for `[TERMINAL]`.
- Signal handler shutdown messages use `colorize()` so they respect `_USE_COLOR` (set by `configure_output()`).
- `run.py` loads `BRConfig` once at the top of `cmd_run()` and passes `edge_label_colors` to both the dry-run and foreground paths.

## Implementation Steps

### 1. `scripts/little_loops/cli/loop/_helpers.py`

**A. `display_progress()` evaluate block (lines 459–468)**

```python
# After:
_elc = edge_label_colors or {}
if verdict in ("yes", "target", "progress"):
    _vc = _elc.get("yes", "32")
    symbol = colorize("\u2713", _vc)
    verdict_colored = colorize(verdict, _vc)
elif verdict == "no":
    _vc = _elc.get("no", "38;5;208")
    symbol = colorize("\u2717", _vc)
    verdict_colored = colorize(verdict, _vc)
elif verdict == "error":
    _vc = _elc.get("error", "38;5;208")
    symbol = colorize("\u2717", _vc)
    verdict_colored = colorize(verdict, _vc)
else:
    symbol = colorize("\u2717", "38;5;208")
    verdict_colored = colorize(verdict, "2")
```

> Fallback for `error` stays `"38;5;208"` (orange) not `"31"` (red) — matches existing visual; the config default `"31"` only applies if explicitly set.

**B. `print_execution_plan()` signature (line 155)**

```python
def print_execution_plan(fsm: FSMLoop, edge_label_colors: dict[str, str] | None = None) -> None:
    _elc = edge_label_colors or {}
    _yes_color = _elc.get("yes", "32")
    # ...
    terminal_marker = colorize(" [TERMINAL]", _yes_color) if state.terminal else ""
```

**C. Signal handler messages (lines 49, 52)**

```python
# line 49:
print(colorize("\nForce shutdown requested", "38;5;208"), file=sys.stderr)
# line 52:
print(colorize("\nShutdown requested, will exit after current state...", "33"), file=sys.stderr)
```

### 2. `scripts/little_loops/cli/loop/run.py`

**Consolidate BRConfig loading** — move to top of `cmd_run()`, remove the second load inside the foreground `try` block, and pass `edge_label_colors` to the dry-run call:

```python
_config = BRConfig(Path.cwd())
_edge_label_colors = _config.cli.colors.fsm_edge_labels.to_dict()
_highlight_color = _config.cli.colors.fsm_active_state
_badges = _config.loops.glyphs.to_dict()

if args.dry_run:
    print_execution_plan(fsm, edge_label_colors=_edge_label_colors)
    return 0
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `docs/reference/OUTPUT_STYLING.md` — in the `fsm_edge_labels` section (around line 205), add a note that this config key now also controls verdict symbol colors in `display_progress()` and the `[TERMINAL]` marker color in `print_execution_plan()`; not just the FSM diagram renderer arrows

## Scope Boundaries

- Arrow/transition colors in `print_execution_plan()` (`_helpers.py:182–194`): `colorize('->', '2')` and transition targets remain hardcoded dim (`"2"`); only the `[TERMINAL]` marker is targeted by this issue
- `display_progress()` state-change and action events are out of scope; only the evaluate event verdict symbols (`yes`/`target`/`progress` checkmarks, `no`/`error` x-marks) are addressed
- Color behavior under `NO_COLOR=1` or non-TTY output is not changed — governed by `_USE_COLOR` (set via `configure_output()`), which is already respected by `colorize()`

## Verification

1. `ll-loop run <loop> --dry-run` → `[TERMINAL]` marker uses config `yes` color
2. `ll-loop run <loop>` (loop with evaluate step) → verdict checkmarks/x-marks use config colors
3. `NO_COLOR=1 ll-loop run <loop>` → all output unstyled (existing behavior preserved)
4. `Ctrl-C` during run → shutdown messages appear colorized (orange / yellow)
5. Existing tests: `python -m pytest scripts/tests/ -k loop -v`

### Codebase Research Findings

_Added by `/ll:refine-issue` — test file and patterns to follow:_

- **Primary test file**: `scripts/tests/test_ll_loop_display.py`
  - Run with: `python -m pytest scripts/tests/test_ll_loop_display.py -v`
  - `TestDisplayProgressEvents` class (around line 1534): inject `{"event": "evaluate", "verdict": "yes", ...}` via `MockExecutor`, assert colored output with `capsys.readouterr().out`
  - `TestPrintExecutionPlan` class (around line 329): tested via `--dry-run` CLI entry; add a case passing custom `edge_label_colors` and assert `[TERMINAL]` SGR code changes
  - Override `_USE_COLOR` for color assertions: `with patch.object(output_mod, "_USE_COLOR", True):`
- **Config test file**: `scripts/tests/test_config.py:1289–1309` — pattern for testing `fsm_active_state` override; follow same structure for `fsm_edge_labels` in new tests if needed

## Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — 3 changes (verdict colors, execution plan signature, signal handler messages)
- `scripts/little_loops/cli/loop/run.py` — 1 change (consolidate BRConfig, pass `edge_label_colors` to dry-run)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — 4 targeted edits:
  1. `print_execution_plan()` signature at `line 155`: add `edge_label_colors: dict[str, str] | None = None` parameter; replace hardcoded `"32"` at `line 162` with `(edge_label_colors or {}).get("yes", "32")`
  2. `display_progress()` evaluate block at `lines 453–468`: add `_elc = edge_label_colors or {}` at top of block; replace `"32"` and `"38;5;208"` literals with `_elc.get("yes", "32")`, `_elc.get("no", "38;5;208")`, `_elc.get("error", "38;5;208")`
  3. Signal handler `line 49`: wrap `"\nForce shutdown requested"` with `colorize(..., "38;5;208")`
  4. Signal handler `line 52`: wrap `"\nShutdown requested, will exit after current state..."` with `colorize(..., "33")`
- `scripts/little_loops/cli/loop/run.py` — move `BRConfig` load and color extraction before the `args.dry_run` check at `line 93`; update `print_execution_plan(fsm)` call at `line 94` to `print_execution_plan(fsm, edge_label_colors=_edge_label_colors)`

### Caller of `print_execution_plan()`
- `scripts/little_loops/cli/loop/run.py:94` — the **only** caller; dry-run path in `cmd_run()`; must pass `edge_label_colors=_edge_label_colors` after the signature change

### `display_progress()` Scope
- Defined as a nested function inside `run_foreground()` at `_helpers.py:317`; `edge_label_colors` is already in closure scope from `run_foreground()`'s parameter at `_helpers.py:290` — no new parameter needed on `display_progress()` itself

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file for both functions:
  - Evaluate event tests at `lines 1534–1563`: use `MockExecutor` + event dict with `"event": "evaluate"` + `capsys.readouterr().out` assertions; extend these with `edge_label_colors` kwarg and assert custom SGR codes appear
  - `print_execution_plan` tested via `--dry-run` CLI path at `lines 329–446`; extend to pass custom `edge_label_colors` and assert `[TERMINAL]` uses that color
  - Existing `edge_label_colors` test pattern at `lines 1277–1331`: `patch.object(output_mod, "_USE_COLOR", True)` + custom colors dict → assert `"\033[99m"` in output
  - `_render_fsm_diagram` call-arg verification at `lines 1604–1626`: `patch.object(layout_mod, "_render_fsm_diagram", wraps=...)` + `mock_render.assert_called_once_with(...)` — follow this pattern to verify `edge_label_colors` is threaded through

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_background.py` — `TestLoopSignalHandler` directly tests `_loop_signal_handler`; signal handler messages at `_helpers.py:49,52` are being wrapped with `colorize()`. Existing tests assert only on flag state and `SystemExit` (no SGR assertions), so no updates needed — but verify after implementation
- `scripts/tests/test_cli_loop_lifecycle.py` — imports both `cmd_run` from `run.py` and `_loop_signal_handler` from `_helpers.py`; `TestCmdRunYAMLConfigOverrides` (line 767) tests the `BRConfig` YAML config path, which is affected by the `BRConfig` consolidation in `cmd_run()`; safe as-is (no SGR assertions), but run to confirm after the `BRConfig` load move
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdRunContextInjection` (line 2068) calls `cmd_run` directly with `dry_run=True` (line 2127); exercises `print_execution_plan` code path; no color assertions, safe
- **May break** — `scripts/tests/test_ll_loop_display.py:1620–1625, 1680–1685, 1917–1936` — these mock `_render_fsm_diagram` and assert `edge_label_colors=None` in the call args. They call `run_foreground()` directly (not via `cmd_run`), so they will receive `edge_label_colors=None` (the default). They are safe as long as `run_foreground`'s default param stays `None` — which it does per the implementation plan. Verify these still pass after implementation.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md:205` — currently states "Edge label colors are user-configurable via `cli.colors.fsm_edge_labels`" but only in the context of the FSM diagram renderer (`layout.py`). After ENH-1050, the same config key also governs `display_progress()` verdict symbols (`✓`/`✗`) and the `print_execution_plan()` `[TERMINAL]` marker. Add a note to the relevant section documenting the expanded scope.

### Supporting Files (Read-Only)
- `scripts/little_loops/config/cli.py:102–116` — `CliColorsEdgeLabelsConfig.to_dict()` maps config fields to the `dict[str, str]` passed as `edge_label_colors`; keys include `"yes"`, `"no"`, `"error"`, `"partial"`, `"next"`, `"default"` (→ `"_"`)
- `scripts/little_loops/cli/output.py:90` — `colorize` is defined here; `_helpers.py` imports it at `_helpers.py:14` via `from little_loops.cli.output import colorize, terminal_width`
- `scripts/little_loops/cli/loop/layout.py:27–36` — `_EDGE_LABEL_COLORS` fallback dict; keys `"yes"`, `"no"`, `"error"` are the same keys used by the `edge_label_colors` dict

### Out of Scope (Known Hardcoded Colors Left Unchanged)
- `print_execution_plan()` arrow/transition colors at `_helpers.py:182–194`: `colorize('->', '2')` and transition targets use hardcoded `"2"` (dim). Issue only targets the `[TERMINAL]` marker.

## Impact

- **Priority**: P4 - Minor cosmetic fix; users with custom `ll-config.json` colors see no effect on verdict symbols or `[TERMINAL]` marker until this is wired
- **Effort**: Small - 3 targeted edits in `_helpers.py` and 1 consolidation in `run.py`; all infrastructure already in place
- **Risk**: Low - Additive change; all SGR codes have hardcoded fallbacks so behavior is unchanged when no config is set
- **Breaking Change**: No - `print_execution_plan()` gains an optional `edge_label_colors` parameter defaulting to `None`; all existing callers are unaffected

## Labels

`enhancement`, `colorization`, `cli`, `config-integration`

## Related Issues

- ENH-595 (completed): Added basic `colorize()` to `_helpers.py`
- ENH-815 (completed): Made FSM edge label colors configurable in `ll-config.json`

---

## Resolution

Implemented in `_helpers.py` and `run.py`:

1. **Signal handler messages**: Wrapped `"\nForce shutdown requested"` with `colorize(..., "38;5;208")` and `"\nShutdown requested..."` with `colorize(..., "33")` so they respect `_USE_COLOR`.
2. **`print_execution_plan()`**: Added `edge_label_colors: dict[str, str] | None = None` parameter; `[TERMINAL]` marker now uses `_elc.get("yes", "32")` instead of hardcoded `"32"`.
3. **`display_progress()` evaluate block**: Replaced hardcoded `"32"` and `"38;5;208"` with `_elc.get("yes", "32")`, `_elc.get("no", "38;5;208")`, `_elc.get("error", "38;5;208")` drawn from the `edge_label_colors` closure variable.
4. **`run.py` BRConfig consolidation**: Moved `BRConfig` load before the dry-run check; passed `edge_label_colors=_edge_label_colors` to both dry-run `print_execution_plan()` and `run_foreground()`; removed the second `BRConfig` load in the foreground path.
5. **`docs/reference/OUTPUT_STYLING.md`**: Added a note clarifying that `cli.colors.fsm_edge_labels` now also controls verdict symbol colors and the `[TERMINAL]` marker.

All 176 related tests pass.

## Status

Completed

## Session Log
- `/ll:ready-issue` - 2026-04-12T05:17:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab5e84d9-0a67-4165-9bed-c48fd6c94f98.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f54f3a-dbcf-4014-96af-26801a901446.jsonl`
- `/ll:wire-issue` - 2026-04-12T05:08:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4df6d63-0f49-4dd7-9784-803b617b2e26.jsonl`
- `/ll:refine-issue` - 2026-04-12T04:58:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a85d1e55-862d-4918-9fa4-361cea909a58.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1437654-cf08-44ef-b694-93b1f1d22897.jsonl`
- `/ll:manage-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
