---
id: FEAT-2683
title: 'll-queue run: serial dequeue-and-execute worker loop'
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T00:00:00Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2670
depends_on:
- FEAT-2682
relates_to:
- FEAT-2669
- FEAT-2682
labels:
- queue
- cli
- scheduling
---

# FEAT-2683: `ll-queue run` — serial dequeue-and-execute worker loop

## Summary

Add the `ll-queue run` worker that dequeues persisted entries (from
FEAT-2682's store) by priority/FIFO and dispatches each through
ENH-2668's shared `run_action()`, updating entry `status`/`result` with
the actual execution outcome. Strict serial execution for v1, per
FEAT-2669's resolved Q1.

## Parent Issue

Decomposed from FEAT-2669: Generic `ll-queue` (heterogeneous work-item
queue). This child covers the "execution-on-dequeue" half of FEAT-2669's
Expected Behavior — the half that turns persisted entries into actual
work getting done, replacing today's block-and-retry-lock pattern.

## Motivation

Today, nothing ever dequeues-and-executes a queue entry — a "queued"
FSM loop is just the blocked process retrying its lock
(`cli/loop/run.py:355-369`). FEAT-2682 gives entries a real home; this
child is what actually runs them.

## Expected Behavior

- `ll-queue run` (or a long-running worker mode) dequeues entries from
  FEAT-2682's persistence layer in priority/FIFO order.
- Each entry's `ActionSpec` is dispatched through ENH-2668's
  `run_action()` (`runner_spec.py`), covering `SKILL`/`CMD`/`MCP`/
  `PROMPT` kinds. `RunnerType.LOOP` dispatch stays out of scope here —
  `run_action()` explicitly excludes it (raises `ValueError`); FSM loop
  execution remains on `PersistentExecutor` per ENH-2668's existing
  design, not something this child changes.
- Strict serial execution for v1 (FEAT-2669 Decision Rationale Q1) — a
  serial loop directly calling `run_action()`, no `ThreadPoolExecutor`/
  `WorkerPool`-style bounded concurrency. That precedent
  (`parallel/worker_pool.py`, `cli/sprint/run.py:487-498`) is
  issue-processing-specific and explicitly deferred as unneeded surface
  area for v1.
- On completion, the entry's `status` and `result` (per FEAT-2682's
  hybrid inline/scratch schema) reflect the actual execution outcome —
  not a liveness guess.

## Acceptance Criteria

- `ll-queue run` dequeues and executes entries through the ENH-2668
  runner in priority/FIFO order.
- Entry `status`/`result` reflect actual execution outcomes (success,
  failure, exit code, error) after `run` processes them.
- New test coverage for worker dequeue-and-dispatch ordering and
  status/result updates, independent of FEAT-2682's persistence tests.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: the dequeue loop, dispatch through `run_action()`, status/
  result write-back on completion.
- **Out**: queue persistence/schema and `add`/`list`/`status`/`remove`
  (FEAT-2682, a dependency of this child). Bounded-concurrency execution
  — explicitly deferred to a future issue if needed. `ll-loop run
  --queue` compat behavior (FEAT-2684).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2669 | Parent issue — full design context and resolved open questions |
| FEAT-2682 | Persistence layer this worker dequeues from |
| ENH-2668 | `run_action()` — the dispatch target for each dequeued entry |

## Session Log
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Status

**Open** | Created: 2026-07-18 | Priority: P2
