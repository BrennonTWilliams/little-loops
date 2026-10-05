---
id: ENH-3730
type: ENH
title: Narrow the store-wide cross-channel ambiguity gate to per-group coverage scope
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T02:23:16Z'
parent: EPIC-3562
decision_needed: true
testable: true
relates_to:
- ENH-3723
- ENH-3731
- ENH-3732
- ENH-3733
- ENH-3543
- BUG-3735
---

# ENH-3730: Narrow the store-wide cross-channel ambiguity gate to per-group coverage scope

## Summary

Decide whether verified overlap domains can safely narrow `select_usage_coverage`'s global ambiguity gate enough to justify implementation. Independent `_coverage_key` groups alone do not prove disjointness: a sessionless live observation could duplicate a verified transcript group. Preserve wildcard uncertainty and the full requested population. BUG-3735 separately repairs output narrowing that currently hides possible counterparts; this enhancement must compose with that fix rather than reintroduce it.

## Current Behavior

`select_usage_coverage` computes `ambiguous_cross_channel` over its acquired rows: live plus non-live channels are present and any row lacks verified identity. Every group is then unresolved. The original 2026-10-04 local-store probe found all 20,045 groups unresolved across 517,222 rows; that is a dated observation, not a current count.

A read-only 2026-10-05 distribution check found 295 live rows: 33 with no verified host, 262 with a verified invocation host but no proved session identity, and none with a verified host/session pair. `row_host_verified` treats an observed live invocation host as verified even without replay `host_basis=handle`; replay requires that marker. Under the conservative domain proposal, the 33 host-wildcard rows still taint possible opposite-channel groups store-wide. Narrowing domains therefore does not promise numeric all-history totals on this store.

BUG-3735 reproduced a distinct correctness defect: host/session SQL filtering drops wildcard counterparts before ambiguity is checked. This issue must not use the already-scoped reader as proof that those rows are independent.

## Expected Behavior

Narrow ambiguity only where retained evidence proves that observations cannot overlap. Unresolved contributors remain in completeness accounting and blank any full aggregate containing them; selected-group subtotals are audit figures, not a full-store canonical total. No counts, timestamps, order, configured-host names or equal values establish native identity.

Preserve the declared ENH-3731 logical `channel=` acquisition scope. Determine overlap from that population before host/session output selection and report filters (`since`, run attribution). The quality report's transcript-only acquisition is separate from a claim that transcript/live channels are disjoint.

## Decision Needed

1. **Implement conservative domains** only if fixture/aggregate-level evidence demonstrates a useful recovered figure while every same-host/session and unknown-host wildcard control remains unresolved. Record that measured benefit and the algorithm before coding.
2. **Retain the global gate and defer/cancel this enhancement with a rationale** if wildcard evidence makes it a no-op or the benefit does not justify complexity. This does not waive BUG-3735 or shared qualification, and does not block host capture or production publication after those correctness gates pass.

The 2026-10-05 distribution above is the baseline. Do not implement the discarded “each group is independent, ignore unrelated unidentified rows” shortcut. Until this decision is recorded, `decision_needed: true` remains; an issue-file review is not an implementation-readiness pass.

## Proposed Solution

The only admissible narrowing policy is conservative potential-overlap domains:

- A verified host/session pair can be independent of a different verified host or a different **verified** session. An unverified session ID never isolates an observation.
- A row with verified host but absent/unproved session is a wildcard across potential opposite-channel groups of that host. A row without verified host is a wildcard across hosts. Unverified replay host strings are not a verified-host boundary.
- Same verified-session live/replay or other cross-channel groups retain the existing unresolved reasons unless a native join separately proves coverage; no such join is introduced here.
- Preserve the existing Codex invocation-scope, live-identity and rollout-native-request prerequisites. Domain independence cannot upgrade an otherwise unknown group to measured or canonical.
- Apply group/domain classifications to all requested contributors, retaining unknown/unresolved annotations. Whole-selection and model aggregates still use the worst in-population coverage, not a sum of only selected rows.
- Build bounded host/channel/domain summaries in a pass over acquired rows; avoid pairwise comparisons or per-group scans of a large store. No persistent graph/index or source migration is assumed.

## Program Design

### Signatures

- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None, channel=None) -> CoverageSelection` — the `channel` argument is ENH-3731's planned acquisition scope; keep its semantics in either landing order. Refine only ambiguity classification after the decision.
- `_verified_usage_identity`, `_coverage_key`, `_classify_coverage` in `history_reader/usage.py` — reuse existing verification and unknown/unresolved prerequisites; do not treat key separation as proof against wildcard rows.

### Call Path

`select_usage_coverage` acquisition population → `_verified_usage_identity` and wildcard summaries → `_classify_coverage` for the full population → host/session output selection → report-window/run filtering → `CoverageSelection` annotated audit/selected rows → `select_usage_observations` → shared qualification and source/snapshot/session readers.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — ambiguity domains and stable classification reasons, if approved.
- `scripts/tests/test_enh3543_usage_coverage.py` — verified disjoint, same-session and wildcard fixtures; filter order and aggregate completeness.
- `scripts/tests/test_enh3543_snapshot_usage.py`, `scripts/tests/test_enh3656_stored_cache_rate.py`, `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` — source/snapshot/stored-reader parity where existing helpers apply.
- `docs/reference/API.md`, `docs/reference/CLI.md` — explain which scopes can recover figures and why all-history figures may remain unavailable.

### Dependent Files

- `scripts/little_loops/token_provenance.py` — shared qualification remains authoritative.
- `scripts/little_loops/session_store/queries.py`, `scripts/little_loops/cli/ctx_stats.py` — consume annotations; no consumer-local scope exception.
- `scripts/little_loops/issue_history/agent_quality.py` — transcript-only quality population is unaffected.

### Similar Patterns

- Existing verified-host/thread grouping and post-reconciliation `since`/run filters; BUG-3735 separates acquisition from output narrowing.

### Tests

- Unverified/sessionless live evidence for host A cannot certify A's verified transcript; an independently verified host B can recover only if no host-wildcard evidence remains.
- A no-verified-host row conservatively taints every possible opposite-channel host group; a configured host string does not bypass this.
- Different verified sessions remain independent; same-session live/replay is unresolved, and Codex unknown prerequisites remain unknown.
- Wildcards outside `since` or without run attribution still influence coverage; host/session output filtering cannot hide them.
- A recovered selected group plus an unresolved requested group never yields a full canonical subtotal; model and whole-selection aggregation retain completeness.
- Default unscoped, declared transcript acquisition, source/snapshot and stored-session results obey one policy; repeated calls and insertion-order permutations agree.

### Documentation

- Reader-facing API/CLI domain, scope and unresolved-aggregate semantics; no new configuration knob.

## Implementation Steps

1. Record the implement/defer/cancel decision using the current distribution and a representative recovered-group fixture; specify which aggregate actually benefits.
2. If approved, implement conservative summaries and compose with BUG-3735/ENH-3731 filter order in either landing order.
3. Drive source/snapshot/session consumers through wildcard, verified-disjoint, unresolved and filtered populations; document expected remaining blanks.
4. Run `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] An implement/defer/cancel decision records measured benefit and the conservative domain rule; the live distribution and affected figure are evidence, not a promise of restored all-history totals.
- [ ] If implemented, verified host/session independence never isolates unknown-host or same-host unproved-session wildcards; same-session cross-channel and Codex scope/request prerequisites remain intact.
- [ ] If implemented, acquisition precedes full-population ambiguity; host/session output, `since` and run filters cannot erase possible counterparts. Declared channel scope remains separate.
- [ ] If implemented, unresolved requested contributors blank full/model canonical figures while labeled audit subtotals remain; no selected-subset canonical sum, timestamp/count join or provenance promotion appears.
- [ ] Source/snapshot/stored-reader and insertion-order controls pass; no persistent domain subsystem or quadratic store scan is required.
- [ ] If implemented, `python -m pytest scripts/tests/` exits 0. A deferred/cancelled disposition explains remaining scope in the epic ledger.

## Impact

- **Priority**: P3 — possible availability improvement; BUG-3735 owns correctness.
- **Effort**: Medium if justified — bounded domain summaries and consumer controls.
- **Risk**: Medium — unjustified key-based isolation would certify possible duplicates; conservative wildcards may leave this enhancement with little benefit.

## Scope Boundaries

- **In scope**: evidence/value decision and safe ambiguity-domain narrowing if approved.
- **Out of scope**: BUG-3735 scoped-selection repair, ENH-3731/3732/3733 qualification, native live/replay joins, provenance promotion, pricing and source migrations. This enhancement is not a production-publication prerequisite.

## Related Key Documentation

- `docs/reference/API.md` — stored coverage selector.
- `docs/reference/CLI.md` — canonical versus audit figures.

## Status

**Open — decision needed** | Created: 2026-10-05 | Priority: P3

## Session Log

- Pre-implementation epic review - 2026-10-05 - Opus critique (confidence 0.74) rejected independent-group certification without wildcard domains. Added a concrete decision/design/integration/test contract and the read-only live distribution (33 host-wildcard, 262 verified-host/unproved-session, no verified-host/session live rows). Kept BUG-3735 correctness separate and recorded uncertainty about availability benefit.
- `/ll:capture-issue` - 2026-10-05T02:23:32 - `dd4da702-03cb-4aad-8b85-189a7f98afba.jsonl`
