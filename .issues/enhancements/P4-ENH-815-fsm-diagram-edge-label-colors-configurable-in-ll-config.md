---
id: ENH-815
type: ENH
priority: P4
title: "FSM diagram edge label colors configurable in ll-config.json"
status: active
discovered_date: "2026-03-19"
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 82
---

# ENH-815: FSM diagram edge label colors configurable in ll-config.json

## Summary

FSM loop box diagram colors — edge label colors (`yes`, `no`, `error`, `partial`, `next`) and the active-state highlight — should be configurable via `ll-config.json`, reflected in `config-schema.json`, set to defaults by `/ll:init`, and editable via `/ll:configure`.

## Motivation

Currently edge label colors are hardcoded in `_EDGE_LABEL_COLORS` in `scripts/little_loops/cli/loop/layout.py`. The active-state highlight (`fsm_active_state`) is already configurable under `cli.colors` in config-schema.json, but the transition label colors are not. Users who want to adjust colors for their terminal theme or accessibility needs have no way to do so without patching source code.

## Current Behavior

- `_EDGE_LABEL_COLORS` dict in `layout.py:25-32` hardcodes ANSI SGR codes: `yes=32`, `no=38;5;208`, `error=31`, `partial=33`, `next=2`, `_=2`.
- Unknown/custom transition labels render with no color (silent fallback).
- `fsm_active_state` is the only FSM color already in `config-schema.json` under `cli.colors`.

## Expected Behavior

- `cli.colors.fsm_edge_labels` object added to config-schema.json with per-label SGR code overrides.
- Layout code reads these values from config at render time (or at startup via the existing color config loading path).
- `/ll:init` sets sensible defaults (matching current hardcoded values).
- `/ll:configure` exposes the `fsm_edge_labels` sub-keys for interactive editing.

## Implementation Steps

1. **Add `CliColorsEdgeLabelsConfig` dataclass** in `scripts/little_loops/config/cli.py` (before `CliColorsConfig`, following `CliColorsLoggerConfig`/`CliColorsPriorityConfig`/`CliColorsTypeConfig` pattern):
   - Fields: `yes: str = "32"`, `no: str = "38;5;208"`, `error: str = "31"`, `partial: str = "33"`, `next: str = "2"`, `default: str = "2"` (rename `_` → `default` for JSON-friendliness; map back in `to_dict`)
   - `from_dict()` classmethod reads per-key with fallback to field default

2. **Add `fsm_edge_labels` field to `CliColorsConfig`** (`config/cli.py:76–92`):
   - Add `fsm_edge_labels: CliColorsEdgeLabelsConfig = field(default_factory=CliColorsEdgeLabelsConfig)`
   - Update `from_dict()` to call `CliColorsEdgeLabelsConfig.from_dict(data.get("fsm_edge_labels", {}))`

3. **Update `config-schema.json`** — add `fsm_edge_labels` object under `cli.colors.properties` (alongside `fsm_active_state` at line 826), following the `type`/`priority` group pattern with `"additionalProperties": false` and per-label `"type": "string"` + `"default"` + `"description"` entries

4. **Update `_colorize_diagram_labels(diagram, colors)`** in `layout.py:52–65` to accept an optional `colors: dict[str, str] | None = None` parameter; fall back to `_EDGE_LABEL_COLORS` if `None` (preserves existing behavior for callers that don't pass it)

5. **Thread the colors dict through the rendering chain**:
   - `_render_fsm_diagram` (line 1371): add `edge_label_colors: dict[str, str] | None = None` parameter; pass to both `_render_layered_diagram` and `_render_horizontal_simple`; those pass to `_colorize_diagram_labels` at lines 1363 and 1555
   - `run_foreground` in `_helpers.py:278`: add `edge_label_colors: dict[str, str] | None = None` parameter; pass to `_render_fsm_diagram`
   - `cmd_run` in `run.py:151`: read `BRConfig(Path.cwd()).cli.colors.fsm_edge_labels` and convert to `{"yes": ..., "no": ..., ...}` dict; pass to `run_foreground`

6. **`/ll:init` — no changes needed**: init follows the "minimal write rule" and never emits `cli.colors` keys; `CliColorsEdgeLabelsConfig` defaults in `from_dict()` serve as the effective defaults

7. **`/ll:configure` — optional scope**: no `cli` area currently exists in `skills/configure/areas.md`; if in scope, add a `cli` area entry covering `cli.colors.fsm_edge_labels.*`

8. **Add tests**:
   - `test_config.py`: `CliColorsEdgeLabelsConfig` default/override/integration tests (follow pattern at lines 1091–1167)
   - `test_ll_loop_display.py`: pass a custom `edge_label_colors` dict to `_render_fsm_diagram`, assert the overridden ANSI codes appear in the rendered output (follow pattern at lines 1213–1272)

## Integration Map

- `scripts/little_loops/cli/loop/layout.py` — `_EDGE_LABEL_COLORS` (lines 25–32), `_colorize_label` (35–49), `_colorize_diagram_labels` (52–65); both renderers call `_colorize_diagram_labels` as final post-pass at lines 1363 and 1555
- `config-schema.json` — `cli.colors` section (lines 779–836), alongside `fsm_active_state` and nested objects like `type` and `priority`
- `skills/configure/areas.md` — may need `cli.colors.fsm_edge_labels` area entry
- `skills/init/SKILL.md` — defaults generation step

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Config layer (primary addition target):**
- `scripts/little_loops/config/cli.py:76–92` — `CliColorsConfig` dataclass; add `fsm_edge_labels: CliColorsEdgeLabelsConfig = field(default_factory=CliColorsEdgeLabelsConfig)` following the same pattern as `logger`, `priority`, `type` sub-objects; update `from_dict()` at line 84 to call `CliColorsEdgeLabelsConfig.from_dict(data.get("fsm_edge_labels", {}))`
- `scripts/little_loops/config/cli.py:119–124` — `CliConfig.from_dict()` routes `cli.colors` to `CliColorsConfig.from_dict()` automatically; no changes needed here

**Rendering layer (consumer):**
- `scripts/little_loops/cli/loop/layout.py:25–32` — `_EDGE_LABEL_COLORS` module-level dict to replace with values from config
- `scripts/little_loops/cli/loop/layout.py:52–65` — `_colorize_diagram_labels(diagram)` consumes `_EDGE_LABEL_COLORS` directly; must be extended to accept an optional colors dict parameter
- `scripts/little_loops/cli/loop/layout.py:1371–1387` — `_render_fsm_diagram(fsm, verbose, highlight_state, highlight_color)` is the renderer entry point; add `edge_label_colors: dict[str, str] | None = None` parameter, thread through to both internal renderers
- `scripts/little_loops/cli/loop/layout.py:1363, 1555` — call sites for `_colorize_diagram_labels` inside `_render_layered_diagram` and `_render_horizontal_simple`; pass the colors dict

**Note:** `_colorize_label()` (line 35) is NOT used in the rendering path; only `_colorize_diagram_labels()` is called by the renderers. `_colorize_label` may be dead code or used externally — check `info.py` before removing.

**Wiring (runtime config read):**
- `scripts/little_loops/cli/loop/run.py:151–154` — reads `BRConfig(Path.cwd()).cli.colors.fsm_active_state` and passes it to `run_foreground()`; add analogous read of `BRConfig(Path.cwd()).cli.colors.fsm_edge_labels` as a dict and pass to `run_foreground()`
- `scripts/little_loops/cli/loop/_helpers.py:278–323` — `run_foreground()` receives `highlight_color` and passes it to `_render_fsm_diagram`; add `edge_label_colors: dict[str, str] | None = None` parameter alongside `highlight_color`

**Callers/dependents:**
- `scripts/little_loops/cli/loop/info.py` — imports from `layout`; check if it calls `_colorize_label` or `_colorize_diagram_labels` directly

**Tests:**
- `scripts/tests/test_ll_loop_display.py:1213–1272` — existing tests for `highlight_color` in `_render_fsm_diagram`; model new edge-label color tests after these (patch `_USE_COLOR`, call renderer with custom colors dict, assert ANSI codes appear in output)
- `scripts/tests/test_config.py:1091–1167` — existing tests for `CliColorsConfig.fsm_active_state` default/override/integration; add parallel tests for `CliColorsEdgeLabelsConfig`

**configure skill (no `cli` area today):**
- `skills/configure/areas.md` — no `cli` or `colors` area currently exists; `fsm_active_state` has no interactive wizard; adding one is optional scope

**Schema:**
- `config-schema.json:826–830` — `fsm_active_state` is a scalar `string` entry; `fsm_edge_labels` should be an `object` with per-label properties following the `type`/`priority` group pattern (lines 800–825) with `"additionalProperties": false`

## Related Issues

- ENH-813: color-code transition lines in FSM loop diagrams (adds colors; this makes them configurable)
- ENH-654: FSM diagram active-state background fill highlight

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05c0fd42-591b-4a8e-b3b7-08165c6c2477.jsonl`
- `/ll:refine-issue` - 2026-03-19T16:54:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c179030-87aa-47bd-98f0-dbd231f6dfc2.jsonl`
- `/ll:capture-issue` - 2026-03-19T16:50:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
