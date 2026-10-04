---
id: FEAT-3711
type: FEAT
title: ll-next recommendation events and explicit acceptance
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
- FEAT-3721
relates_to:
- ENH-3678
- ENH-3679
- ENH-3720
- FEAT-3722
- BUG-3715
---

# FEAT-3711: ll-next recommendation events and explicit acceptance

## Summary

Add append-only recommendation `shown` and explicit-acceptance events, `ll-next accept REC_ID`, and a read-only `ll-next feedback REC_ID` lookup. This issue owns the arena's only history schema migration; claim the next free schema version at implementation time (currently 58, so 59 if still free). **Slimmed after an Opus epic review (2026-10-04):** automatic observed-acceptance attribution (`ProducerEvidence` adapters) and opt-in activity pressure moved to the deferred FEAT-3722; the shared read-only reader is FEAT-3721; the cross-backend deadline plumbing is ENH-3720. v1 is **local SQLite only**.

## Current Behavior

After FEAT-3561 the core is stateless and every available verb gets a first-round opportunity. No table identifies offered recommendations or explicit acknowledgement. Existing telemetry cannot prove that an unmatched recommendation was ignored.

## Expected Behavior

A normal invocation records the rows it offers; `--no-record` and `--explain` write nothing, including incidental CLI telemetry. `ll-next accept REC_ID` validates a recorded recommendation and appends an idempotent explicit acknowledgement. `ll-next feedback REC_ID [--json]` is a bounded read-only lookup reporting `accepted` (explicit acknowledgement present, with its time) or `unknown`; there is **no `ignored` state** and no automatic matching in this slice. Acceptance never proves causation, implementation start or success.

Selection stays the core round-robin policy; recording never changes recommendation content, order or exit code.

## Motivation

Collect inspectable evidence (what was offered, what the user explicitly took) before trusting any feedback policy, without fabricating rejection from repeated displays or telemetry gaps.

## Proposed Solution

### Events table and recording

- `recommendation_events`: unique `event_id` UUID, `rec_id` UUID, `kind` (`shown`/`accepted_explicit`), `ts`, nullable `session_id`, `invocation_id`, `as_of`, rank, action type/key/fingerprint, target/key and the invocation's requested top/type filter. Retain the offered semantic fingerprint immutably. `UNIQUE(rec_id, kind)` makes accept retries idempotent. Add bounded-query indexes for shown IDs and kind/time. No mutable acceptance column.
- Assign shown UUIDs once per invocation. Persist selected rows in one atomic batch **before** rendering so output can say `recording=recorded|disabled|unavailable(reason)` and expose IDs only for rows actually saved. Shown is an offered output, not proof anyone read it.
- Stamp `shown.ts` at the successful write attempt, immediately before emission; keep the feature-read `as_of` separately.
- Use the shared `schema._MIGRATIONS` for local and remote DDL, update `schema_manifest.json` through its generation path, wire writers/queries through `session_store/__init__.py` imports and `__all__`. Remote open never migrates. **v1 does not record to or read from a remote (libsql/Hrana) store:** recording reports `unavailable(remote_unsupported_v1)`, `accept`/`feedback` exit 2 with that reason; remote support follows ENH-3720.
- Keep the table outside `_REBUILD_TABLES` **and** recommendation search rows outside `_REBUILD_SEARCH_KINDS` (prefer a kindless table); declare the classification so the manifest/kind coverage gate passes. A rebuild test proves shown/accept rows survive and that adding the excluded table does not alter the ENH-3678 derivation digest/version.
- Writes pass `busy_timeout_ms=250` explicitly (ENH-3679 applies it automatically only to `cli_event_context`). Because the cross-backend deadline primitive is ENH-3720, v1 bounds the optional stage with the 250 ms lock timeout plus a monotonic wall-clock check that skips remaining optional work after 1 second; reuse backend error translation, no raw sqlite connection. No recommendation pruning/retention in v1; document growth.
- Automatic recording honors `next.recording.enabled` (default true), `analytics.enabled`, the `LL_ANALYTICS_CAPTURE=0/false/off` kill switch and the `analytics.capture.cli_commands` allowlist; report the disabling reason before opening a write connection. Explicit `accept` is a deliberate acknowledgement independent of automatic capture gates but still requires actual storage success.
- Automatic write failure leaves recommendation content/order and exit code intact with a recording diagnostic and no usable accept IDs. Reads fall back gracefully. `--help` and usage/config errors do no history work. This slice avoids `cli_event_context` and write-capable wrappers for `feedback`.

### accept and feedback

- `accept REC_ID` is project-scoped and may run in another session. Require an existing shown row, reject unknown IDs, retain the immutable shown target/action, and be idempotent (success for an already accepted ID). Exit 0 on success/idempotent replay, 1 for unknown ID, 2 for usage/config/storage failure.
- `feedback REC_ID` reads the shown row and any acknowledgement through FEAT-3721's reader and renders `accepted|unknown` with as_of, availability and provenance. It never records another display, creates/migrates a store or writes cache files. Exit 0 for a found row, 1 for unknown ID, 2 for usage/config/unavailable storage. Add a generated feedback JSON Schema/fixture alongside the core output schema.

## Integration Map

### Files to Modify

- `session_store/schema.py`, `schema_manifest.json`, `writers.py`, `queries.py`, `__init__.py`; migration/rebuild tests.
- FEAT-3561 CLI: recording, `accept`, `feedback`, `--no-record`; FEAT-3721 reader consumption.
- `config/{features,core,__init__}.py`, `config-schema.json` for `next.recording.enabled`; `docs/reference/CLI.md`, `API.md`, `CONFIGURATION.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`.

## Program Design

### Types

- `RecommendationEvent` with the schema fields above; `FeedbackResult(state, accepted_at, provenance, reason)`, state `accepted` or `unknown`.

### Signatures

- `record_shown(events, *, now: Callable[[], datetime]) -> RecordingResult`; `record_accepted(rec_id) -> AcceptanceWriteResult` — bounded, idempotent identities.
- `lookup_feedback(snapshot: HistorySnapshot, rec_id: str) -> FeedbackResult` — pure over the snapshot.

### Call Path

CLI → pure project snapshot → generators/scoring → select → bounded atomic record (unless disabled) → render recording status/IDs. Accept → resolve shown ID in current project → append acknowledgement → report result. Feedback → FEAT-3721 snapshot → `lookup_feedback` → human/JSON.

## Implementation Steps

1. Implement after FEAT-3561 and FEAT-3721; claim the next free schema version.
2. Add migration, indexes, classification/exports and rebuild-preservation tests; verify the derivation fingerprint is unchanged.
3. Add recording, `accept`, `feedback`, `--no-record`; document the remote-unsupported behavior.
4. Update docs/tests; keep default round-robin deterministic.

## Scope Boundaries

- **In scope:** append-only events, explicit accept, feedback lookup, local-only recording, migration/exports/config/docs.
- **Out of scope:** automatic observed-acceptance attribution and pressure (FEAT-3722, deferred), cross-backend deadline plumbing and remote support (ENH-3720), the shared reader (FEAT-3721), ignored/rejection labels, causal attribution, learned weights, retention/pruning, execute.

## Impact

- **Priority**: P3
- **Effort**: Medium — one table, recording/accept/feedback CLI and config wiring.
- **Risk**: Low–Medium — additive schema; recording is best-effort and never alters output.
- **Breaking Change**: No.

## Use Case

A user sees recorded recommendation IDs and explicitly accepts one from another session; `feedback` confirms it. Repeated displays never manufacture acceptance.

## Acceptance Criteria

- [ ] One additive shared migration and manifest/classification/exports work locally; claim the next free version, preserve events through rebuild, leave the ENH-3678 derivation fingerprint/version unchanged.
- [ ] Atomic shown batches expose persisted IDs/status truthfully; `accept` rejects unknown IDs, is project-scoped, cross-session and concurrency/retry-idempotent; remote stores report `unavailable(remote_unsupported_v1)`.
- [ ] `feedback` is a read-only lookup with human/JSON Schema and exit-code tests; only `accepted|unknown`; no store creation/migration or cache writes.
- [ ] Automatic writes use the 250 ms lock timeout and the 1-second optional-stage cutoff; unavailable storage never changes recommendation content/order/exit code; deliberate `accept` reports storage failure.
- [ ] Automatic capture respects `analytics.enabled`, `LL_ANALYTICS_CAPTURE` and the `cli_commands` allowlist; no-record/explain/help/errors write nothing.
- [ ] Consumed config/output Schema/docs and focused tests pass; `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`.

## Review Notes

- 2026-10-03: Opus recommended deferring pressure; kept as opt-in. Follow-up consult gave conditional GO (0.76) and added deadlines, per-source availability and parameter-aware offers.
- 2026-10-04: Opus epic review (0.78) found the issue bundled four projects. Split out the reader (FEAT-3721), deadline plumbing (ENH-3720) and, to deferred FEAT-3722, ProducerEvidence attribution and pressure (full design preserved there). v1 is local-only.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
