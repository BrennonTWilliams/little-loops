---
discovered_date: 2026-04-07
discovered_by: split-from-ENH-494
---

# ENH-977: Add `ll-verify-skills` CLI Lint Command

## Summary

Add a `ll-verify-skills` CLI tool that enforces the 500-line SKILL.md limit introduced by ENH-494. The tool scans all `skills/*/SKILL.md` files, flags any that exceed 500 lines, and exits non-zero if violations are found — enabling CI enforcement of the companion-file convention.

## Current Behavior

There is no automated check for SKILL.md file size. The 500-line convention (established by ENH-494) is documented in `CONTRIBUTING.md` but not machine-enforced. Violations can silently accumulate.

## Expected Behavior

- `ll-verify-skills` scans all `skills/*/SKILL.md` files
- Prints a violation line for each file over 500 lines (with actual line count)
- Exits 0 if all files are within limit; exits 1 if any exceed it
- Companion files (non-`SKILL.md` files in `skills/<name>/`) are not counted toward the limit
- Integrates into CI alongside `ll-verify-docs` and `ll-check-links`

## Motivation

ENH-494 establishes the 500-line convention and companion-file pattern, but only as a documented standard. Without a lint check, oversized skills can silently re-emerge (as already happened: `confidence-check` grew 60 lines between 2026-04-02 and 2026-04-07). A cheap automated check closes this loop.

## Proposed Solution

Extend `scripts/little_loops/doc_counts.py` with a skill-size checker function and add a CLI entry point following the established `ll-verify-docs` pattern.

## Implementation Steps

1. Extend `scripts/little_loops/doc_counts.py:61–79` — add a `check_skill_sizes(limit: int = 500) -> list[tuple[Path, int]]` function using `rglob("SKILL.md")` (mirrors `count_files()` at the same location); return list of `(path, line_count)` for files exceeding `limit`
2. Add `main_verify_skills()` entry point in `scripts/little_loops/cli/docs.py` — follow `main_verify_docs()` pattern at `docs.py:9–98`; print violations, exit 1 on any, exit 0 on clean
3. Register entry point in `scripts/pyproject.toml:57–58` — add `ll-verify-skills = "little_loops.cli:main_verify_skills"` alongside `ll-verify-docs`
4. Update `scripts/little_loops/cli/__init__.py:22,40,51` — add `main_verify_skills` import and `__all__` entry (follow `main_verify_docs` at lines 22, 40, 51)
5. Add tests:
   - Add `TestMainVerifySkills` class to `scripts/tests/test_cli_docs.py` — follow the 22-test `TestMainVerifyDocs` pattern (line 20, `sys.argv`-patch approach)
   - Add `scripts/tests/test_skill_size_checker.py` — follow `TestCountFiles` at `test_doc_counts.py:18–53`; test that SKILL.md > 500 lines is flagged, ≤ 500 passes, and companion files alongside `SKILL.md` are not counted
6. Register in all CLI tool listings:
   - `commands/help.md:220` — "CLI TOOLS" section; add `ll-verify-skills` entry
   - `.claude/CLAUDE.md:113` — CLI Tools section; add `ll-verify-skills` line after `ll-verify-docs`
   - `README.md:433–441` — add `ll-verify-skills` subsection alongside `ll-verify-docs`
   - `docs/reference/CLI.md` — add `ll-verify-skills` reference section after `ll-verify-docs` (line 904)
7. Update skill templates that enumerate CLI tools:
   - `skills/init/SKILL.md:440,519,543` — allowed-tools block template and completion message template list `ll-verify-docs`; add `ll-verify-skills` at each occurrence
   - `skills/configure/areas.md:793` — description string enumerates all 12 `ll-` CLI tools; append `ll-verify-skills`

## Scope Boundaries

- **In scope**: New CLI tool, tests, registration in all tool listings
- **Out of scope**: Changing the 500-line limit itself (change `CONTRIBUTING.md` instead), modifying skill content

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py:61–79` — add `check_skill_sizes()` function
- `scripts/little_loops/cli/docs.py:9–98` — add `main_verify_skills()` entry point
- `scripts/pyproject.toml:57–58` — register `ll-verify-skills` entry point
- `scripts/little_loops/cli/__init__.py:22,40,51` — add import and `__all__` entry
- `scripts/tests/test_cli_docs.py` — add `TestMainVerifySkills` class
- `commands/help.md:220` — add `ll-verify-skills` to CLI TOOLS list
- `.claude/CLAUDE.md:113` — add `ll-verify-skills` to CLI Tools section
- `README.md:433–441` — add `ll-verify-skills` documentation
- `docs/reference/CLI.md` — add `ll-verify-skills` reference section (after line 904)
- `skills/init/SKILL.md:440,519,543` — add `ll-verify-skills` to three template locations
- `skills/configure/areas.md:793` — append `ll-verify-skills` to CLI enumeration

### New Files
- `scripts/tests/test_skill_size_checker.py` — unit tests for `check_skill_sizes()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/docs.py:9–98` — `main_verify_docs()` is the direct implementation pattern to follow
- `scripts/tests/test_doc_counts.py:18–53` — `TestCountFiles` is the test pattern to follow
- `scripts/tests/test_link_checker.py` — structural reference for doc-validation test patterns

## Impact

- **Priority**: P4 — CI hygiene; not blocking
- **Effort**: Low — Pure addition; follows a well-established pattern
- **Risk**: Low — New tool, no changes to existing behavior
- **Breaking Change**: No

## Blocked By

- ENH-494 — 500-line convention must be established before writing a lint check for it

## Labels

`enhancement`, `cli`, `testing`, `skills`, `context-engineering`

## Status

**Open** | Created: 2026-04-07 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-04-11T19:02:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
