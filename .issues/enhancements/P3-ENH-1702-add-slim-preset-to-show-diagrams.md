---
id: ENH-1702
status: done
priority: P3
type: ENH
discovered_date: 2026-05-25
captured_at: '2026-05-25T23:00:07Z'
completed_at: '2026-05-27T02:13:13Z'
discovered_by: capture-issue
labels:
- cli
- loop
- diagram
- ux
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1702: Add `slim` Preset to `--show-diagrams` for Narrow Terminals

## Summary

Add a `slim` preset to `--show-diagrams` that combines the neighborhood
topology of `local` with the noise-reduction of `clean`, making it suitable
for terminals with narrow widths (≤80 cols). It fills the gap between
`oneline` (ultra-narrow, inline) and `local` (neighborhood but wide with
edge labels).

## Current Behavior

No `slim` preset exists. Users with narrow-terminal panes who want topology
context must choose between `local` (neighborhood topology but includes edge
labels, too wide at ≤80 cols) or `clean` (strips edge labels but uses full
layered topology, still wide). Neither preset serves the "narrow terminal +
topology context" use case.

## Expected Behavior

`--show-diagrams=slim` renders a neighborhood-topology diagram without edge
labels and with title-only state names, making it suitable for terminals ≤80
cols wide. See **Proposed Behavior** below for the exact `DiagramFacets`
specification.

## Motivation

`local` uses neighborhood topology (1-hop preds → active → succs), which is
already narrower than `layered`, but still renders edge labels — making it
too wide for narrow panes. `clean` strips edge labels and uses title-only
state detail, but keeps the full layered topology. Neither preset alone
serves the "narrow terminal, topology context" use case. `slim` combines
both noise-reduction axes.

## Success Metrics

- `"slim" in PRESET_VALUES` is `True` — verified by existing preset round-trip test
- `resolve_facets("slim")` returns `DiagramFacets("neighborhood", False, "title", "main", "preset")` — verified by unit test in `test_diagram_modes.py`
- `--show-diagrams=slim` renders a diagram without edge labels and with title-only state names
- All existing preset tests continue to pass (no regression)

## Proposed Behavior

`--show-diagrams=slim` expands to:

```python
DiagramFacets("neighborhood", False, "title", "main", "preset")
```

- **topology**: `neighborhood` — 1-hop preds → [active] → succs; bounded
  width regardless of FSM size
- **edge_labels**: `False` — bare `───` connectors, no label text
- **state_detail**: `title` — state name only, no body/verdict lines
- **scope**: `main` — main-path states only

## Implementation Steps

1. **`scripts/little_loops/cli/loop/diagram_modes.py`** — one-liner addition
   to `PRESET_EXPANSIONS`:

   ```python
   "slim": DiagramFacets("neighborhood", False, "title", "main", "preset"),
   ```

2. **`PRESET_VALUES`** — add `"slim"` to the frozenset.

3. **Argparse help string** — update the `--show-diagrams` help text in
   `scripts/little_loops/cli/loop/__init__.py` (appears 3×) to include
   `slim` in the preset list.

4. **Tests** — add `slim` to the preset round-trip test in
   `scripts/tests/test_diagram_modes.py` (or equivalent); verify
   `resolve_facets` returns the expected `DiagramFacets`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/CLI.md` — add `slim` to the preset list in the `--show-diagrams` row of the ll-loop run, resume, and show flag tables (3 occurrences of `(detailed|summary|clean|local|oneline)`)
6. Update `docs/guides/LOOPS_GUIDE.md` — add `slim` to the preset list in the Run and Resume Flags table (1 occurrence)
7. Add `test_show_diagrams_slim_forwarded_to_render` to `test_ll_loop_display.py` — kwargs-forwarding test for run-loop path (Pattern D; clone `test_show_diagrams_clean_forwarded_to_render` at line 2033)
8. Add `test_show_diagrams_slim_preset` to `test_ll_loop_commands.py::TestCmdShowDiagramOptions` — kwargs-forwarding test for `cmd_show` path (Pattern E; clone `test_show_diagrams_clean_preset` at line 3851)

## API / Interface

No CLI flag changes. `slim` becomes a valid `--show-diagrams` value
alongside `detailed`, `summary`, `clean`, `local`, `oneline`.

## Out of Scope

- No new topology or rendering logic required — `neighborhood` + label-off
  is fully implemented via existing facets.
- No changes to `_LEGACY_HINTS` (no old name to migrate from).

## Impact

- **Priority**: P3 — Quality-of-life improvement for narrow-terminal users; no blocking dependencies
- **Effort**: Small — One-liner addition to `PRESET_EXPANSIONS` + help-text updates + mechanical test clones; reuses fully-implemented `neighborhood` topology and label-suppression path
- **Risk**: Low — Purely additive; no existing behavior changes; all existing preset tests continue to pass
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/diagram_modes.py` — add `"slim"` to `PRESET_VALUES` (line 20) and add one entry to `PRESET_EXPANSIONS` (lines 56–62)
- `scripts/little_loops/cli/loop/__init__.py` — update preset list in `--show-diagrams` help text in three subparser registrations: `run_parser` (lines 160–167), `resume_parser` (lines 300–306), `show_parser` (lines 448–457); all three currently read `(detailed|summary|clean|local|oneline)`
- `scripts/tests/test_ll_loop_display.py` — extend test coverage (see Implementation Steps)

### Dependent Files (Read-Only, No Changes)
- `scripts/little_loops/cli/loop/_helpers.py` — imports `resolve_facets` from `diagram_modes`; picks up `slim` automatically once `PRESET_EXPANSIONS` is updated
- `scripts/little_loops/cli/loop/info.py` — imports `resolve_facets` from `diagram_modes`; no changes needed
- `scripts/little_loops/cli/loop/layout.py` — consumes resolved `DiagramFacets`; `neighborhood` topology already supported
- `scripts/little_loops/cli/loop/run.py` — imports `resolve_facets` inside `cmd_run()` dry-run branch (line 174); picks up `slim` automatically [Wiring pass added by `/ll:wire-issue`]

### Tests
- `scripts/tests/test_ll_loop_display.py:3177` — `TestDiagramFacets.test_each_preset_resolves_to_documented_facets`: add `"slim": DiagramFacets("neighborhood", False, "title", "main", "preset")` to the expected dict
- `scripts/tests/test_ll_loop_display.py:3535` — `TestShowDiagramsArgparse`: add `test_show_diagrams_preset_slim` method (argparse acceptance)
- `scripts/tests/test_ll_loop_display.py:3643` — `TestShowDiagramsSubprocessReemit`: add `test_preset_slim_reemitted_to_cmd` method (subprocess re-emit)
- Note: `_parse_show_diagrams` error message auto-generates from `sorted(PRESET_VALUES)` — no manual update needed there

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py` — add `test_show_diagrams_slim_forwarded_to_render` in the kwargs-forwarding class (Pattern D; mirrors `test_show_diagrams_clean_forwarded_to_render` at line 2033); expected: `suppress_labels=True, title_only=True, mode="main"` [5th test pattern identified by Agent 3]
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdShowDiagramOptions`: add `test_show_diagrams_slim_preset` method (Pattern E; mirrors `test_show_diagrams_clean_preset` at line 3851); patches `info_mod._render_fsm_diagram`, asserts `suppress_labels=True, title_only=True, mode="main"` [Agent 3 finding — this class covers the `cmd_show` path and has no slim test]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — hard-codes preset list as `(detailed|summary|clean|local|oneline)` in three flag-table rows (ll-loop run, resume, show); add `slim` to all three
- `docs/guides/LOOPS_GUIDE.md` — hard-codes preset list as `a **preset** (detailed|summary|clean|local|oneline)` in the Run and Resume Flags table; add `slim`

### Similar Patterns
- `local` preset at `diagram_modes.py:59` — closest analogue (`neighborhood`, `True`, `title`, `main`, `preset`); `slim` differs only in `edge_labels=False`
- `clean` preset at `diagram_modes.py:58` — shares `edge_labels=False, state_detail=title, scope=main` fields; differs in `topology=layered`
- Test patterns for `clean`/`local` at `test_ll_loop_display.py:3177,3543,3655` — direct template for `slim` additions

### Codebase Research Notes

_Added by `/ll:refine-issue` — based on codebase analysis:_

The `_parse_show_diagrams` validator (lines 72–87) accepts any value in `TOPOLOGY_VALUES | PRESET_VALUES`. Adding `"slim"` to `PRESET_VALUES` is sufficient to ungate it in argparse — no changes to the validator body needed. The bare `--show-diagrams` flag uses `const=True` (bypasses the type function) and resolves to the `summary` preset default via `resolve_facets()`; `slim` has no interaction with this path.

The test file `test_ll_loop_display.py` has **five distinct test patterns** over presets (bulk expansion dict, `resolve_facets` round-trip, argparse acceptance, subprocess re-emit, `_render_fsm_diagram` kwargs forwarding). The issue's Success Metrics reference only the first two; the argparse acceptance test and subprocess re-emit test are low-effort additions that follow identical mechanical patterns for each existing preset.

## Session Log
- `/ll:ready-issue` - 2026-05-27T02:07:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7333fa9b-23e1-4d86-b9f4-e566eefd4ba6.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/651eaac4-300f-4fe6-b50d-34d0d2965c0e.jsonl`
- `/ll:wire-issue` - 2026-05-27T02:01:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44c24902-b7db-4f3d-8b6d-550ea0038154.jsonl`
- `/ll:refine-issue` - 2026-05-27T01:56:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3786932-ec4d-4cae-adac-46d10e0c0537.jsonl`
- `/ll:format-issue` - 2026-05-26T01:37:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c75bd9d1-613d-4aa0-9283-47dd1f54df31.jsonl`
- `/ll:capture-issue` - 2026-05-25T23:00:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/632387fc-2984-41b5-beb0-6ada22e27465.jsonl`
