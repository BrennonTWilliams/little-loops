---
id: FEAT-1098
type: FEAT
priority: P3
discovered_date: 2026-04-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# FEAT-1098: Add svg-textgrad Built-in FSM Loop with Gradient History Tracking

## Summary

Add a new built-in FSM loop `svg-textgrad` that combines TextGrad-style prompt optimization with SVG image generation. Unlike `svg-image-generator` (which passes raw critique directly to the generator), `svg-textgrad` treats `brief.md` as the optimizable prompt and computes structured text gradients to update it. A `gradients.md` log accumulates gradient history so `compute_gradient` can reason about *repeated* failure patterns across iterations, not just the most recent critique.

## Current Behavior

`svg-image-generator` feeds `critique.md` directly back to the `generate` state on each iteration. The generator must reconcile both the brief and the critique simultaneously — conflicting signals on later iterations, and no structured analysis of *why* the brief caused the failure.

`apo-textgrad` provides the TextGrad pattern (FAILURE_PATTERN → ROOT_CAUSE → GRADIENT → apply to prompt) but operates on text prompts against labeled examples, not on creative visual briefs evaluated visually.

No built-in loop combines these two patterns.

## Expected Behavior

A new built-in loop `svg-textgrad` with the following state machine:

```
init → plan → generate → evaluate → score
                ↑                      ↓ (ITERATE)
                └── apply_gradient ← compute_gradient
                                          ↓ (PASS)
                                         done
```

Key behavioral differences from `svg-image-generator`:

1. **`generate` reads only `brief.md`** — not `critique.md`. The brief has already been gradient-updated; the generator follows the brief, not raw critique.
2. **`compute_gradient` state** — computes structured output:
   - `FAILURE_PATTERN`: what is wrong with the generated SVG
   - `ROOT_CAUSE`: what in the brief caused the failure (vague color spec? missing size constraint? contradictory requirements?)
   - `GRADIENT`: precise instruction for how to change the brief to fix this
3. **`gradients.md` log** — each iteration appends the gradient. `compute_gradient` reads the full log to identify *repeated* patterns (systematic brief failures vs. one-off generation noise).
4. **`apply_gradient` state** — rewrites `brief.md` to directly address ROOT_CAUSE and implement GRADIENT.

## Motivation

The TextGrad insight is that gradient-updating the *prompt* (brief) rather than the *artifact* (SVG) produces more systematic improvement. Raw critique feedback to the generator requires the generator to both understand the critique and map it back to the brief — two hops of indirection. Computing a gradient that points at the brief directly shortens this loop.

Gradient history tracking adds a layer `svg-image-generator` lacks entirely: by accumulating gradients across iterations, `compute_gradient` can detect when the same ROOT_CAUSE recurs and escalate its gradient accordingly (stronger structural change vs. a minor tweak).

## Proposed Solution

New file: `scripts/little_loops/loops/svg-textgrad.yaml`

States: `init`, `plan`, `generate`, `evaluate`, `compute_gradient`, `apply_gradient`, `score` (terminal routing), `done`

The `gradients.md` log format per iteration:
```
## Iteration N — [timestamp]
FAILURE_PATTERN: ...
ROOT_CAUSE: ...
GRADIENT: ...
```

`compute_gradient` is prompted to read the full `gradients.md` before computing the new gradient, with explicit instruction to escalate if a ROOT_CAUSE has appeared 2+ times.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml` — new built-in loop (primary deliverable)
- `scripts/tests/test_builtin_loops.py:48-89` — add `"svg-textgrad"` to the `test_expected_loops_exist` canonical set (test uses `assert expected == actual`; it **will fail** without this)
- `scripts/little_loops/loops/README.md` — add loop entry to the Harness category table

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/svg-image-generator.yaml` — reference implementation; svg-textgrad forks from this
- `scripts/little_loops/loops/apo-textgrad.yaml` — reference for gradient state structure

### Similar Patterns
- `svg-image-generator.yaml` — GAN-style harness to derive from (init/plan/evaluate/score/done skeleton)
- `apo-textgrad.yaml` — TextGrad compute_gradient/apply_gradient/route_convergence pattern to adapt
- `apo-opro.yaml` — alternative in-memory history accumulation via `capture: score_history` recycling (no file I/O)
- `html-website-generator.yaml` — sibling harness with identical score/PASS/ITERATE routing structure

### Tests
- `scripts/tests/test_builtin_loops.py:46-91` — `test_expected_loops_exist` uses `assert expected == actual`; add `"svg-textgrad"` to the expected set at line 89 (after `"svg-image-generator"`)
- No behavioral Python unit tests needed (YAML-only loop)
- Manual test: run with a description, verify `gradients.md` accumulates entries, verify `brief.md` is rewritten each iteration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1403-1480` — `TestSvgImageGeneratorLoop` is the direct template; optionally add `TestSvgTextgradLoop` class following the same pattern (top-level fields, required states, routing assertions, context keys, `compute_gradient`→`append_gradient`→`apply_gradient` chain) [Agent 3 finding — new test class, not strictly required but follows established convention for harness loops]
- `test_all_parse_as_yaml` (`test_builtin_loops.py:29-34`) and `test_all_validate_as_valid_fsm` (`test_builtin_loops.py:36-44`) — auto-covered; both iterate all `*.yaml` files via glob and will validate `svg-textgrad.yaml` without any changes [Agent 3 finding — no action needed]

### Documentation
- `docs/guides/loops/` — add `svg-textgrad.md` guide once loop is stable
- Loop catalog if one exists

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:91` — hardcoded `**40 FSM loops**` count becomes stale; update to `**41 FSM loops**` [Agent 2 finding — established pattern: FEAT-1094 updated this same line when `svg-image-generator` was added]
- `docs/guides/LOOPS_GUIDE.md:614-619` — Harness Examples table lists current harness loops; add `svg-textgrad` row after `svg-image-generator`; line 621 prose enumerates `html-website-generator` and `svg-image-generator` by name and may warrant a mention of `svg-textgrad` [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:739-740` — Further Reading "Real-world GAN-style harness" list names `svg-image-generator.yaml` and `html-website-generator.yaml` explicitly; optionally add `svg-textgrad.yaml` entry [Agent 2 finding — optional]

### Configuration
- `context.pass_threshold: 6` (same default as `svg-image-generator`)
- `context.output_dir: ".loops/tmp/svg-textgrad"`

## Implementation Steps

1. **Create `svg-textgrad.yaml`** — Copy `svg-image-generator.yaml` as the skeleton. Keep `init`, `evaluate`, `score`, `done` states intact. Change one thing: `score` routing from `on_no: generate` → `on_no: compute_gradient` (the single most important divergence). Update `generate` to remove the conditional `critique.md` read (lines 70-71 of svg-image-generator.yaml); it reads only `brief.md`.
2. **Extend `init` shell state** — After `mkdir -p "$DIR"`, add `touch "$DIR/gradients.md"` to initialize the log before any state reads it. (Pattern: `svg-image-generator.yaml:24-35`)
3. **Implement `compute_gradient` state** (prompt) — Instruct Claude to: (a) read `${captured.run_dir.output}/brief.md`, `${captured.run_dir.output}/critique.md`, and `${captured.run_dir.output}/gradients.md`; (b) check whether the same ROOT_CAUSE appears 2+ times in the history and escalate if so; (c) output exactly three labeled lines: `FAILURE_PATTERN:`, `ROOT_CAUSE:`, `GRADIENT:`. Set `capture: gradient`. Transition: `next: append_gradient`.
4. **Add `append_gradient` shell state** — Appends the captured gradient to the file log: `printf '## Iteration %s — %s\n%s\n\n' "${state.iteration}" "$(date -u +%Y%m%dT%H%M%SZ)" "${captured.gradient.output}" >> "${captured.run_dir.output}/gradients.md"`. Transition: `next: apply_gradient`. (Pattern from `issue-refinement.yaml:34-39`)
5. **Implement `apply_gradient` state** (prompt) — Read `${captured.run_dir.output}/brief.md`, incorporate `${captured.gradient.output}` addressing the ROOT_CAUSE directly, and overwrite `${captured.run_dir.output}/brief.md` with the rewritten brief. Transition: `next: generate`. (Pattern from `apo-textgrad.yaml:52-62`)
6. **Update `test_builtin_loops.py:89`** — Add `"svg-textgrad"` to the expected set in `test_expected_loops_exist` after `"svg-image-generator"`. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles -v` to confirm.
7. **Update `loops/README.md`** — Add `svg-textgrad` to the Harness category table with description: "TextGrad-style SVG harness; optimizes the brief via structured gradient updates across iterations, with gradient history accumulation".
8. **Manual test** — Run `ll-loop run svg-textgrad --input "a geometric fox head icon"`, inspect `gradients.md` after 3+ iterations to verify accumulation, verify `brief.md` is rewritten each iteration.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `README.md:91` — change `**40 FSM loops**` to `**41 FSM loops**` (established pattern: this line was updated from 39→40 when `svg-image-generator` was added in FEAT-1094)
10. Update `docs/guides/LOOPS_GUIDE.md:614-619` — add `svg-textgrad` row to the Harness Examples table after the `svg-image-generator` row; optionally update line 621 GAN-style prose to mention `svg-textgrad`
11. _(Optional)_ Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:739-740` — add `svg-textgrad.yaml` entry to the "Real-world GAN-style harness" Further Reading list alongside `svg-image-generator.yaml`
12. _(Optional)_ Add `TestSvgTextgradLoop` class to `scripts/tests/test_builtin_loops.py` after `TestSvgImageGeneratorLoop` (line 1480), following the same structural pattern: top-level fields, required states set, `compute_gradient`→`append_gradient`→`apply_gradient` routing chain, `context` keys

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**FSM engine interpolation namespaces** (`fsm/interpolation.py:65-165`):
- `${context.*}` — values from the YAML `context:` block
- `${captured.<varname>.output}` — stdout from a prior `capture:` shell/prompt state
- `${state.iteration}` — current iteration counter (use this for gradient log headers)
- `${loop.name}` — loop name for reference

**Prompt vs shell state file I/O** (`fsm/runners.py:86-170`):
- Shell states: file I/O via bash commands directly; `capture:` stores stdout into `self.captured`
- Prompt states: file I/O via Claude's Write/Bash tools; `action:` string is the instruction to Claude

**`score` state routing change** (critical — differs from reference implementation):
- `svg-image-generator.yaml`: `score` routes `on_no: generate`
- `svg-textgrad` requires: `score` routes `on_no: compute_gradient`

**Full corrected state list** (issue body omits `append_gradient`):
`init` → `plan` → `generate` → `evaluate` → `score` → (`PASS`) `done` / (`ITERATE`) `compute_gradient` → `append_gradient` → `apply_gradient` → `generate`

**`evaluate.source:` override** (`executor.py:673-679`) — lets an evaluate block check previously captured text. Used in `apo-textgrad.yaml`'s `route_convergence` state. Not needed for svg-textgrad since `score` is the convergence gate.

**`test_expected_loops_exist` assertion** (`test_builtin_loops.py:91`) — uses `assert expected == actual`; the test **fails** if svg-textgrad is in the loops dir but not in the expected set. Must add before running tests.

## Impact

- **Priority**: P3 — Useful addition to the built-in loop catalog; no production urgency
- **Effort**: Small — Pure YAML, derives directly from two existing loops
- **Risk**: Low — New file only, no modifications to existing loops or Python
- **Breaking Change**: No

## Use Case

User runs:
```bash
ll-loop svg-textgrad --input "a geometric fox head icon for a developer tools brand"
```

After 3 iterations, `gradients.md` shows the brief's color spec was too vague twice. On iteration 4, `compute_gradient` detects the recurrence and escalates the gradient to specify exact hex values. The final brief is more precise, and the generator produces a passing SVG without further iteration.

## Acceptance Criteria

- [ ] `svg-textgrad.yaml` exists in `scripts/little_loops/loops/`
- [ ] `generate` state does not reference `critique.md`
- [ ] `compute_gradient` state produces FAILURE_PATTERN, ROOT_CAUSE, GRADIENT
- [ ] Each iteration appends to `gradients.md` with iteration number
- [ ] `compute_gradient` is prompted to read full `gradients.md` and escalate on repeated ROOT_CAUSE
- [ ] `apply_gradient` overwrites `brief.md`
- [ ] Loop reaches `done` on a simple description within 20 iterations

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `harness`, `captured`

## Status

**Open** | Created: 2026-04-13 | Priority: P3

---

## Session Log
- `/ll:confidence-check` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdedf90e-4d4e-4f89-b815-b5c239501618.jsonl`
- `/ll:wire-issue` - 2026-04-13T19:20:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee2a7734-4c20-43d2-81d7-7fc7742b4beb.jsonl`
- `/ll:refine-issue` - 2026-04-13T19:00:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0a940ed-94f1-4edf-888f-181582227a03.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ec013ba-177c-4041-8da5-23ee6cecf9a6.jsonl`
