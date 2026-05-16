---
discovered_commit: 925b8ce
discovered_branch: main
discovered_date: 2026-02-13T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-405: Document `ll-next-id` CLI tool

## Summary

The `ll-next-id` CLI tool is defined in `scripts/pyproject.toml` (entry point `little_loops.cli:main_next_id`) but is not documented in the README CLI Tools section, CLAUDE.md CLI Tools section, or CONTRIBUTING.md file tree.

## Current Behavior

The README CLI Tools section documents 11 tools but omits `ll-next-id`. The CLAUDE.md CLI Tools section also omits it. The CONTRIBUTING.md package tree listing under `cli/` does not include `next_id.py`. The tool is registered in `pyproject.toml` and functions correctly — it prints the next globally unique issue number.

## Expected Behavior

Add `ll-next-id` documentation to all three locations:
- **README.md**: Add an `ll-next-id` subsection to the CLI Tools section
- **CLAUDE.md**: Add `ll-next-id` to the CLI tools bullet list
- **CONTRIBUTING.md**: Add `next_id.py` to the `cli/` directory tree

## Motivation

All other CLI tools are documented in README, CLAUDE.md, and CONTRIBUTING.md. Omitting `ll-next-id` creates an inconsistency and makes the tool harder to discover for contributors and users.

## Proposed Solution

1. In `README.md` CLI Tools section, add:
   ```markdown
   ### ll-next-id

   Print the next available issue number:

   ```bash
   ll-next-id                       # Print next issue number (e.g., 042)
   ```
   ```

2. In `.claude/CLAUDE.md` CLI Tools section, add:
   ```
   - `ll-next-id` - Print next available issue number
   ```

3. In `CONTRIBUTING.md` package tree under `cli/`, add `next_id.py` entry.

## Scope Boundaries

- Only documentation changes — no code modifications to `ll-next-id` itself
- Does not cover adding `--help` improvements or new CLI flags
- Does not cover `docs/CLI-TOOLS-AUDIT.md` or other secondary docs

## Impact

- **Priority**: P4 - Low-priority documentation gap, no functional impact
- **Effort**: Small - Three small text additions to existing doc sections
- **Risk**: Low - Documentation-only changes, no code or behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `README.md`: Added `### ll-next-id` subsection to CLI Tools section
- `.claude/CLAUDE.md`: Added `ll-next-id` bullet to CLI Tools list
- `scripts/little_loops/cli/__init__.py`: Added `ll-next-id` to module docstring

### Notes
- CONTRIBUTING.md already had `next_id.py` in the directory tree (line 173), no change needed

### Verification Results
- Tests: PASS (2734 passed)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:manage-issue` - 2026-02-13T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1cee0634-9d0d-48fe-a632-6f4f97ccb3c3.jsonl`

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P4
