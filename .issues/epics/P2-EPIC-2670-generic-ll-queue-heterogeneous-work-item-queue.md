---
id: EPIC-2670
type: EPIC
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
relates_to:
- ENH-2668
- EPIC-2616
- ENH-2620
- FEAT-2682
- FEAT-2683
- FEAT-2684
labels:
- queue
- runners
- cli
- scheduling
completed_at: '2026-07-19T20:20:28Z'
---

# EPIC-2670: Generic `ll-queue` — heterogeneous work-item queue on a shared runner abstraction

## Summary

Replace `ll-loop queue`'s liveness-marker mechanism with a real work-item
queue. Today a queue entry (`.loops/.queue/{uuid}.json`) is only created as a
side effect of `ll-loop run --queue` losing a lock race
(`cli/loop/run.py:355-369`); nothing ever dequeues-and-executes an item, and
there is no way to queue non-FSM work (a skill invocation, a one-shot
command, a prompt) for long-running, ordered, or throttled execution. This
EPIC delivers that in two phases: extract a shared
`RunnerType`/`ActionSpec` runner abstraction from
`ll-harness`/`ll-action`/`ll-loop` (ENH-2668), then build `ll-queue` with
real `add`/`run`/`list`/`status`/`remove` semantics on top of it
(FEAT-2669). Design doc:
`thoughts/plans/2026-07-17-generic-ll-queue-design.md`.

## Goal

Heterogeneous work items — FSM loops, prompts/Skills/Commands, and raw CLI
commands — are first-class queueable entries with real enqueue, ordering,
and execution-on-dequeue semantics, dispatched through one shared runner
primitive instead of three parallel if/elif dispatchers.

## Motivation

- `ll-loop queue` is not a scheduler; it's PID-liveness bookkeeping for the
  block-and-retry-lock pattern. `queue remove` only SIGTERMs the waiter
  (`queue.py:159-167`).
- No shared runner abstraction exists: `ll-action` and `ll-harness` each own
  if/elif dispatch, sharing only the `RunnerResult` output shape
  (`harness.py:25-33`). The extraction (Phase 1) is independently useful —
  it removes that duplication even if the queue slips.
- `ll-parallel`/`ll-sprint` do ordering but are hard-typed to
  `IssueInfo`/parsed `.issues/*.md`; a generic queue sits beside them for
  smaller/heterogeneous long-tail work, not issue-driven waves.

## Scope

**In scope:**
- Shared runner abstraction: `RunnerType` enum + `ActionSpec` dataclass +
  single dispatch function; `ll-action`/`ll-harness`/`ll-loop run` become
  thin callers (ENH-2668).
- `ll-queue` command family with persisted entries
  (`{id, action, enqueuedAt, priority, status, result}`), a worker loop that
  dequeues and dispatches through the shared runner, and
  `add`/`run`/`list`/`status`/`remove` (FEAT-2669).
- Migration/compat story for `ll-loop run --queue` and the EPIC-2616
  `ll-loop queue` subcommands (decision pending — see FEAT-2669 open
  questions).

**Explicitly out of scope:**
- Replacing `ll-parallel`/`ll-sprint` issue-specific orchestration.
- Changing runner semantics, timeouts, or existing CLI UX in Phase 1.
- The HTMX dashboard / HTTP bridge deferred from EPIC-2616.

## Sequencing

Phase 1 (ENH-2668) first, as standalone work, validated before committing to
Phase 2's scheduler design — the abstraction is low-risk and mechanical; the
scheduler is new design work with four open questions (concurrency model,
`--queue` compat shim vs. breaking change, priority model, result storage)
that FEAT-2669 carries as `decision_needed: true`. Do not decompose Phase 2
further until those are resolved (via `/ll:spike` or decisions.yaml).

## Children

- **ENH-2668** — Extract shared runner abstraction (`RunnerType`/`ActionSpec`)
  from `ll-harness`/`ll-action`/`ll-loop`.
- **FEAT-2669** — Generic `ll-queue`: heterogeneous work-item queue with real
  add/run semantics (blocked on ENH-2668 + open questions).
- **FEAT-2682** — `ll-queue` persistence + CRUD commands (`add`/`list`/
  `status`/`remove`) backed by `.ll/queue.db`.
- **FEAT-2683** — `ll-queue run` worker loop: serial dequeue-and-execute
  dispatching through the ENH-2668 shared runner.
- **FEAT-2684** — `ll-loop queue` compat shim: migrate FEAT-2616's
  PID-liveness markers to the new persisted queue while preserving
  `ll-loop queue list`/`remove` UX.

## Success Metrics

- One dispatch primitive covers `skill`/`cmd`/`mcp`/`prompt`/`dsl` + FSM loop
  execution; no duplicated runner if/elif remains in
  `action.py`/`harness.py`.
- `ll-queue add` accepts all three work-item kinds; `ll-queue run` actually
  dequeues and executes with real status/result tracking.
- FEAT-2669's four open questions have recorded decisions before its
  implementation begins.
- `python -m pytest scripts/tests/` exits 0 across both phases.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/harness.py`, `cli/action.py`,
  `cli/loop/run.py` — Phase 1 extraction call sites
- New runner module + new `cli/queue.py` (or package) — Phase 2
- `cli/loop/queue.py`, `cli/loop/_helpers.py:172-200` — deprecate/shim/retire
  per compat decision

### Related Key Documentation
| Document | Why Relevant |
|----------|--------------|
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | Source design doc (both phases) |
| EPIC-2616 | Existing `ll-loop queue` list/remove CLI this supersedes/migrates |
| ENH-2620 | ll-loop queue docs issue — likely superseded by FEAT-2669 |

## Impact

- **Priority**: P2 — unlocks queueing of non-FSM work; cleans up three-way
  dispatch duplication; nothing blocked today.
- **Effort**: Large across the EPIC (Small-Medium Phase 1 + Medium-Large
  Phase 2).
- **Risk**: Medium — Phase 1 low (behavior-preserving); Phase 2 carries the
  compat/breaking-change question for `ll-loop run --queue`.
- **Breaking Change**: Possibly — depends on the compat decision in
  FEAT-2669.

## Session Log
- `/ll:capture-issue` - 2026-07-18T00:00:00Z - epic grouping ENH-2668 + FEAT-2669, from `thoughts/plans/2026-07-17-generic-ll-queue-design.md`.

---

## Status

- **Current**: done
- **Last Updated**: 2026-07-19
- **Closure**: All 5 children (ENH-2668, FEAT-2669, FEAT-2682, FEAT-2683,
  FEAT-2684) completed 2026-07-18. Shared `RunnerType`/`ActionSpec` abstraction
  extracted; `ll-queue` CRUD + worker loop shipped; `ll-loop queue` migrated
  to a compat shim over the new persisted queue.
