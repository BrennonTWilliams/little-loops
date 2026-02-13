# BUG-381: README skills count wrong and table missing loop-suggester - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-381-readme-skills-count-wrong-and-table-missing-loop-suggester.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

README.md line 86 says "7 skills" and the Skills table (lines 185-193) lists 7 skills. The `loop-suggester` skill exists at `skills/loop-suggester/SKILL.md` but is missing from both the count and the table.

## Desired End State

- Line 86 says "8 skills"
- Skills table includes `loop-suggester` row under "Automation & Loops" capability group

## What We're NOT Doing

- Not changing any other counts or tables
- Not modifying any code files

## Implementation Phases

### Phase 1: Fix README.md

#### Changes Required

**File**: `README.md`

1. Line 86: Change "7 skills" to "8 skills"
2. After line 193 (confidence-check row), add: `| `loop-suggester` | Automation & Loops | Suggest FSM loops from user message history |`

#### Success Criteria

- [x] Count says "8 skills"
- [x] Table has 8 rows including loop-suggester
