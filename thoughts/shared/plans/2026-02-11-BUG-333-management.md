# BUG-333: create_loop template wizard shows use-cases instead of paradigms - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P3-BUG-333-create-loop-template-wizard-shows-use-cases-instead-of-paradigms.md
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

Step 0.1 in `commands/create_loop.md` (lines 48-66) presents use-case templates (Python quality, JavaScript quality, etc.) when user selects "Start from template". The five loop paradigms (goal, convergence, invariants, imperative, FSM) should be presented instead.

## Desired End State

Step 0.1 presents the five paradigms with descriptions. After paradigm selection, the flow continues to Step 0.2 for customization or directly into paradigm-specific questions (Step 2).

## What We're NOT Doing

- Not changing the "Build from paradigm" path (Step 1+)
- Not removing template definitions (they can still be useful as examples)
- Not changing the template customization flow (Step 0.2)

## Solution Approach

Replace the Step 0.1 AskUserQuestion options from use-case templates to the five paradigms. Update Step 0.2 to gather paradigm-specific customization. Wire the selected paradigm into subsequent steps (skipping Step 1 since paradigm is already chosen).

## Implementation Phases

### Phase 1: Replace Step 0.1 template list with paradigm options

**File**: `commands/create_loop.md`
**Changes**: Replace lines 48-66 (Step 0.1) with paradigm selection, update Step 0.2 flow.

#### Success Criteria
- [ ] The Step 0.1 question presents 4 paradigm options (goal, convergence, invariants, imperative) plus FSM
- [ ] Flow after selection routes to paradigm-specific questions (Step 2)
- [ ] Existing template definitions remain as reference examples
