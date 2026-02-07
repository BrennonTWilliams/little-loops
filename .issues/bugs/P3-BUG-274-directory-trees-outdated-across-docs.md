---
discovered_commit: 59ef770
discovered_branch: main
discovered_date: 2026-02-07T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-274: Directory trees outdated across README, CONTRIBUTING, and ARCHITECTURE docs

## Summary

Documentation issue found by `/ll:audit_docs`. The directory tree listings in README.md, CONTRIBUTING.md, and docs/ARCHITECTURE.md are missing recently added Python modules, the `hooks/scripts/lib/` directory, and the `loops/` directory.

## Location

- **Files**: `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`
- **Sections**: Plugin Structure / Project Structure / Directory Structure

## Missing Items

### Python modules missing from all three files
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

### Hook file missing
- `hooks/scripts/lib/common.sh` (shared shell functions)

### New directory missing from README
- `loops/` directory with 5 built-in loop YAML files (recently shipped)

### ARCHITECTURE.md specific
- Line 62: Shows `plugin.json` at root — should be `.claude-plugin/plugin.json`

## Files to Update

1. **README.md** lines 587-631: Update directory tree
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
