---
discovered_commit: 43094b0
discovered_branch: main
discovered_date: 2026-01-16T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-053: plugin.json path incorrect in README structure diagram

## Summary

README.md Plugin Structure section shows `plugin.json` at project root, but the actual plugin manifest is located at `.claude-plugin/plugin.json`. The root `plugin.json` was deleted (visible in git status).

## Location

- **Files**: README.md
- **Lines**: 500-502

## Current Content

README.md (lines 500-502):
```markdown
little-loops/
├── plugin.json           # Plugin manifest
├── config-schema.json    # Configuration schema
```

## Problem

1. The `plugin.json` file does not exist at the project root (git status shows ` D plugin.json` - deleted)
2. The actual plugin manifest is at `.claude-plugin/plugin.json`
3. This creates confusion for developers trying to understand the plugin structure

### Verification

```bash
$ ls -la plugin.json
ls: plugin.json: No such file or directory

$ ls -la .claude-plugin/plugin.json
-rw-r--r--  1 user  staff  432 Jan 16 00:00 .claude-plugin/plugin.json
```

## Expected Content

README.md (lines 500-502):
```markdown
little-loops/
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
├── config-schema.json    # Configuration schema
```

Or alternatively, if the plugin format requires the manifest at root, restore the `plugin.json` file to the root directory.

## Files to Update

1. **README.md**
   - Lines 500-502: Update directory structure to show correct plugin manifest location

## Impact

- **Severity**: Medium (misleading documentation, potential confusion for contributors)
- **Effort**: Small (structure diagram update)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Resolved** | Created: 2026-01-16 | Resolved: 2026-01-16 | Priority: P2

## Resolution

The root `plugin.json` was accidentally deleted from the working directory. The README was correct - Claude Code plugins expect `plugin.json` at the project root. Restored the file with `git restore plugin.json`. The `.claude-plugin/plugin.json` is a separate file (incomplete, only has hooks) and should not be the primary manifest.
