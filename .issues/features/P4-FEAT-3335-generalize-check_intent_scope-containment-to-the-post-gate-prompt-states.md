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

## Current Behavior

Assuming FEAT-3332 has landed: exactly one containment assertion exists, between
`validate_intent` and `sketch_state_graph`. Every prompt state after it is
unaudited. A stray write from `sketch_state_graph` onward is as invisible as the
original incident was.

`diagnose` is the one post-gate prompt state FEAT-3332 already handles — it gets
BUG-3327's no-stray-writes fence clause there (requirement (j)), because
FEAT-3332 creates the `on_no` edge into it. That is a fence, not a gate: nothing
checks whether `diagnose` complied.

## Expected Behavior

Containment is asserted across the whole pipeline, not just its first window,
without multiplying near-duplicate state definitions.

Two open design questions this issue must settle before implementing:

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
  (class at line 2996)
- A `promote` / `loops_dir` case: a legitimate write to `${context.loops_dir}`
  under `auto_promote: true` must **not** trip the gate. This is the regression
  the deferred requirement (h) exists to prevent.
- `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  — watch for new WARNING categories from the added states

### Documentation
- Both files above

### Configuration
- N/A

## Program Design

### Signatures

- To be determined by the design question above — either N additional
  `check_*_scope() -> int` shell states, or one parameterized fragment re-entered
  at N points.

### Call Path

To be determined. The insertion candidates, in pipeline order after
FEAT-3332's gate: `sketch_state_graph`, `attach_evaluators`, `resolve_routing`,
`emit_artifact`, `shrink`, `promote`.

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
whatever picks this up. ~~Blocked on FEAT-3332 landing~~ — **FEAT-3332 is done
(confirmed 2026-08-28), so this issue is unblocked**; it reuses FEAT-3332's
gate body, baseline mechanics, and escape paths, all now in the tree.

Original incident: `postmortems/workflow-generator-output-json-gate-gap.md`
§4, §5 R5.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P4
