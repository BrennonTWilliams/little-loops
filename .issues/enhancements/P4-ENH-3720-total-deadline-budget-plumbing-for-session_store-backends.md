---
id: ENH-3720
type: ENH
title: Total-deadline budget plumbing for session_store backends
priority: P4
status: open
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
verify_verdict: CLAIMS_OUTDATED
verify_evidence: "Integration Map > Tests: 'scripts/tests/test_enh3720_session_store_deadline.py — new file (ENH-numbered convention...' is flagged stale_file_ref (untracked) because the planned-new marker is not in the recognised form -> write '(new file)' (or '(new)'/'(to be created)') immediately after the path so format-check classifies it planned_new"

---

# ENH-3720: Total-deadline budget plumbing for session_store backends

## Summary

Add a monotonic total-deadline budget to `session_store/backend.py`, `libsql.py` and `hrana.py` so optional history reads/writes can honor a whole-operation bound (cold verification + queries + transactions + response reads). Split out of FEAT-3711 after an Opus review (2026-10-03): it is shared infrastructure, not an ll-next feature. v1 `ll-next` reads **local SQLite only**, so this is **not** a prerequisite of EPIC-3710; it unlocks remote-history reads for ll-next and any other optional-telemetry caller.

## Current Behavior

`LibsqlBackend.connect_readonly` ignores its timeout argument and each Hrana request starts a fresh budget, so a cold verification followed by a stalled query can exceed any caller-intended total. SQLite lock timeouts bound waiting for a lock but not query execution. ENH-3679 bounds only `cli_event_context` (250 ms per connection).

## Expected Behavior

- A caller passes one monotonic deadline; the remaining budget is carried through cold access verification, queries, transactions and response reads in the libsql/Hrana backends. SQLite gets a progress-handler cancellation bound in addition to a remaining-budget lock timeout.
- Existing readers keep their default (unbounded-as-today) behavior when no deadline is passed.
- No timed-out task continues writing after the caller reports a timeout.
- Read-only paths never use `connect_telemetry` (its file-backed verification/unreachable caches violate no-write contracts).
- Coordinate with ENH-3682 (budget best-effort remote prepatch reads): share the common primitive; keep prepatch/cache behavior independent.

## Acceptance Criteria

- [ ] Deadline primitive threaded through `backend.py`, `libsql.py`, `hrana.py`; tests cover cold slow verification followed by a stalled query/write, with request counts and a documented small scheduling tolerance.
- [ ] SQLite query cancellation via progress handler bounded by remaining budget.
- [ ] A deadline expiry surfaces as `HistoryUnavailable` on both legs — the SQLite leg wraps the progress-handler `sqlite3.OperationalError` ("interrupted"), the remote leg raises `HranaUnavailable` — so `history_reader/_base.py::_connect_readonly` (which catches only `HistoryError` and returns `None` on failure) degrades identically on both backends. Verified by a test driving an expired deadline through `_connect_readonly` on each backend and asserting `None` with no raw `sqlite3.OperationalError` escaping.
- [ ] The SQLite progress handler is installed per operation and cleared (`set_progress_handler(None, 0)`) when the operation ends, so a reused connection is not aborted by a stale handler; a no-deadline path installs no handler. Verified by a test that runs a deadline-bounded operation on a connection, lets the deadline lapse, then runs a long query on the same connection and asserts it completes.
- [ ] Default behavior of existing callers unchanged; no background worker continues a write after timeout.
- [ ] Documented in `docs/guides/HISTORY_SESSION_GUIDE.md`/`API.md`; `python -m pytest scripts/tests/` passes.

## Scope Boundaries

- **In scope**: a shared monotonic deadline primitive; threading it through `Backend.connect_readonly`, `LibsqlBackend`/`LibsqlConnection` (cold access verification, queries, transactions) and `HranaClient` (per-request budget, response reads); a SQLite progress-handler cancellation bound plus remaining-budget lock timeout; docs in `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/reference/API.md`.
- **Out of scope**:
  - Switching `ll-next` (EPIC-3710/FEAT-3711) to remote-history reads — v1 is local-SQLite only; this only unlocks that later.
  - Remote prepatch read budgeting and cache behavior (ENH-3682) — shares the primitive but stays independent.
  - Changing `cli_event_context`'s 250 ms per-connection bound (ENH-3679) or the `connect_telemetry` verification/unreachable caches.
  - Any change to default (no-deadline) behavior of existing readers/writers.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/session_store/backend.py` — `connect_readonly` is declared in four places that must stay signature-aligned: the `Backend` protocol (`:224`), `SqliteBackend` (`:278`), the module-level wrapper (`:365`, which resolves the target then forwards `timeout=`), and `LibsqlBackend` (`libsql.py:273`). The wrapper's docstring says timeout is "ignored by remote backends".
- `scripts/little_loops/session_store/libsql.py` — `LibsqlBackend.connect_readonly` (`:273`) accepts `timeout` "for protocol parity and ignored"; it builds `LibsqlConnection(self._client(remote), read_only=True, ...)` with `_client(..., timeout=DEFAULT_TIMEOUT_S)` (`:45`, 10.0 s) and makes no network call at connect time. `LibsqlConnection` (`:152`) has no deadline attribute; its statement entry points are `execute` (`:215`) and `executemany` (`:219`), both of which call `_guard` (`:177`) then `_run` (`:201`).
- `scripts/little_loops/session_store/hrana.py` — `HranaClient.__init__` stores one per-client `_timeout` (`:199`); `_post` (`:215`) computes `deadline = time.monotonic() + self._timeout` on every call (`:218`) and opens the connection with the same `timeout=self._timeout` (`:226`); only `_read` (`:255`) consults the monotonic deadline. Public entry points `execute` (`:289`), `batch` (`:297`) and `execute_many` (`:313`) all funnel through `_results` (`:271`) to `_post`, one HTTP POST each.
- `scripts/little_loops/session_store/remote_schema.py` — `check_access` (`:222`) receives an already-built client and has no timeout of its own; cold verification is `read_state` (`:74`) → `client.batch` → one `_post`. `LibsqlConnection.ensure_schema` path (`libsql.py:283`) calls `check_access(..., write=True)` directly, outside `_guard`.

**Request-count facts (for the test constraint)**
- A cold `LibsqlConnection.execute` on a non-telemetry connection is **2 HTTP requests** (verification batch + the statement); warm is 1, because `_VERIFIED` (`remote_schema.py:213`) is process-wide and keyed `(base_url, project_id)`. `executemany` is one atomic `begin/rows/commit` batch pipeline — there is no interactive transaction, `executescript`, or multi-round-trip write path in `libsql.py`/`hrana.py`.
- `migrate_remote` issues several sequential `_post`s (`_apply_one` re-reads state on `HranaUnavailable`); whether it is in scope for a deadline is not stated in the issue.

**Dependent Files (Callers/Importers)**
- Importers of `backend.py` (graph-confirmed): `cli/session.py:78`, `history_reader/runs.py:26`, `history_reader/formatting.py:18`, `issue_history/parsing.py:19`, `cli/issues/set_status.py:13`, and within `session_store/`: `queries.py`, `lifecycle.py:36`, `schema.py:25`, `writers.py:36`, `usage_refresh.py:17`, `remote_schema.py:29`, `hrana.py:33`, `libsql.py:31`, `__init__.py:79`. Importers of `hrana.py`: `libsql.py:40`, `remote_schema.py:30`.
- Existing `connect_readonly` callers that pass an explicit `timeout=`: `lifecycle.rebuild_needed` (`lifecycle.py:1102`, `_REBUILD_NEEDED_TIMEOUT = 0.5`, tied to the 5 s SessionStart budget). These are the callers whose per-connection float-seconds `timeout` must keep meaning what it means today.
- `connect_readonly` is also reached by ~25 `history_reader/*` and `issue_history/*` modules via `open_history_readonly` / `_connect_readonly` (`history_reader/_base.py`), none of which pass a deadline today.

**Conventions in Force**
- A new knob is added keyword-only with `None` meaning "keep prior behavior", resolved inside the callee, and mirrored through every seam layer — evidence: `schema.connect(path, *, busy_timeout_ms=None)` and `writers._connect_telemetry` forwarding the kwarg only when set. The four `connect_readonly` declarations above must move in lockstep (ENH-3678 needed a wrapper pass-through fix for the same reason).
- Transport failures never leak a raw `TimeoutError`: `HranaClient._post` catches `OSError`/`http.client.HTTPException` (`TimeoutError` is an `OSError`) and re-raises `HranaUnavailable` (a `HistoryUnavailable`); `LibsqlConnection._run` is the single place that reacts to error classes (marks unreachable only on telemetry connections). A deadline expiry must stay inside this taxonomy; there is no deadline-specific exception class today.
- No shared time-budget type exists; every site computes `deadline = time.monotonic() + X` inline and recomputes `deadline - time.monotonic()` (`hrana.py:_read`, `mcp_call.py`, `transport.py`). Contested: some sites use `time.time()` for deadlines (`runner_spec.py`, `fsm/executor.py`), and `remote_telemetry` TTLs use wall-clock `_now()`. This issue's primitive is monotonic by requirement.
- Unit split: `connect_readonly`/`HranaClient`/`sqlite3` take float **seconds**; `busy_timeout_ms` and `telemetry_timeout_ms` are int **milliseconds**. Frozen dataclasses in `session_store/` are pure value types (`targets.BackendConfig`, `remote_schema.RemoteState`); none carries behavior methods, so a `Deadline` with `remaining()`/`expired()` is a new shape here.
- The read-only path never uses `connect_telemetry`/the file-backed verified and unreachable caches: `LibsqlConnection(telemetry=False)` means `persist=False` in `check_access` and no marker checks in `_guard`. That is the property the "never `connect_telemetry`" criterion pins; the `_VERIFIED` in-process cache is still consulted and populated.

**Tests**
- `scripts/tests/hrana_stub.py::HranaStub` — real `ThreadingHTTPServer`; knobs are a single **global** `delay` (initialised at `:126`; the sleep at `:92-93` in `do_POST` is applied *after* the request is appended to `requests` at `:89`), `fail_next`, and `requests`. It has no per-request/per-statement delay and no mid-body stall, so "cold slow verification followed by a stalled query" cannot be expressed with it as-is; a stalled request still counts in `len(stub.requests)` even after the client gives up.
- Timing tests use real wall time with a loose inline upper bound (3–5× the configured timeout) and no named tolerance constant: `test_hrana_client.py::TestTimeouts` (`:222`, `< 1.5` for `timeout=0.3`), `test_remote_ingestion_telemetry.py::TestTelemetryBudget`, `test_libsql_integration.py` (env-gated). Request counts are asserted as `len(stub.requests)` before/after. No test patches `time.monotonic` for the hrana client; no test asserts that a timed-out request has no late side effects.
- Local-SQLite lock-wait precedent: `test_session_store_writers.py::TestCliEventLockBound` (`:3545`) holds `BEGIN IMMEDIATE` from a thread released by an `Event`, asserts `0.2 <= waited <= 2.0` for a 250 ms bound, and spies `sqlite3.connect`. `test_enh3678_rebuild_derive_gate.py::TestConnectReadonlyTimeout` only checks `timeout=` is accepted.
- Suite constraints (`scripts/pyproject.toml`): default `-n logical`, `--timeout=120 --timeout-method=thread`. The `no_parallel` marker (serial-only, via `test_no_parallel_serial_gate.py`) exists for timing-sensitive tests but none of the hrana/libsql timing tests use it. Existing tests that import these modules and must keep passing: `test_hrana_client.py`, `test_libsql_backend.py`, `test_libsql_integration.py`, `test_remote_schema.py`, `test_remote_operation_matrix.py`, `test_remote_callers_bug3652.py`, `test_remote_hooks.py`, `test_remote_doctor.py`, `test_session_store_backend.py`.

**Documentation**
- `docs/reference/API.md` § `little_loops.session_store` → "Backend chokepoint" lists `connect_readonly` in an import block but documents no `timeout` parameter and has no section for `libsql`/`hrana`/`remote_schema`; its only libsql mention (~`:9975`) calls it a "future remote (libSQL) provider", which lags the code (libsql ships today).
- `docs/guides/HISTORY_SESSION_GUIDE.md` has **no** remote/libsql/Hrana content at all (0 hits). The remote-backend timeout material actually lives in `docs/reference/CONFIGURATION.md` (`history.backend.telemetry_timeout_ms`, "Explicit reads use a longer bound (10s)", ~`:620–725`). The acceptance criterion naming the Guide therefore needs either new end-user-facing content there or a redirect to CONFIGURATION.md. Both are end-user docs: no `scripts/tests/…` or `scripts/little_loops/…` paths (`test_docs_audience_gate.py`).

**Configuration**
- `scripts/little_loops/config-schema.json` (`telemetry_timeout_ms`, ~`:2246`), `session_store/targets.py` (`DEFAULT_TELEMETRY_TIMEOUT_MS = 1500`), `config/features.py` — existing per-write telemetry budget; out of scope per the issue but it is the nearest existing "total budget" knob and must keep its current semantics.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/backend.py` — `open_history_readonly()` ends in `backend.connect_readonly(resolved)` with no `timeout`/deadline; a deadline reaches the ~70 `history_reader/*` readers only if this (and `history_reader/_base.py::_connect_readonly`) gains a parameter. That seam is ENH-3682's `best_effort` territory — share the `Deadline` primitive, do not add a second seam here [Agent 1/2 finding]
- `scripts/little_loops/history_reader/_base.py` — in `_connect_readonly()`: `except HistoryError` only, so a raw `sqlite3.OperationalError("interrupted")` from the progress handler escapes the "return None on failure" contract unless the SQLite leg wraps expiry as `HistoryUnavailable`; remote failures route through `remote_telemetry.warn_once(...)` [Agent 2 finding]
- `scripts/little_loops/session_store/lifecycle.py` — in `rebuild_needed()` (`:1102`, `timeout=_REBUILD_NEEDED_TIMEOUT`): wraps open+read in a bare `except Exception` → `unknown/read_error`, so a deadline expiry is already degrade-safe; no edit needed. Second `connect_readonly(db)` site in `lifecycle.py:1658` passes no kwargs [Agent 1/2 finding]
- `scripts/little_loops/session_store/writers.py` — `_DEGRADE_ERRORS = (sqlite3.Error, HistoryError)` (`:54`): a progress-handler `sqlite3.OperationalError` or a `HistoryUnavailable` expiry are both inside it; no edit needed [Agent 2 finding]
- `scripts/little_loops/cli/doctor.py` — in `_remote_client()`/`_REMOTE_PROBE_TIMEOUT_S = 3.0` (`:464`, `HranaClient(..., timeout=...)` at `:480`) and `remote_schema.read_state(client)` (`:780`): builds its own per-client budget and does not go through `connect_readonly`; positional `resolve_backend().connect_readonly(...)` at `:535`, `:579`, `:890`. All stay valid with a default-`None` kwarg; no edit [Agent 1/2 finding]
- `scripts/little_loops/cli/doctor_trim.py:280`, `cli/history.py:800`, `cli/ctx_stats.py:157,260,300,460`, `cli/logs.py:868,1610`, `issue_history/evolution.py:44`, `issue_history/workspace_quality.py:120` — positional `connect_readonly(path)` callers; unchanged by an additive kwarg [Agent 1 finding]
- `scripts/little_loops/cli/session.py` — in `_main_migrate()`: `HranaClient(cfg.endpoint(), cfg.auth_token())` + `migrate_remote` (`:496–500`) and `connect_readonly(path)` probe in `contextlib.closing` (`:504–509`); no deadline today, out of scope per the `migrate_remote` open question [Agent 1/2 finding]
- `scripts/little_loops/session_store/__init__.py` — `connect_readonly` import/`__all__` (`:87`, `:244`); a `Deadline` export (optional) needs an import + `__all__` entry here [Agent 1 finding]
- `scripts/little_loops/session_store/remote_schema.py` — in `migrate_remote()`/`_apply_one()`: sequential `read_state`/`client.batch`/`client.execute` without a deadline; a changed `read_state`/`check_access` signature reaches it indirectly [Agent 2 finding]

### Files to Modify
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py` — export `Deadline` alongside `connect_readonly` **only if** callers outside `session_store` construct one (they do: `lifecycle`/`history_reader`/CLI readers); `test_session_store_schema.py::test_all_and_required_private_names_resolve` then covers it automatically [Agent 1/3 finding]
- `scripts/tests/hrana_stub.py` — add a default-off per-request / per-chunk delay knob (e.g. `delay_for`/`trickle`) so "slow verification, then stalled statement" and a slow-trickle body (`_read` per-chunk deadline) are expressible; the existing global `delay` sleeps before any bytes are sent [Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — in `Backend chokepoint: little_loops.session_store.backend`: add the `connect_readonly(target, *, timeout=5.0, deadline=None)` signature and `Deadline` semantics; also refresh the stale "SQLite-only prerequisite for a future remote (libSQL) provider" intro [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — in `Remote history backend` (`history.backend.telemetry_timeout_ms` row, "Explicit reads use a longer bound (10s)", "Orchestration and loops" bullet "can stall that read for up to about 10 s"): cross-link the deadline option; wording must stay true for callers that pass no deadline [Agent 2 finding]
- `docs/ARCHITECTURE.md` — in the "Every history.db connection funnels through `little_loops.session_store.backend`" paragraph (`:862`): mention the optional deadline; keep the substring `_connect_readonly` — `test_wiring_guides_and_meta.py:134` asserts it [Agent 2/1 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — in the remote/timeout material it lacks entirely: add end-user text or a link to `CONFIGURATION.md`; dotted module names only (`test_docs_audience_gate.py` rejects `scripts/tests`, `scripts/little_loops/`, "this repo", `pytest scripts`) [Agent 2 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hrana_client.py` — in `TestTimeouts` (copy `test_read_timeout_raises_unavailable_within_the_bound`): new `TestDeadline` class — already-expired deadline, deadline shorter than client `timeout`, deadline through each of `execute`/`batch`/`execute_many`, slow-trickle body through `_read`, no-deadline default unchanged [Agent 3 finding]
- `scripts/tests/test_remote_schema.py` — in `TestOpenPolicy::test_the_check_runs_once_per_process` (counts `sqlite_master` requests): pin cold = 2 requests and warm = 1 with a deadline passed; any extra request added by deadline threading trips it [Agent 3 finding]
- `scripts/tests/test_libsql_backend.py` — in `TestReadOnly::test_reads_work_and_writes_are_refused_client_side` (asserts `len(stub.requests) == before`): extend for `connect_readonly(deadline=...)` + `TestBackendRegistry::test_libsql_resolves`; read-only path stays off `connect_telemetry` [Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — in `TestConnectReadonlyTimeout::test_default_timeout_unchanged_and_override_accepted`: pins `timeout` as a float-seconds keyword and the no-deadline default; add the SQLite progress-handler abort + remaining-budget lock-timeout tests here (lock-hold pattern from `TestRebuildNeeded::test_locked_store_maps_to_unknown_within_short_timeout`) [Agent 3 finding]
- `scripts/tests/test_session_store_writers.py` — in `TestCliEventLockBound._hold_write_lock` / `test_both_telemetry_connects_use_short_timeout` (`:3545`, `:3605`): reuse the held-`BEGIN IMMEDIATE` helper (`0.2 <= waited <= 2.0` shape); re-read the telemetry-timeout test before changing how `timeout` maps onto remaining budget [Agent 3 finding]
- `scripts/tests/test_session_store_backend.py` — in `TestProtocolConformance`: `Backend` is `@runtime_checkable`, so existing `isinstance` checks verify names only; add a new `inspect.signature` parity test over the four `connect_readonly` declarations (no precedent for these classes) [Agent 2/3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — in `test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist`: AST gate on raw `sqlite3.connect(`; passes if progress-handler/`Deadline` code adds no `sqlite3.connect` outside `backend.py` (a new helper module that connects needs an allowlist entry) [Agent 2/3 finding]
- `scripts/tests/test_remote_callers_bug3652.py` — in `TestReadersDegradeOnRemoteFailure` (`_open(db_path)` fake patching `history_reader.runs._connect_readonly`, `:509–526`): breaks only if the `_connect_readonly` wrapper signature changes (ENH-3682 seam), not from this issue's kwarg [Agent 1/3 finding]
- `scripts/tests/test_enh3720_session_store_deadline.py` — new file (ENH-numbered convention, cf. `test_enh3678_rebuild_derive_gate.py`): cross-layer cold-slow-verify + stalled-statement test importing `HranaStub` from `tests.hrana_stub`, request counts + named tolerance constant; mark `@pytest.mark.no_parallel` only if xdist CPU contention flakes it (no session_store test uses it today) [Agent 3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/libsql.py` — in `LibsqlBackend._client` (`DEFAULT_TIMEOUT_S = 10.0`, `:45`) and `connect_telemetry` (`telemetry_timeout_ms / 1000.0`, `:264–269`): the per-client cap the deadline must be `min()`-ed with; no new config key, so `config-schema.json`, `config/features.py`, `targets.py` (`DEFAULT_TELEMETRY_TIMEOUT_MS`), `db.py` and `test_history_backend_config.py` need no change [Agent 2 finding]

## Program Design

### Types

- `Deadline.expires_at: float` — absolute `time.monotonic()` value
- `Deadline` — frozen dataclass; `None` deadline means unbounded (today's behavior)

### Signatures

- `Deadline.after(seconds: float) -> Deadline`
- `Deadline.remaining() -> float` — seconds left, floored at 0.0
- `Deadline.expired() -> bool`
- `Backend.connect_readonly(target: Path | HistoryTarget, *, timeout: float = 5.0, deadline: Deadline | None = None) -> sqlite3.Connection`
- `HranaClient.execute(sql: str, params: Sequence[Any] = (), *, deadline: Deadline | None = None) -> HranaResult`
- `LibsqlConnection.execute(sql: str, parameters: Sequence[Any] = ()) -> LibsqlCursor` — reads the connection's own `deadline` and passes remaining budget to each `HranaClient` call

### Call Path

`connect_readonly` (`backend.py`) -> `LibsqlBackend.connect_readonly` -> `LibsqlConnection._guard` -> `remote_schema.check_access` -> `HranaClient._post` -> `HranaClient._read`

SQLite leg: `connect_readonly` -> `SqliteBackend.connect_readonly` -> `sqlite3.Connection.set_progress_handler` (aborts when `Deadline.expired()`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

**Ground-truth corrections to the types/signatures/call path above (verified against current code)**
- `HranaClient.execute(sql, params=())` (`hrana.py:289`) has no deadline parameter today, and neither do its siblings `batch` (`:297`) and `execute_many` (`:313`). `check_access` → `read_state` reaches the wire through `client.batch`, so a deadline carried only on `execute` would leave cold verification (`read_state`) and `executemany` unbudgeted. Whatever carries the budget has to reach `_post`/`_read` for all three entry points.
- `LibsqlConnection._guard` (`libsql.py:177`) is **not** on the `connect_readonly` call path: `LibsqlBackend.connect_readonly` makes no network call and does not invoke `_guard`. `_guard` runs lazily per statement inside `execute`/`executemany`, and the first one triggers `check_access` via `_run`. The cold-verification leg therefore happens at first-statement time, inside the caller's operation — which is exactly why a connect-time deadline must be stored on the connection rather than consumed at connect.
- `_post` computes its budget from `self._timeout` and `_read` takes an absolute `deadline: float` argument (static method). The existing absolute-monotonic-float contract in `_read` is the seam where a caller-supplied expiry and the per-client `_timeout` cap have to be reconciled (effective budget = the smaller of the two is the reading consistent with "unbounded-as-today when no deadline is passed").
- `SqliteBackend.connect_readonly` (`backend.py:278`) passes `timeout=` to `sqlite3.connect` (lock-wait only, seconds) and sets `PRAGMA query_only = ON`; it does not set `PRAGMA busy_timeout`, and no `set_progress_handler` exists anywhere in the repo (repo-wide search, source and tests). `sqlite3` surfaces a progress-handler abort as `sqlite3.OperationalError` ("interrupted"), which `connect_readonly`'s `HistoryUnavailable` wrapper does not cover (it wraps only open/PRAGMA); read-path `sqlite3.OperationalError` is currently unwrapped except where a call site opts into `translate_sqlite_errors()`.

**Open decisions this issue introduces (state the answers when implementing; none is pinned yet)**
- Expiry error: a deadline expiry on the remote leg is naturally `HranaUnavailable` (existing taxonomy; `TimeoutError` → `HranaUnavailable` conversion already happens in `_post`). The local leg's expiry type (raw `sqlite3.OperationalError` vs `HistoryUnavailable`) is unspecified, and callers that treat the two backends uniformly depend on that parity.
- Units: `Deadline` is monotonic seconds; `busy_timeout_ms` is int ms. The remaining-budget lock timeout must be converted consistently, and a remaining budget of `0.0` must not be passed to `sqlite3.connect(timeout=0)` / `PRAGMA busy_timeout` in a way that reads as "unbounded" on either backend.
- Progress-handler granularity: `set_progress_handler(handler, n)` fires every `n` VM instructions, so cancellation latency is bounded by `n`, not exactly by the deadline; the "documented small scheduling tolerance" criterion should name this too. The handler is per-connection state and persists for the connection's lifetime — a handler left installed on a connection reused after the deadline would abort unrelated later queries.
- Server-side outcome of a timed-out write: the client abandoning a Hrana request does not prove the server did not commit (`remote_schema._apply_one` already treats a mid-batch `HranaUnavailable` as an *ambiguous commit* and re-reads the idempotency marker). `hrana.py`/`libsql.py` spawn no threads, so "no timed-out task continues writing" holds client-side by construction; the criterion cannot mean server-side non-commit. The only background writer in `session_store` is the `compact-6section-*` daemon thread in `lifecycle._maybe_soft_threshold_summary`, which is not deadline-aware and is outside this issue's stated scope.

### Decision Rules
- Not a new gate/keyword/threshold: the issue adds a budget primitive, not a classification rule. Left as `N/A — no new decision logic` for the gate's purposes; the open decisions above are implementation judgments.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

1. A caller-supplied monotonic deadline is honored across every wire round-trip on the remote leg — cold verification (`remote_schema.read_state` → `HranaClient.batch`), the statement (`execute`), and `executemany` — and is capped by, not replacing, the client's existing `_timeout`. Verified by a stub-backed test where verification is slow and the following statement stalls, asserting elapsed time against the deadline plus a tolerance, and `len(stub.requests)` (2 for cold, not more).
2. `Backend.connect_readonly` accepts the optional deadline on all four declarations (`backend.py:224`, `:278`, `:365`; `libsql.py:273`) and ignoring it is no longer true for libsql. Verified by a signature-parity assertion alongside `test_session_store_backend.py` / `test_libsql_backend.py`, and by existing `timeout=` callers (`lifecycle.rebuild_needed`) behaving unchanged.
3. The SQLite read-only leg cancels a long-running query when the remaining budget is exhausted, and the cancellation handler does not outlive the operation on a reused connection. Verified with a local test in the style of `TestCliEventLockBound` (held lock + a deliberately slow query), asserting both a lower and an upper elapsed bound.
4. With no deadline passed, behavior is byte-for-byte as today: no handler installed, no changed lock timeout, no extra requests. Verified by the existing suites listed under Integration Map → Tests passing unmodified.
5. The test harness can express a slow-verification-then-stalled-statement scenario (the stub's single global `delay` cannot today); any new stub knob must not disturb the 8 files that import `HranaStub`.
6. Docs: `API.md` documents the new parameter and the deadline semantics; the HISTORY_SESSION_GUIDE.md criterion is reconciled with the fact that remote-backend behavior is documented in `CONFIGURATION.md`. `python -m pytest scripts/tests/` exits 0, including `test_docs_audience_gate.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/hrana_stub.py` — add the default-off per-request/per-chunk delay knob before writing the deadline tests; the 8 `HranaStub` importers (`test_remote_schema.py`, `test_remote_doctor.py`, `test_remote_operation_matrix.py`, `test_hrana_client.py`, `test_remote_hooks.py`, `test_libsql_backend.py`, `test_remote_ingestion_telemetry.py`, `test_remote_callers_bug3652.py`) must pass unmodified
- Add `scripts/tests/test_enh3720_session_store_deadline.py` and extend `test_hrana_client.py::TestTimeouts`, `test_enh3678_rebuild_derive_gate.py::TestConnectReadonlyTimeout`, `test_session_store_backend.py::TestProtocolConformance` (new `inspect.signature` parity test across the four `connect_readonly` declarations)
- Decide and state the SQLite-leg expiry type: wrap progress-handler `sqlite3.OperationalError` as `HistoryUnavailable` so `history_reader/_base.py::_connect_readonly` (`except HistoryError`) keeps its "return None on failure" contract and local/remote callers see the same taxonomy; `writers._DEGRADE_ERRORS` and `lifecycle.rebuild_needed` already tolerate either
- Install the progress handler per-operation and clear it (`set_progress_handler(None, 0)`) when the operation ends, so a reused connection is not aborted by a stale handler; any no-deadline path installs nothing
- Inject at `scripts/little_loops/session_store/backend.py::open_history_readonly` / `history_reader/_base.py::_connect_readonly` — only in coordination with ENH-3682 (its `best_effort` seam); this issue supplies the `Deadline` primitive, not a second wrapper signature
- Update `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/ARCHITECTURE.md` (keep `_connect_readonly` substring), and `docs/guides/HISTORY_SESSION_GUIDE.md` (dotted module names only) to describe the optional deadline
- Learning registry gap: `ll-learning-tests check --stale-aware sqlite3` is proven but carries no assertion for `Connection.set_progress_handler` (abort surfaces as `OperationalError: interrupted`, handler persists per-connection, `n`-instruction granularity) — add one before relying on it; `learning_tests_required: [sqlite3]` already present, unchanged

## Impact

- **Priority**: P4 — not on the ll-next critical path (v1 is local-only).
- **Effort**: Medium — three backends plus concurrency-sensitive tests.
- **Risk**: Medium — timing-sensitive tests; touches shared backend code.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-10-04 | Priority: P4

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item). Ran `--from-evidence`: only the claim listed in `verify_evidence` was re-checked.

- Integration Map > Tests: `hrana_stub.py::HranaStub` citation placed the post-`requests.append` sleep at `:126`/`:128`. Current code: `self.delay = 0.0` is initialised at `:126` (`self.requests` init is `:128`); the sleep is `scripts/tests/hrana_stub.py:92-93` in `do_POST`, after `stub.requests.append` at `:89`. Rewrote the citation in place.

## Session Log
- `/ll:verify-issues` - 2026-10-04T03:10:04 - `2d651013-b69a-457e-aeca-c0e6f7d1781c.jsonl`
- `/ll:verify-issues` - 2026-10-04T03:08:18 - `676efbca-b77e-4cfe-b025-9bbe4d011d98.jsonl`
- `/ll:reconcile-issue` - 2026-10-04T03:04:52 - `38f792e1-e775-40d5-80c0-389347b2f30b.jsonl`
- `/ll:wire-issue` - 2026-10-04T03:02:09 - `39534f88-48e0-4284-9aba-e665169cbc9b.jsonl`
- `/ll:refine-issue` - 2026-10-04T02:55:00 - `af5bb97e-76ce-451e-8263-48fef122a263.jsonl`
- `/ll:format-issue` - 2026-10-04T02:49:34 - `e03f42f4-9f83-4f77-a4ff-c803cba4148f.jsonl`
