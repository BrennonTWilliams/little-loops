---
discovered_commit: fc652df07b9234f2a79fb0663efd253590b170eb
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: audit-docs
status: open
labels:
- observability
- otel
learning_tests_required:
- opentelemetry
verify_verdict: VALID
size: Large
---

# BUG-3066: OTel loop spans never close ERROR — `loop_complete` never carries `outcome`

## Summary

`OTelTransport` decides a loop span's final status by reading an `outcome` key off the
`loop_complete` event, but no emitter ever sets that key. Every loop span therefore closes
`StatusCode.OK`, including runs that crashed, timed out, or landed on a `failure: true`
terminal. The same latent read exists in the SQLite writer.

## Current Behavior

`scripts/little_loops/transport.py:471-475`:

```python
outcome = str(event.get("outcome", ""))
...  # _OTEL_ERROR_OUTCOMES = frozenset({"error", "failed", "exhausted"})
```

`scripts/little_loops/session_store/writers.py:1941-1942` does the analogous
`state = event.get("outcome", state)`.

The only producer of `loop_complete` is `FSMExecutor._finish`
(`scripts/little_loops/fsm/executor.py:3202-3217`), whose payload is:

```python
payload = {
    "final_state": self.current_state,
    "iterations": self.iteration,
    "terminated_by": terminated_by,
    "failure_terminal": failure_terminal,
}
if error is not None:
    payload["error"] = error
```

No `outcome`. The lookup always falls through to `""`, which is not in
`_OTEL_ERROR_OUTCOMES`, so the span is marked `OK`. Only `scripts/tests/test_transport.py`
(lines 715, 751) exercises the ERROR branch, and it does so by hand-constructing an event
with an `outcome` key that production never produces — so the tests pass while the
behavior is dead.

## Expected Behavior

A loop that terminated in failure produces a span with `StatusCode.ERROR`, so OTel-based
dashboards and alerting can distinguish failed runs from successful ones.

## Proposed Solution

Two viable directions; pick one deliberately rather than patching both reads:

**Option A — read what is already emitted.** Change `transport.py` and
`writers.py` to derive status from `failure_terminal` (ENH-2814, emitted
unconditionally) and `terminated_by` (`"error"`, `"timeout"`, `"max_steps"`,
`"stall_detected"`, `"cycle_detected"`, `"host_pressure_abort"`,
`"host_budget_exceeded"`, …). No wire-format change; consumers of the JSONL stream are
unaffected. Requires deciding which `terminated_by` values count as failures — note
`failure_terminal` alone is insufficient, since it is `false` for a crash
(`terminated_by="error"`).

**Option B — emit `outcome`.** Add a derived `outcome` field to the `loop_complete`
payload in `_finish`, keeping the existing reads intact. Wire-format addition, so
`generate_schemas.py`'s `loop_complete` entry and `docs/reference/EVENT-SCHEMA.md` need the
new field too.

Option A is the smaller change and avoids adding a second, redundant encoding of failure to
the event payload.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- `ExecutionResult.failure_terminal: bool` — `scripts/little_loops/fsm/types.py:60`

### Signatures
- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` — `scripts/little_loops/fsm/executor.py:3202`, builds the `loop_complete` payload (`final_state`, `iterations`, `terminated_by`, `failure_terminal`, optional `error`); no `outcome` key.
- `OTelTransport._handle_loop_complete(self, event: dict[str, Any]) -> None` — `scripts/little_loops/transport.py:462-478`, the only OTel consumer of `event.get("outcome", ...)`.
- `SQLiteTransport.send(self, event)` — `scripts/little_loops/session_store/writers.py:1929`, `loop_complete` branch at `1941-1942` is the only writer consumer of `event.get("outcome", ...)`.
- `_map_final_status(terminated_by: str, failure_terminal: bool) -> str` — `scripts/little_loops/fsm/persistence.py:117-153`. Pre-existing, already-correct bucketing of every `terminated_by` value the executor can produce into `"interrupted" | "awaiting_continuation" | "timed_out" | "completed" | "failed"`. Used today by `PersistentExecutor.run()`/`archive_run_only()` for the persisted run status — `OTelTransport`/`SQLiteTransport` currently bypass it entirely in favor of the dead `outcome` read.

### Call Path
`FSMExecutor._finish` (executor.py:3202) → `FSMExecutor._emit` (executor.py:2868, wraps payload as `{"event": "loop_complete", "ts": ..., **payload}`) → `event_callback` = `PersistentExecutor._handle_event` (fsm/persistence.py:758) → `self.event_bus.emit(event)` (persistence.py:844) → `EventBus.emit` (events.py:117-138) iterates registered transports and calls `transport.send(event)` for each with the **same dict object** — `OTelTransport.send` and `SQLiteTransport.send` both read off one shared, unserialized `loop_complete` event; there is no per-transport payload variation to account for.

### Decision Rules
`terminated_by` values the executor can produce (`fsm/executor.py`, all call sites of `_finish`): `user_stopped`, `system_signal`, `interrupted`, `max_steps`, `max_iterations_reached`, `timeout`, `terminal` (qualified by `failure_terminal`), `error`, `host_pressure_abort`, `stall_detected`, `host_budget_exceeded`, `cycle_detected`, `handoff`.

`_map_final_status` already buckets all of these into 5 statuses: `interrupted` (`max_steps`, `max_iterations_reached`, `interrupted`, `interrupted_force`), `awaiting_continuation` (`handoff`), `timed_out` (`timeout`), `completed`/`failed` (`terminal`, split by `failure_terminal`), `failed` (everything else — `cycle_detected`, `error`, `user_stopped`, `system_signal`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`).

Unresolved for whichever option is chosen: the issue's `_OTEL_ERROR_OUTCOMES` framing (`{"error", "failed", "exhausted"}`) is a 2-way ERROR-vs-OK split, but `_map_final_status`'s existing bucketing is 5-way. Pin down explicitly: does an OTel/SQLite consumer treat `interrupted` and `timed_out` and `awaiting_continuation` runs as ERROR, or only `failed`? And should `transport.py`/`writers.py` import and reuse `_map_final_status` directly (single source of truth, but introduces an `fsm.persistence` import into `transport.py`/`session_store/writers.py`) rather than re-deriving a subset of its logic from `terminated_by`/`failure_terminal` inline, per Option A's phrasing. Escape hatch: none — this is exactly the "pick one deliberately" decision the issue's Proposed Solution already calls for; no default applies.

_Wiring pass added by `/ll:wire-issue`:_ the `fsm.persistence` import is confirmed safe — `fsm/persistence.py` imports neither `transport.py` nor `session_store/writers.py` (only `EventBus`, `fsm/concurrency`, `fsm/executor`, `fsm/schema`), and neither target module imports back into `fsm/persistence.py`, so reusing `_map_final_status` directly from either file introduces no circular import.

## Impact

- **Priority**: P3 — observability-only; no runtime behavior or data loss. Matters
  to anyone routing loop telemetry into OTel and alerting on span status.
- **Effort**: Small — one predicate plus tests, once the direction is chosen.
- **Risk**: Low. The main risk is a test suite that currently passes for the wrong
  reason: `test_transport.py`'s ERROR-path tests must be rewritten to feed a
  realistic `loop_complete` payload, or the fix will look verified when it is not.

## Integration Map

- `scripts/little_loops/transport.py` — `OTelTransport` span-closing logic (~line 471)
- `scripts/little_loops/session_store/writers.py` — `outcome` fallback (~line 1941)
- `scripts/little_loops/fsm/executor.py` — `_finish()` payload (line 3202), only if Option B
- `scripts/tests/test_transport.py` — lines ~715, ~751 currently synthesize `outcome`
- `docs/reference/EVENT-SCHEMA.md` — the OTel span-closing table now documents this gap
  explicitly; update it once the behavior is fixed
- `scripts/little_loops/generate_schemas.py` + `docs/reference/schemas/loop_complete.json` —
  only if Option B

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_writers.py:74-79` — `TestSQLiteTransport::test_loop_complete_records_outcome_as_state` hand-constructs a `loop_complete` event with a fake `outcome` key, the same dead-test pattern as `test_transport.py:715,751`; must be rewritten to feed a realistic payload (`terminated_by`/`failure_terminal`, no `outcome`) alongside the `writers.py` fix. Confirmed via `ll-code callers-of` + direct grep — no other test in `scripts/tests/` hand-constructs a `loop_complete` event with an `outcome` key.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:1271` — "Span-closing events" section; table row at line 1276 explicitly names this bug (`outcome` never set) and needs rewriting once the fix lands, not just the general field table.

## Related Key Documentation

- [docs/reference/EVENT-SCHEMA.md](../../docs/reference/EVENT-SCHEMA.md) — `loop_complete`
  field table and the OTel span-closing table
- `thoughts/audit-docs-reference-2026-08-05.md` — the docs audit that surfaced this

## Session Log
- `/ll:refine-issue` - 2026-08-06T00:10:23 - `e8c97e21-d6b8-47c7-b5a5-a7c138f3cb82.jsonl`
- `/ll:verify-issues` - 2026-08-06T00:09:04 - `e5d62d34-d995-4f7f-8a1e-fc36e13ff4a4.jsonl`
- `/ll:wire-issue` - 2026-08-06T00:07:09 - `55aa9897-679e-49ae-9c14-0223c3576a7c.jsonl`
- `/ll:refine-issue` - 2026-08-06T00:03:25 - `346e9963-6b6e-4bfa-aedd-41d27acae5bd.jsonl`
- `/ll:refine-issue` - 2026-08-06T00:03:18 - `346e9963-6b6e-4bfa-aedd-41d27acae5bd.jsonl`

---

## Status

**Open** | Created: 2026-08-05 | Priority: P3
