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

`FSMExecutor._emit()` (`scripts/little_loops/fsm/executor.py:3328`) stamps only `event`, `ts`, and the caller-supplied payload — no run identity. `loop` is emitted exactly once, on `loop_start` (`executor.py:494`), by the caller passing it in the payload rather than by `_emit()` itself. `run_id` is never put on the wire at all; it's derived twice, independently, inside `_finish()` (`executor.py:3686` and `:3711`) purely for archive rows (`loop_runs`, `usage_events`), from `self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]` + `"-" + self.fsm.name`.

## Expected Behavior

Every event emitted via `_emit()` during a run — `loop_start` through `loop_complete` — carries non-empty `run_id` and `loop` fields, computed once and reused for the whole run. Two concurrent runs writing to one `events.jsonl` (or any other single-sink transport) can be split back into per-run streams by grouping on `run_id` alone, with no socket-provenance inference required.

## Motivation

Multi-run observability is currently unreliable: `_claim_socket_path()` (`scripts/little_loops/transport.py`) hands a second concurrent producer a `{stem}-{pid}{suffix}` sibling instead of evicting the first (BUG-3324), so a consumer merging several `.ll/*.sock` streams has no field to key state on, and single-file sinks (`jsonl`, `sqlite`, `webhook`, `otel`) interleave two runs irrecoverably. `debug-loop-run`, `audit-loop-run`, and `ll-session`/`history.db` queries all re-derive run scoping by inference today instead of reading a field the executor already computes at `_finish()` time. Stamping the wire format closes that gap for the cost of two dict keys per event.

## Proposed Solution

Compute `run_id` once, right after `self.started_at = _iso_now()` is set at the top of `FSMExecutor.run()` (`executor.py:481`), using the same derivation `_finish()` already uses (`started_at` digits + `-` + `fsm.name`), and store it as `self.run_id`. Change `_emit()` (`executor.py:3327-3334`) to always merge `run_id` and `loop` into the payload:

```python
def _emit(self, event: str, data: dict[str, Any]) -> None:
    self.event_callback(
        {
            "event": event,
            "ts": _iso_now(),
            "run_id": self.run_id,
            "loop": self.fsm.name,
            **data,
        }
    )
```

Then replace both inline derivations in `_finish()` (`:3686`, `:3711`) with reads of `self.run_id` so archive rows and live events agree by construction instead of by duplicated formula. This is purely additive on the wire: `LLEvent.from_dict()` (`scripts/little_loops/events.py:54`) folds unknown top-level keys into `payload`, so existing consumers that don't know about `run_id`/`loop` are unaffected, and the existing `loop_start`-supplied `loop` key becomes a harmless duplicate that can be dropped from that call site.

Out of scope: `parallel.*` and `issue.*` event emitters build their dicts inline rather than going through `_emit()`, so they need the same treatment or an explicit decision to leave them run-less — tracked separately (see Scope Boundaries).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — add `self.run_id` computation in `run()` (`:481` area), update `_emit()` (`:3327`), update the two inline derivations in `_finish()` (`:3686`, `:3711`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/events.py` (`LLEvent.from_dict()`, `:54`) — already forward-compatible, no change required, but is the consumer contract this issue relies on
- Transports under `scripts/little_loops/transport.py` and any registered sinks (`jsonl`, `sqlite`, `webhook`, `otel`) — pass events through unchanged; no code change expected, but they're the consumers this issue is meant to unblock

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py::archive_run` — the run_id derivation this issue's `self.run_id` must continue to match, so archived rows still JOIN cleanly

### Tests
- `scripts/tests/` FSM executor event-emission tests — add assertions that `run_id` and `loop` are present and non-empty on every emitted event, and that `run_id` is stable across all events within one run

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — document `run_id` and `loop` in the wire-format table
- `docs/reference/schemas/` — regenerate via `ll-generate-schemas` per the issue's stated acceptance criteria

### Configuration
- N/A

## Program Design

### Types

- `FSMExecutor.run_id: str` (new instance attribute, set in `run()`)

### Signatures

- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (existing, modified to stamp `run_id` and `loop`)

### Call Path

`FSMExecutor.run()` (sets `self.started_at`, then `self.run_id`) -> `FSMExecutor._emit()` (stamps `run_id`/`loop` on every call site, e.g. `loop_start` at `:494`, `loop_complete` at `:3675`) -> `self.event_callback` -> registered transports (`jsonl`/`sqlite`/`webhook`/`otel`)

## Implementation Steps

1. Add `self.run_id` computation in `FSMExecutor.run()` immediately after `self.started_at = _iso_now()`, reusing `_finish()`'s existing derivation
2. Update `_emit()` to merge `run_id` and `loop` into every event payload; drop the now-redundant `loop` key from the `loop_start` call site
3. Replace the two inline `run_id` derivations in `_finish()` with reads of `self.run_id`
4. Add/extend executor tests asserting `run_id`/`loop` presence and stability across a run's events
5. Update `docs/reference/EVENT-SCHEMA.md` and regenerate `docs/reference/schemas/` via `ll-generate-schemas`
6. Verify: emit two concurrent runs to one `events.jsonl` and confirm they split cleanly by `run_id`

## Impact

- **Priority**: P2 - Correctness/observability gap affecting any multi-run consumer (dashboards, loop-viz, history.db queries); not user-blocking but actively undermines a stated capability (BUG-3324's multi-stream scenario)
- **Effort**: Small - Confined to `_emit()`, one new instance attribute in `run()`, and two call-site edits in `_finish()`; no new dependencies or schema migrations
- **Risk**: Low - Purely additive wire fields; `LLEvent.from_dict()` already folds unknown keys into `payload`, so no consumer can break from two new keys appearing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Success Metrics

Every event in a captured `events.jsonl` from a test run has non-empty `run_id` and `loop`. Two concurrent loop runs writing to one `events.jsonl` can be split into exactly two disjoint per-run event sequences by grouping on `run_id`, with zero cross-run leakage.

## Scope Boundaries

Out of scope: retrofitting `parallel.*` and `issue.*` emitters that build event dicts inline rather than through `_emit()` — that's the sibling issue ENH-3346. Out of scope: fixing `_claim_socket_path()`'s socket-eviction behavior for concurrent producers (BUG-3324) — this issue only makes concurrent runs *distinguishable* on shared sinks, not resolves socket contention. Out of scope: backfilling `run_id` onto already-archived historical events.

## API/Interface

```python
# New wire fields on every FSMExecutor-emitted event (additive, non-breaking):
{"event": "...", "ts": "...", "run_id": "20260827T195651-my-loop", "loop": "my-loop", ...}
```


## Session Log
- `/ll:format-issue` - 2026-08-27T19:59:35 - `278ef87b-9267-47eb-b438-15c48011237e.jsonl`
- `/ll:capture-issue` - 2026-08-27T19:56:51 - `f1d9d0f2-280e-4e9e-bb4a-45c14f878f7b.jsonl`
