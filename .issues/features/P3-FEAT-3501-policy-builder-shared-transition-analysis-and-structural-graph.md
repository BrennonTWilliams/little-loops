---
id: FEAT-3501
type: FEAT
title: Policy builder shared transition analysis and structural graph
priority: P3
status: open
discovered_by: manual-review-split
discovered_date: '2026-09-17'
captured_at: '2026-09-17T21:17:47Z'
parent: EPIC-3493
labels:
- policy-builder
blocked_by:
- ENH-3492
relates_to:
- FEAT-3488
- FEAT-3474
unproven_mechanism: false
verify_verdict: VALID
---

# FEAT-3501: Policy builder shared transition analysis and structural graph

## Summary

Extract a shared `analyzeTransitions(model)` structural helper for lifecycle policies and consume it from both `summarizeTransitions` and a new structural graph panel in the builder UI. Split out of FEAT-3488 on 2026-09-17: it shares nothing with scenario suites except the "structure, not prediction" rule, and touches `summarizeTransitions`, which suites never call.

## Current Behavior

`summarizeTransitions` in `policy_builder_core.mjs` returns prose/step fields (`steps`, `stopsAfterImplement`, `stopDestination`, `verification`, `stepsPerAttempt`, `attempts`, `maxStepsNote`). It walks goto chains with a private cycle guard for step counting only; it exposes no graph edges, reachability, or cycle diagnostics. The template's transition summary (rendered near `summarizeTransitions` at the summary call site) has no graph view.

## Expected Behavior

One structural analysis contract feeds both the existing summary and a graph presentation. It represents dispatch, emitted outcomes, and ENH-3492 terminals with typed edges; reports reachable nodes and cycle node groups, distinguishing goto cycles from rescore feedback; and makes no claim that a structural cycle must execute or never terminate. Existing summary output is unchanged.

## Motivation

Lifecycle policies can author goto chains and rescore feedback that the prose summary cannot show. A structural graph lets a maintainer see unreachable outcomes and cycles before emitting YAML, and sharing one analysis with `summarizeTransitions` prevents the summary and graph from disagreeing.

## Use Case

**Who**: A maintainer authoring or editing an `issue_lifecycle` policy in the builder UI.

**Context**: The policy defines goto chains and rescore feedback loops that the prose transition summary cannot show — e.g. an outcome that routes to a destination nothing else reaches, or a goto chain that cycles back on itself.

**Goal**: See a structural graph of the policy's dispatch/goto/rescore/terminal edges, with unreachable nodes and cycle groups flagged, before emitting YAML.

**Outcome**: The maintainer spots an unreachable outcome or an unintended goto cycle in the builder UI and fixes the policy definition before it ships, without the graph and the existing prose summary ever disagreeing (they're driven by one shared `analyzeTransitions` call).

## Program Design

### Types

- `TransitionNode: {id: string, kind: 'scoring'|'dispatch'|'outcome'|'terminal'}`
- `TransitionEdge: {source: string, target: string, kind: 'dispatch'|'goto'|'rescore'|'terminal'}`
- `CycleRecord: {nodeIds: string[], kind: 'goto'|'rescore_feedback'}`
- `TransitionAnalysis: {nodes: TransitionNode[], edges: TransitionEdge[], reachableNodeIds: string[], cycles: CycleRecord[], diagnostics: string[]}`

### Signatures

- `analyzeTransitions(model: PolicyModel) -> TransitionAnalysis`
- `summarizeTransitions(model: PolicyModel) -> TransitionSummary` (existing signature; migrated to consume `analyzeTransitions` internally)

### Call Path

`cmd_policy_builder` generates the self-contained page with the embedded core and template. In that page: lifecycle summary render site -> `summarizeTransitions(model)` -> `analyzeTransitions(model)` -> `_emittedVerbs(model)` / `_dispatchedDestinations(model)` / `_requiredTerminalBlocks(model)` / `_KIND_TO_DESTINATION`

## Proposed Solution

- Add `analyzeTransitions(model) -> {nodes, edges, reachableNodeIds, cycles, diagnostics}`. Nodes have stable IDs and kinds (scoring/dispatch/outcome/terminal); edges have source, target, and kind (dispatch/goto/rescore/terminal). Rescore edges return to scoring/dispatch and denote possible subsequent routing, not a predicted next winner. Cycle records contain node IDs and a kind (`goto` vs `rescore_feedback`).
- Derive edges from the same emitted-outcome/destination semantics YAML generation uses (`_emittedVerbs`, `_dispatchedDestinations`, `_requiredTerminalBlocks`, `_KIND_TO_DESTINATION`), so the graph can never disagree with the emitted loop.
- Migrate `summarizeTransitions` to consume the shared analysis (chain length from the goto edges) while preserving its existing return shape and values.
- Render the graph and cycle warnings in `policy-router-builder.html.tmpl` for issue_lifecycle mode from the same analysis. Warnings describe possible transitions only; no action effects.
- Export `analyzeTransitions` through the `window.PolicyBuilderCore` bridge; regenerate golden HTML through the generator.

## Integration Map

- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: new `analyzeTransitions`, `summarizeTransitions` migration, bridge export.
- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: graph/cycle presentation in the lifecycle summary area.
- Tests: `scripts/tests/js/policy_validator.test.mjs` (node:test), `scripts/tests/test_policy_builder_node_gate.py`, `scripts/tests/test_policy_builder_emit.py` golden regeneration.
- Docs: `docs/guides/POLICY_ROUTER_GUIDE.md` structural-analysis limits.

## Implementation Steps

1. Add `analyzeTransitions` in core.mjs, built from `_emittedVerbs`, `_dispatchedDestinations`, `_requiredTerminalBlocks`, and `_KIND_TO_DESTINATION`; export it through the bridge.
2. Snapshot current `summarizeTransitions` outputs for seed/presets/blank in node:test, then migrate its chain-length computation onto the shared analysis and assert the snapshots still match.
3. Render graph nodes/edges and cycle warnings in the lifecycle summary area of the template; regenerate golden HTML; update the guide.
4. Verify with `node --test scripts/tests/js/*.test.mjs` via the pytest gate plus the emit/golden tests; record the manual browser check per the ENH-3487 manual-testing decision.

## Impact

- **Priority**: P3 - same tier as FEAT-3488; independent of it.
- **Effort**: Small/Medium - one pure helper, one consumer migration, one presentation panel.
- **Risk**: Low - summary output is snapshot-guarded; no YAML emission changes.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Summary and graph consume one `analyzeTransitions` contract; `summarizeTransitions` return values are byte-identical to today for the seeded lifecycle model, presets, and blank model.
- [ ] Tests cover goto chains, goto cycles, rescore feedback, unreachable outcomes, and explicit success/skip/needs-attention terminals from ENH-3492.
- [ ] Structural warnings make no claims about actual action outcomes or inevitable nontermination.
- [ ] Golden HTML and Node/Python gates pass; the browser bridge exports the new helper.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` documents the structural-analysis contract's limits (no execution-outcome or nontermination claims).

## Scope Boundaries

Excludes scenario suites, traces, expectations, and coverage (FEAT-3488) and connected execution (FEAT-3498). No skill, shell, LLM, or issue mutation executes from the analysis.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Lifecycle semantics, structural-analysis limits |

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a record
of what was wrong and fixed, not an outstanding action item). Every claim about
current state (check 1-4) held; the defect was in the Proposed Solution's
consequences (check B6).

- **Current Behavior claims** — confirmed accurate. `summarizeTransitions`
  (`scripts/little_loops/templates/policy_builder_core.mjs:1334-1409`) returns
  exactly `{steps, stopsAfterImplement, stopDestination, verification,
  stepsPerAttempt, attempts, maxStepsNote}`, walks goto chains via a private
  `chainLenFrom` cycle guard used only for `stepsPerAttempt`, and exposes no
  edges/reachability/cycle diagnostics. The template's summary render site
  (`scripts/little_loops/templates/policy-router-builder.html.tmpl:1211,1226-1231`)
  writes `summarizeTransitions(model)` output as plain text into `#transition-summary`
  — no graph view. `analyzeTransitions` does not yet exist in `policy_builder_core.mjs`
  (confirmed absent). Call Path's `cmd_policy_builder` entry point confirmed at
  `scripts/little_loops/cli/artifact/policy_builder.py:62`.
- **Blocked By**: `ENH-3492` is `done` — satisfied. `MISSING_BACKLINK`: `ENH-3492`
  has no `## Blocks` section referencing `FEAT-3501` (it predates this issue's split
  from FEAT-3488, so this is expected, not an error requiring action).
- **Evidence quotes** (`ll-verify-evidence --json`): clean, 0 findings.
- **Decisions log**: no active required rules to check against.
- **PROPOSAL_UNSOUND finding (check B6, AC coverage of Integration Map points)**:
  the Integration Map names a Docs integration point
  (`docs/guides/POLICY_ROUTER_GUIDE.md` — "structural-analysis limits"), and
  Implementation Step 3 says to "update the guide," but no Acceptance Criterion
  requires the doc update. As written, all four ACs can be satisfied while the
  guide update is silently dropped.

Fixed in the same pass: added an Acceptance Criterion requiring
`docs/guides/POLICY_ROUTER_GUIDE.md` to document the structural-analysis
contract's limits, closing the Integration Map's unenforced Docs point.

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-17T21:31:46 - `270c2766-2f75-4410-a3ba-53dfe4b6f1e8.jsonl`
- `/ll:format-issue` - 2026-09-17T21:24:30 - `fabca22b-468e-4dd5-8426-9cc105e3ce12.jsonl`
