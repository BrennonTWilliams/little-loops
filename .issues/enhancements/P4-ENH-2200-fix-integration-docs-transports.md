---
id: ENH-2200
type: ENH
priority: P4
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels: [hermes, docs, transports]
testable: false
---

# Fix integration docs: transport count and SQLiteTransport location

## Summary

Integration-facing docs (and the v4 PRD) state "six transports ship" while only
**five** exist: `JsonlTransport`, `WebhookTransport`, `UnixSocketTransport`,
`OTelTransport` (in `transport.py`) and `SQLiteTransport` (in `session_store.py`,
not `transport.py`). Correct the count and note the location in
`docs/reference/EVENT-SCHEMA.md` and any transport reference docs so integrators
building against the transport layer have an accurate map. Source:
`PRD-Hermes-Integration-v4.md` (EG-5; the PRD text itself has been corrected).

## Current Behavior

`docs/reference/EVENT-SCHEMA.md` and other transport reference docs claim six transports ship, and do not document that `SQLiteTransport` resides in `session_store.py` rather than `transport.py`.

## Acceptance Criteria

- `docs/reference/EVENT-SCHEMA.md` and transport reference docs state five transports.
- `SQLiteTransport`'s actual location (`session_store.py`) is documented.
- No remaining "six transports" claim in repo docs.

## Motivation

Integrators building against the transport layer rely on docs for an accurate count and location map. A wrong count (six vs. five) and an undocumented module location (`SQLiteTransport` in `session_store.py`) will cause incorrect integration attempts and confusion when the expected sixth transport cannot be found.

## Proposed Solution

1. `grep -rn "six transports\|6 transports" docs/` to locate all incorrect claims.
2. Update `docs/reference/EVENT-SCHEMA.md`: change count to five, add a note that `SQLiteTransport` lives in `session_store.py`.
3. Update any other transport reference docs surfaced by the grep.
4. Verify final state with `grep "class .*Transport" scripts/little_loops/transport.py scripts/little_loops/session_store.py`.

## Scope Boundaries

- **In scope**: Count correction and `SQLiteTransport` location note in `docs/reference/EVENT-SCHEMA.md` and any linked transport reference docs.
- **Out of scope**: Code changes to transports, moving `SQLiteTransport` into `transport.py`, or adding/removing transport implementations.

## Implementation Steps

1. Grep docs for "six transports" / "6 transports" to enumerate all affected files
2. Update `EVENT-SCHEMA.md` with correct count (5) and `SQLiteTransport` location
3. Update any other affected reference docs found in step 1
4. Verify no remaining incorrect claims remain in repo docs

## Impact

- **Priority**: P4 — documentation correction; no user-facing feature impact
- **Effort**: Small — targeted doc-only edits, no code changes
- **Risk**: Low — docs-only change, no runtime impact
- **Breaking Change**: No

## Notes

- Verify against `grep "class .*Transport" scripts/little_loops/transport.py
  scripts/little_loops/session_store.py`.
- Small, doc-only change; no code impact.

## Status

**Open** | Created: 2026-06-16 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-16T18:28:30 - `652072f2-a11c-4dd7-9a33-67f1e5b1a03c.jsonl`
