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

A normal invocation records the rows it offers **when the existing local store/schema is ready**; it never creates/migrates history to record a recommendation. `--no-record` and `--explain` write nothing, including incidental CLI telemetry. `ll-next accept REC_ID` validates a recorded recommendation and appends an idempotent explicit acknowledgement. `ll-next feedback REC_ID [--json]` is a bounded read-only lookup reporting `accepted` (explicit acknowledgement present, with its time) or `unknown`; there is **no `ignored` state** and no automatic matching in this slice. Acceptance never proves causation, implementation start or success.

Selection stays the core round-robin policy; recording never changes recommendation content, order or exit code.

## Motivation

Collect inspectable evidence (what was offered, what the user explicitly took) before trusting any feedback policy, without fabricating rejection from repeated displays or telemetry gaps.

## Proposed Solution

### Events table and recording

- `recommendation_events`: unique `event_id` UUID, `rec_id` UUID, `kind` (`shown`/`accepted_explicit`), `ts`, `project_key`, nullable `session_id`, `invocation_id`, `as_of`, rank, action type/key/fingerprint, serialized typed `action_spec`, target/key and the invocation's requested top/type filter. Retain the offered semantic fingerprint/action specification immutably. `UNIQUE(rec_id, kind)` makes accept retries idempotent and supplies the v1 lookup index; no redundant kind/time/search index without a consumer. No mutable acceptance column.
- `project_key` is a SHA-256 hash of the canonical resolved project-root path, computed once independently of DB location. Invocation from a subdirectory shares the same key; a different checkout/project does not, even if `LL_HISTORY_DB` or `history.db_path` points both at one SQLite file. All writes retain this key and accept/feedback verify it. Relocating the checkout makes old IDs unknown in the new location; document this v1 limitation rather than adding a project-identity registry. Global UUID identity still uses `UNIQUE(rec_id, kind)`; project scope is an access predicate, not a different recommendation identity.
- Assign shown UUIDs once per invocation. Persist selected rows in one atomic batch **before** rendering so output can say `recording=recorded|disabled|unavailable(reason)` and expose IDs only for rows actually saved. Shown is an offered output, not proof anyone read it.
- Stamp `shown.ts` once for the atomic write attempt immediately before emission; keep the feature-read `as_of` separately. A committed shown row means an offer was prepared for output: broken pipes/process failure after commit may prevent delivery. Do not claim the write-before-render protocol proves successful display or reading.
- Use the shared `schema._MIGRATIONS` for local and remote DDL, update `schema_manifest.json` through its generation path, wire writers/queries through `session_store/__init__.py` imports and `__all__`. Remote open never migrates. **v1 does not record to or read from a remote (libsql/Hrana) store:** recording reports `unavailable(remote_unsupported_v1)`, `accept`/`feedback` exit 2 with that reason; remote support follows ENH-3720.
- Keep the table outside `_REBUILD_TABLES` **and** recommendation search rows outside `_REBUILD_SEARCH_KINDS` (prefer a kindless table); declare the classification so the manifest/kind coverage gate passes. A rebuild test proves shown/accept rows survive and that adding the excluded table does not alter the ENH-3678 derivation digest/version.
- Before any write, use FEAT-3721's strict read-only seam to verify the existing local schema stamp and required recommendation table/columns. Missing/outdated/incompatible schema reports `unavailable(schema_not_ready)` with the existing `ll-session migrate` initialization remedy; normal recording, accept and feedback never call `ensure_db`, initialize legacy files or perform rebuild/backfill. No new prepare command.
- Writes pass `busy_timeout_ms=250` explicitly (ENH-3679 applies it automatically only to `cli_event_context`) and use one batch transaction through a **local existing-store writable backend seam that never ensures schema**. `backend.open_history`/`SqliteBackend.connect` currently call schema setup, so this issue owns the narrow opt-in no-ensure seam if none exists at implementation time; open SQLite in existing-file `mode=rw`, preserve error translation, and leave all default callers unchanged. Recheck required schema in the transaction to handle preflight/write races without migrating or recreating a removed DB. There is no promised one-second total deadline: lock waits are capped per operation, finite transaction work is bounded by selected rows, and filesystem stalls/total write deadlines are separate work. No recommendation pruning/retention in v1; document growth.
- Automatic recording honors `next.recording.enabled` (default true), `analytics.enabled`, the `LL_ANALYTICS_CAPTURE=0/false/off` kill switch and the `analytics.capture.cli_commands` allowlist; report the disabling reason before opening a write connection. Explicit `accept` is a deliberate acknowledgement independent of automatic capture gates but still requires actual storage success.
- Automatic write failure leaves recommendation content/order and exit code intact with a recording diagnostic and no usable accept IDs. Reads fall back gracefully. `--help` and usage/config errors do no history work. This slice avoids `cli_event_context` and write-capable wrappers for `feedback`.

### accept and feedback

- `accept REC_ID` is project-scoped and may run in another session. Validate UUID syntax before storage access. In one `BEGIN IMMEDIATE` transaction, require a shown row with the current project key, then `INSERT OR IGNORE` an acknowledgement copied from that immutable offer; rollback on failure. Reject unknown/foreign-project IDs as unknown in this project, and be idempotent (success for an already accepted ID). Exit 0 on success/idempotent replay, 1 for unknown-in-project ID, 2 for usage/config/schema/storage failure. Capture gates do not bypass project validation.
- `feedback REC_ID` validates UUID syntax, requests the exact project/rec_id through FEAT-3721's point lookup (independent of recent-event caps), and renders `accepted|unknown` with offered target/action, as_of, availability and provenance. It never records another display, creates/migrates a store or writes cache files. Exit 0 for a found row, 1 for unknown-in-project ID, 2 for usage/config/unavailable storage. Only a successful lookup with a shown row and no acknowledgement yields state `unknown`; query failure is unavailable storage. Add a generated feedback JSON Schema/fixture alongside the core output schema.

Extend the core **recommendation** JSON Schema as well as adding the feedback schema: include envelope recording status/reason and nullable per-recommendation `rec_id`, present only after the whole batch commits. IDs/times/recording diagnostics are observational fields; with those removed, recorded/disabled/unavailable invocations must have identical semantic recommendation content and order. Empty recommendation lists do no write work. Keep help/config/usage-error paths ahead of history resolution and avoid incidental `cli_event_context` on every ll-next mode.

## Integration Map

### Files to Modify

- `session_store/schema.py`, `schema_manifest.json`, `writers.py`, `queries.py`, `__init__.py`; migration/rebuild tests and the narrow local existing-store writable seam in `session_store/backend.py` (default behavior unchanged).
- FEAT-3561 CLI: recording, `accept`, `feedback`, `--no-record`; FEAT-3721 reader consumption.
- `config/{features,core,__init__}.py`, `config-schema.json` for `next.recording.enabled`; `docs/reference/CLI.md`, `API.md`, `CONFIGURATION.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`.

## Program Design

### Types

- `RecommendationEvent` with the schema fields above; `FeedbackResult(state, accepted_at, provenance, reason)`, state `accepted` or `unknown`.

### Signatures

- `record_shown(events, *, project_key: str, now: Callable[[], datetime]) -> RecordingResult`; `record_accepted(rec_id, *, project_key: str) -> AcceptanceWriteResult` — finite atomic batches, existing-schema-only and idempotent identities.
- `lookup_feedback(snapshot: HistorySnapshot, rec_id: str) -> FeedbackResult` — pure over the snapshot.

### Call Path

CLI → pure project snapshot → generators/scoring → select → bounded atomic record (unless disabled) → render recording status/IDs. Accept → resolve shown ID in current project → append acknowledgement → report result. Feedback → FEAT-3721 snapshot → `lookup_feedback` → human/JSON.

## Implementation Steps

1. Implement after FEAT-3561 and FEAT-3721; claim the next free schema version.
2. Add migration, project ownership/action payload, consumed lookup index, classification/exports and rebuild-preservation tests; verify the derivation fingerprint is unchanged.
3. Add strict schema preflight and the existing-store no-ensure write seam, then recording, transactional `accept`, point-query `feedback`, `--no-record` and recommendation/feedback schema extensions; document schema-not-ready and remote-unsupported behavior.
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
- [ ] Atomic shown batches expose persisted IDs/status truthfully; failed/rolled-back batches expose no usable IDs. Transactional `accept` rejects unknown/foreign-project IDs, is cross-session and concurrency/retry-idempotent. Shared-DB two-project, subdirectory, relocation and malformed-UUID fixtures pin scope; remote stores report `unavailable(remote_unsupported_v1)`.
- [ ] `feedback` is a read-only lookup with human/JSON Schema and exit-code tests; only `accepted|unknown`; no store creation/migration or cache writes.
- [ ] Recording/accept use the 250 ms per-lock timeout and existing-store no-ensure seam; missing/old/incompatible schema degrades without directory/file creation, migration or rebuild, including a preflight/write race. Unavailable recording preserves semantic recommendation content/order/exit code; deliberate `accept` reports schema/storage failure. Default backend callers retain their behavior; no total-write-deadline guarantee is asserted.
- [ ] Automatic capture respects `analytics.enabled`, `LL_ANALYTICS_CAPTURE` and the `cli_commands` allowlist; no-record/explain/help/errors write nothing.
- [ ] Recommendation and feedback JSON Schemas/drift fixtures cover recorded/disabled/unavailable/null-ID states, exact old-ID lookup and unavailable-vs-unknown exits; consumed config/docs and focused tests pass. `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`.

## Review Notes

- 2026-10-03: Opus recommended deferring pressure; kept as opt-in. Follow-up consult gave conditional GO (0.76) and added deadlines, per-source availability and parameter-aware offers.
- 2026-10-04: Opus epic review (0.78) found the issue bundled four projects. Split out the reader (FEAT-3721), deadline plumbing (ENH-3720) and, to deferred FEAT-3722, ProducerEvidence attribution and pressure (full design preserved there). v1 is local-only.
- 2026-10-04: Follow-up audit/Opus critique (0.78) added concrete project ownership for redirected/shared stores, immutable action payloads and transactional accept; removed unused indexes and the unsupported one-second write guarantee. Recording now skips unprepared schema and owns only a narrow existing-store no-ensure write seam; existing `ll-session migrate` performs deliberate setup. Recommendation output Schema changes and undelivered committed offers are explicit.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
