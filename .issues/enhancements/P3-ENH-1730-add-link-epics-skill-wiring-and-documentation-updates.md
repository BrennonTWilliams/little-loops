---
id: ENH-1730
title: 'Add link-epics skill: wiring and documentation updates'
type: ENH
status: done
priority: P3
parent: ENH-1728
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1730: Add link-epics skill: wiring and documentation updates

## Summary

Update all existing files that reference the skill catalog to include `link-epics`: CLAUDE.md, capture-issue, issue-workflow, help.md, COMMANDS.md, and the three count-tracking docs (README, CONTRIBUTING, ARCHITECTURE).

## Parent Issue

Decomposed from ENH-1728: Add skill to link parentless open issues to open epics

## Prerequisites

ENH-1729 must be complete (skill file at `skills/link-epics/SKILL.md` must exist) before these documentation updates can be applied.

## Scope

This child covers **Implementation Steps 8–12** from the parent:

8. Update `skills/capture-issue/SKILL.md` — add `link-epics` as a follow-up in `## Integration` section ("After capturing issues, run `/ll:link-epics` to assign parentless issues to epics")
9. Update `skills/issue-workflow/SKILL.md` — add `link-epics` to `### 2. Refinement Phase` command sequence and `## Related Skills` table
10. Update `commands/help.md` — add `link-epics` stanza to `ISSUE REFINEMENT` block (static file; not auto-discovered by `/ll:help`)
11. Update `docs/reference/COMMANDS.md` — add `### /ll:link-epics` section with `--auto`/`--min-score` flags, Quick Reference table row, and append `link-epics` to the `--auto`-supported skills row in the Flag Conventions table
12. Increment skill counts in count-tracking docs (all enforced by `ll-verify-docs` CI gate via `scripts/little_loops/doc_counts.py`):
    - `README.md`: `30 skills` → `31 skills`
    - `CONTRIBUTING.md`: `30 skill definitions` → `31`
    - `docs/ARCHITECTURE.md`: `SKL[Skills<br/>30 composable skills]` → `31` (Mermaid) AND `30 skill definitions` → `31` (directory tree)

Also update `docs/reference/CLI.md` — add `link-epics` skill invocation example (identified in the parent's "Files to Modify" list).

## Files to Modify

- `skills/capture-issue/SKILL.md` — `## Integration` section
- `skills/issue-workflow/SKILL.md` — Refinement Phase + Related Skills
- `commands/help.md` — ISSUE REFINEMENT block
- `docs/reference/COMMANDS.md` — new section + Quick Reference row + Flag Conventions table
- `docs/reference/CLI.md` — invocation example
- `README.md` — skill count 30 → 31
- `CONTRIBUTING.md` — skill count 30 → 31
- `docs/ARCHITECTURE.md` — Mermaid SKL node + directory tree count 30 → 31

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files Modified
- `skills/capture-issue/SKILL.md` — added `/ll:link-epics` as step 4 in `## Integration` section (after prioritize-issues, before commit)
- `skills/issue-workflow/SKILL.md` — added `/ll:link-epics [--auto]` to Refinement Phase bash block (after `decide-issue`, before `verify-issues`) and a row to Related Skills table
- `commands/help.md` — added `/ll:link-epics [flags]` stanza to ISSUE REFINEMENT block (lines 75–78)
- `docs/reference/COMMANDS.md` — added `### /ll:link-epics` section (lines 328–338), Quick Reference table row, and `link-epics` to `--auto` Flag Conventions row
- `docs/reference/CLI.md` — added `ll-action invoke link-epics --args --auto` usage example inside the existing `ll-action` section
- `README.md` — incremented skill count 30 → 31 (line 165)
- `CONTRIBUTING.md` — incremented skill count 30 → 31 (line 123 directory tree comment)
- `docs/ARCHITECTURE.md` — updated Mermaid `SKL[Skills<br/>31 composable skills]` node and directory tree `# 31 skill definitions` comment

### Count Enforcement Infrastructure
- `scripts/little_loops/doc_counts.py:verify_documentation()` — scans README.md, CONTRIBUTING.md, docs/ARCHITECTURE.md for skill-count strings; compares to actual glob of `skills/*/SKILL.md` (excluding bridge skills containing `BRIDGE_MARKER`)
- `scripts/little_loops/cli/docs.py:main_verify_docs` — CLI entry point invoked by `ll-verify-docs`
- `scripts/tests/test_doc_counts.py` and `scripts/tests/test_cli_docs.py` — test coverage for count verification

### Known Gap (Post-Completion)
- `commands/help.md:301` — Quick Reference Table Issue Refinement list omits `link-epics`; this line was not in the original scope and was not updated: `**Issue Refinement**: \`normalize-issues\`, ..., \`audit-issue-conflicts\`` (missing `link-epics`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1447_doc_wiring.py` — asserts `"30 skills"` / `"30 skill definitions"` / `"30 composable skills"` counts (`TestReadmeSkillCount`, `TestContributingWiring`, `TestArchitectureSkillCount` × 2); **4 assertions currently fail** since docs now say "31"
- `scripts/tests/test_feat1287_doc_wiring.py` — asserts `"30 skills"` / `"30 skill definitions"` (`TestReadmeSkillCount`, `TestContributingWiring`); **2 assertions currently fail** against current docs

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` lines 143–144 — skills directory tree shows count=31 but `link-epics/` entry is absent (insert between `issue-workflow/` and `manage-issue/`)
- `docs/ARCHITECTURE.md` lines 159–161 — skills directory tree shows count=31 but `link-epics/` entry is absent (insert between `issue-workflow/` and `manage-issue/`)
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `### Plan a Feature Sprint` refinement sequence omits `link-epics` step
- `commands/help.md:301` — **confirmed**: Quick Reference Table Issue Refinement list omits `link-epics` (same as Known Gap above)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1730_doc_wiring.py` — **new test file needed**: does not exist; follow `test_feat1447_doc_wiring.py` pattern to assert `"31 skills"`, `link-epics` presence in `commands/help.md`, `skills/capture-issue/SKILL.md`, `skills/issue-workflow/SKILL.md`, `docs/reference/COMMANDS.md`, `docs/reference/CLI.md`, and Quick Reference Table
- `scripts/tests/test_feat1447_doc_wiring.py` — update `TestReadmeSkillCount`, `TestContributingWiring`, `TestArchitectureSkillCount` assertions from `"30"` → `"31"` (4 failing assertions)
- `scripts/tests/test_feat1287_doc_wiring.py` — update `TestReadmeSkillCount`, `TestContributingWiring` assertions from `"30"` → `"31"` (2 failing assertions)

### Configuration / Registrations

_Wiring pass added by `/ll:wire-issue`:_
- `skills/link-epics/agents/openai.yaml` — Codex Skills API adapter does not exist; run `ll-adapt-skills-for-codex --apply` to generate it (every other canonical skill has this file)

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Verify prerequisite: confirm `skills/link-epics/SKILL.md` exists (ENH-1729)
2. Update `skills/capture-issue/SKILL.md` — insert `4. **Link**: \`/ll:link-epics\` to assign parentless issues to open epics` in `## Integration` numbered list
3. Update `skills/issue-workflow/SKILL.md` — insert `/ll:link-epics [--auto]        # Assign parentless issues to open epics via similarity scoring` in Refinement Phase bash block; add `| \`link-epics\` | Assign parentless open issues to open epics via similarity scoring |` row to Related Skills table
4. Update `commands/help.md` — append entry to ISSUE REFINEMENT block following the three-line pattern: command line, description line, Flags line
5. Update `docs/reference/COMMANDS.md` — add `### \`/ll:link-epics\`` section with prose description, `**Flags:**` bullet list, `**Output:**` line, `**Trigger keywords:**` line; add Quick Reference table row; append `link-epics` to `--auto` Flag Conventions row
6. Update `docs/reference/CLI.md` — add `ll-action invoke link-epics --args --auto` usage example inside the `ll-action` section
7. Update `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` skill counts (30 → 31)
8. Run `ll-verify-docs` to confirm counts pass the CI gate

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Fix `commands/help.md:301` — add `link-epics` to the Issue Refinement list in the Quick Reference Table (after `` `audit-issue-conflicts` ``)
10. Add `link-epics/` entry to `CONTRIBUTING.md` directory tree (between `issue-workflow/` and `manage-issue/`, with skill-count comment)
11. Add `link-epics/` entry to `docs/ARCHITECTURE.md` directory tree (between `issue-workflow/` and `manage-issue/`)
12. Update `scripts/tests/test_feat1447_doc_wiring.py` — change all `"30"` count assertions to `"31"` (4 assertions in `TestReadmeSkillCount`, `TestContributingWiring`, `TestArchitectureSkillCount`)
13. Update `scripts/tests/test_feat1287_doc_wiring.py` — change all `"30"` count assertions to `"31"` (2 assertions)
14. Create `scripts/tests/test_enh1730_doc_wiring.py` — new wiring test following `test_feat1447_doc_wiring.py` pattern; assert `"31 skills"` and `link-epics` presence across all updated files
15. Run `ll-adapt-skills-for-codex --apply` to generate `skills/link-epics/agents/openai.yaml`
16. Add `link-epics` to `### Plan a Feature Sprint` refinement sequence in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

## Acceptance Criteria

- `ll-verify-docs` exits 0 (skill count in README/CONTRIBUTING/ARCHITECTURE matches actual `skills/` directory count)
- `/ll:help` shows `link-epics` in the Issue Refinement section
- `commands/help.md` contains a `link-epics` entry in the ISSUE REFINEMENT block

## Session Log
- `/ll:wire-issue` - 2026-05-26T23:03:12 - `52106e6a-2007-47aa-a7aa-17b1421a6040.jsonl`
- `/ll:refine-issue` - 2026-05-26T22:56:46 - `0cab094d-290b-469d-bdf6-fdf86146f89f.jsonl`
- `/ll:issue-size-review` - 2026-05-26T22:30:00Z - `d2480abd-758c-47ca-aa87-454ae8a76200.jsonl`
- `/ll:confidence-check` - 2026-05-26T18:05:00Z - `5e0e182b-2dca-4b85-82cb-bf3fdb2e7bfa.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
