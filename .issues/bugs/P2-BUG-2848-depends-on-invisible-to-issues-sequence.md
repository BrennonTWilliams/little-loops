---
id: BUG-2848
type: BUG
priority: P2
status: done
discovered_date: 2026-07-26
completed_at: '2026-07-27T01:36:52Z'
discovered_by: manual-review
labels:
- dependency-graph
- issues-cli
- audit-issue-conflicts
relates_to:
- FEAT-2842
- ENH-2847
confidence_score: 96
outcome_confidence: 80
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2848: `depends_on` edges are invisible to `ll-issues sequence`, and the conflict audit prefers them

## Summary

`ll-issues sequence` orders issues with `DependencyGraph.topological_sort()`,
which computes in-degree **solely** from `blocked_by`. `depends_on` edges are
collected into a separate map that the sort never reads. Meanwhile
`/ll:audit-issue-conflicts` tells the user `depends_on` is the **preferred**
field for soft ordering. The skill's recommended choice therefore produces a
dependency edge that the sequencer structurally cannot see, and the dependent
issue is reported as having no blockers.

## Current Behavior

Two halves of the graph disagree about what `depends_on` means:

| Consumer | Honours `depends_on`? | Evidence |
|---|---|---|
| `get_ready_issues()` — wave planning, `ll-parallel`, `next-issue` | **Yes** | `dependency_graph.py:148-175`; "ordering-enforcing-but-non-fatal" (BUG-2632) |
| `topological_sort()` — `ll-issues sequence` | **No** | `dependency_graph.py:318-319` builds `in_degree` from `self.blocked_by` only; the loop at `:337` walks `self.blocks` only |

`depends_on_edges` (`dependency_graph.py:129-143`) has exactly one consumer
outside its own module — `dependency_mapper/formatting.py`, for display.

`/ll:audit-issue-conflicts` steers users toward the invisible field:

- `SKILL.md:370` — "`depends_on: [ISSUE-B]` (soft ordering — **preferred** when
  no hard dependency exists)"
- `interactive-prompts.md:34` — describes it as "wave-gated ordering (ISSUE-A
  scheduled after ISSUE-B) but non-fatal if ISSUE-B is absent"

That description is accurate for `get_ready_issues()` and silently wrong for
`ll-issues sequence`. A user who accepts the recommended option gets:

```
[P2, no blockers] FEAT-110: ...
```

for an issue the audit just recorded as dependent.

The `--json` output has the same hole: `sequence.py:63` emits
`"blocked_by": sorted(graph.blocked_by.get(...))` and no `depends_on` key at
all, so downstream automation cannot recover the edge either.

## Expected Behavior

`ll-issues sequence` must not report an issue as unblocked when a recorded
`depends_on` prerequisite is still active. Either:

- **(a)** `topological_sort()` gains an optional soft-edge mode that folds
  `depends_on_edges` into in-degree (matching `get_ready_issues()` semantics:
  prerequisites absent from the graph or already complete never block), and
  `sequence` uses it; or
- **(b)** `sequence` keeps hard-edge ordering but annotates and reports
  `depends_on` prerequisites in both text and `--json` output.

(a) is preferred — it makes one graph mean one thing. Under (a), rationale text
should distinguish the edge classes, e.g.
`[P2, blocked by: FEAT-109; after: FEAT-120]`.

Independently, `/ll:audit-issue-conflicts` must stop calling `depends_on` the
preferred default until the asymmetry is gone, and its option descriptions must
state which consumers honour each field.

## Root Cause

`depends_on` was added as a soft-prerequisite concept and wired into the
readiness/wave path only. `topological_sort()` predates it and was never
updated, so the two orderings diverged. Nothing tests that the two agree.

## Implementation Steps

1. Add a regression test asserting that an issue with an active `depends_on`
   prerequisite is **not** first in `ll-issues sequence` output — this fails
   today and pins the fix.
2. Implement (a): fold `depends_on_edges` into `topological_sort()`'s in-degree
   behind a parameter, defaulting to the semantics `get_ready_issues()` already
   uses. Confirm no existing caller of `topological_sort()` depends on the
   hard-edge-only behavior.
3. Extend `sequence.py` rationale text to name the edge class, and add
   `"depends_on"` to the `--json` record (`sequence.py:56-69`).
4. Fix `SKILL.md:370` — drop "preferred", default the prompt to `blocked_by`.
5. Fix `interactive-prompts.md:31-34` — state per-field which consumers honour
   the edge.
6. Audit the other `topological_sort()` callers (`cli/issues/clusters.py:642`
   uses its own `_topo_sort_cluster` over a `blocked_by`-only map — decide
   whether it needs the same treatment or is intentionally hard-edges-only).

## Acceptance Criteria

- [ ] A test constructs A with `depends_on: [B]`, B active, and asserts
      `ll-issues sequence` does not place A before B and does not label A
      `no blockers`.
- [ ] `ll-issues sequence --json` includes soft prerequisites.
- [ ] `topological_sort()` and `get_ready_issues()` agree on whether a given
      `depends_on` edge constrains ordering; a test pins the agreement.
- [ ] Neither `SKILL.md` nor `interactive-prompts.md` presents `depends_on` as
      the preferred default.

## Impact

- **Users**: issues with recorded soft prerequisites are scheduled first and
  presented as ready. The failure is silent and looks like a correct answer,
  which is worse than an error.
- **Risk**: Medium. Every `depends_on` edge written since BUG-2632 is
  potentially mis-sequenced; conversely, folding soft edges into the sort could
  reorder existing output, so the change needs the caller audit in step 6.
- **Effort**: Small-Medium.

## Steps to Reproduce

1. Take two active issues A and B.
2. `ll-issues link A --depends-on B` (or hand-add `depends_on: [B]` to A's
   frontmatter today).
3. Run `ll-issues sequence`.
4. Observe A listed with rationale `no blockers`, potentially ahead of B.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/dependency_graph.py:301-346` | `topological_sort()` — reads `blocked_by` only |
| `scripts/little_loops/dependency_graph.py:148-175` | `get_ready_issues()` — the semantics to match |
| `scripts/little_loops/cli/issues/sequence.py:43-82` | The consumer producing the wrong output |
| `skills/audit-issue-conflicts/interactive-prompts.md:23-37` | The prompt steering users to the invisible field |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale line ref**: the "preferred" language in step 4 lives at
  `skills/audit-issue-conflicts/SKILL.md:381` (verified against current file),
  not `:370` as stated above — the file has shifted since this issue was
  drafted.
- **Reusable predicate for step 2**: `get_pending_prerequisites(issue_id,
  completed)` (`dependency_graph.py:183-201`) is already the exact "prerequisite
  absent/completed never blocks, active prerequisite blocks" rule —
  `self.depends_on_edges.get(issue_id, set()) - completed`. `topological_sort()`
  can reuse this directly rather than reimplementing the filter.
- **No existing soft-edge toggle convention**: grep for
  `include_depends_on|include_soft|strict:|honor_depends_on|respect_depends_on`
  in `scripts/` returns no matches — there is no precedent boolean-parameter
  pattern to follow. `detect_cycles()` (`dependency_graph.py:355-407`) and
  `get_execution_waves()` instead always union `blocked_by` and
  `depends_on_edges` unconditionally
  (`self.blocked_by.get(node, set()) | self.depends_on_edges.get(node, set())`
  at line 388) — that unconditional-union shape is the closer precedent if (a)
  is implemented as "always fold soft edges in" rather than an opt-in flag.
- **No reverse index for `depends_on_edges`**: unlike `blocked_by`/`blocks`,
  which are precomputed as mirror maps, `depends_on_edges` is one-directional
  only (`from_issues()` comment at line 130: "no reverse edge is built here").
  A Kahn's-algorithm fix needs to derive a dependent-of (reverse) map on the
  fly since there's no existing `depends_on_by`-style forward index to walk.
- **Test locations for step 1**: extend `class TestTopologicalSort` in
  `scripts/tests/test_dependency_graph.py:388-449` (existing tests:
  `test_no_deps_sorted_by_priority`, `test_linear_chain_order`,
  `test_diamond_dependency`, `test_empty_graph`, `test_cycle_raises_value_error`)
  using the `make_issue(..., depends_on=[...])` fixture helper
  (`test_dependency_graph.py:18-39`). CLI-level `--json` assertions belong in
  the `sequence` command test block in `scripts/tests/test_issues_cli.py:1408-1663`
  (pattern: `assert "blocked_by" in item` at line 1508 — mirror this for the new
  `depends_on`/prerequisite key).
- **`_topo_sort_cluster()` for step 6**: confirmed structurally separate from
  `DependencyGraph` — `scripts/little_loops/cli/issues/clusters.py:350-384`
  takes a bare caller-constructed `blocked_by: dict[str, set[str]]` map (built
  at `clusters.py:631-634` directly from `issue.blocked_by`), not a
  `DependencyGraph` instance, so it can't inherit the fix automatically; it
  needs its own explicit decision/change per step 6.
- **JSON-field extension precedent**: `sequence.py`'s existing `--json` block
  (`cmd_sequence()`, lines 54-70) already shows the additive-field convention
  to follow for a new `depends_on`/prerequisite key — plain always-present dict
  keys (`"blocked_by"`, `"blocks"`) alongside a conditional
  `**({...} if condition else {})` spread (used there for `type_filter`).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/formatting.py:267` — `format_epic_tree()` calls `graph.topological_sort()` directly (`ordered = [issue for issue in graph.topological_sort() if issue.issue_id in child_map]`). This is a second, previously unlisted consumer. If fix option (a) changes `topological_sort()`'s *default* in-degree calculation (rather than adding an opt-in parameter), `ll-deps` epic-tree child ordering will silently change for any epic whose children carry `depends_on` edges. Confirmed independently by both the caller-tracer and side-effect agents. [Agent 1 + Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:26-32` — contains the same mischaracterization the issue targets in `SKILL.md`/`interactive-prompts.md`: "For preferred-but-not-required ordering, use `depends_on` instead." This is the canonical field-semantics reference other docs point to and was not in the issue's original file list — update alongside the skill docs in step 4/5. [Agent 2 finding]
- `docs/reference/API.md:1191-1201` — generated API reference for `topological_sort()`'s docstring; will drift from the updated docstring unless regenerated via `ll-generate-schemas`-adjacent doc regen (or hand-updated) once the method's behavior/parameter changes. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_dependency_mapper.py` — no existing test pins `format_epic_tree()`'s ordering against `depends_on` edges; add one if step 2's fix changes `topological_sort()`'s default behavior (per the Dependent Files finding above), so epic-tree reordering is intentional and covered, not incidental. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_cli.py:1096` — asserts `"blocked by: FEAT-001" in output` against `_render_execution_plan()` (`scripts/little_loops/cli/sprint/_helpers.py`), an **independent** implementation that happens to share the `"blocked by: "` substring with `sequence.py`'s rationale text. Do not let step 3's rationale-text reword (`"blocked by: X; after: Y"`) leak into this file via a codebase-wide find/replace — it is out of scope and already correct. [Agent 2 finding]
- `scripts/tests/test_dependency_graph.py` — existing `TestTopologicalSort` cases (`test_no_deps_sorted_by_priority:391`, `test_linear_chain_order:404`, `test_diamond_dependency:416`, `test_empty_graph:435`, `test_cycle_raises_value_error:441`) all use `blocked_by`-only fixtures and won't break from folding `depends_on`, but none exercise the reverse-lookup gap below — the regression test in step 1 must cover it explicitly. [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Reverse-lookup gap (correctness-critical for step 2)**: `topological_sort()`'s decrement loop (`dependency_graph.py:337`) walks `self.blocks.get(issue_id, set())` — a reverse map populated only from `blocked_by`/`blocks`. `depends_on_edges` is one-directional (`from_issues()` comment at line 130-131: "no reverse edge is built here"). Folding `depends_on_edges` into the *initial* in-degree count without also deriving a reverse (dependent-of) map for the decrement step will leave in-degree permanently non-zero for any issue with an active `depends_on` prerequisite, making it vanish from the sort output entirely rather than being correctly ordered after its prerequisite. Build the reverse map on the fly (no existing `depends_on_by`-style index to reuse).
8. Audit `dependency_mapper/formatting.py:267` (`format_epic_tree()`) — decide whether its `topological_sort()` call should inherit the new soft-edge semantics (epic-tree child order also reflects `depends_on`) or be pinned to hard-edges-only via the same parameter used in step 2; add a `test_dependency_mapper.py` case either way.
9. Update `docs/ARCHITECTURE.md:26-32`'s field-semantics table alongside `SKILL.md`/`interactive-prompts.md` so all three no longer describe `depends_on` as simply "preferred."

## Context

Found while auditing `/ll:audit-issue-conflicts` after `ll-issues sequence`
placed a dependent issue first with rationale `[P2, no blockers]`.

## Resolution

- **Completed**: 2026-07-27
- **Fix**: Implemented option (a) — `topological_sort()` now folds
  `depends_on_edges` into its Kahn's-algorithm in-degree calculation, deriving
  a dependent-of reverse map on the fly for the decrement step (no existing
  `depends_on_by`-style index to reuse). `get_ready_issues()` and
  `topological_sort()` now agree on `depends_on` semantics.
- **`sequence.py`**: rationale text now distinguishes edge classes
  (`blocked by: X; after: Y`), and `--json` output gained a `depends_on` key
  (pending prerequisites via `get_pending_prerequisites()`).
- **`format_epic_tree()`**: inherits the new soft-edge semantics (no opt-in
  parameter added, matching the unconditional-union precedent already used by
  `detect_cycles()`/`get_execution_waves()`); pinned with a new
  `test_dependency_mapper.py` case.
- **`_topo_sort_cluster()`** (`clusters.py`): left hard-edges-only —
  structurally separate from `DependencyGraph` (takes a bare caller-built
  `blocked_by` map), out of scope for this fix per step 6's own research
  finding; not changed.
- **Docs**: `SKILL.md`/`interactive-prompts.md` no longer call `depends_on`
  "preferred" and now state which consumers honour each field; default
  guidance points to `blocked_by` when unsure. `docs/ARCHITECTURE.md`'s
  "preferred-but-not-required" phrasing cited in the issue's wiring pass was
  already gone from the current file (stale reference) — no change needed
  there.
- **Tests**: added regression coverage in `test_dependency_graph.py`
  (`TestTopologicalSort`), `test_issues_cli.py` (`--json` `depends_on` key),
  and `test_dependency_mapper.py` (`TestFormatEpicTree`).

## Session Log
- `/ll:manage-issue` - 2026-07-27T01:36:10 - `be2ae143-085e-4b1a-86c5-8cf54d81f613.jsonl`
- `/ll:ready-issue` - 2026-07-27T01:25:40 - `7c823fe0-8787-46ef-982b-a1a134fba8be.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `d7d11d8f-c76c-4dbf-ba12-f3341e8a249c.jsonl`
- `/ll:wire-issue` - 2026-07-27T01:23:28 - `b5a869fe-5f62-444f-99a9-0656b67e2bb2.jsonl`
- `/ll:refine-issue` - 2026-07-27T01:17:24 - `58c10c66-949c-4a71-be48-0b7e4dc32477.jsonl`

---

## Status

open
