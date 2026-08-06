---
id: BUG-3066
type: BUG
title: "OTel loop spans never close ERROR \u2014 loop_complete never carries outcome"
priority: P3
discovered_commit: fc652df07b9234f2a79fb0663efd253590b170eb
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: audit-docs
status: open
labels:
- observability
- otel
verify_verdict: VALID
testable: true
size: Small
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3066: OTel loop spans never close ERROR — `loop_complete` never carries `outcome`

## Summary

`OTelTransport` decides a loop span's final status by reading an `outcome` key off the
`loop_complete` event, but no emitter ever sets that key. Every loop span therefore closes
`StatusCode.OK`, including runs that crashed, timed out, or landed on a `failure: true`
terminal. The SQLite writer reads the same phantom key, and fares worse: its fallback is
also absent from the payload, so every `loop_complete` row lands with `state = NULL`.

## Current Behavior

`scripts/little_loops/transport.py:471-475`:

```python
outcome = str(event.get("outcome", ""))
...  # _OTEL_ERROR_OUTCOMES = frozenset({"error", "failed", "exhausted"})
```

`scripts/little_loops/session_store/writers.py:1940-1942`:

```python
state = event.get("state")              # loop_complete has final_state, NOT state
if event_type == "loop_complete":
    state = event.get("outcome", state) # -> None
```

This is not merely the analogous latent read — it is strictly worse. `loop_complete`
carries no `state` key either (see the payload below; `_emit` at `executor.py:2868` adds
only `event` and `ts`), so the fallback fails too. **Every `loop_complete` row written to
the session store today has `state = NULL`.** OTel is wrong-but-populated; SQLite is empty.

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

## Steps to Reproduce

Both defects reproduce without an OTLP collector — the SDK's in-memory exporter and a
tmp-path SQLite file are sufficient.

**OTel span closes OK on a crashed run:**

1. Install the extra: `pip install -e "./scripts[otel]"`.
2. Build an `OTelTransport` against an in-memory tracer provider (see the
   `test_provider`/`exporter` fixtures in `scripts/tests/test_transport.py`).
3. Feed it the payload the executor actually emits for a crash:
   ```python
   t.send({"event": "loop_start", "loop_name": "l"})
   t.send({"event": "loop_complete", "final_state": "run", "iterations": 3,
           "terminated_by": "error", "failure_terminal": False, "error": "boom"})
   t.close()
   ```
4. Inspect the finished span: `status.status_code` is `StatusCode.OK`. Expected `ERROR`.
   Repeats identically for `terminated_by="timeout"` and for
   `terminated_by="terminal", failure_terminal=True`.

**SQLite row records a NULL state:**

1. `SQLiteTransport(tmp_path / "session.db")`.
2. Send the same realistic `loop_complete` payload above, then `close()`.
3. Query the `loop_events` row: `state` is `NULL` — the `outcome` key is absent and the
   `event.get("state")` fallback is absent too.

Note both existing tests pass today only because they hand-construct an `outcome` key
(`test_transport.py:751`, `test_session_store_writers.py:74`) that no emitter produces.

## Expected Behavior

A loop that terminated in failure produces a span with `StatusCode.ERROR`, so OTel-based
dashboards and alerting can distinguish failed runs from successful ones.

## Proposed Solution

**Decided 2026-08-05 — no open options remain.** Fix both consumers to read what the
executor already emits, deriving status by importing `_map_final_status` from
`fsm/persistence.py` rather than re-deriving a subset of its logic inline. That keeps one
source of truth for "how did this run end" across the persisted run status, the OTel span,
and the session store. There is no wire-format change: `_finish`'s payload is untouched and
JSONL consumers are unaffected. The wiring pass (below) confirmed the import is
non-circular.

**Promote the symbol first.** `_map_final_status` is underscore-private but becomes a
three-consumer shared contract under this fix. Rename it to `map_final_status`, update its
two existing callers (`PersistentExecutor.run()`, `archive_run_only()`), and import the
public name from `transport.py` and `session_store/writers.py`. Do not import the private
name across package boundaries.

**Status mapping** — `_map_final_status`'s 5 buckets collapse to 3 OTel status codes:

| `map_final_status` | OTel `StatusCode` | SQLite `state` |
|---|---|---|
| `failed` | `ERROR` | `failed` |
| `timed_out` | `ERROR` | `timed_out` |
| `completed` | `OK` | `completed` |
| `interrupted` | `UNSET` | `interrupted` |
| `awaiting_continuation` | `UNSET` | `awaiting_continuation` |

`UNSET` — not `OK` — is the correct OTel semantic for the last two. It means "no explicit
judgement," and a user-stopped or handed-off run is genuinely neither success nor failure.
Mapping them to `OK` would re-create the same false-green this bug is about, just for a
narrower set of runs. `_OTEL_ERROR_OUTCOMES` (`transport.py:335`) is deleted outright; the
`outcome` read disappears from both consumers.

**Also set span attributes.** `_handle_loop_complete` currently sets no attributes at all,
so collapsing 5 statuses into 3 status codes would discard the distinction permanently. Set
`ll.terminated_by` (raw `terminated_by`) and `ll.final_status` (the `map_final_status`
bucket) on the loop span before ending it, so dashboards keep full fidelity. This is the
difference between alertable and diagnosable.

### Considered and Rejected

**Emitting a derived `outcome` field** from `_finish`, keeping the existing reads intact.
Rejected: it is a wire-format addition — `generate_schemas.py`'s `loop_complete` entry and
`docs/reference/EVENT-SCHEMA.md` would both need the new field — and it adds a second,
redundant encoding of failure to a payload that already carries `terminated_by` and
`failure_terminal` (ENH-2814). The chosen approach is strictly smaller and keeps one
encoding.

**Re-deriving the failure predicate inline** in `transport.py`/`writers.py` from
`terminated_by` and `failure_terminal`. Rejected: `failure_terminal` alone is insufficient
(it is `false` for a crash, where `terminated_by="error"`), so each consumer would need its
own copy of the bucketing logic — a third and fourth place to drift from
`_map_final_status`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- `ExecutionResult.failure_terminal: bool` — `scripts/little_loops/fsm/types.py:60`

### Signatures
- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` — `scripts/little_loops/fsm/executor.py:3202`, builds the `loop_complete` payload (`final_state`, `iterations`, `terminated_by`, `failure_terminal`, optional `error`); no `outcome` key.
- `OTelTransport._handle_loop_complete(self, event: dict[str, Any]) -> None` — `scripts/little_loops/transport.py:462-478`, the only OTel consumer of `event.get("outcome", ...)`.
- `SQLiteTransport.send(self, event)` — `scripts/little_loops/session_store/writers.py:1929`, `loop_complete` branch at `1941-1942` is the only writer consumer of `event.get("outcome", ...)`.
- `_map_final_status(terminated_by: str, *, failure_terminal: bool = False) -> str` — `scripts/little_loops/fsm/persistence.py:115-151`. Note `failure_terminal` is **keyword-only** with a default; it cannot be passed positionally. Pre-existing, already-correct bucketing of every `terminated_by` value the executor can produce into `"interrupted" | "awaiting_continuation" | "timed_out" | "completed" | "failed"`. Used today by `PersistentExecutor.run()`/`archive_run_only()` for the persisted run status — `OTelTransport`/`SQLiteTransport` currently bypass it entirely in favor of the dead `outcome` read.

### Call Path
`FSMExecutor._finish` (executor.py:3202) → `FSMExecutor._emit` (executor.py:2868, wraps payload as `{"event": "loop_complete", "ts": ..., **payload}`) → `event_callback` = `PersistentExecutor._handle_event` (fsm/persistence.py:758) → `self.event_bus.emit(event)` (persistence.py:844) → `EventBus.emit` (events.py:117-138) iterates registered transports and calls `transport.send(event)` for each with the **same dict object** — `OTelTransport.send` and `SQLiteTransport.send` both read off one shared, unserialized `loop_complete` event; there is no per-transport payload variation to account for.

### Decision Rules
`terminated_by` values the executor can produce (`fsm/executor.py`, all call sites of `_finish`): `user_stopped`, `system_signal`, `interrupted`, `max_steps`, `max_iterations_reached`, `timeout`, `terminal` (qualified by `failure_terminal`), `error`, `host_pressure_abort`, `stall_detected`, `host_budget_exceeded`, `cycle_detected`, `handoff`.

`_map_final_status` already buckets all of these into 5 statuses: `interrupted` (`max_steps`, `max_iterations_reached`, `interrupted`, `interrupted_force`), `awaiting_continuation` (`handoff`), `timed_out` (`timeout`), `completed`/`failed` (`terminal`, split by `failure_terminal`), `failed` (everything else — `cycle_detected`, `error`, `user_stopped`, `system_signal`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`).

**RESOLVED** (2026-08-05) — this was the issue's one open decision (`_OTEL_ERROR_OUTCOMES`'s 2-way ERROR-vs-OK split vs `_map_final_status`'s 5-way bucketing, and whether to import it or re-derive inline). Both are settled in [Proposed Solution](#proposed-solution): import the (newly public) `map_final_status`, map `failed`/`timed_out` → `ERROR`, `completed` → `OK`, `interrupted`/`awaiting_continuation` → `UNSET`.

_Wiring pass added by `/ll:wire-issue`:_ the `fsm.persistence` import is confirmed safe — `fsm/persistence.py` imports neither `transport.py` nor `session_store/writers.py` (only `EventBus`, `fsm/concurrency`, `fsm/executor`, `fsm/schema`), and neither target module imports back into `fsm/persistence.py`, so reusing `_map_final_status` directly from either file introduces no circular import.

## Acceptance Criteria

1. `map_final_status` is public in `fsm/persistence.py`; its two pre-existing callers
   (`PersistentExecutor.run()`, `archive_run_only()`) are updated; no caller imports the
   underscore-private name.
2. A `loop_complete` event with `terminated_by="error"` (or `"timeout"`, or
   `terminated_by="terminal"` with `failure_terminal=true`) closes its OTel loop span with
   `StatusCode.ERROR`.
3. A `loop_complete` with `terminated_by="terminal"`, `failure_terminal=false` closes `OK`.
4. A `loop_complete` with `terminated_by` in `{interrupted, max_steps,
   max_iterations_reached, handoff}` closes `UNSET` — i.e. neither `OK` nor `ERROR`.
   `user_stopped` and `system_signal` are **not** in this set; see the note below.
5. The loop span carries `ll.terminated_by` and `ll.final_status` attributes.
6. `SQLiteTransport` writes a **non-NULL** `state` for every `loop_complete` row, equal to
   the `map_final_status` bucket. A regression test asserts non-NULL explicitly (the
   current NULL would otherwise slip past a value-only assertion on a fixture that
   happens to be a failure run).
7. `_OTEL_ERROR_OUTCOMES` is deleted and no production code reads `event["outcome"]` off a
   `loop_complete` event.
8. **Anti-regression (grep-enforceable):** no test in `scripts/tests/` constructs a
   `loop_complete` event containing an `outcome` key. All three current offenders
   (`test_transport.py:715,751`, `test_session_store_writers.py:74`) are rewritten to feed
   realistic payloads (`terminated_by`/`failure_terminal`). Without this AC a rewrite can
   quietly leave one behind and the suite stays green for the wrong reason a second time.
9. `docs/reference/EVENT-SCHEMA.md:1276` no longer documents the gap; it documents the
   mapping table instead.
10. `python -m pytest scripts/tests/` exits 0.

### `user_stopped` / `system_signal` map to ERROR — accepted

_Resolved 2026-08-06 during pre-implementation review._ An earlier draft of AC 4 listed
`user_stopped` and `system_signal` among the "neither OK nor ERROR" cases, contradicting
this issue's own mapping table and Decision Rules: `_map_final_status` buckets both into
`failed`, which this fix maps to `StatusCode.ERROR`.

The contradiction is resolved **in favour of the table** — reuse `_map_final_status`
exactly as it is. Ctrl-C closing an ERROR span is arguably wrong semantically, but
re-bucketing those two values is not an OTel change: `_map_final_status` also drives the
**persisted run status**, so moving `user_stopped` out of `failed` would silently change
`ll-loop status` / run-archive output for every host. That is a separate, wider decision
than "stop closing every span OK," and folding it in here would defeat the point of having
one source of truth.

If the semantics are later judged wrong, change `_map_final_status` once — for all three
consumers — under its own issue, rather than adding an OTel-only exception here.

## Impact

- **Priority**: P3 — observability-only; no runtime behavior or data loss. Matters
  to anyone routing loop telemetry into OTel and alerting on span status.
- **Effort**: Small — two predicates, one symbol rename, ~4 rewritten tests, one doc row.
  Frontmatter `size` corrected from `Large` to `Small` to match (2026-08-05).
- **Risk**: Low. The main risk is a test suite that currently passes for the wrong
  reason: the ERROR-path tests must be rewritten to feed a realistic `loop_complete`
  payload, or the fix will look verified when it is not. AC 8 is the guard.
- **`learning_tests_required: [opentelemetry]` removed** (2026-08-06). It was justified
  only by the introduction of `StatusCode.UNSET` — an enum member, not API semantics that
  need an LLM proof session. Keeping it also created a dated trap: the
  `.ll/learning-tests/opentelemetry.md` record is dated `2026-07-08`, so at
  `stale_after_days: 30` it goes stale on **2026-08-08** and the gate would have blocked
  this issue from that date onward for no substantive reason. The existing record's
  assertions already cover the span/context mechanics this fix relies on; only the status
  code is new, and AC 2–4 test it directly.

## Integration Map

- `scripts/little_loops/transport.py` — `OTelTransport._handle_loop_complete` span-closing
  logic (~line 471) plus deletion of `_OTEL_ERROR_OUTCOMES` (line 335)
- `scripts/little_loops/session_store/writers.py` — `outcome` fallback (~line 1941)
- `scripts/little_loops/fsm/persistence.py` — rename `_map_final_status` →
  `map_final_status` (line 115) and update its two in-file callers (`PersistentExecutor.run()`,
  `archive_run_only()`)
- `scripts/little_loops/fsm/executor.py` — `_finish()` payload (line 3202); **not touched**
  under the resolved Option A direction
- `scripts/tests/test_transport.py` — lines ~715, ~751 currently synthesize `outcome`
- `docs/reference/EVENT-SCHEMA.md` — the OTel span-closing table now documents this gap
  explicitly; update it once the behavior is fixed
- `scripts/little_loops/generate_schemas.py` + `docs/reference/schemas/loop_complete.json` —
  **not touched** under Option A; no wire-format change, so the published `loop_complete`
  schema (which correctly does not list `outcome`) stays as-is

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_writers.py:74-79` — `TestSQLiteTransport::test_loop_complete_records_outcome_as_state` hand-constructs a `loop_complete` event with a fake `outcome` key, the same dead-test pattern as `test_transport.py:715,751`; must be rewritten to feed a realistic payload (`terminated_by`/`failure_terminal`, no `outcome`) alongside the `writers.py` fix. Note the test name itself (`test_loop_complete_records_outcome_as_state`) encodes the phantom field and should be renamed. Confirmed via `ll-code callers-of` + direct grep — no other test in `scripts/tests/` hand-constructs a `loop_complete` event with an `outcome` key.
- `_map_final_status` has **no test-suite references** (`grep -rn "_map_final_status" scripts/` matches only `fsm/persistence.py` itself), so the rename to `map_final_status` touches no tests — verified 2026-08-05.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:1271` — "Span-closing events" section; table row at line 1276 explicitly names this bug (`outcome` never set) and needs rewriting once the fix lands, not just the general field table.

## Related Key Documentation

- [docs/reference/EVENT-SCHEMA.md](../../docs/reference/EVENT-SCHEMA.md) — `loop_complete`
  field table and the OTel span-closing table
- [thoughts/audit-docs-reference-2026-08-05.md](../../thoughts/audit-docs-reference-2026-08-05.md) — the docs audit that surfaced this

## Session Log
- `/ll:confidence-check` - 2026-08-06T00:35:27 - `2ea053a9-974c-4ef9-a923-fb98627db81f.jsonl`
- `/ll:confidence-check` - 2026-08-06T00:14:47 - `22a2d710-b927-4674-8d5f-e2d567aaea06.jsonl`
- `/ll:refine-issue` - 2026-08-06T00:10:23 - `e8c97e21-d6b8-47c7-b5a5-a7c138f3cb82.jsonl`
- `/ll:verify-issues` - 2026-08-06T00:09:04 - `e5d62d34-d995-4f7f-8a1e-fc36e13ff4a4.jsonl`
- `/ll:wire-issue` - 2026-08-06T00:07:09 - `55aa9897-679e-49ae-9c14-0223c3576a7c.jsonl`
- `/ll:refine-issue` - 2026-08-06T00:03:25 - `346e9963-6b6e-4bfa-aedd-41d27acae5bd.jsonl`
- `/ll:refine-issue` - 2026-08-06T00:03:18 - `346e9963-6b6e-4bfa-aedd-41d27acae5bd.jsonl`

---

## Status

**Open** | Created: 2026-08-05 | Priority: P3
