---
id: ENH-1953
title: Schema v12 and data layer foundation for cross-session condensation
type: ENH
priority: P3
status: done
completed_at: 2026-06-05 01:03:27+00:00
parent: ENH-1927
relates_to:
- FEAT-1712
- BUG-1926
labels:
- enhancement
- history
- session-store
- schema
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1953: Schema v12 and data layer foundation for cross-session condensation

## Summary

Add the `level` column to `summary_nodes` table, a cross-session dedup index, and the `level` field to the `SummaryNode` dataclass — the data-layer prerequisite for recursive cross-session condensation (ENH-1927).

## Parent Issue

Decomposed from ENH-1927: Recursive cross-session condensation for a project-root summary

## Scope Boundaries

This child covers the schema and data-layer foundation that the condensation pass (ENH-1954) and N-level traversal (ENH-1955) build upon. It establishes the `level` column as the mechanism for distinguishing leaf (0), session-condensed (1), higher-order (2+), and root (max) nodes.

## Current Behavior

The `summary_nodes` table implements a two-level DAG (leaf and per-session condensed) via the v10 schema (FEAT-1712). Deduplication uses `idx_summary_nodes_condensed_dedup` (`UNIQUE(session_id) WHERE kind='condensed'`), which only covers per-session condensed nodes — rows with `session_id IS NULL` (cross-session) are not deduplicated. There is no mechanism to distinguish N-level condensation tiers in the DAG. `SCHEMA_VERSION` is 11, and the `SummaryNode` dataclass at `history_reader.py:108` lacks a `level` field.

## Expected Behavior

The `summary_nodes` table includes a `level INTEGER DEFAULT 0` column, with 0 = leaf/per-session-condensed, 1+ = cross-session condensed, and max = root. A new partial unique index `idx_summary_nodes_cross_dedup` on `(level, ts_start, ts_end) WHERE kind='condensed' AND session_id IS NULL` prevents duplicate cross-session condensed nodes. The existing `idx_summary_nodes_condensed_dedup` is unchanged for per-session dedup. `SCHEMA_VERSION` is 12, and `SummaryNode.level` is populated from the new column.

## Impact

- **Priority**: P3 — Foundational data-layer prerequisite for ENH-1954 and ENH-1955. No user-facing impact in isolation; enables the recursive condensation pipeline.
- **Effort**: Small — One `ALTER TABLE ADD COLUMN` + one partial unique index, following established v2 and v10 migration patterns. ~20 lines of migration SQL, ~60 lines of test code.
- **Risk**: Low — `DEFAULT 0` ensures backward compatibility for all existing rows. The new partial unique index only affects rows where `kind='condensed' AND session_id IS NULL`, leaving existing indexes untouched.
- **Breaking Change**: No — Existing consumers and queries continue to work without modification.

## Proposed Solution

Add the `level` column and cross-session dedup index to `summary_nodes` in a single v12 schema migration, following the established `ALTER TABLE ADD COLUMN` precedent from v2 (`session_store.py:220-225`) and the partial unique index pattern from v10 (`session_store.py:332-337`). Update the `SummaryNode` dataclass and its `ll_describe()` constructor to surface the new column. Bump `SCHEMA_VERSION` from 11 to 12 and update all hardcoded assertions.

This is a single-approach data-layer change — no architectural alternatives. `level` defaults to 0 so existing rows (both leaf and per-session condensed) are backward-compatible; the new partial unique index only affects rows where `kind='condensed' AND session_id IS NULL`, leaving the existing per-session dedup index untouched. The approach mirrors ENH-1942's v11 migration: one migration string appended to `_MIGRATIONS`, one version bump, one new test class (`TestSchemaV12`), and assertion updates in existing tests.

## Implementation Steps

### 1. Schema migration (v12)

Append to `_MIGRATIONS` (`session_store.py:164`) an `ALTER TABLE summary_nodes ADD COLUMN level INTEGER DEFAULT 0` + a new partial unique index for cross-session dedup:

```sql
CREATE UNIQUE INDEX idx_summary_nodes_cross_dedup
  ON summary_nodes(level, ts_start, ts_end)
  WHERE kind='condensed' AND session_id IS NULL
```

Follow Pattern 5a/5d for migration structure and testing. See existing migration v2 (`session_store.py:220-225`) for `ALTER TABLE ... ADD COLUMN` precedent.

### 2. Add `level` to `SummaryNode` dataclass

`history_reader.py:108` — Add `level: int | None` field. Update `ll_describe()` (`history_reader.py:785`) to populate it from the new column.

### 3. Revise dedup for cross-session nodes

`session_store.py:334` — The current `idx_summary_nodes_condensed_dedup` (`UNIQUE(session_id) WHERE kind='condensed'`) does not cover `session_id IS NULL` rows. The v12 migration adds a second partial unique index. The existing index remains unchanged for per-session dedup.

### 4. Version bump surface

Bump `SCHEMA_VERSION` from `11` to `12` in `session_store.py:75`.

Update all hardcoded `assert SCHEMA_VERSION == 11` assertions to `assert SCHEMA_VERSION == 12` (5 locations in `test_session_store.py`, 1 in `test_assistant_messages.py`):

| File | Line | Current Assertion | Change |
|------|------|-------------------|--------|
| `test_session_store.py` | 1104 | `assert SCHEMA_VERSION == 11` | → `12` (TestSchemaV6) |
| `test_session_store.py` | 1421 | `assert SCHEMA_VERSION == 11` | → `12` (TestCliEventContext) |
| `test_session_store.py` | 1505 | `assert SCHEMA_VERSION == 11` | → `12` (TestSchemaV9) |
| `test_session_store.py` | 1557 | `assert SCHEMA_VERSION == 11` | → `12` (TestSchemaV10) |
| `test_assistant_messages.py` | 88 | `assert SCHEMA_VERSION == 11` | → `12` |

Rename `test_schema_version_is_11` to `test_schema_version_is_12` in `test_assistant_messages.py:87`.

Assertions using `assert int(row[0]) == SCHEMA_VERSION` (relative to the constant) auto-follow and do NOT need manual bumping — there are 7 such locations across `test_session_store.py`.

### 5. Session store docstring

`session_store.py:305-314` — Update the module-level comment describing v10's two-level `summary_nodes` schema to reflect the v12 multi-level DAG structure.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_session_store.py:1422` — bump `assert int(row[0]) == 11` to `12` (adjacent to already-listed line 1421 in TestCliEventContext)
7. Update `scripts/tests/test_session_store.py:1506` — bump `assert int(row[0]) == 11` to `12` (adjacent to already-listed line 1505 in TestSchemaV9)
8. Update `scripts/tests/test_session_store.py:1558` — bump `assert int(row[0]) == 11` to `12` (adjacent to already-listed line 1557 in TestSchemaV10)
9. Update `scripts/tests/test_session_store.py:1636` — bump `assert int(version[0]) == 11` to `12` (TestSchemaV10.test_v9_to_v10_migration — hardcoded, not relative to SCHEMA_VERSION constant)
10. Update `scripts/tests/test_history_reader.py:933-942` — add `assert node.level == 0` to `test_ll_describe_returns_node_metadata` to validate the new field propagates correctly for existing leaf nodes
11. Update `scripts/little_loops/cli/session.py:374` — add `level` to `describe` subcommand output line (e.g., `f"id={node.id} kind={node.kind} level={node.level} session={node.session_id}"`) — soft coupling; no runtime breakage if deferred to ENH-1954/ENH-1955
12. Update `docs/ARCHITECTURE.md:549-564` — add v11 and v12 rows to schema versions table; broaden "v1–v10" references to "v1–v12" on lines 564, 607, 632

## Tests

Add `TestSchemaV12` to `scripts/tests/test_session_store.py` after line 1639, following the `TestSchemaV9` pattern (`test_session_store.py:1494-1543`) which is a closer match (one column + one index) than the larger TestSchemaV10:

```python
class TestSchemaV12:
    """Verify that the v12 migration adds level column and cross-session dedup index (ENH-1953)."""

    def test_schema_version_is_twelve(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 12
        assert int(row[0]) == 12

    def test_summary_nodes_has_level_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info('summary_nodes')")}
        finally:
            conn.close()
        assert "level" in cols

    def test_cross_dedup_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_cross_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "idx_summary_nodes_cross_dedup index must exist after ensure_db()"

    def test_v11_to_v12_migration(self, tmp_path: Path) -> None:
        """Bootstrap v11 schema, insert a row, migrate to v12, verify level=0 preserved."""
        db = tmp_path / "history.db"
        from little_loops.session_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for sql in _MIGRATIONS[:11]:  # v1–v11
                conn.executescript(sql)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '11')")
            # Insert a row to verify data preservation through ALTER TABLE ADD COLUMN
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
                " VALUES('condensed', 'pre-migration test', 100, 's-test', NULL, NULL, '2026-01-01T00:00:00Z')"
            )
            conn.commit()
        finally:
            conn.close()
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            cols = {r[1] for r in conn.execute("PRAGMA table_info('summary_nodes')")}
            index_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_cross_dedup'"
            ).fetchone()
            # Verify data preserved with level=0 (DEFAULT)
            row = conn.execute("SELECT level FROM summary_nodes WHERE kind='condensed'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert "level" in cols
        assert index_row is not None
        assert row is not None and row[0] == 0
```

Update `test_schema_version_is_11` → `test_schema_version_is_12` in `test_assistant_messages.py:87` and bump its assertion from `11` to `12` (line 88).

## Files to Modify

- `scripts/little_loops/session_store.py:75` — `SCHEMA_VERSION = 11` → `12`
- `scripts/little_loops/session_store.py:164` — `_MIGRATIONS` list (append v12 migration at index 11)
- `scripts/little_loops/session_store.py:305-314` — module docstring (update v10 two-level → v12 multi-level DAG description)
- `scripts/little_loops/history_reader.py:108-119` — `SummaryNode` dataclass (add `level: int | None` field)
- `scripts/little_loops/history_reader.py:785-808` — `ll_describe()` (add `level` to SELECT and manual constructor)
- `scripts/tests/test_session_store.py` — add `TestSchemaV12` class (after line 1639)
- `scripts/tests/test_session_store.py:1104,1421,1505,1557` — bump 4 hardcoded `SCHEMA_VERSION == 11` assertions to `12`
- `scripts/tests/test_assistant_messages.py:87-88` — rename `test_schema_version_is_11` → `test_schema_version_is_12`, bump assertion
- `scripts/tests/test_session_store.py:1422` — bump `assert int(row[0]) == 11` → `12` [wiring pass]
- `scripts/tests/test_session_store.py:1506` — bump `assert int(row[0]) == 11` → `12` [wiring pass]
- `scripts/tests/test_session_store.py:1558` — bump `assert int(row[0]) == 11` → `12` [wiring pass]
- `scripts/tests/test_session_store.py:1636` — bump `assert int(version[0]) == 11` → `12` [wiring pass]
- `scripts/tests/test_history_reader.py:933-942` — add `assert node.level == 0` to `test_ll_describe_returns_node_metadata` [wiring pass]
- `scripts/little_loops/cli/session.py:374` — add `level` to `describe` subcommand output (soft — no runtime breakage if deferred) [wiring pass]
- `docs/ARCHITECTURE.md:549-564,607,632` — add v11+v12 rows to schema versions table, broaden "v1–v10" references [wiring pass]

### Notes from codebase analysis

- `ll_describe()` at `history_reader.py:785-808` does NOT use the generic `_row_to_dataclass()` helper at line 183 — it manually constructs `SummaryNode(...)`. Both the SELECT column list AND the constructor call must include `level`. This is a common pitfall: adding the field to the dataclass alone will cause a `TypeError` at runtime because the constructor receives an unexpected keyword argument from the SELECT.
- The v10 module docstring at `session_store.py:305-314` currently describes a two-level DAG (leaf + condensed). This must be updated to reflect the v12 multi-level structure: level 0 = leaf/per-session-condensed, level 1+ = cross-session condensed, max level = root.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/session.py:364-378` — `describe` subcommand calls `ll_describe()` and manually prints `SummaryNode` fields (id, kind, session_id, ts_start, ts_end, tokens, created_at). Should add `level` to output for feature completeness. No runtime breakage if skipped; can be deferred to ENH-1954/ENH-1955.
- `scripts/tests/test_history_reader.py:933-942` — `test_ll_describe_returns_node_metadata` calls `ll_describe()` and asserts on returned fields. Should add `assert node.level == 0` to verify the default value propagates correctly for existing rows.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md:549-564` — Schema versions table currently lists v1–v10 only. Missing v11 entry (`assistant_messages` table + dedup index, ENH-1942) and v12 entry (`level` column + `idx_summary_nodes_cross_dedup`, this issue). Lines 564, 607, and 632 reference "v1–v10" and should broaden to "v1–v12".

### Additional Test Assertions to Bump

_Wiring pass added by `/ll:wire-issue`:_ The issue's change table covers the 5 `assert SCHEMA_VERSION == 11` lines. Four additional adjacent lines also hardcode `11` and must be bumped:

| File | Line | Current Assertion | Change |
|------|------|-------------------|--------|
| `test_session_store.py` | 1422 | `assert int(row[0]) == 11` | → `12` (TestCliEventContext) |
| `test_session_store.py` | 1506 | `assert int(row[0]) == 11` | → `12` (TestSchemaV9) |
| `test_session_store.py` | 1558 | `assert int(row[0]) == 11` | → `12` (TestSchemaV10) |
| `test_session_store.py` | 1636 | `assert int(version[0]) == 11` | → `12` (TestSchemaV10 migration) |

## Acceptance Criteria

- `ensure_db()` on a fresh DB creates `summary_nodes` with `level INTEGER DEFAULT 0` column
- `ensure_db()` on a v11 DB migrates to v12 without data loss (existing rows get `level=0`)
- `idx_summary_nodes_cross_dedup` exists and prevents duplicate cross-session condensed nodes
- `SummaryNode.level` is populated when reading from DB
- `test_schema_version_is_12` passes

## Session Log
- `/ll:ready-issue` - 2026-06-05T00:51:42 - `d59678ba-b279-4ad4-9cc9-01cc794a40ab.jsonl`
- `/ll:wire-issue` - 2026-06-05T00:45:02 - `c244634d-8d5a-4dc3-83b9-be722db5f226.jsonl`
- `/ll:refine-issue` - 2026-06-05T00:37:07 - `2e4997af-6c0d-416c-92a3-c29ce6846265.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:48:44Z - `0414437e-d0ef-4b95-b7ed-45d7f13cc1df.jsonl`
- `/ll:manage-issue` - 2026-06-05T01:03:27Z - `1d13b873-f994-495d-8ad5-97402f89fc61.jsonl`
