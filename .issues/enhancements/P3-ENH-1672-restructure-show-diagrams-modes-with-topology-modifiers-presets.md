---
captured_at: "2026-05-24T07:08:02Z"
discovered_date: 2026-05-24
discovered_by: capture-issue
status: open
priority: P3
type: ENH
---

# ENH-1672: Restructure --show-diagrams modes with topology + modifier flags + presets

## Summary

The current `--show-diagrams=<main|full|mini>` flag on `ll-loop run` / `ll-loop resume` conflates four orthogonal axes (path scope, edge labels, state body detail, topology) into a single enum. The `mini` name is also misleading — it describes the *visual size* rather than what was actually removed (edge labels + state body rows). Restructure into a primary topology flag with orthogonal modifier flags, plus named presets for common combinations.

## Current Behavior

Three modes are exposed via `--show-diagrams=<mode>`:

- `main` (default when flag passed bare) — layered diagram, main-path edges only, full labels, full state body
- `full` — layered diagram, all edges, full labels, full state body
- `mini` — layered diagram, no edge labels, title-only state boxes

Two other rendering modes exist internally but are not user-selectable:

- `_render_neighborhood_diagram` (layout.py:1702) — 1-hop horizontal `preds → [active] → succs` view
- `_render_single_line_status` (_helpers.py:229) — single-line `fsm: preds → [active] → succs`

These are used only as automatic fallbacks by `_choose_pinned_layout` (_helpers.py:205) when the terminal viewport is too short for the user's selected mode.

Problems:
1. `mini` name describes appearance, not the actual change (no labels + title-only states)
2. Users cannot select neighborhood or inline views directly
3. Four orthogonal facets (topology, edge labels, state detail, path scope) are collapsed into a single enum, blocking valid combinations like "neighborhood topology with main-path filtering" or "layered topology with no edge labels but full state body"
4. `main`/`full` names describe path *scope*, not topology — a poor fit once topology becomes a user choice

## Expected Behavior

**Primary flag** `--show-diagrams=<topology-or-preset>`:
- Topology values: `layered` | `neighborhood` | `inline`
- Preset values: `detailed` | `summary` | `clean` | `local` | `oneline`
- Bare `--show-diagrams` → defaults to `summary` preset

**Modifier flags** (always override preset expansion):
- `--diagram-edge-labels=on|off` (default `on`)
- `--diagram-state-detail=title|full` (default `full`)
- `--diagram-scope=main|full` (default `full`; silently ignored for `inline` topology)

**Preset expansion table:**

| Preset | Topology | Edge labels | State detail | Scope |
|---|---|---|---|---|
| `detailed` | layered | on | full | full |
| `summary` | layered | on | full | main |
| `clean` | layered | off | title | main |
| `local` | neighborhood | on | title | main |
| `oneline` | inline | — | — | — |

**Viewport fallback:** the existing `layered → neighborhood → inline` auto-degradation in `_choose_pinned_layout` kicks in only when the topology was chosen via default or preset. If the user explicitly passed `--show-diagrams=layered|neighborhood|inline`, the topology is respected exactly — no auto-degradation, accept overflow.

**Hard-rename migration** (no silent aliasing): old values error with a helpful hint:

| Old | Error message |
|---|---|
| `--show-diagrams` (bare) | "Bare --show-diagrams now selects the 'summary' preset by default; pass --show-diagrams=summary to silence this notice." |
| `--show-diagrams=main` | "main was renamed: use --show-diagrams=summary (path scope is now controlled by --diagram-scope=main)." |
| `--show-diagrams=full` | "full was renamed: use --show-diagrams=detailed (full graph is now controlled by --diagram-scope=full)." |
| `--show-diagrams=mini` | "mini was renamed: use --show-diagrams=clean (or set --diagram-edge-labels=off --diagram-state-detail=title for the underlying primitives)." |

## Motivation

The current mode set is a leaky enum: each value bundles unrelated decisions (topology, labels, content density, scope), so adding the obvious next variant ("layered with no edge labels but full state body" or "neighborhood with main-path scope") would require yet another mode name. The cross-product is ~24 combos, but only ~10-12 are sensible — the right shape is orthogonal facets with named presets for the common ones.

Concretely:
- "mini" forces users to read source to know what it does
- The neighborhood and inline renderers already exist and have been polished (BUG-759 alignment fix, `prev_state` highlight in commit `4fe19cd3`) but remain hidden behind a viewport-size heuristic
- Users running on wide terminals never see the neighborhood view even when they'd prefer it for focus
- The flat-enum design will collapse the moment we want a fifth or sixth combination

Human value is high: this is a UX surface that runs on every loop iteration with `--show-diagrams`, and the names appear in docs (LOOPS_GUIDE.md, CLI.md), commit messages, and issue references.

## Proposed Solution

### Argparse surface (cli/loop/__init__.py)

Replace the existing `--show-diagrams` choice list with a string-typed argument validated by a custom parser:

```python
TOPOLOGY_VALUES = {"layered", "neighborhood", "inline"}
PRESET_VALUES = {"detailed", "summary", "clean", "local", "oneline"}

def _parse_show_diagrams(value: str) -> str:
    if value in TOPOLOGY_VALUES | PRESET_VALUES:
        return value
    # Hard-rename migration: emit specific error per legacy value
    legacy_hints = {
        "main": "main was renamed: use --show-diagrams=summary ...",
        "full": "full was renamed: use --show-diagrams=detailed ...",
        "mini": "mini was renamed: use --show-diagrams=clean ...",
    }
    if value in legacy_hints:
        raise argparse.ArgumentTypeError(legacy_hints[value])
    raise argparse.ArgumentTypeError(
        f"unknown --show-diagrams value {value!r}; "
        f"choose from topologies {sorted(TOPOLOGY_VALUES)} or presets {sorted(PRESET_VALUES)}"
    )
```

Add three new flags on both `run` and `resume` subparsers:
- `--diagram-edge-labels` with `choices=["on", "off"]`, default `"on"`
- `--diagram-state-detail` with `choices=["title", "full"]`, default `"full"`
- `--diagram-scope` with `choices=["main", "full"]`, default `"full"`

### Preset expansion (new module, e.g. cli/loop/diagram_modes.py)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DiagramFacets:
    topology: str       # layered | neighborhood | inline
    edge_labels: bool   # True = on
    state_detail: str   # title | full
    scope: str          # main | full
    source: str         # "preset" | "topology" | "default" — drives fallback behavior

PRESET_EXPANSIONS: dict[str, DiagramFacets] = {
    "detailed": DiagramFacets("layered", True, "full", "full", "preset"),
    "summary":  DiagramFacets("layered", True, "full", "main", "preset"),
    "clean":    DiagramFacets("layered", False, "title", "main", "preset"),
    "local":    DiagramFacets("neighborhood", True, "title", "main", "preset"),
    "oneline":  DiagramFacets("inline", True, "title", "full", "preset"),
}

def resolve_facets(args) -> DiagramFacets | None:
    raw = getattr(args, "show_diagrams", None)
    if raw is None:
        return None
    if raw is True:  # bare --show-diagrams
        base = PRESET_EXPANSIONS["summary"]
        base = replace(base, source="default")
    elif raw in PRESET_EXPANSIONS:
        base = PRESET_EXPANSIONS[raw]
    elif raw in TOPOLOGY_VALUES:
        base = DiagramFacets(raw, True, "full", "full", "topology")
    else:
        raise ValueError(f"unreachable: argparse should have rejected {raw!r}")
    # Apply modifier overrides (always win, regardless of source)
    return replace(
        base,
        edge_labels=_override_bool(args.diagram_edge_labels, base.edge_labels),
        state_detail=getattr(args, "diagram_state_detail", base.state_detail),
        scope=getattr(args, "diagram_scope", base.scope),
    )
```

### Viewport fallback gating (cli/loop/_helpers.py:205)

`_choose_pinned_layout` currently always tries `[full, neighborhood, single]`. Gate the fallback chain on `facets.source`:

```python
def _choose_pinned_layout(rows, facets, variants_builder, ...):
    if facets.source == "topology":
        # Explicit topology: render once, no fallback
        single_variant = variants_builder(facets.topology)
        return single_variant, _count_display_lines(single_variant)
    # source == "preset" or "default": existing fallback chain
    ...
```

### Renderer thread-through (layout.py)

The existing `_render_fsm_diagram`, `_render_neighborhood_diagram`, and `_render_single_line_status` already accept the relevant primitives separately. The change is to stop deriving them from the old `mode` enum and instead pass `facets.edge_labels`, `facets.state_detail`, `facets.scope` through directly.

Existing parameters that map cleanly:
- `verbose` (currently set from `mode == "full"`) → derived from `facets.scope == "full"` and `facets.state_detail == "full"`
- `title_only` (currently set from `mode == "mini"`) → directly `facets.state_detail == "title"`
- The `_filter_main_path_graph` call (currently triggered by `mode in ("main", "mini")`) → triggered by `facets.scope == "main"`
- Edge-label suppression (currently triggered by `mode == "mini"`) → triggered by `not facets.edge_labels`

### Subprocess re-emission (cli/loop/_helpers.py:567)

The existing `cmd.extend(["--show-diagrams", show_diagrams_mode])` path needs to also forward the three new modifier flags so background subprocess invocations preserve the user's choices. Add:

```python
if facets.edge_labels is False:
    cmd.extend(["--diagram-edge-labels", "off"])
if facets.state_detail == "title":
    cmd.extend(["--diagram-state-detail", "title"])
if facets.scope == "main":
    cmd.extend(["--diagram-scope", "main"])
```

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — argparse definitions (run + resume subparsers, lines ~139, ~260)
- `scripts/little_loops/cli/loop/_helpers.py` — `show_diagrams_mode` resolution (~lines 567, 638-680), `_choose_pinned_layout` fallback (line 205), `_build_pinned_pane` dispatch (~lines 243, 258), subprocess re-emission (~line 567)
- `scripts/little_loops/cli/loop/layout.py` — `_render_fsm_diagram`, `_render_neighborhood_diagram`, `_render_single_line_status` parameter rewiring (mode → facets); `_render_neighborhood_diagram` already accepts `mode` arg at line 1709
- `scripts/little_loops/cli/loop/next_loop.py` — `show_diagrams=None` callsite (line 318)
- New file: `scripts/little_loops/cli/loop/diagram_modes.py` — `DiagramFacets` dataclass + `PRESET_EXPANSIONS` + `resolve_facets()`

### Dependent Files (Callers/Importers)

Run `grep -rn "show_diagrams\|--show-diagrams" scripts/ docs/ loops/` to enumerate. Known callsites from prior survey:
- `scripts/little_loops/cli/loop/__init__.py` (5 references)
- `scripts/little_loops/cli/loop/_helpers.py` (10+ references)
- `scripts/little_loops/cli/loop/next_loop.py` (1)
- `scripts/little_loops/cli/loop/layout.py` (4 docstring references)
- Loop YAMLs in `loops/` — check if any embed `--show-diagrams=main|full|mini` in their definitions (must be migrated or the hard rename breaks them)

### Similar Patterns

- The existing `--verbose` flag on `ll-loop` is the closest precedent for an orthogonal density modifier
- `ll-action`'s structured-output flags (`--format json|yaml|text`) are a precedent for enum + modifier separation

### Tests

- `scripts/tests/test_ll_loop_display.py` — add coverage for:
  - Each preset expansion (5 cases) resolves to the documented `DiagramFacets`
  - Each topology bare value (3 cases) resolves with correct defaults
  - Modifier flags override preset values (e.g. `--show-diagrams=clean --diagram-edge-labels=on` flips labels back on)
  - Hard-rename: each legacy value (`main`, `full`, `mini`, bare) raises `argparse.ArgumentTypeError` with a helpful message
  - Viewport fallback: `source="preset"` triggers fallback chain, `source="topology"` does not
  - Subprocess re-emission: new modifier flags are forwarded
- `scripts/tests/test_ll_loop.py` — argparse smoke tests for new flags on both `run` and `resume`

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — update `--show-diagrams` section (currently references `main`/`full`/`mini`)
- `docs/reference/CLI.md` — update `ll-loop run` and `ll-loop resume` flag tables
- `CHANGELOG.md` — breaking change entry under next release section (NOT `[Unreleased]` per repo convention)
- `.issues/enhancements/P4-ENH-1652-*.md` — link this issue as the follow-up restructure

### Configuration

- N/A (no config schema changes)

## Implementation Steps

1. **Add `DiagramFacets` dataclass and `PRESET_EXPANSIONS`** in new `cli/loop/diagram_modes.py`, plus `resolve_facets()` that reads argparse Namespace and returns the resolved facet object (with `source` field for fallback gating).
2. **Update argparse** on both `run` and `resume` subparsers in `cli/loop/__init__.py`: add custom `type=_parse_show_diagrams`, add three modifier flags, update help text. Legacy values raise `ArgumentTypeError` with migration hints.
3. **Rewire renderers** in `layout.py` to consume primitives (`edge_labels`, `state_detail`, `scope`) directly instead of deriving from `mode` enum. Existing `mode` parameter stays for `_filter_main_path_graph` selection but its inputs change.
4. **Gate viewport fallback** in `_choose_pinned_layout` and `_build_pinned_pane` on `facets.source`: only `preset`/`default` degrade through `layered → neighborhood → inline`; explicit `topology` is rendered exactly once.
5. **Forward modifier flags through subprocess re-emission** in `_helpers.py:567` so background `ll-loop` invocations preserve user choices.
6. **Audit `loops/` directory** for any embedded `--show-diagrams=<legacy>` and migrate to new names (otherwise hard rename breaks existing loops).
7. **Update docs** (LOOPS_GUIDE.md, CLI.md, CHANGELOG.md) and link from ENH-1652.
8. **Write tests** per Integration Map → Tests above.

## API/Interface

```python
# scripts/little_loops/cli/loop/diagram_modes.py
from dataclasses import dataclass

TOPOLOGY_VALUES: frozenset[str] = frozenset({"layered", "neighborhood", "inline"})
PRESET_VALUES:   frozenset[str] = frozenset({"detailed", "summary", "clean", "local", "oneline"})

@dataclass(frozen=True)
class DiagramFacets:
    topology: str       # layered | neighborhood | inline
    edge_labels: bool   # True = render edge labels
    state_detail: str   # title | full
    scope: str          # main | full  (ignored when topology == "inline")
    source: str         # default | preset | topology  (drives fallback gating)

PRESET_EXPANSIONS: dict[str, DiagramFacets] = {...}

def resolve_facets(args) -> DiagramFacets | None: ...
def _parse_show_diagrams(value: str) -> str: ...   # argparse type=
```

CLI surface change (breaking):

```
# Old (errors out with migration hint)
ll-loop run <loop> --show-diagrams=main
ll-loop run <loop> --show-diagrams=full
ll-loop run <loop> --show-diagrams=mini

# New
ll-loop run <loop> --show-diagrams=summary
ll-loop run <loop> --show-diagrams=detailed
ll-loop run <loop> --show-diagrams=clean

# New topologies (previously fallback-only)
ll-loop run <loop> --show-diagrams=local      # neighborhood
ll-loop run <loop> --show-diagrams=oneline    # inline

# New modifier composition
ll-loop run <loop> --show-diagrams=layered --diagram-scope=main --diagram-edge-labels=off
```

## Success Metrics

- All 5 presets + 3 topologies parseable and produce the documented `DiagramFacets`
- All 4 legacy values (`main`, `full`, `mini`, bare) emit migration-hint errors and exit non-zero
- Test coverage ≥ 90% for `diagram_modes.py`
- Zero references to legacy `mode` enum values in `scripts/little_loops/cli/loop/` after migration
- Docs (LOOPS_GUIDE.md, CLI.md) updated; `grep -r "show-diagrams=\(main\|full\|mini\)" docs/` returns empty

## Scope Boundaries

**Out of scope:**
- Adding new diagram topologies beyond layered/neighborhood/inline (e.g. radial, tree)
- Per-state styling overrides (color customization, custom badges)
- Interactive/live diagram modes (pan, zoom, click-to-focus)
- Persistence of diagram preferences in `.ll/ll-config.json` (could be a follow-up)
- Backward-compatibility aliasing — explicitly *not* doing this per the hard-rename decision; legacy values are errors, not warnings
- Renaming the `--show-diagrams` flag itself — name stays, only its values change
- Changes to the underlying `_render_*` algorithms or visual output of each topology

## Impact

- **Priority**: P3 — UX restructure with no functional blocker; current modes still work (just under new names after migration)
- **Effort**: Medium — touches argparse, helpers, layout renderers, subprocess re-emission, docs, and tests; ~6-10 hours including test coverage and loop YAML audit
- **Risk**: Medium — breaking CLI change (no aliasing) means any external scripts, loop YAMLs, or user muscle memory using `=main|full|mini` will error until migrated. Mitigated by clear per-value error messages pointing at the replacement.
- **Breaking Change**: Yes — `--show-diagrams=main|full|mini` no longer parse; bare `--show-diagrams` semantics preserved (still defaults, just to `summary` instead of `main`).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `breaking-change`, `ux`, `diagrams`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-24T07:12:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0356f6a-4e5b-45ac-bc51-6d6bd837e3ee.jsonl`

- `/ll:capture-issue` - 2026-05-24T07:08:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36dab78b-8ea5-4759-9747-53b92e93a9f7.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P3
