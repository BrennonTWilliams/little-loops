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

## Impact

- **Priority:** P2 — persuasive runnable recommendations can omit actual prerequisites or cycles.
- **Effort:** Small — captured shape validation and an existing eligibility gate.
- **Risk:** Low — malformed dependency metadata receives an explicit exclusion; valid input semantics remain unchanged.
- **Breaking Change:** No.

## Root Cause

- `scripts/little_loops/next_arena/state.py:278` — `_split_ids` discards mappings; `_merge_edge_ids` treats the resulting empty IDs as body-fallback input.
- `scripts/little_loops/issue_parser.py:4372` — the shared parser converts truthy non-string relationship values to a list, retaining mapping keys.
- These differing captured/runtime shape policies let an invalid relationship establish apparently valid runnable metadata.

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
- `/ll:capture-issue` - 2026-10-08T15:15:05 - `c063533a-bfa9-410e-8a16-0fe48d320a3b.jsonl`
