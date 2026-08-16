---
id: ENH-3200
title: verify-issue-loop criteria mode short-circuits on first failure; evaluate all
  criteria and report every failure
type: ENH
priority: P3
status: done
testable: true
discovered_date: '2026-08-15'
completed_at: '2026-08-16T04:24:13Z'
labels:
- verification
- fsm
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

## Summary

`verify-issue-loop` criteria mode builds one FSM state per acceptance criterion, chained linearly, with every state routing `on_no`/`on_partial` straight to the `failed` terminal (`cli/loop/scaffold_verify.py:58-88`). So a run stops at the **first** failing criterion. For an issue with eight criteria where three fail, you learn about one, fix it, rerun, learn about the next, and pay a full N-state verification run each time.

Change the chain so every criterion is evaluated, outcomes accumulate, and a single aggregate terminal state reports which criteria failed.

## History

This issue originally proposed a fixed-format multi-check output block — one judge pass emitting N individually parseable verdicts — split out of ENH-3185's AC2. That framing was replaced on review, for two reasons:

1. **Its stated benefit already exists.** The multi-check block was motivated by per-check attribution ("check 3's failure is attributable to criterion 3"). The current per-state chain already delivers that, and more reliably: each criterion gets its own *named* FSM state, so attribution is structural rather than parsed. There is no misattribution failure mode to fix because there is no parser.
2. **It traded away the thing the loop exists for.** Each criterion state today is a full `action_type="prompt"` investigation — *"Inspect the implementation, run any commands needed, and gather concrete evidence"* — followed by its own `llm_structured` eval. Collapsing N criteria into one pass splits a single investigation's evidence budget N ways. For an 8-criterion issue that is roughly an eighth of the attention per criterion, and thinner evidence is exactly what produces more abstentions once ENH-3185 lands. Verification rigor is the point of this loop; spending it to save invocations is the wrong trade, especially since the original issue explicitly disclaimed cost reduction as a success criterion.

What survived review is the genuine deficiency the multi-check framing had bundled with it: the short-circuit. That is separable from the single-pass rearchitecture, and this issue now covers only it. No new output contract, no new parser, no change to how deeply any one criterion is verified.

If invocation cost later becomes the actual driver, the single-pass block is still available as a separate proposal — but it should be motivated by cost, with the depth-per-criterion regression priced in.

## Current Behavior

`_criteria_states()` (`cli/loop/scaffold_verify.py:58-88`) emits, for each criterion:

```python
states[slot.state_name] = StateConfig(
    action=action_text,
    action_type="prompt",
    timeout=_STATE_TIMEOUT,
    evaluate=EvaluateConfig(type="llm_structured", prompt=eval_prompt),
    on_yes=next_state,
    on_no="failed",
    on_partial="failed",
)
```

Both non-pass routes terminate. Consequences:

- Criteria after the first failure are never evaluated — their status is unknown, not passing.
- The run reports "failed" without a per-criterion summary; which criterion failed is recoverable only from the transition log.
- Discovering K failures costs K full runs, each re-verifying every criterion before the newest failure.
- `_adversarial_states()` (lines 130-173) has the same shape across its three probe states, with the same consequence.

## Expected Behavior

Every criterion is evaluated on every run, regardless of earlier outcomes. Each criterion's verdict is recorded. The chain ends at an aggregate state that reports the full picture — which criteria passed, which failed, which (post-ENH-3185) were abstained on — and terminates with `failure=True` if any criterion did not pass.

Attribution stays structural: states keep their `verify-criterion-N` names, so a failure still names its criterion without any parsing.

One run tells you everything that is wrong.

## Decisions (resolved 2026-08-15)

All three items below were originally open with stated leans; the leans are hereby adopted
as decisions so the implementer does not re-litigate: **#1 → option (a)** (add `verdict` to
the capture dict via a post-`_evaluate()` write-back, both capture sites), **#2 → yes**
(`on_partial` keeps counting as failure; reconsider separately once per-criterion reporting
makes it visible), **#3 → yes** (`_adversarial_states()` gets the same treatment in the
same change). The original analyses are retained below for the record.

1. **How does a criterion's verdict reach the aggregate state?** This is the only non-trivial part. `state.capture` populates `self.captured[key]` with `{"output", "stderr", "exit_code", "duration_ms", "failure_type"}` (`fsm/executor.py:2332-2353`) — **the evaluator verdict is not among them**, so `${captured.verify-criterion-3.verdict}` does not resolve today. Options:
   - **(a) Add `verdict` to the capture dict.** Still the recommendation, and generally useful beyond this issue — any loop wanting to branch on a prior state's verdict currently cannot. But it is **not** the one-key edit an earlier draft assumed, because of an ordering problem:
     - The capture dict is written at `executor.py:2333`, inside the **action-execution** path (`_run_action_or_route()`, called from `_execute_state()` at lines 1777 and 1846).
     - Evaluation happens **after**, at `executor.py:1856` (`eval_result = self._evaluate(state, action_result, ctx)`); routing at line 2060.

     So at the moment `self.captured[state.capture]` is built, **no verdict exists yet**. Option (a) therefore requires a *second write-back* that mutates the already-populated dict after `_evaluate()` returns — not a new key in an existing dict literal. Constraints on that write-back:
     - It must tolerate `state.capture` being unset (most states) and `_evaluate()` returning `None` (states with no evaluator) — writing an empty rather than misleading value, per the `failure_type` precedent.
     - There is a **second capture site** at `executor.py:1049/1056` (the nested child-executor path, which also writes `failure_terminal` at 1067). It needs the same treatment or `verdict` is silently absent for nested states.
     - It must not collide with the existing `failure_type` key, which carries a `classify_failure()` value, not an evaluator verdict.

     This does not change the recommendation — (a) is still right and still small — but it moves the executor change from trivial to a real edit with an ordering invariant, and it is why Effort is no longer rated Small.
   - **(b) Have each criterion state write a line to `${context.run_dir}/criteria-results.jsonl`** via a shell action, and have the aggregate state read the file. No executor change, but adds a state per criterion and puts loop-generated artifacts in the run dir (consistent with the meta-loop artifact-isolation rule, but heavier).
   - (a) is the recommendation; (b) is the fallback if adding a capture key proves contentious.
2. **Does `on_partial` still count as failure?** Today it routes to `failed` alongside `on_no`. Preserving that is the conservative default and is what this issue assumes, but with per-criterion reporting it becomes visible enough to reconsider separately.
3. **Same treatment for `_adversarial_states()`? — lean: yes, in the same change.** The three probe states have the same short-circuit. Fix both together. The probes are independent by construction (boundary / malformed / failure-mode are distinct attack classes with no ordering dependency), so the "less independent" argument for deferring does not hold — a malformed-input finding tells you nothing about whether boundary probes would also have found something. Fixing only criteria mode ships adversarial mode with the exact defect criteria mode just lost, in a generator the two modes share. The counter-argument (three states is small enough that K reruns is tolerable) is real but weak against the marginal cost, which is one more application of a routing change already written.

## Acceptance Criteria

- **AC1.** A criteria-mode loop with N criteria evaluates all N on a single run, including criteria that follow a failing one. Test: a generated loop with 3 criteria where criterion 1 fails still reaches and evaluates criteria 2 and 3.
- **AC2.** Each criterion's outcome is recorded and available to the aggregate state, by whichever mechanism Open Decision #1 selects.
- **AC3.** The chain ends at an aggregate terminal state that names every criterion that did not pass. A run with 3 failures reports 3, not 1.
- **AC4.** The aggregate state terminates with `failure=True` if any criterion did not pass, and `failure=False` only if all passed — so the loop's exit status is unchanged from today's semantics for both the all-pass and any-fail cases.
- **AC5.** Attribution remains structural: criterion states keep their `verify-criterion-N` names and one-state-per-criterion shape. No parser is introduced, and no criterion's verdict is derived from another's.
- **AC6.** Per-criterion investigation depth is unchanged — each criterion keeps its own `action_type="prompt"` action and its own `llm_structured` evaluation. This issue does not merge investigations.
- **AC7.** Existing generated loop YAMLs on disk keep working. They are self-contained, so only regeneration produces the new shape; a test asserts an old-shape loop (with `on_no: failed`) still validates and runs.
- **AC8 (added 2026-08-15 review — error/blocked verdicts must not short-circuit either).** The criterion states declare only `on_yes`/`on_no`/`on_partial` today, so an `error` or `blocked` verdict mid-chain hits `_route() → None` and terminates the whole run — the same short-circuit this issue removes, through a different verdict. Generated criterion states route `on_error`/`on_blocked` to the next criterion as well, with the outcome recorded and counted toward `failure=True` (per the unknown-counts-as-failure rule in Decision Rules). Test: a 3-criterion loop where criterion 1's evaluator returns `error` still evaluates criteria 2 and 3 and reports criterion 1 as not-passed. Side effect, accepted: routing `on_error` forward means a transient infra error (e.g. an API 429) is recorded as "criterion not-passed" instead of terminating/retrying — the aggregate should surface the captured `failure_type` alongside the verdict so infra faults stay distinguishable from genuine NOs.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/scaffold_verify.py` — `_criteria_states()` (lines 58-88) is the whole change surface for AC1-AC5: reroute `on_no`/`on_partial` to the next criterion rather than `failed`, add the aggregate terminal state, and add whatever capture declaration Open Decision #1 settles on. The module docstring example (lines 42-55) shows `on_no: failed` and must be updated to match. `_adversarial_states()` (lines 130-173) per Open Decision #3.
- `scripts/little_loops/fsm/executor.py` — only if Open Decision #1 resolves to (a). **Two** sites, not one, and the change is a post-evaluation write-back rather than a new key in the dict literal (the literal at lines 2332-2353 is built before `_evaluate()` runs at line 1856): the primary capture at line 2333, and the nested child-executor capture at lines 1049/1056/1067.
- Prose/doc sync inside `scaffold_verify.py` itself (`skills/verify-issue-loop/templates.md` is now a stub pointing at this module post-FEAT-2948 — there is no template there to keep in sync): the module docstring (lines 4-8) describing `on_no`/`on_partial` routed to a shared `failed` terminal; `PREPATCH_CHECK_STATE_EXAMPLE` (lines 42-55) showing `on_no: failed`; the generated criteria-mode description string (lines 233-234), which says "fails fast on any criterion that fails"; and optionally the stale `_PROBES` annotation (lines 91-92) that still cites templates.md.

### Tests
- `scripts/tests/test_verify_issue_loop.py` — existing coverage of the generated shape; AC1/AC3/AC7 land here.
- `scripts/tests/test_fsm_executor.py` — capture-dict coverage if Open Decision #1 resolves to (a).

## Program Design

### Types
- `CriterionSlot` (`issue_parser.py:1746`) — frozen-shaped dataclass with `index: int`, `source_text: str`, `state_name: str`. Already carries everything the aggregate state needs to name a failing criterion; no new field required. `state_name` is what keeps attribution structural per AC5.
- `StateConfig` (`fsm/schema.py`) — the per-state config the generator emits. The aggregate state is a **non-terminal evaluating state** that inspects the captured criterion verdicts and routes `on_yes → done` / `on_no → failed` (the existing terminals). It cannot be `terminal=True` with a "computed" `failure` value — `failure` is a static YAML bool fixed at generation time, so runtime derivation from verdicts requires an evaluating state in front of the terminals. No new type is introduced.
- The executor's capture dict is an untyped `dict[str, Any]` written into `self.captured[state.capture]` (`fsm/executor.py:2333`), currently carrying `output`, `stderr`, `exit_code`, `duration_ms`, `failure_type`, `timeout_kind`. Option (a) adds a `verdict` key; there is no dataclass to extend.

### Signatures
- `_criteria_states(criteria: list[CriterionSlot], issue_id: str) -> dict[str, StateConfig]` — `cli/loop/scaffold_verify.py:58`. Unchanged signature; the body changes what each state's `on_no`/`on_partial` point at and appends the aggregate state.
- `_adversarial_states(...) -> dict[str, StateConfig]` — `cli/loop/scaffold_verify.py:130`. Same change per Open Decision #3.
- `FSMExecutor._evaluate(self, state: StateConfig, action_result: ActionResult | None, ctx: InterpolationContext) -> EvaluationResult | None` — `fsm/executor.py:2532`. Not modified, but its return is the value the option-(a) write-back must fold into `self.captured`, and its `None` case is the one that must not write a misleading verdict.
- `FSMExecutor._run_action_or_route(...)` — `fsm/executor.py:3173`; contains the capture write at line 2333 that runs *before* `_evaluate()`.

### Call Path
`_criteria_states` -> `StateConfig` -> `_execute_state` -> `_run_action_or_route` (capture write, line 2333) -> `_evaluate` (line 1856) -> verdict write-back -> `_route` (line 2060) -> aggregate state

### Decision Rules
- **Routing.** Each criterion state's `on_no`/`on_partial` retarget from the `failed` terminal to the *next* criterion state (and the last criterion's to the aggregate state), so the chain always runs to completion. `on_yes` already points at `next_state` and is unchanged.
- **Aggregate failure derivation (AC4).** The aggregate state terminates `failure=True` if any captured criterion verdict is not `yes`, `failure=False` only if all are `yes`. Deriving from captured verdicts rather than from reaching a particular state is what preserves today's exit semantics while removing the short-circuit.
- **Unknown vs. failed.** A criterion whose verdict is absent from `captured` (state never ran, evaluator returned `None`) must be reported as unknown and counted toward `failure=True` — never silently as a pass. This is the one place the change could invert today's semantics if written carelessly.
- **Abstention (post-ENH-3185).** If `cannot_judge` exists when this lands, it is a third reported bucket and counts toward `failure=True` by default — matching ENH-3185's AC3 requirement that consumers handle abstention distinctly from failure without treating it as a pass.
- **Guarded interpolation.** The aggregate state's captured-verdict references must use the guarded idiom — `${captured.verify-criterion-N.verdict:default=...}` or the nullable `${...?}` form — per the unguarded-captured-refs lint (`fsm/validation/reachability.py:41`); a missing verdict then resolves safely (feeding the unknown-counts-as-failure rule above) instead of raising `InterpolationError`. Bare bash `:-` defaults are not an alternative: they trip MR-7 (`fsm/validation/shell_safety.py`).
- **Escape hatch (AC7).** No migration of existing loop YAMLs. They are self-contained, still validate, and still run with `on_no: failed`; only regeneration produces the new shape.

## Relationship to ENH-3185

No hard dependency in either direction; either can land first.

- If **this** lands first, the aggregate state reports pass/fail per criterion, and gains a third bucket for free once `cannot_judge` exists.
- If **ENH-3185** lands first, the aggregate state should record abstention as a distinct third outcome from the start rather than folding it into failure — which is the same distinction ENH-3185's AC3 requires of its other consumers.

Note that ENH-3185 changes what these states can emit (`on_cannot_judge`, falling back to `on_error`), so whichever lands second should confirm the criterion states route abstention somewhere sensible rather than into the aggregate as a silent pass.

## Scope Boundaries

Explicitly **out of scope**:

- **Single-pass multi-check judging.** Superseded framing — see History. Each criterion keeps its own investigation and its own judge invocation.
- **Any new output contract or block parser.** `parse_check_block()` and the `MultiCheckResult` type from the previous framing are not built.
- **Reducing invocation count.** N criteria still cost N investigations. Cost is not what this issue optimizes; if it becomes the driver, that is a separate proposal.
- **The abstention verdict itself** — ENH-3185.
- **Changing what any individual criterion means,** or how strictly it is judged.
- **Migrating existing generated loops.** AC7 keeps them working; regenerating is the user's choice.

## Impact

- **Priority**: P3 — nothing is incorrect today; the verdicts the loop produces are accurate as far as they go. The cost is workflow: K failures take K full runs to discover. Real friction, no correctness defect behind it.
- **Effort**: Small-to-Medium — a routing change plus an aggregate state in one generator function (small, and applied twice per Open Decision #3), plus the executor capture change, which is **not** the one-key edit first assumed: the capture dict is populated before evaluation runs, so `verdict` needs a post-`_evaluate()` write-back across two capture sites with `None`-evaluator handling (see Open Decision #1a). Still materially smaller than the Medium estimate the previous framing carried, since the parser, the output contract, and the `_criteria_states()` rewrite all disappear.
- **Risk**: Low — down from Medium. The previous framing's main risk was misattribution from an off-by-one in block parsing, reporting a confident and specific wrong result; with states staying named and one-per-criterion, that failure mode does not exist. Residual risk is that the aggregate state's `failure=True` derivation is wrong, which AC4 covers directly and which fails loudly rather than silently.
- **Breaking Change**: No — down from Yes. Existing loop YAMLs on disk are self-contained and keep working (AC7); only newly generated loops have the new shape, and their pass/fail exit semantics are unchanged (AC4).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 95/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 78/100 → MODERATE

### Gaps to Address

_Both gaps below were addressed in the 2026-08-15 second-pass review — a `## Program Design` section was added, and Open Decision #3 now carries an explicit lean. Retained for the record._

- `## Program Design` section is missing entirely (`ll-issues check-design ENH-3200` fails; `ll-issues format-check` lists `Program Design` under `missing`). The project's Program Design gate is armed (`.ll/program-design-cutover.json`, cutover 2026-07-30, predating this issue's 2026-08-15 filing date, so it is not grandfathered) and the issue carries no `program_design_not_applicable: true`. Add a `## Program Design` section with the concrete types/signatures/call path for the `_criteria_states()` rewrite and the chosen capture-dict change (run `/ll:refine-issue` or `/ll:reconcile-issue`), or mark the issue `program_design_not_applicable: true` if judged genuinely trivial.
- Open Decision #3 (whether `_adversarial_states()` gets the same no-short-circuit treatment) has no stated default or lean, unlike Decisions #1 and #2 which each carry an explicit recommendation/assumed default — pick one explicitly before implementation to avoid a half-changed adversarial mode.

## Resolution

Implemented per the Program Design: `_criteria_states()` and `_adversarial_states()`
(`cli/loop/scaffold_verify.py`) now route every verdict (`on_yes`/`on_no`/`on_partial`/
`on_error`/`on_blocked`) to the next state in the chain instead of short-circuiting to
a shared `failed`/`failed_with_finding` terminal. Each criterion/probe state declares
`capture: <state_name>`; a new `_aggregate_state()` helper emits a deterministic shell
state (`verify-aggregate` / `probe-aggregate`) that inspects every captured
`${captured.<key>.verdict:default=unknown}` (guarded, per the reachability lint) and
reports every state that did not pass, surfacing `failure_type` alongside a not-passed
verdict (AC8). `FSMExecutor._execute_state()` gained a post-`_evaluate()` write-back at
both capture sites (`executor.py`: the main action-execution path, and the nested
child-executor path) so `verdict` is available without disturbing the existing
`failure_type`/`output`/`exit_code` capture shape. AC7 (old-shape loops keep working)
required no migration — only the generator's new output changed shape.

Tests: `test_ll_loop_scaffold_verify.py` (structural no-short-circuit assertions plus an
end-to-end `TestAggregateExecutionEndToEnd` class that runs the generated chain through
a real `FSMExecutor` with a real bash subprocess for the aggregate state, covering
AC1/AC3/AC4/AC8) and `test_fsm_executor.py` (`TestCapture`/`TestSubLoopExecution`
additions covering the verdict write-back at both capture sites). Full suite:
19470 passed, 46 skipped (pre-existing, unrelated), 0 failed.

## Session Log
- `/ll:manage-issue` - 2026-08-16T04:23:17 - `953e8134-a0de-46ec-8da0-03d0781ca4b7.jsonl`
- `/ll:ready-issue` - 2026-08-16T03:40:55 - `f665b010-96f7-4727-9a39-205fdb545e7f.jsonl`
- `/ll:confidence-check` - 2026-08-16T00:17:33 - `64e9e21e-d2d6-44cd-97cd-d980a3cc037d.jsonl`
- Pre-implementation review (third pass) - 2026-08-15 - verified all cited executor/generator line refs against current code; corrected the Program Design aggregate-state shape (non-terminal evaluating state routing `on_yes → done` / `on_no → failed` — `failure` is a static YAML bool, so `terminal=True` with a computed value was unimplementable); replaced the stale `templates.md` Integration Map item with the real prose-sync targets inside `scaffold_verify.py` (module docstring 4-8, `PREPATCH_CHECK_STATE_EXAMPLE` 42-55, "fails fast" description string 232-233, `_PROBES` annotation 90-91); updated `CriterionSlot` ref 1722 → 1741 (drifted via 72fb87ea); added the guarded-interpolation Decision Rule (`:default=`/`?` refs, MR-7 trap) and the AC8 infra-error side-effect note (surface `failure_type` in the aggregate). Confirmed no decision remains open and MR-1..MR-6 meta-loop rules do not apply.
- Pre-implementation review (batch) - 2026-08-15 - formalized the three open decisions as resolved (capture write-back option (a); `on_partial` stays failure; adversarial mode fixed in the same change); added AC8: `error`/`blocked` verdicts must not short-circuit the chain either — criterion states gain `on_error`/`on_blocked` routes to the next criterion, outcome recorded and counted toward `failure=True`.
- `/ll:decide-issue` - 2026-08-15T22:32:38 - `1722f1f7-02d5-4af2-b8ec-39c8c40ec8ac.jsonl`
- Pre-implementation review (second pass) - 2026-08-15 - added the missing `## Program Design` section (confidence-check hard-override gap); gave Open Decision #3 an explicit lean (fix `_adversarial_states()` in the same change); documented the capture-ordering problem in Open Decision #1a — `self.captured` is written at `executor.py:2315` *before* `_evaluate()` runs at line 1850, so `verdict` needs a post-evaluation write-back across two capture sites, not a new dict key. Effort re-rated Small-to-Medium.
- `/ll:confidence-check` - 2026-08-15T20:36:25 - `94c0eb90-8c6b-4ad6-ab84-c1a6874ad15f.jsonl`
- Split from ENH-3185 - 2026-08-15
- Pre-implementation review - 2026-08-15 - replaced the single-pass multi-check-block framing with the no-short-circuit fix; rationale recorded in History. Effort Small (was Medium), Risk Low (was Medium), no longer a breaking change, hard `depends_on: ENH-3185` removed.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
