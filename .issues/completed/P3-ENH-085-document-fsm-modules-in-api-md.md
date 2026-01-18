---
discovered_commit: 68997ce18a454cb21ec487df508fed6fda5b3b68
discovered_branch: main
discovered_date: 2026-01-17T00:00:00Z
discovered_by: audit_docs
doc_file: docs/API.md
---

# ENH-085: Document FSM modules in docs/API.md

## Summary

Documentation enhancement found by `/ll:audit_docs`. The FSM loop system modules (`little_loops.fsm.*`) and sprint module are implemented but not documented in API.md.

## Location

- **File**: `docs/API.md`
- **Section**: Module Overview table and new section for FSM modules

## Current State

The API.md documents core modules like `config`, `issue_parser`, `parallel`, etc. but is missing:

- `little_loops.fsm` (package)
- `little_loops.fsm.schema` - FSM schema definition
- `little_loops.fsm.compilers` - Paradigm compilers
- `little_loops.fsm.evaluators` - Verdict evaluators
- `little_loops.fsm.executor` - FSM execution engine
- `little_loops.fsm.interpolation` - Variable interpolation
- `little_loops.fsm.validation` - Schema validation
- `little_loops.fsm.persistence` - State persistence
- `little_loops.sprint` - Sprint planning

## Expected Enhancement

Add new section documenting FSM modules:

```markdown
## little_loops.fsm

FSM loop system for automation workflows.

### Overview

| Module | Purpose |
|--------|---------|
| `little_loops.fsm.schema` | FSM state machine schema definitions |
| `little_loops.fsm.compilers` | Compile paradigms (goal, convergence, etc.) to FSM |
| `little_loops.fsm.evaluators` | Verdict evaluators (exit_code, llm_structured, etc.) |
| `little_loops.fsm.executor` | FSM execution engine |
| `little_loops.fsm.interpolation` | Variable substitution (${context.*}, etc.) |
| `little_loops.fsm.validation` | Schema validation utilities |
| `little_loops.fsm.persistence` | Loop state persistence |

[Detailed documentation for each module]
```

## Impact

- **Severity**: Medium (API discoverability)
- **Effort**: Medium (documentation writing)
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-17 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-18
- **Status**: Completed

### Changes Made
- `docs/API.md`: Added FSM and sprint modules to Module Overview table
- `docs/API.md`: Added comprehensive `## little_loops.fsm` section with:
  - Submodule overview table
  - Quick import guide
  - Detailed documentation for schema module (FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig)
  - Detailed documentation for compilers module (compile_paradigm and paradigm-specific functions)
  - Detailed documentation for evaluators module (all evaluate_* functions)
  - Detailed documentation for executor module (FSMExecutor, ExecutionResult, ActionResult)
  - Detailed documentation for interpolation module (InterpolationContext, interpolate)
  - Detailed documentation for validation module (ValidationError, validate_fsm, load_and_validate)
  - Detailed documentation for persistence module (LoopState, StatePersistence, PersistentExecutor)
- `docs/API.md`: Added comprehensive `## little_loops.sprint` section with:
  - SprintOptions dataclass
  - Sprint dataclass with methods
  - SprintManager class with methods

### Verification Results
- Tests: PASS (1345 tests)
- Lint: PASS
- Types: PASS (only expected optional anthropic import warning)
