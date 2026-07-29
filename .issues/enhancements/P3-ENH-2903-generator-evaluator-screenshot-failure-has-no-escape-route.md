---
id: ENH-2903
type: ENH
priority: P3
status: done
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
discovered_by: svg-image-generator-screenshot-hang-diagnosis
depends_on:
- BUG-2901
- BUG-2904
relates_to:
- BUG-2901
- BUG-2904
learning_tests_required:
- playwright
confidence_score: 98
outcome_confidence: 75
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 16
completed_at: '2026-07-29T04:06:22Z'
---

# ENH-2903: generator-evaluator screenshot failure has no escape route

## Summary

Every outcome of the `evaluate` state in
`scripts/little_loops/loops/oracles/generator-evaluator.yaml:82-84` routes to the
same place, so a failed screenshot cannot be distinguished from a bad artifact
and the loop keeps iterating blind.

This is the defect that **persists after** BUG-2901 and BUG-2904 are both fixed:
bounding the hang and reaping the tree still leaves the loop burning its full
step budget on un-evaluable iterations.

## Status

Open. BUG-2901 is `done` (commit `e2cb3d8e`). Still blocked on **BUG-2904 only**.

> **PREMISE CORRECTED 2026-07-29** (pre-implementation review). This issue
> previously said its design "assumes `exit_code: 124` is an observable signal
> downstream of `evaluate`" and described a timeout as reaching `on_error`.
> **It does not reach `on_error`.** The `evaluate` state inherits
> `evaluate.type: output_contains` / `pattern: "CAPTURED"` from the
> `playwright_screenshot` fragment, and `output_contains` never consults the
> exit code — only the no-`evaluate:` default path calls `evaluate_exit_code`
> (`scripts/little_loops/fsm/executor.py:1994`). A timed-out screenshot
> therefore yields verdict **`no`**, not `error`. The 124 is visible in the
> event stream but invisible to routing.
>
> This **does not invalidate the design** — detecting a missing/stale
> `screenshot.png` in `snapshot` is the right approach precisely *because*
> routing cannot discriminate. But an implementer reading the old text would
> wire an `on_error`-keyed detector that never fires. Do not do that.

## Current Behavior

```yaml
  on_yes: snapshot
  on_no: snapshot
  on_error: snapshot
```

A screenshot that fails — for any reason, including the timeout BUG-2904 will
start producing (which arrives as `on_no`, per the correction above) — advances
to `snapshot` → `score` → `check_stall` → `check_diff_stall` → `generate` and
iterates again. `snapshot` copies with `cp ... || true`, silently swallowing the
absent file, and `score` then rubric-scores an artifact whose screenshot is
missing or stale from a previous iteration.

Note `snapshot` swallows a missing **artifact** the same way:

```bash
      cp "$RUN_DIR/${context.artifact_path}" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
      cp "$RUN_DIR/screenshot.png" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
```

Same defect class, same state, same fix shape — in scope here rather than left
for a third issue.

## Expected Behavior

A persistently un-screenshottable artifact converges through the existing stall
machinery to a terminal state with an honest verdict, while a single transient
screenshot fault remains survivable.

## Impact

The loop cannot distinguish "the artifact is bad" from "we never managed to look
at the artifact." Rubric scores computed against stale screenshots are silently
wrong, and the run exhausts `max_steps` rather than terminating on a real signal.

## Proposed Solution

Keep `on_error: snapshot`, but make the downstream states able to *see* that the
screenshot is missing:

1. `snapshot` detects a missing or stale `screenshot.png` and records the miss.
   "Stale" means the file predates this iteration's artifact write — compare
   mtimes, or hash it against the previous iteration's copy in `iter-$((N-1))/`.
   Apply the same detection to the missing-artifact `cp` noted above.
2. `score` treats "no fresh screenshot this iteration" as a distinct,
   non-passing signal rather than silently scoring a stale image.
3. Consecutive screenshot misses feed `check_stall` / `check_diff_stall`, which
   already own convergence.

The miss is recorded to a counter file under `${context.run_dir}/` (MR-3:
per-run isolation, never bare `.loops/tmp/`), alongside the existing
`.iter_counter` and `.score_history`.

### Why not simply `on_error: failed`

The original diagnosis recommended changing `on_error` to `failed`. That is too
blunt:

- It discards a run whose *artifact* may be perfectly good and whose only
  failure was the screenshot step — a transient Playwright/Chromium fault fails
  the whole generation.
- It is an unvalidated behavior change across every consumer of this oracle
  (`html-website-generator`, `html-anything`, `hitl-md`,
  `p5js-sketch-generator`, `svg-image-generator`). The diagnosis explicitly
  flagged that no consumer's dependence on the current snapshot-after-error path
  was checked.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify

- `scripts/little_loops/loops/oracles/generator-evaluator.yaml`
  - `evaluate` (lines 74-85) — inherits `evaluate.type: output_contains` /
    `pattern: "CAPTURED"` from the `playwright_screenshot` fragment
    (`scripts/little_loops/loops/lib/harness.yaml:2-14`); its `on_yes`/`on_no`/
    `on_error` all route to `snapshot` today.
  - `snapshot` (lines 87-101) — the state that must gain mtime/hash staleness
    detection for `screenshot.png` and the `.screenshot_misses` counter write.
    Currently both `cp` lines swallow failure with `2>/dev/null || true`.
  - `check_stall` (lines 156-174, `fragment: score_stall_gate`) and
    `check_diff_stall` (lines 176-189, `fragment: diff_stall_gate`) — the
    existing convergence chain the `.screenshot_misses` counter should feed
    into. Neither currently reads `.iter_counter` or any screenshot-related
    file; `check_stall` uses `evaluate_score_stall()`
    (`scripts/little_loops/fsm/evaluators.py:689`, reads
    `${context.run_dir}/.score_history`), `check_diff_stall` uses
    `evaluate_diff_stall()` (`evaluators.py:594`, `git diff --stat` against a
    `.loops/tmp/ll-diff-stall-<md5>.{txt,count}` cache — evaluator-internal
    state, not a loop-authored artifact, so it is not subject to MR-3).

#### Dependent Files (variants and consumers)

- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml` and
  `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` — variant
  oracles with their own `evaluate:` overrides (the flux variant uses `from:
  generator-evaluator` inheritance, FEAT-2269 pattern); check whether either
  needs the same screenshot-miss detection or already diverges from the
  shared `snapshot`/`check_stall` shape.
- Five consumer loops wrapping the oracle (ENH-1869 pattern), listed in Scope
  Boundaries above as needing "no behavior change" verification:
  `scripts/little_loops/loops/html-website-generator.yaml`,
  `scripts/little_loops/loops/html-anything.yaml`,
  `scripts/little_loops/loops/hitl-md.yaml`,
  `scripts/little_loops/loops/p5js-sketch-generator.yaml`,
  `scripts/little_loops/loops/svg-image-generator.yaml`.

#### Similar Patterns

- **mtime staleness check (`stat -f`/`stat -c` fallback pair)**:
  `scripts/little_loops/loops/rn-build.yaml:1014-1029` compares a file's
  mtime against run-start time with `stat -f %m "$FILE" 2>/dev/null || stat -c
  %Y "$FILE" 2>/dev/null` — the reusable primitive for detecting a
  pre-existing/stale `screenshot.png`, though that state compares against run
  start rather than iteration start, so this issue's check needs its own
  reference point (e.g. compare against `.iter_counter`'s prior copy in
  `iter-$((N-1))/`).
- **Per-run counter-file-with-threshold shape**: `.phantom_complete_count` /
  `.action_fail_count` in `scripts/little_loops/loops/cua-agent-desktop.yaml:551-573,
  597-619` — read-increment-write-compare-reset idiom to model
  `.screenshot_misses` after.
- **MR-13-satisfying penultimate "abandoned" state** (the `rn-implement::report`
  shape referenced in `.claude/CLAUDE.md`): `scripts/little_loops/loops/general-task.yaml`
  — `summarize_success` (~lines 709-736, non-terminal) writes `summary.json`
  with a `VERDICT`/`"abandoned":N` key conditioned on a counter (grep count of
  `- [!]` lines), `next: check_abandoned_route`; `check_abandoned_route`
  (~lines 744-772, penultimate, non-terminal) re-reads the count back off disk
  (deliberately not via `${captured.*}`, per its own comment, to sidestep
  capture-reachability lint) via `evaluate: {type: output_numeric, operator:
  eq, target: 0}`, `on_yes: done`, `on_no: partial`. This is the exact
  precedent for the AC item "convergence path emits an `\"abandoned\"` key ...
  and downgrades the verdict."
- **MR-13 implementation** (exact regexes/logic to satisfy):
  `scripts/little_loops/fsm/validation/evaluator_rules.py`,
  `_validate_abandonment_verdict()` (lines 155-239) — checks for
  `_ABANDONED_KEY_EMIT_RE` (a literal `"abandoned":` match, line 147)
  somewhere in the loop whenever an abandonment mechanism
  (`_ABANDON_BANG_MARKER_RE`/`_ABANDON_CHECKED_ANNOTATION_RE`/
  `_ABANDON_ATTEMPT_CAP_RE`, lines 128-139) is present, and flags any
  hardcoded `"verdict":"success"` (`_HARDCODE_VERDICT_SUCCESS_RE`, lines
  151-153) lacking an abandon-counter reference or key emit in the same
  state's action.

#### Tests

- `scripts/tests/test_fsm_validation_evaluator_rules.py` —
  `TestAbandonmentVerdict` (line 1048+) covers MR-13 detection patterns; add
  coverage there or in a generator-evaluator-specific test confirming the new
  abandoned-key state satisfies the rule with no `abandonment_verdict_ok`
  suppression needed.
- `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_flux_image_generator.py`
  — existing structural validation tests for generator-evaluator and its flux
  variant; extend for the new `snapshot`/`check_stall` routing.
- `scripts/tests/test_fsm_evaluators.py` — covers `evaluate_output_contains()`
  and `evaluate_exit_code()`, confirming the routing-cannot-see-124 premise.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/lib/common.yaml` — `score_stall_gate` (lines
  162-181) and `diff_stall_gate` (lines 148-160) are the fragment
  *definitions* `check_stall`/`check_diff_stall` inherit; not a file to
  change (the plan feeds a new counter into the states, not the shared
  fragments), but read it before touching either state's `evaluate:` block
  since `diff_stall_gate` is also consumed by 9 unrelated loops
  (`incremental-refactor.yaml`, `harness-single-shot.yaml`,
  `harness-multi-item.yaml`, `vega-viz.yaml`, `pixi-data-viz.yaml`,
  `openscad-model-generator.yaml`, `generative-art.yaml`,
  `canvas-sketch-generator.yaml`,
  `harness-plan-research-implement-report.yaml`) — any change to the
  fragment itself (as opposed to generator-evaluator-local logic) would
  regress all nine. [Agent 1 finding]
- `.ll/decisions.d/0d811c99-8ce6-485f-a6e6-bac24a6f9031.json` — prior
  decision on unevaluated-terminal-state design that cites
  `generator-evaluator.yaml` as precedent (BUG-2756); check it doesn't
  conflict with the new MR-13 penultimate-state shape before writing it.
  [Agent 1 finding]
- `.ll/decisions.d/5eb2dfa3-4e06-4916-9fc9-ebf3e47465d4.json` — prior
  decision establishing `from:`-based inheritance for
  `generator-evaluator-flux.yaml` (FEAT-2817); relevant to the "flux does
  not inherit `evaluate`/`snapshot`" gap noted below. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — the `## oracles/generator-evaluator`
  state-machine ASCII diagram documents today's unconditional
  `evaluate.on_yes/on_no/on_error → snapshot` routing and will go stale the
  moment `snapshot` gains staleness-detection logic or a new state is
  inserted; the `## oracles/generator-evaluator-cli` section's claim that
  `check_stall`/`check_diff_stall`/`done`/`failed` are "inherited unchanged"
  from the parent also needs re-verification once the parent's convergence
  chain changes. [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — documents the MR-13
  abandonment-verdict convention this issue's penultimate state must
  satisfy; cross-check the new state against the documented shape rather
  than only against the `general-task.yaml` precedent. [Agent 1/2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- None — `.screenshot_misses` is a shell-managed per-run file under
  `${context.run_dir}/`, the same as `.iter_counter`/`.score_history`; it is
  outside `EvaluateConfig`/`fsm-loop-schema.json` and needs no schema
  change (MR-14 does not apply). [Agent 2 finding, confirms existing plan]

### Wiring Notes (Implementation-Blocking)

_Wiring pass added by `/ll:wire-issue`:_
- **MR-13's detector will not recognize a bare counter-threshold mechanism.**
  `_validate_abandonment_verdict()`
  (`scripts/little_loops/fsm/validation/evaluator_rules.py:155-239`) only
  sets `mechanism_state` when a state's action matches one of three
  regexes: `_ABANDON_BANG_MARKER_RE` (`- [!]` checkbox rewrite),
  `_ABANDON_CHECKED_ANNOTATION_RE` (`[x]...abandon` annotation), or
  `_ABANDON_ATTEMPT_CAP_RE` (literal substring `max_step_attempts`). A
  `.screenshot_misses` counter compared against a threshold (the
  `.phantom_complete_count`/`.action_fail_count` idiom this issue already
  cites) matches none of them — `ll-loop validate` will pass with **no**
  MR-13 warning regardless of whether the `"abandoned"` key is actually
  emitted, which is silence, not compliance. To get real MR-13 enforcement,
  either name the threshold parameter/context key so it literally contains
  `max_step_attempts`, or verify the abandoned-key emission by test
  inspection rather than by `ll-loop validate` passing. [Agent 2 finding]
- **Adding a `summary.json` here is a new contract, not just a new file.**
  No state in `generator-evaluator.yaml` currently writes `summary.json`;
  `fsm/persistence.py` copies it to the run archive "if present" for every
  consumer, so the new penultimate state introduces an archived-run
  artifact all five wrapper loops implicitly gain. Fine per the issue's own
  scope decision ("land in the shared oracle"), but implementers should not
  be surprised that this is observable outside the oracle. [Agent 2
  finding]
- **`generator-evaluator-flux.yaml` does not inherit `evaluate`/`snapshot`
  — it reimplements them.** Unlike `generator-evaluator-cli.yaml` (`from:
  generator-evaluator`), the flux variant independently defines its own
  `evaluate` state (`generator-evaluator-flux.yaml:188-205`, its own
  `evaluate.on_yes == "snapshot"` at line 205). If the staleness check
  lands inside `snapshot`'s action/routing rather than as a wholly separate
  state, flux needs the parallel change and `test_flux_image_generator.py`
  needs a parallel test — this is a second implementation site, not just a
  "check whether it diverges" item. [Agent 1/3 finding, sharpens the
  existing "Dependent Files (variants and consumers)" note above]

### Tests (additional)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestGeneratorEvaluatorOracle` — specific
  existing tests that will break or need updating:
  - `test_evaluate_routes_to_snapshot_on_all_outcomes` (~line 9814) — breaks
    if `evaluate` routes anywhere other than `snapshot` directly.
  - `test_score_uses_output_contains_all_pass` /
    `test_score_routes_to_done_on_yes` (~lines 9820/9824) — update if
    `score`'s fragment/`on_yes` changes for the stale-screenshot skip.
  - `test_max_steps_covers_intended_cycle_count` (~line 9855) — hardcodes a
    "7-state cycle" (`max_steps >= 7 * 5`); update the multiplier if a new
    state is inserted into the generate→score cycle.
  - `test_records_score_history_under_run_dir` (~line 9842) — the template
    to mirror for a new `.screenshot_misses`-under-run_dir structural test.
  [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestGeneratorEvaluatorCliOracle` —
  `test_resolved_has_generator_evaluator_states` /
  `test_resolved_inherits_on_max_steps_summary_state` (~lines 9926/9932) —
  extend the expected-states list with any new state name(s), since the CLI
  variant inherits everything via `from:`. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::test_generator_evaluator_no_mr4_warnings`
  (~line 564) — the pattern to copy for a new
  `test_generator_evaluator_no_mr13_warnings` test: load the real YAML,
  run the MR-13 rule function, assert no unexpected warning. [Agent 3
  finding]

## Scope Boundaries

In scope: the screenshot-miss signal and its propagation through `snapshot`,
`score`, and the stall detectors in `oracles/generator-evaluator.yaml`; the
parallel missing-artifact blindness in `snapshot`'s first `cp ... || true`; and
the MR-13 `"abandoned"` summary key on the convergence path.

Out of scope — two recommendations from the source diagnosis are deliberately
excluded:

- **Gating re-launch on `user-stop.marker`.** The marker written at `22:51:15Z`
  did not prevent a new run at `22:51:47Z`, but that orchestration lives in the
  `loop-sandbox` repo, not here.
- **A host-level `chrome-headless-shell` descendant counter.** Belt-and-braces
  defense against a leak that BUG-2901 fixes at the root; revisit only if
  orphaned trees are observed after that lands.

A `screenshot_timeout` event type was also considered and dropped — once
BUG-2901 works, the timeout already surfaces as `exit_code: 124` in the event
stream, which downstream tooling can key on without a new event type. (This
remains true: the 124 *is* in the event stream. It is only *routing* that cannot
see it — see the premise correction under Status.)

## Open Questions

All three resolved 2026-07-29 (pre-implementation review):

- **Dedicated counter, not `diff_stall` inference.** `diff_stall` compares
  artifact content; an absent screenshot alongside an unchanged artifact is a
  genuinely different condition, and overloading the detector would conflate
  "the generator has plateaued" with "we never got a look at the output." Use an
  explicit `.screenshot_misses` counter under `${context.run_dir}/`, and let it
  feed the existing stall states rather than replacing them.
- **Land in the shared oracle, not per-consumer.** "Do not rubric-score a stale
  screenshot" is correct for all five wrappers; per-wrapper tolerance is
  speculative, and there is no evidence any consumer wants the current silent
  behavior. Revisit only if a wrapper is later shown to need a different
  threshold.
- **Yes on MR-13.** If this converges to a terminal state via abandonment, the
  run must emit an `"abandoned"` key into `summary.json` and downgrade the
  verdict; otherwise `ll-loop validate` warns (MR-13, suppressible only via
  `abandonment_verdict_ok`, which is not the right answer here). Budget for a
  penultimate non-terminal state that writes the summary — a terminal state's
  own `action:` is dead code per the `terminal-action-ok` rule.

## Acceptance Criteria

- [x] BUG-2901 is merged — commit `e2cb3d8e`.
- [ ] BUG-2904 is merged (remaining hard prerequisite).
- [ ] A missing/stale `screenshot.png` is detectable downstream of `evaluate`
      **without relying on an `on_error` route** (a timeout arrives as `no`).
- [ ] A missing artifact in `snapshot`'s first `cp` is likewise detected rather
      than swallowed by `|| true`.
- [ ] `score` does not silently rubric-score a stale screenshot.
- [ ] Repeated screenshot failures converge to a terminal state with an honest
      verdict rather than exhausting `max_steps`.
- [ ] The convergence path emits an `"abandoned"` key into `summary.json` and
      downgrades the verdict (MR-13); `ll-loop validate` raises no MR-13 warning
      and no `abandonment_verdict_ok` suppression flag is added.
- [ ] No behavior change for consumers whose screenshots succeed.
- [ ] `ll-loop validate` passes for the oracle and all five wrappers.
- [ ] `python -m pytest scripts/tests/` exits 0.


## Session Log
- `ll-auto` - 2026-07-29T04:06:22 - `fe1a990c-7983-4595-8a5e-184d7214c6f5.jsonl`
- `/ll:confidence-check` - 2026-07-29T00:00:00 - `be35e6e0-35c8-4478-9abb-abfba23b18e9.jsonl`
- `/ll:wire-issue` - 2026-07-29T03:48:42 - `e1c2f611-44fd-43eb-a38e-d59fca2b6505.jsonl`
- `/ll:refine-issue` - 2026-07-29T03:42:41 - `12f97373-165e-476f-920f-f5e8e6a85dac.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
