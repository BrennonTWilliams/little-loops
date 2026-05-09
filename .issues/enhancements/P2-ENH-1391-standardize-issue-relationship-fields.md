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

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — relationship field parsing
- `scripts/little_loops/cli/deps.py` — traverse canonical fields
- `scripts/little_loops/cli/issues.py` — show/sequence relationship display
- `scripts/little_loops/sync/` — relationship type mapping for each platform
- `skills/map-dependencies/SKILL.md` — use canonical vocabulary
- `config-schema.json` — relationship field definitions and validation
- All existing issue `.md` files — migrate `parent_issue:` → `parent:`, `related:` → `relates_to:`

### Migration Script Needed
- Sed/Python script to rename `parent_issue:` → `parent:` and `related:` → `relates_to:` in all issue frontmatter

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

## Impact

- **Priority**: P2 — incorrect relationship traversal affects sprint planning and sync correctness today
- **Effort**: Small-Medium — field renaming is mechanical; logic changes in `ll-deps` and `ll-sprint` are targeted
- **Risk**: Low — automated rename is reversible; field additions are backwards-compatible

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `schema`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
