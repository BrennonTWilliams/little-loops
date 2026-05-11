---
id: ENH-1433
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1432
status: done
completed_at: 2026-05-11T02:50:53Z
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1433: Standardize Relationship Fields — Skills, Docs & Display

## Summary

Update all skill definitions and documentation to use the canonical 6-field relationship vocabulary. Extend `ll-issues sequence --json` output if `cmd_sequence()` gains new fields. This is the final child of ENH-1391 and can begin once ENH-1432 is merged (depends on the display decision in `formatting.py`).

## Current Behavior

Various skill files and documentation still reference the deprecated `parent_issue:` field name and lack coverage of the full 6-field canonical relationship vocabulary. The `IssueInfo` dataclass and schema (ENH-1430, ENH-1432) are already updated, but skill definitions (`issue-size-review`, `confidence-check`, `audit-issue-conflicts`, `manage-issue`, `map-dependencies`), reference docs (`ISSUE_TEMPLATE.md`, `API.md`), contributing guidelines (`CONTRIBUTING.md`), and user guides (`ISSUE_MANAGEMENT_GUIDE.md`, `SPRINT_GUIDE.md`) still use old names or omit the new fields.

## Expected Behavior

All skill definitions and documentation use the canonical 6-field relationship vocabulary (`parent`, `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`, plus computed `blocks`). A new doc-wiring test (`test_enh1433_doc_wiring.py`) asserts correct vocabulary across the key skill files and reference docs.

## Impact

- **Priority**: P2 — Documentation drift creates confusion and inconsistency between schema truth and written guidance; blocks users from discovering the full relationship model.
- **Effort**: Medium — 10 files to update (mostly prose/template changes) plus one new test file.
- **Risk**: Low — Documentation-only surface; existing parser, schema, and tooling are already updated by prior ENH-1430/1432 completions.
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `skills`, `relationship-fields`

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
- `skills/manage-issue/SKILL.md`
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify (with specific anchors)

| File | Location | Current | Change To |
|------|----------|---------|-----------|
| `skills/issue-size-review/SKILL.md` | Phase 4 template (~line 208-224) | `parent_issue: [PARENT-ID]` | `parent: [PARENT-ID]` |
| `skills/issue-size-review/SKILL.md` | Phase 6 prose (line 277) | `"must include parent_issue: [PARENT-ID]"` | `"must include parent: [PARENT-ID]"` |
| `skills/confidence-check/SKILL.md` | Criterion 3 (~line 235) | `parent_issue: EPIC-NNN references` | `parent: EPIC-NNN references` |
| `skills/audit-issue-conflicts/SKILL.md` | `add_dependency` action (lines 126-127, 238-239, 310, 363, 397) | `blocked_by` only | Add `depends_on` as soft-ordering alternative; distinguish hard vs soft |
| `skills/map-dependencies/SKILL.md` | Main description (~line 13) | Only `## Blocked By` / `## Blocks` | Reference canonical 6-field vocabulary |
| `docs/reference/ISSUE_TEMPLATE.md` | Frontmatter table (line 896) | `parent_issue` row only | Rename to `parent:`; add rows for `depends_on`, `relates_to`, `duplicate_of` |
| `docs/reference/ISSUE_TEMPLATE.md` | EPIC checklist (line 522) | `parent_issue: EPIC-NNN` | `parent: EPIC-NNN` |
| `docs/reference/API.md` | `IssueInfo` dataclass block (lines 558-585) | `blocked_by`, `blocks` only | Add `parent: str \| None`, `depends_on: list[str]`, `relates_to: list[str]`, `duplicate_of: str \| None` |
| `CONTRIBUTING.md` | Issue authoring guidelines section | No relationship field coverage | Add canonical vocabulary table |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | Frontmatter example (lines 42-50) | `blocked_by: []` only | Extend to all 6 canonical fields |
| `docs/guides/SPRINT_GUIDE.md` | Wave scheduling section (lines 28-68, 392-396) | `blocked_by` only | Add `depends_on` (soft ordering) vs `blocked_by` (hard stop) distinction |

#### Canonical Field Definitions (Model After)

The authoritative field definitions live in `config-schema.json` (lines 200-228):
- `parent` — `string` (single value; line 200-203)
- `blocked_by` — `array of strings` (lines 204-209)
- `depends_on` — `array of strings` (lines 210-216)
- `relates_to` — `array of strings` (lines 217-223)
- `duplicate_of` — `string` (lines 224-228)

Live canonical examples in issue frontmatter: `.issues/completed/P2-ENH-1431-*.md` uses both `parent:` and `depends_on:`.

#### What the Actual `IssueInfo` Dataclass Looks Like (Model the API Doc After)

Defined in `scripts/little_loops/issue_parser.py` lines 248-253:
```python
blocked_by: list[str] = field(default_factory=list)
blocks: list[str] = field(default_factory=list)
parent: str | None = None
depends_on: list[str] = field(default_factory=list)
relates_to: list[str] = field(default_factory=list)
duplicate_of: str | None = None
```

#### `blocked_by` vs `depends_on` Distinction (Canonical Source)

`docs/reference/OUTPUT_STYLING.md` (lines 277-282) already documents this in the arrow table:
- `──→` = `blocked_by` (hard dependency)
- `-->` = `depends_on` (soft ordering prerequisite)

Use this phrasing for SPRINT_GUIDE and audit-issue-conflicts updates.

#### sequence.py Extension — NOT Applicable

ENH-1432 is in `.issues/completed/`. Its implementation did NOT extend `cmd_sequence()` to include `depends_on`/`relates_to` in `--json` output (still only `blocked_by` and `blocks` at `sequence.py` lines 48-57). The conditional test assertion step from the issue is therefore a no-op — skip it.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/manage-issue/SKILL.md` — uses `parent_issue: EPIC-NNN` in EPIC handling paragraph (line 54); must be updated to `parent: EPIC-NNN` alongside the other four skills [Agent 1 finding]

### Files Confirmed No Changes Needed

- `scripts/little_loops/issue_parser.py` — IssueInfo already has all 6 fields (ENH-1430 completed)
- `scripts/little_loops/sync.py` — `duplicate_of` and `blocked_by` mapping already done (ENH-1438 completed)
- `scripts/little_loops/dependency_mapper/formatting.py` — `depends_on`/`relates_to` rendering already done (ENH-1432 completed)
- `docs/reference/OUTPUT_STYLING.md` — arrow table already documents `blocked_by` vs `depends_on` distinction
- `docs/reference/CLI.md` — accurately documents `ll-migrate-relationships` tool, no vocabulary update needed
- `docs/reference/EVENT-SCHEMA.md` — uses `parent_issue_id` as an event bus field name (not a frontmatter key); semantically distinct, no change needed
- `CHANGELOG.md` — historical entry uses `parent_issue` to describe what ENH-1324 introduced; immutable historical record

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1433_doc_wiring.py` — new test file needed; no existing test guards the vocabulary changes in this issue. Follow the `test_enh[NNN]_doc_wiring.py` pattern (see `test_enh1428_doc_wiring.py` for the template): assert presence of `parent:` and absence of `parent_issue:` in `skills/issue-size-review/SKILL.md`, `skills/confidence-check/SKILL.md`, `skills/manage-issue/SKILL.md`, and `docs/reference/ISSUE_TEMPLATE.md`; assert presence of new IssueInfo fields in `docs/reference/API.md` [Agent 3 finding]
- `scripts/tests/test_issues_cli.py` — skip: `cmd_sequence()` was not extended in ENH-1432; no new assertions needed

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **`skills/issue-size-review/SKILL.md`** — Two-location fix: (a) Phase 4 template block: change `parent_issue: [PARENT-ID]` → `parent: [PARENT-ID]`; (b) Phase 6 prose line 277: update sentence to say `parent: [PARENT-ID]` instead of `parent_issue:`
2. **`skills/confidence-check/SKILL.md`** — One-line fix at Criterion 3 (~line 235): change `parent_issue: EPIC-NNN references` → `parent: EPIC-NNN references`
3. **`skills/audit-issue-conflicts/SKILL.md`** — Add to the `add_dependency` resolution path: introduce `depends_on` as a soft-ordering alternative and clarify when to use each. Update lines 126-127 (action description), 238-239 (interactive question), 310 (execution step), and 363 (example output). Reference phrasing: "`blocked_by` (hard stop — must complete first) or `depends_on` (soft ordering — preferred when no hard dependency exists)"
4. **`skills/map-dependencies/SKILL.md`** — Add vocabulary note referencing the canonical 6-field set; use `docs/reference/OUTPUT_STYLING.md` arrow table phrasing as the model
5. **`docs/reference/ISSUE_TEMPLATE.md`** — (a) Frontmatter table at line 896: rename `parent_issue` row to `parent:` and add rows for `depends_on`, `relates_to`, `duplicate_of`; (b) EPIC checklist at line 522: change `parent_issue: EPIC-NNN` → `parent: EPIC-NNN`
6. **`docs/reference/API.md`** — Extend the `IssueInfo` block (lines 558-585) to match actual dataclass: add `parent`, `depends_on`, `relates_to`, `duplicate_of` fields using the same format as `blocked_by`/`blocks`
7. **`CONTRIBUTING.md`** — In the issue authoring guidelines section, add a "Relationship Fields" subsection with the canonical 6-field vocabulary table (field name, type, meaning, when to use)
8. **`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — Extend the frontmatter example block (lines 42-50) to include all 6 canonical relationship fields with inline comments explaining each
9. **`docs/guides/SPRINT_GUIDE.md`** — In the wave scheduling section (lines 28-68 and the example at lines 392-396), add a paragraph or table distinguishing `blocked_by` (hard stop, wave-gated) from `depends_on` (soft ordering, not wave-gated)
10. **`scripts/tests/test_issues_cli.py`** — Skip: `cmd_sequence()` was not extended in ENH-1432; no new assertions needed

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. **`skills/manage-issue/SKILL.md`** — One-line fix at line 54: change `parent_issue: EPIC-NNN` → `parent: EPIC-NNN` in the EPIC handling paragraph (same vocabulary standardization as the four skills already in scope)
12. **`scripts/tests/test_enh1433_doc_wiring.py`** — Create new doc wiring test file following the `test_enh[NNN]_doc_wiring.py` convention. Add presence/absence assertions for:
    - `skills/issue-size-review/SKILL.md`: `parent:` present, `parent_issue:` absent in draft template block
    - `skills/confidence-check/SKILL.md`: `parent:` present, `parent_issue:` absent in Criterion A prose
    - `skills/manage-issue/SKILL.md`: `parent: EPIC-NNN` present, `parent_issue: EPIC-NNN` absent
    - `docs/reference/ISSUE_TEMPLATE.md`: `parent:` present in frontmatter table, `parent_issue` absent
    - `docs/reference/API.md`: `parent`, `depends_on`, `relates_to`, `duplicate_of` all present in IssueInfo block

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-11T02:50:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-11T02:42:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a555351-df6a-4f42-bf84-3dd83151ea36.jsonl`
- `/ll:refine-issue` - 2026-05-11T02:33:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f4d9f13-80d2-4865-8e76-f1b57b45dd8f.jsonl`
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
