---
id: ENH-1698
status: done
priority: P3
type: ENH
discovered_date: 2026-05-25
captured_at: '2026-05-25T21:37:44Z'
completed_at: '2026-05-25T22:13:46Z'
discovered_by: capture-issue
labels:
- cli
- loop
- ux
- diagram
confidence_score: 98
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1698: Wire `--show-diagrams` Options into `ll-loop show` Output

## Summary

`ll-loop show` renders the FSM diagram but exposes no mode options — users cannot customize topology, edge labels, state detail, or scope when previewing a loop. Wire the existing `--show-diagrams` flag (with all its facets) into the `show` subcommand so users get the same diagram customization available during `ll-loop run`.

## Current Behavior

`ll-loop show <loop>` renders the FSM diagram using a fixed rendering path (verbose + badges mode). It accepts no diagram customization flags — users cannot control topology, edge labels, state detail, or diagram scope when previewing a loop without executing it.

## Expected Behavior

`ll-loop show <loop>` accepts the full `--show-diagrams[=MODE]` flag family (identical to `ll-loop run`/`ll-loop resume`), enabling diagram customization without executing the loop. Bare `--show-diagrams` defaults to the `summary` preset. When `--show-diagrams` is absent, existing behavior is unchanged.

## Motivation

`ll-loop run` and `ll-loop resume` both accept `--show-diagrams[=MODE]` plus the modifier flags `--diagram-edge-labels`, `--diagram-state-detail`, and `--diagram-scope`. The static `ll-loop show` command is the primary way users preview FSM diagrams before running a loop, yet it has no equivalent controls. Users who want a compact view, a neighborhood layout, or edge-label-free output must rely on the run-time flags — making it impossible to inspect diagram rendering without actually executing the loop.

## Use Case

A user previews a complex loop before running it:

```bash
# Compact overview — title-only states, no edge labels, main-path scope
ll-loop show my-loop --show-diagrams=clean

# Full detail with all edges
ll-loop show my-loop --show-diagrams=detailed

# Neighborhood layout centered on a state of interest
ll-loop show my-loop --show-diagrams=neighborhood

# Bare flag uses the default "summary" preset (layered, main-path scope)
ll-loop show my-loop --show-diagrams
```

## Acceptance Criteria

- [ ] `ll-loop show` accepts `--show-diagrams[=MODE]` where MODE is any topology or preset value recognized by `_parse_show_diagrams`
- [ ] Bare `--show-diagrams` defaults to the `summary` preset (matching `run`/`resume` behavior)
- [ ] Modifier flags `--diagram-edge-labels`, `--diagram-state-detail`, `--diagram-scope` are accepted on `show` and override the preset
- [ ] When `--show-diagrams` is absent, `ll-loop show` diagram rendering is unchanged (existing `verbose` + `badges` path)
- [ ] `--show-diagrams` and `--json` are mutually exclusive (JSON mode emits config, not a diagram)
- [ ] Help text on `show_parser` matches the description used on `run_parser`

## Scope Boundaries

- Out of scope: Changes to `ll-loop run` or `ll-loop resume` diagram rendering behavior
- Out of scope: New diagram modes, topologies, or presets (this wires existing capabilities only)
- Out of scope: Interactive or live diagram controls
- Out of scope: Changes to `--json` output format

## API/Interface

```
ll-loop show <loop> [--verbose] [--json] [--resolved]
                    [--show-diagrams[=MODE]]
                    [--diagram-edge-labels on|off]
                    [--diagram-state-detail title|full]
                    [--diagram-scope main|full]
```

New flags mirror `run`/`resume` exactly. `resolve_facets(args)` from `diagram_modes.py` is reused without modification.

## Implementation Steps

1. **`scripts/little_loops/cli/loop/__init__.py` — extend `show_parser`**  
   After `show_parser.add_argument("--resolved", ...)`, add the same `--show-diagrams`, `--diagram-edge-labels`, `--diagram-state-detail`, and `--diagram-scope` argument blocks that appear on `run_parser`. Copy the help text verbatim so behavior is consistent.

2. **`scripts/little_loops/cli/loop/info.py` — update `cmd_show()`**  
   In `cmd_show()`, after loading the FSM, call `resolve_facets(args)` from `diagram_modes.py`. If facets are non-None, pass them through to `_render_fsm_diagram()` via the existing `facets` parameter (or add it if absent). If facets are None, fall back to the current `verbose`+`badges` path unchanged.

3. **Check `_render_fsm_diagram()` signature** — confirm it already accepts a `facets: DiagramFacets | None` parameter (added as part of ENH-1693 or similar). If not, add it with `None` default and wire into `_render_2d_diagram()`.

4. **`--json` mutual exclusion** — add `show_parser.add_mutually_exclusive_group()` or a runtime guard in `cmd_show()` that exits with an error if both `--json` and `--show-diagrams` are set.

5. **Tests** — add cases in `scripts/tests/test_ll_loop_display.py` or a new `test_ll_loop_show_diagram_options.py`:
   - `--show-diagrams=clean` produces output without edge labels
   - `--show-diagrams=detailed` produces full output
   - bare `--show-diagrams` uses the `summary` preset
   - `--show-diagrams` + `--json` raises an error

### Codebase Research Corrections

_Added by `/ll:refine-issue` — Step 3 above is incorrect in two ways:_

1. **`_render_fsm_diagram()` has NO `facets` parameter** (`layout.py:1583`). Its signature is:
   ```python
   def _render_fsm_diagram(
       fsm, verbose=False, highlight_state=None, highlight_color="32",
       edge_label_colors=None, badges=None, mode="full", *,
       suppress_labels=False, title_only=False,
   ) -> str:
   ```
   Do NOT add a `facets` parameter — unpack at the call site instead.

2. **`_render_2d_diagram()` does not exist.** The function to call is `_render_fsm_diagram()`.

**Correct Step 3** — in `cmd_show()` after calling `resolve_facets(args)`, branch on whether facets is None:
```python
facets = resolve_facets(args)
if facets is None:
    # Existing unchanged path
    diagram = _render_fsm_diagram(fsm, verbose=verbose, badges=badges)
else:
    # Facets-driven path — unpack following _helpers.py:792-801 pattern
    diagram = _render_fsm_diagram(
        fsm,
        badges=badges,
        mode=facets.scope,
        suppress_labels=not facets.edge_labels,
        title_only=facets.state_detail == "title",
    )
```

**For Step 4 (`--json` mutual exclusion):** the existing early-return at `info.py:725` already silently skips `--show-diagrams` when `--json` is set. To emit an explicit error instead, add a runtime guard before the early-return:
```python
if getattr(args, "json", False) and getattr(args, "show_diagrams", None) is not None:
    logger.error("--json and --show-diagrams are mutually exclusive")
    return 1
```
Alternatively use `add_mutually_exclusive_group()` on `show_parser` — see `cli/history.py:99` for the pattern.

**Test fixture pattern** — reuse the `_make_args` helper at `test_ll_loop_display.py:1648` style:
```python
args = argparse.Namespace(
    verbose=False, json=False, resolved=False,
    show_diagrams=True,           # bare --show-diagrams (summary preset)
    diagram_edge_labels=None,
    diagram_state_detail=None,
    diagram_scope=None,
)
```
Assert via `patch.object(layout_mod, "_render_fsm_diagram", ...)` following lines 1953–2011 of the same file.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--show-diagrams` flag group to `show_parser`
- `scripts/little_loops/cli/loop/info.py` — update `cmd_show()` to call `resolve_facets()` and forward to `_render_fsm_diagram()`; confirm/add `facets` parameter on `_render_fsm_diagram()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/diagram_modes.py` — `resolve_facets()`, `DiagramFacets` (reused without modification)

### Similar Patterns
- `run_parser` / `cmd_run()` and `resume_parser` / `cmd_resume()` in `__init__.py` and `run.py` — copy flag group verbatim for consistency

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing display tests; add `show` + diagram-flag cases, or create `test_ll_loop_show_diagram_options.py`

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact line numbers:**
- `scripts/little_loops/cli/loop/__init__.py:145–185` — `--show-diagrams` arg group on `run_parser`
- `scripts/little_loops/cli/loop/__init__.py:284–323` — identical arg group on `resume_parser`
- `scripts/little_loops/cli/loop/__init__.py:423–434` — `show_parser` (currently: `loop`, `--verbose/-v`, `--json/-j`, `--resolved` only)
- `scripts/little_loops/cli/loop/info.py:725` — `--json` early-return in `cmd_show()` (already prevents diagram from running silently)
- `scripts/little_loops/cli/loop/info.py:817–827` — current fixed diagram call: `_render_fsm_diagram(fsm, verbose=verbose, badges=badges)`
- `scripts/little_loops/cli/loop/layout.py:1583–1594` — `_render_fsm_diagram()` signature (see correction note in Implementation Steps)
- `scripts/little_loops/cli/loop/_helpers.py:669` — `resolve_facets(args)` call site in `run_foreground()`
- `scripts/little_loops/cli/loop/_helpers.py:792–801` — **reference pattern** for unpacking `DiagramFacets` into `_render_fsm_diagram` params
- `scripts/little_loops/cli/history.py:99` — `add_mutually_exclusive_group()` example for `--json` / `--show-diagrams` mutual exclusion
- `scripts/tests/test_ll_loop_display.py:1648–1671` — `_make_args` test helper (model for `cmd_show` diagram tests)
- `scripts/tests/test_ll_loop_display.py:1953–2011` — existing diagram render assertion pattern

## Impact

- **Priority**: P3 — Non-blocking UX gap; workaround (run-time flags during `ll-loop run`) exists but is inconvenient for inspection-only workflows
- **Effort**: Small — primarily argument wiring; `resolve_facets()` and `_render_fsm_diagram()` already handle facets
- **Risk**: Low — additive flag; no change to existing `ll-loop show` behavior when flags are absent
- **Breaking Change**: No

## Status

**Open** | Created: 2026-05-25 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-25T22:07:31 - `432171fe-0cc8-40cb-a835-f0fb1286db77.jsonl`
- `/ll:confidence-check` - 2026-05-25T22:02:05 - `f360a7f8-c817-4ae2-95db-0b84dfdf3ee6.jsonl`
- `/ll:refine-issue` - 2026-05-25T22:00:13 - `40f247a8-f03d-401e-b7ae-d40b0149d9df.jsonl`
- `/ll:format-issue` - 2026-05-25T21:46:36 - `3a01038c-21a2-488f-9f60-e918f0e642d0.jsonl`

- `/ll:capture-issue` - 2026-05-25T21:37:44Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/64b024bf-4308-4b6e-97ef-4392da3c6e4b.jsonl`
- `/ll:manage-issue` - 2026-05-25T22:13:46Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
