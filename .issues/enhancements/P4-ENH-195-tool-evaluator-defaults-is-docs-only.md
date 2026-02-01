# Tool Evaluator Defaults Table is Documentation-Only Guidance

## Type
ENH

## Priority
P4

## Status
OPEN

## Description

The `/ll:create_loop` command documentation includes a comprehensive "Tool Evaluator Defaults" table (lines 268-289) that shows recommended evaluator types for various tools (pytest, mypy, ruff, eslint, tsc, cargo test, go test).

However, **there is no code** that implements automatic tool pattern detection. This table is purely human guidance for Claude during the wizard flow.

**Table contents:**
| Tool Pattern | Recommended Evaluator | Rationale |
|--------------|----------------------|-----------|
| `pytest` | exit_code | Well-behaved: 0=all pass, 1=failures, 2+=errors |
| `mypy` | exit_code | Well-behaved: 0=no errors, 1=type errors |
| `ruff check` | exit_code | Well-behaved: 0=clean, 1=violations |
| ... | ... | ... |

**Evidence:**
- `commands/create_loop.md:268-289` - Full table with tool patterns
- `scripts/little_loops/fsm/evaluators.py` - No detection logic
- `scripts/little_loops/fsm/compilers.py` - No detection logic

**Impact:**
Misleading. Users might think there's automatic tool detection and evaluator selection. The table is actually just guidance for the AI to customize questions.

## Files Affected
- `commands/create_loop.md`

## Options

### Option 1: Add Disclaimer (Recommended)
Add a note clarifying the table is guidance for question customization, not automatic detection:
```
Note: This table guides question customization during the wizard. There is no automatic tool detection - users should select appropriate evaluators based on their tools.
```

### Option 2: Implement Auto-Detection
Add actual tool pattern detection in the compilers or validators that suggests appropriate evaluator defaults.

## Recommendation
Option 1 (add disclaimer) is simpler and sufficient. The current approach of letting users/custom AI select evaluators is flexible and appropriate for this use case.

## Related Issues
None
