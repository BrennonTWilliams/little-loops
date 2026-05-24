---
captured_at: '2026-05-23T22:59:14Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

- **Active `depends_on` pairs** (4): ENH-1617→ENH-1618, ENH-1658→BUG-1628, ENH-1631→BUG-1628, FEAT-1475→FEAT-1478
- **EPIC-1622 family** (5): FEAT-1475/1476/1478/1479/1480 share `parent: EPIC-1622`
- **Deferred clusters**: frontend/UI (~13 issues), FEAT-1156 chain, FEAT-1315 chain, FEAT-1232 cluster

## Expected Behavior

Default invocation walks **all relationship types across active status** (`open`/`in_progress`/`blocked`) and reports ~10+ clusters. Flags retain access to the old narrow view and to deferred work:

- `--edges=all` (new default), `--edges=blocking` (today's behaviour), `--edges=hard` (`blocked_by`+`blocks`+`depends_on`)
- `--status=active` (new default), `--status=all`, `--status=+deferred`

## Root Cause

Three independent narrowings compose:

1. **Edge filter** — `scripts/little_loops/cli/issues/clusters.py:30` `_get_connected_components()` walks only `graph.blocked_by ∪ graph.blocks` (neighbor expression at line 49-51). The four active `depends_on` pairs are invisible. The single visible cluster is ENH-977 blocked_by ENH-494.

2. **Status filter** — `scripts/little_loops/issue_parser.py:831` `find_issues()` unconditionally drops `done`/`cancelled`/`deferred` at lines 871-872. Every deferred cluster (verified: ENH-1073, FEAT-1156 both `status: deferred`) is excluded before the graph is built.

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

3. **Status-scoped issue loading** — `find_issues()` (`scripts/little_loops/issue_parser.py:831`) gains optional `status_filter: set[str] | None = None`. When `None`, current behaviour preserved. `cmd_clusters` passes the resolved status set explicitly.

4. **Renderer updates** — `scripts/little_loops/cli/issues/clusters.py`:
   - `EDGE_COLOR` (line 17-22): add `depends_on` → `35` (magenta), `relates_to` → `37` (white/dim); `parent` and `sibling` entries already exist in `EDGE_COLOR` — keep them unchanged.
   - `_cluster_edges` (line 97-104): emit directed edges for every in-scope relationship type. Tuples become `(from_id, to_id, relationship)` where relationship is the canonical type recorded during graph construction.
   - `_topo_sort_cluster` (line 60-94): keep using `blocked_by` only for ordering — non-blocker edges have no DAG meaning. Cycles in soft edges must not trigger the "cycle detected" warning.
   - `_max_degree()` closure inside `cmd_clusters()`: also uses only `graph.blocked_by + graph.blocks`. Update it in parallel with the neighbour-map change so `--min-connections` filtering is consistent with the new edge set.

5. **JSON output schema** — `--json` output (clusters.py:229-249) already emits `edges` with a `relationship` field. Existing consumers will start seeing new relationship types (`depends_on`, `relates_to`, `parent`). Document in command-help epilog; no schema break.

6. **Documentation updates** _(added by `/ll:wire-issue`)_ — Update `docs/reference/API.md` (find_issues signature at line 736; clusters subcommand flag table at line 3062) and add a dedicated `ll-issues clusters` subsection to `docs/reference/CLI.md` covering `--edges` and `--status` with their aliases. Use canonical status vocabulary only to avoid breaking `test_enh1428_doc_wiring.py`.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — `IssueManager.__init__()` calls `find_issues(self.config, self.category)` to seed the dependency graph; used by `ll-auto` and `ll-parallel`. **Safety**: if `find_issues` default behavior ever changed to include deferred issues, this would corrupt the dep_graph and break scheduling — the `status_filter=None` default must continue excluding deferred.
- `scripts/little_loops/parallel/priority_queue.py` — `IssuePriorityQueue.scan_issues()` calls `find_issues(config, category=..., skip_ids=..., only_ids=..., type_prefixes=...)` — verify unchanged under `status_filter=None` default.
- `scripts/little_loops/cli/deps.py` — `cmd_deps()` calls `find_issues(config, only_ids=only_ids)` and `gather_all_issue_ids()` — safe, no status logic.
- `scripts/little_loops/issue_parser.py:find_highest_priority_issue` — internal wrapper that calls `find_issues()`; any callers of this function inherit the same default-path behaviour.
- `scripts/little_loops/cli/issues/next_action.py`, `next_issue.py`, `next_issues.py`, `impact_effort.py`, `refine_status.py`, `sequence.py`, `search.py` — all call `find_issues()` without `status_filter`; all safe under `status_filter=None` default.

### Similar Patterns
- The clusters command's prior `_get_connected_components` and `_cluster_edges` helpers — the new neighbour-map builder replaces them but should match their BFS shape and undirected-edge output.
- `dependency_mapper.analysis` — also walks issue relationships but for a different purpose (waves/ready queries); ensure the new clusters builder does not converge on its DAG semantics.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Canonical BFS-on-adjacency-dict pattern**: `scripts/little_loops/issue_history/coupling.py:_build_coupling_clusters()` — builds `adjacency: dict[str, set[str]]` directly from data objects (no intermediate graph class), adds both directions per edge for undirected traversal, then runs the same BFS loop shape used in `_get_connected_components()`. This is the closest structural analogue in the codebase and should be the model for the new neighbour-map builder.
- **`--status` flag registration pattern**: `scripts/little_loops/cli/issues/__init__.py` lines 126-131, 205-212, and 278-284 — three existing subcommands (`list`, `search`, `count`) use identical `add_argument("--status", "-S", choices=[...], default="open")` blocks. The clusters subparser `cl` is at lines 320-342; insert the new `--edges`/`--status` arguments after `--min-connections` following this pattern.
- **`find_issues()` exact current signature** (`issue_parser.py:831-837`): `find_issues(config, category=None, skip_ids=None, only_ids=None, type_prefixes=None)`. Add `status_filter: set[str] | None = None` after `type_prefixes`; guard the existing skip at line 872 with `if status_filter is None or info.status in status_filter`.
- **`depends_on_edges` is one-directional in `DependencyGraph`**: even if BFS were patched to consult `depends_on_edges`, targets would not find their sources. This validates the decision to build a fresh neighbour map from `IssueInfo` fields directly.
- **`gather_all_issue_ids()`** — `scripts/little_loops/dependency_mapper/operations.py`: used by `cmd_clusters()` to populate `all_known_ids` before the graph build. Keep this call; pass the resolved ID set into the new neighbour-map builder the same way it's passed to `DependencyGraph.from_issues()` today.

### Tests
- `scripts/tests/test_issues_cli.py:TestIssuesCLIClusters` (line 3514) — existing test class to extend; uses fixture `issues_dir_with_deps` (line 3474) for blocked_by/blocks setup. Add a parallel fixture for `depends_on`/`relates_to`/`parent` edges using either frontmatter YAML or Markdown section format.
- New cluster tests to add: `depends_on` edges under `--edges=all`; `relates_to`+`parent` edges under `--edges=all`; `--edges=blocking` regression guard reproducing the current single 2-issue cluster; `--status=+deferred` surfacing deferred issues; JSON output emitting `depends_on`/`relates_to`/`parent` as valid `relationship` values. Model each test after `test_clusters_min_connections_filter` (line 3762) — patches `sys.argv` with `["ll-issues", "clusters", "--flag", "--json", "--config", str(dir)]`, runs `main_issues()`, parses stdout JSON.
- `scripts/tests/test_dependency_graph.py` — regression check that all existing `find_issues()` callers without `status_filter` see identical behaviour; `make_issue()` helper in this file is reusable for building test `IssueInfo` instances.
- `scripts/tests/test_issue_parser.py` — add parametrized tests for new `status_filter` parameter variations on `find_issues()`.

_Wiring pass added by `/ll:wire-issue`:_
- New fixture `issues_dir_with_soft_edges` — parallel to `issues_dir_with_deps` (line 3474); use frontmatter `depends_on`/`relates_to`/`parent` fields (not `## Blocks` sections); must create `completed/` and `deferred/` subdirs like the existing fixtures.
- New test methods to write in `TestIssuesCLIClusters`: `test_clusters_depends_on_edges_under_default`, `test_clusters_relates_to_and_parent_edges`, `test_clusters_edges_blocking_regression` (`--edges=blocking` reproduces old single-cluster), `test_clusters_status_plus_deferred`, `test_clusters_json_new_relationship_types`.
- `make_issue()` helper in `test_dependency_graph.py` (line 14) — currently accepts `blocked_by`, `blocks`, `depends_on` but **not** `relates_to` or `parent`. Extend its signature with `relates_to: list[str] | None = None, parent: str | None = None` so regression tests for the new neighbour-map builder can use it.
- **Monitor for breakage**: `test_clusters_with_dependency_links` (line 3679) asserts `"Cluster 2"` and `"3 issues"` — safe only if `issues_dir_with_deps` fixture stays pure hard-edge (no `depends_on` frontmatter); `test_clusters_min_connections_filter` (line 3762) — safe only if `_max_degree` update remains consistent with existing fixture topology.
- `scripts/tests/test_issue_parser.py:TestFindIssues.test_find_issues_skips_status_deferred` (line 1106) — asserts deferred is excluded from default `find_issues()` output; **must remain passing** — the `status_filter=None` default must preserve this exclusion.

### Documentation
- `ll-issues clusters --help` epilog (in `scripts/little_loops/cli/issues/__init__.py`) — document new `--edges` and `--status` flags, default change, and the `--edges=blocking` alias for legacy behaviour.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` line 736 — `find_issues()` signature is already diverged (`only_ids: set[str] | None` vs actual `list[str] | set[str] | None`); add `status_filter: set[str] | None = None` parameter to the documented signature.
- `docs/reference/API.md` line 3062 — `clusters` row in the `ll-issues` subcommands table documents only `--include-orphans`, `--min-connections`, `--json`; add `--edges` and `--status` to this table.
- `docs/reference/CLI.md` — no `ll-issues clusters` dedicated subsection exists (unlike `anchor-sweep`, `check-flag`, etc.). Add a subsection documenting `--edges` and `--status` with their aliases; avoid non-canonical status vocabulary to keep `test_enh1428_doc_wiring.py:TestCliMdStatusVocab` tests passing.

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
- [ ] All four active `depends_on` pairs (ENH-1617→ENH-1618, ENH-1658→BUG-1628, ENH-1631→BUG-1628, FEAT-1475→FEAT-1478) appear in default output
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
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3f102e7-8b1c-40a0-92c7-9fea7bc9a310.jsonl`
- `/ll:wire-issue` - 2026-05-24T07:41:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2345830b-0a2d-4cf9-8ce2-c8909925173d.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:32:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/995aa695-3c58-4826-8afa-21cb7bcdc032.jsonl`
- `/ll:verify-issues` - 2026-05-24T03:55:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86b55377-f187-4e58-9c10-c40043e89408.jsonl`
- `/ll:format-issue` - 2026-05-23T23:06:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11d6a79-dbf6-4df8-88d4-640a18cdec70.jsonl`

- `/ll:capture-issue` - 2026-05-23T22:59:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97f3f20e-c2e8-4f2d-bf70-a8aa3f33ad7b.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
