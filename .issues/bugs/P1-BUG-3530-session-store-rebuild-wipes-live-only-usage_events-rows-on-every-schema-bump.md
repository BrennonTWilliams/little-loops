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
confidence_score: 95
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
- Tests: `test_session_store_lifecycle.py`, `test_session_store_schema.py`, `test_session_store_writers.py`.

## Impact

- **Priority**: P1 — silent, recurring data loss on every schema bump.
- **Effort**: Small to medium.
- **Risk**: Medium — touches rebuild; must not leave duplicate transcript rows.
- **Unblocks**: ENH-3528 and ENH-3532, whose migrations would otherwise trigger this loss.

## Acceptance Criteria

- [ ] Rows written by `record_usage_event` survive `rebuild()` unchanged (count, `run_id`, `state`, token and cost columns).
- [ ] Transcript-derived usage rows are still replaced by replay; running `rebuild()` twice yields identical `usage_events` totals.
- [ ] The SessionStart version-advance path is covered, not only a direct `rebuild()` call.
- [ ] The mechanism distinguishing live from replayable rows is documented next to `_REBUILD_TABLES` (e.g. a nullable origin column via an append-only migration, or a narrowed `DELETE ... WHERE <replayable>`). Existing rows with unprovable origin follow a documented policy.
- [ ] `schema_manifest.json`/version pins updated together if a migration is added.

## Program Design

### Types

- `origin: str | None` — candidate nullable `usage_events` column (`live` vs `transcript`) if the fix chooses the column approach; legacy rows need a documented policy.

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — signature unchanged; deletes only replayable usage rows before replay.
- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int, cache_creation_tokens: int) -> None` — marks rows live (if the column approach is chosen).

### Call Path

- SessionStart version advance → `rebuild` → `_backfill_usage_events`
- `record_usage_event` rows must survive `rebuild`.

## Verification Notes

Verdict: **VALID** (2026-09-23). `usage_events` is in `_REBUILD_TABLES` and is `DELETE`d wholesale (`lifecycle.py:940-951, 986-987`); `_backfill_usage_events` writes `state = NULL`; `record_usage_event` (`writers.py:1929`) inserts with `run_id`; SessionStart appends `--rebuild` when `last_rebuild_version < SCHEMA_VERSION` (`session_start.py:196`). `ll-verify-evidence` clean.

Design note: `usage_events.run_id` already exists (v29, ENH-2723) and `record_usage_event` requires it, while transcript-backfilled rows leave it NULL. A narrowed `DELETE FROM usage_events WHERE run_id IS NULL` may therefore need no new column or migration; worth weighing against the `origin` column candidate in Program Design.

## Status

**Open** | Created: 2026-09-24 | Priority: P1

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Concerns
- The Verification Notes' design hint (`DELETE ... WHERE run_id IS NULL`, no migration) is contradicted by code: `_backfill_usage_events` derives `run_id` for transcript rows via a timestamp-window join (`writers.py:_derive_run_id_for_ts`, ENH-2725), so backfilled rows can carry a `run_id`. That filter would leave stale transcript rows and cause duplicates on replay. Live rows may also have `state=None`, so `state IS NOT NULL` isn't a safe discriminator either.

### Outcome Risk Factors
- Unresolved design decision: nullable `origin` column (append-only migration, schema_manifest/version pins) vs. a narrowed DELETE — must be chosen before implementing; legacy-row policy also undecided.
- Broad change surface: `usage_events` is referenced in ~24 modules, and a schema migration itself triggers a rebuild on every consuming project (the very path under repair).
- Moderate per-site complexity: rebuild semantics, idempotency across repeated rebuilds, duplicate-row risk.

## Session Log
- `/ll:confidence-check` - 2026-09-24T00:45:00 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`
