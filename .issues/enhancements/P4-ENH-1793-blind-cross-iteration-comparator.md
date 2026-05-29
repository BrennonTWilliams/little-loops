---
id: ENH-1793
type: ENH
priority: P4
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: open
labels: [enhancement, loops, evaluator, regression-detection]
---

# ENH-1793: Blind Cross-Iteration Comparator

## Summary

Add a `check_comparator` evaluator that performs an anonymized A/B comparison between the current iteration's output and a previously-successful output stored in `.loops/runs/<loop>/baseline/`. Catches *quality regressions* that the absolute `check_semantic` YES/NO judge misses — outputs that still pass the threshold but are objectively worse than what the harness produced before.

## Motivation

Our current `check_semantic` evaluator is *absolute*: it grades each iteration's output against a fixed prompt and routes on YES/NO. This is fine for catching catastrophic failures but blind to gradual degradation. A run that returns "summary is reasonable" YES on a one-paragraph stub *and* on a three-paragraph well-cited revision treats them as equivalent.

`revfactory/harness`'s "Comparator" agent (`references/skill-testing-guide.md` §5-2) addresses this with *blind A/B* — two outputs anonymized as A and B, judge picks which is better. This is a different signal from absolute scoring:
- Absolute judge: "Is this acceptable?" (binary, threshold-based)
- Comparator: "Is this better than what we had?" (ordinal, drift-detecting)

Use it to catch regressions when refining harness prompts, models, or skills.

This depends on having a reliable previous baseline to compare against. Sequencing: ship FEAT-1790 (A/B baseline) and ENH-1792 (variance diagnostics) first — both produce the data this evaluator consumes. Hence P4.

## Use Case

A harness author updates a `check_semantic` prompt to be "less strict" because too many runs were failing. Subsequent runs all pass — but the outputs are now visibly worse. With a comparator gate:

```yaml
check_comparator:
  action_type: comparator
  baseline_path: ".loops/runs/harness-refine-issue/baseline/"
  evaluate:
    type: comparator
    prompt: >
      Which output better satisfies the refinement criteria —
      A or B? Consider depth of analysis, codebase grounding,
      and concrete actionability.
  on_yes: advance      # current beats baseline → advance, update baseline
  on_no: execute       # baseline still better → retry
```

The judge sees both outputs labelled only `A` and `B` (random shuffle per call) without knowing which is the new candidate. If the new output wins on majority of pairs across N items, baseline gets refreshed; otherwise the harness is flagged as having regressed.

## API/Interface

New evaluator kind:

```yaml
evaluate:
  type: comparator
  baseline_path: <dir>          # where prior successful outputs live
  prompt: <comparison criteria> # the judge's question
  min_pairs: 3                  # require N comparisons before deciding
```

Verdicts:
- `yes` — current wins ≥ majority of pairs
- `no` — baseline wins majority
- `tie` — within noise threshold (route same as `yes` to avoid stalling)
- `no_baseline` — first run with no prior to compare against (route same as `yes` to bootstrap)

Baseline management: on `yes`, optionally promote current outputs to baseline (configurable `auto_promote: true|false`). Manual promotion via `ll-loop promote-baseline <loop>`.

## Implementation Steps

1. **Baseline storage convention** — `.loops/runs/<loop>/baseline/<item_id>.txt` (or similar). Document in run-directory schema.
2. **Comparator evaluator** — new module in `scripts/little_loops/evaluators/`. Reads baseline + current output, randomly shuffles labels, calls host runner with comparison prompt, parses YES/NO/TIE.
3. **Schema** — extend `ll-loop validate` to accept `action_type: comparator` and required `baseline_path`.
4. **Baseline lifecycle** — `auto_promote` config + `ll-loop promote-baseline <loop>` CLI for manual control.
5. **Tests** — pytest cases: current-wins, baseline-wins, tie, no-baseline (bootstrap), shuffle correctness (judge never sees consistent labelling).
6. **Docs** — add to `AUTOMATIC_HARNESSING_GUIDE.md` Evaluation Phases, placement guidance: after `check_semantic` (or replacing it for regression-sensitive harnesses).

## Acceptance Criteria

- [ ] Comparator evaluator runs against `baseline_path` files, returns yes/no/tie/no_baseline
- [ ] Label shuffling verified (judge prompt is symmetric in A/B)
- [ ] First-run bootstrap path works (no baseline → auto-promote current)
- [ ] `auto_promote` and manual `ll-loop promote-baseline` both functional
- [ ] Tests cover all four verdict cases plus shuffle correctness
- [ ] Docs updated with use case and placement guidance

## Out of Scope

- Multi-baseline support (comparing against N prior successful runs) — single baseline is sufficient for v1.
- Auto-rollback to baseline on regression — this evaluator only signals; rollback is a separate concern.
- Tournament-style multi-iteration brackets — single A/B per iteration only.

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | New evaluator slots into the documented chain |
| `.issues/features/P2-FEAT-1790-ab-baseline-mode-for-ll-loop-run.md` | Sibling A/B work — that one produces with/without baselines; this consumes prior-success baselines |
| `.issues/enhancements/P3-ENH-1792-detect-non-discriminating-evaluators-from-history.md` | Variance diagnostics that motivate having a regression-sensitive gate |

## Session Log
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open
