---
id: ENH-1705
title: Render FSM diagram in dry-run when --show-diagrams passed
type: ENH
status: done
priority: P3
captured_at: '2026-05-25T23:40:11Z'
completed_at: '2026-05-26T20:38:26Z'
discovered_date: 2026-05-25
discovered_by: capture-issue
labels:
- cli
- diagrams
- captured
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

## Success Metrics

- `ll-loop run <loop> --dry-run --show-diagrams` renders a box-drawing diagram above the execution plan (output contains box-drawing characters)
- `ll-loop run <loop> --dry-run --show-diagrams detailed` also renders a diagram (detailed scope respected)
- `ll-loop run <loop> --dry-run` (without `--show-diagrams`) output is unchanged — no diagram rendered

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — calls `cmd_run()` in `main_loop()` (line 539); no signature change needed, already passes `show_diagrams` in `args`
- `scripts/little_loops/cli/loop/next_loop.py` — calls `cmd_run()` at line 332 via `--execute` flag; same args pass-through, no change needed

### Similar Patterns
- `run_foreground` in `scripts/little_loops/cli/loop/_helpers.py` — already calls `_render_fsm_diagram` on `state_enter` events (lines 770–801); same pattern applies here

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add `test_dry_run_with_show_diagrams_renders_diagram` near existing dry-run tests (e.g. `test_positional_input_injected_into_context`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py` — contains `TestPrintExecutionPlan` (lines 329–548, dry-run output tests; all pass `show_diagrams=None`, safe/no changes needed) and `TestRunForeground.test_show_diagrams_state_enter_prints_diagram` (line ~2002, diagram rendering pattern to follow for new test)
- `scripts/tests/test_ll_loop_integration.py` — contains `TestMainLoopIntegration.test_run_dry_run_outputs_plan` (line 115; uses `in`-assertions on plan text, passes without `--show-diagrams`, unaffected)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Add to `TestCmdRunContextInjection` class, after `test_positional_input_injected_into_context` (line 2623) — this is the only class that calls `cmd_run` directly with `dry_run=True`
- Reuse the `_SIMPLE_LOOP_YAML` constant at line 3707 for the loop fixture
- Full `argparse.Namespace` template: use same fields as `test_positional_input_injected_into_context` (lines 2629–2648), set `show_diagrams=True` (bare-flag sentinel), `diagram_edge_labels=None`, `diagram_state_detail=None`, `diagram_scope=None`
- Capture output via `capsys.readouterr().out`
- Assertions: `assert "┌" in out or "─" in out` (box-drawing chars, pattern from `test_diagram_output_contains_box_chars` line 3839); `assert "Execution plan for" in out` (plan still renders after diagram)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-loop run` flag table: `--dry-run` row describes "Show execution plan without running" with no mention of diagram interaction; no combined `--dry-run --show-diagrams` example in the examples block (line ~594)
- `docs/guides/LOOPS_GUIDE.md` — **Run Flags** section: `--show-diagrams` entry (line ~2563) describes "after each step" behavior but is silent on dry-run; no combined example

### Configuration
- N/A

## Implementation Steps

1. Modify dry-run block in `cmd_run` (`scripts/little_loops/cli/loop/run.py`) to call `resolve_facets` and conditionally render the diagram before `print_execution_plan`.
2. Add unit test `test_dry_run_with_show_diagrams_renders_diagram` in `scripts/tests/test_ll_loop_commands.py` — use `capsys` or `io.StringIO`, pass `argparse.Namespace(dry_run=True, show_diagrams=True, ...)`, assert exit code 0, header line present, and box-drawing characters in output.
3. Verify manually: `ll-loop run <any-loop> --dry-run --show-diagrams` and `--dry-run --show-diagrams detailed`; confirm plain `--dry-run` is unchanged.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/reference/CLI.md` — add a combined `--dry-run --show-diagrams` example and note in the `--dry-run` flag description that diagram rendering is not suppressed when `--show-diagrams` is also passed.
5. Update `docs/guides/LOOPS_GUIDE.md` — add analogous note in the **Run Flags** section for `--show-diagrams` describing dry-run interaction.

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

## Session Log
- `/ll:ready-issue` - 2026-05-26T20:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9add640f-7a17-4157-9018-185efd7ddc81.jsonl`
- `/ll:confidence-check` - 2026-05-26T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a2e6f38-a0eb-41d9-820e-6ac6a48415f5.jsonl`
- `/ll:wire-issue` - 2026-05-26T20:31:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47cef901-86e9-4bd2-b772-ff487dd8bdac.jsonl`
- `/ll:refine-issue` - 2026-05-26T20:25:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a02e39e-0327-4fde-996c-a64d954c3e35.jsonl`
- `/ll:format-issue` - 2026-05-26T20:16:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f238e1de-2a0d-4c63-94af-3f5bc586be30.jsonl`

- `/ll:capture-issue` - 2026-05-25T23:40:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a35eda6f-f9c7-4896-b583-29b513842fa6.jsonl`

---

**Open** | Created: 2026-05-25 | Priority: P3
