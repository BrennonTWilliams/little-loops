---
captured_at: "2026-04-21T21:41:58Z"
completed_at: "2026-04-21T23:04:53Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
status: done
---

# FEAT-1241: ll-issues clusters Subcommand with Box Diagram Visualization

## Summary

Add a `clusters` subcommand to `ll-issues` that renders issue relationship graphs as
CLI box diagrams. Issues connected by blockers, parent/sibling, or other dependency
relationships are grouped into clusters, each rendered using the existing box diagram
system. Clusters are sorted by size (largest first).

## Current Behavior

`ll-issues` has no way to visualize issue relationship clusters. Users can inspect
individual dependency chains via `ll-deps`, but there is no holistic "show me all
connected groups at once" view.

## Expected Behavior

`ll-issues clusters` outputs box diagrams to the CLI, one per cluster. Each diagram
shows issues as nodes with labeled, color-coded edges for relationship type (blocks,
parent, sibling, etc.). Each cluster is preceded by a header label showing its issue
count (e.g., `── Cluster 1 (8 issues) ──`). Clusters are sorted by issue count
descending — the biggest cluster appears first, the smallest (e.g., 2-issue pairs) last.

With `--json`, no diagrams are rendered; instead the full cluster graph is emitted as
structured JSON (one array of cluster objects, each containing issue IDs and edges).

With `--min-connections N`, only clusters where at least one issue has N or more
connections (degree ≥ N) are included in the output.

## Motivation

Issue dependency sprawl grows silently. A clusters view surfaces which issues are
interconnected and how large those webs are, helping teams sequence work, spot
unresolvable blocking chains, and decide which cluster to attack next. The box diagram
format reuses existing rendering infrastructure and stays consistent with the FSM
diagram UX users already know.

## Use Case

A developer runs `ll-issues clusters` before sprint planning. They see three clusters:
one with 8 interconnected features (rendered first), one 4-issue blocker chain, and
several isolated pairs. They immediately identify the large cluster as the sprint's
highest-leverage area and begin sequencing implementation order from the diagram.

## Acceptance Criteria

- [ ] `ll-issues clusters` is a registered subcommand in `scripts/little_loops/cli/issues/__init__.py`
- [ ] Reads issue relationship metadata (blockers, parent/sibling) from issue frontmatter
- [ ] Groups issues into connected components (clusters) via graph traversal
- [ ] Renders each cluster as a box diagram using the existing box diagram system
- [ ] Clusters are output in descending order by issue count (largest first)
- [ ] Each box shows: issue ID, priority, and title (truncated to terminal width)
- [ ] Each edge is labeled with the relationship type (`blocks`, `parent`, `sibling`, etc.)
- [ ] Each edge is color-coded by relationship type using ANSI colors (consistent mapping, e.g. `blocks` = red, `parent` = blue, `sibling` = cyan)
- [ ] Each cluster is preceded by a header line showing its index and issue count (e.g., `── Cluster 1 (8 issues) ──`)
- [ ] 1-issue clusters (orphans) are omitted by default; a `--include-orphans` flag includes them
- [ ] `--min-connections N` filters to only clusters where at least one node has degree ≥ N
- [ ] `--json` suppresses all diagram output and emits a JSON array of cluster objects; each object has `cluster_index`, `issue_count`, `issues` (list of issue IDs + metadata), and `edges` (list of `{from, to, relationship}` objects)
- [ ] Outputs a summary line: `N clusters, M issues total` at the end (suppressed under `--json`)
- [ ] Handles the case where no relationships exist (prints friendly message)

## API/Interface

```python
# scripts/little_loops/cli/issues/clusters.py

def cmd_clusters(config: BRConfig, args: argparse.Namespace) -> int:
    """Render issue relationship clusters as box diagrams.

    Args:
        config: Project configuration (provides issue directories and CLI settings)
        args: Parsed CLI args (include_orphans: bool, min_connections: int, json: bool)

    Returns:
        Exit code (0 = success)
    """
```

```
# CLI usage
ll-issues clusters [--include-orphans] [--min-connections N] [--json]
```

### JSON output schema

```json
[
  {
    "cluster_index": 1,
    "issue_count": 8,
    "issues": [
      {"id": "FEAT-1001", "priority": "P2", "title": "Add auth middleware"}
    ],
    "edges": [
      {"from": "FEAT-1001", "to": "FEAT-1002", "relationship": "blocks"}
    ]
  }
]
```

### Edge color mapping (ANSI)

| Relationship | Color  |
|-------------|--------|
| `blocks`    | Red    |
| `blocked_by`| Yellow |
| `parent`    | Blue   |
| `sibling`   | Cyan   |
| other       | White  |

## Proposed Solution

1. **Graph construction**: Load all active issues, parse frontmatter relationship fields
   (`blocked_by`, `blocks`, `parent`, `sibling`). Build an undirected adjacency graph.
   Reuse or extend `scripts/little_loops/dependency_mapper/analysis.py` for graph
   traversal; `format_text_graph` in `formatting.py` already renders chains, but a
   new renderer is needed for arbitrary cluster graphs.

2. **Cluster extraction**: Run BFS/union-find over the adjacency graph to extract
   connected components. Sort by size descending.

3. **Box diagram rendering**: For each cluster, render a header label (`── Cluster N (K
   issues) ──`), then issues as labeled boxes and relationships as color-coded, labeled
   edges. Use `_draw_box` from `layout.py` as the box primitive; implement a lightweight
   cluster-specific layout in `clusters.py` using **topological column layout**: assign
   each node a column by BFS depth from source nodes (nodes with no blockers = column 0,
   issues they block = column 1, etc.); stack same-depth nodes vertically; draw arrows
   left-to-right between columns. For clusters containing a cycle (detected during BFS),
   fall back to a **vertical stack layout** (all boxes in one column, edge labels as
   right-margin annotations) and emit a `⚠ cycle detected` warning line before the
   diagram. Apply a consistent ANSI color per relationship type at render time via
   `colorize()` from `cli/output.py`; fall back gracefully when the terminal does not
   support color.

4. **JSON mode**: When `--json` is passed, skip all rendering and instead serialize the
   cluster list to stdout as a JSON array following the schema defined in API/Interface.
   Useful for piping into `jq` or downstream tooling.

5. **CLI integration**: Register `clusters` in `main_issues()` in
   `scripts/little_loops/cli/issues/__init__.py` following the same pattern as
   `cmd_sequence`, `cmd_impact_effort`, etc.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`analysis.py` is not the right module for graph traversal**: `dependency_mapper/analysis.py` handles file-path overlap proposals. Use `DependencyGraph.from_issues()` (`dependency_graph.py:52`) instead — it already builds the `blocked_by`/`blocks` adjacency dicts needed for cluster extraction.
- **`blocked_by`/`blocks` are parsed from markdown sections** (`## Blocked By`, `## Blocks`), not YAML frontmatter. They are already in `IssueInfo.blocked_by` and `IssueInfo.blocks` (`issue_parser.py:234-235`) — no changes to `issue_parser.py` needed for v1.
- **`parent`/`sibling` are out of scope for v1**: These fields don't exist in `IssueInfo`. Capture a separate issue to add them (suggested: run `/ll:issue-size-review`). This feature is scoped to `blocked_by`/`blocks` relationships only.
- **Box diagram renderer**: Use `_draw_box(grid, row, col, width, height, content)` at `layout.py:557` as the box primitive (allocates a `list[list[str]]` character grid, draws unicode box characters). Write a lightweight cluster-specific layout in `clusters.py` — do not call `_render_fsm_diagram()` (`layout.py:1439`) or `_render_layered_diagram()` (`layout.py:665`); both are FSM-coupled and accept FSM-typed params. `colorize()` and `terminal_width()` from `cli/output.py` are fully reusable.
- **JSON pattern**: Check `args.json` before text rendering, call `print_json()` from `cli/output.py:102`, return `0` immediately. Matches pattern in `sequence.py:45-61`.
- **`configure_output(config.cli)` is already called** in `main_issues()` before dispatch — subcommand does not need to call it.
- **Heavy imports are deferred**: All imports (`find_issues`, `DependencyGraph`, etc.) go inside the `cmd_clusters` function body, not at module level — matches all other subcommands (`__init__.py:17-30` pattern).

## Implementation Steps

1. Add `blocked_by` / `blocks` / `parent` / `sibling` frontmatter parsing to
   `scripts/little_loops/issue_parser.py` (if not already present)
2. Build adjacency graph + BFS cluster extraction in
   `scripts/little_loops/cli/issues/clusters.py`; apply `--min-connections` filter before
   rendering
3. Implement cluster box diagram renderer (adapting loop layout or building a lightweight
   node-edge box renderer); include cluster header label and ANSI color-coded edges
4. Implement `--json` serialization path (no diagram output, structured JSON to stdout)
5. Register `clusters` subcommand in `__init__.py`
6. Write tests: graph construction, cluster sorting, edge label/color rendering,
   `--min-connections` filtering, `--json` output schema, empty-state

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected step-level details from codebase analysis:_

- **Step 1**: No changes to `issue_parser.py` needed — `IssueInfo.blocked_by` (`issue_parser.py:234`) and `IssueInfo.blocks` (`issue_parser.py:235`) already exist and are populated from `## Blocked By` / `## Blocks` markdown sections via `_parse_section_items()` (`issue_parser.py:572-608`). `parent`/`sibling` fields are out of scope for v1.
- **Step 2**: `DependencyGraph.from_issues(issues)` (`dependency_graph.py:52-110`) builds the full adjacency structure from `IssueInfo.blocked_by` lists. For connected-component extraction, implement BFS over `graph.blocked_by` and `graph.blocks` dicts in `clusters.py` — `DependencyGraph` has no `get_connected_components()` method but the data structures are sufficient.
- **Step 3**: Use `_draw_box(grid, row, col, width, height, content)` (`layout.py:557-657`) as the box primitive. Allocate a `list[list[str]]` character grid, place issue boxes, draw directional arrow characters + `colorize()`d labels between them. Apply ANSI codes from the edge color table using `colorize()` from `cli/output.py:95`.
- **Step 5**: Import `cmd_clusters` lazily inside `main_issues()` at the top block (`__init__.py:17-30`). Add `cl = subs.add_parser("clusters", ...)` + `cl.set_defaults(command="clusters")` after the `impact-effort` subparser (~line 278). Add dispatch `if args.command == "clusters": return cmd_clusters(config, args)` after line ~446.
- **Step 6**: Tests go in `scripts/tests/test_issues_cli.py` as a new class `TestIssuesCLIClusters` — no new file. Pattern: `patch.object(sys, 'argv', ["ll-issues", "clusters", "--config", str(temp_project_dir)])` + `main_issues()`. JSON tests call `json.loads(captured.out)`. ANSI suppression tests patch `little_loops.cli.output._USE_COLOR = False`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `cmd_clusters`
- `scripts/little_loops/issue_parser.py` — parse relationship frontmatter fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — central dispatch
- Any CLI integration test that enumerates subcommands

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:29` — re-exports `main_issues` and lists it in `__all__`; `pyproject.toml:61` points the `ll-issues` entry point here (no changes needed — informational)

### Similar Patterns
- `scripts/little_loops/cli/issues/sequence.py` — subcommand structure to mirror
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph` for reference
- `scripts/little_loops/cli/loop/layout.py` — box diagram layout engine to adapt

### Tests
- `scripts/tests/test_issues_cli.py` — add class `TestIssuesCLIClusters` (existing test file; no new file per project pattern)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — needs `issues_dir_with_deps` fixture: existing `issues_dir` fixture writes no dependency frontmatter; must write `blocked_by`/`blocks` YAML for multi-cluster tests
- Tests to write in `TestIssuesCLIClusters` (follow `TestIssuesCLIImpactEffort` at `test_issues_cli.py:726–755`):
  - `test_clusters_renders_box_diagram` — assert box-drawing chars (`┌`, `┐`, `│`) appear in output
  - `test_clusters_empty_project` — assert friendly message + return code 0
  - `test_clusters_json_output` — `json.loads(captured.out)`, assert `cluster_index`, `issue_count`, `issues`, `edges` keys
  - `test_clusters_json_suppresses_box_diagram` — assert box chars absent under `--json`
  - `test_clusters_no_ansi_when_no_color` — patch `output_mod._USE_COLOR = False`, assert `"\033["` absent
  - `test_clusters_with_dependency_links` — use `issues_dir_with_deps`, assert multiple cluster header lines render
- Pattern: `patch.object(sys, "argv", ["ll-issues", "clusters", "--config", str(temp_project_dir)])` + `from little_loops.cli import main_issues` inside `with` block + `capsys.readouterr()`
- No existing test will break — confirmed no test enumerates the `ll-issues` subcommand list

### Documentation
- `docs/reference/API.md` — add `clusters` to ll-issues subcommand list

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:115` — add `clusters` to the ll-issues inline subcommand parenthetical in the CLI Tools section
- `commands/help.md:228` — add `clusters` to the `ll-issues` line in the hardcoded CLI TOOLS block
- `README.md:405–447` — add `ll-issues clusters [--include-orphans] [--min-connections N] [--json]` example invocations in the `### ll-issues` section

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — precise file:line references from codebase analysis:_

#### Key Files to Read Before Implementing
- `scripts/little_loops/cli/issues/__init__.py:17-30` — lazy import block; add `cmd_clusters` import here
- `scripts/little_loops/cli/issues/__init__.py:89` — `subs = parser.add_subparsers(dest="command")`; add clusters parser after line ~278
- `scripts/little_loops/cli/issues/__init__.py:419-447` — flat dispatch chain; add `clusters` case here
- `scripts/little_loops/dependency_graph.py:32-110` — `DependencyGraph` dataclass + `from_issues()` class method; `.blocked_by` and `.blocks` are `dict[str, set[str]]`
- `scripts/little_loops/issue_parser.py:234-235` — `IssueInfo.blocked_by: list[str]` and `IssueInfo.blocks: list[str]` (already parsed; no changes needed)
- `scripts/little_loops/issue_parser.py:679-750` — `find_issues(config, type_prefixes)` returns sorted `list[IssueInfo]`
- `scripts/little_loops/cli/loop/layout.py:557-657` — `_draw_box(grid, row, col, width, height, content, ...)` — reusable box primitive, no FSM coupling
- `scripts/little_loops/cli/output.py:16` — `terminal_width(default=80) -> int`
- `scripts/little_loops/cli/output.py:95` — `colorize(text, code) -> str`; guards on `_USE_COLOR`
- `scripts/little_loops/cli/output.py:102` — `print_json(data) -> None`
- `scripts/little_loops/cli/output.py:31-49` — `PRIORITY_COLOR` and `TYPE_COLOR` dicts

#### Existing Subcommand Reference Implementation
- `scripts/little_loops/cli/issues/sequence.py:1-79` — nearest pattern; imports `DependencyGraph`, handles `--json` before text rendering, uses `try/except ValueError` for cycle detection, returns 0 on empty

## Impact

- **Priority**: P3 - Useful for sprint planning and dependency visualization; not blocking
- **Effort**: Medium - Requires adapting the box diagram engine for a new node type; cluster extraction is straightforward
- **Risk**: Low - New subcommand with no changes to existing behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-issues`, `visualization`, `box-diagram`, `refined`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/cli/issues/__init__.py:39–85` epilog — add `clusters` to the `Sub-commands:` list and a usage example to the `Examples:` section (specific callout within Step 5)
8. Update `.claude/CLAUDE.md:115` — add `clusters` to the ll-issues subcommand parenthetical in the CLI Tools section
9. Update `commands/help.md:228` — add `clusters` to the `ll-issues` line in the hardcoded CLI TOOLS block
10. Update `README.md:405–447` — add `ll-issues clusters` invocation examples in the `### ll-issues` section
11. Update `docs/reference/API.md` — add `clusters` to the ll-issues subcommand list

## Resolution

Implemented `ll-issues clusters` as a new subcommand in `scripts/little_loops/cli/issues/clusters.py`. Key changes:

- **`clusters.py`**: BFS connected-component extraction, topological sort per cluster (cycle fallback), box diagram rendering via `_draw_box` from `cli/loop/layout.py`, ANSI-colored edge labels, `--include-orphans`, `--min-connections`, `--json` flags
- **`__init__.py`**: import, epilog entry, subparser (`clusters`/`cl` alias), dispatch
- **Tests**: 12 new tests in `TestIssuesCLIClusters` covering box rendering, empty state, no-relationships, JSON schema, JSON suppresses diagram, no-ANSI, multiple clusters, sort order, orphans, min-connections, summary line, short flag
- **Docs**: `docs/reference/API.md`, `commands/help.md`, `README.md` updated

All 5126 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-04-21T23:04:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-21T22:53:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6922353d-eb89-4086-927b-1df9aa85f4c8.jsonl`
- `/ll:confidence-check` - 2026-04-21T22:20:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/85f1d22e-4c76-41d4-914d-62974c14c745.jsonl`
- `/ll:wire-issue` - 2026-04-21T22:06:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f6c47d4-9358-40a4-adfa-83e69673bf40.jsonl`
- `/ll:refine-issue` - 2026-04-21T21:57:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7deeead-3f29-447a-aac8-b84769c43188.jsonl`
- `/ll:capture-issue` - 2026-04-21T21:41:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17ef1d96-3e92-4f16-8219-a62e2307b979.jsonl`

---

## Status

**Completed** | Created: 2026-04-21 | Completed: 2026-04-21 | Priority: P3
