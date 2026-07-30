---
id: BUG-2929
title: "`ll-queue run` claim is a TOCTOU race \u2014 concurrent drainers double-execute\
  \ the same entry"
type: BUG
status: done
priority: P2
captured_at: '2026-07-30T21:27:49Z'
completed_at: '2026-07-30T22:08:29Z'
discovered_date: 2026-07-30
discovered_by: capture-issue
relates_to:
- FEAT-2683
- FEAT-2930
- BUG-2928
labels:
- queue
- concurrency
confidence_score: 96
outcome_confidence: 94
score_complexity: 24
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2929: `ll-queue run` claim is a TOCTOU race

## Summary

`cmd_run` selects the head pending entry and then marks it `running` in two
separate, uncoordinated database round-trips. Nothing makes that pair atomic, so
two `ll-queue run` processes both observe the same entry as `pending` and both
dispatch it. The work item executes twice.

## Motivation

FEAT-2683 shipped `ll-queue run` as a strictly serial v1 worker, which made a
non-atomic claim harmless in the common case. That assumption is already
breakable by hand (two terminals) and becomes structurally false the moment a
second drainer can exist — which is exactly what FEAT-2930's `--watch` mode
introduces. Fixing the claim is a prerequisite for any multi-drainer design, and
is worth doing on its own merits regardless of whether `--watch` lands.

## Current Behavior

`cli/queue.py:289-294`:

```python
while True:
    pending = [e for e in list_entries(QUEUE_DB_PATH) if e.status == "pending"]
    if not pending:
        break
    entry = pending[0]
    update_entry_result(entry.id, "running", None, db_path=QUEUE_DB_PATH)
```

`list_entries` (`queue_store.py:284`) opens a connection, reads, and closes.
`update_entry_result` (`queue_store.py:337`) then opens a *separate* connection
and issues an unconditional write:

```python
"UPDATE queue_entries SET status = ?, result = ? WHERE id = ?"
```

There is no `WHERE status = 'pending'` guard and no enclosing transaction, so
the update succeeds and returns `rowcount > 0` even when another process already
claimed the entry microseconds earlier.

> ⚠ The `queue_store.py:284`/`:337` anchors above are still current, but the
> `cli/queue.py:289-294` anchor has drifted — commit `35bc5b46` (BUG-2928,
> landed the same day as this issue was captured) shifted line numbers above
> `cmd_run` without touching the loop itself. The unguarded claim now lives at
> `cli/queue.py:334-338`, inside `cmd_run` (`cli/queue.py:318-381`); the code
> shape quoted above is unchanged, only the line numbers moved. The final
> status write (`cli/queue.py:362`, `update_entry_result(entry.id, status,
> result_dict, ...)`) is the *same* unguarded call, reused a second time after
> dispatch — that reuse is intentional per this issue's own Program Design
> (the completion writer assumes the caller already owns the entry) and is not
> part of this bug's fix surface.

## Steps to Reproduce

1. Enqueue several long-running entries: `ll-queue add <target> --runner cmd`.
2. Start two drainers near-simultaneously, in separate terminals:
   ```bash
   ll-queue run   # terminal A
   ll-queue run   # terminal B
   ```
3. Observe both processes dispatch the same head entry. Each writes its own
   terminal status over the other's; the last writer wins, so one execution's
   outcome is silently lost from `result`.

## Expected Behavior

Claiming an entry is atomic: exactly one drainer transitions a given entry from
`pending` to `running`, and every other drainer observing that entry skips it
and moves to the next candidate. A losing claimant never dispatches the action.

## Root Cause

`queue_store.py` exposes no claim primitive. `update_entry_result` is a
general-purpose status writer designed for the *completion* write, where the
caller already owns the entry; `cmd_run` reuses it for the *acquisition* write,
where ownership is precisely what's in question. The check ("is it pending?")
happens in Python against a stale read, not in SQL against the live row.

## Proposed Solution

Add a dedicated claim function to `queue_store.py` that performs the test and
the set inside one immediate transaction, and have `cmd_run` call it instead of
`update_entry_result`:

```python
def claim_entry(entry_id, db_path=DEFAULT_DB_PATH) -> bool:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'running' "
            "WHERE id = ? AND status = 'pending'",
            (entry_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0
```

`BEGIN IMMEDIATE` matches the precedent already established by
`_apply_migrations` (`queue_store.py:132`). `cmd_run`'s drain loop then advances
past any entry whose claim returns `False` rather than dispatching it.

Note the loop must not simply `break` on a failed claim — a lost race means
*another* drainer took that entry, not that the queue is drained. It should
re-read and try the next candidate, terminating only when no pending entry
remains unclaimed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`isolation_level` gap in the sketch above**: `connect()` (`queue_store.py`)
  leaves `sqlite3.Connection.isolation_level` at the Python default (implicit
  per-statement transactions), and `_apply_migrations`
  (`queue_store.py:120-148`) — the only existing `BEGIN IMMEDIATE` user in this
  file — explicitly sets `conn.isolation_level = None` before issuing `BEGIN
  IMMEDIATE`, then restores `prior_isolation` in a `finally`, and issues
  `COMMIT`/`ROLLBACK` manually rather than via `conn.commit()`. The
  `claim_entry` sketch in this section calls `conn.commit()` directly under
  the connection's default isolation level, which does not follow that
  established idiom. To stay consistent with the codebase's own precedent
  (and avoid relying on undocumented sqlite3-module BEGIN-statement
  detection), `claim_entry` should mirror `_apply_migrations`'s exact shape:
  set `isolation_level = None`, `BEGIN IMMEDIATE`, `try`/`except
  BaseException: ROLLBACK; raise`, `finally: isolation_level = prior_isolation`.
- **Test placement**: `scripts/tests/test_queue_store.py` groups tests into
  `Test<FunctionName>` classes 1:1 with `queue_store.py` functions —
  `TestUpdateEntryResult` sits at lines 211-225 and already covers the
  "happy path" / "not-found" pair for the sibling `update_entry_result`
  function. A new `TestClaimEntry` class belongs immediately alongside it,
  with the same two cases (claim succeeds on `pending`, returns `False` on
  `running`/unknown) plus the concurrency regression case below.
- **Concurrency regression test pattern**: `test_session_store_schema.py`'s
  `TestConnect.test_concurrent_ensure_db_on_fresh_path`
  (`scripts/tests/test_session_store_schema.py:188-219`) is the closest
  existing precedent — `threading.Barrier(N)` synchronizes worker threads onto
  the critical section, each thread appends its outcome to a shared list, and
  assertions run against a fresh direct `sqlite3.connect()` after `join()`.
  For this bug's regression test, `threading.Barrier(2)` with each of 2
  threads calling `claim_entry(entry_id, db_path=db)` and appending its bool
  return to a lock-guarded list, then asserting `sorted(results) == [False,
  True]`, is a direct adaptation. `test_git_lock.py` (around line 395/423)
  has a second, event-based (non-Barrier) two-thread interleaving pattern if
  a deterministic ordering is preferred over barrier-synchronized overlap.
- **No competing lock primitive to reconcile with**: the only other
  concurrency mechanism touching queue-like state in this codebase is
  `ll-loop queue`'s filesystem PID-liveness marker system
  (`cli/loop/queue.py`), which is unrelated (FEAT-2684 compat shim, not
  SQLite-backed) — `claim_entry` has no existing lock to coordinate with
  beyond SQLite's own `BEGIN IMMEDIATE` write lock and the module's
  `PRAGMA busy_timeout = 5000` / `journal_mode = WAL` settings
  (`queue_store.py:60`, `_configure_connection`).

## Integration Map

### Files to Modify
- `scripts/little_loops/queue_store.py` — add `claim_entry(entry_id, db_path) -> bool`
  adjacent to `update_entry_result` (`:337-353`), following the
  `isolation_level=None` + `BEGIN IMMEDIATE` shape of `_apply_migrations`
  (`:120-148`) rather than the plain-`commit()` shape of `update_entry_result`.
  Also add `"claim_entry"` to the module's `__all__` export list (`:37-50`,
  currently ends with `"update_entry_result"`) — an easy-to-miss edit distinct
  from the function body itself; every other public function in this module is
  listed there. [Agent 2 finding]
- `scripts/little_loops/cli/queue.py` — `cmd_run`'s drain loop
  (`:318-381`, race at `:334-338`): replace the unconditional
  `update_entry_result(entry.id, "running", None, ...)` claim write with
  `claim_entry(entry.id, db_path=QUEUE_DB_PATH)`; on `False`, continue the
  loop against the next pending candidate instead of dispatching.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py:cmd_run` is `update_entry_result`'s and
  `list_entries`'s only caller in the claim path — no other module calls
  either function for claim purposes, so the fix surface is contained to the
  two files above.

### Similar Patterns
- `scripts/little_loops/queue_store.py:120-148` (`_apply_migrations`) — the
  transaction-control idiom `claim_entry` should copy.
- `scripts/little_loops/session_store/schema.py:~973-990` — the sibling
  `BEGIN IMMEDIATE` migration guard `_apply_migrations`'s own docstring cites
  as its design precedent.
- `scripts/little_loops/queue_store.py:326-334` (`remove_entry`) and `:337-353`
  (`update_entry_result`) — the `cur.rowcount > 0` return convention
  `claim_entry` should also follow.
- `scripts/tests/test_concurrency.py:360-383`
  (`TestLockManagerRaceConditions.test_concurrent_acquire_same_scope_only_one_wins`)
  — `threading.Barrier(2)` + shared results list +
  `results.count(True) == 1` is the closest existing "exactly one claimant
  wins" test shape in the repo; model the regression test on it rather than
  inventing a new pattern. The same class's
  `test_n_waiters_all_acquire_with_retry_loop` (`:385-424`) is the N-waiter
  variant if more than 2 concurrent claimants are worth covering.

### Tests
- `scripts/tests/test_queue_store.py` — add `TestClaimEntry` next to
  `TestUpdateEntryResult` (`:211-225`), before `class TestConnect:` (`:228`).
  Add `claim_entry` to the `from little_loops.queue_store import (...)` block
  (`:12-24`); also home for the barrier-synchronized concurrency regression
  test. Confirmed no existing test in `test_queue_store.py`,
  `test_cli_queue_run.py`, or `test_cli_queue.py` mocks/asserts a call count
  on `update_entry_result` during the *claim* phase, so swapping `cmd_run`'s
  acquisition write to `claim_entry` does not break any existing assertion by
  itself.
- `scripts/tests/test_cli_queue_run.py` — existing `cmd_run` test file; add a
  case asserting a lost claim advances to the next candidate rather than
  breaking the drain loop. Model on `TestCmdRunOnlyPending.test_run_skips_non_pending_entries`
  (`:170-189`): seed two entries, pre-claim the first directly via
  `claim_entry`/`update_entry_result` before invoking `cmd_run`, then assert
  `cmd_run` dispatched only the second entry. A new `TestCmdRunClaimContention`
  class (or an addition to `TestCmdRunOnlyPending`) follows the file's
  one-class-per-scenario convention.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:9070-9086` (`## little_loops.queue_store`) — the
  hand-maintained `from little_loops.queue_store import (...)` sample lists
  `update_entry_result` with an inline FEAT-2683 comment but has no
  `claim_entry` entry; add one. The trailing prose sentence ("`result` is
  `NULL` until a worker calls `update_entry_result()`.") describes only the
  completion write — extend it (or add a sentence) to name `claim_entry` as
  the acquisition-write primitive.
- `docs/ARCHITECTURE.md:851` (`## Queue DB (ll-queue)`) — the sentence
  "`update_entry_result` backs `ll-queue run` (FEAT-2683), the serial
  dequeue-and-execute worker loop..." attributes the whole `run` dispatch flow,
  including acquisition, to `update_entry_result`. After this fix, acquisition
  is `claim_entry` and `update_entry_result` is only the completion write —
  update this sentence to name both functions and their distinct roles.

## Program Design

### Signatures

- `claim_entry(entry_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> bool`

  Returns `True` iff this caller won the claim.

- `update_entry_result(entry_id: str, status: str, result: dict | None) -> bool`

  Unchanged; still used for the completion write, where the caller owns the entry.

### Call Path

`cmd_run` -> `list_entries` -> `claim_entry` (skip entry on `False`) ->
`_run_loop_entry` | `run_action` -> `update_entry_result`

## Acceptance Criteria

- [x] `queue_store.claim_entry` exists and performs the conditional update inside
      a `BEGIN IMMEDIATE` transaction.
- [x] `claim_entry` returns `False` for an entry already in `running`, `done`, or
      `failed`, and leaves that row untouched.
- [x] `cmd_run` claims via `claim_entry` and skips to the next candidate on a
      lost claim instead of dispatching or breaking out of the drain loop.
- [x] Regression test: two concurrent claimants against one entry produce exactly
      one `True` and one `False`, and the action dispatches exactly once.
- [x] `python -m pytest scripts/tests/` exits 0.

## Resolution

Added `queue_store.claim_entry(entry_id, db_path) -> bool`, mirroring
`_apply_migrations`'s `isolation_level=None` + `BEGIN IMMEDIATE` +
manual `COMMIT`/`ROLLBACK` idiom, performing the pending-check and the
`status = 'running'` write inside one transaction. `cmd_run`'s drain loop
(`cli/queue.py`) now claims via `claim_entry` and advances to the next
pending candidate on a lost claim instead of reusing `update_entry_result`
for acquisition or breaking the loop.

Added `TestClaimEntry` (`test_queue_store.py`) covering the happy path,
non-pending rejection, unknown-id rejection, and a `threading.Barrier(2)`
concurrency regression asserting exactly one of two simultaneous claimants
wins. Added `TestCmdRunClaimContention` (`test_cli_queue_run.py`) asserting
`cmd_run` skips an entry pre-claimed by another drainer and dispatches only
the remaining candidate. Updated `docs/reference/API.md` and
`docs/ARCHITECTURE.md` to document `claim_entry` as the distinct acquisition
write alongside `update_entry_result`'s completion-write role.

`python -m pytest scripts/tests/` — 17192 passed, 42 skipped.
`ruff check` and `python -m mypy` clean on all touched files.

## Impact

Today the blast radius is limited — a user must start two drainers by hand — but
the consequence is severe when it happens: duplicate execution of an arbitrary
work item, which for a `LOOP` entry means two concurrent `autodev` runs against
the same issue, and for a `CMD` entry means whatever that command does, twice.
The lost `result` write also makes the double-run hard to detect after the fact.

**Effort**: Small — one new store function, a loop adjustment, and a concurrency
test. **Risk**: Low — additive; the completion-write path is unchanged.

## Related

- **FEAT-2683** — shipped the serial worker whose single-drainer assumption made
  this latent
- **FEAT-2930** — `--watch` mode; makes multiple drainers a first-class scenario
  and therefore depends on this fix
- **BUG-2928** — separate `ll-queue run` defect (LOOP subprocess timeout)

## Session Log
- `/ll:manage-issue` - 2026-07-30T22:07:55Z - `00041c0b-3526-41ec-b743-a686380c429a.jsonl`
- `/ll:confidence-check` - 2026-07-30T21:57:04Z - `1ec42bc6-065f-4b0f-a9e3-c6d78deb5e14.jsonl`
- `/ll:wire-issue` - 2026-07-30T21:55:17 - `086910fa-b436-491f-b2fe-60d2d3074ea0.jsonl`
- `/ll:refine-issue` - 2026-07-30T21:50:02 - `f98f2c50-21df-4e5f-b604-307f4a1efb7c.jsonl`
- `/ll:capture-issue` - 2026-07-30T21:27:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f37dc1-b451-4197-a82c-a55434adcd06.jsonl`

## Status

**Open** | Created: 2026-07-30 | Priority: P2
