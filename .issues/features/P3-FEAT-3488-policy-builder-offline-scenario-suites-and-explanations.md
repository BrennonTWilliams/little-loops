---
id: FEAT-3488
parent: EPIC-3493
epic: EPIC-3493
type: FEAT
title: Policy builder offline scenario suites and explanations
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:21Z'
labels:
- policy-builder
- captured
blocked_by:
- BUG-3486
- ENH-3487
- ENH-3491
- ENH-3492
relates_to:
- FEAT-3474
- BUG-3489
- BUG-3490
- ENH-3491
- FEAT-3498
unproven_mechanism: false
blocks:
- FEAT-3498
confidence_score: 80
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3488: Policy builder offline scenario suites and explanations

## Summary

Add named per-mode scenario suites, independently authored expected outcomes, condition explanations, coverage, boundary suggestions, local issue-file import, and structural flow analysis. Offline authoring remains self-contained. Connected execution was extracted into FEAT-3498 after the 2026-09-17 review; it is not part of this issue's completion criteria.

## Current Behavior

Decision-table and lifecycle Try-it evaluate one transient sample through `evaluateModel`. In `policy_builder_core.mjs`, that function returns the winning rule index, target, fallback flag, and only the winning rule's boolean condition results. Earlier failed conditions and actual values are discarded; malformed rules return a no-match shape. Rubric is skipped by the template's `updateTryIt` and instead uses aggregate-threshold routing in generated YAML. There is no suite store or reusable boundary generator.

## Expected Behavior

Users save examples with each mode's draft, run all cases without executing actions, inspect why earlier rules failed and the winner matched, and distinguish failed assertions, unasserted cases, and invalid inputs. Rubric cases test supplied aggregate scores rather than simulating LLM scoring. Structural flow warnings describe possible transitions, never predicted action effects.

## Proposed Solution


- Extend ENH-3487's draft wrapper to `{model, scenarios: []}`. Missing scenarios migrate to an empty list. Save/Open, reload, and whole-project history preserve scenarios; edits use the committed-edit path. Preset/start-blank replaces that draft's model and clears its scenarios atomically per ENH-3491; undo restores both.

- A scenario has a stable ID/name, mode-specific input, `expectedTarget: string | null`, and optional `expectedRuleIndex`. `null` is unasserted: suggestions never manufacture their own test oracle. Pin rule-index expectations to a fingerprint of the ordered authored rules; if order/content changes, mark that expectation as needing review (unasserted), retaining the prior expectation for inspection. Target-only assertions remain valid. Do not silently rebind an index to a different rule after reorder; undo restores the fingerprint and expectation.

- Add a shared compiled tracing path used by `evaluateModel` and `evaluateScenario`. Preserve `evaluateModel`'s existing MatchResult shape and legacy `evaluateRules`/Python/corpus contracts. Trace every rule evaluated through the winner, with rule index, compiled predicate, actual value or explicit missing flag, expected operand, and boolean result. Later rules are `not_evaluated`; fallback and authored catch-all identities remain distinct. Evaluate all predicates within each visited rule for explanations without changing first-match routing.

- Decision-table inputs are explicit dimension values; lifecycle inputs are frontmatter parsed by `parseFrontmatterBlock` then encoded by `encodeFrontmatterScores`. Rubric input is a user-supplied finite aggregate in [0,100], routed using the same high/medium comparisons and destinations as the generated rubric loop. Those comparisons are pinned by the runtime fragments (`scripts/little_loops/loops/lib/rubric-router.yaml:103-104,121-122`): `high` is `aggregate >= threshold_high`, `medium` is `aggregate >= threshold_medium && aggregate < threshold_high`, `low` is everything else — both tiers are inclusive at their threshold, so an "at threshold" boundary suggestion lands in the upper tier. The JS branch evaluator and `suggestScenarios` must use exactly these operators, and a node:test asserts the at-threshold case for both tiers. Label this as testing routing for an assumed aggregate, not predicting LLM scores. Rubric coverage uses its high/medium/low branches, not authored rule indexes.

- Return verdict `error` for invalid model/scenario input before routing; never silently turn compile failure into no-match, pass, or unasserted. Results include diagnostics and the supplied input. Expected target absent from the current policy is an actionable error; a stale index fingerprint is unasserted/needs review.

- Suite totals distinguish passed/failed/unasserted/errors. Coverage records which rules or rubric branches were reached by valid scenarios, even unasserted ones; it does not imply assertion coverage. Report uncovered rules/branches separately from shadow warnings.

- Suggest missing-field cases and just-below/at/above numeric thresholds using deterministic finite values; deduplicate suggestions and keep rubric suggestions in [0,100]. All suggestions have `expectedTarget: null`. Cover repeated targets, explicit lifecycle terminals from ENH-3492, fallback, absent values, and threshold equality.

- Local lifecycle issue import uses file input/FileReader and the existing frontmatter parser, with diagnostics for unsupported content. Reuse ENH-3491's transition summary data for graph/cycle warnings rather than introducing a competing transition interpretation. No skill, shell, LLM, or issue mutation executes from scenarios.

## Integration Map


- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: draft migration/serialization, shared compiled trace, scenario suite and suggestion functions, rubric branch evaluation.

- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: suite editing/results, local file input, committed-edit wiring, structural graph presentation.

- Preserve the browser-global export bridge when adding public helpers; regenerate the golden HTML through the existing generator, not by hand-editing its embedded JS.

- Tests: `scripts/tests/js/policy_validator.test.mjs`, `scripts/tests/test_policy_builder_node_gate.py`, `scripts/tests/test_policy_builder_emit.py`, project fixtures and existing conformance corpus gates.

- Documentation: `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md`.

- No server, transport, queue, MCP, or config changes. BUG-3486 is done; ENH-3487 provides saved drafts; ENH-3492 provides terminal semantics and follows ENH-3491's presets/summary.

## Program Design

### Types

`Scenario {id, name, input, expectedTarget, expectedRuleIndex?, expectedRulesFingerprint?}`; `ScenarioResult {scenarioId, actualTarget, ruleIndex?, rubricBranch?, trace, verdict, diagnostics}`. Verdicts are pass/fail/unasserted/error.

### Signatures

Proposed new contracts in core.mjs:

- `traceModel(model, input) -> {match, rules, rubricBranch?, diagnostics}`. `match` retains the current MatchResult shape; `rules` carries evaluated/not-evaluated status and per-condition values. Share compilation/predicate evaluation with `evaluateModel` instead of duplicating semantics.

- `evaluateScenario(model, scenario) -> ScenarioResult`.

- `runScenarioSuite(model, scenarios) -> {results, summary: {passed, failed, unasserted, errors, uncoveredRuleIndexes, uncoveredRubricBranches}}`.

- `suggestScenarios(model) -> Scenario[]` with null expectations.

- Scenario index expectations additionally store an ordered-rule fingerprint (a canonical rules serialization is sufficient; cryptographic hashing is unnecessary offline).

### Call Path

`cmd_policy_builder` generates the self-contained page with the embedded core and template handlers. In that page: `updatePreview` → `buildModel` → `validateBuilderModel`; Run all → `runScenarioSuite` → `evaluateScenario` → `traceModel`. `updatePreview` builds and validates the model; explicit Run all evaluates cases through the shared trace/evaluator and renders results. On an edit, clear or mark displayed results stale until rerun; results are derived data and are not saved as authoritative assertions.

## Implementation Steps

1. Extend draft parsing and history with scenario migration, structural checks, and expectation fingerprints.
2. Add shared compiled trace and explicit rubric aggregate evaluation; retain existing evaluator/conformance behavior.
3. Implement scenario editing, Run all, totals, traces, coverage, and stale-result feedback.
4. Add boundary suggestions, local lifecycle issue import, and structural graph warnings using shared transition data.
5. Test all modes, project round trips and terminal destinations; regenerate golden HTML and update docs. Record manual browser save/reload/import/preset/undo checks using ENH-3487's existing manual-testing decision.

## Acceptance Criteria


- [ ] Old projects acquire `scenarios: []` per draft; named cases, inputs, expectations, and fingerprints survive Save/Open/reload/undo. Applying a preset clears only that draft's suite and one undo restores it.

- [ ] Traces explain failed earlier rules and the winning rule with compiled predicates and actual/missing values; later rules are not evaluated. Repeated-target, authored catch-all, and derived-fallback identities are correct. Existing `evaluateModel`, `evaluateRules`, Python evaluator, and conformance corpus behavior remain compatible.

- [ ] Rubric aggregate cases below/at/above both thresholds agree with generated rubric routing. The UI labels supplied aggregates as assumptions and reports rubric branch coverage separately.

- [ ] Totals distinguish pass/fail/unasserted/error. Invalid models/inputs cannot report pass or normal no-match; stale rule-index expectations need review after reorder/edit and recover on undo. Target-only expectations are unaffected by index changes.

- [ ] Suggestions are deterministic, deduplicated, unasserted, and include absent fields and numeric boundaries without nonfinite/out-of-range rubric inputs.

- [ ] Coverage includes valid unasserted inputs but is labeled routing coverage; ENH-3492 terminal targets/fallbacks are exercised.

- [ ] Local issue import works offline with explicit parser diagnostics. Scenarios and structural graphs execute no actions and make no predictions about LLM/action effects.

- [ ] Editing a policy invalidates displayed results; preset/clear/undo and all suite controls pass the documented manual browser workflow. Golden HTML and applicable Node/Python gates pass.

## Use Case

A maintainer saves ready, blocked, and unscored issue examples, changes the readiness threshold, and runs the suite to see which independently authored expectations changed and which earlier rule conditions failed.

## Impact


- Priority: P3 — improves confidence in policy edits.

- Effort: Medium/large — suite UI plus trace and rubric contracts.

- Risk: Medium — shared evaluation must preserve existing semantics.

- Breaking change: No; project schema additions are backward-readable and existing YAML emission is unchanged.

## Scope Boundaries

Includes offline scenario suites and structural analysis. Excludes connected issue discovery, run submission/approval, hashing, queue changes, and arbitrary YAML import. FEAT-3498 owns all former Phase B work and the level-2 spike follow-up. ENH-3487 owns document identity/persistence; ENH-3491 owns presets; ENH-3492 owns destinations and scoring metadata.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Routing, lifecycle semantics, simulation limits |
| Reference | docs/reference/CLI.md | Builder usage |

## Review History

The earlier refinement/wiring passes mixed offline suites with connected transport and described the pre-BUG-3486 evaluator. Their active directives were reconciled on 2026-09-17. Connected design, unresolved queue risks, and `scripts/tests/spike/level2_run_handoff/` follow-up now belong to FEAT-3498; the spike does not prove the production queue approval path.

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-17_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 64/100 → LOW

### Gaps to Address
- `blocked_by` lists ENH-3487, ENH-3491, and ENH-3492, all still `open` — the Dependencies Hard Override forces STOP regardless of the 80/100 aggregate. This issue's own Proposed Solution explicitly builds on ENH-3487's draft wrapper, ENH-3491's presets/transition summary, and ENH-3492's terminal semantics; none of those contracts exist yet to implement against.

### Outcome Risk Factors
- Moderate per-site complexity: the shared compiled trace path (`traceModel`) must preserve `evaluateModel`'s existing MatchResult shape plus legacy `evaluateRules`/Python/corpus contracts while adding new tracing — a cross-module change with shared state, not a mechanical edit.
- Ambiguity residual: several proposed-solution details (transition summary reuse, terminal destination exercising) depend on ENH-3491/ENH-3492 designs that may still shift before those issues land.

## Session Log

- `/ll:confidence-check` - 2026-09-17T06:34:31 - `0ef705a3-d006-496e-b37a-476f2afd18d1.jsonl`
- `/ll:verify-issues` - 2026-09-17T06:28:40 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - added ENH-3491 to `blocked_by` (summary data and preset-clears-scenarios contract were only transitively covered); pinned rubric tier comparisons to `lib/rubric-router.yaml` (`>=` inclusive at both thresholds)

- manual review - 2026-09-17 - split connected execution into FEAT-3498; specified full traces, rubric aggregate scenarios, error verdicts, index-fingerprint invalidation, preset semantics, coverage, and ENH-3492 dependency

- manual review - 2026-09-17 - transport gaps closed: SseBridge needs do_POST; page served same-origin (no CORS); LOOP entries run via `ll-loop run` shell-out with `loop_input`, YAML persisted content-addressed; sync pure-JS SHA-256; `raise_on_error=False` pinned; drafts are `{model}` wrappers per ENH-3487. BUG-3486 dependency done.

- `/ll:verify-issues` - 2026-09-16T22:52:47 - `56d2686a-f690-474a-8849-1b96c2edbd15.jsonl`

- manual review - 2026-09-16 - narrowed `blocked_by` to BUG-3486/ENH-3487; resolved transport to `ll-queue`; defined `requestId`/`revisionId`; built scenarios on `evaluateModel`; per-draft scenarios; unasserted state; split into Phase A/B; spike not promoted

- `/ll:wire-issue` - 2026-09-16T22:32:07 - `c1fe383a-93c2-4cce-a8fa-6eeed2e54d04.jsonl`

- `/ll:spike` - 2026-09-16T21:26:31 - `60e2c60c-390c-4854-b7a8-e5d6ce9f3356.jsonl`

- `/ll:refine-issue` - 2026-09-16T21:07:55 - `7017ba73-36ea-43e3-b3d4-064b9a419b43.jsonl`

- `/ll:capture-issue` - 2026-09-16T20:55:14 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
