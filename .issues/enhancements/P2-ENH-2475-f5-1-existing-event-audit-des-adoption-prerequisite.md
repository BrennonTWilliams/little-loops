---
id: ENH-2475
title: "F5.1 — Existing-event audit (DES adoption prerequisite)"
type: ENH
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2470]
labels:
  - token-cost
  - observability
  - des
  - history-db
  - tier-1
---

# ENH-2475: F5.1 — Existing-event audit (DES adoption prerequisite)

## Summary

Enumerate every event currently written to `.ll/history.db`, classify each
into a DES (discriminated-union) variant, and port non-conforming shapes
into new variants so that F5 (`gen_ai.usage.*` emission under a canonical
schema) can land without coercing unmodeled shapes.

This is EPIC-2456 § Children [TBD-3] — the gate that precedes F5's DES
adoption. Per EPIC-2456 § Success Metrics, F5's gate is "DES schema accepts
100% of currently-emitted events"; that gate cannot be measured without
this audit finishing first.

## Motivation

EPIC-2456 already lists a canonical DES schema for `gen_ai.usage.*` emission
(F5), but F5's emit path is non-trivial: it requires every existing
event-emission site to map cleanly to a known variant. Until we audit
what's currently emitted, F5 risks either silently dropping events or
growing an ad-hoc shape registry that defeats the point of a canonical
schema.

This issue pays down that prerequisite debt in one short pass so F5
(`observability/tracing.py`) can ship with a static-known surface instead
of a runtime shape-coercion layer.

## Current Behavior

Today, every site that writes to `.ll/history.db` chooses its own event
shape. There is no central registry of event variants. F5's emit path will
either (a) refuse to emit when an event doesn't match a known variant, or
(b) grow a runtime adapter that handles each non-conforming shape — both
are bad outcomes for cost attribution.

## Expected Behavior

A new `scripts/little_loops/observability/schema.py` (~30 LOC) holding the
DES variant definitions, plus a one-shot audit script that walks every
current event-emission site, classifies the shape it emits against the DES
registry, and lists the ones whose shape doesn't match a known variant
(MUST be empty before F5 ships).

After this lands, every event emit path uses one of the registered
variants — or registers a new one before adopting F5.

## Proposed Solution

1. **Inventory**: grep `scripts/little_loops/**` for `history.db` writers
   (`SQLiteTransport`, `subprocess_utils.UsageEvent`, etc.) and any direct
   `INSERT`/`REPLACE` into the event tables.
2. **DES registry**: `observability/schema.py` defines each variant as a
   `TypedDict` keyed by `type` (discriminator) — the canonical shape is
   the OTel `gen_ai.usage.*` attribute set used in F5, plus the existing
   `tool_events` / `loop_runs` / `fsm_state` / `session_*` event shapes.
3. **Audit script**: a testable CLI (`observability/audit.py`) that walks
   every emit site via static analysis (call-graph or import-graph), runs
   each branch against the schema, and exits non-zero if any shape is
   unmatched.
4. **Port report**: a `docs/observability/des-audit.md` listing every
   registered variant and the emit sites that satisfy it (auto-generated
   output, not hand-written).

## Integration Map

### Files to Modify

- `scripts/little_loops/observability/schema.py` (new) — DES variant registry
- `scripts/little_loops/observability/audit.py` (new) — one-shot audit script
- `docs/observability/des-audit.md` (new) — auto-generated port report

### Dependent Files (Callers/Importers)

- `scripts/little_loops/sqlite_transport.py` — write path that this audit walks
- `scripts/little_loops/subprocess_utils.py:50–51, 462–465` — `UsageEvent` write site
- `scripts/little_loops/fsm/executor.py:1295–1305` — per-state cache-aggregator write
- Future F5 emit path (`observability/tracing.py`, not yet filed) consumes the registry

### Similar Patterns

- `scripts/little_loops/fsm/schema.py` — already uses discriminator-style typing for loop YAML; reuse the pattern
- `scripts/little_loops/history_reader.py` — read-side can validate every row against the registry at load time (companion enhancement)

### Tests

- `scripts/tests/test_des_schema.py` (new) — every registered variant parses cleanly from a representative event payload
- `scripts/tests/test_des_audit.py` (new) — audit script exits non-zero on an unmodeled shape, zero on a clean tree
- Wired into `python -m pytest scripts/tests/` per project CI policy

### Documentation

- `docs/observability/des-audit.md` — registered variants + emit-site map (auto-generated)
- `docs/reference/API.md` — document `observability/schema.py` registry API

### Configuration

- N/A — no config schema changes; the schema is source-of-truth in code

## Implementation Steps

1. Inventory emit sites with a grep walk; produce a draft variant list
2. Author `observability/schema.py` with the DES variant registry
3. Author `observability/audit.py` that walks emit sites statically and classifies each
4. Add `scripts/tests/test_des_schema.py` + `scripts/tests/test_des_audit.py`
5. Wire CI: `python -m pytest scripts/tests/ test_des_audit.py` must exit 0
6. Document in `docs/reference/API.md`
7. Hand off to F5 (`observability/tracing.py`) — gate ships when audit returns 100% match

## Acceptance Criteria

- DES variant registry in `observability/schema.py` covers every event table in `.ll/history.db`
- Audit script exits 0 against the current tree (i.e. every emit site maps to a known variant), OR exists with an explicit list of remaining port sites that F5 will pick up
- `python -m pytest scripts/tests/` exits 0 with the new tests added
- `docs/reference/API.md` documents the registry API
- EPIC-2456 § Success Metric "DES schema accepts 100% of currently-emitted events" gate is unblocked

## Scope Boundaries

- **In**: Audit + DES registry + port list
- **Out**: OTel `gen_ai.usage.*` attribute emission (F5 child); `gen_ai.invocation.id` UUID stamping (F5 child); cost attribution UI (out of scope for this EPIC)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; § Tier 1 [TBD-3], § Success Metrics F5 |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | Sibling Tier 0 work; emits the events this audit will classify |

## Impact

- **Priority**: P2 — gates EPIC-2456 § Tier 1 F5 from being able to land its DES schema cleanly
- **Effort**: Small — ~30 LOC schema + audit script + tests
- **Risk**: Low — read-only audit + static registry; no runtime behavior change
- **Breaking Change**: No — registry is additive; existing events keep flowing

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
