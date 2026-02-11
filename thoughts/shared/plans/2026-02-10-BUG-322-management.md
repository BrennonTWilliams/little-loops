# BUG-322: Old v1.0 template section names in 3 files - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P3-BUG-322-old-v1-template-section-names-in-3-files.md
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Solution

Simple string replacements in 3 files:

1. `scripts/little_loops/issue_lifecycle.py:468` — `Reproduction Steps` → `Steps to Reproduce`
2. `scripts/little_loops/issue_lifecycle.py:472` — `Proposed Fix` → `Proposed Solution`
3. `scripts/tests/test_issue_discovery.py:125` — `Proposed Fix` → `Proposed Solution`
4. `commands/find_dead_code.md:181` — `Proposed Fix` → `Proposed Solution`

## Verification
- [x] Tests pass
- [x] Grep confirms no remaining old section names
