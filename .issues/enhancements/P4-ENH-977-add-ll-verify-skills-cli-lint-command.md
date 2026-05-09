---
discovered_date: 2026-04-07
discovered_by: split-from-ENH-494
blocked_by: [ENH-494, ENH-1038]
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

## Labels

`enhancement`, `cli`, `testing`, `skills`, `context-engineering`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- No `check_skill_sizes()` function in `scripts/little_loops/doc_counts.py` ✓
- No `main_verify_skills()` in `scripts/little_loops/cli/docs.py` ✓
- No `ll-verify-skills` entry point in `scripts/pyproject.toml` ✓
- Blocked by ENH-494 (500-line convention not yet established) ✓

## Status

**Open** | Created: 2026-04-07 | Priority: P4


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-1038 (ll-verify-docs should track FSM loop counts) both modify `scripts/little_loops/doc_counts.py` and `scripts/little_loops/cli/docs.py`. Changes are additive in different sections (ENH-977 adds `check_skill_sizes()` and `main_verify_skills()`; ENH-1038 adds to `COUNT_TARGETS`), but they should be sequenced or merged to avoid conflicts in the same PR. Related: ENH-1038.

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): The "companion files alongside `SKILL.md` are not counted toward the 500-line limit" test case (Implementation Step 5) explicitly assumes ENH-494's flat-companion-file pattern landed first. ENH-977's `rglob('SKILL.md')` walk is robust to the alternative subdirectory pattern, but the test fixtures are not — keep `blocked_by: [ENH-494]` and re-validate the fixture layout if ENH-494's companion-file decision ever changes.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): After ENH-494 ships and extracts overflow content from `audit-claude-config`, `confidence-check`, `init`, and `manage-issue` SKILL.md files, re-verify that the 500-line threshold is still meaningful (i.e., the remaining SKILL.md files are not all trivially under 500 lines). Confirm the threshold before publishing `ll-verify-skills` — if ENH-494 brings all files well below 500 lines, the tool may need a lower threshold or per-file annotations to remain useful.
