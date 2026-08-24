---
id: FEAT-3039
title: Advisor FSM stall escalation and routable verdicts
type: FEAT
parent: EPIC-3041
priority: P4
status: open
testable: true
discovered_date: 2026-08-03
depends_on:
- FEAT-3044
- FEAT-3120
- FEAT-3116
- FEAT-3117
- FEAT-3118
labels:
- planning-hub
verify_verdict: VALID
size: Very Large
confidence_score: 80
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
---

# FEAT-3039: Advisor FSM stall escalation and routable verdicts

## Summary

Slice 3 of the host-agnostic advisor (FEAT-3037). Let an FSM loop escalate to
the advisor when a stall evaluator fires, and make the consult verdict a
first-class routable evaluator output so a state can branch on
`recommendation` / `confidence` rather than only logging it.

## Current Behavior

- `evaluate_diff_stall`, `evaluate_score_stall`, `evaluate_action_stall`, and
  `evaluate_open_question_stall` (`fsm/evaluators.py`) all produce verdicts that
  a loop can route on today, but the only available responses are terminate,
  retry the same cheap model, or hand off.
- There is **no `on_stall` key in the FSM schema** — stall handling goes through
  the ordinary transition table. Any escalation must be expressed that way.
- After FEAT-3038 the advisor is reachable from hooks and the confidence gate,
  but not from inside a loop's state machine.
- `evaluate_llm_structured` returns a verdict + details; there is no evaluator
  whose output *is* an advisor consult.

## Expected Behavior

- A loop can declare a state that consults the advisor and routes on the
  verdict, reachable from any stall evaluator's `stall` branch through the
  normal transition table.
- A new `advisor_consult` evaluator type runs a consult and produces a routable
  verdict, with `confidence` available for threshold routing the same way
  `llm_structured` exposes its confidence today.
- The consult context includes the stuck-state context (recent action output,
  the stall evaluator's details) — assembled explicitly, never an auto-slurp.
- `ll-loop validate` accepts the new evaluator type and, per MR-1, does **not**
  flag an advisor consult as a substitute for a non-LLM signal — the stall
  evaluator that routes into it *is* the external signal.

## Use Case

A `refine-to-ready-issue` loop hits `score_stall` on its third iteration: the
readiness score has not improved. Rather than terminating or burning a fourth
identical Sonnet pass, the loop routes to an `advisor_consult` state. Opus sees
the stuck-state context and returns `recommendation: "the criteria prompt is
underspecified — the artifact is passing but the gate asks for evidence the
artifact format cannot carry"` with `confidence: 0.85`. The loop routes on that
verdict to a prompt-repair state instead of another refine iteration.

## Proposed Solution

Add `advisor_consult` alongside the existing evaluator types in
`fsm/evaluators.py` (registered in the dispatch `elif` chain where
`score_stall` and friends are wired — `score_stall` now at
`evaluators.py:1833`), delegating to `consult_for_trigger()` (FEAT-3116,
landed — `advisor.py:451`) — never calling
`little_loops.advisor.consult()` directly, per the exclusivity contract
settled 2026-08-23 (see Scope Boundary).

**Trigger gating (settled 2026-08-24)**: `consult_for_trigger()` gates on
`trigger in config.advisor.triggers` *and* passes the trigger through as the
consult signal. Deriving the trigger from the routing state's name would
force users to allowlist every state name in `advisor.triggers` and would
otherwise silently skip (`trigger_not_allowed` → neutral verdict). The
evaluator therefore always gates under the fixed trigger **`"loop_stall"`**
(already the example in config-schema's `triggers` description); the routing
state's name is carried in the assembled question/context and in
`EvaluationResult.details["state"]`, not as the trigger. The optional
`signal` config field overrides the trigger for advanced cases; whatever it
names must then appear in `advisor.triggers` or the consult skips.

**Verdict mapping (settled 2026-08-24)**: `AdvisorVerdict` carries only
free-text `recommendation` plus `confidence`/`risks`/`dissent` — there is no
closed-set field to map through `verdict_map`. The evaluator injects
`verdict_map`'s keys into the consult question as the allowed decision set
("Answer with exactly one `decision` from: proceed, revise, abort") and
parses the decision out of the structured response; `verdict_map` then maps
decision → FSM verdict. A response naming no known decision (or any parse
failure) falls back to the configured neutral verdict. Either way
`confidence` is surfaced in `details` for threshold routing, and a failed
consult never strands the loop.

**Per-state timeout (settled 2026-08-24)**: neither `consult_for_trigger()`
nor `consult()` accepts a timeout parameter — the timeout comes from
`config.advisor.timeout_seconds`. An optional per-state `timeout` is applied
by overriding `timeout_seconds` on a *copied* config object before the
`consult_for_trigger` call (the `cli/advise.py` direct-mutation pattern,
applied to a copy so the ambient config is untouched).

Budget and signal accounting flow through FEAT-3038's `should_consult` /
`record_consult`, so loop-driven consults count against the same per-task cap.

Determinism: consults stay excluded from the resume/replay input hash
(established in FEAT-3037), so a resumed run does not re-bill or re-consult.

## Program Design

### Types

- `AdvisorConsultConfig: {question: str, verdict_map: dict[str, str], signal: str | None (default "loop_stall"), timeout: int | None, context_from: list[str] | None}` — these five keys must land in `EvaluateConfig` and `fsm-loop-schema.json` together (lockstep test, see Tests)

### Signatures

- `evaluate_advisor_consult(output: str, *, question: str, verdict_map: dict[str, str], signal: str | None, timeout: int | None, context_from: list[str] | None, state_name: str) -> EvaluationResult`
- `_advisor_context(state_name: str, output: str, details: dict) -> str`

### Call Path

`FSM executor` -> evaluator dispatch (`eval_type == "advisor_consult"`) -> `evaluate_advisor_consult` -> `consult_for_trigger` (FEAT-3116; runs `should_consult` internally, then `little_loops.advisor.consult`) -> `EvaluationResult`

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/evaluators.py` — `evaluate_advisor_consult` + the
  two dispatch registration sites.
- `scripts/little_loops/fsm/schema.py` — evaluator type + config validation.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — `ll-loop validate`
  support for the new evaluator type.
- `scripts/little_loops/fsm/validation/meta_rules.py` — ensure MR-1 (`meta-loop
  must have at least one non-LLM evaluator`, `meta_rules.py:74-76`) does not
  misfire on an advisor state paired with a stall evaluator.
  > ⚠ Superseded — exclusion mechanism lives in validation/_base.py, not this file; see § Codebase Research Findings under Integration Map
- `scripts/little_loops/cli/loop/info.py` — display name for the new type
  (alongside the `score_stall` entry at ~line 1452).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `advisor_consult` to
  the `evaluateConfig.type` enum and add `question`/`verdict_map`/`signal`/
  `timeout`/`context_from` to `evaluateConfig.properties`. Hard lockstep requirement, not
  optional: `test_schema_json_evaluate_config_properties_match_dataclass_fields`
  (`test_fsm_schema.py:261-277`) asserts this JSON schema's property keys
  exactly equal `EvaluateConfig`'s dataclass field names — adding the new
  fields to the dataclass without this file fails that test immediately.
  [Agent 3 finding]
- `scripts/little_loops/fsm/validation/_base.py` — beyond
  `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` already listed above,
  `_is_llm_judged()` (`_base.py:165-181`) is a second, independent
  LLM-classification mechanism keyed on `state.evaluate.type in
  ("llm_structured", "check_semantic")`. It gates the MR-8 evidence-contract
  check, the FEAT-2711 session-mode-inheritance check, and the ENH-2713
  haiku-pinned-generator check in `evaluator_rules.py`. Add `"advisor_consult"`
  to this tuple or those three checks misclassify an advisor state as an
  ungated generator. [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/advisor.py` — signal/budget accounting reused as-is.
- Built-in loops under `scripts/little_loops/loops/` — none change in this
  slice; adoption is opt-in.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py` — `ll-loop test`/`ll-loop
  simulate` (`cmd_simulate`) imports and runs the real `evaluate()` dispatcher
  against simulated actions. An `advisor_consult` state in a simulated loop
  triggers a real network-bound consult the same way `llm_structured` already
  does during simulation today — no special-cased mock path exists for either,
  so this is consistent with existing behavior, not a regression, but worth
  confirming during implementation. [Agent 2 finding]

### Tests

- `scripts/tests/test_fsm_evaluators.py` — verdict mapping, confidence in
  details, neutral fallback on consult failure, budget-exhausted path.
- `scripts/tests/test_builtin_loops.py` / loop validation tests — the new type
  validates; MR-1 does not flag a stall→advisor route.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py` — additionally: display-name and
  MR-1-classification tests modeled on `test_fsm_open_question_stall.py`'s
  `TestOpenQuestionStallDisplay` / `TestMR1NonLLMEvaluatorForOpenQuestionStall`
  (lines 201-228), with **inverted polarity** — assert
  `"advisor_consult" not in NON_LLM_EVALUATOR_TYPES` (it's LLM-judged, unlike
  `open_question_stall`). Verdict-map routing, confidence-in-details, and
  neutral-fallback tests should follow the `mock_cli`/dispatch pattern and
  parametrized-routing style of `test_mcp_result_routing` (line 1923), but
  must mock `consult_for_trigger` (the evaluator's actual collaborator under
  the settled exclusivity contract — mocking `advisor.consult` directly would
  bypass the budget/allowlist gating the evaluator relies on); no existing
  test mocks it since the function doesn't exist yet (see Wiring Phase
  blocker below). [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — new
  `test_advisor_consult_evaluator_type_is_valid` + round-trip test, modeled on
  the per-type pattern at lines 2101-2130, plus round-trip coverage for the
  new `question`/`verdict_map`/`signal`/`timeout` fields. [Agent 3 finding]
- `scripts/tests/test_fsm_validation_meta_rules.py` — new MR-1 test modeled on
  `test_mr1_fires_for_meta_loop_with_only_llm_evaluator` /
  `test_mr1_passes_when_score_stall_evaluator_present` (lines 71-122)
  confirming a stall-evaluator→`advisor_consult` route does not misfire MR-1.
  [Agent 3 finding]

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — stall escalation as a sanctioned
  pattern and its relationship to MR-1.
- `docs/reference/API.md` — new evaluator.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5474-5489` — separately from the new-evaluator
  addition above: a hand-copied reproduction of `EvaluateConfig.type`'s
  `Literal[...]` that mirrors `schema.py:77-92`. Already stale today (missing
  `open_question_stall`), confirming it's not test-enforced — add
  `"advisor_consult"` while touching this section. [Agent 2 finding]
- `docs/generalized-fsm-loop.md:306-309` — inline YAML-comment enumeration of
  evaluator types (`# exit_code, output_numeric, ... comparator`), also
  already missing several current types — add `advisor_consult`. [Agent 2
  finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Line-reference refresh** (locator axis re-verified 2026-08-08; the issue's prior refine pass predates a `docs/reference/API.md` edit that made this stale):
  - Evaluator dispatch table in `scripts/little_loops/fsm/evaluators.py`: the `elif eval_type == "..."` chain runs 1846-2005 (`score_stall` at 1944), not 1830-1944 as stated — 1830 is inside the `_EXIT_CODE_AWARE_EVALUATORS`-style list construction, not the dispatch itself.
  - MR-1 rule (`meta_rules.py`): `_validate_meta_loop_evaluation()` spans 73-100 as stated; the actual non-LLM-membership check is `NON_LLM_EVALUATOR_TYPES`, imported from `scripts/little_loops/fsm/validation/_base.py:65-69` — that frozenset is derived automatically from `EVALUATOR_REQUIRED_FIELDS.keys()` minus `{llm_structured, comparator, contract}`. Registering `advisor_consult` in `EVALUATOR_REQUIRED_FIELDS` (`_base.py:45-61`) makes it non-LLM by default unless explicitly excluded — `_base.py` is the file that needs the exclusion, not `meta_rules.py` itself, which only consumes the frozenset.
  - `cli/loop/info.py`: confirmed `_EVALUATE_TYPE_DISPLAY` dict at lines 1443-1455 (not a single "~1452" line); `score_stall` entry is at line 1450.
  - `fsm/schema.py`: `EvaluateConfig.type` Literal is at lines 77-92 (14 current evaluator types, `classify` last) — `advisor_consult` needs to be added to this list.
  - New file not previously listed: `scripts/little_loops/fsm/validation/_base.py` — owns `EVALUATOR_REQUIRED_FIELDS` and `NON_LLM_EVALUATOR_TYPES`; add `advisor_consult` here (required fields list + exclusion decision) as well as in `evaluator_rules.py`/`meta_rules.py`.
- **`docs/reference/API.md` status**: currently documents the `little_loops.advisor` module (line 98, added by FEAT-3108) but has no dedicated FSM-evaluators section. The doc update this issue calls for is a new addition, not an edit to an existing evaluator section.
- **Additional test files confirmed relevant**: `scripts/tests/test_fsm_validation_evaluator_rules.py`, `scripts/tests/test_fsm_validation_meta_rules.py`, `scripts/tests/test_fsm_schema.py`, `scripts/tests/test_advisor.py` (FEAT-3108) — all exist and cover files this issue modifies.
- **`scripts/little_loops/advisor.py`**: as of this pass only contains `MODEL_RANKS`/`rank_model`/`check_floor` (capability floor, from FEAT-3038-adjacent work); `consult()`, `AdvisorVerdict`, `AdvisorConfig`, `should_consult`, `resolve_task_key`, and `record_consult` are not yet present — confirming this issue's `depends_on: FEAT-3044` is load-bearing, not just declared.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Anchor correction** (gap-analysis re-check 2026-08-08): `fsm/schema.py`'s
  `EvaluateConfig.type` `Literal[...]` is now at lines **77-93** (15 entries,
  `classify` last) — `open_question_stall` was added after the prior refine
  pass. The "14 types at lines 77-92" figure earlier in this section (under
  Codebase Research Findings) and the same `schema.py:77-92` cross-reference
  under Files to Modify are both stale by this one-line/one-entry shift;
  `advisor_consult` still needs to be appended as entry 16. All other cited
  anchors (`evaluators.py` dispatch 1846-2005/`score_stall`@1944,
  `_base.py` `EVALUATOR_REQUIRED_FIELDS`@45/`NON_LLM_EVALUATOR_TYPES`@65/
  `_is_llm_judged()`@165-181, `info.py` `_EVALUATE_TYPE_DISPLAY`@1443/
  `score_stall`@1452) were re-verified and remain accurate.

_Anchor refresh — 2026-08-24 (pre-implementation review):_

- `fsm/schema.py` `EvaluateConfig.type` Literal is now at **lines 86-102**
  (15 types, `classify` last) — the 77-93 figures below are stale.
- `fsm/evaluators.py` is now 1898 lines; the dispatch `elif` chain ends well
  before the previously cited 2005 — `score_stall` dispatch is at **:1833**.
- `cli/loop/info.py` `_EVALUATE_TYPE_DISPLAY`: `score_stall` entry now at
  **:1463**.
- `_base.py` anchors still hold: `NON_LLM_EVALUATOR_TYPES`@65,
  `_is_llm_judged()`@168.
- `AdvisorConfig` gained `max_consults_per_task: int = 3` (FEAT-3116) — now
  7 fields.
- `consult_for_trigger()` (`advisor.py:451`) signature:
  `(trigger, *, question, context="", config=None, main_host=None,
  main_model=None, manual=False) -> ConsultOutcome`; `ConsultOutcome`
  carries `verdict: AdvisorVerdict | None` and `skipped_reason` ∈
  `{disabled, trigger_not_allowed, budget_exhausted, not_configured,
  floor_violation, failed, timeout}` — the evaluator's neutral-verdict
  fallback maps every non-`None` `skipped_reason` uniformly.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Sequencing blocker — RESOLVED 2026-08-24**: FEAT-3044, FEAT-3116,
  FEAT-3117, FEAT-3118, and FEAT-3120 are all `done`.
  `scripts/little_loops/advisor.py` now ships `consult()` (`:190`),
  `AdvisorVerdict` (`:162`), `resolve_task_key` (`:338`), `record_consult`
  (`:378`), `should_consult` (`:408`), and `consult_for_trigger` (`:451`,
  returning `ConsultOutcome`). No dependency blocks implementation.
- Update `scripts/little_loops/fsm/fsm-loop-schema.json` — add
  `advisor_consult` to `evaluateConfig.type`'s enum and add
  `question`/`verdict_map`/`signal`/`timeout`/`context_from` to
  `evaluateConfig.properties`,
  in the same change as the `EvaluateConfig` dataclass fields (hard lockstep
  gate, see Tests).
- Update `_is_llm_judged()` in
  `scripts/little_loops/fsm/validation/_base.py:165-181` — add
  `"advisor_consult"` to its type tuple.
- Update `docs/reference/API.md:5474-5489` and
  `docs/generalized-fsm-loop.md:306-309` — add `advisor_consult` to the
  hand-copied evaluator-type enumerations.

## Acceptance Criteria

1. A loop state with `evaluate: {type: advisor_consult, ...}` runs a consult and
   returns a routable verdict drawn from its `verdict_map`.
2. `confidence` is present in `EvaluationResult.details` and usable for
   threshold routing.
3. A stall evaluator's `stall` branch can transition into an advisor state
   through the ordinary transition table — no new schema key is introduced.
4. A failed, timed-out, or budget-exhausted consult returns the configured
   neutral verdict; the loop never strands.
5. Loop-driven consults increment the FEAT-3038 per-task counter and are
   gated/recorded under the fixed `loop_stall` trigger (or the state's
   explicit `signal` override); the routing state's name is carried in the
   consult context and in `EvaluationResult.details`, not as the trigger.
6. `ll-loop validate` accepts the type, and MR-1 does not flag a
   stall-evaluator→advisor route as an unpaired LLM judgment.
7. A resumed run does not re-bill an unbounded number of consults: consults
   stay excluded from the resume/replay input hash, and `record_consult`'s
   per-task budget (`max_consults_per_task`) bounds re-execution across
   resumes. At most one additional consult per resume of an advisor state is
   acceptable; no state-level consult cache is required.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Impact

- **Priority**: P4 — genuinely useful but strictly downstream of a working,
  budget-counted advisor. Loops function without it.
- **Effort**: Medium — the evaluator itself is small; validation-rule
  interaction and the resume/determinism path are where the care goes.
- **Risk**: Medium — adds a network call inside the FSM execution loop. Mitigated
  by neutral-verdict fallback and opt-in adoption.
- **Breaking Change**: No — new evaluator type; no existing loop changes.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md#the-design-rules-mr-1mr-14`

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Verification Notes

_Added by `/ll:verify-issues --check` — 2026-08-08:_

Nearly all locator claims re-verified accurately (evaluators.py dispatch
1846-2005/score_stall@1944, meta_rules.py `_validate_meta_loop_evaluation`@73,
`_base.py` `EVALUATOR_REQUIRED_FIELDS`@45/`NON_LLM_EVALUATOR_TYPES`@65-69/
`_is_llm_judged()`@165-181, `info.py` `_EVALUATE_TYPE_DISPLAY`@1443/
`score_stall`@1452, `advisor.py` current contents, all cited test files, the
`test_schema_json_evaluate_config_properties_match_dataclass_fields` lockstep
gate, FEAT-3038 decomposition into FEAT-3116/3117/3118, and the FEAT-3044
dependency all check out as stated).

One stale locator: `## Codebase Research Findings` (line 201) says
`EvaluateConfig.type`'s Literal in `fsm/schema.py` lists "14 current
evaluator types" at lines 77-92. It is now **15 types** at lines 77-93 —
`open_question_stall` was added after this issue's last refine pass. Does not
change the Proposed Solution or Acceptance Criteria; only the type-count
callout needs updating on next refine. As a side note (not a defect in this
issue), the same `open_question_stall` gap also exists independently in
`fsm-loop-schema.json`'s enum, `docs/reference/API.md:5474-5489`, and
`docs/generalized-fsm-loop.md:306-309` — pre-existing drift unrelated to
`advisor_consult`.

No decisions-log violations (`ll-issues decisions list --type rule
--enforcement required --active-only` returned no entries). No dependency
reference issues found for `depends_on: [FEAT-3044, FEAT-3038]` (both exist;
this project tracks dependencies via frontmatter `depends_on`, not a `##
Blocked By`/`## Blocks` markdown section, so backlink checks are structurally
not applicable here).

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-08-08:_

**Readiness: 80/100 — PROCEED WITH CAUTION.** **Outcome Confidence: 75/100 — MODERATE.**

### Concerns

- **Dependencies are not actually satisfied**, despite `depends_on` frontmatter
  resolving cleanly under `ll-issues show` (no automated `blocked_by` hard
  override fires here — this project's dependency edges are tracked via
  `depends_on`, not `blocked_by`, so BUG-3051's Phase 1.7 override is
  structurally inert for this issue). Checked directly:
  - `FEAT-3044` ("Advisor core — ll-advise CLI, capability floor, and
    ll-doctor check") is **Open**.
  - `FEAT-3038` shows `status: done` in this issue's own `depends_on`, but the
    live status is **Completed** only in name — its Session Log records it was
    decomposed into `FEAT-3116`, `FEAT-3117`, `FEAT-3118`, all three of which
    are **Open**.
  - The issue's own "Wiring Phase — Sequencing blocker" note (confirmed
    against the current `scripts/little_loops/advisor.py`) states
    `consult()`, `AdvisorVerdict`, `AdvisorConfig`, `should_consult`,
    `resolve_task_key`, and `record_consult` do not exist yet — the file
    currently contains only `MODEL_RANKS`/`rank_model`/`check_floor`.
  - Net effect: this issue cannot be implemented or its tests written against
    real symbols until at least `FEAT-3044` and `FEAT-3116` land. Criterion 5
    (Dependencies Satisfied) is scored 0/20 — "critical dependencies
    unresolved, cannot proceed" — even though it doesn't trip the automated
    `DEP_FAIL` hard override.
- Criterion A (Complexity) scores 10/25 — the change touches 7 source files
  plus 2 docs across three subsystems (evaluators, schema/validation, docs),
  and the validation-rule interaction (`_base.py`'s `NON_LLM_EVALUATOR_TYPES`
  derivation, `_is_llm_judged()`) is cross-module/shared-state territory, not
  purely mechanical.
- Criterion B (Test Coverage) scores 20/25 — test files and patterns to model
  are explicitly identified, but the `advisor.consult` mock the tests need
  cannot be written until the real function exists (same root cause as the
  dependency gap above).

### Recommendation

Do not begin implementation yet. This is functionally a **STOP — ADDRESS
GAPS** situation even though the raw 80/100 sum lands in the "PROCEED WITH
CAUTION" band — the aggregate score doesn't capture that one criterion (5)
is a hard blocker for correctness, not just a minor deduction. Re-run this
check after `FEAT-3044` and `FEAT-3116` (at minimum) reach `done`.

- 2026-08-16: `depends_on` lists FEAT-3044 (done), FEAT-3038 (done), FEAT-3120 (open), FEAT-3116 (open). FEAT-3038 was decomposed into FEAT-3116/FEAT-3117/FEAT-3118, all of which are still `status: open` — so despite FEAT-3038 itself showing `status: done` in frontmatter, the real successor work it was split into is NOT done, meaning this issue's actual blockers (FEAT-3120, FEAT-3116, and transitively FEAT-3117/FEAT-3118) remain unresolved. Verdict: DEP_ISSUES.

_Update 2026-08-24: **superseded.** All listed dependencies (FEAT-3044,
FEAT-3116, FEAT-3117, FEAT-3118, FEAT-3120) are `done` and every required
symbol exists in `advisor.py` (see the resolved sequencing-blocker note under
Wiring Phase). The STOP recommendation and the 2026-08-16 DEP_ISSUES verdict
above no longer apply — the issue is implementable now._

## Session Log
- `/ll:verify-issues` - 2026-08-16T16:40:26 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:51 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:confidence-check` - 2026-08-08T21:44:19 - `d7b6c474-eeb6-4901-9ffd-be8f7cc9a06c.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:37:48 - `3b85ed9c-ef3f-4ce0-b887-f5737d6ea801.jsonl`
- `/ll:verify-issues` - 2026-08-08T21:36:40 - `27260c29-4eae-4b2b-89eb-04118be493b8.jsonl`
- `/ll:wire-issue` - 2026-08-08T21:34:07 - `3b85ed9c-ef3f-4ce0-b887-f5737d6ea801.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:25:31 - `b38ce9a8-ea1d-4784-ba74-81f9cf6e4c56.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:35:15 - `0ee091c0-c5a3-41d6-b340-a6539437cf84.jsonl`
- `/ll:verify-issues` - 2026-08-04T21:29:47 - `e72897bf-a708-4dcd-aeaa-907564ef9e34.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`; **SETTLED 2026-08-23**):
the FSM evaluator routes through `consult_for_trigger` (carrying the
state-derived signal) and never calls `little_loops.advisor.consult()`
directly — FEAT-3116 AC #5's exclusivity assertion stands unqualified.
The Proposed Solution and Call Path above have been updated to match. Note
`consult_for_trigger` already runs `should_consult` and the budget check
internally, which also satisfies this issue's AC #5 (per-task counter) and
the budget-exhausted branch of AC #4 without evaluator-local gating code.
