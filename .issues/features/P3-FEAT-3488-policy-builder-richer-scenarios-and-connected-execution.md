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

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py.
- Integration points to refine: scripts/little_loops/cli/artifact/serve.py, scripts/little_loops/mcp_server/resources.py, scripts/little_loops/fsm/validation/, and existing host/event handoff interfaces. These are candidates, not authorization to modify every transport.
- Similar patterns: shared compiled evaluator and saved-project model from the preceding workstreams; artifact control levels; project-enriched snapshots.
- Tests: scripts/tests/js/policy_validator.test.mjs and policy-builder Python gates; add scenario/serialization tests and mocked connected-handoff integration tests under local pytest.
- Configuration: connected mode is opt-in; existing offline generation remains the default.

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

## Implementation Steps

1. Integrate the shared diagnostic/evaluation result and versioned saved-project schema.
2. Implement named scenarios, independent expectations, suite execution, and condition/coverage explanations.
3. Add suggested boundary/missing-input cases, local issue import, and clearly labeled structural flow analysis.
4. Refine and register the host-mediated transport and request/result contract using existing artifact infrastructure.
5. Implement canonical validation, immutable revision handoff, deduplication, and observable results.
6. Test offline functionality, project migrations, and connected success/failure paths without real LLM or implementation runs.

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

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-16T20:55:14 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
