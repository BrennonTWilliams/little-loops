---
id: FEAT-766
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# FEAT-766: APO Loop — TextGrad (Text Gradient Descent)

## Summary

Add a built-in FSM loop `apo-textgrad` that implements a text-gradient descent strategy for prompt optimization: test the current prompt on a batch of examples, compute a "text gradient" (natural language critique of what went wrong), apply that gradient to refine the prompt, and repeat until a quality threshold is reached.

## Current Behavior

`ll-loop` has no built-in loop implementing a TextGrad-style approach. The existing `apo-feedback-refinement` loop (FEAT-722) evaluates prompt quality holistically but does not systematically test against a batch of concrete examples or derive structured failure signals from them. Users who want example-driven, gradient-style refinement must build a custom FSM.

## Expected Behavior

Users can run `ll-loop apo-textgrad` to refine a prompt using structured failure signals derived from test examples:

1. Test the current prompt against a batch of examples (input/expected-output pairs)
2. Compute a text gradient: a structured critique of what failed and why
3. Apply the gradient to produce a refined prompt
4. Route to `done` if pass rate converges; otherwise repeat

## Motivation

TextGrad (Stanford, 2024) adapts the gradient descent metaphor to natural language — instead of numeric gradients, it computes textual descriptions of failures and uses them to update the prompt. This is more targeted than holistic feedback refinement: failures on specific examples produce specific signals, leading to faster convergence on prompts with clear success criteria (e.g., classification accuracy, extraction correctness). Adding `apo-textgrad` as a built-in gives users a third, qualitatively distinct APO strategy alongside the holistic refinement of `apo-feedback-refinement` and the exploration breadth of `apo-beam`.

## Use Case

**Who**: Developer building a Claude-powered extraction or classification feature

**Context**: They have a system prompt and 10-20 input/output example pairs. The prompt produces correct outputs on most examples but fails on a predictable subset. They want to fix the failures systematically without breaking the working cases.

**Goal**: Run `ll-loop apo-textgrad` with their prompt file and examples file. Each iteration tests the prompt on the examples, computes which ones failed and why, then applies targeted fixes.

**Outcome**: After N iterations, the prompt correctly handles the failing examples without regressing on the passing ones. The loop terminates when pass rate reaches `target_pass_rate` or `max_iterations` is hit.

## Acceptance Criteria

- [ ] `loops/apo-textgrad.yaml` exists and passes `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm`
- [ ] Loop tests the prompt against `context.examples_file` each iteration
- [ ] Loop computes a text gradient (structured failure critique) and applies it to the prompt
- [ ] Loop terminates on convergence (emits `CONVERGED` token) or `max_iterations`
- [ ] `scripts/tests/test_builtin_loops.py` `expected` set updated to include `apo-textgrad`
- [ ] `on_blocked` defined for all prompt-driven states
- [ ] `docs/guides/LOOPS_GUIDE.md` documents the loop with usage example and `examples_file` format guidance

## Proposed Solution

Add `loops/apo-textgrad.yaml`. The distinguishing feature is the `compute_gradient` state that produces a structured critique from test failures — this is the "text gradient" that drives refinement:

```yaml
name: apo-textgrad
description: "TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement"
initial: test_on_examples
max_iterations: 20
context:
  prompt_file: system.md
  examples_file: examples.json
  target_pass_rate: 90
states:
  test_on_examples:
    action_type: prompt
    action: |
      Read the prompt from ${context.prompt_file}.
      Read the test examples from ${context.examples_file}.
      Run the prompt against each example and compare output to expected.
      For each example output: "Example N: PASS/FAIL — <one-line reason if FAIL>"
      On the final line output: PASS_RATE=<integer 0-100>
    capture: test_results
    on_blocked: done
    next: compute_gradient
  compute_gradient:
    action_type: prompt
    action: |
      Analyze these test results to compute a text gradient — a structured description of the failures:
      ${captured.test_results.output}
      Output:
      1. FAILURE_PATTERN: <common theme across all failures>
      2. ROOT_CAUSE: <what is wrong in the current prompt that causes this>
      3. GRADIENT: <precise instruction for how to change the prompt to fix this>
      If PASS_RATE=100 or PASS_RATE exceeds ${context.target_pass_rate}, output CONVERGED on its own line instead.
    capture: gradient
    on_blocked: done
    next: route_convergence
  route_convergence:
    evaluate:
      type: output_contains
      source: "${captured.gradient.output}"
      pattern: "CONVERGED"
    on_yes: done
    on_no: apply_gradient
  apply_gradient:
    action_type: prompt
    action: |
      Apply this text gradient to improve the prompt:
      Current prompt: (read from ${context.prompt_file})
      Gradient: ${captured.gradient.output}
      Produce a refined prompt that addresses the ROOT_CAUSE and follows the GRADIENT instruction.
      Output the full refined prompt, then overwrite ${context.prompt_file} with it.
    on_blocked: done
    next: test_on_examples
  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `loops/apo-textgrad.yaml` — **primary deliverable**: new built-in YAML (no Python changes required)
- `scripts/tests/test_builtin_loops.py:48-61` — **required**: add `"apo-textgrad"` to the `expected` set in `test_expected_loops_exist`
- `docs/guides/LOOPS_GUIDE.md` — add `apo-textgrad` entry with `examples_file` format guidance and `ll-loop apo-textgrad` invocation example

### Dependent Files (No Changes Needed)
- `scripts/little_loops/cli/loop/_helpers.py:81-83` — `get_builtin_loops_dir()` already returns `<repo-root>/loops/`
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` fallback already resolves built-ins by name
- `scripts/little_loops/cli/loop/config_cmds.py:37-66` — `cmd_install()` already copies built-ins; `ll-loop install apo-textgrad` works for free

### Similar Patterns
- `loops/backlog-flow-optimizer.yaml:35-58` — canonical `output_contains` routing with uppercase sentinel on final line
- `loops/fix-quality-and-tests.yaml` — gold standard for `action_type: prompt` test-and-fix pattern with `on_blocked`
- `loops/issue-refinement.yaml` — `${captured.<state>.output}` chaining between states
- `scripts/little_loops/fsm/interpolation.py:65` — valid namespaces: `context`, `captured`, `prev`, `result`, `state`, `loop`, `env`

### Tests
- `scripts/tests/test_builtin_loops.py:28-43` — auto-covers new YAML; no additional test code needed beyond `expected` set update
- `scripts/tests/test_builtin_loops.py:254-284` — `apo-textgrad` uses `output_contains` (not `llm_structured`), so not in the enforced `on_blocked` set; include `on_blocked` as best practice

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — explain text gradient concept, `examples_file` expected format (JSON array of `{input, expected}` objects), when to use vs `apo-feedback-refinement` (example-driven vs holistic)

### Configuration
- N/A — no schema changes needed

## Implementation Steps

1. Read `loops/fix-quality-and-tests.yaml` and `loops/backlog-flow-optimizer.yaml` to internalize the test-fix pattern and `output_contains` routing
2. Author `loops/apo-textgrad.yaml` following the YAML shape in Proposed Solution above
3. Add `"apo-textgrad"` to `expected` set in `scripts/tests/test_builtin_loops.py:48-61`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — all 3 auto-tests must pass
5. Add `apo-textgrad` entry to `docs/guides/LOOPS_GUIDE.md` including `examples_file` format guidance

## API/Interface

```bash
# Run with defaults
ll-loop apo-textgrad

# Run with a concrete examples file
ll-loop apo-textgrad \
  --context prompt_file=prompts/extractor.md \
  --context examples_file=tests/extraction-examples.json \
  --context target_pass_rate=95

# Install to project
ll-loop install apo-textgrad

# Inspect definition
ll-loop show apo-textgrad
```

### Expected `examples_file` Format

```json
[
  { "input": "Support ticket text...", "expected": "HIGH" },
  { "input": "Another ticket...", "expected": "LOW" }
]
```

## Impact

- **Priority**: P3 - Most targeted of the APO loops for prompts with clear success criteria (classification, extraction); high value for that use case
- **Effort**: Small — YAML authoring only; no Python changes required
- **Risk**: Low — additive; test-and-fix pattern is well-established in existing loops
- **Breaking Change**: No

## Related Issues

- FEAT-722: Built-in Loops for APO Techniques (parent initiative)
- FEAT-764: APO Loop — OPRO (sibling)
- FEAT-765: APO Loop — Beam Search (sibling)

## Labels

`feat`, `loops`, `apo`, `prompt-engineering`

## Status

**Open** | Created: 2026-03-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - conversation
