---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-334: Replace mermaid dependency graphs with text diagrams in CLI

## Summary

The dependency graph output in `/ll:map_dependencies` and `/ll:create_sprint` uses mermaid code blocks which don't render in the terminal. Replace all mermaid graph output with generated ASCII/text diagrams that are readable directly in the CLI.

## Current Behavior

Dependency graphs are output as ````mermaid` code blocks (via `format_mermaid()` in `scripts/little_loops/dependency_mapper.py:713`). These render as raw code in the terminal, not as visual diagrams.

## Expected Behavior

Dependency graphs should be rendered as ASCII/text art diagrams that are immediately readable in the terminal. For example:

```
BUG-100 ──► ENH-200 ──► FEAT-300
              │
              └──► BUG-150
```

## Affected Files

- `scripts/little_loops/dependency_mapper.py` - `format_mermaid()` at line 713
- Any skills/commands that call or inline mermaid graph output for dependencies

## Implementation Steps

1. Create a `format_text_graph()` function in `dependency_mapper.py` as a replacement for `format_mermaid()`
2. Use box-drawing or ASCII arrow characters to render directed graphs
3. Replace all call sites of `format_mermaid()` with `format_text_graph()`
4. Update or remove `format_mermaid()` if no longer needed
5. Update tests in `scripts/tests/test_dependency_mapper.py`

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
