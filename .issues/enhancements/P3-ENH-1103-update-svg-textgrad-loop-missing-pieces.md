---
discovered_date: "2026-04-13"
discovered_by: capture-issue
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

Add a `route_convergence` state (like `apo-textgrad`) that routes `CONVERGED` → `done`, otherwise → `append_gradient`.

**5. Fix evaluate comment** — correct the misleading comment to say regeneration happens without scoring.

**6. Scoring weight consistency** — either implement weighted average (`(2*vc + 2*orig + craft + scalability)/6 >= threshold`) or remove the weight documentation from the `score` prompt.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml` — primary change target

### Dependent Files (Callers/Importers)
- `scripts/tests/test_loop_schemas.py` — may validate loop YAML structure
- `docs/` — `LOOPS_GUIDE.md` references svg-textgrad behavior

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml` — `on_error`/`failed` pattern to copy
- `scripts/little_loops/loops/apo-textgrad.yaml` — `route_convergence` + `CONVERGED` pattern to copy

### Tests
- No unit tests for loop YAML content; manual run test recommended
- `scripts/tests/test_loop_schemas.py` — verify new states pass schema validation if applicable

### Documentation
- `docs/LOOPS_GUIDE.md` — update svg-textgrad section to reflect new states and convergence behavior

### Configuration
- N/A

## Implementation Steps

1. Add `on_error` to `evaluate` and `score` states; add `failed` terminal
2. Add `record_scores` shell state between `score` and `compute_gradient`; update routing
3. Add best-artifact tracking (shell logic in `record_scores` or standalone state)
4. Add convergence detection to `compute_gradient` prompt; add `route_convergence` state
5. Fix misleading `evaluate.on_no` comment
6. Resolve weight documentation vs. pass condition inconsistency
7. Update `done` state to report `scores.md`, `best.svg`, `best-brief.md`
8. Update `LOOPS_GUIDE.md` documentation

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
| `docs/LOOPS_GUIDE.md` | References svg-textgrad behavior and states |
| `scripts/little_loops/loops/svg-image-generator.yaml` | Source for `on_error`/`failed` pattern |
| `scripts/little_loops/loops/apo-textgrad.yaml` | Source for convergence routing pattern |

## Labels

`enhancement`, `loops`, `svg-textgrad`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29031437-93bc-4a95-a6ec-0b6e91b4455e.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P3
