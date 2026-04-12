---
discovered_date: 2026-04-11
discovered_by: capture-issue
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

## Verification

1. `ll-loop run <loop> --dry-run` → `[TERMINAL]` marker uses config `yes` color
2. `ll-loop run <loop>` (loop with evaluate step) → verdict checkmarks/x-marks use config colors
3. `NO_COLOR=1 ll-loop run <loop>` → all output unstyled (existing behavior preserved)
4. `Ctrl-C` during run → shutdown messages appear colorized (orange / yellow)
5. Existing tests: `python -m pytest scripts/tests/ -k loop -v`

## Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — 3 changes (verdict colors, execution plan signature, signal handler messages)
- `scripts/little_loops/cli/loop/run.py` — 1 change (consolidate BRConfig, pass `edge_label_colors` to dry-run)

## Related Issues

- ENH-595 (completed): Added basic `colorize()` to `_helpers.py`
- ENH-815 (completed): Made FSM edge label colors configurable in `ll-config.json`

---

## Status

Open

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1437654-cf08-44ef-b694-93b1f1d22897.jsonl`
