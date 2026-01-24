---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-124: Smart defaults per tool for loop evaluators

## Summary

When users select common tools in the `/ll:create_loop` wizard (pytest, mypy, ruff), the wizard should suggest appropriate evaluator configurations based on known tool behavior rather than always defaulting to exit code.

## Context

Identified from conversation analyzing why created loops don't work. Different tools have different output patterns and exit code behaviors. The wizard could offer smart defaults based on tool selection.

## Current Behavior

All tools default to exit code evaluation regardless of which tool is selected. The wizard doesn't leverage knowledge about common tool behaviors.

## Expected Behavior

When a user selects or enters a common tool, suggest the best evaluator:

| Tool | Default Evaluator | Rationale |
|------|------------------|-----------|
| `pytest` | exit_code | Well-behaved, 0=pass |
| `mypy` | exit_code OR output_contains "Success" | Can have exit 0 with issues |
| `ruff check` | exit_code | Well-behaved |
| `ruff check --output-format=json` | output_json with `.length` | Parse error count |
| `npm test` | exit_code | Standard behavior |
| `npm run build` | exit_code OR output_contains "error" (negated) | Build tools vary |

## Proposed Solution

1. Create a tool pattern database in the command or a reference file
2. When user enters/selects a check command, match against known patterns
3. Pre-select the recommended evaluator and show why:

```markdown
Detected tool: mypy
Recommended evaluator: Exit code (mypy returns non-zero on errors)
```

Or for more complex tools:
```markdown
Detected tool: ruff with JSON output
Recommended evaluator: JSON path - check `.length == 0` for no errors
```

## Impact

- **Priority**: P3 (convenience improvement)
- **Effort**: Medium (pattern database + matching logic)
- **Risk**: Low (suggestions only, user can override)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_loop.md | Wizard implementation |
| architecture | scripts/little_loops/fsm/evaluators.py | Available evaluator types |

## Labels

`enhancement`, `create-loop`, `evaluators`, `ux`, `captured`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P3
