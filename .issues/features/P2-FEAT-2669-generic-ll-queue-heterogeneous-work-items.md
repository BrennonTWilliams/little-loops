---
id: FEAT-2669
title: "Generic ll-queue: heterogeneous work-item queue with real add/run semantics"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-18T00:00:00Z"
discovered_date: 2026-07-18
discovered_by: capture-issue
depends_on: [ENH-2668]
parent: EPIC-2670
relates_to: [ENH-2668]
labels:
  - queue
  - cli
  - scheduling
decision_needed: true
---

# FEAT-2669: Generic `ll-queue` (heterogeneous work-item queue)

## Summary

Build a generic `ll-queue` that accepts heterogeneous work items — FSM
loops, prompts/Skills/Commands, and raw CLI commands — as first-class
queueable entries, with real `add`, ordering, and execution-on-dequeue
semantics. Built on the `RunnerType`/`ActionSpec` abstraction from ENH-2668.
This is Phase 2 of `thoughts/plans/2026-07-17-generic-ll-queue-design.md`.

**Blocked on ENH-2668**, and `decision_needed: true` — four open design
questions (below) must be resolved (or spiked via `/ll:spike`) before
implementation starts.

## Motivation

`ll-loop queue` is not a scheduler — it's a liveness-marker mechanism for
FSM loop execution. There is no `add`/`enqueue` command; a queue entry
(`.loops/.queue/{uuid}.json`) is only ever created as a side effect of
`ll-loop run --queue` losing a lock race (`cli/loop/run.py:355-369`).
"Running" a queued entry is just the blocked process retrying its lock;
`queue remove` only SIGTERMs the waiter and deletes the marker file
(`queue.py:159-167`). Nothing ever dequeues-and-executes an item, and there
is no way to queue non-FSM work (a single skill invocation, a one-shot
command, a prompt) for long-running, ordered, or throttled execution.

## Expected Behavior

- Real persisted queue entries (not liveness markers) — likely
  `.ll/queue.db` (sqlite, consistent with `.ll/history.db`) or a
  `.queue/*.json` directory with a proper schema:
  `{id, action: ActionSpec, enqueuedAt, priority, status, result}`.
- `ll-queue add <action-spec>` — accepts an FSM loop name, a skill/command
  name, or a raw CLI invocation, normalized into an `ActionSpec` via
  ENH-2668.
- `ll-queue run` / a worker loop that dequeues by priority/FIFO and
  dispatches through the shared runner, replacing today's
  block-and-retry-lock pattern with actual sequential (or bounded-
  concurrency) execution.
- `ll-queue list`/`status`/`remove` mirroring today's `ll-loop queue` UX
  but operating on real entries with real status, not just PID liveness.

## Open Questions (resolve before implementation)

1. Bounded concurrency (N workers) or strict serial execution for v1?
2. Preserve `ll-loop run --queue`'s lock-conflict behavior as a
   compatibility shim, or accept a breaking change?
3. Priority model: simple FIFO, or numeric priority like
   `IssuePriorityQueue`?
4. Where do results live — inline in the queue entry, or written to
   `.loops/tmp/`-style artifacts per the scratch-pad convention?

Recommendation: resolve via a short `/ll:spike` or a design decision pass;
record outcomes in `.ll/decisions.yaml` and update this issue before
starting.

## Integration Map

### Files to Modify

- New `scripts/little_loops/cli/queue.py` (or `cli/queue/` package) —
  `add`/`run`/`list`/`status`/`remove`
- `scripts/little_loops/cli/loop/run.py` — `--queue` behavior (per open
  question #2)
- `scripts/little_loops/cli/loop/queue.py` + `cli/loop/__init__.py:884-919`
  — deprecate/shim/replace `ll-loop queue`
- Persistence layer (sqlite or JSON dir, per open question #4 discussion)

### Dependent Files (Callers/Importers)

- `cli/loop/_helpers.py:172-200` (`read_queue_entries()`) — current marker
  reader; retired or repointed

### Similar Patterns

- `parallel/priority_queue.py:22-259` (`IssuePriorityQueue`) — ordering
  precedent, but hard-typed to `IssueInfo`
- `cli/sprint/run.py:487-498` — `ThreadPoolExecutor`-based orchestrator
  precedent

### Tests

- New test module for queue persistence, ordering, add/normalize, worker
  dequeue-and-dispatch, remove/status
- Existing `ll-loop queue` tests updated per compat decision

### Documentation

- `docs/reference/API.md` and CLI docs — new `ll-queue` command
- ENH-2620 (document ll-loop queue subcommands) may be affected/superseded

### Configuration

- Possible `queue.*` namespace in `.ll/ll-config.json` (worker count,
  result location) — finalize with the open questions

## Acceptance Criteria

- `ll-queue add` accepts all three work-item kinds (FSM loop, skill/command/
  prompt, raw CLI invocation) and persists real entries with schema
  `{id, action, enqueuedAt, priority, status, result}`.
- `ll-queue run` dequeues and executes entries through the ENH-2668 runner;
  entry `status`/`result` reflect actual execution outcomes.
- `ll-queue list`/`status`/`remove` operate on real entries (no PID-liveness
  inference).
- `ll-loop run --queue` behavior matches whatever open question #2 decided,
  with the decision recorded.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: queue persistence, `add`/`run`/`list`/`status`/`remove`, worker
  loop, `ll-loop queue` migration/shim.
- **Out**: replacing `ll-parallel`/`ll-sprint`'s issue-specific orchestration
  — those stay issue-typed and separate. `ll-queue` is for smaller/
  heterogeneous long-tail work, not issue-driven waves. Further
  decomposition (persistence vs. commands as separate issues) deferred until
  the open questions are answered.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | Source design doc — Phase 2 + open questions |
| ENH-2668 | Prerequisite runner abstraction |
| ENH-2620 | Existing ll-loop queue docs issue — may be superseded |

## Impact

- **Priority**: P2 — unlocks queueing of non-FSM work; no user blocked today.
- **Effort**: Medium-Large — new scheduler design + persistence + five
  subcommands + compat migration; several design decisions still open.
- **Risk**: Medium — genuinely new design work; compat question #2 could be
  a breaking change for `ll-loop run --queue` users.
- **Breaking Change**: Possibly — depends on open question #2.

## Status

**Open (blocked on ENH-2668 + open questions)** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-18T00:00:00Z - filed from `thoughts/plans/2026-07-17-generic-ll-queue-design.md` Phase 2; blocked on ENH-2668 and four open design questions.
