---
id: ENH-1904
title: Mine user corrections from backfilled message_events
type: ENH
priority: P2
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T19:50:05Z'
completed_at: '2026-06-03T20:47:49Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1887
- ENH-1831
- ENH-1830
- ENH-1847
- ENH-1888
labels:
- captured
- history-db
decision_needed: false
confidence_score: 100
outcome_confidence: 85
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
---

# ENH-1904: Mine user corrections from backfilled message_events

## Summary

`user_corrections` in `.ll/history.db` has **1 row** despite **9,657** rows in
`message_events`. The correction detector (`is_correction()` /
`record_correction()` in `scripts/little_loops/session_store.py`) is invoked
**only** from `hooks/user_prompt_submit.py` — a live, forward-only path. The
backfill path that seeds `message_events` (`_backfill_messages()`, ~line 862)
writes raw rows via `INSERT INTO message_events` but never runs the correction
detector over historical messages. As a result the corrections corpus that
EPIC-1707's consumer skills depend on is effectively empty.

## Current Behavior

- `_backfill_messages()` ingests user blocks from session JSONL into
  `message_events` only; it does not call `is_correction()` or
  `record_correction()`.
- Corrections are captured solely going forward, per live prompt, and only when
  the prompt matches the prefix/phrase regexes in `is_correction()`.
- `user_corrections` = 1 row across 3,973 sessions.

## Expected Behavior

- During backfill (`backfill()` / `backfill_incremental()` →
  `_backfill_messages()`), each historical user message is run through
  `is_correction()`, and matches are persisted via `record_correction()`
  (respecting the `analytics.capture.corrections` gate from ENH-1831/1841).
- A one-time mining pass over the existing 9,657 `message_events` populates
  `user_corrections` so the consumer skills have signal to read.
- Idempotent: re-running backfill does not duplicate correction rows.

## Motivation

EPIC-1707's headline success metric is *"a measurable reduction in repeated
user_corrections on the same topic."* The 5 consumer skills (`refine-issue`,
`ready-issue`, `confidence-check`, `go-no-go`, `capture-issue`) read
`user_corrections` via `ll-history-context`. With the table near-empty, the
entire consumer surface reads nothing — the EPIC's value proposition does not
land regardless of how many skills are wired.

## Success Metrics

- `user_corrections` row count: 1 → meaningfully > 1 after one-time mining pass over 9,657 existing `message_events`.
- Re-running backfill produces 0 duplicate rows (idempotency verified).
- `analytics.capture.corrections = false` config gate produces 0 new rows during backfill.

## Scope Boundaries

- **In scope**: Threading `is_correction()` into `_backfill_messages()`, idempotency guard on `(session_id, content)`, config-gate respect, one-time mining pass over existing `message_events`.
- **Out of scope**: Changing `is_correction()` detection logic or phrase regexes, modifying the live `user_prompt_submit.py` forward path, adding new correction categories, reporting or visualization of mined corrections.

## Proposed Solution

### Option A: Inline correction insert into `_backfill_messages()` using shared `conn`

> **Selected:** Option A — consistent with all other backfill helpers (`_backfill_issues`, `_backfill_sessions`), avoids per-match connection overhead, and directly reusable test scaffolding.

Add a `config: dict | None = None` parameter to `_backfill_messages()` (and
thread it through `backfill()` and `backfill_incremental()`). After the
`message_events` insert, run `is_correction(text)` and write directly via
`conn.execute("INSERT OR IGNORE INTO user_corrections ...")` using the shared
connection. A v9 migration creates the unique index that makes `INSERT OR IGNORE`
effective. A sibling `mine_corrections_from_messages(db, config=None)` function
handles the one-time pass over already-backfilled `message_events` rows.

- **Pros**: Single commit per backfill; no extra connections; consistent with how
  `_backfill_issues()` (line 637) and `_backfill_sessions()` (line 946) work.
- **Cons**: Duplicates the `_index()` + truncation logic from `record_correction()`.
  Future changes to correction-write semantics must be made in two places.

### Option B: Call `record_correction()` per match via `db_path`

Add `db_path: Path | str` and `config: dict | None = None` parameters to
`_backfill_messages()`. For each correction match, call `record_correction(db_path,
session_id, text, "backfill", config=config)`. Add idempotency by adding the v9
unique index migration so `record_correction()`'s bare INSERT silently fails on
duplicate; OR pre-check with `SELECT 1 FROM user_corrections WHERE session_id=?
AND content=?` before each call.

- **Pros**: Reuses existing `record_correction()` (single source of truth for the
  write path, including FTS indexing and truncation).
- **Cons**: `record_correction()` (lines 401–431) opens its own connection via
  `connect(db_path)` — one extra connection open/close per matching message
  (slow for bulk; 9,657 messages could yield hundreds of connections). Also
  requires changing `_backfill_messages()` signature to accept `db_path`.

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

**Connection mismatch (critical implementation detail):** `_backfill_messages()`
(line 861) takes `conn: sqlite3.Connection` but `record_correction()` (line 401)
calls `connect(db_path)` to open its own connection — they cannot share the
backfill transaction. Option A avoids this by inlining the SQL; Option B requires
passing `db_path` into the backfill function and accepts the per-match connection
overhead.

**`user_corrections` has no unique index** (schema defined at migration v0, lines
173–179): `id AUTOINCREMENT`, `ts`, `session_id`, `content`, `source` — no
unique constraint. The v9 migration needed: `CREATE UNIQUE INDEX IF NOT EXISTS
idx_corrections_dedup ON user_corrections(session_id, content)`, mirroring v3's
`idx_issue_events_dedup` (lines 205–209). Note: SQLite treats two `NULL` values
as distinct in a unique index, but in practice backfill always resolves
`session_id` from JSONL `sessionId` field (line 886).

**`message_events` also has no unique index** — `_backfill_messages()` does a
bare `INSERT` (line 905–907), not `INSERT OR IGNORE`. Re-running the full
`backfill()` on the same JSONL files would duplicate `message_events` rows too.
The idempotency protection today is file-mtime filtering in
`backfill_incremental()`. This is an existing limitation, not introduced by this
ENH — but the correction mining pass must be robust to pre-existing duplicates.

**`analytics.capture.corrections` defaults to `True`** (permissive when absent):
`AnalyticsCaptureConfig.from_dict()` does `data.get("corrections", True)` (line
445 in `config/features.py`). The gate is also checked inside `record_correction()`
itself when `config=` is passed — but the live hook at `user_prompt_submit.py:70`
applies the gate _before_ calling `record_correction()` and does not re-pass
`config=`. The backfill path should gate consistently via the same
`AnalyticsCaptureConfig` check.

**One-time mining pass** for the existing 9,657 `message_events` rows: add
`mine_corrections_from_messages(db, config=None) -> int` that runs
`SELECT ts, session_id, content FROM message_events` and calls the correction
insert for each match. Call it from `backfill()` after `_backfill_messages()`.
With the unique index in place, repeated calls are safe (idempotent via `INSERT OR
IGNORE`).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-03.

**Selected**: Option A — Inline correction insert into `_backfill_messages()` using shared `conn`

**Reasoning**: Option A scores 11/12 versus Option B's 6/12. Every other backfill helper (`_backfill_issues()` line 637, `_backfill_sessions()` line 946) already uses `INSERT OR IGNORE` with the shared `conn` — inlining the correction write is the dominant codebase pattern. Option B's `record_correction()` opens its own connection per match, which is a concrete performance risk across ~9,657 messages; threading `db_path` into backfill helpers also breaks the established signature contract.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (inline, shared conn) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B (call record_correction()) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: `_backfill_issues()` (line 637) and `_backfill_sessions()` (line 946) both use `INSERT OR IGNORE` with shared `conn`; v3 `idx_issue_events_dedup` migration (lines 205–209) provides the exact template for the required v9 unique index; `TestBackfillMessages._user_record()` (line 451) is directly reusable for new test cases.
- Option B: `record_correction()` (lines 401–431) calls `connect(db_path)` internally, opening one extra connection per matching message — potentially hundreds for a bulk pass; passing `db_path` into `_backfill_messages()` contradicts how all other backfill helpers take `conn`; bare `INSERT` in `record_correction()` has no idempotency guard until the v9 migration is added anyway.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_backfill_messages()` (line 861),
  `backfill()` (line 962), `backfill_incremental()` (line 994); add correction
  mining into the backfill loop and a new `mine_corrections_from_messages()`
  function for the one-time pass over existing rows.
- `scripts/little_loops/session_store.py` — `_MIGRATIONS` list (line 136): add
  v9 migration to create `idx_corrections_dedup` unique index on
  `user_corrections(session_id, content)` so `INSERT OR IGNORE` can enforce
  idempotency (mirrors v3 `idx_issue_events_dedup` pattern at lines 205–209).
- `scripts/little_loops/cli/session.py` — `main_session()` backfill branch
  (lines 247–284): add `corrections={counts.get('corrections', 0)}` to the
  `logger.success` format string.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py` — existing live
  correction-capture path via `handle()` (line ~53); must remain unchanged
- `scripts/little_loops/cli/session.py` — `ll-session backfill` entry point;
  `_build_parser()` at line 106, dispatch at lines 247–284
- Consumer skills (`refine-issue`, `ready-issue`, `confidence-check`,
  `go-no-go`, `capture-issue`) — read `user_corrections` via `ll-history-context`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py` — `_run_backfill()` (inner
  function, line ~127) calls `backfill_incremental(_db_path, jsonl_files=...)`
  **without** passing a `config` dict; corrections gate will default to `True`
  (permissive) via `AnalyticsCaptureConfig.from_dict(None)`. No code change
  needed unless the gate must be honored at session-start time — document this
  behavioral default in the implementation.

### Similar Patterns
- `_backfill_sessions()` idempotency: `INSERT OR IGNORE` + `PRIMARY KEY` (lines
  944–950); `_backfill_issues()` uses same pattern with named unique index (line
  751) — replicate for corrections
- v3 migration (`idx_issue_events_dedup`): `CREATE UNIQUE INDEX IF NOT EXISTS
  idx_issue_events_dedup ON issue_events(issue_id, transition)` (lines 205–209)
  — add analogous v9 migration for `user_corrections`
- `TestBackfillMessages._user_record()` helper (line 451) — reuse in new tests
  to construct JSONL fixture data

### Tests
- `scripts/tests/test_session_store.py` class `TestBackfillMessages` (lines
  448–531) — add methods: assert backfill with a correction-pattern message
  populates `user_corrections`; assert `capture.corrections: false` gate
  produces 0 rows; assert running backfill twice on same JSONL produces exactly
  1 correction row (idempotency).
- Add `TestMineCorrectionsFromMessages` class or methods: assert
  `mine_corrections_from_messages()` picks up pre-existing `message_events`
  rows; assert idempotency on repeated calls; assert config gate.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py` line 1041 — `TestSchemaV6.test_schema_version_is_seven`:
  `assert SCHEMA_VERSION == 8` **will break** when `SCHEMA_VERSION` is bumped to 9;
  update to `== 9`.
- `scripts/tests/test_session_store.py` lines 1346–1347 — `TestCliEventContext.test_schema_v8_cli_events_table_exists`:
  both `assert SCHEMA_VERSION == 8` and `assert int(row[0]) == 8` **will break**;
  update both to `== 9`.
- Add `TestSchemaV9` class in `test_session_store.py` (following the
  `TestCliEventContext` pattern at line 1334): assert `idx_corrections_dedup`
  index exists on `user_corrections`; assert `SCHEMA_VERSION == 9` and
  `int(row[0]) == 9` after `ensure_db()`; assert v8→v9 migration: bootstrap a
  v8 schema manually (with `cli_events` table, no `idx_corrections_dedup`), call
  `ensure_db()`, assert index now present and version == 9.
- `scripts/tests/test_ll_session.py` — `TestMainSession.test_backfill_reports_messages_count`
  (line 182): add `assert "corrections=0" in out` to cover the new
  `corrections={counts.get('corrections', 0)}` field in the `logger.success`
  format string. (Note: `"Backfilled 12"` total assertion still passes since
  `.get('corrections', 0)` = 0 when mock lacks the key — test will not break
  but is incomplete without this new assertion.)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — section "**`history.db` schema versions**": add v9
  row for `idx_corrections_dedup`; update three occurrences of `v1–v8` (prose,
  component table, Mermaid sequence diagram) to `v1–v9` [Agent 2 finding]
- `CONTRIBUTING.md` — directory-layout comment for `session_store.py` contains
  `v1–v8 migrations`; update to `v1–v9`; optionally add `mine_corrections_from_messages`
  to the function list [Agent 2 finding]
- `docs/reference/API.md` — `backfill` subcommand description in the
  `ll-session` section does not mention `corrections=` output field; add it
  [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` key `analytics.capture.corrections` (default `true`) —
  gate that controls whether correction mining runs during backfill; read via
  `AnalyticsCaptureConfig.from_dict()` in
  `scripts/little_loops/config/features.py:AnalyticsCaptureConfig` (line 426).

## Implementation Steps

1. **Add v9 DB migration** in `session_store.py:_MIGRATIONS` (after v8 at line
   259): `CREATE UNIQUE INDEX IF NOT EXISTS idx_corrections_dedup ON
   user_corrections(session_id, content)` — mirrors `_MIGRATIONS[2]` (v3) at
   lines 205–209.

2. **Add `mine_corrections_from_messages(db, config=None) -> int`** in
   `session_store.py`: query `SELECT ts, session_id, content FROM message_events`,
   run `is_correction(content)` on each row, and write matches via `INSERT OR
   IGNORE INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?,
   'backfill')` using a shared connection. Apply `AnalyticsCaptureConfig` gate
   before writing (matching the pattern at `record_correction()` lines 413–419).
   Return the count of rows actually inserted (check `cursor.rowcount`).

3. **Call `mine_corrections_from_messages()`** from `backfill()` (line 962):
   add `counts["corrections"] = mine_corrections_from_messages(conn, config)`.
   Also call from `backfill_incremental()` (line 994) so new sessions are mined
   on each incremental pass. Thread `config: dict | None = None` into both
   orchestrators and into `_backfill_messages()` if using Option A.

4. **Update CLI output** in `session_cli.py:main_session()` (lines 263–273):
   add `corrections={counts.get('corrections', 0)}` to the `logger.success`
   format string so the count is visible on `ll-session backfill`.

5. **Write tests** in `scripts/tests/test_session_store.py`:
   - Extend `TestBackfillMessages` (line 448): assert that a JSONL with a
     correction-pattern message (e.g. `"no, don't do that"`) causes backfill to
     populate `user_corrections` with 1 row (`recent(db, kind="correction")`).
   - Assert gate: pass `config={"analytics": {"capture": {"corrections": False}}}`
     and assert `user_corrections` remains empty (mirrors
     `test_record_correction_gate_disabled` at line 1229).
   - Assert idempotency: call `backfill()` twice with the same JSONL;
     assert `recent(db, kind="correction")` returns exactly 1 row (mirrors
     `TestBackfillDedup.test_double_backfill_produces_single_row` pattern).
   - Assert `mine_corrections_from_messages()` round-trip: seed
     `message_events` directly via `conn.execute(INSERT ...)`, call the
     function, assert row count and `recent(db, kind="correction")` content.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Fix two breaking test assertions** — in `scripts/tests/test_session_store.py`:
   - `TestSchemaV6.test_schema_version_is_seven` (line 1041): change `assert SCHEMA_VERSION == 8` → `== 9`
   - `TestCliEventContext.test_schema_v8_cli_events_table_exists` (lines 1346–1347): change both `== 8` → `== 9`

7. **Add `TestSchemaV9` class** to `scripts/tests/test_session_store.py` — verify
   `idx_corrections_dedup` exists after `ensure_db()`, `SCHEMA_VERSION == 9`,
   and that a manually-bootstrapped v8 schema migrates to v9 correctly.

8. **Update `test_ll_session.py`** — add `assert "corrections=0" in out` to
   `TestMainSession.test_backfill_reports_messages_count` (line 182) to cover the
   new `corrections=` field in the CLI success output.

9. **Update documentation** with schema v9 references:
   - `docs/ARCHITECTURE.md`: add v9 row, update three `v1–v8` → `v1–v9` strings
   - `CONTRIBUTING.md`: update `v1–v8` → `v1–v9` in `session_store.py` description
   - `docs/reference/API.md`: add `corrections=N` to backfill output description

10. **Run one-time mine** over the existing DB:
   ```bash
   ll-session backfill   # next full backfill automatically calls mine_corrections_from_messages()
   ```
   Verify with `python -c "from little_loops.session_store import connect; c=connect('.ll/history.db'); print(c.execute('SELECT count(*) FROM user_corrections').fetchone())"` — row count should rise from 1 to a meaningful number.

## Impact

- **Priority**: P2 — unblocks the EPIC's core metric; cheap relative to payoff.
- **Effort**: Small-Medium.
- **Risk**: Low — additive; gated; idempotent.
- **Breaking Change**: No.

## Labels

`captured`, `history-db`

## Resolution

- Added v9 DB migration: `idx_corrections_dedup` unique index on `user_corrections(session_id, content)` enabling idempotent `INSERT OR IGNORE`
- Added `mine_corrections_from_messages(conn, config=None) -> int` that scans all `message_events`, applies `is_correction()`, and inserts matches via `INSERT OR IGNORE`
- Threaded `config: dict | None = None` into `backfill()` and `backfill_incremental()`; both now call `mine_corrections_from_messages()` and return `counts["corrections"]`
- Updated `ll-session backfill` CLI output to show `corrections=N`
- Fixed existing schema version assertions (v8 → v9) in two test classes
- Added `TestSchemaV9`, `TestMineCorrectionsFromMessages`, and three new `TestBackfillMessages` methods
- One-time mining pass: `user_corrections` 1 → 78 rows from 19,322 `message_events`; second run produces `corrections=0` (idempotency verified)

## Session Log
- `/ll:ready-issue` - 2026-06-03T20:36:29 - `01b723de-4602-463d-aef4-34abca28d9bb.jsonl`
- `/ll:confidence-check` - 2026-06-03T21:00:00Z - `05f0b8cd-d4c6-444a-8f99-5505d4cea6e9.jsonl`
- `/ll:wire-issue` - 2026-06-03T20:16:37 - `5cfac3fd-69b5-4992-849b-b3e21aecf055.jsonl`
- `/ll:decide-issue` - 2026-06-03T20:09:38 - `b6afb15c-f134-4ccb-92b1-d82d2072936c.jsonl`
- `/ll:refine-issue` - 2026-06-03T20:06:01 - `1558f3ff-28c1-450e-9bbc-b30a9621bda5.jsonl`
- `/ll:format-issue` - 2026-06-03T19:59:43 - `78944f8c-66dc-4a2a-ac84-0c737cbc3e68.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:50:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13a13638-9030-4da6-94ba-939418824572.jsonl`

---

**Open** | Created: 2026-06-03 | Priority: P2
