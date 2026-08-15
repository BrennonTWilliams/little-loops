---
id: ENH-3204
type: ENH
title: Record the credential scope a run was granted for after-the-fact audit
priority: P3
status: blocked
blocked_by: [ENH-3203]
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: true
---

# ENH-3204: Record the credential scope a run was granted for after-the-fact audit

## Summary

Nothing anywhere records what authority a given run held. Once ENH-3203 lets a task declare a credential scope, an audit should be able to answer after the fact what a given run could reach.

Record the declared scope with the run. The record stores **capability and variable *names* only — never values**.

**Blocked by ENH-3203** — there is no declaration to record until it lands.

## Current Behavior

No table, column, or log line records the authority a run held. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped for this.

## Expected Behavior

Each run records the capability and variable names it was granted, queryable after the fact. Names only — a record that could leak a credential value is worse than no record.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` is currently **40** (line 21, verified 2026-08-15), so a new migration is **v41**. Confirm the current value before writing the migration; it moves.
- The projection helper in `scripts/little_loops/host_runner.py` — emits the granted-names record at spawn time.

### Tests
- `scripts/tests/` — migration round-trip, plus a test asserting no credential *value* can reach the record.

## Program Design

### Types
- No existing per-run authority record exists to extend. `loop_events` rows are the nearest per-run ledger shape.

### Signatures
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None` — the existing shared env-injection helper the projection helper sits beside (`host_runner.py:1784-1799`); the new writer is invoked from the same spawn-time seam.
- The writer itself takes a run identifier plus two `frozenset[str]` name-sets (capabilities, variables) and returns `None`. Indicative shape; no value-bearing parameter may exist.

### Call Path
`resolve_host` → `_apply_automation_env` → projection helper → `loop_events`

### Decision Rules
- Names only, never values — enforced by test, not convention.
- No record is written for undeclared specs, since there is no scope to report.

## Scope Boundaries

Explicitly **out of scope**:

- **The declaration mechanism itself** — ENH-3203.
- **Spawn-site centralization** — ENH-3184.
- **Retention, pruning, or compaction of the new record.** Per project policy, `raw_events`-style deletion stays a manually-run CLI action; this issue adds no automatic pruning.
- **Any surfacing UI or `ll-*` query command.** Follow-on if wanted.

## Open Decisions

1. **Where does the record land?** A column on the existing `loop_events` ledger, or a new `.ll/history.db` table. `loop_events` is closest; a dedicated table is cleaner if the record is per-spawn rather than per-run.
2. **Per-run or per-spawn granularity?** A single loop run makes many spawns with potentially different declarations.

## Impact

- **Priority**: P3 — audit value only; no runtime behaviour depends on it, and it is meaningless until ENH-3203 lands.
- **Effort**: Small — one migration, one write path, two tests.
- **Risk**: Low, with one sharp edge: a record that stores values instead of names inverts the issue's purpose. Test for it explicitly.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
