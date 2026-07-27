---
id: BUG-2848
type: BUG
priority: P2
status: open
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- dependency-graph
- issues-cli
- audit-issue-conflicts
relates_to:
- FEAT-2842
- ENH-2847
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

## Context

Found while auditing `/ll:audit-issue-conflicts` after `ll-issues sequence`
placed a dependent issue first with rationale `[P2, no blockers]`.

---

## Status

open
