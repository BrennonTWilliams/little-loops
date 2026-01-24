# ENH-128: Update directory structures across documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-128-update-directory-structures-across-documentation.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: fix

## Current State Analysis

Multiple documentation files have directory structure diagrams that don't fully reflect the current project layout.

### Key Discoveries
- `docs/ARCHITECTURE.md:60-147` - Directory structure is mostly complete, FSM modules already documented (lines 121-131), only missing `skills/` directory
- `CONTRIBUTING.md:69-119` - Missing `skills/` directory, missing FSM modules (`signal_detector.py`, `handoff_handler.py`, `__init__.py`), missing `issue_history.py` and `sprint.py`
- `docs/API.md:16-36` - Missing `issue_history`, `logo`, and `dependency_graph` module entries

### Verified Actual State
- `skills/` directory exists with 4 skills: analyze-history, capture-issue, issue-workflow, workflow-automation-proposer
- FSM modules exist: `__init__.py`, `schema.py`, `compilers.py`, `evaluators.py`, `executor.py`, `interpolation.py`, `validation.py`, `persistence.py`, `signal_detector.py`, `handoff_handler.py`
- `issue_history.py`, `logo.py`, `dependency_graph.py` all exist in `scripts/little_loops/`

## Desired End State

All three documentation files accurately reflect the current project structure:
1. ARCHITECTURE.md includes `skills/` directory
2. CONTRIBUTING.md includes `skills/`, all FSM modules, and missing Python modules
3. API.md includes all Python module entries

### How to Verify
- Visual inspection of updated diagrams
- Cross-reference with actual directory contents

## What We're NOT Doing

- Not updating any other documentation files
- Not modifying code files
- Not changing file counts (26 commands, 8 agents, etc.)

## Implementation Phases

### Phase 1: Update ARCHITECTURE.md

#### Overview
Add `skills/` directory to the directory structure between `hooks/` and `templates/`.

#### Changes Required

**File**: `docs/ARCHITECTURE.md`
**Lines**: Insert after line 91 (after hooks/ section ends)

Insert:
```
├── skills/                  # 4 skill definitions
│   ├── analyze-history/
│   │   └── SKILL.md
│   ├── capture-issue/
│   │   └── SKILL.md
│   ├── issue-workflow/
│   │   └── SKILL.md
│   └── workflow-automation-proposer/
│       └── SKILL.md
```

#### Success Criteria
- [x] `skills/` directory appears in ARCHITECTURE.md structure

---

### Phase 2: Update CONTRIBUTING.md

#### Overview
Add `skills/` directory, missing FSM modules, and missing Python modules.

#### Changes Required

**File**: `CONTRIBUTING.md`

1. Add `skills/` directory after line 77 (`├── hooks/`)
2. Add missing FSM modules to fsm/ section (lines 103-110)
3. Add `issue_history.py` and `sprint.py` to little_loops/ section

#### Success Criteria
- [x] `skills/` directory appears in CONTRIBUTING.md structure
- [x] All FSM modules listed
- [x] All Python modules listed

---

### Phase 3: Update API.md

#### Overview
Add missing module entries to the Module Overview table.

#### Changes Required

**File**: `docs/API.md`
**Lines**: 18-35 (Module Overview table)

Add entries for:
- `little_loops.issue_history` - Issue history and statistics
- `little_loops.logo` - CLI logo display
- `little_loops.dependency_graph` - Dependency graph construction

#### Success Criteria
- [x] All modules in scripts/little_loops/ are represented in Module Overview

---

### Phase 4: Rename duplicate issue file

#### Overview
The P4-ENH-128 file should be renamed to ENH-133 to avoid ID collision.

#### Changes Required
Rename `.issues/enhancements/P4-ENH-128-readme-command-naming-inconsistency.md` to `.issues/enhancements/P4-ENH-133-readme-command-naming-inconsistency.md`

#### Success Criteria
- [x] No duplicate ENH-128 files exist

---

## Verification

- Lint: N/A (documentation only)
- Types: N/A (documentation only)
- Tests: N/A (documentation only)

## References

- Original issue: `.issues/enhancements/P3-ENH-128-update-directory-structures-across-documentation.md`
