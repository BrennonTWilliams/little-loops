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
- FEAT-3501
unproven_mechanism: false
blocks:
- FEAT-3498
confidence_score: 80
verify_verdict: VALID
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3488: Policy builder offline scenario suites and explanations

## Summary

Add named per-mode scenario suites, independently authored expected outcomes, condition explanations, coverage, boundary suggestions, and local issue-file import. Offline authoring remains self-contained. Connected execution was extracted into FEAT-3498 and structural transition analysis (`analyzeTransitions` + graph UI) into FEAT-3501 after the 2026-09-17 reviews; neither is part of this issue's completion criteria.

## Current Behavior

Decision-table and lifecycle Try-it evaluate one transient sample through `evaluateModel`. In `policy_builder_core.mjs`, that function returns the winning rule index, target, fallback flag, and only the winning rule's boolean condition results. Earlier failed conditions and actual values are discarded; malformed rules return a no-match shape. Rubric is skipped by the template's `updateTryIt` and instead uses aggregate-threshold routing in generated YAML. There is no suite store or reusable boundary generator.

## Expected Behavior

Users save examples with each mode's draft, run all cases without executing actions, inspect why earlier rules failed and the winner matched, and distinguish failed assertions, unasserted cases, and invalid inputs. Rubric cases test supplied aggregate scores rather than simulating LLM scoring.

## Proposed Solution


- Extend ENH-3487's draft wrapper to `{model, scenarios: []}`. Missing scenarios migrate to an empty list. Save/Open, reload, and whole-project history preserve scenarios; edits use the committed-edit path. Preset/start-blank replaces that draft's model and clears its scenarios atomically per ENH-3491; undo restores both.

  Preserve the full wrapper (including unknown JSON-compatible sibling metadata) in `_persistDraft`, `_persistAllDrafts`, `currentProject`, `commit`, hydration/history initialization, mode switching, Open, and snapshot restoration. These paths currently reconstruct `{model}` or persist only `.model`; updating the core serializer alone is insufficient. Preset/start-blank intentionally clears the destination suite only; preserve other drafts and their metadata.

  Template state ownership: `state` stays model-only. `drafts[mode]` is the sole owner of `scenarios` and any sibling metadata; suite edits mutate `drafts[state.mode].scenarios` and go through `commit()`. `commit()`, mode switch, and `applyPreset` write `.model` into the existing wrapper (`{...drafts[mode], model}`) rather than rebuilding `{ model }`, except that preset/start-blank replaces the destination wrapper with `{model, scenarios: []}` by design. Never hang scenarios off `state`; that reintroduces the drop-on-switch defect.

  Schema version: keep `BUILDER_PROJECT_SCHEMA_VERSION` at 1. `parseBuilderProject` rejects any newer version, so a bump would make new saves unopenable in previously generated pages. `scenarios` is an optional additive field: `validateProjectStructure` validates its shape (array of structurally valid scenarios) only when present and tolerates absence; migration fills `[]` after parse.

- A scenario has a stable ID/name, mode-specific input, `expectedTarget: string | null`, and optional `expectedRuleIndex`. `null` is unasserted: suggestions never manufacture their own test oracle. Pin rule-index expectations to a fingerprint of the ordered authored rules; if order/content changes, mark that expectation as needing review (unasserted), retaining the prior expectation for inspection. Target-only assertions remain valid. Do not silently rebind an index to a different rule after reorder; undo restores the fingerprint and expectation.

  Provide an explicit Reconfirm expectation action: the user reviews/selects the target and optional authored rule index before committing a fresh fingerprint. Never copy the observed winner into an expectation automatically. Rule indexes are zero-based authored indexes; omit the index for rubric cases. A null target with an index is invalid, rather than an implicit index-only assertion.

  Derived-fallback assertions: an optional `expectedFallback: true` asserts that the derived fallback (not an authored catch-all sharing the same target) won. It is mutually exclusive with `expectedRuleIndex`, requires a non-null `expectedTarget`, and is not fingerprint-pinned (the fallback identity does not depend on rule order). Without it, a target-only expectation passes whether an authored rule or the fallback produced the target.

  Fingerprint contract: fingerprint the authored rules only, as canonical JSON of `model.rules` (each rule's ordered predicates `{dim, op, value}` and `target`, in authored order). Do not use `_serializeRulesText`, which appends the derived fallback; fingerprinting that text would stale every index expectation whenever only the fallback target changes.

- Add a shared compiled tracing path used by `evaluateModel` and `evaluateScenario`. Preserve `evaluateModel`'s existing MatchResult shape and legacy `evaluateRules`/Python/corpus contracts. Trace every rule evaluated through the winner, with rule index, compiled predicate, actual value or explicit missing flag, expected operand, and boolean result. Later rules are `not_evaluated`; fallback and authored catch-all identities remain distinct. Evaluate all predicates within each visited rule for explanations without changing first-match routing.

- Decision-table inputs are explicit dimension values; lifecycle inputs are frontmatter parsed by `parseFrontmatterBlock` then encoded by `encodeFrontmatterScores`. Rubric input is a user-supplied finite aggregate in [0,100], routed using the same high/medium comparisons and destinations as the generated rubric loop. Those comparisons are pinned by the runtime fragment the emitted rubric loop includes (`scripts/little_loops/loops/lib/rubric-router.yaml:93`, the `tier = "high" if agg >= thresh_high else ("medium" if agg >= thresh_med else "low")` expression in `rubric_parse_scores`; the gate descriptions at lines 103-104 and 121-122 restate it): `high` is `aggregate >= threshold_high`, `medium` is `aggregate >= threshold_medium && aggregate < threshold_high`, `low` is everything else — both tiers are inclusive at their threshold, so an "at threshold" boundary suggestion lands in the upper tier. The JS branch evaluator and `suggestScenarios` must use exactly these operators, and a node:test asserts the at-threshold case for both tiers. Label this as testing routing for an assumed aggregate, not predicting LLM scores. Rubric coverage uses its high/medium/low branches, not authored rule indexes.

- Return verdict `error` for invalid model/scenario input before routing; never silently turn compile failure into no-match, pass, or unasserted. Results include diagnostics and the supplied input. Expected target absent from the current policy is an actionable error; a stale index fingerprint is unasserted/needs review.

  Verdict precedence is explicit: invalid model/input/expectation structure or missing expected target → `error`; otherwise an index expectation with a stale fingerprint → `unasserted` with `needsReview: true`; otherwise null expectation → `unasserted`; otherwise compare target and, when supplied, the current index (both must match to pass). Preserve stale index values for review even if now out of range; reject an out-of-range index claiming a current fingerprint. A missing fingerprint on an index expectation needs review. Failed assertions and stale expectations still contribute routing coverage when the model and input routed successfully.

- Suite totals distinguish passed/failed/unasserted/errors. Routing coverage counts winning authored rule indexes, the derived fallback as a separate identity, and winning rubric branches, including valid unasserted scenarios. Separately report evaluated rule indexes; visiting a rule whose conditions fail never covers that route. Authored catch-all coverage belongs to its authored index, not the derived fallback. Report uncovered routes separately from shadow warnings; routing coverage does not imply assertion coverage. Invalid model/input cases contribute no coverage; expectation-only errors may retain coverage from a successful routing evaluation.

- Suggest missing-field cases and just-below/at/above numeric thresholds using deterministic finite values; deduplicate suggestions and keep rubric suggestions in [0,100]. All suggestions have `expectedTarget: null`. Cover repeated targets, explicit lifecycle terminals from ENH-3492, fallback, absent values, and threshold equality.

- Local lifecycle issue import uses file input/FileReader, extracts only the opening `---`-delimited frontmatter block, then passes its contents to the existing parser. Ignore the Markdown body entirely; diagnose missing opening fences, unclosed fences, and unsupported frontmatter. Accept CRLF and an optional leading UTF-8 BOM. Complete extraction, parsing, and input validation before adding a scenario in one committed edit; any read/validation failure leaves the existing suite unchanged. Imported cases start unasserted.

  The existing lifecycle Try-it paste path and the `{frontmatterText}` scenario input keep their fence-optional behavior: `parseFrontmatterBlock` already tolerates bare `---` lines, so pasted frontmatter with or without fences remains valid. Only file import requires a complete opening fenced block, because a file carries a Markdown body that must be excluded. Do not make paste stricter to match import.

- No skill, shell, LLM, or issue mutation executes from scenarios. Structural transition analysis and the graph UI are FEAT-3501; nothing here depends on it.

## Integration Map


- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: draft migration/serialization, input normalization with provenance, frontmatter extraction, shared compiled trace, scenario suite and suggestion functions, and rubric branch evaluation. Extend `validateProjectStructure` for optional `scenarios`; leave `BUILDER_PROJECT_SCHEMA_VERSION` at 1.

- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: suite editing/results, local file input, committed-edit wiring; rewrite `commit()` (line ~368), the mode-switch handler (~1298-1301), `applyPreset` (~1317-1319), `_persistDraft`/`_persistAllDrafts` (~306-317), and Open/hydration (~412, ~1469) to carry full wrappers.

- Preserve the browser-global export bridge when adding public helpers; regenerate the golden HTML through the existing generator, not by hand-editing its embedded JS.

- Tests: `scripts/tests/js/policy_validator.test.mjs`, `scripts/tests/test_policy_builder_node_gate.py`, `scripts/tests/test_policy_builder_emit.py`, project fixtures and existing conformance corpus gates.

- Documentation: `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md`.

- No server, transport, queue, MCP, or config changes. BUG-3486 is done; ENH-3487 provides saved drafts; ENH-3492 provides terminal semantics and follows ENH-3491's presets/summary.

## Program Design

### Types

`Scenario {id, name, input, expectedTarget, expectedRuleIndex?, expectedFallback?, expectedRulesFingerprint?}`; `ScenarioResult {scenarioId, actualTarget, ruleIndex?, rubricBranch?, trace, verdict, diagnostics}`. Verdicts are pass/fail/unasserted/error.

`ScenarioInput` is selected by the containing draft's mode:
- decision table: `{values: Record<string, number | boolean>}` keyed by normalized dimension name; finite numeric scores in [0,100], actual booleans encoded to 100/0. Omitted keys mean missing; null, numeric strings, wrong types, unknown keys, and nonfinite/out-of-range values are errors.
- lifecycle: `{frontmatterText: string}` containing the extracted/pasted frontmatter, processed by `parseFrontmatterBlock` and `encodeFrontmatterScores`. Preserve the encoder's runtime-compatible coercions and missing/null behavior; do not apply decision-table score bounds to lifecycle numeric fields. Unsupported parser syntax or a non-string text field is an error; unrelated frontmatter keys are allowed.
- rubric: `{aggregate: number}` with a finite value in [0,100]. Strings/null/nonfinite/out-of-range values are errors.

Trace condition records include `{sourceKey, rawPresent, rawValue, encodedPresent, encodedValue, predicate, result}`. For lifecycle derived dimensions retain the actual source key (e.g. `priority` for `priority_rank`); absent boolean/list source fields remain visibly absent even though their encoded value is `"0"`. Distinguish an absent field from a present null value. Include the supplied input and `needsReview` in `ScenarioResult`.

### Signatures

Proposed new contracts in core.mjs:

- `normalizeScenarioInput(model, input) -> {scores, provenance, aggregate?, diagnostics}` implements the mode-specific contract above.

- `extractIssueFrontmatter(text) -> string` extracts a complete opening frontmatter block or throws a diagnostic before any suite mutation.

- `traceModel(model, input) -> {match, rules, rubricBranch?, diagnostics}` normalizes scenario input and retains raw/encoded provenance. `match` retains the current MatchResult shape; `rules` carries evaluated/not-evaluated status and per-condition values. Share lower-level compilation/predicate evaluation with `evaluateModel` instead of duplicating semantics; the legacy evaluator still accepts encoded scores and preserves its compile-failure/no-match behavior.

- `evaluateScenario(model, scenario) -> ScenarioResult`.

- `runScenarioSuite(model, scenarios) -> {results, summary: {passed, failed, unasserted, errors}, coverage: {winningRuleIndexes, evaluatedRuleIndexes, uncoveredRuleIndexes, fallback: {applicable, covered}, winningRubricBranches, uncoveredRubricBranches}}`. Non-applicable mode collections are empty; fallback applicability refers only to an emitted derived fallback.

- `suggestScenarios(model) -> Scenario[]` with null expectations.

- `rulesFingerprint(model) -> string`: canonical JSON of the authored `model.rules` only (see the fingerprint contract above); cryptographic hashing is unnecessary offline.

### Call Path

`cmd_policy_builder` generates the self-contained page with the embedded core and template handlers. In that page: `updatePreview` → `buildModel` → `validateBuilderModel`; Run all → `runScenarioSuite` → `evaluateScenario` → `traceModel`. `updatePreview` builds and validates the model; explicit Run all evaluates cases through the shared trace/evaluator and renders results. On an edit, clear or mark displayed results stale until rerun; results are derived data and are not saved as authoritative assertions.

## Implementation Steps

1. Extend draft parsing and every enumerated browser persistence/history path with scenario migration, full-wrapper preservation, structural checks, and expectation fingerprints (schema version stays 1).
2. Add mode-specific input normalization/provenance, shared compiled trace, and explicit rubric aggregate evaluation; retain existing evaluator/conformance behavior.
3. Implement scenario editing and explicit expectation reconfirmation, verdict precedence, Run all, totals, separate winning/evaluated coverage, and stale-result feedback.
4. Add boundary suggestions and atomic local issue import with frontmatter extraction.
5. Test all modes, each browser persistence transition, import failure atomicity, verdict combinations, raw/encoded missing values, and coverage identities; regenerate golden HTML and update docs. Record manual browser save/reload/import/preset/undo checks using ENH-3487's existing manual-testing decision.

## Acceptance Criteria


- [ ] Old projects acquire `scenarios: []` per draft; named cases, inputs, expectations, and fingerprints survive Save/Open/reload/undo. Applying a preset clears only that draft's suite and one undo restores it. `BUILDER_PROJECT_SCHEMA_VERSION` remains 1 and a project saved with scenarios opens in a page generated before this change.

- [ ] Fingerprints derive from authored `model.rules` only: changing just the fallback target leaves index expectations current; reordering or editing any authored rule stales them. `expectedFallback: true` passes only when the derived fallback won, fails when an authored catch-all with the same target won, and is rejected alongside `expectedRuleIndex`.

- [ ] Traces explain failed earlier rules and the winning rule with compiled predicates and actual/missing values; later rules are not evaluated. Repeated-target, authored catch-all, and derived-fallback identities are correct. Existing `evaluateModel`, `evaluateRules`, Python evaluator, and conformance corpus behavior remain compatible.

- [ ] Rubric aggregate cases below/at/above both thresholds agree with generated rubric routing. The UI labels supplied aggregates as assumptions and reports rubric branch coverage separately.

- [ ] Totals distinguish pass/fail/unasserted/error. Invalid models/inputs cannot report pass or normal no-match; stale rule-index expectations need review after reorder/edit and recover on undo. Target-only expectations are unaffected by index changes.

- [ ] Suggestions are deterministic, deduplicated, unasserted, and include absent fields and numeric boundaries without nonfinite/out-of-range rubric inputs.

- [ ] Coverage includes valid unasserted inputs but is labeled routing coverage; ENH-3492 terminal targets/fallbacks are exercised.

- [ ] Local issue import works offline with explicit parser diagnostics. Scenarios execute no actions and make no predictions about LLM/action effects. The lifecycle paste path still accepts fence-less frontmatter.

- [ ] Editing a policy invalidates displayed results; preset/clear/undo and all suite controls pass the documented manual browser workflow. Golden HTML and applicable Node/Python gates pass.

- [ ] Full draft wrappers survive ordinary committed edits, active/inactive mode switches, Save/Open, storage reload, and undo/redo, including unknown sibling metadata. Preset/start-blank clears only the selected destination suite atomically; undo restores it. Verification exercises browser paths, not only core JSON round trips.

- [ ] Mode-specific input contracts reject malformed values without treating valid absence as an error. Tests cover decision-table true/false encoding, missing lifecycle boolean/list fields showing raw absence alongside encoded zero, present null versus absence, and derived `priority_rank` source provenance.

- [ ] Verdict tests cover invalid input combined with stale fingerprints (error wins), a removed expected target (error), stale index plus target mismatch (needs review), current index plus target match/mismatch, missing fingerprints, and explicit reconfirmation followed by undo. No reconfirmation silently adopts the observed result.

- [ ] A visited-but-failing rule appears only in evaluated coverage and remains uncovered as a winning route. Tests distinguish repeated-target authored rules, authored catch-all, derived fallback, rubric branches, valid unasserted/failed assertions, and invalid model/input cases.

- [ ] A complete issue Markdown file imports successfully without parsing its body; BOM/CRLF are handled. Missing/unclosed fences, unsupported frontmatter, and read failures produce diagnostics without altering the suite. Successful import adds one unasserted case and is undoable.

- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` document the scenario-suite feature: authoring/running scenarios, expectation types (target-only, rule-index with fingerprint, `expectedFallback`), verdicts, coverage semantics, boundary suggestions, and local issue-file import.

## Use Case

A maintainer saves ready, blocked, and unscored issue examples, changes the readiness threshold, and runs the suite to see which independently authored expectations changed and which earlier rule conditions failed.

## Impact


- Priority: P3 — improves confidence in policy edits.

- Effort: Large — suite persistence across every browser draft path, shared trace, rubric contract, suggestions, and import; the prior `score_complexity: 10` predates the 2026-09-17 rewrite and is stale. If still too large after the FEAT-3501 split, suggestions plus import are the next natural extraction.

- Risk: Medium — shared evaluation must preserve existing semantics.

- Breaking change: No; project schema additions are backward-readable and existing YAML emission is unchanged.

## Scope Boundaries

Includes offline scenario suites only. Excludes structural transition analysis and the graph UI (FEAT-3501), connected issue discovery, run submission/approval, hashing, queue changes, and arbitrary YAML import. FEAT-3498 owns all former Phase B work and the level-2 spike follow-up. ENH-3487 owns document identity/persistence; ENH-3491 owns presets; ENH-3492 owns destinations and scoring metadata.

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

_Historical assessment from `/ll:confidence-check` on 2026-09-17; superseded dependency finding corrected by manual review later that day._

**Prior Readiness Score**: 80/100; the prior dependency-based STOP no longer applies.
**Prior Outcome Confidence**: 64/100. Frontmatter scores are historical and have not been recomputed by this specification edit; rerun confidence-check before implementation.

### Gaps to Address
- All listed dependencies (BUG-3486, ENH-3487, ENH-3491, ENH-3492) are now done. Retain their dependency links as implementation provenance; they no longer block this issue. The manual-review gaps are incorporated into the directive sections and acceptance criteria above.

### Outcome Risk Factors
- Moderate per-site complexity: the shared compiled trace path (`traceModel`) must preserve `evaluateModel`'s existing MatchResult shape plus legacy `evaluateRules`/Python/corpus contracts while adding new tracing — a cross-module change with shared state, not a mechanical edit.
- Browser persistence currently reconstructs model-only wrappers. This issue now explicitly owns full-wrapper preservation with `drafts[mode]` as the single scenario owner; verification must exercise these integration paths alongside the pure helpers.

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- All current-state claims checked out against source: `evaluateModel` (`policy_builder_core.mjs:452`) returns exactly `{ruleIndex, target, isFallback, conditionResults}` with only the winning rule's condition results, matching Current Behavior; `updateTryIt` (`policy-router-builder.html.tmpl:1064`) short-circuits for rubric mode (`state.mode !== "decision_table"`), confirming rubric is skipped; no `runScenarioSuite`/`evaluateScenario`/`suggestScenarios`/`rulesFingerprint`/`traceModel`/`normalizeScenarioInput`/`extractIssueFrontmatter` exist yet, confirming "no suite store or reusable boundary generator."
- All cited line numbers verified against current source: `commit()` at html.tmpl:364 (cited ~368), mode-switch handler at html.tmpl:1296-1305 (cited ~1298-1301), `applyPreset` at html.tmpl:1313 (cited ~1317-1319), `_persistDraft`/`_persistAllDrafts` at html.tmpl:306-317 (exact), Open/hydration at html.tmpl:412 and :1469 (exact). All three commit/switch/preset sites reconstruct `{model}`-only wrappers and `_persistDraft` persists only `.model`, exactly as claimed.
- `rubric-router.yaml` citations verified exact: line 93's tier expression and lines 103-104/121-122's gate descriptions match the quoted text and the inclusive-at-threshold (`>=`) semantics described.
- `_serializeRulesText` (core.mjs:1506) appends `model.fallback` (a field separate from `model.rules`) only when no authored catch-all exists — confirms fingerprinting `model.rules` alone naturally excludes the derived fallback, as the fingerprint contract requires.
- Dependencies BUG-3486, ENH-3487, ENH-3491, ENH-3492 all confirmed `done`. `blocks`/`relates_to` references all resolve and backlink correctly (FEAT-3498's `blocked_by` includes FEAT-3488; FEAT-3474/BUG-3489/BUG-3490/FEAT-3501 all exist) — no DEP_ISSUES.
- Decisions log checked (`.ll/decisions.yaml` + `.ll/decisions.d/`): no active required rules — no DECISIONS_VIOLATION.
- `ll-verify-evidence --json`: 0 findings — no EVIDENCE_UNVERIFIED.
- **Proposal-vs-code consequence check (B6) finding**: the Integration Map named a Documentation integration point (`docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md`), and Implementation Step 5 said to "update docs," but no Acceptance Criterion verified the docs were actually updated — every listed AC covered code/schema/UI/test behavior, none named the docs. That was a real AC-coverage gap, not a claim-accuracy defect. **Fixed**: added an AC requiring `POLICY_ROUTER_GUIDE.md` and the CLI.md policy-builder section to document scenario authoring/running, expectation types, verdicts, coverage semantics, suggestions, and import.

## Session Log

- `/ll:verify-issues` - 2026-09-17T21:35:36 - `ba3eff4d-1d07-4139-8410-b5c4e703860f.jsonl`
- manual review - 2026-09-17 - split structural transition analysis + graph UI into FEAT-3501; pinned template state ownership (`state` model-only, `drafts[mode]` owns scenarios), schema version stays 1, authored-rules-only fingerprint, `expectedFallback` assertion, fence-optional paste vs fenced import, corrected rubric-router citation to line 93; marked effort Large and `score_complexity` stale

- manual review - 2026-09-17 - applied pre-implementation review: full-wrapper browser persistence, atomic fenced-frontmatter import, winning-route versus evaluated-rule coverage, typed input/provenance contracts, shared transition analysis, verdict precedence and explicit reconfirmation; corrected stale dependency assessment without inventing new confidence scores.

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
