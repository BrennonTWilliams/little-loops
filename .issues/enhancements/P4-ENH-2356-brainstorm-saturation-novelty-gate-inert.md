---
id: ENH-2356
priority: P4
type: ENH
status: open
discovered_date: 2026-06-27
discovered_by: audit-loop-run
confidence_score: 80
---

# ENH-2356: brainstorm saturation/novelty early-stop gate is inert in practice

## Summary

In the `brainstorm` built-in loop, the saturation-based early-stop convergence
path is effectively dead: the difflib novelty dedup never flags duplicates, so
the saturation counter never increments, so `saturation_gate` always routes
"continue." Termination comes solely from exhausting the finite lens queue. The
`max_saturation` contract is a safety net that never engages.

## Motivation

Audited via `/ll:audit-loop-run brainstorm` on run `2026-06-27T214631` (verdict:
`met` — the run was otherwise healthy). Evidence from that run:

- 9 lenses × `ideas_per_round=5` = **45 ideas**, and difflib dedup
  (`novelty_threshold=0.80`) removed **0 of 45**.
- `saturation.txt` stayed at `0` for the entire run (`count = 0 if novel else
  count + 1`, and every round had ≥1 "novel" idea).
- `saturation_gate` (`output_numeric`, `lt ${context.max_saturation}`) therefore
  evaluated `0 < 2 → yes → pop_lens` on every iteration. The loop only stopped
  because `pop_lens` drained the lens queue (`on_no → cluster`).

Root cause: a `0.80` difflib `SequenceMatcher.ratio()` on differently-worded
one-sentence ideas almost never reaches threshold, so the dedup pass admits
nearly everything as "novel." This makes the saturation early-stop and the
configured `max_saturation` contract decorative — convergence relies entirely on
the finite lens list.

This is not a correctness bug (finite lenses guarantee termination), but it means
two configured knobs (`novelty_threshold`, `max_saturation`) do not influence
behavior, which is misleading to anyone tuning the loop.

Distinct from ENH-2251 (done), which added `saturation_gate → on_error: cluster`
resilience routing — that fixed the error path, not the inert-gate behavior.

## Proposed Solution

One or more of:

1. Lower the default `novelty_threshold` (e.g. to ~0.55) so paraphrase-level
   duplicates actually register and saturation can build.
2. Wire the configured `novelty_backend` to a semantic comparator (embeddings)
   so dedup measures meaning rather than string overlap, letting the
   `max_saturation` early-stop engage on genuinely repeated ideas.
3. If lens-exhaustion is intended as the sole convergence mechanism, document
   `max_saturation` as a pure safety net and consider removing the
   `novelty_threshold`/`max_saturation` knobs from the advertised contract to
   avoid implying they tune output.

## Acceptance Criteria

- [ ] A brainstorm run over a brief with overlapping idea space records ≥1
      duplicate removed in `ideas.jsonl` (dedup demonstrably fires), OR
- [ ] The loop's documented contract accurately reflects which knobs affect
      convergence.
