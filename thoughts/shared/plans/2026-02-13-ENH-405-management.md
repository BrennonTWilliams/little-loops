# ENH-405: Document ll-next-id CLI tool - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-405-document-ll-next-id-cli-tool.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

`ll-next-id` is fully implemented (`scripts/little_loops/cli/next_id.py`), registered in `pyproject.toml:58`, imported/exported in `cli/__init__.py`, and tested. However, it is missing from documentation in:
- README.md CLI Tools section (lines 198-315)
- .claude/CLAUDE.md CLI Tools bullet list (lines 101-114)
- cli/__init__.py module docstring (lines 1-13)

Note: CONTRIBUTING.md already has `next_id.py` in the directory tree at line 173.

## Desired End State

All documentation files list `ll-next-id` alongside the other CLI tools.

## What We're NOT Doing

- Not modifying ll-next-id code itself
- Not adding --help improvements or new CLI flags
- Not updating secondary docs (CLI-TOOLS-AUDIT.md, etc.)

## Implementation Phases

### Phase 1: Add ll-next-id to README.md

Insert `### ll-next-id` subsection after `ll-deps` (line 305) and before `ll-verify-docs / ll-check-links` (line 307).

### Phase 2: Add ll-next-id to CLAUDE.md

Add bullet item after `ll-check-links` entry (line 114).

### Phase 3: Add ll-next-id to cli/__init__.py docstring

Add `- ll-next-id: Print next globally unique issue number` after line 12.

### Success Criteria
- [ ] All three files updated
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
