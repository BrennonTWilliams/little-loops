---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-071: capture_issue uses hardcoded values instead of config references

## Summary

The `/ll:capture-issue` command hardcodes directory paths and issue type prefixes instead of using `{{config.issues.*}}` template variables, making it inconsistent with other commands and breaking if users customize their config.

## Current Behavior

1. **Hardcoded directory paths** (lines 137-139):
   ```bash
   ls -la {{config.issues.base_dir}}/bugs/*.md 2>/dev/null || true
   ls -la {{config.issues.base_dir}}/features/*.md 2>/dev/null || true
   ls -la {{config.issues.base_dir}}/enhancements/*.md 2>/dev/null || true
   ```
   Uses hardcoded `bugs/`, `features/`, `enhancements/` instead of deriving from `config.issues.categories.*.dir`.

2. **Hardcoded `completed/` path** (lines 157, 160, 258, 446, 451):
   ```bash
   ls -la {{config.issues.base_dir}}/completed/*.md
   ```
   Should use `{{config.issues.completed_dir}}` like `manage_issue.md` does.

3. **Hardcoded issue prefixes** (line 304):
   ```bash
   grep -oE "(BUG|FEAT|ENH)-[0-9]+"
   ```
   Should derive from `config.issues.categories.*.prefix`.

4. **Unusable `{{config.issues.categories}}` display** (line 20):
   ```markdown
   - **Categories**: `{{config.issues.categories}}`
   ```
   This is an object, not a string, so it renders as `[object Object]`.

## Expected Behavior

- Use `{{config.issues.completed_dir}}` for completed directory references
- Derive category directories from config dynamically or document the assumption
- Either remove the categories display or format it properly
- Match patterns used in `manage_issue.md`, `ready_issue.md`, and other commands

## Files to Modify

- `commands/capture_issue.md:20` - Fix categories display
- `commands/capture_issue.md:137-139` - Consider dynamic category iteration
- `commands/capture_issue.md:157,160,258` - Use `{{config.issues.completed_dir}}`
- `commands/capture_issue.md:446,451` - Use `{{config.issues.completed_dir}}`
- `commands/capture_issue.md:304` - Document or parameterize prefix pattern

## Impact

- **Priority**: P3
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `consistency`

---

## Verification Notes

**Verified: 2026-01-19**

Line numbers updated to reflect current state of `commands/capture_issue.md`. Issue remains valid - the file still uses hardcoded directory names and prefix patterns instead of deriving them from configuration.

---

## Status

**Open** | Created: 2025-01-15 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-20
- **Status**: Completed

### Changes Made
- `commands/capture_issue.md:20`: Replaced unusable `{{config.issues.categories}}` with `{{config.issues.completed_dir}}`
- `commands/capture_issue.md:133-145`: Replaced hardcoded directory listing with dynamic glob iteration pattern that skips completed directory
- `commands/capture_issue.md:162-166`: Used `{{config.issues.completed_dir}}` for completed directory path
- `commands/capture_issue.md:263`: Used `{{config.issues.completed_dir}}` in completed issue path display
- `commands/capture_issue.md:309`: Added note about prefix pattern using default category prefixes
- `commands/capture_issue.md:452-457`: Used `{{config.issues.completed_dir}}` in reopen action with updated documentation note

### Verification Results
- Tests: N/A (no Python changes)
- Lint: PASS
