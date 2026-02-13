# ENH-356: Document orphan command and CLI tools in CLAUDE.md - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-356-document-orphan-command-and-cli-tools.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

`.claude/CLAUDE.md` has two sections that need updates:

### Commands Section (line 54)
- **Code Quality** category currently lists: `check_code`, `run_tests`, `audit_docs`
- Missing: `find_dead_code` (exists at `commands/find_dead_code.md`)

### CLI Tools Section (lines 104-111)
- Currently lists 8 tools (ll-auto through ll-deps)
- Missing 3 tools defined in `scripts/pyproject.toml:53,56,57`:
  - `ll-sync` - Sync local .issues/ files with GitHub Issues (source: `cli/sync.py`)
  - `ll-verify-docs` - Verify documented counts match actual file counts (source: `cli/docs.py`)
  - `ll-check-links` - Check markdown documentation for broken links (source: `cli/docs.py`)

## Desired End State

All 4 orphaned components documented in their respective CLAUDE.md sections.

### How to Verify
- `find_dead_code` appears in Code Quality commands group
- `ll-sync`, `ll-verify-docs`, `ll-check-links` appear in CLI Tools section
- Format matches existing patterns

## What We're NOT Doing

- Not updating README.md or docs/COMMANDS.md (already done in ENH-275 per issue)
- Not restructuring existing sections or reordering entries
- Not adding detailed descriptions beyond the existing pattern

## Implementation Phases

### Phase 1: Update CLAUDE.md

#### Changes Required

**File**: `.claude/CLAUDE.md`

1. **Line 54** - Add `find_dead_code` to Code Quality:
   - From: `- **Code Quality**: \`check_code\`, \`run_tests\`, \`audit_docs\``
   - To: `- **Code Quality**: \`check_code\`, \`run_tests\`, \`audit_docs\`, \`find_dead_code\``

2. **Lines 108-111** - Add 3 CLI tools after `ll-deps`:
   - `- \`ll-sync\` - Sync local issues with GitHub Issues`
   - `- \`ll-verify-docs\` - Verify documented counts match actual file counts`
   - `- \`ll-check-links\` - Check markdown documentation for broken links`

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] All 4 components now appear in CLAUDE.md
- [ ] Format matches existing entries exactly
