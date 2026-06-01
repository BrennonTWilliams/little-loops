---
id: ENH-1863
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T00:00:00Z'
discovered_date: '2026-06-01'
discovered_by: issue-size-review
parent: ENH-1858
decision_needed: false
---

# ENH-1863: `format_epic_tree()` rendering engine for EPIC child hierarchy

## Summary

Add `format_epic_tree()` to `scripts/little_loops/dependency_mapper/formatting.py` — a pure rendering function that takes a root EPIC, a child-info map, and a `DependencyGraph` scoped to the EPIC's children, and produces a Unicode box-drawing tree string (or passes structured data to the JSON path). Export it from `dependency_mapper/__init__.py` and cover it with unit tests in `test_dependency_mapper.py`.

## Parent Issue

Decomposed from ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Proposed Solution

### Step 1 — Implement `format_epic_tree()`

Add to `scripts/little_loops/dependency_mapper/formatting.py` (after `format_text_graph()`, the existing last function):

```python
def format_epic_tree(
    root_id: str,
    root_info: IssueInfo,
    child_map: dict[str, IssueInfo],
    graph: DependencyGraph,
    use_color: bool = True,
) -> str:
```

**Required new imports in `formatting.py`** (add at module top alongside existing imports):
```python
from little_loops.cli.output import colorize, BOX_ML, BOX_BL, BOX_V
from little_loops.cli.issues.clusters import EDGE_COLOR
```

`IssueInfo` and `DependencyGraph` are already gated behind `TYPE_CHECKING` in the current file (`from __future__ import annotations` is already present at line 1); they can be used as type hints without runtime import.

**Empty-children sentinel**: if `child_map` is empty, return `f"{root_id}: (no children)"` — mirrors `format_text_graph()`'s `"(no issues)"` pattern.

**`use_color` guard**: wrap every `colorize()` call: `colorize(text, code) if use_color else text`. This ensures `use_color=False` (used in tests) strips all ANSI codes without touching the `_USE_COLOR` module-level flag in `output.py`.

Model the recursive indent on `doc_scraper.DocScraper._print_sitemap()` (`doc_scraper.py:824`):
- `connector = "└── " if is_last else "├── "` (use `BOX_BL + "── "` and `BOX_ML + "── "`)
- `extension = "    " if is_last else "│   "` (use `BOX_V + "   "` for the non-last case)

Status badges: show `[done]` / `[blocked]` inline; suppress `[open]` for brevity (consistent with `list_cmd.py`). Annotate blocking edges as `⮡ blocks ISSUE-NNN` under the blocker's tree line — check `graph.blocks.get(child_id, [])` for each child.

Use `colorize()` + `EDGE_COLOR` dict from `clusters.py` for edge coloring (`"blocks": "31"`, `"blocked_by": "33"`, `"depends_on": "35"`).

Use `graph.topological_sort()` for tree ordering. The summary header line uses the `8/12 done` pattern: count children with `status in {"done", "deferred"}` over `len(child_map)`.

### Step 2 — Export from `__init__.py`

Add `format_epic_tree` to the public exports in `scripts/little_loops/dependency_mapper/__init__.py` alongside `format_report` and `format_text_graph`:
- **Lines 48–51**: extend the `from little_loops.dependency_mapper.formatting import (...)` block
- **Lines 82–83**: add `"format_epic_tree"` to the `__all__` list under the `# Formatting` comment

### Step 3 — Unit tests

Add `TestFormatEpicTree` class in `scripts/tests/test_dependency_mapper.py` following the `TestFormatTextGraph` pattern (lines 944–990). Call `format_epic_tree(root_id, root_info, child_map, graph, use_color=False)` and assert on string content. Cover:
- Linear chain → `├──` / `└──` renders correctly
- EPIC with no children → `"(no children)"` sentinel
- `[done]` / `[blocked]` badge annotation
- Blocking edge inline annotation (`⮡ blocks`)

**`make_issue` limitation**: the factory at line 33 does not accept `status` or `parent` parameters. For tests needing these fields (badge and blocking-edge cases), either:
- Extend `make_issue()` with `status: str = "open"` and `parent: str | None = None` params, or
- Construct `IssueInfo(...)` directly in the test (same pattern used in `test_issue_lifecycle.py:53`)

**`DependencyGraph` construction in tests**: build via `DependencyGraph.from_issues(list(child_map.values()))` — this is the classmethod at `dependency_graph.py:54` that processes `blocked_by`, `blocks`, and `depends_on` edges from a list of `IssueInfo` objects.

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper/formatting.py` — add `format_epic_tree()`
- `scripts/little_loops/dependency_mapper/__init__.py` — export `format_epic_tree`
- `scripts/tests/test_dependency_mapper.py` — add `TestFormatEpicTree` class

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` dataclass (line 32); `from_issues()` classmethod (line 54), `topological_sort()` Kahn's algorithm (line 272), `blocks` dict field; consumed by `format_epic_tree`
- `scripts/little_loops/cli/output.py` — `colorize(text, code)` (line 139), `BOX_ML`/`BOX_BL`/`BOX_V` constants (lines 54–61), `TYPE_COLOR`/`PRIORITY_COLOR` dicts (lines 72–85)
- `scripts/little_loops/cli/issues/clusters.py` — `EDGE_COLOR` dict (lines 16–23): `{"blocks": "31", "blocked_by": "33", "depends_on": "35", ...}`
- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass (line 211); fields used: `issue_id`, `title`, `priority`, `status`, `blocked_by`, `blocks`, `depends_on`, `parent`, `priority_int` (property, line 278)

### Similar Patterns
- `scripts/doc_scraper.py:DocScraper._print_sitemap()` (line 824) — canonical `├──` / `└──` recursive indent model; uses `connector`/`extension` logic with `prefix` accumulator
- `scripts/little_loops/dependency_mapper/formatting.py:format_text_graph()` (line 142) — existing chain renderer (note: uses inline `──→`, NOT indented tree — shows what NOT to do); follow the `lines: list[str]` accumulator + `"\n".join(lines)` return pattern
- `scripts/tests/test_dependency_mapper.py:TestFormatTextGraph` (lines 944–990) — unit-test pattern to follow; uses `make_issue()` factory (line 33) and `assert "..." in text` substring checks
- `scripts/tests/test_dependency_mapper.py:make_issue()` (line 33) — factory helper; currently lacks `status` and `parent` params (must extend or use `IssueInfo(...)` directly for badge/blocking tests)

## Implementation Steps

1. Add new imports to `scripts/little_loops/dependency_mapper/formatting.py` top section: `colorize`, `BOX_ML`, `BOX_BL`, `BOX_V` from `little_loops.cli.output`; `EDGE_COLOR` from `little_loops.cli.issues.clusters`
2. Add `format_epic_tree(root_id, root_info, child_map, graph, use_color=True)` after the existing `format_text_graph()` function in `formatting.py`; handle empty `child_map` → return sentinel; call `graph.topological_sort()` for ordered children; use `_print_sitemap()`-style prefix/connector/extension pattern
3. In `scripts/little_loops/dependency_mapper/__init__.py` lines 48–51: add `format_epic_tree` to the `from ... formatting import (...)` block; lines 82–83: add `"format_epic_tree"` to `__all__`
4. Optionally extend `make_issue()` at `scripts/tests/test_dependency_mapper.py:33` with `status: str = "open"` and `parent: str | None = None` params to support badge/blocking test cases
5. Add `TestFormatEpicTree` class after `TestFormatTextGraph` (line 944) in `test_dependency_mapper.py`; build `DependencyGraph` via `DependencyGraph.from_issues(list(child_map.values()))`; call with `use_color=False`; assert four cases
6. Run `python -m pytest scripts/tests/test_dependency_mapper.py::TestFormatEpicTree -v`

## Covers (from ENH-1858)

Parent steps covered by this child:
- Step 4: Render tree as `format_epic_tree()` standalone function
- Step 8: Export `format_epic_tree()` from `dependency_mapper/__init__.py`
- Step 11: Add `TestFormatEpicTree` class in `test_dependency_mapper.py`

## Impact

- **Priority**: P3 — follows parent priority
- **Effort**: Small — pure function + unit tests, no CLI wiring
- **Risk**: Low — additive, no mutation of existing behavior
- **Breaking Change**: No

## Success Metrics

- `format_epic_tree()` is importable from `little_loops.dependency_mapper`
- All four `TestFormatEpicTree` test cases pass
- Output matches the box-drawing tree format from the parent issue's "Expected Behavior" section

## Session Log
- `/ll:refine-issue` - 2026-06-01T18:43:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca893-3738-4d07-9997-b5b15ecc0bae.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcaa931c-330d-44e9-b237-2540a93e4fcb.jsonl`
