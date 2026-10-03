---
id: FEAT-3711
type: FEAT
title: ll-next recommendation_events, derived acceptance and time-based bucket pressure
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
relates_to:
- FEAT-3713
---

# FEAT-3711: ll-next recommendation_events, derived acceptance and time-based bucket pressure

## Summary

Add an append-only `recommendation_events` table and replace FEAT-3561's round-robin cross-type fill with time-based bucket pressure derived from those events. Owns the only `SCHEMA_VERSION` bump (58 → 59) in the EPIC-3710 arena work, plus `ll-next accept REC_ID` and the `--no-record` flag.

## Current Behavior

After FEAT-3561, `ll-next` is stateless: it fills `--top N` by fixed round-robin across verbs and records nothing. No table identifies which recommendations were shown or acted on, and treating unmatched recommendations as "ignored" would fabricate negative feedback.

## Expected Behavior

Each `ll-next` display appends `shown` rows (recommendation ID, ts, session, rank, `(action_type, target)`). `ll-next accept REC_ID` appends an `accepted_explicit` row. Acceptance is **derived at query time**, never stored mutably: a shown row is `accepted` when a named producer event for the same `(action_type, target)` occurs at or after the shown ts within a configurable match window; `ignored` only for verbs with a reliable producer once the window has elapsed; otherwise `unknown`. Bucket pressure is computed from events with `ts <= as_of` in wall-clock units (days since the bucket's last accepted evidence, capped), resets only on accepted evidence, and is never reset or advanced by display or by repeated/scripted runs. A `--type` filtered run neither accrues nor resets excluded buckets.

## Motivation

Pressure makes neglected action types surface without learned weights, but only if acceptance is honest and reproducible. Append-only rows plus query-time derivation avoid mutable-column conflicts with remote sync and keep the as-of backtest reproducible.

## Proposed Solution

### Producer table (name before enabling automatic acceptance)

| Verb | Acceptance producer | Notes |
|---|---|---|
| `implement-issue`, `resolve-blocker` | `skill_events` `manage-issue` with the issue ID in `args`; `orchestration_runs` for ll-auto/ll-parallel picks | `issue_events` `in_progress` is **not** a producer (9 rows vs 3,341 `done`). Completion (`done`) is outcome, matched separately. |
| `refine-issue` | `skill_events` refine/format/verify/ready-issue with the ID in `args` | |
| `run-loop` | `loop_runs` start for the loop name after the shown ts | |
| `run-sprint`, `capture-issues` | Named in FEAT-3713 when those generators land; `unknown` until then | |

### Schema and storage

- `recommendation_events` in `session_store/schema.py`, `remote_schema.py`, `schema_manifest.json` and the writers/queries API exports; bounded, non-fatal writes using ENH-3679's busy-timeout so a lock wait never changes `ll-next`'s exit code or output.
- Decide and document rebuild membership: default is **not** in `_REBUILD_TABLES` (rows are not derivable from `raw_events`); confirm against ENH-3678's `REBUILD_DERIVE_VERSION` fingerprint test.
- `--no-record` suppresses writes (also implied for `--explain`, and available for CI/tests).

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/schema.py`, `remote_schema.py`, `schema_manifest.json`, `writers.py`, `queries.py`; `little_loops.cli.next` (FEAT-3561) for recording, `accept` and `--no-record`; selection module for pressure; `docs/reference/CLI.md`, `API.md`.

## Implementation Steps

1. Land FEAT-3561; write the per-verb producer table with tests before enabling automatic acceptance.
2. Add `recommendation_events` to local and remote schema, `schema_manifest.json`, writers and queries; make the rebuild-membership decision and confirm the ENH-3678 fingerprint test.
3. Implement query-time acceptance derivation and as-of pressure; replace round-robin fill in `select_candidates`; add `ll-next accept` and `--no-record`.
4. Fixed-clock fixtures for acceptance states and pressure (including repeated-run and `--type` invariance), remote persistence tests, docs.

## Use Case

A user who always accepts implement recommendations and never refines sees `refine-issue` rise in the `--top 3` list as its bucket's last accepted evidence ages, while re-running `ll-next --json` in a script changes nothing.

## Program Design

### Types

- `RecommendationEvent(rec_id, ts, session_id, kind, rank, action_type, target)` is a typed record; `kind` is `shown` or `accepted_explicit`. Acceptance state is a derived value, never a stored field.

### Signatures

- `derive_acceptance(events: list[RecommendationEvent], producers: ProducerTable, *, as_of: datetime, window: timedelta) -> dict[str, AcceptanceState]` — maps each recommendation ID to `accepted`, `ignored` or `unknown` using only producer events with `ts <= as_of`.
- `bucket_pressure(acceptance: dict[str, AcceptanceState], *, as_of: datetime) -> dict[str, float]` — returns days since each bucket's last accepted evidence, capped, in wall-clock units.

### Call Path

Existing `find_issues` source path → `cmd_next` → `generate_candidates` → `bucket_pressure` → `select_candidates` (pressure-ordered fill) → rendering → `record_shown` (skipped under `--no-record`/`--explain`). `ll-next accept` calls `record_accepted`.

## Impact

- **Priority:** P3
- **Effort:** Medium — one table across local and remote, derivation queries, pressure.
- **Risk:** Medium — acceptance attribution is observational and cannot prove causation; pressure is gameable if counted per invocation, hence wall-clock units.
- **Breaking Change:** No.

## Scope Boundaries

- **In scope:** table + local/remote schema, writers/queries, producer table, derived acceptance, pressure formula and selection, `accept`, `--no-record`.
- **Out of scope:** learned weights, treating unobservable verbs as ignored, `--execute`, backtesting pressure (FEAT-3712 is pressure-free).

## Acceptance Criteria

- [ ] `recommendation_events` exists locally and remotely; the 58 → 59 bump does not auto-spawn a full rebuild and the ENH-3678 fingerprint test passes with the documented rebuild-membership decision.
- [ ] Every verb with automatic acceptance has a named producer in a tested table; others stay `unknown` or use `ll-next accept`.
- [ ] Acceptance is derived at query time; no mutable acceptance column; `ignored` is never emitted for verbs without a reliable producer.
- [ ] Pressure uses only events with `ts <= as_of`, is unaffected by repeated or `--json` runs, resets only on accepted evidence, and a `--type` run does not change excluded buckets.
- [ ] Event writes are bounded and non-fatal; `--no-record` and `--explain` write nothing.
- [ ] `python -m pytest scripts/tests/` passes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P3
