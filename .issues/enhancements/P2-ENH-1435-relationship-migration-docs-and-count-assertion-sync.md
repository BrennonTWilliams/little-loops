---
id: ENH-1435
type: ENH
priority: P2

depends_on:
- ENH-1434
status: done
completed_at: 2026-05-11T00:36:46Z
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1431
---

# ENH-1435: Relationship Migration — Docs and Count Assertion Sync

## Summary

Update all documentation files to register `ll-migrate-relationships` as a new CLI tool, and sync the hardcoded count assertions in test files that verify doc accuracy. Depends on ENH-1434 (the CLI must exist before it can be documented).

## Parent Issue

Decomposed from ENH-1431: Standardize Relationship Fields — Migration Script

## Scope

Covers Steps 14 and 15 from ENH-1431 (wiring pass doc and count-assertion updates).

## Current Behavior

`ll-migrate-relationships` is not listed in `.claude/CLAUDE.md`, `README.md`, `commands/help.md`, `docs/reference/CLI.md`, or `skills/configure/areas.md`. Count assertions in `test_create_extension_wiring.py` and `test_ll_logs_wiring.py` still reference the old totals (`"18 CLI tools"` and `"Authorize all 17"`), so the test suite will fail once ENH-1434 ships without these updates.

## Expected Behavior

All 5 documentation files register `ll-migrate-relationships`; `README.md` reads `"19 CLI tools"`; `skills/configure/areas.md` reads `"Authorize all 18"`; all existing count assertion tests and the new `TestEnh1435LlMigrateRelationshipsWiring` presence tests pass.

## Current Pain Point

`ll-migrate-relationships` exists as a CLI tool (ENH-1434) but is invisible in every doc surface — help text, CLI reference, CLAUDE.md, and the configure prompt. Users cannot discover or authorize it. Additionally, the tightly-coupled count assertion tests will fail immediately after ENH-1434 ships if this sync is not applied in the same release.

## Impact

Medium — blocks test suite from passing after ENH-1434 lands and leaves a new CLI tool undiscoverable. Pure doc and test sync; no logic changes, no schema risk.

## Labels

`documentation`, `enhancement`, `testing`

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Proposed Solution

### Step 14 — Documentation files (5 files)

Add `ll-migrate-relationships` to each doc following the same pattern used when `ll-migrate` landed in ENH-1420:

- `.claude/CLAUDE.md` — "CLI Tools" bullet list (near line 119): add `ll-migrate-relationships` entry after `ll-migrate`
- `README.md` — (a) increment `"18 CLI tools"` → `"19 CLI tools"` (line 90); (b) add `### ll-migrate-relationships` section after `### ll-migrate` (~line 500)
- `commands/help.md` — CLI TOOLS block (near line 239): add `ll-migrate-relationships` line after `ll-migrate`
- `docs/reference/CLI.md` — add `### ll-migrate-relationships` section (flags table + examples) after `### ll-migrate` section (~line 1156)
- `skills/configure/areas.md` — `authorize-all` description (line 823): `"Authorize all 17"` → `"Authorize all 18"`; add `ll-migrate-relationships` to the enumerated tool list

### Step 15 — Count assertion tests (2 test files)

Update hardcoded count strings that verify the docs updated in Step 14. Must be applied together with Step 14 or tests will fail:

- `scripts/tests/test_create_extension_wiring.py`:
  - `TestFeat1045DocUpdates.test_readme_tool_count_is_18`: `"18 CLI tools"` → `"19 CLI tools"`
  - `TestFeat1229LlActionWiring.test_readme_tool_count_is_18`: `"18 CLI tools"` → `"19 CLI tools"`
  - `TestConfigureAreasWiring.test_count_updated_to_17`: `"Authorize all 17"` → `"Authorize all 18"`
  - `TestFeat1229LlActionWiring.test_configure_areas_count_is_17`: `"Authorize all 17"` → `"Authorize all 18"`
- `scripts/tests/test_ll_logs_wiring.py`:
  - `TestConfigureAreasWiring.test_authorize_all_count_is_17`: `"Authorize all 17"` → `"Authorize all 18"`

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact text to insert for each file:_

**`.claude/CLAUDE.md`** — insert after line 119 (`ll-migrate` bullet):
```
- `ll-migrate-relationships` - One-time migration that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files (ENH-1434)
```

**`README.md`** — insert after `### ll-migrate` section (after line 509), before `### ll-generate-schemas`:
```markdown
### ll-migrate-relationships

One-time migration script that renames deprecated relationship frontmatter keys across all `.md` files in `.issues/`: `parent_issue:` → `parent:` and `related:` → `relates_to:`. Part of the ENH-1434 relationship field standardization.

```bash
ll-migrate-relationships --dry-run   # Preview all planned renames
ll-migrate-relationships             # Execute migration
```

Run `ll-migrate-relationships --help` for all options.
```

**`commands/help.md`** — insert after `ll-migrate` line 239 (align spacing to match existing entries):
```
ll-migrate-relationships Rename deprecated relationship frontmatter keys in all issue files (one-time, ENH-1434)
```

**`docs/reference/CLI.md`** — insert after `### ll-migrate` section (after line 1174 `---`), before `### ll-verify-docs`:
```markdown
### ll-migrate-relationships

One-time migration script that renames deprecated relationship frontmatter keys in all `.md` files under `.issues/`: `parent_issue:` → `parent:` and `related:` → `relates_to:`. Part of the ENH-1434 relationship field standardization.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned renames without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-relationships --dry-run   # Preview all planned renames
ll-migrate-relationships             # Execute migration
ll-migrate-relationships --config /path/to/project  # Run for a specific project
```

---
```

**`skills/configure/areas.md`** — replace line 823 description string:
- Before: `"Authorize all 17 ll- CLI tools and handoff write: ..., ll-migrate, ll-create-extension, ll-logs, Write(...)"`
- After: `"Authorize all 18 ll- CLI tools and handoff write: ..., ll-migrate, ll-migrate-relationships, ll-create-extension, ll-logs, Write(...)"`

**Correction**: `test_configure_areas_count_is_17` belongs to `TestFeat1229LlActionWiring`, not `TestConfigureAreasWiring` — verified against actual test file (line 198). Both methods assert `"Authorize all 17"` and need the same string change to `"Authorize all 18"`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

16. Add `TestEnh1435LlMigrateRelationshipsWiring` class to `scripts/tests/test_create_extension_wiring.py` — 4 presence assertions (`"ll-migrate-relationships" in content`) for `HELP_MD`, `CLAUDE_MD`, `CLI_REFERENCE`, and `README`. Follow the `TestFeat1229LlActionWiring` pattern (lines 172–204). This class uses the module-level path constants already defined in the file.

**Note**: Steps 14, 15, and 16 must land in the same PR — doc changes and all tests verifying them (count assertions + presence assertions) are tightly coupled. Apply all 5 doc files and both test files together.

## Integration Map

### Files to Modify
- `.claude/CLAUDE.md` — add `ll-migrate-relationships` bullet to CLI Tools list
- `README.md` — tool count `"18 CLI tools"` → `"19 CLI tools"`; add `### ll-migrate-relationships` section
- `commands/help.md` — add `ll-migrate-relationships` line in CLI TOOLS block
- `docs/reference/CLI.md` — add `### ll-migrate-relationships` section (flags table + examples)
- `skills/configure/areas.md` — `"Authorize all 17"` → `"Authorize all 18"`; add tool to enumerated list
- `scripts/tests/test_create_extension_wiring.py` — four count assertion updates
- `scripts/tests/test_ll_logs_wiring.py` — one count assertion update

### Similar Patterns (Template Files)
- ENH-1420 commit — shows exactly how `ll-migrate` was added to the same set of files

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests to update** (Step 15 — count assertions):
- `scripts/tests/test_create_extension_wiring.py` — 4 count assertions (already in Files to Modify):
  - `TestFeat1045DocUpdates.test_readme_tool_count_is_18` — `"18 CLI tools"` → `"19 CLI tools"`
  - `TestFeat1229LlActionWiring.test_readme_tool_count_is_18` — `"18 CLI tools"` → `"19 CLI tools"`
  - `TestConfigureAreasWiring.test_count_updated_to_17` — `"Authorize all 17"` → `"Authorize all 18"`
  - `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` — `"Authorize all 17"` → `"Authorize all 18"`
- `scripts/tests/test_ll_logs_wiring.py` — 1 count assertion (already in Files to Modify):
  - `TestConfigureAreasWiring.test_authorize_all_count_is_17` — `"Authorize all 17"` → `"Authorize all 18"`

**New tests to write** (Step 16 — presence assertions, following established pattern):

Add a new test class `TestEnh1435LlMigrateRelationshipsWiring` in `scripts/tests/test_create_extension_wiring.py` following the same pattern as `TestFeat1229LlActionWiring` (lines 172–204):
```python
class TestEnh1435LlMigrateRelationshipsWiring:
    """ENH-1435: ll-migrate-relationships must be registered in all 4 doc files."""

    def test_help_md_lists_ll_migrate_relationships(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-migrate-relationships" in content

    def test_claude_md_lists_ll_migrate_relationships(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-migrate-relationships" in content

    def test_cli_reference_has_ll_migrate_relationships_section(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-migrate-relationships" in content

    def test_readme_has_ll_migrate_relationships_section(self) -> None:
        content = README.read_text()
        assert "ll-migrate-relationships" in content
```

**Tests confirmed NOT affected:**
- `scripts/tests/test_migrate_relationships.py` — functional CLI tests for the migration logic; no doc assertions; no changes needed
- `scripts/tests/test_cli_docs.py` — uses synthetic `tmp_path` fixtures; not affected
- `scripts/tests/test_doc_counts.py` — uses synthetic `tmp_path` fixtures; not affected
- `scripts/tests/test_issue_migration.py` — tests `ll-migrate` CLI logic; no doc-count or list assertions

## Acceptance Criteria

- `README.md` reads `"19 CLI tools"` and includes a `### ll-migrate-relationships` section
- `commands/help.md` lists `ll-migrate-relationships` in the CLI TOOLS block
- `docs/reference/CLI.md` includes a `### ll-migrate-relationships` section with flags and examples
- `skills/configure/areas.md` reads `"Authorize all 18"` and lists `ll-migrate-relationships`
- All count assertion tests pass (`test_create_extension_wiring.py` and `test_ll_logs_wiring.py`)
- New `TestEnh1435LlMigrateRelationshipsWiring` class passes (all 4 presence assertions)

## Scope Boundaries

- **In scope**: Doc registration for the new CLI and count assertion test sync
- **Out of scope**: The CLI implementation itself (ENH-1434), schema changes (ENH-1430)
- **Depends on**: ENH-1434 — CLI must exist before docs reference it

## Resolution

Implemented Steps 14, 15, and 16 together in one pass:
- Added `ll-migrate-relationships` entry to `.claude/CLAUDE.md`, `README.md`, `commands/help.md`, `docs/reference/CLI.md`, and `skills/configure/areas.md`
- Incremented README count `"18 CLI tools"` → `"19 CLI tools"`
- Updated `"Authorize all 17"` → `"Authorize all 18"` in `skills/configure/areas.md`
- Updated 4 count assertions in `test_create_extension_wiring.py` and 1 in `test_ll_logs_wiring.py`
- Added `TestEnh1435LlMigrateRelationshipsWiring` class with 4 presence assertions (all passing)
- All 36 tests pass

## Session Log
- `/ll:ready-issue` - 2026-05-11T00:34:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2dc0bf31-d1cf-4179-938d-2d3c33713f1b.jsonl`
- `/ll:wire-issue` - 2026-05-11T00:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0d4d572-037b-4532-8e35-dccea4423a93.jsonl`
- `/ll:refine-issue` - 2026-05-11T00:24:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45131201-1b9b-478e-8183-3c238b1c70f6.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98a93952-5a1f-4e01-9075-6dbfef3784ef.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9bfe60a5-1759-442f-af25-52e19b1521e4.jsonl`
