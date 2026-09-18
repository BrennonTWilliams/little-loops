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
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
- `TransitionAnalysis: {nodes: TransitionNode[], edges: TransitionEdge[], reachableNodeIds: string[], cycles: CycleRecord[]}`

### Contract Semantics (review pass, 2026-09-17)

These pin the decisions the type list alone leaves open; the implementation must follow them, not re-derive them.

- **Node IDs are emitted YAML state names.** `score` and `policy_dispatch` (kinds `scoring`/`dispatch`), the five verbs from `model.outcomes` (kind `outcome`), and the terminals `done` plus `_requiredTerminalBlocks(model)` (kind `terminal`). Reserved-name rules (`RESERVED_STATE_NAMES`, `LIFECYCLE_DESTINATIONS`) guarantee no collisions, which is what makes the graph map 1:1 onto the YAML.
- **Fixed edges**: `score → policy_dispatch` (kind `dispatch`); `policy_dispatch → <target>` for every distinct `rules[].target` and `model.fallback` (kind `dispatch`; target may be a verb or a destination).
- **Per-outcome edges** derive from `outcomes[].transition` exactly as `_outcomeStateLines` serializes them (`policy_builder_core.mjs:2243-2261`):
  - `goto` → edge `outcome → transition.target` (kind `goto`), only when the target is a defined outcome (mirrors `_emittedVerbs`'s guard; a dangling target is already an error from `validateBuilderModel`, `:744`, and produces no edge).
  - `rescore` → edge `outcome → score` (kind `rescore`).
  - `stop`/`skip`/`attention` → edge `outcome → _KIND_TO_DESTINATION[kind]` (kind `terminal`).
  - `finish` (or no transition) with an action → edge `outcome → done` (kind `terminal`). `finish` with no action → the outcome node is itself a sink (`terminal: true` in YAML); no edge.
- **Implicit routes are NOT edges.** `on_max_steps → needs_attention` and each state's `on_error: failed` fan out from every state and are not authored transitions; the graph omits them, `failed` is not a node, and the guide's limits section names both omissions. The "cannot disagree with the emitted loop" guarantee is therefore scoped to *authored* transitions.
- **`reachableNodeIds`** = nodes reachable from `score` over the edge list above. Consequence: `needs_attention` is always emitted but is in `reachableNodeIds` only when authored-reachable (an `attention` transition or a rule/fallback target); the template's "unreachable" warning applies to `kind === "outcome"` nodes only, never terminals.
- **Goto cycles**: DFS/SCC over `goto` edges restricted to reachable outcome nodes, self-loops included; one `CycleRecord` per cycle with `kind: "goto"` and `nodeIds` in `model.outcomes` order. These are warnings in the panel.
- **Rescore feedback**: one `CycleRecord` per reachable outcome whose transition is `rescore`, `kind: "rescore_feedback"`, `nodeIds: ["score", "policy_dispatch", <outcome>]`. Every preset and the seed use `rescore` (`:114`, `:128`, `:1770`, `:1776`), so this is the normal shape of a lifecycle policy: the panel renders it as informational, never as a warning.
- **No `diagnostics` field.** `validateBuilderModel` already owns dangling-reference errors in the `_diag` `{severity, field, message}` shape that `renderMessages` consumes; a parallel string list would duplicate messaging. The template derives its warning lines from `nodes` / `reachableNodeIds` / `cycles`.
- **Non-lifecycle modes**: `analyzeTransitions` returns `{nodes: [], edges: [], reachableNodeIds: [], cycles: []}` for `decision_table`/`rubric` models (the bridge export is callable from any mode; the panel itself is lifecycle-only).
- **Determinism**: `nodes` in the order scoring, dispatch, `model.outcomes` order, then `done` followed by `LIFECYCLE_DESTINATIONS` order; `edges` in source-node order then authoring order. Both are stable so tests can deep-equal them.

### Signatures

- `analyzeTransitions(model: PolicyModel) -> TransitionAnalysis`
- `summarizeTransitions(model: PolicyModel) -> TransitionSummary` (existing signature; migrated to consume `analyzeTransitions` internally)

### Call Path

`cmd_policy_builder` generates the self-contained page with the embedded core and template. In that page: lifecycle summary render site -> `summarizeTransitions(model)` -> `analyzeTransitions(model)` -> `_emittedVerbs(model)` / `_dispatchedDestinations(model)` / `_requiredTerminalBlocks(model)` / `_KIND_TO_DESTINATION`

- Concrete anchors: `updatePreview()` (`policy-router-builder.html.tmpl:1178-1233`) calls `summarizeTransitions(model)` at `:1211` inside the `mode === "issue_lifecycle"` branch (`:1210-1232`); `summarizeTransitions` (`policy_builder_core.mjs:1334-1409`) calls `_emittedVerbs(model)` at `:1337` and reads `_KIND_TO_DESTINATION[implementKind]` at `:1348`/`:1350`.
- `summarizeTransitions` has exactly one caller in this codebase — the template call site above. Confirmed via `ll-code callers-of` (no hits) plus a repo-wide grep; `scripts/tests/js/policy_validator.test.mjs` calls it directly as the unit under test, not as an integration caller.
- `_emittedVerbs` (`:1923-1947`) and `_dispatchedDestinations` (`:1961-1973`, itself reading `_KIND_TO_DESTINATION` at `:1969`) are the only helpers that currently touch `goto`/terminal transitions. **No existing code traverses `rescore` transitions**: `_emittedVerbs`'s fixed-point loop only follows edges where `transition.kind === "goto"` (`:1938`), so a `rescore` edge is never followed by any function in the file today — `analyzeTransitions`'s rescore-edge handling is new logic, not an extraction of an existing walk.

_Anchor refresh — `/ll:refine-issue` — 2026-09-17 — the file grew ~580-600 lines since the anchors above were written; re-confirmed via `ll-code` + codebase-analyzer against the current tree. The numbers above are now stale; use these instead:_

- `summarizeTransitions` function span: `policy_builder_core.mjs:1932-2007` (was `:1334-1409`). Calls `_emittedVerbs(model)` at `:1935` (was `:1337`); reads `_KIND_TO_DESTINATION[implementKind]` at `:1946` and `:1948` (was `:1348`/`:1350`).
- `chainLenFrom`'s cycle guard: `:1969-1978` (was `:1371-1380`); fresh-`Set`-per-dispatch-target reset: `:1986` (was `:1388`).
- `_emittedVerbs`: `:2521-2545` (was `:1923-1947`); its `goto`-only fixed-point check is at `:2536` (was `:1938`).
- `_dispatchedDestinations`: `:2559-2571` (was `:1961-1973`); its own `_KIND_TO_DESTINATION` read is at `:2567` (was `:1969`).
- `_requiredTerminalBlocks`: `:2584-2588`; calls `_dispatchedDestinations(model)` internally at `:2585`.
- Template `updatePreview()`'s `summarizeTransitions(model)` call: `:1592` (was `:1211`); its second `_dispatchedDestinations(model)` call: `:1603` (was `:1222`).
- Template `computeSummary(model)` — a fourth, independent consumer not previously named — calls `_emittedVerbs(model)`/`_dispatchedDestinations(model)` at `:535`/`:536`.
- `rescore` transitions remain untraversed by any function today (re-confirmed against current file): `_emittedVerbs`'s `:2536` check and `chainLenFrom`'s `:1974` check both gate on `=== "goto"` only; `rescore` has no `target` field to resolve (model-shape comment, `:44-45`) — this is structural (rescore carries no target), not an oversight in the goto-only checks. The only place `rescore` is handled at all is the serializer's hardcoded `next: score` line (`_serializeIssueLifecycle`, `:2251`).
- `analyzeTransitions` still has no call site (confirmed absent repo-wide). Per this file's existing pattern (each consumer calls shared helpers directly rather than through one another), it would sit alongside `_emittedVerbs`/`_dispatchedDestinations`/`_requiredTerminalBlocks` (the `:2521-2588` region), since that's the only place today all dispatch/goto/terminal edge data is assembled; it still needs new logic for `rescore` edges, which none of those three touch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `PolicyModel` fields `analyzeTransitions` must walk to build nodes/edges: `rules[].target` and `model.fallback` (dispatch edges — seeded today in `_emittedVerbs`, `policy_builder_core.mjs:1928-1931`), `outcomes[].transition.kind === "goto"` chains (walked today in `_emittedVerbs`'s fixed-point loop, `:1933-1944`, and `summarizeTransitions`'s `chainLenFrom`, `:1371-1380`), and `outcomes[].transition.kind` mapped through `_KIND_TO_DESTINATION` for terminal edges (walked today in `_dispatchedDestinations`, `:1964-1971`). `outcomes[].transition.kind === "rescore"` (feedback edges back to scoring/dispatch) is checked only by `_emittedVerbs`'s inner `goto` test, which `rescore` fails — no existing code follows a `rescore` edge anywhere in the file.
- `summarizeTransitions`'s private cycle guard is a `Set`-based visited-node guard local to `chainLenFrom` (`policy_builder_core.mjs:1371-1380`, the `seen` parameter), reset to a fresh `Set` per top-level dispatch target (`:1388`) — it bounds recursion within one chain-length computation only, not across targets, and affects no returned field besides `stepsPerAttempt`/`attempts`/`maxStepsNote`.

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- The `chainLenFrom` cycle guard already implements ad hoc reachability/cycle detection (a `seen`-set-guarded recursive walk over `goto` edges only, `policy_builder_core.mjs:1969-1978`) — this is the only cycle-detection code in the file today, but it is local to `summarizeTransitions`, not exported or reused, and returns only a chain length, not the set of cyclic node IDs. `analyzeTransitions`'s `CycleRecord.nodeIds` output is new surface area, not a rename of this guard's return value.
- No JS graph/node/edge typed structure exists anywhere in this codebase (repo-wide search, re-confirmed). The codebase's only structural-cycle-detection precedent remains Python's `DependencyGraph.detect_cycles()` (`dependency_graph.py:380-432`), whose test suite (`test_dependency_graph.py:504-590`, `TestCycleDetection`) asserts cycle membership/length (`len(cycles) > 0`, `"X" in cycle_nodes`) rather than a full snapshot of the cycle list — the same field-level (not snapshot) assertion style already used for `summarizeTransitions`'s own tests.
- A directly-on-point precedent exists in this same file area for migrating a function onto a newly-extracted shared helper while preserving output: ENH-3035 (`policy_builder_core.mjs`'s `themed_css_vars()` extraction) captured a byte-identical golden fixture from the pre-refactor output *before* starting the extraction, in its own commit — "the byte-identical AC is unprovable if captured after the port" (`.issues/enhancements/P3-ENH-3035-...md:317`). The existing `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` (`:62-68`) already performs this exact byte-comparison for `cmd_policy_builder`'s output; the same before/after-golden discipline applies to the `summarizeTransitions` migration.
- This codebase's convention is that new shared modules/helpers are extracted when a second consumer needs the same logic, not proactively (ENH-3035 finding, citing `render_to_disk()` in `cli/artifact/render.py`) — `analyzeTransitions` already has its second consumer specified by this issue (the graph panel), so this convention is satisfied by the issue's own proposed shape, not a gap.

## Proposed Solution

- Add `analyzeTransitions(model) -> {nodes, edges, reachableNodeIds, cycles}` per the Contract Semantics above. Nodes have stable IDs (emitted YAML state names) and kinds (scoring/dispatch/outcome/terminal); edges have source, target, and kind (dispatch/goto/rescore/terminal). Rescore edges return to `score` and denote possible subsequent routing, not a predicted next winner. Cycle records contain node IDs and a kind (`goto` vs `rescore_feedback`).
- Derive edges from the same emitted-outcome/destination semantics YAML generation uses (`_emittedVerbs`, `_dispatchedDestinations`, `_requiredTerminalBlocks`, `_KIND_TO_DESTINATION`, `_outcomeStateLines`'s transition branch), so the graph can never disagree with the emitted loop's *authored* transitions. Implicit `on_max_steps`/`on_error` routes are deliberately omitted (see Contract Semantics).
- Migrate `summarizeTransitions` to consume the shared analysis (chain length from the `goto` edges) while preserving its existing return shape and values. `chainLenFrom`'s exact semantics must be reproduced from the edge list: a fresh visited set per dispatch target, a revisit contributes 0, a `goto` to a non-outcome contributes 1 and ends the chain. While there, add the missing `stopDestination` entry to `summarizeTransitions`'s JSDoc `@returns`.
- Render the graph and cycle/unreachable lines in `policy-router-builder.html.tmpl` for issue_lifecycle mode from the same analysis, as a **text/list adjacency rendering** in a new `renderTransitionGraph(model, analysis)` function (one line per node listing its outgoing edges by kind, then one line per `goto` cycle as a warning, one per `rescore_feedback` cycle as info, one per unreachable `outcome` node as a warning). No SVG/canvas layout: the page is self-contained with no diagram precedent, and a hand-rolled layout engine is out of scope for this issue (follow-up if wanted). Warnings describe possible transitions only; no action effects.
- Export `analyzeTransitions` through the `window.PolicyBuilderCore` bridge; regenerate golden HTML through the generator.

## Integration Map

- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: new `analyzeTransitions`, `summarizeTransitions` migration, bridge export.
- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: graph/cycle presentation in the lifecycle summary area.
- Tests: `scripts/tests/js/policy_validator.test.mjs` (node:test), `scripts/tests/test_policy_builder_node_gate.py`, `scripts/tests/test_policy_builder_emit.py` golden regeneration.
- Docs: `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` structural-analysis limits.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/templates/policy-router-builder.html.tmpl:1592` — the only caller of `summarizeTransitions(model)` in the codebase (confirmed via `ll-code callers-of`, no hits, plus a repo-wide grep); this is also the insertion point for a new `analyzeTransitions(model)` call feeding the graph panel.
- `scripts/little_loops/cli/artifact/policy_builder.py` `cmd_policy_builder()` (`:62`, reads/inlines both files at `:101-115`) — no code change needed here, but any new `.mjs` export must remain valid when spliced verbatim into the template's `<script type="module">` block.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/templates/policy_builder_core.mjs:1652` — a second read site of `_KIND_TO_DESTINATION[t.kind]`, independent of `summarizeTransitions`'s reads at `:1348`/`:1350`; verify it stays correct once the constant is also consumed by `analyzeTransitions`.
- `scripts/little_loops/templates/policy_builder_core.mjs:2047,2054,2081` — a second, independent consumer (the serialization path near `_outcomeStateLines`) calls `_emittedVerbs(model)`, `_dispatchedDestinations(model)`, and `_requiredTerminalBlocks(model)` directly; these are the same private helpers `analyzeTransitions` is built from and must keep working unchanged.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:458-459` — a second call site (`computeSummary`-area) calls `_emittedVerbs(model)`/`_dispatchedDestinations(model)` directly, separate from the known `:1211` `summarizeTransitions` call.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:1222` — inside the same `updatePreview` block as the known `:1211` call, `_dispatchedDestinations(model)` is called again to build `reached`.
- `scripts/little_loops/cli/artifact/__init__.py:48,59,197` — CLI registration chain for `cmd_policy_builder` (import, `__all__` re-export, `main_artifact` dispatch); no code change expected, listed for completeness of the call chain.

_Anchor refresh — `/ll:refine-issue` — 2026-09-17 (same corrected numbers as the Program Design → Call Path refresh; recorded here too since this subsection is keyed by caller):_

- `scripts/little_loops/templates/policy-router-builder.html.tmpl:1592` (was `:1211`) — the `summarizeTransitions(model)` call inside `updatePreview()`; re-confirmed still the sole caller.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:1603` (was `:1222`) — second `_dispatchedDestinations(model)` call in the same `updatePreview()` block, building `reached`.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl:535-536` (was `:458-459`) — `computeSummary(model)` calls `_emittedVerbs(model)`/`_dispatchedDestinations(model)` directly, independent of `summarizeTransitions`.
- `scripts/little_loops/templates/policy_builder_core.mjs:2645, :2652, :2679` (was `:2047, :2054, :2081`) — `_serializeIssueLifecycle`'s calls to `_emittedVerbs(model)`, `_dispatchedDestinations(model)`, `_requiredTerminalBlocks(model)`.
- `scripts/little_loops/templates/policy_builder_core.mjs:2250` (was `:1652`) — the per-outcome `_KIND_TO_DESTINATION[t.kind]` read inside the YAML transition-line serializer.
- `scripts/little_loops/templates/policy_builder_core.mjs:2958-3007` (was `:2334-2375`) — the `window.PolicyBuilderCore` bridge object; `summarizeTransitions` is exported at `:2998` under the `// ENH-3491` group, `_emittedVerbs`/`_dispatchedDestinations`/`_requiredTerminalBlocks` at `:2973`/`:2977`/`:2978`. A new `analyzeTransitions` export would join its own `// FEAT-3501 (...)` group, appended after the current last group (`// FEAT-3488`, `:2999-3005`), per this file's chronological-grouping convention.
- `scripts/tests/js/policy_validator.test.mjs:1032-1043` (was `:1019-1030`), `:1052-1063` (was `:1039-1050`), `:1257-1260` (was `:1244-1247`) — the three `summarizeTransitions` tests named in this issue's Tests subsection; line numbers corrected, tests themselves unaffected.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — confirmed to embed byte-mirrored copies of every symbol above (e.g. `summarizeTransitions` at its own line 2381, bridge exports at 3422-3447); regeneration remains required as already noted.
- `docs/guides/POLICY_ROUTER_GUIDE.md:318` and `docs/reference/CLI.md:5083` — both prose descriptions of the transition summary re-confirmed still present at these lines; the guide change that triggered this re-refine was elsewhere in the file, not at this anchor.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5083` (`#### ll-artifact policy-builder` section) — carries its own independent prose describing the current transition summary ("distinguishing reachable verbs, verification status, and attempts vs. raw step count"); not named in this issue's Related Key Documentation table or Docs bullet, but must stay accurate alongside the guide (precedent: ENH-3487 updated both `CLI.md` and `POLICY_ROUTER_GUIDE.md` together for this same feature area).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py` (`test_policy_builder_renders_byte_identically_to_golden_fixture`, `:62-68`) — asserts `cmd_policy_builder()` output is byte-identical to `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`; will break on any `.mjs`/`.tmpl` change (including the new bridge export and graph markup) until the fixture is regenerated. Not one of the three test files this issue already names.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — the golden fixture itself; must be regenerated by running `cmd_policy_builder` and overwriting this file's bytes (no dedicated regeneration script/flag exists in the repo — confirmed via repo-wide search for `UPDATE_GOLDEN`/`--update-golden`/`regenerate_golden`).
- `scripts/tests/js/policy_validator.test.mjs:1019-1030` (`summarizeTransitions computes stepsPerAttempt/attempts from the reachable goto chain`) — asserts exact `stepsPerAttempt`/`attempts` values derived from `chainLenFrom`'s goto-only traversal; must still pass after migrating chain-length computation onto `analyzeTransitions`.
- `scripts/tests/js/policy_validator.test.mjs:1039-1050` (`summarizeTransitions handles a goto cycle without infinite recursion`) — directly exercises the cycle guard being migrated; most likely to catch behavioral drift if `analyzeTransitions`'s cycle detection uses different seen-set semantics than `chainLenFrom`'s per-branch fresh `Set` (reset per dispatch target, `:1388`).
- `scripts/tests/js/policy_validator.test.mjs:1244-1247` (`summarizeTransitions.maxStepsNote never classifies the budget route as success`) — depends transitively on `stepsPerAttempt` correctness.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Established convention: this codebase's shape for "shared analysis feeding multiple consumers" is each consumer calling the shared helper directly and independently, never one consumer wrapping another's output — evidence: `summarizeTransitions` (`policy_builder_core.mjs:1337`), `_serializeIssueLifecycle` (`policy_builder_core.mjs:2047`), and the template's own `computeSummary` (`policy-router-builder.html.tmpl:458-459`) each call `_emittedVerbs`/`_dispatchedDestinations` directly rather than through one another.
- Established convention: `window.PolicyBuilderCore` bridge additions are grouped under a `// <ISSUE-ID> (<short description>)` comment naming every new export added, in chronological order — evidence: `policy_builder_core.mjs:2334-2375` (`// FEAT-3474`, `// ENH-3492`, `// BUG-3489`, `// ENH-3491` groupings).
- No existing JS code in this codebase defines a typed node/edge graph structure — searched repo-wide across `*.js`/`*.mjs`; the only hit was vendored `htmx.js` DOM-node references, not a data graph. Nearest structural precedent is Python: `dependency_graph.py`'s `DependencyGraph` dataclass (parallel adjacency dicts `blocked_by`/`blocks`/`depends_on_edges`) and its `detect_cycles()` (three-color DFS unioning two edge-set kinds to distinguish cycle kinds — `dependency_graph.py:380-432`), and `fsm/validation/reachability.py`'s BFS-with-visited-set (`_dominated_by_any`, `:303-350`) which computes neighbors on the fly rather than via a precomputed adjacency map. Cross-language shape references only, nothing directly importable.
- Existing `summarizeTransitions` tests assert individual return fields (`.verification`, `.stopsAfterImplement`, `.stepsPerAttempt`) rather than a full-object deep-equal snapshot — evidence: `scripts/tests/js/policy_validator.test.mjs:1039-1050` (goto-cycle test), `:1005` (unreachable-verify test). This codebase's only full-object snapshot convention is a golden-file fixture compare, used for `serializeLoopYaml` output (`policy_validator.test.mjs:94-98`), not for `summarizeTransitions`.

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- No precedent exists anywhere in this codebase for rendering a node/edge diagram inside an HTML template: the repo has exactly one `.html.tmpl` file (`policy-router-builder.html.tmpl` itself), and it contains no `<svg>`/`createElementNS`/`<canvas>`/DOM-node-graph-layout code. The nearest structurally-similar precedent, `ll-issues clusters` (`cli/issues/clusters.py`), renders a relationship graph as ANSI box-drawing characters to a terminal — a different medium (text, not DOM/SVG) — so it informs layout/adjacency thinking only, not markup to copy.
- This template's existing panel-rendering functions follow a `render<Noun>(model, ...)` naming convention (`renderDimensions`, `renderFallback`, `renderOutcomes`, `renderLifecycleOutcomes`, `renderRules`, `renderTryIt`, `renderMessages(model, diagnostics)`, `renderScenarios`, `renderPresetButtons`, `renderConfidenceGateInfo`, all in `policy-router-builder.html.tmpl`) — a new graph-panel render function would follow this naming shape for consistency.
- `summarizeTransitions`'s JSDoc (`policy_builder_core.mjs:1920-1931`, immediately preceding its export) follows a fixed shape in this file: a prose paragraph naming the triggering issue ID, a purity/determinism note ("Pure — derived from ... never from template `state` directly"), then `@param`/`@returns` tags with an inline object-shape type — `analyzeTransitions`'s own JSDoc would follow the same shape per this file's convention.
- The "Result" panel's `<h2>` is at `policy-router-builder.html.tmpl:256`, with the existing `#transition-summary` element immediately below at `:258` (was cited as `:234-252`/`:237` in an earlier pass) — this is the current DOM insertion point for a graph/cycle-warning panel.

## Implementation Steps

1. **Snapshot first, in its own commit** (ENH-3035 discipline): capture current `summarizeTransitions` outputs as JSON deep-equal fixtures in node:test for the seed, every `taskPresets()` entry, `blankModel("issue_lifecycle")`, **plus** the goto-cycle model from `policy_validator.test.mjs:1052` and the unreachable-`verify` model from `:1018` (the seed/presets/blank set contains no cycles and no unreachable verbs, so it alone cannot guard the cycle-guard migration).
2. Add `analyzeTransitions` in core.mjs per Contract Semantics, alongside `_emittedVerbs`/`_dispatchedDestinations`/`_requiredTerminalBlocks`; export it through the bridge under a `// FEAT-3501` group.
3. Migrate `summarizeTransitions`'s chain-length computation onto the `goto` edges and assert the step-1 snapshots still match; fix the JSDoc `@returns` to include `stopDestination`.
4. Add `renderTransitionGraph(model, analysis)` (text/list rendering) and its DOM element next to `#transition-summary`; call both `summarizeTransitions` and `analyzeTransitions` from `updatePreview()`; regenerate golden HTML; update `POLICY_ROUTER_GUIDE.md` and `CLI.md`.
5. Verify with `node --test scripts/tests/js/*.test.mjs` via the pytest gate plus the emit/golden tests; record the manual browser check per the ENH-3487 manual-testing decision.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

_Anchors below were folded to the 2026-09-17 refreshed numbers (the original wiring pass cited `:234-252`/`:237`/`:1211`/`:2047-2081`/`:458-459`, now stale)._

- Add the graph/cycle-warning panel markup in `policy-router-builder.html.tmpl` in the `Result` panel (its `<h2>` at `:256`), alongside the existing `#transition-summary` element at `:258` — the actual DOM insertion point, distinct from the `updatePreview()` script-logic call site at `:1592`.
- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` after implementation by running `cmd_policy_builder` and overwriting the fixture's bytes (no scripted regeneration mechanism exists in the repo); `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` will fail until this is done.
- Update `docs/reference/CLI.md`'s `ll-artifact policy-builder` section (`:5083`) alongside `POLICY_ROUTER_GUIDE.md`, per the ENH-3487 precedent of updating both together.
- Verify the second `_emittedVerbs`/`_dispatchedDestinations`/`_requiredTerminalBlocks` consumer at `policy_builder_core.mjs:2645-2679` (`_serializeIssueLifecycle`) and the template's second `_emittedVerbs`/`_dispatchedDestinations` call site at `:535-536` (`computeSummary`) remain correct and unaffected by the `analyzeTransitions` extraction.
- Follow the Python `DependencyGraph.detect_cycles()` test-shape precedent (`scripts/tests/test_dependency_graph.py:504-586`, `TestCycleDetection`) for structuring new `cycles`-field tests — no JS precedent for a typed node/edge graph return value exists in this codebase.

## Impact

- **Priority**: P3 - same tier as FEAT-3488; independent of it.
- **Effort**: Small/Medium - one pure helper, one consumer migration, one presentation panel.
- **Risk**: Low - summary output is snapshot-guarded; no YAML emission changes.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Summary and graph consume one `analyzeTransitions` contract; `summarizeTransitions` return values are JSON deep-equal to the pre-migration snapshots for the seeded lifecycle model, every preset, the blank model, the goto-cycle model, and the unreachable-`verify` model (snapshots captured in a commit that precedes the migration).
- [ ] `analyzeTransitions` follows the Contract Semantics: node IDs are YAML state names; `finish`-with-action yields a `terminal` edge to `done`; `finish`-without-action yields no edge; `on_max_steps`/`on_error` routes are absent; non-lifecycle models return the empty analysis; `nodes`/`edges` ordering is deterministic.
- [ ] Tests cover goto chains, goto cycles (including a self-loop), rescore feedback (`nodeIds: ["score", "policy_dispatch", <outcome>]`), unreachable outcomes, `finish` with and without an action, and explicit stop/skip/attention terminals from ENH-3492.
- [ ] The panel renders `goto` cycles and unreachable `outcome` nodes as warnings, `rescore_feedback` as informational, and never warns on an unreachable terminal node; the seed and every preset render with zero warnings.
- [ ] Structural warnings make no claims about actual action outcomes or inevitable nontermination.
- [ ] Golden HTML and Node/Python gates pass; the browser bridge exports the new helper.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` document the structural-analysis contract's limits: no execution-outcome or nontermination claims, and the omitted implicit `on_max_steps`/`on_error` routes.

## Scope Boundaries

Excludes scenario suites, traces, expectations, and coverage (FEAT-3488) and connected execution (FEAT-3498). No skill, shell, LLM, or issue mutation executes from the analysis. Excludes any SVG/canvas diagram layout (text/list rendering only), graph analysis for `decision_table`/`rubric` modes (empty analysis returned), and representing the implicit `on_max_steps`/`on_error` routes as edges.

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
- `/ll:confidence-check` - 2026-09-18T03:36:59 - `d695727c-523e-4f8f-9435-490cc16d6455.jsonl`
- `/ll:verify-issues` - 2026-09-18T03:34:39 - `3cbf9e05-8884-443a-be0b-4fb3a3466d9a.jsonl`
- manual review - 2026-09-17 - pinned Contract Semantics (finish/done edges, implicit routes omitted, reachability, cycle records, no diagnostics field, non-lifecycle return, ordering), text/list rendering, expanded snapshot set and ACs, folded stale wiring anchors
- `/ll:confidence-check` - 2026-09-18T03:05:11 - `51bcd34b-4f80-4b37-8ce2-712eaadce80b.jsonl`
- `/ll:reconcile-issue` - 2026-09-18T02:59:34 - `875cb38b-51ff-4136-a01d-589b447fa745.jsonl`
- `/ll:refine-issue` - 2026-09-18T02:55:58 - `7d3a461e-3fe9-4958-b2ec-13988dba9be7.jsonl`
- `/ll:wire-issue` - 2026-09-17T21:47:21 - `7963a725-b58e-4327-aa83-67156f2c5955.jsonl`
- `/ll:refine-issue` - 2026-09-17T21:38:23 - `c96a075b-f0e6-4219-b95e-97d676bc5f62.jsonl`
- `/ll:verify-issues` - 2026-09-17T21:31:46 - `270c2766-2f75-4410-a3ba-53dfe4b6f1e8.jsonl`
- `/ll:format-issue` - 2026-09-17T21:24:30 - `fabca22b-468e-4dd5-8426-9cc105e3ce12.jsonl`
