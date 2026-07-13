---
id: BUG-2632
title: "depends_on not enforced in execution waves \u2014 EPIC children run before\
  \ prerequisites"
type: bug
status: done
priority: P2
captured_at: '2026-07-13T18:40:43Z'
completed_at: '2026-07-13T21:07:02Z'
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to:
- BUG-2629
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
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

## Impact

- **Priority**: P2 — silently mis-orders EPIC child scheduling in `ll-auto`/autodev,
  producing false `low_readiness` skips and wasted refinement cycles; degraded
  automation quality rather than data loss or a crash.
- **Effort**: Medium — the core fix reuses the existing `depends_on_edges` map and the
  demarcated soft-ordering block in `get_execution_waves()`, but the change is
  ordering-enforcing graph-wide, requires extending `detect_cycles()` to traverse
  `depends_on`, rewriting two committed soft-semantics tests, and re-verifying ~6-10
  wave-consuming callers.
- **Risk**: Medium — touches the graph-wide scheduling path shared by `ll-sprint`/
  `ll-parallel`; new `depends_on` cycle-detection logic could introduce a new failure
  mode if not carefully bounded (see Confidence Check risk factors).
- **Breaking Change**: No (behavioral: `depends_on` becomes ordering-enforcing-but-non-fatal;
  reconcile "not wave-gated" docs/skills per Integration Map).

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/manage.py:109` — calls `get_execution_waves()`, feeds
  `refine_waves_for_contention()` and conflict-pair reporting. **Regression-sensitive** under
  the Option 1 change. [Agent 2 finding]
- `scripts/little_loops/cli/sprint/show.py:194` — calls `get_execution_waves()` for human/JSON
  (`_show_json`) sprint preview; wave-count/membership changes surface in preview output. [Agent 2 finding]
- `scripts/little_loops/issue_manager.py:1215` — `IssueManager._get_next_issue()` →
  `get_ready_issues(completed)`. **This is the exact AC #2 path** (referenced in the Decision
  Rationale but not previously listed as a dependent file). `get_ready_issues()` (lines 145-171)
  currently reads only `blocked_by` and never consults `depends_on_edges`, so `depends_on` has
  zero effect on `ll-auto` single-issue dispatch today — the surface AC #2 must fix. [Agent 3 finding]
- `scripts/little_loops/dependency_mapper/formatting.py:174-180,243-247` — builds its **own**
  `depends_on_edges` adjacency from `issue.depends_on` for ASCII chain rendering (`--> depends on`
  legend); does NOT call `get_execution_waves()`. Won't break, but its "soft" chain arrows will
  visually contradict the new enforced ordering — reconcile the legend wording if graph-wide
  semantics change (Option 1). [Agent 2 finding]

_Wiring pass 3 added by `/ll:wire-issue` (2026-07-13):_
- `scripts/little_loops/issue_parser.py:1264` — **new caller not previously listed.** `find_issues()`
  builds `DependencyGraph.from_issues(all_active)` and filters to `graph.get_ready_issues()` (the
  `skip_blocked`/ready-set path). Currently `get_ready_issues()` reads only `blocked_by`, so under the
  Option 1 change this filter would begin deferring `depends_on`-dependents too — verify `ll-issues
  list --skip-blocked` / next-issue selection still behaves as intended. [Agent 1 finding, verified]
- `scripts/little_loops/cli/sprint/edit.py:17` — `manager.load_or_resolve(args.sprint)`; `ll-sprint edit`
  resolves EPICs the same way as `run`/`show`, so it inherits the corrected ordering. No code change
  expected. [Agent 1 finding, verified]
- `scripts/little_loops/dependency_mapper/analysis.py:480-481` — `DependencyGraph.from_issues(...)` used
  purely for **cycle detection**. Directly relevant to the `detect_cycles()` extension: if `detect_cycles()`
  starts traversing `depends_on`, a `depends_on`-only cycle would now surface through `ll-deps` analysis
  too. Re-verify `ll-deps` cycle reporting under the new logic. [Agent 1 finding, verified]
- **CORRECTION to the prior wiring pass:** `scripts/little_loops/parallel/orchestrator.py` was listed
  above as a "Regression-sensitive" wave consumer, but it does **NOT** call `get_execution_waves()`,
  `get_ready_issues()`, or `DependencyGraph` at all (verified: zero matches). Parallel wave scheduling
  routes through `sprint.py`/`cli/sprint/run.py`, not `orchestrator.py`. `orchestrator.py` is out of the
  blast radius; no orchestrator change or re-verification is needed for this fix. [Agent 1 + Agent 3, verified]

### Built-in Loops (consume `load_or_resolve()`)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (lines 125, 306) — the loop from the
  bug's repro run; inherits corrected EPIC child ordering transparently via `Sprint.issues`. [Agent 1 finding]
- `scripts/little_loops/loops/goal-cluster.yaml` (lines 103-104) — also resolves EPICs via
  `load_or_resolve()`; same transparent inheritance. [Agent 1 finding]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py` — **AC #2 coverage gap (new test needed).** No existing
  test exercises `_get_next_issue()`/`get_ready_issues()` with a `depends_on` (vs `blocked_by`)
  fixture — `TestDependencyAwareSequencing` (class at line 502: `test_blocked_issue_not_selected_first` 565,
  `test_blocked_issue_selected_after_blocker_completed` 580, `test_no_issue_when_all_blocked` 600)
  all use `## Blocked By`. Add a `depends_on`-based analog asserting the dependent is not returned
  until its target completes. Also `TestCycleDetection`/`test_cycle_detected_on_init` (663-677)
  asserts on the `"Dependency cycle detected"` log string — still valid but will exercise a new
  code path if `detect_cycles()` starts traversing `depends_on` cycles. [Agent 3 finding]
- `scripts/tests/test_dependency_graph.py::TestCycleDetection` (class ~line 443) — builds cycles
  purely via `blocked_by`; existing asserts should still pass, but **new `depends_on`-cycle test
  cases must be added here** if `detect_cycles()` is extended. [Agent 2 finding]
- `scripts/tests/test_dependency_mapper.py` — imports `DependencyGraph`; verify chain-rendering
  tests don't encode the old soft-arrow semantics if `formatting.py` legend wording changes. [Agent 1 finding]
- `scripts/tests/test_sprint_integration.py` — `test_sprint_wave_composition` (line 243) and
  wave-count asserts (~1274, ~1322) use `## Blocked By`, so **not expected to break**, but they are
  the structural precedent for a new `depends_on`-defers-wave integration test (same
  `_setup_multi_wave_project` fixture shape). [Agent 2/3 finding]

_Wiring pass 3 added by `/ll:wire-issue` (2026-07-13):_
- `scripts/tests/test_cli_sprint_show.py` — **new gap.** Its render tests (`TestRenderExecutionPlan`,
  `TestRenderDependencyGraph`, ~lines 134-360) hand-build `waves = [[...]]` lists (unaffected by the
  fix), and its `--json` integration test (`test_show_json_output`, ~line 421) only asserts key presence
  (`"waves" in data`). There is **no test that builds a `depends_on` fixture and asserts on the real
  `get_execution_waves()` output through `ll-sprint show`** — the concrete test scaffold for Wiring-Phase
  step 5. No golden/snapshot files exist for `ll-sprint show`/`ll-deps`, so no stale-fixture break risk.
  [Agent 3 finding, verified]
- `scripts/tests/test_cli_sprint.py:828,1037` — mocks `get_execution_waves.return_value`, so it is
  decoupled from the real wave logic and **will not break**; listed only so it isn't mistaken for real
  coverage of the new ordering. [Agent 1 finding, verified]
- `scripts/tests/test_orchestrator.py` — confirmed **not** affected: `orchestrator.py` doesn't consume
  waves, so no `depends_on`-ordering case is needed here despite the (now-corrected) orchestrator mention
  above. [Agent 3 finding]

### Documentation
- `docs/guides/SPRINT_GUIDE.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — document
  `depends_on:` vs `blocked_by:` semantics for users; update if soft→ordering meaning changes.
- `docs/reference/API.md` — `DependencyGraph.get_execution_waves()` / `SprintManager` signatures.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — references dependency-graph architecture / Orchestration Layers; update
  if `depends_on` wave-ordering semantics change graph-wide (Option 1). [Agent 1 finding]

_Wiring pass 3 added by `/ll:wire-issue` (2026-07-13):_
The Option 1 change makes `depends_on` **ordering-enforcing** graph-wide, which directly contradicts
the "soft / not wave-gated" wording repeated verbatim across several reference docs and skills. Each
of these is an **independent copy** (not rendered from a single source) and must be reconciled so it
no longer claims `depends_on` is ignored for wave ordering:
- `docs/reference/ISSUE_TEMPLATE.md:893` — `depends_on` row: "Soft ordering prerequisites … **not
  wave-gated** (sprint proceeds without waiting)." Direct semantic claim this bug inverts. [Agent 2, verified]
- `skills/map-dependencies/SKILL.md:27` — field table: "`depends_on` … preferred ordering but **not
  wave-gated**". [Agent 2, verified]
- `skills/audit-issue-conflicts/SKILL.md` (~line 291 area) — interactive prompt text distinguishing
  `blocked_by` (wave-gated) vs `depends_on` (soft, not wave-gated) when adding a dependency edge. [Agent 2]
- `skills/scope-epic/SKILL.md` — **behavioral consumer, not just prose:** generates child issues with
  `depends_on: [...]` expecting them to influence ordering. This is exactly the contract BUG-2632 makes
  real — confirm generated EPIC children now schedule in the intended order after the fix. [Agent 2]
- `docs/reference/CLI.md` — `--edges` alias table (`hard` = `blocked_by`+`blocks`+`depends_on`),
  `ll-issues sequence`, and `ll-sprint show` wave-order wording; check for accuracy against the new
  enforcement. [Agent 2, lower risk]
- `docs/reference/OUTPUT_STYLING.md` — legend: `-->` = "Soft `depends_on` prerequisite" (used by
  `format_epic_tree`, ordered via `topological_sort()`, not `get_execution_waves()`); incidental but
  reconcile if the "soft" framing changes globally. [Agent 2, lower risk]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Add AC #2 dispatch-order regression test in `test_issue_manager.py` — a `depends_on`-based
   analog of `test_blocked_issue_not_selected_first` asserting `get_ready_issues()`/`_get_next_issue()`
   defers the dependent until its `depends_on` target completes (the path `get_execution_waves()`
   tests do not cover).
4. Extend `detect_cycles()` to traverse `depends_on_edges` and add `depends_on`-cycle cases to
   `test_dependency_graph.py::TestCycleDetection`; confirm `test_issue_manager.py:test_cycle_detected_on_init`
   still passes.
5. Verify wave-consuming CLI callers (`cli/sprint/manage.py:109`, `cli/sprint/show.py:194`,
   `cli/sprint/run.py:400`) still behave correctly under the new wave layout — no code change
   expected, but exercise `ll-sprint show`/`run` on the EPIC-2616 fixture.
6. Reconcile `dependency_mapper/formatting.py` chain-legend wording (`--> depends on`) with the new
   enforced ordering, or explicitly document the soft/visual vs. enforced distinction.
7. Confirm EPIC-resolving loops (`auto-refine-and-implement.yaml`, `goal-cluster.yaml`) inherit the
   corrected ordering via `Sprint.issues` with no loop-YAML change.

_Wiring pass 3 added by `/ll:wire-issue` (2026-07-13):_

8. Re-verify the `get_ready_issues()` filter in `issue_parser.py:1264` (`find_issues()` ready-set path)
   and `dependency_mapper/analysis.py:480-481` (cycle detection) under the new `depends_on` semantics —
   both are additional consumers of the changed functions beyond `issue_manager.py`.
9. Add a `depends_on`-ordering test to `test_cli_sprint_show.py` that drives the real
   `get_execution_waves()` through `ll-sprint show --json` (no such test exists today).
10. Reconcile the "not wave-gated" `depends_on` wording across `docs/reference/ISSUE_TEMPLATE.md:893`,
    `skills/map-dependencies/SKILL.md:27`, `skills/audit-issue-conflicts/SKILL.md`, and `docs/reference/CLI.md`
    so they no longer claim `depends_on` is ignored for ordering (Option 1 makes it enforcing). Verify
    `skills/scope-epic/SKILL.md`'s generated `depends_on` children now schedule in the intended order.
11. **Do NOT** add orchestrator work: `parallel/orchestrator.py` does not consume execution waves
    (corrected above) — the earlier "regression-sensitive orchestrator" note was inaccurate.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-13_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Change surface spans ~6-10 dependent callers/consumers (orchestrator.py, sprint/run.py, cli/auto.py, sequence/next_issue.py, cli/deps.py, plus wiring-pass additions in sprint/manage.py, sprint/show.py, issue_manager.py) — broad surface even though each individual site needs no code change, just re-verification under the new wave layout.
- `detect_cycles()` must be extended to traverse `depends_on_edges` in addition to `blocked_by`, which is new logic (not just a config/data change) and could introduce a new cycle-detection failure mode if not carefully bounded.

## Resolution

Implemented **Option 1** — `depends_on` is now ordering-enforcing graph-wide in
`get_execution_waves()`, via a single change to readiness semantics.

**Source changes (`scripts/little_loops/dependency_graph.py`):**
- Added `get_pending_prerequisites(issue_id, completed)` — returns the incomplete
  `depends_on` targets still present in the graph (absent/already-completed targets
  are never in `depends_on_edges`, so they never defer the dependent).
- `get_ready_issues()` now also excludes issues with pending `depends_on`
  prerequisites, so both `blocked_by` (hard/fatal) and `depends_on`
  (soft/non-fatal) gate readiness. This is the exact AC #2 path
  (`IssueManager._get_next_issue()` → `get_ready_issues()`), so `ll-auto`/autodev
  now defers dependents automatically.
- `get_execution_waves()` simplified — the old "pull-forward nudge" block is
  removed; strict per-wave ordering now falls out of the readiness gate. EPIC-2616
  resolves to `[[ENH-2617], [FEAT-2618, FEAT-2619], [ENH-2620]]`.
- `detect_cycles()` now traverses `depends_on_edges ∪ blocked_by`, so a
  `depends_on`-only cycle surfaces a meaningful error instead of an empty
  "cycles: " message.
- `sprint.py` `load_or_resolve()` docstring updated (AC #4).

**Tests:**
- `test_dependency_graph.py`: rewrote the two soft-semantics tests
  (`test_depends_on_enforces_wave_ordering`, `test_depends_on_diamond_ordering`,
  `…absent_target…`, `…completed_target…`) + 3 `depends_on`-cycle cases.
- `test_issue_manager.py`: AC #2 dispatch-order regression
  (`test_depends_on_dependent_not_selected_first` / `…after_prereq_completed`).
- `test_sprint.py`: AC #1 EPIC-2616 4-child ordering regression.
- `test_cli_sprint_show.py`: real `get_execution_waves()` through `--json`.

**Docs/skills reconciled** ("not wave-gated" → "wave-gated but non-fatal"):
`ISSUE_TEMPLATE.md`, `API.md`, `SPRINT_GUIDE.md`, `ISSUE_MANAGEMENT_GUIDE.md`,
`map-dependencies/SKILL.md`, `audit-issue-conflicts/SKILL.md`.

**Verification:** full suite `python -m pytest scripts/tests/` → 14873 passed,
36 skipped; `mypy` + `ruff` clean on changed files.

## Session Log
- `/ll:ready-issue` - 2026-07-13T20:53:18 - `a0d9a701-7b93-460f-8517-67eb329a920c.jsonl`
- `/ll:wire-issue` - 2026-07-13T20:42:03 - `d154846b-b4c8-41c5-b8d7-abc1392f1fa8.jsonl`
- `/ll:refine-issue` - 2026-07-13T20:01:16 - `ab08c78a-26df-4fed-a025-fdde9a34f268.jsonl`
- `/ll:refine-issue` - 2026-07-13T19:12:08 - `4cd0afa9-a469-4a21-8356-556cc6bf5d6e.jsonl`
- `/ll:confidence-check` - 2026-07-13T00:00:00 - `512e9fa0-44e8-41e5-881c-991b9a85cd58.jsonl`
- `/ll:wire-issue` - 2026-07-13T19:03:12 - `3d59c4d4-b18d-40a1-874b-1e281c5157ec.jsonl`
- `/ll:decide-issue` - 2026-07-13T18:54:44 - `e555b243-e23c-429d-9cab-61c70b69018b.jsonl`
- `/ll:refine-issue` - 2026-07-13T18:46:15 - `7b1b09e0-77ab-4197-917e-348281ecdd0c.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:40:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: done
- **Priority**: P2
