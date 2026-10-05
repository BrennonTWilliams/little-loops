---
id: BUG-3735
type: BUG
title: Scoped usage selection hides unverified overlap candidates
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T17:27:31Z'
completed_at: '2026-10-05T20:33:41Z'
parent: EPIC-3562
labels:
- observability
- usage-coverage
testable: true
blocks:
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
relates_to:
- BUG-3736
- ENH-3730
- ENH-3731
- ENH-3732
- ENH-3733
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3735: Scoped usage selection hides unverified overlap candidates

## Summary

`select_usage_coverage` filters by `host`/`session_id` in SQL before checking cross-channel ambiguity. A sessionless live observation can therefore be excluded from a selected session even when it could duplicate that session's transcript; a live row without a verified host is also excluded by a host filter. The resulting scoped reader publishes `non_overlapping` where the unnarrowed acquisition population remains `overlap_unresolved`. Preserve possible counterparts during coverage analysis, then narrow returned rows to the requested host/session. This is a correctness repair; ENH-3730 separately evaluates whether verified overlap domains can safely recover availability.

## Current Behavior

A temporary-database probe on 2026-10-05 inserted a synthetic complete measured Claude transcript (`host_basis=handle`, session `session-a`) and a complete measured `live` row for the same host without a session identity. The unscoped and host-only selections both returned `overlap_unresolved`, reason `unverified_cross_channel_identity`, 2 audit rows and 0 selected rows. Selecting that host plus `session-a` returned `non_overlapping`, 1 audit row and 1 selected row. After clearing the live row's host, host-only selection also returned `non_overlapping`, 1 audit row and 1 selected row. These are synthetic contract probes, not captured native duplicates; without identity the selector cannot prove disjointness.

A second review reproduced both cases and found that the pair SQL also disagrees with `_verified_usage_identity`: it admits a `rollout` row with `host_basis='handle'` but no `identity_basis='host_observed'` into pair audit output, although the helper rejects its identity. It excludes a NULL-channel handle-attributed transcript completely. A schema lacking `channel`/`identity_basis` separately returns the existing `no_verified_identity_columns` diagnostic; preserve that schema compatibility boundary and distinguish it from NULL values on a supported schema. The admitted unverified Codex rollout remains `unknown` today; this is an attribution inconsistency, not a reproduced numeric certification for that control.

A mixed-failure synthetic control also returned aggregate `overlap_unresolved` with reason `codex_live_scope_unknown`: the reason came from the first unknown group although another group's overlap won the status. Output narrowing must preserve a truthful reason from the winning visible status.

The NULL-channel admission repair also exposes a consumer mismatch: `_compute_cache_rate_from_usage` builds `channels` with `row["channel"] or "unknown"`, while its `ObservationGroup` subtotals already use `row_channel`. Once a verified NULL-channel transcript reaches this reader, those two fields would disagree. Normalize that existing channel metadata as part of the compatibility control.

## Steps to Reproduce

1. Create a temporary history database through `ensure_db`, then insert two synthetic complete measured observations: a Claude transcript with verified source host and session `session-a`, and a same-host live observation with no session identity. Use input/output/cache-read/cache-creation values 10/2/4/0 on each.
2. Compare `select_usage_coverage(conn)` with `select_usage_coverage(conn, host="claude-code", session_id="session-a")`. The full selection is unresolved while the scoped result incorrectly certifies one selected observation.
3. Set the live observation's host to NULL and call `select_usage_coverage(conn, host="claude-code")`. The host filter now hides the wildcard and incorrectly certifies the transcript again.

## Expected Behavior

Compute ambiguity over the declared acquisition population before host/session output narrowing and before `since`/run filters. A missing/unverified host or session cannot establish that a possible opposite-channel counterpart lies outside the requested session. A host/session pair returns only rows with that verified pair; wildcard evidence influences coverage without leaking into that session's totals. Host-only output retains the existing host-attributed audit population (including unverified rows), rather than silently dropping completeness contributors. An ID-only call remains rejected. An explicitly declared logical `channel=` acquisition scope, once ENH-3731 adds it, is applied before ambiguity; it is a population choice, not proof of cross-channel disjointness.

Resolve logical channels with `row_channel` for both acquisition and verified-pair output checks, and reuse `_verified_usage_identity` for pair admission after the existing schema gate. Live and rollout rows require `identity_basis='host_observed'`; transcript replay requires the verified source handle and session. A replay row with a session ID, `host_basis='handle'`, and a NULL channel value is a logical transcript, so it must not be discarded by the current SQL `channel IS NOT NULL` predicate. Identity admission does not qualify numeric provenance or waive Codex request/scope prerequisites; NULL/unknown provenance remains unqualified under the existing stored reader and ENH-3731.

Existing stored-session `channels` metadata and `channel_subtotals` must agree on that logical transcript channel; preserve the stored NULL value rather than rewriting history. BUG-3736's retained-source ingestion check remains a separate admission check: it must not introduce a source-path acquisition filter here or hide retained wildcard overlap evidence. Neither bug requires the other to land first; use a directly inserted retained-evidence fixture for this selector's independent regression, and add the production lifecycle/reader integration control once both repairs are present.

Make the legacy schema rule explicit: pair selection preserves the current schema gate requiring `host`, `host_basis`, `session_id`, `channel` and `identity_basis` columns; an absent column keeps `unknown/no_verified_identity_columns`. Once that gate passes, NULL channel values resolve through `row_channel`; a NULL `identity_basis` prevents live/rollout admission but does not reject a handle-attributed transcript. Host-only selection without a `host` column keeps `unknown/no_host_column`. Optional-column NULL projection remains available to unscoped/host-only acquisition. Session-ID-only calls still raise `ValueError`. Supporting older pair schemas is a separate compatibility change, not part of this repair.

Classify complete groups before narrowing them, then construct returned groups, row annotations and channel subtotals from only output-visible rows. Hidden counterparts may taint that classification but must not appear in scoped rows, counts or subtotals. An empty output remains unknown/unavailable; it cannot acquire a numeric zero or expose another session's audit evidence. Keep the existing aggregate status precedence (`overlap_unresolved` > `unknown` > `non_overlapping`); choose the aggregate reason from visible groups with that winning status, breaking multiple-reason ties by lexical code order. Preserve the existing bounded coverage-reason vocabulary and each row/group's own reason.

Keep the existing conservative ambiguity policy for this repair. Do not infer disjointness from counts, timestamps, configured host strings or equal token values. Any narrower domain policy belongs to ENH-3730. Qualified historical/as-of values remain retained; a newly unresolved canonical rate becomes unavailable with a coverage reason rather than deleting observations or fabricating zero.

## Motivation

Host/session selection must not certify usage by hiding an unidentified possible duplicate. All six remaining-host delivery issues need this repaired selector before publishing usage or switching readers.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — separate acquisition and output narrowing; preserve identity verification and annotations.
- `scripts/little_loops/cli/ctx_stats.py` — normalize existing stored-session channel metadata with the helper from `token_provenance.py` so NULL-channel compatibility matches the shared selector/subtotals.
- `scripts/tests/test_enh3543_usage_coverage.py` — sessionless same-host live and unknown-host wildcard controls; filter-order tests.
- `scripts/tests/test_enh3656_stored_cache_rate.py`, `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` — drive actual session readers where the existing fixture helpers apply; retain text/JSON as-of behavior and empty-vs-zero distinctions.
- `docs/reference/API.md`, `docs/reference/CLI.md` — clarify that host/session selection does not hide possible overlap and may make previously displayed rates unavailable.

### Dependent Files

- `scripts/little_loops/session_store/queries.py` — snapshot remains on the shared selector.

### Similar Patterns

- Existing `since`/`require_run_id` filters run after coverage reconciliation; host/session output selection needs the same completeness discipline.
- `_verified_usage_identity`, `_coverage_key`, `row_channel` and `row_host_verified` already encode the identity policy; pair output must use the same policy rather than a second SQL approximation.

### Tests

- Same-host sessionless live plus verified transcript: scoped selection remains unresolved.
- No verified host on live or replay counterpart: a host filter cannot remove its ambiguity influence.
- Fully verified disjoint session controls retain the existing result; same-session live/replay remains unresolved; unverified stored host strings cannot create isolation.
- A counterpart outside `since` or lacking a run ID still influences scoped coverage.
- Logical transcript-only acquisition (when ENH-3731 lands) excludes live/rollout as declared, without altering default cross-channel behavior.
- Scoped audit rows/counts never include a different host/session's usage merely because it influenced coverage.
- Legacy NULL-channel replay with verified handle attribution survives pair output as a logical transcript; absent required schema columns keep the existing unknown diagnostics. Host-only output keeps unverified audit contributors and cannot certify a complete subset by dropping them.
- Drive that NULL-channel row through the real stored-session reader and assert `channels=["transcript"]` agrees with the transcript subtotal; a NULL provenance control still has no qualified numeric rate.
- Test absent `channel` and absent `identity_basis` separately and together, as well as NULL values on the current schema. Absent schema columns fail closed; live/rollout lacking host-observed identity never enter pair output. Verified rollout identity with an invalid request/turn remains audit-only under the existing classifier.
- Default global conservatism is deliberate: an unverified acquired row can keep an otherwise verified scoped group unresolved even outside that host/session. Fully verified different-session controls remain independent; restoring availability with verified-host wildcard domains belongs to ENH-3730.
- Validate returned `CoverageGroup` rows, annotations and per-channel event/component counts, not just the flattened row count. Empty selections, mixed visible failure statuses, repeated calls and insertion-order permutations preserve status/reason semantics without leaking hidden audit rows.
- Retained unverified opposite-channel evidence still taints scoped coverage without leaking its hidden row/count/subtotal into the selected session. Insert retained usage without raw directly for this independent selector regression; once BUG-3736 lands, exercise production pruning and retained-reader admission too. Neither raw-source absence nor that admission check may remove stored ambiguity evidence.

### Documentation

- Reader-facing API/CLI coverage and unavailable-rate semantics; no source-DB schema change.

## Program Design

### Signatures

- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None) -> CoverageSelection` — keep current arguments and any ENH-3731 `channel` addition; separate full acquisition candidates from narrowed output rows.
- `select_usage_observations(...)` — continues delegating to the same selector and yielding annotated audit rows.

### Call Path

Stored usage → `select_usage_coverage` acquisition candidates (logical channel scope if supplied) → `_classify_coverage` with full-population ambiguity → verified host/session output selection → report-window/run filters → `CoverageSelection` → `select_usage_observations` and `_compute_cache_rate_from_usage` consumers.

### Algorithm Constraints

- Fetch the declared acquisition population once; no host/session SQL predicate may remove its ambiguity evidence. Preserve optional-column NULL projection and the essential-schema diagnostics above.
- Build identity groups and the existing global ambiguity flag from that population. Pair output requires matching host/session plus `_verified_usage_identity(row)`; host-only output matches the stored host without discarding unverified audit contributors.
- Rebuild visible group subtotals after output/window/run narrowing while carrying the earlier classification. Preserve deterministic row ordering and linear grouping; no pairwise counterpart scan or per-group database query is needed.
- No hard dependency on ENH-3731: land this repair on the current selector or compose with its `channel=` argument in either order. BUG-3736 is independent lifecycle work. The `blocks` edges above encode the already stated prerequisite for the six remaining-host delivery issues.

## Implementation Steps

1. Reproduce both synthetic scoped-certification cases, the rollout/helper disagreement, and NULL-channel/absent-schema controls in selector tests.
2. Separate acquisition, coverage classification and output selection; reuse the identity helpers after the existing schema gate, and preserve the declared channel scope in either landing order with ENH-3731.
3. Exercise stored-session readers and source/snapshot controls, including logical channel metadata, scoped group counts and empty output; document the conservative availability change. Keep BUG-3736's source admission separate from this selector's acquisition population.
4. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — a selected session can otherwise expose a falsely certified rate.
- **Effort**: Small to medium — shared-selector filter order plus existing consumer controls.
- **Risk**: Medium — conservative repair may make formerly displayed scoped figures unavailable; retain audit/as-of evidence and explain why.
- **Breaking Change**: No signature change; unsafe numeric results become explicitly unavailable.

## Root Cause

- **File**: `scripts/little_loops/history_reader/usage.py`
- **Anchor**: `select_usage_coverage`
- **Cause**: the SQL `host`/`session_id` clauses discard possible wildcard counterparts before `ambiguous_cross_channel` is computed. `_coverage_key` cannot reconcile rows that were never acquired.

## Acceptance Criteria

- [ ] Sessionless same-host and unknown-host opposite-channel candidates cannot be hidden by host/session selection; unresolved coverage and bounded reasons reach the real stored reader.
- [ ] Host/session arguments constrain returned rows and attribution, not the completeness of cross-channel evidence; identity-only calls still fail and unverified attributed rows cannot enter a verified session's totals.
- [ ] Pair output uses logical channel identity for verified legacy NULL-channel transcripts, and real stored-session channel labels/subtotals agree; absent required schema columns keep the existing fail-closed diagnostics. Host-only output retains unverified host-attributed audit contributors; legacy/unknown provenance is never promoted by the identity repair.
- [ ] After the existing five-column schema gate, pair admission agrees with `_verified_usage_identity` for every logical channel: live/rollout require host-observed identity, transcript permits NULL `channel`/`identity_basis` values, and request/scope qualification remains separate.
- [ ] Coverage is computed before host/session output narrowing and report-window/run filters; an ENH-3731 logical channel acquisition scope remains a distinct earlier population choice.
- [ ] Fully verified disjoint controls, same-session unresolved controls, scoped group subtotals/counts, empty output, matching status/reason, source/snapshot parity, historical retention and text/JSON unavailable-vs-zero behavior pass without insertion-order-dependent results.
- [ ] No live/replay join, provenance promotion, price change, source re-derive or ENH-3730 availability optimization is introduced.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope**: scoped selection correctness and existing consumer/diagnostic regression tests.
- **Out of scope**: ENH-3730 overlap-domain optimization, ENH-3731 qualification policy, native host evidence, workspace additive-counting policy, older pair-schema support and source-history migrations.

## Related Key Documentation

- `docs/reference/API.md` — stored coverage selector.
- `docs/reference/CLI.md` — stored cache-rate output.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- `/ll:manage-issue` - 2026-10-05T20:33:41 - `f5a1b523-6452-4ef2-b7df-927c51b9b006.jsonl`
- `/ll:ready-issue` - 2026-10-05T20:24:02 - `7ea957ea-936a-4160-a3b8-dd75a58926b9.jsonl`
- `/ll:confidence-check` - 2026-10-05T20:19:17 - `f6d5bda9-e0b6-40a7-a941-d62aa0ca7fa2.jsonl`
- `/ll:capture-issue` - 2026-10-05T17:36:12 - `b20687c5-3662-40c9-ac0d-0a4ae5fef8fe.jsonl`
- Pre-implementation epic review - 2026-10-05 - Captured the scoped overlap defect after Opus critique (confidence 0.74) and synthetic same-host/sessionless and no-host probe reproduction. Full selection is unresolved while host/session output narrowing falsely certifies it; ENH-3730 remains separate availability work.
- Pre-implementation issue review - 2026-10-05 - Reproduced both scoped-certification defects in temporary databases; confirmed pair SQL admits an identity-unverified rollout to audit output and excludes verified logical transcripts with NULL channel. A mixed-failure control also paired overlap status with an unrelated unknown reason. Added shared-helper admission after the existing schema gate, scoped group/count and deterministic status/reason controls, and the six declared delivery-blocking edges. Opus consult (`/ll:advise`, `claude-opus-5-5`, confidence 0.78) clarified NULL-value versus absent-schema scope; older pair-schema support is deferred. Existing focused reader/selector/lifecycle/version tests passed (86 tests); the new cases remain implementation regression requirements.
- Follow-up implementation-readiness review - 2026-10-05 - Kept the already specified conservative global ambiguity policy; Opus (`/ll:advise`, `claude-opus-5-5`, confidence 0.72) found no blocking design gap. Added the latent stored-reader channel-label mismatch exposed by NULL-channel admission, a retained-evidence integration control with BUG-3736, and explicit separation of retained-source admission from overlap acquisition. Existing focused selector/reader/refresh tests passed (38 tests); no implementation or new regression-test coverage is claimed.

## Resolution

- **Action**: fix
- `select_usage_coverage` now acquires the full usage population and classifies ambiguity over it; `host`/`session_id` only narrow returned rows (pair output reuses `_verified_usage_identity`; host-only keeps unverified host-attributed audit rows). Aggregate reason comes from groups with the winning status (lexical tie-break). `_compute_cache_rate_from_usage` channel labels now use `row_channel`.
- Tests: 7 new controls in `scripts/tests/test_enh3543_usage_coverage.py`; docs in `docs/reference/API.md`.
- Full suite: 28239 passed; unrelated failures — `test_verify_evidence` corpus gate (BUG-3738/ENH-3700 issue text) and `test_libsql_integration` live-endpoint errors.
