---
id: ENH-3746
type: ENH
title: Recognize retained-source ingestion in the stored cache-rate reader after raw
  pruning
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
- BUG-3735
- ENH-3731
- ENH-3744
- ENH-3745
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3744
- ENH-3745
- ENH-3770
testable: true
---

# ENH-3746: Recognize retained-source ingestion in the stored cache-rate reader after raw pruning

## Summary

Admit a selected stored session from verified source-attributed replay observations when its raw rows were pruned. Keep admission separate from metric qualification/coverage, read admission, figure and source boundary in one committed revision, and publish freshness/as-of only when that boundary covers the whole figure. ENH-3744/3745 and ENH-3770 are `done`: shared proof, caller-connection freshness, witness storage/readers and guarded production witness population have landed. Consume those witnesses now; legacy, untracked or insufficient witness evidence keeps qualified figures visible with unknown freshness and NULL as-of.

## Current Behavior

On inspected branch `main`, `_compute_cache_rate_from_usage` in `scripts/little_loops/cli/ctx_stats.py` checks verified raw-row existence before selecting usage. Production prune can remove all four Claude raw fixture rows while both usage observations survive, turning the earlier 77% rate into `session_not_ingested`. The function also closes its selection connection before `usage_source_freshness` opens another, although the latter now supports `conn=`. A later committed boundary can therefore label an older figure fresh/as-of a newer offset. A real-ingestion temporary-store probe with two files for one Claude session returns four contributing observations and `fresh` from the selected file while the other file is `stale`; sharing one database revision alone cannot fix that population mismatch. ENH-3770's `usage_replay` now records actual production suppliers and consumed context for tracked acquisitions, while unacquired/legacy observations can still lack affirmative witnesses. Source-completion dependencies store observation IDs, not those observations' last-applied value positions; a same-ID Claude update can change the figure they reference.

## Expected Behavior

- Verified source-attributed committed replay evidence proves historical ingestion for the same host/session and original source spelling or resolved handle path. Reuse logical `row_channel` and `_verified_usage_identity`; an observation's provenance/price/component validity does not decide whether ingestion occurred.
- Claude transcript and Codex rollout observations may admit, including verified unknown audit observations; live-only, unverified legacy, other host/session/source, cursor-only and hold-only evidence cannot. NULL logical transcript channels follow the shared mapping rather than a SQL literal channel test.
- Admission is a separate existence/identity check. The subsequent figure still uses shared host/session coverage selection, including BUG-3735's hidden ambiguity evidence and every in-session contributor, regardless of which source admitted ingestion. Do not source-filter or add an acquisition-channel pin to the metric population to make a rate available.
- Unknown audit evidence can establish ingestion but cannot produce a numeric rate. Qualification, operands/counts, availability, coverage, provenance and returned metadata remain governed by the shared measured-only policy. Unavailable is NULL with a reason; qualified zero stays zero and a zero denominator has no numeric rate.
- Keep the four absence codes. Verified surviving raw with no observation gives `ingested_without_usage`; a rawless source with no verified retained replay observation stays `session_not_ingested` even if a cursor exists. Document that limitation without retaining arbitrary non-usage anchors.
- Source loss/rotation stays stale/unknown with a truthful historical boundary or unknown as-of, never current. Neither a replay hold nor admitted ingestion certifies freshness. ENH-3745 supplies boundary validity; this issue makes the reader use it coherently.
- Publish one figure-level `as_of`/`as_of_offset` only if every in-scope audit contributor used for values/qualification maps to the selected source spelling/resolved path and its applied-value native position is covered by the compatible successful derived boundary. Other-source/live/unlocated rows or later applied snapshots leave the figure's boundary unproved. Keep the figure/qualification population intact, set freshness to `unknown`, reason to `figure_boundary_unproven`, and both as-of fields to NULL. This is a freshness diagnostic, not a fifth absence code or new payload field.
- Missing/unavailable production witnesses take that same unknown-freshness branch. Ordinary tracked Claude/Codex acquisitions must exercise the positive branch using ENH-3770's actual stored witnesses. Neither a source-completion observation ID nor a surviving original raw link certifies the last-applied value or consumed qualification frontier. This availability change affects freshness labels only; admission, measured operands and qualification remain independent.

## Impact

- **Priority**: P2 — retained usage currently disappears behind raw-only admission.
- **Effort**: Medium — bounded identity admission, coherent snapshot and whole-figure supplier/context-boundary validation.
- **Risk**: Medium — admission must not change the metric population or certify a newer as-of boundary.
- **Breaking Change**: No payload-shape change; previously optimistic freshness/as-of labels become unknown when their whole-figure boundary cannot be proved.

## Proposed Solution

Add a bounded identity-only replay-ingestion predicate at the existing reader SQL seam, combine it with raw admission, and retain the existing figure selection/qualification. Pin admission, usage and the landed freshness metadata in one read transaction. Use internal contributor identity queries and `usage_source_state`'s typed supplier/frontier readers to validate the whole figure against the successful source boundary; do not widen public selector rows or add a second canonical selector.

## Program Design

### Types

Reuse `SessionHandle`, stored source-attribution/identity columns and the existing payload/absence diagnostic types. A boolean ingestion predicate needs no new result class, observation-ID export or hold-derived session identity.

### Signatures

- `has_replay_source_ingestion(conn: sqlite3.Connection, *, host: str, session_id: str, source_paths: Sequence[str], channel: str) -> bool` — new helper in `history_reader/usage.py`. Read only identity/source columns; reuse verified identity and logical channel policy. Missing identity/source columns cannot certify ingestion; query/store failures follow the outer `unreadable_store` path. Restrict replay channels to transcript/rollout and never admit live.
- Existing `_compute_cache_rate_from_usage(handle: SessionHandle, db_path: Path) -> tuple[dict[str, Any] | None, str | None]` keeps its payload/diagnostic interface.
- Consume ENH-3745's `usage_source_freshness(db, source, *, conn=None)` using the already-open reader connection and its transaction; no second history revision.
- Reuse `usage_source_state.read_source_head(conn, source_path)` and `read_observation_witness(conn, usage_event_id)` internally. `DerivedBoundary` carries the successful source scope and physical `line_no`/`offset`; `ObservationWitness` carries supplier scope/line/ordinal and consumed `qualification_dependencies`. No new lineage table or public contributor-ID API is needed.

### Call Path

`_compute_cache_rate_from_usage` → `has_replay_source_ingestion` or verified raw admission → `select_usage_coverage` → `usage_source_freshness` on the pinned connection + internal contributor-boundary check → shared measured-only qualification/output. File comparison remains external against the selected revision's boundary. Numeric qualification and source/figure freshness remain independent decisions.

### Decision Rules

- Historical source attribution requires no current file/generation match for admission; freshness separately checks boundary/source compatibility. Use both the original stored spelling and expanded/resolved handle path without stat-based equality, basename matching or arbitrary alias inference.
- A source hold has no session ID and cannot admit alone; wildcard holds cannot manufacture source/session evidence. An admitted unknown audit row does not become qualified consumption.
- Read all figure contributors under the existing host/session scope after admission. Retained-source evidence cannot hide another ambiguous, live or audit-only contributor.
- The same read transaction covers admission, selected observations and derived boundary facts. A later append/derive commit cannot label older figures with its fresh/as-of boundary. Honor connection/transaction ownership and close owned resources on every diagnostic exit.
- Verify cursor host/session/source scope against the admitted selected scope before publishing its freshness/as-of label; a cursor for another session at a reused path cannot certify this figure. Missing/malformed proof remains bounded unknown/stale through ENH-3745.
- Verify contributor lineage against the same pinned boundary as well as cursor identity. A Claude request first observed within the prefix but replaced beyond an earlier gap is outside that boundary; use its last-applied source/generation/native position, not its original request position or timestamp. A cross-source Codex dedup survivor retains the supplying source's lineage. Do not infer another source's freshness from a selected file, native-key equality or equal numeric values.
- Compare the successful boundary's source/host/session/generation/derive version with each known supplier witness, and require its physical supplier line to lie inside the successful physical line boundary. An ordinal may supply native-order evidence but cannot be compared to a physical line/byte boundary; raw IDs, ordinals and byte offsets are not interchangeable. Missing/malformed/unavailable or invalidated witness facts fail closed. Do not substitute `usage_completion_dependencies` observation-ID membership for applied-value evidence.
- Where qualification consumed model/closure context, require a known frontier and cover every dependency's compatible source/host/session/generation/version and physical position with the same successful boundary. A consumed dependency from another source or beyond the prefix makes figure freshness unproved even if all numeric suppliers lie inside it. An explicit `not_consumed` frontier is accepted only for a contract that requires no such context; absent frontier data is not an empty proved frontier. Reader enforcement is gating here; use ENH-3770's landed supplier/frontier behavior rather than inventing promotion or recovery in the reader. A `known` storage status alone is insufficient: require complete compatible supplier scope and a positive physical `supplier_line_no`. For qualified Codex rollout contributors, require consumed `model` and `closure` roles with compatible scope and positive physical positions; a known-but-empty or missing-role frontier, or `not_consumed` for that contract, takes `figure_boundary_unproven`. Claude embedded-model contracts with no external context may use `not_consumed`. The typed storage reader returns facts; it does not certify these contract-specific invariants.
- Preserve an old source boundary internally when later safe work proceeds, but do not attach it to a changed aggregate it does not bound. `figure_boundary_unproven` clears both public as-of fields while preserving values, operands/counts, coverage and qualification metadata. The four existing absence codes remain reserved for missing store/ingestion/observation outcomes; a populated result with unknown freshness is not absence.
- Missing proof storage/state yields populated unknown freshness when the metric can still be read; genuine connection/query failures retain the outer `unreadable_store` diagnostic. No current source availability, conservation hold or guessed default upgrades unavailable proof.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_usage` raw-or-replay admission, pinned read lifetime and caller-connection freshness call; keep selection/qualification/output populations unchanged.
- `scripts/little_loops/history_reader/usage.py` — identity-only ingestion predicate, internal actual-contributor identity/source queries and whole-figure boundary validation through shared witness readers. The selector currently omits source/raw-link columns, so use bounded internal queries here rather than assuming annotated audit rows already expose `source_path` or widening all public selector payloads. No observation IDs or lineage facts leave the internal read path.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `usage_source_state.py` — landed validated successful boundary, caller-connection freshness and typed source/witness reads. This issue owns threading the connection and figure-scope publication checks, without storage changes.
- `scripts/little_loops/session_store/writers.py`, `usage_replay.py`, `usage_source_tracking.py` — ENH-3770's landed guarded replay populates production applied-value/context witnesses and invalidates affected dependents atomically. Missing facts stay unknown here; no hold/cursor/completion-ID dependency manufactures an observation or supplier proof. Extend reader integration without another writer/storage implementation or scheduling prerequisite.

### Tests

Extend `scripts/tests/test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_bug3736_usage_replay_holds.py` and shared reader/chokepoint controls. Use real ingestion/derivation and production prune, original/resolved paths, repeated rebuild and source loss. Add source-only/wildcard holds without observations, unknown audit admission, logical NULL channels and missing identity/source columns. Drive actual text/JSON and metadata pointers, not only the predicate.

Add a two-source session whose selected source is fresh while the second has an unprocessed append, a live/unlocated contributor, and a Codex dedup survivor from the other source. All keep their full metric population and get unknown figure freshness/NULL as-of. Add a Claude request originally inside the successful prefix, then updated beyond a pending gap: the old prefix cannot label its new values. Add same-ID value changes with only old completion-ID dependencies, and a value supplier inside the prefix whose consumed closure/model dependency lies beyond it; both must fail the figure-boundary check. Use actual storage helpers for compatible and wrong-generation/host/session/position witness fixtures. Keep the ordinary single-source 77% value control, legacy/untracked missing-witness unknown freshness, and a positive fully bounded freshness/file-size control with actual production-written witnesses. Add helper-written `known` witnesses with NULL/zero supplier positions and Codex empty/model-only/closure-only frontiers; all retain figures with unknown freshness and NULL as-of. A positive Codex control covers both consumed roles. ENH-3770 supplies production witnesses now: drive tracked Claude and Codex acquire → guarded derive → production prune → reader positives without fixture-written witnesses or a later flag flip. A Codex context-only qualification change must preserve its numeric supplier and use the new consumed frontier; source generation/rotation and beyond-boundary context keep freshness unproved. Retain WAL race/connection ownership and missing-proof-versus-store-error controls.

Pair a still-bounded, unchanged historical figure with a later acquired append/usage-pending gap: retain its truthful old boundary and stale/unknown source status, never `fresh`. If a contributor's applied supplier or consumed frontier advances beyond that successful prefix, agreeing `known` witnesses cannot certify the changed figure; publish `figure_boundary_unproven` with NULL as-of. Add a mixed tracked-production/witnessless-legacy two-source figure and preserve every contributor while leaving its boundary unproved. “Retained as-of consumption” describes committed historical observations, not permission to fill public freshness `as_of` from observation timestamps. Quality may blank a complete-session/window metric on known outstanding usage while this observed cache-rate figure remains numeric with non-fresh metadata; document that intentional difference without weakening either policy.

## Acceptance Criteria

- [ ] Real Claude/Codex retained as-of rates remain visible after all raw rows are pruned, including source loss/rebuild controls; source loss is stale/unknown with truthful historical or unknown boundary, never fresh.
- [ ] Other-host/session/source, live-only, unverified legacy and cursor/hold-only controls do not admit. Matching verified unknown replay evidence admits without a numeric rate; logical NULL-channel/source-spelling controls pass.
- [ ] Admission preserves all in-session figure contributors and BUG-3735 ambiguity evidence; measured-only qualification, unavailable-vs-zero and the full existing payload/provenance metadata remain correct.
- [ ] Raw-with-no-usage versus rawless/no-observation keeps the four existing absence codes; no non-usage anchor is retained just to make admission work.
- [ ] Admission, figure and successful boundary use one committed read snapshot. A WAL append/derive between reads cannot stamp old usage with newer freshness/as-of; reused-path other-session cursor and malformed-proof controls fail closed.
- [ ] Multi-source/live/unlocated, missing/malformed witnesses, beyond-prefix replacement and beyond-prefix consumed-context cases retain their full figures/qualification but publish `unknown` freshness with `figure_boundary_unproven` and NULL `as_of`/`as_of_offset`. Single-source figures with complete compatible supplier/frontier witnesses, positive physical positions and every contract-required context role retain normal freshness/boundary behavior; a `known` flag or empty Codex frontier alone is insufficient. Production raw-pruned figures need no fabricated witness to remain numerically visible. No absence code or payload key is added.
- [ ] No source-only metric filter, new canonical selector or exported observation-ID surface is introduced. Existing SQL/history-store chokepoint gates pass.
- [ ] Final reader integration consumes the landed freshness/state seams and `python -m pytest scripts/tests/` exits 0. Witness-backed positive tests use real tracked production acquisition/derive, not only helper-written fixtures; missing legacy/untracked witnesses retain the conservative branch.

## Implementation Steps

1. Add/test the identity-only retained-ingestion predicate without changing the metric population; preserve negative identity/hold/cursor controls and implement the source-set publication check.
2. Pin admission/coverage/boundary reads, pass the existing connection through freshness, and enforce actual applied-value plus consumed-context witness coverage. Missing facts take `figure_boundary_unproven`; no waiting for future producer population or deferred fallback is required.
3. Exercise real prune/rebuild/source-loss and concurrent-commit text/JSON cases plus helper-backed negative boundary controls; require tracked Claude/Codex production witness-backed positives through the actual reader, including Codex closure-only qualification changes. Keep separate untracked/legacy missing-witness controls; verify payload/chokepoint compatibility and run the local suite.

## Scope Boundaries

No source freshness boundary storage/algorithm, semantic prune/replay/hold changes, arbitrary source aliases, non-usage anchors, new selector population or search restoration. Figure-scope publication checks, conservative missing-witness handling and production writer-to-reader interoperability belong here; ENH-3770's witness population has landed. Closeout requires actual tracked-production positives alongside legacy/untracked fail-closed controls. Admission alone is partial implementation.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation epic review - 2026-10-08 - Reconciled the completed ENH-3770 producer handoff and required actual Claude/Codex production witness-to-reader positives now, including closure-only requalification and pruned sources. Legacy/untracked missing-witness cases remain numerically independent of freshness. No implementation or readiness claim.

- Pre-implementation epic review - 2026-10-07 - Required complete positive-position supplier facts and contract-required Codex model/closure roles, preventing vacuous acceptance of helper-written known/empty witnesses. The current reader consumes future producer witnesses through data without another code/flag cutover; ENH-3770 owns production interoperability. No storage, scheduling, payload or readiness change.

- Pre-implementation landed-handoff review - 2026-10-07 - Corrected the completed ENH-3744/3745 storage/freshness handoff versus ENH-3770 production witness population. Required whole-figure applied-value and consumed-context coverage using shared typed reads, with unknown freshness/NULL as-of when missing; retained numeric admission/qualification and the existing reason/payload vocabulary. Completion-ID membership is not supplier proof. Positive boundary controls use actual helper-written witnesses, with production interoperability following ENH-3770 and no new hard scheduling edge. Opus confidence 0.78 supported this conservative delivery; rejected speculative cache-only invalidation because raw-cache obligations concern message/tool caches. Format/design/dependency checks and relevant existing suites/prose gate: 330 passed. No implementation or readiness score.
- `/ll:ready-issue` - 2026-10-07T23:18:26 - `d4950fb6-e6e8-449c-ae1d-00ebb49011d8.jsonl`
- Pre-implementation epic review - 2026-10-07 - Split the figure-boundary check into a source-set half (existing attribution, no new witness storage; lands with the admission helper and fixes the reproduced multi-source `fresh` mislabel) and an applied-value-position half (waits for the ENH-3744/3745 handoff, fail-closed `figure_boundary_unproven` meanwhile). Opus consult (confidence 0.72) recommended the same separation. No implementation or readiness claim.

- Pre-implementation handoff review - 2026-10-06 - Reproduced a four-observation multi-source Claude figure labeled fresh while its other source was stale. Required whole-figure contributor/boundary coverage in addition to one read revision, including later applied snapshots and other-source dedup survivors. Chose bounded unknown freshness/NULL as-of without filtering values or changing absence/payload contracts; tied lineage ownership to the paired ENH-3744/3745 handoff. Opus confidence 0.74 supported the check; absence codes were not reused for a populated freshness result. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reproduced `session_not_ingested` after production prune while both Claude observations survived (previous rate 77%). Corrected the payload signature, prohibited hold-only session proof and added concrete source-loss/as-of, identity, chokepoint and combined freshness tests. No implementation or new score is claimed.

- Pre-implementation review - 2026-10-06 - Pinned a boolean identity-only helper, corrected selector source-column assumptions and retained unknown-audit versus numeric-qualification separation. Added same-revision figure/boundary and reused-path scope controls; recorded ENH-3745 as the actual final integration prerequisite. Opus confidence 0.72; no observation-ID result/export needed. Existing related suites: 188 passed; no implementation/readiness claim.
