---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-071: capture_issue uses hardcoded values instead of config references

## Summary

The `/ll:capture_issue` command hardcodes directory paths and issue type prefixes instead of using `{{config.issues.*}}` template variables, making it inconsistent with other commands and breaking if users customize their config.

## Current Behavior

1. **Hardcoded directory paths** (lines 123-125, 146):
   ```bash
   ls -la {{config.issues.base_dir}}/bugs/*.md 2>/dev/null || true
   ls -la {{config.issues.base_dir}}/features/*.md 2>/dev/null || true
   ls -la {{config.issues.base_dir}}/enhancements/*.md 2>/dev/null || true
   ```
   Uses hardcoded `bugs/`, `features/`, `enhancements/` instead of deriving from `config.issues.categories.*.dir`.

2. **Hardcoded `completed/` path** (lines 143, 146, 218, 355):
   ```bash
   ls -la {{config.issues.base_dir}}/completed/*.md
   ```
   Should use `{{config.issues.completed_dir}}` like `manage_issue.md` does.

3. **Hardcoded issue prefixes** (line 250):
   ```bash
   grep -oE "(BUG|FEAT|ENH)-[0-9]+"
   ```
   Should derive from `config.issues.categories.*.prefix`.

4. **Unusable `{{config.issues.categories}}` display** (line 17):
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

- `commands/capture_issue.md:17` - Fix categories display
- `commands/capture_issue.md:123-125` - Consider dynamic category iteration
- `commands/capture_issue.md:143,146` - Use `{{config.issues.completed_dir}}`
- `commands/capture_issue.md:218,355` - Use `{{config.issues.completed_dir}}`
- `commands/capture_issue.md:250` - Document or parameterize prefix pattern

## Impact

- **Priority**: P3
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `consistency`

---

## Status

**Open** | Created: 2025-01-15 | Priority: P3
