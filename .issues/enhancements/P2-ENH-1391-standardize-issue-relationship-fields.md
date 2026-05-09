---
id: ENH-1391
type: ENH
priority: P2
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [FEAT-1389, ENH-1390, ENH-1392, ENH-1393]
---

# ENH-1391: Standardize Issue Relationship Fields

## Summary

Consolidate the inconsistent `parent:` / `parent_issue:` field names and overloaded `related:` field into a minimal, platform-standard relationship vocabulary: `epic`, `parent`, `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`. Each field has a distinct semantic that maps 1:1 to relationship types in JIRA, ADO, GitHub, and Linear.

## Current Behavior

Four problems exist in the current relationship model:

1. **`parent` vs `parent_issue`** — same concept, two field names (7 issues use `parent_issue:`, 16 use `parent:`). Tooling must handle both or silently miss one.
2. **`related:` is overloaded** — used to mean "soft ordering dependency", "informational association", and "same epic cluster" depending on the issue author. No consistent semantic.
3. **`depends_on:` is partial** — exists in some deferred issues but not recognized by all tooling; not documented in the issue schema.
4. **No `duplicate_of:`** — duplicates can only be marked by closing with a comment; no machine-readable dedup field exists.

## Expected Behavior

The recognized relationship fields are exactly:

| Field | Semantic | Directional? | Platform mapping |
|---|---|---|---|
| `epic: EPIC-NNN` | Container epic this issue belongs to | one-way | JIRA: Epic Link; ADO: parent Epic; Linear: Project |
| `parent: TYPE-NNN` | Decomposition parent (same tier, e.g. issue decomposed from a larger issue) | one-way | JIRA: Sub-task parent; GitHub: parent issue |
| `blocked_by: [...]` | Cannot start until these are done | one-way | JIRA: "is blocked by"; ADO: "Predecessor"; Linear: "blocked by" |
| `depends_on: [...]` | Should follow these, but not a hard stop | one-way | JIRA: "depends on"; ADO: "Related Work"; Linear: "depends on" |
| `relates_to: [...]` | Associated — no ordering implication | symmetric | JIRA: "relates to"; GitHub: linked issues; Linear: "related" |
| `duplicate_of: TYPE-NNN` | This issue is a duplicate of another | one-way | JIRA: "duplicates"; GitHub: closing reference; Linear: "duplicate of" |

The `related:` field is deprecated and migrated to `relates_to:`.

## Motivation

- **Tooling correctness**: `ll-deps`, `ll-sprint`, and `map-dependencies` skill all traverse relationships. Inconsistent field names mean they silently miss edges.
- **Sync fidelity**: `ll-sync` can only map relationship types it recognizes. Standardizing to platform vocabulary makes the mapping trivial.
- **Sprint planning**: Distinguishing `blocked_by` (hard stop) from `depends_on` (soft ordering) from `relates_to` (informational) is essential for correct dependency-aware ordering in `ll-sprint`.
- **Dedup**: A machine-readable `duplicate_of:` enables `ll-issues` to auto-detect and skip duplicate issues during processing.

## Proposed Solution

1. Define the canonical 6-field vocabulary in `config-schema.json` and issue validation
2. Rename `parent_issue:` → `parent:` across all existing issues (automated)
3. Migrate `related:` → `relates_to:` across all existing issues (automated; the semantic is compatible for most cases)
4. Add `duplicate_of:` recognition to all tooling
5. Add `epic:` field recognition (in concert with FEAT-1389)
6. Update `ll-deps`, `ll-sprint`, `map-dependencies`, and `ll-sync` to use the canonical field set
7. Add a validation rule: `blocked_by` values must be valid issue IDs; `duplicate_of` must be a single value, not a list

## API/Interface

Frontmatter schema additions to `config-schema.json`:

```yaml
# Canonical relationship fields in issue frontmatter
epic: EPIC-NNN            # single value
parent: TYPE-NNN          # single value
blocked_by: [TYPE-NNN]    # list
depends_on: [TYPE-NNN]    # list
relates_to: [TYPE-NNN]    # list
duplicate_of: TYPE-NNN    # single value

# Deprecated (supported as aliases during migration):
parent_issue: TYPE-NNN    # → migrated to parent:
related: [TYPE-NNN]       # → migrated to relates_to:
```

Validation rules:
- `blocked_by`, `depends_on`, `relates_to` accept lists only
- `epic`, `parent`, `duplicate_of` accept single values only
- Unknown relationship fields emit a validation warning

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — relationship field parsing
- `scripts/little_loops/cli/deps.py` — traverse canonical fields
- `scripts/little_loops/cli/issues.py` — show/sequence relationship display
- `scripts/little_loops/sync/` — relationship type mapping for each platform
- `skills/map-dependencies/SKILL.md` — use canonical vocabulary
- `config-schema.json` — relationship field definitions and validation
- All existing issue `.md` files — migrate `parent_issue:` → `parent:`, `related:` → `relates_to:`
- Migration script (new): `scripts/little_loops/cli/migrate_relationships.py`

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "parent_issue\|relates_to\|blocked_by\|depends_on\|duplicate_of" scripts/`
- `scripts/little_loops/cli/sprint.py` — likely imports `issue_manager` relationship parsing
- `ll-auto`, `ll-parallel`, `ll-sprint` entrypoints — consume `ll-deps` output

### Similar Patterns
- `config-schema.json` existing field definitions — follow same JSON Schema pattern for new relationship field entries
- `scripts/little_loops/sync/` platform mappers — each already maps field names; extend same pattern for new canonical fields

### Tests
- `scripts/tests/test_issue_manager.py` — add tests for deprecated alias handling and canonical field parsing
- `scripts/tests/test_deps.py` — add tests for `blocked_by` (hard) vs `depends_on` (soft) traversal
- `scripts/tests/test_sync.py` — add tests for relationship type mapping per platform

### Documentation
- `docs/reference/API.md` — update relationship field reference section
- `CONTRIBUTING.md` — note canonical vocabulary in issue authoring guidelines

### Configuration
- `config-schema.json` — relationship field schema additions (primary change)

## Implementation Steps

1. Define canonical relationship fields in `config-schema.json` with descriptions and value constraints
2. Update `issue_manager.py` field parser to recognize all 6 fields (and `parent_issue:` as deprecated alias)
3. Write migration script: `parent_issue:` → `parent:`, `related:` → `relates_to:` in all `.issues/**/*.md`
4. Update `ll-deps` CLI to traverse `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`
5. Update `ll-sprint` dependency ordering to use `blocked_by` (hard) and `depends_on` (soft) separately
6. Update `ll-sync` platform mappers for each relationship type
7. Add validation: warn on unknown relationship field names in issue frontmatter
8. Update `skills/map-dependencies/SKILL.md` with canonical vocabulary
9. Update docs

## Success Metrics

- Zero `.issues/**/*.md` files containing `parent_issue:` field after migration
- Zero `.issues/**/*.md` files containing `related:` field after migration
- All 6 canonical fields (`epic`, `parent`, `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`) traversed correctly by `ll-deps`, `ll-sprint`, `map-dependencies`, and `ll-sync`
- `ll-issues` validation flags unknown relationship field names with a warning

## Scope Boundaries

- **In scope**: Defining the 6 canonical relationship fields in `config-schema.json`, automating migration of `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files, updating `ll-deps` / `ll-sprint` / `map-dependencies` / `ll-sync` to use canonical fields, adding validation warnings for unknown field names
- **Out of scope**: Adding relationship types beyond the 6 defined (e.g., `conflicts_with`, `supersedes`), platform-specific relationship extensions not in the canonical set, UI/visual display of relationship graphs, changes to how relationships affect auto-prioritization logic, `ll-sync` full bidirectional sync (covered by FEAT-1389)

## Impact

- **Priority**: P2 — incorrect relationship traversal affects sprint planning and sync correctness today
- **Effort**: Small-Medium — field renaming is mechanical; logic changes in `ll-deps` and `ll-sprint` are targeted
- **Risk**: Low — automated rename is reversible; field additions are backwards-compatible

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `schema`, `captured`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T20:38:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf87852d-ec5b-4a4d-959f-57a040534f19.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): The `epic:` relationship field defined in the canonical vocabulary table above maps to JIRA Epic Link / ADO parent Epic / Linear Project. However, the formal implementation of `epic:` field parsing, config-schema registration, and tooling wiring is owned by FEAT-1389 (Add EPIC as first-class issue type). ENH-1391 establishes the vocabulary entry and platform mapping; it must NOT implement `epic:` field parsing in `issue_manager.py` or register the field in `config-schema.json` — defer those to FEAT-1389. Add FEAT-1389 as a dependency when sequencing this issue.
