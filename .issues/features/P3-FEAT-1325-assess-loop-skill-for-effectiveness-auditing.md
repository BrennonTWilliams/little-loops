---
id: FEAT-1325
type: FEAT
priority: P3
captured_at: "2026-05-02T19:05:00Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# FEAT-1325: `/ll:assess-loop` Skill for Loop Effectiveness Auditing

## Summary

Add a sibling skill to `/ll:analyze-loop` that judges whether a loop is **accomplishing the purpose stated in its description**, not just whether it crashed. `/ll:analyze-loop` stays lean and rule-based (runtime fault detection). `/ll:assess-loop` adds reasoning-heavy effectiveness analysis: it consumes `analyze-loop`'s findings as Phase 1, then layers on a goal-vs-outcome scorecard, success-contract extraction, artifact inspection, and an LLM-graded rubric-vs-description audit.

## Motivation

Survey of the 30+ built-in loops in `scripts/little_loops/loops/` showed that "did the loop do its job" is almost never visible from event history alone. Success is defined by **artifact state changes external to the FSM**: file mtime/diffs (`apo-textgrad`'s `prompt_file`, `svg-image-generator`'s `image.svg`), frontmatter score thresholds (`refine-to-ready-issue`'s `confidence` ≥ 90 / `outcome` ≥ 75), captured numeric trajectories (`rl-coding-agent`'s composite reward ≥ `reward_target`), and rubric semantics (the eval-harness mistake captured in `feedback_eval_harness_purpose.md` — running `/ll:manage-issue` from an `execute` state is a phantom success the current skill can't detect).

The existing `analyze-loop` Step 3b "Goal alignment" only compares state names against the `description` string — that's far too thin to catch phantom convergence, degenerate gates, or rubrics that don't operationalize the stated goal.

## Use Case

A user runs `apo-textgrad` to optimize a prompt. The loop terminates cleanly on iteration 1 because the model emitted `CONVERGED` from `compute_gradient` without ever entering `apply_gradient` — the prompt file is byte-identical to what it was at the start. `/ll:analyze-loop` reports no faults. `/ll:assess-loop` reports:

```
Goal:        Test prompt against examples; refine until pass-rate ≥ 90
Contract:    target_pass_rate=90, prompt_file mutation expected
Achieved:    iteration 1; pass_rate=100 (unverified); apply_gradient never visited
Artifacts:   git diff ${context.prompt_file} → empty
Verdict:     PHANTOM — terminal reached, contract unmet
Proposals:   1) tighten convergence rubric to require evidence;
             2) add invariant: apply_gradient must run ≥ 1× before terminal
```

## API/Interface

```bash
/ll:assess-loop [loop-name] [--tail N] [--no-rubric-audit]
```

- `loop-name` — same resolution rules as `/ll:analyze-loop` (auto-select most recent if omitted).
- `--no-rubric-audit` — skip the LLM rubric-vs-description pass (cost gate).
- Phase 1 internally calls `/ll:analyze-loop --json` and includes its findings.
- Output is the goal-vs-outcome scorecard followed by ranked improvement proposals (NOT auto-created issues — the user runs `/ll:capture-issue` selectively).

## Implementation Steps

1. **Resolve the loop fully** — merge `from:` parents, expand `fragment:` against `lib/*.yaml`, recursively parse one level of `loop:` sub-loop refs. (See ENH companion for stand-alone version of this step that also benefits `/ll:analyze-loop`.)
2. **Extract success contract** — parse `context.*` thresholds (`target_pass_rate`, `pass_threshold`, `quality_threshold`, `readiness_threshold`, `outcome_threshold`, `reward_target`, `target_score`, `min_per_category`, `adversarial_cap`); tag each `evaluate` state with the threshold it gates.
3. **Inspect artifacts** — read files under `.loops/tmp/<loop>/<run>/` and run `git diff` against any path the loop's actions touch (`${context.prompt_file}`, `system.md`, `.issues/**`, `data/curated/`, `image.svg`, `examples.json`, `manifest.json`).
4. **Phase 1 — invoke `/ll:analyze-loop`** and parse its JSON output for fault signals; include verbatim in the scorecard.
5. **Goal-vs-outcome scorecard** — output the structured block: Goal / Contract / Achieved / Artifacts / Verdict (met | partial | phantom | degraded).
6. **Rubric-vs-description audit** (gated by `--no-rubric-audit`) — for each `evaluate.type: llm_structured`, send the loop description plus that evaluator's `prompt` text to a single judge call: "Does this rubric operationalize the loop's stated purpose?" Catches the harness-running-`/ll:manage-issue` mistake and rubric drift.
7. **Sub-loop verdict laundering check** — when a state has `loop: <child>`, verify `on_success` and `on_failure` route to different downstream states.
8. **Proposals** — emit ranked improvement suggestions (state-level, rubric-level, contract-level) with concrete YAML diffs where possible.

## Coordination With `outer-loop-eval`

`outer-loop-eval` already has prompt-based `analyze_definition` / `analyze_execution` / `generate_report` states. See the companion ENH to swap those inline prompts for `/ll:analyze-loop` + `/ll:assess-loop` calls so we don't ship two diverging analyzers.

## Acceptance Criteria

- [ ] `/ll:assess-loop` skill exists at `skills/assess-loop/SKILL.md` with documented arguments and triggers.
- [ ] Phase 1 invokes `/ll:analyze-loop --json` and threads its output into the scorecard.
- [ ] Scorecard verdict is one of: `met`, `partial`, `phantom`, `degraded`.
- [ ] Detects the phantom-success case on a synthetic `apo-textgrad` run that converges on iter 1 without diff.
- [ ] Detects the harness-running-wrong-skill case (rubric audit flags an `execute` action that doesn't match the harness subject).
- [ ] `--no-rubric-audit` flag skips all LLM judge calls.
- [ ] Tests cover at least: phantom success, degenerate gate, rubric drift, sub-loop verdict laundering.

## Labels

`feature`, `loops`, `analysis`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3
