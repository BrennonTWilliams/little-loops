---
id: FEAT-3582
type: FEAT
title: 'Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:13Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
relates_to:
- FEAT-2248
---

# FEAT-3582: Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio

## Summary

Replace the body of `scripts/little_loops/loops/brainstorm.yaml` with the new core
engine (C + B + A from EPIC-3581): **reframe → grid-tagged diverge → script dedup →
per-cell shortlist → script-driven pairwise tournament → portfolio output**, with a
hard minimum-idea invariant. Removes difflib novelty, the saturation counter, and the
forced best-of hybrid.

## Current Behavior

- `dedup_novelty` uses difflib `SequenceMatcher` against `novelty_threshold: "0.55"`;
  observed max pairwise ratio across 45 ideas was 0.44, so nothing is ever deduped and
  `saturation_gate` never early-exits (evidence: transient run dirs under
  `.loops/runs/brainstorm-*`).
- Each `diverge` call sees only the brief, never prior ideas.
- `cluster` / `rank` / `converge` are single listwise LLM passes; `converge` always
  synthesizes a hybrid.
- `verify_artifacts` only checks `brainstorm.md` is non-empty, so a zero-idea run
  (07-01) whose report says "No synthesis produced" passes.

## Expected Behavior

1. `reframe` — generate N problem framings ("How might we…"), select 2–3 (skippable
   per profile).
2. `diverge` per framing × lens — prompt includes the running list of idea titles;
   each idea is emitted with a grid cell (2 axes) and a cluster tag.
3. `dedup` (script) — collapse ideas sharing cell + cluster tag; keep the richer one.
4. `shortlist` (script + LLM) — best idea per occupied cell.
5. `tournament` — script builds a Swiss/single-elim bracket over finalists; LLM
   judges batched pairs with position swapped; script tallies.
6. `portfolio` — winner, runner-up from a different cell, wildcard; hybrid only when
   `synthesize=true`.
7. `verify_artifacts` — fail when idea count < `min_ideas` or occupied cells <
   `min_cells`, not just on an empty report.

Sinks (`none|file|issue|decision`) keep their contract and read `winners` from the
portfolio.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Define the idea record schema and grid-cell tagging contract.
2. Rewrite states per Expected Behavior; reuse `lib/common.yaml` fragments
   (`parse_tagged_json`, `queue_pop`).
3. Write the tournament bracket/tally script inline (or as a small helper under the
   loop) with position-swap handling.
4. Tighten `verify_artifacts`.
5. Update tests and the loop's description/docs.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- difflib, `novelty_threshold`, `max_saturation`, `novelty_backend`, and
  `saturation.txt` are removed.
- A run with 0 ideas (e.g. forced empty diverge) routes to `failed`.
- Tournament bracket construction and scoring are deterministic shell/Python; only
  individual pair verdicts are LLM calls; each pair is judged in both orders.
- Output `brainstorm.md` presents a portfolio + the grid map; `ideas.jsonl` records
  `cell`, `cluster`, `framing`, `lens` per idea.
- `ll-loop validate brainstorm` passes; artifacts only under `${context.run_dir}/`.
- Existing brainstorm tests updated; new tests cover dedup-by-cell and the min-idea
  invariant.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:36 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
