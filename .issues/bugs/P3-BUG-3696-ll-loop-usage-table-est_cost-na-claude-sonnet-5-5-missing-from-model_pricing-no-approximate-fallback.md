---
id: BUG-3696
type: BUG
title: 'll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING,
  no approximate fallback'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:30Z'
parent: EPIC-3562
---

# BUG-3696: ll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING, no approximate fallback

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for every state because the run's model, `claude-sonnet-5-5`, has no entry in `MODEL_PRICING`. The tool should estimate at API list prices regardless of how the user is billed (subscription or API key), and an unrecognized model ID should degrade to a flagged estimate rather than blanking the column.

## Current Behavior

Run `refine-to-ready-issue-20261002T111524` (model `claude-sonnet-5-5`, as recorded in `usage.jsonl`) printed `est_cost` = `n/a` for all five states. Cause chain:

1. `scripts/little_loops/pricing.py` `MODEL_PRICING` has `claude-sonnet-5` but no `claude-sonnet-5-5` (it does have `claude-opus-5-5` and `claude-fable-5-1`). Verified: `estimate_cost_usd("claude-sonnet-5-5", ...)` returns `None`, while `claude-sonnet-5`, `claude-opus-5-5` and `claude-fable-5-1` all price.
2. `estimate_cost_usd` returns `None` on any unknown model; `fsm/cost_graph.py` (`from_usage_jsonl`) then sets `has_unknown_model`, and `PerStateCost.table_row` renders `n/a`.
3. Because cost is `None` whenever any contributor is unpriced, one unknown model blanks the per-state cost and the run-wide total (`_compute_totals`). The same gap leaves null `cost_usd` rows in `usage_events` (see the FEAT-3183 note in `pricing.py`).

## Expected Behavior

- `claude-sonnet-5-5` is priced at its published API rate.
- Cost is shown even when the host is on a subscription: this is an API-price estimate, not a billed amount.
- A model ID absent from the table falls back to the closest known family (longest-prefix match, e.g. `claude-sonnet-5-5` -> `claude-sonnet-5`) and the table marks the figure as approximate (e.g. `~$0.1234`), rather than `n/a`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

1. Add `claude-sonnet-5-5` to `MODEL_PRICING` using the current published rate (confirm against the Anthropic pricing page; do not copy `claude-sonnet-5`'s rate by assumption, since `claude-opus-5-5` and `claude-fable-5-1` differ from their predecessors).
2. Add a family-prefix fallback in `estimate_cost_usd` (or a sibling helper) that returns an estimate plus an `approximate` flag; thread the flag through `PerStateCost` / `CostReport.to_dict` and render a `~` prefix in `table_row`. Keep the stable-JSON shape change additive.
3. Add a test that fails when a model ID the harness can emit (`claude-<family>-<major>[-<minor>]` from the host runner's model map) has no price entry, so a new model cannot silently regress to `n/a`.
4. Verify `ll-history quality`'s cost-coverage gate treats approximate rows distinctly from exact ones.

## Integration Map

### Files to Modify
- `scripts/little_loops/pricing.py` - `MODEL_PRICING`, `estimate_cost_usd`
- `scripts/little_loops/fsm/cost_graph.py` - `PerStateCost`, `table_row`, `from_usage_jsonl`, `_compute_totals`
- `docs/reference/API.md` - pricing / cost-report notes if the JSON shape gains a field

### Tests
- `scripts/tests/` pricing and `cost_graph` tests; new price-coverage test

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 - cosmetic for the user, but also leaves null `cost_usd` rows in history
- **Effort**: Small
- **Risk**: Low

## Acceptance Criteria

- [ ] `estimate_cost_usd("claude-sonnet-5-5", ...)` returns a float at the published rate
- [ ] A model ID with no table entry but a known family prefix yields an approximate estimate, not `None`
- [ ] `ll-loop run` usage table shows `$X.XXXX` (or `~$X.XXXX` when approximate) for the ENH-3678 `usage.jsonl`; no `n/a` for a known family
- [ ] A test fails if a model ID emitted by the harness lacks a price entry
- [ ] `python -m pytest scripts/tests/` exits 0

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`
