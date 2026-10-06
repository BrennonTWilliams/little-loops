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
- BUG-3737
---

# FEAT-3711: ll-next recommendation events and explicit acceptance

## Summary

Add append-only recommendation `shown` and explicit-acceptance events, `ll-next accept REC_ID`, and a read-only `ll-next feedback REC_ID` lookup. This issue owns the arena's only history schema migration; claim the next free schema version at implementation time (currently 60, so 61 if still free), and derive the write-readiness floor from the assigned migration version. **Slimmed after an Opus epic review (2026-10-04):** automatic observed-acceptance attribution (`ProducerEvidence` adapters) and opt-in activity pressure moved to the deferred FEAT-3722; the shared read-only reader is FEAT-3721; the cross-backend read-deadline primitive ENH-3720 is now done and reused here. It does not bound writes or activate remote support. v1 is **local SQLite only**.

## Current Behavior

After FEAT-3561 the core is stateless and every available verb gets a first-round opportunity. No table identifies offered recommendations or explicit acknowledgement. Existing telemetry cannot prove that an unmatched recommendation was ignored.

## Expected Behavior

A normal invocation records the rows it offers **when the existing local store/schema is ready**; it never creates/migrates history to record a recommendation. `--no-record` and `--explain` perform no application writes, including incidental CLI telemetry. History reads can create SQLite-managed WAL/SHM coordination files under FEAT-3721’s documented mode=ro limitation; the main DB/schema and application cache/marker files remain untouched. `ll-next accept REC_ID` validates a recorded recommendation and appends an idempotent explicit acknowledgement. `ll-next feedback REC_ID [--json]` is a bounded read-only lookup reporting `accepted` (explicit acknowledgement present, with its time) or `unknown`; there is **no `ignored` state** and no automatic matching in this slice. Acceptance never proves causation, implementation start or success.

Selection stays the core round-robin policy; recording never changes recommendation content, order or exit code.

## Motivation

Collect inspectable evidence (what was offered, what the user explicitly took) before trusting any feedback policy, without fabricating rejection from repeated displays or telemetry gaps.

## Proposed Solution

### Events table and recording

- `recommendation_events`: unique `event_id` UUID, `rec_id` UUID, `kind` (`shown`/`accepted_explicit`), `ts`, `project_key`, nullable `session_id`, `invocation_id`, `as_of`, rank, action type/key/fingerprint, serialized typed `action_spec`, target/key and the invocation's requested top/type filter. Retain the offered semantic fingerprint/action specification immutably. `UNIQUE(rec_id, kind)` makes accept retries idempotent and supplies the v1 lookup index; no redundant kind/time/search index without a consumer. No mutable acceptance column.
- `project_key` is a SHA-256 hash of the canonical resolved project-root path, computed once independently of DB location. Invocation from a subdirectory shares the same key; a different checkout/project does not, even if `LL_HISTORY_DB` or `history.db_path` points both at one SQLite file. All writes retain this key and accept/feedback verify it. Relocating the checkout makes old IDs unknown in the new location; document this v1 limitation rather than adding a project-identity registry. Global UUID identity still uses `UNIQUE(rec_id, kind)`; project scope is an access predicate, not a different recommendation identity.
- Assign shown UUIDs once per invocation. Persist selected rows in one atomic batch **before** rendering so output can say `recording=recorded|disabled|unavailable(reason)` and expose IDs only for rows actually saved. Shown is an offered output, not proof anyone read it.
- Shown batches use plain `INSERT`: any constraint or UUID collision rolls back the entire batch, yields `unavailable(write_failed)` and exposes no usable IDs. Do not ignore a conflicting row or attach the new offer to an existing recommendation identity. The acceptance retry policy below applies only to `(rec_id, kind)`, not arbitrary integrity failures.
- Persist the offered typed `action_spec` without a lossy verb-specific field whitelist or reconstruction from today's files/config. Preserve every field of the registered action variant, including loop/sprint definition provenance, assessed sprint-member provenance and normalized scan scope when FEAT-3713 extends the registry. Acceptance copies that stored payload and fingerprint unchanged; mutable member-status provenance is not added to semantic identity. Test events-before-generators and generators-before-events integration so extensions survive recording/accept/feedback in either arrival order. This does not require accepting arbitrary unregistered action variants.

- Once offers are persisted, freeze each registered action variant's discriminator and existing field meanings. Follow-ons may add variants or optional fields whose absence retains the historical meaning; an incompatible semantic change needs a new explicit variant discriminator, not reinterpretation of existing rows. No separate offer-version field/decoder framework is needed for the two additive feature-arrival orders. A found offer with an unsupported variant reports unavailable `unsupported_action_spec` (exit 2 for accept/feedback), distinct from an absent-in-project ID or a valid unacknowledged offer; malformed recognized payloads keep the strict unavailable/storage-failure policy. This failure is confined to that identity/request, not unrelated offers or CLI evidence. Expanded six-verb code must still decode/acknowledge four-verb offers with their original payload/fingerprint.

- Preserve the core loop variant's `fingerprint_scope` and top-level-digest limitation. Every new shown offer receives an independent random UUID even when its fingerprint equals a prior offer; fingerprint equality cannot coalesce displays, reuse an assessment, suppress a new offer or transfer acceptance between IDs. Explicit accept acknowledges the stored `rec_id`, offered action specification and `as_of`; it does not assert that inherited/imported behavior, runtime dependencies or today's gates match that offer. Historical payload validation checks its registered shape/scope, not live executable equivalence.
- Store event timestamps and feature `as_of` in one fixed-precision UTC `Z` ISO format (microseconds). Inject `now` into acceptance as well as shown recording. A wall-clock rollback does not invalidate an acknowledgement or require `accepted.ts >= shown.ts`; append/transaction identity determines acceptance, and timestamps are reported with that limitation.
- Stamp `shown.ts` once for the atomic write attempt immediately before emission; keep the feature-read `as_of` separately. A committed shown row means an offer was prepared for output: broken pipes/process failure after commit may prevent delivery. Do not claim the write-before-render protocol proves successful display or reading.
- Use the shared `schema._MIGRATIONS` for local and remote DDL, update `schema_manifest.json` through its generation path, wire writers/queries through `session_store/__init__.py` imports and `__all__`. Remote open never migrates. **v1 does not record to or read from a remote (libsql/Hrana) store:** recording reports `unavailable(remote_unsupported_v1)`, `accept`/`feedback` exit 2 with that reason; remote support requires a separate consumer feature; the completed ENH-3720 primitive alone does not enable it.
- Keep the table outside `_REBUILD_TABLES` **and** recommendation search rows outside `_REBUILD_SEARCH_KINDS` (prefer a kindless table); declare the classification so the manifest/kind coverage gate passes. A rebuild test proves shown/accept rows survive and that adding the excluded table does not alter the ENH-3678 derivation digest/version.
- This issue adds typed `RecommendationLookup(project_key, rec_id)` and `RecommendationSchemaProbe` requests/dispatch to FEAT-3721’s shared reader, together with the real migration/columns/index fixtures; FEAT-3721 does not preimplement future table SQL. Lookup is bounded to at most the shown/accepted rows through `UNIQUE(rec_id, kind)` and verifies project ownership independently of CLI history budgets. The readiness probe verifies the index as well as columns so a malformed lookalike cannot cause a hidden full-table scan. Before any write, use that strict read-only seam to verify the existing local schema stamp and required recommendation table/columns. Writes require a valid stamp at least the owning migration version and no newer than the installed runtime, plus required table/columns/unique-index shape; column-compatible exact reads can remain available independently of write readiness. Missing/outdated/incompatible schema reports `unavailable(schema_not_ready)` with the existing `ll-session migrate` initialization remedy; normal recording, accept and feedback never call `ensure_db`, initialize legacy files or perform rebuild/backfill. No new prepare command.
- Read probes and feedback use FEAT-3721’s one shared `Deadline.after(1.0)` with explicit 250 ms lock waits and its nonpreemptive limitations. Writes pass `busy_timeout_ms=250` explicitly (ENH-3679 applies it automatically only to `cli_event_context`) and use one batch transaction through a **local existing-store writable backend seam that never ensures schema**. `backend.open_history`/`SqliteBackend.connect` currently call schema setup, so this issue owns the narrow opt-in no-ensure seam if none exists at implementation time; open SQLite in existing-file `mode=rw`, preserve error translation, and leave all default callers unchanged. Recheck required schema in the transaction to handle preflight/write races without migrating or recreating a removed DB. There is no promised one-second total **write** deadline: lock waits are capped per operation, finite transaction work is bounded by selected rows, and filesystem stalls/total write deadlines are separate work. No recommendation pruning/retention in v1; document growth.
- Reuse BUG-3737's shared percent-encoded literal file-URI builder for the new `mode=rw` seam. Raw `file:{path}` interpolation can lose the mode query and create/open a different file; special-character existing/missing paths and populated truncated/decoded decoys must prove writer identity/no-creation as well as the reader's guarantee. Preserve the previously resolved local target without cwd re-resolution.
- Automatic recording honors `next.recording.enabled` (default true), `analytics.enabled`, the `LL_ANALYTICS_CAPTURE=0/false/off` kill switch and the `analytics.capture.cli_commands` allowlist; report the disabling reason before opening a write connection. Explicit `accept` is a deliberate acknowledgement independent of automatic capture gates but still requires actual storage success.
- Automatic write failure leaves recommendation content/order and exit code intact with a recording diagnostic and no usable accept IDs. Best-effort recommendation history falls back gracefully; an explicit feedback request reports storage unavailability with exit 2. `--help` and usage/config errors do no history work. This slice avoids `cli_event_context` and write-capable wrappers for `feedback`.

### accept and feedback

- `accept REC_ID` is project-scoped and may run in another session; it acknowledges the stored immutable offer without revalidating today's gates or executing work. A removed/completed target or changed definition remains the historical offered action, explicitly labeled as such. Validate UUID syntax before storage access. In one `BEGIN IMMEDIATE` transaction, require a valid shown row with the current project key, then insert an acknowledgement copied from that immutable offer with targeted `ON CONFLICT(rec_id, kind) DO NOTHING`; rollback on failure. If using `INSERT ... SELECT`, include its shown-row/project `WHERE` predicate before `ON CONFLICT` to avoid SQLite's parser ambiguity. Read back and validate the project-scoped acknowledgement in the same transaction before reporting success; return its original stored timestamp on replay. A missing or inconsistent acknowledgement is a storage failure, never successful acceptance. Other constraints, including `event_id` uniqueness, must raise and roll back; do not use `INSERT OR IGNORE`, which can silently discard NOT NULL/CHECK violations and unrelated conflicts. Reject unknown/foreign-project IDs as unknown in this project, and be idempotent (success for an already accepted ID). Exit 0 only after successful commit/idempotent replay, 1 for unknown-in-project ID, 2 for usage/config/schema/storage failure. Capture gates do not bypass project validation.
- `feedback REC_ID` validates UUID syntax, requests the exact project/rec_id through this issue’s point-lookup request added to FEAT-3721 (independent of recent-event caps), and renders `accepted|unknown` with offered target/action, as_of, availability and provenance. Exact identity lookup reads the current transaction’s committed offer/acknowledgement, without filtering by the feature `as_of` captured earlier; an accept committed between that clock capture and the read is visible. Report `read_observed_at` separately from the offer’s `as_of`; neither implies an atomic issue/git/history snapshot. It never records another display, creates/migrates the main store or writes application cache files; SQLite coordination sidecars follow the shared reader limitation. Exit 0 for a found row, 1 for unknown-in-project ID, 2 for usage/config/unavailable storage. Only a successful lookup with a shown row and no acknowledgement yields state `unknown`; query failure is unavailable storage. Add a generated feedback JSON Schema/fixture alongside the core output schema.

Extend the core **recommendation** JSON Schema as well as adding the feedback schema: include envelope recording status/reason and nullable per-recommendation `rec_id`, present only after the whole batch commits. IDs/times/recording diagnostics are observational fields; with those removed, recorded/disabled/unavailable invocations must have identical semantic recommendation content and order. Empty recommendation lists do no recording probes or writes; any generator read remains separately driven by its requested evidence. `--no-record` disables automatic writes only; a requested sprint bucket may still need a read, while implement-only/no-record and history-independent explain paths request no history. Disabled recording short-circuits readiness probes/write target resolution as well as the write connection. Keep help/config/usage-error paths ahead of history resolution and avoid incidental `cli_event_context` on every ll-next mode.

Register `recording` in the landed shared `NextConfig` root allowlist/schema without validating it in the legacy loop-weight consumer. Extend the core cross-consumer fixtures with malformed recording settings beside otherwise valid legacy weights; merely constructing config and consuming the independent legacy subtree must retain their behavior. Recommendation recording validates its own consumed setting before opening storage.

Use FEAT-3721's frozen target/resolution provenance on recording, accept and feedback. Relative `LL_HISTORY_DB` retains its existing original-cwd-relative meaning: root/subdirectory invocation shares the project key but can deliberately select different stores under that override. Document using an absolute override to share a store across working directories; do not reinterpret it as project-root-relative or fabricate another project's offer when the selected store lacks the ID.

## Integration Map

### Files to Modify

- `session_store/schema.py`, `schema_manifest.json`, `writers.py`, `queries.py`, `__init__.py`; migration/rebuild tests and the narrow local existing-store writable seam in `session_store/backend.py` (default behavior unchanged).
- FEAT-3561 CLI: recording, `accept`, `feedback`, `--no-record`; FEAT-3721 reader consumption.
- `config/{features,core,__init__}.py`, `config-schema.json` for `next.recording.enabled`; `docs/reference/CLI.md`, `API.md`, `CONFIGURATION.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`.

## Program Design

### Types

- `RecommendationEvent` with the schema fields above; `FeedbackResult(state, accepted_at, read_observed_at, provenance, reason)`, state `accepted` or `unknown`.

### Signatures

- `record_shown(events, *, project_key: str, now: Callable[[], datetime]) -> RecordingResult`; `record_accepted(rec_id, *, project_key: str, now: Callable[[], datetime]) -> AcceptanceWriteResult` — finite atomic batches, existing-schema-only and idempotent identities.
- `lookup_feedback(snapshot: HistorySnapshot, rec_id: str) -> FeedbackResult` — pure over the snapshot.

### Call Path

CLI → pure project snapshot → generators/scoring → select → bounded atomic record (unless disabled) → render recording status/IDs. Accept → resolve shown ID in current project → append acknowledgement → report result. Feedback → FEAT-3721 snapshot → `lookup_feedback` → human/JSON.

## Implementation Steps

1. Implement after FEAT-3561 and FEAT-3721; claim the next free schema version.
2. Add migration, project ownership/action payload, consumed lookup index, classification/exports and rebuild-preservation tests; verify the derivation fingerprint is unchanged.
3. Add strict schema preflight and the existing-store no-ensure write seam, then recording, transactional `accept`, point-query `feedback`, `--no-record` and recommendation/feedback schema extensions; document schema-not-ready and remote-unsupported behavior.
4. Update docs/tests; keep default round-robin deterministic.

## Scope Boundaries

- **In scope:** append-only events, explicit accept, feedback lookup, local-only recording, migration/table-specific reader requests/exports/config/docs.
- **Out of scope:** automatic observed-acceptance attribution and pressure (FEAT-3722, deferred), new deadline machinery, write deadlines and remote support (reuse completed ENH-3720 for reads only), the shared reader (FEAT-3721), ignored/rejection labels, causal attribution, learned weights, retention/pruning, execute.

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
- [ ] Forced NOT NULL/CHECK and unrelated `event_id` conflicts cannot silently succeed: accept exits 2 and creates no acknowledgement; a shown-batch conflict rolls back every offered row and exposes no IDs. Successful/idempotent acceptance reads back the stored project-scoped payload and original acceptance time before commit. Malformed/inconsistent stored offers or acknowledgements are storage failures, not unknown IDs or success.
- [ ] Registered action-spec extension fields survive shown/accept/feedback without loss or recomputation, including FEAT-3713's offered sprint definition/member provenance and scan scope. Both feature arrival orders retain identical stored fingerprint/payload semantics despite later definition/config/status changes.
- [ ] Offers written before the six-verb extension remain decodable/acknowledgeable after it, with optional-field absence preserving historical meaning and no rewritten payload/fingerprint. An unsupported action variant makes only its found identity unavailable with exit 2, never `unknown`/accepted; recognized malformed payloads remain strict failures. No separate offer-version field or compatibility framework is introduced.
- [ ] Separate invocations with equal limited loop fingerprints create distinct shown IDs; acknowledging one does not accept another or suppress re-assessment. Inheritance/import changes cannot be hidden by fingerprint reuse, and feedback preserves the registered fingerprint scope rather than labeling it a full definition version.
- [ ] `feedback` is a read-only lookup with human/JSON Schema and exit-code tests; only `accepted|unknown`; no main-store creation/migration or application cache writes. Old-ID lookup stays exact when CLI history exceeds its budget; incompatible/absent lookup tables or indexes do not erase usable CLI evidence. Fixtures cover injected acceptance time, clock rollback, accept committed after feature-as_of/before the read, removed/changed targets and SQLite-managed WAL sidecars.
- [ ] Recording/accept use the 250 ms per-lock timeout and existing-store no-ensure seam; missing/old/incompatible schema degrades without directory/file creation, migration or rebuild, including a preflight/write race. Unavailable recording preserves semantic recommendation content/order/exit code; deliberate `accept` reports schema/storage failure. Default backend callers retain their behavior; no total-write-deadline guarantee is asserted.
- [ ] Existing-file writes consume BUG-3737's encoded URI helper; `#`, `?`, `%`, spaces and Unicode in filenames/directories cannot select or create a truncated/decoded alias. Missing files remain missing and populated decoys untouched; default backend connection policy is unchanged.
- [ ] Recording/accept/feedback consume the once-frozen target; relative environment-override root/subdirectory fixtures preserve and disclose cwd-relative store selection, while an absolute override shares the store and project-scoped IDs as documented.
- [ ] Automatic capture respects `analytics.enabled`, `LL_ANALYTICS_CAPTURE` and the `cli_commands` allowlist; no-record/explain/help/errors write nothing.
- [ ] Recommendation and feedback JSON Schemas/drift fixtures cover recorded/disabled/unavailable/null-ID states, exact old-ID lookup and unavailable-vs-unknown exits; consumed config/docs and focused tests pass. `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`.

## Review Notes

- 2026-10-03: Opus recommended deferring pressure; kept as opt-in. Follow-up consult gave conditional GO (0.76) and added deadlines, per-source availability and parameter-aware offers.
- 2026-10-04: Opus epic review (0.78) found the issue bundled four projects. Split out the reader (FEAT-3721), deadline plumbing (ENH-3720) and, to deferred FEAT-3722, ProducerEvidence attribution and pressure (full design preserved there). v1 is local-only.
- 2026-10-04: Follow-up audit/Opus critique (0.78) added concrete project ownership for redirected/shared stores, immutable action payloads and transactional accept; removed unused indexes and the unsupported one-second write guarantee. Recording now skips unprepared schema and owns only a narrow existing-store no-ensure write seam; existing `ll-session migrate` performs deliberate setup. Recommendation output Schema changes and undelivered committed offers are explicit.

- 2026-10-05: Opus review (0.72) moved recommendation lookup/probe SQL and schema fixtures here with their migration, pinned injected UTC acceptance timestamps and current-transaction lookup semantics, adopted completed ENH-3720 for reads only, and clarified explicit acceptance of historical offers/no-record read behavior. Read-only filesystem claims now disclose SQLite-managed WAL sidecars; recording semantics and local-only scope are retained.

- 2026-10-05 (additional review): Opus critique (0.76) plus source reproduction added BUG-3737's literal-safe URI helper to the future mode=rw seam, with existing/missing special-character and decoy fixtures. Pinned lossless persistence of registered action-spec extensions and both feature arrival orders, so sprint/scan offer provenance survives shown/accept/feedback without live reconstruction. No new event type, schema slice or automatic attribution was added.

- 2026-10-05 (identity/bounded-history review): Opus (0.78) corroborated the relative-environment-override mismatch: LL_HISTORY_DB is cwd-relative even with an explicit root, unlike configured/default paths. Recording/accept/feedback now consume the once-frozen absolute target with that documented exception, matching existing ll-session migrate and ll-sprint producers. Rejected a proposed general offer-size policy: exact point lookups remain at most two indexed rows and preserve the payload ll-next wrote; the narrow oversized-CLI-args guard belongs to FEAT-3721. Event schema/acceptance scope and feature independence remain unchanged.

- 2026-10-05 (implementation-contract review): Opus (0.74) corroborated the SQLite integrity gap: a temporary probe printed "INSERT OR IGNORE with NULL payload: 0 rows; no exception". Replaced broad ignore with targeted acknowledgement conflict handling/readback and plain atomic shown inserts; other integrity failures roll back. Updated current schema-version example to 59 -> 60 if free and pinned lazy recording-config isolation. Focused Opus advice (0.80) preserves limited loop fingerprint scope and fresh IDs per offer; equal hashes cannot transfer acknowledgement or suppress assessment. No event implementation, migration or score change is claimed.

- 2026-10-06: Source SCHEMA_VERSION is now 60 after BUG-3755; refreshed the illustrative next migration to 61 if still free, retaining assignment/readiness from the actual owning migration. Opus (0.80) recommended freezing persisted variant meanings instead of adding unused offer-version machinery for additive arrival orders. Adopted backward-compatible variant/optional-field rules and historical-offer fixtures. Rejected its proposed `unknown` result for unsupported/invalid payloads because that would conflate a found but unvalidated offer with a valid unacknowledged one; keep request-local unavailable/exit-2 diagnostics. Existing acceptance, local-only scope and feature independence are unchanged.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
