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

## Acceptance Criteria

- `docs/reference/EVENT-SCHEMA.md` and transport reference docs state five transports.
- `SQLiteTransport`'s actual location (`session_store.py`) is documented.
- No remaining "six transports" claim in repo docs.

## Notes

- Verify against `grep "class .*Transport" scripts/little_loops/transport.py
  scripts/little_loops/session_store.py`.
- Small, doc-only change; no code impact.
