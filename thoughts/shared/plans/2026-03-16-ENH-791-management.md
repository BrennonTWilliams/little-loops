# Plan: ENH-791 — normalize-issues: detect and fix type misclassifications

**Date**: 2026-03-16
**Issue**: P3-ENH-791
**Action**: improve
**File**: `commands/normalize-issues.md`

## Summary

Extend `/ll:normalize-issues` with a Step 1c that reads issue content and detects type misclassifications (e.g., an ENH describing a defect). Misclassified issues are renamed (prefix change) and moved to the correct directory.

## Changes Required

All changes are in `commands/normalize-issues.md`:

### 1. Step -0.5: Add type mismatch to --check mode (after line 70)
Add `[ID] normalize: type mismatch (ENH → BUG)` to the list of check-mode line formats.

### 2. Step 1c: New detection step (insert after Step 1b, ~line 177)
- Read each active issue file's content using the `Read` tool
- Apply keyword heuristics to infer type (BUG/FEAT/ENH)
- Flag issues where inferred type ≠ filename prefix with confidence ≥ 0.7
- Also flag when frontmatter `type:` field disagrees with filename prefix

### 3. Step 5: Add "Type Mismatch Fixes" sub-table (~line 253)
Add a sub-table after "Duplicate ID Renames" showing proposed reclassifications with confidence scores.

### 4. Step 6: Add cross-directory git mv variant (~line 266)
The existing step only renames within the same directory. Add a variant for type mismatches that moves files between directories.

### 5. Step 8: Update report (~line 329)
- Add `type mismatches detected/fixed: N` to the Summary block
- Add "Type Mismatch Fixes" table after "Duplicate ID Fixes"

## Success Criteria

- [ ] `--check` mode reports `[ID] normalize: type mismatch (ENH → BUG)` lines
- [ ] Step 1c detects type mismatches with confidence-scored heuristics
- [ ] Rename plan shows type mismatch table with confidence scores
- [ ] Step 6 handles cross-directory git mv for reclassified issues
- [ ] Report has "Type Mismatch Fixes" section and updated summary counts
- [ ] `--auto` mode applies reclassifications without prompting
