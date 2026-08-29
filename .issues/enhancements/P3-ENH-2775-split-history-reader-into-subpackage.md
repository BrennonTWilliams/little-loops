---
id: ENH-2775
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
relates_to:
- ENH-3359
---

# ENH-2775: Split history_reader.py into a subpackage along concern boundaries

## Summary

Architectural issue found by `/ll:audit-architecture`. `history_reader.py` is
a top-tier large file accreting unrelated concerns.

> **Rescoped 2026-08-29**: this issue originally also covered splitting
> `fsm/executor.py`. That half carried nearly all the outcome risk (33/100
> outcome confidence was dominated by it) and its research showed the
> originally-proposed extractions (retry, handoff, continuity) already exist
> as collaborator modules. The remaining executor work was narrowed and moved
> to ENH-3359 (deferred). This issue is now the `history_reader` split only —
> a mechanical mirror of the completed ENH-2772/ENH-2774 sibling splits.
> Prior confidence/verify scores were removed as they measured the bundled
> scope.

## Location

- **File**: `scripts/little_loops/history_reader.py` — 3,585 lines (was 3,099
  at capture, still growing)
- **Module**: `little_loops.history_reader`

## Finding

### Current State

- `history_reader.py`: 88 top-level defs mixing JSONL parsing, session
  discovery, querying, and formatting in one flat module.

### Impact

- **Development velocity**: recurring merge-conflict hotspot.
- **Maintainability**: concern boundaries exist informally (region comments,
  naming prefixes) but not structurally.

## Proposed Solution

Convert `history_reader.py` into a subpackage along its existing seams,
preserving public import paths via re-exports — the exact shape of the
completed EPIC-2789 siblings.

### Suggested Approach

1. `history_reader` → package: `history_reader/__init__.py` (re-exports full
   public surface) plus concern submodules, e.g. `parsing.py` (JSONL/event
   decoding), `discovery.py` (session file location), query modules,
   `formatting.py`.
2. `__init__.py` docstring documents "Package layout" and "Public API"
   sections, matching `session_store/__init__.py` and
   `fsm/validation/__init__.py`.
3. Split `scripts/tests/test_history_reader.py` one-for-one into per-submodule
   test files (`test_history_reader_<submodule>.py`), following commit
   `9a4977a14`'s precedent.
4. Full test suite green with no importer changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- The two completed EPIC-2789 siblings (ENH-2772 session_store split, ENH-2774
  fsm/validation split) both landed as a **subpackage** — `name/__init__.py`
  plus concern submodules, with matching per-submodule test files — rather
  than sibling flat files kept alongside an unrenamed original (see
  Integration Map -> Conventions in Force for both `__init__.py` examples).
  This issue mirrors that shape directly.
- The single flat "Query API" region (L456-2386, ~1,930 lines, ~35 functions)
  covers at least 9 distinguishable query domains — finer-grained than a
  single `queries.py` would comfortably hold; expect several query submodules
  (see Program Design -> Signatures).

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/history_reader.py` (3,585 lines currently — grown
  further since capture, was 3,351) — flat module; existing region comments
  already mark `Dataclasses` (L104), `Helpers` (L412), `Query API` (L456,
  spans ~1,930 lines through L2386 and covers at least 9 distinguishable query
  domains — not one homogeneous group), `Summary DAG retrieval` (L2389,
  FEAT-1712), `Project digest — section providers` (L2624, ENH-1907), `Hook
  execution telemetry` (L2833, ENH-2506), `ll-harness / eval outcome
  telemetry` (L2966).

### Dependent Files (Callers/Importers)
- `history_reader` direct importers (8, via `ll-code importers-of`):
  `cli/history_context.py`, `cli/session.py`, `issue_history/collisions.py`,
  `issue_history/evolution.py`, `issue_history/rework.py`,
  `tests/test_assistant_messages.py`, `tests/test_enh_2505_subagent_runs.py`,
  `tests/test_history_reader.py`.
- Transitive impact set (`ll-code impact-of`) is 16 files (reaches
  `cli/__init__.py`, `issue_history/analysis.py`). The split must keep
  `from little_loops.history_reader import ...` importable unchanged across
  all of these — the re-export requirement the Proposed Solution already
  states.

### Conventions in Force
- This codebase's established convention for splitting a god-module is a
  **subpackage**, not sibling flat files left alongside an unrenamed original:
  convert `name.py` -> `name/__init__.py` + concern submodules, with the
  `__init__.py` docstring documenting a "Package layout" (submodule ->
  concerns) section and a "Public API" (re-exported names) section — evidence:
  `scripts/little_loops/session_store/__init__.py:1-40` (ENH-2772, split into
  `db.py`/`lifecycle.py`/`queries.py`/`schema.py`/`writers.py`) and
  `scripts/little_loops/fsm/validation/__init__.py:1-30` (ENH-2774, split into
  `_base.py`/`structural_rules.py`/`evaluator_rules.py`/`meta_rules.py`/
  `reachability.py`/`shell_safety.py`) — both are completed sibling issues of
  this one under the same parent EPIC-2789.
- The same convention extends to tests: the flat test file is split one-for-one
  into per-submodule test files (`test_<pkg>_<submodule>.py`), not kept as one
  shared file — evidence: commit `9a4977a14` split `test_fsm_validation.py`
  (5,358 lines) into
  `test_fsm_validation_{evaluator_rules,meta_rules,reachability,shell_safety,structural}.py`.

### Tests
- `scripts/tests/test_history_reader.py` — 3,221 lines, already organized into
  25 domain-scoped `Test*` classes (e.g. `TestCostAttribution`,
  `TestWasteAttribution`, `TestHandoffFrequency`, `TestWorktreeSummary`,
  `TestSummaryDagRetrieval`) that map directly onto candidate submodule
  boundaries — the test-file split is a mechanical class-per-domain move.

### Documentation
- `docs/reference/API.md` — the `little_loops.history_reader` entry (line 54)
  cites the current flat-module layout and needs updating to the new package
  structure.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — carries structural, not just conceptual, file-path
  references that go stale on a split. Specific spots: the Read Path mermaid
  diagram's `HR[history_reader.py]` node (L723); the Components table row
  `history_reader.py | history_reader.py | Public read API: 10 query
  functions, 7 dataclasses, ...` (L751), which states counts that presuppose a
  single flat file.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `history_reader.py` | Public functions/dataclasses (`find_user_corrections`, `search`, `cost_attribution`, `UserCorrection`, etc.) | PRESERVED | Split is purely structural; `history_reader/__init__.py` re-exports the full existing public surface per the Proposed Solution's own stated goal ("preserving public import paths via re-exports") |

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- `search(query: str) -> list[SearchResult]` (`scripts/little_loops/history_reader.py:529`) — FTS5 full-text query entry point, representative of the Query API surface the split relocates unchanged.
- `find_user_corrections(topic: str) -> list[UserCorrection]` (`scripts/little_loops/history_reader.py:461`) — corrections query, same relocation-only disposition.
- `cost_attribution(group_by: str) -> list[dict]` (`scripts/little_loops/history_reader.py:924`) — cost/waste-attribution domain exemplar.

### Types
- No new data shape is introduced. The 27 dataclasses in `history_reader.py`
  (`UserCorrection`, `FileEvent`, `SearchResult`, ... `ReviewEvent`) are
  relocated by the split, not changed.

### Signatures
- `history_reader.py` has no classes besides its dataclasses; its 75
  module-level functions are grouped by naming/region rather than by class.
  The "Query API" region alone (L456-2386) spans roughly 35 of those 75
  functions across at least 9 distinguishable domains — cost/waste
  attribution, usage aggregation, context-pressure curves, commit events,
  prompt-opt events, learning tests, lifecycle/handoff, worktree summaries,
  subagent tree/retries/budget, orchestration/loop-run aggregation, issue
  effort/velocity, session metadata, and grep/search formatting
  (`ll_grep`/`ll_expand`/`ll_describe`) — finer-grained than a single
  `queries.py` module would comfortably hold.
- `search(query: str) -> list[SearchResult]` (`scripts/little_loops/history_reader.py:529`) — FTS5 full-text query entry point, representative of the Query API surface the split relocates unchanged.
- `find_user_corrections(topic: str) -> list[UserCorrection]` (`scripts/little_loops/history_reader.py:461`) — corrections query, same relocation-only disposition.
- `cost_attribution(group_by: str) -> list[dict]` (`scripts/little_loops/history_reader.py:924`) — cost/waste-attribution domain exemplar.

### Call Path
- `cli/session.py:44` -> `history_reader.search()` (`scripts/little_loops/history_reader.py:529`) — representative importer path; after the split this resolves through `history_reader/__init__.py` re-exports with the import line unchanged.
- `cli/history_context.py:31` -> `history_reader.condensed_nodes_for_issue()` and other query functions — same re-export-preserved path; all 8 direct importers follow this shape.

### Decision Rules
N/A — no new decision logic; this issue is a structural module split
introducing no new gate, threshold, or classification rule.

## Related Key Documentation

- `docs/reference/API.md` — documents `history_reader` module-by-module;
  splitting it requires updating those entries to match the new package
  layout.
- `docs/ARCHITECTURE.md` — describes the internals `history_reader.py`
  implements; a structural split is exactly the kind of architecture change
  this doc covers.

## Verification Notes

- 2026-08-16: Core issue still real; file has grown further since capture
  rather than shrunk — `history_reader.py` is now 3,351 lines (was 3,099).
  Verdict: OUTDATED (line counts updated above).
- 2026-08-29: Rescoped to `history_reader` only; `fsm/executor.py` half moved
  to ENH-3359 (deferred). Prior verify verdict and confidence scores removed —
  they measured the bundled two-file scope.

## Session Log
- `/ll:confidence-check` - 2026-08-29T23:32:17 - `8d7bb2d0-d27b-4d28-89fe-e2d8b28cb272.jsonl`
- `/ll:verify-issues` - 2026-08-29T23:27:10 - `8d7bb2d0-d27b-4d28-89fe-e2d8b28cb272.jsonl`
- `/ll:wire-issue` - 2026-08-29T23:19:32 - `3877ebdc-d9d3-4449-9bcf-1a7f4ef3ce26.jsonl`
- `/ll:refine-issue` - 2026-08-29T23:06:34 - `ed9b2f61-6325-4a0c-aa2f-badcd208e1b6.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:49 - `6160b806-1147-4cb9-be05-f6b3edf1653b.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
