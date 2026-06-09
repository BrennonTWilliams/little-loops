---
id: ENH-2045
title: Port rlhf-animated-svg harness patterns to vega-viz loop
type: ENH
priority: P3
status: deferred
captured_at: '2026-06-09T16:04:37Z'
discovered_date: 2026-06-09
discovered_by: capture-issue
labels:
- loops
- fsm
- harness
- visualization
- vega
relates_to:
- ENH-2010
confidence_score: 94
outcome_confidence: 72
score_complexity: 20
score_test_coverage: 12
score_ambiguity: 20
score_change_surface: 20
implementation_order_risk: true
size: Very Large
---

# ENH-2045: Port rlhf-animated-svg harness patterns to vega-viz loop

## Summary

Port four proven harness patterns from `rlhf-animated-svg` into `vega-viz` to give it regression protection, stuck-loop escalation, adaptive optimization phases, and a cheap artifact existence gate — without touching its architecture or the vega-specific states (`resolve_data`, `validate`, `repair`, `record`).

## Motivation

`vega-viz` currently has no protection against iterating in a degrading direction (it overwrites `best.html` on every pass regardless of score), no mechanism to force a mark/encoding pivot when scores are stuck, and no phase-aware strategy to avoid premature convergence. All four patterns below are already proven in `rlhf-animated-svg` and translate cleanly to Vega's generate→score loop.

## Current Behavior

`vega-viz` overwrites `best.html` on every iteration regardless of score — a run that degrades in later iterations terminates with the last iteration's artifact, not the highest-scoring one. There is no mechanism to detect score plateaus or regressions, no forced concept pivot when iteration scores are stuck, and no phase-aware prompting to balance exploration vs. convergence across the loop's lifetime.

## Expected Behavior

After the port, `vega-viz` will:
- Restore the highest-scoring `best.html` as the final output artifact regardless of which iteration last ran (`restore_best` terminal state)
- Detect score regressions during `record` and route back to `generate` with `SCORE_REGRESSION` context before the artifact is overwritten
- Escalate to a grammar or mark/encoding pivot after N consecutive non-improving iterations (`check_score_streak` → `concept_reset`)
- Apply explore → exploit → converge phase-aware prompting in both `generate` and `score` states
- Gate artifact capture on a confirmed render file existence via `verify_render` before `capture`

## Scope

Four targeted changes to `scripts/little_loops/loops/vega-viz.yaml`:

### Item 1 — Regression guard + `restore_best` terminal state

**In `record`**: after updating `best_score.txt`, add a regression check. If `current_score < best_score - tolerance` (tolerance = `best_score * 0.25` during explore, `* 0.15` during converge), copy `best.html` → `index.html` before routing to `generate`, and emit `SCORE_REGRESSION` to stderr/stdout so the generator sees it.

**New `restore_best` shell state** inserted between `write_final_summary` (if added) and `done`: mechanically copies `best.html` → `index.html` on termination so the best-scored artifact is always the final output, regardless of which iteration last ran.

```yaml
restore_best:
  action_type: shell
  action: |
    DIR="${captured.run_dir.output}"
    if [ -f "$DIR/best.html" ]; then
      cp "$DIR/best.html" "$DIR/index.html"
      echo "RESTORED_BEST_AT_TERMINATION"
    else
      echo "NO_BEST_CHECKPOINT"
    fi
  next: done
```

**`done` routes through `restore_best`** instead of being reached directly from `record`.

### Item 2 — Score-streak escalation (`check_score_streak` + `_score_streak_route` + `concept_reset`)

Add three states that activate after N consecutive `ITERATE` verdicts without a score improvement:

```yaml
context:
  score_fail_streak_max: 3          # new
  replan_escalation_threshold: 2    # new
```

**`check_score_streak`** (shell): counts consecutive `ITERATE` outcomes via `.score_fail_streak` file. When streak ≥ `score_fail_streak_max`, checks `.score_replan_count` — if below `replan_escalation_threshold`, emits `REPLAN`; if at or above, emits `CONCEPT_RESET`. Resets streak on escalation.

**`_score_streak_route`** (evaluate-only): routes `REPLAN` → `generate` (with escalation context), `CONCEPT_RESET` → `concept_reset`.

**`concept_reset`** (prompt): reads current `index.html` and `critique.md`, identifies the current chart type and encoding, then forces a plan for a fundamentally different approach — grammar escalation (Vega-Lite → full Vega) if applicable, otherwise a mark/encoding pivot (e.g., bar → scatter, line → area+points). Routes to `generate`.

`record`'s `on_no` path routes to `check_score_streak` instead of directly to `generate`.

### Item 4 — Optimization phase awareness in `generate` and `score`

Add context vars:

```yaml
context:
  explore_cutoff: 4     # iterations 1–4: diverse approaches
  exploit_cutoff: 12    # iterations 5–12: target lowest-scoring dimension
                        # iterations 13+: converge — minimal safe changes
```

**In `generate`**: inject an optimization phase block keyed on `${state.iteration}` vs the cutoffs. Explore phase: prefer novel chart types and encodings over incremental fixes; pivot freely. Exploit phase: focus on the single lowest-scoring criterion from `critique.md`; be surgical. Converge phase: apply only changes with high confidence; skip structural changes.

**In `score`**: inject phase context so the judge knows whether to reward exploration diversity (explore) or penalize regression risk (converge). In converge phase, add explicit instruction: "penalize any change that introduces visual regression even if the new direction is interesting."

### Item 6 — `verify_render` gate before `capture`

Insert a cheap shell state between `validate`'s `on_yes` path and `capture`:

```yaml
verify_render:
  action_type: shell
  action: |
    DIR="${captured.run_dir.output}"
    if [ -f "$DIR/index.html" ]; then
      echo "RENDER_EXISTS"
    else
      echo "RENDER_MISSING" >&2
      exit 1
    fi
  evaluate:
    type: output_contains
    pattern: "RENDER_EXISTS"
  on_yes: capture
  on_no: generate
  on_error: generate
```

`validate`'s `on_yes` routes to `verify_render` instead of directly to `capture`.

## Implementation Notes

- Do not touch `resolve_data`, `validate`, `repair`, `plan`, or the `capture` interaction logic.
- `record`'s deterministic VERDICT routing is a strength — keep it. The regression guard is an additive extension, not a replacement.
- The per-criterion hard-gate scoring (`faithfulness`/`honesty` at `hard_gate`, `effectiveness`/`craft` at `pass_threshold`) is preserved as-is; `check_score_streak` counts full `ITERATE` outcomes, not per-criterion failures.
- Use `.score_replan_count` (not `.replan_count`) to avoid counter interference if a future `check_replan_budget` state is added.
- All intermediate state files (`.score_fail_streak`, `.score_replan_count`) go under `${captured.run_dir.output}/`.

## Scope Boundaries

- `resolve_data`, `validate`, `repair`, `plan`, and `capture` interaction logic are not touched
- Per-criterion hard-gate scoring thresholds (`faithfulness`/`honesty` at `hard_gate`, `effectiveness`/`craft` at `pass_threshold`) are preserved as-is
- No architecture or state-graph shape changes — all four changes are additive insertions
- Items 3 and 5 from the rlhf-animated-svg pattern set are not ported in this issue

## Acceptance Criteria

- [ ] `restore_best` shell state exists; `done` is only reachable through it
- [ ] `record` detects regression and copies `best.html` → `index.html` before re-entering `generate`
- [ ] `check_score_streak` + `_score_streak_route` + `concept_reset` states exist; `record` `on_no` routes to `check_score_streak`
- [ ] `concept_reset` forces a grammar escalation or mark/encoding pivot distinct from the current approach
- [ ] `context` block has `explore_cutoff`, `exploit_cutoff`, `score_fail_streak_max`, `replan_escalation_threshold`
- [ ] `generate` prompt has phase-aware blocks (explore/exploit/converge)
- [ ] `score` prompt has phase-aware instructions
- [ ] `verify_render` state exists between `validate` on_yes and `capture`
- [ ] `ll-loop validate vega-viz` passes with no new MR violations
- [ ] Loop runs to completion on a sample description without regression

## Impact

- **Priority**: P3 — medium priority; vega-viz is functional without these patterns, but they eliminate a known class of degrading-run failures already solved in rlhf-animated-svg
- **Effort**: Medium — four targeted YAML state additions to one file; no Python changes required
- **Risk**: Low — all changes are additive; existing states (`resolve_data`, `validate`, `repair`, `capture`) are untouched; `ll-loop validate` provides structural verification
- **Breaking Change**: No

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/vega-viz.yaml` — primary target; all four harness-pattern additions

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

No static callers. `vega-viz.yaml` is discovered generically at runtime via `get_builtin_loops_dir()` in `scripts/little_loops/cli/loop/_helpers.py`; `resolve_loop_path()`, `run.py`, `info.py`, and `config_cmds.py` all load it by stem without hardcoded references. No Python code needs changing.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py` — only coverage today is the manifest assertion at line 150 (`"vega-viz"` in `test_expected_builtin_loop_files`). A new `TestVegaVizHarnessPatterns` class is required covering all four ported patterns (27 method stubs). Templates:
  - `restore_best` → adapt `TestRefineToReadyIssueSubLoop` lines 1091–1200 (subprocess `tmp_path` fixture, `RESTORED_BEST_AT_TERMINATION` / `NO_BEST_CHECKPOINT` token asserts)
  - `verify_render` routing + shell → adapt `TestRlhfSvgGenerateSubLoop` lines 6413–6416 + inline subprocess pattern
  - `check_score_streak` / `_score_streak_route` / `concept_reset` → adapt `TestRlhfAnimatedSvgParentOrchestration` line 6609 presence test + subprocess streak-counter tests
  - Phase-var context declarations → adapt `TestRlhfSvgGenerateSubLoop` lines 6443–6451
  - Routing regression guards (currently unguarded): `record.on_no → check_score_streak`, `record.on_yes → restore_best`, `validate.on_yes → verify_render`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/LOOPS_GUIDE.md` — vega-viz section (~line 2034) needs:
  1. Context-variables table (lines 2063–2071): add `explore_cutoff`, `exploit_cutoff`, `score_fail_streak_max`, `replan_escalation_threshold`
  2. FSM flow ASCII diagram (~line 2082): update three stale routing edges — `validate → verify_render` (was `capture`), `record → check_score_streak` (was `generate` on `on_no`), `done ← restore_best` (new terminal predecessor)
  3. State inventory / notes block (~line 2103): document the four new states (`restore_best`, `check_score_streak`, `_score_streak_route`, `concept_reset`, `verify_render`)

## Implementation Steps

_Base scope is in the [Scope](#scope) section above. The steps below are the wiring touchpoints identified by `/ll:wire-issue`._

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints must be included in the implementation alongside the primary YAML edits:_

1. Add `TestVegaVizHarnessPatterns` to `scripts/tests/test_builtin_loops.py` — cover all four harness patterns (restore_best shell execution, check_score_streak streak counter, verify_render routing and shell, phase-var context declarations, and three routing-change regression guards); run `python -m pytest scripts/tests/test_builtin_loops.py -k TestVegaVizHarness` to confirm
2. Update `docs/guides/LOOPS_GUIDE.md` vega-viz section — add four context vars to the table, update the FSM flow diagram for three routing changes, document the five new states

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/rlhf-animated-svg.yaml` | Source of all four patterns; reference implementation |
| `scripts/little_loops/loops/vega-viz.yaml` | Target loop |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Loop design rationale |

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Test coverage for the new vega-viz states is limited to the manifest assertion at line 150 — a `TestVegaVizHarnessPatterns` class must be authored as a **co-deliverable** alongside the YAML edits (templates at `test_builtin_loops.py` lines 846–1163, 6413–6451)

## Session Log
- `/ll:wire-issue` - 2026-06-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c4adbd7-711a-4819-b554-88a6850d98cc.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/692b45ba-2ea8-44a0-b8f2-25922c8cfa15.jsonl`
- `/ll:format-issue` - 2026-06-09T16:09:16 - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:capture-issue` - 2026-06-09T16:04:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
