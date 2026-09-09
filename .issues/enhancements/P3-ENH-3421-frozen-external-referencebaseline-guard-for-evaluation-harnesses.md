---
id: ENH-3421
type: ENH
title: Frozen external reference/baseline guard for evaluation harnesses
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:49:43Z'
labels:
- harness
- evaluation
- statistics
relates_to:
- ENH-3415
program_design_not_applicable: true
decision_needed: true
---

# ENH-3421: Frozen external reference/baseline guard for evaluation harnesses

## Summary

Companion guard to ENH-3415's n-sample redundancy: a candidate should be tested against both
the incumbent and an unchanged frozen external reference/baseline, not just its immediate
parent — otherwise a lineage of promotions can drift into a self-referential local optimum
where every generation only beats the one before it, never an outside bar. ENH-3415's
Summary calls this out as a second mandatory-structure guard from evolutionary-search
harnesses, explicitly deferred as its own issue rather than folded into that one.

This is a stub: scope, the harness(es) it applies to, and what "frozen" means operationally
(a pinned commit? a pinned model? a pinned eval set?) are all open and need research before
this is implementation-ready.

## Current Behavior

No frozen external reference/baseline guard exists in `ll-harness` or any other little-loops
evaluation harness today (confirmed by ENH-3415's own codebase research, 2026-09-09: nothing
in `.issues/` described this before ENH-3415 filed it).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed by direct read of `cli/harness.py`: `ll-harness` itself has no incumbent/candidate concept anywhere — `HarnessEvalOutcome`, `_grade()`, and the ENH-3415 `_run_sample_loop()`/`SampleTally` tally only *this invocation's* samples; `_read_target_history()` (`cli/harness.py:1136`) prints a cross-invocation historical pass-rate line for display only — it never feeds `passed`/`verdict`/exit code. Any "did this beat something" decision is made one layer up, by whatever FSM loop calls `ll-harness`.
- Two existing FSM-level mechanisms already compare a candidate to *something*, but neither is frozen: (1) `harness-optimize.yaml`'s `convergence` gate (`evaluate_convergence()`, `fsm/evaluators.py:438`) compares each candidate only to `prev_score`, which the loop's own `capture_prev` state overwrites with the just-accepted candidate's score every iteration — `evaluate_convergence`'s signature (`current, previous, target, tolerance, direction`) has no fourth "frozen" input, so there is nowhere to plug an unchanging reference in today. (2) `evaluate_comparator()` (`fsm/evaluators.py:1604`) already reads a persisted `.loops/baselines/<loop>/output.txt` file that *can* stay genuinely frozen (`auto_promote: false` + manual `ll-loop promote-baseline`), but with the default `auto_promote: true` it is overwritten with the winning candidate's output on every "yes" verdict — the same rolling-drift shape as `prev_score`, via a different mechanism. `check_comparator` is also not wired into `harness-optimize.yaml`'s gate at all today; it is used by other loops (e.g. `harness-single-shot.yaml`) for whole-loop regression checks.
- Repo-wide search for "incumbent" or "frozen" (as an evaluation-baseline concept) found zero hits outside ENH-3415/ENH-3421's own issue text — confirms no prior art or naming convention exists to reuse.

## Expected Behavior

`harness-optimize.yaml` (and any confirmed sibling `convergence_gate` loop, see Scope
Boundaries' Codebase Research Findings) gates each accepted candidate against both its
immediate parent (the existing `prev_score`/`convergence` comparison) and a reference that
does not advance across iterations — closing the gap this issue's Summary describes, where
today `prev_score` is reseeded from the winning candidate every cycle (`capture_prev`) and the
codebase's only existing frozen-capable comparison mechanism (`evaluate_comparator`'s
`auto_promote: false` baseline file) is not wired into that loop's gate at all. Two viable
mechanical shapes for this, grounded in what already exists, are laid out under Proposed
Solution.

## Scope Boundaries

- **In scope**: the research/refine pass itself — determining which harness(es) (`ll-harness` at minimum, per ENH-3415's companion framing) need a frozen external reference guard, and what "frozen" means operationally for each (pinned commit, pinned model, pinned eval set).
- **Out of scope**: implementing the guard mechanism — this issue is a stub; implementation is a follow-up once scope is resolved. Any change to ENH-3415's n-sample redundancy guard — the two are companions, not the same mechanism.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed candidate: `harness-optimize.yaml` is the one loop in the codebase confirmed to exhibit the drift risk this issue describes — it populates `convergence_gate`'s `evaluate.previous` with a rolling `prev_score` that advances every accepted iteration. Other `convergence_gate` consumers (`agent-eval-improve.yaml`, `rl-policy.yaml`) do **not** populate `evaluate.previous` at all — they compare only against a fixed target, not a rolling prior score — so they do not currently exhibit this drift shape and are not confirmed in-scope. `rl-coding-agent.yaml` and `test-coverage-improvement.yaml` also use the `convergence_gate` fragment; whether they populate `evaluate.previous` with a rolling value was not confirmed either way and needs a direct check before scoping them in or out.

## Proposed Solution

**Option A**: Add a frozen-reference input to the `convergence` evaluator itself — a new
`EvaluateConfig` field that `evaluate_convergence()` (`fsm/evaluators.py:438`) checks alongside
`previous`, seeded once from `baseline_score`'s captured output and never reassigned by
`capture_prev`. Keeps the guard inside the numeric mechanism `harness-optimize.yaml` already
runs every iteration.

**Option B**: Wire the existing `check_comparator` evaluator (`evaluate_comparator()`,
`fsm/evaluators.py:1604`) into `harness-optimize.yaml`'s per-iteration `gate` state as a second,
required check alongside `convergence`, with `auto_promote: false` enforced so
`.loops/baselines/<loop>/output.txt` stays genuinely frozen between manual
`ll-loop promote-baseline` runs. Reuses a mechanism that already has frozen semantics, at the
cost of an LLM-judged blind A/B (`min_pairs`) on every iteration instead of a numeric
comparison.

**Recommended**: Option A for `harness-optimize.yaml` and its `convergence_gate`-family loops —
it keeps the guard numeric and cheap, matching the per-iteration scorer these loops already run,
and it closes the exact gap found (no frozen slot in `evaluate_convergence`'s current signature)
without requiring loop authors to adopt a second, differently-shaped evaluator. Option B remains
the better fit for `harness-single-shot.yaml`-style whole-loop regression checks, where it is
already used today.

## Integration Map

### Files to Modify (candidate — scope not yet decided, see Option A/B above)
- Option A: `scripts/little_loops/fsm/schema.py` (`EvaluateConfig`, ~line 133) — new
  frozen-reference field; `scripts/little_loops/fsm/evaluators.py:438`
  (`evaluate_convergence`) — accept and check it; `scripts/little_loops/loops/lib/common.yaml`
  (`convergence_gate` fragment, ~151-162) — thread the new field through; `harness-optimize.yaml`
  — populate it once from `baseline_score`, stop discarding it in `capture_prev`.
- Option B: `scripts/little_loops/loops/harness-optimize.yaml`'s `gate` state — add a second
  `check_comparator` evaluator entry with `auto_promote: false`.

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestComparatorEvaluator` (line 2357) and the
  `evaluate_convergence` call sites (lines 453-500) cover whichever evaluator the chosen option
  extends.
- `scripts/tests/test_harness_optimize.py` — rubric/behavior tests for the loop itself.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — already hosts the MR-1..MR-14 design-rule table
  and baseline semantics (MR-2); natural home for the new rule.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — documents the existing `--baseline` vs.
  `check_comparator` distinction this guard sits beside.

### Related Issues (context, not this issue's scope)
- `ENH-1122` (deferred) — a *different* "frozen" concept (byte-region edit-mutation guard for
  `harness-optimize`'s own file edits) — do not conflate with this issue's frozen-evaluation-
  reference concept.
- `ENH-1793`/`ENH-1828`/`ENH-1829` (done) — existing comparator-evaluator-core and
  baseline-lifecycle CLI; the mechanism Option B would reuse.

## Impact

- **Priority**: P3 - matches the filed priority; not user-visible until scoped, and only becomes urgent if an evolutionary-search harness is observed drifting into a self-referential local optimum in practice.
- **Effort**: Small - the issue itself is scoped as a research/refine pass only (see Scope Boundaries); implementation effort is unknown until that pass determines which harness(es) and what "frozen" means.
- **Risk**: Low - no code changes ship from this issue as filed; it only produces a scoping decision.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-09 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-09T14:08:38 - `1658f0c5-d510-42b4-beb1-234626dbd6e5.jsonl`
- `/ll:format-issue` - 2026-09-09T13:23:21 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
