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

## Location

- **File**: `.claude/CLAUDE.md`

## Fix

- Add `find_dead_code` to the Issue Discovery commands list
- Add `ll-sync`, `ll-verify-docs`, `ll-check-links` to the CLI Tools section with brief descriptions

## Impact

Low — documentation completeness improvement.
