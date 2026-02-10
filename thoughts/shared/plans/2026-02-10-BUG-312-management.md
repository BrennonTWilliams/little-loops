# BUG-312: Commands crash on null project commands - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-312-commands-crash-on-null-project-commands.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `check_code.md:55` - lint block interpolates `lint_cmd` without null guard
- `check_code.md:77` - format block interpolates `format_cmd` without null guard
- `check_code.md:99` - types block interpolates `type_cmd` without null guard
- `check_code.md:111` - build block HAS null guard instruction (ENH-310 pattern)
- `check_code.md:141,145` - fix mode interpolates `lint_cmd` and `format_cmd` without guards
- `manage_issue.md:476` - test_cmd interpolated without guard
- `manage_issue.md:479` - lint_cmd interpolated without guard
- `manage_issue.md:482` - type_cmd has comment but no guard
- `manage_issue.md` - build_cmd missing entirely from Phase 4
- Templates (generic, Go, Java, etc.) legitimately set commands to `null`

### Patterns to Follow
- ENH-310 established the guard pattern at `check_code.md:111`: instruction text "Run X if `Y_cmd` is configured (non-null). Skip silently if not configured." + inline comment

## Desired End State

All nullable project commands (`lint_cmd`, `format_cmd`, `type_cmd`, `test_cmd`, `build_cmd`) are guarded in both `check_code.md` and `manage_issue.md`. When null, checks are skipped with SKIP status instead of crashing.

### How to Verify
- Read both files to confirm null-guard instructions are present for all command blocks
- Summary report in check_code shows SKIP as possible status for all checks
- manage_issue Phase 4 includes all five command types with guards

## What We're NOT Doing

- Not changing the config schema nullable types
- Not modifying template files
- Not adding runtime Python null-checking logic
- Not changing the plan template success criteria in manage_issue (those are examples, not executed)

## Solution Approach

Replicate the build_cmd guard pattern (instruction text + inline comment) to all unguarded command blocks.

## Implementation Phases

### Phase 1: Add null guards to check_code.md

#### Changes Required

**File**: `commands/check_code.md`

1. **Lint block** (line 46): Add guard instruction before code block
2. **Format block** (line 68): Add guard instruction before code block
3. **Types block** (line 90): Add guard instruction before code block
4. **Fix mode** (lines 141, 145): Add guard instructions for lint_cmd and format_cmd
5. **Summary report** (lines 169-172): Add SKIP as possible status for lint, format, types

#### Success Criteria
- [ ] All four check blocks (lint, format, types, build) have consistent null-guard instructions
- [ ] Fix mode has null-guard instructions for lint_cmd and format_cmd
- [ ] Summary report shows SKIP as possible status for all checks

### Phase 2: Add null guards to manage_issue.md Phase 4

#### Changes Required

**File**: `commands/manage_issue.md`

1. **Phase 4** (lines 470-488): Rewrite verification section with null-guard instructions for test_cmd, lint_cmd, type_cmd, and add build_cmd

#### Success Criteria
- [ ] Phase 4 has null-guard instructions for all five commands (test, lint, type, build, custom)
- [ ] Skipped checks are reported as SKIP in verification output

## Testing Strategy

- Read both modified files to verify correct guard pattern application
- Run `python -m pytest scripts/tests/` to ensure no regressions
- Run `ruff check scripts/` for lint
