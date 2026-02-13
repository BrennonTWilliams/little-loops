---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-363: allowed-tools mismatch in scan_codebase and scan_product commands

## Summary

Two commands declare `allowed-tools` in frontmatter that don't match the tools actually used in their command body:

1. **`scan_codebase.md`**: Body uses `Task` tool (lines 68, 72, 104, 137) and `TodoWrite` (line 27), but `allowed-tools` only lists `Bash(git:*, gh:*)`.
2. **`scan_product.md`**: Body uses `Skill` tool (line 138) and `TodoWrite` (line 33), but `allowed-tools` only lists `Bash(git:*, gh:*)`.

## Location

- **Files**: `commands/scan_codebase.md` (frontmatter), `commands/scan_product.md` (frontmatter)

## Current Behavior

If the Claude Code plugin framework enforces `allowed-tools` restrictions, these tool invocations would be blocked at runtime.

## Expected Behavior

Update `allowed-tools` to include all tools actually used in the command body:
- `scan_codebase.md`: Add `Task` (or keep `Bash` only if `allowed-tools` is advisory)
- `scan_product.md`: Add `Skill` (or keep `Bash` only if `allowed-tools` is advisory)

Note: Also update `TodoWrite` references to current `TaskCreate`/`TaskUpdate`/`TaskList` names.

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Blocked By

- ENH-399: Add allowed-tools to commands — broader allowed-tools audit should complete first to avoid conflicting changes

## Labels

`bug`, `commands`, `config`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
