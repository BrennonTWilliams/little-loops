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

## Steps to Reproduce

1. Open `commands/scan_codebase.md` and inspect the `allowed-tools` frontmatter (line 4)
2. Search the command body for tool references: `Task` (lines 68, 72, 104, 137), `TodoWrite` (line 27)
3. Observe that `allowed-tools` only lists `Bash(git:*, gh:*)` — omitting `Task` and `TodoWrite`
4. Repeat for `commands/scan_product.md`: `Skill` (line 138), `TodoWrite` (line 33) are used but not declared

## Actual Behavior

Both `scan_codebase.md` and `scan_product.md` declare `allowed-tools: Bash(git:*, gh:*)` in frontmatter, but their command bodies invoke tools not listed:
- `scan_codebase.md` uses `Task` and `TodoWrite`
- `scan_product.md` uses `Skill` and `TodoWrite`

## Current Behavior

If the Claude Code plugin framework enforces `allowed-tools` restrictions, these tool invocations would be blocked at runtime.

## Expected Behavior

Update `allowed-tools` to include all tools actually used in the command body:
- `scan_codebase.md`: Add `Task` and `TodoWrite`
- `scan_product.md`: Add `Skill` and `TodoWrite`

## Motivation

This bug would:
- Prevent potential runtime tool blocking if the plugin framework enforces `allowed-tools` restrictions
- Business value: Ensures scan commands can use all required tools without silent failures
- Technical debt: Aligns declared tool permissions with actual tool usage, reducing configuration drift

## Root Cause

- **File**: `commands/scan_codebase.md` and `commands/scan_product.md`
- **Anchor**: `in allowed-tools frontmatter`
- **Cause**: The `allowed-tools` lists were authored when the commands only used `Bash(git:*, gh:*)` but the command bodies later evolved to use `Task`, `Skill`, and `TodoWrite` tools without updating the frontmatter accordingly

## Implementation Steps

1. Audit tool usage in `commands/scan_codebase.md` body to identify all tools invoked (`Task`, `TodoWrite`, etc.)
2. Audit tool usage in `commands/scan_product.md` body to identify all tools invoked (`Skill`, `TodoWrite`, etc.)
3. Update `allowed-tools` frontmatter in both files to include all tools actually used
4. Test both scan commands to verify they execute without tool blocking

## Integration Map

### Files to Modify
- `commands/scan_codebase.md` — update `allowed-tools` frontmatter to include `Task` and `TodoWrite`
- `commands/scan_product.md` — update `allowed-tools` frontmatter to include `Skill` and `TodoWrite`

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- Other commands with `allowed-tools` that may also be out of date (see BUG-365)

### Tests
- N/A — frontmatter-only change; verified by running affected scan commands

### Documentation
- N/A — internal configuration fix

### Configuration
- N/A

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Blocked By

- ENH-399: Add allowed-tools to commands — broader allowed-tools audit should complete first to avoid conflicting changes

## Labels

`bug`, `commands`, `config`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `commands/scan_codebase.md`: Added `Task` and `TodoWrite` to `allowed-tools` frontmatter
- `commands/scan_product.md`: Added `Skill` and `TodoWrite` to `allowed-tools` frontmatter

### Verification Results
- Tests: PASS (not applicable — frontmatter-only change)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13
- `/ll:manage_issue` - 2026-02-13T01:35:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-bug-363-20260213-013329/688220dc-7b35-4713-b5d9-56fef6be4510.jsonl`

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P4
