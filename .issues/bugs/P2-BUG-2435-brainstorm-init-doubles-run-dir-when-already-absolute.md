---
id: BUG-2435
priority: P2
type: BUG
status: open
discovered_date: 2026-07-02
discovered_by: debug-loop-run
source_loop: brainstorm
source_state: init
confidence_score: 95
outcome_confidence: 90
decision_needed: false
---

# BUG-2435: brainstorm `init` doubles run_dir path when `${context.run_dir}` is already absolute

## Summary

The `init` action in `scripts/little_loops/loops/brainstorm.yaml` builds the captured
`run_dir` value with `echo "$(pwd)/$DIR"`, which assumes `${context.run_dir}` is
a *relative* path. When the runner injects an *absolute* path (as observed in
this debug pass), the captured value becomes a doubled absolute path of the
form `/abs/A//abs/A/.loops/runs/<id>/`. Every downstream state that interpolates
`${captured.run_dir.output}/<filename>` resolves to a nonexistent filesystem path,
so shell states fail silently and prompt-state LLMs receive malformed input. The
`diverge` phase is skipped entirely and the loop terminates "successfully" with
zero ideas — the canonical "double-diamond" design never engages.

## Steps to Reproduce

1. Invoke the loop on a project with an absolute working directory, e.g.
   `cd /Users/brennon/AIProjects/brenentech/little-loops && ll-loop run brainstorm "<brief>"`.
2. Ensure the runner injects `${context.run_dir}` as an absolute path (observed in
   run `2026-07-02T012115`; many runner modes do this for absolute `cwd`).
3. Observe the `init` action's `captured.run_dir.output`:
   `/Users/brennon/AIProjects/brenentech/little-loops//Users/brennon/AIProjects/brenentech/little-loops/.loops/runs/brainstorm-20260701T202115/`
   (doubled absolute path).
4. `pop_lens` runs with that doubled path, finds no `lenses.txt`, and exits 1.
   The evaluator (`exit_code: 1` → `verdict: no`) routes `pop_lens → cluster`.
5. `cluster`, `rank`, and `converge` each read `ideas.jsonl`, find it empty,
   and route forward honestly.
6. Loop terminates `done`, `terminated_by: terminal`, `iterations: 7`, with
   `ideas.jsonl` empty and `brainstorm.md` documenting the empty state —
   a silent failure.

## Current Behavior

The `init` action in `scripts/little_loops/loops/brainstorm.yaml` unconditionally
prepends the current working directory to `${context.run_dir}`:

```bash
echo "$(pwd)/$DIR"
```

When the runner injects an absolute path, the captured value becomes a doubled
absolute path of the form `/abs/A//abs/A/.loops/runs/<id>/`. Every downstream
state that interpolates `${captured.run_dir.output}` then resolves to a
nonexistent filesystem path:

- `pop_lens` exits 1 (file missing at the doubled path), which the evaluator
  reads as "queue exhausted" and routes forward to `cluster`.
- The `diverge` phase is never entered.
- The loop terminates "successfully" (`done`, `terminated_by: terminal`,
  `iterations: 7`) with `ideas.jsonl` empty and `brainstorm.md` documenting
  the empty state.

Verbatim action bodies and observed output are preserved in the
**History Excerpt** section below for evidence.

## Loop Context

- **Loop**: `brainstorm` (built-in, category=planning)
- **Run**: `2026-07-02T012115`
- **Final state**: `done` (terminated_by=`terminal`, iterations=7)
- **Observed path**: `init → frame → pop_lens → cluster → rank → converge → route_sink → done`
  (the `diverge` state was never entered)

## Integration Map

### Files to Modify (primary bug site + sibling audit)

- `scripts/little_loops/loops/brainstorm.yaml` — lines 32–45 (`init` state action body); the only behavioral fix needed for this BUG. Lines 73–86 (`pop_lens`) for the optional defense-in-depth.
- `scripts/little_loops/loops/rn-plan.yaml` — line 32 (`init`); identical recipe; canonical reference per FEAT-2248.
- `scripts/little_loops/loops/rn-refine.yaml` — line 78 (`init`); identical recipe.
- `scripts/little_loops/loops/rn-plan-apo.yaml` — line 51 (`init`); **note**: uses `$PARENT_DIR` instead of `$DIR` (slight variant — same fix applies).
- `scripts/little_loops/loops/deep-research.yaml` — line 36 (`init`).
- `scripts/little_loops/loops/hitl-md.yaml` — line 58 (`init`).
- `scripts/little_loops/loops/hitl-compare.yaml` — line 35 (`init`).
- `scripts/little_loops/loops/html-anything.yaml` — line 37 (`init`).
- `scripts/little_loops/loops/canvas-sketch-generator.yaml` — line 58 (`init`).
- `scripts/little_loops/loops/vega-viz.yaml` — line 65 (`init`).
- `scripts/little_loops/loops/pixi-data-viz.yaml` — line 44 (`init`).
- `scripts/little_loops/loops/openscad-model-generator.yaml` — line 45 (`init`).
- `scripts/little_loops/loops/svg-image-generator.yaml` — line 32 (`init`).
- `scripts/little_loops/loops/svg-textgrad.yaml` — line 38 (`init`).
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — line 45 (`init`).
- `scripts/little_loops/loops/cua-agent-desktop.yaml` — line 60 (`init`).
- `scripts/little_loops/loops/interactive-component-generator.yaml` — line 50 (`init`).
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml` — line 51 (`init`).
- `scripts/little_loops/loops/generative-art.yaml` — line 42 (`init`).
- `scripts/little_loops/loops/adversarial-redesign.yaml` — line 36 (`init`).
- `scripts/little_loops/loops/lib/task-templates/data-lib-task.yaml.tmpl` — line 29 (`init` template).
- `scripts/little_loops/loops/lib/task-templates/stateful-service-task.yaml.tmpl` — line 29 (`init` template).
- `scripts/little_loops/loops/lib/task-templates/desktop-gui-task.yaml.tmpl` — line 29 (`init` template).

### Downstream Consumers of `${captured.run_dir.output}` (in `brainstorm.yaml`)

- `frame` (line 59) — LLM prompt interpolates the path into a `to ${captured.run_dir.output}/lenses.txt` instruction.
- `pop_lens` (lines 73–86) — bash: `QUEUE="${captured.run_dir.output}/lenses.txt"`. Default `exit_code` evaluator → `exit_code: 1` (empty queue) → `on_no: cluster`. **No `on_error:` route.**
- `dedup_novelty` (lines 143, 151–152, 166) — Python heredoc reads/writes `ideas.jsonl`; missing-file `FileNotFoundError` is silently swallowed by `try/except`.
- `saturation_gate` (line 195) — `cat "${captured.run_dir.output}/saturation.txt" 2>/dev/null || echo 0` masks the missing-file error with a fallback.
- `cluster` (lines 204–220) — LLM prompt; writes `clusters.md`.
- `rank` (lines 223–247) — LLM prompt; writes `ranked.md`.
- `converge` (lines 250–285) — LLM prompt; writes `brainstorm.md` + `winners.md`.
- `sink_file` (lines 297–310) — bash: `cp` from `${captured.run_dir.output}/brainstorm.md`; non-zero exit → `on_no: done`.

### FSM Executor (capture & interpolation mechanism)

- `scripts/little_loops/fsm/executor.py` — `_execute_action_with_capture()` line 1244 interpolates `${context.run_dir}` before bash invocation; lines 1310–1316 store stdout (with trailing `\n\r` stripped) under `self.captured[state.capture]["output"]`.
- `scripts/little_loops/fsm/interpolation.py` — `InterpolationContext._get_nested()` lines 112–134 resolves `captured.run_dir.output` to a plain string with no `realpath` canonicalization.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` line 166 wraps the action in `bash -c`.

### Runner Injection (the absolute-path source)

- `scripts/little_loops/cli/loop/run.py` — line 99 (`loops_dir = loops_dir.resolve()`); line 170 (`fsm.context["run_dir"] = str(loops_dir / "runs" / ...) + "/"`). The injected value is **always absolute** in current runner modes.
- `scripts/little_loops/cli/loop/lifecycle.py` — line 494 (resume); same absolute-path pattern.
- `scripts/little_loops/cli/loop/testing.py` — line 216 (test); same absolute-path pattern.

### Similar Patterns (the inverse case — already fixed)

- `scripts/little_loops/loops/svg-textgrad.yaml:33` and `scripts/little_loops/loops/svg-image-generator.yaml:33` — prior fix at `P2-BUG-1102-evaluate-playwright-failed-9x-exit-code-1-in-svg-textgrad-loop.md` flipped `echo "$DIR"` to `echo "$(pwd)/$DIR"` (relative-path case). Same recipe, opposite failure mode.
- `scripts/little_loops/loops/lib/common.yaml` — `snapshot_artifact` (lines 183–209), `subloop_rate_limit_diagnostic` (lines 326–348), `loop_failure_diagnose` (lines 254–280). All **consume** `run_dir` (don't capture it) — no existing shared helper for `run_dir` capture/normalization.

### Tests (existing scaffolding)

- `scripts/tests/test_brainstorm.py` — `TestBrainstormShellStates.test_init_shell_creates_artifacts` (line 477) and `test_init_is_shell_with_capture` (line 146), `test_init_action_uses_absolute_path` (line 152) cover the structural shape but **do not assert** on the doubled-path case.
- `scripts/tests/test_rn_plan.py` — `test_init_creates_run_directory` (line 137) + `test_init_outputs_absolute_path` (line ~158) follow the same shape; the latter only asserts `path.startswith("/")` (which a doubled path also satisfies).
- `scripts/tests/test_deep_research.py` (lines 130–161) and `scripts/tests/test_deep_research_arxiv.py` (lines 157–188) — same shape, same gap.
- `scripts/tests/test_fsm_validation.py` line 3210–3214 — `test_mr9_does_not_fire_for_correct_single_dollar` already validates the `echo "$(pwd)/$DIR` form against MR-9 false-positives (don't break this).
- `scripts/tests/test_builtin_loops.py` — has per-loop structural assertions including `assert "$(pwd)" in action` (per BUG-1102 wiring pattern); needs a sibling assertion for the absolute-path guard once the fix lands.

### Tests (sibling-loop files newly identified by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_rn_refine.py` — `TestInitPlumbing` class at line 135 wraps `_init_action()` via `_render(..., context={..., "run_dir": run_dir})` and exercises the rendered init body; needs an absolute-path guard assertion analogous to `test_init_action_uses_absolute_path`.
- `scripts/tests/test_rn_plan_apo.py` — `TestRunPlannerState` class at line 101 has no assertion for `$(pwd)/$PARENT_DIR` or absolute-path shape (rn-plan-apo uses `$PARENT_DIR` not `$DIR`); add a `$PARENT_DIR`-aware guard assertion.
- `scripts/tests/test_rn_implement.py` — lines 254, 308, 844, 910, 1019 assert `${captured.run_dir.output}` in action bodies for the `rn-implement` loop. Note: `rn-implement.yaml:75,128` use the inverse BUG-1102 recipe (`echo "$RUN_DIR"`, *not* `echo "$(pwd)/$DIR"`), so the BUG-2435 fix does not apply here — but `test_rn_implement.py` is the closest pattern for a sibling-loop test extension if a future cross-loop audit decides to unify the recipe.
- `scripts/tests/test_builtin_loops.py` — `TestPixiDataVizLoop` (line 4373), `TestInteractiveComponentGeneratorLoop` (line 8570), `TestRlhfAnimatedSvgParentOrchestration` (line 7470), `TestCuaAgentDesktopLoop` (line 700) **have no `test_init_*` assertions at all** — needs the per-class structural assertion added alongside the 6 existing `test_init_action_uses_absolute_path` classes (lines 4127, 4524, 4766, 5023, 5179, 5353).
- `scripts/tests/test_builtin_loops.py` — `pop_lens` defense-in-depth (Step 4) has zero action-body coverage. `test_pop_lens_routes_to_diverge_on_yes` (line 161) only checks `on_yes`/`on_no` from YAML. Add a `TestPopLensEmptyQueue` class that exercises the missing-file-at-iteration-0 path.
- No dedicated test file exists for: `canvas-sketch-generator`, `vega-viz`, `cli-anything-bootstrap`, `generative-art`, or the 3 task templates under `lib/task-templates/`. The sibling-loop audit in Step 3 should add a per-loop `test_init_action_uses_absolute_path` to either `test_builtin_loops.py` (preferred — same file as the 6 existing siblings) or a new file per loop.
- The `_bash(script, cwd)` helper is duplicated across 9 test files (test_brainstorm.py:18, test_rn_plan.py:18, test_deep_research.py:17, test_deep_research_arxiv.py:24, test_rn_refine.py:25, test_general_task_loop.py:759, test_harness_optimize.py:16, test_loops_sft_corpus.py:8, test_loops_recursive_refine.py:14). Out of scope for BUG-2435 (orthogonal refactor), but flagging because the new sibling-loop tests would multiply the duplication.

### Documentation

- `thoughts/plans/pixi-js-2-loops-plan.md` — lines 47, 204 record the recipe in plan docs.
- `.issues/features/P3-FEAT-2248-brainstorm-builtin-fsm-loop.md` — line 185 (recipe); line 214 (canonical reference to `rn-plan.yaml:states.init`). **Update required** to record the absolute-path guard.
- `.issues/enhancements/P3-ENH-1726-unify-fsm-loop-run-artifacts-into-per-run-directory.md` — line 182 documents the unified FSM-loop init recipe; flag the absolute-path fragility here too.
- `.issues/features/P3-FEAT-2354-builtin-loop-generates-reusable-claude-code-workflows.md` — line 269 records the recipe in builtin-loop authoring guidance.

### Documentation (newly identified by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/generalized-fsm-loop.md` line 1058 — "Runner-injected context variables" table row for `run_dir` currently says "(.loops/runs/&lt;loop&gt;-&lt;timestamp&gt;/)" with no absolute/relative annotation. **Update recommended** to note the value is always absolute via `loops_dir.resolve()` (so implementers don't reintroduce BUG-1102's `echo "$DIR"` form thinking the runner gives a relative path).
- `docs/reference/loops.md` line 402 — parameter table entry reads `| run_dir | yes | — | Directory path for generated artifacts (absolute or runner-injected relative path) |`. This actively documents the dual-shape contract the bug exploits. **Update required** to "always absolute (since `loops_dir.resolve()` is applied at injection time)" or equivalent.
- `CHANGELOG.md` — no `## [Unreleased]` section to update. A new versioned entry under the next `[X.Y.Z]` section is needed at release time, paralleling the BUG-1102 entry at `CHANGELOG.md:1443`. Out of scope for the implementation; flagged for the release-prep pass.

### Related Issues

- `.issues/enhancements/P3-ENH-2251-harden-brainstorm-loop-resilience-and-handoff.md` (done) — explicitly deferred `init` fragility; this BUG is the deferred item.
- `.issues/enhancements/P3-ENH-2419-run-dir-propagation-with-subloop-regression-test.md` (open) — adjacent run_dir propagation concern.
- `.issues/enhancements/P3-ENH-2428-score-plateau-early-stop-for-generator-evaluator.md` — touches `context.run_dir` semantics.
- `.issues/enhancements/P3-ENH-2367-audit-loop-run-surface-captured-values-and-pid-heuristic.md` — references MR-9 PID-corruption unit-test pattern relevant to FSM shell-action escape hygiene (test_brainstorm.py coverage should not regress on this BUG).

### Configuration

- `scripts/little_loops/config.py` — `BRConfig` resolves `loops_dir` from `Path.cwd()`; the absolute-path behavior is a side effect of `Path.resolve()` rather than an explicit config. No config change required.

## History Excerpt

From `ll-loop history brainstorm 2026-07-02T012115 --json`:

`init` action body and output (verbatim):

```bash
DIR="${context.run_dir}"
mkdir -p "$DIR"
: > "$DIR/ideas.jsonl"
echo 0 > "$DIR/saturation.txt"
: > "$DIR/lenses.txt"
: > "$DIR/brainstorm.md"
echo "$(pwd)/$DIR"
```

`init` `action_complete` `output_preview`:

```
/Users/brennon/AIProjects/brenentech/little-loops//Users/brennon/AIProjects/brenentech/little-loops/.loops/runs/brainstorm-20260701T202115/
```

`pop_lens` action body:

```bash
QUEUE="${captured.run_dir.output}/lenses.txt"
ITEM=$(head -1 "$QUEUE" 2>/dev/null)
if [ -z "$ITEM" ]; then
  exit 1
fi
tail -n +2 "$QUEUE" > "$QUEUE.tmp" && mv "$QUEUE.tmp" "$QUEUE"
echo "$ITEM"
```

`pop_lens` `action_complete` (`exit_code: 1`, `output_preview: null`),
`evaluate` (`type: exit_code`, `verdict: no`), `route pop_lens → cluster`.

`cluster`, `rank`, `converge` each ran as LLM prompt states, each honestly
reported that `ideas.jsonl` was 0 bytes, and routed forward.

`loop_complete`: `final_state: done`, `iterations: 7`, `terminated_by: terminal`.

## Expected Behavior

Either:
- **`init` should always produce a single, valid absolute path** in
  `captured.run_dir.output`, regardless of whether the runner injected
  `${context.run_dir}` as relative or absolute. The fix is one of:
  - `echo "$(pwd)/$DIR"` only when `$DIR` is relative (test with
    `[[ "$DIR" = /* ]]`); `echo "$DIR"` otherwise.
  - Use `realpath "$DIR"` to canonicalize, e.g. `echo "$(realpath "$DIR")/"`.
  - Replace `echo "$(pwd)/$DIR"` with `echo "${DIR:-$PWD}"` or similar
    defensive construction.

**AND**, as a defense-in-depth follow-on:
- `pop_lens` should distinguish "queue exhausted after popping ≥1 item" from
  "queue empty from the start (lenses.txt missing/unreadable)" — currently both
  produce exit 1 → `cluster`, so a malformed upstream path silently bypasses
  the entire diverge phase. Consider routing "first pop fails because file
  missing" to `failed` (terminal) or `frame` (retry), or at minimum logging a
  warning that lenses.txt was empty at iteration_count=0.

## Motivation

The brainstorm loop is a composite quality 28/30 built-in designed around a
double-diamond pipeline. The `init` → `frame` → `diverge` → `cluster` →
`rank` → `converge` → `route_sink` → `done` sequence is what makes it useful;
any path-injection fragility that silently bypasses `diverge` turns the loop
into a no-op that still reports "success."

The current run produced:
- `ideas.jsonl`: 0 bytes
- `clusters.md`: explicit "no content" notice
- `ranked.md`: explicit "no content" notice
- `brainstorm.md`: documented empty state
- `winners.md`: `[]`

A user invoking `ll-loop run brainstorm "<brief>"` would see the loop complete
normally with no error and an empty brainstorm.md — a silent failure that is
much harder to debug than a hard error.

The bug is also latent: any other built-in loop that follows the
`echo "$(pwd)/$DIR"` pattern (the recipe FEAT-2248 documents as canonical, used
by `rn-plan.yaml` and likely others) is susceptible to the same failure mode
when the runner injects an absolute path.

## Root Cause

- **File**: `scripts/little_loops/loops/brainstorm.yaml`
- **Anchor**: the `init` state, inside its `action` body (the bash shell state
  that captures `${context.run_dir}`)
- **Cause**: The captured value is computed as `echo "$(pwd)/$DIR"`, which
  assumes `${context.run_dir}` is a relative path. When the runner supplies an
  absolute value, `$(pwd)/$DIR` produces a doubled absolute path
  (`/abs/A//abs/A/...`). The action has no `[[ "$DIR" = /* ]]` guard to
  short-circuit the absolute case.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Runner always injects absolute paths.** `scripts/little_loops/cli/loop/run.py:170` sets `fsm.context["run_dir"] = str(loops_dir / "runs" / ...) + "/"` where `loops_dir = loops_dir.resolve()` (line 99). The same absolute-path pattern is used in `cli/loop/lifecycle.py:494` (resume) and `cli/loop/testing.py:216` (test). **The relative-path branch in `init` is effectively dead code in current usage** — the bug fires on the canonical path, not a corner case.
- **Interpolation happens before bash.** `scripts/little_loops/fsm/executor.py:1244` (`_execute_action_with_capture()`) calls `interpolate(action_template, ctx)` so by the time bash sees the script, `${context.run_dir}` has already been substituted. The `DIR=...` rebinding inside bash is a redundant mask that hides the real shape of the injected value.
- **Capture mechanism strips nothing but newlines.** `executor.py:1310–1316` stores `result.output.rstrip("\n\r")` under `self.captured[state.capture]["output"]`. No `realpath`/canonicalization step exists downstream (`scripts/little_loops/fsm/interpolation.py:112–134` `InterpolationContext._get_nested()` returns a plain string).
- **No shared helper for `run_dir` capture.** `scripts/little_loops/loops/lib/common.yaml` has `snapshot_artifact`, `subloop_rate_limit_diagnostic`, and `loop_failure_diagnose` fragments that *consume* `run_dir` but never *capture/normalize* it. The `echo "$(pwd)/$DIR"` line is hand-rolled in every loop.
- **`pop_lens` has no `on_error:` route.** Combined with the doubled-path bug, the `exit 1` from `pop_lens` (default `exit_code` evaluator → `verdict: no` → `on_no: cluster`) silently bypasses `diverge` without any error-logging path. The FSM executor's default error handler does not engage for non-zero exit codes.
- **Inverse precedent exists** at `.issues/bugs/P2-BUG-1102-...md` — fixed the relative-path case (`echo "$DIR"` → `echo "$(pwd)/$DIR"`) and propagated the same change to `svg-image-generator.yaml` plus added structural `assert "$(pwd)" in action` tests in `test_builtin_loops.py`. The BUG-2435 fix should follow the same propagation pattern (fix + sibling audit + `test_builtin_loops.py` wiring).

## Proposed Solution

Conditionally handle absolute vs. relative `${context.run_dir}` inside the
`init` action:

```bash
if [ "${DIR:0:1}" = "/" ]; then
  echo "$DIR"
else
  echo "$(pwd)/$DIR"
fi
```

This preserves the documented relative-path behavior and adds a guard for the
absolute-path case. A `realpath`-based variant (`echo "$(realpath "$DIR")"`)
works but requires coreutils on macOS, so the conditional is preferred.

For the optional defense-in-depth (`pop_lens` empty-queue handling) and the
sibling-loop audit, see **Implementation Steps** and the `pop_lens` action
anatomy described in **History Excerpt**.

### Codebase Research Findings (option inventory)

_Added by `/ll:refine-issue` — three implementation options, ordered by preferability:_

**Option A — Conditional guard (preferred).** Add a `[ "${DIR:0:1}" = "/" ]`
test and skip `$(pwd)` when `DIR` is already absolute. Pure bash builtins,
no external dependency, preserves the relative-path case verbatim. Tradeoff:
handles only the two known cases (absolute vs. relative); a malformed value
like `~user/.loops/runs/foo` would still misbehave — but the runner never
produces such values, so this is not a practical concern.

> **Selected:** Option A — Conditional guard — Pure bash guard with no external dependency; aligns with the 4 prior `case "$VAR" in /*) … esac` precedents at consumption sites (`interactive-component-generator.yaml:484-489`, `svg-image-generator.yaml:141-146`, `html-website-generator.yaml:171-176`, `oracles/generator-evaluator.yaml:68-75`), and extends the absolute-or-relative dispatch from the consumption site back to the capture site.

**Option B — `realpath` canonicalize.** Replace `echo "$(pwd)/$DIR"` with
`echo "$(realpath "$DIR")"`. Tradeoff: requires GNU coreutils on macOS
(no system `realpath` historically; macOS Ventura+ ships one but with
slightly different semantics around symlinks). Would also normalize any
path quirks (trailing slashes, `.`/`..` segments), which is a slight
behavioral change from the current recipe. Preferred if portability is
not a concern.

**Option C — Default substitution (`${DIR:-$PWD}`).** Replace with
`echo "${DIR:-$PWD}"`. Tradeoff: minimal one-liner but only works when
`$DIR` is empty — does NOT fix the doubling case when `$DIR` is non-empty
but absolute. Misleading as a fix for BUG-2435 specifically; would only
catch the (now-defunct) empty-`run_dir` injection.

**Recommendation:** Option A. It is the smallest behavioral change, has no
external dependency, and matches the symmetry of BUG-1102's fix (which was
also a 1-line change to the same recipe).

After the fix lands, update the canonical-recipe doc
(`.issues/features/P3-FEAT-2248-brainstorm-builtin-fsm-loop.md:185,214`) to
record the absolute-path guard.

### Defense-in-depth: `pop_lens` empty-queue handling (optional)

For the separate but related issue: `pop_lens`'s `exit 1` on empty
`lenses.txt` is currently indistinguishable from a malformed upstream
path. Research confirms `pop_lens` has **no `on_error:` route** declared
and the default `exit_code` evaluator reads `exit 1` as `verdict: no` →
`on_no: cluster`. This means any silent upstream failure (path doubling,
permission denied, etc.) routes forward as a "queue exhausted" success.
A defensive fix is to distinguish "first pop fails because file missing"
(`iteration_count == 0` and `[ ! -f "$QUEUE" ]`) from "queue exhausted
after ≥1 pop" and route the former to `failed` (terminal) or `frame`
(retry). This is **optional** and separable from the primary fix.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-02.

**Selected**: Option A — Conditional guard

**Reasoning**: Option A targets the exact bug surface (capture site producing a single valid absolute path regardless of runner injection shape) with no external dependency, preserves the relative-path branch verbatim, and aligns with the codebase's established absolute-or-relative dispatch idiom (`case "$VAR" in /*) … esac`) already used at four consumption sites — `interactive-component-generator.yaml:484-489`, `svg-image-generator.yaml:141-146`, `html-website-generator.yaml:171-176`, and `oracles/generator-evaluator.yaml:68-75`. The implementer should match the existing `case` idiom during the fix; the `[ "${DIR:0:1}" = "/" ]` form proposed in the issue is semantically equivalent but introduces a novel syntax variant. Option B (`realpath`) has one cross-purpose precedent (`rn-refine.yaml:63`) but no portability guard anywhere; Option C (`${DIR:-$PWD}`) has zero precedent and breaks the relative-path branch — bash's `${VAR:-default}` distinguishes empty vs. non-empty, not absolute vs. relative.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Conditional guard | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| B — `realpath` canonicalize | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |
| C — `${DIR:-$PWD}` default | 1/3 | 3/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- **Option A**: 4 prior consumption-site precedents via `case "$VAR" in /*) … esac`; existing test helpers (`_bash` at `scripts/tests/test_brainstorm.py:18-19`, `test_init_outputs_absolute_path` at `:152-154`, MR-9 non-regression at `scripts/tests/test_fsm_validation.py:3210-3214`) reuse as-is. Reuse score: 1/3 — five-loops-worth of precedent but the exact `[ "${VAR:0:1}" = "/" ]` substring idiom is novel in this corpus.
- **Option B**: One cross-purpose shell precedent at `rn-refine.yaml:63` (file-path write-back, not `run_dir` capture). The 22 other `init` sites do not use `realpath`. No `command -v realpath` portability guard anywhere (cf. `flock` at `hooks/scripts/lib/common.sh:13`, `date` at `:99-117`, `stat` at `:143-160`). Reuse score: 1/3.
- **Option C**: Zero precedent for `${DIR:-$PWD}` in FSM loop YAML action bodies; bash `${VAR:-default}` semantics distinguish empty vs. non-empty, not absolute vs. relative — fixes the absolute-doubling case by accident of runner behavior (which always injects absolute paths per `cli/loop/run.py:170`), breaks the relative-path branch (the FEAT-2248 documented contract). Reuse score: 0/3.

## Implementation Steps

1. Patch the `init` action in `scripts/little_loops/loops/brainstorm.yaml` so
   a relative `${context.run_dir}` keeps the existing `echo "$(pwd)/$DIR"` and
   an absolute one is returned unchanged.
2. Add a regression test under `scripts/tests/test_brainstorm.py` covering
   both the absolute and relative `${context.run_dir}` injection cases for
   `init`.
3. Audit sibling loops in `scripts/little_loops/loops/*.yaml` for the same
   `echo "$(pwd)/$DIR"` recipe (FEAT-2248 documents this as canonical; suspect
   `rn-plan.yaml` and any other copy); apply the same guard where found.
4. (Optional, defense-in-depth) Update `pop_lens` so an empty `lenses.txt` at
   `iteration_count=0` is treated as a fatal upstream error (route to
   `failed` or `frame`), not "queue exhausted → cluster."
5. Update FEAT-2248 (the doc that recorded the recipe as canonical) to record
   the absolute-path guard.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. Each is wired to an agent finding._

6. **Tests — extend `test_rn_refine.py`** (caller-tracer finding): `TestInitPlumbing` at line 135 renders `rn-refine.yaml:78` `init` via `_render(...)`; add a `test_init_action_uses_absolute_path` analog and a new `test_init_handles_absolute_context_run_dir` regression test.
7. **Tests — extend `test_rn_plan_apo.py`** (caller-tracer finding): `TestRunPlannerState` at line 101 has no `$(pwd)/$PARENT_DIR` or absolute-path assertion; add one. The `$PARENT_DIR` variant requires the guard check `"${PARENT_DIR:0:1}"` (Step 3 special case).
8. **Tests — add 4 missing per-loop structural assertions in `test_builtin_loops.py`** (test-gap-finder finding): `TestPixiDataVizLoop` (line 4373), `TestInteractiveComponentGeneratorLoop` (line 8570), `TestRlhfAnimatedSvgParentOrchestration` (line 7470), `TestCuaAgentDesktopLoop` (line 700) currently have no `test_init_*` assertions. Add `test_init_action_uses_absolute_path` to each, paralleling the 6 existing siblings.
9. **Tests — add `TestPopLensEmptyQueue` class in `test_brainstorm.py`** (test-gap-finder finding): the optional Step 4 defense-in-depth has zero action-body coverage. Add a class that exercises the missing-file-at-iteration-0 path and verifies the new `on_error: failed` (or `on_error: frame`) route engages.
10. **Tests — add new per-loop `test_init_action_uses_absolute_path` for loops with no dedicated test file** (test-gap-finder finding): `canvas-sketch-generator`, `vega-viz`, `cli-anything-bootstrap`, `generative-art`, plus the 3 task templates under `lib/task-templates/`. Either add to `test_builtin_loops.py` (preferred) or create one new test file per loop.
11. **Documentation — update `docs/generalized-fsm-loop.md` line 1058** (side-effect-tracer finding): the "Runner-injected context variables" table row for `run_dir` must annotate "always absolute via `loops_dir.resolve()`" to prevent future implementers from reintroducing BUG-1102's `echo "$DIR"` form.
12. **Documentation — update `docs/reference/loops.md` line 402** (side-effect-tracer finding): the parameter table currently says "absolute or runner-injected relative path" — actively documents the buggy contract. Update to "always absolute."
13. **Tests — verify MR-9 non-regression after the fix** (side-effect-tracer finding): `test_fsm_validation.py:3210–3214` validates `echo "$(pwd)/$DIR"` against MR-9 false-positives via an inline FSM string, so it's independent of any loop YAML change; the new conditional form does not interact with MR-9 detection. Confirm with `python -m pytest scripts/tests/test_fsm_validation.py -v` after the change.
14. **Release notes — out-of-scope flag** (side-effect-tracer finding): add a `CHANGELOG.md` entry under the next `[X.Y.Z]` section at release time, paralleling the BUG-1102 entry at line 1443.

### Codebase Research Findings (concrete references)

_Added by `/ll:refine-issue` — file paths and test patterns from codebase scan:_

**Step 1 — primary fix.** Edit `scripts/little_loops/loops/brainstorm.yaml:43`.
Replace the `echo "$(pwd)/$DIR"` line with the conditional form:

```bash
if [ "${DIR:0:1}" = "/" ]; then
  echo "$DIR"
else
  echo "$(pwd)/$DIR"
fi
```

**Step 2 — regression test.** Add to `scripts/tests/test_brainstorm.py`
following the existing `_bash(script, tmp_path)` helper pattern (lines 17–19).
Two new test methods under `TestBrainstormShellStates`:

- `test_init_handles_absolute_context_run_dir` — invoke `_bash(...)` with
  `DIR="/abs/path/.loops/runs/brainstorm-test"` (absolute injection); assert
  captured output is the same absolute path (no doubling), i.e. the result
  equals `tmp_path`-resolved absolute path verbatim.
- `test_init_handles_relative_context_run_dir` — invoke `_bash(...)` with
  `DIR=".loops/runs/brainstorm-test"` (relative injection); assert captured
  output equals `tmp_path / ".loops/runs/brainstorm-test"`.

The existing `test_init_outputs_absolute_path` (asserting `startswith("/")`)
**does not catch** the doubling case — both `"/abs/path/.loops/runs/foo"`
and `"/abs/path//abs/path/.loops/runs/foo"` start with `/`. The new tests
must explicitly assert equality with the expected (single) absolute path.

**Step 3 — sibling audit.** The recipe appears in 19 built-in loops + 3 task
templates (all listed in **Integration Map** above). For each:
- Apply the same conditional guard.
- Update `scripts/tests/test_builtin_loops.py` with a structural assertion
  per loop following the BUG-1102 wiring pattern (`assert "$(pwd)" in action`
  is preserved; add an assertion for the absolute-path guard, e.g.
  `assert 'if [ "${DIR:0:1}" = "/" ]' in action`).
- Special case: `scripts/little_loops/loops/rn-plan-apo.yaml:51` uses
  `$PARENT_DIR` — apply the equivalent guard checking `"${PARENT_DIR:0:1}"`.

**Step 4 — defense-in-depth (optional).** Edit
`scripts/little_loops/loops/brainstorm.yaml:73–86` to distinguish "queue
exhausted after ≥1 pop" from "file missing from start." Concretely:
replace `exit 1` (line 81) with a `[ ! -f "$QUEUE" ] && exit 1` short-circuit
that only fires when the file is missing entirely. Add a new error-handler
route `on_error: failed` (or `on_error: frame`) so the FSM executor's
default error handler engages for upstream path/permission failures.
Note: this is a separate concern from the primary fix and can ship
independently.

**Step 5 — doc updates.** Update three docs to record the absolute-path guard:
- `.issues/features/P3-FEAT-2248-brainstorm-builtin-fsm-loop.md:185,214`
  (canonical recipe).
- `.issues/enhancements/P3-ENH-1726-unify-fsm-loop-run-artifacts-into-per-run-directory.md:182`
  (unified FSM-loop init recipe).
- `thoughts/plans/pixi-js-2-loops-plan.md:47,204` (plan-doc recipe).

**Verification commands** (single command per concern):

```bash
# Primary fix + sibling structural assertions
python -m pytest scripts/tests/test_brainstorm.py::TestBrainstormShellStates -v
python -m pytest scripts/tests/test_builtin_loops.py -v

# Full test suite (catches regressions in shared FSM machinery)
python -m pytest scripts/tests/ -v --tb=short

# Lint / format / type-check
ruff check scripts/
ruff format scripts/
python -m mypy scripts/little_loops/

# End-to-end smoke (relative + absolute injection)
cd /tmp && ll-loop run brainstorm "smoke test brief" --yes
ll-loop run brainstorm "smoke test brief" --yes   # run from absolute cwd
```

**MR-9 escape-validation sanity check.** Confirm the new conditional does
not trip the FSM shell-escape validator:
`scripts/tests/test_fsm_validation.py:3210–3214` already validates the
`echo "$(pwd)/$DIR"` form against MR-9 false-positives; the new
`if [ "${DIR:0:1}" = "/" ]; then` form is pure POSIX shell and should
not interact with MR-9's `$$`/`$$VAR` over-escape detection, but verify
with `python -m pytest scripts/tests/test_fsm_validation.py -v` after
the change.

## Acceptance Criteria

- [ ] `init` action's captured `run_dir` output is a single valid absolute path
      regardless of whether `${context.run_dir}` is relative or absolute.
- [ ] `ll-loop run brainstorm "test brief"` (with both relative and absolute
      `${context.run_dir}` injection) reaches the `diverge` state and produces
      `ideas.jsonl` with content.
- [ ] `scripts/tests/test_brainstorm.py` has a regression test covering both
      `init` path-injection modes.
- [ ] If step 2 (defense-in-depth) is in scope: `pop_lens` on first iteration
      with an empty/missing `lenses.txt` does not silently route to `cluster`;
      it raises an error or routes to a recovery state.
- [ ] Sibling loops using the same `init` recipe are audited and fixed.

## Distinct From

- **ENH-2251** (done) — added `on_handoff: spawn` and missing `on_error` routes
  to four states; explicitly skipped `init` (it was not considered fragile at
  the time). This BUG is the `init` fragility ENH-2251 deferred.
- **ENH-2356** (done) — fixed the saturation/novelty gate inertness by
  lowering `novelty_threshold` to 0.55. Does not address `init` path
  handling.
- **FEAT-2248** — the brainstorm built-in feature doc that records
  `echo "$(pwd)/$DIR"` as the canonical `init` pattern, asserting the
  relative-path assumption this BUG invalidates.

## Impact

- **Priority**: P2 — silent failure of a quality 28/30 built-in loop; visible to
  any user invoking `ll-loop run brainstorm`, but the failure surface is one
  component (no critical user path) and the loop terminates nominally rather
  than corrupting data.
- **Effort**: Small — primary fix is a one-line change in one action; Medium if
  the `pop_lens` defense-in-depth and the sibling-loop audit are included in
  the same pass; either way, no new abstractions required.
- **Risk**: Low — change is tightly scoped to `init`'s path capture; the
  `lenses.txt`, `ideas.jsonl`, and downstream behaviors for the relative-path
  case are unchanged.
- **Breaking Change**: No — relative-path behavior is preserved; only the
  absolute-path case is corrected.

## Labels

`bug`, `loops`, `brainstorm`, `init`, `path-handling`, `silent-failure`

## Status

**Open** | Created: 2026-07-02 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-02T02:43:02 - `ff5d5f7e-3c9f-4d50-9348-296316693ec5.jsonl`
- `/ll:wire-issue` - 2026-07-02T02:30:25 - `cb3c86ae-20cf-4f27-b380-49ec39e6074d.jsonl`
- `/ll:decide-issue` - 2026-07-02T02:10:56 - `b7d7ca48-3c72-438a-9a8c-43e1379523cf.jsonl`
- `/ll:refine-issue` - 2026-07-02T01:58:43 - `f0cfa837-0f98-4d3a-81f4-e95b8ecf0070.jsonl`
- `/ll:format-issue` - 2026-07-02T01:43:29 - `2884d673-f5fa-4baa-8dd2-e07e55218424.jsonl`

- `/ll:debug-loop-run brainstorm` — 2026-07-02T01:21–01:23 — discovered during
  analysis of run `2026-07-02T012115`.