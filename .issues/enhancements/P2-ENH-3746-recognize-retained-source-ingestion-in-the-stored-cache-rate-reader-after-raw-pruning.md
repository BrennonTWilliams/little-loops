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
testable: true
---

# ENH-3746: Recognize retained-source ingestion in the stored cache-rate reader after raw pruning

## Summary

Admit a selected stored session from verified source-attributed replay observations when its raw rows were pruned. Keep admission separate from metric qualification/coverage, read admission, figure and source boundary in one committed revision, and publish freshness/as-of only when that boundary covers the whole figure. The admission helper can be developed independently; final reader integration requires ENH-3745's caller-connection freshness seam and ENH-3744's applied-value witness handoff through their paired delivery.

## Current Behavior

On inspected branch `main`, `_compute_cache_rate_from_usage` in `scripts/little_loops/cli/ctx_stats.py` checks verified raw-row existence before selecting usage. Production prune can remove all four Claude raw fixture rows while both usage observations survive, turning the earlier 77% rate into `session_not_ingested`. The function also closes its selection connection before `usage_source_freshness` opens another, allowing later committed boundary metadata to label an older figure fresh/as-of a newer offset. A real-ingestion temporary-store probe with two files for one Claude session returns four contributing observations and `fresh` from the selected file while the other file is `stale`; sharing one database revision alone cannot fix that population mismatch.

## Expected Behavior

- Verified source-attributed committed replay evidence proves historical ingestion for the same host/session and original source spelling or resolved handle path. Reuse logical `row_channel` and `_verified_usage_identity`; an observation's provenance/price/component validity does not decide whether ingestion occurred.
- Claude transcript and Codex rollout observations may admit, including verified unknown audit observations; live-only, unverified legacy, other host/session/source, cursor-only and hold-only evidence cannot. NULL logical transcript channels follow the shared mapping rather than a SQL literal channel test.
- Admission is a separate existence/identity check. The subsequent figure still uses shared host/session coverage selection, including BUG-3735's hidden ambiguity evidence and every in-session contributor, regardless of which source admitted ingestion. Do not source-filter or add an acquisition-channel pin to the metric population to make a rate available.
- Unknown audit evidence can establish ingestion but cannot produce a numeric rate. Qualification, operands/counts, availability, coverage, provenance and returned metadata remain governed by the shared measured-only policy. Unavailable is NULL with a reason; qualified zero stays zero and a zero denominator has no numeric rate.
- Keep the four absence codes. Verified surviving raw with no observation gives `ingested_without_usage`; a rawless source with no verified retained replay observation stays `session_not_ingested` even if a cursor exists. Document that limitation without retaining arbitrary non-usage anchors.
- Source loss/rotation stays stale/unknown with a truthful historical boundary or unknown as-of, never current. Neither a replay hold nor admitted ingestion certifies freshness. ENH-3745 supplies boundary validity; this issue makes the reader use it coherently.
- Publish one figure-level `as_of`/`as_of_offset` only if every in-scope audit contributor used for values/qualification maps to the selected source spelling/resolved path and its applied-value native position is covered by the compatible successful derived boundary. Other-source/live/unlocated rows or later applied snapshots leave the figure's boundary unproved. Keep the figure/qualification population intact, set freshness to `unknown`, reason to `figure_boundary_unproven`, and both as-of fields to NULL. This is a freshness diagnostic, not a fifth absence code or new payload field.

## Impact

- **Priority**: P2 — retained usage currently disappears behind raw-only admission.
- **Effort**: Small-medium — bounded identity helper plus coherent reader/freshness integration.
- **Risk**: Medium — admission must not change the metric population or certify a newer as-of boundary.
- **Breaking Change**: No

## Proposed Solution

Add a bounded identity-only replay-ingestion predicate at the existing reader SQL seam, combine it with raw admission, and retain the existing figure selection/qualification. Pin the reader's admission, usage and ENH-3745 freshness metadata in one read transaction. Use an internal contributor-boundary query at that same seam to validate the figure's scope against the source fact; do not widen public selector rows or add a second canonical selector.

## Program Design

### Types

Reuse `SessionHandle`, stored source-attribution/identity columns and the existing payload/absence diagnostic types. A boolean ingestion predicate needs no new result class, observation-ID export or hold-derived session identity.

### Signatures

- `has_replay_source_ingestion(conn: sqlite3.Connection, *, host: str, session_id: str, source_paths: Sequence[str], channel: str) -> bool` — new helper in `history_reader/usage.py`. Read only identity/source columns; reuse verified identity and logical channel policy. Missing identity/source columns cannot certify ingestion; query/store failures follow the outer `unreadable_store` path. Restrict replay channels to transcript/rollout and never admit live.
- Existing `_compute_cache_rate_from_usage(handle: SessionHandle, db_path: Path) -> tuple[dict[str, Any] | None, str | None]` keeps its payload/diagnostic interface.
- Consume ENH-3745's `usage_source_freshness(db, source, *, conn=None)` using the already-open reader connection and its transaction; no second history revision.

### Call Path

`_compute_cache_rate_from_usage` → `has_replay_source_ingestion` or verified raw admission → `select_usage_coverage` → `usage_source_freshness` on the pinned connection + internal contributor-boundary check → shared measured-only qualification/output. File comparison remains external against the selected revision's boundary. Numeric qualification and source/figure freshness remain independent decisions.

### Decision Rules

- Historical source attribution requires no current file/generation match for admission; freshness separately checks boundary/source compatibility. Use both the original stored spelling and expanded/resolved handle path without stat-based equality, basename matching or arbitrary alias inference.
- A source hold has no session ID and cannot admit alone; wildcard holds cannot manufacture source/session evidence. An admitted unknown audit row does not become qualified consumption.
- Read all figure contributors under the existing host/session scope after admission. Retained-source evidence cannot hide another ambiguous, live or audit-only contributor.
- The same read transaction covers admission, selected observations and derived boundary facts. A later append/derive commit cannot label older figures with its fresh/as-of boundary. Honor connection/transaction ownership and close owned resources on every diagnostic exit.
- Verify cursor host/session/source scope against the admitted selected scope before publishing its freshness/as-of label; a cursor for another session at a reused path cannot certify this figure. Missing/malformed proof remains bounded unknown/stale through ENH-3745.
- Verify contributor lineage against the same pinned boundary as well as cursor identity. A Claude request first observed within the prefix but replaced beyond an earlier gap is outside that boundary; use its last-applied source/generation/native position, not its original request position or timestamp. A cross-source Codex dedup survivor retains the supplying source's lineage. Do not infer another source's freshness from a selected file, native-key equality or equal numeric values.
- Preserve an old source boundary internally when later safe work proceeds, but do not attach it to a changed aggregate it does not bound. `figure_boundary_unproven` clears both public as-of fields while preserving values, operands/counts, coverage and qualification metadata. The four existing absence codes remain reserved for missing store/ingestion/observation outcomes; a populated result with unknown freshness is not absence.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_usage` raw-or-replay admission, pinned read lifetime and caller-connection freshness call; keep selection/qualification/output populations unchanged.
- `scripts/little_loops/history_reader/usage.py` — identity-only ingestion predicate and internal source/generation/native-position query for actual contributor IDs, using existing shared verification/channel rules. The selector currently omits source/raw-link columns, so use bounded internal queries here rather than assuming annotated audit rows already expose `source_path` or widening all public selector payloads. No observation IDs or lineage facts leave the internal read path.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py` — ENH-3745's validated successful boundary and caller-connection reader. It owns freshness/storage semantics; this issue owns threading the connection and selected-scope checks.
- `scripts/little_loops/session_store/writers.py` — ENH-3744 source/host/identity consistency and applied-value lineage, with ENH-3745 owning missing durable witness fields. No hold/cursor manufactures an observation. Final ENH-3744/3745 integration supplies this shared handoff without a circular scheduling edge.

### Tests

Extend `scripts/tests/test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_bug3736_usage_replay_holds.py` and shared reader/chokepoint controls. Use real ingestion/derivation and production prune, original/resolved paths, repeated rebuild and source loss. Add source-only/wildcard holds without observations, unknown audit admission, logical NULL channels and missing identity/source columns. Drive actual text/JSON and metadata pointers, not only the predicate.

Add a two-source session whose selected source is fresh while the second has an unprocessed append, a live/unlocated contributor, and a Codex dedup survivor from the other source. All keep their full metric population and get unknown figure freshness/NULL as-of. Add a Claude request originally inside the successful prefix, then safely updated beyond a pending gap: the old prefix cannot label its new values. Keep the ordinary single-source 77%/file-size boundary control and WAL race/connection ownership controls.

## Acceptance Criteria

- [ ] Real Claude/Codex retained as-of rates remain visible after all raw rows are pruned, including source loss/rebuild controls; source loss is stale/unknown with truthful historical or unknown boundary, never fresh.
- [ ] Other-host/session/source, live-only, unverified legacy and cursor/hold-only controls do not admit. Matching verified unknown replay evidence admits without a numeric rate; logical NULL-channel/source-spelling controls pass.
- [ ] Admission preserves all in-session figure contributors and BUG-3735 ambiguity evidence; measured-only qualification, unavailable-vs-zero and the full existing payload/provenance metadata remain correct.
- [ ] Raw-with-no-usage versus rawless/no-observation keeps the four existing absence codes; no non-usage anchor is retained just to make admission work.
- [ ] Admission, figure and successful boundary use one committed read snapshot. A WAL append/derive between reads cannot stamp old usage with newer freshness/as-of; reused-path other-session cursor and malformed-proof controls fail closed.
- [ ] Multi-source/live/unlocated and beyond-prefix replacement cases retain their full figures/qualification but publish `unknown` freshness with `figure_boundary_unproven` and NULL `as_of`/`as_of_offset`. Single-source fully bounded figures keep their existing freshness/boundary behavior. No absence code or payload key is added.
- [ ] No source-only metric filter, new canonical selector or exported observation-ID surface is introduced. Existing SQL/history-store chokepoint gates pass.
- [ ] Final integration consumes the landed ENH-3745 seam and `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add/test the identity-only retained-ingestion predicate without changing the metric population; preserve negative identity/hold/cursor controls.
2. After the paired ENH-3744/3745 handoff, pin admission/coverage/boundary reads, pass the existing connection through freshness, and validate every contributor's applied-value lineage against the selected-source boundary before publishing freshness/as-of.
3. Exercise real prune/rebuild/source-loss and concurrent-commit text/JSON cases; verify payload and chokepoint compatibility, then run the local suite.

## Scope Boundaries

No source freshness boundary storage/algorithm, semantic prune/replay/hold changes, arbitrary source aliases, non-usage anchors, new selector population or search restoration. Figure-scope publication checks belong here; the paired writer witness/connection dependency is required for final closeout. Admission alone is partial implementation.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- Pre-implementation handoff review - 2026-10-06 - Reproduced a four-observation multi-source Claude figure labeled fresh while its other source was stale. Required whole-figure contributor/boundary coverage in addition to one read revision, including later applied snapshots and other-source dedup survivors. Chose bounded unknown freshness/NULL as-of without filtering values or changing absence/payload contracts; tied lineage ownership to the paired ENH-3744/3745 handoff. Opus confidence 0.74 supported the check; absence codes were not reused for a populated freshness result. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reproduced `session_not_ingested` after production prune while both Claude observations survived (previous rate 77%). Corrected the payload signature, prohibited hold-only session proof and added concrete source-loss/as-of, identity, chokepoint and combined freshness tests. No implementation or new score is claimed.

- Pre-implementation review - 2026-10-06 - Pinned a boolean identity-only helper, corrected selector source-column assumptions and retained unknown-audit versus numeric-qualification separation. Added same-revision figure/boundary and reused-path scope controls; recorded ENH-3745 as the actual final integration prerequisite. Opus confidence 0.72; no observation-ID result/export needed. Existing related suites: 188 passed; no implementation/readiness claim.
