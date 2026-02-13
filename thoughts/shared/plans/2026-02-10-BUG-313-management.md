# BUG-313: Ghost `find_demo_repos` command in COMMANDS.md - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-313-ghost-find-demo-repos-command-in-docs.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

`docs/COMMANDS.md` documents a `/ll:find_demo_repos` command in two locations:
1. **Lines 169-176**: Full detailed documentation section under "Auditing & Analysis"
2. **Line 294**: Quick Reference table row

No `commands/find_demo_repos.md` file exists. The command was erroneously documented during ENH-275, which mistakenly assumed the command file existed.

### Key Discoveries
- Ghost entry at `docs/COMMANDS.md:169-176` (detailed section)
- Ghost entry at `docs/COMMANDS.md:294` (quick reference table)
- No `commands/find_demo_repos.md` exists in `commands/` directory
- Command not registered in `plugin.json`
- Counts in README.md and ARCHITECTURE.md already corrected to 34 in commit `3b78009`

## Desired End State

- `docs/COMMANDS.md` no longer references `find_demo_repos`
- COMMANDS.md documents exactly 34 commands, matching the 34 command files
- All count references remain consistent at 34

### How to Verify
- `find_demo_repos` does not appear in `docs/COMMANDS.md`
- Command count in COMMANDS.md matches actual command file count (34)

## What We're NOT Doing

- Not creating the command file (Option B) — command was never implemented
- Not modifying README.md or ARCHITECTURE.md — counts already correct at 34

## Solution Approach

Option A from the issue: Delete the ghost entry from both locations in COMMANDS.md.

## Implementation Phases

### Phase 1: Remove Ghost Entry from COMMANDS.md

#### Changes Required

**File**: `docs/COMMANDS.md`

1. Delete lines 169-176 (the detailed `/ll:find_demo_repos` section)
2. Delete line 294 (the quick reference table row)

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c find_demo_repos docs/COMMANDS.md` returns 0
- [ ] Command file count matches documented count (34)

## Testing Strategy

- Verify no references to `find_demo_repos` remain in COMMANDS.md
- Verify command counts are consistent across README.md, ARCHITECTURE.md, and COMMANDS.md
