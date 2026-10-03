---
id: ENH-3679
type: ENH
title: Bound cli_event_context lock waits with a short busy timeout and a drop counter
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
relates_to:
- EPIC-3693
- ENH-3698
- ENH-3658
- ENH-3666
- ENH-3678
- ENH-3680
blocks:
- ENH-3683
- ENH-3698

---

# ENH-3679: Bound cli_event_context lock waits with a short busy timeout and a drop counter

## Summary

Make `cli_event_context` resilient to a held local SQLite write lock: use a short **per-phase** busy-timeout budget (setup + entry <= 250 ms, exit <= 250 ms) via an explicit `busy_timeout_ms` parameter, and count every dropped event in a sidecar drop counter surfaced by `ll-doctor`, so loss is measurable. The bounded spool that would retain dropped events is **deferred to ENH-3683**, to be built only if measured drops justify it. Split out of ENH-3666 after its 2026-09-29 Opus review; rescoped 2026-09-30. Detached from EPIC-3693 2026-10-02 (local-store fix; `relates_to` only).

## Current Behavior

`cli_event_context` can wait `_BUSY_TIMEOUT_MS` (5000 ms) at entry and again at exit, then drop the event or its completion data under a held lock. Observed with a detached `--rebuild` holding the lock, but any long local writer can cause it.

## Expected Behavior

`cli_event_context` bounds SQLite lock waiting in two phases: **setup + entry insert share 250 ms** and **exit update gets a fresh 250 ms**. Use a monotonic deadline within each phase, passing only the remaining budget to every connection/pragma/query lock wait. Never measure a single deadline across the arbitrary command body. This bounds lock waiting, not arbitrary filesystem or migration CPU time; tests on an already migrated store assert elapsed time with a documented small scheduling tolerance. A timed-out event/completion is dropped best-effort and counted in an `.ll/` sidecar; `ll-doctor` reports the count. Non-telemetry writers keep 5000 ms.

**Drop-count rule (defines "exactly once per dropped event"):** if the entry was dropped, the exit skips entirely with **no second count**; if the entry succeeded and the exit was dropped, **one completion drop** is counted. A single command therefore adds at most one to the counter.

**What counts as a drop (2026-10-03 Opus review):** only a lock failure — `sqlite3.OperationalError` whose `sqlite_errorcode & 0xFF` is `SQLITE_BUSY`/`SQLITE_LOCKED` — or an exhausted phase budget. `HistorySuppressed` (remote), disk-full, corruption, and permission errors keep their existing handling and are **not** counted, so the ENH-3683 decision metric stays pure.

**Budget mechanics (2026-10-03 Opus review):**
- The entry deadline starts **after** the capture gate / kill-switch checks, so a suppressed event spends no budget.
- The connection stays open across the command body, so the exit phase must **re-issue `PRAGMA busy_timeout = 250` on that same connection** before the UPDATE and commit — otherwise it inherits whatever residual the entry phase left. Never pass a value <= 0 to the pragma (it disables waiting); treat an exhausted budget as a drop instead.
- Also pass `timeout=` to the `sqlite3.connect` calls: its 5.0 s default survives a swallowed pragma failure.
- Steady-state setup takes no write lock (`_apply_migrations` fast path is a lock-free read), so only the INSERT and commit can block. `connect()` owns an internal deadline when `busy_timeout_ms` is set (rather than threading one through `ensure_db`); migrations stay on the telemetry path (skipping them would break fresh-db creation).
- **Log level:** a counted lock drop logs at `debug`, not `warning` — a 250 ms bound under ordinary `ll-parallel` contention would otherwise print a stderr line on every command. Other failures keep `warning`.
- **Documented limits:** WAL auto-/close-time checkpoint I/O and VACUUM writers fall outside the bound; the read->write upgrade hazard (busy handler skipped) does not apply because no read transaction is open when the INSERT starts; a `kill -9` of the command leaves a row with NULL `exit_code` (unchanged).

## Scope Phasing (2026-09-30 Opus review)

- **This issue (former Phase 1):** a short per-phase timeout budget for `cli_event_context` (setup + entry <= 250 ms, exit <= 250 ms) via an **explicit `busy_timeout_ms` parameter** threaded through `schema.connect` → `_configure_connection` (not a contextvar; `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` today), plus the sidecar drop counter. Set the timeout before any `ensure_db`/`schema.connect` lock wait; shared `connect()` and other writers keep `_BUSY_TIMEOUT_MS`.
- **ENH-3683 (deferred, former Phase 2):** the immutable-file spool and idempotent drain. Its motivating lock holder (a multi-minute detached `--rebuild`) is largely removed by ENH-3678; activate it only if the drop counter, measured after ENH-3678 ships, shows material loss.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` entry and exit handling (`_connect_telemetry` gains the kwarg); `session_store/schema.py` `connect`/`_configure_connection` (explicit `busy_timeout_ms`); the drop-counter sidecar and its `ll-doctor` line. `skill_event_context` and other writers are out of scope.
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`). The remote branch of `connect()` accepts and ignores `busy_timeout_ms`; the `Backend` protocol signature is unchanged.
- **Sidecar path:** derive it from the *resolved* store path (honoring `LL_HISTORY_DB` / `history.db_path`). `cli/doctor.py:_history_db_data` currently reads `Path.cwd() / DEFAULT_DB_PATH`; the doctor line must use the same resolver as the writer, or an override silently reports zero drops.
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread; released via `threading.Event`, not sleeps; threads rather than subprocesses to avoid xdist worker-timeout hazards), asserting elapsed time within a pinned **[200 ms, 1000 ms]** window per phase for both entry and exit — the lower bound proves the wait actually happened (SQLite builds without `HAVE_USLEEP` make a sub-1000 ms `busy_timeout` fail instantly). Cover the drop-count rule (entry dropped -> exit skipped, one count; entry ok + exit dropped -> one completion count); non-lock errors and `HistorySuppressed` do not count; drop counter increments once per dropped event and `ll-doctor` reports it; other writers keep 5000 ms; remote path unchanged. **Test-first:** rewrite the tests pinning the warning text for lock drops (`test_session_store_writers.py` "enter failed"/"exit update failed" at ~562/595, `test_cli_queue.py:517` `OperationalError: database is locked`) to expect `debug`, keeping `warning` for non-lock failures.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape; `ll-doctor` drop-count line. **Sequencing:** the drop-count line is an informational `CheckResult` added **inside the existing `_history_db_check`** (`cli/doctor.py`), not a new registered check, so the `ll-doctor` check list/count in `docs/reference/CLI.md` is unchanged and the shared-surface conflict with ENH-3698 (rebuild-pending check) and ENH-3658 (`--trim` remote guard) reduces to a doc-line edit; still land in sequence, never as parallel branches.

## Program Design

### Signatures

- `connect(path=DEFAULT_DB_PATH, *, busy_timeout_ms: int | None = None)` (`little_loops.session_store.schema`) — `None` keeps `_BUSY_TIMEOUT_MS`; `cli_event_context` passes the short value.
- `record_dropped_cli_event(db: Path | str, kind: Literal["E", "X"]) -> None` — counts a drop without a database write or blocking user-space lock; never raises. `E` = entry (whole event lost), `X` = completion (row kept, `exit_code`/`duration_ms` lost). **Counter spec (revised 2026-10-03):** open `<resolved-db>.cli-event-drops` with `O_CREAT | O_WRONLY | O_APPEND`, append one fixed-width 12-byte record `<10-digit epoch seconds><E|X>\n` with a single `os.write`, and close. A sub-`PIPE_BUF` `O_APPEND` write is atomic on a local filesystem, so concurrent processes cannot interleave. No read-modify-write or `flock`: a contended counter must not replace the SQLite stall. Doctor parses whole 12-byte records, ignores a malformed/torn tail (possible on ENOSPC), and reports **drops in the last 7 days split by kind, plus the ratio against `cli_events` rows** — a timeless lifetime count cannot decide whether ENH-3683 is warranted, and the record format cannot change after rollout. `.ll/*.lock` is gitignored today, but the suffix is misleading for a non-lock file, so the sidecar drops it; add `.ll/*.cli-event-drops` to `.gitignore` and the `ll-init` writer list (`init/writers.py`). Counts are exact when append succeeds; an unwritable/full filesystem fails softly and cannot guarantee an increment. No size cap needed at 12 B/drop; doctor may note a large file.
- **Threading the timeout:** `connect()` owns an internal monotonic deadline when `busy_timeout_ms` is set (see Budget mechanics): compute remaining time before each possible lock wait (setup connections, pragmas, insert, commit) and drop when exhausted — a fresh 250 ms at every step would multiply the budget. Ordinary callers retain the existing timeout. Entry failure skips all exit work. The exit phase re-issues `PRAGMA busy_timeout = 250` on the open connection; a command body longer than 250 ms still receives that fresh exit budget and can persist its completion. Update connection monkeypatches for the new keyword; no raw `sqlite3.connect(` outside the existing chokepoint.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout `connect` → lock failure → `record_dropped_cli_event`; `ll-doctor` reads the sidecar.

## Scope Boundaries

- **In scope**: a short per-phase timeout budget for `cli_event_context` and the drop counter with its `ll-doctor` line.
- **Out of scope**: the spool and drain (ENH-3683), other telemetry writers, `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` remote hook spool (ENH-3680, no coupling), remote-backend CLI telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small - timeout plumbing, a sidecar counter, one doctor line
- **Risk**: Low - no new durability surface; drops are counted, not retained
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE` on a migrated store, lock waiting uses one 250 ms setup/entry budget and a fresh 250 ms exit budget (values pinned); observed phase latency falls in the pinned **[200 ms, 1000 ms]** window (lower bound proves the wait occurred). Other writers keep 5000 ms. The arbitrary command body is excluded from these measurements.
- [ ] The exit phase re-issues `PRAGMA busy_timeout = 250` on the open connection (test: entry consumes most of its budget, exit still gets ~250 ms); no code path passes a value <= 0 to the pragma.
- [ ] Only lock failures (`SQLITE_BUSY`/`SQLITE_LOCKED`) or exhausted budget count as drops; `HistorySuppressed`, disk-full, corruption, and permission errors do not. Each dropped event writes exactly one record per the drop-count rule (entry dropped -> exit skips, no second record; entry ok + exit dropped -> one `X` record) and `ll-doctor` reports last-7-day counts split by kind plus the ratio vs `cli_events` rows, using the same resolved sidecar path as the writer (honors `LL_HISTORY_DB`).
- [ ] Counted lock drops log at `debug`; non-lock failures keep `warning`; the tests that pinned the lock-drop warning text are updated test-first.
- [ ] A command body longer than 250 ms does not consume the exit budget. Multi-step setup cannot reset the entry deadline, and the deadline starts after the capture gate. Concurrent threads append N known drops and doctor reports N; a held `flock` on the sidecar does not stall the append; a torn tail record is ignored; sidecar write failure never escapes.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path); `busy_timeout_ms` is accepted and ignored there.
- [ ] The doctor line is an informational `CheckResult` inside `_history_db_check` (no change to the registered-check count) and never affects the exit code.
- [ ] Existing telemetry-writer tests pass; docs describe the timeout, drop counter, and documented limits (checkpoint/VACUUM outside the bound).
- [ ] ENH-3683 (spool) stays deferred unless the measured drop count justifies activating it.

## Related

- ENH-3666, ENH-3678; ENH-3683 (deferred spool, former Phase 2); ENH-3680 (independent remote hook spool; no envelope coupling).

## Confidence Check Notes

_Updated 2026-10-02 after the EPIC-3693 pre-implementation review._

Prior 90/79 scores were cleared: per-step timeout resets and a blocking counter lock undermined the intended bound. The revised plan uses two independent cumulative phase budgets and an append-only counter. Re-run `/ll:confidence-check` on this scope before implementation; planned lock-holder/concurrent-counter tests are verification requirements, not completed evidence.

_Revised 2026-10-03 after a pre-implementation review with an Opus second opinion (`/ll:advise`, confidence 0.82)._ Changes: exit phase re-issues the busy-timeout pragma; counter moved from a one-byte count to a 12-byte timestamped, kind-tagged record (the ENH-3683 decision needs a windowed rate, not a lifetime count); explicit drop definition (lock errors only); lock drops log at `debug`; timing window pinned to [200 ms, 1000 ms]; sidecar path derived from the resolved store (fixes the `LL_HISTORY_DB` divergence) and renamed without `.lock`; doctor line folded into `_history_db_check`. Opus's dissent: a one-byte count is defensible if a human compares two snapshots, so the timestamped record is cheap insurance rather than strictly required. Rejected: skipping migrations on the telemetry path (breaks fresh-db creation).

## Verification Notes

_Verified 2026-10-03 by `/ll:verify-issues --auto`._

Verdict at time of check: **DEP_ISSUES** (the backlink fix below was applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Fixed:** ENH-3698 lists ENH-3679 in `blocked_by` (and the Scope Boundary note states that edge), but this issue's `blocks:` frontmatter listed only ENH-3683. Added `ENH-3698` (MISSING_BACKLINK).
- **Informational:** ENH-3678 is `done` (satisfied edge). ENH-3683 is `deferred` and still correctly blocked by this issue. ENH-3680 is `cancelled`, so the "independent remote hook spool" references in Scope Boundaries and Related are historical, not a live sibling.
- **Verified accurate:** `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` (`schema.py:1525-1538`); `schema.connect` takes no `busy_timeout_ms` yet; `_apply_migrations` steady-state fast path takes no write lock; `cli_event_context` enter/exit warning text (`writers.py:617`, `:647`) and the pinning tests (`test_session_store_writers.py:562`/`:595`, `test_cli_queue.py:517`); `_history_db_data` reads `Path.cwd() / DEFAULT_DB_PATH` (`doctor.py:520`); `_history_db_check` exists (`doctor.py:556`); `.ll/*.lock` in `.gitignore:114` and `init/writers.py:108`; chokepoint gate test and `libsql.py` `warn_once` exist; `Backend.connect` protocol has no timeout kwarg; `HistorySuppressed` exists (`backend.py:64`); `ll-verify-evidence` clean. No decisions-log conflicts found; proposal-vs-code trace (B6) found no unsound mechanism.
- **Graph:** `ll-code` provider=`codegraph`, freshness=`fresh` (status only; no graph query was needed).

## Status

**Open** | Created: 2026-09-30 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Ordering vs ENH-3698: ENH-3679 lands before ENH-3698 (ENH-3698 is `blocked_by` this issue). The "after or with ENH-3698" wording is superseded for ENH-3698 — "with" is impossible under the `blocked_by` edge. Sequencing against ENH-3658 is unchanged.

## Session Log
- `/ll:verify-issues` - 2026-10-03T17:10:47 - `aa9ffd51-8240-4480-856c-316b8f27306a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:01 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:59 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
