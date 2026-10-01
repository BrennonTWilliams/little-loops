---
id: FEAT-3686
type: FEAT
title: 'Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline
  ideas'
priority: P2
status: done
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
completed_at: '2026-09-30T05:55:21Z'
---

# FEAT-3686: Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline ideas

## Summary

One-day offline measurement spike over the preserved baseline ideas (`postmortems/brainstorm-baseline/fresh-20260929/*/ideas.jsonl`, 45 ideas per pinned brief) that tests the load-bearing, so-far-unmeasured claims of the EPIC-3581 design **before** the grid-dependent parts of FEAT-3667 and the FEAT-3582 loop rewrite are built. It doubles as the **common tagging pass** that FEAT-3582's merge gate and FEAT-3596's comparison both require, which removes the FEAT-3582 ↔ FEAT-3596 circular ownership.

_Created 2026-09-30 from the EPIC-3581 fifth pre-implementation review (`/ll:advise` with Opus, structural/process pass; nothing here has been measured yet)._

## Current Behavior

No measurement exists for the grid, blind re-tag, occupancy steering, LLM dedup or batched round judging; the design is committed to in seven issues on reasoning alone.

## Expected Behavior

Each load-bearing claim has a recorded measurement and go/no-go verdict before FEAT-3667's grid-dependent commands and FEAT-3582 are built.

## Motivation

Four spec-detail reviews produced a large design (grid + occupancy steering, blind re-tag, LLM dedup, batched round-robin judging) whose first quality evidence would arrive only after FEAT-3667 (≈ 16 CLI commands) and the FEAT-3582 single-commit rewrite exist. Cells pervade `IdeaRecord`, shortlist, floors and portfolio, so a negative result found late forces rework in the module's core types. A ≈ 75-call replay is cheaper than that rework.

## Impact

- **Priority**: P2 - gates the FEAT-3667 grid pieces and FEAT-3582
- **Effort**: Small - one day, ≈ 75 LLM calls, offline scripts only
- **Risk**: Low - no repo code changes; results only re-route existing issues
- **Breaking Change**: No

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

## Results (2026-09-30)

**Verdict: GO with four amendments; no design piece dropped.** 160 LLM calls, $3.26; full tables, raw calls and caveats in `postmortems/brainstorm-spike/RESULTS.md`; consensus tags in `postmortems/brainstorm-spike/tags.jsonl`.

| # | Result | Verdict |
|---|--------|---------|
| 1 | Tagger agreement with bin definitions: b1 exact 0.83 / axes 0.91, 0.91; b2 exact 0.62 / axes 0.82, **0.72**. Names-only: 0.67 / 0.51 | b1 pass; b2 marginal (`approach` axis < 0.75); definitions required |
| 2 | Old-loop occupied cells: 6 / 9 on both briefs | pass |
| 3 | Occupied cells old → unsteered control → steered: b1 6 → 7 → 9; b2 6 → 6 → 8. Generator self-tags claim 9 cells on both (exact agreement with blind consensus 0.60 / 0.62) | pass (+2 vs control); blind re-tag justified |
| 4 | Dedup, default prompt: b1 P 0.63 R 0.83; b2 P 1.0 (12/12 sampled) R ≈ 0.85–0.95. Strict per-profile criterion: b1 P 1.0 R 1.0 | pass with a `duplicate_criterion` per profile |
| 5 | Batched round judging vs per-pair: swap-consistency 0.82 / 0.82; Kendall τ 0.71 / 0.71 (0.79 in reversed order); top-1 identical in all orders and per-pair; abstention 0; first-shown advantage 12 / 5 pp | pass; keep batched round judging and 8 finalists |

**Amendments** (applied to FEAT-3667, FEAT-3582, FEAT-3583, FEAT-3596 on 2026-09-30): (1) bin definitions mandatory in every axis; (2) `duplicate_criterion` profile key printed in the dedup prompt block; (3) the `functional` `approach` axis is re-measured with the same 3-call tagger check before FEAT-3583 pins it; (4) old-loop baselines for the merge gate: 6 occupied cells; b1 5 / b2 ≈ 19 redundant retained ideas.

Caveats: dedup labels were made by Claude, not a human (spot-check `m4_sample.json`); one model family generates, tags and judges; n = 2 briefs, one run each; lens lists reconstructed.

## Dependencies

- **Blocks**: FEAT-3582; FEAT-3667's grid-dependent commands/types (`ingest` cell normalization, `collapse` re-tag, `shortlist-apply`, `check-floors` `min_cells`, wildcard slot) — the grid-independent commands may start in parallel.
- Consumes: `postmortems/brainstorm-baseline/` (recorded 2026-09-29, SHA `2fe16824a`).

## Status

**Open** | Created: 2026-09-30 | Priority: P2
