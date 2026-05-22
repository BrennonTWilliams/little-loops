---
id: ENH-1551
type: enhancement
priority: P3
status: done
completed_at: 2026-05-17T09:26:50Z
labels: [migration, issue-management, cleanup, one-shot]
parent: ENH-1539
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
implementation_order_risk: true
---

# ENH-1551: Status one-shot cleanup pass for non-canonical values in .issues/

## Summary

Run a targeted rewrite of existing `.issues/**/*.md` files that contain non-canonical `status:` values (`completed`, `in`, `proven`, or any truncation), committing them as a single normalization pass and verifying the result with grep.

## Current Behavior

Five `.issues/` files have `status: completed` in their frontmatter — a non-canonical value. The parser (ENH-1549) normalizes on read via `STATUS_SYNONYMS`, so tooling sees `done` at runtime, but on-disk values remain non-canonical and will confuse direct `grep` queries or non-Python consumers.

## Expected Behavior

All `.issues/**/*.md` files have only the 6 canonical status values on disk: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. The verification command outputs exactly those 6 values and nothing else.

## Scope Boundaries

- **In scope**: `status:` frontmatter fields in `.issues/**/*.md` files only
- **Out of scope**: `status:` appearing in issue body text (e.g., FEAT-1287 line 102 YAML block); code files; configuration files; any other field name

## Parent Issue

Decomposed from ENH-1539: Normalize status synonyms and document canonical enum

## Proposed Solution

### 1. Identify all non-canonical values

```bash
grep -rn "^status: " .issues/ | grep -v "status: open\|status: in_progress\|status: blocked\|status: deferred\|status: done\|status: cancelled" | sort
```

Expected output (~5-10 files at time of writing): `status: completed`, `status: proven`, and possibly truncations.

### 2. Rewrite script

Write a short Python script (or inline `sed`) that applies the same `STATUS_SYNONYMS` map to on-disk files:

```python
import re, pathlib

SYNONYMS = {
    "complete": "done", "completed": "done", "finished": "done", "closed": "done",
    "in-progress": "in_progress", "in progress": "in_progress", "wip": "in_progress",
    "proven": "done",  # one-off stray value found in snapshot
}

issues_root = pathlib.Path(".issues")
for f in issues_root.rglob("*.md"):
    text = f.read_text()
    updated = re.sub(
        r"^(status: )(\S+)$",
        lambda m: m.group(1) + SYNONYMS.get(m.group(2), m.group(2)),
        text,
        flags=re.MULTILINE,
    )
    if updated != text:
        f.write_text(updated)
        print(f"Normalized: {f}")
```

### 3. Run and commit

```bash
python scripts/normalize_status.py  # or inline
git add .issues/
git commit -m "chore(issues): normalize non-canonical status synonyms to canonical values"
```

Commit message should note: "one-shot rewrite; parser now normalizes on read so this won't recur".

### 4. Verify

```bash
grep -rn "^status: " .issues/ | grep -oE "status: [a-z_]+" | sort -u
```

Expected output (exactly these 6):
```
status: blocked
status: cancelled
status: deferred
status: done
status: in_progress
status: open
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact current state**: Exactly 5 files have non-canonical `status: completed` frontmatter values. `status: proven` appears only in body text of `FEAT-1287` (line 102), not in frontmatter — it is **not** a migration target. The "~5-10 files" estimate in the issue should be treated as exactly 5.

**Note on `proven` guard**: The proposed `SYNONYMS` dict in the script above includes `"proven": "done"` — this is a safe no-op guard since proven does not appear in any frontmatter. However, it does not need to be added to the permanent `STATUS_SYNONYMS` in `frontmatter.py`.

**Alternative implementation: Option B — Migration module pattern**

> **Selected:** Option B — Migration module pattern — all three existing migrations are wired CLI entry points with tests; STATUS_SYNONYMS, cli_args, and test templates are already present with zero new infrastructure required.

Instead of a temporary `normalize_status.py`, follow the established `ll-migrate-*` module pattern used by `migrate_relationships.py` and `migrate_labels.py`:

1. Create `scripts/little_loops/cli/migrate_status.py` with:
   - `_migrate_content(content: str) -> tuple[str, list[str]]` — apply `STATUS_SYNONYMS` regex substitution, return list of normalized field descriptions
   - `main_migrate_status() -> int` — walk `.issues/**/*.md`, apply transform, dry-run guard, print per-file report, return exit code 1 on any error
   - Import `STATUS_SYNONYMS` from `little_loops.frontmatter` (lines 17–25) — reuses the authoritative mapping

2. Wire in `scripts/little_loops/cli/__init__.py` following lines 47–49 and 73–75 (import + `__all__`)

3. Add entry point in `scripts/pyproject.toml` (lines 66–68 pattern): `ll-migrate-status = "little_loops.cli:main_migrate_status"`

4. Add tests at `scripts/tests/test_migrate_status.py` following `test_migrate_relationships.py` structure

**Trade-off**: Option A (standalone script) is faster and self-contained — right choice if this is truly a one-off. Option B (migration module) adds ~4 files but is consistent with codebase conventions and reusable if non-canonical values resurface. Both options are semantically equivalent for the 5 affected files.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation (Option B path):_

5. Update `docs/reference/CLI.md` — add `### ll-migrate-status` subsection after `### ll-migrate-labels` (line ~1270) with Flags table and Examples
6. Update `.claude/CLAUDE.md` — add `ll-migrate-status` bullet in `## CLI Tools` section
7. Update `scripts/little_loops/cli/__init__.py` — add `ll-migrate-status` to module docstring (lines 6–29)
8. Update `commands/help.md` — add `ll-migrate-status` row to tool listing table
9. Update `skills/configure/areas.md` — add `ll-migrate-status` to "All ll- commands" description; increment tool count

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-17.

**Selected**: Option B — Migration module pattern

**Reasoning**: Option B scores 10/12 vs. Option A's 7/12. All three existing migrations in this codebase (`migrate.py`, `migrate_relationships.py`, `migrate_labels.py`) are wired as full CLI entry points with tests — Option A (standalone throwaway script) has no migration-specific precedent and would be the only divergence from established convention. Every required component for Option B already exists: `STATUS_SYNONYMS` at `frontmatter.py:17`, `add_dry_run_arg`/`add_config_arg` in `cli_args.py`, and copy-adaptable test templates in `test_migrate_labels.py`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (standalone script) | 1/3 | 3/3 | 1/3 | 2/3 | 7/12 |
| Option B (migration module) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `doc_scraper.py` is the only non-wired standalone script precedent, but it is a utility tool, not a migration; all 3 existing migration scripts diverge from this pattern entirely
- Option B: `migrate_relationships.py` and `migrate_labels.py` are direct structural templates; `STATUS_SYNONYMS` at `frontmatter.py:17` is already imported by test files; `test_migrate_labels.py` test helpers (`_make_project`, `_run_migrate`) are copy-adaptable with zero new infrastructure

## Prerequisite

ENH-1549 should be merged first so the parser already normalizes on read and future files self-heal. This cleanup pass then brings the on-disk state into alignment with what parsers already see.

## Integration Map

### Issue Files with Non-Canonical Status (exactly 5, all `status: completed` → `done`)
- `.issues/enhancements/P3-ENH-1533-codex-agent-selection-ux-and-prompt-injection.md`
- `.issues/enhancements/P3-ENH-522-hybrid-relevance-scoring-for-ll-history-generate-docs.md`
- `.issues/enhancements/P4-ENH-467-add-missing-skills-to-command-tables.md`
- `.issues/enhancements/P3-ENH-653-init-interactive-add-tdd-mode-to-advanced-features.md`
- `.issues/enhancements/P2-ENH-1440-dependency-graph-get-execution-waves-soft-ordering-via-depends-on-edges.md`

### STATUS_SYNONYMS Source of Truth
- `scripts/little_loops/frontmatter.py` — `STATUS_SYNONYMS` constant (lines 17–25); import this for Option B migration module

### Files to Create/Modify (Option A — standalone script)
- `scripts/normalize_status.py` (temporary script — delete after running, or commit as a one-off migration tool)

### Files to Create/Modify (Option B — migration module pattern)
- `scripts/little_loops/cli/migrate_status.py` — new module; model after `scripts/little_loops/cli/migrate_relationships.py`
- `scripts/little_loops/cli/__init__.py` — add import + `__all__` entry (lines 47–49, 73–75 pattern)
- `scripts/pyproject.toml` — add `ll-migrate-status` entry point (lines 66–68 pattern)
- `scripts/tests/test_migrate_status.py` — new test file; model after `scripts/tests/test_migrate_relationships.py`

### Documentation

- No documentation updates needed for the canonical enum itself (ENH-1550 handled that)

_Wiring pass added by `/ll:wire-issue`:_

The new `ll-migrate-status` CLI tool must be registered in the same locations as other `ll-migrate-*` tools:
- `docs/reference/CLI.md` — add `### ll-migrate-status` subsection after `### ll-migrate-labels` (line ~1270), following the Flags table + Examples pattern used by the other three migration subsections [Agent 2 finding]
- `.claude/CLAUDE.md` — add `ll-migrate-status` bullet in the `## CLI Tools` section after the existing `ll-migrate-labels` entry [Agent 2 finding]
- `scripts/little_loops/cli/__init__.py` — module docstring (lines 6–29) enumerates all CLI tools; add `ll-migrate-status` line after `ll-migrate-labels` [Agent 2 finding]
- `commands/help.md` — add `ll-migrate-status` row to the tool listing table [Agent 2 finding]
- `skills/configure/areas.md` — add `ll-migrate-status` to the "All ll- commands" `description:` string (line ~823) and increment the tool count [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

Follow the `test_migrate_relationships.py` pattern (module-level import from `little_loops.cli.migrate_status` directly, not via `cli/__init__`):

- `scripts/tests/test_migrate_status.py` (new) — primary test file; model after `scripts/tests/test_migrate_relationships.py`; suggested test classes:
  - `TestMigrateStatusNormalization` — `test_renames_completed_to_done`, `test_renames_complete_to_done`, `test_renames_wip_to_in_progress`, `test_canonical_status_is_unchanged`, `test_file_without_status_is_unchanged`
  - `TestMigrateStatusDryRun` — `test_dry_run_makes_no_file_changes`, `test_dry_run_still_exits_zero`
  - `TestMigrateStatusEdgeCases` — `test_no_issues_dir_returns_error`, `test_already_canonical_file_is_unchanged`, `test_multiple_files_updated`, `test_all_synonyms_are_normalized`
- `scripts/tests/test_issue_parser_properties.py` — existing `TestStatusSynonyms` class tests `STATUS_SYNONYMS` invariants; no changes needed, but `migrate_status.py` must import from `frontmatter.py` (not define its own copy) to stay consistent [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

No callers require modification. All files that read issue status use `parse_frontmatter()` from `frontmatter.py`, which already normalizes via `STATUS_SYNONYMS` on read (ENH-1549). The on-disk migration is a one-way write; no callers break.

## Acceptance Criteria

1. `grep -rn "^status: " .issues/` output contains only the 6 canonical values
2. No `status: completed`, `status: proven`, or truncations remain in `.issues/`
3. Single clean commit with descriptive message

## Impact

- **Effort**: Minimal — 1 script run + 1 commit
- **Risk**: Low — semantic no-op (value meaning is preserved)
- **Dependency**: ENH-1549 (core normalization) should precede this for on-disk self-healing going forward

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Unresolved implementation path (Option A vs B): scope uncertainty — Option B touches 8 code/doc sites vs 1 standalone script for Option A. Resolve before implementing by running `/ll:decide-issue ENH-1551`.
- Tests are co-deliverables: `test_migrate_status.py` does not yet exist and must be authored during this implementation pass; write the tests before wiring the entry point so import errors surface early.
- Option B only — broad change surface across scripts, CLI wiring, and 4 documentation sites. If Option A is chosen, this risk evaporates entirely.

## Resolution

Implemented Option B (migration module pattern) as decided:

- Created `scripts/little_loops/cli/migrate_status.py` — imports `STATUS_SYNONYMS` from `frontmatter.py`, applies regex normalization to `status:` frontmatter fields, dry-run support
- Wired `main_migrate_status` into `scripts/little_loops/cli/__init__.py` (import + `__all__`)
- Added `ll-migrate-status` entry point in `scripts/pyproject.toml`
- Created `scripts/tests/test_migrate_status.py` with 12 tests covering normalization, dry-run, and edge cases
- Updated `docs/reference/CLI.md`, `.claude/CLAUDE.md`, `commands/help.md`, `skills/configure/areas.md`
- Ran migration: 5 files normalized (`status: completed` → `status: done`)
- Verified: `grep -rn "^status: " .issues/` shows only 6 canonical values in frontmatter

## Session Log
- `/ll:verify-issues` - 2026-05-22T16:11:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:ready-issue` - 2026-05-17T09:19:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c04248b-cf40-48f6-8529-813d82ec8b61.jsonl`
- `/ll:decide-issue` - 2026-05-17T09:14:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e6329ee2-2e87-4e97-85ea-e027a2f56866.jsonl`
- `/ll:refine-issue` - 2026-05-17T09:03:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b593fc76-d9f5-4eba-b981-1fff01eee5e6.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
- `/ll:wire-issue` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e728cfc1-f912-4a50-9931-2326282f6db6.jsonl`
- `/ll:confidence-check` - 2026-05-17T10:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa0fbe59-dc17-4625-9838-c69ad376e043.jsonl`
