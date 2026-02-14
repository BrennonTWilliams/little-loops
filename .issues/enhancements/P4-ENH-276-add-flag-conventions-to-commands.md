---
discovered_date: 2026-02-08
discovered_by: manual-review
---

# ENH-276: Add flag conventions to commands

## Summary

Add `--flag` style modifier conventions to existing commands so users can adjust behavior without needing separate commands for each variant. Inspired by SuperClaude's `--think-hard`, `--focus security`, `--delegate` pattern.

## Current Behavior

Most commands have fixed behavior with no way to modify depth, focus area, or execution mode from user input. `/ll:manage-issue` is the exception — it already supports `--plan-only`, `--resume`, and `--gates` flags. However, this pattern is not standardized or documented as a convention, and other commands like `/ll:scan-codebase` and `/ll:audit-architecture` have no flag support.

## Expected Behavior

Define a standard set of flags parsed from the user's text input (not actual CLI args):

- `--quick` — Reduce analysis depth for faster results
- `--deep` — Increase thoroughness, accept longer execution time
- `--focus [area]` — Narrow scope to a specific area (e.g., `--focus security`, `--focus performance`)
- `--dry-run` — Show what would happen without making changes

Commands should document supported flags in their help text. Flags are optional — commands work unchanged without them.

### Priority commands to update:
- `/ll:scan-codebase` — `--quick`, `--deep`, `--focus [area]`
- `/ll:manage-issue` — `--dry-run`, `--quick`
- `/ll:audit-architecture` — `--focus [area]`, `--deep`

## Files to Modify

- `commands/scan-codebase.md` — Add flag parsing and conditional behavior
- `skills/manage-issue/SKILL.md` — Add flag parsing and conditional behavior (manage-issue is a skill, not a command)
- `commands/audit-architecture.md` — Add flag parsing and conditional behavior
- `commands/help.md` — Document the flag convention

## Motivation

This enhancement would:
- Improve user control: users can adjust command behavior without needing separate command variants
- Standardize existing patterns: `manage-issue` already supports flags but the convention isn't documented
- Reduce command proliferation: flags allow one command to serve multiple use cases

## Scope Boundaries

- **In scope**: Defining flag conventions, adding flag support to scan-codebase, manage-issue, audit-architecture
- **Out of scope**: Adding flags to all commands at once, creating a generic flag parsing library

## Implementation Steps

1. Document the flag convention (syntax, supported flags, parsing approach)
2. Add `--quick`/`--deep`/`--focus` flag parsing to `scan-codebase.md`
3. Add `--dry-run`/`--quick` flag parsing to `skills/manage-issue/SKILL.md`
4. Add `--focus`/`--deep` flag parsing to `audit-architecture.md`
5. Update `help.md` to document the flag convention

## Integration Map

### Files to Modify
- `commands/scan-codebase.md` - Add flag parsing
- `skills/manage-issue/SKILL.md` - Add flag parsing (manage-issue is a skill, not a command)
- `commands/audit-architecture.md` - Add flag parsing
- `commands/help.md` - Document convention

### Dependent Files (Callers/Importers)
- N/A - commands are user-invoked

### Similar Patterns
- `commands/manage-issue.md` already supports `--plan-only`, `--resume`, `--gates` flags

### Tests
- N/A — command markdown files are not Python-testable; verified via manual invocation

### Documentation
- `commands/help.md` — add flag convention reference section
- `docs/COMMANDS.md` — document standard flags (--quick, --deep, --focus, --dry-run)
- `CONTRIBUTING.md` — add flag convention guidelines for command authors

### Configuration
- N/A

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

- **Verified**: 2026-02-13
- **Verdict**: CORRECTED
- **File path fixed**: `commands/manage-issue.md` corrected to `skills/manage-issue/SKILL.md` (manage-issue is a skill, not a command) in Files to Modify, Implementation Steps, and Integration Map
- `manage-issue` already supports `--plan-only`, `--resume`, `--gates` flags (confirmed at skills/manage-issue/SKILL.md)
- Issue scope refined to standardizing the flag convention across other commands/skills and documenting it in help

---

## Tradeoff Review Note

**Reviewed**: 2026-02-11 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | LOW |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - Needs scope clarification before implementation:
1. Which commands/flags should be implemented first as proof-of-concept?
2. What's the rollout strategy (all at once vs incremental)?
3. Are all 4 flags needed for all commands?
4. Use `manage-issue`'s existing flags as reference implementation to document and standardize

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | LOW |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - Decent UX improvement but needs scope refinement: which commands first, all flags needed, rollout strategy. Consistent across two reviews.
