---
id: FEAT-2930
title: "`ll-queue run --watch`: long-lived drainer so queued work starts without a manual run"
type: FEAT
status: open
priority: P2
captured_at: '2026-07-30T21:27:49Z'
discovered_date: 2026-07-30
discovered_by: capture-issue
relates_to:
- BUG-2929
- BUG-2928
- FEAT-2683
- FEAT-2669
- ENH-2931
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

`cmd_run` (`cli/queue.py:316`) loops until no `pending` entry remains, then
returns. Once it exits, `.ll/queue.db` has no reader — nothing in the codebase
references `queue_store` outside `cli/queue.py` itself, so entries added
afterward sit in `pending` indefinitely until a human invokes `ll-queue run`
again. Observed live: four `autodev` entries enqueued behind a foreground run
were all still `pending` after that run completed.

### Dependency status

Both prerequisites are now **`done`** — this issue is unblocked:

- **BUG-2929** — `claim_entry` exists (`queue_store.py:392`) and is correct:
  `BEGIN IMMEDIATE` with `UPDATE ... WHERE id = ? AND status = 'pending'`,
  returning `rowcount > 0`. Concurrent drainers cannot double-execute an entry.
- **BUG-2928** — `LOOP` entries no longer carry the 120s default; the subprocess
  timeout is unbounded for that runner kind. This has a consequence for `--watch`
  (see "Stuck entries" below) that the one-shot never had.

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
- Poll interval is configurable via `--poll-interval` (default on the order of a
  few seconds); the mechanism is a sleep-poll, not a busy loop.
- Shutdown and crash-recovery semantics are as specified below. No entry is left
  stranded in `running` with no owner — not on signal, and not after a hard kill.

### Shutdown semantics (decision, not an open choice)

The original phrasing — "the in-flight entry is allowed to finish **or** is
marked `failed`" — left the important case undecided. The harder problem is that
`LOOP` entries dispatch via `subprocess.run(...)` (`cli/queue.py:280`) with
`timeout=None` post-BUG-2928, and a `SIGTERM` delivered to the drainer does
**not** propagate to that child (no process group is established). So "shut down
cleanly" mid-entry has no default behavior at all today. Specify:

- **First `SIGINT`/`SIGTERM`**: set a stop flag, log "finishing current entry,
  will exit", let the in-flight entry run to completion, write its real result,
  then exit 0 without claiming anything further. Graceful drain.
- **Second signal**: forward `SIGTERM` to the in-flight child process, mark the
  entry `failed` with `error: "interrupted by operator"`, exit 0. Immediate stop.
- **Idle wait**: either signal exits 0 immediately; nothing is in `running`.

Start the child in its own process group (`start_new_session=True`) so the
forward is a targeted `os.killpg` rather than a signal the child may already
have inherited.

### Stale-entry reclaim (new requirement)

`queue_entries` (`queue_store.py:106`) is `{id, action, enqueued_at, priority,
status, result}` — no `claimed_at`, no `owner_pid`, no heartbeat. `claim_entry`
flips `pending` → `running` and records nothing about who claimed it. If the
drainer is `SIGKILL`ed, OOM-killed, or the machine reboots, that entry stays
`running` forever, and the subcommand set (`add`/`list`/`status`/`remove`/`run`)
offers no way back — there is no `requeue`/`reset`, only `remove`.

With a one-shot drainer this was a rare event a human was present to witness.
A long-lived drainer makes it the *normal* failure mode, so it has to be handled
here rather than deferred:

- Add `claimed_at TEXT` and `owner_pid INTEGER` columns via a new entry in
  `queue_store._MIGRATIONS` (nullable; existing rows unaffected). `claim_entry`
  populates both inside its existing `BEGIN IMMEDIATE` transaction.
- On watcher startup and on each idle poll, sweep `running` entries whose
  `owner_pid` is not alive and return them to `pending`. Use the same
  `psutil`-with-identity-check liveness approach `ll-loop queue` already applies
  to its PID marker files (FEAT-2684) — a bare `os.kill(pid, 0)` will resurrect
  work under a recycled PID.
- Add `ll-queue requeue <id> [--force]` as the manual escape hatch for the case
  the sweep can't decide (owner still alive but wedged). Without it an operator's
  only recourse for a stranded entry is `remove`, which loses the work item.

### Stuck entries are now silent

BUG-2928 removed the `LOOP` subprocess timeout, which was correct for the
one-shot case. Combined with `--watch`, a wedged `ll-loop run` blocks the queue
indefinitely with no signal to the operator. ENH-2931's elapsed-time column on
`ll-queue list` is the visibility mechanism; this issue does not add a timeout
back, but it does depend on that column existing to be operable. Land ENH-2931
first (see Sequencing).

## API/Interface

```
ll-queue run [--json] [--watch] [--poll-interval SECONDS]
ll-queue requeue <id> [--force]
```

Under `--watch`, `--json` emits **NDJSON**: one compact JSON object per line,
one line per processed entry, `stdout` flushed after each. It does not emit the
one-shot's single accumulated array, since a watcher never reaches a natural
end-of-list. State this explicitly in `--help` — every other `--json` in the CLI
is a one-shot `print_json(...)` document, so a per-entry stream is a deliberate
departure from the house convention and consumers must not expect a single
parseable document. Without `--watch`, `--json` is unchanged (single array).

## Program Design

### Signatures

- `cmd_run(args: argparse.Namespace) -> int`

  Existing handler; gains the watch branch.

- `_drain_once(json_mode: bool, stop: threading.Event) -> list[dict[str, Any]]`

  The current `while True` body, extracted so both modes share one dispatch
  path. Checks *stop* before each claim so a graceful shutdown stops claiming
  new work without interrupting the current entry.

- `_reclaim_stale(db_path) -> int`

  Returns `running` entries whose `owner_pid` is dead to `pending`; returns the
  count reclaimed.

- `cmd_requeue(args: argparse.Namespace) -> int`

### Call Path

`cmd_run` -> `_reclaim_stale` -> `_drain_once` (repeat under `--watch`, sleeping
between passes) -> `claim_entry` (BUG-2929) -> `_run_loop_entry` | `run_action`
-> `update_entry_result`

### Fix the existing busy-spin on the way through

`cmd_run`'s current lost-claim path (`cli/queue.py:~342`) does a bare `continue`
with no sleep when every pending entry was claimed by another drainer. Today
that path is near-unreachable — there is normally only one drainer. Under
`--watch` it becomes routine (two watchers, or a watcher racing a manual
`ll-queue run`), and a bare `continue` is then a hot loop hammering SQLite. The
poll sleep must cover that path, not only the empty-queue path.

## Implementation Steps

1. Add the `claimed_at`/`owner_pid` migration to `queue_store._MIGRATIONS`;
   populate both in `claim_entry`'s existing transaction.
2. Extract the existing drain body from `cmd_run` into `_drain_once`, taking a
   stop event; apply the poll sleep to the lost-claim `continue` path.
3. Add `--watch` / `--poll-interval` to the `run` subparser.
4. Wrap `_drain_once` in a sleep-poll loop under `--watch`, with the two-stage
   signal handling above and `start_new_session=True` on the `LOOP` subprocess.
5. Implement `_reclaim_stale` (startup + each idle poll) and `ll-queue requeue`.
6. Switch `--json` under `--watch` to per-line NDJSON with an explicit flush.
7. Tests: watch pickup, both signal stages, stale reclaim, requeue, busy-spin
   regression, and unchanged one-shot behavior.

## Acceptance Criteria

- [ ] `ll-queue run --watch` picks up an entry enqueued after it started.
- [ ] `ll-queue run` without `--watch` behaves exactly as today (drain, exit 0),
      including its single-array `--json` output.
- [ ] `--poll-interval` is honored; the default is documented in `--help`.
- [ ] `SIGTERM` during an idle wait exits 0; no entry is left in `running`.
- [ ] A first `SIGTERM` mid-entry lets that entry finish and records its real
      result; the drainer then exits 0 without claiming further work.
- [ ] A second `SIGTERM` terminates the in-flight child process and marks the
      entry `failed`; the child is confirmed dead (no orphaned `ll-loop run`).
- [ ] A `running` entry whose `owner_pid` is dead is returned to `pending` by a
      subsequently-started watcher, and then executes.
- [ ] `ll-queue requeue <id>` returns a stranded `running` entry to `pending`.
- [ ] The lost-claim path sleeps rather than spinning: with two drainers racing a
      single entry, the loser's poll count over a fixed interval is bounded by
      `--poll-interval`, not by CPU speed.
- [ ] `--json` under `--watch` emits one NDJSON object per line per processed
      entry, flushed per entry (assert on a piped, non-TTY stdout).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: the watch loop, poll interval, two-stage signal handling, NDJSON
  streaming, the `claimed_at`/`owner_pid` columns, stale-entry reclaim,
  `ll-queue requeue`, the lost-claim busy-spin fix.
- **Out**: bounded-concurrency execution (still deferred — `--watch` remains a
  single serial drainer, just a persistent one); a single-instance lockfile (see
  below); reinstating a `LOOP` timeout (BUG-2928 removed it deliberately;
  visibility comes from ENH-2931 instead); waking the drainer from an FSM
  `loop_complete` event (a latency optimization on top of this, deliberately not
  captured yet); process supervision / auto-start on boot.

### On a single-instance guard

Deliberately **out of scope**, stated explicitly rather than left silent.
Correctness under multiple concurrent watchers is already guaranteed by
`claim_entry`'s atomic transition — a second watcher wastes polls but cannot
double-execute an entry. A lockfile would be a convenience (a clear "already
running" error instead of silent duplication), not a correctness requirement,
and it interacts awkwardly with the stale-reclaim sweep. Revisit if operators
actually start watchers by accident.

## Sequencing

Implement **after ENH-2931**, despite this issue's P2 against that one's P4.
Both edit row rendering in `cli/queue.py`; ENH-2931 is ~30 lines with no
dependencies and produces the `_format_action_summary` helper this issue's
per-entry progress line should call instead of hand-building a third copy of the
`runner:target` format. ENH-2931's elapsed-time column is also the only
visibility an operator has into a wedged entry under a watcher.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` — `cmd_run` split, `run` subparser flags,
  signal handling, `_reclaim_stale`, `cmd_requeue`
- `scripts/little_loops/queue_store.py` — `_MIGRATIONS` entry for
  `claimed_at`/`owner_pid`; `claim_entry` populates both
- `scripts/tests/` — new coverage for watch pickup, both signal stages, stale
  reclaim, requeue, and the busy-spin regression

### Documentation
- `.claude/CLAUDE.md` § CLI Tools — the `ll-queue` entry describes `run` as
  serially dequeuing pending entries; extend to mention `--watch`,
  `--poll-interval`, the NDJSON streaming departure, and `requeue`
- `docs/reference/API.md` — `queue_store` schema gains two columns

### Related
- **BUG-2929** (`done`) — atomic claim, already landed; without it a second
  drainer started alongside a watcher would double-execute
- **BUG-2928** (`done`) — removed the 120s `LOOP` subprocess timeout, already
  landed. Note the direction reversed: it is no longer a blocker but a source of
  a new requirement, since an unbounded `LOOP` entry can now wedge a watcher
  silently
- **ENH-2931** — `ll-queue list` args/timeout/elapsed rendering; implement first
  (see Sequencing), and the source of the `_format_action_summary` helper
- **FEAT-2683** — the one-shot worker this extends
- **FEAT-2684** — `ll-loop queue` PID-liveness compat shim; a separate mechanism,
  but its `psutil` identity-checked liveness test is the pattern `_reclaim_stale`
  should reuse rather than reinvent

## Impact

Turns the persisted queue from something you must remember to service into
something that services itself. Directly addresses the observed failure: four
`autodev` entries enqueued behind a foreground run sat `pending` indefinitely
because nothing drains the store automatically.

**Effort**: Medium — revised up from small-to-medium. The drain loop itself is
extraction plus a sleep, but the durability work (schema migration, PID-liveness
reclaim, `requeue`) and two-stage signal handling with child-process forwarding
are each their own testable surface. **Risk**: Medium — a long-lived process
turns shutdown and stranded-entry edge cases from rare into routine, and the
`LOOP` child is an unbounded subprocess that does not receive the parent's
signals by default. Mitigated by BUG-2929's atomic claim (already landed), the
`owner_pid` reclaim sweep, and explicit tests for both signal stages.

## Session Log
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`
- Pre-implementation review - 2026-07-30 - BUG-2929 and BUG-2928 both verified `done`; dropped the stale `depends_on` (unblocked). Added three requirements the original deferred or left open: decided two-stage signal semantics (the `LOOP` child is an unbounded `subprocess.run` that does not inherit the parent's `SIGTERM`); `claimed_at`/`owner_pid` columns plus PID-liveness reclaim and `ll-queue requeue`, since a daemon makes stranded-`running` the normal failure mode and the schema records no owner; and the poll sleep on `cmd_run`'s existing lost-claim `continue`, which becomes a hot loop once two drainers can coexist. Specified `--json` as NDJSON explicitly. Sequenced after ENH-2931. Effort/risk revised up to Medium.

## Status

**Open** | Created: 2026-07-30 | Priority: P2
