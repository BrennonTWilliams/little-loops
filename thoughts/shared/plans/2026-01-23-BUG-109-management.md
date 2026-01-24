# BUG-109: CLAUDE.md missing CLI tools documentation - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-109-claude-md-missing-cli-tools-documentation.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `.claude/CLAUDE.md` file documents only 3 CLI tools (lines 79-82):
- `ll-auto`
- `ll-parallel`
- `ll-messages`

However, `scripts/pyproject.toml` defines 7 CLI tools (lines 47-54):
- `ll-auto`
- `ll-parallel`
- `ll-messages`
- `ll-loop`
- `ll-sprint`
- `ll-workflows`
- `ll-history`

## Desired End State

The CLI Tools section in CLAUDE.md lists all 7 available tools with accurate descriptions.

### How to Verify
- All 7 tools from pyproject.toml are listed in CLAUDE.md
- Descriptions match the tool functionality

## What We're NOT Doing

- Not changing any Python code
- Not modifying pyproject.toml
- Not updating other documentation files

## Solution Approach

Add the 4 missing CLI tools to the existing list in CLAUDE.md.

## Implementation Phases

### Phase 1: Update CLI Tools Section

#### Overview
Add the 4 missing CLI tools to CLAUDE.md

#### Changes Required

**File**: `.claude/CLAUDE.md`
**Changes**: Add 4 new tool entries to the CLI Tools section

#### Success Criteria

**Automated Verification**:
- [x] File contains all 7 CLI tools

**Manual Verification**:
- [ ] Descriptions are accurate and helpful

## References

- Original issue: `.issues/bugs/P2-BUG-109-claude-md-missing-cli-tools-documentation.md`
- Source of truth: `scripts/pyproject.toml:47-54`
