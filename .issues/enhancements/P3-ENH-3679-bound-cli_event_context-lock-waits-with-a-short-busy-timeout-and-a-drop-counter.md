---
id: ENH-3679
type: ENH
title: Bound cli_event_context lock waits with a short busy timeout and a drop counter
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
completed_at: '2026-10-03T17:52:50Z'
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
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3679: Bound cli_event_context lock waits with a short busy timeout and a drop counter

## Summary

Make `cli_event_context` resilient to a held local SQLite write lock: use a short **per-lock-wait** busy timeout (250 ms on every telemetry connection, so steady-state entry and exit each wait <= 250 ms) via an explicit `busy_timeout_ms` parameter, and count every dropped event in a sidecar drop counter surfaced by `ll-doctor`, so loss is measurable. The bounded spool that would retain dropped events is **deferred to ENH-3683**, to be built only if measured drops justify it. Split out of ENH-3666 after its 2026-09-29 Opus review; rescoped 2026-09-30. Detached from EPIC-3693 2026-10-02 (local-store fix; `relates_to` only).

## Current Behavior

`cli_event_context` can wait `_BUSY_TIMEOUT_MS` (5000 ms) at entry and again at exit, then drop the event or its completion data under a held lock. Observed with a detached `--rebuild` holding the lock, but any long local writer can cause it.

## Expected Behavior

`cli_event_context` bounds each SQLite lock wait at **250 ms**: every telemetry connection (the `ensure_db` setup connection and the `connect` connection kept open across the command body) is opened with `timeout=0.25` and `PRAGMA busy_timeout = 250`. `busy_timeout` is a fixed per-connection property, not a depleting budget, so the exit UPDATE on the same connection gets the same 250 ms with no re-arming, and the command body never consumes it. In steady state (migrated WAL store) the INSERT and the exit UPDATE are the **only** statements that lock-wait (measured 2026-10-03: under a held `BEGIN IMMEDIATE`, `PRAGMA journal_mode = WAL` and the `meta` version read return in 0 ms; the INSERT waits 285 ms at `busy_timeout=250`), so entry and exit each wait <= 250 ms. This bounds lock waiting, not arbitrary filesystem or migration CPU time. A timed-out event/completion is dropped best-effort and counted in an `.ll/` sidecar; `ll-doctor` reports the count. Non-telemetry writers keep 5000 ms.

**Drop-count rule (defines "exactly once per dropped event"):** if the entry was dropped, the exit skips entirely with **no second count**; if the entry succeeded and the exit was dropped, **one completion drop** is counted. A single command therefore adds at most one to the counter.

**What counts as a drop (revised 2026-10-03):** only a lock failure — a `sqlite3.Error` whose `getattr(exc, "sqlite_errorcode", None)`, masked `& 0xFF`, is `sqlite3.SQLITE_BUSY`/`sqlite3.SQLITE_LOCKED`. Use `getattr`, never `exc.sqlite_errorcode`: a hand-constructed `sqlite3.OperationalError` has **no** such attribute (verified on 3.12), and an `AttributeError` raised inside the `except` handler would escape the best-effort contract. Classification is **errorcode-only** — no `"database is locked"` message fallback. `HistorySuppressed` (remote), disk-full, corruption, permission errors, and errorcode-less errors keep their existing handling and are **not** counted, so the ENH-3683 decision metric stays pure.

**Timeout mechanics (revised 2026-10-03; supersedes the shared-deadline design):**
- **No shared monotonic deadline, no "exhausted budget" drop class, no exit-phase pragma re-issue.** Steady-state setup never lock-waits (measured above), so a deadline threaded across setup steps only mattered on a pending-migration store; the per-connection 250 ms covers that case within a documented worst case.
- Thread `busy_timeout_ms` through `connect` → `ensure_db` → `_configure_connection`, and pass `timeout=busy_timeout_ms / 1000` to **both** `sqlite3.connect` calls (`ensure_db` and `connect`): the 5.0 s connect default would otherwise survive a swallowed pragma failure, and `ensure_db` opens its own connection.
- Migrations stay on the telemetry path (skipping them would break fresh-db creation).
- **Worst case (documented):** up to K x 250 ms with K <= 3 lock waits (`journal_mode` conversion on a non-WAL store, migration `BEGIN IMMEDIATE`, INSERT) — only on a non-WAL store with a pending migration under contention, i.e. at most once per schema bump. The 250 ms per-wait figure is the steady-state contract, not an absolute per-phase bound.
- **Log level:** a counted lock drop logs at `debug`, not `warning` — a 250 ms bound under ordinary `ll-parallel` contention would otherwise print a stderr line on every command. Other failures keep `warning`.
- **Documented limits:** WAL auto-/close-time checkpoint I/O and VACUUM writers fall outside the bound; SQLite's internal `walTryBeginRead` WAL_RETRY loop (checkpointer holding read-mark 0 with all read-marks contended) is not governed by `busy_timeout` — normally microseconds, pathologically ~10 s — documented, not engineered around; the read->write upgrade hazard (busy handler skipped) does not apply because no read transaction is open when the INSERT starts; a `kill -9` of the command leaves a row with NULL `exit_code` (unchanged).

## Scope Phasing (2026-09-30 Opus review)

- **This issue (former Phase 1):** a 250 ms per-lock-wait timeout for `cli_event_context` via an **explicit `busy_timeout_ms` parameter** threaded through `schema.connect` → `ensure_db` → `_configure_connection` (not a contextvar; `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` today), plus the sidecar drop counter. Set the timeout at `sqlite3.connect(timeout=...)` time on both connections; shared `connect()` and other writers keep `_BUSY_TIMEOUT_MS`.
- **ENH-3683 (deferred, former Phase 2):** the immutable-file spool and idempotent drain. Its motivating lock holder (a multi-minute detached `--rebuild`) is largely removed by ENH-3678; activate it only if the drop counter, measured after ENH-3678 ships, shows material loss.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` entry and exit handling (`_connect_telemetry` gains the kwarg); `session_store/schema.py` `connect`/`_configure_connection` (explicit `busy_timeout_ms`); the drop-counter sidecar and its `ll-doctor` line. `skill_event_context` and other writers are out of scope.
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`). The remote branch of `connect()` accepts and ignores `busy_timeout_ms`; the `Backend` protocol signature is unchanged.
- **Doctor surfaces (three, one source):** `_history_db_data()` feeds the `--json` `history_db` key (`doctor.py:~1740`), the text `_print_history_db_section()` (`~1858`), and the registered `_history_db_check` (`~556`). Compute drop stats once in a helper (e.g. `_cli_event_drops_data()`), attach it to `_history_db_data()`'s dict as `cli_event_drops`, print one sub-line in the text section, and emit the informational `CheckResult` from `_history_db_check` — so JSON, text, and check output never disagree. Skip it entirely under a remote backend (no local sidecar). The 7-day `cli_events` count is a full scan (no `ts` index) but measured 25 ms on a 10 GB / 474k-row store — no index needed.
- **Sidecar path:** derive it from the *resolved* store path (honoring `LL_HISTORY_DB` / `history.db_path`). `cli/doctor.py:_history_db_data` currently reads `Path.cwd() / DEFAULT_DB_PATH`; the doctor line must use the same resolver as the writer, or an override silently reports zero drops.
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread; released via `threading.Event`, not sleeps; threads rather than subprocesses to avoid xdist worker-timeout hazards), asserting elapsed lock-wait time within a pinned **[200 ms, 2000 ms]** window for both entry and exit — the lower bound proves the wait actually happened (SQLite builds without `HAVE_USLEEP` make a sub-1000 ms `busy_timeout` fail instantly); the ~2000 ms ceiling absorbs xdist scheduling load while still excluding the 5000 ms default. Cover the drop-count rule (entry dropped -> exit skipped, one count; entry ok + exit dropped -> one completion count); non-lock errors and `HistorySuppressed` do not count; drop counter increments once per dropped event and `ll-doctor` reports it; other writers keep 5000 ms; remote path unchanged.
- **Test-first rewrite of the lock-fake tests.** Errorcode-only classification means a bare `sqlite3.OperationalError("database is locked")` fake is a **non-lock** error. Add a shared helper `_locked_error()` that builds the error and sets `sqlite_errorcode = sqlite3.SQLITE_BUSY` (the attribute is settable), and use it in the `cli_event_context` lock tests: `test_session_store_writers.py` enter (~551) and exit (~587) fakes, and `test_cli_queue.py:~474`; flip their assertions to `debug`. Repurpose the subprocess stderr test `test_cli_queue.py::test_locked_history_db_stderr_is_one_line_no_traceback` (~487-517) to a **non-lock** error (e.g. errorcode `SQLITE_IOERR`, still exactly one clean stderr line via `logging.lastResort`), and add a lock-variant asserting **zero** stderr lines. Leave the queue-store fakes (`test_cli_queue.py:424/442/558`, `test_feat_queue_mcp_tools.py`) and other-writer `boom` fakes (`test_hook_*`, `test_session_store_writers.py:2259/3321/3401/3466`) untouched — those writers are out of scope.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape; `ll-doctor` drop-count line. **Sequencing:** the drop-count line is an informational `CheckResult` added **inside the existing `_history_db_check`** (`cli/doctor.py`), not a new registered check, so the `ll-doctor` check list/count in `docs/reference/CLI.md` is unchanged and the shared-surface conflict with ENH-3698 (rebuild-pending check) and ENH-3658 (`--trim` remote guard) reduces to a doc-line edit; still land in sequence, never as parallel branches.

## Program Design

### Signatures

- `connect(path=DEFAULT_DB_PATH, *, busy_timeout_ms: int | None = None)` (`little_loops.session_store.schema`) — `None` keeps `_BUSY_TIMEOUT_MS`; `cli_event_context` passes the short value. The remote branch accepts and ignores it.
- `ensure_db(path=DEFAULT_DB_PATH, *, busy_timeout_ms: int | None = None) -> Path` — same default; forwards to its own `sqlite3.connect(timeout=...)` and `_configure_connection`.
- `_configure_connection(conn, busy_timeout_ms: int = _BUSY_TIMEOUT_MS) -> None` — the pragma value becomes the parameter.
- `_is_lock_error(exc: BaseException) -> bool` — `(getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}`; never raises.
- `record_dropped_cli_event(db: Path | str, kind: Literal["E", "X"]) -> None` — counts a drop without a database write or blocking user-space lock; never raises. `E` = entry (whole event lost), `X` = completion (row kept, `exit_code`/`duration_ms` lost). **Counter spec (revised 2026-10-03):** open `<resolved-db>.cli-event-drops` with `O_CREAT | O_WRONLY | O_APPEND`, append one fixed-width 12-byte record `<10-digit epoch seconds><E|X>\n` with a single `os.write`, and close. A sub-`PIPE_BUF` `O_APPEND` write is atomic on a local filesystem, so concurrent processes cannot interleave. No read-modify-write or `flock`: a contended counter must not replace the SQLite stall. Doctor parses whole 12-byte records, ignores a malformed/torn tail (possible on ENOSPC), and reports **drops in the last 7 days split by kind, plus the ratio against `cli_events` rows** — a timeless lifetime count cannot decide whether ENH-3683 is warranted, and the record format cannot change after rollout. `.ll/*.lock` is gitignored today, but the suffix is misleading for a non-lock file, so the sidecar drops it; add `.ll/*.cli-event-drops` to `.gitignore` and the `ll-init` writer list (`init/writers.py`). Counts are exact when append succeeds; an unwritable/full filesystem fails softly and cannot guarantee an increment. No size cap needed at 12 B/drop; doctor may note a large file.
- **Threading the timeout:** a plain keyword passed down `connect` → `ensure_db` → `_configure_connection`, applied at `sqlite3.connect(timeout=...)` and `PRAGMA busy_timeout` on both connections (see Timeout mechanics). No deadline object, no remaining-budget arithmetic, no exit-phase re-issue: the open connection keeps its 250 ms across the command body, so a body longer than 250 ms still leaves the exit UPDATE its full 250 ms. Ordinary callers retain the existing timeout. Entry failure skips all exit work. Existing `connect` monkeypatches all accept `**kwargs`, so the new keyword breaks none; no raw `sqlite3.connect(` outside the existing chokepoint.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → `_connect_telemetry` → `connect(busy_timeout_ms=250)` → `ensure_db(busy_timeout_ms=250)` → INSERT / exit UPDATE → lock failure (`_is_lock_error`) → `record_dropped_cli_event`; `ll-doctor` `_history_db_check` reads the sidecar.

## Scope Boundaries

- **In scope**: a short per-phase timeout budget for `cli_event_context` and the drop counter with its `ll-doctor` line.
- **Out of scope**: the spool and drain (ENH-3683), other telemetry writers, `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` remote hook spool (ENH-3680, no coupling), remote-backend CLI telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small - timeout plumbing, a sidecar counter, one doctor line
- **Risk**: Low - no new durability surface; drops are counted, not retained
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE` on a migrated WAL store, each lock wait is capped at 250 ms (value pinned) at both entry and exit; observed entry and exit lock-wait latency each fall in the pinned **[200 ms, 2000 ms]** window (lower bound proves the wait occurred). Both `sqlite3.connect` calls on the telemetry path (`ensure_db` and `connect`) receive `timeout=0.25`. Other writers keep 5000 ms. The arbitrary command body is excluded from these measurements.
- [ ] A command body longer than 250 ms does not reduce the exit wait: the exit UPDATE still waits ~250 ms under a held lock.
- [ ] Only lock failures (`sqlite_errorcode & 0xFF` in `SQLITE_BUSY`/`SQLITE_LOCKED`, read via `getattr`) count as drops; `HistorySuppressed`, disk-full, corruption, permission errors, and errorcode-less errors do not, and classifying an errorcode-less `sqlite3.OperationalError` never raises. Each dropped event writes exactly one record per the drop-count rule (entry dropped -> exit skips, no second record; entry ok + exit dropped -> one `X` record) and `ll-doctor` reports last-7-day counts split by kind plus the ratio vs `cli_events` rows, using the same resolved sidecar path as the writer (honors `LL_HISTORY_DB`).
- [ ] Counted lock drops log at `debug`; non-lock failures keep `warning`. Test-first: the `cli_event_context` lock-fake tests use a `_locked_error()` helper (errorcode `SQLITE_BUSY`) and expect `debug`; the subprocess stderr test is repurposed to a non-lock error (exactly one clean stderr line) plus a lock-variant asserting zero stderr lines.
- [ ] Concurrent threads append N known drops and doctor reports N; a held `flock` on the sidecar does not stall the append; a torn tail record is ignored; sidecar write failure never escapes.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path); `busy_timeout_ms` is accepted and ignored there.
- [ ] The doctor line is an informational `CheckResult` inside `_history_db_check` (no change to the registered-check count) and never affects the exit code.
- [ ] Existing telemetry-writer tests pass; docs describe the 250 ms per-lock-wait timeout, the K x 250 ms (K <= 3) migrating-store worst case, the drop counter, and documented limits (checkpoint/VACUUM and the `walTryBeginRead` retry loop outside the bound).
- [ ] ENH-3683 (spool) stays deferred unless the measured drop count justifies activating it.

## Related

- ENH-3666, ENH-3678; ENH-3683 (deferred spool, former Phase 2); ENH-3680 (independent remote hook spool; no envelope coupling).

## Pre-Implementation Review (2026-10-03, Fable second opinion)

_Reviewed with `/ll:advise` (claude-fable-5-1, confidence 0.88). Supersedes parts of the earlier 2026-10-03 Opus revision._

- **Dropped the shared monotonic deadline, the "exhausted budget" drop class, the exit-phase `PRAGMA busy_timeout` re-issue, and the `<= 0` pragma guard.** Empirical probe: under a held `BEGIN IMMEDIATE` on a WAL store, `PRAGMA journal_mode = WAL` and the `meta` version read return in 0 ms; only the INSERT lock-waits (285 ms at 250). `busy_timeout` is a non-depleting per-connection property, so with no deadline the re-issue is dead code. Replaced with a per-lock-wait 250 ms bound and a documented K x 250 ms (K <= 3) migrating-store worst case.
- **Resolved the `ensure_db` contradiction** flagged by the prior confidence check: `busy_timeout_ms` is now threaded through `ensure_db` (it opens its own `sqlite3.connect` with the 5 s default), and both connects get `timeout=`.
- **Fixed a spec bug:** `exc.sqlite_errorcode` raises `AttributeError` on a hand-constructed `sqlite3.OperationalError`, which would escape the best-effort handler. Classifier now uses `getattr`, errorcode-only (no message fallback — Fable: it would exist only to serve tests). Lock-fake tests get a `_locked_error()` helper; the subprocess stderr test is repurposed to the non-lock case plus a zero-stderr lock variant.
- Timing window ceiling widened 1000 -> 2000 ms for xdist load; added the `walTryBeginRead` WAL_RETRY loop to the documented limits; specified the three doctor surfaces share one data helper.
- **Fable dissent:** a message fallback would be harmless (SQLite error strings are fixed English); keeping the exit re-issue is defensible belt-and-braces but would mislead readers into thinking the timeout depletes.

## Confidence Check Notes

_Re-scored 2026-10-03 by `/ll:confidence-check` after the Fable pre-implementation review (replaces the earlier 2026-10-03 note: readiness 95, outcome 63)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE (at/above `outcome_threshold` 65)

Prior concerns, now resolved in the issue body: the `ensure_db` setup connection is bounded (`busy_timeout_ms` threaded through `ensure_db`, `timeout=` on both connects); `PRAGMA journal_mode = WAL` measured lock-free on a WAL store under a held write lock (its non-WAL conversion wait is inside the documented K x 250 ms worst case); the shared deadline and exit re-arm are removed (Complexity depth Moderate -> Local); errorcode classification now uses `getattr` with `& 0xFF`; timing-window ceiling widened to 2000 ms. Residual, non-blocking: `cli_event_context` wraps ~52 `ll-*` entry-point modules, so a mistake in the bound or the `debug` log level is visible everywhere (Change surface 10/25); mitigated by the default-preserving keyword and the real-lock timing tests.

_Revised 2026-10-03 after a pre-implementation review with an Opus second opinion (`/ll:advise`, confidence 0.82)._ Changes: exit phase re-issues the busy-timeout pragma; counter moved from a one-byte count to a 12-byte timestamped, kind-tagged record (the ENH-3683 decision needs a windowed rate, not a lifetime count); explicit drop definition (lock errors only); lock drops log at `debug`; timing window pinned to [200 ms, 1000 ms]; sidecar path derived from the resolved store (fixes the `LL_HISTORY_DB` divergence) and renamed without `.lock`; doctor line folded into `_history_db_check`. Opus's dissent: a one-byte count is defensible if a human compares two snapshots, so the timestamped record is cheap insurance rather than strictly required. Rejected: skipping migrations on the telemetry path (breaks fresh-db creation).

## Verification Notes

_Verified 2026-10-03 by `/ll:verify-issues --auto`._

Verdict at time of check: **DEP_ISSUES** (the backlink fix below was applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Fixed:** ENH-3698 lists ENH-3679 in `blocked_by` (and the Scope Boundary note states that edge), but this issue's `blocks:` frontmatter listed only ENH-3683. Added `ENH-3698` (MISSING_BACKLINK).
- **Informational:** ENH-3678 is `done` (satisfied edge). ENH-3683 is `deferred` and still correctly blocked by this issue. ENH-3680 is `cancelled`, so the "independent remote hook spool" references in Scope Boundaries and Related are historical, not a live sibling.
- **Verified accurate:** `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` (`schema.py:1525-1538`); `schema.connect` takes no `busy_timeout_ms` yet; `_apply_migrations` steady-state fast path takes no write lock; `cli_event_context` enter/exit warning text (`writers.py:617`, `:647`) and the pinning tests (`test_session_store_writers.py:562`/`:595`, `test_cli_queue.py:517`); `_history_db_data` reads `Path.cwd() / DEFAULT_DB_PATH` (`doctor.py:520`); `_history_db_check` exists (`doctor.py:556`); `.ll/*.lock` in `.gitignore:114` and `init/writers.py:108`; chokepoint gate test and `libsql.py` `warn_once` exist; `Backend.connect` protocol has no timeout kwarg; `HistorySuppressed` exists (`backend.py:64`); `ll-verify-evidence` clean. No decisions-log conflicts found; proposal-vs-code trace (B6) found no unsound mechanism.
- **Graph:** `ll-code` provider=`codegraph`, freshness=`fresh` (status only; no graph query was needed).

## Resolution

**Completed** 2026-10-03 via `/ll:manage-issue`. `busy_timeout_ms` is threaded through `schema.connect` -> `ensure_db` -> `_configure_connection` (both `sqlite3.connect` calls get `timeout=`); `cli_event_context` uses 250 ms; lock-only drops (`_is_lock_error`, errorcode-only) append a 12-byte record to `<db>.cli-event-drops` (`record_dropped_cli_event`); `ll-doctor` reports 7-day counts and ratio from `_history_db_check`/`_history_db_data`. `.gitignore` and `ll-init` entries added; API.md and HISTORY_SESSION_GUIDE.md updated. Tests: `TestCliEventLockBound`, `TestCliEventDrops`, repurposed `test_cli_queue` stderr tests. ENH-3683 stays deferred.

## Status

**Open** | Created: 2026-09-30 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Ordering vs ENH-3698: ENH-3679 lands before ENH-3698 (ENH-3698 is `blocked_by` this issue). The "after or with ENH-3698" wording is superseded for ENH-3698 — "with" is impossible under the `blocked_by` edge. Sequencing against ENH-3658 is unchanged.

## Session Log
- `/ll:manage-issue` - 2026-10-03T17:52:50 - `05c63175-ed06-4f22-8685-47cf365c9c7c.jsonl`
- `/ll:ready-issue` - 2026-10-03T17:35:34 - `1a640d13-c917-485b-b40b-78ea13b6f3c3.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:32:11 - `96a50b45-4dca-4ccc-b651-5f8f8b336c88.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:15:02 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`
- `/ll:verify-issues` - 2026-10-03T17:10:47 - `aa9ffd51-8240-4480-856c-316b8f27306a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:01 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:59 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
