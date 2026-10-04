---
id: ENH-3703
type: ENH
title: Optional family-prefix pricing fallback with approximate cost flag
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:16Z'
parent: EPIC-3562
decision_needed: true
relates_to:
- BUG-3696
- BUG-3701
- ENH-3719
- BUG-3724
deferred_by: human
deferred_date: '2026-10-04T01:48:19Z'
deferred_reason: decision_unresolved
---

# ENH-3703: Optional family-prefix pricing fallback with approximate cost flag

## Summary

Decide whether unknown concrete model IDs should receive explicitly approximate family pricing after ENH-3719's missing-price footer has been tried. Retain this optional enhancement as a deferred child of EPIC-3562 for traceability; it does not block the other pricing or host implementation work. Before epic closure, settle the decision: if the footer is sufficient, cancel this issue with a rationale; otherwise record the permitted matching policy and implement it, or revise epic scope explicitly.

## Current Behavior

`estimate_cost_usd` uses exact model IDs. Unpriced IDs yield unavailable costs. BUG-3696 owns the exact Sonnet 5.5 rate; ENH-3719 owns the missing-price footer and cost-table documentation. Neither introduces approximate pricing.

## Expected Behavior

First evaluate whether the footer makes missing pricing actionable enough. If a fallback is justified, use a segment-boundary, longest-prefix rule within an explicitly permitted model family/major version and label every affected state/run figure approximate. An exact table entry always wins; unverified model aliases and cross-version guesses remain unavailable.

Approximate list-price estimates must never enforce a cost ceiling. Persisted `usage_events.cost_usd` remains exact-only because that field lacks approximate-price provenance. Exact-only stable report JSON remains unchanged; any approximate metadata has a tested round-trip contract.

## Motivation

A family estimate can differ substantially from a new model's actual rates, especially for cache-heavy runs. ENH-3719 may solve the visibility problem with less complexity. Defer this value decision until there is evidence that users need the estimate.

## Decision Needed

- **Cancel:** the footer identifies missing pricing adequately; maintain verified exact rates as models are added.
- **Implement:** record evidence of a remaining user need, permitted model families/versions, acceptable uncertainty, and the visible approximate label. Do not apply fallback to already priced Sonnet 5.5.

The `relates_to` link to ENH-3719 records the evaluation sequence; the deferred decision is reconsidered after the footer can be evaluated. BUG-3701's alias/rank changes are independent. Use status `cancelled` for the cancel decision, with its rationale.

## Proposed Solution

Only after the decision, add a separate approximate estimator/result used by `CostReport` while keeping `estimate_cost_usd` exact-only. Use segment boundaries (`model == key` or `model.startswith(key + "-")`) and the longest eligible prefix; explicit version policy prevents crossing a major version. Propagate an approximate flag/reason through state and total costs and JSON loading/writing. Cost ceilings use the unknown-cost path with reason approximate price.

## Program Design

### Types

- Proposed `ApproximateCost`: nullable cost, approximate flag, matched pricing key/reason. Existing `PerStateCost`/`CostReport` propagate approximate metadata only when applicable.

### Signatures

- `estimate_cost_usd_approx(model: str, *, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None, cache_creation_tokens: int | None, is_batch: bool = False) -> ApproximateCost` — proposed, if the fallback is approved.
- Existing `CostReport.from_usage_jsonl`, `CostReport.read_json`, and `_compute_totals` preserve the chosen metadata contract.

### Call Path

`CostReport.from_usage_jsonl` → exact estimator, then permitted approximate fallback → state/total approximate label → table/JSON. `FSMExecutor._check_cost_ceiling` treats approximate values as unavailable for enforcement.

## Integration Map

### Files to Modify

- `scripts/little_loops/pricing.py` — separate fallback result and matcher, if approved.
- `scripts/little_loops/fsm/cost_graph.py` — approximate state/total label and JSON round-trip.
- `scripts/little_loops/fsm/executor.py` — `_check_cost_ceiling` unknown-cost diagnostic.

### Dependent Files (Callers/Importers)

- Usage reporter and history report consumers where they display approximate cost. `session_store/writers.py` remains exact-only.

### Similar Patterns

- Existing unknown-cost propagation and ENH-3719's exact missing-price diagnostic. BUG-3724 owns mixed-model/batch attribution and is not folded into fallback pricing.

### Tests

- `scripts/tests/test_pricing.py`, `test_fsm_cost_graph.py`, `test_cost_ceiling_enforcement.py`, and reporter/round-trip tests. Exact keys and segment boundaries, longest eligible prefix, rejected version/family guesses, incomplete tokens, batch handling, and approximate ceilings need coverage.

### Documentation

- `docs/reference/CLI.md` and `docs/reference/API.md` — permitted fallback scope, uncertainty and labels, if implemented.

### Configuration

- No configuration option is assumed before the value/policy decision.

## Implementation Steps

1. After ENH-3719 lands, evaluate the footer and record implement/cancel evidence and permitted matching policy.
2. If cancelled, record the rationale and close; otherwise add the separate approximate result and narrowly allowed matcher.
3. Propagate approximation through reports and round-trips; keep stored usage exact-only and ceilings fail-closed.
4. Test exact-only parity, boundaries, uncertainty labels and ceilings; document the selected contract.

## Acceptance Criteria

- [ ] Implement/cancel decision is recorded after footer evaluation. It does not block other EPIC-3562 implementation; before epic closure, finish the approved work or cancel it with a rationale, unless the epic's scope is explicitly revised.
- [ ] If implemented, exact IDs win; segment-boundary longest-prefix and permitted version/family policy reject unsafe guesses. No family fallback replaces a verified exact Sonnet 5.5 price.
- [ ] If implemented, every affected state and run total is visibly approximate; metadata round-trips and exact-only `to_dict` output is unchanged.
- [ ] If implemented, incomplete/unpriced contributions remain unavailable as appropriate, stored `usage_events.cost_usd` remains exact-only, and approximate figures produce `cost_ceiling_unknown` rather than enforcing a guessed cost.
- [ ] If implemented, reporter/history labels and docs match the selected policy, and `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope:** optional fallback value decision, permitted matcher, approximation provenance, reports and ceiling protection if approved.
- **Out of scope:** exact Sonnet 5.5 pricing (BUG-3696), alias/rank changes (BUG-3701), footer/doc correction (ENH-3719), mixed-model attribution (BUG-3724), context windows and history backfill.

## Impact

- **Priority:** P4 — optional; first establish whether the footer leaves a useful problem to solve.
- **Effort:** Medium if implemented — matcher plus report provenance, round-trip and ceiling handling.
- **Risk:** Medium — inferred family rates can mislead cost decisions; explicit decision and labeling are required.
- **Breaking Change:** No exact-only output change; approximate metadata needs an explicit additive contract.

## Review Notes

2026-10-03: retained under EPIC-3562 at the user's direction and deferred pending ENH-3719 evaluation. Replaced copied, contradictory wiring notes with the actual optional scope and owners; no implementation is claimed.

## Related Key Documentation

- `docs/reference/CLI.md` — usage estimates and ceilings.
- `docs/reference/API.md` — pricing/report contracts.

## Status

**Open** | Created: 2026-10-02 | Priority: P4
