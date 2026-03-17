---
discovered_date: 2026-03-16
discovered_by: capture-issue
---

# FEAT-792: Built-in Policy+RLHF Nested FSM Loop for Agentic Coding

## Summary

Add a built-in FSM loop (`loops/rl-coding-agent.yaml`) that composes `rl-policy` (outer strategy-improvement loop) with `rl-rlhf` (inner artifact quality-gating loop) to drive agentic coding tasks — bug fixing, test generation, or code refinement — using multiple reward signals (test pass rate, lint score, LLM-as-judge).

## Context

The existing `rl-policy.yaml` and `rl-rlhf.yaml` loops in `loops/` are template stubs with placeholder actions. During a design session exploring RL loop use cases in agentic coding, a natural composition emerged: an outer policy loop that adapts the *strategy* (what to fix, which files to target, which approach to use) while an inner RLHF loop polishes each *artifact* (individual code change, docstring, test file) to a quality threshold before the outer loop observes it and updates its strategy.

Current workaround: running them as separate `ll-loop` invocations with no context sharing. The loops directory has no ready-to-use agentic coding loop combining both patterns.

## Expected Behavior

`loops/rl-coding-agent.yaml` exists and is runnable via `ll-loop run rl-coding-agent`:

```yaml
name: rl-coding-agent
description: |
  Policy+RLHF composite loop for agentic coding. An outer policy loop adapts the
  coding strategy (which files, which approach) while an inner RLHF loop polishes
  each artifact to a quality threshold before the outer loop observes results.
  Reward = weighted composite of test pass rate, lint score, and LLM-as-judge.
initial: act
context:
  reward_target: 0.85
  quality_threshold: 7
  target_files: ""       # Override: space-separated file globs to act on
  test_cmd: "python -m pytest"
  lint_cmd: "ruff check"
states:
  act:
    # Execute current coding strategy on target files
    action: |
      echo "Executing coding strategy on: ${context.target_files}"
      # Replace: run your coding action (ll-manage-issue, claude prompt, patch, etc.)
      echo "strategy_applied"
    action_type: shell
    capture: action_result
    next: refine

  refine:
    # Inner RLHF loop: polish the artifact until quality >= threshold
    action: |
      ll-loop run rl-rlhf \
        --context quality_dimension="correctness and test coverage" \
        --max-iterations 10
    action_type: shell
    capture: refine_result
    next: observe

  observe:
    # Compute composite reward: test_pass_rate * 0.5 + lint_score * 0.3 + llm_score * 0.2
    action: |
      # Test score (0.0-1.0)
      TEST_OUT=$(${context.test_cmd} --tb=no -q 2>&1 | tail -1)
      PASSED=$(echo "$TEST_OUT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo 0)
      TOTAL=$(echo "$TEST_OUT" | grep -oE '[0-9]+ (passed|failed)' | grep -oE '[0-9]+' | paste -sd+ | bc || echo 1)
      TEST_SCORE=$(python3 -c "print(round($PASSED / max($TOTAL, 1), 3))")

      # Lint score (0.0-1.0): 1 - clamped(errors/10)
      LINT_ERRORS=$(${context.lint_cmd} --select E,W 2>/dev/null | grep -c '^' || echo 0)
      LINT_SCORE=$(python3 -c "print(round(max(0, 1 - $LINT_ERRORS / 10), 3))")

      # Composite reward
      REWARD=$(python3 -c "print(round($TEST_SCORE * 0.5 + $LINT_SCORE * 0.3 + 0.2, 3))")
      echo "test=$TEST_SCORE lint=$LINT_SCORE composite=$REWARD"
      echo "$REWARD"
    action_type: shell
    capture: observation
    next: score

  score:
    action: |
      echo "${captured.observation.output}" | tail -1 | tr -d '[:space:]'
    action_type: shell
    evaluate:
      type: convergence
      target: "${context.reward_target}"
      direction: maximize
      tolerance: 0.05
    route:
      target: done
      progress: improve
      stall: act
      error: failed

  improve:
    # Update strategy based on observed reward and refine output
    action: |
      echo "Reward achieved: ${captured.observation.output}"
      echo "Refine output: ${captured.refine_result.output}"
      # Replace: update strategy file, adjust prompt, change target files, etc.
      echo "Strategy updated based on observations."
    action_type: shell
    next: act

  done:
    terminal: true
  failed:
    terminal: true

max_iterations: 50
on_handoff: pause
```

## Use Case

**Who**: Developer running `ll-loop` for automated code improvement

**Context**: Has a set of files with failing tests or lint errors and wants a loop that both improves code quality iteratively *and* adapts its strategy based on observed reward signals — without manually wiring two separate loops

**Goal**: Run `ll-loop run rl-coding-agent` and have it converge on a target composite reward (e.g., 0.85) by alternating between acting, polishing artifacts, observing test+lint outcomes, and improving its approach

**Outcome**: A single runnable YAML that converges on target code quality, with `done` reached when tests pass and lint is clean

## Acceptance Criteria

- [ ] `loops/rl-coding-agent.yaml` exists and passes `ll-loop test rl-coding-agent`
- [ ] All states are reachable; all terminal states are reachable
- [ ] `refine` state invokes `rl-rlhf` as a subprocess (via `ll-loop run`)
- [ ] `observe` state computes a composite reward from test pass rate + lint score + LLM weight
- [ ] `score` state uses `convergence` evaluator routing to `done`/`improve`/`act`/`failed`
- [ ] Loop YAML is annotated with comments explaining the Policy+RLHF composition pattern
- [ ] `loops/README.md` (or equivalent index) mentions the new loop

## Motivation

- **Composability gap**: The existing `rl-policy.yaml` and `rl-rlhf.yaml` are stubs with no concrete actions. A coding-specific composition loop gives users a practical starting point rather than two abstract templates to wire up independently.
- **Multiple reward signals**: Real coding quality isn't captured by a single metric. A composite (tests + lint + LLM judgment) is more robust and mirrors how code review actually works.
- **Path to native nesting**: Once FEAT-659 (Hierarchical FSM Loops) lands, the `refine` state's subprocess delegation can be replaced with a native `loop: rl-rlhf` sub-loop state — giving full context passthrough and proper convergence tracking. This loop is designed to be upgraded.

## Implementation Steps

1. Create `loops/rl-coding-agent.yaml` with the structure above
2. Validate: `ll-loop test rl-coding-agent` — confirm structure passes validation
3. Smoke-test the reward computation script in `observe` with a test repo
4. Annotate states with `# POLICY OUTER:` and `# RLHF INNER:` comments for readability
5. **Create** `loops/README.md` — no README exists in `loops/` yet; add a minimal index listing all built-in loops with one-line descriptions
6. Update `scripts/tests/test_builtin_loops.py:48-68` — add `"rl-coding-agent"` to the hardcoded `expected` set in `test_expected_loops_exist`; without this the test suite will fail as it asserts an exact match of loop names

## Integration Map

### Files to Create/Modify
- `loops/rl-coding-agent.yaml` — new composite loop
- `loops/README.md` — must be **created** (does not exist); add index of all built-in loops
- `scripts/tests/test_builtin_loops.py:48-68` — add `"rl-coding-agent"` to the `expected` set in `test_expected_loops_exist` or the test will fail on exact-match assertion

### Dependencies
- `loops/rl-rlhf.yaml` — invoked as subprocess in `refine` state (`loops/rl-rlhf.yaml` exists: `generate → score → refine` cycle, `output_numeric` evaluator, `quality_dimension` context var)
- `loops/rl-policy.yaml` — source template for the outer policy pattern (`act → observe → score → improve` with `convergence` evaluator and `route:` table)
- `ll-loop run` — supports `--context KEY=VALUE` as a repeatable flag; confirmed in `scripts/little_loops/cli/loop/run.py:61-65` and `__init__.py:141-144`
- `ll-loop test` — runs single-state validation; structural validation happens on load via `load_and_validate` in `scripts/little_loops/fsm/validation.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`--context` passthrough confirmed**: `ll-loop run rl-rlhf --context quality_dimension="..."` will work as written — `run.py:61-65` applies `--context` overrides directly to `fsm.context` before execution
- **`convergence` evaluator requires plain float output** (`evaluators.py:759-765`): the `score` state's `echo | tail -1 | tr -d '[:space:]'` pattern correctly isolates the float — same as `rl-policy.yaml:32` and `rl-bandit.yaml:34`
- **`convergence` stall detection** (known limitation): without a `previous:` field in `evaluate`, `previous` is always `None` and the `stall` verdict never fires — iterations return `progress` indefinitely until `target`. This is consistent with the existing rl-policy stub. If stall detection is desired, add `previous: "${captured.action_result.output}"` to the `score` state's `evaluate` block (the `capture: action_result` on `score` means the prior iteration's score is available on subsequent iterations)
- **LLM score hardcoded to 0.2**: the `observe` state computes `REWARD = TEST_SCORE * 0.5 + LINT_SCORE * 0.3 + 0.2` — the LLM weight is a fixed constant rather than a computed score; this is intentional given subprocess complexity but worth a comment in the YAML
- **No `loops/README.md` exists**: `loops/` contains 18 YAML files with no index; implementation step 5 must CREATE it
- **`test_expected_loops_exist` (test_builtin_loops.py:46-69)** asserts `expected == actual` where `expected` is a hardcoded set of 18 loop names; adding `rl-coding-agent.yaml` without updating this set will fail the test suite

### Upgrade Path (post FEAT-659)
When FEAT-659 lands, replace:
```yaml
refine:
  action: "ll-loop run rl-rlhf --max-iterations 10"
  action_type: shell
```
with:
```yaml
refine:
  loop: rl-rlhf
  context_passthrough: true
  on_success: observe
  on_failure: failed
```

### Related Issues
- FEAT-659: Hierarchical FSM Loops — runtime infrastructure for native sub-loop support
- FEAT-754: Add Example FSM Loops (Harnessing) — parallel effort for harness-pattern examples
- `loops/rl-bandit.yaml`, `loops/rl-policy.yaml`, `loops/rl-rlhf.yaml` — source templates

### Tests
- `ll-loop test loops/rl-coding-agent.yaml` — structural validation (single-state simulation)
- `python -m pytest scripts/tests/test_builtin_loops.py` — validates all built-in loops including the new one; requires updating `test_expected_loops_exist` at `test_builtin_loops.py:48-68`
- Manual: run against a small repo with known test failures to verify reward convergence

## Impact

- **Priority**: P3 — developer experience and loop library value
- **Effort**: Small — new YAML file only; no code changes
- **Risk**: Low — additive; no existing loops affected
- **Breaking Change**: No

## Labels

`loops`, `rl`, `agentic-coding`, `feat`, `developer-experience`

---

## Status

- [ ] Not started

## Session Log
- `/ll:refine-issue` - 2026-03-17T03:11:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9bf31b0a-cfc9-42ad-a35f-c71298680f5c.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/732dcab7-eba9-4078-8001-cb11dc975881.jsonl`
