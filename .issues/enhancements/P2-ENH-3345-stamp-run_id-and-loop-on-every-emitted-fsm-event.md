---
id: ENH-3345
type: ENH
title: Stamp run_id and loop on every emitted FSM event
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T19:56:15Z'
---

# ENH-3345: Stamp run_id and loop on every emitted FSM event

## Summary

`FSMExecutor._emit()` (`scripts/little_loops/fsm/executor.py:3328`) stamps only `event`, `ts`, and the caller-supplied payload. No run-scoped identity is attached: only `loop_start` (`executor.py:484`) carries the `loop` name, and `run_id` is derived *at archive time* in `_finish()` (`executor.py:3686`, `:3711`) from `started_at` + `fsm.name` — never on the wire.

Consequences:

- **Multi-stream consumers cannot correlate.** Concurrent runs each bind their own socket: `_claim_socket_path()` in `scripts/little_loops/transport.py` hands a second producer a `{stem}-{pid}{suffix}` sibling rather than evicting the first (BUG-3324). A consumer that discovers and merges several `.ll/*.sock` streams therefore has no field to key state on. Any realtime multi-run view (dashboard, game-scene visualizer, the "loop-viz" external consumer named in `docs/reference/EVENT-SCHEMA.md`) must infer run identity from socket provenance, which breaks the moment two runs share a sink (`jsonl`, `sqlite`, `webhook`, `otel` are all single-file/single-endpoint).
- **Single-sink transports interleave irrecoverably.** Two concurrent runs writing `.ll/events.jsonl` or `.ll/history.db` via `SQLiteTransport` produce a stream that cannot be de-interleaved after the fact.
- **Downstream tooling re-derives what the executor already knows.** `debug-loop-run`, `audit-loop-run`, and `ll-session`/`history.db` queries reconstruct run scoping by inference instead of reading a field.

Proposed change: compute `run_id` once at executor construction (same derivation as `_finish()` uses today, so archive rows and live events agree) and have `_emit()` stamp `run_id` and `loop` onto every event alongside `event`/`ts`. Purely additive — existing consumers that ignore unknown keys are unaffected, and `LLEvent.from_dict()` folds the new keys into `payload` without change.

Scope note: `parallel.*` and `issue.*` emitters build their dicts inline rather than going through `_emit()`, so they need the same treatment or an explicit decision to leave them run-less. Sibling issue covers the `parallel.*` surface.

Acceptance: every event observed on the bus during a loop run carries a non-empty `run_id` and `loop`; two concurrent runs writing one `events.jsonl` can be fully separated by `run_id`; `docs/reference/EVENT-SCHEMA.md` documents both fields in the wire-format table; `docs/reference/schemas/` regenerated via `ll-generate-schemas`.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-27T19:56:51 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
