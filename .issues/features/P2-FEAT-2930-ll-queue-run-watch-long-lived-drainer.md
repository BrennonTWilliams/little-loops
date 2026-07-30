---
id: FEAT-2930
title: "`ll-queue run --watch`: long-lived drainer so queued work starts without a manual run"
type: FEAT
status: open
priority: P2
captured_at: '2026-07-30T21:27:49Z'
discovered_date: 2026-07-30
discovered_by: capture-issue
depends_on:
- BUG-2929
relates_to:
- FEAT-2683
- FEAT-2669
- BUG-2928
labels:
- queue
- cli
- scheduling
---

# FEAT-2930: `ll-queue run --watch` — long-lived drainer

## Summary

Add a `--watch` mode to `ll-queue run` that blocks on an empty queue instead of
exiting, so entries enqueued later are picked up automatically. Start it once
per project; it owns `.ll/queue.db` and drains everything that lands in it.

## Motivation

`ll-queue run` today is a one-shot: it drains whatever is pending at invocation
time and exits. That means every batch of queued work requires a human to
remember to run the drainer, which substantially undercuts the value of having a
persisted queue at all — you can enqueue four `autodev` runs behind a foreground
one, walk away, and come back to four entries still sitting in `pending`.

FEAT-2683 anticipated this: its Expected Behavior says "`ll-queue run` (or a
long-running worker mode)", but the delivered v1 was strictly the one-shot, with
longer-running and concurrent modes "explicitly deferred to a future issue if
needed." This is that issue.

## Current Behavior

`cmd_run` (`cli/queue.py:274`) loops until no `pending` entry remains, then
returns. Once it exits, `.ll/queue.db` has no reader — nothing in the codebase
references `queue_store` outside `cli/queue.py` itself, so entries added
afterward sit in `pending` indefinitely until a human invokes `ll-queue run`
again. Observed live: four `autodev` entries enqueued behind a foreground run
were all still `pending` after that run completed.

## Use Case

An operator queues several loop runs behind work already in progress:

```bash
ll-queue run --watch &                      # started once, stays up
ll-queue add autodev --runner loop --input "ENH-2924"
ll-queue add autodev --runner loop --input "ENH-2925"
```

Each entry begins as soon as the drainer is free, in priority/FIFO order, with
no further operator action.

## Expected Behavior

- `ll-queue run --watch` drains pending entries exactly as the one-shot does,
  then waits rather than exiting.
- New entries added while it waits are picked up on the next poll.
- Without `--watch`, behavior is unchanged: drain what's pending, then exit.
- `SIGINT`/`SIGTERM` shuts down cleanly — the in-flight entry is allowed to
  finish or is marked `failed` with a clear error, never left stranded in
  `running`.
- Poll interval is configurable via `--poll-interval` (default on the order of a
  few seconds); the mechanism is a sleep-poll, not a busy loop.

## API/Interface

```
ll-queue run [--json] [--watch] [--poll-interval SECONDS]
```

`--json` composes with `--watch` by streaming one JSON object per processed
entry rather than accumulating a single array, since a watcher never reaches a
natural end-of-list.

## Program Design

### Signatures

- `cmd_run(args: argparse.Namespace) -> int`

  Existing handler; gains the watch branch.

- `_drain_once(json_mode: bool) -> list[dict[str, Any]]`

  The current `while True` body, extracted so both modes share one dispatch path.

### Call Path

`cmd_run` -> `_drain_once` (repeat under `--watch`, sleeping between passes)
-> `claim_entry` (BUG-2929) -> `_run_loop_entry` | `run_action`
-> `update_entry_result`

## Implementation Steps

1. Extract the existing drain body from `cmd_run` into `_drain_once`.
2. Add `--watch` / `--poll-interval` to the `run` subparser.
3. Wrap `_drain_once` in a sleep-poll loop under `--watch`, with signal handling
   for clean shutdown.
4. Adjust `--json` output to stream per-entry under `--watch`.
5. Tests for watch pickup, clean shutdown, and unchanged one-shot behavior.

## Acceptance Criteria

- [ ] `ll-queue run --watch` picks up an entry enqueued after it started.
- [ ] `ll-queue run` without `--watch` behaves exactly as today (drain, exit 0).
- [ ] `--poll-interval` is honored; the default is documented in `--help`.
- [ ] `SIGTERM` during an idle wait exits 0; no entry is left in `running`.
- [ ] `--json` under `--watch` emits one object per processed entry.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: the watch loop, poll interval, signal handling, streaming JSON.
- **Out**: bounded-concurrency execution (still deferred — `--watch` remains a
  single serial drainer, just a persistent one); the atomic claim primitive
  (BUG-2929, a dependency); waking the drainer from an FSM `loop_complete` event
  (a latency optimization on top of this, deliberately not captured yet);
  process supervision / auto-start on boot.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` — `cmd_run` split, `run` subparser flags
- `scripts/tests/` — new coverage for watch pickup and shutdown

### Dependent Files
- `scripts/little_loops/queue_store.py` — supplies `claim_entry` via BUG-2929

### Documentation
- `.claude/CLAUDE.md` § CLI Tools — the `ll-queue` entry describes `run` as
  serially dequeuing pending entries; extend to mention `--watch`

### Related
- **BUG-2929** (dependency) — atomic claim; without it a second drainer started
  alongside a watcher double-executes
- **BUG-2928** — LOOP entries die at the 120s subprocess timeout; a watcher is
  of little use until that lands, since the most valuable target type can't
  complete
- **FEAT-2683** — the one-shot worker this extends
- **FEAT-2684** — `ll-loop queue` PID-liveness compat shim, a separate mechanism

## Impact

Turns the persisted queue from something you must remember to service into
something that services itself. Directly addresses the observed failure: four
`autodev` entries enqueued behind a foreground run sat `pending` indefinitely
because nothing drains the store automatically.

**Effort**: Small-to-medium — the drain logic already exists; this is extraction
plus a poll loop and signal handling. **Risk**: Low-medium — a long-lived
process introduces shutdown and stranded-entry edge cases that the one-shot
never had; mitigated by BUG-2929's atomic claim and explicit signal tests.

## Session Log
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`

## Status

**Open** | Created: 2026-07-30 | Priority: P2
