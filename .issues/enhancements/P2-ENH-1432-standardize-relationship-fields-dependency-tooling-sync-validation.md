---
id: ENH-1432
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1430
status: open
---

# ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Summary

Update `dependency_graph.py`, `dependency_mapper/`, `sync.py`, and `formatting.py` to traverse and validate all canonical relationship fields. Adds `depends_on` soft-ordering to wave planning, maps relationship types in GitHub sync, and warns on unknown field names in frontmatter. Depends on ENH-1430 (new `IssueInfo` fields must exist). Can run in parallel with ENH-1431.

## Parent Issue

Decomposed from ENH-1391: Standardize Issue Relationship Fields

## Scope

Covers implementation steps 4, 5, 6, 7, and 13 from the parent.

## Proposed Solution

### Step 4 — `dependency_mapper/analysis.py` and `dependency_mapper/operations.py`

**`analysis.py` `validate_dependencies()`:**
- Extend to check broken refs in `depends_on`, `relates_to`, `duplicate_of` using same broken-ref logic as `blocked_by`

**`operations.py`:**
- Add `_add_to_section(path, "Depends On", id)` and `_add_to_section(path, "Relates To", id)` call-sites alongside the existing `"Blocked By"` and `"Blocks"` sections

### Step 5 — `dependency_graph.py` `DependencyGraph.from_issues()`

Add a third pass for `issue.depends_on` (soft ordering):
- Build a separate `depends_on_edges` dict (does NOT block wave entry)
- Update `get_execution_waves()` to place `depends_on` targets in earlier waves without hard-blocking the dependent
- No change to `blocked_by` hard-stop semantics
- Extend `make_issue()` helper in tests with `depends_on: list[str] | None = None` kwarg

### Step 6 — `sync.py` `GitHubSyncManager._push_single_issue()`

GitHub has no native relationship API; map relationship fields as:
- `blocked_by` → add a `blocked-by` label
- `duplicate_of` → append a closing comment reference

Note: `ll-sync` currently maps NO relationship fields — this is new territory.

### Step 7 — Unknown field validation

Add `validate_frontmatter_fields()` helper (in `dependency_mapper/analysis.py` or new file) that warns via `logger.warning()` when an issue's frontmatter contains an unrecognized relationship key (e.g., `parent_issue:` or `related:` after migration). Pattern: `caplog`-testable `logger.warning(...)`.

### Step 13 — `dependency_mapper/formatting.py` `format_text_graph()`

Decide whether `depends_on` edges should appear in the ASCII graph output and extend `format_text_graph()` accordingly. Current: iterates only `issue.blocked_by` for edges. Recommended: show `depends_on` edges with a distinct marker (e.g., `-->` vs `==>` for `blocked_by`).

## Files to Modify

- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`, `get_execution_waves()`
- `scripts/little_loops/dependency_mapper/analysis.py` — `validate_dependencies()`, new `validate_frontmatter_fields()`
- `scripts/little_loops/dependency_mapper/operations.py` — new section call-sites
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph()` edge display
- `scripts/little_loops/sync.py` — `GitHubSyncManager._push_single_issue()`

## Tests

- `scripts/tests/test_dependency_graph.py` — add `test_depends_on_soft_ordering()` using `make_issue()` helper; extend `make_issue()` with `depends_on` kwarg; extend `get_execution_waves()` tests
- `scripts/tests/test_dependency_mapper.py` — add validation tests for broken refs in `depends_on`, `relates_to`, `duplicate_of`; extend `make_issue()` helper with `depends_on` kwarg
- `scripts/tests/test_cli_sync.py` — extend with relationship field mapping assertions (`blocked-by` label, `duplicate_of` comment)

## Acceptance Criteria

- `DependencyGraph.from_issues()` builds soft-ordering edges from `depends_on` without treating them as hard blocks
- `get_execution_waves()` respects `depends_on` for soft ordering (target in earlier wave, not required)
- `validate_dependencies()` reports broken refs in `depends_on`, `relates_to`, `duplicate_of`
- `validate_frontmatter_fields()` emits `logger.warning()` for any unrecognized relationship key (`parent_issue:`, `related:`, etc.)
- `GitHubSyncManager` maps `blocked_by` to label and `duplicate_of` to closing comment
- `format_text_graph()` displays `depends_on` edges distinctly from `blocked_by`
- All new tests pass

## Scope Boundaries

- **In scope**: `dependency_graph.py`, `dependency_mapper/*`, `sync.py`, `formatting.py` changes and their tests
- **Out of scope**: Schema/parser (ENH-1430), migration script (ENH-1431), docs/skills (ENH-1433)
- **Depends on**: ENH-1430 — `IssueInfo.depends_on`, `.relates_to`, `.duplicate_of` fields must exist

## Session Log
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
