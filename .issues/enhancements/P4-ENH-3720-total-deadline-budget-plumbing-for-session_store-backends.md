---
id: ENH-3720
type: ENH
title: Total-deadline budget plumbing for session_store backends
priority: P4
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:29:51Z'
relates_to:
- ENH-3682
- FEAT-3711
- FEAT-3721
- EPIC-3710
learning_tests_required:
- sqlite3
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3720: Total-deadline budget plumbing for session_store backends

## Summary

Add an opt-in, connection-lifetime monotonic deadline to strict read-only history connections. Local SQLite queries and remote libSQL access verification, queries and response reads share the caller's absolute expiry. ENH-3682 is the first concrete consumer and owns best-effort prepatch integration; this issue owns the reusable deadline and backend/transport enforcement. v1 `ll-next` remains local-SQLite only, so this issue is not a prerequisite of EPIC-3710.

## Current Behavior

- `LibsqlBackend.connect_readonly` accepts `timeout` for compatibility but ignores it; its Hrana client uses a 10-second per-request timeout. Cold access verification and the query start separate budgets.
- `HranaClient._read` checks time between `resp.read(65536)` calls. A buffered read can receive a trickle for longer than its socket timeout. `getresponse()` can also detach the connection's socket for connection-closing responses, leaving `conn.sock` unavailable while the response still owns its reader.
- `SqliteBackend.connect_readonly` returns a raw SQLite connection with a lock-wait timeout and no query cancellation. Query work can continue in cursor fetching and iteration after `execute()` returns.
- `history_reader._base._connect_readonly` catches opening failures only and calls `open_history_readonly(..., ensure=True)`. It cannot catch later query/fetch failures, and no deadline is passed through that seam today.

## Expected Behavior

- One absolute deadline governs the entire lifetime of an opted-in connection. Opening, cold verification and all subsequent read statements consume that same budget; an expired connection cannot start another query or request.
- SQLite cancellation covers execution, fetching and iteration. Remaining-budget lock timeouts are refreshed before subsequent SQL statements, rather than frozen at connection creation.
- Remote verification and query requests use the same expiry, capped by the client's existing per-request timeout. Stalled or trickling headers/body cannot keep an opted-in socket operation alive beyond its effective deadline plus documented scheduling tolerance.
- Expiry raises `HistoryUnavailable` locally and `HranaUnavailable` remotely, including expiry during fetching. This is a backend exception contract; reader fallback is ENH-3682's separate responsibility.
- Connections opened without a deadline retain existing timeout, exception, request-count and cache behavior. Ordinary SQLite connections install no new handler or adapter.
- Strict read-only connections do not use `connect_telemetry` or file-backed verification/unreachable caches. The existing in-process verification cache remains allowed.

## Motivation

Optional history reads need a shared latency budget rather than a fresh allowance per network request or SQL statement. Separating this primitive from ENH-3682 avoids implementing conflicting deadline mechanisms while keeping reader fallback and marker policy independent.

## Proposed Solution

Use a frozen `Deadline` value with an absolute `time.monotonic()` expiry, float-second `remaining()` and `expired()` helpers. Add keyword-only `deadline=None` to the `Backend` protocol, both providers' `connect_readonly` methods and the module-level `connect_readonly` wrapper. Preserve the existing meaning of `timeout`: SQLite busy-wait seconds; remote callers use the optional deadline in addition to the existing Hrana client cap.

For SQLite, use an opt-in `sqlite3.Connection` factory and cursor adapters only on deadline-bound connections. Check expiry before opening or starting a statement, install a connection-owned progress handler for its lifetime, and refresh the busy timeout to the smaller of the original lock cap and remaining budget before subsequent statements. Connection shortcuts and explicitly created cursors must enforce the same contract. Keep the handler active through `fetchone`, `fetchmany`, `fetchall` and iteration; clearing it when `execute()` returns would leave most query work unbounded. Translate deadline-triggered interrupts and deadline-exhausted lock waits to `HistoryUnavailable`, preserving the original exception as the cause; unrelated SQLite errors retain their prior taxonomy. The handler ends with connection closure. Reuse after expiry is intentionally refused; open a fresh unbounded connection for unrelated work.

For libSQL, construct a dedicated deadline-bound Hrana client for the read-only connection. Store the immutable deadline on that client so lazy `check_access` -> `read_state` -> `batch` and the data query automatically share it, without adding per-call keywords to every schema helper or mutating a shared client. Keep verification lazy. Recheck expiry before each statement and POST, including cache-hit paths. Each request's effective expiry is the earlier of the caller's expiry and the current request's existing timeout cap.

Enforce that expiry through connect/TLS, request send, header reads and body reads. Retain access to the response's live socket when `getresponse()` detaches `conn.sock`; close both response and connection on every exit. Deadline checks between large buffered reads alone are insufficient: use reads or cancellation that can interrupt a continuing trickle within one body read or header parse. If an interrupt watchdog is needed, it may only cancel owned I/O and must be stopped before returning; do not run queries in abandoned background workers.

The deadline is not a universal hard wall-time guarantee: synchronous DNS resolution, JSON encoding/decoding, SQLite user-defined functions and filesystem stalls are not preempted by socket timeouts or VM progress callbacks. Document these limits and the progress-handler instruction granularity. Check expiry before further I/O and before reporting successful completion after synchronous work. Writes are outside v1; abandoning a future remote write cannot establish whether it committed, so unknown outcomes must not be blindly retried.

## Scope Boundaries

- **In scope:** shared monotonic `Deadline`; strict read-only connection plumbing; local execution/fetch/lock enforcement; remote lazy verification and socket enforcement; default-off test-harness fault controls; backend API and timeout documentation.
- **Out of scope:** writable `connect`, `connect_telemetry`, write transactions, `ensure_schema`, migrations, automatic retries, existing telemetry caches/markers and the ENH-3679 CLI-event budget.
- **Owned by ENH-3682:** `open_history_readonly`/`history_reader._base._connect_readonly` best-effort seam, remote readonly telemetry policy, prepatch call sites, schema-ensure skipping and open/mid-query `None` fallback. ENH-3682 depends on this issue and consumes its primitive; do not add a parallel reader seam here.
- **Also out of scope:** switching ll-next to remote reads, broad reader rewrites, new configuration/dependencies, and changing no-deadline defaults.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/deadline.py` (new file) — frozen deadline value; no database opens in this module.
- `scripts/little_loops/session_store/backend.py` — three `connect_readonly` declarations, wrapper forwarding, and opt-in SQLite connection/cursor enforcement. Keep raw SQLite opens in this existing chokepoint.
- `scripts/little_loops/session_store/libsql.py` — `LibsqlBackend.connect_readonly`, client construction and read-only connection expiry checks; preserve writable/telemetry defaults.
- `scripts/little_loops/session_store/hrana.py` — optional immutable client deadline; request/socket/response cleanup and enforcement.
- `scripts/little_loops/session_store/__init__.py` — export `Deadline` for downstream callers, including ENH-3682.
- `scripts/tests/hrana_stub.py` — default-off per-request delays and stalled/trickling header/body controls; retain existing fixture behavior.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/session_store/remote_schema.py` — lazy `check_access`/`read_state` uses the bound client; public signatures, writable ensure and migrations stay unchanged.
- `scripts/little_loops/session_store/lifecycle.py` — `rebuild_needed(timeout=_REBUILD_NEEDED_TIMEOUT)` retains its current timeout semantics; no new caller opt-in here.
- `scripts/little_loops/session_store/backend.py` and `scripts/little_loops/history_reader/_base.py` — existing high-level reader openers remain unchanged here; ENH-3682 owns integration and catches failures at both open and query boundaries.
- `scripts/little_loops/cli/doctor.py` — existing independently configured probe clients retain their timeout defaults.

### Similar Patterns

- Keyword-only optional settings use `None` to preserve defaults, as in `schema.connect` and telemetry connection forwarding.
- Keep expiry within the existing `HistoryError` taxonomy. A local adapter must cover cursor work; wrapping only the connection opener does not translate later interrupts.
- Extend the sqlite3 learning proof for progress-handler persistence, interrupt errors, connection/cursor factories and fetch-time work before relying on these mechanisms. Existing `learning_tests_required: [sqlite3]` remains in force.

### Tests

- `scripts/tests/test_enh3720_session_store_deadline.py` (new file) — backend-boundary cold/warm/expired tests, connection-lifetime semantics, fetch/iteration cancellation and lock waits after earlier budget consumption.
- `scripts/tests/test_hrana_client.py` — stalled/trickling headers/body, effective request cap, connection-closing responses, cleanup and no-deadline defaults.
- `scripts/tests/test_libsql_backend.py` and `scripts/tests/test_remote_schema.py` — lazy read-only verification, strict cache policy and request counts.
- `scripts/tests/test_session_store_backend.py` and `scripts/tests/test_enh3678_rebuild_derive_gate.py` — deadline keyword/default parity across all four declarations, wrapper forwarding and legacy timeout behavior.
- `scripts/tests/test_session_store_schema.py` and `scripts/tests/test_history_store_chokepoint_gate.py` — exported names and database-opening chokepoint remain valid.
- Use fake clocks/transports for exact budget accounting. Mark real timing cases `no_parallel` and use a named scheduling tolerance smaller than the tested budget, so two complete budgets or a prolonged trickle cannot pass. Do not substitute the existing 3-5x timeout allowances for total-deadline assertions.

### Documentation

- `docs/reference/API.md` — exported `Deadline`, read-only signatures, connection lifetime, expiry errors and limits; refresh the stale future-libSQL introduction.
- `docs/reference/CONFIGURATION.md` — distinguish existing per-request/telemetry caps from an optional caller deadline without changing documented no-deadline defaults.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — link to timeout documentation and describe user-visible failure behavior; use end-user language and no source/test paths.
- `docs/ARCHITECTURE.md` — mention the optional backend deadline; preserve existing `_connect_readonly` wiring references.

### Configuration

No new option, schema migration or dependency. Existing telemetry timeout and marker semantics are unchanged; ENH-3682 uses that timeout to construct the new deadline.

## Program Design

### Types

- `Deadline` (new frozen dataclass): `expires_at: float`, an absolute monotonic time in seconds.
- `_DeadlineConnection` (proposed new `sqlite3.Connection` subclass) and `_DeadlineCursor` (proposed new `sqlite3.Cursor` subclass): preserve driver compatibility while enforcing the opted-in deadline through statements and cursor consumption.
- `HranaClient` holds an optional immutable deadline on a dedicated client instance; no mutable per-request deadline on a shared client.

### Signatures

- `Deadline.after(seconds: float) -> Deadline`
- `Deadline.remaining() -> float` — floored at zero.
- `Deadline.expired() -> bool`
- `Backend.connect_readonly(target: Path | HistoryTarget, *, timeout: float = 5.0, deadline: Deadline | None = None) -> sqlite3.Connection` — mirror keyword/default semantics in `SqliteBackend` and the module wrapper; `LibsqlBackend` keeps its existing `LibsqlConnection` return type.
- `HranaClient.__init__(url: str, auth_token: str | None = None, *, timeout: float = 10.0, deadline: Deadline | None = None) -> None` — proposed additive constructor keyword; existing statement/batch signatures stay unchanged.
- `LibsqlConnection.execute(sql: str, parameters: Sequence[Any] = ()) -> LibsqlCursor` — existing signature, lazy verification and query use the same bound client.

### Call Path

Remote: module-level `connect_readonly` -> `LibsqlBackend.connect_readonly` (no HTTP request) -> caller's `LibsqlConnection.execute` -> `_guard` -> `remote_schema.check_access` -> `remote_schema.read_state` -> `HranaClient.batch` -> `_post`; the data statement then uses `HranaClient.execute` -> `_post` -> `_read` with the same caller expiry.

Local: module-level `connect_readonly` -> `SqliteBackend.connect_readonly` -> opted-in connection/cursor factory -> SQL execution and cursor fetch/iteration with a persistent progress handler and remaining-budget lock timeout.

## Implementation Steps

1. Extend the sqlite3 learning proof, add/export the deadline value and align the read-only connection signatures.
2. Add opt-in local connection/cursor enforcement, fetch-time exception translation and per-statement lock budgeting.
3. Bind the remote client deadline across lazy verification and data reads; enforce socket expiry and cleanup, including trickling and connection-closing responses.
4. Add deterministic accounting tests and a small serial real-I/O matrix; update docs and run the full suite. Keep reader/marker integration in ENH-3682.

## Impact

- **Priority:** P4 — reusable infrastructure with ENH-3682 as the first consumer; not on the ll-next critical path.
- **Effort:** Medium — two backends, cursor adapters and transport cancellation tests.
- **Risk:** Medium — shared backend code and timing-sensitive behavior; changes are opt-in.
- **Breaking Change:** No; bounded connections intentionally fail after their caller-specified expiry.

## Acceptance Criteria

- [ ] All four `connect_readonly` declarations accept and forward `deadline=None` with consistent keyword/default semantics; existing `timeout=` callers pass unchanged regression tests.
- [ ] A bound remote connection shares one absolute expiry across cold verification and data queries: cold success makes two POSTs, warm success one, expiry before dispatch zero, and verification consuming the budget prevents the second POST. Fake-clock tests assert the effective cap without resetting the caller budget.
- [ ] Serial socket tests for stalled headers/body, a continuing trickle within a buffered read/header parse, and connection-closing responses finish within effective expiry plus a named tolerance smaller than the tested budget; response/connection resources are closed on success and failure.
- [ ] Local tests cover expired-before-open and expired-before-statement rejection, execution cancellation, `fetchone`/`fetchmany`/`fetchall`/iteration cancellation through both connection shortcuts and explicit cursors, and lock waits after prior budget consumption.
- [ ] Deadline-triggered local interrupts/lock expiry raise `HistoryUnavailable` with the SQLite cause preserved; remote expiry raises `HranaUnavailable`. Unrelated SQLite failures keep their existing exception behavior. These are backend tests, not `_connect_readonly` reader-fallback tests.
- [ ] Every read on an expired bound connection fails, including small queries/cache-hit paths; closing it releases owned cancellation state. A separate no-deadline connection performs long reads without a new handler, shortened timeout or changed exception policy.
- [ ] Strict remote reads refuse writes before any POST and do not invoke `connect_telemetry` or write file-backed cache/marker files; in-process verification reuse remains allowed. No request starts after expiry and no abandoned query worker continues after timeout.
- [ ] Writable connections, telemetry defaults, schema ensure/migrations and existing no-deadline request counts remain unchanged in regression tests; existing HranaStub users retain default behavior.
- [ ] API, timeout and history-guide documentation specifies the connection lifetime, exception contract, scheduling/VM granularity and DNS/CPU/UDF/filesystem limits; `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-10-04 | Priority: P4

## Review Notes

Revised 2026-10-04 after code review, targeted local reproductions and `/ll:advise` with Opus. An 80 ms Hrana timeout took about 205 ms under a slow trickle; clearing a SQLite handler after `execute()` allowed fetching to outlive a 30 ms deadline. These observations motivate the transport and fetch-time acceptance criteria. Earlier appended research/open decisions are consolidated above; the old persisted verification verdict/evidence was cleared because it described the previous draft, not this revised contract.

## Session Log
- `/ll:confidence-check` - 2026-10-04T19:40:08 - `e588d5e7-f6f0-45f7-81e4-8c0cef455170.jsonl`
- `/ll:verify-issues` - 2026-10-04T03:10:04 - `2d651013-b69a-457e-aeca-c0e6f7d1781c.jsonl`
- `/ll:verify-issues` - 2026-10-04T03:08:18 - `676efbca-b77e-4cfe-b025-9bbe4d011d98.jsonl`
- `/ll:reconcile-issue` - 2026-10-04T03:04:52 - `38f792e1-e775-40d5-80c0-389347b2f30b.jsonl`
- `/ll:wire-issue` - 2026-10-04T03:02:09 - `39534f88-48e0-4284-9aba-e665169cbc9b.jsonl`
- `/ll:refine-issue` - 2026-10-04T02:55:00 - `af5bb97e-76ce-451e-8263-48fef122a263.jsonl`
- `/ll:format-issue` - 2026-10-04T02:49:34 - `e03f42f4-9f83-4f77-a4ff-c803cba4148f.jsonl`
