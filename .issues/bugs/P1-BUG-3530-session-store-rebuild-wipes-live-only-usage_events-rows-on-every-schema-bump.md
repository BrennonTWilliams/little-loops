---
id: BUG-3530
type: BUG
title: Session-store rebuild wipes live-only usage_events rows on every schema bump
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:32Z'
labels:
- observability
- history
confidence_score: 90
outcome_confidence: 59
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
---

# BUG-3530: Session-store rebuild wipes live-only usage_events rows on every schema bump

## Summary

`session_store.lifecycle.rebuild()` deletes every row of every table in `_REBUILD_TABLES`, which includes `usage_events`, then replays raw transcripts. Live per-invocation rows written by `record_usage_event` (FSM loop runs, ENH-2724) carry the FSM `state` and `run_id` and have no transcript source to replay from, so each rebuild permanently loses them. SessionStart requests a rebuild whenever `SCHEMA_VERSION` advances, so every schema bump silently destroys live usage history and its per-state attribution.

## Steps to Reproduce

1. Write a live row: call `record_usage_event(db, run_id="r1", ts=..., state="s1", model="sonnet", input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_creation_tokens=0)` (or finish any loop run with usage capture enabled).
2. Run `ll-session rebuild` (or bump `SCHEMA_VERSION` and start a session so SessionStart triggers the rebuild).
3. `SELECT count(*) FROM usage_events WHERE run_id = 'r1'` returns 0.

## Current Behavior

- `_REBUILD_TABLES` (`scripts/little_loops/session_store/lifecycle.py`) lists `usage_events`; `rebuild()` runs a DELETE over it before replay.
- `_backfill_usage_events` re-derives transcript usage with `state = NULL`; `record_usage_event` rows (state-attributed, from loop runs) are not reconstructible.
- `hooks/session_start.py` triggers `--rebuild` after a schema version advance, so the loss happens automatically, not only on a manual rebuild.
- The adjacent comment already documents this hazard for `prompt_opt_events` ("a wipe would destroy the live offer rows") — `usage_events` has the same property but is still wiped.

## Expected Behavior

A rebuild replaces only transcript-derived (replayable) usage rows. Live-only rows, their `run_id`/`state` association, and cost fields survive any number of rebuilds, and repeated rebuilds leave totals stable.

## Integration Map

- `scripts/little_loops/session_store/{lifecycle,writers,schema}.py`, `schema_manifest.json`, `scripts/little_loops/hooks/session_start.py`.
- `scripts/little_loops/cli/backfill_worker.py` — the detached worker SessionStart spawns; it passes `--rebuild` into `backfill_incremental(..., also_rebuild=True)`. This is the bridge from the version-advance check to `rebuild()`.
- Tests: `test_session_store_lifecycle.py`, `test_session_store_schema.py`, `test_session_store_writers.py`.
- Coordinated with ENH-3528, which plans host/provenance/channel columns on `usage_events`. This issue introduces the **channel** column; ENH-3528 reuses it rather than adding its own.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

**Conventions in force (pattern-finder):**
- `SCHEMA_VERSION` is derived from the length of `_MIGRATIONS` (`schema.py`, 52 entries at research time). Each change appends one entry with a leading `# vN (ISSUE-ID): ...` comment; `ensure_db`/`_apply_migrations` replay from the recorded version under one write lock. Column-add precedents on `usage_events`: v21 (`invocation_id`, `provider_vendor`) and v29 (`run_id` + index) — nullable, additive, no FK. v52 (`channels_json`) is fix-forward: no DEFAULT, no backfill.
- Contested/absent: no existing migration classifies legacy rows in place with an `UPDATE` (searched `ALTER TABLE`/`_MIGRATIONS` lines only, not full SQL bodies). The in-migration classification this issue requires has no confirmed precedent; the implementer must make that call knowingly.
- A schema bump touches four places that must move together: `schema_manifest.json` (checked by `TestSchemaManifest.test_schema_manifest_matches_checked_in_file`), the manifest-vs-live version test, the ~15 literal `SCHEMA_VERSION == 52` assertions in `test_session_store_schema.py` (e.g. near lines 650, 664, 716, 812), and `_reference_manifest_at(len(_MIGRATIONS))` (downgrade/heal path, BUG-3255; referenced by `test_history_store_chokepoint_gate.py`).
- Tables that cannot be replayed are excluded from `_REBUILD_TABLES` at table level, with a comment above the tuple (`lifecycle.py` ~926–939) stating why; `prompt_opt_events` is the precedent (excluded, then UPDATE-only `_backfill_prompt_opt` after replay). `usage_events` is the only tuple member that also receives live writes, and the `DELETE FROM {table}` loop in `rebuild()` has no per-table predicate today — a predicate is a new shape, and the exclusion tests (`test_<table>_excluded_from_rebuild_tables`, asserting tuple membership) would not cover it.
- `rebuild()` runs replay inside one `try/finally` with a single `conn.commit()` at the end; on exception the connection closes uncommitted, so DELETEs roll back implicitly (no explicit `rollback`). The rollback acceptance criterion depends on that property holding after the DELETE is narrowed.
- Test layout: migration tests are `TestSchemaVNN...` classes / `test_vN_db_upgrades_*` in `test_session_store_schema.py` (v52 class near line 3445); rebuild tests live in `test_session_store_lifecycle.py` (`test_rebuild_is_idempotent_for_usage` ~1918, `test_rebuild_does_not_touch_out_of_scope_tables` ~1759).
- Searched, no hits: no existing test injects a mid-`rebuild()` failure; no fixture DB pinned at a prior `SCHEMA_VERSION` was found (tests build fresh DBs via `ensure_db`; how `test_v8_to_v9_migration`-style tests construct their old DB was not confirmed). Both acceptance criteria that need these (rollback, pre-migration fixture) have no in-repo template.

## Impact

- **Priority**: P1 — silent, recurring data loss on every schema bump.
- **Effort**: Small to medium.
- **Risk**: Medium — touches rebuild; must not leave duplicate transcript rows.
- **Unblocks**: ENH-3528 and ENH-3532, whose migrations would otherwise trigger this loss.

## Acceptance Criteria

- [ ] Add a nullable `usage_events.channel` column (`'live'` | `'transcript'`) in an append-only migration at the next free schema version. `record_usage_event` writes `'live'`; `_backfill_usage_events` writes `'transcript'`.
- [ ] `rebuild()` deletes only `channel = 'transcript'` rows before replay. The discriminator is documented next to `_REBUILD_TABLES`. `run_id IS NULL` and `state IS NOT NULL` are **not** valid discriminators: backfill derives `run_id` via `_derive_run_id_for_ts`, and live rows permit `state=None`.
- [ ] Legacy classification happens inside the migration (before any rebuild can run): `session_id IS NOT NULL` → `'transcript'`, otherwise `'live'`. This is provable from the writers: `record_usage_event` has never inserted `session_id` (since ENH-2724, b06a15bba), and `_backfill_usage_events` always inserts it from the record's `sessionId`. No other `INSERT INTO usage_events` exists.
- [ ] Transcript records with no `sessionId` (which would be classified `'live'` and then recreated on replay) are handled explicitly: backfill either skips them or they get a documented `'unknown'` classification that is deleted on rebuild. Whatever the choice, repeated rebuilds must not grow totals.
- [ ] Rows written by `record_usage_event` survive `rebuild()` unchanged (count, `run_id`, `state`, token and cost columns), including live rows with `state=None`.
- [ ] Transcript rows carrying a non-null derived `run_id` are still replaced by replay; running `rebuild()` twice yields identical `usage_events` totals.
- [ ] Migration test on an **actual pre-migration database** (fixture at the prior `SCHEMA_VERSION`, with mixed live and transcript rows): after migration and the rebuild it triggers, live rows are intact and there are no duplicate transcript rows.
- [ ] If replay raises mid-rebuild, the delete is rolled back, so no transcript rows are lost and live rows are untouched.
- [ ] The SessionStart version-advance path is covered end to end (`session_start` → `backfill_worker --rebuild` → `rebuild`), not only a direct `rebuild()` call.
- [ ] `schema_manifest.json`/version pins updated together.

## Program Design

### Types

- `channel: str | None` — new nullable `usage_events` column, `'live'` or `'transcript'` (acquisition channel, shared with ENH-3528). Legacy rows are classified by `session_id` presence in the migration.

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — signature unchanged; deletes only replayable usage rows before replay.
- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int, cache_creation_tokens: int) -> None` — signature unchanged; inserts `channel = 'live'`.

### Call Path

- SessionStart version advance → `backfill_worker --rebuild` → `backfill_incremental` → `rebuild` → `_backfill_usage_events`
- `record_usage_event` rows must survive `rebuild`.

## Verification Notes

Verdict: **VALID** (2026-09-23). `usage_events` is in `_REBUILD_TABLES` and is `DELETE`d wholesale (`lifecycle.py:940-951, 986-987`); `_backfill_usage_events` writes `state = NULL`; `record_usage_event` (`writers.py:1929`) inserts with `run_id`; SessionStart appends `--rebuild` when `last_rebuild_version < SCHEMA_VERSION` (`session_start.py:196`). `ll-verify-evidence` clean.

~~Design note: a narrowed `DELETE FROM usage_events WHERE run_id IS NULL` may need no new column.~~ **Withdrawn (2026-09-23)**: transcript backfill assigns `run_id` via `_derive_run_id_for_ts` (`writers.py:3623`), so that filter would leave stale transcript rows and duplicate them on replay. Resolved to the `channel` column; see Acceptance Criteria.

**Design decision (2026-09-23)**: this issue adds the `channel` column. It is itself a schema bump, so it triggers the rebuild it fixes. Legacy rows must therefore be classified inside the migration, before the first rebuild after the version advance runs.

## Status

**Open** | Created: 2026-09-24 | Priority: P1

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23 (re-scored 2026-09-23)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Concerns
- Internal contradiction on the delete predicate: Acceptance Criteria say `rebuild()` deletes only `channel = 'transcript'`, but the Scope Boundary note (audit-issue-conflicts) requires deleting every replayable channel (incl. ENH-3532 Codex `rollout` rows). Reconcile the AC to "delete all replayable channels" and add the rollout-not-duplicated criterion.
- The no-`sessionId` transcript-record policy is left as "skip or `'unknown'`" — pick one before implementing.
- The Verification Notes' design hint (`DELETE ... WHERE run_id IS NULL`, no migration) is contradicted by code: `_backfill_usage_events` derives `run_id` for transcript rows via a timestamp-window join (`writers.py:_derive_run_id_for_ts`, ENH-2725), so backfilled rows can carry a `run_id`. That filter would leave stale transcript rows and cause duplicates on replay. Live rows may also have `state=None`, so `state IS NOT NULL` isn't a safe discriminator either.

### Outcome Risk Factors
- ~~Unresolved design decision: nullable `origin` column vs. a narrowed DELETE; legacy-row policy undecided.~~ Resolved 2026-09-23: a `channel` column, with legacy rows classified by `session_id` presence in the migration.
- Broad change surface: `usage_events` is referenced in ~24 modules, and a schema migration itself triggers a rebuild on every consuming project (the very path under repair).
- Moderate per-site complexity: rebuild semantics, idempotency across repeated rebuilds, duplicate-row risk.

## Session Log
- `/ll:decide-issue` - 2026-09-24T01:27:18 - `34910629-d012-4bc0-9f28-9b313ee78c98.jsonl`
- `/ll:confidence-check` - 2026-09-24T01:24:53 - `f2782d90-4a24-474c-afe0-ce24c17410f3.jsonl`
- `/ll:refine-issue` - 2026-09-24T01:11:53 - `b8e8635a-fb67-47b8-a409-92a092610b22.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:confidence-check` - 2026-09-24T00:45:00 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue owns the `channel` column. `rebuild()` must delete every replayable channel (`transcript` and the Codex `rollout` rows ENH-3532 ingests), not only `channel = 'transcript'`, otherwise replay duplicates rollout rows and inflates totals. Add an acceptance criterion that ENH-3532 rollout rows are replaced, not duplicated, on rebuild. See ENH-3532.
