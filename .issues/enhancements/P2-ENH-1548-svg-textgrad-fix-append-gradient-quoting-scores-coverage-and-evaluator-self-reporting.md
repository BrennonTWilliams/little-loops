---
id: 1548
type: ENH
priority: P2
status: open
captured_at: "2026-05-17T08:08:24Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
source_loop: svg-textgrad
source_run: "2026-05-17T07:44:12"
---

# ENH-1548: svg-textgrad — fix append_gradient quoting, scores.md coverage, and evaluator self-reporting

## Summary

Four improvements identified during a post-run audit of the svg-textgrad FSM loop (run: 2026-05-17T07:44:12, 20 iterations, verdict: partial). Two are reproducible contract bugs with evidence; two are design enhancements.

1. **[Bug] append_gradient shell quoting** — `gradients.md` remained 0 bytes for the entire run due to exit code 2 on both iteration 9 and 17, disabling convergence detection
2. **[Bug] scores.md under-populated** — only 2 of 20 iterations recorded in `scores.md`; `record_scores` only runs on the ITERATE path, so `compute_gradient`'s convergence check (requires 3 iterations) can never trigger
3. **[Enhancement] max_iterations too low** — 20 iterations insufficient for a 4-criterion weighted rubric; convergence guard is the intended exit but was non-functional due to Bug 1
4. **[Enhancement] Self-reported score evaluator** — the `score` state judges its own weighted-average math via `output_contains`; no external shell verification, creating rubric-drift risk

## Current Behavior

**Bug 1 — append_gradient (exit code 2):**
The `append_gradient` state embeds `${captured.gradient.output}` (multi-line, contains backticks, colons, markdown) directly into a `printf` argument. The shell exits with code 2 when the gradient string contains characters that break quoting. `gradients.md` stays empty, so `compute_gradient` never detects repeated ROOT_CAUSE patterns and cannot escalate gradient strength.

**Bug 2 — scores.md coverage:**
`record_scores` is only reachable via `score → on_no → record_scores`. When the loop is terminated by `max_iterations` mid-run, or when `score` exits via `on_yes` (rare) or `on_error`, `scores.md` receives no entry. The audit run scored iterations 6 and 14 but ran 20 total; `compute_gradient`'s convergence check (3+ `## Iteration` sections) never had enough data to trigger.

**Enhancement 3 — max_iterations:**
Loop ran all 20 iterations without passing. Scored iterations: iter 6 ~5.83 weighted avg, iter 14 ~5.67. Weighted average tracks below pass_threshold=6 throughout. With convergence detection broken (Bug 1), the loop had no early-exit guard. Even with both bugs fixed, 20 iterations may be tight for a brief that must satisfy `scalability` (icon-scale legibility) when the description is inherently document-scale (e.g., "terminal keybindings reference card").

**Enhancement 4 — self-reported evaluator:**
`score` state writes scores to `critique.md`, then checks its own `stdout` for `"ALL_PASS"` via `output_contains`. The LLM both scores and decides pass/fail on its own arithmetic. No external process verifies that the scores in `critique.md` match the computed weighted average.

## Expected Behavior

1. `append_gradient` writes gradient output via a temp file (`printf '%s\n' ... > tmp; cat tmp >> gradients.md`); exits 0 on every iteration; `gradients.md` accumulates gradient history
2. Every iteration that reaches `score` appends a score row to `scores.md`, regardless of ALL_PASS/ITERATE routing; convergence detection activates after 3 iterations
3. `max_iterations` raised to 40 (or a new `max_iterations` context override supported), so the convergence guard — not the iteration budget — is the primary exit
4. A shell state after `score` reads `critique.md`, computes the weighted average externally, and performs the routing decision; the `score` prompt no longer outputs `ALL_PASS`/`ITERATE`

## Motivation

The TextGrad optimization premise depends on: (a) accumulating gradient history so `compute_gradient` can detect repeating failure modes and escalate, and (b) convergence detection so the loop exits early when progress plateaus. Both mechanisms were completely non-functional in the audit run. Without gradient history, every iteration applies a gradient blind. Without convergence detection, the loop always runs to `max_iterations`. Fixing these restores the core TextGrad loop contract.

The external evaluator improvement (4) prevents the LLM from inflating scores to bypass the loop early — a known failure mode in self-evaluating optimization loops.

## Proposed Solution

**Fix 1 — append_gradient quoting:**
```yaml
states:
  append_gradient:
    action: |
      DIR="${captured.run_dir.output}"
      ITER="${state.iteration}"
      TS=$(date -u +%Y%m%dT%H%M%SZ)
      printf '%s\n' "${captured.gradient.output}" > "$DIR/.gradient_tmp.txt"
      {
        printf '## Iteration %s — %s\n' "$ITER" "$TS"
        cat "$DIR/.gradient_tmp.txt"
        printf '\n'
      } >> "$DIR/gradients.md"
      rm -f "$DIR/.gradient_tmp.txt"
    next: apply_gradient
```

**Fix 2 — scores.md in score state:**
Move the `scores.md` append from `record_scores` into the `score` prompt action (as a shell step before the ALL_PASS/ITERATE routing output), OR split `score` into two states: `score_write` (writes critique.md + scores.md) and `score_evaluate` (reads critique.md and outputs routing signal). The simpler approach: add a shell post-step in `score` that appends scores before the LLM outputs its routing decision.

Alternative: keep `record_scores` but also add a shell append to the `score` state's `action` as an embedded shell line before the ALL_PASS/ITERATE computation. Since `score` is `action_type: prompt`, the cleanest fix is to duplicate the append logic as a separate shell call embedded in the prompt, or restructure `score` → `write_scores` (shell) → `evaluate_scores` (prompt).

**Fix 3 — raise max_iterations:**
```yaml
max_iterations: 40
```
Or add a context variable:
```yaml
context:
  max_iterations_override: 40
```
so callers can tune without editing the loop definition.

**Fix 4 — external score verification:**
Add a `verify_score` shell state after the `score` prompt:
```yaml
verify_score:
  action_type: shell
  action: |
    DIR="${captured.run_dir.output}"
    VC=$(grep -E "^visual_clarity: [0-9]+" "$DIR/critique.md" | grep -oE "[0-9]+" | head -1)
    OG=$(grep -E "^originality: [0-9]+" "$DIR/critique.md" | grep -oE "[0-9]+" | head -1)
    CR=$(grep -E "^craft: [0-9]+" "$DIR/critique.md" | grep -oE "[0-9]+" | head -1)
    SC=$(grep -E "^scalability: [0-9]+" "$DIR/critique.md" | grep -oE "[0-9]+" | head -1)
    THRESH="${context.pass_threshold}"
    # Weighted avg * 6 >= threshold * 6 avoids floats
    WEIGHTED=$((2*VC + 2*OG + CR + SC))
    DENOM=6
    # Pass if WEIGHTED/DENOM >= THRESH, i.e. WEIGHTED >= THRESH*DENOM
    if [ "$WEIGHTED" -ge "$((THRESH * DENOM))" ]; then
      echo "SHELL_PASS"
    else
      echo "SHELL_ITERATE"
    fi
  evaluate:
    type: output_contains
    pattern: "SHELL_PASS"
  on_yes: done
  on_no: record_scores
  on_error: record_scores
```
The `score` prompt then no longer needs to output `ALL_PASS`/`ITERATE` — it only writes `critique.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml` — states `append_gradient`, `score`, `record_scores` (possibly removed); add `verify_score`; raise `max_iterations`

### Dependent Files (Callers/Importers)
- `ll-loop run svg-textgrad` invocations — behavioral change: `gradients.md` and `scores.md` now populate reliably; routing logic moves from prompt output to shell arithmetic

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml` — reference for shell-state patterns; check if similar shell-quoting issues exist in its `action` blocks

### Tests
- No existing automated tests for `svg-textgrad.yaml` loop states; manual verification via `ll-loop run svg-textgrad "a terminal keybindings reference card" --max-iterations 5` as described in Implementation Steps #6

### Documentation
- N/A — no docs reference `svg-textgrad.yaml` internals

### Configuration
- `max_iterations` top-level field in `svg-textgrad.yaml` (raised from 20 to 40)
- Fix 2 (scores.md) is a prerequisite for convergence detection in `compute_gradient`; Fix 1 (gradient quoting) is prerequisite for gradient escalation in `compute_gradient`

## Implementation Steps

1. Fix `append_gradient` — replace `printf '%s\n' "$GRAD"` with temp-file pattern (Fix 1)
2. Move scores.md append into `score` state or add `verify_score` shell state (Fix 2 + Fix 4 can be combined: `verify_score` shell state reads critique.md, appends scores.md, and computes routing — replaces `record_scores` and removes self-reporting from `score` prompt)
3. Remove the ALL_PASS/ITERATE output instruction from the `score` prompt (now handled by `verify_score`)
4. Update routing: `score → verify_score → done/record_scores` (or `score → done/verify_score` if keeping separate)
5. Raise `max_iterations: 40`
6. Run `ll-loop run svg-textgrad "a terminal keybindings reference card" --max-iterations 5` and verify: gradients.md non-empty after iteration 1, scores.md has an entry after iteration 1, verify_score shell routes correctly

## Scope Boundaries

**In scope:**
- `svg-textgrad.yaml` states: `append_gradient` (shell quoting fix), `score` (remove self-reported routing), `record_scores` (possibly removed), `verify_score` (new shell state)
- `max_iterations` field (raise to 40)

**Out of scope:**
- Other loops (`svg-image-generator.yaml`, etc.) — no cross-loop changes even if similar shell-quoting patterns exist
- Loop executor, FSM runner, or `orchestrator.py` — no Python changes
- `compute_gradient` escalation logic — thresholds and escalation rules unchanged
- General shell-quoting audit of all loop YAML files — this fix is svg-textgrad only

## Impact

- **Priority**: P2 — Both bugs completely disable core TextGrad mechanisms (gradient accumulation and convergence detection), but the loop still produces output; not a crash-level failure
- **Effort**: Small — All changes are isolated to `svg-textgrad.yaml`; no Python code changes; 4 targeted edits to YAML states and one integer update
- **Risk**: Low — Changes are scoped to one loop file; no breaking changes to the FSM executor, Python modules, or other loops
- **Breaking Change**: No — `ll-loop run svg-textgrad` call signature is unchanged; output files (`gradients.md`, `scores.md`, `critique.md`) still produced in same locations

**Value restored:**
- **Gradient history**: `compute_gradient` can detect repeated root causes and escalate; currently always reads an empty file
- **Convergence detection**: 3-iteration plateau check becomes functional; loop can exit early instead of burning all 40 iterations
- **Rubric integrity**: external shell arithmetic prevents LLM from self-certifying pass when math doesn't support it
- **Audit trail**: `scores.md` accurately reflects every scored iteration, making post-run analysis meaningful

## Success Metrics

- `gradients.md` is non-empty after iteration 1 (Fix 1: shell quoting verified)
- `scores.md` has one entry per scored iteration, regardless of ALL_PASS/ITERATE routing path (Fix 2: universal append verified)
- `verify_score` shell state routes to `done` when weighted average ≥ `pass_threshold` and to `record_scores` otherwise (Fix 4: external routing verified)
- Loop exits via convergence detection (3-iteration plateau in `compute_gradient`) before `max_iterations: 40` when the brief produces plateauing scores (Fixes 1+2 enable this path)
- Verification command: `ll-loop run svg-textgrad "a terminal keybindings reference card" --max-iterations 5` produces non-empty `gradients.md` and `scores.md` after the first scored iteration

## Related Key Documentation

- `scripts/little_loops/loops/svg-textgrad.yaml` — affected loop definition
- `scripts/little_loops/loops/svg-image-generator.yaml` — reference for shell-state patterns

## Labels

loop, svg-textgrad, shell-quoting, convergence-detection, textgrad

## Status

**Open** | Created: 2026-05-17 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-17T08:11:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4976d4f8-c206-4101-b4ca-7f83eeb1d1f4.jsonl`
- `/ll:capture-issue` - 2026-05-17T08:08:24Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ccc2e272-5433-4234-bd5a-8b2343569a3a.jsonl`
