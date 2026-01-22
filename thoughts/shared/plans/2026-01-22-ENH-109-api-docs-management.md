# ENH-109: Add workflow_sequence_analyzer to API.md - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-109-add-workflow-sequence-analyzer-to-api-md.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The API.md documentation file (`docs/API.md`) currently documents 14 modules in the Module Overview table (lines 18-34) but omits the `little_loops.workflow_sequence_analyzer` module which exists at `scripts/little_loops/workflow_sequence_analyzer.py`.

### Key Discoveries
- Module exists at `scripts/little_loops/workflow_sequence_analyzer.py:1-913`
- Tests exist at `scripts/tests/test_workflow_sequence_analyzer.py`
- Module exports 12 public symbols via `__all__` (line 34-46)
- Module is Step 2 of a 3-step workflow analysis pipeline
- Module has both library API (`analyze_workflows()` at line 723) and CLI interface (`main()` at line 805)

### Documentation Patterns from API.md
1. Module section headers use `---` separator and `##` heading
2. Classes documented with `###` heading, brief description, code example
3. Dataclasses show full definition with fields and types
4. Functions documented with signature, parameters, returns, and examples
5. Helper functions grouped under `### Helper Functions` subheading

## Desired End State

The `docs/API.md` file will include:
1. Entry in Module Overview table for `little_loops.workflow_sequence_analyzer`
2. New section documenting the module's public API:
   - 5 dataclasses: `SessionLink`, `EntityCluster`, `WorkflowBoundary`, `Workflow`, `WorkflowAnalysis`
   - Main function: `analyze_workflows()`
   - 5 utility functions: `extract_entities`, `calculate_boundary_weight`, `entity_overlap`, `get_verb_class`, `semantic_similarity`
   - Constants: `VERB_CLASSES`, `WORKFLOW_TEMPLATES`

### How to Verify
- API.md contains `little_loops.workflow_sequence_analyzer` in Module Overview
- API.md contains new section with complete API documentation
- Lint and type checks pass
- Documentation is consistent with existing patterns

## What We're NOT Doing

- Not documenting internal/private functions (prefixed with `_`)
- Not documenting CLI in detail (CLI docs belong elsewhere)
- Not modifying the Python source code
- Not adding tests for documentation

## Solution Approach

Add documentation for `workflow_sequence_analyzer` following the established patterns in API.md:
1. Add entry to Module Overview table (alphabetically placed after `user_messages`, before `cli`)
2. Add new `## little_loops.workflow_sequence_analyzer` section before the Import Shortcuts section (line 1457)
3. Document all public API elements following existing patterns

## Implementation Phases

### Phase 1: Add Module to Overview Table

#### Overview
Add entry for workflow_sequence_analyzer to the Module Overview table.

#### Changes Required

**File**: `docs/API.md`
**Changes**: Insert new row in Module Overview table after `user_messages` (line 30)

```markdown
| `little_loops.user_messages` | User message extraction from Claude logs |
| `little_loops.workflow_sequence_analyzer` | Workflow sequence analysis for multi-step patterns |
| `little_loops.cli` | CLI entry points |
```

#### Success Criteria

**Automated Verification**:
- [x] Lint passes: `ruff check scripts/`
- [x] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Document Module API

#### Overview
Add comprehensive documentation section for the workflow_sequence_analyzer module.

#### Changes Required

**File**: `docs/API.md`
**Changes**: Insert new section before "Import Shortcuts" section (before line 1458)

The new section will include:
1. Module header and description
2. Quick example
3. Dataclass documentation (SessionLink, EntityCluster, WorkflowBoundary, Workflow, WorkflowAnalysis)
4. Main function documentation (analyze_workflows)
5. Utility functions documentation
6. Constants documentation

#### Success Criteria

**Automated Verification**:
- [x] Tests pass: `python -m pytest scripts/tests/`
- [x] Lint passes: `ruff check scripts/`
- [x] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Update Import Shortcuts

#### Overview
Add workflow_sequence_analyzer imports to the Import Shortcuts section.

#### Changes Required

**File**: `docs/API.md`
**Changes**: Add imports to the Import Shortcuts section

```python
# Workflow analysis
from little_loops.workflow_sequence_analyzer import (
    analyze_workflows,
    SessionLink,
    EntityCluster,
    WorkflowBoundary,
    Workflow,
    WorkflowAnalysis,
    extract_entities,
    calculate_boundary_weight,
    entity_overlap,
    get_verb_class,
    semantic_similarity,
)
```

#### Success Criteria

**Automated Verification**:
- [x] Tests pass: `python -m pytest scripts/tests/`
- [x] Lint passes: `ruff check scripts/`

---

## Testing Strategy

### Verification
- Run lint check to ensure no regressions
- Run test suite to verify no regressions
- Manual review of documentation for accuracy and completeness

## References

- Original issue: `.issues/enhancements/P4-ENH-109-add-workflow-sequence-analyzer-to-api-md.md`
- Module source: `scripts/little_loops/workflow_sequence_analyzer.py`
- Module tests: `scripts/tests/test_workflow_sequence_analyzer.py`
- Completed feature: `.issues/completed/P2-FEAT-027-workflow-sequence-analyzer-python.md`
