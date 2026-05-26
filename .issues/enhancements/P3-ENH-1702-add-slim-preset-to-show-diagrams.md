---
id: ENH-1702
status: open
priority: P3
type: ENH
discovered_date: 2026-05-25
captured_at: '2026-05-25T23:00:07Z'
discovered_by: capture-issue
labels:
- cli
- loop
- diagram
- ux
---

# ENH-1702: Add `slim` Preset to `--show-diagrams` for Narrow Terminals

## Summary

Add a `slim` preset to `--show-diagrams` that combines the neighborhood
topology of `local` with the noise-reduction of `clean`, making it suitable
for terminals with narrow widths (≤80 cols). It fills the gap between
`oneline` (ultra-narrow, inline) and `local` (neighborhood but wide with
edge labels).

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

## API / Interface

No CLI flag changes. `slim` becomes a valid `--show-diagrams` value
alongside `detailed`, `summary`, `clean`, `local`, `oneline`.

## Out of Scope

- No new topology or rendering logic required — `neighborhood` + label-off
  is fully implemented via existing facets.
- No changes to `_LEGACY_HINTS` (no old name to migrate from).

## Session Log
- `/ll:format-issue` - 2026-05-26T01:37:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c75bd9d1-613d-4aa0-9283-47dd1f54df31.jsonl`
- `/ll:capture-issue` - 2026-05-25T23:00:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/632387fc-2984-41b5-beb0-6ada22e27465.jsonl`
