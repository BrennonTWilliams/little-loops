---
id: ENH-3431
type: ENH
title: 'll-issues clusters: render in work-order direction with wave grouping'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T23:02:24Z'
verify_verdict: VALID
---

# ENH-3431: ll-issues clusters: render in work-order direction with wave grouping

## Summary

`ll-issues clusters` is used by a developer to decide **what order to implement open issues in**, but every renderer (`tree`, `boxes`, `list`) draws edges in *semantic* direction (`A blocked_by B` is drawn from A toward B) rather than *work-order* direction (B before A). The reader has to decode three things per edge — the arrow glyph (`→`/`←`, `▲`/`▼`), the relationship word, and the legend's "source/target" convention — and the default `tree` layout additionally roots at the highest-degree hub, which is frequently an issue in the *middle* of the order. Normalize ordering edges into a single "before" direction, add wave (topological-level) grouping, and re-root the tree at prerequisites so reading top-down is reading the order.

## Current Behavior

All three layouts draw each edge in the direction the frontmatter spells it: `blocked_by` points from the blocked issue to its blocker, `blocks` the opposite way, `depends_on` like `blocked_by`. The `tree` default roots at the highest-degree node, so a mid-chain hub becomes the root and the real starting issue appears as a child with `→ blocked_by`. `boxes` topo-sorts correctly but draws `blocked_by` as `▲`, uses `relates_to` as a connector between parallel issues, and dumps non-adjacent blocking edges into a trailing text list. No layout groups issues by dependency level.

## Expected Behavior

Reading any layout top-down is reading the implementation order. Issues with no in-cluster prerequisite appear first (wave 1) and are marked `ready` only when every one of their `blocked_by` targets — including targets outside the cluster or outside the `--status` filter — is terminal (`done`/`cancelled`); issues that can proceed in parallel are visibly grouped in the same wave; every edge label reads in one consistent direction (`needs` / `unblocks`) so the legend is not required to interpret the diagram; `relates_to` and `parent` are shown as undirected annotations and never as ordering edges. The topo order used by `list`/`boxes`/`tree` and the wave numbers used by `waves`/JSON come from the same normalized edge set, so all layouts agree.

## Motivation

Concrete example (5-issue cluster, `edges=all`). The true order is ENH-3427 → {ENH-3428, ENH-3429, ENH-3430 in parallel} → ENH-3422. Current default `tree` output:

```
[P2] ENH-3430  Rewire ll-logs onto the session-discovery seam; …
├── [P2] ENH-3427  Host-resolution seam — --host flag, …  → blocked_by
│   ⤷ ← blocked_by ENH-3428
│   ⤷ ← blocked_by ENH-3429
├── [P2] ENH-3428  Rewire ll-messages onto the session-discovery seam …  ← relates_to
│   ⤷ → relates_to ENH-3429
├── [P2] ENH-3429  Rewire ll-ctx-stats onto the session-discovery seam …  ← relates_to
└── [P3] ENH-3422  Make _backfill_raw_events consume iter_events …  ← blocked_by
```

The root (ENH-3430) is the hub by degree but is third in execution order; the actual starting point (ENH-3427) is drawn as a *child* with `→ blocked_by`. The order is invisible.

`--layout boxes` gets the topo order right (3427, 3428, 3429, 3430, 3422) but draws every `blocked_by` as `▲` (pointing against the stack), inserts `relates_to` arrows between 3428/3429/3430 so three parallel issues look like a serial chain, and demotes the two most important edges (3428→3427, 3429→3427 `blocked_by`) to a trailing text list.

Root causes in `scripts/little_loops/cli/issues/clusters.py`:

- `_cluster_edges` returns `(from_id, to_id, rel)` in frontmatter direction and every renderer draws that direction verbatim. `blocked_by`, `blocks`, and `depends_on` are three spellings of one ordering fact but are rendered as three differently-oriented edges.
- `_render_cluster_tree` picks roots by descending degree, tie-broken by topo index (the hub heuristic). Correct for EPIC/`parent` hierarchies, wrong for blocking chains.
- `_render_cluster_diagram` only draws connectors between *consecutive* topo-sorted nodes and treats `relates_to` as a connector, so parallelism is never visible.
- `_topo_sort_cluster` produces a flat order but no level/wave information; `clusters.py` itself has no wave helper — the two related helpers found elsewhere in the package (`LayerAssigner.assign()`, `DependencyGraph.get_execution_waves()`) use different algorithms/edge sets and are not drop-ins (see Codebase Research Findings below).
- `_topo_sort_cluster` is fed a raw `issue.blocked_by` map (`cmd_clusters`, `clusters.py:638-648`), so the render order ignores `blocks`, `depends_on`, and the `--edges` filter entirely. An issue that declares only `blocks: [X]` (no reciprocal `blocked_by` on X) is invisible to the sort. Any wave computation built on a different edge set than this sort would make `ordered_ids` and `waves` disagree.
- `_cluster_edges` dedups per unordered pair with `_EDGE_PRIORITY` ranking `parent` (2) above `depends_on` (3): a child with both `parent: EPIC-1` and `depends_on: EPIC-1` keeps only the annotation and loses the ordering fact. The same dedup collapses a 2-cycle (`A blocked_by B`, `B blocked_by A`) into a single edge, so cycle detection cannot rely on the deduped list.
- "No in-cluster prerequisite" is not "ready": under the default `--status=active`, a blocker that is `deferred`, filtered out, or a dangling ID is simply absent, so the blocked issue would land in wave 1. Per CLAUDE.md only `done`/`cancelled` resolve dependency edges; `find_issues_for_graph` (`issue_parser.py:4452-4471`, BUG-2897) exists for exactly this superset-then-narrow pattern.

## Proposed Solution

1. **Normalize ordering edges** (`_normalize_edges`): map `X blocked_by Y`, `Y blocks X`, and `X depends_on Y` to a single directed fact `Y → X` ("Y before X"), tagged `hard` (`blocked_by`/`blocks`) or `weak` (`depends_on`). `relates_to` and `parent` are not ordering facts: keep them as undirected annotations (`~`), never as tree branches (except the mixed-cluster rule in item 4) or arrow slots.

   - **Dedup per category, not per pair.** Change `_cluster_edges` so each unordered pair may keep *one ordering edge* (priority `blocked_by` > `blocks` > `depends_on`) *and one annotation edge* (`parent` > `relates_to`) — today `parent` outranks `depends_on` and silently drops the ordering fact. Contradictory ordering declarations on one pair (`A blocked_by B` and `A blocks B`) resolve by that same priority. The raw JSON `edges` array keeps its current shape but may now contain two entries for one pair.
   - **Keep both directions of a 2-cycle.** Normalization must operate on the pre-dedup candidate list (or dedup on the *ordered* pair) so `A blocked_by B` + `B blocked_by A` survives as two normalized edges and is detected as a cycle. Cycle detection never reads the pair-deduped list.
   - Naming: the existing `--edges=hard` alias already includes `depends_on` (`_HARD_EDGE_TYPES`, `clusters.py:53`). The strength tag therefore uses `hard`/`weak`, not `hard`/`soft`, and the CLI.md prose calls this out so the two vocabularies don't read as contradictory.

2. **One ordering pass** (`_order_and_waves`): Kahn's algorithm over the *normalized* edge list (hard and weak edges both order; `--edges` filtering applies because the input is the filtered `_cluster_edges` output). Returns `(ordered_ids, waves, has_cycle)` in a single call so `list`/`boxes`/`tree` order and `waves`/JSON wave numbers can never disagree. Wave = longest-path depth, 1-indexed. Replaces the `blocked_by_map` input to `_topo_sort_cluster` in `cmd_clusters` (`clusters.py:638-648`); `_topo_sort_cluster` itself is either retired or reduced to a thin wrapper. Nodes that never reach in-degree 0 — cycle members *and* anything downstream of a cycle — go into a final **`unresolved`** bucket (not labelled "cycle", since downstream nodes aren't in the cycle) in sorted-ID order, and `has_cycle` stays true, reusing the existing fallback warning.

3. **Readiness** (`_ready_ids`): wave 1 means "no in-cluster prerequisite", which is *not* "ready". Load the non-terminal superset via `find_issues_for_graph(config)` (`issue_parser.py:4452`, the BUG-2897 pattern) once per command, and mark an issue `ready` only when every ID in its raw `blocked_by`/`depends_on` is absent from that superset (i.e. terminal or nonexistent). A wave-1 issue with a `deferred` or `--status`-filtered blocker renders without `ready` and with a `⏳ waits on ENH-NNNN (deferred)` suffix. The same superset answers the reverse case: a `status: blocked` issue whose blockers are all terminal gets `⚠ status is blocked but no active blockers`. The display list is still the `--status`-narrowed `find_issues` result; the superset is only consulted for readiness.

4. **New default layout `waves`**. Every line always prints its own `needs` list (when non-empty) and `unblocks` list; wave headers carry no "(after X)" parenthetical, because that label is only well-defined when every member shares one prerequisite. Wave 1's header reads `(no in-cluster prerequisite)`; `ready` is a per-line marker:

```
─── Cluster 1 (5 issues) · 3 waves · start ENH-3427 · P2×4 P3×1 ───
Wave 1  (no in-cluster prerequisite)
  [P2] ENH-3427  Host-resolution seam — --host flag, …          ready
                 unblocks ENH-3428, ENH-3429, ENH-3430

Wave 2
  [P2] ENH-3428  Rewire ll-messages …        needs ENH-3427   ~ ENH-3429, ENH-3430
  [P2] ENH-3429  Rewire ll-ctx-stats …       needs ENH-3427   ~ ENH-3430
  [P2] ENH-3430  Rewire ll-logs …            needs ENH-3427   unblocks ENH-3422

Wave 3
  [P3] ENH-3422  Make _backfill_raw_events … needs ENH-3430

Unresolved (cycle)
  …only present when has_cycle…
```

   Within a wave, lines sort by priority, then by `relates_to` adjacency (issues related to each other stay together), then by ID.

5. **Re-root `tree`** at wave-1 issues (instead of the hub), walk "before" edges downstream, annotate `needs <X>` on a child only for prerequisites that are not its direct tree parent; cross-edges and `relates_to` stay as `⤷` lines with `~` for undirected:

```
[P2] ENH-3427  Host-resolution seam …                    ready
├── [P2] ENH-3428  Rewire ll-messages …
│   ⤷ ~ relates_to ENH-3429, ENH-3430
├── [P2] ENH-3429  Rewire ll-ctx-stats …
│   ⤷ ~ relates_to ENH-3430
└── [P2] ENH-3430  Rewire ll-logs …
    └── [P3] ENH-3422  Make _backfill_raw_events …
```

   Three root-selection cases, gated on the cluster's edge mix:
   - **No ordering edges** (all `parent`/`relates_to`): keep the existing hub-root heuristic verbatim — the EPIC-hierarchy case FEAT-2337 designed it for.
   - **Only ordering edges**: roots are the wave-1 issues in wave-line order; branches are "before" edges only.
   - **Mixed** (the common real case: an EPIC with `parent` children where some children block each other): `parent` edges act as tree branches *only from a parent to its wave-1 children*; deeper children hang under their blockers via "before" edges as usual. Result reads EPIC → ready children → downstream. A node with no `parent` edge and wave 1 is still its own root. A `parent` edge to a non-wave-1 child renders as `⤷ ~ parent EPIC-N` under that child.

6. **`boxes`**: with the stack ordered from normalized edges, every arrow between consecutive nodes is `▼` and the label reads `needs`. Move skip edges into the box as an `unblocks:` line; drop `relates_to` from arrow slots. Boxes stays a secondary layout (a single column cannot show parallelism).

7. **Header/legend**: when the cluster has ordering edges, replace `hub ENH-XXXX` with `start ENH-XXXX` if exactly one wave-1 issue exists, otherwise `N start` (e.g. `3 start`), followed by `· M waves`. When the cluster has no ordering edges, keep `hub ENH-XXXX` so header and tree body agree (both hub computations at `clusters.py:131` and `:254` switch on the same gate). Legend shrinks to `needs` (hard, must finish first), `prefers` (weak, `depends_on`), `~` (related, no ordering).

8. **JSON**: add `wave` (int, `null` for unresolved) and `ready` (bool) per issue, and a `normalized_edges` array (`{before, after, strength}`) alongside the existing raw `edges`, so automation gets the same answer as the terminal. The JSON branch must call the same `_order_and_waves` + `_ready_ids` the text path uses.

9. `--edges` semantics unchanged; `--edges=blocking` simply yields no `weak` edges and no `~` annotations. Readiness (item 3) always reads raw `blocked_by`/`depends_on` regardless of `--edges`, because a filtered-out edge does not make an issue ready.

10. **CHANGELOG**: entry under the next concrete version section (not `[Unreleased]`) for the default-layout change, the `hub`→`start` header token, and the new JSON fields.

## Scope Boundaries

- Out of scope: changing `--edges` filter semantics — unchanged per item 9 of Proposed Solution.
- Out of scope: changing `find_issues`/`find_issues_for_graph` — the readiness check only *calls* the existing superset loader.
- Out of scope: `dependency_mapper/formatting.py::format_epic_tree` or any other EPIC-hierarchy rendering path — this issue only touches `scripts/little_loops/cli/issues/clusters.py`.
- Out of scope: making `tree` wave-rooted by default. `waves` becomes the new default layout (Open Questions recommendation); `tree` keeps its existing hub-root heuristic for pure `parent`/`relates_to` clusters and is re-rooted at wave-1 issues only when ordering edges are present (item 4).
- Out of scope: adding wave/topological-level grouping to other commands (`sprint.py`, `dependency_mapper/`) — confined to `ll-issues clusters`.
- Out of scope: removing or renaming the existing JSON `edges` field — `wave` and `normalized_edges` are additive only.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — `_cluster_edges` (per-category dedup), `_topo_sort_cluster` (replaced by `_order_and_waves`), `_ClusterRenderData`, `_render_cluster_tree`, `_render_cluster_diagram`, `_render_cluster_compact`, `_cluster_header`, `_print_legend`, `cmd_clusters` (JSON branch + layout dispatch + `find_issues_for_graph` superset load)
- `scripts/little_loops/cli/issues/__init__.py` — `--layout` choices and help text (~line 536)
- `CHANGELOG.md` — entry per Proposed Solution item 10

### Dependent Files (Callers/Importers)
- `_draw_box` from `scripts/little_loops/cli/loop/layout.py` (imported by `_render_cluster_diagram`; unchanged)
- Any skill/loop that greps the `hub ENH-NNNN` header token — verify with grep before renaming to `start`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/formatting.py:11,294` — imports `EDGE_COLOR` from `clusters.py` (used as `EDGE_COLOR['blocks']` in epic-tree rendering); `EDGE_COLOR` itself is untouched by this issue, no edit needed here — noted because it confirms `clusters.py` has a real cross-module constant surface [Agent 1 finding]
- `hub ENH-NNNN` token grep confirmed clean: repo-wide search found zero references outside `clusters.py` and `scripts/tests/test_issues_cli.py` — the pre-existing "verify with grep before renaming" caveat above is satisfied [Agent 1 finding]

### Similar Patterns
- `dependency_mapper/formatting.py::format_epic_tree` — the `├──`/`└──` connector idiom the tree renderer already generalizes
- `_topo_sort_cluster` (Kahn's) — base for `_wave_levels`

### Tests
- `scripts/tests/test_issue_parser.py` — existing `cmd_clusters` / `_render_cluster_tree` tests; add cases listed under `## Tests`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:4824-4827` — `TestPriorityRegexCompletenessAllowlist._ALLOWLIST["cli/issues/clusters.py"][68]` pins `_PRIORITY_TAG_RE` at clusters.py:68 by exact line number; inserting new top-level code (e.g. `_normalize_edges`/`_wave_levels` constants) above line 68 breaks this gate — bump the allowlist's line-number key in the same commit [confirmed live, enforced test — not a comment]
- `scripts/tests/test_issues_cli.py:6112-6132` — `test_enriched_header_shows_hub_spread_and_edges` (inside `TestIssuesCLIClustersScoping`, distinct from the already-catalogued `TestIssuesCLIClustersLegendAndHeader`) pins the literal substring `"Cluster 1 (3 issues) · hub BUG-002 · P0×1 P1×1 P2×1 · 2 edges"` — breaks verbatim on the `hub`→`start` rename; update alongside the `TestIssuesCLIClustersLegendAndHeader` cases already listed under `## Tests` [Agent 3 finding]
- `_wave_levels` test precedent: `LayerAssigner.assign()` (`scripts/little_loops/cli/loop/layout.py:577-669`) is the closest existing longest-path-depth-over-topo-order implementation but has no direct unit tests anywhere — it's exercised only indirectly via full-diagram string assertions in `test_ll_loop_display.py` (`test_diamond_pattern`, `test_fan_in_three_paths`) that never assert numeric depth values; a depth-asserting `_wave_levels` test has no existing precedent to model that assertion style on [Agent 3 finding]
- `DependencyGraph.get_execution_waves()` tests (`scripts/tests/test_dependency_graph.py:684-859`, class `TestGetExecutionWaves`) are BFS-round rather than longest-path-depth, but their assertion idiom is directly reusable: list-equality for singleton waves, set-equality for same-wave siblings (`test_diamond_three_waves`, :718), nested-list-equality for a full wave sequence (`test_depends_on_enforces_wave_ordering`, :802), `pytest.raises(ValueError, match="cycles")` for cycles (:752) — model `_wave_levels` tests on this idiom [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` § `ll-issues clusters` — flag table, examples, default-layout prose

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4605` — the `ll-issues` sub-command table's `clusters` row lists only `--include-orphans`, `--min-connections N`, `--json`, `--edges SET`, `--status SET` (already missing `--layout`/`--cluster`/`--limit`/`--compact` before this issue); add `--layout {waves,tree,list,boxes}` and the new default so this row doesn't diverge further [Agent 2 finding]

### Configuration
- N/A

### Behavior Parity

_Added 2026-09-09 pre-implementation review; covers every behavior of the code being replaced or re-rooted:_

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `clusters.py::_topo_sort_cluster` | Kahn topo order over raw `issue.blocked_by` only, ignoring `blocks`/`depends_on`/`--edges` | CHANGED | `_order_and_waves` orders over the normalized, `--edges`-filtered edge list. A `blocks`-only declaration now orders; `--edges=relates_to` now yields no ordering (was: still ordered by `blocked_by`). Deliberate; the old behavior was the "topo-sorts correctly" illusion. |
| `clusters.py::_topo_sort_cluster` | Cycle members appended in sorted-ID order after the acyclic prefix; `has_cycle=True` | PRESERVED | Same in `_order_and_waves`; the bucket is labelled `unresolved` in `waves` output because downstream-of-cycle nodes share it. |
| `clusters.py::_cluster_edges` | One edge per unordered pair, `blocked_by > blocks > parent > depends_on > relates_to` | CHANGED | One ordering edge + one annotation edge per pair. `parent`+`depends_on` no longer loses the ordering fact; 2-cycles survive. JSON `edges` may carry two entries per pair. |
| `clusters.py::_render_cluster_tree` | Hub root (max degree, topo tie-break) for every cluster | PRESERVED for pure `parent`/`relates_to` clusters, CHANGED otherwise | Gate is `has_ordering_edges`; FEAT-2337's EPIC-hierarchy case keeps the exact existing rendering and is covered by a regression test. |
| `clusters.py::_render_cluster_tree` | Every edge appears once, as branch or `⤷` cross-ref; nothing demoted to a trailing list | PRESERVED | Re-rooted walk keeps the "every edge rendered" invariant; `~` replaces `→`/`←` for annotation edges. |
| `clusters.py::_render_cluster_diagram` | `▲` for edges pointing against the stack; `relates_to` in arrow slots; skip edges in a trailing text list | CHANGED | All `▼`/`needs`; annotations never in arrow slots; skip edges moved into the box as `unblocks:`. |
| `clusters.py::_cluster_header` | `hub ENH-NNNN` token for every multi-issue cluster | PRESERVED for pure annotation clusters, CHANGED otherwise | `start ENH-NNNN` / `N start` + `M waves` when ordering edges exist. Pinned test strings at `test_issues_cli.py:6132` and `TestIssuesCLIClustersLegendAndHeader` updated. |
| `clusters.py::_print_legend` | One line per present relationship type with source/target prose | CHANGED | Three-entry legend (`needs`, `prefers`, `~`); only entries present in the output are printed (same suppression rule). |
| `cmd_clusters` default layout | `tree` | CHANGED | `waves`; `--compact` → `list` alias preserved; explicit `--layout` still wins over `--compact`. |
| `cmd_clusters` JSON branch | `cluster_index`, `issue_count`, `issues[{id,priority,title}]`, `edges[{from,to,relationship}]`; identical across `--layout` values | PRESERVED (additive) | New `wave`, `ready`, `normalized_edges`; cross-layout equality kept. |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `_cluster_edges(cluster_ids: set[str], issues: list[IssueInfo], edge_types: set[str]) -> list[tuple[str, str, str]]` (`clusters.py:393-440`) returns `(from_id, to_id, relationship)` in frontmatter/semantic direction, already deduplicated per unordered pair via `_EDGE_PRIORITY` (`clusters.py:59-65`, `blocked_by=0 > blocks=1 > parent=2 > depends_on=3 > relates_to=4`) — this is the exact input `_normalize_edges` consumes.
- `_topo_sort_cluster(cluster_ids: list[str], blocked_by: dict[str, set[str]]) -> tuple[list[str], bool]` (`clusters.py:356-390`) is Kahn's algorithm scoped to `blocked_by` only; it returns only the flat order and `has_cycle` — no in-degree/level state is retained after the call, so `_wave_levels` must duplicate the `in_degree`/`adj` construction rather than reuse partial state from this function.
- `_ClusterRenderData` (`clusters.py:72-88`) currently has exactly 5 fields — `index: int, ids: list[str], ordered_ids: list[str], edges: list[tuple[str,str,str]], has_cycle: bool` — no `waves`/`normalized_edges` fields exist yet.
- Two independent "hub" computations exist today, not one: `_cluster_header`'s hub token (`clusters.py:131`, keyed off the full-graph `neighbours` map) and `_render_cluster_tree`'s root selection (`clusters.py:254`, keyed off the cluster-scoped `adj` map built at `clusters.py:199-206` from every edge in `cd.edges` regardless of relationship type). Both compute a hub independently and both need updating for `start`/wave-root behavior — updating one without the other leaves the header and the tree body disagreeing on the starting issue.
- The JSON branch in `cmd_clusters` (`clusters.py:600-622`) never calls `_topo_sort_cluster` today — topo order and `has_cycle` are computed only in the text-rendering path (`clusters.py:648`). Adding a `wave` field to JSON output requires wiring a new call into the JSON branch, not extending an existing computation already available there.
- `LayerAssigner.assign()` (`scripts/little_loops/cli/loop/layout.py:577-669`) is an existing longest-path-depth-over-Kahn's-topo-order helper operating on the same `(src, dst, label)` edge-tuple shape `_cluster_edges` produces. This narrows the Motivation section's "no wave helper anywhere in the package to reuse" claim for the longest-path-depth algorithm specifically — and `clusters.py` already has a documented precedent for importing a private primitive across this same module boundary (`_draw_box`, `clusters.py:455-457`, with an existing comment noting the cross-module import is intentional).
- `DependencyGraph.get_execution_waves()` (`scripts/little_loops/dependency_graph.py:210-269`) is a separate existing "wave" helper (BFS ready-set rounds, not longest-path depth), called directly by `cli/sprint/show.py`, `run.py`, and `manage.py` (`cli/sprint/_helpers.py::_render_execution_plan` renders the resulting waves but does not call `get_execution_waves()` itself). It models only `blocked_by`/`blocks`/`depends_on` (no `relates_to`/`parent`) and raises `ValueError` on any cycle (`dependency_graph.py:264-267`) rather than falling back the way `_topo_sort_cluster` does — not a drop-in for `_wave_levels`, but its existence further narrows the "no wave helper anywhere" claim.
- Every `choices=[...]`-backed enum-style CLI flag in `scripts/little_loops/cli/` (`clusters.py`'s own existing `list`/`boxes`/tree-default dispatch at `clusters.py:674-680`, plus `history.py`, `link_epics.py`) dispatches via an `if`/`elif` chain in the handler body — no `dict[str, Callable]` dispatch-table convention exists anywhere in this package for this kind of flag.
- Test coverage for `cmd_clusters`/renderers actually lives in `scripts/tests/test_issues_cli.py` (classes `TestIssuesCLIClusters` at :4769, `TestIssuesCLIClustersTreeLayout` at :5348, `TestIssuesCLIClustersLegendAndHeader` at :5681, `TestIssuesCLIClustersScoping` at :5942) — not `scripts/tests/test_issue_parser.py` as currently cited in this section and in `## Tests` below.

## Program Design

### Types

- Normalized ordering edge: `tuple[before: str, after: str, strength: Literal["hard", "weak"]]` — `hard` for `blocked_by`/`blocks`, `weak` for `depends_on`
- Wave map: `dict[str, int | None]` — issue ID to 1-indexed wave number; `None` for the unresolved bucket
- `_ClusterRenderData` gains `waves: dict[str, int | None]`, `normalized_edges: list[tuple[str, str, str]]`, `ready: set[str]`, `stale_blocked: set[str]`, `has_ordering_edges: bool`

### Signatures

- `_cluster_edges(cluster_ids, issues, edge_types) -> list[tuple[str, str, str]]` — signature unchanged; dedup becomes per-category (one ordering + one annotation edge per pair)
- `_normalize_edges(edges: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]` — `(before, after, strength)`; input is the per-category-deduped list so both directions of a 2-cycle survive
- `_order_and_waves(ids: list[str], normalized: list[tuple[str, str, str]]) -> tuple[list[str], dict[str, int | None], bool]` — `(ordered_ids, waves, has_cycle)`; single Kahn pass, longest-path depth; replaces `_topo_sort_cluster`
- `_ready_ids(ids: list[str], issues_map: dict[str, IssueInfo], non_terminal_ids: set[str]) -> tuple[set[str], set[str]]` — `(ready, stale_blocked)`; reads raw `blocked_by`/`depends_on`, ignores `--edges`
- `_render_cluster_waves(cd: _ClusterRenderData, issues_map: dict[str, IssueInfo]) -> list[str]`

### Call Path

`cmd_clusters` -> `find_issues` (display set) + `find_issues_for_graph` (readiness superset) -> `_cluster_edges` -> `_normalize_edges` -> `_order_and_waves` -> `_ready_ids` -> `_render_cluster_waves` | re-rooted `_render_cluster_tree` | reworked `_render_cluster_diagram` | `_render_cluster_compact`. The JSON branch runs the same chain through `_ready_ids`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Existing `_cluster_edges(cluster_ids: set[str], issues: list[IssueInfo], edge_types: set[str]) -> list[tuple[str, str, str]]` (`clusters.py:393-440`) is the exact input `_normalize_edges` consumes — a flat `(from_id, to_id, relationship)` list, already deduplicated per unordered pair.
- Existing `_topo_sort_cluster(cluster_ids: list[str], blocked_by: dict[str, set[str]]) -> tuple[list[str], bool]` (`clusters.py:356-390`) is Kahn's algorithm scoped to `blocked_by` only; returns a flat order plus `has_cycle`, with no level/round state retained — `_wave_levels` needs its own `in_degree`/`adj` construction.
- Existing `_ClusterRenderData` (`clusters.py:72-88`): `index: int, ids: list[str], ordered_ids: list[str], edges: list[tuple[str, str, str]], has_cycle: bool` — the dataclass `waves: dict[str, int]` and `normalized_edges: list[tuple[str, str, str]]` extend.
- Precedent for the longest-path-depth-over-topo-order algorithm itself: `LayerAssigner.assign()` (`scripts/little_loops/cli/loop/layout.py:577-669`), operating on the same `(src, dst, label)` edge-tuple shape as `_cluster_edges` — computes `layer_of[node] = max((layer_of.get(p, 0) + 1 for p in reverse[node]), default=0)` over a Kahn topo order, the same recurrence `_wave_levels` needs.
- `_cluster_header`'s hub (`clusters.py:131`, full-graph `neighbours` map) and `_render_cluster_tree`'s root selection (`clusters.py:254`, cluster-scoped `adj` map) are two independent computations today — both are on the call path for the `start`/wave-root behavior, not just the tree renderer.

## Implementation Steps

1. Change `_cluster_edges` dedup to per-category (one ordering edge + one annotation edge per unordered pair; ordering priority `blocked_by` > `blocks` > `depends_on`, annotation priority `parent` > `relates_to`). Existing tests asserting a single edge per pair for a `parent`+`depends_on` pair will need updating.
2. Add `_normalize_edges` and `_order_and_waves` next to `_topo_sort_cluster`; retire `_topo_sort_cluster` (or reduce to a wrapper). Extend `_ClusterRenderData` per Program Design.
3. Add `_ready_ids`; in `cmd_clusters` load the readiness superset with `find_issues_for_graph(config)` once, build `non_terminal_ids`, and pass it through. Wire the same into the JSON branch (`clusters.py:600-622`), which today never computes order or cycles.
4. Add `_render_cluster_waves`; register `waves` in the `--layout` choices in `scripts/little_loops/cli/issues/__init__.py` (~line 536), make it the default in the dispatch in `cmd_clusters` (`clusters.py:633-635`), and keep `--compact` → `list`.
5. Change root selection and edge walk in `_render_cluster_tree` per the three-case rule (no ordering edges → hub; only ordering → wave-1 roots; mixed → `parent` branches to wave-1 children only).
6. Update `_render_cluster_diagram` arrow/label logic and skip-edge placement.
7. Update `_cluster_header` (`start`/`N start`/`hub` rule, wave count) and `_print_legend`; both hub sites switch on `has_ordering_edges`.
8. Extend JSON branch with `wave`, `ready`, `normalized_edges`.
9. Update `docs/reference/CLI.md` § `ll-issues clusters` (flag table, examples, default-layout prose, `hard`-alias vs `weak`-strength note) and the `--layout` help string.
10. Add `CHANGELOG.md` entry.
11. Tests (see below).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/API.md:4605` — add `--layout {waves,tree,list,boxes}` to the `clusters` row of the `ll-issues` sub-command table alongside the `docs/reference/CLI.md` update in step 7
- Update `scripts/tests/test_issue_parser.py:4824-4827` — bump the `_ALLOWLIST["cli/issues/clusters.py"]` line-number key if new top-level code (e.g. `_normalize_edges`/`_wave_levels` module-level definitions) lands above the current `_PRIORITY_TAG_RE` at line 68
- Update `scripts/tests/test_issues_cli.py:6112-6132` — `test_enriched_header_shows_hub_spread_and_edges` pins the literal `hub BUG-002` header substring; update it alongside the `TestIssuesCLIClustersLegendAndHeader` cases for the `hub`→`start` rename

## Impact

- **Priority**: P3 - Usability defect in a planning tool; no data or automation is wrong, but the primary use case (ordering) is currently unanswerable from the output.
- **Effort**: Medium - Normalization, a single order+waves pass, a readiness helper, one new renderer, three renderers and the header/legend/JSON adjusted, plus the `_cluster_edges` dedup change; all contained in `clusters.py` plus argparse, docs, CHANGELOG.
- **Risk**: Low-Medium - Rendering plus one data-shape change: the per-category dedup can emit two `edges` entries for one pair, and the topo order now honours `blocks`/`depends_on`/`--edges` (previously `blocked_by`-only), so existing order-sensitive tests may shift. JSON additions are additive.
- **Breaking Change**: No (JSON `edges` shape unchanged; header text and default layout change are cosmetic; CHANGELOG entry required per Proposed Solution item 10)

## API/Interface

- `ll-issues clusters --layout {waves,tree,list,boxes}`: new `waves` value; default changes from `tree` to `waves`; `tree` is re-rooted at wave-1 issues when ordering edges exist. `--compact` alias unchanged.
- JSON output: additive fields `issues[].wave` (int or `null`), `issues[].ready` (bool), and `normalized_edges` (`{before, after, strength: "hard"|"weak"}`). Existing `edges` array keeps its shape but may now hold two entries for one pair (one ordering, one annotation) — consumers that assumed one-edge-per-pair should be checked (none found in-repo).
- Header line format changes (`hub` → `start ENH-NNNN` / `N start` + wave count) only for clusters with ordering edges; `hub` is retained for pure `parent`/`relates_to` clusters. Repo-wide grep for `hub ` confirmed clean outside `clusters.py` and its tests.
- One additional issue-directory scan per invocation (`find_issues_for_graph`) for readiness; negligible for `.issues/` sizes in practice.

## Tests

Existing coverage lives in `scripts/tests/test_issue_parser.py` (`cmd_clusters` / `_render_cluster_tree` tests). Add:

- `_cluster_edges` dedup: a pair with `parent` + `depends_on` yields two edges (one ordering, one annotation); a pair with `blocked_by` + `parent` yields both; `A blocked_by B` + `A blocks B` yields one ordering edge (`blocked_by` wins); `A blocked_by B` + `B blocked_by A` yields both directions.
- `_normalize_edges`: `blocked_by`, `blocks`, `depends_on` all collapse to the same `(before, after)`; `relates_to`/`parent` are excluded; strength is `hard` for the first two and `weak` for `depends_on`.
- `_order_and_waves`: the 5-issue example above yields waves `{3427:1, 3428:2, 3429:2, 3430:2, 3422:3}` and `ordered_ids` consistent with those waves; diamond DAG gives longest-path depth (not BFS depth); an issue that only declares `blocks: [X]` (no reciprocal) still orders before X; a `depends_on`-only chain still produces waves; 2-cycle members land in the unresolved bucket with `wave=None`, a node downstream of the cycle also lands there, and `has_cycle` stays true; `--edges=relates_to` yields all wave 1 and `has_ordering_edges=False`.
- `_ready_ids`: wave-1 issue with a `deferred` blocker is not `ready` and gets the `⏳ waits on` suffix; wave-1 issue whose blocker is `done` (absent from superset) is `ready`; wave-1 issue with a dangling blocker ID is `ready`; `status: blocked` issue with only terminal blockers lands in `stale_blocked`; readiness ignores `--edges=blocking` for a `depends_on` blocker.
- `waves` layout snapshot for the example; wave-1 issues render before everything else; every non-wave-1 line carries `needs`; no wave header contains "(after"; parallel issues in one wave never get an arrow between them; unresolved bucket renders last with the existing cycle warning.
- `tree` layout: root is a wave-1 issue, not the hub; hub-root heuristic still applies to a pure `parent`-edge EPIC cluster (regression for FEAT-2337); mixed cluster (EPIC + `parent` children + child-to-child `blocked_by`) renders EPIC as root, wave-1 children as branches, blocked children under their blockers, and `⤷ ~ parent` on non-wave-1 children.
- `boxes`: no `▲` glyph appears with normalized edges; `relates_to` never occupies an arrow slot.
- JSON: `wave` and `ready` present on every issue (`wave: null` for unresolved); `normalized_edges` matches `_normalize_edges`; `edges` unchanged in shape; cross-layout equality at `test_issues_cli.py:5613` still holds.
- Header/legend: `start ENH-NNNN` with one wave-1 issue, `N start` with several, wave count present; `hub` absent when ordering edges exist and present (matching the tree root) when none do.
- Allowlist gate: `_PRIORITY_TAG_RE` line key in `test_issue_parser.py:4824-4827` bumped if any top-level constant is added above line 68.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Existing cluster/renderer coverage lives in `scripts/tests/test_issues_cli.py`, not `test_issue_parser.py` as previously cited: `TestIssuesCLIClusters` (:4769), `TestIssuesCLIClustersTreeLayout` (:5348), `TestIssuesCLIClustersLegendAndHeader` (:5681), `TestIssuesCLIClustersScoping` (:5942).
- Every existing cluster test invokes the CLI entry point (`main_issues()` with patched `sys.argv`) and asserts via substring/line-filtering, e.g. `assert "├── " in out or "└── " in out`, `skip_lines = [ln for ln in out.splitlines() if ...]`. No full-string/snapshot-style assertion (`captured.out == """..."""`) exists anywhere in `scripts/tests/` for renderer output today — a `waves`-layout snapshot test would be the first of its kind in this file.
- No shared cluster-fixture builder exists; each test class hand-writes its own markdown fixture function via `Path.write_text(...)` (e.g. `issues_dir_with_deps` at :4730, `issues_dir_multi_root` at :4703, `issues_dir_with_soft_edges` at :5616, `issues_dir_with_cycle` at :5662).
- JSON-output equality across `--layout` values is already asserted today (`_json([]) == _json(["--layout", "boxes"]) == _json(["--layout", "tree"])`, :5613) — new `wave`/`normalized_edges` JSON fields need this same cross-layout-stability property preserved.

## Open Questions

_Resolved 2026-09-09 during pre-implementation review; decisions folded into Proposed Solution:_

- Default layout → `waves` is the new default; `tree` is also re-rooted (item 5).
- `relates_to` as intra-wave tiebreaker → yes, never wave-creating (item 4).
- Stale `status: blocked` flag → yes, driven by the same readiness superset (item 3).
- Soft edges in wave computation → yes, `depends_on` orders and participates in cycle detection; the strength tag is `weak` to avoid colliding with the existing `--edges=hard` alias (items 1, 2).
- Mixed `parent` + ordering clusters in `tree` → `parent` branches to wave-1 children only (item 5).
- Multi-root header → `N start` (item 7); wave headers drop "(after X)" in favour of always-on per-line `needs` (item 4).

No open questions remain.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CLI.md` § `ll-issues clusters` | Flag table, layout semantics, and examples that must be updated with the new default and `waves` layout |

## Verification Notes

_Added by `/ll:verify-issues --auto` — 2026-09-09:_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

- All core code claims verified accurate against HEAD: `_cluster_edges` (clusters.py:393-440), `_topo_sort_cluster` (356-390), `_ClusterRenderData` (72-88), the hub root-selection tie-break at `_render_cluster_tree` (line 254, confirmed `min(unvisited, key=lambda x: (-len(adj[x]), order_index[x]))`), the un-filtered `adj` build from all edge types (199-206), `_PRIORITY_TAG_RE` at line 68 (matches the allowlist test's pinned key), the `EDGE_COLOR` import in `dependency_mapper/formatting.py:11,294`, and all four cited test class locations plus the pinned `hub BUG-002` string in `test_issues_cli.py:6132` all match verbatim.
- `ll-verify-evidence` flagged the backtick-quoted `(-degree, topo_index)` in the Motivation section as an unverifiable span (not a verbatim match for the real sort key `(-len(adj[x]), order_index[x])`). The description was semantically accurate but styled as a code quote it wasn't; reworded to prose. Re-run confirms clean (`ok: true`).
- `LayerAssigner.assign()` was cited with two different, both-imprecise line ranges (`577-681` and `577-654`); the class spans `577-669` and `assign()` itself is `594-669`. Corrected all three citations to `577-669`. The quoted recurrence snippet itself (`layer_of[node] = max(...)`) was already verbatim-accurate.
- `DependencyGraph.get_execution_waves()` was described as "consumed by `cli/sprint/_helpers.py`"; the actual callers are `cli/sprint/show.py`, `run.py`, and `manage.py` — `_helpers.py::_render_execution_plan` only renders the waves it's handed. Corrected.
- Motivation's flat claim "no wave helper anywhere in the package to reuse ... have none" contradicted the issue's own later Codebase Research Findings (which found `LayerAssigner.assign()` and `DependencyGraph.get_execution_waves()`, and explicitly said they "narrow" that claim). Softened the Motivation line to match what the research findings already concluded.
- Proposal-vs-code check (B6): no exception-handler or test-fixture incompatibilities found — this is pure in-process rendering/data-transform code with no I/O, and the Tests section already specifies a FEAT-2337 regression case for the hub-heuristic carve-out.
- Decisions log: no active required rules. No dependency-reference sections (`Blocked By`/`Blocks`) present to validate.

## Status

**Open** | Created: 2026-09-09 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-10T00:27:31 - `5b36b229-aecd-464e-a51e-d8fefd4480a0.jsonl`
- `/ll:verify-issues` - 2026-09-09T23:38:11 - `8a31ffc6-a676-4cb1-9565-9ce146e62087.jsonl`
- `/ll:wire-issue` - 2026-09-09T23:27:24 - `5d95d69e-346f-4853-a030-ad0adc7a6174.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:16:43 - `73a6f102-4f3f-4672-b41c-d8529550109f.jsonl`
- `/ll:format-issue` - 2026-09-09T23:07:00 - `14c7b756-a099-48f6-aa72-1ec8cb09fa11.jsonl`
- `/ll:capture-issue` - 2026-09-09T23:02:32 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
