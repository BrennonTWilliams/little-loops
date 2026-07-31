---
id: FEAT-2930
title: '`ll-queue run --watch`: long-lived drainer so queued work starts without a
  manual run'
type: FEAT
status: done
priority: P2
captured_at: '2026-07-30T21:27:49Z'
completed_at: '2026-07-31T01:02:14Z'
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
learning_tests_required:
- psutil
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

- [x] `ll-queue run --watch` picks up an entry enqueued after it started.
- [x] `ll-queue run` without `--watch` behaves exactly as today (drain, exit 0),
      including its single-array `--json` output.
- [x] `--poll-interval` is honored; the default is documented in `--help`.
- [x] `SIGTERM` during an idle wait exits 0; no entry is left in `running`.
- [x] A first `SIGTERM` mid-entry lets that entry finish and records its real
      result; the drainer then exits 0 without claiming further work.
- [x] A second `SIGTERM` terminates the in-flight child process and marks the
      entry `failed`; the child is confirmed dead (no orphaned `ll-loop run`).
- [x] A `running` entry whose `owner_pid` is dead is returned to `pending` by a
      subsequently-started watcher, and then executes.
- [x] `ll-queue requeue <id>` returns a stranded `running` entry to `pending`.
- [x] The lost-claim path sleeps rather than spinning: with two drainers racing a
      single entry, the loser's poll count over a fixed interval is bounded by
      `--poll-interval`, not by CPU speed.
- [x] `--json` under `--watch` emits one NDJSON object per line per processed
      entry, flushed per entry (assert on a piped, non-TTY stdout).
- [x] `python -m pytest scripts/tests/` exits 0.

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
  `claimed_at`/`owner_pid`; `claim_entry` populates both. Also hand-bump the
  `SCHEMA_VERSION` constant (`:98`, currently literal `1`, not derived from
  `len(_MIGRATIONS)`) to `2`. Decide whether `QueueEntry.to_dict()`/`_from_row()`
  (`:258-283`) should surface the two new columns — that's the single choke
  point `ll-queue status --json`/`list --json` go through, so it's the natural
  place for `_reclaim_stale`/`requeue` output to report `owner_pid`. Also decide
  whether `update_entry_result` (`:373-389`) should null `owner_pid` on a
  `done`/`failed` write (data hygiene, not correctness — `_reclaim_stale`'s
  `WHERE status = 'running'` filter already excludes completed entries either
  way).
- `scripts/pyproject.toml` — move `psutil` from `[project.optional-dependencies].dev`
  (`:125-127`, currently justified only by pytest-xdist core detection) to
  `[project].dependencies` (`:40-52`), with a **new** inline justification
  comment for `_reclaim_stale`'s PID-liveness identity check — the existing
  dev-extras comment's rationale (xdist) doesn't apply at the new location, and
  `.claude/CLAUDE.md`'s dependency policy requires a pin-adjacent justification.
  Note this also fixes a pre-existing latent gap: `cli/loop/queue.py:17` already
  imports `psutil` unconditionally at module scope despite it being declared
  dev-only today, so a bare `pip install little-loops` already risks an
  `ImportError` on that code path.
- `scripts/tests/` — new coverage for watch pickup, both signal stages, stale
  reclaim, requeue, and the busy-spin regression (see Tests subsection below for
  concrete patterns to follow)

### Documentation
- `.claude/CLAUDE.md` § CLI Tools — the `ll-queue` entry describes `run` as
  serially dequeuing pending entries; extend to mention `--watch`,
  `--poll-interval`, the NDJSON streaming departure, and `requeue`
- `docs/reference/API.md` — `queue_store` schema gains two columns. Two distinct
  restatements need updating, not one: the module-index one-liner (`:81`,
  `"schema {id, action, enqueuedAt, priority, status, result}"`) and the fuller
  prose description.
- `docs/reference/CLI.md` § `### ll-queue` (`:2772-2837`) — _Wiring pass added
  by `/ll:wire-issue`:_ not in the original Integration Map, but this is the
  fullest existing prose description of `run`'s one-shot semantics:
  - Subcommand table (`:2778-2784`) needs a `requeue ID [--force]` row.
  - `run` flags table (`:2823-2825`, currently only `--json`) needs
    `--watch`/`--poll-interval` rows, plus a note that `--json` under `--watch`
    is NDJSON — a deliberate departure from this file's own stated house
    convention.
  - The `run` prose paragraph (`:2821`) states dispatch semantics but nothing
    about blocking/exit — needs the one-shot-vs-watch distinction.
  - Examples block (`:2827-2837`, ends with `ll-queue run  # Execute all
    pending entries serially`) — add a `--watch` example and a `requeue`
    example.
- `docs/ARCHITECTURE.md` § "Queue DB (ll-queue)" (`:843-851`) — _Wiring pass
  added by `/ll:wire-issue`:_ the `queue_entries` schema table row (`:849`,
  hand-written prose `id, action (JSON ActionSpec), enqueued_at, priority,
  status, result`) will drift the moment the migration lands; add
  `claimed_at`/`owner_pid`. The paragraph at `:851` narrating `claim_entry`'s
  transaction ("performs the `pending` -> `running` acquisition") should
  mention it now also stamps ownership — it's the closest thing to a written
  contract for that function beyond its docstring. Also check the nearby prose
  describing the lost-claim path ("a lost claim advances to the next pending
  candidate rather than dispatching or breaking the drain loop") for staleness
  once the poll-sleep is added there.
- `commands/help.md:299` — _Wiring pass added by `/ll:wire-issue`:_ the
  `ll-queue` catalog one-liner ("Persisted work-item queue: add/list/status/
  remove/run commands (FEAT-2682, FEAT-2683)") needs `requeue` added to stay in
  sync with the actual subcommand set.

### Tests

_Wiring pass added by `/ll:wire-issue`:_ concrete patterns confirmed to exist
in the codebase for each new testable surface (all currently unexercised for
`cli/queue.py`/`queue_store.py`):
- **Migration test** — new class in `test_queue_store.py` (no
  migration-specific test class exists there today), modeled on
  `test_session_store_schema.py:679-702`'s `test_v8_to_v9_migration`: replay
  `_MIGRATIONS[:N-1]`, hand-stamp the prior `schema_version` via `INSERT OR
  IGNORE INTO meta`, call `ensure_db()`, assert the new columns exist and
  `schema_version` advanced.
- **Watch-loop sleep-poll test** — no existing precedent for a
  drain-then-poll-forever loop specifically, but `_cmd_tail` in
  `cli/logs.py:725-754` (an unbounded `while True` + `time.sleep(0.1)`, same
  shape) is tested in `test_ll_logs.py` `TestTail` by patching
  `little_loops.cli.logs.time.sleep` with a `side_effect` that raises after N
  calls (`:678`) rather than trying to interrupt a truly infinite loop. Apply
  the same technique to `little_loops.cli.queue.time.sleep`, or drive the
  `threading.Event` the Program Design already specifies for `_drain_once`.
- **Two-stage signal handler test** — model on `test_sprint.py:588-647`'s
  `_sprint_signal_handler` coverage: call the handler function directly with
  `signal.SIGINT`/`SIGTERM` and inspect the module-global flag / logger output
  / `sys.exit` on the second call — not a subprocess-based test.
- **PID-liveness / `_reclaim_stale` test** — no existing "reclaim a stranded
  entry via PID-liveness sweep" test exists anywhere; model a new
  `TestReclaimStale` class on `test_cli_loop_queue.py:420-489`'s confirmed
  module-qualified mock targets — `patch("little_loops.cli.queue.psutil.Process",
  ...)` and `patch("little_loops.cli.queue.os.kill", ...)` (not `psutil.Process`
  directly), covering both an identity-unverifiable case (`side_effect`) and a
  genuine-identity case (`return_value` with `cmdline` set).
- **Process-group kill test** — model on `test_cli_loop_lifecycle.py:139-560+`'s
  `patch("little_loops.cli.loop.lifecycle.os.killpg", ...)` pattern for
  `_kill_with_timeout`/`_signal_process_group`; new test needs
  `patch("little_loops.cli.queue.os.killpg", ...)` asserting SIGTERM-then-
  escalation and `ProcessLookupError`/`PermissionError` swallowed.
- **NDJSON flush test — genuine gap, no precedent to copy**: no existing test
  in the codebase mocks `sys.stdout.isatty()` or asserts `flush=True` was
  honored per-line on piped non-TTY stdout. `_emit()`
  (`cli/action.py:170-171`) is the implementation model but has no flush-
  assertion test of its own to copy. Needs either a real subprocess with
  `subprocess.PIPE` stdout, or `patch("sys.stdout")` with a `MagicMock` to
  assert `.flush()` was called after each `print()`.
- **`requeue` dispatch test** — add a case to `test_cli_queue.py`'s
  `main_queue` dispatch tests (`TestCmdRemove`-adjacent, `:364-410`), following
  the existing `remove` dispatch shape.
- **Non-breaking confirmation**: `TestCmdRunClaimContention.test_run_skips_already_claimed_entry`
  (`test_cli_queue_run.py:195-217`) and `TestEnsureDb`
  (`test_queue_store.py:51-66`) should keep passing unmodified — neither
  asserts the literal `queue_entries` column set or lost-claim timing. A new
  test exercising the actual lost-claim retry-and-succeed path needs
  `patch("little_loops.cli.queue.time.sleep")` to stay fast once the busy-spin
  fix lands there.
- **`claim_entry`'s sole caller is confirmed as `cli/queue.py:381`** (plus the
  direct-call test) — no other module imports it, so its signature/behavior
  change from populating `claimed_at`/`owner_pid` needs no update elsewhere.
- `ll-verify-kinds` (`cli/verify_kinds.py:31-40`) is hardcoded to
  `session_store._MIGRATIONS`/`_KIND_TABLE` only and does not walk
  `queue_store._MIGRATIONS` — no gate needs updating, and none exists to catch
  a malformed migration here either (non-finding, stated so no implementer
  assumes this gate provides coverage).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current anchors (line numbers drift-corrected as of this research pass):**
- `cmd_run` — `scripts/little_loops/cli/queue.py:361-429` (not `:316`; the drain
  `while True:` loop is at line 376, `if not pending: break` at 378-379).
- Lost-claim path — `scripts/little_loops/cli/queue.py:383-386` (not `:~342`).
- `_run_loop_entry`'s `subprocess.run(...)` call — `scripts/little_loops/cli/queue.py:344`
  (not `:280`); it does **not** pass `start_new_session=True` today, unlike
  every other subprocess launch site in the codebase (`runner_spec.py:214`,
  `mcp_call.py:211`, `fsm/runners.py:238`, `subprocess_utils.py:426`) —
  confirms Implementation Step 4 is adding something genuinely absent here,
  not toggling an existing flag.
- `run` subparser (single `--json` flag today, no `--watch`/`--poll-interval`)
  — `scripts/little_loops/cli/queue.py:527-533`.
- `main_queue` dispatch chain (`if/elif` on `parsed.command`) —
  `scripts/little_loops/cli/queue.py:432-549`; a new `requeue` subcommand
  slots in alongside `remove` (`:513-525`), following its
  `_not_found_or_ambiguous`/`resolve_entry` shape.

**PID-liveness reuse — one nuance the issue's Stale-entry reclaim section
doesn't call out:** there are two distinct existing primitives, not one:
- `_process_alive(pid)` — `scripts/little_loops/fsm/concurrency.py:56-68` —
  bare `os.kill(pid, 0)` liveness only, no psutil. Already imported
  cross-module (`cli/loop/queue.py:21`), so cross-module reuse has precedent.
- `_verify_queue_pid_identity(pid, entry)` —
  `scripts/little_loops/cli/loop/queue.py:88-113` — the psutil-based
  *identity* check (confirms the live PID is genuinely an `ll-loop` process,
  not just alive) that "the pattern `_reclaim_stale` should reuse" refers to.
  It is private to `cli/loop/queue.py` and matches on `"ll-loop" in cmdline or
  "little_loops.cli.loop" in cmdline` — reuse requires either (a) promoting a
  shared copy parameterized by marker string (`"ll-queue"` /
  `"little_loops.cli.queue"` for this issue), or (b) a small duplicate.
  Recommend (a) to avoid near-identical duplicated logic across the two
  queue implementations.
- **Dependency note**: `psutil` is declared only under `[dev]` extras in
  `scripts/pyproject.toml`, not `[project] dependencies`, yet
  `cli/loop/queue.py` already imports it unconditionally at module scope — a
  de facto runtime dependency today. `_reclaim_stale` extending that use
  doesn't introduce a new question, but formalizing the pin under
  `[project] dependencies` (with the inline justification comment
  `.claude/CLAUDE.md`'s dependency policy requires) is in scope for
  correctness even though Implementation Steps doesn't list it.

**Signal-handling precedent — `_loop_signal_handler` is explicitly unsafe for
this reuse:** `cmd_run`'s own docstring already notes
`register_loop_signal_handlers`/`_loop_signal_handler`
(`cli/loop/_helpers.py:121-244`) is unsafe to invoke repeatedly within one
`ll-queue run` process (module-global state). Better-fitting precedents for
the two pieces this issue needs:
- Two-stage *signal-handler flag* shape (first signal sets a flag and logs,
  second signal exits): `_sprint_signal_handler` in
  `scripts/little_loops/cli/sprint/run.py:108-127`, wired via
  `signal.signal(SIGINT/SIGTERM, ...)` at `:343-344`.
- Proper setup/handler/restore triad (preserves and restores the original
  handler on exit): `parallel/orchestrator.py`'s
  `_setup_signal_handlers`/`_signal_handler`/`_restore_signal_handlers`
  (`:233-243`, `:676-681`).
- Two-stage **child-kill escalation** via process group (SIGTERM, wait, then
  SIGKILL) — the closest precedent for "forward SIGTERM to the child on the
  second signal": `_kill_with_timeout`/`_signal_process_group` in
  `scripts/little_loops/cli/loop/lifecycle.py:88-128`, using
  `os.getpgid`/`os.killpg` (falls back to single-PID `os.kill`). This already
  assumes `start_new_session=True` (session leader, `PGID == PID`) — exactly
  the launch mode Implementation Step 4 specifies — making it a closer model
  than `parallel/worker_pool.py`'s simpler terminate/wait/kill (`:241-249`).

**NDJSON precedent — a concrete existing implementation to follow:** `_emit()`
in `scripts/little_loops/cli/action.py:170-171`
(`print(json.dumps(event), flush=True)`, no `indent=`) is the closest
existing NDJSON emitter in the codebase. `cli/messages.py:234-236/260-262/283-285`
is a second, `--stdout`-flag-gated precedent (per-record `print(json.dumps(...))`,
no explicit `flush=True`). Recommend modeling `--watch --json` directly on
`_emit()`'s shape.

**Migration test precedent:** `queue_store.py` has no migration-specific test
class today (`test_queue_store.py`'s `TestEnsureDb`, lines 51-60, only covers
create/idempotent). `scripts/tests/test_session_store_schema.py`'s
`test_v8_to_v9_migration`-style tests (e.g. lines 679-702) — replay
`_MIGRATIONS[:N-1]`, hand-stamp the prior `schema_version`, call `ensure_db()`,
assert the new column/index exists and `schema_version` advanced — are the
pattern to follow for the new `claimed_at`/`owner_pid` migration test.

**Test mocking convention:** existing psutil/subprocess mocking in this test
family patches the *module-qualified* import path (e.g.
`little_loops.cli.loop.queue.psutil.Process`,
`little_loops.cli.loop.queue.os.kill`), not the library path directly.
`scripts/tests/test_cli_queue_run.py`'s `TestCmdRunLoopDispatch` (mocks
`little_loops.cli.queue.subprocess.run`) and `TestCmdRunClaimContention`
(`test_run_skips_already_claimed_entry`) are the direct existing precedents
to extend for the watch-pickup, signal-stage, and busy-spin-regression tests
— the busy-spin regression test likely wants
`patch("little_loops.cli.queue.time.sleep")` with a call-count/elapsed-time
assertion.

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
- `/ll:manage-issue` - 2026-07-31T01:01:26Z - `ac46b638-cc76-4783-9d30-43fe42c3223f.jsonl`
- `/ll:ready-issue` - 2026-07-31T00:32:59 - `321fe859-f6e6-4283-a6bc-c7014269623d.jsonl`
- `/ll:confidence-check` - 2026-07-31T00:31:02Z - `16d96c23-32fa-49ec-ab21-23083dc4339d.jsonl`
- `/ll:wire-issue` - 2026-07-31T00:28:04 - `7dfa71ff-fe70-45e9-8f8d-d2cbacf58017.jsonl`
- `/ll:refine-issue` - 2026-07-31T00:22:00 - `d82db468-8c38-4808-83e2-a20eea418eca.jsonl`
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`
- Pre-implementation review - 2026-07-30 - BUG-2929 and BUG-2928 both verified `done`; dropped the stale `depends_on` (unblocked). Added three requirements the original deferred or left open: decided two-stage signal semantics (the `LOOP` child is an unbounded `subprocess.run` that does not inherit the parent's `SIGTERM`); `claimed_at`/`owner_pid` columns plus PID-liveness reclaim and `ll-queue requeue`, since a daemon makes stranded-`running` the normal failure mode and the schema records no owner; and the poll sleep on `cmd_run`'s existing lost-claim `continue`, which becomes a hot loop once two drainers can coexist. Specified `--json` as NDJSON explicitly. Sequenced after ENH-2931. Effort/risk revised up to Medium.

## Status

**Open** | Created: 2026-07-30 | Priority: P2
