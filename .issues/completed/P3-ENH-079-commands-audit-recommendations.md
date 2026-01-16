---
discovered_commit: 1b47d0d
discovered_branch: main
discovered_date: 2026-01-16
discovered_by: manual_audit
---

# ENH-079: Implement Commands Audit Recommendations

## Summary

Implement the recommendations identified during the comprehensive audit of the 21 commands in the little-loops plugin. The audit found 5 warnings and 12 suggestions for improvement.

## Context

A full audit of all commands in `commands/*.md` was performed to assess quality, consistency, and best practices compliance. Overall quality score was 8.5/10 with no critical issues.

## High Priority

### 1. Fix Typo in commit.md
- **File**: `commands/commit.md:38`
- **Issue**: Typo "PATTERMS_LIST" should be "PATTERNS_LIST"
- **Effort**: Small

### 2. Add Arguments Section to describe_pr.md
- **File**: `commands/describe_pr.md`
- **Issue**: Missing `$ARGUMENTS` block; could benefit from optional `base_branch` argument
- **Effort**: Small

## Medium Priority

### 3. Standardize Argument Default Documentation
- **Issue**: Some commands document defaults in frontmatter, others in body text
- **Files**: `check_code.md`, `run_tests.md`, `toggle_autoprompt.md`
- **Fix**: Add explicit `default` field to argument definitions
- **Effort**: Small

### 4. Add --dry-run Flag to File-Modifying Commands
- **Files**: `normalize_issues.md`, `prioritize_issues.md`, `verify_issues.md`
- **Issue**: Commands make file changes without preview option
- **Fix**: Add `--dry-run` flag to show changes without applying
- **Effort**: Medium

### 5. Document Exit Codes for All Commands
- **Issue**: Only `audit_claude_config.md` documents exit codes
- **Fix**: Add exit code section to all commands for automation compatibility
- **Effort**: Medium

### 6. Add Arguments to verify_issues.md
- **File**: `commands/verify_issues.md`
- **Issue**: No arguments, but could benefit from `issue_id` parameter like `ready_issue`
- **Effort**: Small

### 7. Fix test_dir Config Reference
- **File**: `commands/run_tests.md:20`
- **Issue**: References `{{config.project.test_dir}}` which may not be in schema
- **Fix**: Verify in config-schema.json or use documented path
- **Effort**: Small

## Low Priority

### 8. Consider Dynamic Help Generation
- **File**: `commands/help.md`
- **Issue**: Static command list may drift from actual commands
- **Fix**: Generate help dynamically from command files
- **Effort**: Large

### 9. Add Verbose Mode to Scanning Commands
- **Files**: `scan_codebase.md`, `verify_issues.md`, `normalize_issues.md`
- **Fix**: Add `--verbose` flag for detailed output
- **Effort**: Medium

### 10. Add Command Aliases
- **Issue**: Frequently used commands could have short aliases
- **Suggested aliases**:
  - `commit` -> `ci`
  - `check_code` -> `cc`
  - `run_tests` -> `rt`
- **Effort**: Medium

### 11. Add Integration Sections
- **Files missing Integration section**:
  - `commit.md`
  - `help.md`
  - `toggle_autoprompt.md`
- **Effort**: Small

### 12. Standardize Example Sections
- **Issue**: Some commands have 5+ examples, others have 1-2
- **Fix**: Standardize to 3-5 examples per command
- **Effort**: Small

## Proposed Approach

Split into multiple smaller tasks:
1. Quick fixes (items 1, 2, 3, 6, 7, 11, 12) - single session
2. Flag additions (items 4, 5, 9) - separate session
3. Larger changes (items 8, 10) - defer or create separate issues

## Impact

- **Severity**: Low
- **Effort**: Medium (total)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `commands`, `quality`

---

## Status

**Open** | Created: 2026-01-16 | Priority: P3
