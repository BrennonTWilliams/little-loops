---
id: FEAT-2669
title: 'Generic ll-queue: heterogeneous work-item queue with real add/run semantics'
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
depends_on:
- ENH-2668
parent: EPIC-2670
relates_to:
- ENH-2668
labels:
- queue
- cli
- scheduling
decision_needed: true
confidence_score: 90
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 18
size: Very Large
completed_at: '2026-07-18T21:06:14Z'
---

# FEAT-2669: Generic `ll-queue` (heterogeneous work-item queue)

## Summary

Build a generic `ll-queue` that accepts heterogeneous work items — FSM
loops, prompts/Skills/Commands, and raw CLI commands — as first-class
queueable entries, with real `add`, ordering, and execution-on-dequeue
semantics. Built on the `RunnerType`/`ActionSpec` abstraction from ENH-2668.
This is Phase 2 of `thoughts/plans/2026-07-17-generic-ll-queue-design.md`.

**ENH-2668 is now done** (`RunnerType`/`ActionSpec`/`run_action()` exist in
`runner_spec.py`), and all four open design questions below are resolved —
this issue is unblocked for implementation.

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

1. **Bounded concurrency (N workers) or strict serial execution for v1?**
   ✅ **RESOLVED** (2026-07-18, by `/ll:refine-issue`) — strict serial
   execution for v1.
2. **Preserve `ll-loop run --queue`'s lock-conflict behavior as a
   compatibility shim, or accept a breaking change?**
   ✅ **RESOLVED** (2026-07-18, by `/ll:refine-issue`) — preserve as a
   compatibility shim.
3. **Priority model: simple FIFO, or numeric priority like
   `IssuePriorityQueue`?**
   ✅ **RESOLVED** (2026-07-18, by `/ll:refine-issue`) — numeric priority,
   reusing `IssuePriorityQueue`'s model.
4. **Where do results live — inline in the queue entry, or written to
   `.loops/tmp/`-style artifacts per the scratch-pad convention?**
   ✅ **RESOLVED** (2026-07-18, by `/ll:refine-issue`) — hybrid: small
   result metadata inline, large stdout/stderr as scratch artifacts.

See `### Codebase Research Findings` below for evidence and rationale
behind each resolution.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ENH-2668 status correction**: this issue's Summary/Motivation describe
  it as blocked on ENH-2668. As of this research pass, ENH-2668 is
  `status: done` — `RunnerType`, `ActionSpec`, `RunnerResult`, and
  `run_action()` already exist in `scripts/little_loops/runner_spec.py`
  (lines 43–226), covering `SKILL`/`CMD`/`MCP`/`PROMPT` dispatch.
  `RunnerType.LOOP` exists in the enum but is explicitly excluded from
  `run_action()`'s dispatch table (raises `ValueError`) — FSM loop
  execution stays on `PersistentExecutor`, not the shared runner. This
  issue's remaining blocker is implementation, not a missing dependency.
- **Q1 (concurrency)**: `WorkerPool` (`parallel/worker_pool.py`) and
  `cli/sprint/run.py:487-498` are the proven bounded-concurrency
  precedent (`ThreadPoolExecutor`, `Future`-per-item, SIGTERM/SIGKILL
  grace windows), but they are issue-processing-specific and add
  meaningful surface area this issue's own Scope Boundaries defer
  ("Further decomposition... deferred until open questions answered"). A
  serial dequeue-execute loop directly calling `run_action()` satisfies
  the Acceptance Criteria ("entry status/result reflect actual execution
  outcomes") with far less code; bounded concurrency can be layered on
  later without a persistence-format change.
- **Q2 (compat)**: `FEAT-2618`/`FEAT-2619`/`ENH-2617` recently shipped
  `ll-loop queue list`/`remove` against the existing
  `.loops/.queue/*.json` liveness-marker format —
  `read_queue_entries()` (`cli/loop/_helpers.py:172-200`) and
  `_is_earliest_waiter()` are shared, tested
  (`test_cli_loop_queue.py`), and load-bearing for the FIFO fix in
  BUG-1281. Breaking this format regresses recently-completed work with
  no user-facing benefit. `ll-loop run --queue`'s marker-write/retry-loop
  behavior (`cli/loop/run.py:355-427`) stays as-is for FSM lock
  contention; the new `ll-queue` persistence is additive for non-FSM
  `ActionSpec` work, not a replacement.
- **Q3 (priority)**: `IssuePriorityQueue`
  (`parallel/priority_queue.py:22-259`) already implements P0>...>P5
  tiered ordering with FIFO-within-tier via `QueuedIssue.__lt__`
  (`parallel/types.py`) comparing `(priority, timestamp)`, and is proven
  and tested (`test_priority_queue.py`). Reusing the same ordering
  semantics keeps both queue implementations in this codebase
  consistent rather than introducing a second, different priority
  convention.
- **Q4 (results)**: `RunnerResult` (`runner_spec.py`) carries
  `stdout`/`stderr`/`exit_code`/`timed_out`/`error` — stdout/stderr can
  be arbitrarily large for CLI/skill dispatches. `.claude/CLAUDE.md`'s
  Automation Scratch Pad convention already mandates piping large
  command output to scratch files rather than inline data. Store
  `{id, action, enqueuedAt, priority, status, exit_code, error}` inline
  in the queue entry/row; write `stdout`/`stderr` to a per-entry-id
  artifact file referenced by path, mirroring the scratch-pad pattern
  rather than a flat inline-string field.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-18.

**Selected**: strict-serial execution (Q1) + compat shim (Q2) + numeric
priority reusing `IssuePriorityQueue` (Q3) + hybrid inline/scratch result
storage (Q4).

**Reasoning**: each resolution is the option with the strongest direct
codebase precedent — `IssuePriorityQueue`'s ordering model, the
already-shipped `ll-loop queue` liveness-marker compat surface, and the
scratch-pad convention for large command output — combined with the
project's stated preference (Scope Boundaries, CLAUDE.md "don't design
for hypothetical future requirements") to keep v1 minimal and avoid the
`ThreadPoolExecutor`/subprocess-lifecycle complexity `WorkerPool` carries
for a use case this issue doesn't yet require.

#### Scoring Summary

| Question | Consistency | Simplicity | Testability | Risk | Total |
|----------|-------------|------------|-------------|------|-------|
| Q1: serial vs. bounded concurrency | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |
| Q2: compat shim vs. breaking change | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Q3: numeric priority vs. FIFO | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Q4: hybrid vs. flat inline results | 3/3 | 2/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- Q1: `WorkerPool`/`ThreadPoolExecutor` precedent is real but adds
  process-lifecycle complexity out of scope for v1; a serial loop over
  `run_action()` is directly testable and matches the AC.
- Q2: `ll-loop queue list`/`remove` (FEAT-2618/2619/ENH-2617) are recent,
  tested, and load-bearing — breaking them has no offsetting benefit.
- Q3: `IssuePriorityQueue` is a direct, tested precedent for exactly this
  ordering need.
- Q4: `RunnerResult` fields can be large; CLAUDE.md's scratch-pad
  convention is the established pattern for exactly this case.

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

**Open (unblocked — ENH-2668 done, open questions resolved)** | Created: 2026-07-18 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 60/100 → LOW

### Outcome Risk Factors
- The persistence backend choice (sqlite `.ll/queue.db` vs a `.queue/*.json`
  directory) is still an open decision — resolve before implementing, since it
  drives the schema, the `read_queue_entries()` migration path, and every
  persistence-touching test. The four numbered Open Questions above resolved
  Q4 (inline vs scratch result storage) but not this separate backend choice.
- The new scheduler/persistence subsystem (dequeue-execute loop, priority
  ordering, worker) has no existing test coverage — deep per-site complexity
  combined with untested new code compounds implementation risk; write
  ordering/dequeue tests early.

## Session Log
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `a12bdb66-c732-4cfc-b1c4-63e2b67e0c3c.jsonl`
- `/ll:decide-issue` - 2026-07-18T20:59:43 - `91b41730-7f32-4c92-b9ee-2290157dd53c.jsonl`
- `/ll:refine-issue` - 2026-07-18T20:59:43 - `91b41730-7f32-4c92-b9ee-2290157dd53c.jsonl`
- `/ll:capture-issue` - 2026-07-18T00:00:00Z - filed from `thoughts/plans/2026-07-17-generic-ll-queue-design.md` Phase 2; blocked on ENH-2668 and four open design questions.
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-18
- **Reason**: Issue too large for single session (score 11/11, Very Large); own Scope Boundaries had already deferred this split until open questions were resolved, which they now are.

### Decomposed Into
- FEAT-2682: `ll-queue` persistence layer and `add`/`list`/`status`/`remove` commands
- FEAT-2683: `ll-queue run` — serial dequeue-and-execute worker loop
- FEAT-2684: `ll-loop run --queue` compat shim and `ll-loop queue` migration

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-18
- **Decomposed into**: FEAT-2682, FEAT-2683, FEAT-2684

Work for FEAT-2669 is now carried by its child issues; this parent was closed by rn-decompose.
