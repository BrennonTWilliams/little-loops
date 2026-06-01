---
id: ENH-1858
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [ENH-1727, FEAT-1855]
---

# ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Summary

Extend `ll-deps` with a tree view rooted at an EPIC, showing child issues with their dependency edges (`blocked_by`, `depends_on`, `blocks`) and current status. Complements `ll-issues list --group-by epic` (flat per-bucket list) with a structural view that surfaces critical path and blockers within an EPIC.

## Current Behavior

`ll-deps` analyzes cross-issue dependencies project-wide but has no EPIC-rooted view. To see "what's blocking EPIC-1773's progress" the user must run `ll-deps` globally and manually filter to children of EPIC-1773 — or open files one by one.

`ll-issues list --group-by epic` shows children flat under each EPIC bucket but does not render dependency edges between them.

## Expected Behavior

```
$ ll-deps tree --epic EPIC-1773
EPIC-1773  Audit & simplify built-in FSM loops [open, 8/12 done]
├── ENH-1641  Extract shared fragments  [open, 24d stalled]
│   └── ⮡ blocks  ENH-1820  Migrate goal-cluster to fragments  [blocked]
├── FEAT-1820  Migrate goal-cluster to fragments  [blocked by ENH-1641]
├── ENH-1774  Wave 1: ll-commit shared fragments  [done]
└── ENH-1775  Wave 2: extract generator-evaluator  [done]
```

JSON output via `--format json` for tooling integration.

## Motivation

Within an EPIC, the question is rarely "what dependencies exist globally" — it's "what's the critical path inside this initiative, what's currently blocking forward progress, and which children are independent?". A scoped tree answers this in one glance.

This complements the FEAT-1855 progress aggregation (numbers) and FEAT-1856 review-epic skill (interpretation) with structural visibility.

## Proposed Solution

1. Add `ll-deps tree` subcommand accepting `--epic EPIC-NNN` (and optionally `--root ISSUE-NNN` for non-EPIC roots later).
2. Resolve children via the FEAT-1737 union path.
3. Build a directed graph from child `blocked_by` / `depends_on` / `blocks` edges, restricted to the child set.
4. Render as Unicode tree with status badges and edge annotations.
5. `--format json` for programmatic callers.

For rendering, model the tree on standard `tree(1)` output with Unicode box-drawing. Use existing `DependencyGraph` (`scripts/little_loops/dependency_graph.py`) — restrict its node set to the EPIC children before topo/wave layout.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — add `tree` subcommand + argparse wiring
- `scripts/little_loops/dependency_graph.py` — N/A (reuse `from_issues()` filtered to child set)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()` for EPIC→children resolution (FEAT-1737)
- `scripts/little_loops/cli/issues/list_cmd.py` — adjacent epic-grouping output for cross-reference

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` epic-grouping branch (ENH-1727) — same `parent:` scan + `Unparented` exclusion (here we explicitly require an EPIC root)
- `scripts/little_loops/dependency_graph.py:DependencyGraph.from_issues()` + `.get_execution_waves()` — existing layout; topo sort handles tree ordering

### Tests
- `scripts/tests/test_deps_cli.py` — new `TestDepsTree` class
  - EPIC with no children → clear message, exit 0
  - EPIC with linear chain → renders chain
  - EPIC with diamond dependency → renders correctly with shared node annotation
  - EPIC not found → exit non-zero
  - `--format json` round-trips

### Documentation
- `docs/reference/CLI.md` — `ll-deps tree` subcommand block

### Configuration
- N/A

## Implementation Steps

1. **Add `tree` subparser** to `ll-deps` with `--epic` and `--format`.
2. **Resolve children** via FEAT-1737 path.
3. **Build filtered DependencyGraph** restricted to child node set.
4. **Render tree** — Unicode + status badges; annotate edges with relation type.
5. **JSON path** — emit `{root, nodes: [{id, status, parent}], edges: [{from, to, kind}]}`.
6. **Tests** for each render path.
7. **Docs** update.

## Impact

- **Priority**: P3 — Useful but lower-leverage than FEAT-1855 (aggregation); answers a structural question (1855 answers a quantitative one).
- **Effort**: Small–Medium — Reuses `DependencyGraph` and FEAT-1737 resolution; pure rendering work.
- **Risk**: Low — New read-only subcommand.
- **Breaking Change**: No

## Success Metrics

- Tree view appears in `ll-deps --help` and is documented in CLI reference.
- For EPICs with ≥3 children, tree output fits in a single terminal screen and is unambiguous about blockers.

## Scope Boundaries

- No mutation of issue files.
- No automatic edge inference from prose — only `blocked_by` / `depends_on` / `blocks` frontmatter.
- No Gantt or timeline rendering — that is a separate (deferred) follow-up.
- Does not modify `ll-deps`'s existing global view.

## API/Interface

```
ll-deps tree --epic EPIC-NNN [--format {text,json}]
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `cli`, `deps`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
