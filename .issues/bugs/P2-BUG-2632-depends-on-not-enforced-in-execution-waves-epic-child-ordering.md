---
id: BUG-2632
title: depends_on not enforced in execution waves — EPIC children run before prerequisites
type: bug
status: open
priority: P2
captured_at: "2026-07-13T18:40:43Z"
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to: [BUG-2629]
decision_needed: false
---

# BUG-2632: depends_on not enforced in execution waves — EPIC children run before prerequisites

## Summary

`DependencyGraph.get_execution_waves()` orders issues **only** by hard
`blocked_by:` edges. `depends_on:` edges are treated as *soft* — they can pull a
prerequisite **forward** into the current wave, but they never push a dependent
into a **later** wave. So when an EPIC's children express their prerequisites via
`depends_on:` (the common case), the graph collapses them into a single wave in
lexical order, and a dependent issue can be scheduled — and refined — **before**
its prerequisites exist. This produces false `low_readiness` skips and wasted
refinement cycles in the `auto-refine-and-implement` / `autodev` loops.

## Steps to Reproduce

Observed in run `auto-refine-and-implement-20260713T123044` (scope `EPIC-2616`).
Children and their declared deps:

```
ENH-2617 (helper)      depends_on: []
FEAT-2618 (list)       depends_on: [ENH-2617]
FEAT-2619 (remove)     depends_on: [ENH-2617]
ENH-2620 (docs)        depends_on: [FEAT-2618, FEAT-2619]
```

Live reproduction:

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.sprint import SprintManager
sprint = SprintManager(config=BRConfig(Path.cwd())).load_or_resolve("EPIC-2616")
print(sprint.issues)
# Actual:  ['ENH-2617', 'ENH-2620', 'FEAT-2618', 'FEAT-2619']   ← lexical, one wave
# Correct: ['ENH-2617', 'FEAT-2618', 'FEAT-2619', 'ENH-2620']   ← 2620 last
```

`get_execution_waves()` returns a **single wave** containing all four children —
i.e. it detected no ordering constraints at all, despite the `depends_on:` edges
being present on the issue objects.

## Current Behavior

ENH-2620 (docs, `depends_on: [FEAT-2618, FEAT-2619]`) was dispatched **2nd**,
before either dependency existed. It documents `ll-loop queue list`/`queue
remove` — neither of which was implemented yet — so its outcome_confidence was
correctly low → skipped `low_readiness`. The refinement effort spent on it was
wasted, and the skip reason misattributes a scheduling defect to issue
readiness.

## Root Cause

`scripts/little_loops/dependency_graph.py`:
- `get_ready_issues()` / `get_execution_waves()` (~line 205) gate wave
  membership **only** on `blocked_by:` (hard) edges.
- The soft `depends_on` handling (~lines 209-220) only *pulls prerequisites
  forward* into the current wave; there is no path that defers a dependent to a
  later wave. Comment at ~line 209 confirms: "Soft ordering: nudge depends_on
  targets into this wave…".

`scripts/little_loops/sprint.py:362-372` — `load_or_resolve()` for an EPIC calls
`get_execution_waves()`; because that returns one flat wave, `ordered_ids`
degrades to lexical `(priority, issue_id)` order. (The docstring at
`sprint.py:291` claims the result is "ordered by dependency graph" — currently
false for `depends_on`-only children.)

## Expected Behavior

Declared `depends_on:` prerequisites must enforce ordering: a dependent issue is
scheduled in a **strictly later** wave than all of its `depends_on` targets. For
EPIC-2616 the resolver should return `[ENH-2617, FEAT-2618, FEAT-2619,
ENH-2620]` (or waves `[[2617], [2618, 2619], [2620]]`).

## Implementation Steps

Pick one:

> **Selected:** Option 1 (global `get_execution_waves` fix) — only option that fixes the `ll-auto`/autodev `get_ready_issues()` path required by AC #2.

1. **In `get_execution_waves`**: treat `depends_on` as wave-ordering (a dependent
   is not "ready" until its `depends_on` targets are in `processed`), while
   keeping `blocked_by` as the hard/cycle-raising edge. Preserve today's
   cycle-detection semantics and the "pull-forward" behavior where it doesn't
   conflict. Care: `depends_on` is documented as *soft* elsewhere — decide
   whether soft means "ordering-only, never fails the build" vs. "ignored for
   ordering". This bug argues for ordering-enforcing-but-non-fatal.
2. **Or in the EPIC resolver** (`sprint.py:load_or_resolve`): map children's
   `depends_on` → scheduling constraints before building the graph, so ordering
   is enforced without changing `depends_on`'s hard/soft meaning globally.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-13.

**Selected**: Option 1 — enforce `depends_on` ordering in `get_execution_waves()`.

**Reasoning**: AC #2 requires that a dependent is never dispatched/refined before its
`depends_on` targets in `auto-refine-and-implement`/`autodev`. That path runs through
`IssueManager._get_next_issue()` → `get_ready_issues()` (`issue_manager.py:1215`), not
`load_or_resolve()` — so Option 2 (EPIC-resolver-local) would leave the exact path in the
bug's repro run unfixed and would create divergent `depends_on` semantics between
EPIC-resolved and manually-created sprints. Option 1 reuses the existing `depends_on_edges`
map and the demarcated soft-ordering block in `get_execution_waves()` (lines 209-220) plus
the `make_issue()`/wave-assertion test idioms; its known extra cost (extend `detect_cycles()`
to traverse `depends_on`, rewrite `test_depends_on_soft_ordering` /
`test_depends_on_does_not_hard_block`) is already anticipated in the Integration Map.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (global `get_execution_waves`) | 2/3 | 2/3 | 3/3 | 1/3 | 8/12 |
| Option 2 (EPIC-resolver-local) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option 1: dual-map `depends_on_edges` model + soft-ordering nudge site already exist (reuse 2); requires extending `detect_cycles()` (only traverses `blocked_by`) and rewriting two committed soft-semantics tests; touches graph-wide callers including `ll-auto`.
- Option 2: reuses the local `except ValueError` sort precedent (`sprint.py:369-372`) but has no reusable "map depends_on → strict wave" utility (reuse 1), duplicates the graph BFS, and leaves `get_ready_issues()` consumers (`ll-auto`, `orchestrator`) unfixed.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — Option 1 fix site. `get_ready_issues()`
  (lines 147-171, hard-gate at line 166 reads only `self.blocked_by`);
  `get_execution_waves()` (lines 173-234) — hard wave selection at line 205, soft
  pull-forward nudge at lines 209-220 (`wave.extend(nudged)`, line 220). To enforce
  ordering, a dependent must not be "ready" until its `depends_on` targets are in
  `processed`. Note `detect_cycles()` (lines 327-370) traverses **only** `blocked_by`
  (line 352) — if `depends_on` becomes ordering-enforcing, a `depends_on`-only cycle
  would currently leave issues unprocessed and raise a misleading `blocked_by` cycle
  error (lines 227-232); cycle detection must be extended to cover `depends_on`.
- `scripts/little_loops/sprint.py` — Option 2 fix site + docstring fix. `load_or_resolve()`
  wave flatten at lines 362-372 (`ordered_ids = [issue.issue_id for wave in waves for
  issue in wave]`, line 367; lexical `(priority or "P5", issue_id)` fallback only on
  `except ValueError`, lines 369-372). Docstring claim "ordered by dependency graph" at
  line 291 (AC #4).

### Dependent Files (Callers / Consumers of waves)
- `scripts/little_loops/parallel/orchestrator.py` — `ll-parallel`/`ll-sprint` dependency-aware
  scheduler; consumes execution waves. **Regression-sensitive**: an Option 1 change to
  `get_execution_waves()` affects parallel scheduling, not just EPIC resolution.
- `scripts/little_loops/cli/sprint/run.py` — sprint runner, executes in wave order.
- `scripts/little_loops/cli/auto.py` — `ll-auto`, drives autodev/auto-refine loops.
- `scripts/little_loops/cli/issues/sequence.py`, `cli/issues/next_issue.py` — use
  `get_ready_issues()` / sequencing.
- `scripts/little_loops/cli/deps.py`, `issue_manager.py:1003` — call `DependencyGraph.from_issues()`.

### Tests
- `scripts/tests/test_dependency_graph.py` — `TestGetExecutionWaves` (class at line 589).
  Helper `make_issue()` (lines 18-39) builds `IssueInfo` fixtures with `blocked_by`/
  `depends_on`. **Existing tests that encode the current soft semantics and must be
  updated (not left to silently regress):** `test_depends_on_soft_ordering` (lines
  707-735) and `test_depends_on_does_not_hard_block` — both assert pull-forward-only /
  never-defer behavior that this bug intends to change. Wave-assertion idioms to model:
  `test_linear_chain_three_waves` (608-621), `test_diamond_three_waves` (623-640).
- `scripts/tests/test_sprint.py` — `TestSprintManagerLoadOrResolve` (class at line 2384),
  `epic_project` fixture (2384-2411), template test `test_load_or_resolve_epic_id_backward_lookup`
  (2450-2467). New 4-child EPIC-2616 regression fixture (`parent: EPIC-2616` +
  `depends_on:` frontmatter) should follow this shape and assert via index comparison
  (`ids.index("ENH-2617") < ids.index("FEAT-2618")`, etc.).
- `scripts/tests/test_sprint_integration.py` — integration coverage for `load_or_resolve()`.

### Documentation
- `docs/guides/SPRINT_GUIDE.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — document
  `depends_on:` vs `blocked_by:` semantics for users; update if soft→ordering meaning changes.
- `docs/reference/API.md` — `DependencyGraph.get_execution_waves()` / `SprintManager` signatures.

### Design History (prior-art — the semantics this bug proposes to change)
- **The soft/pull-forward-only behavior is a deliberately-shipped design, not an oversight.**
  Completed `ENH-1439` (added `depends_on_edges` field), `ENH-1436` + `ENH-1440`
  (implemented soft-ordering "nudge" in `get_execution_waves()`) under parent `ENH-1432`
  (standardized `depends_on` vs `blocked_by`). This bug argues that soft-ordering should
  become **ordering-enforcing-but-non-fatal** — i.e. it revises the ENH-1440 contract.
  Option 2 (EPIC-resolver-local constraint mapping) confines the change to EPIC resolution
  and leaves the global `depends_on` semantics from ENH-1440 intact — **lower blast radius
  on `ll-parallel`/`ll-sprint`** and the recommended path unless the enforcing semantics
  are wanted graph-wide.

## Acceptance Criteria

- `SprintManager.load_or_resolve("EPIC-2616")` returns an order where every issue
  precedes all issues that `depends_on` it (regression test with the 4-child
  fixture above).
- A dependent issue is never dispatched/refined before its `depends_on` targets
  in `auto-refine-and-implement` / `autodev`.
- Existing `blocked_by`-based wave behavior and cycle detection are unchanged
  (existing dependency_graph tests still pass).
- `sprint.py:291` docstring matches actual behavior.

## Notes

- FEAT-2619's skip in the same run was **not** caused by this bug — its only dep
  (ENH-2617) had passed, and it was refined to only 73 confidence on its own
  merits (below the 85/90 readiness and 75 outcome thresholds). This bug covers
  only the ordering defect that skipped ENH-2620.
- Relates to BUG-2629 (same run's post-mortem).

## Session Log
- `/ll:decide-issue` - 2026-07-13T18:54:44 - `e555b243-e23c-429d-9cab-61c70b69018b.jsonl`
- `/ll:refine-issue` - 2026-07-13T18:46:15 - `7b1b09e0-77ab-4197-917e-348281ecdd0c.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:40:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
