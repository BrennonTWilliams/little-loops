---
id: FEAT-3711
type: FEAT
title: ll-next recommendation events, observed acceptance and opt-in activity pressure
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
blocks:
- FEAT-3713
relates_to:
- ENH-3678
- ENH-3679
- ENH-3682
- BUG-3715
---

# FEAT-3711: ll-next recommendation events, observed acceptance and opt-in activity pressure

## Summary

Add append-only recommendation display/explicit-acceptance events, a shared read-only history snapshot with explicit unavailable states, query-time observed acceptance, and **opt-in** activity-based bucket pressure. Keep FEAT-3561's round-robin policy as the default. This issue owns the arena's only history schema migration; use the next free schema version at implementation time (currently 58, so 59 if still free), not a hardcoded reservation.

## Current Behavior

After FEAT-3561, the core is stateless and every available verb gets a first-round opportunity by default. No table identifies offered recommendations or explicit acceptance. Existing skill capture is best-effort and can be disabled, orchestration rows record a dequeue before implementation gates, and loop summary rows arrive only at completion. None proves that an unmatched recommendation was ignored or that a requested action completed successfully.

## Expected Behavior

A normal invocation can record the rows it offers; `--no-record` and `--explain` write nothing, including incidental CLI telemetry. `ll-next accept REC_ID` validates a previously recorded recommendation and appends an idempotent explicit acknowledgement. `ll-next feedback REC_ID [--json]` is a bounded read-only lookup that reports query-time `accepted` or `unknown` with evidence/provenance; **no `ignored` state** in this slice. Acceptance means an observed matching invocation/pick or explicit acknowledgement, never proof of causation, implementation start or successful outcome.

Pressure is disabled by default. When enabled, it uses observable action activity independently of how often recommendations were displayed; it can reorder buckets within round-robin rounds, particularly when an explicit `--top` requests fewer slots. Missing history degrades to the core policy with a visible reason. FEAT-3713 uses this issue's history reader rather than introducing a second one.

## Motivation

Collect inspectable evidence before trusting a feedback policy. Repeated displays, telemetry gaps and delayed completion records must not manufacture rejection, unfairly inflate acceptance, or turn a short advisory command into a database stall.

## Proposed Solution

### Shared history snapshot and producer contracts

Add one injected `HistorySnapshot` reader through the existing resolved-store/backend chokepoint. It opens read-only, never creates/migrates a store, honors `LL_HISTORY_DB`/configured local or remote targets and project access checks, and returns typed availability/diagnostics. Use one UTC `as_of`, bounded indexed queries and an explicit total read deadline. Missing files/tables, old remote schemas, suppressed/unavailable backends or timeouts yield unavailable data, not an exception or guessed negative evidence.

Availability is **per source/table**, with an overall diagnostic summary. A missing recommendation_events table cannot erase valid existing issue/loop/sprint activity. Read only the operation/target/time slices needed by the requested buckets or feedback ID. Pin finite query/row budgets; if a cap/deadline prevents proving the newest qualified activity or the most recent eligible offer, report that result as unknown/partial rather than attributing against an incomplete prefix. A requested row must be attributed against all competing offers relevant to its evidence, not just the one displayed by feedback.

`ProducerEvidence` has a stable semantic key, `action_key`, `target_key`, nullable proven `action_fingerprint`, `activity_bucket`, `event_at`, `available_at`/availability basis and provenance. Store row IDs alone are unsuitable identity because skill rows can be rebuilt. For skills, key the normalized session/timestamp/operation/explicit-target tuple; for orchestration use driver/run_id/issue_id/start, and for loops use run_id. Expand explicit batch targets into target-specific evidence only when their argument syntax is verified. Adapters normalize UTC timestamps and exact argument tokens; substring matching must never confuse BUG-1 with BUG-10. Truncated/ambiguous args, implicit targets and unrelated actions are unknown.

Reuse FEAT-3561's typed action grammar, canonicalization and fingerprint helper; FEAT-3712 imports the same pure parser without depending on this history reader. Normalize verified `ll:`/slash skill-name prefixes. Existing writers silently truncate skill argument text at 200 characters and CLI argv at 50 tokens: capture at either boundary is conservatively ambiguous, even if its visible prefix parses (a hidden trailing dry-run/filter flag could change the operation). Do not add a truncation flag or new producer subsystem here. For parameterized loops, exact target name/run_id alone is insufficient: matching input/context must be reconstructible and fingerprint-equal, otherwise automatic acceptance stays unknown. Coarse named activity can still drive the loop bucket without claiming exact invocation acceptance.

| Candidate operation | Named evidence and limitations |
|---|---|
| Issue implementation / root-blocker implementation | `skill_events` with `skill_name=manage-issue`, explicit TYPE + fix/implement/improve + exact ID; exclude verify/plan, plan-only/dry-run invocations. `orchestration_runs` with exact issue ID and `started_at` is evidence of a **pick/attempt**, not passing a readiness gate. This includes ll-auto, ll-parallel and ll-sprint per-issue picks. |
| Issue refinement / root-blocker refinement | Exact `action_key` from the displayed step and explicit target in the corresponding format-issue, verify-issues, confidence-check, refine-issue or ready-issue skill. An arbitrary refinement of the same issue does not accept a different displayed operation. |
| Loop run | `loop_runs` with exact loop name and a valid `started_at`, but usable only once its completion row is observable (`ended_at <= as_of`). It is delayed evidence of a run, **not a live start producer**. A separately verified live `loop_start` adapter may be used only if its loop identity and persistence path have focused tests. |
| Sprint / scoped scan | No automatic adapter in this issue. FEAT-3713 adds only producers whose exact target/scope can be verified; otherwise acceptance remains unknown and explicit accept still works. |

Backfilled skills lack reliable arrival timestamps. Mark them `event_time_proxy`; do not claim point-in-time knowledge from `ts` alone. Loop completion can provide a bounded availability time. Match only evidence available by `as_of`, with a documented proxy limitation when true availability is absent. Derivation is observational, and later ingestion can change historical attribution; it is not used as a feature by FEAT-3712.

### Acceptance attribution

- Match the same `action_key`, namespaced target and proven semantic arguments/fingerprint, with `shown.ts <= event_at <= shown.ts + match_window`; default `match_window=7 days`, configured as a positive number of days. A missing parameter fingerprint cannot match a parameterized offer. Explicit acceptance is independent of this automatic window.
- A producer credits **one** most recent eligible shown row across compatible verbs for that operation/target; timestamp ties break by `rec_id`. Repeated displays do not allow one invocation to accept every displayed copy. Coalesce duplicate evidence with the same semantic identity before matching; test hook/backfill duplicates without relying on row IDs.
- Return accepted evidence time/provenance plus unknown reasons (pending window, window elapsed without evidence, unavailable capture, ambiguous target). Expiry never produces ignored: an enabled producer is not proof capture was complete.
- Outcome (`issue done`, successful loop completion, etc.) is a separate concept; do not add an outcome-learning subsystem here.
- The existing cli_event_context records zero when a wrapped handler **returns** a nonzero integer normally; it only detects exceptions. Its historical exit_code cannot certify success. Any CLI adapter must label invocation evidence with outcome unknown unless a verified producer supplies a trustworthy result; do not repair this unrelated producer globally inside this issue.
- `accept REC_ID` is project-scoped and can run in another session. Require an existing shown row, reject unknown IDs, retain the immutable shown target/action, and make retries idempotent. Return success for an already accepted ID. Unavailable persistence is an explicit failure for this deliberate mutation, not a false success.

`feedback REC_ID` loads the immutable shown row, acknowledgements and relevant competing offers/producers through the shared strict reader, then renders derive_acceptance's result with as_of, availability and reason/provenance. It never records another display, changes pressure, creates/migrates a store or writes remote cache/marker files. Exit 0 for a found row (including unknown evidence), 1 for an unknown ID, 2 for usage/config or unavailable lookup storage; missing optional producer data still permits a found row with unknown attribution. Add a generated feedback JSON Schema/fixture alongside the core output schema. This single-ID inspection is the attribution consumer; aggregate acceptance dashboards/metrics are outside scope.

### Activity pressure (opt-in)

Add consumed keyed settings `next.recording.enabled` (default true, also respecting `analytics.enabled` for automatic writes), `next.acceptance.match_window_days=7`, `next.pressure.enabled=false`, and `next.pressure.cap_days=14`. Validate at the next consumer with the same merge/reset/error policy as FEAT-3561.

Automatic recording also honors the existing `LL_ANALYTICS_CAPTURE=0/false/off` kill switch and `analytics.capture.cli_commands` allowlist for ll-next; explicit next settings cannot force-enable it past an analytics exclusion. Report the disabling reason before opening a write connection. `accept` is a deliberate user-requested acknowledgement, independent of automatic capture gates, and still requires actual storage success; document that distinction. Read-only pressure/feedback remain available when automatic recording is disabled.

For a bucket with known activity time `t_v <= as_of`, use `pressure_v = min(max((as_of - t_v).total_seconds() / 86400, 0), cap_days) / cap_days`. `t_v` is the latest qualified producer's **available evidence time**, or an explicit acknowledgement of a recorded recommendation in that bucket. Activity does not need a preceding shown row. No qualified activity time or no supported adapter yields `pressure=null`, ordered as zero with a diagnostic; there is no invented cold-start epoch. Available automatic evidence is positive evidence even when capture coverage cannot be proved complete.

The activity-bucket map is explicit: manage-issue implementation and per-issue orchestration picks → implement-issue; the named refinement operations → refine-issue; qualified loop runs → run-loop; the later exact named sprint/scoped scan adapters → their own verbs. A producer credits one activity bucket, rather than resetting every compatible recommendation verb. `resolve-blocker` describes purpose, not a distinct execution producer: its pressure uses explicit acknowledgements only until historical blocker intent is independently observable. Do not infer that purpose from today's dependency graph or a displayed row. Automatic recommendation attribution can still credit a resolve-blocker offer with its matching underlying operation; that attribution does not supply an automatic blocker-pressure reset.

Sort nonempty buckets by pressure descending (null treated as zero), ties by canonical verb order. Visit each bucket once per round; retain within-bucket scoring, caps, duplicate refill and alternate-action annotations. Do not greedily drain a high-pressure bucket. Default remains round-robin; explain/output names the actual selection policy.

Display never changes `t_v`. Repeated runs at a fixed clock, JSON/text surfaces and `--no-record` have identical selection. `--type` only filters displayed buckets; it writes no counters or last-seen timestamps for excluded buckets. Natural elapsed time still changes pressure in all buckets, so the old claim that filtering prevents excluded buckets from accruing wall-clock age is removed. Record activity/explicit acceptance as the reset evidence, not the time the next display query happens.

### Schema, recording and failure behavior

- `recommendation_events`: unique `event_id` UUID, `rec_id` UUID, `kind` (`shown`/`accepted_explicit`), `ts`, nullable `session_id`, `invocation_id`, `as_of`, rank, action type/key/fingerprint, target/key and the invocation's requested top/type filter/surface. Retain the offered semantic fingerprint immutably so later parameter changes cannot alter acceptance matching. `UNIQUE(rec_id, kind)` makes explicit-accept retries idempotent. Add bounded-query indexes for shown IDs, operation/target/fingerprint/time and kind/time. No mutable acceptance column.
- Assign shown UUIDs once per invocation. Persist selected rows in one atomic batch **before** rendering so output can say `recording=recorded|disabled|unavailable(reason)` and expose IDs only for rows actually saved. Treat shown as an offered output, not proof a person read it. No retry IDs may duplicate offers after an ambiguous remote commit.
- Use the shared `schema._MIGRATIONS` for both local and remote DDL, update `schema_manifest.json` through its existing generation path, and wire writers/queries through `session_store/__init__.py` imports and `__all__`. `remote_schema.py` already consumes that list: no second migration definition. Remote open never migrates; an old remote version reports the existing migrate hint and skips automatic recording.
- Keep this non-reconstructible table outside `_REBUILD_TABLES` **and** recommendation search rows outside `_REBUILD_SEARCH_KINDS`. Prefer a kindless table until a real search/recent consumer is included; declare the classification explicitly so the manifest/kind coverage gate passes. A rebuild test proves shown/accept rows survive. Adding an excluded table must not alter the derivation digest/version; coordinate around BUG-3715's existing rebuild edits rather than regenerating its fingerprint by reflex. ENH-3678 and ENH-3679 are already done and provide reusable safety seams.
- Pass `busy_timeout_ms=250` explicitly to recommendation writes; ENH-3679 only applies it automatically to `cli_event_context`. Bound the whole optional history read/write stage to 1 second per invocation, including setup, local query execution and remote network requests; a SQLite lock timeout alone is insufficient. Stop scheduling further optional work when the deadline expires. Reuse backend error translation; no raw sqlite connection or silently unbounded remote retry.
- Implement the missing **shared monotonic deadline plumbing** in `session_store/backend.py`, `libsql.py` and `hrana.py`, not just a deadline argument on the arena wrapper. LibsqlBackend.connect_readonly currently ignores timeout, and each Hrana request starts a new budget. Carry the remaining total budget through cold access verification, queries, transactions and response reads; SQLite needs a query progress/cancellation bound as well as a remaining-budget lock timeout. Reuse ENH-3682's seam if landed; otherwise coordinate the common primitive while keeping its prepatch/cache behavior independent. Do not use connect_telemetry on read-only paths: its file-backed verification/unreachable caches violate the no-write contract. No background worker may continue a write after the command reports a timeout. Test a cold slow verification followed by a stalled query/write, with request counts and a documented small scheduling tolerance.
- Automatic write failure leaves recommendation content/order and exit code intact, with a recording diagnostic and no usable accept IDs. Read failure leaves pure recommendations available and falls back to core bucket order. `--no-record` may read history but cannot create files or migrate anything. `--help` and usage/config errors do no history work. Deliberate accept returns exit 0 on persistence success/idempotent replay, 1 for unknown ID, 2 for usage/config/storage failure.
- No recommendation pruning/retention policy in v1; indexes bound queries and tests prohibit full-store scans. Preserve rows through rebuild. Document growth rather than silently deleting feedback.

Capture `as_of` once for feature/history reads, but stamp shown.ts at the successful bounded write attempt, immediately before emission. A long core scan must not make a pick that occurred before the offer eligible for acceptance merely because it happened after feature as_of. Keep both timestamps and test that intervening work does not accept a not-yet-offered row. A sent remote commit whose acknowledgement times out is `recording=unavailable(commit_unknown)` with no exposed IDs; do not retry it with new UUIDs. Deliberate acknowledgement retries reuse the same `(rec_id, kind)` identity and resolve the stored outcome idempotently.

## Integration Map

### Files to Modify

- `session_store/schema.py`, `schema_manifest.json`, `writers.py`, `queries.py`, `__init__.py`; backend/remote migration tests where needed, using shared migrations rather than duplicated remote DDL.
- New read-only snapshot/producer adapters shared by the next CLI and FEAT-3713; FEAT-3561 snapshot extension, selection bucket-order input, output Schemas and CLI recording/accept/feedback modes.
- `session_store/{backend,libsql,hrana}.py` for an enforceable total-deadline seam; coordinate with ENH-3682 without importing its cache-writing behavior into strict reads.
- `config/{features,core,__init__}.py`, `config-schema.json`; `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`.
- Focused migration/rebuild preservation, backend deadline, producer/attribution, concurrency/idempotency and deterministic pressure tests.

## Program Design

### Types

- Immutable `HistorySnapshot(availability_by_source, producers, recommendations, diagnostics)` and `ProducerEvidence(key, action_key, target_key, action_fingerprint, activity_bucket, event_at, available_at, availability_basis, provenance)`.
- `RecommendationEvent` with the schema fields above; `AcceptanceResult(state, evidence_key, accepted_at, provenance, reason)`, state `accepted` or `unknown`.

### Signatures

- `read_history_snapshot(store, *, as_of: datetime, deadline: float) -> HistorySnapshot` — read-only and fail-soft.
- `derive_acceptance(shown, acknowledgements, producers, *, as_of: datetime, window: timedelta) -> Mapping[str, AcceptanceResult]` — pure, deterministic one-producer/one-offer attribution.
- `bucket_pressure(history: HistorySnapshot, *, as_of: datetime, cap_days: float) -> Mapping[str, float | None]` — derives activity ages independently of display counts.
- `record_shown(events, *, deadline: float) -> RecordingResult`; `record_accepted(rec_id, *, deadline: float) -> AcceptanceWriteResult` — bounded writes, idempotent identities.

### Call Path

CLI → pure project snapshot → optional read-only history snapshot → generators/scoring → configured bucket order → select → bounded atomic record (unless disabled) → render recording status/IDs. Accept → resolve shown ID in current project → append acknowledgement → report persistence result.

Feedback → strict read-only shown lookup plus bounded relevant competition/evidence snapshot → pure derive_acceptance → human/JSON result; no write-capable context wrapper.

## Implementation Steps

1. Implement after FEAT-3561; pin event/output/config identities and producer fixtures, including the existing writers' actual timing.
2. Add the shared read-only history reader and pure evidence/acceptance adapters; verify deadline/degradation behavior before enabling recording.
3. Add one local/remote migration, indexes, classification/exports and rebuild-preservation tests; verify derivation fingerprint unchanged.
4. Add recording, accept, single-ID feedback inspection and no-record semantics, then opt-in pressure as bucket ordering only.
5. Update docs and tests; keep default round-robin and no-record/explain behavior deterministic.

## Scope Boundaries

- **In scope:** append-only events, bounded shared history snapshot, observed/explicit acceptance, opt-in activity pressure, migration/exports/config/docs.
- **Out of scope:** ignored/rejection labels, causal attribution, learned weights, new execution telemetry producers, retention/pruning, default-on pressure, execute, pressure backtesting.

## Impact

- **Priority:** P3
- **Effort:** Medium–Large — one table, shared bounded reader, producer adapters and CLI/config wiring.
- **Risk:** Medium — incomplete capture and proxy timestamps limit observational claims; default-off pressure and unknown states make that limitation explicit.
- **Breaking Change:** No; default selection remains the stateless core policy.

## Use Case

A user sees recorded recommendation IDs and explicitly accepts one from another session. Repeated displays do not manufacture acceptance. After opting into pressure, a recent actual loop/issue invocation can reorder the shorter list even if it was never recommended.

## Acceptance Criteria

- [ ] One additive shared migration and manifest/classification/exports work locally/remotely; claim the next free version, preserve events through rebuild, and leave the ENH-3678 derivation fingerprint/version unchanged.
- [ ] Read-only HistorySnapshot honors resolved backend/project access, never creates/migrates or writes cache/marker files, has indexed bounded queries, per-source availability and tested absent/old-schema/suppressed/locked/remote-timeout degradation. Row-budget saturation cannot yield false exact attribution/activity.
- [ ] Producer adapters validate exact operation/target tokens and reject implicit/truncated references; exclude plan/dry-run invocations and handle delayed completion, dequeue-before-gate semantics, timestamp normalization/limits and deduplication.
- [ ] Attribution is pure and one-producer/one-most-recent-offer, action-aware across compatible verbs, with accepted/unknown reasons only; no fabricated ignored/outcome states.
- [ ] Atomic shown batches expose persisted IDs/status truthfully; accept rejects unknown IDs and is project-scoped, cross-session and concurrency/retry-idempotent, including ambiguous remote commits.
- [ ] Single-ID feedback is a documented read-only attribution consumer with human/JSON Schema and exit-code tests; it considers relevant competing offers, and unknown evidence remains unknown. Parameter changes, 200-character/50-token capture boundaries, hidden flags and pre-offer work cannot fabricate acceptance.
- [ ] Pressure is opt-in, activity-based, capped and deterministic; the tested activity-bucket map never infers blocker purpose or sprint identity from per-issue work. Missing history falls back, fixed-clock repeated surfaces/filter/no-record runs do not change it, and round-robin caps/dedup remain intact.
- [ ] Automatic writes explicitly use the short lock timeout and the entire optional stage has a tested 1-second deadline; unavailable storage never changes recommendation content/order/exit code. Deliberate accept reports storage failure.
- [ ] No-record/explain/help/errors write nothing; consumed config/output Schema/docs and focused tests pass; `python -m pytest scripts/tests/` passes.
- [ ] Automatic capture respects analytics.enabled, LL_ANALYTICS_CAPTURE and the cli_commands allowlist; deliberate accept behavior is documented independently. Cold remote verification/query/write share one deadline, no timed-out task continues writing, and existing readers retain their default behavior.

## Related Key Documentation

- `docs/guides/HISTORY_SESSION_GUIDE.md` — backend, schema migration and telemetry degradation.
- `docs/reference/API.md` — writers/queries and backend chokepoint.
- `docs/reference/CONFIGURATION.md` and `docs/reference/CLI.md` — next settings, recording and accept contract.

## Review Notes

- 2026-10-03: Opus recommended deferring pressure because producers are observational. Retained it as opt-in activity ordering, kept default round-robin, removed ignored labels, and made reader ownership/FEAT-3713 dependency explicit. Corrected completion-time loop evidence, exact matching, record IDs, rebuild membership and bounded backend behavior.
- 2026-10-03: Follow-up Opus consult gave conditional GO (confidence 0.76). Added enforceable backend deadlines, per-source availability, capture opt-outs/truncation boundaries, parameter-aware immutable offers, truthful offer timing and strict no-cache-write reads. Kept observational attribution with a minimal single-ID feedback consumer; Opus preferred deferral but identified this alternative in its dissent. Explicit accept remains a deliberate write independent of automatic capture gates.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
