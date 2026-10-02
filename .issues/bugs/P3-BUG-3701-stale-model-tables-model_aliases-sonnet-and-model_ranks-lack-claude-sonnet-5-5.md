---
id: BUG-3701
type: BUG
title: 'Stale model tables: MODEL_ALIASES sonnet and MODEL_RANKS lack claude-sonnet-5-5'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:15Z'
parent: EPIC-3562
---

# BUG-3701: Stale model tables: MODEL_ALIASES sonnet and MODEL_RANKS lack claude-sonnet-5-5

## Summary

`MODEL_ALIASES['sonnet']` in `scripts/little_loops/host_runner.py` still resolves to `claude-sonnet-5`, and `MODEL_RANKS["claude-code"]` in `scripts/little_loops/advisor.py` has no `claude-sonnet-5-5`, although real runs now report `claude-sonnet-5-5` (observed in `usage.jsonl` for run `refine-to-ready-issue-20261002T111524`).

## Current Behavior

- `resolve_model_alias("sonnet")` returns `claude-sonnet-5` while the host actually runs `claude-sonnet-5-5`.
- `advisor.rank_model("claude-sonnet-5-5")` has no rank entry, so advisor capability-floor comparisons treat the model as unranked.
- `context_window.MODEL_CONTEXT_WINDOW` should be checked for the same gap.

## Expected Behavior

The alias, rank and context-window tables cover every model ID the repo itself names or the hosts report. Decide deliberately whether `sonnet` should now alias to `claude-sonnet-5-5` and where `claude-sonnet-5-5` ranks relative to `claude-sonnet-5` and the Opus entries.

## Motivation

Split out of BUG-3696 (advisor review, 2026-10-02): it affects advisor ranking and alias resolution, not pricing, so it must not ride along with the pricing fix. Related: BUG-3696's price-coverage test pins `MODEL_ALIASES` / `MODEL_RANKS` / `MODEL_CONTEXT_WINDOW` against `MODEL_PRICING`, so any model added here also needs a price entry.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. `python -c "from little_loops.advisor import rank_model; print(rank_model('claude-sonnet-5-5'))"` — observe the unranked result.
2. `python -c "from little_loops.host_runner import resolve_model_alias as r; print(r('sonnet'))"` — observe `claude-sonnet-5`.

## Acceptance Criteria

- [ ] `MODEL_RANKS["claude-code"]` ranks `claude-sonnet-5-5` (rank relative to neighbours stated in the change)
- [ ] The `sonnet` alias target is decided and documented (keep `claude-sonnet-5` or move to `claude-sonnet-5-5`)
- [ ] `MODEL_CONTEXT_WINDOW` covers `claude-sonnet-5-5` or the issue records why not
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

**Open** | Created: 2026-10-02 | Priority: P3
