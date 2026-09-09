---
id: ENH-3416
title: Add attempt budget, backoff, and dead-lettering to ll-queue
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
labels:
- queue
- reliability
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
missing_artifacts: false
decision_needed: false
---

## Summary

`ll-queue`'s only unbounded retry is the owner-death reclaim. `_reclaim_stale`
(`scripts/little_loops/cli/queue.py:542`) runs on watcher startup and every idle
poll and returns any `running` entry whose `owner_pid` is not verifiably alive
to `pending` via `reset_to_pending` (`scripts/little_loops/queue_store.py:417`),
with no attempt counter anywhere on `QueueEntry`. An entry that reliably kills
its own drainer (OOM of the drainer process, a SIGKILL mid-dispatch) is
therefore reclaimed and re-dispatched forever, and a long-lived `--watch`
drainer makes that the normal case rather than a rare one someone is present to
witness.

Every *other* failure is the opposite problem: a nonzero exit, a raised
exception, or a timeout lands on terminal `failed` on the first attempt
(`cli/queue.py:481-496`) and is never retried, even when the cause is a 429 or a
dropped connection that would succeed a minute later.

This issue adds: an `attempt` counter incremented at claim time so it survives
a dead drainer; bounded exponential backoff via a `next_attempt_at` the claim
path honors; a terminal `dead_letter` status carrying the last error, reached
when a *retryable* failure exhausts the budget or an owner dies too many times;
retryability classified by reusing the existing `classify_failure()` text
classifier rather than exit codes, filtered to an explicit allowlist of its
`reason` strings; and an explicit `cancel` verb with a reason.
`requeue` keeps its meaning (manual return to `pending`) and is widened to
revive `dead_letter`/`failed`/`cancelled` entries with a fresh budget.

## Current Behavior

- `QueueEntry` (`queue_store.py:267`) has exactly: `id`, `action`,
  `enqueued_at`, `priority`, `status`, `result`, `claimed_at`, `owner_pid`. No
  attempt counter, no `next_attempt_at`, no reason field. `enqueued_at` is set
  once in `add_entry()` and never mutated.
- `reset_to_pending` (`queue_store.py:417`) is one SQL statement
  (`UPDATE ... SET status='pending', claimed_at=NULL, owner_pid=NULL WHERE id=?
  AND status='running'`) shared by `_reclaim_stale`, `cmd_requeue`
  (`cli/queue.py:686`), and the MCP `queue_requeue` tool
  (`mcp_server/tools.py:644`). Nothing records that the entry has been
  reclaimed before.
- `claim_entry` (`queue_store.py:466`) claims any `pending` row unconditionally
  inside `BEGIN IMMEDIATE` (BUG-2929). No time-gated eligibility exists.
- `_drain_once` (`cli/queue.py:434`) maps the dispatch result to `done` iff
  `exit_code == 0 and not timed_out and error is None`, otherwise `failed`, and
  writes it via `update_entry_result`. A raised exception is also `failed`.
  There is no retry of any kind on this path.
- `update_entry_result` (`queue_store.py:439`) has no status guard (`WHERE id
  = ?` only): whatever the row's status is when the dispatch finishes, the
  completion write overwrites it. Today this is a latent clobber (a
  misidentified-dead owner that later finishes overwrites the reclaim); an
  operator `cancel` verb would make it a first-class race.
- `_drain_once`'s `force_stop` branch (`cli/queue.py:498-501`) hand-sets
  `status = "failed"` with `error: "interrupted by operator"`, the closest
  existing analog to an operator cancel, but it lands on the same status as an
  ordinary failure.
- `cmd_requeue` accepts only `id`, `--force`, `--json`; acts only on `running`
  entries; there is no cancel verb.
- Statuses are ad hoc string literals. `_STATUS_COLOR` (`cli/queue.py:50-55`),
  the `queue_list` MCP tool description (`mcp_server/tools.py:838`),
  `docs/ARCHITECTURE.md:834`, and `docs/reference/CLI.md` each enumerate the
  set independently.
- No overflow, trimming, eviction, or max-size logic exists in
  `queue_store.py` or `cli/queue.py`.

## Expected Behavior

- `attempt` is incremented inside `claim_entry`'s UPDATE. A drainer that dies
  mid-dispatch leaves the incremented count behind, so the owner-death path
  consumes budget without any extra bookkeeping.
- After a failed dispatch, `_drain_once` classifies the failure with
  `classify_failure()` and the reason allowlist below. A retryable failure
  with budget remaining returns the entry to `pending` with
  `next_attempt_at = now + backoff(attempt)`, where `now` is the dispatch
  *completion* time, not `claimed_at`. A retryable failure with no budget
  remaining moves it to `dead_letter`. A non-retryable failure lands on
  `failed` on the first attempt, unchanged from today.
- Every post-dispatch write (`update_entry_result`, `schedule_retry`,
  `dead_letter_entry`, `cancel_entry`'s running branch) is guarded with
  `AND status = 'running'`. If the guard misses (rowcount 0), the entry was
  cancelled or reclaimed out from under the drainer; `_drain_once` re-reads
  the row and reports the *actual* status in its record rather than the one
  it tried to write.
- `_reclaim_stale` returns a dead-owner entry to `pending` with `enqueued_at`
  untouched (so it keeps its priority/FIFO position) when `attempt <
  QUEUE_MAX_ATTEMPTS`, and moves it to `dead_letter` with error
  `"attempt budget exhausted after N attempts; last: owner died"` otherwise
  (`attempt` is shared between transient failures and owner deaths, so the
  message must not claim N deaths). It never touches `next_attempt_at`; an
  owner death is not a backoff-eligible failure, it is a slot to refill.
- All "current time" reads in `queue_store.py` and `cli/queue.py` go through
  one `queue_store._utcnow() -> str` helper so tests patch a single seam
  instead of each call site's `datetime.now`.
- `claim_entry` and `_drain_once`'s pending filter honor `next_attempt_at`: a
  row with `next_attempt_at > now` is not eligible. One-shot `ll-queue run`
  drains what is eligible and exits, reporting how many entries are backing
  off. `--watch` picks them up on later polls.
- `ll-queue cancel <id> [--reason TEXT]` moves a `pending` or `running` entry
  to terminal `cancelled` with `result.reason`. Cancelling a `running` entry
  is a status-only mark: it does **not** kill the in-flight process. The
  drainer's guarded completion write then no-ops and the entry stays
  `cancelled`. The `force_stop` branch routes through the same function with
  reason `"interrupted by operator"` and passes the dispatch result
  (`exit_code`/`stdout`/`stderr`) as the extra dict so partial output is not
  lost, matching what the `failed` path preserves today.
- `ll-queue requeue <id>` keeps its running→pending meaning and additionally
  accepts `dead_letter`, `failed`, and `cancelled` entries, resetting `attempt`
  to 0 and clearing `next_attempt_at`. The prior `result` is preserved under
  `result.previous` rather than discarded.
- `ll-queue list` renders `attempt=N` in the summary suffix when `attempt > 0`
  and `retry in Xs` when `next_attempt_at` is in the future, so a backing-off
  entry is distinguishable from a fresh `pending` one.
- The `--watch` idle-poll report distinguishes reclaimed from dead-lettered
  entries (`Reclaimed N stale entries, dead-lettered M`).
- `enqueued_at` is never mutated by any path. Backoff yields via
  `next_attempt_at`; there is no "go to the back" semantic.
- The status set and terminal subset are declared once as frozensets in
  `queue_store.py` and every other enumeration derives from or is locked
  against them.

## Design Decisions

### Retryability classification (settled here; no external taxonomy issue exists)

Reuse `classify_failure(error_output, returncode)` from
`issue_lifecycle.py:159`, but gate on its returned **`reason` string**, not
on `FailureType` alone. The classifier was written for host-CLI stderr; a
queue entry's stderr is arbitrary program output (a whole `ll-loop run` log,
a pytest run), where its broad substrings (`"timeout"`, `"429"`,
`"overloaded"`, `"api error"`, `"context window"`) fire on unrelated text.
Mapping every `TRANSIENT` to retry would send a pytest run with
`test_timeout_x FAILED` in its output through five dispatches with backoff.

```python
QUEUE_RETRYABLE_REASONS = frozenset({
    "API quota or rate limit exceeded",
    "Network or connectivity error",
    "API server error",
    "Infra teardown: SIGTERM after result event",  # INFRA_RETRY
})
```

| `classify_failure` result | Queue outcome |
|---|---|
| `TRANSIENT`/`INFRA_RETRY` with `reason in QUEUE_RETRYABLE_REASONS` | retry with backoff; `dead_letter` on exhaustion |
| `TRANSIENT` with any other reason (`"Command timeout"`, `"Context window exhausted"`, `"CLI session continuation error"`, `"System resource error"`) | `failed`, no retry |
| `REAL` | `failed`, no retry |
| `NON_RECOVERABLE` | `failed`, no retry |

Inputs: `error_output = result.stderr or result.error or ""`, `returncode =
result.exit_code`. A raised exception (the `except Exception` branch) is
classified from `str(exc)` with `returncode=None → -1`.

`timed_out=True` is **non-retryable** regardless of text, checked explicitly
before classification. A command that hit its own timeout will hit it again
with identical input; per the principle below, that is not a retry. (Note:
SKILL/PROMPT/LOOP timeouts return empty stderr at `runner_spec.py:219,235,390`,
but `_run_cmd` returns the captured stderr with `timed_out=True` at
`runner_spec.py:343-345`, so the explicit check is required, not merely
defensive.)

**LOOP entries**: `ll-loop run` already retries 429/overload internally with
its own budget (`fsm/executor.py`), so a LOOP exit after exhausting that
budget must not be retried five more times by the queue. `_classify_dispatch`
treats `RunnerType.LOOP` with `error == "terminal failure"`
(`FAILURE_TERMINAL_EXIT_CODE`, `cli/queue.py:397`) as non-retryable; only a
LOOP failure to *launch* (`FileNotFoundError` → `exit_code=-1` at `:384`) or
a dead drainer consumes budget.

Principle (kept from the reference shape): a retry that cannot change the
input is not a retry. Only failures whose cause is outside the entry (quota,
network, infra teardown, drainer death) consume the budget.

### Policy constants (module constants, not config)

Declared in `queue_store.py`, each with a comment naming the failure it guards
against and the trade-off accepted:

```python
QUEUE_MAX_ATTEMPTS = 5        # bounds a poison entry to 5 dispatches / 4 reclaims
QUEUE_BACKOFF_BASE_S = 5      # 5, 10, 20, 40 s between attempts 1..4
QUEUE_BACKOFF_CEILING_S = 300 # worst-case wait bounded at 5 min
```

`backoff(attempt) = min(QUEUE_BACKOFF_BASE_S * 2 ** (attempt - 1),
QUEUE_BACKOFF_CEILING_S)`, non-jittered (see Decision Rationale). Not exposed
in `QueueConfig`/`config-schema.json` in this issue: doing so pulls in the
BUG-3192 schema/dataclass parity guards across three test files for no present
need. A follow-up can lift them into `queue` config if a project needs it.

### Status vocabulary

```python
QUEUE_STATUSES = frozenset({"pending", "running", "done", "failed", "dead_letter", "cancelled"})
QUEUE_TERMINAL_STATUSES = frozenset({"done", "failed", "dead_letter", "cancelled"})
```

`failed` = non-retryable on attempt 1. `dead_letter` = retryable but budget
exhausted (including owner death). `cancelled` = operator decision, with
reason. All three are terminal; all three are `requeue`-able.

### Removal guard

`remove` stays pending-only without `--force`; `dead_letter`/`cancelled` need
`--force` exactly as `failed` does today. The MCP `queue_remove` gate
(`mcp_server/tools.py:601`) is unchanged. Explicit no-op decision.

### Cancel vs. in-flight dispatch (status-guarded completion writes)

`cancel` on a `running` entry is allowed but does not signal the process;
killing arbitrary runner subprocesses from a second CLI process is out of
scope (only the drainer holds the `Popen`). To keep the operator's decision
from being overwritten when the dispatch finishes, every completion write
gains `AND status = 'running'`. `update_entry_result` keeps its signature and
gains the guard (its only callers are `_drain_once` and tests; a `done`/
`failed` write to a non-running row was never intended). On a guard miss
`_drain_once` re-reads the entry and records its real status. This also
closes today's latent clobber where a misidentified-dead owner that later
finishes overwrites the reclaim.

## Scope Boundaries

- **In scope**: `attempt`/`next_attempt_at` columns and migration; claim-time
  increment and SQL time gate; `compute_backoff_s` and the three policy
  constants; `QUEUE_RETRYABLE_REASONS`; `_utcnow` seam;
  `schedule_retry`/`dead_letter_entry`/`cancel_entry`/`revive_entry`;
  status-guarded completion writes; `_drain_once` classification branch;
  `_reclaim_stale` budget check; `ll-queue cancel`; widened `requeue`;
  `list` summary suffix for attempt/backoff; status frozensets and the three
  lock tests; docs and MCP description parity.
- **Out of scope: killing an in-flight process on `cancel`.** See the
  cancel-vs-dispatch decision above.
- **Out of scope**:

- **Overflow/trimming.** No size bound or eviction exists anywhere in the
  store; per-path trim rules were carried over from the reference shape's
  bounded in-memory buffer and do not apply to a persisted SQLite table. File
  separately if a size bound is ever wanted.
- **Consecutive-failure circuit breaker across entries.** The FSM-side
  breakers (`P3-FEAT-1637`, `P2-ENH-2245`) are state-failure detectors, not
  queue companions. The constants above are the only vocabulary a future
  queue-level breaker must reuse.
- **Jittered backoff.** See Decision Rationale.

### Decision Rationale (backoff shape)

**Selected**: non-jittered iterative doubling, `delay = min(base * 2^(attempt-1), ceiling)`.

`ll-queue` is a local, single-writer-SQLite work queue. Every non-jittered
backoff site in the codebase (`transport.py:1833,1843` webhook retry,
`transport.py:1106` SSE fan-in reconnect, `parallel/git_lock.py:154,167`) is
local/same-machine; the sole jittered site (`fsm/executor.py:3918`) targets an
external distributed rate-limit retry. Concurrent-drainer contention is
already closed by `claim_entry`'s `BEGIN IMMEDIATE` and `_BUSY_TIMEOUT_MS`
(`queue_store.py:103`), so jitter would duplicate a mechanism that exists.
Non-jittered also needs no `random` import and no monkeypatch scaffolding in
tests.

| Dimension | Non-jittered | Jittered |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 3 | 2 |
| Testability | 3 | 2 |
| Risk | 3 | 2 |
| **Total** | **12/12** | **7/12** |

## Acceptance Criteria

- A `running` entry whose owner is dead is reclaimed to `pending` with
  `enqueued_at` byte-identical and `attempt` preserved; after
  `QUEUE_MAX_ATTEMPTS` claims it is `dead_letter` with
  `result.error == "attempt budget exhausted after N attempts; last: owner died"`
  and is never reclaimed again. `_reclaim_stale` returns
  `(reclaimed, dead_lettered)` and the `--watch` report prints both counts.
- A dispatch whose stderr matches a retryable reason (e.g. `"429"` → `"API
  quota or rate limit exceeded"`) returns the entry to `pending` with
  `attempt == 1` and `next_attempt_at == now + 5s` where `now` is the
  patched `_utcnow()` at dispatch completion; the `n`-th such failure sets
  `next_attempt_at` per the doubling sequence `[5, 10, 20, 40]`, and the 5th
  lands on `dead_letter` with the last error in `result`.
- A dispatch with a nonzero exit and no retryable reason lands on `failed`
  with `attempt == 1`, unchanged from today; a `timed_out` result lands on
  `failed` regardless of stderr text; a non-timed-out CMD failure whose
  stderr contains only the word `"timeout"` (e.g. `test_timeout_x FAILED`)
  lands on `failed`, not `pending`; a LOOP result with
  `error == "terminal failure"` lands on `failed`.
- `claim_entry` refuses a row whose `next_attempt_at` is in the future (SQL
  gate, not only a Python filter); `_drain_once` skips it and one-shot
  `ll-queue run` exits reporting the count backing off; `ll-queue list` shows
  `attempt=N` / `retry in Xs` for that entry.
- `ll-queue cancel <id> --reason "..."` on a `pending` or `running` entry
  yields `cancelled` with `result.reason`; a second-signal `force_stop`
  produces `cancelled` with reason `"interrupted by operator"` and the
  dispatch's `exit_code`/`stdout`/`stderr` still present in `result`.
- **Cancel-race lock**: with an entry `running` under a stubbed dispatch,
  `cancel_entry` is invoked mid-dispatch; when the dispatch returns success,
  the row is still `cancelled` (not `done`) and the `_drain_once` record
  reports `status == "cancelled"`. Same shape for `schedule_retry` and
  `dead_letter_entry` (rowcount 0 on a non-running row).
- `ll-queue requeue <id>` on a `dead_letter`, `failed`, or `cancelled` entry
  returns it to `pending` with `attempt == 0`, `next_attempt_at IS NULL`, and
  the prior result under `result.previous`; on `running` it behaves as today.
- **Retryable-reason join lock**: a test asserts that every string in
  `QUEUE_RETRYABLE_REASONS` is actually produced by `classify_failure` for
  some input (so a reworded reason in `issue_lifecycle.py` cannot silently
  make the queue never retry), that `"Command timeout"` is *not* in the set,
  and that `QUEUE_MAX_ATTEMPTS > 1`. This guards the silent failure where a
  correct classification chain is rendered inert by drift or a one-attempt
  budget.
- **Constants lock**: a test asserts the three constants equal their declared
  values and that `[compute_backoff_s(n) for n in range(1, 8)] == [5, 10, 20,
  40, 80, 160, 300]` (ceiling applied). No grep-shaped source assertion.
- **Status-set lock**: `_STATUS_COLOR.keys() == QUEUE_STATUSES` and the
  `queue_list` MCP tool description enumerates exactly `QUEUE_STATUSES`.
- Migration `_MIGRATIONS[2]` adds `attempt INTEGER NOT NULL DEFAULT 0` and
  `next_attempt_at TEXT` (nullable); `SCHEMA_VERSION` becomes 3; a
  `TestV2ToV3Migration` asserts the columns via `PRAGMA table_info` and that
  pre-existing rows read back with `attempt == 0`.
- `QueueEntry.to_dict()` emits `attempt` and `nextAttemptAt`; `ll-queue status
  <id>` (non-JSON) shows both plus `result.reason`/`result.error` when set.

## Program Design

### Types

- `QueueEntry` (`queue_store.py:267`): add `attempt: int = 0`,
  `next_attempt_at: str | None = None`. Extend `to_dict()` and `_from_row()`.
- `QUEUE_STATUSES`, `QUEUE_TERMINAL_STATUSES`, `QUEUE_RETRYABLE_REASONS`
  frozensets; `QUEUE_MAX_ATTEMPTS`, `QUEUE_BACKOFF_BASE_S`,
  `QUEUE_BACKOFF_CEILING_S` ints; all in `queue_store.py`.

### Signatures

- `_utcnow() -> str` (`queue_store.py`, new): `datetime.now(UTC).strftime(
  "%Y-%m-%dT%H:%M:%SZ")`. The single time seam; `add_entry`, `claim_entry`,
  `_drain_once`, `_reclaim_stale`, and `_format_action_summary` all call it
  (replacing their inline `datetime.now(UTC)` calls) so tests patch
  `little_loops.queue_store._utcnow` once.
- `claim_entry(entry_id, db_path=..., *, owner_pid=None, now: str | None = None) -> bool`
  (`queue_store.py:466`): UPDATE adds `attempt = attempt + 1` and the WHERE
  adds `AND (next_attempt_at IS NULL OR next_attempt_at <= ?)`. `now` defaults
  to `_utcnow()`; injectable for tests.
- `compute_backoff_s(attempt: int) -> int` (`queue_store.py`, new): the
  doubling-then-cap formula.
- `reset_to_pending(entry_id, db_path=..., *, root=None) -> bool`
  (`queue_store.py:417`): unchanged contract for the running→pending reclaim;
  sets nothing but `status`/`claimed_at`/`owner_pid`. Docstring updated to say
  it is the *reclaim* path and does not touch `attempt`.
- `update_entry_result(entry_id, status, result, db_path=...) -> bool`
  (`queue_store.py:439`): signature unchanged; WHERE gains
  `AND status = 'running'`. Docstring updated to state the guard and that a
  False return means the entry was cancelled/reclaimed mid-dispatch.
- `schedule_retry(entry_id, error: str, next_attempt_at: str, db_path=...) -> bool`
  (new): running→pending (guarded), sets `next_attempt_at`, stores the
  failure in `result`, clears `claimed_at`/`owner_pid`.
- `dead_letter_entry(entry_id, error: str, db_path=...) -> bool` (new):
  running→`dead_letter` (guarded), stores `{"error": error, ...}` in `result`,
  clears ownership.
- `cancel_entry(entry_id, reason: str, db_path=..., *, extra: dict[str, Any] | None = None) -> bool`
  (new): pending|running→`cancelled`, stores `{**(extra or {}), "reason":
  reason}` in `result`, clears ownership. `_drain_once`'s `force_stop` branch
  passes the dispatch `result_dict` as `extra`.
- `revive_entry(entry_id, db_path=...) -> bool` (new): terminal→pending,
  `attempt = 0`, `next_attempt_at = NULL`, `result = {"previous": <old
  result>}` (or NULL when there was none). Used by `cmd_requeue` for
  non-running entries.
- `_reclaim_stale(db_path) -> tuple[int, int]` (`cli/queue.py:542`): for each
  dead-owner entry, `dead_letter_entry` if `entry.attempt >=
  QUEUE_MAX_ATTEMPTS` else `reset_to_pending`. Returns `(reclaimed,
  dead_lettered)`; `_report_reclaim` (`:665`) prints both when nonzero.
- `_classify_dispatch(runner: RunnerType, result_dict, timed_out) -> tuple[bool, str]`
  (new, `cli/queue.py`): returns `(retryable, reason)`. Order: `timed_out` →
  non-retryable; `runner is LOOP and error == "terminal failure"` →
  non-retryable; else `classify_failure(...)` and `retryable = reason in
  QUEUE_RETRYABLE_REASONS`.
- `_format_action_summary` (`cli/queue.py:65`): appends `attempt=N` when
  `entry.attempt > 0` and `retry in Xs` when `entry.next_attempt_at` is in
  the future (reversing the earlier "no new branch needed" call).
- `cmd_cancel(args) -> int` (new): `id`, `--reason`, `--json`.
- `cmd_requeue(args) -> int` (`cli/queue.py:686`): widen the status guard;
  dispatch to `reset_to_pending` (running) or `revive_entry` (terminal).

### Call Path

`cmd_run` → `_drain_once` → `list_entries` filtered to
`status == "pending" and (next_attempt_at is None or <= now)` → `claim_entry`
(increments `attempt`, SQL time gate) → dispatch →
- success → `update_entry_result(..., "done", ...)` (guarded)
- `force_stop` set → `cancel_entry(id, "interrupted by operator", extra=result_dict)`
- failure → `_classify_dispatch(entry.action.runner, ...)` →
  - not retryable → `update_entry_result(..., "failed", ...)` (guarded)
  - retryable, `attempt < QUEUE_MAX_ATTEMPTS` → `schedule_retry(id, error, now + compute_backoff_s(attempt))`
  - retryable, exhausted → `dead_letter_entry(id, error)`
- any of the above returns False → `get_entry` and use its `status` in the
  `processed` record / `on_entry` callback.

`_run_watch` → `_reclaim_stale` → per dead-owner entry → `reset_to_pending` or `dead_letter_entry`.

## Integration Map

### Files to Modify

- `scripts/little_loops/queue_store.py` — `QueueEntry` fields, `to_dict`,
  `_from_row`; new constants; `_MIGRATIONS[2]`, `SCHEMA_VERSION = 3`;
  `claim_entry` UPDATE/WHERE; new `compute_backoff_s`, `schedule_retry`,
  `dead_letter_entry`, `cancel_entry`, `revive_entry`; `reset_to_pending`
  docstring.
- `scripts/little_loops/cli/queue.py` — `_drain_once` eligibility filter,
  classification branch, `force_stop` → `cancel_entry`, guard-miss re-read;
  `_reclaim_stale` budget check + tuple return; `_report_reclaim` (`:665`)
  two-count message; `cmd_requeue` widening; new `cmd_cancel` + argparse
  subparser; `_STATUS_COLOR` entries for `dead_letter`/`cancelled`;
  `cmd_status`'s `status_block` (`:306-317`) gains `attempt`, `nextAttemptAt`,
  and reason/error; `_format_action_summary` (`:85`) gains the
  `attempt=N` / `retry in Xs` suffix parts; `_verify_owner_alive` docstring
  (`:514-523`) still accurate since `cmd_requeue` remains a requeue; the
  `--force to requeue anyway` message (`:713-717`) stays. **Prose that says
  the second signal marks the entry `failed` must change to `cancelled`**:
  `_drain_once` docstring (`:455-458`), `_run_watch` docstring (`:633-639`),
  and the `--watch` help string (`:846-848`). The module-level
  `_current_loop_proc` comment is unaffected.
- `scripts/little_loops/mcp_server/tools.py` — `_tool_queue_requeue`
  (`:615-645`) widens its status guard to match `cmd_requeue` and computes
  the `changes[].from` from the actual status; `queue_list` description
  (`:838`) enumerates `QUEUE_STATUSES`; optional `queue_cancel` tool
  registered in `policy.MUTATING_TOOLS` (`policy.py:62-63`) mirroring
  `queue_requeue`. `_tool_queue_remove` (`:585-612`) unchanged.
- `scripts/tests/test_cli_surface.py:139` — add `cancel` to the `ll-queue`
  subcommand-set lock.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/mcp_server/tools.py:622,644` — `reset_to_pending`
  caller; contract unchanged for `running` entries, so this stays correct
  unless the tool adopts the widened guard.
- `scripts/tests/test_queue_store.py:428,438,444` (`TestResetToPending`) —
  contract unchanged; add assertions that `attempt`/`next_attempt_at` are not
  touched.
- `scripts/tests/test_cli_queue_run.py:638-746` (`TestReclaimStale`,
  `TestCmdRequeue`) — extend for the budget-exhausted reclaim and the widened
  requeue; both patch `little_loops.cli.queue.psutil.Process`.
- `scripts/tests/test_cli_queue_run.py` lines 121, 137, 153, 175, 212, 290,
  412, 426 assert `status == "failed"` immediately after a failure. Under the
  mapping above these stay `failed` (their fixtures produce non-transient
  stderr or exit codes); only fixtures whose stderr happens to match a
  `TRANSIENT` pattern need review. Raw-SQL fixture at `:195` names the
  pre-migration column set; `attempt` has a DEFAULT so it still works, but
  add the column for clarity.
- `scripts/tests/test_feat_queue_mcp_tools.py:142-176`
  (`test_queue_requeue_running_entry`) — still valid; raw-SQL fixture at
  `:157` unaffected by the defaulted column.
- `scripts/tests/test_cli_queue.py:311-328`
  (`test_list_json_unaffected_by_summary_change`) — pattern to extend for
  asserting `attempt`/`nextAttemptAt` in `--json`.
- `scripts/tests/test_cli_queue_run.py:68-88` (`TestCmdRunDispatchOrder`) —
  still passes (no `next_attempt_at` set); add a sibling test that a
  backing-off entry is skipped while eligible siblings dispatch.

### Conventions in Force

- Backoff as named base + ceiling constants, `delay = base * 2^(attempt-1)`
  (`transport.py:76-77,1830`; `git_lock.py:47-49,154,167`).
- Machine-readable status/reason sets as a declared set locked by a test
  (`DeferReason`/`_DEFERRAL_REASON_CODES`, `issue_lifecycle.py:65-93`,
  `test_issue_lifecycle.py:1985-1993`).
- New nullable/defaulted columns as `ALTER TABLE ... ADD COLUMN` per migration
  entry with a motivating-issue comment (`queue_store.py:124-131`).
- Retryability classification as a text-pattern function returning
  `(Enum, reason)` (`classify_failure`, `issue_lifecycle.py:159-239`), not an
  exit-code allowlist (`retryable_exit_codes`, `fsm/schema.py:713`).
- Operator-supplied reason stored as its own field, free text
  (`close_reason`, `parallel/types.py:77`).

### Tests

- `scripts/tests/test_queue_store.py` — one `TestX` class per new function;
  `TestV1ToV2Migration` (375-401) is the template for `TestV2ToV3Migration`;
  `TestClaimEntry` gains the time-gate and `attempt`-increment cases (inject
  `now`).
- `scripts/tests/test_cli_queue_run.py` — new classes for the classification
  branch (drive `_drain_once` directly with a stubbed `run_action` returning
  retryable stderr, real stderr, `"timeout"`-only stderr, a LOOP
  `"terminal failure"`, and `timed_out=True`), the `force_stop` →
  `cancelled` path (currently untested; grep for `"interrupted by operator"`
  in `scripts/tests/` finds nothing), the cancel-race lock (stubbed
  `run_action` calls `cancel_entry` on its own entry before returning
  success), `_reclaim_stale` exhaustion, and `cmd_cancel`. Precedent for
  asserting the doubling sequence: `test_git_lock.py::TestRetryLogic`
  (209-248). Precedent for exhaustion logging: `test_transport.py:1604-1623`.
- `scripts/tests/test_queue_store.py` — `TestUpdateEntryResult` gains a case
  asserting a write to a non-running row returns False and leaves the row
  unchanged (the new guard).
- `_STATUS_COLOR` has no test today; the status-set lock covers it.
- `_verify_owner_alive`'s `claimed_at` fallback (`cli/queue.py:531-536`) is
  untested but out of scope here.

### Documentation

- `docs/ARCHITECTURE.md:827-838` — Queue DB section: schema, statuses,
  migration table row at `:834`; the final paragraph's "marks that entry
  `failed`" (second-signal shutdown) becomes `cancelled`; note the
  status-guarded completion write alongside the `claim_entry` BEGIN IMMEDIATE
  prose.
- `docs/reference/API.md:90`, `:10510-10533` — `QueueEntry` field lists and
  module reference; `:5056-5066` CLI entry point.
- `docs/reference/CLI.md:4052-4135` — `ll-queue` reference: field list
  (`:4054`), exit-code→status mapping (`:4102`, add the classify/backoff
  branch), `requeue` prose (`:4122`, widened statuses), new `cancel`
  subcommand; `:5299-5304` MCP mutating-tools prose.
- `docs/guides/MCP_SERVER_GUIDE.md:309-345,364` — `QueueEntry` JSON example
  gains the two fields.
- `docs/reference/CONFIGURATION.md:717` — no change (constants are not
  configurable in this issue).

### Configuration

None. `QueueConfig` (`config/features.py:1559-1570`) and
`config-schema.json:2262-2270` are untouched, so
`test_config.py:4423-4451` and `test_config_schema.py`'s BUG-3192 parity
guards are not in play.

## Implementation Steps

1. `queue_store.py`: constants (incl. `QUEUE_RETRYABLE_REASONS`), `_utcnow`, `compute_backoff_s`, migration + `SCHEMA_VERSION = 3`, `QueueEntry` fields/`to_dict`/`_from_row`.
2. `queue_store.py`: `claim_entry` increment + time gate; `update_entry_result` status guard; `schedule_retry`, `dead_letter_entry`, `cancel_entry(extra=)`, `revive_entry` (preserves `result.previous`); `reset_to_pending` docstring.
3. `cli/queue.py`: `_classify_dispatch` (timeout → LOOP terminal → reason allowlist); `_drain_once` eligibility filter, outcome branch, `force_stop` → `cancel_entry`, guard-miss re-read, backing-off count in the one-shot summary.
4. `cli/queue.py`: `_reclaim_stale` budget check + tuple return; `_report_reclaim`; `cmd_requeue` widening; `cmd_cancel` + subparser; `_STATUS_COLOR`; `cmd_status` block; `_format_action_summary` suffix; `failed`→`cancelled` prose in docstrings/help.
5. `mcp_server/tools.py`: `_tool_queue_requeue` guard + `changes[].from`; `queue_list` description; optional `queue_cancel`.
6. Tests per the Tests section, including the three lock tests (retryable-join, constants, status-set) and `test_cli_surface.py:139`.
7. Docs per the Documentation section.

## Impact

- **Priority**: P1 — an entry that kills its drainer is re-dispatched forever today.
- **Effort**: Medium — one migration, five small store functions, one new subcommand, one classification branch. Reduced from Large by cutting overflow/trimming and keeping `reset_to_pending`/`requeue` contracts intact.
- **Risk**: Medium — behavior change: transient failures now retry instead of landing on `failed`. Bounded by `QUEUE_MAX_ATTEMPTS` and by the explicit non-retryable mapping for timeouts and real errors.
- **Breaking Change**: No — `reset_to_pending` keeps its contract; `requeue` only widens accepted statuses; new statuses are additive. Consumers filtering on `status == "failed"` will no longer see transient failures there until the budget is exhausted. `update_entry_result` now returns False (no-op) on a non-running row; no in-tree caller relied on writing a completion to a non-running entry.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08 against the prior revision; scores in frontmatter are stale pending a re-run. The three UNRESOLVED items it flagged (constant values, retryability taxonomy, overflow rules) are settled or cut in Design Decisions above._

## Status

**Open** | Created: 2026-09-08 | Priority: P1

## Session Log
- manual review - 2026-09-08 - added cancel-vs-dispatch status guard, `QUEUE_RETRYABLE_REASONS` allowlist + LOOP terminal rule, `_utcnow` seam, corrected owner-death message / `next_attempt_at` base / CMD-timeout-stderr claim, `cancel_entry(extra=)`, `result.previous` on revive, `list` backoff suffix, two-count reclaim report, dropped grep-shaped constants test
- `/ll:confidence-check` - 2026-09-09T04:38:32 - `4a00b9f5-2c1a-4bb9-8901-1abcda8ab946.jsonl`
- `/ll:verify-issues` - 2026-09-09T04:36:14 - `a78c41f1-909c-4220-a4df-fe4ab8b7ba0c.jsonl`
- manual review rewrite - 2026-09-09 - design layer rewritten; wiring findings retained
- `/ll:wire-issue` - 2026-09-09T04:19:11 - `31613f06-17db-4122-af95-f9089ed7405e.jsonl`
- `/ll:decide-issue` - 2026-09-09T04:08:14 - `3577db8f-8723-4e0e-adb7-90253d958f56.jsonl`
- `/ll:refine-issue` - 2026-09-09T04:03:54 - `92947113-ae24-4c67-9cb1-ea2af355904e.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:57:00 - `6d9082d6-8afc-4d51-af36-c0955fd01c58.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:53:40 - `8963b056-bb60-497d-9529-e15d23112f43.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:43:16 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:41:28 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:17:51 - `ae93785e-f7d9-41cc-96ab-d51f1883c15a.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:04:27 - `a4badc70-f3c5-4caf-beea-29940135de9c.jsonl`
- `/ll:format-issue` - 2026-09-09T02:34:54 - `b326158e-3610-46e0-8daf-a6fb008cff1f.jsonl`
