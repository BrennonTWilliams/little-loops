---
discovered_date: "2026-04-13"
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1103: Update svg-textgrad Loop — Address Missing Pieces

## Summary

The `svg-textgrad` loop is missing several robustness and quality features compared to `svg-image-generator` and has design gaps identified in code review: missing error handlers, no score history for gradient computation, no best-artifact preservation, a misleading comment on the evaluate fallback path, no convergence/plateau detection, and an inconsistency between documented scoring weights and the actual pass condition.

## Current Behavior

- No `on_error` handlers on `evaluate` or `score` states — LLM failures stall silently with no fallback to a `failed` terminal
- No `failed` terminal state (present in `svg-image-generator`, absent here)
- `compute_gradient` reads only the current `critique.md` and gradient history; it cannot detect score plateaus or regressions across iterations
- If a good SVG is generated on iteration N but gradient-driven regeneration produces a worse result on iteration N+1, the final output is the worse version — no best-artifact tracking
- `evaluate` comment says *"LLM-only scoring if Playwright is unavailable"* but `on_no: generate` skips scoring entirely, producing no feedback signal
- No convergence detection — loop runs all 20 iterations even when scores are flat, wasting compute
- `score` state documents 2x weights for `visual_clarity` and `originality` but the pass condition is flat (`all >= threshold`); weights only influence LLM framing, not the decision

## Expected Behavior

- `evaluate` and `score` states have `on_error` routing; a `failed` terminal state exists
- A shell step after `score` appends `iter N: visual_clarity=X, originality=X, craft=X, scalability=X` to `scores.md` so `compute_gradient` can detect plateaus and regressions
- Best-scoring SVG and brief are preserved as `best.svg` and `best-brief.md`; `done` state reports both the final and best artifacts
- `evaluate.on_no` comment is corrected to accurately describe what happens (re-generates without scoring)
- `compute_gradient` detects score plateaus (no improvement across last 3 iterations) and outputs a `CONVERGED` signal, routing to `done` early
- Pass condition either uses a weighted average or the weight documentation is removed from the prompt to avoid misleading the LLM

## Motivation

Silent failures and wasted iterations make the loop unreliable in practice. Without score history, `compute_gradient` applies gradients blind — it can't tell if the previous gradient improved anything or made things worse. Without best-artifact tracking, a single bad generation after a good one produces a worse final output. These gaps undermine the TextGrad optimization premise: if the feedback loop loses signal, the brief never converges meaningfully.

## Proposed Solution

**1. Add `on_error` handlers + `failed` terminal** (matches `svg-image-generator` pattern):
```yaml
evaluate:
  on_error: generate

score:
  on_error: failed

failed:
  terminal: true
```

**2. Score history** — add a shell state `record_scores` between `score` and `compute_gradient`:
```yaml
record_scores:
  action_type: shell
  action: |
    # parse scores from critique.md and append to scores.md
    DIR="${captured.run_dir.output}"
    ITER="${state.iteration}"
    grep -E "^(visual_clarity|originality|craft|scalability):" "$DIR/critique.md" \
      | awk -v iter="$ITER" 'BEGIN{printf "## Iteration %s\n", iter} {print}' \
      >> "$DIR/scores.md"
    echo "" >> "$DIR/scores.md"
  next: compute_gradient
```
Route `score.on_no` → `record_scores` → `compute_gradient`. Pass `scores.md` to `compute_gradient` prompt.

**3. Best-artifact preservation** — shell step after `score` (or in `record_scores`):
```bash
# Copy if weighted score exceeds current best (or on first pass)
```
Track `best_score` in a `best.txt` file; update `best.svg` / `best-brief.md` when exceeded.

**4. Convergence detection** — add to `compute_gradient` prompt:
> Read scores.md. If the last 3 recorded iterations show no improvement in any score, output CONVERGED on its own line instead of FAILURE_PATTERN/ROOT_CAUSE/GRADIENT.

`compute_gradient` already has `capture: gradient` at line 139 (output is stored as `${captured.gradient.output}`). Change `next: append_gradient` → `next: route_convergence`, then add:

```yaml
  route_convergence:
    evaluate:
      type: output_contains
      source: "${captured.gradient.output}"
      pattern: "CONVERGED"
    on_yes: done
    on_no: append_gradient
    on_error: append_gradient  # continue cycle if eval itself errors
```

The `source:` key reads from the prior captured state rather than re-running an action — this is the critical detail from `apo-textgrad.yaml:44–51`.

**5. Fix evaluate comment** — correct the misleading comment to say regeneration happens without scoring.

**6. Scoring weight consistency** — either implement weighted average (`(2*vc + 2*orig + craft + scalability)/6 >= threshold`) or remove the weight documentation from the `score` prompt.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml` — primary change target

### Dependent Files (Callers/Importers)
- `scripts/tests/test_loop_schemas.py` — may validate loop YAML structure
- `docs/` — `LOOPS_GUIDE.md` references svg-textgrad behavior

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml:104` — `evaluate.on_error: generate` (exact syntax to copy)
- `scripts/little_loops/loops/svg-image-generator.yaml:151,169–173` — `score.on_error: failed` + bare `failed` terminal (no `action_type`, no `action`, only `terminal: true`)
- `scripts/little_loops/loops/apo-textgrad.yaml:44–51` — `route_convergence` state with `source: "${captured.gradient.output}"` evaluator reading from prior capture
- `scripts/little_loops/loops/svg-textgrad.yaml:164–178` — `append_gradient` shell state; follow this exact pattern (`${state.iteration}` variable) for `record_scores`

### Tests
- `scripts/tests/test_builtin_loops.py:35–43` — `test_all_validate_as_valid_fsm` runs schema + routing validation on all built-in loops; new states will be validated automatically with no test changes required
- `scripts/tests/test_builtin_loops.py:45–91` — `test_expected_loops_exist` enumerates expected loop names; `svg-textgrad` is already listed — no change needed

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must be updated):**
- `scripts/tests/test_builtin_loops.py:1580–1583` — `test_score_state_routes_to_compute_gradient_on_iterate` asserts `score.on_no == "compute_gradient"`; planned change 2 reroutes `score.on_no` → `record_scores` — assertion must be updated
- `scripts/tests/test_builtin_loops.py:1585–1589` — `test_compute_gradient_captures_gradient` asserts `compute_gradient.next == "append_gradient"`; planned change 4 changes this to `route_convergence` — assertion must be updated

**New tests to write in `TestSvgTextgradLoop`** (follow patterns from `TestRecursiveRefineLoop` at line 1031 and `TestRefineToReadyIssueSubLoop` at line 633):
- `test_failed_state_is_terminal` — `failed.terminal is True`
- `test_evaluate_on_error_routes_to_generate` — `evaluate.on_error == "generate"`
- `test_score_on_error_routes_to_failed` — `score.on_error == "failed"`
- `test_score_on_no_routes_to_record_scores` — `score.on_no == "record_scores"` (replaces broken test)
- `test_record_scores_is_shell` — `record_scores.action_type == "shell"`
- `test_record_scores_routes_to_compute_gradient` — `record_scores.next == "compute_gradient"`
- `test_required_states_exist` — expand `required` set at line 1542 to include `record_scores`, `route_convergence`, `failed`
- `test_compute_gradient_routes_to_route_convergence` — `compute_gradient.next == "route_convergence"` (replaces broken half of `test_compute_gradient_captures_gradient`)
- `test_route_convergence_has_output_contains_evaluator` — `evaluate.type == "output_contains"`, `evaluate.pattern == "CONVERGED"`
- `test_route_convergence_evaluator_source` — `evaluate.source == "${captured.gradient.output}"` (follow pattern from `test_check_semantic_evaluate_has_source` at line 736)
- `test_route_convergence_on_yes_routes_to_done` — `route_convergence.on_yes == "done"`
- `test_route_convergence_on_no_routes_to_append_gradient` — `route_convergence.on_no == "append_gradient"`
- `test_route_convergence_has_on_error` — `"on_error" in route_convergence`
- `test_done_reports_scores_md_and_best_artifacts` — `"scores.md"` and `"best.svg"` and `"best-brief.md"` in `done.action`

### Documentation
- `docs/guides/LOOPS_GUIDE.md:734–801` — update svg-textgrad section (FSM flow diagram at ~line 769, output files table at ~line 786); add `failed` terminal, `record_scores`, `route_convergence` states and update output files list to include `scores.md`, `best.svg`, `best-brief.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:797` — prose explicitly states `on_no` "falls back to `generate`, which then proceeds to `score` using LLM-only judgment" — directly contradicts planned change 5 (the `on_no: generate` path skips scoring); must be corrected alongside the YAML comment fix
- `docs/guides/LOOPS_GUIDE.md:755` — `output_dir` context variable description enumerates output files; add `scores.md`, `best.svg`, `best-brief.md`, `best.txt`
- `docs/guides/LOOPS_GUIDE.md:756` — `pass_threshold` description says "all four criteria must clear this value"; update if weighted average is implemented (planned change 6)
- `docs/guides/LOOPS_GUIDE.md:776–783` — Evaluation criteria table has a "Weight" column showing `visual_clarity` and `originality` as `2×`; update if weights are removed from prompt (planned change 6)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `svg-textgrad.yaml` has **zero `on_error` handlers** across all 9 states and no `failed` terminal — confirmed by reading the full file
- `svg-textgrad.yaml:139` — `compute_gradient` already has `capture: gradient`; its output is addressable as `${captured.gradient.output}` — the `route_convergence` state can read this without any action
- `svg-textgrad.yaml:164–178` — `append_gradient` uses `${state.iteration}` for the iteration counter; `record_scores` should use the same variable
- `svg-image-generator.yaml:104` — exact `on_error: generate` line on `evaluate` state
- `svg-image-generator.yaml:151` — exact `on_error: failed` line on `score` state
- `svg-image-generator.yaml:169–173` — `failed` state is only `terminal: true` with an explanatory comment; no `action_type` or action prompt
- `apo-textgrad.yaml:44–51` — `route_convergence` is a pure routing state (no `action_type`); the `source:` key on its `evaluate` block is required to read from `${captured.gradient.output}` — without `source:`, it reads the current state's own (empty) output
- `apo-textgrad.yaml:40` — `CONVERGED` signal is embedded in the `compute_gradient` prompt instructions; the LLM must be instructed to print `CONVERGED` before `route_convergence` can detect it
- `scripts/tests/test_builtin_loops.py:35–43` — schema validation runs automatically on `svg-textgrad`; new states (including `failed`, `record_scores`, `route_convergence`) will be validated for dangling references and routing completeness with no test file changes needed
- `docs/guides/LOOPS_GUIDE.md:734` — svg-textgrad guide section starts here (not `docs/LOOPS_GUIDE.md` as originally written in the issue)
- `test_loop_schemas.py` does **not exist** — the issue originally referenced a non-existent file; use `test_builtin_loops.py` instead

## Implementation Steps

1. **`svg-textgrad.yaml` — `on_error` handlers + `failed` terminal**: Copy pattern from `svg-image-generator.yaml:104,151,169–173`. Add `on_error: generate` to `evaluate` state (~line 92); add `on_error: failed` to `score` state (~line 137); add bare `failed` terminal state (only `terminal: true`, no action) after `done`.
2. **`svg-textgrad.yaml` — `record_scores` shell state**: Insert between `score.on_no` and `compute_gradient`. Follow `append_gradient` pattern at lines 164–178 using `${state.iteration}`. Parse score values from `critique.md` and append to `scores.md`. Update `score.on_no` → `record_scores` and `record_scores.next` → `compute_gradient`.
3. **`svg-textgrad.yaml` — best-artifact tracking**: Add shell logic to `record_scores` (or a standalone shell state) that compares new scores against `best.txt`; copies `image.svg` → `best.svg` and `brief.md` → `best-brief.md` when score improves.
4. **`svg-textgrad.yaml` — `route_convergence` state**: Change `compute_gradient.next` from `append_gradient` → `route_convergence`. Add the `route_convergence` state reading `source: "${captured.gradient.output}"` (see `apo-textgrad.yaml:44–51`). Enrich the `compute_gradient` prompt with convergence instructions referencing `scores.md`.
5. **`svg-textgrad.yaml` — fix `evaluate.on_no` comment**: Correct the misleading comment to state that `on_no: generate` re-generates without scoring (Playwright screenshot was unavailable or empty).
6. **`svg-textgrad.yaml` — scoring weight consistency**: Either implement weighted average (`(2*vc + 2*orig + craft + scalability)/6 >= threshold`) or remove the 2× weight documentation from the `score` prompt (lines 126–129).
7. **`svg-textgrad.yaml` — update `done` state**: Add `scores.md`, `best.svg`, `best-brief.md` to the artifact list in the `done` prompt (~lines 201–216).
8. **`docs/guides/LOOPS_GUIDE.md:734–801`**: Update FSM flow diagram and output files table to reflect new states (`record_scores`, `route_convergence`, `failed`) and new output files.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **`scripts/tests/test_builtin_loops.py:1580–1583`** — update `test_score_state_routes_to_compute_gradient_on_iterate`: change assertion from `on_no == "compute_gradient"` to `on_no == "record_scores"`
10. **`scripts/tests/test_builtin_loops.py:1585–1589`** — split `test_compute_gradient_captures_gradient` into two tests: one asserting `capture == "gradient"` (unchanged), one asserting `next == "route_convergence"` (was `"append_gradient"`)
11. **`scripts/tests/test_builtin_loops.py` — `TestSvgTextgradLoop`** — add 14 new test methods (see Tests section): `on_error` handlers, `failed` terminal, `record_scores` state, `route_convergence` evaluator chain, expanded `required` states set, `done` artifact references; follow patterns from `TestRecursiveRefineLoop:1031` and `test_check_semantic_evaluate_has_source:736`
12. **`docs/guides/LOOPS_GUIDE.md:797`** — correct on_no prose that says the path "proceeds to `score`"; it does not — it re-generates without scoring

## Scope Boundaries

- Do not change the core TextGrad architecture (plan → generate → evaluate → score → compute_gradient → apply_gradient cycle)
- Do not add multi-candidate generation (out of scope for this pass)
- Do not change the `svg-image-generator` loop as part of this issue

## Impact

- **Priority**: P3 - Loop is functional but loses quality signal in common failure modes
- **Effort**: Small - YAML-only changes, no Python code required; patterns can be copied directly from sibling loops
- **Risk**: Low - additive changes, no structural rewrites; new states extend the DAG without modifying existing state transitions
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_GUIDE.md:734–801` | References svg-textgrad behavior and states |
| `scripts/little_loops/loops/svg-image-generator.yaml` | Source for `on_error`/`failed` pattern |
| `scripts/little_loops/loops/apo-textgrad.yaml` | Source for convergence routing pattern |

## Labels

`enhancement`, `loops`, `svg-textgrad`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-13T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b58bc250-37fe-4a3c-aa5d-a5634a8341f0.jsonl`
- `/ll:wire-issue` - 2026-04-13T22:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2129c183-0b70-41f6-8799-9dacd5b5f99e.jsonl`
- `/ll:refine-issue` - 2026-04-13T21:58:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff5edae9-4701-414b-9704-2fdd2017809d.jsonl`
- `/ll:format-issue` - 2026-04-13T21:53:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae05ca10-09ef-44cc-86ee-cbf1bf87bce1.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29031437-93bc-4a95-a6ec-0b6e91b4455e.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P3
