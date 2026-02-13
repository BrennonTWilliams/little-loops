# BUG-382: CONTRIBUTING.md directory trees outdated - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-382-contributing-directory-trees-outdated.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

CONTRIBUTING.md lines 124-150 contain three outdated directory tree sections:

### Skills (line 130-136)
- Comment says "7 skill definitions" but there are 8
- Tree lists only 6 of 8 directories
- Missing: `confidence-check/`, `loop-suggester/`

### Loops (lines 124-129)
- Shows 5 YAML files but there are 8
- Missing: `history-reporting.yaml`, `sprint-execution.yaml`, `workflow-analysis.yaml`

### Docs (lines 138-150)
- Missing files: `CONFIGURATION.md`, `ISSUE_TEMPLATE.md`, `MERGE-COORDINATOR.md`
- Missing subdirectories: `claude-code/`, `demo/`, `research/`

## Desired End State

All three directory tree sections in CONTRIBUTING.md accurately reflect the current contents of `skills/`, `loops/`, and `docs/`.

## What We're NOT Doing

- Not changing any other sections of CONTRIBUTING.md
- Not reorganizing the tree format or style

## Implementation Phases

### Phase 1: Update all three tree sections

**File**: `CONTRIBUTING.md`

1. Update loops section (lines 124-129): Add 3 missing YAML files in alphabetical order
2. Update skills section (lines 130-136): Change comment from "7" to "8" and add 2 missing directories in alphabetical order
3. Update docs section (lines 138-150): Add 3 missing files and 3 missing subdirectories in alphabetical order

#### Success Criteria
- [ ] All 8 loop YAML files listed
- [ ] Skills comment says "8 skill definitions" and all 8 directories listed
- [ ] All docs files and subdirectories listed
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
