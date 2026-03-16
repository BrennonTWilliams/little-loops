---
id: FEAT-764
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# FEAT-764: APO Loop — OPRO (Optimization by PROmpting)

## Summary

Add a built-in FSM loop `apo-opro` that implements the OPRO technique: maintain a running history of prompt candidates and their scores, then ask an LLM to propose a better prompt using that history as context — iterating until a score threshold is reached or max iterations exhausted.

## Current Behavior

`ll-loop` has no built-in loop implementing the OPRO pattern. Users who want to run history-guided prompt optimization must design a custom FSM from scratch, including the score-history accumulation and meta-prompting logic.

## Expected Behavior

Users can run `ll-loop apo-opro` to iteratively optimize a prompt using the OPRO strategy:

1. Load the current prompt and any accumulated score history
2. Propose a new prompt candidate using LLM, informed by past candidates and scores
3. Evaluate the candidate against provided criteria
4. Update score history with the new result
5. Route to `done` if score converges, otherwise loop

## Motivation

OPRO (DeepMind, 2023) is a well-studied gradient-free optimization method applicable to prompt engineering. It outperforms naive refinement by giving the optimizer full visibility of prior attempts and their outcomes — making it less likely to re-explore dead ends. Adding this as a built-in loop makes a research-grade technique immediately accessible to little-loops users.

## Use Case

**Who**: Prompt engineer or researcher iterating on a system prompt

**Context**: They have a prompt file and a set of evaluation criteria. Prior refinement attempts haven't converged — the LLM keeps making similar mistakes without learning from previous iterations.

**Goal**: Run `ll-loop apo-opro` with their prompt file, criteria, and target score. The loop maintains a history of past candidates and scores, using them to guide each new proposal.

**Outcome**: After N iterations, the loop surfaces an optimized prompt that has reached the target score (or the best-scoring candidate if max_iterations is hit).

## Acceptance Criteria

- [ ] `loops/apo-opro.yaml` exists and passes `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm`
- [ ] Loop is runnable via `ll-loop apo-opro --context prompt_file=my-prompt.md --context eval_criteria="..."`
- [ ] Loop maintains a score history across iterations using `capture:` accumulation
- [ ] Loop terminates on convergence (emits `CONVERGED` token) or `max_iterations`
- [ ] `scripts/tests/test_builtin_loops.py` `expected` set updated to include `apo-opro`
- [ ] `on_blocked` defined for any `llm_structured` evaluate states
- [ ] `docs/guides/LOOPS_GUIDE.md` documents the loop with usage example

## Proposed Solution

Add `loops/apo-opro.yaml` following the patterns established in FEAT-722 (`apo-feedback-refinement`) and `loops/issue-refinement.yaml` (history accumulation via `capture:`):

```yaml
name: apo-opro
description: "OPRO-style prompt optimization — history-guided proposal until convergence"
initial: propose_candidate
max_iterations: 25
context:
  prompt_file: system.md
  eval_criteria: ""
  target_score: 90
states:
  propose_candidate:
    action_type: prompt
    action: |
      You are a prompt optimizer. Read the current prompt from ${context.prompt_file}.
      Past candidates and scores (most recent last):
      ${captured.score_history.output}
      Propose an improved prompt variant that avoids the weaknesses in prior attempts.
      Output the full improved prompt text only.
    capture: candidate
    on_blocked: done
    next: evaluate_candidate
  evaluate_candidate:
    action_type: prompt
    action: |
      Evaluate this prompt candidate:
      ${captured.candidate.output}
      Criteria: ${context.eval_criteria}
      Output a score 0-100 and a brief analysis. On the last line output either CONVERGED or CONTINUE.
    capture: eval_result
    on_blocked: done
    next: update_history
  update_history:
    action_type: prompt
    action: |
      Append this entry to the score history and output the full updated history:
      Previous history: ${captured.score_history.output}
      New entry — Score: (extract from ${captured.eval_result.output}) | Summary: (1-line summary)
    capture: score_history
    on_blocked: done
    next: route_convergence
  route_convergence:
    evaluate:
      type: output_contains
      source: "${captured.eval_result.output}"
      pattern: "CONVERGED"
    on_yes: done
    on_no: propose_candidate
  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `loops/apo-opro.yaml` — **primary deliverable**: new built-in YAML (no Python changes required; `resolve_loop_path()` in `_helpers.py:102-105` already resolves from `loops/`)
- `scripts/tests/test_builtin_loops.py:48-61` — **required**: add `"apo-opro"` to the `expected` set in `test_expected_loops_exist`; test asserts exact set equality and will fail without this update
- `docs/guides/LOOPS_GUIDE.md` — add `apo-opro` entry with technique description and `ll-loop apo-opro` invocation example

### Dependent Files (No Changes Needed)
- `scripts/little_loops/cli/loop/_helpers.py:81-83` — `get_builtin_loops_dir()` returns `<repo-root>/loops/`; already handles new files
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` fallback already resolves built-in YAMLs by name
- `scripts/little_loops/cli/loop/config_cmds.py:37-66` — `cmd_install()` already copies built-in loops; `ll-loop install apo-opro` works for free

### Similar Patterns
- `loops/issue-refinement.yaml` — score history accumulation via chained `capture:` states; `${captured.<state>.output}` interpolation pattern
- `loops/backlog-flow-optimizer.yaml:35-58` — canonical `output_contains` routing with uppercase token on final line (`CONVERGED`/`CONTINUE`)
- `loops/fix-quality-and-tests.yaml` — gold standard for `action_type: prompt` + LLM-driven evaluate states with `on_blocked`
- `scripts/little_loops/fsm/interpolation.py:65` — valid namespaces: `context`, `captured`, `prev`, `result`, `state`, `loop`, `env`; use `${context.prompt_file}` not `${var.prompt_file}`

### Tests
- `scripts/tests/test_builtin_loops.py:28-43` — `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` auto-cover new YAML; no additional test code needed beyond `expected` set update
- `scripts/tests/test_builtin_loops.py:254-284` — `TestBuiltinLoopOnBlockedCoverage` enforces `on_blocked` on audited loops using `llm_structured`; OPRO uses `output_contains` routing (not `llm_structured`), so `on_blocked` is a best-practice add, not enforced — but include anyway per FEAT-722 implementation guidance

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add OPRO technique description, when to use vs `apo-feedback-refinement`, required variables, and `ll-loop apo-opro` invocation example

### Configuration
- N/A — no schema changes needed; `output_contains` evaluator already registered

## Implementation Steps

1. Read `loops/issue-refinement.yaml` and `loops/backlog-flow-optimizer.yaml` to internalize the `capture:` accumulation and `output_contains` routing patterns
2. Author `loops/apo-opro.yaml` following the YAML shape in Proposed Solution above; validate field names against `schema.py:179-227` `StateConfig` fields
3. Add `"apo-opro"` to `expected` set in `scripts/tests/test_builtin_loops.py:48-61`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — all 3 auto-tests (`parse`, `validate`, `expected_set`) must pass
5. Add `apo-opro` entry to `docs/guides/LOOPS_GUIDE.md` with usage example

## API/Interface

```bash
# Run with defaults
ll-loop apo-opro

# Run with context overrides
ll-loop apo-opro \
  --context prompt_file=prompts/classifier.md \
  --context eval_criteria="classify sentiment correctly on test set" \
  --context target_score=92

# Install to project
ll-loop install apo-opro

# Inspect definition
ll-loop show apo-opro
```

## Impact

- **Priority**: P3 - Valuable prompt engineering capability; complements FEAT-722 loops
- **Effort**: Small — YAML authoring only; no Python changes required
- **Risk**: Low — additive; no existing behavior changed
- **Breaking Change**: No

## Related Issues

- FEAT-722: Built-in Loops for APO Techniques (parent initiative — covers `apo-feedback-refinement` and `apo-contrastive`)
- FEAT-765: APO Loop — Beam Search (sibling)
- FEAT-766: APO Loop — TextGrad (sibling)

## Labels

`feat`, `loops`, `apo`, `prompt-engineering`

## Status

**Open** | Created: 2026-03-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - conversation
