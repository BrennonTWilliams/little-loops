# ENH-332: Add loop templates using CLI tools - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-332-add-loop-templates-using-cli-tools.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

5 existing loop templates in `loops/` all use `/ll:` slash commands. None use shell-based CLI tools. The FSM compiler auto-detects shell commands (no `/` prefix = shell action_type).

## Desired End State

3 new loop templates demonstrating CLI tools with `action_type: shell` (auto-detected):
1. **sprint-execution.yaml** (imperative) — `ll-sprint` for batch processing
2. **workflow-analysis.yaml** (imperative) — `ll-messages` + `ll-workflows` for pattern discovery
3. **history-reporting.yaml** (invariants) — `ll-history` for retrospective analysis with quality gate

## What We're NOT Doing

- Not modifying existing templates
- Not changing the FSM loop engine or compilers
- Not implementing new paradigm compilers (goal/convergence)

## Implementation Phases

### Phase 1: Create 3 loop template YAML files

**File**: `loops/sprint-execution.yaml` [CREATE]
- Imperative paradigm using `ll-sprint run` with `ll-sprint show` for status checking

**File**: `loops/workflow-analysis.yaml` [CREATE]
- Imperative paradigm using `ll-messages` then `ll-workflows` pipeline

**File**: `loops/history-reporting.yaml` [CREATE]
- Invariants paradigm using `ll-history` for analysis checks

### Success Criteria
- [ ] `ll-loop compile loops/sprint-execution.yaml`
- [ ] `ll-loop compile loops/workflow-analysis.yaml`
- [ ] `ll-loop compile loops/history-reporting.yaml`
- [ ] `ll-loop validate` passes for all three
- [ ] Tests pass: `python -m pytest scripts/tests/`
