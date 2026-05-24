---
captured_at: '2026-05-24T13:15:53Z'
completed_at: '2026-05-24T21:02:22Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: done
depends_on:
- ENH-1658
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1676: Add partial DoD satisfaction threshold to loop contracts

## Summary

Add `min_pass_rate` and `hard_criteria_tags` fields to the loop contract schema so that `check_done`-style evaluators can route to `done` when all hard criteria are met and the overall pass rate exceeds a configurable threshold — rather than requiring 100% satisfaction of every criterion including those that involve human decisions or pre-existing environmental conditions.

## Current Behavior

The `check_done` evaluator in `general-task.yaml` requires 100% satisfaction of all DoD criteria before routing to `done`. When any criterion — including human-decision criteria like "Working tree is clean" — remains unchecked, the loop cannot terminate even if all substantive technical work is complete. This creates circular dependencies where the loop stalls indefinitely on criteria outside the agent's control.

## Motivation

The `general-task` loop's `check_done` evaluator demands 100% DoD criterion satisfaction. In the audit of run `2026-05-24T093122`, criterion "Working tree is clean" created a circular dependency: it can only be satisfied by a human deciding whether to commit or discard pre-existing artifacts unrelated to the task. The loop could not terminate `done` even though all substantive work was complete. A configurable threshold with hard/soft criterion distinction would let loops reach `done` while leaving documented non-blocking criteria to the operator.

## Expected Behavior

Loop YAML gains two optional contract fields:

```yaml
context:
  min_pass_rate: 0.95
  hard_criteria_tags: ["code", "render", "verify"]
```

The `check_done` evaluator prompt (and its LLM evaluator) is updated to:
- Require **all hard criteria** (tagged with any label in `hard_criteria_tags`) to be `[x]`
- Require overall pass rate ≥ `min_pass_rate` across all criteria
- Route `on_yes` when both conditions hold (instead of requiring 100%)
- Log which soft criteria remain `[ ]` and why they are non-blocking

## Proposed Solution

**Decision: Option A — Loop-level context fields + evaluator parameterization**

Option A is selected. Option B (contract-level schema fields) is out of scope for this issue.

1. The loop YAML exposes `min_pass_rate` and `hard_criteria_tags` in `context:`.
2. The evaluator (LLM prompt or shell counter, depending on whether ENH-1658 has landed) interpolates these values.
3. The evaluator applies the two-tier check instead of requiring 100%.

This requires only loop YAML and evaluator changes — no executor or JSON schema changes.

**ENH-1658 interaction**: If ENH-1658 lands first (replacing the `check_done` LLM evaluator with a shell counter), Option A still applies — the context fields remain in `context:` and the shell counter script is parameterized instead of the LLM prompt. The spirit of Option A (no framework schema changes) is preserved either way.

## Implementation Steps

1. Add `min_pass_rate: 0.95` and `hard_criteria_tags: ["code", "render", "verify"]` to the `context:` block in `scripts/little_loops/loops/general-task.yaml`.
2. Update the `check_done` evaluator prompt to incorporate the two-tier check:
   - Parse any DoD criterion that carries a tag matching `hard_criteria_tags` as a hard criterion.
   - Count total criteria and checked criteria; compute pass rate.
   - Route YES only if all hard criteria are `[x]` **and** pass rate ≥ `min_pass_rate`.
   - When routing NO, distinguish "hard criterion unmet" from "soft criterion unmet — non-blocking".
3. Add a `## Non-blocking Criteria` section convention to the DoD template in `define_done`'s action prompt so loop authors can explicitly tag soft criteria upfront.
4. Update `skills/create-loop/loop-types.md` to document the threshold pattern for harness loops.
5. (Optional) Add `contract.min_pass_rate` and `contract.hard_criteria_tags` as first-class fields to `fsm-loop-schema.json` for future loops.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_general_task_loop.py::TestCountDoneShellScript` — adapt `test_all_done_emits_total_zero` and `test_unchecked_criterion_emits_nonzero_total` to reference `hard_unchecked_dod`/`soft_unchecked_dod` instead of `unchecked_dod`; update `test_failed_sample_emits_nonzero_total` if `total` is redefined
7. Add `test_context_has_min_pass_rate_and_hard_criteria_tags` to `test_general_task_loop.py` — assert both keys present in `raw_data["context"]`; follow `test_context_thresholds_defined` pattern from `scripts/tests/test_builtin_loops.py`
8. Add new `TestCountDoneShellScript` methods with `[hard]`-tagged DoD fixture strings — use existing `_load_count_done_script()` / `_bash()` / `_setup_dod_plan()` helpers; cover three scenarios: all-hard-done, any-hard-unchecked, all-hard-done-with-soft-unchecked
9. Update `docs/guides/LOOPS_GUIDE.md:340` — replace verbatim JSON schema description with updated `hard_unchecked_dod`/`soft_unchecked_dod` fields and two-tier routing description; update line 332 if DoD template gains `[hard]` tag convention
10. Verify ENH-1681 sequencing — if ENH-1681 has already landed (reroutes `count_done.on_yes` to `final_verify`), reconcile that edge with ENH-1676's rewritten shell body in the same PR

## Scope Boundaries

- **In scope**: Adding `min_pass_rate` and `hard_criteria_tags` context fields to `general-task.yaml`; updating the `check_done` evaluator (LLM prompt or shell counter) to apply a two-tier hard/soft criterion check
- **Out of scope**: Modifying the FSM executor or JSON schema (Option B is explicitly excluded); changing behavior of any loop other than `general-task`; auto-tagging existing DoD criteria (loop authors must opt in by adding tags to their DoD template)

## Success Metrics

- A `general-task` loop run reaches `done` state when all hard-tagged criteria are `[x]` and overall pass rate ≥ `min_pass_rate`, even when soft criteria remain unchecked
- Loops that do not set `min_pass_rate` or `hard_criteria_tags` in context behave identically to current 100%-pass behavior (no regression)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add context fields + update `check_done` evaluator prompt
- `skills/create-loop/loop-types.md` — document threshold pattern

### Tests
- No executor or schema tests needed (Option A: loop YAML + evaluator changes only)
- Add an integration test or fixture that verifies the evaluator correctly applies the threshold when the DoD file has mixed hard/soft criteria

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py::TestCountDoneShellScript.test_all_done_emits_total_zero` — **update**: asserts `data["unchecked_dod"] == 0`; must be updated when `unchecked_dod` is split into `hard_unchecked_dod`/`soft_unchecked_dod` [Agent 3 finding]
- `scripts/tests/test_general_task_loop.py::TestCountDoneShellScript.test_unchecked_criterion_emits_nonzero_total` — **update**: asserts `data["unchecked_dod"] >= 1`; must be updated when field is split [Agent 3 finding]
- `scripts/tests/test_general_task_loop.py::TestCountDoneShellScript.test_failed_sample_emits_nonzero_total` — **update**: asserts `data["total"] >= 1`; may need update if `.total` is redefined to exclude soft criteria [Agent 3 finding]
- `scripts/tests/test_general_task_loop.py::TestChange7CountDoneShellGate.test_count_done_evaluate_path_is_total` — **conditional break**: breaks only if `.gate` design is chosen instead of redefining `.total`; safe if `.total` is preserved as the sole routing field [Agent 3 finding]
- New: `test_context_has_min_pass_rate_and_hard_criteria_tags` — assert both keys exist in `raw_data["context"]`; follow `test_context_thresholds_defined` pattern from `scripts/tests/test_builtin_loops.py` [Agent 3 finding]
- New: `TestCountDoneShellScript` methods with `[hard]`-tagged DoD fixtures — cover: (a) all-hard-done → `done`, (b) any-hard-unchecked → no, (c) all-hard-done-with-soft-unchecked → `done`; use `_load_count_done_script()` + `_bash()` + `_setup_dod_plan()` helper pattern [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add a note on partial DoD satisfaction for harness loops

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:340` — verbatim JSON schema description `{"unchecked_dod": N, "unchecked_plan": N, "failed_samples": N, "total": N}` must be updated to reflect `hard_unchecked_dod`/`soft_unchecked_dod` split and two-tier routing logic [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:332` — `define_done` step description should mention the `[hard]` tag convention for authors to mark hard vs. soft criteria [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/tests/test_general_task_loop.py` — extend `TestCountDoneShellScript` (~line 265) and `TestChange7CountDoneShellGate` (~line 146) with threshold-aware test scenarios

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/enhancements/P3-ENH-1681-add-final-verify-and-close-gate-to-general-task-loop.md` — **open conflict**: ENH-1681 reroutes `count_done.on_yes` from `done` to `final_verify`; ENH-1676 rewrites the `count_done` shell body — these changes overlap on the same state definition and will create a merge conflict; sequence ENH-1676 before ENH-1681, or co-land [Agent 2 finding]
- `.issues/enhancements/P3-ENH-1631-fsm-runtime-on-max-iterations-summary-hook.md` — **forward reference**: ENH-1631 (open) references old field names `{unchecked_dod, unchecked_plan, failed_samples}` at line 89; when ENH-1631 is implemented after ENH-1676, it must use `hard_unchecked_dod`/`soft_unchecked_dod` [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/apo-contrastive.yaml` `score_and_select` — `${context.quality_threshold}` interpolated into a prompt action string (integer threshold pattern)
- `scripts/little_loops/loops/prompt-regression-test.yaml` `report`/`update_baseline` — `${context.pass_threshold}` in a prompt string (0–100 integer, same shape as `min_pass_rate`)
- `scripts/little_loops/loops/rl-rlhf.yaml` `score` — `output_numeric` with `operator: ge` + integer target (closest evaluator shape if emitting a float pass-rate directly)
- `scripts/little_loops/loops/rl-coding-agent.yaml` `score` — `${context.reward_target}` inside `evaluate.target` for `convergence` type (confirms context interpolation in evaluate blocks works for numeric/convergence but **not** for `output_json`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**ENH-1658 dependency satisfied.** ENH-1658 status is `done` (completed 2026-05-24). The `check_done` LLM evaluator is already removed; `count_done` (shell counter) is the live gate today. The `check_done` state is now a write-only prompt that always routes unconditionally to `count_done`.

**Implementation target (Step 2 correction).** The shell script to extend lives in the `count_done` state, not `check_done`. Current `count_done` outputs:
```json
{"unchecked_dod": N, "unchecked_plan": N, "failed_samples": N, "total": N}
```
and routes `done` when `.total == 0`. ENH-1676 must split `unchecked_dod` into `hard_unchecked_dod` and `soft_unchecked_dod`, then apply a two-condition gate.

**`evaluate_output_json` constraint.** The evaluator compares a single JSON path against a single scalar target — no compound conditions. The shell script must pre-compute a composite scalar. Two viable approaches:
- Redefine `.total` as `hard_unchecked_dod + unchecked_plan + failed_samples` (soft DoD criteria excluded from the total), keeping the existing `evaluate.path: ".total", operator: eq, target: 0`
- Or emit a separate `.gate: 0` field when both threshold conditions hold and switch `evaluate.path` to `.gate`

**`hard_criteria_tags` list interpolation constraint.** `${context.hard_criteria_tags}` with a YAML sequence resolves in shell to the Python list string `"['code', 'render', 'verify']"` — not parseable by grep/awk. Two safe approaches:
- Store as pipe-delimited string: `hard_criteria_tags: "code|render|verify"` → `grep -E "(code|render|verify)"` in awk
- Rely on an inline `[hard]` tag per criterion (simpler awk, no YAML list needed): `- [ ] Deploy passes CI [hard]`

**Context interpolation confirmed.** `${context.min_pass_rate}` in a shell `action:` string resolves correctly via `scripts/little_loops/fsm/interpolation.py` `InterpolationContext.resolve()`. No Python schema changes needed — `FSMLoop.context` is `dict[str, Any]`.

**`define_done` prompt update required (Step 3).** The `define_done` action prompt currently writes untagged flat checkboxes under `## Verification Criteria`. For the shell script to distinguish hard vs. soft criteria, the prompt must instruct the model to use the chosen tag syntax (inline `[hard]` tag or a `## Hard Criteria` subsection) before `count_done` can count them. Step 3 must land alongside or before Step 2.

## Impact

- **Priority**: P3
- **Effort**: Small (Option A: prompt + YAML changes only)
- **Risk**: Low — purely additive; existing loops unaffected
- **Breaking Change**: No

## Labels

`fsm-loops`, `general-task`, `contracts`, `evaluator`

## Status

**Open** | Created: 2026-05-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-24, updated 2026-05-24): This issue's Option A (loop-level context fields + evaluator parameterization) targets the `check_done` evaluator. ENH-1658 removes the LLM evaluator, replacing it with a shell counter. **Decision (2026-05-24): Option A is the chosen path regardless.** If ENH-1658 lands first, the shell counter is parameterized with `min_pass_rate` and `hard_criteria_tags` from `context:` instead of the LLM prompt — same loop YAML contract, different evaluator target. Option B (framework schema changes) is excluded. `depends_on: [ENH-1658]` is retained to sequence the evaluator target correctly.

## Tradeoff Review Note

**Reviewed**: 2026-05-24 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
**Decision made (2026-05-24): Option A** — loop-level context fields with no framework schema changes. If ENH-1658 lands first, adapt Option A to parameterize the shell counter rather than the LLM prompt. Option B is excluded.

---

## Session Log
- `/ll:ready-issue` - 2026-05-24T20:50:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c45ae03d-5b5b-437f-b1fc-ade691acba64.jsonl`
- `/ll:wire-issue` - 2026-05-24T20:32:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b92c2500-75a5-45eb-9f0c-cb00ad0d148c.jsonl`
- `/ll:refine-issue` - 2026-05-24T20:23:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4127329-5a5e-420f-b172-2383e64684bd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T13:37:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c29e127-5f7b-421f-9734-c94217103bba.jsonl`
- `/ll:format-issue` - 2026-05-24T13:19:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/765fa3c6-1a05-4cb7-8170-c01366684b4e.jsonl`
- `/ll:capture-issue` - 2026-05-24T13:15:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bfd5e964-4cba-4f63-8354-255b3fbb9f18.jsonl`
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`
- `/ll:confidence-check` - 2026-05-24T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2d625aa-98a6-43f6-8465-069e31302f35.jsonl`
