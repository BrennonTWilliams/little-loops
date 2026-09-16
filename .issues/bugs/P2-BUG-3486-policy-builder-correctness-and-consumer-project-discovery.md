---
id: BUG-3486
type: BUG
title: Policy builder preview, validation, and editing correctness (browser/core)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:20Z'
labels:
- policy-builder
- captured
relates_to:
- FEAT-3474
- BUG-3489
- BUG-3490
blocked_by:
- BUG-3489
blocks:
- ENH-3487
---

# BUG-3486: Policy builder preview, validation, and editing correctness (browser/core)

## Summary

Fix policy-builder browser/core correctness across Decision Table, Rubric, and Issue Lifecycle modes: preview evaluation, model validation, editing-state reconciliation, JS/Python parser parity, and generated-state-name collisions. Preview, validation, and generated YAML must agree.

**Split 2026-09-16:** runtime fragment defects (stale LLM scores, decision-table dispatch errors routing to a success outcome) moved to BUG-3489; consumer-project catalog discovery moved to BUG-3490. This issue is the JS `.mjs` + `.html.tmpl` cluster only (original defects a–e).

Captured from the 2026-09-16 whole-builder review following FEAT-3474. The focused Python/Node gate suite passed 126 tests, but direct core/runtime probes reproduced the defects below. Browser policy prevented opening local HTML; UI findings are source-derived, not a completed visual browser test.

## Current Behavior

- Decision-table Try it evaluates uncompiled boolean operators. In the seeded example, quality 99 and has-citations false previews done while compiled rules select light-repair.
- Both previews recover the winning row by its target name. Lifecycle confidence 90 matches rule 3 but highlights rule 2, which also targets implement; fallback matches lack explicit feedback.
- JavaScript accepts nonnumeric ordered comparisons and malformed targets rejected by Python. Model validation misses duplicate/reserved outcome names, missing references, unsupported mode/type combinations, incomplete actions, invalid step budgets, and inverted rubric thresholds. A user outcome named score produces duplicate YAML state keys. The shared completion-name helper only checks done before selecting finished.
- Changing a rule's field does not reconcile its stored operator with the new field type. Invalid string edits remain visible while the model retains the previous value. Adding an incomplete lifecycle rule can throw during preview compilation.
- Frontmatter Try it misreads inline comments and quoted commas in lists; the derived priority_rank handling can also disagree with Python. These yield different routing inputs.

## Expected Behavior

Every supported input has identical browser/runtime parsing and evaluation semantics; unsupported inputs produce explicit diagnostics. Invalid or incomplete models cannot be exported, and editing never silently substitutes stale values. Rule identity and fallback matches are reported accurately.

## Motivation

Users cannot trust policy decisions when the preview disagrees with execution or reports healthy output for malformed models. These are existing behavior defects and must be resolved before richer scenario testing or execution handoff relies on them.

## Proposed Solution

Add a pure model-validation pipeline shared by preview/export and a compiled evaluation result that preserves winning rule identity and per-condition results. Reconcile field/operator changes and represent invalid draft inputs explicitly. Match the Python parser/encoder for the supported frontmatter subset; reject unsupported syntax rather than guessing.

**Decisions (2026-09-16 review):**
- **Reserved-name rejection, not dynamic allocation.** `validateBuilderModel` rejects user outcome names that collide with a fixed, explicitly enumerated reserved set, exported from `policy_builder_core.mjs` as a constant (e.g. `RESERVED_STATE_NAMES`, keyed per mode) so the Node tests can pin it. Enumerated from the serializers as of 2026-09-16:
  - decision_table: `score`, `parse_scores`, `policy_dispatch`, `finished`, `failed`
  - rubric: `score`, `parse_scores`, `route_high`, `route_medium`, `done`
  - issue_lifecycle: `issue_id`, `score`, `policy_dispatch`, `done`, `failed`
  - all modes: `aggregate` (`fsm/validation/reachability.py:170` `_RESERVED`), and the route sentinels `_` / `_error`
  This matches the codebase's fixed-reserved-token convention (`FAILURE_TERMINAL_NAMES`, `_RESERVED`) and avoids `done_2`-style surprises in emitted YAML. `failed` must be reserved because BUG-3489 adds it as the decision-table failure terminal.
- **`done` stays a legal decision-table outcome name; the auxiliary terminal becomes a fixed `finished`.** `seedExample("decision_table")` (mjs ~450) names an outcome `done`, and `_doneStateName()` exists precisely to allow that — reserving `done` would make the default page load with an export-blocking diagnostic. So: `_doneStateName()`'s dynamic `done`→`finished` selection is replaced by the constant `finished` (reserved above), which is the only name the auxiliary `terminal: true` state is ever emitted under. Golden fixtures change only where `usedDoneState` is true (a finish outcome with a non-`none` action); `sample-decision-table.model.json` has no such outcome, so verify whether its YAML changes before regenerating.
- **Handler logic moves into the `.mjs` core.** There is no jsdom/playwright and no npm dependency budget, so inline `.html.tmpl` handlers cannot be tested by `node:test`. The field/operator reconciliation, draft-input state, and winner lookup in (b)–(d) are extracted as pure functions in `policy_builder_core.mjs` (e.g. `reconcilePredicateForDim`, `evaluateModel`), leaving the template as thin DOM glue. "Browser-editing coverage" in the ACs means Node tests over those pure functions, not DOM tests.
- **`priority_rank` parity follows Python:** derive it when a dimension's `raw_key == "priority_rank"` (`frontmatter_scores.py:106-115`), not when a dimension is named `priority`.
- **Supported frontmatter subset for `parseFrontmatterBlock` (defect e), stated precisely so "supported comments" and "reject rather than guess" don't conflict:** strip `#` and the rest of the line only when the `#` is at line start or preceded by whitespace and is outside single/double quotes; split flow lists (`[a, "b, c"]`) on commas outside quotes and unquote the elements; a quoted `#` or `,` is literal. Anything else the mini-parser cannot represent (block lists, nested mappings, multi-line scalars, anchors) raises a diagnostic in the Try-it hint instead of producing routing inputs.
- **Draft-input representation (defect d):** each predicate in the model carries `value` (last committed, always parser-valid) plus `draft: { text, error } | null`. The DOM input shows `draft.text` when present; `validateBuilderModel` emits an error diagnostic for any predicate with a non-null `draft`, so a rejected edit blocks export instead of silently exporting the previous value. `reconcilePredicateForDim(pred, newDimType)` resets `op` to the new type's default and clears `value`/`draft` when the stored op is not legal for the new type.
- **Export surfaces:** "disable export" means the Copy button (`#copy-btn`, tmpl ~217) and the Download button (`#download-btn`, tmpl ~218) are disabled while any error-severity diagnostic exists; the YAML preview still renders alongside the diagnostics so the user can see what would be emitted.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl. (`cli/artifact/policy_builder.py` → BUG-3490; `loops/lib/policy-router.yaml` → BUG-3489.)
- Dependent contracts: scripts/little_loops/fsm/policy_rules.py and scripts/little_loops/fsm/frontmatter_scores.py; generated fixtures in scripts/tests/fixtures/policy_builder/.
- Similar patterns: `_serializeIssueLifecycle()`'s explicit `failed:` terminal; `$("add-dim").onclick`'s existing duplicate-name check (tmpl ~898) as the shape for outcome-name validation.
- Tests: scripts/tests/test_policy_builder_emit.py, scripts/tests/test_policy_builder_corpus.py, scripts/tests/test_policy_builder_node_gate.py, scripts/tests/test_frontmatter_scores.py, scripts/tests/js/policy_validator.test.mjs; add browser-editing coverage under the local pytest gate.
- Configuration: preserve existing project configuration and offline artifact behavior.
- Coordination: BUG-3489 also edits `_serializeDecisionTable()` and regenerates the same golden fixtures; land BUG-3489 first (small) so this issue's reserved-name list includes `failed` and the fixtures are regenerated once.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/route_table.py` — defines `_detect_shadows()` (not `policy_rules.py`) and `PolicyRuleExtractor.extract()`; it is the actual Python oracle the conformance corpus pins JS `detectShadows()` against, and a second Python-side parser of `context.policy_rules` via `parse_rules()`. Should be named alongside `fsm/policy_rules.py` under Dependent contracts. [Agent 1 finding]
- `scripts/little_loops/fsm/policy_rules.py` — `grammar_spec()` and `_py_pattern_to_js()` (imported at `cli/artifact/policy_builder.py:63,70,76`) are the Python oracle for the JS-side predicate regex stamped into the emitted page; `test_policy_rules.py`'s `test_ordered_op_non_numeric_raises`/`test_invalid_target_name_raises` pin the exact behaviors `parseRuleTable`/`parsePredicate` must be made to match for defect (c). [Agent 1 finding]
- `scripts/little_loops/fsm/validation/reachability.py` — calls `parse_rules()` inside a policy-dims-scored reachability check (catches `ValueError`); a regression-risk consumer of `policy_rules.py`'s parsing contract, not itself modified by this issue. [Agent 1 finding]
- `scripts/little_loops/fsm/schema.py` — `FAILURE_TERMINAL_NAMES` frozenset; the new decision-table failure terminal needs no schema change only if it reuses the name `"failed"` (matching `_serializeIssueLifecycle`'s existing precedent) — a different name requires either an explicit `failure: true` field on the emitted state or registration here. [Agent 2 finding]

### Tests (wiring additions)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — byte-exact golden-HTML comparison; breaks on any `.mjs`/`.tmpl` edit, requires regenerating `fixtures/policy_builder/golden_policy_router_builder.html`. [Agent 2/3 finding]
- `scripts/tests/js/policy_validator.test.mjs::"serializeLoopYaml matches golden decision-table fixture"`, `scripts/tests/test_policy_builder_emit.py::test_golden_yaml_validates`, and `scripts/tests/test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode[sample-decision-table.model.json]` — all pinned to `fixtures/policy_builder/sample-decision-table.yaml`/`.model.json`, whose `_error: escalate` route will change once decision-table mode gains a dedicated failure terminal; regenerate both fixtures together. [Agent 2/3 finding]
- `scripts/tests/test_policy_rules.py` — Python oracle tests (`test_ordered_op_non_numeric_raises`, `test_invalid_target_name_raises`, `grammar_spec`/`_py_pattern_to_js` assertions) that new JS parity tests/corpus cases must match. [Agent 1/3 finding]
- `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json` — no existing case exercises `#`-comment stripping, a quoted comma inside a flow-list, or a dimension where `priority`/`priority_rank` are decoupled; add new cases, since the current 17 cases cannot distinguish old from fixed behavior. [Agent 3 finding]
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — add cases targeting `parseRuleTable`'s error-raising behavior (nonnumeric ordered comparisons, malformed targets); `evaluate_cases` itself is unaffected since compiled-input evaluation behavior doesn't change. [Agent 2/3 finding]
- _(policy_parse_scores test harness note moved to BUG-3489.)_

### Documentation (wiring additions)

_Wiring pass added by `/ll:wire-issue`:_
- _(Catalog doc updates moved to BUG-3490.)_

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Fixture/corpus files backing the differential Python/JS parity convention already in force (`scripts/tests/fixtures/policy_builder/`):
- `conformance_corpus.json` — `evaluate_cases`/`shadow_cases`, pinning JS `evaluateRules`/`detectShadows` against Python `evaluate_rules`/`_detect_shadows`, consumed by `scripts/tests/js/policy_validator.test.mjs` and `scripts/tests/test_policy_builder_corpus.py`.
- `frontmatter_encoding_corpus.json` — pins JS `encodeFrontmatterScores`/`parseFrontmatterBlock` against Python `encode_frontmatter_scores` (`fsm/frontmatter_scores.py`).
- `sample-*.model.json` + `sample-*.yaml` — golden model-to-YAML pairs (decision-table, rubric, issue-lifecycle) asserted byte-for-byte equal from both languages.
- `golden_policy_router_builder.html` — structural/markup golden for the generated page.

Conventions in force (codebase-pattern-finder, evidence cited per rule):
- **Differential parity, not shared validation**: this codebase's established pattern for keeping Python and JS in sync is corpus-pinned parity tests (above), not a single shared validator called from both a preview and an export path — no example of the latter shape exists anywhere in the repo (searched `^def validate` plus every `validate_fsm`/`_detect_shadows`/`renderMessages` call site, no path filter). `frontmatter_scores.py:10-14` and `policy_builder_core.mjs:1-7` both carry explicit "mirrors" docstrings stating the two implementations are pinned against the same conformance corpus so they can't silently drift — the proposed `validateBuilderModel` would be new in kind, not an extension of an existing shared-validator shape.
- **FSM failure routing**: the established convention across ~80 loop YAML files (e.g. `general-task.yaml:1326-1328`, `rn-build.yaml:1394-1403`) is a dedicated failure terminal (typically named `failed`), driven by `on_error:`/`on_max_steps:` and marked via `schema.py`'s `FAILURE_TERMINAL_NAMES` frozenset (implicit `failure: true` for legacy names `failed`/`error`/`aborted`/`finalize_aborted`) or an explicit `failure: true` field for other names. `_serializeIssueLifecycle()` (mjs 974-1041) already follows this convention (explicit `failed:` terminal, `on_error: failed`); `_serializeDecisionTable()` (mjs 800-804) does not — it has no dedicated failure terminal at all.
- **Reserved/generated-name collision avoidance**: the only *dynamic* used-name-set-and-fallback example in the codebase is `_doneStateName()` itself (mjs 733-739) — the file this issue already touches. Elsewhere the codebase uses *fixed* reserved tokens instead (`_RESERVED = {"aggregate"}` in `fsm/validation/reachability.py:170`; `FAILURE_TERMINAL_NAMES` in `schema.py:26-35`), a different shape (static exemption vs. dynamic collision detection) — no second dynamic-collision example exists to generalize from.
- **JS test harness**: `scripts/tests/js/policy_validator.test.mjs` is the only `.test.mjs` file in the repo; it uses Node's built-in `node:test` + `node:assert/strict` with zero npm dependencies, gated into the local suite via `scripts/tests/test_policy_builder_node_gate.py` (skips gracefully below Node 22 or when absent).

## Program Design

### Types

Proposed MatchResult carries ruleIndex, target, isFallback, and conditionResults; Diagnostic carries severity, field path, and message. Predicate gains `draft: { text: string, error: string } | null` alongside the committed `value` (see Decisions). `RESERVED_STATE_NAMES` is an exported per-mode constant.

### Signatures

Proposed new JS core contracts:
- `validateBuilderModel(model) -> DiagnosticList`
- `evaluateModel(model, scores) -> MatchResult`
- `reconcilePredicateForDim(pred, newDimType) -> Predicate`
- `export const RESERVED_STATE_NAMES: { decision_table: Set, rubric: Set, issue_lifecycle: Set }`

Keep evaluateRules' existing target-returning API compatible.

### Call Path

Target wiring: `updatePreview` -> `buildModel` -> `validateBuilderModel` -> `serializeLoopYaml`.

Existing anchors this extends: `evaluateRules` and `parseRuleTable` in `scripts/little_loops/templates/policy_builder_core.mjs` (compiled evaluation + parity), `_serializeRulesText` (boolean compile step reused by the Try-it path), `detectShadows` (absorbed into `validateBuilderModel`), and Python oracle `evaluate_rules` in `scripts/little_loops/fsm/policy_rules.py`.


### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Current (pre-fix) signatures, confirmed by direct code reading:

- `evaluateRules(rules, scores) -> string | null` (`policy_builder_core.mjs:239-245`) — returns only the matched rule's `target` string today; no rule index or identity is returned. This is the gap the proposed `MatchResult` type closes.
- `parseRuleTable(text, grammar?) -> Array<{predicates, target, isCatchall}>` (`policy_builder_core.mjs:544-575`) — `grammar` is optional, falling back to `DEFAULT_PRED_RE`.
- `_find_plugin_root() -> Path` (`cli/action.py:179-182`, thin wrapper over `skill_expander.py:25-35`) — no arguments; checks `CLAUDE_PLUGIN_ROOT` env var, else falls back to the package's installed location.
- `validateBuilderModel` has no definition anywhere in the codebase today (repo-wide search, no hits outside this issue file) — confirms it is genuinely new code, not a rename/refactor of an existing function.

Corrected current call path (the issue's proposed `updatePreview -> buildModel -> validateBuilderModel -> serializeLoopYaml` describes target-state wiring; `validateBuilderModel` is not yet implemented, so today's actual path is different): `updatePreview()` (tmpl 809-816) calls `buildModel()` (tmpl 248-268), then independently and in fixed but unordered-relative-to-each-other sequence calls `serializeLoopYaml(model)` (writing to the YAML preview unconditionally), `computeSummary(model)`, `renderMessages(model)` (tmpl 780-807 — today's only in-page validation-like surface, combining the exported `detectShadows()` from `policy_builder_core.mjs` with ad hoc inline checks that live only in the `.html.tmpl` file and are therefore untested by the Node gate), and `updateTryIt()`. None of these gate each other today — YAML serialization is never blocked on what `renderMessages` finds.

## Implementation Steps

1. Capture each reproduced mismatch in targeted regressions (Node tests over extracted core functions plus corpus cases).
2. Unify model validation, compiled evaluation, parser parity, and reserved-name rejection.
3. Repair editing-state synchronization, fallback feedback, and export gating.
4. Update fixtures and user-facing behavior descriptions; run focused gates and the required local suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate `fixtures/policy_builder/golden_policy_router_builder.html` after any `.mjs`/`.tmpl` edit — required for `test_enh3035_artifact_template_kit.py` to keep passing.
- Decision-table failure terminal and its fixture regeneration are owned by BUG-3489 (name decided: `failed`).
- Add new cases to `frontmatter_encoding_corpus.json` (comment stripping, quoted comma in a flow-list, decoupled `priority`/`priority_rank`) and to `conformance_corpus.json` (`parseRuleTable` error cases for nonnumeric ordered comparisons and malformed targets) rather than modifying existing cases.
- Cite `scripts/little_loops/fsm/route_table.py::_detect_shadows` (not `policy_rules.py`) as the Python oracle for JS `detectShadows` parity work.
- Update `docs/guides/POLICY_ROUTER_GUIDE.md`/`CLI.md` for validation diagnostics and reserved names (`CONFIGURATION.md`/`API.md` catalog updates moved to BUG-3490).

## Impact

- Priority: P2 — routing decisions and generated loops can be wrong despite a healthy preview.
- Effort: Medium — browser/core fixes with differential tests (runtime and discovery split out).
- Risk: Medium — preserve valid existing rules while tightening malformed-input behavior.
- Breaking change: No intended change to valid rule semantics; invalid exports become blocked.

## Steps to Reproduce

1. Import seedExample, evaluateRules, parseRuleTable, and _serializeRulesText from scripts/little_loops/templates/policy_builder_core.mjs in Node. Evaluate the default seed with quality 99 and has-citations 0 using raw rules and compiled rules; compare done versus light-repair.
2. Evaluate the lifecycle seed with status open and confidence_score 90. Compare the actual matching rule index with the template's first matching target-name lookup.
3. Compare JavaScript/Python parsing of confidence_score:>=high -> implement and quality:>=90 -> bad/target; only Python rejects both.
4. Compare encoders on confidence_score with an inline comment, a flow-list item containing a quoted comma, and priority high accompanied by priority_rank 1.

## Root Cause

The template's updateTryIt and updateFrontmatterTryIt use different evaluation paths and infer row identity from a nonunique target. Core parseRuleTable does not enforce the full Python parser contract. renderMessages is a small hint collector rather than model validation. Generated state names share a namespace with user outcomes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Per-defect file:line anchors, confirmed by direct code reading:

- **(a) Decision-table Try-it uses uncompiled boolean ops** — `policy-router-builder.html.tmpl` `updateTryIt()` (~line 730) calls `evaluateRules(model.rules, scores)` on the **raw** rules, whose boolean predicates still carry literal ops `"==true"`/`"==false"`. In `policy_builder_core.mjs` `evalPredicate()` (lines 193-231), `"==true"`/`"==false"` are absent from `ORDERED_OPS`, fall to the string-compare branch, and because `op` is literally `"==true"` (not `"=="`) the code takes the `!=` arm — `==true` predicates evaluate as `!=`. Contrast: `updateFrontmatterTryIt()` (tmpl lines 754-778) compiles first via `parseRuleTable(_serializeRulesText(model))` before evaluating — the raw-rules path is not used there.
- **(b) Both previews recover winner by target name** — `evaluateRules()` (mjs lines 232-245) returns `string | null` only — no rule index/identity. Both `updateTryIt()` (tmpl line 733) and `updateFrontmatterTryIt()` (tmpl line 775) recover the row via `model.rules.findIndex(r => r.target === winnerTarget)`, which returns the *first* rule with that target, not the rule actually matched. Both also silently no-op (no fallback indicator) when `winnerTarget` doesn't match any `model.rules` entry (catch-all fired).
- **(c) Validation gaps** — Python `_parse_predicate()` (`fsm/policy_rules.py:72-95`) rejects non-numeric values for ordered ops via `float(value)`; JS `parsePredicate()` (mjs lines 525-535) never performs this check. Python's `_TARGET_PATTERN = re.compile(r"^[\w][\w\-]*$")` (`policy_rules.py:37`, enforced 140-144) rejects malformed targets; JS `parseRuleTable()` (mjs 544-575) only checks for an empty string (557-559). `$("add-outcome").onclick` (tmpl 906-913) has no duplicate/reserved-name check, unlike `$("add-dim").onclick` (tmpl 886-905) which does check duplicates (898). `_doneStateName()` (mjs 733-739) returns `"finished"` if `"done"` is used, but never checks whether `"finished"` is *also* already used. `$("f-maxsteps").oninput` (tmpl 881) only guards falsy values (`Number(...) || 1`), so negative step budgets pass through.
- **(d) Editing reconciliation** — `dimSel.onchange` in `renderRules()` (tmpl line 604) sets `p.dim` but never resets/validates `p.op` against the new dimension's type. The string-value `oninput` handler in `renderRules()` (tmpl 609-619) returns early on invalid input without resetting `valInput.value`, leaving the DOM and model showing different values. `updateFrontmatterTryIt()`'s call to `parseRuleTable(_serializeRulesText(model))` (tmpl ~758) has no try/catch (unlike the `parseFrontmatterBlock` call just above it, tmpl 762-767); a freshly-added predicate has `value: ""` (tmpl line 919 / 637), which fails `_PRED_PATTERN` in `parsePredicate()` (mjs 525-535) and throws uncaught.
- **(e) Frontmatter Try-it parser divergence** — `parseFrontmatterBlock()` (mjs 1094-1148) has no `#`-comment stripping, unlike Python's real `yaml.load`-based `parse_frontmatter()` (`frontmatter.py`). The flow-list branch (mjs 1133-1136) splits on every comma via `.split(",")`, breaking on a quoted element containing a literal comma. `encodeFrontmatterScores()` (mjs 1198-1209) derives `priority_rank` when a dimension is *named* `"priority"`; Python's `encode_frontmatter_scores()` (`frontmatter_scores.py:106-115`) derives it when a dimension's `raw_key == "priority_rank"` — different trigger keys that only coincide because `BUILTIN_FRONTMATTER_DIMENSIONS` (mjs 85-95) always ships both together.
- **(f) Stale score files** _(moved to BUG-3489)_ — the reusable clean-slate pattern is `_clean_slate(run_dir: Path)` in `fsm/frontmatter_scores.py:158-169` (globs and unlinks `rubric-dim-*.txt` and `rubric-aggregate.txt`), called from `main()` (`frontmatter_scores.py:200`) before writing new scores. The `policy_parse_scores` fragment (`loops/lib/policy-router.yaml`, lines 84-116) has no equivalent — it only writes files for `DIMENSION:` lines found in the current pass and never deletes pre-existing `rubric-dim-*.txt` files, which `policy_table_dispatch` (same file, 197-208) then reads indiscriminately via `os.listdir(run_dir)`.
- **(g) Dispatch errors route to first outcome** _(moved to BUG-3489)_ — `_serializeDecisionTable()` (mjs 800-804): `errorState = tokens[0] || fallbackState` — `tokens[0]` is whichever outcome the first authored rule targets, with no dedicated failure terminal ever emitted for decision-table mode. Contrast: `_serializeIssueLifecycle()` (mjs 974-1041) emits an explicit `failed:` terminal (line 1037) and routes `_error: failed` unconditionally (line 1022).
- **(h) Catalog discovery** _(moved to BUG-3490)_ — confirmed: `_load_skill_catalog()` (`cli/artifact/policy_builder.py:21-53`) globs only `project_root/"skills"` and `project_root/"commands"`, and does not call `_find_plugin_root()` (`cli/action.py:179-182` → `skill_expander.py:25-35`) anywhere in that file — the only caller of `_load_skill_catalog` is `cmd_policy_builder()` (line 79).

## Acceptance Criteria

- [ ] Python/JS differential cases agree for boolean rules, missing fields, supported frontmatter comments/lists/quoting, derived priority, malformed targets, and nonnumeric ordered comparisons.
- [ ] Regression tests assert actual winning row identity for repeated targets and explicit fallback matches.
- [ ] Invalid/incomplete models show diagnostics and disable export; field changes, field removal, and rejected draft edits cannot silently export previous or incompatible values.
- [ ] Duplicate/reserved outcome names (the enumerated `RESERVED_STATE_NAMES` per mode, including `finished`, `failed`, and `aggregate`) are rejected by `validateBuilderModel`; `done` remains a valid decision-table outcome and the seed example loads with zero error diagnostics; no model can produce duplicate YAML keys or broken transitions; valid models in all three modes pass runtime validation.
- [ ] Invalid/incomplete models disable both `#copy-btn` and `#download-btn`; a predicate with a non-null `draft` is an error diagnostic.
- [ ] Editing/reconciliation logic lives in `policy_builder_core.mjs` as pure functions covered by `scripts/tests/js/policy_validator.test.mjs`; the template contains only DOM wiring.
- [ ] Existing offline generation, theme behavior, and valid model semantics remain covered by the local Python/Node suite.

## Scope Boundaries

Includes browser/core correctness and validation feedback. Excludes runtime fragment fixes (BUG-3489), catalog discovery (BUG-3490), saved projects, UI reorganization, named scenario suites, and connected execution (ENH-3487, FEAT-3488).

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Project-enriched artifacts and shared generator architecture |
| Reference | docs/reference/CLI.md | Policy-builder generation and validation contract |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Rule grammar, preview semantics, and lifecycle mode |

## Status

**Open** | Created: 2026-09-16 | Priority: P2


## Session Log
- review - 2026-09-16 - added `blocked_by: BUG-3489`; enumerated `RESERVED_STATE_NAMES`; `done` stays legal, auxiliary terminal fixed to `finished`; defined frontmatter subset, draft-input shape, and export surfaces; removed BUG-3490 leftovers from Integration Map
- split - 2026-09-16 - defects f/g → BUG-3489, h → BUG-3490; decisions recorded in Proposed Solution
- `/ll:wire-issue` - 2026-09-16T21:29:31 - `0e35d235-ff66-480a-930e-d4d9ddd5eeb9.jsonl`
- `/ll:refine-issue` - 2026-09-16T21:10:28 - `23738f99-b471-4d7b-a1d6-399ffa424bef.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
