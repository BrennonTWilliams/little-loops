---
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit_claude_config
---

# ENH-356: Document orphan command and CLI tools in CLAUDE.md

## Summary

4 components exist in the project but are not documented in CLAUDE.md:

1. **Command**: `find_dead_code` — exists in `commands/` but not listed in the Commands section
2. **CLI tool**: `ll-sync` — defined in `pyproject.toml` but not listed in CLI Tools section
3. **CLI tool**: `ll-verify-docs` — defined in `pyproject.toml` but not listed in CLI Tools section
4. **CLI tool**: `ll-check-links` — defined in `pyproject.toml` but not listed in CLI Tools section

## Current Behavior

The CLAUDE.md Commands section lists commands grouped by capability but omits `find_dead_code` (which exists in `commands/find_dead_code.md`). The CLI Tools section lists 8 tools but omits `ll-sync`, `ll-verify-docs`, and `ll-check-links` (all defined in `scripts/pyproject.toml`).

## Expected Behavior

All commands in `commands/` and all CLI tools in `pyproject.toml` should be documented in their respective CLAUDE.md sections so users can discover them.

## Location

- **File**: `.claude/CLAUDE.md`

## Proposed Solution

- Add `find_dead_code` to the **Code Quality** commands group (or **Issue Discovery** depending on categorization)
- Add `ll-sync`, `ll-verify-docs`, `ll-check-links` to the CLI Tools section with brief descriptions

## Scope Boundaries

- Only update `.claude/CLAUDE.md` — README.md and docs/COMMANDS.md were already updated in ENH-275
- Do not restructure existing sections or reorder entries

## Impact

- **Priority**: P4 - Documentation completeness, not blocking any functionality
- **Effort**: Small - Simple text additions to an existing file
- **Risk**: Low - Documentation-only change, no code impact
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`

## Session Log
- `/ll:manage-issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/<project>/4f2cc317-481c-47c3-90c7-4ac9fc0391c9.jsonl`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `.claude/CLAUDE.md`: Added `find_dead_code` to Code Quality commands group
- `.claude/CLAUDE.md`: Added `ll-sync`, `ll-verify-docs`, `ll-check-links` to CLI Tools section

### Verification Results
- Tests: N/A (documentation-only change)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Status

**Completed** | Created: 2026-02-12 | Priority: P4
