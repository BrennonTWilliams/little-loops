# Sample Research Notes: Evaluation Techniques

This document contains notes on evaluation techniques for automated systems.

## Technique 1: Convergence-Based Termination

A loop can terminate when successive iterations produce changes below a threshold
epsilon. Rather than running for a fixed number of iterations, track a delta metric
(e.g., number of new findings, change in a quality score) and stop when delta < epsilon
for K consecutive rounds. This prevents both premature termination and infinite loops.

**Applicability**: Directly applicable to FSM loop convergence detection. The `diff_stall`
evaluator implements a variant of this for file-change detection.

## Technique 2: Ensemble Scoring

Instead of relying on a single evaluator, aggregate scores from multiple independent
evaluators (e.g., rule-based, model-based, heuristic-based). Weight by historical
accuracy. This reduces bias from any single evaluator's blind spots.

**Applicability**: Could improve LLM judge accuracy in harness loops by combining
`llm_structured` verdicts with `exit_code` checks.

## Technique 3: Checkpoint Recovery

Write state snapshots at each major phase boundary. On failure, resume from the last
checkpoint rather than restarting from scratch. Especially valuable for long-running
loops where early phases are expensive.

**Applicability**: FSM runner already uses `run_dir` for artifact isolation; adding
explicit checkpoint files would enable graceful resume after timeout or crash.

## Technique 4: Stratified Sampling for Coverage Assessment

When measuring coverage of a large space, use stratified sampling to ensure all
subgroups are represented. Random sampling can miss rare but important cases.

**Applicability**: Less directly applicable to the current tooling focus.
