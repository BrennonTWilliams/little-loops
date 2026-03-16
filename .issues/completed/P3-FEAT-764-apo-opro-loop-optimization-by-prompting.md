---
id: FEAT-764
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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

OPRO (DeepMind, 2023) is the foundational gradient-free LLM-as-optimizer technique: give the optimizer full visibility of prior candidates and scores, and it proposes better variants without re-exploring dead ends. It is the simplest correct implementation of the LLM-as-optimizer pattern — well-studied, transparent, and easy to reason about.

By 2025-2026, more capable methods have emerged (DSPy/MIPROv2 for joint instruction+example optimization, TextGrad for multi-step pipelines, PhaseEvo for efficient search). OPRO remains actively cited and extended, but is best positioned as a solid starting point rather than state-of-the-art. Adding it as a built-in loop makes the foundational technique immediately accessible and provides a reference implementation that users can understand before reaching for heavier alternatives.

## Use Case

**Who**: Prompt engineer or researcher iterating on a system prompt

**Context**: They have a prompt file and a set of evaluation criteria. Prior refinement attempts haven't converged — the LLM keeps making similar mistakes without learning from previous iterations.

**Goal**: Run `ll-loop apo-opro` with their prompt file, criteria, and target score. The loop maintains a history of past candidates and scores, using them to guide each new proposal.

**Outcome**: After N iterations, the loop surfaces an optimized prompt that has reached the target score (or the best-scoring candidate if max_iterations is hit).

## Acceptance Criteria

- [x] `loops/apo-opro.yaml` exists and passes `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm`
- [x] Loop is runnable via `ll-loop apo-opro --context prompt_file=my-prompt.md --context eval_criteria="..."`
- [x] Loop maintains a score history across iterations using `capture:` accumulation
- [x] Loop terminates on convergence (emits `CONVERGED` token) or `max_iterations`
- [x] `scripts/tests/test_builtin_loops.py` `expected` set updated to include `apo-opro`
- [x] `on_blocked` defined for any `llm_structured` evaluate states
- [x] `docs/guides/LOOPS_GUIDE.md` documents the loop with usage example

## Proposed Solution

Add `loops/apo-opro.yaml` following the patterns established in FEAT-722 (`apo-feedback-refinement`) and `loops/issue-refinement.yaml` (history accumulation via `capture:`):

```yaml
name: apo-opro
description: "OPRO-style prompt optimization — history-guided proposal until convergence"
initial: init_history
max_iterations: 25
context:
  prompt_file: system.md
  eval_criteria: ""
  target_score: 90
states:
  init_history:
    action: echo "No previous candidates."
    action_type: shell
    capture: score_history
    next: propose_candidate
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
- `scripts/tests/test_builtin_loops.py:48-64` — **required**: add `"apo-opro"` to the `expected` set in `test_expected_loops_exist`; test asserts exact set equality on line 66 and will fail without this update
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

> **Note**: `loops/apo-feedback-refinement.yaml` now exists (FEAT-722 is completed) and is a valid reference. Use it alongside `loops/issue-refinement.yaml` and `loops/backlog-flow-optimizer.yaml`.

### Tests
- `scripts/tests/test_builtin_loops.py:28-43` — `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` auto-cover new YAML; no additional test code needed beyond `expected` set update
- `scripts/tests/test_builtin_loops.py:254-284` — `TestBuiltinLoopOnBlockedCoverage` enforces `on_blocked` on audited loops using `llm_structured`; OPRO uses `output_contains` routing (not `llm_structured`), so `on_blocked` is a best-practice add, not enforced — but include anyway per FEAT-722 implementation guidance

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add OPRO technique description, when to use vs `apo-feedback-refinement`, required variables, and `ll-loop apo-opro` invocation example

### Configuration
- N/A — no schema changes needed; `output_contains` evaluator already registered

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Critical — interpolation raises on missing captured keys**: `interpolation.py:102-124` `_get_nested` raises `InterpolationError("Path '...' not found in captured")` when the referenced slot hasn't been populated. The original proposed YAML had `initial: propose_candidate` which reads `${captured.score_history.output}` on the first iteration — this would crash before any candidate is proposed. Fix applied above: `initial: init_history` seeds `score_history` with `"No previous candidates."` via a shell action.
- **`capture:` slot is overwritten each iteration**: `rl-rlhf.yaml:46` confirms a slot name like `score_history` is always overwritten by the most recent state that captures to it — the running history must be explicitly reconstructed in `update_history` (already done in proposed YAML).
- **`test_expected_loops_exist` assert is at line 64** (not 61): the `expected` set spans `test_builtin_loops.py:48-62`; the `assert expected == actual` is on line 64.
- **`LOOPS_GUIDE.md` table spans lines 157-171** (not 157-169): `apo-opro` row sorts before `backlog-flow-optimizer` alphabetically, so it goes first in the table.
- **`REQUIRED_ON_BLOCKED` audit list** (`test_builtin_loops.py:261-266`) only audits specific named `llm_structured` states in four named loops; OPRO's `on_blocked: done` on prompt states is best-practice, not test-enforced.

## Implementation Steps

1. Read `loops/issue-refinement.yaml` and `loops/backlog-flow-optimizer.yaml` to internalize the `capture:` accumulation and `output_contains` routing patterns
2. Author `loops/apo-opro.yaml` following the YAML shape in Proposed Solution above; ensure `initial: init_history` (not `propose_candidate`) — `interpolation.py:122-123` raises `InterpolationError` on any missing captured key, so `score_history` must be seeded before `propose_candidate` runs; validate remaining field names against `schema.py:179-227` `StateConfig` fields
3. Add `"apo-opro"` to `expected` set in `scripts/tests/test_builtin_loops.py:48-61`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — all 3 auto-tests (`parse`, `validate`, `expected_set`) must pass
5. Add `apo-opro` row to the built-in loops table in `docs/guides/LOOPS_GUIDE.md:157-174`; the format is a single two-column table row — `| \`apo-opro\` | [one-line description from YAML] |`; append after `apo-contrastive` (line 173); no separate technique section or invocation example block is needed

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

### Known Limitations

- **Model-size sensitivity**: OPRO requires a large frontier model as the optimizer. On models under ~13B parameters it consistently underperforms plain CoT baselines (ACL 2024 findings). Best results with GPT-4-class or Gemini Pro.
- **Token cost**: Each optimization run can consume 96K+ input tokens across iterations. `max_iterations: 25` is a reasonable cap but users should expect significant API spend on long runs.
- **Single-objective only**: The history-guided proposal pattern degrades on multi-objective tasks where tradeoffs between criteria cannot be collapsed to a single score.
- **When to prefer alternatives**: Users with DSPy already in their stack should prefer MIPROv2 (joint instruction+few-shot optimization); users optimizing multi-step pipelines should prefer TextGrad (FEAT-766).

## Related Issues

- FEAT-722: Built-in Loops for APO Techniques (parent initiative — covers `apo-feedback-refinement` and `apo-contrastive`)
- FEAT-765: APO Loop — Beam Search (sibling)
- FEAT-766: APO Loop — TextGrad (sibling)

## Labels

`feat`, `loops`, `apo`, `prompt-engineering`

## Status

**Completed** | Created: 2026-03-15 | Resolved: 2026-03-15 | Priority: P3

## Resolution

Implemented `loops/apo-opro.yaml` following the OPRO pattern with `init_history` seeding, history-accumulating `update_history` state, and `output_contains` convergence routing. Updated the test expected set and LOOPS_GUIDE.md table. All 18 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-03-16T03:22:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec916e72-2c5c-4ed0-acb5-84a29b90647f.jsonl`
- `/ll:refine-issue` - 2026-03-16T02:58:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5174c024-3fd6-45af-99ec-40b65318a9fe.jsonl`
- `/ll:refine-issue` - 2026-03-16T01:43:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/985aba8f-2b18-4a2d-9edb-1476f791cb38.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - conversation
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b13fa42-ae65-4611-bb1d-5fee30b6940b.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cfa2c78-0022-4007-b1b6-448ac982f4aa.jsonl`
