---
id: BUG-3735
type: BUG
title: Scoped usage selection hides unverified overlap candidates
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T17:27:31Z'
parent: EPIC-3562
labels:
- observability
- usage-coverage
testable: true
relates_to:
- ENH-3730
- ENH-3731
- ENH-3732
- ENH-3733
---

# BUG-3735: Scoped usage selection hides unverified overlap candidates

## Summary

`select_usage_coverage` filters by `host`/`session_id` in SQL before checking cross-channel ambiguity. A sessionless live observation can therefore be excluded from a selected session even when it could duplicate that session's transcript; a live row without a verified host is also excluded by a host filter. The resulting scoped reader publishes `non_overlapping` where the unnarrowed acquisition population remains `overlap_unresolved`. Preserve possible counterparts during coverage analysis, then narrow returned rows to the requested host/session. This is a correctness repair; ENH-3730 separately evaluates whether verified overlap domains can safely recover availability.

## Current Behavior

A temporary-database probe on 2026-10-05 inserted a synthetic complete measured Claude transcript (`host_basis=handle`, session `session-a`) and a complete measured `live` row for the same host without a session identity. The unscoped and host-only selections both returned `overlap_unresolved`, reason `unverified_cross_channel_identity`, 2 audit rows and 0 selected rows. Selecting that host plus `session-a` returned `non_overlapping`, 1 audit row and 1 selected row. After clearing the live row's host, host-only selection also returned `non_overlapping`, 1 audit row and 1 selected row. These are synthetic contract probes, not captured native duplicates; without identity the selector cannot prove disjointness.

## Steps to Reproduce

1. Create a temporary history database through `ensure_db`, then insert two synthetic complete measured observations: a Claude transcript with verified source host and session `session-a`, and a same-host live observation with no session identity. Use input/output/cache-read/cache-creation values 10/2/4/0 on each.
2. Compare `select_usage_coverage(conn)` with `select_usage_coverage(conn, host="claude-code", session_id="session-a")`. The full selection is unresolved while the scoped result incorrectly certifies one selected observation.
3. Set the live observation's host to NULL and call `select_usage_coverage(conn, host="claude-code")`. The host filter now hides the wildcard and incorrectly certifies the transcript again.

## Expected Behavior

Compute ambiguity over the declared acquisition population before host/session output narrowing and before `since`/run filters. A missing/unverified host or session cannot establish that a possible opposite-channel counterpart lies outside the requested session. Returned audit/selected rows still contain only the requested verified host/session; wildcard evidence influences coverage without leaking into that session's totals. An ID-only call remains rejected. An explicitly declared logical `channel=` acquisition scope, once ENH-3731 adds it, is applied before ambiguity; it is a population choice, not proof of cross-channel disjointness.

Keep the existing conservative ambiguity policy for this repair. Do not infer disjointness from counts, timestamps, configured host strings or equal token values. Any narrower domain policy belongs to ENH-3730. Qualified historical/as-of values remain retained; a newly unresolved canonical rate becomes unavailable with a coverage reason rather than deleting observations or fabricating zero.

## Motivation

Host/session selection must not certify usage by hiding an unidentified possible duplicate. All six remaining-host delivery issues need this repaired selector before publishing usage or switching readers.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — separate acquisition and output narrowing; preserve identity verification and annotations.
- `scripts/tests/test_enh3543_usage_coverage.py` — sessionless same-host live and unknown-host wildcard controls; filter-order tests.
- `scripts/tests/test_enh3656_stored_cache_rate.py`, `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` — drive actual session readers where the existing fixture helpers apply; retain text/JSON as-of behavior and empty-vs-zero distinctions.
- `docs/reference/API.md`, `docs/reference/CLI.md` — clarify that host/session selection does not hide possible overlap and may make previously displayed rates unavailable.

### Dependent Files

- `scripts/little_loops/cli/ctx_stats.py` — stored reader consumes annotations and existing bounded coverage reasons.
- `scripts/little_loops/session_store/queries.py` — snapshot remains on the shared selector.

### Similar Patterns

- Existing `since`/`require_run_id` filters run after coverage reconciliation; host/session output selection needs the same completeness discipline.

### Tests

- Same-host sessionless live plus verified transcript: scoped selection remains unresolved.
- No verified host on live or replay counterpart: a host filter cannot remove its ambiguity influence.
- Fully verified disjoint session controls retain the existing result; same-session live/replay remains unresolved; unverified stored host strings cannot create isolation.
- A counterpart outside `since` or lacking a run ID still influences scoped coverage.
- Logical transcript-only acquisition (when ENH-3731 lands) excludes live/rollout as declared, without altering default cross-channel behavior.
- Scoped audit rows/counts never include a different host/session's usage merely because it influenced coverage.

### Documentation

- Reader-facing API/CLI coverage and unavailable-rate semantics; no source-DB schema change.

## Program Design

### Signatures

- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None) -> CoverageSelection` — keep current arguments and any ENH-3731 `channel` addition; separate full acquisition candidates from narrowed output rows.
- `select_usage_observations(...)` — continues delegating to the same selector and yielding annotated audit rows.

### Call Path

Stored usage → `select_usage_coverage` acquisition candidates (logical channel scope if supplied) → `_classify_coverage` with full-population ambiguity → verified host/session output selection → report-window/run filters → `CoverageSelection` → `select_usage_observations` and `_compute_cache_rate_from_usage` consumers.

## Implementation Steps

1. Reproduce both synthetic scoped-certification cases in selector tests.
2. Separate acquisition, coverage classification and output selection; preserve existing identity checks and the declared channel scope in either landing order with ENH-3731.
3. Exercise stored-session readers and source/snapshot controls; document the conservative availability change.
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
- [ ] Coverage is computed before host/session output narrowing and report-window/run filters; an ENH-3731 logical channel acquisition scope remains a distinct earlier population choice.
- [ ] Fully verified disjoint controls, same-session unresolved controls, audit subtotals, source/snapshot parity, historical retention and text/JSON unavailable-vs-zero behavior pass.
- [ ] No live/replay join, provenance promotion, price change, source re-derive or ENH-3730 availability optimization is introduced.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope**: scoped selection correctness and existing consumer/diagnostic regression tests.
- **Out of scope**: ENH-3730 overlap-domain optimization, ENH-3731 qualification policy, native host evidence, workspace additive-counting policy and source-history migrations.

## Related Key Documentation

- `docs/reference/API.md` — stored coverage selector.
- `docs/reference/CLI.md` — stored cache-rate output.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-10-05T17:36:12 - `b20687c5-3662-40c9-ac0d-0a4ae5fef8fe.jsonl`
- Pre-implementation epic review - 2026-10-05 - Captured the scoped overlap defect after Opus critique (confidence 0.74) and synthetic same-host/sessionless and no-host probe reproduction. Full selection is unresolved while host/session output narrowing falsely certifies it; ENH-3730 remains separate availability work.
