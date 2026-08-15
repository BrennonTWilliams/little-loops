---
id: ENH-3200
title: verify-issue-loop criteria mode short-circuits on first failure; evaluate all
  criteria and report every failure
type: ENH
priority: P3
status: open
testable: true
discovered_date: '2026-08-15'
labels:
- verification
- fsm
confidence_score: 95
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

## Summary

`verify-issue-loop` criteria mode builds one FSM state per acceptance criterion, chained linearly, with every state routing `on_no`/`on_partial` straight to the `failed` terminal (`cli/loop/scaffold_verify.py:58-87`). So a run stops at the **first** failing criterion. For an issue with eight criteria where three fail, you learn about one, fix it, rerun, learn about the next, and pay a full N-state verification run each time.

Change the chain so every criterion is evaluated, outcomes accumulate, and a single aggregate terminal state reports which criteria failed.

## History

This issue originally proposed a fixed-format multi-check output block — one judge pass emitting N individually parseable verdicts — split out of ENH-3185's AC2. That framing was replaced on review, for two reasons:

1. **Its stated benefit already exists.** The multi-check block was motivated by per-check attribution ("check 3's failure is attributable to criterion 3"). The current per-state chain already delivers that, and more reliably: each criterion gets its own *named* FSM state, so attribution is structural rather than parsed. There is no misattribution failure mode to fix because there is no parser.
2. **It traded away the thing the loop exists for.** Each criterion state today is a full `action_type="prompt"` investigation — *"Inspect the implementation, run any commands needed, and gather concrete evidence"* — followed by its own `llm_structured` eval. Collapsing N criteria into one pass splits a single investigation's evidence budget N ways. For an 8-criterion issue that is roughly an eighth of the attention per criterion, and thinner evidence is exactly what produces more abstentions once ENH-3185 lands. Verification rigor is the point of this loop; spending it to save invocations is the wrong trade, especially since the original issue explicitly disclaimed cost reduction as a success criterion.

What survived review is the genuine deficiency the multi-check framing had bundled with it: the short-circuit. That is separable from the single-pass rearchitecture, and this issue now covers only it. No new output contract, no new parser, no change to how deeply any one criterion is verified.

If invocation cost later becomes the actual driver, the single-pass block is still available as a separate proposal — but it should be motivated by cost, with the depth-per-criterion regression priced in.

## Current Behavior

`_criteria_states()` (`cli/loop/scaffold_verify.py:58-87`) emits, for each criterion:

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
- `_adversarial_states()` (lines 129-172) has the same shape across its three probe states, with the same consequence.

## Expected Behavior

Every criterion is evaluated on every run, regardless of earlier outcomes. Each criterion's verdict is recorded. The chain ends at an aggregate state that reports the full picture — which criteria passed, which failed, which (post-ENH-3185) were abstained on — and terminates with `failure=True` if any criterion did not pass.

Attribution stays structural: states keep their `verify-criterion-N` names, so a failure still names its criterion without any parsing.

One run tells you everything that is wrong.

## Open Decisions

Resolve before implementing.

1. **How does a criterion's verdict reach the aggregate state?** This is the only non-trivial part. `state.capture` populates `self.captured[key]` with `{"output", "stderr", "exit_code", "duration_ms", "failure_type"}` (`fsm/executor.py:2313-2325`) — **the evaluator verdict is not among them**, so `${captured.verify-criterion-3.verdict}` does not resolve today. Options:
   - **(a) Add `verdict` to the capture dict.** Smallest change, and generally useful beyond this issue — any loop wanting to branch on a prior state's verdict currently cannot. Needs care that it does not collide with the existing `failure_type` key's meaning, and that states with no evaluator write an empty/absent value rather than a misleading one.
   - **(b) Have each criterion state write a line to `${context.run_dir}/criteria-results.jsonl`** via a shell action, and have the aggregate state read the file. No executor change, but adds a state per criterion and puts loop-generated artifacts in the run dir (consistent with the meta-loop artifact-isolation rule, but heavier).
   - (a) is the recommendation; (b) is the fallback if adding a capture key proves contentious.
2. **Does `on_partial` still count as failure?** Today it routes to `failed` alongside `on_no`. Preserving that is the conservative default and is what this issue assumes, but with per-criterion reporting it becomes visible enough to reconsider separately.
3. **Same treatment for `_adversarial_states()`?** The three probe states have the same short-circuit. Fixing both together is cheap and consistent; fixing only criteria mode is defensible since the probes are fewer and less independent. Pick one explicitly rather than leaving adversarial mode half-changed.

## Acceptance Criteria

- **AC1.** A criteria-mode loop with N criteria evaluates all N on a single run, including criteria that follow a failing one. Test: a generated loop with 3 criteria where criterion 1 fails still reaches and evaluates criteria 2 and 3.
- **AC2.** Each criterion's outcome is recorded and available to the aggregate state, by whichever mechanism Open Decision #1 selects.
- **AC3.** The chain ends at an aggregate terminal state that names every criterion that did not pass. A run with 3 failures reports 3, not 1.
- **AC4.** The aggregate state terminates with `failure=True` if any criterion did not pass, and `failure=False` only if all passed — so the loop's exit status is unchanged from today's semantics for both the all-pass and any-fail cases.
- **AC5.** Attribution remains structural: criterion states keep their `verify-criterion-N` names and one-state-per-criterion shape. No parser is introduced, and no criterion's verdict is derived from another's.
- **AC6.** Per-criterion investigation depth is unchanged — each criterion keeps its own `action_type="prompt"` action and its own `llm_structured` evaluation. This issue does not merge investigations.
- **AC7.** Existing generated loop YAMLs on disk keep working. They are self-contained, so only regeneration produces the new shape; a test asserts an old-shape loop (with `on_no: failed`) still validates and runs.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/scaffold_verify.py` — `_criteria_states()` (lines 58-87) is the whole change surface for AC1-AC5: reroute `on_no`/`on_partial` to the next criterion rather than `failed`, add the aggregate terminal state, and add whatever capture declaration Open Decision #1 settles on. The module docstring example (lines ~45-55) shows `on_no: failed` and must be updated to match. `_adversarial_states()` (lines 129-172) per Open Decision #3.
- `scripts/little_loops/fsm/executor.py` — only if Open Decision #1 resolves to (a): the capture dict at lines 2313-2325 gains a `verdict` key.
- `skills/verify-issue-loop/templates.md` — documents the fixed generated shape (`_PROBES` is annotated "verbatim per skills/verify-issue-loop/templates.md's fixed 3-probe template"), so the template and the generator must not drift.

### Tests
- `scripts/tests/test_verify_issue_loop.py` — existing coverage of the generated shape; AC1/AC3/AC7 land here.
- `scripts/tests/test_fsm_executor.py` — capture-dict coverage if Open Decision #1 resolves to (a).

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
- **Effort**: Small — a routing change plus an aggregate state in one generator function, and (probably) one key added to the executor's capture dict. Materially smaller than the Medium estimate the previous framing carried, since the parser, the output contract, and the `_criteria_states()` rewrite all disappear.
- **Risk**: Low — down from Medium. The previous framing's main risk was misattribution from an off-by-one in block parsing, reporting a confident and specific wrong result; with states staying named and one-per-criterion, that failure mode does not exist. Residual risk is that the aggregate state's `failure=True` derivation is wrong, which AC4 covers directly and which fails loudly rather than silently.
- **Breaking Change**: No — down from Yes. Existing loop YAMLs on disk are self-contained and keep working (AC7); only newly generated loops have the new shape, and their pass/fail exit semantics are unchanged (AC4).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 95/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 78/100 → MODERATE

### Gaps to Address
- `## Program Design` section is missing entirely (`ll-issues check-design ENH-3200` fails; `ll-issues format-check` lists `Program Design` under `missing`). The project's Program Design gate is armed (`.ll/program-design-cutover.json`, cutover 2026-07-30, predating this issue's 2026-08-15 filing date, so it is not grandfathered) and the issue carries no `program_design_not_applicable: true`. Add a `## Program Design` section with the concrete types/signatures/call path for the `_criteria_states()` rewrite and the chosen capture-dict change (run `/ll:refine-issue` or `/ll:reconcile-issue`), or mark the issue `program_design_not_applicable: true` if judged genuinely trivial.
- Open Decision #3 (whether `_adversarial_states()` gets the same no-short-circuit treatment) has no stated default or lean, unlike Decisions #1 and #2 which each carry an explicit recommendation/assumed default — pick one explicitly before implementation to avoid a half-changed adversarial mode.

## Session Log
- Split from ENH-3185 - 2026-08-15
- Pre-implementation review - 2026-08-15 - replaced the single-pass multi-check-block framing with the no-short-circuit fix; rationale recorded in History. Effort Small (was Medium), Risk Low (was Medium), no longer a breaking change, hard `depends_on: ENH-3185` removed.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
