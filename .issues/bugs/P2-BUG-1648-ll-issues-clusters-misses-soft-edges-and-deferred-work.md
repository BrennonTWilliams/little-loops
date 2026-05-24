---
captured_at: "2026-05-23T22:59:14Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
---

# BUG-1648: `ll-issues clusters` misses soft edges and deferred work, reporting 1 cluster instead of 10+

## Summary

`ll-issues clusters` reports a single 2-issue cluster despite 44 of 91 open issues having dependencies on other open issues, plus several large deferred clusters totalling 20+ inter-linked issues. Three nested narrowings in the clusters pipeline collapse the real relationship graph: (1) the edge walker only follows `blocked_by`/`blocks`, dropping the four active `depends_on` pairs the user enumerated; (2) `find_issues()` hard-drops `done`/`cancelled`/`deferred`, removing every deferred cluster before the graph is built; (3) `DependencyGraph` doesn't model `relates_to` or `parent`, so the EPIC-1622 family and soft links can't surface at all.

## Steps to Reproduce

1. Use a backlog containing `depends_on`, `parent`, and `relates_to` relationships across active issues (e.g., the current repo state: 91 open issues, 44 with cross-issue dependencies, plus EPIC-1622's 5-issue `parent`-linked family and several deferred clusters).
2. Run `ll-issues clusters` with no flags.
3. Observe: output reports exactly one 2-issue cluster (ENH-977 ↔ ENH-494) and lists all other dependent issues as orphans.
4. Confirm hidden relationships exist by cross-checking with `ll-issues show ENH-1617`, `ll-issues show FEAT-1475`, etc. — the `depends_on` and `parent` edges are present in the issue files but never surface in `clusters` output.

## Current Behavior

`ll-issues clusters` prints exactly one cluster of 2 issues (ENH-977 ↔ ENH-494). Hidden:

- **Active `depends_on` pairs** (4): ENH-1617→ENH-1618, ENH-1629→BUG-1628, ENH-1631→BUG-1628, FEAT-1475→FEAT-1478
- **EPIC-1622 family** (5): FEAT-1475/1476/1478/1479/1480 share `parent: EPIC-1622`
- **Deferred clusters**: frontend/UI (~13 issues), FEAT-1156 chain, FEAT-1315 chain, FEAT-1232 cluster

## Expected Behavior

Default invocation walks **all relationship types across active status** (`open`/`in_progress`/`blocked`) and reports ~10+ clusters. Flags retain access to the old narrow view and to deferred work:

- `--edges=all` (new default), `--edges=blocking` (today's behaviour), `--edges=hard` (`blocked_by`+`blocks`+`depends_on`)
- `--status=active` (new default), `--status=all`, `--status=+deferred`

## Root Cause

Three independent narrowings compose:

1. **Edge filter** — `scripts/little_loops/cli/issues/clusters.py:49-51` `_get_connected_components()` walks only `graph.blocked_by ∪ graph.blocks`. The four active `depends_on` pairs are invisible. The single visible cluster is ENH-977 blocked_by ENH-494.

2. **Status filter** — `scripts/little_loops/issue_parser.py:872` `find_issues()` unconditionally drops `done`/`cancelled`/`deferred`. Every deferred cluster (verified: ENH-1073, FEAT-1156 both `status: deferred`) is excluded before the graph is built.

3. **Graph representation gap** — `scripts/little_loops/dependency_graph.py` `DependencyGraph` models `blocked_by`/`blocks`/`depends_on_edges` only. `relates_to` and `parent` are not stored. EPIC-1622's 5-issue family and soft `relates_to` links cannot be surfaced at all.

## Motivation

`ll-issues clusters` is the canonical command for understanding dependency structure across the backlog. Reporting 1 cluster when reality has 10+ produces a wrong-answer diagnostic — users planning sprints or tracing coupling get a false picture and miss real coordination requirements (especially the EPIC-1622 family, where parent-linked work currently looks unrelated).

## Proposed Solution

Keep `DependencyGraph` untouched — it is load-bearing for `ll-auto`, `ll-parallel`, `ll-sprint`, `get_execution_waves`, cycle detection, and `dependency_mapper.analysis`, all of which require strict-blocker DAG semantics. Adding `relates_to`/`parent` neighbours there would corrupt wave ordering and ready-issue queries.

Instead, build the clusters command's graph directly from already-parsed `IssueInfo` records — clusters needs undirected connectivity, not a DAG. This isolates the change to the clusters command and one small helper.

## Implementation Steps

1. **Per-edge-type neighbour map in `clusters.py`** — Replace `_get_connected_components(graph, all_ids)` with a helper built from `IssueInfo`:
   - `neighbours: dict[str, set[str]]` from each issue's `blocked_by`, `blocks`, `depends_on`, `relates_to`, `parent` (filtered to in-scope IDs and active edge-type set).
   - `edge_type: dict[tuple[str, str], str]` recording which relationship produced each undirected edge. When two relationships describe the same pair, prefer in order: `blocked_by` > `blocks` > `parent` > `depends_on` > `relates_to`.
   - BFS over `neighbours` to extract components (same shape as today's `_get_connected_components`).

2. **New CLI flags on the `clusters` subparser** — `scripts/little_loops/cli/issues/__init__.py:321-339`:
   - `--edges <set>` default `all`. Comma list of `blocked_by,blocks,depends_on,relates_to,parent` or aliases `all` / `blocking` (`blocked_by`+`blocks`) / `hard` (`blocked_by`+`blocks`+`depends_on`).
   - `--status <set>` default `active`. Comma list of canonical statuses or aliases `active` (`open`/`in_progress`/`blocked`) / `all` (everything except `cancelled`) / `+deferred`.
   - Existing `--include-orphans`, `--min-connections`, `--json` unchanged.

3. **Status-scoped issue loading** — `find_issues()` (`scripts/little_loops/issue_parser.py:868-897`) gains optional `status_filter: set[str] | None = None`. When `None`, current behaviour preserved. `cmd_clusters` passes the resolved status set explicitly.

4. **Renderer updates** — `scripts/little_loops/cli/issues/clusters.py`:
   - `EDGE_COLOR` (line 17-22): add `depends_on` → `35` (magenta), `relates_to` → `37` (white/dim); keep existing `blocks`/`blocked_by`/`parent`/`sibling`.
   - `_cluster_edges` (line 97-104): emit directed edges for every in-scope relationship type. Tuples become `(from_id, to_id, relationship)` where relationship is the canonical type recorded during graph construction.
   - `_topo_sort_cluster` (line 60-94): keep using `blocked_by` only for ordering — non-blocker edges have no DAG meaning. Cycles in soft edges must not trigger the "cycle detected" warning.

5. **JSON output schema** — `--json` output (clusters.py:229-249) already emits `edges` with a `relationship` field. Existing consumers will start seeing new relationship types (`depends_on`, `relates_to`, `parent`). Document in command-help epilog; no schema break.

## API/Interface

`find_issues(status_filter: set[str] | None = None)` — additive optional parameter, default `None` preserves all existing callers' behaviour.

`ll-issues clusters` gains `--edges` and `--status` flags; default output changes from "blocking-only / active-only" to "all-relationships / active-only". Old narrow view reachable via `--edges=blocking`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — new neighbour-map builder; rework `_get_connected_components`, `_cluster_edges`, `EDGE_COLOR`, `cmd_clusters` body to resolve `--edges`/`--status` args.
- `scripts/little_loops/cli/issues/__init__.py` — add `--edges`/`--status` to the `clusters` subparser; update epilog example block.
- `scripts/little_loops/issue_parser.py` — add optional `status_filter` parameter to `find_issues()`; default `None` preserves current behaviour.

### Dependent Files (Callers/Importers)
- `find_issues()` callers must remain unaffected: `ll-auto`, `ll-parallel`, `ll-sprint`, `get_execution_waves`, `dependency_mapper.analysis`, cycle detection. Verify each uses the default `status_filter=None` path so behaviour is preserved.
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` is intentionally **not** touched; this fix builds the clusters graph directly from `IssueInfo` to avoid corrupting wave ordering and ready-issue queries that depend on strict-blocker DAG semantics.

### Similar Patterns
- The clusters command's prior `_get_connected_components` and `_cluster_edges` helpers — the new neighbour-map builder replaces them but should match their BFS shape and undirected-edge output.
- `dependency_mapper.analysis` — also walks issue relationships but for a different purpose (waves/ready queries); ensure the new clusters builder does not converge on its DAG semantics.

### Tests
- `scripts/tests/` — new cluster tests covering: `depends_on` edges under `--edges=all`; `relates_to`+`parent` edges under `--edges=all`; `--edges=blocking` regression guard reproducing the current single 2-issue cluster; `--status=+deferred` surfacing the frontend/UI cluster; JSON output emitting `depends_on`/`relates_to`/`parent` as valid `relationship` values.
- Regression check that all existing `find_issues()` callers without `status_filter` see identical behaviour.

### Documentation
- `ll-issues clusters --help` epilog (in `scripts/little_loops/cli/issues/__init__.py`) — document new `--edges` and `--status` flags, default change, and the `--edges=blocking` alias for legacy behaviour.

### Configuration
- N/A — no project config changes; flags are CLI-only.

## Verification

```bash
# Default behaviour: expect ~10+ clusters, not 1
ll-issues clusters

# Regression guard: should reproduce today's "1 cluster of 2 issues"
ll-issues clusters --edges=blocking

# Should surface the frontend/UI cluster, FEAT-1156 chain, etc.
ll-issues clusters --status=+deferred

# JSON view to confirm relationship types
ll-issues clusters --json | jq '[.[] | {n: .issue_count, types: [.edges[].relationship] | unique}]'

# Tests
python -m pytest scripts/tests/ -k cluster -v
```

Manual spot-checks against enumerated clusters:

- ENH-1617 ↔ ENH-1618 appears (`depends_on`)
- FEAT-1475 ↔ FEAT-1478 appears (`depends_on`, also share `parent: EPIC-1622`)
- EPIC-1622 family (5 issues) clusters via `parent` edges
- With `--status=+deferred`: frontend/UI cluster (~13 issues), FEAT-1156 chain, FEAT-1315 chain, FEAT-1232 cluster all present

## Acceptance Criteria

- [ ] `ll-issues clusters` (no flags) reports ≥10 clusters on current backlog
- [ ] `ll-issues clusters --edges=blocking` reproduces today's single 2-issue cluster (regression guard)
- [ ] `ll-issues clusters --status=+deferred` surfaces the frontend/UI deferred cluster
- [ ] EPIC-1622 family appears as a cluster via `parent` edges under default flags
- [ ] All four active `depends_on` pairs (ENH-1617→ENH-1618, ENH-1629→BUG-1628, ENH-1631→BUG-1628, FEAT-1475→FEAT-1478) appear in default output
- [ ] `find_issues()` callers without a `status_filter` argument observe identical behaviour to today (no regression in `ll-auto`/`ll-parallel`/`ll-sprint`)
- [ ] JSON output includes `depends_on`, `relates_to`, `parent` as valid `relationship` values
- [ ] Tests in `scripts/tests/` cover each new flag combination

## Impact

- **Priority**: P2 — `ll-issues clusters` is the canonical diagnostic for backlog dependency structure; reporting 1 cluster when reality has 10+ produces wrong-answer planning input. Workaround is to read issue files manually, so it does not block correctness — only erodes trust in the tool.
- **Effort**: Medium — three files touched (`clusters.py`, `cli/issues/__init__.py`, `issue_parser.py`), one additive helper, two new CLI flags, additive optional parameter on `find_issues()`, and a focused test sweep. No new dependencies or architectural changes.
- **Risk**: Low — `DependencyGraph` (the load-bearing DAG used by `ll-auto`/`ll-parallel`/`ll-sprint`/`get_execution_waves`) is intentionally untouched. `find_issues(status_filter=None)` default preserves all current caller behaviour. The clusters output default changes, but the prior view is preserved verbatim via `--edges=blocking`.
- **Breaking Change**: No (behavioural default only) — `ll-issues clusters` with no flags will report more clusters than before. Loop-/script-based JSON consumers will begin seeing additional `relationship` values (`depends_on`, `relates_to`, `parent`), which is additive within the existing schema. Old narrow output reachable via `--edges=blocking`.

## Context

Captured from plan `~/.claude/plans/why-does-our-ll-issues-twinkling-pie.md`. User confirmed the new default should be "all relationship types across active status", with deferred and the old narrow view reachable via flags.

Related (all `done`): BUG-1297 (skip-level edges in rendering + one-sided `blocks:`), BUG-1259 (frontmatter/body merge), BUG-1260 (linear-chain rendering). Those address rendering and parsing correctness within the existing edge set; this issue widens the edge set and status set themselves.

## Labels

`bug`, `ll-issues`, `clusters`, `dependency-graph`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T23:06:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11d6a79-dbf6-4df8-88d4-640a18cdec70.jsonl`

- `/ll:capture-issue` - 2026-05-23T22:59:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97f3f20e-c2e8-4f2d-bf70-a8aa3f33ad7b.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
