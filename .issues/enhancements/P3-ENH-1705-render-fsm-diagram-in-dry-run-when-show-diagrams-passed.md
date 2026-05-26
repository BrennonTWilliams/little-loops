---
id: ENH-1705
title: "Render FSM diagram in dry-run when --show-diagrams passed"
type: ENH
status: open
priority: P3
captured_at: "2026-05-25T23:40:11Z"
discovered_date: 2026-05-25
discovered_by: capture-issue
labels: ["cli", "diagrams", "captured"]
---

# ENH-1705: Render FSM diagram in dry-run when --show-diagrams passed

## Summary

`ll-loop run <loop> --dry-run --show-diagrams` silently ignores `--show-diagrams`. The dry-run block in `cmd_run` exits early via `print_execution_plan()` before `resolve_facets` is ever called, so the diagram flag is discarded. Since the `FSMLoop` is fully loaded at that point and all config-derived rendering variables are already in scope, there is no technical barrier to rendering the diagram — it's an oversight.

## Current Behavior

Running `ll-loop run <loop> --dry-run --show-diagrams` (or `--show-diagrams detailed`) produces only the execution plan output. The `--show-diagrams` flag is silently discarded; no diagram is rendered.

## Expected Behavior

When `--show-diagrams` is passed alongside `--dry-run`, the FSM diagram is rendered before the execution plan is printed. The `--dry-run` flag should not suppress diagram rendering; both outputs should appear together.

Without `--show-diagrams`, dry-run behavior is unchanged.

## Motivation

Users run `--dry-run` to preview a loop before executing it. The diagram provides structural context — state graph, transitions, edge labels — that complements the execution plan. Silently discarding `--show-diagrams` is surprising and means users must run two separate commands (one dry-run, one `ll-loop show`) to get the full picture. This is a low-effort fix since all required variables are already in scope at the dry-run branch.

## Proposed Solution

Add diagram rendering inside the dry-run block of `cmd_run` in `scripts/little_loops/cli/loop/run.py` (~lines 173–175), before calling `print_execution_plan`:

```python
if args.dry_run:
    from little_loops.cli.loop.diagram_modes import resolve_facets
    from little_loops.cli.loop.layout import _render_fsm_diagram
    from little_loops.cli.output import terminal_width

    facets = resolve_facets(args)
    if facets is not None:
        tw = terminal_width()
        header_text = f"== loop: {fsm.name} "
        print(header_text + "=" * max(0, tw - len(header_text)))
        diagram = _render_fsm_diagram(
            fsm,
            highlight_color=_highlight_color,
            edge_label_colors=_edge_label_colors,
            badges=_badges,
            mode=facets.scope,
            suppress_labels=not facets.edge_labels,
            title_only=facets.state_detail == "title",
        )
        print(diagram)
        print()
    print_execution_plan(fsm, edge_label_colors=_edge_label_colors)
    return 0
```

All referenced variables (`fsm`, `_highlight_color`, `_edge_label_colors`, `_badges`) are already set before the dry-run block. Imports are scoped to the dry-run path to avoid loading layout code on every invocation.

**Utilities to reuse:**
- `resolve_facets(args)` — `scripts/little_loops/cli/loop/diagram_modes.py` — parses `--show-diagrams`, `--diagram-edge-labels`, `--diagram-state-detail`, `--diagram-scope` into a `DiagramFacets` dataclass; returns `None` when flag is absent.
- `_render_fsm_diagram(fsm, ...)` — `scripts/little_loops/cli/loop/layout.py` — returns diagram as a string; already used in `run_foreground` on `state_enter` events.
- `terminal_width()` — `scripts/little_loops/cli/output.py` — already imported in `_helpers.py`; needs a local import in `run.py`'s dry-run block.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — dry-run block (~lines 173–175)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/diagram_modes.py` — `resolve_facets` function (reuse, no change)
- `scripts/little_loops/cli/loop/layout.py` — `_render_fsm_diagram` function (reuse, no change)
- `scripts/little_loops/cli/output.py` — `terminal_width` function (reuse, no change)

### Similar Patterns
- `run_foreground` in `scripts/little_loops/cli/loop/run.py` — already calls `_render_fsm_diagram` on `state_enter` events; same pattern applies here

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add `test_dry_run_with_show_diagrams_renders_diagram` near existing dry-run tests (e.g. `test_positional_input_injected_into_context`)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Modify dry-run block in `cmd_run` (`scripts/little_loops/cli/loop/run.py`) to call `resolve_facets` and conditionally render the diagram before `print_execution_plan`.
2. Add unit test `test_dry_run_with_show_diagrams_renders_diagram` in `scripts/tests/test_ll_loop_commands.py` — use `capsys` or `io.StringIO`, pass `argparse.Namespace(dry_run=True, show_diagrams=True, ...)`, assert exit code 0, header line present, and box-drawing characters in output.
3. Verify manually: `ll-loop run <any-loop> --dry-run --show-diagrams` and `--dry-run --show-diagrams detailed`; confirm plain `--dry-run` is unchanged.

## Scope Boundaries

- Does not change `print_execution_plan` output or its position (diagram always precedes it).
- Does not add new CLI flags — reuses the existing `--show-diagrams` flag as-is.
- Does not affect non-dry-run execution paths.

## Impact

- **Priority**: P3 — Usability improvement; dry-run is commonly used but diagram suppression is a minor annoyance.
- **Effort**: Small — Single-file change (~10 lines) reusing existing utilities; no new abstractions.
- **Risk**: Low — Dry-run exits before any state mutations; diagram rendering is read-only and already tested in the foreground path.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `diagrams`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-25T23:40:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a35eda6f-f9c7-4896-b583-29b513842fa6.jsonl`

---

**Open** | Created: 2026-05-25 | Priority: P3
