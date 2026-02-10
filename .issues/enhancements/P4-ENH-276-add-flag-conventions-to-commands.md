---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-276: Add flag conventions to commands

## Summary

Add `--flag` style modifier conventions to existing commands so users can adjust behavior without needing separate commands for each variant. Inspired by SuperClaude's `--think-hard`, `--focus security`, `--delegate` pattern.

## Current Behavior

Most commands have fixed behavior with no way to modify depth, focus area, or execution mode from user input. `/ll:manage_issue` is the exception — it already supports `--plan-only`, `--resume`, and `--gates` flags. However, this pattern is not standardized or documented as a convention, and other commands like `/ll:scan_codebase` and `/ll:audit_architecture` have no flag support.

## Expected Behavior

Define a standard set of flags parsed from the user's text input (not actual CLI args):

- `--quick` — Reduce analysis depth for faster results
- `--deep` — Increase thoroughness, accept longer execution time
- `--focus [area]` — Narrow scope to a specific area (e.g., `--focus security`, `--focus performance`)
- `--dry-run` — Show what would happen without making changes

Commands should document supported flags in their help text. Flags are optional — commands work unchanged without them.

### Priority commands to update:
- `/ll:scan_codebase` — `--quick`, `--deep`, `--focus [area]`
- `/ll:manage_issue` — `--dry-run`, `--quick`
- `/ll:audit_architecture` — `--focus [area]`, `--deep`

## Files to Modify

- `commands/scan_codebase.md` — Add flag parsing and conditional behavior
- `commands/manage_issue.md` — Add flag parsing and conditional behavior
- `commands/audit_architecture.md` — Add flag parsing and conditional behavior
- `commands/help.md` — Document the flag convention

## Impact

- **Priority**: P4
- **Effort**: Medium
- **Risk**: Low — flags are additive, no existing behavior changes

## Labels

`enhancement`, `commands`, `ux`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P4

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID (after update)
- Updated Current Behavior: `manage_issue` already supports `--plan-only`, `--resume`, `--gates` flags
- Issue scope refined to standardizing the flag convention across other commands and documenting it in help
