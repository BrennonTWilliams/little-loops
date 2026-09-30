---
id: FEAT-3686
type: FEAT
title: 'Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline
  ideas'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:35:03Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- spike
blocks:
- FEAT-3582
---

# FEAT-3686: Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline ideas

## Summary

One-day offline measurement spike over the preserved baseline ideas (`postmortems/brainstorm-baseline/fresh-20260929/*/ideas.jsonl`, 45 ideas per pinned brief) that tests the load-bearing, so-far-unmeasured claims of the EPIC-3581 design **before** the grid-dependent parts of FEAT-3667 and the FEAT-3582 loop rewrite are built. It doubles as the **common tagging pass** that FEAT-3582's merge gate and FEAT-3596's comparison both require, which removes the FEAT-3582 ↔ FEAT-3596 circular ownership.

_Created 2026-09-30 from the EPIC-3581 fifth pre-implementation review (`/ll:advise` with Opus, structural/process pass; nothing here has been measured yet)._

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

Four spec-detail reviews produced a large design (grid + occupancy steering, blind re-tag, LLM dedup, batched round-robin judging) whose first quality evidence would arrive only after FEAT-3667 (≈ 16 CLI commands) and the FEAT-3582 single-commit rewrite exist. Cells pervade `IdeaRecord`, shortlist, floors and portfolio, so a negative result found late forces rework in the module's core types. A ≈ 75-call replay is cheaper than that rework.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

Offline scripts only under `postmortems/brainstorm-spike/` (gitignored, source-repo-only; quotes run data). No changes to `brainstorm.yaml`, no new package code. Use the profile axes pinned in FEAT-3583 § Pinned Preset Contents (`artifact`: register × tone; `functional`: scope × approach) as the grid; the model is the one used for the baseline (`claude-sonnet-5-5`).

## Measurements and go/no-go thresholds

| # | Measurement | Method | Go threshold |
|---|-------------|--------|--------------|
| 1 | **Tagger self-agreement** | Tag every baseline idea twice in independent blind calls (no generator tag visible); compare cells | exact-cell agreement ≥ 0.6 **and** per-axis ≥ 0.75 |
| 2 | **Old-loop grid headroom** | Occupied cells of the old loop's ideas under the consensus tags (this is also FEAT-3596's "occupied cells" baseline) | ≤ 7 of 9 occupied per brief; otherwise the grid has no headroom to improve |
| 3 | **Occupancy-steering lift** | Re-run diverge for the same lenses with `diverge_state.md` (titles + per-cell occupancy) in the prompt; count occupied cells under the same tagger | ≥ +2 occupied cells vs. item 2 |
| 4 | **LLM dedup quality** | One dedup call over `{id, title, body excerpt}`; compare duplicate groups to human labels of a sample of ≥ 20 pairs (include paraphrases) | precision ≥ 0.8, recall ≥ 0.6 |
| 5 | **Batched-round judge consistency** | 8 finalists per brief; judge one round (4 disjoint pairs) per call vs. one pair per call; repeat with pair order swapped and with shuffled in-round order | swap-consistency ≥ 0.75; Kendall τ vs. per-pair ranking ≥ 0.6; top-1 stable in ≥ 2 of 3 orderings |

Also record: calls made, input/output/cache tokens per call, wall-clock per call (feeds FEAT-3596's `PRE_TOURNAMENT_WORST_S` and the token-ceiling in FEAT-3582).

## Outcomes and routing

- **All go** → FEAT-3667 proceeds unchanged; FEAT-3582 unblocked.
- **1 or 3 fails** (grid unreliable or no lift) → FEAT-3667/3582 drop the grid and blind re-tag: `cell` stays nullable, `min_cells`/wildcard-on-both-axes/occupancy steering are removed from the contract; shortlist becomes a plain dedup-then-cap. Record as a Review Decision in FEAT-3667/3582.
- **2 fails** (old loop already fills ≥ 8/9 cells) → the grid adds no measurable value; same routing as above.
- **4 fails** → keep the dedup state but do not rely on it for `min_ideas`; floors count pre-dedup ideas.
- **5 fails** → the tournament child judges one pair per call (calls ≈ C(N,2)) with `max_finalists` lowered to 6 and the budgets in FEAT-3582 § Tournament Specification re-derived from the measured latencies.

## Acceptance Criteria

- All five measurements are recorded in `postmortems/brainstorm-spike/RESULTS.md` (raw call outputs alongside) with the per-brief numbers and a go/no-go verdict per row.
- The consensus cell tags for both baselines' ideas are saved as the shared file FEAT-3582's merge gate and FEAT-3596's comparison read (`postmortems/brainstorm-spike/tags.jsonl`).
- The outcome routing above is applied: FEAT-3667/FEAT-3582/FEAT-3583 carry a Review Decision citing the results, and any dropped grid pieces are removed from their contracts.
- Latency/token figures are copied into FEAT-3596 for the timeout derivation and the token ceiling.

## Dependencies

- **Blocks**: FEAT-3582; FEAT-3667's grid-dependent commands/types (`ingest` cell normalization, `collapse` re-tag, `shortlist-apply`, `check-floors` `min_cells`, wildcard slot) — the grid-independent commands may start in parallel.
- Consumes: `postmortems/brainstorm-baseline/` (recorded 2026-09-29, SHA `2fe16824a`).

## Status

**Open** | Created: 2026-09-30 | Priority: P2
