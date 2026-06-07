---
id: FEAT-1991
title: "rn-implement — Value-Ranked Dequeue (select_next scheduler)"
type: FEAT
priority: P3
status: open
parent: FEAT-1990
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Medium
relates_to:
- FEAT-1990
labels:
- loops
- scheduling
- rn-implement
---

# FEAT-1991: `rn-implement` — Value-Ranked Dequeue (`select_next`)

## Summary

Add a `value_ranked` schedule mode to `rn-implement` so that, instead of popping
the head of `queue.txt` (FIFO / depth-first prepend), it selects the
highest-value **ready** issue at the current frontier each tick — using
`ll-deps` for dependency-readiness and `ll-issues impact-effort` for value.
This is the one genuinely new capability behind EPIC-1811's "agents decide what
to work on next" thesis, and it benefits every `rn-implement` caller, not just
`rn-build` (FEAT-1990).

## Parent Issue

Decomposed from FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder.

## Motivation

`rn-implement` today is blind: `dequeue_next` (`rn-implement.yaml:101`) pops the
head of the queue, and `rn-decompose` prepends children depth-first. There is no
notion of "which ready issue is most valuable to do next." `goal-cluster` does
topo order; neither ranks by value. For a greenfield build (and for backlog
processing generally), value- and dependency-aware ordering is the difference
between an agent that *processes* a queue and one that *decides* what to work on.

## Design

### Critical constraint — rank at the frontier, not globally

`rn-implement` deliberately prepends decomposed children (depth-first) so a
parent fully resolves before siblings; a naive global value-rank would interleave
half-finished feature trees and thrash shared files. The scheduler MUST:

1. Compute the **ready set**: queued issues whose `blocked_by` deps are all
   `done` and that are not in `blocked.txt`.
2. Rank the ready set by a composite score (see below).
3. Use **depth-first as the tie-breaker** (prefer deeper / more-recently
   decomposed issues at equal score) to preserve the resolve-parent-subtree-first
   discipline.

### Schedule modes

Add a `schedule_mode` context knob (default `fifo` to preserve current behavior;
`value_ranked` opt-in):

```yaml
context:
  schedule_mode: "fifo"   # "fifo" (current) | "value_ranked"
```

### `select_next` state

Replace the bare `dequeue_next` pop with a mode dispatch:
- `fifo` → existing `queue_pop` behavior (unchanged).
- `value_ranked` → new `select_next` shell state that:
  - reads `queue.txt`, `depth_map.txt`, `blocked.txt`, `visited.txt`
  - shells to `ll-deps` to filter the ready set (deps satisfied)
  - shells to `ll-issues impact-effort --json` for value scores
  - computes composite rank = `priority_weight` (P0 highest) + `impact/effort`,
    tie-broken by depth (deeper first)
  - removes the chosen issue from `queue.txt`, writes it as `captured.input`,
    increments `dequeue_count`, marks visited — matching the post-conditions of
    today's `dequeue_next` exactly so downstream states are unchanged.

### Ranking signal (composite)

| Signal | Source | Weight |
|--------|--------|--------|
| Priority (P0–P5) | issue filename / frontmatter | primary |
| Impact / effort | `ll-issues impact-effort` | secondary |
| Depth (tie-break) | `depth_map.txt` | deeper first |

Ready-set gating (`blocked_by` all `done`) is a hard filter applied before ranking.

## Files to Modify

- `scripts/little_loops/loops/rn-implement.yaml` — add `schedule_mode` context
  knob; add `select_next` state; route `dequeue_next` → `select_next` when
  `value_ranked`.
- `scripts/tests/test_rn_implement.py` (or the existing rn-implement test module)
  — add ready-set gating tests, ranking tests, depth-tiebreak test, and a
  `fifo`-unchanged regression test.
- `docs/guides/LOOPS_GUIDE.md` — document `schedule_mode`.

## Acceptance Criteria

- `schedule_mode: fifo` reproduces current behavior exactly (regression test).
- `schedule_mode: value_ranked` only ever selects issues whose `blocked_by` deps
  are all `done`.
- At equal composite score, the deeper issue is selected (depth-first tie-break).
- `select_next` leaves the same post-state as `dequeue_next` (queue popped,
  `captured.input` set, counters/visited updated).
- `ll-loop validate rn-implement.yaml` passes.
- `python -m pytest scripts/tests/ -k rn_implement -v` passes.

## Dependencies

- **Unblocked** — can start immediately; decoupled from goal-cluster.
- Verify `ll-issues impact-effort --json` exists and returns per-issue scores; if
  not, fall back to `score_complexity`/`score_*` frontmatter fields already
  present on refined issues.

## Status

- **State**: open
- **Created**: 2026-06-06
