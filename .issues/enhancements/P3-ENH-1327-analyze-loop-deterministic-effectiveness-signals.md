---
id: ENH-1327
type: ENH
priority: P3
captured_at: "2026-05-02T19:05:00Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# ENH-1327: Add Deterministic Effectiveness Signals to `/ll:analyze-loop`

## Summary

Extend `/ll:analyze-loop`'s Step 3 signal classifier with five new **rule-based** signals that catch effectiveness problems without requiring artifact inspection or LLM judgment. These complement (not replace) the LLM-heavy effectiveness audit being added as `/ll:assess-loop` (FEAT-1325) and the `from:`/fragment/sub-loop resolution work (ENH-1326).

## Motivation

The current signal set is purely fault-oriented: action failure, SIGKILL, FATAL_ERROR, retry flood, slow state, evaluate failure. Loops can run cleanly through every one of those checks while still failing to do their job. The five signals below are detectable purely from the resolved YAML plus event history — no model calls, no artifact reads — so they belong in the cheap rule-based skill, not the reasoning-heavy assessor.

## Proposed Signals

### 1. Iteration-1 Convergence with No Apply

- **Trigger**: loop terminated with `iteration_count == 1` AND a state matching the apply/refine pattern (`apply_*`, `refine_*`, `update_*`, `write_*`, `commit_*`) was never visited.
- **Priority**: P3
- **Title**: `"<loop_name> converged on iteration 1 without entering apply/refine state — likely phantom convergence"`
- **Catches**: `apo-textgrad` model emitting `CONVERGED` from `compute_gradient` without ever firing `apply_gradient`.

### 2. Degenerate Gate

- **Trigger**: an `evaluate` state's `route` event distribution shows >95% to a single branch across ≥10 evaluations within the same run, OR ≥20 evaluations across the most recent 5 runs.
- **Priority**: P3
- **Title**: `"<state> route fan-out is degenerate (<N>/<M> evaluations took <branch>)"`
- **Catches**: `refine-to-ready-issue.check_outcome` always routing to `breakdown_issue` when the outcome rubric is too strict.

### 3. Stub Action Detection

- **Trigger**: a state's `action` body matches one of:
  - `^echo "\d+"$` in a state whose name contains `score`, `evaluate`, `judge`, `reward`
  - `^echo "Replace.*"$` or `^echo "TODO.*"$` in any state
  - `^echo "[A-Z_]+"$` (literal verdict echo) in a state whose `evaluate.type` is `output_string`
- **Priority**: P2
- **Title**: `"<state> action is a stub (<echo body>) — loop ships unimplemented"`
- **Catches**: `rl-rlhf` template's `echo "5"` in `score` and `echo "Replace with..."` in `generate`/`refine`. This is a static check at Step 2 (config-time), not history-driven.

### 4. Capture Vacuum

- **Trigger**: a downstream state's `action` or `evaluate.source` references `${captured.X.output}` AND the producing event for capture `X` shows empty/whitespace output in >20% of occurrences within the analyzed window.
- **Priority**: P3
- **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`
- **Catches**: `examples-miner` chained captures (`harvested_examples → judge_scores → calibrated_corpus`) where any upstream silently produces nothing.

### 5. Numeric Trajectory Stall

- **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has standard deviation < 1% of mean for ≥3 iterations AND the value has not crossed its target threshold.
- **Priority**: P3
- **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`
- **Catches**: `rl-coding-agent` reward stuck at the same composite score iteration after iteration; `apo-beam` best-score plateaued below `target_score`.

## Implementation Steps

1. Add a `static_analysis` pass that runs on the resolved state map (depends on ENH-1326 for fragment expansion) and emits Signal 3 (Stub Action) before history is even loaded.
2. Add a `route_distribution` accumulator to the event-history walker; emit Signal 2 (Degenerate Gate) when thresholds met.
3. Add an `apply_state_visit` check to the existing terminal-event handler; emit Signal 1 (Iter-1 Convergence) when conditions met.
4. Add `capture_emptiness` tracking keyed by capture name; emit Signal 4 (Capture Vacuum) at the end of the walk.
5. Add `numeric_trajectory` tracking per `output_numeric`/`convergence` evaluator; emit Signal 5 (Numeric Stall).
6. Update Step 5 output to group these under a new "Effectiveness Signals" subsection, distinct from the existing fault signals.

## API/Interface

No CLI surface change. New signals appear inline in `/ll:analyze-loop` output and propagate through `--json` output under a new `effectiveness_signals` key (separate from `fault_signals`) so `/ll:assess-loop` (FEAT-1325) can consume them cleanly.

## Acceptance Criteria

- [ ] All five signals implemented in `skills/analyze-loop/SKILL.md` Step 3 with deterministic thresholds.
- [ ] Synthetic test: `apo-textgrad` run that converges iter 1 → emits Signal 1.
- [ ] Synthetic test: state with `echo "5"` in score action → emits Signal 3 at config-load time.
- [ ] Synthetic test: 10 evaluate routes 10/10 to one branch → emits Signal 2.
- [ ] `--json` output partitions `fault_signals` and `effectiveness_signals` keys.
- [ ] No false positives on healthy runs of `dataset-curation`, `sprint-build-and-validate`, `rl-coding-agent` (when properly populated).

## Depends On

- ENH-1326 — fragment/inheritance resolution is needed before stub-action and numeric-trajectory checks can be reliably applied.

## Labels

`enhancement`, `loops`, `analysis`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3
