---
id: FEAT-3335
type: FEAT
title: Generalize the check_intent_scope containment gate to workflow-generator's
  post-gate prompt states
priority: P4
status: open
discovered_by: review-of-FEAT-3332
discovered_date: '2026-08-26'
captured_at: '2026-08-26T00:00:00Z'
depends_on: [FEAT-3332]
decision_needed: false
learning_tests_required: [pyyaml]
unproven_mechanism: true
spike_completed: true
spike_attempted: true
---

# FEAT-3335: Generalize the check_intent_scope containment gate to workflow-generator's post-gate prompt states

## Summary

FEAT-3332 adds `check_intent_scope`, a runtime containment gate asserting that the
changed-file set since `init` stays under `${captured.run_dir.output}`. By its own
statement it is **one-shot, at one point in a twelve-state pipeline**: it audits
only the `init` → `validate_intent` window, because that is where the source
incident (`2026-08-26T171218-workflow-generator`, `capture_intent` writing
`research/*.md` outside `run_dir`) occurred.

`sketch_state_graph`, `attach_evaluators`, `resolve_routing`, `emit_artifact`, and
`shrink`/`await_confirmation`/`promote` all run *after* the gate and are equally
capable of writing outside `run_dir`. This issue closes the rest of the pipeline.

> **Correction (2026-08-28) — state inventory is stale.** The "twelve-state
> pipeline" framing above (and the single `shrink` state this issue lists
> throughout) no longer matches the tree: the loop now has **27 states**.
> `shrink` is a 6-state family (`check_shrink_enabled`, `shrink_baseline`,
> `shrink_select_candidate`, `shrink_try_remove`, `shrink_probe_candidate`,
> `shrink_apply`), and `promotion_gate` and `finalize_await_confirmation`
> also exist. AC #1's covered-state list and the open placement-count design
> question (Expected Behavior #1) must be **re-evaluated against the
> 27-state graph and `max_steps: 45`**. The two open design decisions
> (placement count, late-violation routing) remain unresolved and still
> require a decide pass before this issue is implementation-ready.

## Current Behavior

FEAT-3332 landed 2026-08-27. `check_intent_scope` exists in
`scripts/little_loops/loops/workflow-generator.yaml` (state
`check_intent_scope`, `on_yes: sketch_state_graph` / `on_no: diagnose`), and
`init` writes the two baseline files (`baseline-ref.txt`,
`baseline-changed-set.json`). Exactly one containment assertion exists,
between `validate_intent` and `sketch_state_graph`. Every prompt state after
it is unaudited. A stray write from `sketch_state_graph` onward is as
invisible as the original incident was.

`diagnose` is the one post-gate prompt state FEAT-3332 already handles — it gets
BUG-3327's no-stray-writes fence clause there (requirement (j)), because
FEAT-3332 creates the `on_no` edge into it. That is a fence, not a gate: nothing
checks whether `diagnose` complied.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Confirmed landed: the FEAT-3332 gate is `check_intent_scope` at `scripts/little_loops/loops/workflow-generator.yaml:229-344`, with `on_yes: sketch_state_graph` / `on_no: diagnose`; `init` (lines 44-168) captures `baseline-ref.txt` + `baseline-changed-set.json` and truncates `.scope_violations.txt`. The two embedded `python3 -c` bodies must stay byte-identical (argv-only difference) — enforced by `test_check_intent_scope_matched_pair_byte_identical` (`scripts/tests/test_builtin_loops.py:17854`); any factoring of the gate body must keep that pair relationship intact or update that test in the same change.
- Post-gate state taxonomy (constrains the AC's enumeration): the post-gate LLM (`action_type: prompt`) states are `sketch_state_graph`, `attach_evaluators`, `resolve_routing`, `emit_artifact`, `finalize_await_confirmation`, and `diagnose`. There is no state named `shrink` — the shrink pass is five deterministic shell states (`shrink_baseline`, `shrink_select_candidate`, `shrink_try_remove`, `shrink_probe_candidate`, `shrink_apply`); `promote` is also shell; `await_confirmation` is `terminal: true` with no action and cannot write anything. "shrink"/"promote" in this issue name *windows*, not prompt states — a gate over those windows guards against defects in fixed shell scripts, a different (statically auditable) risk class than LLM stray writes.
- The changed-set enumeration excludes `**/.loops/**` AND `**/.ll/**` at any depth (`EXCL`, byte-identical at both script sites, e.g. `workflow-generator.yaml:258`; documented as limit #4 in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:735`). Consequence: with the default `loops_dir: ".ll/loops"`, `promote`'s write is already invisible to the gate — see the loops_dir finding under Proposed Solution.
- Step-budget ground truth (`max_steps: 45`): the default happy path (no shrink, no promote) visits ~16 states. `count_intent_retry`/`count_emit_retry` bound their loops at 3 attempts (~3 steps per retry cycle, up to +12 combined), but the `validate_sketch`→`sketch_state_graph`, `validate_evaluators`→`attach_evaluators`, and `validate_routing`→`resolve_routing` failure bounces have NO counter — they are unbounded 2-step cycles limited only by `max_steps`, and are the real headroom competitor. The shrink pass (off by default) consumes 1 + ~3-4 steps per candidate state of the generated workflow.
- Gate insertion edges, concretely: per-pass gates would sit on `validate_sketch.on_yes→attach_evaluators`, `validate_evaluators.on_yes→resolve_routing`, `validate_routing.on_yes→emit_artifact`, `validate_artifact.on_yes→check_shrink_enabled`, `shrink_select_candidate.on_no→promotion_gate`, and `promote.next→done`. Because every insertion point is on an on_yes/exit edge, retry loops never re-cross a gate — each gate costs exactly +1 step per traversal (+6 total for full coverage; happy path 16→22 of 45).
- Violation-reporting plumbing: the gate writes violations to `${run_dir}/.scope_violations.txt` (truncated at `init`), and `diagnose`'s prompt (`workflow-generator.yaml:866-889`) reads it — but that prompt's text describes only the intent-window failure ("check_intent_scope found..."). Late gates routing to `diagnose` need that text generalized; a warn-and-continue route needs `finalize_await_confirmation`'s prompt (lines 847-859) to surface the violation text instead.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Anchor refresh (2026-08-30, re-verified against current tree): every citation below now resolves at a different line than stated above, but the substantive claim at each is unchanged. `check_intent_scope` now spans `workflow-generator.yaml:248-363` (`on_yes` at line 362, `on_no` at 363), not `:229-344`. `init` now spans `:44-187` (`next: capture_intent` at 187), not `:44-168`. The six insertion edges now sit at `validate_sketch.on_yes:425`, `validate_evaluators.on_yes:507`, `validate_routing.on_yes:555`, `validate_artifact.on_yes:614`, `shrink_select_candidate.on_no:713`, `promote.next:854`. `diagnose`'s prompt is now at `:875-899`; `finalize_await_confirmation`'s is now at `:856-868`. `fence.py`'s `("workflow-generator.yaml", "capture_intent")` fence-site tuple is now at line 90, not `:76`.
- Drift root cause: the ~19-line shift traces to an unrelated ENH-3355 block (lines 69-86 of `init`) that generates `evaluator-vocab.md` from `little_loops.fsm.validation`'s own tables — landed after this issue's 2026-08-28 refine pass, no relation to FEAT-3332/3335 containment logic. No state was renamed, removed, or rerouted.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` anchors also moved: `## Runtime Containment Gates` heading now at `:792` (was `~:679`), limit #1 ("One-shot window...FEAT-3335") now at `:830-837` (was `:714-723`), limit #4 (`.loops`/`.ll` exclusion) now at `:848-852` (was `:735`).
- New gap in that doc, found this pass: limit #1's own enumeration of unaudited states (`sketch_state_graph`, `attach_evaluators`, `resolve_routing`, `emit_artifact`, `diagnose`) omits `finalize_await_confirmation`, even though it is a reachable `action_type: prompt` state (line 856) on the `promotion_gate.on_no` branch. Implementation Step 7's doc update should add it to that enumeration, not just replace the one-shot caveat.

## Expected Behavior

Containment is asserted across the whole pipeline, not just its first window,
without multiplying near-duplicate state definitions.

Two open design questions this issue must settle before implementing (question
1 is now formatted as the Option A/B decision under Proposed Solution →
Codebase Research Findings, with the step budget in hand):

1. **Gate placement — one re-check or several?** A single re-check just before
   `emit_artifact` covers the lowering passes cheaply but reports a violation long
   after the state that caused it, losing attribution. Per-pass gates give exact
   attribution at +1 step each, against a `max_steps` of 45 that already has the
   `count_emit_retry` / `count_intent_retry` retry loops competing for headroom.
   Decide with the step budget in hand.
2. **Routing on violation.** FEAT-3332 routes to `diagnose` because a scope
   violation is not retryable. That reasoning holds for every later state, but a
   violation detected after `emit_artifact` has produced a valid `workflow.yaml`
   is a different operator situation — the useful artifact exists. Decide whether
   late violations fail the run or warn-and-continue to `await_confirmation` with
   the violation surfaced in the confirmation text.

## Use Case

An operator runs the `workflow-generator` meta-loop unattended (e.g. from
`ll-loop run` in automation). A lowering pass such as `resolve_routing` or
`emit_artifact` writes a file outside `${captured.run_dir.output}` — the same
class of stray write as the original incident, just later in the pipeline.
Today that write lands silently in the working tree; with this feature the run
gates on it, the violation is attributed to the offending state (or window),
and the operator sees it in the run output instead of discovering polluted
tree state after the fact.

## Proposed Solution

Rather than duplicating the gate's shell body per insertion point, factor the
containment check once and re-enter it. Candidate approaches, to be evaluated:

- **A shared fragment under `loops/lib/`** referenced from each insertion point
  (note: `loops/lib/` is the fragments dir; loops elsewhere, including
  subdirectories, are runnable — see the repo's loop-authoring conventions).
- **A per-pass baseline rather than a single `init` baseline** — each gate diffs
  against the *previous* gate's snapshot rather than `init`'s, which gives exact
  attribution to the state between them and makes the "which state wrote this"
  question answerable. This changes `init`'s two baseline files into a
  rolling snapshot that each gate rewrites on pass.
- **An `ll-loop`-level facility** rather than YAML-level states, if the check is
  general enough to belong to every meta-loop rather than to this one loop. This
  is the largest option and should not be chosen without a second consumer.

Requirements carried over from FEAT-3332, all of which still apply and must not be
re-derived:

- `loops_dir` (`${context.loops_dir}`, default `.ll/loops`) **must be added to the
  allowed set** once the gate covers `promote` — `auto_promote` legitimately
  writes there, and a run-dir-only subset assertion would read promotion as a
  violation. FEAT-3332 explicitly defers this (its requirement (h)) because its
  gate runs long before `promote`; this issue is where it comes due.
- Root-scoped enumeration (`git -C "$ROOT"`, no cwd-relative `-- .`), the
  `.loops/`-wide exclusion, the dirty-tree baseline, the non-repo and
  outside-the-worktree escapes, and the `$${VAR}` FSM-interpolation escaping.
- The gitignored-write blind spot (`--exclude-standard` hides `node_modules/`,
  `.env`, etc.) remains an accepted limit; generalizing the gate does not close
  it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Candidate (a) "shared fragment" is first-class, precedented machinery, not a convention to invent: the FSM resolves `fragment:` state references at parse time via `resolve_fragments()` (`scripts/little_loops/fsm/fragments.py:66`), from either an `import:` of a library under `scripts/little_loops/loops/lib/` (note: that path, not repo-root `loops/lib/`) or a loop-local `fragments:` block (local wins). Fragments declare `parameters:` (ParameterSpec) bound per state via `with:`, interpolated as `${param.<name>}` in the action body (`scripts/little_loops/fsm/executor.py:3362-3373`). Evidence of the convention: `lib/common.yaml` defines `shell_exit` (line 15 — exactly the `action_type: shell` + `evaluate: exit_code` shape a gate needs), `snapshot_artifact` (line 233, `run_dir` parameter), and `loop_failure_diagnose` (line 304, `loop_name`/`extra_bullets` parameters); `autodev.yaml` references fragments at 8+ states via `import:` (line 43). A loop-local `fragments:` block would keep workflow-generator self-contained with zero new files.
- Contested convention, decide knowingly: workflow-generator itself currently uses NO fragments and no `import:` — its own `count_intent_retry` (line 346) and `count_emit_retry` (line 608) are near-duplicate shell blocks left unfactored, while `autodev.yaml` and others factor aggressively. The codebase holds both positions; this issue's "defined once" AC takes the fragment side for the new gate.
- Candidate (b) rolling snapshot has no in-repo precedent, but is a mechanical extension: the comparison-mode branch of the shared `python3 -c` script already computes the full `current` map; re-dumping it to `baseline-changed-set.json` on pass is an additional mode/argv. Both embedded copies of the script must change together (byte-identical pair, `test_builtin_loops.py:17854`).
- Candidate (c) ground truth: the loop's existing top-level `scope:` key (`workflow-generator.yaml:29-31`) already lists `${context.run_dir}` and `${context.loops_dir}` — but that key is concurrency-control metadata ("paths this loop operates on", `scripts/little_loops/fsm/schema.py:1370`, consumed by `fsm/concurrency.py`), NOT containment enforcement. No `ll-loop`-level containment facility exists, and the "needs a second consumer" bar this issue sets for (c) remains unmet. Do not mistake the `scope:` key for (c) already existing — though it is the natural declared-vocabulary anchor if (c) is ever built.
- loops_dir / requirement (h), materially changed by the landed implementation: the gate's enumeration pathspec-excludes `**/.ll/**` wholesale, so with the default `loops_dir: ".ll/loops"` a `promote` write NEVER enumerates and cannot trip the gate — the "would read promotion as a violation" premise holds only when an operator overrides `loops_dir` to a path outside `.ll/` (e.g. `--set loops_dir=loops`). Adding `${context.loops_dir}` to the allowed set is therefore correct-but-vacuous under defaults; the AC's `promote`/`loops_dir` regression test must override `loops_dir` to a non-`.ll/` path or it passes vacuously and guards nothing.

**Option A**: Single re-check on the `validate_artifact.on_yes` edge (before `check_shrink_enabled`/`promotion_gate`), keeping the init-anchored baseline — +1 step, covers all four lowering passes cheaply, but attributes a violation only to "somewhere after check_intent_scope", and leaves the shrink/promote windows uncovered unless a second instance is added after them.

**Option B**: Per-pass gates at the six window boundaries (edges enumerated under Current Behavior → Codebase Research Findings), factored as one parameterized fragment, with a rolling baseline — each gate re-snapshots on pass, so each diff window names the states between gates and attribution is exact. Deterministic cost +6 steps (happy path 16→22 of `max_steps: 45`); retry loops never re-cross a gate, so the cost does not multiply under retries.

> **Selected:** Option B — only shape satisfying all ACs as written (full coverage incl. shrink/promote windows, gate body defined once, per-window attribution); fragment machinery is precedented and the +6 step cost is deterministic against `max_steps: 45`.

**Recommended**: Option B — the step budget affords +6 (the unbounded validate-bounce loops and the off-by-default shrink pass are the only real competitors for the remaining ~23 steps), the fragment facility makes N insertions a single definition (satisfying the "defined once" AC), and per-window attribution is this issue's stated point (Use Case: "the violation is attributed to the offending state (or window)"). The late-violation routing question (Expected Behavior question 2: fail vs warn-and-continue after `emit_artifact` has produced a valid artifact) is NOT settled by this research — both routes are wireable (see the violation-reporting plumbing finding under Current Behavior) and the choice is an operator-preference call to record via /ll:decide-issue alongside this option selection.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Reconfirmed (2026-08-30, independent repo-wide search): no loop or Python module anywhere in the tree implements a per-pass rolling-baseline diff pattern — searching for `rolling baseline`/`rolling_baseline` as a mechanism name found no hits outside this issue's own text and its decision record. The closest analog, `diff_stall_gate`'s `evaluate.previous`-style comparison, is LLM-loop convergence detection across iterations, a different mechanism (stall detection, not containment attribution). The selected Option B depends on this mechanism for its per-window attribution claim.
  ⚠ Unproven mechanism — rolling baseline has no in-repo precedent

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-28.

**Selected**: Option B — per-pass gates at the six window boundaries, factored as one
parameterized fragment, with a rolling baseline.

**Reasoning**: Option B is the only shape that satisfies the acceptance criteria as
written — coverage of every post-gate window including shrink/promote, a gate body
defined once, and per-window attribution (the Use Case's stated point). The fragment
machinery it needs is first-class and precedented (`resolve_fragments()` at
`scripts/little_loops/fsm/fragments.py:66`; `lib/common.yaml` `shell_exit` /
`snapshot_artifact`; `autodev.yaml` `import:` referenced at 8+ states), and all six
insertion edges are verified on_yes/exit edges, so the +6 step cost is deterministic
(happy path 16→22 of `max_steps: 45`) and never multiplied by retry loops. Option A's
+1-step economy is real, but it cannot cover the shrink/promote windows without a
second instance — at which point it either duplicates the shell body (violating the
defined-once AC) or converges on B's fragment anyway.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 3/3 | 2/3 | 2/3 | 9/12 |
| Option B | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- The rejected single-recheck shape reuses the landed gate body verbatim
  (`workflow-generator.yaml:229-344`) with no baseline changes, matching this loop's
  currently unfactored style (`count_intent_retry`/`count_emit_retry` are unfactored
  near-duplicates) — but it attributes a violation only to "somewhere after
  `check_intent_scope`" and leaves the shrink/promote windows uncovered, failing AC #1
  and the attribution requirement.
- The selected per-pass fragment shape is verified live: `fragments.py:66`;
  `lib/common.yaml:15` `shell_exit` is exactly the shell + `evaluate: exit_code` gate
  shape, parameterized via `ParameterSpec`/`with:`; the six edges
  (`workflow-generator.yaml:406, 499, 547, 605, 636/704, 845`) are all on_yes/exit
  edges; the rolling baseline is a mechanical extra mode of the existing comparison
  script, with the byte-identical-pair constraint (`test_builtin_loops.py:18046`) and
  the resolved-fragments test fixture as the known costs.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — additional gate
  placements and, if the rolling-snapshot approach is chosen, a changed `init`
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — replace FEAT-3332's "one-shot
  window" caveat with the actual coverage
- `docs/reference/loops.md` — the `workflow-generator` `### State Graph` diagram

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/data/loop_interpolation_baseline.json` — the ENH-3338
  ratcheting baseline of embedded-Python interpolation sites; must change in
  the same commit if the gate factoring adds, moves, or renames any
  `${context.*}`/`${captured.*}` reference inside a `python3 -c`/heredoc
  Python body (see Tests below — both directions of the ratchet fail)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/interp_sweep.py` — `scan_corpus()` walks BOTH
  top-level `states:` AND `fragments:` keys of every loop YAML under
  `BUILTIN_LOOPS_DIR` recursively (`interp_sweep.py:232-246`, including
  `lib/*.yaml`), so the new gate body is swept wherever the fragment lives
  (loop-local block or lib file). Consumer only — no edit needed here.
- Conditional branch (fragment location, ENH-3050): the research findings
  recommend a loop-local `fragments:` block (zero new files), but Proposed
  Solution candidate (a) names a shared fragment under
  `scripts/little_loops/loops/lib/` — if that route is chosen instead,
  `scripts/little_loops/loops/lib/common.yaml` (or a new lib file) enters
  Files to Modify and workflow-generator.yaml additionally gains an
  `import:` key (precedent: `autodev.yaml:43`); `scan_corpus` sweeps lib
  fragments identically.

### Tests
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop` — extend
  `test_pipeline_states_exist`, `test_validation_gates_are_exit_code`, and
  `test_run_dir_used_throughout` for each new gate, following
  `TestGeneralTaskFinalVerifySpinGateShellAction`'s shell-action harness shape
  (class at line 2999)
- A `promote` / `loops_dir` case: a legitimate write to `${context.loops_dir}`
  under `auto_promote: true` must **not** trip the gate. This is the regression
  the deferred requirement (h) exists to prevent.
- `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  — watch for new WARNING categories from the added states

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestInterpSweepBaseline.test_completeness_guard`
  (`:19194`, class at `:19183`) — both-directions ratchet against
  `scripts/tests/data/loop_interpolation_baseline.json`: a new unbaselined
  embedded-Python interpolation site fails, and a baseline entry that no
  longer scans fails. workflow-generator already carries 8 class-C heredoc
  entries keyed by state name (`validate_intent`, `validate_sketch`,
  `validate_evaluators`, `validate_routing`, `shrink_baseline`,
  `shrink_select_candidate`, `shrink_try_remove`, `shrink_probe_candidate`);
  factoring that moves a body into a fragment re-keys its site tuple to the
  fragment entry name — update the baseline JSON in the same commit
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop.test_max_steps_is_45`
  (`:18266`) pins `max_steps == 45` exactly (plus `test_max_steps_is_at_least_40`
  at `:18171`). The Option B analysis keeps 45 (happy path 16→22); if the
  implementation instead raises `max_steps` for headroom, this pin must be
  updated deliberately in the same change
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop.test_shrink_gated_by_context_flag`
  (`:17976`) asserts `check_shrink_enabled.on_no == "promotion_gate"` — a
  placement constraint: the shrink-window gate belongs on
  `shrink_select_candidate.on_no` (as the insertion-edge list already says),
  NOT on `check_shrink_enabled.on_no`. Note the shrink-disabled default path
  (`check_shrink_enabled.on_no → promotion_gate`) therefore bypasses the
  shrink-window gate; the `validate_artifact.on_yes` gate is the last
  assertion before promotion on that path
- Edge-pin survey (verified by grep over `TestWorkflowGeneratorLoop`,
  `:17899-18600`): NO existing test asserts the current target of any of the
  six insertion edges (`validate_sketch.on_yes`, `validate_evaluators.on_yes`,
  `validate_routing.on_yes`, `validate_artifact.on_yes`,
  `shrink_select_candidate.on_no`, `promote.next`) — the pinned edges are
  `check_intent_scope.on_yes` (`:18044`), `count_emit_retry.on_yes` (`:18164`),
  `count_intent_retry.on_yes` (`:18250`), `promotion_gate.on_yes/on_no`
  (`:17986-17989`), and `check_shrink_enabled.on_no` (`:17981`), none of which
  the plan re-targets — so the insertions break no existing edge assertion
- Raw-fixture precedent for fragment-ref states: structural tests may assert
  `state.get("fragment") == "<name>"` directly on the raw YAML
  (`test_builtin_loops.py:2585`, `:2678`, `:2783` assert
  `fragment == "shell_exit"`), complementing the resolved-fixture route the
  research findings describe for `action`/`evaluate` assertions

### Behavior Parity

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the "one-shot window" caveat
  from FEAT-3332 is replaced, not deleted: the guide must still document the
  containment gate's mechanics (baseline, allowed set, escapes) exactly as it
  does today, updating only the stated coverage from the single
  `init` → `validate_intent` window to the full pipeline. The gitignored-write
  blind spot caveat is retained verbatim — it remains an accepted limit.

### Documentation
- Both files above

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — advisory only: the catalog row (`:1504`)
  and `### workflow-generator` section (`:2657`) describe the pass/gate
  pipeline and the Promotion window but do not mention the FEAT-3332
  containment gate today, so they do not go stale; update the Technique
  paragraph only if per-window containment coverage should be
  operator-visible at this doc's level
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1205` checked and deliberately
  NOT added: its one-line catalog description ("six sequential passes, each
  LLM pass paired with a non-LLM `exit_code` gate") remains accurate after
  this change

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Test-fixture convention for fragment-using loops: structural tests resolve the raw YAML through `resolve_fragments(yaml.safe_load(...), BUILTIN_LOOPS_DIR)` in a `resolved`/`resolved_data` fixture (`scripts/tests/test_builtin_loops.py:516`, `:9462`, `:12544`, `:12806`). `TestWorkflowGeneratorLoop`'s current `data` fixture (line 17717) reads raw YAML only — if the new gates are `fragment:` references, extensions of `test_validation_gates_are_exit_code` (line 17810) and the matched-pair test (line 17854) must go through the resolved fixture (or read the fragment definition directly), because the raw state dict will no longer carry `action`/`action_type`/`evaluate`.
- The closest shell-action harness is now `TestCheckIntentScopeShellAction` (`scripts/tests/test_builtin_loops.py:18231`) — the FEAT-3332 class that executes the actual gate action against real temp git repos with `_init_repo`/`_run_init`/`_run_gate`/`_setup` helpers; it was itself cloned from `TestGeneralTaskFinalVerifySpinGateShellAction` (now at line 2999; the Tests citation below has been refreshed to match). New per-gate behavioral tests extend the FEAT-3332 class's helpers rather than re-cloning the general-task shape.
- Fence coverage is orthogonal to gate coverage and already accounted: `fence.py` (`scripts/little_loops/fsm/fence.py`) is the canonical authority for BUG-3327 fence text; `capture_intent` is this loop's only classified class-(1) fence site (`fence.py:76`) and `diagnose` carries FENCE_CORE's "write no file" clause inline. The four post-gate lowering prompt states interpolate no user-authored text (they read run_dir files), so they are not fence sites — this issue's gates are the only planned containment for them.
- Docs anchors, current: the "one-shot window" caveat to replace is limit #1 of "Five limits" in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:714-723` (it names FEAT-3335 explicitly); the wholesale `.loops/`/`.ll/` exclusion is limit #4 (line 735). The state-graph diagram to update is `docs/reference/loops.md:157-176`; that file's Context Variables table (lines 147-153) also omits `max_intent_retries` — a pre-existing gap adjacent to the edit, not caused by it.
- `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml` currently passes clean (27 states, max_steps 45) — the no-new-WARNING-categories AC baselines against `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow` (`scripts/tests/test_builtin_loops.py:16221`, class at 16119; both resolve).

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- HARNESS_OPTIMIZATION_GUIDE.md scope addition, found this pass: limit #1's enumeration of unaudited states (currently `sketch_state_graph`, `attach_evaluators`, `resolve_routing`, `emit_artifact`, `diagnose`) omits `finalize_await_confirmation` — a reachable `action_type: prompt` state on the `promotion_gate.on_no` branch. The doc-update Files-to-Modify entry should add this state to the enumeration being replaced, not just swap out the one-shot caveat text.

## Program Design

### Signatures

- `check_scope_containment(baseline_file: str, allowed_dirs: list[str]) -> int` — the
  factored shell gate body: diffs the tracked-file set against the baseline
  snapshot, exits 0 when every changed path is under an allowed dir
  (`${captured.run_dir.output}`, plus `${context.loops_dir}` for gates at or
  after `promote`), non-zero otherwise. Whether it materializes as N
  `check_<state>_scope` FSM shell states or one parameterized fragment is the
  open factoring decision; the contract above holds either way.

### Call Path

`ll-loop run` → FSM state machine for
`scripts/little_loops/loops/workflow-generator.yaml` → existing
`check_intent_scope` gate (FEAT-3332) → new gate insertion points, in pipeline
order: after `sketch_state_graph`, `attach_evaluators`, `resolve_routing`,
`emit_artifact`, `shrink`, and `promote`. Validation surface:
`scripts/little_loops/fsm/validation/meta_rules.py` (`ll-loop validate` MR rules).

Concrete insertion edges (from codebase research, 2026-08-28 — the six window
boundaries as they exist in the landed YAML): `validate_sketch.on_yes` →
`attach_evaluators`, `validate_evaluators.on_yes` → `resolve_routing`,
`validate_routing.on_yes` → `emit_artifact`, `validate_artifact.on_yes` →
`check_shrink_enabled`, `shrink_select_candidate.on_no` → `promotion_gate`,
and `promote.next` → `done`. All are on_yes/exit edges, so retry loops
(`count_intent_retry`, `count_emit_retry`, and the unbounded
`validate_*`-bounce cycles) never re-cross a gate. If gates are `fragment:`
references, `resolve_fragments()` (`scripts/little_loops/fsm/fragments.py:66`)
expands them before `FSMLoop.from_dict`, so the executor and `ll-loop
validate` see ordinary shell states.

### Decision Rules

- Inputs per gate: `baseline-changed-set.json` (or the rolling snapshot, per
  the Option A/B decision under Proposed Solution) diffed against the
  recomputed changed-set map (tracked ∪ untracked, path → sha256, symmetric
  comparison including deletions) — the same rule FEAT-3332 landed.
- Allowed set: a changed path passes iff its `os.path.realpath` is under
  `${captured.run_dir.output}` (prefix check with separator), plus — for
  gates at or after `promote` only — under `${context.loops_dir}`. Note the
  enumeration already pathspec-excludes `**/.loops/**` and `**/.ll/**` at any
  depth, so the `loops_dir` branch is only observable when `loops_dir` is
  overridden outside `.ll/`.
- Escape hatches (carried verbatim from FEAT-3332, apply to every gate): no
  git repo or zero-commit repo → `SKIPPED` on stdout, exit 0; missing,
  zero-byte, or unparseable baseline file → same skip; a baseline parsing to
  `{}` gates normally. Gitignored writes (`--exclude-standard`) remain
  invisible — accepted limit, not closed by this issue.
- Routing on violation: exit non-zero → `on_no` edge; destination for
  post-`emit_artifact` gates (fail via `diagnose` vs warn-and-continue via
  `finalize_await_confirmation`) is Expected Behavior question 2, to be
  recorded by /ll:decide-issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- No `parameters:`/`with:` binding is actually required for the factored fragment: the shared shell body only ever references `${context.run_dir}`, `${captured.run_dir.output}`, and `${captured.run_dir.output:shell}`, all already resolvable at any state in this loop without a fragment binding. A factored fragment can supply the full literal `action:` body with zero declared `parameters:` — mirroring `lib/common.yaml`'s `loop_failure_diagnose` (full literal body + fixed routing, no required `with:`), not `snapshot_artifact` (which does take a `with:`-bound `run_dir`). Each of the six insertion states then supplies only `fragment: <name>` plus its own `on_yes`/`on_no`.
- Call Path edges, current line numbers (2026-08-30): `validate_sketch.on_yes:425`, `validate_evaluators.on_yes:507`, `validate_routing.on_yes:555`, `validate_artifact.on_yes:614`, `shrink_select_candidate.on_no:713`, `promote.next:854` (all confirmed still on_yes/exit edges, none re-targeted).
- Related convention, evidence only: `mechanize-skills.yaml:307-311`'s `diagnosis_retry` state explicitly declines the existing `retry_counter` fragment in favor of hand-rolled logic, because that fragment's baked-in path (`.loops/tmp/`) conflicts with per-run isolation. This codebase does have precedent for opting out of an otherwise-applicable fragment when its hardcoded path assumption doesn't fit — worth checking against if the rolling-baseline fragment ends up encoding a path assumption of its own.

## Implementation Steps

1. Settle the two design questions in Expected Behavior (placement count,
   late-violation routing) against the current `max_steps` budget.
2. Factor the containment check so it is defined once.
3. Add `${context.loops_dir}` to the allowed set for any gate at or after
   `promote`.
4. Place the gates.
5. Add the tests, including the `promote`/`loops_dir` false-positive guard.
6. Verify with `ll-loop validate` and a live run with a deliberately planted
   out-of-scope write from a *post-gate* state — **a green gate proves nothing
   until you have seen it go red**, and this issue's whole premise is that
   FEAT-3332's gate cannot see this class of write.
7. Update both docs, removing the one-shot caveat.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/data/loop_interpolation_baseline.json` in the same
  commit as the factoring if any embedded-Python interpolation site is added,
  moved, or re-keyed (the ENH-3338 ratchet fails in both directions;
  `scan_corpus` walks `states:` AND `fragments:`, `interp_sweep.py:232-246`)
- Keep `max_steps: 45`, or update
  `TestWorkflowGeneratorLoop.test_max_steps_is_45`
  (`scripts/tests/test_builtin_loops.py:18266`) deliberately in the same
  change if headroom is raised
- Place the shrink-window gate on `shrink_select_candidate.on_no` (not
  `check_shrink_enabled.on_no`, which `test_shrink_gated_by_context_flag`
  at `:17976` pins to `promotion_gate`)
- If the shared-lib fragment route is chosen over a loop-local `fragments:`
  block: add the fragment to `scripts/little_loops/loops/lib/common.yaml`
  (or a new lib file) and an `import:` key to `workflow-generator.yaml`
  (precedent: `autodev.yaml:43`)

## Acceptance Criteria

- [ ] Every prompt state after FEAT-3332's gate (`sketch_state_graph`,
      `attach_evaluators`, `resolve_routing`, `emit_artifact`, `shrink`,
      `promote`) is covered by a containment assertion, per the placement
      decision recorded in this issue.
- [ ] The gate body is defined once (fragment, rolling snapshot, or
      parameterized state) — no near-duplicate shell blocks per insertion point.
- [ ] `${context.loops_dir}` is in the allowed set for any gate at or after
      `promote`; a legitimate `auto_promote: true` write there does not trip
      the gate (test-guarded).
- [ ] A deliberately planted out-of-scope write from a post-gate state turns a
      gate red in a live run (the gate has been seen to fail, not just pass).
- [ ] `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml`
      passes with no new WARNING categories
      (`TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`).
- [ ] `TestWorkflowGeneratorLoop` extensions in
      `scripts/tests/test_builtin_loops.py` pass under
      `python -m pytest scripts/tests/`.
- [ ] Both docs updated: the one-shot caveat replaced with actual coverage;
      the state-graph diagram in `docs/reference/loops.md` reflects the new
      gates.

## Impact

- **Priority**: P4 — strictly defense-in-depth on top of defense-in-depth.
  BUG-3327's fence removed the cause; FEAT-3332 guards the window where the
  incident happened; this covers windows where nothing has yet gone wrong.
- **Effort**: Medium — dominated by the factoring decision, not the shell logic,
  which FEAT-3332 will have already written and tested.
- **Risk**: Medium — the same both-directions misfire risk FEAT-3332 documents,
  multiplied by the number of insertion points. The `promote`/`loops_dir`
  false positive is the specific new hazard this issue introduces and must be
  test-guarded.
- **Breaking Change**: No

## Scope

`workflow-generator`-only, matching FEAT-3332. Whether the containment check
should become a facility available to every meta-loop is a genuinely separate
question and should not be answered by widening this issue mid-flight — it needs
a second concrete consumer first.

## Notes

Filed 2026-08-26 from the pre-implementation review of FEAT-3332, which states
the one-shot limitation plainly (Expected Behavior, "Two limits of this
placement") and defers `loops_dir` (Proposed Solution requirement (h)) to
whatever picks this up. FEAT-3332 is done (confirmed 2026-08-28); this issue
reuses its gate body, baseline mechanics, and escape paths, all now in the
tree.

Original incident: the workflow-generator output-JSON gate-gap postmortem
(§4, §5 R5) in the gitignored, source-repo-only `postmortems` directory.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — § Runtime Containment Gates
  (~:679; gate-mechanics definition ~:686) documents the FEAT-3332 gate this
  issue generalizes, including the "one-shot window" caveat this issue
  replaces.
- `docs/reference/loops.md` — § `workflow-generator` (~:132) documents the
  loop, including the `### State Graph` diagram the new gates change.

## Spike Results

_Added by `/ll:spike` on 2026-08-29_

**Retired risks**

| Risk (from Decision Rationale / Codebase Research Findings) | Proven by | Result |
|---------------------------------------------------------------|-----------|--------|
| Rolling-baseline diff pattern has no in-repo precedent | `TestRollingBaselineGate::test_gate_passes_and_advances_baseline` | ✓ pass |
| Baseline advancement on failure could corrupt window boundaries | `TestRollingBaselineGate::test_gate_fails_and_leaves_baseline_untouched` | ✓ pass |
| Per-window attribution (Option B's core claim) is unproven across a multi-gate chain | `TestRollingBaselineGate::test_sequential_windows_attribute_violation_to_correct_gate` | ✓ pass |
| Advance-on-pass could mask a same-pass violation into the next window | `TestRollingBaselineGate::test_advance_does_not_mask_a_violation_in_the_same_pass` | ✓ pass |
| Isolation guard (spike stays standalone, not a production wrapper) | `TestIsolationGuard::test_rolling_gate_module_has_no_production_imports` | ✓ pass |

**Spike location**: `scripts/tests/spike/rolling_scope_gate/`
**Verification**: 5 spike tests pass, plus the 25-test `TestCheckIntentScopeShellAction` regression suite pass unmodified (30 tests across 2 commands).
**Promotion**: move `rolling_gate.py`'s `run_gate`/`changed_set` shape into the actual FSM fragment body in `scripts/little_loops/loops/workflow-generator.yaml` (or `scripts/little_loops/loops/lib/common.yaml`, per the fragment-location decision) in a separate PR.

## Status

**Open** | Created: 2026-08-26 | Priority: P4


## Session Log
- `/ll:spike` - 2026-08-30T04:18:09 - `ff699041-98cb-4619-b0e1-ea29f873929f.jsonl`
- `/ll:refine-issue` - 2026-08-30T03:54:52 - `60f4b2a5-6804-4c4a-8095-0f67f3431a09.jsonl`
- `/ll:wire-issue` - 2026-08-28T23:41:12 - `425908b6-e1d5-4f67-8fd1-7db76f87cdd4.jsonl`
- `/ll:decide-issue` - 2026-08-28T23:33:08 - `9f949531-f7bd-43e0-816a-3a64d73b2bba.jsonl`
- `/ll:refine-issue` - 2026-08-28T23:25:14 - `425908b6-e1d5-4f67-8fd1-7db76f87cdd4.jsonl`
- `/ll:format-issue` - 2026-08-28T23:13:29 - `425908b6-e1d5-4f67-8fd1-7db76f87cdd4.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Anchor refresh (2026-08-30, test file grew between 2026-08-28 and now — content of every cited test unchanged, only line numbers moved): `class TestWorkflowGeneratorLoop` now at `:17935` (its raw `data` fixture at `:17945-17948`, still raw-only, no `resolve_fragments()` call — confirmed); `test_validation_gates_are_exit_code` now at `:18038`; `test_run_dir_used_throughout` now at `:18058`; `test_check_intent_scope_matched_pair_byte_identical` now at `:18082`; `test_shrink_gated_by_context_flag` now at `:18012` (its `check_shrink_enabled.on_no == "promotion_gate"` assertion still confirmed present, adjacent at `:18017`); `TestCheckIntentScopeShellAction` now at `:18544`, its parent `TestGeneralTaskFinalVerifySpinGateShellAction` now at `:3216`; `test_max_steps_is_45` now at `:18387`, `test_max_steps_is_at_least_40` now at `:18292`; `TestInterpSweepBaseline`/`test_completeness_guard` now at `:19572`/`:19583`; `TestValidatorWarningBudget`/`test_deterministic_warning_categories_do_not_regrow` now at `:16346`/`:16449`. No edge-pin test was found to assert any of the six insertion-edge targets — the earlier edge-pin survey's conclusion still holds under the refreshed line numbers.
- Additional structural-test precedent for the fragment route (`fragment:`/`with:` on the raw dict, no `resolve_fragments()` call): `test_rn_decompose.py:489-497` asserts `state.get("fragment") == "subloop_rate_limit_diagnostic"` and `state.get("with", {}).get("operation") == "decomposition"` directly on `yaml.safe_load()` output — the same raw-fixture shape already cited, with a second concrete example.
