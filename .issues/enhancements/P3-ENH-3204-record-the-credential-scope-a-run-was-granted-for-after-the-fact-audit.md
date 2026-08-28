---
id: ENH-3204
type: ENH
title: Record the credential scope a run was granted for after-the-fact audit
priority: P3
status: open
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3233
- ENH-3234
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: true
---

# ENH-3204: Record the credential scope a run was granted for after-the-fact audit

## Summary

Nothing anywhere records what authority a given run held. Once a task can declare a credential scope, an audit should be able to answer after the fact what a given run could reach.

Record the declared scope with the run. The record stores **scope and variable *names* only — never values**.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no declaration code has landed yet. The enforcement chokepoint is ENH-3233; the declaration surfaces this issue records arrive with ENH-3234 (`ActionSpec`) and ENH-3235 (`StateConfig`). All three are in `blocked_by`; scope *names* in the record only exist once at least one declaration surface ships.

## Current Behavior

No table, column, or log line records the authority a run held. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped for this.

## Expected Behavior

Each run records the capability and variable names it was granted, queryable after the fact. Names only — a record that could leak a credential value is worse than no record.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` is currently **45** (line 25, verified 2026-08-28), so a new migration is **v46**. Confirm the current value before writing the migration; it moves (it already drifted from 40 since this issue was written).
- The projection helper in `scripts/little_loops/host_runner.py` — emits the granted-names record at spawn time.

### Tests
- `scripts/tests/` — migration round-trip, plus a test asserting no credential *value* can reach the record.

## Program Design

### Types
- No existing per-run authority record exists to extend. `loop_events` rows are the nearest per-run ledger shape.

### Signatures
- `_apply_automation_env(env: dict[str, str], automation: AutomationContext | None) -> None` — the existing shared env-injection helper the projection helper sits beside (`host_runner.py:1882`, signature updated by ENH-3095's `AutomationContext` refactor); the new writer is invoked from the same spawn-time seam.
- The writer itself takes a run identifier plus two `frozenset[str]` name-sets (scopes, variables) and returns `None`. Indicative shape; no value-bearing parameter may exist.

### Call Path
Spawn site (holds run identifier) → `project_child_env()` result (ENH-3233 chokepoint) → scope-record writer → `loop_events` (or new table, per Open Decision #1)

### Decision Rules
- Names only, never values — enforced by test, not convention.
- No record is written for undeclared specs, since there is no scope to report.
- The write must **not** live inside `project_child_env()` itself: it is a pure helper with ~18 call sites, several of which have no run context at all (`worktree_utils.py`, `git_operations.py`, `mcp_call.py`). Invoke the writer from spawn sites that hold a run identifier.

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


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
