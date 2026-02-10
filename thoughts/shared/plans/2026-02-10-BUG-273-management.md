# BUG-273: README inaccurate counts — Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-273-readme-inaccurate-counts-skills-table-and-plugin-path.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The issue was previously fixed and completed on 2026-02-07, then reopened on 2026-02-10 because the command count drifted again. README.md and ARCHITECTURE.md claim 35 slash commands, but only 34 command files exist in `commands/`.

### Key Discoveries
- 34 command files in `commands/` (verified by ls)
- README.md:25 claims "35 slash commands" — WRONG
- README.md:659 claims "35 commands" — WRONG
- ARCHITECTURE.md:65 claims "35 slash command templates" — WRONG
- ARCHITECTURE.md:24 mermaid diagram says "34 slash commands" — CORRECT
- Skills table and plugin path are already correct from previous fix
- Ghost `find_demo_repos` command in COMMANDS.md tracked separately as BUG-313

## Desired End State

All documentation references match the actual count of 34 command files.

### How to Verify
- `ls commands/*.md | wc -l` returns 34
- README.md line 25 says "34 slash commands"
- README.md line 659 says "34 commands"
- ARCHITECTURE.md line 65 says "34 slash command templates"

## What We're NOT Doing

- Not fixing BUG-313 (ghost find_demo_repos in COMMANDS.md) — separate issue
- Not adding CI verification for count drift — noted as suggestion in issue but out of scope
- Not touching skills table or plugin path — already correct

## Implementation

### Changes Required

**File**: `README.md`
- Line 25: "35 slash commands" → "34 slash commands"
- Line 659: "35 commands" → "34 commands"

**File**: `docs/ARCHITECTURE.md`
- Line 65: "35 slash command templates" → "34 slash command templates"

### Success Criteria
- [ ] `ls commands/*.md | wc -l` returns 34
- [ ] All three lines updated to show 34
- [ ] Lint passes: `ruff check scripts/`
