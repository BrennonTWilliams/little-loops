---
captured_at: "2026-04-21T21:41:58Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
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
shows issues as nodes with labeled edges for relationship type (blocks, parent, sibling,
etc.). Clusters are sorted by issue count descending — the biggest cluster appears first,
the smallest (e.g., 2-issue pairs) last.

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
- [ ] Each edge shows: relationship type label (e.g., `blocks`, `parent`, `sibling`)
- [ ] 1-issue clusters (orphans) are omitted by default; a `--include-orphans` flag includes them
- [ ] Outputs a summary line: `N clusters, M issues total` at the end
- [ ] Handles the case where no relationships exist (prints friendly message)

## API/Interface

```python
# scripts/little_loops/cli/issues/clusters.py

def cmd_clusters(args: argparse.Namespace, base_dir: Path) -> int:
    """Render issue relationship clusters as box diagrams.

    Args:
        args: Parsed CLI args (include_orphans: bool, min_size: int)
        base_dir: Root issues directory

    Returns:
        Exit code
    """
```

```
# CLI usage
ll-issues clusters [--include-orphans] [--min-size N]
```

## Proposed Solution

1. **Graph construction**: Load all active issues, parse frontmatter relationship fields
   (`blocked_by`, `blocks`, `parent`, `sibling`). Build an undirected adjacency graph.
   Reuse or extend `scripts/little_loops/dependency_mapper/analysis.py` for graph
   traversal; `format_text_graph` in `formatting.py` already renders chains, but a
   new renderer is needed for arbitrary cluster graphs.

2. **Cluster extraction**: Run BFS/union-find over the adjacency graph to extract
   connected components. Sort by size descending.

3. **Box diagram rendering**: For each cluster, render issues as labeled boxes and
   relationships as edges. Adapt the FSM box diagram engine in
   `scripts/little_loops/cli/loop/layout.py` — the layout logic handles box sizing,
   edge routing, and terminal width; wrap it for issue nodes instead of FSM states.

4. **CLI integration**: Register `clusters` in `main_issues()` in
   `scripts/little_loops/cli/issues/__init__.py` following the same pattern as
   `cmd_sequence`, `cmd_impact_effort`, etc.

## Implementation Steps

1. Add `blocked_by` / `blocks` / `parent` / `sibling` frontmatter parsing to
   `scripts/little_loops/issue_parser.py` (if not already present)
2. Build adjacency graph + BFS cluster extraction in
   `scripts/little_loops/cli/issues/clusters.py`
3. Implement cluster box diagram renderer (adapting loop layout or building a lightweight
   node-edge box renderer)
4. Register `clusters` subcommand in `__init__.py`
5. Write tests: graph construction, cluster sorting, edge label rendering, empty-state

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `cmd_clusters`
- `scripts/little_loops/issue_parser.py` — parse relationship frontmatter fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — central dispatch
- Any CLI integration test that enumerates subcommands

### Similar Patterns
- `scripts/little_loops/cli/issues/sequence.py` — subcommand structure to mirror
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph` for reference
- `scripts/little_loops/cli/loop/layout.py` — box diagram layout engine to adapt

### Tests
- `scripts/tests/test_ll_issues_clusters.py` — new test file

### Documentation
- `docs/reference/API.md` — add `clusters` to ll-issues subcommand list

### Configuration
- N/A

## Impact

- **Priority**: P3 - Useful for sprint planning and dependency visualization; not blocking
- **Effort**: Medium - Requires adapting the box diagram engine for a new node type; cluster extraction is straightforward
- **Risk**: Low - New subcommand with no changes to existing behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-issues`, `visualization`, `box-diagram`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-21T21:41:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17ef1d96-3e92-4f16-8219-a62e2307b979.jsonl`

---

## Status

**Open** | Created: 2026-04-21 | Priority: P3
