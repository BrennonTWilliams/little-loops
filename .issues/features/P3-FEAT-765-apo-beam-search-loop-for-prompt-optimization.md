---
id: FEAT-765
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# FEAT-765: APO Loop — Beam Search Over Prompt Space

## Summary

Add a built-in FSM loop `apo-beam` that implements beam search for prompt optimization: generate N prompt variants in parallel, score all of them, select the top-k candidates, then either expand (generate new variants from the top-k) or terminate when the best score exceeds a threshold.

## Current Behavior

`ll-loop` has no built-in loop implementing beam search over the prompt space. Users who want to explore multiple prompt variants simultaneously and select the strongest must design a custom FSM from scratch. FEAT-722 (the parent APO initiative) plans a single-path refinement loop (`apo-feedback-refinement`) that only refines one candidate per iteration — it cannot explore multiple directions simultaneously. Neither `apo-beam.yaml` nor `apo-feedback-refinement.yaml` exist yet; both are planned deliverables from FEAT-722. As of 2026-03-15, `loops/` contains no `apo-*.yaml` files.

## Expected Behavior

Users can run `ll-loop apo-beam` to explore a beam of prompt candidates simultaneously:

1. Generate N prompt variants from the current best candidate
2. Score all variants against provided evaluation criteria
3. Select the top-scoring variant as the new best
4. Route to `done` if best score converges; otherwise generate a new beam from the winner

## Motivation

Single-path refinement loops can get stuck in local optima. Beam search explores multiple directions simultaneously and retains the best, reducing the chance of missing high-performing prompt regions. This is especially useful for prompts with a large search space (e.g., few-shot format, persona phrasing, chain-of-thought structure). Adding `apo-beam` as a built-in gives users a qualitatively different optimization strategy from the linear refinement in `apo-feedback-refinement`.

## Use Case

**Who**: Prompt engineer who has tried linear refinement and hit a plateau

**Context**: The `apo-feedback-refinement` loop has converged on a local optimum. They want to explore multiple variations of the current best prompt simultaneously to escape the plateau.

**Goal**: Run `ll-loop apo-beam` with `beam_width=4`, their prompt file, and evaluation criteria. Each iteration generates 4 variants, scores them all, and advances from the highest scorer.

**Outcome**: After N iterations, the loop surfaces the highest-scoring prompt discovered across all beams, outperforming the single-path refinement result.

## Acceptance Criteria

- [ ] `loops/apo-beam.yaml` exists and passes `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm`
- [ ] Loop generates multiple variants per iteration (controlled by `context.beam_width`)
- [ ] Loop scores all variants and selects the highest-scoring one
- [ ] Loop terminates on convergence (emits `CONVERGED` token) or `max_iterations`
- [ ] `scripts/tests/test_builtin_loops.py` `expected` set updated to include `apo-beam`
- [ ] `on_blocked` omitted from `action_type: prompt` states (see Integration Map — `on_blocked` is only valid on `llm_structured` evaluate states)
- [ ] `docs/guides/LOOPS_GUIDE.md` documents the loop with usage example

## Proposed Solution

Add `loops/apo-beam.yaml`. Multi-candidate generation is new territory in little-loops (no existing loop does this) — generate all variants in a single prompt state as a numbered list, score them all in the next state, then select the winner. Use `output_contains` for convergence routing (emit `CONVERGED` from `select_best` when best score exceeds threshold):

```yaml
name: apo-beam
description: "Beam search prompt optimization — generate N variants, score all, advance the winner"
initial: generate_variants
max_iterations: 20
context:
  prompt_file: system.md
  eval_criteria: ""
  beam_width: 4
  target_score: 90
states:
  generate_variants:
    action_type: prompt
    action: |
      Read the current best prompt from ${context.prompt_file}.
      Generate exactly ${context.beam_width} distinct variations of it.
      Vary structure, phrasing, examples, and persona — not just minor wording.
      Output each variant numbered 1 through ${context.beam_width}, separated by "---VARIANT---".
    capture: variants
    next: score_variants
  score_variants:
    action_type: prompt
    action: |
      Score each of these prompt variants against the criteria: ${context.eval_criteria}
      Variants:
      ${captured.variants.output}
      For each variant output: "Variant N: <score 0-100> — <one-line rationale>"
      On the final line output: BEST_VARIANT=N (the number of the highest-scoring variant)
    capture: scores
    next: select_best
  select_best:
    action_type: prompt
    action: |
      Scores: ${captured.scores.output}
      Extract the best variant (indicated by BEST_VARIANT=N) from:
      ${captured.variants.output}
      If the best score exceeds ${context.target_score}, output the variant text followed by CONVERGED on its own line.
      Otherwise output the variant text followed by CONTINUE on its own line.
      Also overwrite ${context.prompt_file} with the winning variant text.
    capture: best_candidate
    next: route_convergence
  route_convergence:
    evaluate:
      type: output_contains
      source: "${captured.best_candidate.output}"
      pattern: "CONVERGED"
    on_yes: done
    on_no: generate_variants
  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `loops/apo-beam.yaml` — **primary deliverable**: new built-in YAML (no Python changes required)
- `scripts/tests/test_builtin_loops.py:48-61` — **required**: add `"apo-beam"` to the `expected` set in `test_expected_loops_exist`
- `docs/guides/LOOPS_GUIDE.md` — add `apo-beam` entry with beam width explanation and `ll-loop apo-beam` invocation example

### Dependent Files (No Changes Needed)
- `scripts/little_loops/cli/loop/_helpers.py:81-83` — `get_builtin_loops_dir()` already returns `<repo-root>/loops/`
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` fallback already resolves built-ins by name
- `scripts/little_loops/cli/loop/config_cmds.py:37-66` — `cmd_install()` already copies built-ins; `ll-loop install apo-beam` works for free

### Similar Patterns
- `loops/backlog-flow-optimizer.yaml:35-58` — canonical `output_contains` routing with uppercase token (`CONVERGED`/`CONTINUE`) on final output line
- `loops/fix-quality-and-tests.yaml` — gold standard for `action_type: prompt` states with `on_blocked`
- `loops/issue-refinement.yaml` — `capture:` chaining to pass output between states via `${captured.<state>.output}`
- FEAT-722 implementation notes: "multi-candidate generation is new territory — generate N variants in a single prompt state as a numbered list, then scoring all in the next state" — this is the exact pattern used here

### Tests
- `scripts/tests/test_builtin_loops.py:28-43` — auto-covers new YAML; no additional test code needed beyond `expected` set update
- `scripts/tests/test_builtin_loops.py:48-62` — `expected` set currently has 13 stems; adding `"apo-beam"` makes 14; bidirectional equality check means both the YAML and the set entry must be added together
- `scripts/tests/test_builtin_loops.py:254-284` — `TestBuiltinLoopOnBlockedCoverage`: enforces `on_blocked` only for `llm_structured` evaluate states; `apo-beam` uses only `output_contains` routing, so it is NOT in the enforced set and must NOT add `on_blocked` to action states (research confirms `on_blocked` appears exclusively on `llm_structured` evaluate states across all existing loops)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — explain beam search concept, when to use vs `apo-feedback-refinement` (exploration vs exploitation), `beam_width` parameter guidance

### Configuration
- N/A — no schema changes needed

## Implementation Steps

1. Read `loops/backlog-flow-optimizer.yaml` to internalize the `output_contains` routing pattern with uppercase sentinel tokens
2. Author `loops/apo-beam.yaml` following the YAML shape in Proposed Solution above
3. Add `"apo-beam"` to `expected` set in `scripts/tests/test_builtin_loops.py:48-61`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — all 3 auto-tests must pass
5. Add `apo-beam` entry to `docs/guides/LOOPS_GUIDE.md:157-171` built-in loops table: `| \`apo-beam\` | Beam search prompt optimization — generate N variants, score all, advance the winner |`

## API/Interface

```bash
# Run with defaults (beam_width=4)
ll-loop apo-beam

# Wider beam for higher-stakes optimization
ll-loop apo-beam \
  --context prompt_file=prompts/triage.md \
  --context eval_criteria="correctly triage support tickets by severity" \
  --context beam_width=6 \
  --context target_score=88

# Install to project
ll-loop install apo-beam
```

## Impact

- **Priority**: P3 - Qualitatively different optimization strategy from linear refinement; high value for users who have hit plateaus
- **Effort**: Small — YAML authoring only; no Python changes required
- **Risk**: Low — additive; multi-variant generation is novel in this codebase but fully implementable with existing `action_type: prompt` + `output_contains` infrastructure
- **Breaking Change**: No

## Related Issues

- FEAT-722: Built-in Loops for APO Techniques (parent initiative)
- FEAT-764: APO Loop — OPRO (sibling)
- FEAT-766: APO Loop — TextGrad (sibling)

## Labels

`feat`, `loops`, `apo`, `prompt-engineering`

## Status

**Open** | Created: 2026-03-15 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-03-16T02:11:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b918c53-10e7-4c18-8f65-7a0fdd85cd04.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - conversation
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1ae078c-0743-4f48-bee3-15017b2d071b.jsonl`
