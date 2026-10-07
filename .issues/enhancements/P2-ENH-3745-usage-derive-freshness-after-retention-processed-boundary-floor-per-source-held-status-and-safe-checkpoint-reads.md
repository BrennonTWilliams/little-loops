---
id: ENH-3745
type: ENH
title: 'Usage derive freshness after retention: processed-boundary floor, per-source
  held status and safe checkpoint reads'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:34Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
blocked_by:
- BUG-3736
- ENH-3744
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3744
- ENH-3746
- ENH-3747
- ENH-3751
- ENH-3770
testable: true
---

# ENH-3745: Usage derive freshness after retention: processed-boundary floor, per-source held status and safe checkpoint reads

## Summary

Preserve validated scan progress after retention, diagnose malformed metadata safely, and publish source freshness from source-local successful derivation. Keep ingestion and derived boundaries separate so skipped work cannot overwrite historical proof. Own the shared source pending/completion and minimal generation/dependency storage consumed by readers and ENH-3770. Land after ENH-3744's pure candidate proof and prune veto; ENH-3770 then implements reconciliation, held-source additive derivation, below-checkpoint retries and parser-refresh preservation. Each issue lands and passes the local suite independently.

## Current Behavior

On inspected `main`, `_set_usage_derive_checkpoint` (`scripts/little_loops/session_store/lifecycle.py:1307`) stamps surviving `MAX(raw_events.id)` even after prune/rebuild. `_derive_usage_incremental_conn` (`:1321`) converts metadata before checking its version and treats max-below-checkpoint as a destructive replay trigger. The same branch initializes a new store; simply replacing every missing checkpoint with skip would break first-enable derivation (`scripts/tests/test_session_store_incremental_usage.py:81`). Both cursor writers publish a complete ingestion boundary even when holds skipped usage; Codex's unchanged-size/mtime fast path (`scripts/little_loops/session_store/lifecycle.py:1437`) bypasses derive-version checks.

Claude refresh advances past malformed/non-object complete lines (`scripts/little_loops/session_store/lifecycle.py:1634`); Codex silently skips malformed JSON/non-objects in `scripts/little_loops/session_store/sessions.py:1011`. Codex also opens strict UTF-8 (`:1001`), so stream decoding can raise before the JSON handler runs. A sanitizer refusal rolls back the entire refresh/backfill transaction, leaving no durable diagnostic. `usage_source_freshness` returns `source_untracked` immediately when no cursor exists (`scripts/little_loops/session_store/lifecycle.py:1752`) and performs unguarded numeric conversions outside its database-read handler.

The 64-byte tail witness does not prove an unchanged historical prefix. `rebuild` deletes/replays observations before its stamping call; checkpoint changes alone cannot preserve their row identity/cost. `refresh_raw_events` deletes linked usage/cursors and global progress before committing a separate `needs_rebuild` phase. Those reconciliation/preservation changes belong to ENH-3770, not this issue's implementation gate.

## Expected Behavior

- Retention cannot lower a validated same-version scan floor or trigger destructive replay solely because surviving raw max fell. Allocation sequence, surviving max and retained usage are never positive processing proof.
- A pristine/live-only store can establish initial progress without deleting anything. Missing, malformed, contradictory or version-changed proof in an established store produces bounded incomplete diagnostics and preserves usage, holds and prior metadata until protected recovery is available.
- New semantic completion requires both complete acquisition of the certified native range and ENH-3744's correspondence proof against committed observations. Represented candidates and recognized benign/terminal omissions can complete; skipped/unrepresented work cannot.
- Fully acquired, represented sources can publish positive completion in this issue. New usage on a held source that today's writer skips stays pending until ENH-3770; this issue does not claim safe additive held-source derivation. An unrelated completed source can remain fresh.
- Ingestion may advance while derivation is incomplete. Keep ingestion offset/line/stat/tail separately from the last successful derived boundary/version/publication time. Preserve that older internal boundary; an absent/unproved boundary remains unknown as-of.
- Durable scoped pending/failure state survives restart and retention. A sanitizer refusal preserves ingestion rollback while recording a content-free diagnostic through a separately guarded failure-only transaction, including when no cursor exists.
- Caller-owned committed reads can obtain admission, figures and source proof in one revision. External source comparisons cannot manufacture a fresh zero or a newer boundary for older figures.

## Impact

- **Priority**: P2 — processing/freshness proof diverges after retention.
- **Effort**: Medium-large — checkpoint guards, source storage, acquisition accounting and reader seam.
- **Risk**: Medium-high — a false boundary can label incomplete figures fresh; validate both cursor writers and every local ingestion seam.
- **Breaking Change**: No public payload/return-type break; optional reader keyword and append-only internal storage. Incomplete refresh status must be truthful rather than an unconditional `complete`.

## Proposed Solution

Consume ENH-3744's pure proof, validate checkpoint state before derive decisions/publication, preserve a justified floor, and persist source-local pending/completion separately from ingestion. Factor pure retained-state completion reads for quality and allow freshness to reuse a caller's pinned read connection. Supply ENH-3770 with shared pending state and minimal observation dependency witnesses; it owns reconciliation and mutation.

## Program Design

### Types

Factor `_valid_usage_checkpoint` into one current-version/non-negative-integer rule over committed metadata. Check version before conversion; handle malformed values and SQLite numeric/type edge cases with bounded reasons. Missing is distinct from proved zero. Validate `sqlite_sequence.seq` for `raw_events`: checkpoint above a valid sequence is contradictory; a positive checkpoint with absent/malformed sequence is unprovable. A missing sequence row is compatible with an independently proved zero checkpoint in a genuinely empty raw store, not evidence that a missing checkpoint equals zero. Sequence values may reject a checkpoint but never raise it or prove processing. Validate source offsets, line/raw bounds, version, status and scope too.

Proposed frozen `SourceDeriveCompletion` records bounded source host/session/generation/version scope, status (`complete`, `pending`, `unprovable`), reason, successful boundary, outstanding-work disposition and completion basis (`semantic`, `legacy`, `none`). Only `semantic` basis can report semantic `complete`; `legacy` labels a public compatibility comparison, not proof. Missing semantic state is `unprovable` with a bounded unavailable reason. Internal positions, native identifiers and witness bytes never become shareable reason strings.

Represent ingestion and successful derived witnesses separately. Reuse existing columns only where their meanings remain valid. Persist the minimal missing source scope/version/boundary/pending facts through the next available append-only migration, including `schema_manifest.json`; do not pin an issue-era version (inspected `main` is v61 on 2026-10-07).

Include a source-scoped pending/retry lower bound sufficient for ENH-3770 to revisit unresolved raw below/equal to the scan high-water. It schedules work; it is not native order or processing proof. A rejected source line with no raw row instead records its first unresolved native line/offset and bounded reason. Do not fabricate a raw-ID bound or store malformed bytes. Invalid scope/bounds stay unprovable. Resolved-neighbor pruning and other-source replay preserve these records.

ENH-3770 also consumes unresolved native-conflict disposition scoped to the affected observation/source generation and version. Prefer sufficient retained conflicting raw/audit evidence; where retention could otherwise erase that obligation, use this shared bounded pending storage rather than a separate conflict ledger. Ordinary replay or unrelated closure cannot silently clear conflict qualification invalidation. ENH-3770 owns detecting the conflict and deciding mutations/recovery; this issue supplies the durable scope/helper seam.

**Mandatory handoff, not deferred storage:** provide the minimal current applied-value supplier and consumed qualification-dependency frontier wherever existing observation columns cannot express them, with source/generation/native-position scope and explicit unavailable legacy values. Define writer/update/read helpers for ENH-3770 so values and their actual supplier, or qualification and its actual dependencies, can change atomically. No automatic first-seen-position substitution or legacy certification. This issue defines/persists the interface and tests storage/transaction behavior; ENH-3770 owns mutation decisions. Full aggregate beyond-prefix as-of integration is deferred separately.

Migration starts conservatively: do not seed successful derived boundaries or semantic completion from legacy `complete` ingestion cursors/global checkpoints. Establish new positive state only from actual acquisition and committed candidate proof. ENH-3744 and ENH-3770 add no competing migration or candidate ledger.

### Signatures

- `backfill_usage_incremental(db: Path | str = DEFAULT_DB_PATH) -> int` — keep this contract and existing refresh/rebuild payload shapes. Carry a bounded internal derive disposition so zero inserted rows can be distinguished from skipped/unverified derivation; map it truthfully to refresh status.
- `usage_source_freshness(db: Path | str, source: Path, *, conn: sqlite3.Connection | None = None) -> dict[str, int | str | None]` — gain the optional caller-owned connection. With `conn`, reuse its read transaction; never open, commit, roll back or close another history connection. Keep `status`, `reason`, `as_of` and `as_of_offset` keys/meanings.
- `read_source_derive_completion(conn: sqlite3.Connection, source_path: str, *, schema: str = "main") -> SourceDeriveCompletion` — proposed committed-state reader. Validate generated attached aliases before SQL interpolation; preserve member/source scope. No source stat/parser/pricing/write normalization. ENH-3732 consumes this alongside candidate proof; historical quality qualification does not require a cursor or current source file.

### Call Path

`backfill_usage_incremental` → checkpoint validation/bootstrap decision → existing eligible derivation → ENH-3744 proof + acquisition disposition → atomic scan/pending/completion publication.

`refresh_usage_source` / `_refresh_codex_usage_source` → physical acquisition accounting + existing eligible derivation → distinct ingestion/derived publication → `usage_source_freshness`. Quality uses the pure retained-state read; ENH-3770 later consumes the pending/dependency handoff.

### Decision Rules

- **Checkpoint guard and bootstrap:** guard `_derive_usage_incremental_conn` before the existing delete/reset branch, both cursor publication sites, Codex's unchanged-file fast path and freshness numeric reads. Changes cannot be confined to `_valid_usage_checkpoint`/`_set_usage_derive_checkpoint`. Bootstrap requires both checkpoint keys absent, no prior replay-derived/non-live usage or replay holds, and no prior successful semantic derived boundary; live-only observations and initial ingestion-only tracking/pending/failure do not block it. That ingestion tracking is expected after pristine raw-only backfill, and an acquisition failure still prevents positive source completion. Derive eligible initial acquired work without deleting/repricing any observation, then establish progress from successful work and source proof. Legacy-unlinked observations, a partially missing checkpoint pair and old-version/invalid existing metadata never take this exception. Established missing/version-changed/contradictory proof skips and reports incomplete; protected recovery is ENH-3770.
- Preserve the previously validated same-version floor across retention: after justified scanning use `max(previous same-version floor, scanned retained raw bound)` (the existing `MAX(raw_events.id)` only when that retained range was actually scanned/accounted for). A smaller surviving raw max alone is not a reset. Never restamp invalid progress as current or use allocation high-water to manufacture a floor. Existing rebuild stamping consumes the same safety rule; row/cost-preserving rebuild reconciliation remains ENH-3770.
- Every global scan advance past unresolved work commits its generation/version-scoped pending disposition in the same write transaction. Without durable pending state, do not make skipped candidates unreachable. Publish completion from ENH-3744's outcomes against committed usage, not prospective inserts, cursor status, conservation-hold absence or global progress. ENH-3770 owns iteration of old pending candidates; this issue supplies durable bounds and leaves them pending meanwhile.
- **Completion is a conjunction:** account for every complete physical source line in the claimed prefix before parser skips/normalizer omissions. Persist coverage beginning at offset zero (or establish it by full verified re-acquisition of the entire claimed prefix), then extend only under compatible continuation. Acquisition disposition plus candidate correspondence must cover the same source/version/range. A retained-only candidate pass, first-seen later offset or legacy cursor cannot prove the earlier physical inventory. Distinguish blank/recognized benign records and proved producer terminal omissions from decode/non-object failures. An unterminated tail stays pending. Publish only a successful prefix; do not jump over a missing candidate. Held history without outstanding work is not itself incomplete, but a held append skipped by today's writer is pending until ENH-3770.
- Account for stream decoding before ordinary parser iteration as well as JSON/non-object rejection, including Codex strict UTF-8 failures. Add internal acquisition accounting while keeping ordinary yielded event types/API contracts compatible. Rejected bytes never enter history storage, logs or exception text. Ordinary local `_backfill_raw_events`/`backfill_raw_events` records source-local pending/failure alongside its successful inserts; both refresh paths consult those dispositions.
- **Sanitizer refusal:** preserve ENH-3751's whole-call rollback for Claude/Codex refresh and raw-only backfill; valid rows before/after the refused line remain un-ingested and cursor, derived boundary and checkpoint remain unchanged. Carry only a bounded reason (`sanitization_refused`, allowed refusal code and first refused line/offset), never input bytes. After the ingestion transaction fully rolls back, a diagnostic-only transaction may persist that failure. Compare-and-swap against the failed attempt's source scope/version, prior committed cursor/completion revision and acquisition witness; a concurrent/newer successful refresh invalidates the comparison, so the delayed refusal cannot taint it. This transaction writes only failure evidence and does not publish processing proof. `_backfill_raw_events` never commits its caller's transaction. Keep public refusal/per-source `skipped` behavior, including `refresh_raw_events` keeping earlier sources' commits. If diagnostic persistence fails, preserve rollback and report a bounded incomplete reason; never substitute success.
- Read pending/failure evidence before returning `source_untracked`; a source with no cursor can still report its durable refusal/decode reason with null as-of. Missing boundaries never borrow ingestion or row timestamps. Unknown/unreadable/changed sources cannot fabricate fresh zero.
- **Marker recovery follows its rejection class:** retained derive-pending clears from ENH-3744's resolved committed correspondence and compatible source scope; it need not re-open a native file. Sanitizer refusal did not advance ingestion: clear its marker only when the refused range successfully re-ingests under the still-valid prior cursor/continuation and matching attempt scope; this clears an admission failure, not a historical generation claim. Decode/non-object rejection advanced ingestion past a gap: clear it only after full re-acquisition from offset zero canonically matches the retained prior raw prefix and repairs the failed range; any uncheckable/already-pruned prefix keeps the marker until independent native/retained proof is available. An unterminated-tail disposition clears only when that tail completes and its acquired candidates resolve. Device/inode or matching 64-byte tail alone proves no full historical continuity. Later valid appends, unchanged refresh, retention and a new generation alone cannot clear unresolved failure. Preserve alias lookup spellings without merging ordering scopes from inode equality.
- **Legacy compatibility is a public fallback, not semantic proof:** legacy public freshness may retain today's valid cursor/checkpoint comparison when no new negative evidence exists, avoiding a blanket permanent `unknown`. `read_source_derive_completion` still reports unavailable/unprovable semantic state for that source. Negative evidence overrides the fallback; once semantic tracking exists, invalidation never falls back to legacy trust. The fallback cannot certify a new derived boundary, clear pending/failure, grant mutation/admission, or act as positive completion for quality. First new acquisition/derive work uses the proof path; old-version/invalid state downgrades truthfully. Migration never upgrades the fallback into a certificate.
- A Codex unchanged-file fast path may preserve legacy public compatibility or avoid parsing a proved current complete source, but it cannot ignore pending/failure/version state or publish new proof. If recovery would replay linked/held rows before ENH-3770, leave it incomplete rather than introducing that replay. Unchanged bytes cannot waive semantic recovery.
- Successful raw/usage changes, source proof and scan/pending publication share the existing `BEGIN IMMEDIATE` transaction; forced failures roll them back together. The separate post-rollback failure-only diagnostic transaction is the explicit exception. Wire scoped completion invalidation/refresh-pending into `refresh_raw_events`' current raw replacement transaction now, including existing lookup aliases, so a newly tracked semantic boundary cannot survive replacement as current. This is negative tracking only: leave its existing delete/`needs_rebuild` workflow until ENH-3770 supplies protected reconciliation. Do not add a replay/preservation/rebuild call, hold release, second refresh journal or new mutation algorithm here. ENH-3770 owns stable old observations/boundaries and durable pending behavior across the later guarded derive.
- Caller-owned read transactions pin admission/usage/boundary together. Without `conn`, freshness owns only its read resources. Compare the opened descriptor and resolved path before/after external file checks; detected truncation/swap/change returns unknown. Pure completion/quality readers do not reopen sources, stat, parse, price, migrate or write. A conservation hold alone cannot blanket-reject retained historical qualification.

### Delivery Contract

**Current whole-issue order (supersedes earlier cross-issue MP1/MP2 atomic slices):** ENH-3744 pure proof/prune veto → ENH-3745 checkpoint/storage/positive completion → ENH-3770 reconciliation. ENH-3747 search preservation is ENH-3770's prerequisite. No issue relies on `parallel.epic_branches` or partial completion of another issue to pass its gate.

Within this issue, implement checkpoint guards/bootstrap first, then the append-only storage and acquisition/failure tracking, then proof-driven publication and pure/optional-connection readers. Legacy compatibility remains bounded as specified above; fully acquired/represented sources can acquire new positive proof. Held unrepresented work stays pending. No `_USAGE_DERIVE_VERSION` bump, linked-row replay, protected mutation, or non-usage rebuild-fingerprint change is introduced.

**Deferred, non-gating:** full-prefix digest continuity; full held/pruned or beyond-gap context-only promotion (ENH-3770); aggregate applied-value/qualification beyond-prefix as-of integration (ENH-3746). Minimal value/qualification dependency storage is mandatory here. Until aggregate integration proves every contributor lies inside the selected compatible prefix, ENH-3746 publishes figure as-of unknown; it must not borrow a source boundary. Until digest continuity exists, native mutation/marker recovery lacking independent continuity proof stays unavailable/pending. Fresh hashing cannot retroactively certify a pruned historical range.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — validation/bootstrap/actual derive guard, safe stamping, internal disposition, local ingestion pending tracking, both cursor writers/fast paths, failure-only diagnostic transaction and pure/optional-connection reads.
- `scripts/little_loops/session_store/sessions.py` — internal acquisition accounting for physical complete lines and pre-parser decode failures while preserving ordinary event iteration contracts.
- `scripts/little_loops/session_store/schema.py` and `schema_manifest.json` — next append-only migration for separate source completion/pending/failure and minimal dependency witness storage; no automatic legacy certification.
- `scripts/little_loops/session_store/usage_refresh.py` — atomically invalidate tracked source completion and record scoped refresh-pending with current raw replacement, without changing its existing destructive/`needs_rebuild` workflow; ENH-3770 later replaces that workflow.

### Dependent Files and Handoffs

- `scripts/little_loops/session_store/writers.py` — existing derivation remains; ENH-3744 exports pure outcomes, ENH-3770 consumes minimal dependency-update helpers for reconciliation. This issue adds no replay/mutation algorithm.
- ENH-3770 — consumes the scoped refresh-pending/invalidation and diagnostic helpers already wired to replacement; protected two-phase replacement, stable observations/boundaries and reconciliation/crash recovery controls belong there.
- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes pure completion/candidate facts, including attached-member scope and unavailable legacy completion.
- `scripts/little_loops/cli/ctx_stats.py` — ENH-3746 owns admission and threading its pinned connection through freshness; this issue supplies/test-drives the keyword and source facts.

### Tests

Extend `test_session_store_incremental_usage.py`, `test_enh3549_codex_usage_refresh.py`, `test_bug3736_usage_replay_holds.py` and relevant reader/migration suites. Drive real first refresh and raw-only bootstrap with pristine/live-only stores, including initial ingestion pending/failure tracking; a failure does not certify completion. Contrast legacy-unlinked usage, missing established/partially missing metadata, malformed/negative/NULL/non-integer/version-changed proof, positive checkpoint above/missing sequence evidence and proved zero in an empty store without a sequence row. Assert no deletion/restamp from invalid derive, no unconditional cursor/fast-path `complete`, bounded reader diagnostics, preserved same-version floor after production prune/catch-up and safe existing rebuild stamping. Verify `test_enh3678`'s non-usage fingerprint remains unchanged; row identity/cost-preserving rebuild is ENH-3770's test.

Exercise fully acquired/represented positive completion and a held source with skipped new usage remaining pending. Source A pending at raw ID 5 while B scans through 10 keeps its durable bound after restart/resolved-neighbor pruning; B may remain fresh. Fail between pending and scan publication and assert both roll back. Do not require below-checkpoint iteration or safe held additive derivation here.

Append malformed UTF-8/JSON and non-object complete lines to real Claude/Codex fixtures, including a decoder failure before any event yield. Assert durable bounded evidence, no complete/fresh prefix over failure, no rejected bytes in storage/diagnostics and correct blank/benign/partial-tail controls. Test raw-only ingestion and no-cursor failure reads, unchanged Codex old-version/pending/failure state, source loss and descriptor/path swap. A matching 64-byte tail alone cannot prove a repaired decode gap: full re-acquisition from zero must verify retained prior raw, and an unavailable/pruned prefix keeps the marker. Distinguish retained derive-pending resolution without file access, successful unadvanced-cursor refusal re-ingestion without inventing a generation, and tail completion. A later first-seen offset plus retained candidate proof cannot certify the earlier inventory.

For Claude refresh, Codex refresh and raw-only backfill, refuse a sanitizer line after valid lines: ingestion/cursor/checkpoint/derived boundary fully roll back while a diagnostic-only transaction records the bounded reason. Correct the affected range and prove recovery only with compatible continuity. Race a delayed refusal against newer successful refresh and verify the compare-and-swap prevents stale failure publication. Inject diagnostic-write failure without leaking payload bytes or turning rollback into success. Preserve ENH-3751's public refusal behavior.

Test migration preserving legacy public freshness without creating semantic completion or successful derived fields. New negative evidence must downgrade it, and invalidated semantic tracking never falls back to legacy; the fallback cannot clear pending or grant admission/mutation. Test completion basis and zero-origin acquisition coverage. In `test_session_store_usage_refresh.py`, verify source replacement commits scoped pending/invalidation atomically, unrelated source state remains untouched, and failure before commit rolls both back; do not assert observation/boundary preservation across its pre-existing destructive workflow here. Test minimal value/qualification witness and unresolved-conflict disposition round trips, explicit unavailable legacy values and atomic helper rollback; ENH-3770 owns actual replacement/promotion/conflict controls. On local/query-only attached reads, forbid stat/parse/pricing/writes; optional-connection freshness must preserve caller ownership and revision under a concurrent derive.

### Documentation

Update `docs/reference/API.md`, `docs/reference/CLI.md` and `docs/guides/HISTORY_SESSION_GUIDE.md` for scan versus source completion, ingestion versus successful boundary, bounded acquisition/refusal diagnostics, legacy fallback versus semantic proof and caller-owned reads. Explain the pending/reconciliation handoff and current continuity limitation; do not claim full-prefix hashing or held-source recovery landed. Historical qualification does not require native files or freshness cursors.

## Acceptance Criteria

- [ ] Pristine/live-only first-enable and raw-only bootstrap derive without deleting/repricing any observation when both checkpoint keys and prior semantic successes/replay usage/holds are absent; initial ingestion pending/failure tracking does not block bootstrap or certify completion. Established/partially missing/invalid/version-changed/contradictory proof skips safely, preserving usage/holds/checkpoint and reporting bounded incomplete status.

- [ ] Actual derive decisions, both cursor writers, unchanged Codex fast paths and freshness numeric reads enforce checkpoint validity. Smaller surviving raw max does not reset; justified same-version floors survive production retention/catch-up and existing rebuild stamping without allocation proof or invalid restamping.

- [ ] New positive source completion has `semantic` basis, acquisition coverage from zero (or full verified re-acquisition) and committed ENH-3744 correspondence over the same compatible range/version. Fully acquired/represented sources complete; held skipped candidates remain pending until ENH-3770. Retained-only proof/first-seen later offsets and ingestion/global progress cannot substitute for completion.

- [ ] Both writers persist distinct ingestion and successful derived boundaries. Missing/unprovable/pending work preserves the older source fact and cannot advance success or borrow row/ingestion timestamps.

- [ ] Scoped pending/retry bounds commit atomically with scan advancement, survive restart/resolved-neighbor retention and preserve another source's independent completion; the supplied bound can locate old work without itself proving native order.

- [ ] Current parser-refresh raw replacement atomically invalidates affected tracked completion and records scoped refresh-pending, including aliases; forced pre-commit failure rolls both back. No tracked semantic source silently remains complete across replacement, and unrelated source tracking is unchanged.

- [ ] Decode/JSON/non-object failures before raw insertion—including strict UTF-8 iteration before parser yield—produce durable content-free evidence. Neither later append, unchanged refresh nor retention clears it; blank/recognized benign and partial-tail controls remain correct.

- [ ] Sanitizer refusal fully rolls back ingestion while a guarded failure-only transaction records its bounded reason, including no-cursor sources. A stale refusal cannot taint newer success; failed diagnostic persistence never manufactures success or leaks payload bytes.

- [ ] Marker-specific recovery works: retained pending resolves from compatible committed proof; unadvanced-cursor refusal clears only after successful affected-range re-ingestion under valid continuation/scope; an advanced decode gap requires full re-acquisition from zero and verified retained prefix, preserving markers for uncheckable/pruned history. Partial tails require completion. Tail/inode equality alone never manufactures a historical generation certificate.

- [ ] Legacy public freshness compatibility remains when valid and without new negative evidence, while the pure semantic read reports unavailable/unprovable. Negative evidence overrides it and invalidated semantic state never falls back to legacy. Migration/fallback never creates a new derived certificate, clears pending, grants mutation/admission or seeds positive quality proof.

- [ ] Minimal applied-value supplier and consumed qualification-dependency witness storage/read/update helpers are available to ENH-3770, with explicit unavailable legacy values and atomic rollback; actual reconciliation and aggregate beyond-prefix integration are outside this gate.

- [ ] Pure completion reads work on query-only local/attached revisions with validated aliases and no file/stat/parse/pricing/write side effects or mandatory freshness cursor. Optional-connection freshness neither opens another history connection nor commits/rolls back/closes the caller's connection; source loss/change remains truthful unknown/stale.

- [ ] `python -m pytest scripts/tests/` exits 0 for this whole issue, without `_USAGE_DERIVE_VERSION` bump, new replay of linked/held rows or changed non-usage rebuild fingerprint. ENH-3732/ENH-3746 can consume the completed proof/storage reader seam before ENH-3770 lands.

## Implementation Steps

1. Confirm ENH-3744 is done; re-run readiness/confidence checks for this whole-issue scope. Reproduce bootstrap and invalid-proof cases, then guard actual derive/cursor/fast-path/freshness seams and preserve justified retention floors without destructive recovery.

2. Add the next append-only migration and pure state/helpers for pending/completion/failure and minimal value/qualification dependencies. Preserve legacy public comparison separately from unavailable semantic state.

3. Integrate local raw ingestion and both refresh acquisition paths, including pre-parser decode accounting and post-rollback scoped diagnostic persistence. Commit pending with scan advancement; keep held skipped work pending. Wire negative source invalidation/refresh-pending into current parser-refresh replacement without changing its destructive workflow.

4. Publish new boundaries only from acquisition plus committed candidate proof, then wire pure/optional-connection readers. Verify mixed-source, migration, continuity recovery, rollback/race and query-only revision controls; run the full local suite.

5. Hand the durable pending/invalidation and dependency interfaces to ENH-3770. Reconciliation, held retries/hold release and protected two-phase parser refresh are its implementation; deferred digest/aggregate hardening is not required to close this issue.

## Scope Boundaries

No semantic candidate recognition/prune veto (ENH-3744), reconciliation/hold release/safe mutation/retry iteration or protected two-phase parser-refresh replacement (ENH-3770), reader admission/aggregate beyond-prefix as-of integration (ENH-3746), or search restoration (ENH-3747). Full-prefix digest continuity and full held/pruned context promotion are deferred. This issue owns validated progress, acquisition/completion/failure storage, the minimal dependency handoff and freshness connection seam.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation review #4 - 2026-10-07 - Re-read checkpoint, cursor, ingestion, parser and rebuild seams against current tests. Replaced cross-issue atomic slices with whole-issue order ENH-3744 → ENH-3745 → ENH-3770; added no-delete pristine/live-only bootstrap, actual derive/publication guards, acquisition-plus-candidate completion, failure-only diagnostic persistence with a scope/witness compare-and-swap, no-cursor failure diagnostics and pre-parser decoding controls. Separated legacy public freshness compatibility from unavailable semantic completion, made the minimal value/qualification witness handoff mandatory, wired negative parser-refresh tracking separately from reconciliation, and moved held retries and deferred hardening out of this issue's gates. `/ll:advise` with Opus (confidence 0.73) supported whole-issue order and distinct semantic/legacy completion basis, zero-origin acquisition coverage and rejection-specific marker recovery. Historical log entries describe superseded delivery proposals. No implementation or new formal confidence score claimed.

- Pre-implementation review #3 - 2026-10-07 - Re-verified Current Behavior against `lifecycle.py`. `/ll:advise` with `claude-opus-5-5` (confidence 0.74) resolved the pending slicing: this issue owns S0 (MP1, checkpoint skip-not-reset, `sqlite_sequence` contradiction check, no schema change) and S1 (MP2, negative-evidence-only storage); digest continuity moved to Phase 2 with an interim marker-clearing rule; added AC/steps for sanitizer refusal, S0 and legacy-freshness non-regression. Atomic paired landing and the version bump coordination were replaced by ENH-3744's Delivery Plan. No implementation or score claimed (ENH-3745 still has no confidence score; run `/ll:confidence-check` for the S0 slice).
- Pre-implementation epic review - 2026-10-07 - Refreshed the schema note (`main` is v61, not 60). Verified in code that ENH-3751's sanitizer refusal in `refresh_usage_source` rolls back the entire refresh (no cursor/boundary advance) — fail-closed but a silent permanent stall, the opposite of the skipped-line false-`complete` defect — and added it as a distinct rejection class with a bounded durable `sanitization_refused` reason and per-route controls. Opus consult (confidence 0.72) recommended deferring full-prefix digest continuity as hardening; not applied, see EPIC-3562 Review Notes (2026-10-07). No implementation or readiness claim.

- Pre-implementation review - 2026-10-06 - Real-fixture probes showed both source refresh paths returning complete/fresh after malformed/non-object lines, unchanged Codex refresh returning complete with an old derive version, and a same-inode prefix rewrite outside the 64-byte tail accepted as fresh. Added durable admission-failure/pending state, all local insertion seams, fast-path validation, full-prefix continuity evidence and two-phase refresh restart controls. Extended figure proof to newly consumed qualification context. Opus confidence 0.76/0.80 supported the handoffs; rejected tail/inode-only continuation, automatic alias scope merging and generation-only clearing of unresolved failures. Existing targeted producer/retention/incremental/refresh suites: 111 passed; both revised issues passed structural checks. No implementation or readiness score claimed.

- Pre-implementation handoff review - 2026-10-06 - Defined scan-high-water versus source completion, durable generation-scoped retry bounds and atomic restart/retention recovery. Clarified that a preserved prefix is an internal source fact, not necessarily an as-of certificate for later changed figures; applied-value witnesses feed ENH-3746's publication check. Opus confidence 0.74 supported persistent pending evidence; its global-minimum completion floor was rejected because it would unnecessarily taint unrelated sources and uses ingestion order as processing proof. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reproduced unchanged-source `stale/derive_pending` after all four raw rows were pruned and catch-up ran, plus `ValueError` on malformed checkpoint metadata. Added shared validation, protected writer recovery, both cursor writers and the ENH-3744/3732 per-source handoff; no implementation or new score is claimed.

- Pre-implementation review - 2026-10-06 - Reconciled source completion versus conservation protection, separated ingestion/derived as-of boundaries and assigned minimal migration/generation ownership. Added malformed cursor metadata, conservative legacy backfill, retention replay-trigger recovery and caller-owned freshness reads; required paired ENH-3744 writer delivery. Opus confidence 0.72; allocation sequence remains a contradiction hint, never processing proof. Existing related suites: 188 passed; no implementation/readiness claim.
