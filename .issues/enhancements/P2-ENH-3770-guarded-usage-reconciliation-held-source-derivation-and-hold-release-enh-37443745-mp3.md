---
id: ENH-3770
type: ENH
title: Guarded usage reconciliation, held-source derivation and hold release (ENH-3744/3745
  MP3)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T16:52:13Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
blocked_by:
- ENH-3744
- ENH-3745
- ENH-3747
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3746
- ENH-3751
- ENH-3747
testable: true
---

# ENH-3770: Guarded usage reconciliation, held-source derivation and hold release (ENH-3744/3745 MP3)

## Summary

Replace the destructive delete-then-replay paths (reset, per-Codex-source catch-up, `rebuild`, parser refresh) with guarded, source-scoped reconciliation against committed usage observations; resume safe additive derivation on held sources; revisit outstanding candidates below the scan high-water; and release conservation holds only when proved safe. This is merge point MP3 of the ENH-3744/3745 Delivery Plan, split out of ENH-3744 on 2026-10-07 so MP1 (checkpoint safety, pure proof, prune veto) and MP2 (source-local completion storage) can be scored and landed first. Read **ENH-3744 § Delivery Plan (decided 2026-10-07)** for the fail-closed non-regression definition and the hazards that bind this issue.

## Current Behavior

On `main`, reset/Codex catch-up and `rebuild` delete unheld observations before replay (`_derive_usage_incremental_conn`, `rebuild`); `refresh_raw_events` deletes linked observations before committing its separate `needs_rebuild` phase. A temporary-store unchanged Claude rebuild replaced row IDs and changed deliberately stored historical costs. `_backfill_usage_events` skips entire held sources, and the incremental `max_id == checkpoint` early return misses outstanding work. `_write_host_usage_observation` uses raw-ID ingestion order to update Claude snapshots and computes cost before checking unchanged replay; neither order nor a high-water checkpoint proves native source order or safe replacement. Codex qualification can legitimately change when a later `task_complete` supplies missing context.

## Expected Behavior

- Keep protected observations unchanged unless a safe mutation is proved. Semantically unchanged or older replay is an idempotent no-op, including row identity, stored cost, timestamps and provenance. A genuinely newer compatible native snapshot may update using its stored/native ordering proof; newly proved native context may permit a separate qualification mutation. Equal numeric values alone do not establish a semantic no-op; path aliases, larger raw IDs and equal values/timestamps alone prove neither generation nor order.
- Allow proved-distinct new requests on a source that still has conservation protection. Preserve old protected rows and the hold while unrelated new appends derive safely; hold removal is not a prerequisite for safe additive work. Unkeyed/wildcard legacy populations may prevent proving distinctness and stay conservative.

## Impact

- **Priority**: P2 — completes the retention-safe derive path after MP1/MP2.
- **Effort**: Large — guarded reconciliation across reset, catch-up, rebuild, parser refresh and hold release.
- **Risk**: High — a false mutation or hold-release proof can lose or double-count usage; destructive paths are replaced.
- **Breaking Change**: No

## Proposed Solution

Consume ENH-3744's pure `inspect_usage_candidates` proof and ENH-3745's source-local pending/completion storage to replace broad usage delete/reinsert with source-scoped reconciliation: compare with committed observations before any deletion, preserve unchanged rows (identity, stored cost, timestamps, provenance), mutate only on proved newer native evidence, and release holds only on proved reconstructibility.

## Program Design

### Signatures

- `backfill_usage_incremental(db: Path | str = DEFAULT_DB_PATH) -> int` — keep the public contract; `rebuild(...)`, `refresh_usage_source(...)` and `usage_refresh.refresh_raw_events(...)` keep their return payloads.
- `_derive_usage_incremental_conn(conn: sqlite3.Connection) -> int` — replace the unconditional usage delete-then-replay with source-scoped reconciliation under the caller's `BEGIN IMMEDIATE`.
- Reuse `inspect_usage_candidates` (ENH-3744) and `read_source_derive_completion` / the pending-retry bound (ENH-3745); no new pure proof types and no competing migration here.

### Call Path

`backfill_usage_incremental` → `_derive_usage_incremental_conn` → `inspect_usage_candidates` → guarded `_backfill_usage_events` reconciliation → source completion (ENH-3745). `rebuild` and `refresh_usage_source` consume the same safe-replay decisions; `usage_refresh.refresh_raw_events` protects observations across its two-phase workflow.

### Decision Rules

- Evaluate candidates against the committed observations **before** any reset, per-Codex-source catch-up, rebuild or parser-refresh deletion. Replace broad usage delete/reinsert with source-scoped reconciliation; unchanged unheld rows need the same cost/identity preservation as held rows. A prospective insert/replace is not committed representation. `prune` consumes proof and writes protection only; it does not derive usage or invoke pricing. Dry-run uses the same proof/context plan in one read snapshot and writes nothing.
- Existing `source_line_no`/`source_ordinal`, verified native stream/session and compatible committed source-generation witnesses may support ordering. A raw ID orders ingestion only. If generation/order cannot be proved after pruning, preserve the retained observation and report mutation unavailable; do not invent compatibility or accept rollback as a risk. ENH-3745 owns a minimal durable witness if existing state is insufficient.
- **[Phase 2 for held/pruned and beyond-gap cases — see Delivery Plan; MP3 keeps today's full-raw-source Codex requalification]** Permit bounded context-only audit-to-measured promotion when newly proved compatible native evidence completes current-producer qualification, such as Codex `task_complete` closing an already represented request. This is not unchanged replay or automatic legacy promotion. Require every relevant request-span/model/closure/conflict/dedup dependency to be proved; a gap inside required context blocks promotion, while an unrelated earlier gap may leave the successful source prefix behind a safely qualified request. Preserve request identity, numeric components, value-supplying position/timestamp and any stored historical cost; update only proved qualification facts and their dependency frontier. Pricing is allowed only for a newly proved eligible unpriced observation under existing semantics. Missing/replayed context or identical duplicate copies grant no permission to promote or downgrade. Demotion, conflicts and changed values remain outside this context-only transition.
- Check for unchanged/older/protected replay before calling pricing. No replay or rebuild reprices an unchanged retained observation. New or proved-changed requests follow existing pricing semantics; stored historic costs are not recalculated as a side effect of proof.
- A proved value replacement atomically updates the applied-value source/generation/native position with its numeric values; a context-only mutation updates its actual qualification dependency frontier without pretending that a newer numeric snapshot supplied the values. No-op replay preserves both witnesses along with cost/metadata. A Codex dedup survivor retains its actual supplying source/position; another copy cannot substitute a convenient selected-source boundary.
- Retry outstanding held candidates below the global scan high-water, including when raw max equals it, using ENH-3745's generation-scoped source pending/retry bound. This issue owns candidate iteration/retry; ENH-3745 owns scan validation and source-local completion, consuming these outcomes. Raw-ID bounds schedule retries only; native context/order still decides recognition and mutation.
- Hold release requires all protected observations safely reconstructible or still explicitly protected by equivalent retained guards, and every pending candidate resolved. Preserving an observation is not permission to drop its protection. Per-source release cannot clear a wildcard population hold or another source's guards.
- Compute proof, protect/replace rows, retain context, delete eligible raw and update hold/progress outcomes in the existing `BEGIN IMMEDIATE` transaction. Forced failure rolls everything back. Retained evidence cannot retrospectively certify inventories of older already-pruned history.
- Preserve the public two-phase parser-refresh workflow: raw replacement and a scoped refresh-pending disposition commit together while existing observations and truthful historical boundaries remain protected. A failure before that commit rolls everything back; a crash/failure before the later derive leaves old usage present and pending work durable. Only proved reconciliation can release those guards. Preserve the existing verified original-source refresh's qualification recovery; ordinary retained replay cannot acquire missing ingest-time contracts by itself. ENH-3745 owns pending/invalidation state, not a second global checkpoint reset.

### Landing Mechanics, Interactions and Constraints

- **ENH-3751 (done 2026-10-06) changed the refresh seams this issue edits.** `usage_refresh.refresh_raw_events` now compares canonical (history-sanitized) payloads in both stored columns, refuses per-line metadata/contract changes (`source_metadata_changed`, `usage_contract_changed`, `existing_payload_not_preserved`, `parser_changed_during_refresh`) and promotes a NULL `usage_contract` monotonically — a persisted marker is never changed. `_refresh_codex_usage_source` first-cursor certification uses the same canonical comparison. Preserve all of this; "the existing verified original-source refresh's qualification recovery" above is that NULL→marker promotion, distinct from the context-only qualification promotion on `usage_events` specified here. The retained payloads the proof reads are sanitized (and legacy rows may be plaintext, or rewritten later by `ll-session redact`): every identity key the proof relies on must be protected by `pii._protocol_rules` for the host/event type (EPIC-3562 § Shared Delivery Ownership, sanitizer identity contract), because a rewrite of an unprotected identity would read as `missing`/`unprovable`. Treat an unregistered identity path as `unprovable`, never as an absent candidate.
- **ENH-3747 coupling (verified in `lifecycle._derive_usage_incremental_conn` and `rebuild`).** Reset/catch-up delete only unheld non-live usage rows but wipe every `kind = 'usage'` search row, and `rebuild` wipes the whole kind; replay re-indexes only what it re-derives. Today only held and live observations lose search entries. Once reconciliation stops re-deriving unchanged unheld observations, every preserved observation does. Land ENH-3747 first, or in the same change with scope "every surviving committed usage observation that replay does not re-derive", and add a search-survival control to this issue's reset/catch-up/rebuild tests.

- **Prerequisites:** MP0 (ENH-3747) must be merged first; MP1 and MP2 supply the proof and storage. Do not start before ENH-3744 and ENH-3745 are `done`.
- **Version bump:** the only merge point allowed to bump `_USAGE_DERIVE_VERSION`; re-justify it against what a mismatch replay may mutate once reconciliation exists — likely unnecessary because mismatch replay becomes non-destructive. No usage-only change bumps `REBUILD_DERIVE_VERSION` or its non-usage fingerprint (`test_enh3678`).
- **Unique-index hazard:** `usage_events.source_raw_event_id` is unique; any new replay path must not plain-INSERT an already-linked raw row. Reconciliation is what makes that safe.
- **Codex requalification regression guard:** keep today's per-Codex-source catch-up requalification for fully retained, unheld sources (a later `task_complete` in a later append). Context-only promotion for held/pruned or beyond-gap requests is Phase 2, not a gate.
- **Safe additive held-source work** needs ENH-3745's generation-scoped pending/retry bound committed in the same transaction as the scan high-water.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — safe observation insert/replace/no-op, held-source additive derivation without clearing protection, unchanged-replay no-op before pricing.
- `scripts/little_loops/session_store/lifecycle.py` — pre-deletion comparison in reset/Codex catch-up/`rebuild`, held-candidate iteration, atomic hold release. Keep the non-usage rebuild fingerprint boundary intact.
- `scripts/little_loops/session_store/usage_refresh.py` — reuse safe preservation/replacement decisions before raw replacement; protect observations across the two-phase workflow. Preserve ENH-3751's canonical-payload refusals and NULL→marker promotion.

### Dependent Files

- ENH-3744 (proof, prune veto), ENH-3745 (pending/completion storage), ENH-3747 (search survival), ENH-3732 / ENH-3746 (readers; unblocked by MP2, not by this issue).

### Tests

Extend `scripts/tests/test_bug3736_usage_replay_holds.py`, `test_session_store_incremental_usage.py` and `test_session_store_usage_refresh.py`.

Run unchanged unheld Claude/Codex observations through all reset/catch-up/rebuild seams with pricing patched to raise; assert stable row IDs, costs and metadata. In `test_session_store_usage_refresh.py`, inject pre-commit replacement failure and post-commit/pre-derive crash, then retry after restart; old usage survives and pending guards remain until proved reconciliation. Separate unchanged verified refresh from supported qualification recovery. Use the Codex fixture's first four lines, then append only its duplicate notification/turn closure: qualify the same request once from actual new context, preserve counts/value position, advance the context frontier and prove rollback/no-op replay. Contrast a missing dependency within that request span (no promotion) with an unrelated earlier gap (safe promotion, but ENH-3746 cannot publish the earlier boundary as the changed figure's as-of). Exercise source-admission failures through ENH-3745's bounded evidence, production prune dry-run/actual count and reason parity with no pricing calls, and the existing non-usage rebuild-fingerprint gate.

Add a search-survival control to the reset/catch-up/rebuild tests (every surviving committed usage observation that replay does not re-derive keeps its search row). Keep new tests fixture-sized and subprocess-free; no test may shell out to a long-running command (xdist worker-timeout hazard).

### Documentation

Update the usage/rebuild/refresh contracts in `docs/reference/API.md`, retention diagnostics in `docs/reference/CLI.md` and Stage 1 hold limitations in `docs/guides/HISTORY_SESSION_GUIDE.md`: safe additive held-source work, preserved historical costs and recoverable parser-refresh pending state. Keep internal native keys/witnesses out of end-user diagnostics.

## Acceptance Criteria

- [ ] A newer retained Claude snapshot cannot be rolled back by an older surviving or re-ingested native position with a larger raw ID. Same-path rotation/restore and alias controls do not manufacture compatibility. Repeated unchanged replay leaves cost/metadata untouched even when pricing is patched to fail/change.
- [ ] Reset, Codex catch-up, full rebuild and verified parser refresh compare with existing usage before mutation; unchanged unheld/held row identities and stored costs survive. A crash between committed raw refresh and later derive leaves protected observations and durable pending evidence, never a lost figure or falsely complete source.
- [ ] Fully retained, unheld Codex sources keep today's requalification when a later append supplies the closure (no regression through MP3's reconciliation; counts and stored cost intact). **Phase 2:** for held/pruned or beyond-gap requests, newly proved compatible closure may qualify an existing audit request without a newer token snapshot or second observation, with the qualification frontier changing atomically; until then those rows stay audit. Equal values or ordinary legacy replay alone never promote qualification.
- [ ] Proved-distinct appends derive while older conservation protection remains; ambiguous/unkeyed/wildcard legacy populations cannot be bypassed. Recovery revisits held candidates below an advanced/equal checkpoint without double counting.
- [ ] Protection, safe mutation, prune deletion and source-progress outcomes commit atomically; forced failures preserve rows, guards and proof. Source release cannot clear another source or wildcard protections.
- [ ] **[Phase 2]** Applied-value source/generation/native positions change atomically on actual replacements and survive no-op replay. ENH-3746 can distinguish a row updated beyond the completed prefix and a dedup survivor supplied by another source without reopening native files or exporting internal identities.
- [ ] A proved-newer native snapshot is the only thing that mutates a retained observation's values; unchanged/older replay leaves row ID, cost, timestamps and provenance untouched even when pricing is patched to raise.
- [ ] Search rows survive reset/catch-up/rebuild for every preserved observation.
- [ ] `python -m pytest scripts/tests/` exits 0 with no `_USAGE_DERIVE_VERSION` bump unless re-justified in this issue's Resolution, and `test_enh3678` unchanged.

## Implementation Steps

1. Confirm ENH-3747, ENH-3744 and ENH-3745 are done; re-run `/ll:confidence-check` for this scope.
2. Reconcile in `_derive_usage_incremental_conn` first (reset and Codex catch-up), proving unchanged rows are preserved with pricing patched to raise.
3. Extend to `rebuild`, then to the two-phase parser refresh (pending protection, crash-between-phases controls).
4. Add below-checkpoint held retries and per-source hold release; then the version-bump decision; then the full local suite.

## Scope Boundaries

No candidate proof or prune veto (ENH-3744), source-completion/boundary storage (ENH-3745), search restoration (ENH-3747), reader admission (ENH-3746), legacy promotion, repricing of retained observations, or Phase 2 items (held/pruned context-only promotion with its qualification frontier, digest continuity, applied-value as-of witness).

## Status

**Open** | Created: 2026-10-07 | Priority: P2

## Session Log

- Split from ENH-3744 - 2026-10-07 - Moved the reconciliation, held-source derivation, hold-release and parser-refresh protection content out of ENH-3744 (Decision Rules, ACs, tests, MP3 step) at the user's direction, after `/ll:advise` (Opus 0.74) sliced the ENH-3744/3745 delivery. No implementation or confidence score claimed.
