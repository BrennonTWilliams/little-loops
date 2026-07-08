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

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).
