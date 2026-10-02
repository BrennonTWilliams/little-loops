---
id: ENH-3703
type: ENH
title: Optional family-prefix pricing fallback with approximate cost flag
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:16Z'
parent: EPIC-3562
---

# ENH-3703: Optional family-prefix pricing fallback with approximate cost flag

## Summary

Optional follow-up to BUG-3696: when a model ID is absent from `MODEL_PRICING`, estimate cost from the nearest known family (segment-boundary longest-prefix match) and mark the figure approximate, instead of showing `n/a`.

## Current Behavior

`estimate_cost_usd` is exact-key only; any unknown model yields `None` and `n/a` in the `ll-loop` usage table. BUG-3696 adds an unpriced-model footer so the gap is visible but supplies no number.

## Expected Behavior

An unknown ID with a known family prefix is priced at the family's rate, flagged approximate (`~$X.XXXX`), with the following constraints from the advisor review:

- **Segment-boundary matching only** (`model == key` or `model.startswith(key + "-")`); never `claude-fable-5-1` pricing `claude-fable-5-10`; longest key wins; never crosses a major version.
- **Accuracy caveat:** minor versions are priced differently (`claude-opus-5-5` input $4 vs `claude-opus-5` $5; `claude-fable-5-1` cache read $0.25 vs `claude-fable-5` $1.00); loop runs are cache-heavy, so a fallback figure can be 20–75% off. Decide whether that is acceptable before implementing; the BUG-3696 footer may be enough.
- Apply only in `fsm/cost_graph.py`; keep `session_store/writers.py` exact-only (`usage_events.cost_usd` has no provenance column).
- `executor._check_cost_ceiling` must treat approximate cost as unknown and emit `cost_ceiling_unknown` (reason "approximate price"), so ceilings never abort on an invented figure.
- `PerStateCost.approximate` emitted in `to_dict` only when True and read back in `CostReport.read_json`; `_compute_totals` aggregates it.
- Deferred wiring/research notes live in BUG-3696 (Integration Map scope-revision banner and Codebase Research Findings).

## Motivation

Models ship every few weeks, and each release blanks cost until the table is edited; a flagged estimate beats `n/a` for most users — provided it is not misleading. Split out of BUG-3696 as optional work; close as won't-do if the footer proves sufficient.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] Decision recorded: implement the fallback or close as won't-do (given the 20–75% accuracy caveat)
- [ ] If implemented: segment-boundary longest-prefix matcher with tests (`claude-fable-5-10` does not match `claude-fable-5-1`; exact keys and dated IDs are not shadowed)
- [ ] If implemented: `_check_cost_ceiling` treats approximate costs as unknown, with a `test_cost_ceiling_enforcement.py` case
- [ ] If implemented: `approximate` round-trips through `write_json` / `read_json`; `to_dict` stays byte-identical for exact-only data
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

**Open** | Created: 2026-10-02 | Priority: P4
