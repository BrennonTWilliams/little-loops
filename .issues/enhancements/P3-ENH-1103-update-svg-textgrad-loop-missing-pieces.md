---
discovered_date: "2026-04-13"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
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
- `svg-textgrad.yaml:32` — `init` state calls `touch "$DIR/gradients.md"` but does NOT touch `scores.md`; `record_scores` will create `scores.md` on first write, but `compute_gradient` reads it on every pass (including iteration 1 before `record_scores` has run) — `init` must also call `touch "$DIR/scores.md"` to prevent read errors
- `critique.md` line format from `score` prompt: `visual_clarity: N/10 — [explanation]`; `grep -oP "^visual_clarity: \K[0-9]+"` extracts the integer score — this pattern works for all four criteria; on macOS (no `-P` flag), use `grep -E "^visual_clarity: [0-9]+" | grep -oE "[0-9]+" | head -1` instead
- Best-artifact tracking uses weighted sum `2*vc + 2*orig + craft + scalability` (max=60) — same weights as documented in score prompt; combining best-artifact tracking and score recording in one `record_scores` state is cleaner than a separate shell state since both read `critique.md`
- `apo-textgrad.yaml:40` — convergence detection instruction in `compute_gradient` prompt: `"If PASS_RATE=100 or PASS_RATE exceeds ${context.target_pass_rate}, output CONVERGED on its own line instead."` — svg-textgrad uses score history instead of pass rate; adapt to: check last 3 `## Iteration` sections in `scores.md` for any score improvement
- `svg-image-generator.yaml` score prompt (lines 138–145) has identical weight notation (`2×`) and identical flat pass condition (`ALL four individual scores >= threshold`) — both loops share this inconsistency; svg-textgrad fix applies the same pattern that svg-image-generator has but never implemented

## Implementation Steps

1. **`svg-textgrad.yaml` — `on_error` handlers + `failed` terminal**: Copy pattern from `svg-image-generator.yaml:104,151,169–173`. Add `on_error: generate` to `evaluate` state (~line 92); add `on_error: failed` to `score` state (~line 137); add bare `failed` terminal state (only `terminal: true`, no action) after `done`. Also add `touch "$DIR/scores.md"` to `init` at line 32 alongside the existing `touch "$DIR/gradients.md"` — `compute_gradient` reads `scores.md` on iteration 1 and will error if the file doesn't exist.
2. **`svg-textgrad.yaml` — `record_scores` shell state**: Insert between `score.on_no` and `compute_gradient`. Combine score recording and best-artifact tracking in a single shell state:
   ```yaml
   record_scores:
     action_type: shell
     action: |
       DIR="${captured.run_dir.output}"
       ITER="${state.iteration}"
       # --- Append scores to history ---
       grep -E "^(visual_clarity|originality|craft|scalability):" "$DIR/critique.md" \
         | awk -v iter="$ITER" 'BEGIN{printf "## Iteration %s\n", iter} {print}' \
         >> "$DIR/scores.md"
       echo "" >> "$DIR/scores.md"
       # --- Best-artifact tracking (weighted sum: 2×vc + 2×orig + craft + scalability) ---
       VC=$(grep -oP "^visual_clarity: \K[0-9]+" "$DIR/critique.md" 2>/dev/null || echo 0)
       OG=$(grep -oP "^originality: \K[0-9]+" "$DIR/critique.md" 2>/dev/null || echo 0)
       CR=$(grep -oP "^craft: \K[0-9]+" "$DIR/critique.md" 2>/dev/null || echo 0)
       SC=$(grep -oP "^scalability: \K[0-9]+" "$DIR/critique.md" 2>/dev/null || echo 0)
       TOTAL=$((2*VC + 2*OG + CR + SC))
       BEST=$(cat "$DIR/best.txt" 2>/dev/null || echo 0)
       if [ "$TOTAL" -gt "$BEST" ]; then
         echo "$TOTAL" > "$DIR/best.txt"
         cp "$DIR/image.svg" "$DIR/best.svg"
         cp "$DIR/brief.md" "$DIR/best-brief.md"
       fi
     next: compute_gradient
   ```
   Update `score.on_no` → `record_scores`. Note: `grep -oP` requires GNU grep (standard on Linux; on macOS use `grep -E "^visual_clarity: [0-9]+" | grep -oE "[0-9]+" | head -1` as fallback).
3. **`svg-textgrad.yaml` — `route_convergence` state**: Change `compute_gradient.next` from `append_gradient` → `route_convergence`. Add the `route_convergence` state reading `source: "${captured.gradient.output}"` (see `apo-textgrad.yaml:44–51`). Update the `compute_gradient` prompt with these exact additions:
   - Add to the file list: `- ${captured.run_dir.output}/scores.md — per-iteration score history (format: "## Iteration N" header, then four scored lines)`
   - Add before the "Output exactly three labeled lines" section: `First, read scores.md. If the last 3 recorded ## Iteration sections show no improvement in any individual score (visual_clarity, originality, craft, or scalability all flat or declining across those 3 iterations), output CONVERGED on its own line and nothing else.`
4. **`svg-textgrad.yaml` — fix `evaluate.on_no` comment**: Correct line 84 comment `"can still make progress via LLM-only scoring if Playwright is unavailable"` — the `on_no: generate` path does NOT score; it re-generates from the existing brief without any evaluation. Change comment to: `"Routes back to generate; no scoring occurs — loop continues with the unchanged brief."` Also fix `docs/guides/LOOPS_GUIDE.md:797`.
5. **`svg-textgrad.yaml` — scoring weight consistency**: Implement weighted average for consistency with the best-artifact tracking formula (`TOTAL = 2*vc + 2*orig + cr + sc`). Replace the pass condition at line 131 from `If ALL four individual scores are >= ${context.pass_threshold}` to: `Compute the weighted average: (2 × visual_clarity + 2 × originality + craft + scalability) / 6. If the weighted average >= ${context.pass_threshold}, output exactly: PASS`. This makes the documented 2× weights functionally meaningful rather than decorative. Update `docs/guides/LOOPS_GUIDE.md:756` to say "weighted average of the four criteria must clear this value" instead of "all four criteria".
6. **`svg-textgrad.yaml` — update `done` state**: Add `scores.md`, `best.svg`, `best-brief.md` to the artifact list in the `done` prompt (currently lines 201–216). The `best.*` files may not exist if the loop exits via `max_iterations` before any score is recorded — mention them conditionally: `"best.svg / best-brief.md — best-scoring iteration artifacts (present if at least one score was recorded)"`.
7. **`docs/guides/LOOPS_GUIDE.md:734–801`**: Update FSM flow diagram and output files table to reflect new states (`record_scores`, `route_convergence`, `failed`) and new output files. Updated FSM flow:
   ```
   init → plan → generate → evaluate
                               ├─ CAPTURED → score
                               │              ├─ PASS    → done
                               │              ├─ ITERATE → record_scores → compute_gradient → route_convergence
                               │              │                                                    ├─ CONVERGED → done
                               │              │                                                    └─ continue  → append_gradient → apply_gradient → generate
                               │              └─ ERROR   → failed
                               ├─ FAILED  → generate
                               └─ ERROR   → generate
   ```

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

## Resolution

**Completed**: 2026-04-13

**Changes made**:
- `scripts/little_loops/loops/svg-textgrad.yaml`: Added `on_error: generate` to `evaluate`; added `on_error: failed` and rerouted `on_no` → `record_scores` on `score`; updated pass condition to weighted average; added `record_scores` shell state (score history + best-artifact tracking); changed `compute_gradient.next` → `route_convergence` and added scores.md to its file list + convergence detection instruction; added `route_convergence` state reading from `${captured.gradient.output}`; updated `done` to list `scores.md`, `best.svg`, `best-brief.md`; added `failed` terminal state; added `touch "$DIR/scores.md"` to `init`.
- `scripts/tests/test_builtin_loops.py`: Fixed `test_score_state_routes_to_compute_gradient_on_iterate` → `test_score_state_routes_to_record_scores_on_iterate`; split `test_compute_gradient_captures_gradient` (added `test_compute_gradient_routes_to_route_convergence`); expanded `test_required_states_exist` with `record_scores`, `route_convergence`, `failed`; added 14 new test methods covering all new states.
- `docs/guides/LOOPS_GUIDE.md`: Updated FSM flow diagram; updated output files table; corrected `pass_threshold` description to weighted average; corrected misleading `on_no` note; updated evaluation criteria header.

**Verification**: 207 tests pass, ruff lint clean.

## Session Log
- `/ll:manage-issue` - 2026-04-13T00:00:00Z - current session
- `/ll:ready-issue` - 2026-04-14T01:49:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/818b13e2-fdc2-4dc3-8847-f1cf51da41a9.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2a35301-9e9f-472b-891c-b2b8d87d943d.jsonl`
- `/ll:refine-issue` - 2026-04-14T01:23:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93817ff5-e7c7-47c7-8e1e-21ed9f2139ab.jsonl`
- `/ll:confidence-check` - 2026-04-13T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b58bc250-37fe-4a3c-aa5d-a5634a8341f0.jsonl`
- `/ll:wire-issue` - 2026-04-13T22:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2129c183-0b70-41f6-8799-9dacd5b5f99e.jsonl`
- `/ll:refine-issue` - 2026-04-13T21:58:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff5edae9-4701-414b-9704-2fdd2017809d.jsonl`
- `/ll:format-issue` - 2026-04-13T21:53:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae05ca10-09ef-44cc-86ee-cbf1bf87bce1.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29031437-93bc-4a95-a6ec-0b6e91b4455e.jsonl`

---

**Completed** | Created: 2026-04-13 | Priority: P3
