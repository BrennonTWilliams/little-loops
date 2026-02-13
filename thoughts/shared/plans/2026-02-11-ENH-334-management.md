# ENH-334: Replace mermaid dependency graphs with text diagrams - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-334-replace-mermaid-dependency-graphs-with-text-diagrams.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

- `format_mermaid()` at `dependency_mapper.py:713-754` generates mermaid code blocks
- Not called in production code — only in tests (`test_dependency_mapper.py:662-700`)
- Not exported from `__init__.py`
- Documented in `docs/API.md:842-859`
- The codebase already has `_render_dependency_graph()` in `cli.py:1595-1664` using `──→` ASCII arrows — a similar pattern to follow

## Desired End State

`format_mermaid()` replaced by `format_text_graph()` that renders readable ASCII dependency graphs in the terminal.

### How to Verify
- Tests updated and passing
- Output is readable ASCII, not mermaid code blocks

## What We're NOT Doing

- Not changing graph data structures
- Not adding interactive graph features
- Not modifying `_render_dependency_graph()` in cli.py (different function, different input types)

## Solution Approach

Replace `format_mermaid()` with `format_text_graph()` using the same `──→` and `-.→` arrow style already used in `cli.py:1634`. The function receives `list[IssueInfo]` and optional proposals, so we build a directed graph and render chains.

## Implementation Phases

### Phase 1: Replace format_mermaid with format_text_graph

**File**: `scripts/little_loops/dependency_mapper.py`

Replace `format_mermaid()` (lines 713-754) with `format_text_graph()`:

```python
def format_text_graph(
    issues: list[IssueInfo],
    proposals: list[DependencyProposal] | None = None,
) -> str:
    """Generate an ASCII dependency graph diagram.

    Shows existing dependencies as solid arrows and proposed
    dependencies as dashed arrows.

    Args:
        issues: List of parsed issue objects
        proposals: Optional proposed dependencies to include

    Returns:
        Text graph string readable in the terminal
    """
    if not issues:
        return "(no issues)"

    issue_ids = {i.issue_id for i in issues}
    sorted_issues = sorted(issues, key=lambda i: (i.priority_int, i.issue_id))

    lines: list[str] = []

    # Build adjacency: blocker -> list of blocked issues
    blocks: dict[str, list[str]] = {}
    for issue in sorted_issues:
        for blocker_id in issue.blocked_by:
            if blocker_id in issue_ids:
                blocks.setdefault(blocker_id, []).append(issue.issue_id)

    # Add proposed edges
    proposed_edges: set[tuple[str, str]] = set()
    if proposals:
        for p in proposals:
            if p.target_id in issue_ids and p.source_id in issue_ids:
                blocks.setdefault(p.target_id, []).append(p.source_id)
                proposed_edges.add((p.target_id, p.source_id))

    # Build chains from roots (issues not blocked by anything in the set)
    blocked_ids = set()
    for targets in blocks.values():
        blocked_ids.update(targets)
    roots = [i.issue_id for i in sorted_issues if i.issue_id not in blocked_ids]

    visited: set[str] = set()
    chains: list[str] = []

    def build_chain(issue_id: str) -> str:
        if issue_id in visited:
            return issue_id
        visited.add(issue_id)
        targets = sorted(blocks.get(issue_id, []))
        if not targets:
            return issue_id
        if len(targets) == 1:
            arrow = "-.→" if (issue_id, targets[0]) in proposed_edges else "──→"
            return f"{issue_id} {arrow} {build_chain(targets[0])}"
        # Multiple branches
        arrow = "-.→" if (issue_id, targets[0]) in proposed_edges else "──→"
        result = f"{issue_id} {arrow} {build_chain(targets[0])}"
        for other in targets[1:]:
            if other not in visited:
                arrow = "-.→" if (issue_id, other) in proposed_edges else "──→"
                chains.append(f"  {issue_id} {arrow} {build_chain(other)}")
        return result

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            chains.append(f"  {chain}")

    # Isolated issues (not in any chain)
    for issue in sorted_issues:
        if issue.issue_id not in visited:
            chains.append(f"  {issue.issue_id}")

    lines.extend(chains)

    if any("──→" in c for c in chains) or any("-.→" in c for c in chains):
        lines.append("")
        legend_parts = []
        if any("──→" in c for c in chains):
            legend_parts.append("──→ blocks")
        if any("-.→" in c for c in chains):
            legend_parts.append("-.→ proposed")
        lines.append(f"Legend: {', '.join(legend_parts)}")

    return "\n".join(lines)
```

### Phase 2: Update tests

**File**: `scripts/tests/test_dependency_mapper.py`

- Rename `TestFormatMermaid` to `TestFormatTextGraph`
- Update import from `format_mermaid` to `format_text_graph`
- Update assertions to check for ASCII arrows instead of mermaid syntax

### Phase 3: Update API docs

**File**: `docs/API.md`

- Replace `format_mermaid` section with `format_text_graph` documentation

### Success Criteria

- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
