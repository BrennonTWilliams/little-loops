# BUG-336: help.md inaccuracies - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P3-BUG-336-help-md-inaccuracies-stale-references.md
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

`commands/help.md` has 3 valid inaccuracies (item 2 was marked invalid in issue):

1. `confidence-check` skill exists at `skills/confidence-check/` but not listed in help.md
2. `ll-messages` CLI exists in pyproject.toml line 50 but not referenced in help.md
3. `analyze_log` listed as plugin command (line 86) but lives at `.claude/commands/analyze_log.md`, not in plugin `commands/`

## Solution

### Fix 1: Add `confidence-check` skill
Add to PLANNING & IMPLEMENTATION section's Skills line (line 64), alongside existing skills.

### Fix 2: Add `ll-messages` CLI reference
Add to META-ANALYSIS section's CLI line (line 152) since it's used with analyze-workflows.

### Fix 3: Remove `analyze_log` from plugin help
Remove `/ll:analyze_log` entry (lines 86-88) since it's a user-level command, not a plugin command. Also remove from Quick Reference Table and SCANNING & ANALYSIS section header if it becomes empty. Move `find_dead_code` and the skills/product-analyzer reference elsewhere.

## Verification
- Visual review of help.md for consistency
- All referenced skills/CLIs exist
