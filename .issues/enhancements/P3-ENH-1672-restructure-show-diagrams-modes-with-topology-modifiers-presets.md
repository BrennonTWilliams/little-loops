---
captured_at: '2026-05-24T07:08:02Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: done
completed_at: '2026-05-24T22:54:47Z'
priority: P3
type: ENH
decision_needed: false
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` calls `run_foreground(executor, fsm, args)` from `_helpers`; args flow through unmodified; no code change needed, but verify `resolve_facets()` uses `getattr` with defaults for the three new modifier attrs so this caller is not broken [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `run_foreground()`; modifier attrs arrive via the updated `resume` subparser in `__init__.py` — covered automatically once argparse is updated; no direct changes needed in `lifecycle.py` [Agent 1+2 finding]

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

_Wiring pass added by `/ll:wire-issue` — additional test files with Namespace factories that need the three new modifier keys:_
- `scripts/tests/test_cli_loop_lifecycle.py` — `_make_args()` at lines 855 and 943 have `show_diagrams=None` but lack `diagram_edge_labels`, `diagram_state_detail`, `diagram_scope`; add with defaults to both helpers [Agent 1+3 finding]
- `scripts/tests/test_cli_loop_background.py` — Namespace factories have no `show_diagrams` field at all; will `AttributeError` if `run_background` reads new modifier attrs without `getattr` defaults — add all four diagram attrs defensively [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py` — inline `argparse.Namespace` at line 2641 has `show_diagrams=None` but missing modifier keys [Agent 1+3 finding]
- `scripts/tests/test_ll_loop_program_md.py` — `_make_args()` at line 159 has `show_diagrams=None` but missing modifier keys [Agent 3 finding]
- `scripts/tests/test_cli_loop_worktree.py` — `_make_args()` at line 575 missing modifier keys [Agent 1+3 finding]
- `scripts/tests/test_cli_loop_queue.py` — `_make_args()` at line 25 missing modifier keys [Agent 3 finding]

_Tests that will BREAK on the mode-string → DiagramFacets transition (must be updated, not deleted):_
- `TestShowDiagramsMode` (lines 3125, 3154, 3167, 3178, 3187) — pass `mode="main"` / `mode="full"` directly to `_render_fsm_diagram`; replace with `DiagramFacets`-based kwargs [Agent 2+3 finding]
- `TestShowDiagramsMiniMode` (lines 3244, 3260, 3275, 3288) — pass `mode="mini"`; replace with `DiagramFacets`-based kwargs [Agent 2+3 finding]
- `TestShowDiagramsArgparse` (lines 3335, 3339, 3343, 3347) — assert on `"main"`, `"full"`, `"mini"` as parse results; convert to hard-rename `ArgumentTypeError` assertions [Agent 2+3 finding]
- `TestShowDiagramsSubprocessReemit` (lines 3393, 3399, 3405) — assert legacy mode strings in subprocess cmd list; also `_capture_cmd` Namespace missing new modifier attrs [Agent 2+3 finding]
- `_make_args()` shim at line 1648 in `TestDisplayProgressEvents` — `True → "main"` must become `True → "summary"` (or removed if `const=True` sentinel flows cleanly through `resolve_facets`) [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — update `--show-diagrams` section (currently references `main`/`full`/`mini`)
- `docs/reference/CLI.md` — update `ll-loop run` and `ll-loop resume` flag tables
- `CHANGELOG.md` — breaking change entry under next release section (NOT `[Unreleased]` per repo convention)
- `.issues/enhancements/P4-ENH-1652-*.md` — link this issue as the follow-up restructure

### Configuration

- N/A (no config schema changes)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify (additions/corrections to list above):**
- `scripts/little_loops/cli/loop/layout.py:710` — `_render_layered_diagram(mode="full")` also computes `title_only = mode == "mini"` internally; needs separate `edge_labels` and `state_detail` params — **missing from original file list**
- `scripts/little_loops/cli/loop/layout.py:1875` — `_render_horizontal_simple(mode="full")` same `title_only = mode == "mini"` pattern — **missing from original file list**
- `scripts/little_loops/cli/loop/_helpers.py:637-645` — `run_foreground()` coercion block (`if raw_show_diagrams is True: show_diagrams_mode = "main"; elif raw_show_diagrams in ("main", "full", "mini"):`) must be replaced with `resolve_facets(args)` from `diagram_modes.py`

**Additional callsite — non-pinned `display_progress()` branch:**
`_helpers.py` contains a parallel fallback in `display_progress()` for the non-pinned path (`in_pinned_mode = False`): `if parent_mode in ("main", "mini") and active_state not in reachable: parent_mode = "full"`. This branch calls `_render_fsm_diagram(mode=parent_mode)` directly and must also be converted to use `DiagramFacets`. Not mentioned in the original file list.

**Argparse `const` value — important implementation note:**
With `nargs="?"`, bare `--show-diagrams` stores the `const` value *without* invoking `type=`. Current `const="main"` must change to `const=True` (sentinel boolean) so `resolve_facets()` can distinguish bare-flag (`raw is True`) from explicit `--show-diagrams=summary`. The `type=_parse_show_diagrams` function is only called on explicit values — `True` bypasses it.

**Frozen dataclass model for `DiagramFacets`:**
Follow the `HostInvocation` pattern from `scripts/little_loops/host_runner.py:90-108`, which includes the project's canonical rationale for `frozen=True` value objects in the codebase.

**Subprocess re-emission exact block (`_helpers.py:567-569`):**
```python
show_diagrams_mode = getattr(args, "show_diagrams", None)
if show_diagrams_mode is not None:
    cmd.extend(["--show-diagrams", show_diagrams_mode])
```
New modifier flags follow the same `getattr(args, "<attr>", None) is not None → cmd.extend(...)` pattern used by every other forwarded flag in the block (lines 556-588).

**Loop YAML audit — confirmed 0 matches:**
`grep -rn "show-diagrams" loops/` returned 0 results. Step 6 of Implementation Steps (audit `loops/`) is N/A — no YAML migration needed.

**Test helper `_make_args` in `test_ll_loop_display.py:1648`:**
Contains `if show_diagrams is True: show_diagrams = "main"` legacy shim — must be updated to `"summary"` (or removed if bare-flag detection moves to `const=True` in argparse).

**Test class anchors (existing — to extend, not replace):**
- `TestShowDiagramsMode` — `test_ll_loop_display.py:3105` — covers `main`/`full`; convert to cover `summary`/`detailed` presets
- `TestShowDiagramsMiniMode` — `test_ll_loop_display.py:3215` — covers `mini`; convert to cover `clean` preset
- `TestShowDiagramsArgparse` — `test_ll_loop_display.py:3316` (6 methods) — extend for new presets/topologies/modifier flags and hard-rename error messages
- `TestShowDiagramsSubprocessReemit` — `test_ll_loop_display.py:3356` — add 3 modifier flag forwarding assertions
- `TestRenderNeighborhoodDiagram` — `test_ll_loop_display.py:3452` — add `local` preset end-to-end path

**`info.py` — no changes needed:**
`scripts/little_loops/cli/loop/info.py` references diagram rendering for the `ll-loop info` subcommand, which does not invoke `run_foreground()` or pass `show_diagrams` args. No changes required.

**`display_progress()` child-FSM mode path (`_helpers.py:785–814`) — missing from original file list:**
Mirrors the `parent_mode` logic for nested/child FSMs. `child_mode = show_diagrams_mode` (line 792), then `if child_mode in ("main", "mini") and ...` filters the main path, overriding `child_mode = "full"` with a `child_note` message when the active child state is off the main path (lines 799–803). Calls `_render_fsm_diagram(mode=child_mode)` at line 806. This block must be converted to `DiagramFacets` alongside the `parent_mode` path.

**`_render_one()` inside `_build_pinned_pane()` (`_helpers.py:291–303`) — pinned-path equivalent:**
The pinned-path parallel of the non-pinned main-path fallback: `mode` starts as `show_diagrams_mode` and is overridden to `"full"` when `highlight_state` is not in `reachable` (the main-path set). Must be converted to use `facets.scope` as the filtering trigger and pass `DiagramFacets` to the render call. Implementation Step 4 mentions `_build_pinned_pane` for fallback gating — this specific `_render_one()` block is the concrete location.

**Confirmed function signatures (for implementer reference):**
- `_render_fsm_diagram(fsm, verbose=False, highlight_state=None, highlight_color="32", edge_label_colors=None, badges=None, mode="full")` — `layout.py:1578`
- `_render_neighborhood_diagram(fsm, active_state, *, edge_label_colors=None, badges=None, highlight_color="32", mode="full", prev_state=None)` — `layout.py:1702`
- `_render_single_line_status(fsm, active_state)` — `_helpers.py:229` (no `mode` param; no changes needed)

## Implementation Steps

1. **Add `DiagramFacets` dataclass and `PRESET_EXPANSIONS`** in new `cli/loop/diagram_modes.py`, plus `resolve_facets()` that reads argparse Namespace and returns the resolved facet object (with `source` field for fallback gating).
2. **Update argparse** on both `run` and `resume` subparsers in `cli/loop/__init__.py`: add custom `type=_parse_show_diagrams`, add three modifier flags, update help text. Legacy values raise `ArgumentTypeError` with migration hints.
3. **Rewire renderers** in `layout.py` to consume primitives (`edge_labels`, `state_detail`, `scope`) directly instead of deriving from `mode` enum. Existing `mode` parameter stays for `_filter_main_path_graph` selection but its inputs change.
4. **Gate viewport fallback** in `_choose_pinned_layout` and `_build_pinned_pane` on `facets.source`: only `preset`/`default` degrade through `layered → neighborhood → inline`; explicit `topology` is rendered exactly once.
5. **Forward modifier flags through subprocess re-emission** in `_helpers.py:567` so background `ll-loop` invocations preserve user choices.
6. **Audit `loops/` directory** for any embedded `--show-diagrams=<legacy>` and migrate to new names (otherwise hard rename breaks existing loops).
7. **Update docs** (LOOPS_GUIDE.md, CLI.md, CHANGELOG.md) and link from ENH-1652.
8. **Write tests** per Integration Map → Tests above.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Update `next_loop.py` Namespace** (lines 306–328) — add `diagram_edge_labels="on"`, `diagram_state_detail="full"`, `diagram_scope="full"` to the manually-constructed `run_args` Namespace so `resolve_facets()` does not raise `AttributeError` if it uses direct attribute access instead of `getattr` with defaults [Agent 2 finding]
10. **Update `_make_args()` shim** in `test_ll_loop_display.py` at line 1648 — change `True → "main"` to `True → "summary"` (or remove the shim once `const=True` sentinel is the canonical design) [Agent 3 finding]
11. **Update Namespace factories in 6 additional test files** — add `diagram_edge_labels`, `diagram_state_detail`, `diagram_scope` with their defaults to every `_make_args()` or inline `argparse.Namespace` in: `test_cli_loop_lifecycle.py` (lines 855, 943), `test_cli_loop_background.py`, `test_ll_loop_commands.py` (line 2641), `test_ll_loop_program_md.py` (line 159), `test_cli_loop_worktree.py` (line 575), `test_cli_loop_queue.py` (line 25) [Agent 1+3 finding]

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- Wide blast radius across `_helpers.py` — `show_diagrams_mode` is used in 8+ distinct function bodies (`run_foreground`, `_build_pinned_pane`, `_choose_pinned_layout`, `display_progress`, subprocess re-emission, `parent_mode`/`child_mode` assignment blocks); each requires logic changes, not just a parameter rename — broad per-site rewiring across one large module.
- Namespace factory updates required in 6 additional test files alongside the main change — the wire-issue pass has enumerated all 6 (lifecycle, background, commands, program_md, worktree, queue); missing any one will cause `AttributeError` at test time.

## Session Log
- `/ll:ready-issue` - 2026-05-24T22:13:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1265e3e-ec44-402f-b392-84a53ecc4c86.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ceb512a0-0fa2-4aec-afc4-02a1e78ad108.jsonl`
- `/ll:refine-issue` - 2026-05-24T22:01:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ceb512a0-0fa2-4aec-afc4-02a1e78ad108.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:57:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91a0ef70-685e-4909-a396-2d9a3ea31d5f.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f20bb894-da96-47c8-9052-e4eb484495b1.jsonl`
- `/ll:wire-issue` - 2026-05-24T21:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0c7cf1b-4752-4dcb-a8c8-db15f836c539.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:29:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ca89f4a-4af7-4703-a6e0-ea8057ea3364.jsonl`
- `/ll:format-issue` - 2026-05-24T07:12:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0356f6a-4e5b-45ac-bc51-6d6bd837e3ee.jsonl`

- `implementation` - 2026-05-24T22:54:47Z - All 7700 tests pass; implementation complete (diagram_modes.py, __init__.py, _helpers.py, layout.py, next_loop.py, display tests, 5 Namespace test files, LOOPS_GUIDE.md, CLI.md)
- `/ll:capture-issue` - 2026-05-24T07:08:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36dab78b-8ea5-4759-9747-53b92e93a9f7.jsonl`

---

**Done** | Created: 2026-05-24 | Completed: 2026-05-24 | Priority: P3
