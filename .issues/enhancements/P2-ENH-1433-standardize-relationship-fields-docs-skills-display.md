---
id: ENH-1433
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1432
status: open
---

# ENH-1433: Standardize Relationship Fields — Skills, Docs & Display

## Summary

Update all skill definitions and documentation to use the canonical 6-field relationship vocabulary. Extend `ll-issues sequence --json` output if `cmd_sequence()` gains new fields. This is the final child of ENH-1391 and can begin once ENH-1432 is merged (depends on the display decision in `formatting.py`).

## Parent Issue

Decomposed from ENH-1391: Standardize Issue Relationship Fields

## Scope

Covers implementation steps 8, 9, 14, and 15 from the parent.

## Proposed Solution

### Step 8 — Skills: `map-dependencies` and `issue-size-review`

- `skills/map-dependencies/SKILL.md` — update vocabulary references to canonical 6-field set
- `skills/issue-size-review/SKILL.md` — change `parent_issue:` written to decomposed child issues → `parent:` (the decomposition template currently writes the deprecated field name)

### Step 9 — Core docs

- `docs/reference/ISSUE_TEMPLATE.md` (~line 896) — rename `parent_issue:` field to `parent:`
- `docs/reference/API.md` — update `IssueInfo` field list to include `parent`, `depends_on`, `relates_to`, `duplicate_of`
- `CONTRIBUTING.md` — add canonical vocabulary note in issue authoring guidelines

### Step 14 — Guide docs

- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — extend example frontmatter block to show full canonical vocabulary (`depends_on:`, `relates_to:`, `duplicate_of:`)
- `docs/guides/SPRINT_GUIDE.md` — document `depends_on` (soft ordering) vs `blocked_by` (hard stop) distinction for wave scheduling

### Step 15 — Skill defs: `audit-issue-conflicts` and `confidence-check`

- `skills/audit-issue-conflicts/SKILL.md` — update `blocked_by: [ISSUE-B]` instructions to reference the canonical 6-field vocabulary; distinguish soft vs hard dependency fields
- `skills/confidence-check/SKILL.md` — replace `parent_issue: EPIC-NNN` references with `parent:` for child-issue enumeration checks

### Display extension (if applicable)

If `cmd_sequence()` in `scripts/little_loops/cli/issues/sequence.py` is extended to include `depends_on` or `relates_to` in `--json` output (as part of ENH-1432), add corresponding assertions to `scripts/tests/test_issues_cli.py` (`test_sequence_json_output` currently asserts `"blocked_by" in item` and `"blocks" in item` only).

## Files to Modify

- `skills/map-dependencies/SKILL.md`
- `skills/issue-size-review/SKILL.md`
- `skills/audit-issue-conflicts/SKILL.md`
- `skills/confidence-check/SKILL.md`
- `docs/reference/ISSUE_TEMPLATE.md`
- `docs/reference/API.md`
- `CONTRIBUTING.md`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- `docs/guides/SPRINT_GUIDE.md`

## Tests

- `scripts/tests/test_issues_cli.py` — if `cmd_sequence()` is extended for new fields, add assertions for `depends_on` and `relates_to` in `--json` output

## Acceptance Criteria

- `skills/issue-size-review/SKILL.md` writes `parent:` (not `parent_issue:`) in child issue templates
- `skills/confidence-check/SKILL.md` reads `parent:` (not `parent_issue:`) for child enumeration
- `skills/audit-issue-conflicts/SKILL.md` uses canonical vocabulary for relationship field instructions
- `docs/reference/ISSUE_TEMPLATE.md` shows `parent:` (not `parent_issue:`)
- `docs/guides/SPRINT_GUIDE.md` documents `blocked_by` vs `depends_on` wave scheduling distinction
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` shows full 6-field canonical vocabulary in frontmatter examples
- `docs/reference/API.md` includes all new `IssueInfo` fields

## Scope Boundaries

- **In scope**: Skill definitions, reference docs, guide docs, `test_issues_cli.py` assertions (conditional)
- **Out of scope**: Schema/parser (ENH-1430), migration (ENH-1431), dependency tooling (ENH-1432)
- **Depends on**: ENH-1432 — formatting/display decisions must be finalized before docs describe them

## Session Log
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
