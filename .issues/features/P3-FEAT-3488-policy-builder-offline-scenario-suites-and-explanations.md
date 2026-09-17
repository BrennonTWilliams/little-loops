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
confidence_score: 100
verify_verdict: VALID
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
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

  History isolation: editable drafts must never share mutable objects with `history.present`, `past`, or `future`. This invariant applies at hydration, Open, and snapshot restoration as well as ordinary commits. The current `restoreFromSnapshot` and Open paths alias live drafts into history; cloning only inside `applyDraftEdit` is too late after an in-place suite edit has already mutated the prior snapshot. Open → suite edit → undo and undo → suite edit → undo must restore the pre-edit values.

  Reload restores every saved mode belonging to the current project, including inactive suites and sibling metadata. The current `hydrateFromStorage` reads only the active mode and the mode-switch handler consults only in-memory drafts; carrying wrappers alone does not satisfy this contract. Opening a project must replace or scope the stored draft set so modes absent from the opened project cannot reappear from a previous project's storage. Verify populate two modes → reload → switch → Save, plus Open a project lacking a previously stored mode → reload → switch.

  Schema version: keep `BUILDER_PROJECT_SCHEMA_VERSION` at 1. `parseBuilderProject` rejects any newer version, so a bump would make new saves unopenable in previously generated pages. `scenarios` is an optional additive field: `validateProjectStructure` validates its shape (array of structurally valid scenarios) only when present and tolerates absence; migration fills `[]` after parse.

  Storage validation is separate from execution validation. Structural checks require scenario objects with non-empty unique IDs within the draft, string names (which may be unfinished/empty), and an input object; known expectation fields, when present, have their declared primitive types. Missing input members or expectations, wrong mode-specific input values, unsupported frontmatter text, out-of-range scores, removed targets, conflicting expectation combinations, and stale/out-of-range indexes remain editable JSON data and survive Save/Open/reload unchanged. Run reports per-case errors or needs-review verdicts using the execution contracts below; these semantic defects must not reject the entire saved project. No storage migration silently repairs an authored expectation. Non-JSON values are outside the persisted-data contract.

- A scenario has a stable ID/name, mode-specific input, `expectedTarget: string | null`, and optional `expectedRuleIndex`. `null` is unasserted: suggestions never manufacture their own test oracle. Pin rule-index expectations to a fingerprint of the ordered authored rules; if order/content changes, mark that expectation as needing review (unasserted), retaining the prior expectation for inspection. Target-only assertions remain valid. Do not silently rebind an index to a different rule after reorder; undo restores the fingerprint and expectation.

  Provide an explicit Reconfirm expectation action: the user reviews/selects the target and optional authored rule index before committing a fresh fingerprint. Never copy the observed winner into an expectation automatically. Rule indexes are zero-based authored indexes; omit the index for rubric cases. A null target with an index is invalid, rather than an implicit index-only assertion.

  Derived-fallback assertions: an optional `expectedFallback: true` asserts that the derived fallback (not an authored catch-all sharing the same target) won. It is mutually exclusive with `expectedRuleIndex`, requires a non-null `expectedTarget`, and is not fingerprint-pinned (the fallback identity does not depend on rule order). Without it, a target-only expectation passes whether an authored rule or the fallback produced the target.

  Fingerprint contract: fingerprint the authored rules only, as canonical JSON of `model.rules` (each rule's ordered predicates `{dim, op, value}` and `target`, in authored order). Do not use `_serializeRulesText`, which appends the derived fallback; fingerprinting that text would stale every index expectation whenever only the fallback target changes.

- Add a shared compiled tracing path used by `evaluateModel` and `evaluateScenario`. Preserve `evaluateModel`'s existing MatchResult shape and legacy `evaluateRules`/Python/corpus contracts. Trace every rule evaluated through the winner, with rule index, compiled predicate, actual value or explicit missing flag, expected operand, and boolean result. Later rules are `not_evaluated`; fallback and authored catch-all identities remain distinct. Evaluate all predicates within each visited rule for explanations without changing first-match routing.

- Decision-table inputs are explicit dimension values; lifecycle inputs are frontmatter parsed by `parseFrontmatterBlock` then encoded by `encodeFrontmatterScores`. Rubric input is a user-supplied finite aggregate in [0,100], routed using the same high/medium comparisons and destinations as the generated rubric loop. Those comparisons are pinned by the runtime fragment the emitted rubric loop includes (`scripts/little_loops/loops/lib/rubric-router.yaml:93`, the `tier = "high" if agg >= thresh_high else ("medium" if agg >= thresh_med else "low")` expression in `rubric_parse_scores`; the gate descriptions at lines 103-104 and 121-122 restate it): `high` is `aggregate >= threshold_high`, `medium` is `aggregate >= threshold_medium && aggregate < threshold_high`, `low` is everything else — both tiers are inclusive at their threshold, so an "at threshold" boundary suggestion lands in the upper tier. The JS branch evaluator and `suggestScenarios` must use exactly these operators, and a node:test asserts the at-threshold case for both tiers. Label this as testing routing for an assumed aggregate, not predicting LLM scores. Rubric coverage uses its high/medium/low branches, not authored rule indexes.

- Return verdict `error` for invalid model/scenario input before routing; never silently turn compile failure into no-match, pass, or unasserted. Results include diagnostics and the supplied input. Expected target absent from the current policy is an actionable error; a stale index fingerprint is unasserted/needs review.

  Rubric target validity is mode-specific: high → `done`, medium → `light_repair`, low → `deep_repair`, matching `_serializeRubric` even when `model.outcomes` is empty and repair outcomes are synthesized. These three destinations form the rubric assertion target set; do not derive it solely from authored outcomes. Rubric scenarios reject `expectedRuleIndex` and `expectedFallback`, since rubric branches are neither authored rules nor derived fallbacks.

  Verdict precedence is explicit: invalid model/input/expectation structure or missing expected target → `error`; otherwise an index expectation with a stale fingerprint → `unasserted` with `needsReview: true`; otherwise null expectation → `unasserted`; otherwise compare target and, when supplied, the current index (both must match to pass). Preserve stale index values for review even if now out of range; reject an out-of-range index claiming a current fingerprint. A missing fingerprint on an index expectation needs review. Failed assertions and stale expectations still contribute routing coverage when the model and input routed successfully.

- Suite totals distinguish passed/failed/unasserted/errors. Routing coverage counts winning authored rule indexes, the derived fallback as a separate identity, and winning rubric branches, including valid unasserted scenarios. Separately report evaluated rule indexes; visiting a rule whose conditions fail never covers that route. Authored catch-all coverage belongs to its authored index, not the derived fallback. Report uncovered routes separately from shadow warnings; routing coverage does not imply assertion coverage. Invalid model/input cases contribute no coverage; expectation-only errors may retain coverage from a successful routing evaluation.

- Suggest missing-field cases and just-below/at/above numeric thresholds using deterministic finite values; deduplicate suggestions and keep rubric suggestions in [0,100]. All suggestions have `expectedTarget: null`. Cover repeated targets, explicit lifecycle terminals from ENH-3492, fallback, absent values, and threshold equality.

  Every suggestion for a valid model must pass `normalizeScenarioInput`. Decision-table numeric suggestions also stay in [0,100]. Lifecycle suggestions use source fields accepted by the encoder: generate `priority: Pn` for `priority_rank`, not a literal `priority_rank` field, and real lists for list-length predicates. Priority ranks and list lengths have discrete representable domains; choose representable neighbors on the intended side of a threshold and skip impossible equality/neighbor cases rather than emit invalid inputs. Tests verify that generated lifecycle source values encode to the intended boundary and that omitted-field suggestions retain the existing missing-value semantics.

- Local lifecycle issue import uses file input/FileReader, extracts only the opening `---`-delimited frontmatter block, then passes its contents to the existing parser. Ignore the Markdown body entirely; diagnose missing opening fences, unclosed fences, and unsupported frontmatter. Accept CRLF and an optional leading UTF-8 BOM. Complete extraction, parsing, and input validation before adding a scenario in one committed edit; any read/validation failure leaves the existing suite unchanged. Imported cases start unasserted.

  The existing lifecycle Try-it paste path and the `{frontmatterText}` scenario input keep their fence-optional behavior: `parseFrontmatterBlock` already tolerates bare `---` lines, so pasted frontmatter with or without fences remains valid. Only file import requires a complete opening fenced block, because a file carries a Markdown body that must be excluded. Do not make paste stricter to match import.

  Unsupported syntax needs explicit validation; the existing parser alone is insufficient. The supported subset is flat scalar/null fields and flat scalar lists in flow or dash-list form, with the existing comment, quoting, status-normalization, and fence-optional paste behavior. Reject nested mappings/collections, block scalars, YAML tags, anchors/aliases, and malformed flow lists with diagnostics before scenario routing or file-import mutation. Regression fixtures include `x: {a: b}`, `x: |`, `x: [a`, and `x: !!str 5`, which the current parser silently treats as strings. Quoted literal text containing those characters remains valid; supported existing paste/encoder cases must retain their behavior. This is subset validation, not general YAML import.

  FileReader completion is bound to the project, destination lifecycle draft, and edit revision captured when import begins. Discard the completion with a diagnostic if that context changed before the read finishes, including mode switching, Open, preset/start-blank, undo/redo, or another committed edit. Use a monotonic session revision or equivalent invalidation token so changing away and back does not revive a pending read. A discarded completion makes no suite or history change; a successful current completion adds exactly one case in one committed edit.

- No skill, shell, LLM, or issue mutation executes from scenarios. Structural transition analysis and the graph UI are FEAT-3501; nothing here depends on it.

## Integration Map


- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: draft migration/serialization, input normalization with provenance, frontmatter extraction and supported-subset validation, shared compiled trace, mode-valid scenario suggestions, and rubric branch/target evaluation. Extend `validateProjectStructure` for optional `scenarios` without conflating storage shape with execution validity; leave `BUILDER_PROJECT_SCHEMA_VERSION` at 1.

- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: suite editing/results, local file input, committed-edit wiring; rewrite `commit()` (line ~368), the mode-switch handler (~1298-1301), `applyPreset` (~1317-1319), `_persistDraft`/`_persistAllDrafts` (~306-317), and Open/hydration (~412, ~1469) to carry full wrappers.

  Browser integration also owns all-mode hydration, replacement/scoping of obsolete storage keys on Open, isolation between live drafts and history at initialization/restoration boundaries, and pending-import invalidation across project/draft/revision changes.

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

1. Draft parsing and every enumerated browser persistence/history path preserve full wrappers, all saved modes, detached history snapshots, semantically unfinished cases, and expectation fingerprints; project replacement cannot revive obsolete drafts (schema version stays 1).
2. Mode-specific input normalization/provenance, supported-frontmatter validation, shared compiled trace, and explicit rubric aggregate/target evaluation satisfy the execution contracts while retaining supported evaluator/conformance behavior.
3. Implement scenario editing and explicit expectation reconfirmation, verdict precedence, Run all, totals, separate winning/evaluated coverage, and stale-result feedback.
4. Boundary suggestions normalize successfully and use representable source values; local issue import extracts supported frontmatter atomically and discards stale asynchronous completions.
5. Test all modes, each browser persistence transition, import failure/stale-read atomicity, verdict combinations, raw/encoded missing values, and coverage identities; regenerate golden HTML and update docs. Record manual browser save/reload/import/preset/undo checks, including the new multi-mode, history-isolation, and delayed-read cases, using ENH-3487's existing manual-testing decision.

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

- [ ] Browser checks populate suites in two modes, reload, switch between them, and Save with both intact. Opening a project without a previously stored mode, then reloading/switching, never resurrects that old project's draft or suite.

- [ ] Live drafts and history snapshots share no mutable scenario/model/metadata objects. Open → suite edit → undo and undo → suite edit → undo restore exact pre-edit content; hydration and redo restoration obey the same isolation invariant.

- [ ] Semantically unfinished scenarios survive Save/Open/reload unchanged: missing input members/expectations, out-of-range scores, unsupported frontmatter text, removed expected targets, and stale indexes are diagnosed per case on Run. Structurally corrupt suite envelopes are rejected atomically without replacing the current project.

- [ ] Default rubric models with no authored outcomes accept assertions for `done`, `light_repair`, and `deep_repair` and match the generated high/medium/low destinations. Unknown targets, `expectedRuleIndex`, and `expectedFallback` produce rubric expectation errors.

- [ ] Mode-specific input contracts reject malformed values without treating valid absence as an error. Tests cover decision-table true/false encoding, missing lifecycle boolean/list fields showing raw absence alongside encoded zero, present null versus absence, and derived `priority_rank` source provenance.

- [ ] Verdict tests cover invalid input combined with stale fingerprints (error wins), a removed expected target (error), stale index plus target mismatch (needs review), current index plus target match/mismatch, missing fingerprints, and explicit reconfirmation followed by undo. No reconfirmation silently adopts the observed result.

- [ ] A visited-but-failing rule appears only in evaluated coverage and remains uncovered as a winning route. Tests distinguish repeated-target authored rules, authored catch-all, derived fallback, rubric branches, valid unasserted/failed assertions, and invalid model/input cases.

- [ ] A complete issue Markdown file imports successfully without parsing its body; BOM/CRLF are handled. Missing/unclosed fences, unsupported frontmatter, and read failures produce diagnostics without altering the suite. Successful import adds one unasserted case and is undoable.

- [ ] Supported-subset tests reject unquoted mappings, block scalars, tags, anchors/aliases, nested collections, and malformed flow lists, including `x: {a: b}`, `x: |`, `x: [a`, and `x: !!str 5`. Quoted literal counterparts and existing supported scalar/list/null/comment cases still work; valid paste remains fence-optional. Unsupported scenario text returns `error`; unsupported file import leaves the suite unchanged.

- [ ] Every generated suggestion for valid models passes input normalization. Decision-table and rubric bounds are respected; lifecycle priority/list suggestions encode to their intended representable boundaries, and impossible neighbors/equalities are omitted. Suggestions remain deterministic, deduplicated, and unasserted.

- [ ] Delayed-read browser checks start import, then switch modes, Open, apply a preset/start-blank, undo/redo, or commit another edit before completion. Stale completions add no case or history entry, even after switching away and back; a current successful completion adds exactly one undoable case to the captured lifecycle draft.

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

## Browser Verification Loop

_Added 2026-09-17 — closes the manual-browser-checklist gap flagged by `/ll:confidence-check` (outcome risk: browser/UI persistence paths manually verified only)._

The browser-facing ACs (1, 8, 9, 10, 14) are exercised by an on-demand Playwright loop, not a test-suite gate:

- Loop: `.loops/verify-feat-3488-browser-persistence.yaml` — generates `policy-router-builder.html` with `ll-artifact policy-builder`, runs the probes, then an LLM judge maps the report to the ACs (it can only downgrade a green run).
- Probes: `.loops/probes/feat-3488-browser-probes.mjs` — 14 scenarios tagged `needs: ENH-3487|FEAT-3488`. The FEAT-3488 ones (`scenario-suite-survives-save-open-reload-undo`, `preset-clears-only-destination-suite`, `run-all-totals-and-edit-invalidation`, `local-issue-import-offline`) report BLOCKED until the `SCENARIO_SELECTORS` block at the top of the script is filled in with the implemented element ids — **do this as part of implementation**, then run `ll-loop run .loops/verify-feat-3488-browser-persistence.yaml` before closing.
- Baseline today (pre-implementation): 8 pass, 4 blocked, 2 fail — `undo-redo-buttons-and-keys` (BUG-3502, the history-aliasing defect this issue's "History isolation" paragraph already specifies) and `open-project-with-unknown-sibling-metadata` (AC-10 full-wrapper persistence, expected to fail until implemented).
- Playwright is resolved from the invoking machine only (`LL_PLAYWRIGHT_ROOT` / `NODE_PATH` / `npm root -g`); the loop ends in `skipped-no-playwright` (a failure, never a pass) when absent. Nothing is added to `scripts/tests/` or `pyproject.toml`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-17_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Outcome Risk Factors
- Wide breadth: the change spans ~15-20 distinct sites (7+ new core.mjs signatures, 6+ rewired html.tmpl wiring points, 4 test files, 2 doc files) — scored 0/12 on Breadth.
- Moderate-to-deep per-site work: the shared compiled trace path (`traceModel`) must preserve `evaluateModel`'s existing MatchResult shape plus legacy `evaluateRules`/Python/corpus contracts while adding tracing, and full-wrapper preservation touches shared state across `commit`, mode-switch, `applyPreset`, `_persistDraft`/`_persistAllDrafts`, and Open/hydration — cross-module logic with shared state, not mechanical edits.
- Change surface: 6-10 distinct wiring sites in `policy-router-builder.html.tmpl` each require site-specific handling (not a uniform substitution) — scored 10/25 on Pattern A blast radius.
- Test coverage gap: browser/UI persistence paths (Save/Open/reload/preset/undo) rely on ENH-3487's existing manual-testing decision rather than automated coverage, per Implementation Step 5 and the acceptance criteria's "documented manual browser workflow" language.

## Session Log

- `/ll:verify-issues` - 2026-09-17T22:18:30 - `d2636fcf-cc12-43a6-bcc7-a9b3292ab5bf.jsonl`
- manual review - 2026-09-17 - applied seven pre-implementation findings: detached history snapshots, all-mode reload and project storage replacement, rubric assertion destinations, explicit frontmatter subset validation, storage-versus-execution validation, representable mode-specific suggestions, and stale asynchronous import cancellation; added corresponding browser and core acceptance checks. Existing confidence scores were not recomputed by this specification edit.

- `/ll:confidence-check` - 2026-09-17T21:41:52 - `8ed2d1e5-4f7c-4c51-b0fb-dddbf5b66162.jsonl`
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
