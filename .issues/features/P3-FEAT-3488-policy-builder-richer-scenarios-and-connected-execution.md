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
- ENH-3487
relates_to:
- FEAT-3474
- BUG-3489
- BUG-3490
unproven_mechanism: true
spike_attempted: true
spike_completed: true
---

# FEAT-3488: Policy builder richer scenarios and connected execution

## Summary

Extend policy-builder with richer scenarios and optional connected execution: named test cases with expected outcomes, explainable rule evaluation, reusable example suites, and a host-mediated path from a validated project to a run. Keep offline authoring and scenario evaluation fully functional.

Captured from the 2026-09-16 review following FEAT-3474, as the third requested workstream.

The work is two phases with different risk profiles, and Phase B may be extracted to its own issue at sprint time without changing Phase A:

- **Phase A — offline scenario suite** (JS-only, Medium, no unproven mechanism): named scenarios, suite execution, condition explanations, rule coverage, suggested boundary cases, local issue-file import, structural flow warnings. Depends only on BUG-3486 and ENH-3487.
- **Phase B — connected execution** (the Medium/high risk): canonical validation and a level-2 host-mediated run request backed by the existing `ll-queue` store. Additionally benefits from BUG-3490 (consumer-project discovery) but is not blocked by it.

BUG-3489 (runtime stale scores / dispatch errors) is a runtime-fragment bug unrelated to the builder and is listed as `relates_to` only.

## Current Behavior

Try it handles one transient sample and highlights a rule without explaining individual conditions or asserting an expected outcome. There is no saved scenario suite, boundary-case generation, actual issue-file import flow, or builder-to-run handoff. The result pane offers YAML Copy/Download and a validation hint. Existing ll-artifact serve provides a live event/history dashboard, not a policy-builder write/run endpoint.

## Expected Behavior

Users save named examples, run the entire suite locally, see expected/actual outcomes and why each condition matched or failed, and identify uncovered or shadowed rules. An optional connected mode resolves project inputs, validates an immutable exported model/YAML revision, and hands a run request to the host with observable acceptance or failure. Previewing scenarios never executes action bodies.

## Motivation

Single-sample inspection does not establish confidence across a policy's edge cases. A reproducible suite catches regressions, and a clear execution handoff removes the gap between downloading YAML and using it without conflating simulation with real mutation.

## Proposed Solution

**Phase A — offline scenario suite**

- Store named scenarios **per draft** (each ENH-3487 `BuilderProject.drafts[mode]` entry owns its own `scenarios: []`, because scenario input shape differs per mode) with mode-specific input, expected outcome, and an expected rule identity that may be omitted. Add create/duplicate/delete, Run all, pass/fail/unasserted totals, condition explanations, fallback feedback, and rule coverage. Migration for projects predating this field sets `scenarios: []` on every draft.
- Build scenario evaluation on BUG-3486's `evaluateModel(model, scores) -> MatchResult` (`ruleIndex`, `target`, `isFallback`, `conditionResults`). `ScenarioResult.conditions` **consumes `MatchResult.conditionResults`**; `evaluateRules`'s bare-string return, the conformance corpus, and the Python `evaluate_rules` contract are not changed by this issue.
- Suggest missing-field and numeric-boundary cases. Suggested scenarios are created with `expectedTarget: null`, which means **unasserted / needs review**; Run all reports unasserted scenarios in their own count, never as pass or fail. Expected outcomes must be authored/reviewed independently; do not derive test oracles from the current policy itself.
- Show transition graphs and structural repeated-action/cycle warnings. Distinguish deterministic routing from action effects; any mocked post-action values must be labeled and cannot be presented as predictions of an LLM call.
- Support local issue-file import offline via `<input type="file">` + `FileReader`, reusing `parseFrontmatterBlock`/`encodeFrontmatterScores` to turn issue frontmatter into scenario input.

**Phase B — connected execution**

- Optional connected mode loads issues from the selected project and validates generated YAML through the canonical Python path (`load_and_validate`, via a temp file under the run's scratch dir since it takes a `Path`) before handoff.
- **Transport decision (resolved 2026-09-16):** the level-2 "ask-to-run-prompt" request is an **`ll-queue` entry** in `.ll/queue.db`. The builder's connected mode submits `queue_store.add_entry(ActionSpec(name=..., runner=RunnerType.LOOP, target=<loop>, args={issue_id, project_id, revision_id}), priority)` through a new `POST` route on `ll-artifact serve`. The host session **accepts** by running the entry as its own action (`ll-queue run` / `claim_entry`) and **rejects** with `ll-queue cancel` / `cancel_entry`; outcome and run identifier arrive through `update_entry_result`, observed by the page via `queue_get`/`ll-queue status` polling or the existing SSE bridge. This reuses the persistent, id-keyed, status-tracked ledger the codebase already has (the earlier research finding that none existed was incorrect) and the MCP surface (`queue_add`, `queue_get`, `queue_list`, `loop_start`).
- **Level boundary rule:** `ll-artifact serve` MUST NOT drain the queue or spawn runs itself. Draining is a host-typed action only. If the serve process ever auto-executes pending entries the target silently becomes level 3, which `docs/reference/ARTIFACT_CONTROL_LEVELS.md` explicitly forbids for a queue-backed path. Do not turn the current read-only serve routes into an implicit shell API; new-run handoff is separate from level-3 interaction with an already running FSM.
- **Identity and deduplication:** `revisionId` = SHA-256 of the canonical `serializeLoopYaml(model)` output (content-addressed, so stale-revision detection is re-serialize-and-compare). `requestId` = SHA-256 of `(projectId, revisionId, issueId)`, a natural key, so a repeated click, page reload, or retry maps to the same request; the serve route returns the existing entry when one with that `requestId` is already non-terminal instead of inserting a second. `requestId` is stored in the `ActionSpec.args` and indexed by the route's lookup.
- Expose request acceptance, rejection, failure, and a run identifier when available.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- No versioned "saved project" schema exists yet in the artifact-template layer. `scripts/little_loops/templates/policy_builder_core.mjs` and `policy-router-builder.html.tmpl` have no `schemaVersion`, `serializeBuilderProject`, or `parseBuilderProject` symbol (repo-wide search, no hits outside issue text); the template's only `localStorage` use stores just the theme toggle (`"ll-policy-builder-theme"`). The versioned project envelope this issue's scenario schema extends is itself only proposed, not yet implemented, in `ENH-3487` (`blocked_by`) — the `BuilderProject`/`serializeBuilderProject`/`parseBuilderProject` names there do not exist in source yet.
- No render target in this codebase has ever declared Artifact Control Level 2 ("ask-to-run-prompt"). `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Declared levels by render target" table lists only level 1 (`html-anything.yaml` dashboards, `ui://` resources, `ll-artifact serve`'s event page) and level 3 (`ll-loop run --serve`'s dashboard, via `LocalBridgeTransport`/`_handle_interaction()` in `scripts/little_loops/transport.py`). The documented closest analog, `HandoffBehavior.SPAWN` (`scripts/little_loops/fsm/handoff_handler.py`), is explicitly called a non-identical analog in the issue that wrote this contract (ENH-3307): it is triggered by the executor detecting a signal in its own loop output, not by a user interacting with a rendered artifact page.
  > ⚠ Unproven mechanism — no level-2 render target ever built
- Level 3's concrete mechanism (the only implemented host-mediated request/response in the codebase) responds to a POST with a bare `204` before touching its inbound queue; accept/reject/result is only observable asynchronously over an already-open SSE stream, not returned synchronously in the POST response (`LocalBridgeTransport._handle_interaction()`, `scripts/little_loops/transport.py`). This shape is not a drop-in template for level 2 (host-decision, not FSM-owned) — any level-2 mechanism this issue designs needs its own accept/observe contract.
- `scripts/little_loops/mcp_server/resources.py` has no `policy_builder`/`policy-router` resource kind and no `ArtifactControlLevel`-valued field on `_ResourceEntry` — the doc that defines that field names it an explicit, not-yet-built forward slot (`docs/reference/ARTIFACT_CONTROL_LEVELS.md`).
- ~~No persistent request-ID/idempotency-key ledger exists anywhere in this codebase~~ **Corrected 2026-09-16:** `ll-queue` (`scripts/little_loops/queue_store.py`, `.ll/queue.db`) is exactly that: SQLite-backed, uuid-keyed `QueueEntry` rows with `pending` → `running` → done/`dead_letter`/cancelled transitions, `add_entry`, `claim_entry`, `update_entry_result`, `cancel_entry`, `schedule_retry`, and `revive_entry`, exposed by the `ll-queue` subcommands in `scripts/little_loops/cli/queue.py` (add, list, status, run, requeue, cancel) and the MCP tools `queue_add`/`queue_get`/`queue_list` plus `loop_start` (`scripts/little_loops/mcp_server/tools.py:609-744`). The three narrower conventions previously cited (`parallel/orchestrator.py:219` in-memory set, `rn_synth_queue.py` sentinel files, `idempotent_hint`) are not needed. What `ll-queue` does **not** provide, and this issue adds: a natural-key `requestId` lookup for dedup (entries are uuid-keyed today) and revision/project/issue binding fields in `ActionSpec.args`.
- No reusable boundary-value/missing-field test-case generation utility exists (JS or Python) outside test-only Hypothesis strategies inlined in individual `scripts/tests/*.py` files (e.g. `test_fsm_route_properties.py`'s `@st.composite route_matrix`) — each is scoped to that file's own regression suite, not importable by production code.
- No `FileReader`/local-file-import convention (`<input type=file>`, drag-drop) exists anywhere in `scripts/little_loops/templates/` — the local issue-file import this issue proposes has no existing browser-side file-reading pattern to follow in this codebase.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py; scripts/little_loops/cli/artifact/serve.py (Phase B route); scripts/little_loops/queue_store.py (requestId lookup).
- Integration points: scripts/little_loops/fsm/validation/ (`load_and_validate`), scripts/little_loops/cli/queue.py and scripts/little_loops/mcp_server/tools.py (host accept/reject surface, docs only). `scripts/little_loops/mcp_server/resources.py`'s `ArtifactControlLevel` forward slot stays unbuilt; declare the level in prose per the doc's "Binding now" rule.
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
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:731,773` — `updateTryIt()`/`updatePreview()` call `evaluateRules(...)`; BUG-3486 migrates these to `evaluateModel()`. This issue does **not** change `evaluateRules`'s return shape; `ScenarioResult.conditions` reads `MatchResult.conditionResults`.
- `scripts/little_loops/queue_store.py` — `add_entry`, `get_entry`, `list_entries`, `cancel_entry`, `update_entry_result`; needs a natural-key lookup (by `requestId` in `ActionSpec.args`) or a small index for dedup
- `scripts/little_loops/cli/queue.py` — `cmd_run`/`cmd_cancel`/`cmd_status` are the host-session accept/reject/observe surface; no changes expected beyond docs
- `scripts/little_loops/mcp_server/tools.py:609-744` — `queue_add`/`queue_get`/`loop_start`; the agent-mediated accept path
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

### Codebase Research Findings (test and doc surfaces)

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- JS core logic (`evaluateRules`, `detectShadows`, `serializeLoopYaml`, `parseRuleTable`, etc.) is tested via `node:test` in `scripts/tests/js/policy_validator.test.mjs` against `scripts/tests/fixtures/policy_builder/conformance_corpus.json`, gated into the enforced pytest suite by `scripts/tests/test_policy_builder_node_gate.py` (shells out to `node --test`, skips gracefully when Node < 22, per CLAUDE.md's CI policy). `scripts/tests/test_policy_builder_emit.py` covers a different surface — `cmd_policy_builder()` HTML generation, golden-YAML validation, and structural/accessibility assertions — and does not unit-test JS logic itself. New scenario-suite JS logic belongs in the `node:test` layer; new Python-side connected-handoff/validation logic belongs in `test_policy_builder_emit.py` or a new sibling test module.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Declared levels by render target" table is asserted verbatim by `scripts/tests/test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT` pins `"notify"`, `"ask-to-run-prompt"`, `"host-owned"` literally) — a new policy-builder row must preserve those exact level-name strings.
- `scripts/little_loops/cli/artifact/serve.py`'s `cmd_serve` passes `interaction_url=None` and declares Level 1 (notify) only — it has no FSM executor backing it, unlike `ll-loop run --serve` (Level 3). Under the resolved transport it needs **no** executor: the new route only inserts a queue entry and reads status. Its declared level becomes 1 and 2, recorded in the "Declared levels by render target" table.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5079-5095` (`#### ll-artifact policy-builder`) — currently documents only `-o/--output`; a new-run/connected-mode flag needs a new Flags-table row and Example line
- `docs/reference/CLI.md:5186-5219` (`#### ll-artifact serve`) — currently documents only `--port`; needs updating if the level-2 transport is wired through `serve.py`
- `docs/reference/API.md:11078` — `assemble_tool_catalog` cites `cli/artifact/policy_builder.py:_load_skill_catalog()` by name; stale if that function is renamed/restructured for local issue-file import
- `docs/reference/CONFIGURATION.md:948-958` (`### artifacts`) — needs a new key-table row if an opt-in connected-mode config key is added
- `docs/reference/EVENT-SCHEMA.md:1815-1828` (`## Reserved Event Names`) — reserves only `artifact_interaction` for level 3 today; not needed if status is observed via queue polling. Only add a reserved event if the SSE bridge is chosen for status delivery.
- `docs/reference/CLI.md` `ll-queue` section — document that a policy-builder connected request is a queue entry, and that `ll-queue run`/`cancel` are the accept/reject actions
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add the connected-mode flow and the "serve never drains" rule

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs:45-46,307-308,312-313` and `scripts/tests/test_policy_builder_corpus.py::test_evaluate_cases_match_canonical` — bare-string `evaluateRules`/`evaluate_rules` assertions; **unchanged** by this issue (scenario logic sits on `evaluateModel`)
- `scripts/tests/test_queue_store.py` / `scripts/tests/test_cli_queue.py` (existing `ll-queue` suites) — the dedup and status tests for Phase B extend these rather than inventing a new ledger test module
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — the closest existing precedent for a named-scenario-suite-with-expected-outcome fixture (shared JS/Python consumers); model the new scenario-suite schema after this pattern
- `scripts/tests/test_orchestrator.py:2087-2098` (`test_idempotent_across_calls`) — dedup-by-side-effect-count style to model the `requestId` natural-key dedup test after (submit twice, assert one queue row)
- `scripts/tests/test_wiring_reference_docs.py` `DOC_STRINGS_PRESENT`/`DOC_FILES_MUST_EXIST` — pins the literal level names `"notify"`, `"ask-to-run-prompt"`, `"host-owned"` in `docs/reference/ARTIFACT_CONTROL_LEVELS.md`. Add the policy-builder row to the **"Declared levels by render target"** table (the canonical per-target table, `:48-55`), updating the `ll-artifact serve` row to "1 (notify), 2 (ask-to-run-prompt)"; do not edit the three-level definition table's level-name cells
- `scripts/tests/test_fsm_schema_fuzz.py:35-80` (`malformed_evaluate_config`) and `scripts/tests/test_fsm_route_properties.py:25-37` (`route_matrix`) — closest existing Hypothesis `@st.composite` conventions to model boundary/missing-field scenario-suggestion generation after (no JS-side property-testing library exists in the repo)
- `scripts/tests/test_policy_builder_emit.py::test_no_internal_jargon_in_visible_markup` (`:150-155`) — denylists "predicate" and other internal jargon from visible markup; new condition-explanation UI text must avoid these literal terms
- `scripts/tests/test_policy_builder_emit.py::test_rubric_mode_has_no_dt_only_affordances` (`:209-221`) and `test_single_mode_toggle` (`:199-201`) — pin fieldset IDs and mode-switch count; a new scenario-suite fieldset needs its own ID wired into `applyModeVisibility()` without tripping these
- **Spike disposition:** `scripts/tests/spike/level2_run_handoff/` is **not promoted**. Its file-backed `RequestLedger` is superseded by `queue_store`. Its state-machine assertions (submit never auto-decides; decide is a separate explicit call; binding is immutable; duplicate submit is a no-op; persistence across restart) are re-expressed as tests against `queue_store` + the serve route. Carry `test_spike_does_not_import_local_bridge_transport`'s AST guard across as a "serve.py's queue route must not import `LocalBridgeTransport` or `run_background`" test, which is the enforceable form of the "serve never drains" rule.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1998-2041` — the `artifacts` object has `"additionalProperties": false`; an opt-in connected-mode key cannot be added to `.ll/ll-config.json` without a new schema key here
- `scripts/little_loops/config/features.py:1319-1332` (`BridgeEventsConfig`) — existing precedent that `ll-artifact serve` deliberately has **no `enabled` config key** ("a config flag that refuses an explicit command is bad UX"); a connected-mode toggle should follow this CLI-flag-not-config-flag precedent or explicitly justify breaking from it
- `scripts/little_loops/cli/artifact/__init__.py:138-148` — the `policy-builder` argparse subparser only defines `-o/--output`; a new-run/connected-mode flag or subcommand must be registered here, plus a matching Example/Exit-code line in the top-level epilog (`:79-134`). Decision: **CLI flag on the serve subparser, not a config key** (exact flag name chosen at implementation), following the `BridgeEventsConfig` precedent; no `config-schema.json` change unless a later need appears.

## Program Design

### Types

Proposed Scenario carries id, name, input, expectedTarget (string, or `null` = unasserted), and optional expectedRuleIndex; stored under `BuilderProject.drafts[mode].scenarios`. ScenarioResult carries scenarioId, actualTarget, ruleIndex, isFallback, conditions (from `MatchResult.conditionResults`), and verdict (`pass` | `fail` | `unasserted`). SuiteSummary carries passed, failed, unasserted, and uncoveredRuleIndexes. RunRequest carries requestId, projectId, revisionId, yaml, and issueId, where revisionId = sha256(yaml) and requestId = sha256(projectId + revisionId + issueId).

### Signatures

Proposed new JS contracts (`policy_builder_core.mjs`, also exported on `window.PolicyBuilderCore`):
- `evaluateScenario(model, scenario) -> ScenarioResult`
- `runScenarioSuite(model, scenarios) -> { results: ScenarioResult[], summary: SuiteSummary }`
- `suggestScenarios(model) -> Scenario[]` (all with `expectedTarget: null`)
- `computeRevisionId(yaml) -> string`
- `buildRunRequest(project, issueId) -> RunRequest`

Proposed Python contracts:
- `queue_store.find_entry_by_request_id(request_id, *, root) -> QueueEntry | None`
- `cli/artifact/serve.py`: `make_run_request_route(config) -> handler` (`POST /{token}/run-request`: validate YAML via `load_and_validate` on a temp file, dedup via `find_entry_by_request_id`, else `add_entry`; `GET /{token}/run-request/{request_id}`: status/run-id readback via `get_entry`)

### Call Path

Phase A: `updatePreview` -> `buildModel` -> `runScenarioSuite` -> `evaluateScenario` -> `evaluateModel` (BUG-3486).

Phase B: `buildRunRequest` -> `serializeLoopYaml` + `computeRevisionId` -> `POST /run-request` -> `load_and_validate` -> `find_entry_by_request_id` / `add_entry`. Host session: `ll-queue run` (`cmd_run` -> `claim_entry` -> `run_action` -> `update_entry_result`) or `ll-queue cancel` (`cmd_cancel` -> `cancel_entry`). Page: `GET /run-request/{id}` -> `get_entry`.

Current implemented call path (today, before this issue): `updatePreview` -> `buildModel` -> `serializeLoopYaml` (fills the YAML preview) and, at its tail, `updateTryIt()` -> `evaluateRules(rules, scores)` (`scripts/little_loops/templates/policy_builder_core.mjs:239`), which returns only a winning `target` string or `null` — no per-condition trace. `buildModel`/`updatePreview` exist today in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline `<script type="module">` block, not in `policy_builder_core.mjs`. `runScenarioSuite`, `evaluateScenario`, and `buildRunRequest` do not exist anywhere in the codebase — they are net new.

### Codebase Research Findings (evaluator and call path)

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `evaluateRules(rules, scores)` (`scripts/little_loops/templates/policy_builder_core.mjs:239`) is the only existing evaluator; it returns a bare winning `target` string or `null` — no per-predicate match/fail trace and no reasoning object survives the call. `evalPredicate` computes a per-predicate boolean internally but discards it (used only inside `.every()`) — `ScenarioResult.conditions` has no existing data source without changing `evaluateRules`'s return shape or `evalPredicate`'s visibility. The only existing "explain a decision" convention in this file is `detectShadows` (`:253`), which reports rule-vs-rule shadowing reasons, not per-condition match/fail detail.
- `buildModel()` and `updatePreview()` already exist under those exact names, but live in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline `<script type="module">` block, not in `policy_builder_core.mjs`. `updatePreview()`'s current tail calls `updateTryIt()`, not a `runScenarioSuite` — this issue's proposed Call Path extends existing wiring rather than replacing it.
- `runScenarioSuite`, `evaluateScenario`, and `buildRunRequest` do not exist anywhere in the codebase (repo-wide search, no hits outside this issue's own text) — all three are net-new JS contracts.
- `load_and_validate` (`scripts/little_loops/fsm/validation/structural_rules.py`) signature: `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: str | None = None) -> tuple[FSMLoop, list[ValidationError]]`. It requires a filesystem `Path` — there is no in-memory/string-input variant. The only demonstrated route from browser-generated YAML text to this function (`scripts/tests/test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode`) writes the YAML to a temp file first, then validates the file.

## Implementation Steps

Phase A (offline):
1. Extend ENH-3487's `BuilderProject.drafts[mode]` with `scenarios: []` and the migration; add `evaluateScenario`/`runScenarioSuite` on top of BUG-3486's `evaluateModel`.
2. Implement named scenarios (create/duplicate/delete), Run all with pass/fail/unasserted totals, per-condition explanations, fallback feedback, and uncovered-rule reporting.
3. Add `suggestScenarios` (missing-field and below/at/above numeric thresholds, all unasserted), local issue-file import via `FileReader` + `parseFrontmatterBlock`, and labeled structural flow analysis (transition graph, repeated-action/cycle warnings).
4. Test Phase A in `policy_validator.test.mjs` (node:test) and the emit/golden suites; regenerate the golden fixture.

Phase B (connected, extractable to its own issue):
5. Add `computeRevisionId`/`buildRunRequest`; add `queue_store.find_entry_by_request_id`.
6. Add the `ll-artifact serve` run-request route (validate → dedup → `add_entry`; status readback) with the "never drains, never imports `run_background`/`LocalBridgeTransport`" guard test.
7. Update `ARTIFACT_CONTROL_LEVELS.md` "Declared levels by render target", CLI.md (`ll-artifact serve`, `ll-queue`), and `POLICY_ROUTER_GUIDE.md`.
8. Test rejection (`ll-queue cancel`), validation failure, missing issue, stale revision, duplicate submission, and accept → run-id readback with a stubbed `run_action`; no real LLM or implementation runs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- `scripts/little_loops/templates/policy-router-builder.html.tmpl:731,773,787` — after BUG-3486, `updateTryIt()`/`updatePreview()` call `evaluateModel()`; wire `runScenarioSuite` at `updatePreview`'s tail next to `updateTryIt()`. `renderMessages(model)`'s `detectShadows` call is unchanged.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html:1618` — keep byte-identical to `window.PolicyBuilderCore`'s export list in `policy_builder_core.mjs:1216-1237` when adding `evaluateScenario`/`runScenarioSuite`/`suggestScenarios`/`computeRevisionId`/`buildRunRequest`
- Register the connected-mode CLI flag in `scripts/little_loops/cli/artifact/__init__.py` (serve subparser) plus a matching Example/Exit-code line in the epilog (`:79-134`); no `config-schema.json` / `CONFIGURATION.md` change (CLI-flag-not-config-flag precedent, `scripts/little_loops/config/features.py:1319-1332`)
- Update `docs/reference/CLI.md` — `ll-artifact serve` (`:5186-5219`) route + flag rows; `ll-queue` section note on policy-builder entries
- Update `docs/reference/ARTIFACT_CONTROL_LEVELS.md` "Declared levels by render target" table — `ll-artifact serve` row becomes "1 (notify), 2 (ask-to-run-prompt)"; keep the literal level-name strings pinned by `scripts/tests/test_wiring_reference_docs.py`
- Write the `requestId` dedup test in the side-effect-counting style of `scripts/tests/test_orchestrator.py:2087-2098` against `queue_store` (submit twice, one row)
- Write the serve-route isolation test (AST guard: route module must not import `run_background` or `LocalBridgeTransport`), ported from the spike's `test_spike_does_not_import_local_bridge_transport`
- Delete `scripts/tests/spike/level2_run_handoff/` once its assertions are re-expressed against `queue_store` (do not promote)

## Impact

- Priority: P3 — improves policy confidence and closes the authoring-to-execution gap after foundational fixes.
- Effort: Large — scenario UX plus a scoped host integration and schema extension.
- Risk: Medium/high — run handoff requires correct revision binding and ownership boundaries.
- Breaking change: No; offline generation remains supported and connected behavior is opt-in.

## Use Case

A maintainer defines unscored, blocked, and ready-to-implement issue examples, sets their expected destinations, and saves them with a builder project. After changing the confidence threshold, Run all examples identifies which expectations changed and explains the winning conditions. The maintainer selects a real issue, reviews the exact validated policy revision and issue ID, and submits a host-mediated run request whose status remains visible.

## API/Interface

Extend ENH-3487's versioned saved-project schema with per-draft `scenarios`, migrating drafts without the field to an empty list. Connected run requests are `ll-queue` entries carrying `requestId`, `projectId`, `revisionId` (sha256 of the canonical YAML), and `issueId` in `ActionSpec.args`; the content-derived `requestId` provides deduplication. Declare `ll-artifact serve` as level 1 and 2 in docs/reference/ARTIFACT_CONTROL_LEVELS.md. The offline page must not require a live connector.

## Acceptance Criteria

Phase A:
- [ ] Named scenarios and independent expected outcomes survive project save/open per draft; a project saved before this field loads with `scenarios: []` on every draft. Run all reports per-case results and passed/failed/unasserted counts deterministically.
- [ ] Repeated-target and fallback cases expose the correct rule identity and per-condition values sourced from `MatchResult.conditionResults`; tests assert rule coverage and uncovered-rule reporting. `evaluateRules`, the conformance corpus, and Python `evaluate_rules` are unchanged.
- [ ] Suggested cases include absent fields and values just below/at/above numeric thresholds; every suggestion is created with `expectedTarget: null` and reported as unasserted until a user sets an expectation.
- [ ] Scenario tests execute no skill, shell, LLM, or issue mutation; any mocked state changes are visibly identified as supplied assumptions.
- [ ] The transition graph and repeated-action/cycle warnings render for each mode and are labeled as structural analysis, not execution prediction.
- [ ] Offline local issue import and suite evaluation work without a server; unsupported input has explicit diagnostics.

Phase B:
- [ ] Connected requests are validated by `load_and_validate` and bound to `projectId`/`revisionId`/`issueId`; rejection (`ll-queue cancel`), validation failure, missing issue, stale revision (re-serialized YAML hash differs), and duplicate submission (same `requestId` twice yields one queue row) are tested.
- [ ] The request is an `ll-queue` entry and the host session owns the run decision; `ll-artifact serve` never drains the queue, and a test asserts its route module imports neither `run_background` nor `LocalBridgeTransport`. No transport executes arbitrary submitted shell commands or intercepts level-3 FSM transitions.
- [ ] Accepted requests expose status and a run identifier read back from the queue entry; connection failure leaves the project/scenarios intact and offline export available.
- [ ] `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s "Declared levels by render target" table lists `ll-artifact serve` at levels 1 and 2 and `test_wiring_reference_docs.py` still passes.

## Scope Boundaries

Includes named scenario suites, deterministic explanations, local issue import, and one opt-in host-mediated new-run integration via `ll-queue`. Excludes autonomous execution from previews, any auto-drain of the queue by the serve process, new retry/backoff semantics (reuse `ll-queue`'s existing ones), arbitrary remote command execution, replacing the FSM executor, building the `ArtifactControlLevel` forward slot on `_ResourceEntry`, and arbitrary existing-loop YAML import. Core correctness (BUG-3486) and persistent guided authoring (ENH-3487) are separate prerequisites. Phase B may be extracted into its own issue at sprint time.

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
**Promotion (revised 2026-09-16)**: not promoted. The transport decision selected the existing `ll-queue` store, which already provides the persistence and status machine the spike prototyped. The spike's state-machine and isolation assertions are re-expressed against `queue_store` and the serve route (see Wiring Phase); the spike directory is deleted once those tests land.

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- manual review - 2026-09-16 - narrowed `blocked_by` to BUG-3486/ENH-3487; resolved transport to `ll-queue`; defined `requestId`/`revisionId`; built scenarios on `evaluateModel`; per-draft scenarios; unasserted state; split into Phase A/B; spike not promoted
- `/ll:wire-issue` - 2026-09-16T22:32:07 - `c1fe383a-93c2-4cce-a8fa-6eeed2e54d04.jsonl`
- `/ll:spike` - 2026-09-16T21:26:31 - `60e2c60c-390c-4854-b7a8-e5d6ce9f3356.jsonl`
- `/ll:refine-issue` - 2026-09-16T21:07:55 - `7017ba73-36ea-43e3-b3d4-064b9a419b43.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:14 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
