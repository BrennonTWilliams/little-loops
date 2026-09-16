---
id: FEAT-3488
type: FEAT
title: Policy builder richer scenarios and connected execution
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
- BUG-3489
- BUG-3490
- ENH-3487
relates_to:
- FEAT-3474
unproven_mechanism: true
spike_attempted: true
spike_completed: true
---

# FEAT-3488: Policy builder richer scenarios and connected execution

## Summary

Extend policy-builder with richer scenarios and optional connected execution: named test cases with expected outcomes, explainable rule evaluation, reusable example suites, and a host-mediated path from a validated project to a run. Keep offline authoring and scenario evaluation fully functional.

Captured from the 2026-09-16 review following FEAT-3474, as the third requested workstream.

## Current Behavior

Try it handles one transient sample and highlights a rule without explaining individual conditions or asserting an expected outcome. There is no saved scenario suite, boundary-case generation, actual issue-file import flow, or builder-to-run handoff. The result pane offers YAML Copy/Download and a validation hint. Existing ll-artifact serve provides a live event/history dashboard, not a policy-builder write/run endpoint.

## Expected Behavior

Users save named examples, run the entire suite locally, see expected/actual outcomes and why each condition matched or failed, and identify uncovered or shadowed rules. An optional connected mode resolves project inputs, validates an immutable exported model/YAML revision, and hands a run request to the host with observable acceptance or failure. Previewing scenarios never executes action bodies.

## Motivation

Single-sample inspection does not establish confidence across a policy's edge cases. A reproducible suite catches regressions, and a clear execution handoff removes the gap between downloading YAML and using it without conflating simulation with real mutation.

## Proposed Solution

- Store named scenarios with mode-specific input, expected outcome, and optional expected rule identity in the versioned builder project. Add create/duplicate/delete, Run all, pass/fail totals, condition explanations, fallback feedback, and rule coverage.
- Suggest missing-field and numeric-boundary cases. Expected outcomes must be authored/reviewed independently; do not derive test oracles from the current policy itself.
- Show transition graphs and structural repeated-action/cycle warnings. Distinguish deterministic routing from action effects; any mocked post-action values must be labeled and cannot be presented as predictions of an LLM call.
- Support local issue-file import offline. Optional connected mode loads issues from the selected project and validates generated YAML through the canonical Python path before handoff.
- Adopt the existing artifact control contract's host-mediated ask-to-run-prompt level for new-run requests. Specify the supported transport during refinement; do not turn the current read-only ll-artifact serve routes into an implicit shell API. New-run handoff is separate from level-3 interaction with an already running FSM.
- Bind each request to the validated policy revision, project, and issue ID. Expose request acceptance, rejection, failure, and a run identifier when available; use existing host/runner/event infrastructure and prevent duplicate submissions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- No versioned "saved project" schema exists yet in the artifact-template layer. `scripts/little_loops/templates/policy_builder_core.mjs` and `policy-router-builder.html.tmpl` have no `schemaVersion`, `serializeBuilderProject`, or `parseBuilderProject` symbol (repo-wide search, no hits outside issue text); the template's only `localStorage` use stores just the theme toggle (`"ll-policy-builder-theme"`). The versioned project envelope this issue's scenario schema extends is itself only proposed, not yet implemented, in `ENH-3487` (`blocked_by`) — the `BuilderProject`/`serializeBuilderProject`/`parseBuilderProject` names there do not exist in source yet.
- No render target in this codebase has ever declared Artifact Control Level 2 ("ask-to-run-prompt"). `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Declared levels by render target" table lists only level 1 (`html-anything.yaml` dashboards, `ui://` resources, `ll-artifact serve`'s event page) and level 3 (`ll-loop run --serve`'s dashboard, via `LocalBridgeTransport`/`_handle_interaction()` in `scripts/little_loops/transport.py`). The documented closest analog, `HandoffBehavior.SPAWN` (`scripts/little_loops/fsm/handoff_handler.py`), is explicitly called a non-identical analog in the issue that wrote this contract (ENH-3307): it is triggered by the executor detecting a signal in its own loop output, not by a user interacting with a rendered artifact page.
  > ⚠ Unproven mechanism — no level-2 render target ever built
- Level 3's concrete mechanism (the only implemented host-mediated request/response in the codebase) responds to a POST with a bare `204` before touching its inbound queue; accept/reject/result is only observable asynchronously over an already-open SSE stream, not returned synchronously in the POST response (`LocalBridgeTransport._handle_interaction()`, `scripts/little_loops/transport.py`). This shape is not a drop-in template for level 2 (host-decision, not FSM-owned) — any level-2 mechanism this issue designs needs its own accept/observe contract.
- `scripts/little_loops/mcp_server/resources.py` has no `policy_builder`/`policy-router` resource kind and no `ArtifactControlLevel`-valued field on `_ResourceEntry` — the doc that defines that field names it an explicit, not-yet-built forward slot (`docs/reference/ARTIFACT_CONTROL_LEVELS.md`).
- No persistent request-ID/idempotency-key ledger exists anywhere in this codebase for deduplicating an externally-submitted request. Three narrower conventions exist instead: an in-memory `set()` guard scoped to one orchestrator process (`scripts/little_loops/parallel/orchestrator.py:219`), a filesystem sentinel-file-per-key (`scripts/little_loops/rn_synth_queue.py`'s `done/<node_id>.done`), and a declarative (non-enforcing) `idempotent_hint` MCP tool annotation (`scripts/little_loops/mcp_server/tools.py`). None is a request-ID ledger the run-request deduplication this issue proposes could reuse directly.
- No reusable boundary-value/missing-field test-case generation utility exists (JS or Python) outside test-only Hypothesis strategies inlined in individual `scripts/tests/*.py` files (e.g. `test_fsm_route_properties.py`'s `@st.composite route_matrix`) — each is scoped to that file's own regression suite, not importable by production code.
- No `FileReader`/local-file-import convention (`<input type=file>`, drag-drop) exists anywhere in `scripts/little_loops/templates/` — the local issue-file import this issue proposes has no existing browser-side file-reading pattern to follow in this codebase.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py.
- Integration points to refine: scripts/little_loops/cli/artifact/serve.py, scripts/little_loops/mcp_server/resources.py, scripts/little_loops/fsm/validation/, and existing host/event handoff interfaces. These are candidates, not authorization to modify every transport.
- Similar patterns: shared compiled evaluator and saved-project model from the preceding workstreams; artifact control levels; project-enriched snapshots.
- Tests: scripts/tests/js/policy_validator.test.mjs and policy-builder Python gates; add scenario/serialization tests and mocked connected-handoff integration tests under local pytest.
- Configuration: connected mode is opt-in; existing offline generation remains the default.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/artifact/__init__.py:48` — imports `cmd_policy_builder` from `policy_builder.py`
- `scripts/little_loops/cli/artifact/__init__.py:197` — dispatches `cmd_policy_builder(args, logger)` when `args.command == "policy-builder"`
- `scripts/little_loops/cli/__init__.py:52` — imports the `cli/artifact` package (transitive impact)
- `scripts/little_loops/cli/artifact/serve.py` — imported by `cli/artifact/__init__.py:50`; also imported by `scripts/tests/test_feat3323_sse_bridge.py:84`
- `scripts/tests/test_enh3035_artifact_template_kit.py:19` (imports `policy_builder.py`), `:65` (`test_policy_builder_renders_byte_identically_to_golden_fixture` calls `cmd_policy_builder`)
- `scripts/tests/test_artifact_templatize.py:13` — imports `policy_builder.py`
- `scripts/tests/test_policy_builder_emit.py` — imports `policy_builder.py`; contains `test_golden_yaml_validates`, `test_golden_rubric_yaml_validates`, `test_golden_issue_lifecycle_yaml_validates`, each calling `load_and_validate` against static checked-in fixtures

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:731,773` — `updateTryIt()`/`updatePreview()` call `evaluateRules(model.rules, scores)` / `evaluateRules(compiled, scores)`; must be updated in lockstep if `evaluateRules`'s return shape changes to carry per-condition traces for `ScenarioResult.conditions`
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:787` — `renderMessages(model)` calls `detectShadows(model.rules)`
- `scripts/little_loops/templates/policy_builder_core.mjs:1216-1237` — `window.PolicyBuilderCore` browser-global export object; byte-mirrored verbatim in `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html:1618` — any new export (e.g. `runScenarioSuite`, `evaluateScenario`, `buildRunRequest`) must be added to both
- `scripts/little_loops/fsm/__init__.py:120,170,203,254` — re-exports `HandoffBehavior` and `load_and_validate` in its public `__all__`
- `scripts/little_loops/fsm/validation/__init__.py:160,175` — re-exports `load_and_validate` (distinct from `structural_rules.py`, which defines it)
- `scripts/little_loops/fsm/loop_paths.py:101,121` — `load_loop()`/`load_loop_with_spec()` call `load_and_validate`
- `scripts/little_loops/fsm/executor.py:1087` — `FSMExecutor._execute_sub_loop()` calls `load_and_validate`
- `scripts/little_loops/fsm/persistence.py:1018,1032` — `PersistentExecutor.__init__` constructs `HandoffHandler(HandoffBehavior(fsm.on_handoff))`, the closest existing analog to a level-2 handoff decision point
- `scripts/little_loops/cli/loop/run.py:644-647` — `cmd_run()` constructs `ServeContext(events_url=..., interaction_url=bridge.url + "interaction")`, the only existing caller that populates `interaction_url` with a real value (vs. `serve.py`'s `None`)
- `scripts/little_loops/cli/artifact/dashboard.py:151,342-343` — `ServeContext.interaction_url` field; `build_dashboard_html()` derives `serve_interaction_enabled`/`serve_interaction_url_js` from it
- `scripts/little_loops/templates/dashboard.llat/manifest.yaml:49` and `template.html.j2:393` — consume the derived `serve_interaction_url_js` value via `fetch(...)`
- `scripts/tests/test_policy_builder_corpus.py:21-28` (`test_evaluate_cases_match_canonical`) — asserts `evaluate_rules(...) == case["expected_target"]` (bare string) against `scripts/tests/fixtures/policy_builder/conformance_corpus.json`'s flat schema; this is the **Python** canonical `little_loops.fsm.policy_rules.evaluate_rules`, a separate function from the JS `evaluateRules` in `policy_builder_core.mjs` but coupled to the same corpus contract — note BUG-3486 already plans a `MatchResult`-shaped return here
- `scripts/tests/test_handoff_handler.py` — `TestHandoffBehavior`/`TestHandoffHandler`/`TestHandoffResult` exercise `HandoffBehavior.SPAWN`/`.PAUSE`/`.TERMINATE`, the nearest existing test convention for a handoff-decision state machine
- `scripts/tests/test_feat3304_artifact_dashboard.py:855,890,1035,1053,1082` — exercises `ServeContext(interaction_url=...)`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- JS core logic (`evaluateRules`, `detectShadows`, `serializeLoopYaml`, `parseRuleTable`, etc.) is tested via `node:test` in `scripts/tests/js/policy_validator.test.mjs` against `scripts/tests/fixtures/policy_builder/conformance_corpus.json`, gated into the enforced pytest suite by `scripts/tests/test_policy_builder_node_gate.py` (shells out to `node --test`, skips gracefully when Node < 22, per CLAUDE.md's CI policy). `scripts/tests/test_policy_builder_emit.py` covers a different surface — `cmd_policy_builder()` HTML generation, golden-YAML validation, and structural/accessibility assertions — and does not unit-test JS logic itself. New scenario-suite JS logic belongs in the `node:test` layer; new Python-side connected-handoff/validation logic belongs in `test_policy_builder_emit.py` or a new sibling test module.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Declared levels by render target" table is asserted verbatim by `scripts/tests/test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT` pins `"notify"`, `"ask-to-run-prompt"`, `"host-owned"` literally) — a new policy-builder row must preserve those exact level-name strings.
- `scripts/little_loops/cli/artifact/serve.py`'s `cmd_serve` passes `interaction_url=None` and declares Level 1 (notify) only — it has no FSM executor backing it, unlike `ll-loop run --serve` (Level 3). A new-run handoff cannot simply extend `serve.py`'s existing routes without adding the executor/interaction machinery `serve.py` today deliberately lacks.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5079-5095` (`#### ll-artifact policy-builder`) — currently documents only `-o/--output`; a new-run/connected-mode flag needs a new Flags-table row and Example line
- `docs/reference/CLI.md:5186-5219` (`#### ll-artifact serve`) — currently documents only `--port`; needs updating if the level-2 transport is wired through `serve.py`
- `docs/reference/API.md:11078` — `assemble_tool_catalog` cites `cli/artifact/policy_builder.py:_load_skill_catalog()` by name; stale if that function is renamed/restructured for local issue-file import
- `docs/reference/CONFIGURATION.md:948-958` (`### artifacts`) — needs a new key-table row if an opt-in connected-mode config key is added
- `docs/reference/EVENT-SCHEMA.md:1815-1828` (`## Reserved Event Names`) — reserves only `artifact_interaction` for level 3 today; a level-2 accept/reject/run-id status surfaced via EventBus would need a new reserved-event row and schema file (contingent on transport choice)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs:45-46,307-308,312-313` — asserts `evaluateRules(...)` equals a bare winning-target string; will break if the return shape changes to carry per-condition traces
- `scripts/tests/test_policy_builder_corpus.py::test_evaluate_cases_match_canonical` — same bare-string assertion against the Python `evaluate_rules`/corpus contract (see Dependent Files)
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — the closest existing precedent for a named-scenario-suite-with-expected-outcome fixture (shared JS/Python consumers); model the new scenario-suite schema after this pattern
- `scripts/tests/test_orchestrator.py:2087-2098,2268-2289` (`test_idempotent_across_calls`, `test_failure_leaves_branch_retryable`) — existing dedup-by-side-effect-count test convention for the in-memory `set()` guard; model the new request-ledger dedup test after this style
- `scripts/tests/test_rn_refine.py:1370-1378` (`test_mark_complete_touches_done_sentinel_and_is_idempotent`) — existing sentinel-file idempotency test convention
- No test in the repo calls an MCP tool twice and asserts a dedup/no-op outcome for `idempotent_hint` — genuine coverage gap; the new Level-2 ledger's dedup test has no MCP-layer precedent to follow
- `scripts/tests/test_wiring_reference_docs.py` `DOC_STRINGS_PRESENT`/`DOC_FILES_MUST_EXIST` — pins literal strings against `docs/reference/ARTIFACT_CONTROL_LEVELS.md`; a new level-2 policy-builder row should extend the "Existing / planned examples" table (`docs/reference/ARTIFACT_CONTROL_LEVELS.md:56-59`), not the three-level definition table, to avoid tripping this test
- `scripts/tests/test_fsm_schema_fuzz.py:35-80` (`malformed_evaluate_config`) and `scripts/tests/test_fsm_route_properties.py:25-37` (`route_matrix`) — closest existing Hypothesis `@st.composite` conventions to model boundary/missing-field scenario-suggestion generation after (no JS-side property-testing library exists in the repo)
- `scripts/tests/test_policy_builder_emit.py::test_no_internal_jargon_in_visible_markup` (`:150-155`) — denylists "predicate" and other internal jargon from visible markup; new condition-explanation UI text must avoid these literal terms
- `scripts/tests/test_policy_builder_emit.py::test_rubric_mode_has_no_dt_only_affordances` (`:209-221`) and `test_single_mode_toggle` (`:199-201`) — pin fieldset IDs and mode-switch count; a new scenario-suite fieldset needs its own ID wired into `applyModeVisibility()` without tripping these
- **Spike promotion** (`scripts/tests/spike/level2_run_handoff/` → `scripts/little_loops/spike/level2_run_handoff/`): `test_level2_run_handoff.py:13-24` imports must move from `scripts.tests.spike.level2_run_handoff.*` to `little_loops.spike.level2_run_handoff.*`; `test_spike_does_not_import_local_bridge_transport` (`:124-147`)'s AST-based guard must travel with the promoted module. Confirmed fully isolated — nothing outside the spike's own test imports it.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1998-2041` — the `artifacts` object has `"additionalProperties": false`; an opt-in connected-mode key cannot be added to `.ll/ll-config.json` without a new schema key here
- `scripts/little_loops/config/features.py:1319-1332` (`BridgeEventsConfig`) — existing precedent that `ll-artifact serve` deliberately has **no `enabled` config key** ("a config flag that refuses an explicit command is bad UX"); a connected-mode toggle should follow this CLI-flag-not-config-flag precedent or explicitly justify breaking from it
- `scripts/little_loops/cli/artifact/__init__.py:138-148` — the `policy-builder` argparse subparser only defines `-o/--output`; a new-run/connected-mode flag or subcommand must be registered here, plus a matching Example/Exit-code line in the top-level epilog (`:79-134`)

## Program Design

### Types

Proposed Scenario carries id, name, input, expectedTarget, and optional expectedRuleIndex. ScenarioResult carries scenarioId, actualTarget, ruleIndex, conditions, and passed. RunRequest carries requestId, projectId, modelRevision, yaml, and issueId.

### Signatures

Proposed new JS contracts:
- `evaluateScenario(model, scenario) -> ScenarioResult`
- `runScenarioSuite(model, scenarios) -> ScenarioResultList`
- `buildRunRequest(project, issueId) -> RunRequest`

### Call Path

`updatePreview` -> `buildModel` -> `runScenarioSuite`.

`serializeLoopYaml` produces the revision handed to the connected host; `load_and_validate` in scripts/little_loops/fsm/validation/ validates it before the existing loop command is invoked through the artifact handoff mechanism. Transport registration and concrete handler ownership require refinement before implementation.

Current implemented call path (today, before this issue): `updatePreview` -> `buildModel` -> `serializeLoopYaml` (fills the YAML preview) and, at its tail, `updateTryIt()` -> `evaluateRules(rules, scores)` (`scripts/little_loops/templates/policy_builder_core.mjs:239`), which returns only a winning `target` string or `null` — no per-condition trace. `buildModel`/`updatePreview` exist today in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline `<script type="module">` block, not in `policy_builder_core.mjs`. `runScenarioSuite`, `evaluateScenario`, and `buildRunRequest` do not exist anywhere in the codebase — they are net new.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `evaluateRules(rules, scores)` (`scripts/little_loops/templates/policy_builder_core.mjs:239`) is the only existing evaluator; it returns a bare winning `target` string or `null` — no per-predicate match/fail trace and no reasoning object survives the call. `evalPredicate` computes a per-predicate boolean internally but discards it (used only inside `.every()`) — `ScenarioResult.conditions` has no existing data source without changing `evaluateRules`'s return shape or `evalPredicate`'s visibility. The only existing "explain a decision" convention in this file is `detectShadows` (`:253`), which reports rule-vs-rule shadowing reasons, not per-condition match/fail detail.
- `buildModel()` and `updatePreview()` already exist under those exact names, but live in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline `<script type="module">` block, not in `policy_builder_core.mjs`. `updatePreview()`'s current tail calls `updateTryIt()`, not a `runScenarioSuite` — this issue's proposed Call Path extends existing wiring rather than replacing it.
- `runScenarioSuite`, `evaluateScenario`, and `buildRunRequest` do not exist anywhere in the codebase (repo-wide search, no hits outside this issue's own text) — all three are net-new JS contracts.
- `load_and_validate` (`scripts/little_loops/fsm/validation/structural_rules.py`) signature: `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: str | None = None) -> tuple[FSMLoop, list[ValidationError]]`. It requires a filesystem `Path` — there is no in-memory/string-input variant. The only demonstrated route from browser-generated YAML text to this function (`scripts/tests/test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode`) writes the YAML to a temp file first, then validates the file.

## Implementation Steps

1. Integrate the shared diagnostic/evaluation result and versioned saved-project schema.
2. Implement named scenarios, independent expectations, suite execution, and condition/coverage explanations.
3. Add suggested boundary/missing-input cases, local issue import, and clearly labeled structural flow analysis.
4. Refine and register the host-mediated transport and request/result contract using existing artifact infrastructure.
5. Implement canonical validation, immutable revision handoff, deduplication, and observable results.
6. Test offline functionality, project migrations, and connected success/failure paths without real LLM or implementation runs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/templates/policy-router-builder.html.tmpl:731,773,787` — adjust `updateTryIt()`/`updatePreview()`/`renderMessages()` calls to `evaluateRules()`/`detectShadows()` if their return shape changes
- Update `scripts/tests/js/policy_validator.test.mjs` and `scripts/tests/test_policy_builder_corpus.py::test_evaluate_cases_match_canonical` — adapt bare-string assertions if `evaluateRules`/`evaluate_rules` return shape changes to carry per-condition traces
- Update `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html:1618` — keep byte-identical to `window.PolicyBuilderCore`'s export list in `policy_builder_core.mjs:1216-1237` when adding `runScenarioSuite`/`evaluateScenario`/`buildRunRequest`
- Register in `scripts/little_loops/cli/artifact/__init__.py:138-148` — add the new-run/connected-mode flag or subcommand to the `policy-builder` argparse subparser, plus a matching Example/Exit-code line in the epilog (`:79-134`)
- Update `docs/reference/CLI.md` — new Flags-table rows for `ll-artifact policy-builder` (`:5079-5095`) and, if applicable, `ll-artifact serve` (`:5186-5219`)
- Update `docs/reference/CONFIGURATION.md:948-958` and `scripts/little_loops/config-schema.json:1998-2041` — add the opt-in connected-mode key (`additionalProperties: false` blocks an unregistered key), following the CLI-flag-not-config-flag precedent in `scripts/little_loops/config/features.py:1319-1332` unless deliberately breaking from it
- Extend `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Existing / planned examples" table (`:56-59`) with the new level-2 policy-builder row — do not touch the three-level definition table or the literal strings pinned by `scripts/tests/test_wiring_reference_docs.py`
- Write a dedup/idempotency test for the new request ledger following the side-effect-counting style of `scripts/tests/test_orchestrator.py:2087-2098` / `scripts/tests/test_rn_refine.py:1370-1378` (no MCP-layer precedent exists for this)
- Promote `scripts/tests/spike/level2_run_handoff/{ledger,driver}.py` to `scripts/little_loops/spike/level2_run_handoff/` when the concrete transport is selected, updating `test_level2_run_handoff.py`'s imports and carrying `test_spike_does_not_import_local_bridge_transport`'s AST guard with it

## Impact

- Priority: P3 — improves policy confidence and closes the authoring-to-execution gap after foundational fixes.
- Effort: Large — scenario UX plus a scoped host integration and schema extension.
- Risk: Medium/high — run handoff requires correct revision binding and ownership boundaries.
- Breaking change: No; offline generation remains supported and connected behavior is opt-in.

## Use Case

A maintainer defines unscored, blocked, and ready-to-implement issue examples, sets their expected destinations, and saves them with a builder project. After changing the confidence threshold, Run all examples identifies which expectations changed and explains the winning conditions. The maintainer selects a real issue, reviews the exact validated policy revision and issue ID, and submits a host-mediated run request whose status remains visible.

## API/Interface

Extend the versioned saved-project schema with scenarios and expected results, migrating projects without scenarios to an empty list. Connected run requests carry an immutable policy revision and required issue input; their request ID provides deduplication. Declare the connected render target's supported control level in docs/reference/ARTIFACT_CONTROL_LEVELS.md. The offline page must not require a live connector.

## Acceptance Criteria

- [ ] Named scenarios and independent expected outcomes survive project save/open; Run all reports per-case results and total passed/failed counts deterministically.
- [ ] Repeated-target and fallback cases expose the correct rule identity and per-condition values, with tests asserting rule coverage and uncovered-rule reporting.
- [ ] Suggested cases include absent fields and values just below/at/above numeric thresholds; suggestions never silently assign the current output as the expected result.
- [ ] Scenario tests execute no skill, shell, LLM, or issue mutation; any mocked state changes are visibly identified as supplied assumptions.
- [ ] Offline local issue import and suite evaluation work without a server; unsupported input has explicit diagnostics.
- [ ] Connected requests require canonical validation and bind to the exact policy revision/project/issue ID; rejection, validation failure, missing issue, stale revision, and duplicate-submission cases are tested.
- [ ] The host receives the declared level-2 request and owns the run decision; no transport directly executes arbitrary submitted shell commands or intercepts level-3 FSM transitions.
- [ ] Accepted requests expose status and a run identifier when provided; connection failure leaves the project/scenarios intact and offline export available.

## Scope Boundaries

Includes named scenario suites, deterministic explanations, local issue import, and one optional host-mediated new-run integration. Excludes autonomous execution from previews, queue/retry orchestration, arbitrary remote command execution, replacing the FSM executor, and arbitrary existing-loop YAML import. Core correctness/discovery and persistent guided authoring are separate captured prerequisites.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Host runner and artifact control integration |
| Contract | docs/reference/ARTIFACT_CONTROL_LEVELS.md | Host-mediated new-run ownership and render-target registration |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Routing and limits of simulation |

## Spike Results

_Added by `/ll:spike` on 2026-09-16_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| (a) Zero precedent: no render target has ever declared Artifact Control Level 2 | `test_submit_creates_pending_record_not_auto_decided`, `test_observe_reflects_transitions_without_synchronous_decision_in_submit`, `test_spike_does_not_import_local_bridge_transport` | ✓ pass |
| (b) No persistent request-ID/idempotency ledger exists anywhere in the codebase | `test_duplicate_submit_returns_existing_record_without_retriggering`, `test_ledger_persists_across_process_restart` | ✓ pass |
| Revision/project/issue-ID binding immutability and validation-failure handling untested | `test_complete_rejects_binding_mismatch`, `test_submit_rejects_missing_binding_fields`, `test_decide_reject_leaves_no_run_id`, `test_decide_accept_then_complete_exposes_run_id_and_result` | ✓ pass |

**Spike location**: `scripts/tests/spike/level2_run_handoff/`
**Verification**: 9 tests pass in the spike suite; 82 pass in `test_transport.py`; 219 pass in `test_wiring_reference_docs.py` (3 commands, all exit 0).
**Promotion**: move to `scripts/little_loops/spike/level2_run_handoff/` in a separate PR when FEAT-3488's implementation selects the concrete host-decision transport (CLI prompt, MCP tool, etc.) — see the plan's Promotion section.

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-16T22:32:07 - `c1fe383a-93c2-4cce-a8fa-6eeed2e54d04.jsonl`
- `/ll:spike` - 2026-09-16T21:26:31 - `60e2c60c-390c-4854-b7a8-e5d6ce9f3356.jsonl`
- `/ll:refine-issue` - 2026-09-16T21:07:55 - `7017ba73-36ea-43e3-b3d4-064b9a419b43.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:14 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
