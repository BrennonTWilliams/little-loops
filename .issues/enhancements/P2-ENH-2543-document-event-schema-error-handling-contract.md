---
id: ENH-2543
title: 'Document event-schema error-handling contract for JSON callers'
type: ENH
priority: P2
status: open
discovered_date: 2026-07-08
captured_at: '2026-07-08T09:20:00+00:00'
discovered_by: audit
decision_needed: false
labels:
  - enhancement
  - documentation
  - event-schema
  - api-contract
  - follow-up-from-docs-audit-2026-07-08
confidence_score: 80
outcome_confidence: 80
score_complexity: 4
score_test_coverage: 4
score_ambiguity: 6
score_change_surface: 5
---

# ENH-2543: Document event-schema error-handling contract for JSON callers

## Summary

Phase 2 of the `docs/reference/` audit (2026-07-08) identified a documentation gap in `docs/reference/EVENT-SCHEMA.md`: the contract for what JSON callers receive when the underlying transport fails or the event emitter crashes is undocumented. Callers today must either guess (most assume exit-code-1 = failure) or read the source. EVENT-SCHEMA.md describes event payloads but never addresses failure shapes.

## Current Behavior

When an event-emitter site (e.g. `EventBus.emit()`, transport `send(event)`, or webhook delivery) encounters an error:

- The behaviour is split across `scripts/little_loops/events.py`, the transport implementations (`scripts/little_loops/transport.py` JsonlTransport / UnixSocketTransport / OTelTransport), and the EventBus dispatcher.
- `EVENT-SCHEMA.md` describes every event payload but says nothing about:
  - What callers see in `--json` output paths when no events match (empty array vs exit code 1 vs error object on stderr)
  - Whether the orchestrator emits an `action_error` event on transport failure (it does — but unindexed in the doc)
  - Whether a malformed event (missing required fields) is dropped, surfaced as a stderr warning, or emitted with `error: <reason>` attached
  - Whether JSON consumers should expect top-level metadata fields (`_meta`, `error_summary`) on partial failure
- Skipping this contract means callers (CI scripts, dashboards, `ll-loop run --json` automation) write defensive code that handles every shape and shape-on-error they can imagine, rather than trusting a documented contract.

## Expected Behavior

Add a new `## Error Handling Contract` section to `docs/reference/EVENT-SCHEMA.md` that documents, for every documented event-emitter surface:

1. **Exit codes** — what `--json` paths emit on success vs partial-failure vs total-failure (e.g. `0` on success, `1` on emit failure, `2` on validation failure).
2. **Empty-result shape** — what `--json`-with-no-events returns (`[]` vs `{}` vs `{"events": [], "errors": []}`).
3. **Partial-failure envelopes** — how transport errors are surfaced (e.g. is there a `meta.errors[]` field on each event? a top-level `summary.failed_count`?).
4. **`action_error` event contract** — document when the orchestrator emits this event (after every shell/prompt action that returns non-zero exit) and that callers must handle it as a first-class event type.
5. **Retry / replay guarantees** — what happens to events that fail to deliver (do they buffer? retry? drop? — see `SqliteTransport` and `JsonlTransport` retention policies).

## Resolution

Read each transport (`scripts/little_loops/transport.py` — `JsonlTransport`, `UnixSocketTransport`, `OTelTransport`, `SqliteTransport`) and document the error-surface in a new `## Error Handling Contract` section of `EVENT-SCHEMA.md`. Cross-reference each transport's behaviour with `EventBus.emit()` failure paths in `scripts/little_loops/events.py`. Approximate location to insert: just before the `## Subsystem` heading at the bottom of the file.

## Out of scope (deferred)

- Changing existing transport error behaviour (this issue is documentation-only).
- Adding new error envelopes or `action_error` event variants.

## Verification

- Audit `EventBus.emit()` and every transport to enumerate the documented failure paths.
- Add a `## Error Handling Contract` section to `EVENT-SCHEMA.md` that names every transport and gives a 1–2 line contract per surface.
- Run `python -m pytest scripts/tests/` to confirm no test breaks (this is doc-only).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct reading of `scripts/little_loops/events.py`, `scripts/little_loops/transport.py`, `scripts/little_loops/session_store.py`, `scripts/little_loops/fsm/executor.py`, and `docs/reference/EVENT-SCHEMA.md`:_

### `EventBus.emit()` contract (`scripts/little_loops/events.py:117-138`)

- **Always swallows transport & observer exceptions.** Exceptions raised by any individual sink are caught, logged via `logger.warning("EventBus transport raised an exception", exc_info=True)`, and silently discarded. One failing transport never blocks delivery to the others — so there is **no stack-trace, no exit-code bump, no error envelope** surfaced back to the caller when a transport fails.
- **Filter is checked before dispatch.** Observers with a `filter=...` pattern only see matching event types (`fnmatch.fnmatch(event_type, p)`); non-matching events are silently skipped for that observer.
- **Ordering is deterministic: observers first, transports second.** Both lists are iterated in registration order within their group.

### `JsonlTransport` (`scripts/little_loops/transport.py:81-98`)

- **No application-level retry, buffering, or rotation.** `send()` opens the file, writes `json.dumps(event) + "\n"`, and closes — a single per-event open/close. Disk-full, permission-denied, or JSON-encoder exceptions bubble up to `EventBus.emit`'s catch block and become a warning log.
- `close()` is a no-op (the constructor creates the parent directory; each `send()` is self-contained).

### `UnixSocketTransport` (`scripts/little_loops/transport.py:115-320`)

- **Drops newest event on full client queue.** A full outbound queue (`_CLIENT_QUEUE_MAXSIZE = 1024`, `transport.py:47`) for a client → event is dropped (preserving causal order) and the dropped count is incremented. A rate-limited warning is logged once per 5s (`_DROP_LOG_INTERVAL_SEC`, `transport.py:48`).
- **Client rejections logged separately.** When `max_clients` is reached, new connections are rejected and counted via `get_stats()["client_rejections"]` (`transport.py:281-283`).
- **AF_UNIX missing → `RuntimeError` raised from `wire_transports()`** (not swallowed) because silently dropping a requested transport would be confusing. Transport raising during construction is the **one path** that propagates out of `wire_transports`; once constructed, `send()` errors are caught by `EventBus.emit`.
- **Disconnected clients removed from pool** without affecting FSM thread (per-client try/except around `sendall`).

### `OTelTransport` (`scripts/little_loops/transport.py:338-492`)

- **Sub-loop events are no-ops** (`depth > 0`, with a one-time warning per session; see `transport.py:385-395`). Nested OTel tracing is out of scope.
- **Out-of-order events warn and skip span creation.** `state_enter` without a prior `loop_start` → warns and returns; `action_start` without `state_enter` → same. These warnings are the only signal that span hierarchy is broken.
- **`close()` blocks on `force_flush()` + `shutdown()`.** No timeout on the underlying SDK calls; rely on OTel SDK's own deadlines.
- **Optional import:** constructor raises `RuntimeError` with install guidance if `opentelemetry-sdk` / `opentelemetry-exporter-otlp-grpc` are missing (`transport.py:358-368`).

### `WebhookTransport` (`scripts/little_loops/transport.py:495-575`)

- **HTTP 5xx and exceptions trigger exponential-backoff retry.** Up to `max_retries=3` retries (overridable); backoff base `_WEBHOOK_RETRY_BASE_S = 0.5` doubles up to cap `_WEBHOOK_RETRY_MAX_S = 8.0`. HTTP non-5xx responses (< 500) are treated as success.
- **Retry exhaustion → batch dropped with warning** (`logger.warning("WebhookTransport: giving up after %d retries posting to %r", ...)`, `transport.py:571-575`). **Never raises to caller.** This is the documented "best-effort" guarantee.
- **Non-blocking `send()`** — events enqueue on a `Queue`, drained by daemon thread on `batch_ms` interval (default 1000ms; `transport.py:56`). Queue overflow not guarded; relies on consumer thread pacing.
- **Optional import:** constructor raises `RuntimeError` if `httpx` is missing (`transport.py:513-518`).

### `SQLiteTransport` (`scripts/little_loops/session_store.py:1311-1430`)

- **Best-effort end-to-end.** Connection failure at construction → `send()` becomes a silent no-op forever (returns early because `self._conn is None`, `session_store.py:1343-1345`); no error is raised to the caller.
- **Per-write failures are logged + swallowed** (`session_store.py:1421-1422`). Writes are serialized with a `threading.Lock`.
- **Recognises a closed set of event types only.** `_LOOP_EVENT_TYPES = frozenset({"loop_start", "loop_resume", "loop_complete", "state_enter", "route", "retry_exhausted", "cycle_detected", "max_steps_summary", "max_iterations_reached_summary"})` (`session_store.py:133-145`) + `issue.*` (prefix match). All other event types silently `return` without insert.
- **`close()` is best-effort** and swallows `sqlite3.Error`.

### `action_error` event contract (`scripts/little_loops/fsm/executor.py:1970-1983`)

- **Emitted only when `state.on_error` is defined** on the state config. If `on_error` is absent, the exception re-raises and the top-level loop handler terminates with `loop_complete.terminated_by="error"` and the message in `loop_complete.error`.
- Payload schema (per `EVENT-SCHEMA.md`): `{state, error, route: "on_error"}`.
- **Consumers MUST treat `action_error` as a first-class event type**, because the same exception would otherwise silently terminate the loop (no separate crash event without `on_error`).

### CLI exit-code conventions (informational — not exhaustive)

- **`ll-sprint run`**: `exit_code = 1` on worker failure / abort paths (`cli/loop/run.py:493, 573, 686, 707`); `exit_code = 130` on `KeyboardInterrupt` (`cli/loop/run.py:715`).
- **`ll-harness`**: `RunnerResult` defaults `exit_code=2` for timeout and exception markers (`cli/harness.py:296, 298, 339, 395, 397`); caller compares to `--exit-code` N passed in.
- **`ll-action` timeouts**: surfaces `exit_code = 124` for action timeouts (`cli/action.py:102, 137`), matching the `--timeout` convention.
- **Pattern for `--json` output with errors**: most `ll-verify-*` tools emit a dataclass result + dual `--json`/`text` output (`cli/verify_design_tokens.py`, `cli/verify_des_audit.py`, `cli/verify_package_data.py`, `cli/verify_triggers.py`, `cli/verify_docs*`). The typical pattern is JSON envelope `{"errors": [...], "warnings": [...], "data": ...}` with exit 0 (errors found) / 1 (tool failure). The new `## Error Handling Contract` section should reference this convention by example rather than redefine it.

### Doc-section anchor suggestion

The existing `EVENT-SCHEMA.md` "Quick Reference" table ends at line ~1107 and the "OTel Transport Field Mapping" section runs lines 1111-1141. Insert the new `## Error Handling Contract` between those (just before "Machine-Readable Schemas" at line ~954) so it appears after every event's payload schema is enumerated but before the cross-cutting machine-readable references. Subsections by transport keep the doc linear — readers who want the contract for one transport can jump to the matching subsection heading.

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).


## Session Log
- `/ll:refine-issue` - 2026-07-08T14:38:41 - `ea1dab68-2ebe-4bc4-99ae-67df8309e565.jsonl`
