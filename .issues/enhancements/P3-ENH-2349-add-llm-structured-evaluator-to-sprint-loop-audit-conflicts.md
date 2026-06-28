---
id: ENH-2349
title: Add llm_structured evaluator to sprint-build-and-validate audit_conflicts state
type: ENH
status: open
priority: P3
captured_at: '2026-06-27T21:16:24Z'
discovered_date: '2026-06-27'
discovered_by: capture-issue
labels:
- loops
- fsm
- sprint
- evaluators
relates_to:
- BUG-2347
depends_on:
- ENH-2342
confidence_score: 85
outcome_confidence: 71
score_complexity: 19
score_test_coverage: 18
score_ambiguity: 12
score_change_surface: 22
decision_needed: false
---

# ENH-2349: Add llm_structured evaluator to sprint-loop audit_conflicts state

## Summary

`sprint-build-and-validate.yaml` has **zero** `llm_structured` evaluators — all five gated
states rely on shell exit codes. The `audit_conflicts` state runs
`/ll:audit-issue-conflicts --auto` and unconditionally proceeds (`next: commit`), so any
non-zero or no-op outcome is treated as success. Add an `llm_structured` evaluator that
scores whether each reported conflict was actually addressed (issue files mutated, scope
merged, or explicit deferral noted) before committing.

## Motivation

Per `.claude/CLAUDE.md` § Loop Authoring (rubric audit), a loop with no LLM-judged measure
of its quality-bearing steps cannot detect rubric drift. In the audited run the conflict
audit did produce a real BUG-367/BUG-368 scope merge, but the FSM had no way to verify that
the audit's *output* matched its *claim* — it would have committed regardless.

This is the lowest-priority audit finding and is explicitly deferrable: it adds latency and
non-determinism and should land only after BUG-2346 and BUG-2347 let the loop complete a
real run. Note the meta-loop rule MR-1 (`.claude/CLAUDE.md`): an `llm_structured` evaluator
in a meta-loop must be paired with a non-LLM evaluator in the routing chain — pair this with
an `exit_code` / file-existence check rather than relying on the LLM grade alone.

## Current Behavior

```yaml
audit_conflicts:
  action_type: prompt
  action: |
    Read the sprint file .sprints/${captured.sprint_name.output}.yaml to get the issue list.
    Run `/ll:audit-issue-conflicts --auto` once for all sprint issues as a single grouped call.
  capture: conflict_result
  next: commit          # proceeds unconditionally
```

## Expected Behavior

`audit_conflicts` evaluates whether each reported conflict was addressed and routes a
below-threshold result to a retry / manual-review path rather than straight to `commit`,
while satisfying MR-1 (a non-LLM evaluator also present in the chain).

## Implementation Steps

1. In `scripts/little_loops/loops/sprint-build-and-validate.yaml`, modify the `audit_conflicts`
   state: remove `next: commit` and add an `evaluate:` block directly on the state. Use
   `source: "${captured.conflict_result.output}"` so the judge reads the already-captured
   audit output rather than the current action's stdout. Add `on_yes: commit`,
   `on_no: audit_conflicts_retry`, `on_partial: audit_conflicts_retry`, `on_error: commit`.
   The `ll_gate` fragment from `lib/common.yaml` (line 47) provides the `action_type: prompt`
   + `evaluate: {type: llm_structured}` boilerplate; either reference the fragment or add the
   evaluate block inline.

2. Add an `audit_conflicts_retry` state (prompt action that re-runs
   `/ll:audit-issue-conflicts --auto` after reviewing the prior output, capturing into
   `conflict_result`, routing `next: commit`).

3. MR-1 is already satisfied at the loop level — `_validate_meta_loop_evaluation()` in
   `scripts/little_loops/fsm/validation.py` performs a loop-wide scan (not per-state) and the
   loop already contains `exit_code` evaluators in `route_input`, `extract_sprint_issues`,
   `route_create`, and `run_sprint`. No extra non-LLM state is needed.

4. Note on `min_confidence`: per `scripts/little_loops/fsm/evaluators.py` and `schema.py`,
   `min_confidence` (default 0.5) only changes routing when combined with
   `uncertain_suffix: true` — without it, routing is driven solely by the `verdict` string
   from the LLM's JSON response. Setting `min_confidence: 0.7` documents intent but does not
   tighten routing on its own. The judge prompt wording is what controls verdict quality.

4b. Increment `max_steps` from 16 to 18 in the loop's top-level config to accommodate the
    2-step retry path without risk of mid-run truncation.

5. Run `ll-loop validate sprint-build-and-validate` (MR-1/MR-4 checks) and then
   `ll-loop diagnose-evaluators sprint-build-and-validate` to confirm the new evaluator has
   healthy Bernoulli variance `p*(1-p) ≥ 0.05` across ≥10 runs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Capture variable available**: `${captured.conflict_result.output}` holds the full text
  of Claude's `/ll:audit-issue-conflicts --auto` run. The evaluator's `source:` field accepts
  this reference because the capture is written before `_evaluate()` is called in
  `scripts/little_loops/fsm/executor.py`.
- **Self-referencing pattern**: `outer-loop-eval.yaml:generate_report` uses
  `source: "${captured.improvement_report.output}"` where `improvement_report` is the same
  state's own capture key — confirming self-reference works.
- **Routing fallback**: `_route()` in `executor.py` falls back from `on_no` to `on_error`
  when `on_no` is absent; always declare both explicitly.
- **`max_steps` impact**: Adding 2 new states (`audit_conflicts` evaluate path + retry)
  adds at most 2 extra steps per retry cycle. Increment `max_steps` to 18 — keeping 16
  risks truncating the retry path when `audit_conflicts` is reached late in the run,
  which would silently fall back to the same unconditional-commit behavior this issue fixes.
- **MR-1 classification**: `sprint-build-and-validate.yaml` is NOT classified as a meta-loop by `_is_meta_loop()` in `scripts/little_loops/fsm/validation.py` (lines 1107–1129) — it does not import `lib/benchmark.yaml` and none of its state actions match `_META_LOOP_ACTION_PATTERNS`. Therefore `_validate_meta_loop_evaluation()` never fires for this loop. Step 3's conclusion (no extra non-LLM state required) is correct but the reason is the loop isn't a meta-loop, not that existing `exit_code` states satisfy MR-1 pairing.
- **`on_error` semantics in `_route()`**: In `scripts/little_loops/fsm/executor.py`, `on_error` handles the `"error"` verdict (LLM evaluator crash — API timeout, malformed JSON). A `"no"` verdict routes to `on_no`; `on_error` is only a fallback for `"no"` when `on_no` is absent. Setting `on_error: commit` means evaluator crashes silently proceed to commit — the Confidence Check concern is valid; confirm intent before merging.
- **`next:` + `evaluate:` are mutually exclusive**: The executor checks `if state.next:` at line 1003 and returns directly, bypassing `_evaluate()`. The `next: commit` key must be removed entirely when adding the `evaluate:` block — do not leave both in the state.
- **Concrete YAML draft** for modified `audit_conflicts` + new `audit_conflicts_retry`:
  ```yaml
  audit_conflicts:
    action_type: prompt
    timeout: 300
    action: |
      Read the sprint file .sprints/${captured.sprint_name.output}.yaml to get the issue list.
      Run `/ll:audit-issue-conflicts --auto` once for all sprint issues as a single grouped call.
    capture: conflict_result
    evaluate:
      type: llm_structured
      source: "${captured.conflict_result.output}"
      prompt: |
        Did the conflict audit resolve or explicitly note every reported conflict?
        Answer YES if: all conflicts were addressed (issue files mutated, scopes merged,
        explicit deferral noted) OR no conflicts were found.
        Answer PARTIAL if some but not all conflicts were addressed.
        Answer NO if conflicts were reported and none were addressed, or the output is
        empty or clearly incomplete.
      min_confidence: 0.7
    on_yes: commit
    on_no: audit_conflicts_retry
    on_partial: audit_conflicts_retry
    on_error: commit    # intentional: evaluator crash ≠ bad audit output; grader failure is operational, not correctness-related

  audit_conflicts_retry:
    action_type: prompt
    timeout: 300
    action: |
      The previous conflict audit did not fully address all reported conflicts.
      Prior output: ${captured.conflict_result.output}
      Re-run `/ll:audit-issue-conflicts --auto` for the sprint issues in
      .sprints/${captured.sprint_name.output}.yaml.
    capture: conflict_result
    next: commit
  ```
- **Retry pattern alternatives**: The dominant codebase pattern for retry is `max_retries + on_retry_exhausted` inline on the failing state (used in `agent-eval-improve.yaml`, `harness-multi-item.yaml`, `general-task.yaml`). A named retry state (`audit_conflicts_retry`) is chosen here because `max_retries` re-runs the same action without the opportunity to review and address the prior output — the retry state's action can read `${captured.conflict_result.output}` and take corrective action. Closest named-retry precedent: `oracles/verify-confidence-scores.yaml` — `retry_confidence_check` state routes with `next:` to a `_final` guard rather than directly to the terminal, but the simpler `audit_conflicts_retry → next: commit` is intentional since a second conflict audit is not worth a third-pass guard.
- **Judge prompt and ENH-2342**: `CHECK_SEMANTIC_EVIDENCE_CONTRACT` does not yet exist in `evaluators.py` — ENH-2342 is not merged. The draft judge prompt above is safe to use now; avoid requiring verbatim evidence quotes since the coercion isn't in place. After ENH-2342 lands, tighten the prompt to reference `CHECK_SEMANTIC_EVIDENCE_CONTRACT` semantics.
- **`llm_gate` fragment location**: `scripts/little_loops/loops/lib/common.yaml` lines 47–59. Provides only `action_type: prompt` and `evaluate.type: llm_structured`; caller must supply `action`, `evaluate.prompt`, `on_yes`, `on_no`. The inline `evaluate:` block approach (as in the draft above) is simpler and avoids fragment merge ambiguity.

## Acceptance Criteria

- [ ] `audit_conflicts` has an `llm_structured` evaluator with a threshold and full routing.
- [ ] A below-threshold audit does not silently route to `commit`.
- [ ] MR-1 is satisfied (non-LLM evaluator paired in the chain); `ll-loop validate` passes.

## Impact

- **Priority**: P3 — low-priority quality improvement; explicitly deferrable until BUG-2346 and BUG-2347 are resolved
- **Effort**: Small — single YAML edit adding one `llm_structured` evaluator plus a retry/review state to `sprint-build-and-validate.yaml`
- **Risk**: Low — isolated to the `audit_conflicts` state; existing `exit_code` routing is unchanged; `ll-loop validate` will catch MR-1 violations before the loop can run
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding an `llm_structured` evaluator to the `audit_conflicts` state in `sprint-build-and-validate.yaml` only
- **Out of scope**: Adding LLM evaluators to other states in the sprint loop
- **Out of scope**: Modifying or replacing the existing `exit_code` evaluators in the loop
- **Out of scope**: Changing the behavior of `/ll:audit-issue-conflicts` itself
- **Out of scope**: Broader FSM refactoring beyond this single state addition

> **Dependency note**: ENH-2342 will globally coerce every `llm_structured` verdict to `"no"` when the LLM response contains no verbatim evidence — enforced in `evaluate_llm_structured()` in `evaluators.py`. The `audit_conflicts` judge prompt must be authored with awareness of this evidence contract, or the evaluator will return permanent `"no"` verdicts and spin the retry loop until `max_steps` is hit. Implement ENH-2342 first, then draft the judge prompt against `CHECK_SEMANTIC_EVIDENCE_CONTRACT` in `evaluators.py`.

## Integration Map

### Files to Modify
- `loops/sprint-build-and-validate.yaml` — add `llm_structured` evaluator and `on_no`/`on_error` routing to `audit_conflicts` state

### Dependent Files (Callers/Importers)
- N/A — loop YAML is invoked directly via `ll-loop run sprint-build-and-validate`

### Similar Patterns
- `scripts/little_loops/loops/outer-loop-eval.yaml` in `generate_report` — `slash_command` + `llm_structured` with `source: "${captured.improvement_report.output}"` (self-referencing capture), `min_confidence: 0.7`, full four-route table; closest structural match to `audit_conflicts`
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` in `check-quality` — `prompt` + `llm_structured` (no `source:`), grades its own output, full four-route table; demonstrates the `ll_gate` fragment pattern
- `scripts/little_loops/loops/loop-specialist-eval.yaml` in `check_skill` — `prompt` + `llm_structured` with `source:` and `min_confidence: 0.7`, multi-condition judge prompt; reference for scoring structured audit output
- `scripts/little_loops/loops/eval-driven-development.yaml` in `route_eval` — action-less pure-router state with `llm_structured` and `source:` from prior state's capture
- `scripts/little_loops/loops/lib/common.yaml` `llm_gate` fragment (line 47) — ready-made `action_type: prompt` + `evaluate: {type: llm_structured}` template; `audit_conflicts` could use `fragment: llm_gate`

### Tests
- N/A — loop YAML changes are validated via `ll-loop validate sprint-build-and-validate` and `ll-loop diagnose-evaluators sprint-build-and-validate` (no unit tests for loop YAML)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestSprintBuildAndValidateLoop` (class at line 3197), `test_required_states_exist` (line 3213): update to add `"audit_conflicts_retry"` to the required set [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — add to `TestSprintBuildAndValidateLoop`: new structural test methods: `test_audit_conflicts_uses_llm_structured_evaluator`, `test_audit_conflicts_on_yes_routes_to_commit`, `test_audit_conflicts_on_no_routes_to_retry`, `test_audit_conflicts_no_longer_uses_bare_next`, `test_audit_conflicts_retry_state_exists`, `test_max_steps_accommodates_retry_cycle` (asserts `data.get("max_steps", 0) >= 18`) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopOnBlockedCoverage.REQUIRED_ON_BLOCKED` (line 1502): add `("sprint-build-and-validate.yaml", "audit_conflicts", "<on_blocked_target>")` if the implementation defines an `on_blocked` handler on the new evaluator state [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` (line 1013): lists `sprint-build-and-validate.yaml` in `migration_targets`; calls `load_and_validate()` on the modified YAML automatically — no change required, but will surface any YAML schema violations introduced by the change [Agent 1 finding]

### Documentation
- N/A — no documentation update required for an internal loop evaluator addition

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — FSM flow diagram in the `sprint-build-and-validate` section: the direct `audit_conflicts → commit` edge becomes conditional; add the `audit_conflicts_retry` path [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — state reference table entry for `audit_conflicts` (line ~756): update description to document the `llm_structured` evaluator type and retry routing [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — notes block (line ~762): update `max_steps: 16` mention to `max_steps: 18` [Agent 2 finding]

### Configuration
- N/A

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_builtin_loops.py` — in `TestSprintBuildAndValidateLoop.test_required_states_exist`, add `"audit_conflicts_retry"` to the required set; add new structural test methods for the evaluator block and routing (see Tests subsection above)
7. Update `docs/guides/LOOPS_REFERENCE.md` — revise the `sprint-build-and-validate` FSM flow diagram and state reference table to reflect conditional routing from `audit_conflicts`; update `max_steps` note if incremented to 18
8. Optionally update `TestBuiltinLoopOnBlockedCoverage.REQUIRED_ON_BLOCKED` in `test_builtin_loops.py` (line 1502) if an `on_blocked` handler is added to the new `audit_conflicts` evaluate block

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-27_

**Readiness Score**: 85/100 → PROCEED _(at configured gate: 85)_
**Outcome Confidence**: 71/100

### Outcome Risk Factors
- **Evidence-contract provisional coupling**: judge prompt correctness is provisional on ENH-2342 (open, P2); without it avoid verbatim evidence requirements or risk permanent `no` verdicts once ENH-2342 lands — tighten the prompt after ENH-2342 merges
- ~~**`on_error: commit` unresolved decision**~~ ✅ **RESOLVED**: `on_error: commit` is intentional — an evaluator crash (API timeout, malformed JSON) is an operational failure, not a correctness failure; the conflict audit output is still valid and should not trigger a retry
- ~~**`max_steps: 16` uncommitted**~~ ✅ **RESOLVED**: increment to 18 — the retry path adds up to 2 extra steps; keeping 16 risks truncating the retry mid-run and silently falling back to unconditional-commit behavior

## Session Log
- `/ll:decide-issue` - 2026-06-28T03:08:05 - `b51169cf-6c2a-410b-8a70-484c629a0537.jsonl`
- `/ll:confidence-check` - 2026-06-27T00:00:00Z - `7175e719-365d-4750-a6bd-b4f54f678467.jsonl`
- `/ll:confidence-check` - 2026-06-27T00:00:00Z - `fcd085ed-5850-4ae2-ad7a-bf6eb0fdc293.jsonl`
- `/ll:wire-issue` - 2026-06-28T01:44:00 - `ab5fc155-764c-486f-833a-1ddc70cbb968.jsonl`
- `/ll:refine-issue` - 2026-06-28T01:35:03 - `6b436cf4-e677-490f-8251-57b34b0928fd.jsonl`
- `/ll:confidence-check` - 2026-06-27T00:00:00Z - `b9db3b68-d279-4338-89b2-02b0cdbcd159.jsonl`
- `/ll:refine-issue` - 2026-06-27T23:55:35 - `ca3a6d49-ed3c-4ce1-b89d-4d43df7442b1.jsonl`
- `/ll:confidence-check` - 2026-06-27T23:55:00Z - `5d604424-edea-410a-99e0-58cd77b7379c.jsonl`
- `/ll:format-issue` - 2026-06-27T23:44:12 - `eeed6b9a-de07-4597-8de0-bdc4a6ac5422.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:56 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:confidence-check` - 2026-06-27T22:00:00Z - `4db93a84-28af-46ec-8824-975ef1360e97.jsonl`
- `/ll:wire-issue` - 2026-06-27T21:41:27 - `b1ff643a-138f-45dd-be1d-f42546ce8905.jsonl`
- `/ll:refine-issue` - 2026-06-27T21:32:33 - `265ed482-e8e6-4a78-a5cf-d16f10ac38ee.jsonl`
- `/ll:format-issue` - 2026-06-27T21:21:09 - `d9d01f4a-6f9b-4201-87a6-de089e4470ef.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md
