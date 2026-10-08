---
id: BUG-3772
type: BUG
title: ll-next ignores mapping-valued issue dependencies
priority: P2
status: open
discovered_by: capture-issue
discovered_date: '2026-10-08'
captured_at: '2026-10-08T15:14:55Z'
relates_to:
- FEAT-3713
- FEAT-3561
---

# BUG-3772: ll-next ignores mapping-valued issue dependencies

## Summary

The landed `ll-next` issue generators can recommend implementation while ignoring nonempty mapping-valued dependency metadata. A two-issue mapping-key cycle disappears from the arena graph although the shared runtime parser recognizes it. Reject affected runnable offers with captured diagnostics instead of treating unsupported relationship shapes as absent prerequisites.

## Current Behavior

`next_arena/state.py::_split_ids` accepts strings and lists/tuples, returning an empty list for mappings. `_merge_edge_ids` then falls back to body relationships. `IssueParser.parse_file` instead converts truthy non-string frontmatter relationship values with `list(fm_val)`, so mapping keys are dependencies. The captured arena graph can omit real runtime edges or use a different body edge set.

A temporary two-member probe used ready open FEAT-001 and FEAT-002 with positive readiness/outcome scores and otherwise valid metadata:

```yaml
# FEAT-001
status: open
depends_on:
  FEAT-002: ignored
# FEAT-002
status: open
depends_on:
  FEAT-001: ignored
```

Observed on 2026-10-08: the core graph reported no cyclic IDs and both implementation assessments were eligible. `SprintManager.load_issue_infos` retained the mutual prerequisites; `DependencyGraph.detect_cycles()` returned FEAT-001 → FEAT-002 → FEAT-001 and execution-wave construction raised ValueError. This is temporary probe output, not a quotation from a source file. A mapping can likewise hide an unresolved outside prerequisite. A follow-up probe with outside FEAT-001 declaring `blocks: {FEAT-002: ignored}` left FEAT-002 eligible in the arena, while the runtime full-project graph retained FEAT-001 as its prerequisite; the executor member-only graph dropped it. Empty-mapping/body-fallback fixtures agreed between both paths. No project issue files or executor code were changed by the probe.

## Steps to Reproduce

1. In a temporary project created with `scripts/tests/next_arena_support.py::make_project`, write canonical P3 FEAT-001/FEAT-002 files under `.issues/features/`. Give each `status: open`, `confidence_score: 90`, `outcome_confidence: 80`, an Impact/Small effort section and the mutual mapping-valued `depends_on` fields above. Use plain YAML mappings rather than the helper that serializes scalar values.
2. Collect the project through `collect_project_state` with a fixed UTC `as_of`, then call `assess_candidates`. Inspect graph cyclic IDs and both `implement-issue` assessments: the graph misses the cycle and both assessments pass.
3. Parse those same captured fixture files with `IssueParser.parse_file` (or `SprintManager.load_issue_infos`), build the ordinary `DependencyGraph` and call `detect_cycles`/`get_execution_waves`: the mutual keys form a cycle and wave construction aborts. The fixture project is disposable; do not modify the real backlog.

## Expected Behavior

A nonempty mapping-valued `blocked_by`, `depends_on` or `blocks` is unsupported dependency input and must not establish readiness for affected implementation/root-blocker offers, including targets named by one-sided `blocks` mappings on outside sources. Retain the raw field and a useful diagnostic in explain; unrelated valid sources still produce candidates. Do not silently normalize it into an empty relationship. Empty mappings preserve the current falsy/body-fallback behavior, and valid string/list relationships retain their existing policy.

## Motivation

A copied implementation recommendation can begin work whose actual prerequisites are unresolved. Unsupported dependency metadata needs an explicit exclusion so the advisory arena does not turn missing edges into persuasive readiness evidence.

## Proposed Solution

Validate nonempty mapping relationship shapes while capturing issue sources, keep typed diagnostic/provenance evidence, and make runnable issue assessments honor that evidence. Fail closed for the affected runnable target rather than guessing mappings are absent. Reuse the captured source and shared assessment/explain path; no per-candidate file reads or runtime resolver simulation.

FEAT-3713 specifies an independent rejection of these shapes on remaining sprint members as `executor_dependency_mismatch`. That guard does not require this broader issue-generator repair and this bug adds no epic child or blocking edge. Do not change shared IssueParser/executor semantics in this fix.

## Integration Map

### Files to Modify

- `scripts/little_loops/next_arena/state.py` — captured relationship validation/provenance.
- `scripts/little_loops/next_arena/candidates.py` and `scripts/little_loops/next_arena/blockers.py` — runnable issue-gate consumption and explain diagnostics.
- Existing `scripts/tests/test_feat3561_phase_b_state.py` and candidate assessment fixtures; add focused regression cases using the shared arena helpers.

### Dependent Files

- `scripts/little_loops/next_arena/graph.py` consumes captured relationships; preserve valid graph identity/cycle policy.
- `scripts/little_loops/issue_parser.py` provides the reproduced runtime parsing reference; no modification is required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-08 — based on codebase analysis:_

- **Capture seam**: `build_source_record` (`next_arena/state.py:308`) derives all three relationship tuples at `state.py:409-411` via `_merge_edge_ids` (`:288`) → `_split_ids` (`:278`). `_split_ids` handles falsy, `str`, and `list`/`tuple`; any other type (including a nonempty `dict`) hits the final `return []`, so `_merge_edge_ids` falls back to body IDs with no diagnostic. `depends_on` has no body fallback, so a mapping there yields `()`. Both helpers have no callers outside `state.py` (tests reach them only through `build_source_record`).
- **Runtime reference**: `IssueParser.parse_file` (`issue_parser.py:4378`, `list(fm_val)`) skips falsy values and keeps mapping keys for truthy ones; `parse_frontmatter` uses `yaml.BaseLoader`, so a nested mapping arrives as `dict[str, str]` and an empty mapping is falsy. `check_format_gaps` (`malformed_dep_id`) silently `continue`s on `dict` too — no shared shape-validation helper exists; edge normalization is duplicated in `state._split_ids`, `cli/issues/show.py:_id_list`, `parse_file`, and `check_format_gaps`.
- **No raw capture today**: `SourceRecord` (`state.py:201`) has `*_raw` fields for scores/flags/dates/status but none for `blocked_by`/`blocks`/`depends_on`; the raw value survives only inside `SourceRecord.frontmatter` (a `MappingProxyType`). `SourceRecord.diagnostics` (`tuple[Diagnostic, ...]`) is the existing per-source evidence channel; `Diagnostic` (`next_arena/inputs.py`) carries only `code`, `message`, `paths`, `subject` — no structured payload, so any raw value must be rendered into `message`.
- **Graph consumption**: `build_issue_graph` (`next_arena/graph.py`) sees only the normalized tuples through the `GraphRecord` protocol and folds one-sided `blocks` into `hard[target][source]` only when the target is a known node. The graph therefore cannot know a source carried an unsupported shape; the target-side evidence for a one-sided `blocks` mapping on an outside source must come from captured `ProjectState.records`, indexed by named target.
- **Gate consumers**: `_prerequisites_gate` (`candidates.py:525`) has exactly two call sites — `_assess_one` (`candidates.py:696`, `implement-issue` only; refinement is deliberately not gated by prerequisites, pinned by `test_refinement_is_not_blocked_by_unmet_prerequisites`) and `_assess_root` (`blockers.py:274`, every record). `GateResult` statuses are `pass`/`fail`/`missing` only (no `unknown`); gate `.code` becomes an exclusion reason for any non-shared non-pass gate. `build_blocker_index`/`_independent_vetoes` in `blockers.py` read the graph and record fields directly and do **not** call `_prerequisites_gate`, so dependent-unlock/leverage counting is a separate path from the runnable gate.
- **Explain visibility**: `render_explain_text` shows gates as `name: status - reason` and does **not** render `evidence["dependencies"]` (JSON only). `collect_diagnostics(..., scope_to=...)` (`render.py:305`) keeps only diagnostics whose `subject` equals the explained target. Consequence: a diagnostic whose subject is the *source* of a one-sided `blocks` mapping will not appear under `--explain` for the *target*; the field/source/raw-value evidence for that case must be carried in the target's gate reason text (and/or a target-subject diagnostic).
- **Conventions in force**:
  - Source-level facts are captured once in `build_source_record` and stored as frozen `SourceRecord` fields; raw values judged later are kept verbatim beside the normalized value (`*_raw` fields; evidence: `confidence_score_raw`, `decision_needed_raw`, `status_raw`).
  - Present-but-unusable input is never coerced: it fails closed with a coded diagnostic and gate (evidence: `invalid_status` + `PROV_INVALID` lifecycle, `unreadable_source`, `<label>_score_invalid` gates). Diagnostics use `Diagnostic(code, f"{rel_path}: ...", (rel_path,), evidence_id)`.
  - Absent input maps to `MISSING`, present-but-invalid maps to `FAIL` (`_score_gate`). The two precedents disagree on whether invalid input also gets a diagnostic (lifecycle: yes; scores: gate only).
  - Aggregated diagnostics go through `sort_diagnostics`; state output must be independent of file enumeration order and each file is read/parsed exactly once (`test_enumeration_order_does_not_change_state`, `test_one_read_and_one_parse_per_file` monkeypatch `state_mod._read_text`/`_parse_frontmatter`).
- **Tests**: function-style module-level tests (no classes) in `scripts/tests/test_feat3561_phase_b_state.py` (capture; `test_frontmatter_edges_win_over_conflicting_body_like_parser` already pins parity with `IssueParser.parse_file` for list values), `test_feat3561_phase_d_assess.py` (prerequisites gate: `test_one_sided_blocks_declaration_blocks_the_named_target`, `test_dependency_cycle_fails_with_diagnostic_and_no_invented_root`, `test_unknown_and_external_dependency_ids_fail_closed`), `test_feat3769_blockers.py` (root-blocker path), `test_feat3561_phase_e_cli.py` (`--explain` exit-0/reason assertions). No existing test passes a mapping-valued relationship field. Fixture constraint: `next_arena_support.issue_text` serializes a `dict` as its Python repr, so mapping fixtures must use `write_issue(..., text=...)` with literal block YAML; `memory_state` builds state from raw text without disk.
- **Non-obvious adjacent shape**: a `list` whose items are mappings is stringified by `_split_ids` into a fake ID (`str(item)`), which already fails closed as an unknown prerequisite — a distinct case from the nonempty-mapping bug, left unchanged.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/next_arena/state.py` — the only `SourceRecord(` constructor is the `return SourceRecord(...)` in `build_source_record` (`:418`); `SourceRecord` is a frozen dataclass without defaults, so a new field is added there and in field order. `build_project_state` (`:643`) merges every `rec.diagnostics` into `ProjectState.diagnostics` and calls `build_issue_graph` (`:662`), so a per-source diagnostic also reaches `--json` for every run, not just `--explain`. [Agent 1/2 finding]
- `scripts/little_loops/next_arena/blockers.py` — beyond `_assess_root` (`:246`), `build_blocker_index` (`:121`) and `_independent_vetoes` (`:95`) never call `_prerequisites_gate` or read unsupported-shape evidence; a dependent that has a body-fallback edge (`blocked_by`/`blocks` mapping with a `## Blocked By`/`## Blocks` section) can still count as an `immediate` unlock/`implementable_count` for its prerequisite. Decide whether the unsupported-shape exclusion surfaces as an `_independent_vetoes` veto. Mapping-only edges produce no graph edge, so they never inflate leverage. [Agent 2 finding]
- `scripts/little_loops/next_arena/candidates.py` — `_assess_one` (`:672`) copies `record.diagnostics` into the assessment and appends each non-shared, non-pass gate's `.code` to `exclusion_reasons`; `_gates_dict` (`:195`) serializes `GateResult` into explain/JSON. No change needed if the new failure keeps the `prerequisites` gate name. [Agent 1/2 finding]
- `scripts/little_loops/next_arena/render.py` — `collect_diagnostics` (`:305`, `scope_to` subject filter) and `render_explain_text` (`:535`) are the explain surface; the target-side evidence for a one-sided `blocks` mapping must be a gate reason or a target-subject diagnostic since the source-subject diagnostic is filtered out. [Agent 1/2 finding]
- `scripts/little_loops/cli/next.py` — drives `collect_project_state` → `collect_diagnostics`/`render_explain_text` (`:430-482`); consumer only. [Agent 1 finding]
- `scripts/little_loops/next_arena/graph.py` — `GraphRecord` protocol (`:59`) lists only `rel_path`, `lifecycle_status`, `blocked_by`, `blocks`, `depends_on`, `issue_type`; extra `SourceRecord` fields are invisible to it and no test implements the protocol. Confirms the target-side lookup must be built from `ProjectState.records`. [Agent 1 finding]
- `scripts/little_loops/next_arena/output-schema.json` — `diagnostic` `$defs` requires only `code` (string, `minLength` 1); `exclusion_reasons`/`gates` are free-form. A new diagnostic or gate code needs no schema change, and `SCHEMA_VERSION` is unaffected. It is generated from `render.build_output_schema()` and pinned by `test_feat3561_phase_e_render.py`; do not regenerate unless that builder changes. [Agent 1/2 finding]
- No consumers outside `scripts/little_loops/next_arena/` and `cli/next.py` parse `ll-next` gates, reasons or diagnostics: `recording.py` (commit 45825d8f8) never reads `exclusion_reasons`/`gates`/`evidence`, and `.loops/`, `loops/`, `hooks/`, `commands/`, `agents/` and `skills/` (apart from `skills/configure/areas.md`, config-only) have none. `_split_ids`/`_merge_edge_ids` have no callers outside `state.py`, and `executor_dependency_mismatch` (FEAT-3713) shares no code. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md` — the `### ll-next` **Diagnostics** paragraph (`:3796`) lists diagnostic codes in prose and is already non-exhaustive (omits `dependency_cycle`, `invalid_status`, `unreadable_source`); add the new unsupported-dependency code. The "What gets recommended" bullets say `implement-issue`/`resolve-blocker` need "prerequisites are done" — note that unsupported relationship shapes also exclude. [Agent 2 finding]
- `docs/reference/API.md` — `little_loops.next_arena` section (`:745`): `state` row describes capture of the "dependency graph", `candidates` row mentions "gates and exclusion reasons"; extend if the new evidence/diagnostic is user-visible. [Agent 2 finding]
- `docs/ARCHITECTURE.md` — has zero `ll-next`/`next_arena` text, so the "Related Key Documentation" row naming it for "Snapshot-based recommendation architecture" is currently unbacked; no edit required unless an architecture paragraph is added. [Agent 2 finding]
- `CHANGELOG.md` — add a bug-fix entry in a concrete `## [X.Y.Z] - DATE` section during release prep, not under `[Unreleased]`. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_feat3561_phase_b_state.py` — add capture cases modeled on `test_lifecycle_matrix_on_disk` (codes via `{d.code for d in rec.diagnostics}`), `test_unreadable_source_is_invalid_and_diagnosed` and `test_raw_score_and_flag_fields_are_kept_raw` (`*_raw` pairing); parity pin alongside `test_frontmatter_edges_win_over_conflicting_body_like_parser`; empty-mapping body fallback. [Agent 3 finding]
- `scripts/tests/test_feat3561_phase_d_assess.py` — prerequisites section: mutual mapping-key cycle, mapping naming an outside unresolved prerequisite, outside one-sided `blocks` mapping in both write orders (`project(..., order=[...])`); keep `"unknown_issue" in reason` and `evidence["dependencies"]["unresolved"][0]["prerequisite_id"|"kind"]` / `["in_cycle"]` assertions valid (additive keys only); `test_refinement_is_not_blocked_by_unmet_prerequisites` (`"prerequisites" not in item.gates`) must still pass. [Agent 3 finding]
- `scripts/tests/test_feat3769_blockers.py` — model for the root-blocker path (`assess_candidates(project(...))` → `blocker(items, id)`); closest tests `test_dependency_cycle_yields_diagnostics_not_a_root`, `test_ambiguous_prerequisite_cannot_make_a_blocker_look_root`, `test_chain_only_the_root_qualifies_and_reachability_is_not_immediate_unlock`. Add a mapping-affected root and a root named by an outside `blocks` mapping. [Agent 3 finding]
- `scripts/tests/test_feat3561_phase_e_cli.py` — add a `--explain implement-issue <target>` case (new parametrize row of `test_explain_excluded_targets_exit_zero_with_reasons`, or its own `make_project` + `write_issue(..., text=...)` fixture as in `test_gate_failures_report_gate_diagnostics_and_exit_one`); assert exit 0, `eligible is False`, and gate-reason text carrying field/source/raw value; `_json` also validates the envelope against `render.load_output_schema()`. [Agent 3 finding]
- `scripts/tests/test_feat3561_phase_b_state.py::test_enumeration_order_does_not_change_state` — asserts dataclass equality of `records`, `identity`, `graph` and `diagnostics` across reversed enumeration; any new `SourceRecord` field or state-level target index must be order-independent and `==`-comparable (tuples/frozensets, not raw dicts). Same for `test_feat3561_phase_d_determinism.py::test_shuffled_source_order_with_fixed_clock_is_identical` (`_dump` JSON-serializes assessments). [Agent 3 finding]
- `scripts/tests/test_feat3561_phase_f_perf.py` — `test_exactly_one_read_and_parse_per_issue_file` and `test_no_reads_or_parses_at_assessment_selection_or_render_time` forbid extra I/O; `test_operation_count_grows_linearly_500_to_5000` and `test_ten_thousand_issue_assess_and_select_within_budget` fail if the one-sided `blocks` lookup is done per target by scanning all records (O(N²)) — build the target index once at state-build time. [Agent 3 finding]
- `scripts/tests/test_feat3561_phase_b_identity.py` — `test_one_sided_blocks_from_every_conflicting_source_are_retained` / `test_one_sided_blocks_resolves_with_the_declaring_source` are the graph-side precedents for the outside-`blocks` case; `rebuilt.diagnostics == state.diagnostics` must keep holding. [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` (~`:5062`) — regex allowlist keyed on `("next_arena/state.py", "_PRIORITY_PREFIX_DIGITS_RE")` and `("next_arena/state.py", "infer_parser_id")`; avoid adding a new priority-shaped regex or filename pattern to `state.py` or this gate trips. [Agent 3 finding]
- `scripts/tests/next_arena_candidates_support.py` — `project(tmp_path, {rel: text}, order=[...])` and `body()` supply raw-text fixtures with an Impact/Effort section; `next_arena_support.py::memory_state` is the disk-free variant. Mapping fixtures use literal block YAML (`issue_text` renders a dict as its Python repr). [Agent 3 finding]

## Program Design

### Types

Reuse the immutable `SourceRecord.frontmatter` and captured diagnostics to retain the offending relationship/raw mapping. Represent unsupported dependency evidence explicitly instead of turning it into an empty ID tuple. Reuse `GateResult` and the shared assessment/explain output; no persistence format or live parser instance is needed.

### Signatures

- `_prerequisites_gate(state: ProjectState, issue_id: str) -> tuple[GateResult, dict[str, Any]]` — extend the existing pure gate to consume captured unsupported-dependency evidence for the affected source/one-sided target, retaining its tri-state result and explain evidence shape.

### Call Path

`build_source_record` in `scripts/little_loops/next_arena/state.py` captures relationship-shape evidence → the captured dependency/eligibility index → `_prerequisites_gate` in `scripts/little_loops/next_arena/candidates.py`, reused by `_assess_root` in `scripts/little_loops/next_arena/blockers.py` → existing assessment/explain rendering exposes source/raw field. Preserve valid graph-building and refinement policy; do not infer executable readiness from an unsupported relationship shape.

## Implementation Steps

1. Reproduce the mapping-key cycle and a mapping naming an unresolved outside prerequisite with otherwise eligible source fixtures.
2. Capture the unsupported relationship evidence and reject affected runnable assessments without live I/O or parser/executor changes.
3. Verify explain retains the raw relationship and valid unrelated offers remain eligible; pin string/list and empty-mapping body fallback regressions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-08 — based on codebase analysis:_

- Constraint on gate placement: the exclusion must hold on both consumers of `_prerequisites_gate` (`implement-issue` in `_assess_one`, all root candidates in `_assess_root`) and must not apply to refinement offers, which are intentionally independent of prerequisites.
- Constraint on result independence: output must not depend on source enumeration order or on which of a mapping's source/target is read first; state remains deterministic and single-read per file (existing order/one-read tests must keep passing).
- Constraint on explain: because explain text renders gate reasons and subject-scoped diagnostics but not `evidence["dependencies"]`, the field name, offending source path, and raw mapping value must be reachable from the affected target's gate reason or a diagnostic scoped to that target.
- Verification: new regression cases cover mutual mapping-key cycle, mapping naming an outside unresolved prerequisite, outside one-sided `blocks` mapping (both orderings), empty-mapping body fallback, and string/list parity; run `python -m pytest scripts/tests/test_feat3561_phase_b_state.py scripts/tests/test_feat3561_phase_d_assess.py scripts/tests/test_feat3769_blockers.py scripts/tests/test_feat3561_phase_e_cli.py`.

## Impact

- **Priority:** P2 — persuasive runnable recommendations can omit actual prerequisites or cycles.
- **Effort:** Small — captured shape validation and an existing eligibility gate.
- **Risk:** Low — malformed dependency metadata receives an explicit exclusion; valid input semantics remain unchanged.
- **Breaking Change:** No.

## Root Cause

- `scripts/little_loops/next_arena/state.py:278` — `_split_ids` discards mappings; `_merge_edge_ids` treats the resulting empty IDs as body-fallback input.
- `scripts/little_loops/issue_parser.py:4372` — the shared parser converts truthy non-string relationship values to a list, retaining mapping keys.
- These differing captured/runtime shape policies let an invalid relationship establish apparently valid runnable metadata.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-08 — based on codebase analysis:_

- Verified: the arena's `_split_ids` (`next_arena/state.py:278`) and the parser's `list(fm_val)` (`issue_parser.py:4378`) disagree only for truthy non-str/non-list values; with `yaml.BaseLoader` the only such shape a file can produce is a nonempty `dict`. No arena code path validates relationship value shape or records a diagnostic for it, so the lost information cannot be recovered downstream (`graph.py` only receives normalized tuples).
- Cycle blind spot is a consequence, not a separate defect: mapping keys never reach `build_issue_graph`, so `dependency_cycle` diagnostics and `cyclic_ids` cannot fire, and `_prerequisites_gate` has nothing unresolved to report.

## Acceptance Criteria

- [ ] Nonempty mapping-valued `blocked_by`, `depends_on` and `blocks` cannot silently produce implementation/root-blocker readiness; affected explain output retains field/source/raw-value diagnostics.
- [ ] The reproduced mutual mapping-key cycle, a mapping naming an unresolved outside prerequisite, and an outside source’s one-sided `blocks` mapping yield no affected runnable offer, regardless of source ordering.
- [ ] Empty mappings preserve body fallback; supported string/list relationships and unrelated valid issues retain their current behavior.
- [ ] Validation and assessment use captured state only, without new per-candidate I/O or changed shared parser/executor semantics; relevant tests pass.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/API.md` | Captured arena state/assessment and shared issue relationship semantics. |
| `docs/ARCHITECTURE.md` | Snapshot-based recommendation architecture. |

## Status

**Open** | Created: 2026-10-08 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-10-08T15:29:03 - `391386d4-3db8-4f5a-9e12-97e5935d2d4b.jsonl`
- `/ll:capture-issue` - 2026-10-08T15:15:05 - `c063533a-bfa9-410e-8a16-0fe48d320a3b.jsonl`
