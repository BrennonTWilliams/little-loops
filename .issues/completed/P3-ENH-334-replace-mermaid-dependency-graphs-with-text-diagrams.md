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

## Motivation

This enhancement would:
- Improve usability: mermaid code blocks are unreadable in the terminal where these commands are used
- Remove a rendering dependency: text diagrams work everywhere, mermaid requires a renderer

## Proposed Solution

Replace `format_mermaid()` in `dependency_mapper.py` with a `format_text_graph()` function that renders directed graphs using box-drawing or ASCII arrow characters (e.g., `──►`, `│`, `└──`).

## Scope Boundaries

- **In scope**: Replacing mermaid output with text diagram output in dependency_mapper.py
- **Out of scope**: Adding interactive graph features, changing graph data structures

## Impact

- **Priority**: P3 - UX improvement for CLI output readability
- **Effort**: Small-Medium - Single function replacement with ASCII rendering logic
- **Risk**: Low - Output format change only, no behavioral changes
- **Breaking Change**: No (output format is not a public API)

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` - Replace `format_mermaid()` with `format_text_graph()`

### Dependent Files (Callers/Importers)
- `skills/map-dependencies/SKILL.md` - calls dependency mapper formatting
- `skills/create-sprint/SKILL.md` - may use dependency graph output

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_dependency_mapper.py` - update format tests

### Documentation
- N/A

### Configuration
- N/A

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

---

## Status

**Completed** | Created: 2026-02-11 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-11
- **Verdict**: VALID
- `format_mermaid()` confirmed at `dependency_mapper.py:713`
- No `format_text_graph()` alternative exists
- Feature is new work — replace mermaid output with ASCII rendering

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `scripts/little_loops/dependency_mapper.py`: Replaced `format_mermaid()` with `format_text_graph()` using ASCII arrows (`──→` for existing, `-.→` for proposed)
- `scripts/tests/test_dependency_mapper.py`: Updated tests to verify ASCII output instead of mermaid
- `docs/API.md`: Updated API documentation for `format_text_graph()`

### Verification Results
- Tests: PASS (58 passed)
- Lint: PASS
- Types: PASS
