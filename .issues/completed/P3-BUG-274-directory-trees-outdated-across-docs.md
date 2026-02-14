---
discovered_commit: 59ef770
discovered_branch: main
discovered_date: 2026-02-07T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-274: Directory trees outdated across README, CONTRIBUTING, and ARCHITECTURE docs

## Summary

Documentation issue found by `/ll:audit-docs`. The directory tree listings in README.md, CONTRIBUTING.md, and docs/ARCHITECTURE.md are missing recently added Python modules, the `hooks/scripts/lib/` directory, and the `loops/` directory.

## Location

- **Files**: `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`
- **Sections**: Plugin Structure / Project Structure / Directory Structure

## Missing Items

### Python modules missing from README.md and ARCHITECTURE.md
- `scripts/little_loops/frontmatter.py`
- `scripts/little_loops/doc_counts.py`
- `scripts/little_loops/link_checker.py`
- `scripts/little_loops/cli_args.py`
- `scripts/little_loops/sync.py`
- `scripts/little_loops/goals_parser.py`
- `scripts/little_loops/sprint.py` (in CONTRIBUTING, not README/ARCH)
- `scripts/little_loops/fsm/concurrency.py`
- `scripts/little_loops/parallel/file_hints.py`
- `scripts/little_loops/parallel/overlap_detector.py`

### Python modules missing from CONTRIBUTING.md only
- `scripts/little_loops/frontmatter.py`
- `scripts/little_loops/doc_counts.py`
- `scripts/little_loops/link_checker.py`

### Hook file missing
- `hooks/scripts/lib/common.sh` (shared shell functions)

### New directory missing from README
- `loops/` directory with 5 built-in loop YAML files (recently shipped)

### ARCHITECTURE.md specific
- Line 62: Shows `plugin.json` at root — should be `.claude-plugin/plugin.json`

## Files to Update

1. **README.md** lines 587-632: Update directory tree
2. **CONTRIBUTING.md** lines 107-192: Update directory tree
3. **docs/ARCHITECTURE.md** lines 60-161: Update directory tree

## Impact

- **Severity**: Medium (contributors and users see stale project structure)
- **Effort**: Medium (three files to update)
- **Risk**: Low

## Labels

`bug`, `documentation`

---

## Status

**Open** | Created: 2026-02-07 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `README.md`: Added `loops/` directory, `fsm/` subdirectory, and 13 missing Python modules to directory tree
- `CONTRIBUTING.md`: Added `loops/` directory, 3 missing Python modules (`frontmatter.py`, `doc_counts.py`, `link_checker.py`), `__init__.py` and `tasks/` to parallel, `INDEX.md` to docs listing
- `docs/ARCHITECTURE.md`: Fixed `plugin.json` path from root to `.claude-plugin/plugin.json`, updated command count from 34 to 35, added `loops/` directory, added 7 missing Python modules, added `concurrency.py` and `fsm-loop-schema.json` to fsm, added `file_hints.py` and `overlap_detector.py` to parallel, added `lib/common.sh` to hooks/scripts, added `optimize-prompt-hook.md` to hooks/prompts

### Verification Results
- Tests: PASS (2619 passed)
- Lint: PASS (pre-existing issues only)
- Types: PASS
