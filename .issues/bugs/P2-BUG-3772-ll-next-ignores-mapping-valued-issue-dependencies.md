---
id: BUG-3772
type: BUG
title: ll-next ignores mapping-valued issue dependencies
priority: P2
status: open
discovered_by: capture-issue
discovered_date: '2026-10-08'
captured_at: '2026-10-08T15:14:55Z'
verify_verdict: VALID
relates_to:
- FEAT-3713
- FEAT-3561
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
risk_factors:
- id: identity-terminal-contract
  domain: outcome
  criterion: complexity
  description: Graph protocol and terminal/ambiguity contract change spans state,
    graph and candidates with a shared live-source predicate
- id: raw-rendering-unpinned
  domain: outcome
  criterion: ambiguity
  description: Deterministic escaped raw rendering and anonymous-source diagnostic
    subject are described but not pinned to an exact format
---

# BUG-3772: ll-next ignores mapping-valued issue dependencies

## Summary

`ll-next` can recommend implementation while ignoring nonempty mapping-valued dependency metadata. The shared runtime parser recognizes mapping keys as relationships, while the arena discards them. Reject affected implementation/root-blocker offers with captured unsupported-shape evidence; do not infer readiness or executable ordering from those keys.

## Current Behavior

`_split_ids` in `scripts/little_loops/next_arena/state.py` accepts strings and lists/tuples but returns an empty list for mappings. `_merge_edge_ids` then falls back to body relationships. `IssueParser.parse_file` instead converts truthy non-string frontmatter relationship values with `list(fm_val)`, retaining mapping keys. This loses real runtime prerequisites or substitutes a different body edge set.

Temporary probes on inspected branch `main` at `0d111015e` (2026-10-08) reproduced:

- Nonempty mappings in each of `blocked_by`, `depends_on` and one-sided `blocks` leave the affected `implement-issue` assessment eligible with `satisfied: true` and no unresolved evidence. The runtime parser retains the named key.
- Mutual `depends_on` mappings produce no arena cyclic IDs, while the runtime `DependencyGraph.detect_cycles` finds FEAT-001 → FEAT-002 → FEAT-001 and execution waves abort.
- An open BUG-010 plus a done duplicate BUG-010, where only the done record declares `blocks` on ready FEAT-020: a list declaration excludes FEAT-020 with `ambiguous_issue_id`; changing that declaration to a mapping makes FEAT-020 eligible. Discarding all terminal-source shape facts would leave this blind spot unfixed.

These are disposable probe results, not quotations from source files. No project backlog or executor code was changed.

## Steps to Reproduce

1. Create a temporary project with `scripts/tests/next_arena_support.py` (`make_project`), then write canonical P3 FEAT-001/FEAT-002 files with `status: open`, `confidence_score: 90`, `outcome_confidence: 80` and a Small effort section. Use this frontmatter in both files, reversing the named key in FEAT-002:

   ```yaml
   depends_on:
     FEAT-002: ignored
   ```

2. Collect with `collect_project_state` and a fixed UTC `as_of`, then call `assess_candidates`. Both implementation assessments pass and the graph misses the cycle.
3. Parse the same files with `IssueParser.parse_file`, build the ordinary `DependencyGraph` and call `detect_cycles`/`get_execution_waves`. The mutual mapping keys form a cycle and wave construction raises `ValueError`.
4. Separately place a `blocks` mapping on an outside source naming the ready target. Include the terminal duplicate case above to verify identity ambiguity cannot be erased by terminal filtering.

## Expected Behavior

A nonempty mapping-valued relationship is unsupported input. Preserve captured facts and fail closed for affected offers using the following policy:

| Declaration | Affected offer |
|---|---|
| Live source's `blocked_by` or `depends_on` mapping | Its own implementation/root-blocker offer |
| Non-terminal source's `blocks` mapping | Each existing target named by an exact mapping key; the source itself stays eligible if otherwise valid |
| Terminal source's `blocks` mapping with an ambiguous named identity | Named targets remain excluded; identity ambiguity takes precedence over terminal satisfaction |
| Uniquely terminal named source, or terminal anonymous source, with a `blocks` mapping | No target exclusion |
| Unrelated mapping keys, unknown target keys, or terminal own-field mappings | No fabricated graph node or named dependency edge |

A named record is live when its identity is ambiguous or its captured lifecycle is non-terminal; an anonymous record is live only when non-terminal. Apply terminal rules to the captured lifecycle/provenance, not the raw status string or `completed_at` alone. Deferred/in-progress/blocked/invalid-status sources remain non-terminal. Preserve ambiguity for duplicate full IDs and shared exact filename numbers; do not collapse conflicting records to an arbitrary status.

Mapping keys are exact parsed strings: do not strip whitespace, expand numeric IDs, normalize digits or introduce aliases. Keys may identify affected existing targets, but never become resolvable prerequisite edges. The reproduced mapping-key cycle is excluded as unsupported input, with `in_cycle: false` and no invented `dependency_cycle` diagnostic.

A nonempty mapping suppresses body fallback for its field on **all** sources, including terminal records. Only an empty mapping preserves current falsy/body fallback. Supported string/list relationships keep their current policy. Refinement remains ungated by prerequisites.

Affected target explain must name the declaring source and field and show an escaped raw excerpt with an explicit truncation marker when necessary. Keep full captured raw provenance on the source; avoid repeating a large `blocks` mapping in every target's output.

## Motivation

A copied implementation recommendation can start work whose actual prerequisites are unresolved. Missing arena edges must not become persuasive readiness evidence, and a malformed declaration must not weaken existing identity safety.

## Proposed Solution

Capture immutable unsupported relationship facts on `SourceRecord`, then feed them into `build_issue_graph` as unresolved `Prerequisite` entries with `reason=unsupported_relationship_shape`, `prerequisite_id=None` and the declaring source path. Extend the existing target-keyed unresolved pass for one-sided `blocks`; apply identity-aware terminal exemptions there, after the inventory exists.

Reuse `_prerequisites_gate` for implementation and root-blocker assessments. Keep gate code `prerequisites_unresolved`; distinguish unsupported input through the unresolved reason and field/source/raw evidence. No new gate status, `ProjectState` field, adjacency from mapping keys, separate blocker veto or per-candidate file read is needed.

`build_blocker_index` already treats a `None` prerequisite as non-exclusive. A dependent with a **supported unresolved prerequisite plus unsupported mapping evidence** is `multi_blocked`, never immediately unlocked. A dependent with only unsupported evidence has no named root entry. Suppressing mapping body fallback removes stale direct/leverage edges; valid independent edges still count normally. A source whose only outgoing relationships are unsupported `blocks` mappings has no graph-derived blocker significance until that metadata is corrected; this repair does not invent leverage from unsupported keys.

FEAT-3713 independently rejects sprint executor relationship mismatches as `executor_dependency_mismatch`. It must work before and after this repair and cannot waive unsupported input as an allowed pending internal edge. Reuse captured evidence where available, while preserving its independent list/scalar/nested-entry guards. Neither issue blocks the other. Shared `IssueParser` and executor behavior are outside this fix.

## Integration Map

### Files to Modify

- `scripts/little_loops/next_arena/state.py` — define the new frozen evidence type; extend `SourceRecord` and its sole constructor in `build_source_record`; capture mappings for every lifecycle; suppress nonempty-mapping fallback. No shape diagnostic is emitted before identity is resolved.
- `scripts/little_loops/next_arena/graph.py` — extend `GraphRecord`, add `REASON_UNSUPPORTED_SHAPE`, and emit deterministic unresolved evidence and live-source diagnostics in the existing passes with identity-aware terminal suppression. Update `Prerequisite` documentation: `None` also denotes unsupported input, not only an unanchored source.
- `scripts/little_loops/next_arena/candidates.py` — `_prerequisites_gate` uses indexed captured-source lookup and adds bounded unsupported evidence and reason text.
- Existing state, identity, assessment, blocker, CLI, determinism and performance test modules listed below.
- `docs/reference/CLI.md` — document `unsupported_dependency_shape`, unsupported-input exclusions and bounded explain evidence; `docs/reference/API.md` — describe the captured relationship facts and unresolved reason.

### Dependent Files

- `scripts/little_loops/next_arena/blockers.py` (`build_blocker_index`, `_assess_root`) — no production change expected; verify mixed known/unsupported prerequisites and root gating.
- `scripts/little_loops/next_arena/render.py` (`collect_diagnostics`, `render_explain_text`) — no production change expected. Subject filtering drops an outside source's diagnostic from target explain, so target gate text must carry its evidence.
- `scripts/little_loops/next_arena/output-schema.json` — no change/version bump expected: gate codes, diagnostics and dependency evidence are extensible. Do not regenerate unless `render.build_output_schema` changes.
- `scripts/little_loops/issue_parser.py` (`IssueParser.parse_file`) and `scripts/little_loops/cli/next.py` (`main_next`) — parsing reference and CLI consumer, unchanged.

### Verified Code Constraints

- `parse_frontmatter` uses `yaml.BaseLoader`: scalar mapping keys are strings, while values may contain nested lists/mappings. Capture the rendered raw value immediately; `SourceRecord.frontmatter` is only shallowly protected by `MappingProxyType`.
- `build_project_state` resolves identity before calling `build_issue_graph`. The graph's `_resolve` checks ambiguity **before** terminal status; its anonymous-source path skips terminal declarations. Preserve these safety rules.
- `ProjectState.record_for_path` is an existing O(1) lookup. Resolve each unsupported prerequisite's `source_paths` through it and match only the captured field equal to `p.kind`. The graph already routes a `blocks` entry to the exact target; do not rescan all source records or scan the K-key tuple again for every affected target.
- `SourceRecord` is a frozen dataclass with one constructor. Tuples and rendered strings protect new provenance from mutation; ordinary dictionaries do support equality, but do not provide this immutability.
- `state.py` already imports `graph.py`. Use a `TYPE_CHECKING` import for the state-owned evidence type in the graph protocol, matching the existing `ProjectState` pattern, to avoid a runtime import cycle.
- Existing operation-count checks measure graph/leverage work on **supported** relationships; the 10k assessment test is opt-in. Keeping them green alone does not measure the new mapping path or provenance/output costs.
- List items that are mappings are a separate existing shape behavior, outside this repair. No new regex, parser-wide normalization or dependency-validation subsystem is needed.

## Program Design

### Types

- New `UnsupportedRelationship` frozen dataclass in `state.py`: `(field: str, keys: tuple[str, ...], raw: str)`. `raw` is a deterministic escaped single-line rendering of the parsed mapping, including nested values; original YAML bytes remain in `SourceRecord.content`.
- New `SourceRecord.unsupported_relationships: tuple[UnsupportedRelationship, ...]`: populated for **every** nonempty mapping, including terminal sources; empty for supported values and empty mappings. Preserve exact keys and deterministic field ordering.
- New `REASON_UNSUPPORTED_SHAPE = "unsupported_relationship_shape"` beside graph resolution constants. Retain the existing `Prerequisite` shape and gate code.
- New `UNSUPPORTED_RAW_EXCERPT_LIMIT = 512` in `graph.py`, reused by `candidates.py`: at most 512 characters from captured `raw`, with explicit `raw_truncated` evidence and a human truncation marker. Bound diagnostic and reason text too; do not construct/serialize the full raw mapping separately for every target.

### Signatures

- `build_issue_graph(records, node_ids, ambiguous, *, counter=None)` — unchanged; `GraphRecord` gains a read-only `unsupported_relationships` property.
- `_prerequisites_gate(state: ProjectState, issue_id: str) -> tuple[GateResult, dict[str, Any]]` — unchanged.
- Existing `evidence["dependencies"]["unresolved"]` entries retain `kind`, `prerequisite_id`, `reason`, `status` and `source_paths`; unsupported entries additionally carry `{raw_excerpt, raw_truncated}`. `kind` names the field and `source_paths` names its declaring source. Stable order and deduplication by declaring source/field; no second unsupported list and no unrelated field evidence. Unsupported reason text names the shape/field/source rather than labeling the entry as an unanchored source.

### Call Path

`build_source_record` detects `isinstance(value, Mapping) and bool(value)`, captures immutable facts and suppresses fallback → `build_project_state` resolves identity → `build_issue_graph` emits `Prerequisite(kind, None, REASON_UNSUPPORTED_SHAPE, declaring_status, (declaring_path,))` for affected nodes → `_prerequisites_gate` recovers the matching frozen fact via `record_for_path` and renders bounded evidence → existing implementation/root-blocker assessment and explain rendering.

After collecting node identity, use the same live predicate for own-field and one-sided `blocks` facts. Emit one graph-side source-subject `unsupported_dependency_shape` diagnostic per live `(path, field)`, with field/path/a bounded escaped raw excerpt and an explicit truncation marker, using the same 512-character limit and existing `Diagnostic` sorting. Full raw provenance remains in `UnsupportedRelationship.raw`; an own-source diagnostic must not bypass target explain's excerpt limit. Use the source node as subject, or `None` for anonymous sources. Uniquely terminal and terminal anonymous sources keep captured shape facts but emit neither graph veto nor diagnostic; ambiguous terminal named records keep both. Aggregate through `build_project_state` so rebuilt graph/state diagnostics remain consistent. Never use a node's arbitrary merged status to exempt an ambiguous source.

Graph work is O(records + supported edges + captured mapping keys), apart from existing deterministic sorting. Count mapping visits with `OpCounter`. Gate provenance lookup is O(1) per unsupported entry (there are at most three fields per source); target raw excerpts are bounded so wide mapping fan-out does not repeat O(K)-sized raw strings K times. Source diagnostics are bounded as well and captured once; the complete raw rendering is frozen once on the source rather than repeated in output.

## Implementation Steps

1. Write failing capture/assessment tests for all three fields, the mutual mapping-key cycle, outside one-sided `blocks` and a terminal duplicate declaring that mapping. `commands.tdd_mode` is enabled.
2. Add captured facts and unconditional mapping body-fallback suppression. Extend the graph protocol and unresolved pass; retain facts through identity resolution and use one identity-aware live predicate for unsupported prerequisites and graph-side diagnostics.
3. Add indexed provenance recovery and bounded target text/JSON evidence. Verify field isolation when a declaring source has several unsupported fields. Keep refinement policy and existing public unresolved keys unchanged.
4. Add the focused regressions below, update CLI/API documentation, and run the focused suite followed by the authoritative `python -m pytest scripts/tests/` gate. Add a versioned changelog entry during release preparation, not an `[Unreleased]` section in this repair.

### Regression Coverage

| Module | Required cases |
|---|---|
| `scripts/tests/test_feat3561_phase_b_state.py` | Parameterize all three nonempty fields, flow/block YAML, nested values and raw capture on terminal sources; exact keys; empty-map fallback and nonempty-map suppression, including terminal records. |
| `scripts/tests/test_feat3561_phase_b_identity.py` | Mapping `blocks` from anonymous sources; conflicting full IDs and shared filename numbers; active/terminal and terminal/terminal conflicts cannot satisfy targets, while uniquely terminal and terminal anonymous sources do. Keep rebuilt graph/state diagnostics consistent. |
| `scripts/tests/test_feat3561_phase_d_assess.py` | Mapping-key cycle excluded as unsupported (no invented cycle); outside prerequisite; outside multi-key `blocks` affects exact targets only and leaves its source/unrelated issues eligible. Mixed fields produce only relevant target evidence. Terminal lifecycle/provenance, deferred/in-progress/invalid sources, and refinement parity. |
| `scripts/tests/test_feat3769_blockers.py` | Mapping-affected root and root named by outside `blocks` are excluded. Supported unresolved prerequisite plus unsupported evidence is `multi_blocked`, never `immediate`. Unsupported-only evidence creates no named root; suppressed body edge creates no stale direct/leverage count. |
| `scripts/tests/test_feat3561_phase_e_cli.py` | Text and schema-valid JSON `--explain implement-issue TARGET` for **outside-source** `blocks`, as well as own-field mappings. Excluded existing targets exit 0 and show field/path/raw excerpt; large raw values explicitly truncate in gates, evidence and source diagnostics. |
| `scripts/tests/test_feat3561_phase_d_determinism.py` and state enumeration tests | Reverse/shuffle actual source enumeration with mapping-heavy multi-source/multi-field fixtures; compare captured records, graph, diagnostics and serialized assessments. Reversing write order alone is insufficient because collection sorts paths. |
| `scripts/tests/test_feat3561_phase_f_perf.py` | Add in-memory wide mapping fan-out fixtures to counted graph work; bound indexed provenance lookups and total per-target excerpt size during assessment; exercise mapping capture/explain in the one-read/parse and no-downstream-I/O tests. Keep existing supported-graph performance checks. |

Use literal block YAML for explicit block-style fixtures. The shared `issue_text` helper also emits valid flow YAML for simple string-key/string-value dictionaries; this is not a required workaround. Pin padded and differently spelled keys (`' FEAT-002 '`, `FEAT-2`, scalar key `2`) without aliasing them to `FEAT-002`.

## Impact

- **Priority:** P2 — runnable recommendations can omit actual prerequisites or identity ambiguity.
- **Effort:** Small — three production modules, existing captured-state/gate mechanisms.
- **Risk:** Low to moderate — the graph protocol and terminal/ambiguity contract change; focused identity, determinism and mapping-specific performance regressions are required.
- **Breaking Change:** No — additive diagnostic/evidence, supported input behavior preserved.

## Root Cause

`_split_ids` discards nonempty mappings and `_merge_edge_ids` treats the empty result as body-fallback input. `IssueParser.parse_file` instead retains their keys. The graph receives only normalized tuples, so lost shape/provenance cannot be recovered downstream. The missing cycle is a consequence; this repair excludes unsupported input rather than turning keys into executable graph edges.

## Acceptance Criteria

- [ ] Nonempty mapping-valued `blocked_by`, `depends_on` and `blocks` produce captured immutable facts and unsupported unresolved evidence on affected nodes; no affected implementation/root-blocker offer is emitted. Refinement and unrelated valid issues retain their current behavior.
- [ ] Mutual mapping-key cycles and mappings hiding outside prerequisites are excluded as unsupported input without invented adjacency/cycle diagnostics. One-sided `blocks` matches exact existing target keys, leaves its source otherwise eligible and preserves anonymous/conflicting-source evidence independent of enumeration order.
- [ ] Terminal suppression is identity-aware: uniquely terminal named and terminal anonymous sources do not exclude targets; a terminal declaration with an ambiguous named identity still does. Lifecycle provenance and invalid/non-terminal states retain the core policy.
- [ ] Empty mappings preserve body fallback; nonempty mappings suppress it on all sources. Supported string/list semantics are unchanged. Mixed supported/unsupported prerequisites yield `multi_blocked`, never immediate unlock; unsupported-only evidence and suppressed body edges invent no named root/direct/leverage relationship.
- [ ] Target text and JSON explain show only relevant field/source/raw excerpts, with explicit truncation above 512 characters. Full raw provenance stays captured on the source. Multi-key mappings use indexed lookups and bounded target output without per-target record/key scans or rereads.
- [ ] Mapping-specific capture, identity, assessment, explain, determinism and performance regressions pass, followed by the authoritative full local suite. No shared parser/executor behavior or output-schema version changes are introduced.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/CLI.md` | ll-next offer eligibility, diagnostics and explain. |
| `docs/reference/API.md` | Captured arena state and graph/assessment contracts. |

## Review Notes

Pre-implementation review on `main` at `0d111015e` (2026-10-08): disposable probes reconfirmed all three mapping fields and the terminal-duplicate blind spot. Focused existing state/identity/assessment/blocker/CLI/determinism/performance baseline: **298 passed, 2 skipped**. This verifies the surrounding contracts, not the unimplemented mapping repair. Format/design checks and learning-test assessment were also run; no learning proof is required and no active required decision rules were found.

`/ll:advise --signal user_requested --host claude-code --model opus` supported the corrections (confidence **0.82**). Adopted the identity-aware live predicate, graph-side diagnostics, indexed provenance, bounded target output and extending existing unresolved evidence instead of a duplicate list. Declined stripped-key matching because runtime and FEAT-3713 use exact keys, and retained a frozen full raw rendering because frontmatter protection is shallow. Opus's dissent proposed omitting diagnostics or attaching own-field evidence to all terminal nodes; live-only diagnostics keep the fixable source finding without completed-history noise. Original pre-review scores are retained, not claimed as a new confidence assessment.

## Status

**Open** | Created: 2026-10-08 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-08_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Risk Factor Delta
- Added: `identity-terminal-contract`, `raw-rendering-unpinned`
- No longer reported: none
- Retained: none
- Changed fields: none

## Session Log
- `/ll:confidence-check` - 2026-10-08T17:40:49 - `cb0aee70-6b64-42fa-afd0-739f77347cf5.jsonl`
- `/ll:confidence-check` - 2026-10-08T16:05:17 - `658f5ae0-b69c-4a05-9e63-5ba97e164dc7.jsonl`
- `/ll:advise` - 2026-10-08T15:59:38 - `27057456-16a6-48c8-bc88-5010ad985f61.jsonl`
- `/ll:ready-issue` - 2026-10-08T15:59:38 - `27057456-16a6-48c8-bc88-5010ad985f61.jsonl`
- `/ll:advise` (opus, 0.80) + manual pre-implementation review - 2026-10-08 - moved evidence into the graph (no blockers/ProjectState change), added terminal-source and body-fallback-suppression rules, resolved all three risk factors
- `/ll:confidence-check` - 2026-10-08T15:38:23 - `737f28e5-338a-4b21-95a2-f4f2ed172ad3.jsonl`
- `/ll:wire-issue` - 2026-10-08T15:35:11 - `892180dc-b296-4d11-bab1-4ceacfb93394.jsonl`
- `/ll:refine-issue` - 2026-10-08T15:29:03 - `391386d4-3db8-4f5a-9e12-97e5935d2d4b.jsonl`
- `/ll:capture-issue` - 2026-10-08T15:15:05 - `c063533a-bfa9-410e-8a16-0fe48d320a3b.jsonl`
