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

### Behavior Parity

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the "one-shot window" caveat
  from FEAT-3332 is replaced, not deleted: the guide must still document the
  containment gate's mechanics (baseline, allowed set, escapes) exactly as it
  does today, updating only the stated coverage from the single
  `init` → `validate_intent` window to the full pipeline. The gitignored-write
  blind spot caveat is retained verbatim — it remains an accepted limit.

### Documentation
- Both files above

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Test-fixture convention for fragment-using loops: structural tests resolve the raw YAML through `resolve_fragments(yaml.safe_load(...), BUILTIN_LOOPS_DIR)` in a `resolved`/`resolved_data` fixture (`scripts/tests/test_builtin_loops.py:516`, `:9462`, `:12544`, `:12806`). `TestWorkflowGeneratorLoop`'s current `data` fixture (line 17717) reads raw YAML only — if the new gates are `fragment:` references, extensions of `test_validation_gates_are_exit_code` (line 17810) and the matched-pair test (line 17854) must go through the resolved fixture (or read the fragment definition directly), because the raw state dict will no longer carry `action`/`action_type`/`evaluate`.
- The closest shell-action harness is now `TestCheckIntentScopeShellAction` (`scripts/tests/test_builtin_loops.py:18231`) — the FEAT-3332 class that executes the actual gate action against real temp git repos with `_init_repo`/`_run_init`/`_run_gate`/`_setup` helpers; it was itself cloned from `TestGeneralTaskFinalVerifySpinGateShellAction` (now at line 2999; the Tests citation below has been refreshed to match). New per-gate behavioral tests extend the FEAT-3332 class's helpers rather than re-cloning the general-task shape.
- Fence coverage is orthogonal to gate coverage and already accounted: `fence.py` (`scripts/little_loops/fsm/fence.py`) is the canonical authority for BUG-3327 fence text; `capture_intent` is this loop's only classified class-(1) fence site (`fence.py:76`) and `diagnose` carries FENCE_CORE's "write no file" clause inline. The four post-gate lowering prompt states interpolate no user-authored text (they read run_dir files), so they are not fence sites — this issue's gates are the only planned containment for them.
- Docs anchors, current: the "one-shot window" caveat to replace is limit #1 of "Five limits" in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:714-723` (it names FEAT-3335 explicitly); the wholesale `.loops/`/`.ll/` exclusion is limit #4 (line 735). The state-graph diagram to update is `docs/reference/loops.md:157-176`; that file's Context Variables table (lines 147-153) also omits `max_intent_retries` — a pre-existing gap adjacent to the edit, not caused by it.
- `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml` currently passes clean (27 states, max_steps 45) — the no-new-WARNING-categories AC baselines against `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow` (`scripts/tests/test_builtin_loops.py:16221`, class at 16119; both resolve).

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

## Status

**Open** | Created: 2026-08-26 | Priority: P4


## Session Log
- `/ll:decide-issue` - 2026-08-28T23:33:08 - `9f949531-f7bd-43e0-816a-3a64d73b2bba.jsonl`
- `/ll:refine-issue` - 2026-08-28T23:25:14 - `425908b6-e1d5-4f67-8fd1-7db76f87cdd4.jsonl`
- `/ll:format-issue` - 2026-08-28T23:13:29 - `425908b6-e1d5-4f67-8fd1-7db76f87cdd4.jsonl`
