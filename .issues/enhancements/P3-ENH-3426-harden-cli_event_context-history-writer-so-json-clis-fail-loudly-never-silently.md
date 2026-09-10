---
id: ENH-3426
type: ENH
title: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:42Z'
reconcile_attempted: true
confidence_score: 85
verify_verdict: VALID
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3426: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently

## Summary

Every `ll-*` CLI entry point wraps its body in `cli_event_context` (`scripts/little_loops/session_store/writers.py:483-561`), which opens `.ll/history.db`, inserts a `cli_events` row, and updates it with exit code and duration on exit. The writer is best-effort for `sqlite3.Error` only (BUG-2706); any other exception on the analytics path (`OSError`, malformed `analytics.capture` config raising `AttributeError`/`TypeError`) still escapes and crashes the wrapped command, and the command's buffered JSON is not flushed before the exit UPDATE waits on `busy_timeout`. This issue closes both gaps so a machine consumer of a JSON-emitting command (`ll-queue list --json`, `ll-loop show -j`, `ll-issues ... --json`) always gets its payload on stdout with exit 0, plus a stderr warning, regardless of what the history writer hits.

**Provenance correction (2026-09-10 review)**: this issue was captured from an ll-console report of `ll-queue list --json` dying with empty stdout, attributed to a locked `history.db`. That attribution is unsupported — see "What Is Verified". `ll-queue list` reads a **different** database, `.ll/queue.db`, unguarded; that is the far more likely cause of the reported symptom and is out of scope here — tracked as **BUG-3432** (filed 2026-09-10; see Scope Boundaries). This issue is pure hardening of `cli_event_context`, not a fix for a reproduced failure.

## What Is Verified

- On this checkout, with the same 7.6 GB `history.db`, `ll-queue list --json` returned exit 0 with `[]` on stdout in 0.2 s. The crash **did not reproduce** here. The likely trigger was a concurrent writer holding the SQLite lock while the ll-console session ran it.
- Database size is **not** a factor (2026-09-09 review). `history.db` is 7.6 GB / 1.9M pages / 1.49M `raw_events` rows / 342K `cli_events` rows (WAL mode, zero freelist) — routine for SQLite (281 TB limit). `cli_event_context` only does a single-row INSERT and UPDATE, both O(log n) B-tree tail operations independent of file size, as the 0.2 s result above shows. The only size-sensitive path is a schema migration in `ensure_db` on first connect after an upgrade (one-time, not steady-state); WAL checkpoint cost scales with WAL size (5 MB here), not DB size. The original size-guard proposal was dropped on this basis.
- `cli_event_context` already catches `sqlite3.Error` on the insert (writers.py:528) and logs a warning rather than raising, so the insert path is not the hole. Unhandled surfaces remain: `resolve_history_db` / `_pkg.connect` (schema migration on first connect after an upgrade, writers.py:520-521 runs inside the try but `connect` may block on `busy_timeout` rather than raise), the `finally` UPDATE (writers.py:543 onward), and any non-`sqlite3.Error` exception (e.g. `OSError` from disk-full, `MemoryError`) escaping either.
- **A locked `history.db` cannot produce the reported symptom with the current code (2026-09-10 review).** Simulated a `connect()` that raises `OperationalError("database is locked")` around a body that prints JSON: result was exit 0, the JSON on stdout, and the `cli_event_context: insert failed` warning (with traceback) on stderr. Both the insert and the exit UPDATE are already guarded (BUG-2706). "Non-zero exit + empty stdout" from a lock is therefore not reachable via this writer today.
- **The reported symptom matches a locked `.ll/queue.db`, not `history.db`.** `ll-queue list` calls `list_entries(QUEUE_DB_PATH)` at `cli/queue.py:249` with no exception guard; `QUEUE_DB_PATH` is `.ll/queue.db` (`queue_store.py:68`), a separate file with its own `busy_timeout` (`queue_store.py:202-214`). A lock held past that timeout raises straight out of `cmd_list`: traceback on stderr, exit 1, nothing on stdout. `ll-mcp`'s `queue_list` tool calls the same `list_entries` and has the same exposure, so the Context note below about ll-console being insulated by the MCP move holds only for `history.db`. Out of scope here — tracked as BUG-3432, see Scope Boundaries.
- **Second real hazard: buffered stdout lost to a consumer kill.** Stdout to a pipe is block-buffered, so the wrapped body's JSON sits in the process buffer while the `finally` UPDATE waits on `busy_timeout`. ll-console's `_run()` in `loop_client.py:42` / `issues_client.py:47` uses `subprocess.run(timeout=30)` and kills the child on expiry, discarding that buffer. Today's worst-case analytics stall (≈5 s on enter + ≈5 s on exit, plus a possible migration connection) is under 30 s, so this is not the current trigger, but it is the only mechanism by which this writer can yield "empty stdout" — and it is closed by flushing stdout before the exit UPDATE (Proposed Hardening step 4).

## Proposed Hardening

1. ~~Establish the failure contract first: ask the ll-console side for the exact stderr and exit code from the observed failure before changing behavior.~~ **Superseded (2026-09-09, `/ll:confidence-check` follow-up)**: no logged stderr/exit-code artifact from the original failure exists anywhere in ll-console's repo — it was a live-session observation, never committed. More importantly, ll-console's queue path no longer reproduces it: commit `56448d3` ("speak MCP stdio directly to ll-mcp", 2026-09-09T21:04:38Z — ~46 min after this issue was captured) repointed `queue_client.py` off the `ll-queue list --json` CLI shell-out onto `ll-mcp`'s `queue_list` tool over stdio. That tool (`_tool_queue_list`, `scripts/little_loops/mcp_server/tools.py:478`) wraps `queue_store.list_entries()` directly and never touches `cli_event_context` or `history.db` — so a locked history.db can no longer affect ll-console's queue reads at all. The remaining real exposure is other direct `ll-queue`/`ll-loop`/`ll-issues` CLI consumers, including ll-console's own `loop_client.py`/`issues_client.py`, which still shell out to `ll-loop`/`ll-issues` per subprocess.
2. Make the history writer best-effort on every path with **`except Exception`**, not `(sqlite3.Error, OSError)`: one guard around the whole pre-`yield` prefix (`resolve_history_db`, the config-gating block, `connect`, INSERT, commit) and one around the exit UPDATE. Rationale (2026-09-10 review): the stated contract is "no analytics-path exception reaches the wrapped body"; the issue's own research found `AttributeError`/`TypeError` from the config-gating prefix that an `OSError` tuple would not catch; the 2-tuple has zero repo precedent while `Exception`-wide suppression is the established EPIC-2457 convention for best-effort writers; and `cli_event_context` is the outermost frame of every `ll-*` CLI, so nothing above it can catch a leak. Never wrap the `yield` itself — body exceptions must still propagate (`except BaseException: exit_code = 1; raise` stays as-is). No new `busy_timeout`: the existing 5000 ms `PRAGMA` (`schema.py:124`, `:1405`) already covers every connection through `connect()`.
3. Add a test (mocked lock, not a real second connection — see Acceptance Criteria items 5 and 6) that invokes the `ll-queue` entry point and asserts it still emits its JSON on stdout with exit 0, plus a warning on stderr (in-process `caplog` test for the record, subprocess test for the real one-line stderr delivery).
4. **Flush stdout before the exit UPDATE** (added 2026-09-10 review): at the top of the `finally` block, `with contextlib.suppress(Exception): sys.stdout.flush()` so the body's payload reaches the consumer before any analytics-side `busy_timeout` wait. This is the only change that makes "never a silent empty stdout" literally true for this writer (see What Is Verified, buffered-stdout hazard). Do the same for `sys.stderr` — cheap and symmetrical.
5. Decide the stderr diagnostic shape and make code and docs agree (2026-09-10 review): Expected Behavior promises a **one-line** warning, but both existing guards pass `exc_info=True`, which prints a full traceback to stderr on every degraded run of a JSON CLI. Drop `exc_info=True` from the two `cli_event_context` warnings and include `type(exc).__name__: exc` in the one-line message instead (keep `exc_info` on a paired `logger.debug` if a traceback is wanted for diagnosis). Note that stderr delivery relies on Python's `logging.lastResort` handler (WARNING and above) because no `logging.basicConfig`, `addHandler`, or `NullHandler` exists anywhere in the package (re-verified 2026-09-10) — document this on the function docstring so a future logging change does not silently swallow the diagnostic.

   **Pinned format strings (2026-09-10 review)** — the widened first guard now covers `resolve_history_db`, the config gate, and `connect`, so the existing "insert failed" wording would be misleading when the failure is upstream of the INSERT. Use exactly:

   ```python
   logger.warning("cli_event_context: enter failed for %r (%s: %s)", binary, type(exc).__name__, exc)
   logger.warning("cli_event_context: exit update failed for %r (%s: %s)", binary, type(exc).__name__, exc)
   ```

   Tests assert the substrings `"cli_event_context: enter failed for"` and `"cli_event_context: exit update failed for"`. The two existing `TestCliEventContext` locked-DB tests (`test_session_store_writers.py:489-542`) do not assert message text today, so renaming "insert failed" → "enter failed" breaks nothing.

## Context

Belongs with the in-flight session-store lifecycle work (FEAT-3417, ENH-3420). Flagged by the ll-console agent as a concern to route here rather than PR themselves.

**Update (2026-09-09)**: the reported symptom is no longer reproducible via ll-console — its `queue_client.py` moved off the `ll-queue list --json` CLI shell-out onto `ll-mcp`'s `queue_list` tool over stdio the same day (commit `56448d3`, ~46 min after this issue was captured), and that tool path never touches `cli_event_context`/`history.db`. The hardening is still worthwhile for the CLI consumers that remain: automation calling `ll-queue`/`ll-loop`/`ll-issues` `--json` directly, and ll-console's own `loop_client.py`/`issues_client.py`, which still shell out to `ll-loop`/`ll-issues` per subprocess.

**Update (2026-09-10 review)**: the paragraph above is only half right. The MCP `queue_list` tool bypasses `history.db`, but it still calls `queue_store.list_entries()` against `.ll/queue.db` unguarded — the same exposure `ll-queue list` has at `cli/queue.py:249`, and the more plausible cause of the original report (see What Is Verified). That path is tracked as BUG-3432; this issue does not claim to fix the ll-console symptom.

## Acceptance Criteria

- [ ] Any `Exception` raised by the history writer (`resolve_history_db`, the config-gating prefix, connect, insert, finally-update) is caught via `except Exception` and logged; the wrapped command's stdout and exit code are unaffected. Exceptions raised by the wrapped body still propagate unchanged.
- [ ] The existing `busy_timeout` (5000ms via `PRAGMA`, applied unconditionally through `connect()` at `schema.py:1405`) is documented as already covering `cli_event_context`'s connection; no new timeout is introduced. The docstring also records that the stderr warning is delivered by Python's `logging.lastResort` handler (no `logging.basicConfig` in the package).
- [ ] `sys.stdout` (and `sys.stderr`) are flushed, under `contextlib.suppress(Exception)`, at the start of the `finally` block before the exit UPDATE runs, so the body's payload is delivered before any analytics-side wait.
- [ ] The degraded-path WARNING records use the pinned format strings from Proposed Hardening step 5 (`cli_event_context: enter failed for %r (%s: %s)` / `cli_event_context: exit update failed for %r (%s: %s)`), carry no `exc_info=True`, and Expected Behavior matches what the code emits.
- [ ] Test (in-process, `caplog`): locked `history.db` → `ll-queue list --json` prints valid JSON, exits 0, and a WARNING record is logged. Lives in `scripts/tests/test_cli_queue.py`, whose autouse fixture already does `monkeypatch.chdir(tmp_path)` so `QUEUE_DB_PATH` (`Path(".ll/queue.db")`, resolved via project-root discovery per ENH-2927) lands in an isolated dir. Shape: monkeypatch `little_loops.session_store.connect` to raise `sqlite3.OperationalError("database is locked")` (the existing pattern at `test_session_store_writers.py:489-511`) — this patches only the **history.db** connect; `queue_store.connect` is a separate function and stays real, which is the point — then `patch("sys.argv", ["ll-queue", "list", "--json"])`, call `main_queue()`, capture with `capsys`, assert `json.loads(out)` succeeds, return value is 0, and `"cli_event_context: enter failed for" in caplog.text` under `caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")`. Do **not** hold a real second connection with `BEGIN IMMEDIATE`: that costs a full 5 s `busy_timeout` per test unless `_BUSY_TIMEOUT_MS` is also monkeypatched down, and adds nothing the mock does not already prove. Note: `caplog` attaches a root handler, so `logging.lastResort` does not fire under this test — it proves the record was emitted, not that stderr received it (that is the next AC).
- [ ] Test (subprocess, stderr): one test runs `[sys.executable, "-c", "<patch little_loops.session_store.connect to raise; import sys; sys.argv=['ll-queue','list','--json']; from little_loops.cli.queue import main_queue; raise SystemExit(main_queue())>"]` via `subprocess.run(capture_output=True, text=True, cwd=tmp_path_with_.ll)` and asserts: returncode 0, `json.loads(stdout)` succeeds, and `stderr.strip().splitlines()` is exactly **one** line containing `cli_event_context: enter failed for 'll-queue' (OperationalError: database is locked)`. This is the only test that exercises the real `logging.lastResort` stderr path and the no-traceback promise; it also guards the docstring claim about `lastResort` against a future `NullHandler`/`basicConfig` being added to the package.
- [ ] Test: a non-`sqlite3.Error` on the analytics path (e.g. `config={"analytics": "oops"}` raising `AttributeError` in the gating prefix, or `connect` raising `OSError`) is swallowed with a warning and the body still runs. Lives in `test_session_store_writers.py::TestCliEventContext` next to the two existing locked-DB tests.


## Current Behavior

`cli_event_context` (`writers.py:483-561`) already catches `sqlite3.Error` on
both the insert (`writers.py:528`) and the `finally` UPDATE (`writers.py:552`)
and degrades to a no-op with a `logger.warning`. It does **not** catch
non-`sqlite3.Error` exceptions (`OSError` from disk-full, `MemoryError`) that
could escape `_pkg.connect()` (`writers.py:521`) or the UPDATE, nor the
`AttributeError`/`TypeError` a malformed `analytics.capture` config raises in
the unguarded gating prefix (`writers.py:512-518`). It does not flush stdout
before the exit UPDATE, so the body's buffered JSON is at the mercy of the
`busy_timeout` wait if a consumer kills the process. (`connect()` does apply a
5000 ms `PRAGMA busy_timeout` — see Codebase Research Findings.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `resolve_history_db(db_path)` (`writers.py:506`) is **not** inside any try/except — it runs unconditionally before the `if gate_open:` block (`writers.py:519`) and the `try:` that guards the INSERT (`writers.py:520`). This corrects the "What Is Verified" claim that "writers.py:520-521 runs inside the try" for both `resolve_history_db` and `connect` together: only `_pkg.connect()` (line 521) is inside the try; `resolve_history_db()` (line 506) is fully unguarded, as is the `config`-gating block (`writers.py:512-518`, `AnalyticsCaptureConfig.from_dict`/`feature_enabled_for`). Any exception from `resolve_history_db` → `_resolve_db_path` (`session_store/db.py:72`) propagates before the wrapped CLI body ever runs — the whole `ll-*` command crashes, not just the analytics row.
- The claim "`connect()` sets no explicit `busy_timeout`" is inaccurate. `connect()` (`schema.py:1560-1569`) calls `ensure_db(path)` then `_configure_connection(conn)` (`schema.py:1392-1408`), which unconditionally executes `PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}` (`_BUSY_TIMEOUT_MS = 5000`, `schema.py:124`) on every connection opened through `connect()` — including `cli_event_context`'s. That pragma call has its own narrow `except sqlite3.OperationalError` (`schema.py:1407`), separate from `cli_event_context`'s guard. A busy_timeout already exists (5s, applied via SQLite `PRAGMA`, not the `sqlite3.connect(timeout=...)` Python kwarg).

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Extends the unguarded-surface finding: the `config`-gating block (`writers.py:512-518` — `AnalyticsCaptureConfig.from_dict`/`feature_enabled_for`) is unguarded in addition to `resolve_history_db()` (`writers.py:506`) — both run before the `if gate_open:` guarded section (`writers.py:519`).
- `schema.connect()`'s `ensure_db()` call (`schema.py:1565`) performs `db_path.parent.mkdir(parents=True, exist_ok=True)` unguarded at `schema.py:1550`, which can raise `OSError` (disk full, permission denied) — and this runs BEFORE `PRAGMA busy_timeout` is applied to any connection (`_configure_connection()` at `schema.py:1553`/`:1567`), so a bounded busy_timeout cannot help a mkdir failure.
- `schema.py`'s `_apply_migrations()` (`schema.py:1424-1438`) deliberately re-raises a locked-DB `sqlite3.OperationalError` from `_current_version()` rather than treating it as a fresh DB — this propagates up through `ensure_db()`/`connect()` uncaught by anything in `writers.py`, a second unguarded failure path distinct from the connect call itself.
- The `finally` exit-UPDATE (`writers.py:543-560`) is independently guarded from the insert's try/except and does not call `resolve_history_db` again — it reuses `conn`/`row_id` set in the outer function scope; when the insert failed or `gate_open` was `False`, both stay `None` and the UPDATE is skipped entirely (`writers.py:544`).
- `skill_event_context`, `record_hook_event`, and `hook_event_context` are three independent implementations of the same shape, not shared code — each redeclares its own `resolve_history_db()` call (`writers.py:602`, `:698`) unguarded before any try/except, matching `cli_event_context`'s pattern. Guarding is inconsistent between them: `cli_event_context`'s `conn.close()` calls (`writers.py:533-534`, `:557-559`) are each wrapped in `try/except sqlite3.Error: pass`, but `skill_event_context`'s exit-path close (`writers.py:665`) and `record_hook_event`'s close (`writers.py:733`) are bare, unguarded calls.
- No existing size check exists anywhere in `writers.py` (confirmed repo-wide: no `.stat().st_size` call in the file). The closest precedent, `lifecycle.py`'s `prune()` (`lifecycle.py:1336-1348`) and `recompress_raw_events()` (`lifecycle.py:887,922`), both check `history.db`'s size only AFTER `connect()`/`ensure_db()` already succeeded — neither is a pre-connect guard. (Moot: the size guard was dropped — see What Is Verified.)

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Correction: `_apply_migrations()` is not at `schema.py:1424-1438` as stated above — that range is `_current_version()` (def at `schema.py:1424`, re-raise at `:1437`). `_apply_migrations()` itself is defined at `schema.py:1441-1516` and calls `_current_version()` internally (at `:1465` and `:1493`). The re-raise behavior described is accurate; only the function-name label was mismatched to the line range.
- `_current_version()`'s docstring (`schema.py:1428-1430`) states the locked-DB `OperationalError` "must propagate — misreading it as 0 makes the caller re-run migration 0 and crash", confirming the re-raise is deliberate. Because `sqlite3.OperationalError` subclasses `sqlite3.Error`, once this propagates up through `_apply_migrations()` → `ensure_db()` → `schema.connect()` to `writers.py:521`, it already lands inside `cli_event_context`'s existing `except sqlite3.Error:` (`writers.py:528`) — narrowing "a second unguarded failure path distinct from connect" (above) to: already covered once it reaches writers.py, just not guarded *within* schema.py itself.
- A distinct, previously unidentified unguarded surface exists in the config-gating block (`writers.py:512-518`) that is **not** `sqlite3.Error`/`OSError` at all: `config.get("analytics", {}).get("capture", {})` (`writers.py:515`) raises `AttributeError` if the `analytics` or `capture` key holds a non-dict value, and `AnalyticsCaptureConfig.from_dict()` (`features.py:914-928`) raises the same if handed a non-dict. Separately, `cli_commands`/`skills` are stored unfiltered by `from_dict` (`features.py:921-922`, unlike `correction_patterns` which is filtered to `isinstance(p, str)` at `:916-919`) — a non-string entry there reaches `fnmatch.fnmatch(subject, p)` inside `feature_enabled_for` (`features.py:100`) and raises `TypeError`. Widening the guard to `except (sqlite3.Error, OSError)` alone would not catch either of these.

## Expected Behavior

Every `ll-*` JSON-emitting CLI wrapped by `cli_event_context` exits
deterministically: on any history-writer failure (locked DB, disk-full,
OOM, malformed analytics config) the wrapped command still completes and
prints its JSON on stdout with exit 0, plus a one-line
`cli_event_context: enter failed for 'll-<name>' (<ExcType>: <msg>)` (or
`exit update failed for ...`) warning on stderr — no traceback, never a
silent empty-stdout crash. The payload is
flushed to the consumer before the exit UPDATE waits on `busy_timeout`, so
even a consumer-side kill during that wait cannot lose it.

## Motivation

This enhancement would:
- Close the remaining theoretical failure modes where analytics-row writes to
  `history.db` (a side-channel, not the CLI's actual payload) can crash a
  machine-facing JSON CLI or lose its buffered payload, corrupting automation
  that parses `ll-queue list --json` / `ll-loop show -j` /
  `ll-issues ... --json` output. None of these has been reproduced; the
  locked-DB case is already handled (BUG-2706).
- Business value: keeps ll-console and other machine consumers reliable even
  when `history.db` is lock-contended or the analytics config is malformed.
- Technical debt: brings `cli_event_context` to a true "no analytics-path
  exception escapes" guarantee (`except Exception`) instead of the current
  `sqlite3.Error`-only guard, and flushes stdout before the exit-side wait.

## Proposed Solution

See `## Proposed Hardening` above for the full plan. Summary: replace the
`except sqlite3.Error` guards on the insert (`writers.py:528`) and `finally`
UPDATE (`writers.py:552`) with `except Exception`, and extend the first guard
upward to cover `resolve_history_db` (`writers.py:506`), the config-gating
prefix (`writers.py:512-518`) and `connect` (`writers.py:521`) so no
analytics-path exception reaches the wrapped body; flush stdout/stderr at the
top of the `finally` before the UPDATE; make the warning one line. No size
guard: DB size does not affect the writer path (see What Is Verified).

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` (`cli_event_context`, `writers.py:483-561`)

### Dependent Files (Callers/Importers)
- Every `ll-*` CLI entry point wraps its body in `cli_event_context` — no
  per-caller changes needed; verify with
  `grep -rn "cli_event_context" scripts/little_loops/`
- Confirmed: 41 distinct `main_*()` call sites, each individually wrapping
  its own body (not a central dispatcher). One documented non-caller:
  `scripts/little_loops/mcp_server/__init__.py:31` (long-running process,
  not a one-shot CLI invocation).
- **Count refresh (`/ll:refine-issue`, 2026-09-10)**: the call-site count has
  drifted since the "41" figure above was last confirmed — a repo-wide
  `grep -rn "with cli_event_context(" scripts/little_loops/` now returns
  **51 occurrences across 48 files** (`cli/docs.py` alone contributes 4 of
  the 51, matching its already-cited `:23,126,252,329`; every other file
  contributes exactly 1). Independently confirmed twice (locator + analyzer
  agents, same grep). Not a change in scope — every new call site is still
  covered by the same "no per-caller changes needed" statement above, since
  the hardening lives entirely inside `cli_event_context` itself.

### Similar Patterns
- `skill_event_context` (same file, `writers.py:577-665`) is the internal-guard
  analogue for skill-host completions, but it is itself already inconsistent
  with `cli_event_context` (its exit `conn.close()` at `writers.py:665` is a
  bare, unguarded call vs. `cli_event_context`'s independently wrapped
  closes) — out of scope for this issue and not modified here.

### Tests
- `scripts/tests/test_session_store_writers.py`
- `scripts/tests/test_ll_session.py`
- `scripts/tests/test_issue_history_cli.py`
- Two tests already exercise `cli_event_context` under a simulated locked DB: `TestCliEventContext.test_cli_event_locked_db_does_not_crash_body` (`test_session_store_writers.py:489-511`) monkeypatches `connect` to raise `sqlite3.OperationalError("database is locked")` on the INSERT and asserts the wrapped body still runs; `.test_cli_event_locked_exit_update_does_not_mask_success` (`test_session_store_writers.py:513-542`) does the same for the exit UPDATE via a connection proxy that raises on the `UPDATE cli_events` statement. Neither asserts stderr warning content, and both simulate `sqlite3.OperationalError` specifically, not `OSError`.
- `test_still_exits_zero_when_db_unwritable` (`test_ll_issues_research_triage.py:140-157`) is the closest existing precedent to Acceptance Criteria item 5: it monkeypatches `connect` to raise `sqlite3.OperationalError`, invokes the full `ll-issues research-triage ... --json` CLI, and asserts exit code 0 with valid JSON parsed from stdout. No existing test does this for `ll-queue list --json` specifically, and none of the three tests found assert a stderr warning was emitted.
- Every locked-DB test found in the suite (also `test_set_status_cli.py:1286-1325`, `test_hook_post_tool_use.py:184-199`) simulates the failure via `monkeypatch.setattr(<module>, "connect", <raising stub>)`; no test in `scripts/tests/` opens a genuine second `sqlite3.Connection` and holds a real `BEGIN IMMEDIATE`/`BEGIN EXCLUSIVE` lock against the writer under test.

_Correction (`/ll:verify-issues`, 2026-09-10):_ `test_set_status_cli.py`'s `test_sqlite_error_is_caught_and_logged` (1289-1325) does **not** monkeypatch `connect` — it patches `little_loops.session_store.record_issue_event` directly with `side_effect=sqlite3.OperationalError("locked")`. It is not a `cli_event_context`-shaped locked-DB test at all (no `connect`/`busy_timeout` path exercised); it belongs in the "closest analogue for a caplog-based warning assertion" category (as already used at line 143/176 above), not the "monkeypatches `connect`" group. The other three tests in this bullet's list (`test_session_store_writers.py`, `test_ll_issues_research_triage.py`, `test_hook_post_tool_use.py`) do monkeypatch `connect` as described.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` (`TestFeatureEnabledForHelper`, line 1963-2019; `TestAnalyticsCaptureConfig`, line 2022-2097) — existing coverage only exercises well-formed `analytics.capture` dicts, `None`, bare strings, and non-list `correction_patterns` (`test_correction_patterns_malformed_non_list`/`_mixed`, line 2085/2091). No test simulates a non-dict `analytics` or `capture` value (e.g. `{"analytics": "oops"}`, raising `AttributeError` at `writers.py:512-518`'s `config.get("analytics", {}).get("capture", {})` chain) or non-string entries inside `skills`/`cli_commands` reaching `fnmatch.fnmatch()` in `feature_enabled_for` (`TypeError`) — the exact unguarded surface this issue's own Codebase Research Findings already identified (above) but had not yet scheduled a test file for. [Agent 3 finding] **Correction (2026-09-10 review)**: this is context, not a test location. A test in `test_config.py` can only exercise `from_dict`/`feature_enabled_for` themselves, which this issue does not change; the malformed-config test belongs in `test_session_store_writers.py::TestCliEventContext` against `cli_event_context` (AC item 7). Hardening `from_dict` itself is a separate follow-up — see Scope Boundaries.
- For the new locked-DB stderr-warning test (Acceptance Criteria item 5), use the flat `"..." in caplog.text` idiom with `caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")` — this matches all 8 existing caplog assertions already in `test_session_store_writers.py` (e.g. `TestRecordIssueSnapshot.test_record_issue_snapshot_number_reuse_warns`, line 720-741) and the pattern used by `test_set_status_cli.py`'s closest analogue (`test_sqlite_error_is_caught_and_logged`, line 1289-1325). The alternative `any(... for rec in caplog.records)` form appears only in `test_session_store_schema.py` and would be inconsistent with this file's convention. [Agent 3 finding]

### Documentation
- `docs/reference/API.md` (session_store writers section), if the
  best-effort guarantee becomes externally documented

_Wiring pass added by `/ll:wire-issue`:_
- If the `### cli_event_context` subsection is added, the exact insertion point is immediately before the existing `### skill_event_context` heading in the `## little_loops.session_store` section (i.e. right after the `### raw_events / rebuild / compact (ENH-2581)` section ends), matching source-file definition order in `writers.py`. `docs/ARCHITECTURE.md` also mentions `cli_event_context()` in three places (schema-version `v8`/`v15` table rows and the "Key Functions Reference" table) but none describe error-handling behavior, so none go stale from this guard-widening change — no update needed there. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed via grep: `cli_event_context` is wired per-CLI, not through a central dispatcher — 41 distinct `main_*()` entry points each individually call `with cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:]):` around their body (e.g. `cli/issues/__init__.py:21`, `cli/queue.py:923`, `cli/harness.py:1751`, `cli/docs.py:23,126,252,329`). One documented exception: `mcp_server/__init__.py:31` explicitly notes no `cli_event_context()` wrapper is used there (a long-running process, not a one-shot CLI invocation).
- `cli_event_context`'s current guard shape (narrow `except sqlite3.Error` around the INSERT and the exit UPDATE, each independently wrapped, `writers.py:519-536` and `writers.py:543-560`) is itself the result of a prior fix, `BUG-2706` (status `done`, `.issues/bugs/P2-BUG-2706-cli-event-context-crashes-every-ll-cli-on-locked-db.md`) — not the pre-hardening baseline the issue's framing implies. BUG-2706 names `skill_event_context` as the contract it brought `cli_event_context` into line with, and its postmortem states `_BUSY_TIMEOUT_MS = 5000` was deliberately left unchanged during that fix ("raising it only makes contended commands hang longer").
- `skill_event_context` (`writers.py:577-665`) is not fully consistent with `cli_event_context` today, despite being cited as the analogue to match: its final `finally: conn.close()` (`writers.py:665`) is a bare, unguarded call, whereas `cli_event_context`'s equivalent close calls (`writers.py:530-534`, `writers.py:556-560`) are each independently wrapped in `try/except sqlite3.Error: pass`. Two other EPIC-1707-tagged best-effort writers in the same file — `record_hook_event`/`hook_event_context` — follow the same internal-guard shape as `cli_event_context`; a second, distinct best-effort convention also exists in the file (`record_prompt_opt_event`, `record_correction`, `record_skill_event`), which raises unguarded and relies on the *caller* wrapping in `contextlib.suppress(Exception)` rather than guarding internally.
- No existing site anywhere in the codebase pairs `except (sqlite3.Error, OSError)` (checked both orderings, repo-wide) — the only occurrence of that tuple is this issue's own prose. Pairing `OSError` with an unrelated exception type in one guard is otherwise a routine, widely-used convention elsewhere in the codebase (`fsm/persistence.py`, `fleet_improve.py`, `decisions.py`), so widening the guard here would follow an established pattern shape, just not one previously applied to this specific pair at this call site.
- Size guard dropped (2026-09-09 review): the originally proposed opt-in `history.db` size threshold was removed because file size has no bearing on the single-row INSERT/UPDATE path — see What Is Verified. (Test-coverage findings folded into the existing `### Tests` subsection above rather than a second `### Tests` heading here.)

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Best-effort error handling in this codebase follows two disagreeing conventions, and `cli_event_context` already belongs to one of them: (1) internal guard — the function itself catches `sqlite3.Error` and logs a warning (`cli_event_context`, `skill_event_context`, `record_hook_event`/`hook_event_context`, all under the EPIC-1707 contract); (2) caller-side suppress — the function raises unguarded and every call site wraps it in `with contextlib.suppress(Exception):` (`record_correction`, `record_skill_event`, `record_prompt_opt_event`, `record_harness_event`, `record_verdict_event`, `record_review_event`, `record_test_run_event`, EPIC-2457 contract). None of the 41 `cli_event_context` call sites use `contextlib.suppress` — widening its guard should stay within convention (1), not adopt (2).
- No repo-wide precedent exists for the exact 2-tuple `except (sqlite3.Error, OSError)` (either ordering) — searched with an adjacency-anchored regex, zero hits. The closest is a 3-tuple, `except (sqlite3.Error, ImportError, OSError)` at `cli/issues/set_status.py:178`. Pairing `OSError` with an unrelated exception type in one guard is otherwise routine (100+ sites repo-wide), so widening here follows a common shape, just not a previously-used exact pairing.
- All four locked-DB tests found in the suite (`test_session_store_writers.py:489-542`, `test_ll_issues_research_triage.py:140-157`, `test_set_status_cli.py:1286-1325`, `test_hook_post_tool_use.py:184-199`) simulate the failure via `monkeypatch.setattr(<module>, "connect", <raising stub>)` raising `sqlite3.OperationalError("database is locked")`; none open a real second connection holding `BEGIN IMMEDIATE`/`BEGIN EXCLUSIVE`, and none assert stderr/warning text specifically (only exit code and/or stdout JSON). A `caplog`-based warning-text assertion convention exists elsewhere (`test_session_store_schema.py:2313-2341`) but has not been applied to any locked-DB scenario. **Correction (`/ll:verify-issues`, 2026-09-10):** `test_set_status_cli.py:1289-1325` is misclassified here — see the correction under `### Tests` above; it patches `record_issue_event`, not `connect`. Only three of the four listed tests actually monkeypatch `connect`.

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `docs/reference/API.md`'s `## little_loops.session_store` section (`API.md:9507`) has no dedicated `### cli_event_context` subsection — unlike `skill_event_context` and `hook_event_context`, which each carry their own subsection with explicit "Best-effort per the EPIC-1707 contract" language. The only mention of `cli_event_context` anywhere in API.md is a passing cross-reference inside `### skill_event_context` (`API.md:9674`). Confirmed as of this pass (API.md last modified 2026-09-09T23:16:57Z, after the prior refine pass) — the conditional documentation task named above ("if the best-effort guarantee becomes externally documented") is still outstanding.
- Convention check: every internal-guard site in this codebase (`cli_event_context`, `skill_event_context`, `hook_event_context`/`record_hook_event`, all `history_reader/*.py` readers, `issue_history/*.py`, `cli/ctx_stats.py`, `cli/doctor.py`, `codequery/codegraph.py` — 62+ sites) uses a bare `except sqlite3.Error:`, never widened with `OSError` or `Exception`. The lone widened guard in the repo, `set_status.py:178`'s `except (sqlite3.Error, ImportError, OSError):`, is a 3-tuple driven by a local `ImportError`-raising import, not a 2-tuple precedent. No 2-tuple `except (sqlite3.Error, OSError)` exists anywhere in the repo today.
- No shared pytest fixture for simulating a locked SQLite DB exists anywhere in `scripts/tests/` (checked `conftest.py` and repo-wide) — every locked-DB test builds its own inline `monkeypatch.setattr(<module>, "connect", <raising stub>)`. The closest *real* (non-mocked) lock-contention test pattern in the repo, `test_file_utils.py:194-239` (`test_second_open_nb_acquire_raises_blocking_io_error`), holds a genuine second `flock` file descriptor and asserts `BlockingIOError` — structurally similar to what a real-lock SQLite test would need, but targets a filesystem lock, not SQLite, and provides no ready-made SQLite fixture.
- Two disagreeing-but-both-live `caplog` warning-assertion idioms exist for locked-DB tests: `assert any(<substr> in rec.message for rec in caplog.records)` (`test_session_store_schema.py:2341,2416` — 1 file) vs. a flat `assert "<substr>" in caplog.text` (`test_set_status_cli.py:1325`, `test_session_store_writers.py:718,739-741`, plus `test_ll_loop_commands.py`, `test_sprint.py:334-335`, `test_recursive_finalize.py:250`, `test_link_cli.py:145` — 7+ files, the more common form). `test_set_status_cli.py:1289-1325` (`test_sqlite_error_is_caught_and_logged`) combines the monkeypatch-locked-DB pattern with the `caplog.text` form and is the closest existing analogue to Acceptance Criteria item 5's not-yet-written test.

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Consistency check on EPIC-2457 precedent (2026-09-10)**: Proposed Hardening step 2 cites "the established EPIC-2457 convention for best-effort writers" as precedent for widening `cli_event_context`'s own internal guard to `except Exception`. Pattern search across the codebase's two disagreeing best-effort conventions confirms EPIC-2457's actual shape is caller-side suppression (writer raises unguarded, caller wraps in `with contextlib.suppress(Exception):` — `record_correction`/`record_skill_event` in `writers.py`, called from `hooks/user_prompt_submit.py:126-129`), not an internal guard widened to `Exception`. No repo-wide site pairs an internal `except` (the shape `cli_event_context` already has) with `except Exception` — the internal-guard family (`cli_event_context`, `skill_event_context`, `hook_event_context`/`record_hook_event`, 60+ sites) is uniformly `except sqlite3.Error`. Does not change the recommendation — `cli_event_context` should stay internally guarded per its own existing shape, just widened, which more closely matches a third convention (outer hook entry-points wrapping their whole body in bare `except Exception`, e.g. `hooks/subagent_stop.py:30-52`) than EPIC-2457's caller-suppress convention. See the fuller version of this finding under Program Design → Codebase Research Findings.
- **No reusable abstraction exists (2026-09-10)**: confirmed no shared helper exists anywhere in the repo for (a) defensively flushing stdout/stderr before a blocking call — 8 `.flush()` sites found repo-wide, all unguarded, none paired with `contextlib.suppress` — or (b) formatting a one-line `type(exc).__name__: exc` diagnostic for `logger.warning` specifically (the string shape exists at 4 sites, but only in `print()`/f-string/`pytest.fail` contexts, never inside a `logger.warning` call). Both pieces of this hardening are new code, not reuse of an existing utility.

## Program Design

### Types

- No new types — reuses `sqlite3.Connection`, existing `cli_events` schema.

### Signatures

- `cli_event_context(binary: str, args: list[str] | None, db_path: Path | None, config: dict | None) -> ContextManager[None]` (unchanged signature, `writers.py:483`)
- ~~Internal: `_pkg.connect(effective_path, timeout=2.0)` — add explicit `timeout` kwarg at `writers.py:521`~~ **Superseded (`/ll:verify-issues`, 2026-09-10)**: this entry was never updated after the issue's own later research (below, and Acceptance Criteria item 2 / Implementation Steps item 2) concluded no new timeout is needed — the existing 5000ms `PRAGMA busy_timeout` already covers every connection through `connect()`. Do not implement this line; it predates and contradicts the issue's current, authoritative guidance.

### Call Path

`cli_event_context` (`writers.py:483`) -> [one `try/except Exception` spanning `resolve_history_db` (`:506`), config gate (`:512-518`), `_pkg.connect` (`:521`), INSERT+commit (`:522-527`)] -> `yield` (unguarded, `except BaseException: exit_code = 1; raise` unchanged) -> `finally`: `suppress(Exception): sys.stdout.flush(); sys.stderr.flush()` -> [`try/except Exception` around `conn.execute(...UPDATE cli_events...)` + commit (`:547-551`)] -> guarded `conn.close()`.

`gate_open`/`effective_path` must be initialised before the first `try` so the `except` branch can leave `conn`/`row_id` as `None` and the `finally` skips the UPDATE exactly as it does today for a failed insert.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Actual current signature (`writers.py:483-488`): `cli_event_context(db_path: Path | str = DEFAULT_DB_PATH, binary: str = "", args: list[str] | None = None, config: dict | None = None) -> Generator[None, None, None]`. This corrects the "Signatures" entry above: param order is `db_path, binary, args, config` (not `binary`-first), `db_path` defaults to `DEFAULT_DB_PATH` (not `None`), and the return annotation is `Generator[None, None, None]` (not `ContextManager[None]`). Confirmed against all 41 real call sites, which pass positionally as `cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:])` (e.g. `cli/issues/__init__.py:21`, `cli/queue.py:923`, `cli/session.py:424`).
- `_pkg.connect` (`writers.py:521`) resolves to `little_loops.session_store.connect`, re-exported verbatim from `schema.connect` (`schema.py:1560-1569`) — not a wrapper with its own defaults. `schema.connect()` calls `ensure_db(path)` (mkdir + migrations, can raise `OSError`) before `sqlite3.connect(str(db_path))` (`schema.py:1566`, no `timeout=` kwarg — the 5s stdlib default applies at the Python connect level), then `_configure_connection()` applies the 5000ms `PRAGMA busy_timeout` described above.
- No call site in the repo passes an explicit `timeout=` kwarg to `sqlite3.connect()` (checked all 25 `sqlite3.connect(` sites across `session_store/`, `cli/`, `queue_store.py`, `codequery/`, `history_reader/`). The codebase's sole busy-wait precedent is the shared `PRAGMA busy_timeout` in `_configure_connection` (`schema.py:1392-1408`), independently mirrored (not shared code) in `queue_store.py`'s own `_configure_connection` (`queue_store.py:202-214`).

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Ordering relevant to the widened-guard Call Path entries (`writers.py:521`, `writers.py:547`): `ensure_db()`'s unguarded `mkdir` (`schema.py:1550`) runs BEFORE `_configure_connection()` applies `PRAGMA busy_timeout` to either the throwaway migration connection (`schema.py:1553`) or `connect()`'s returned connection (`schema.py:1567`) — a bounded busy_timeout only guards lock contention, not disk-full/permission failures during directory creation.
- No exact-2-tuple `except (sqlite3.Error, OSError)` precedent exists repo-wide (searched both orderings, zero hits); the nearest shape is a 3-tuple at `set_status.py:178`. The proposed widened guard would follow a common tuple-with-OSError shape used elsewhere (100+ sites), not a previously-used exact pairing.

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Count refresh (2026-09-10)**: the "41 distinct `main_*()` entry points" figure in this section's earlier bullet has drifted — a repo-wide `grep -rn "with cli_event_context(" scripts/little_loops/` now returns 51 occurrences across 48 files (`cli/docs.py` contributes 4, matching its cited `:23,126,252,329`; every other file contributes 1). See the matching correction under Integration Map → Dependent Files (Callers/Importers). Does not change the widened-guard plan — every citation checked against the current checkout (writers.py:483-561, :506, :512-518, :521, :528, :547, :552; schema.py:124, :1392-1408, :1405, :1407, :1424, :1437, :1441-1516, :1550, :1553, :1560-1569, :1567) matched exactly, with no other drift found.
- **Precedent precision (2026-09-10)**: Proposed Hardening step 2 justifies widening `cli_event_context`'s own internal guard to `except Exception` by citing "the established EPIC-2457 convention for best-effort writers." Pattern search confirms EPIC-2457's actual convention is caller-side suppression — the writer function raises unguarded and the *caller* wraps the call in `with contextlib.suppress(Exception):` (e.g. `record_correction`/`record_skill_event` in `writers.py`, called from `hooks/user_prompt_submit.py:126-129`). No site anywhere in the repo pairs an *internal* `except` clause (guard living inside the writer, as `cli_event_context` already does) with `except Exception` — every internal-guard site (`cli_event_context`, `skill_event_context`, `hook_event_context`/`record_hook_event`, 60+ sites repo-wide) uses bare `except sqlite3.Error`. The closest existing shape for what this issue actually proposes — widening an *internal* per-operation guard to catch the whole function body — is a different, third convention: outer hook entry-points that wrap their whole call chain in a bare `except Exception: pass`/`except Exception: return 0` (`hooks/subagent_stop.py:30-52`, `hooks/post_commit.py:87-101`). This does not change the recommendation (`except Exception` is still the right choice per the issue's own stated contract — "no analytics-path exception reaches the wrapped body" — and `cli_event_context` is the outermost frame of every `ll-*` CLI, same shape as Pattern 3's hooks), only the precedent it should cite: the internal-guard family provides no precedent for the widened exception type, only for keeping the guard internal rather than moving to caller-side suppress.
- **Flush/format-string precedent check (2026-09-10)**: no existing site anywhere in the repo wraps `sys.stdout.flush()`/`sys.stderr.flush()` in `contextlib.suppress(Exception)` (8 `.flush()` sites found repo-wide, all unguarded, none preceding a blocking DB call) — this hardening is genuinely new ground, not an existing pattern being applied. Similarly, no existing `logger.warning(...)` call site interpolates `type(exc).__name__` — every `logger.warning` + exception site in `writers.py` currently uses `exc_info=True` instead (16 sites checked). The `type(exc).__name__: exc` string shape itself is an established codebase idiom, but only outside `logger.warning` (in `print()`/f-string/`pytest.fail` contexts — `cli/doctor.py:306,324`, `cli/verify_decisions.py:62,77`). Neither absence blocks the plan; both confirm there is no existing helper to reuse and no established `logger.warning` precedent being contradicted.

## Implementation Steps

1. ~~Confirm the exact failure contract from ll-console (stderr content, exit
   code) before changing behavior~~ — superseded; see Proposed Hardening step
   1 and Context for why this can no longer be confirmed via ll-console and
   is no longer a blocker.
2. Widen both exception guards to `except Exception` — no new `busy_timeout`
   is needed, it is already set unconditionally (5000ms via `PRAGMA`,
   `schema.py:1405`). Extend the first guard to wrap `resolve_history_db()`
   (`writers.py:506`), the config-gating prefix (`writers.py:512-518`),
   `_pkg.connect()` (`writers.py:521`) and the INSERT; keep the second around
   the `finally` UPDATE (`writers.py:547`). Never wrap the `yield`.
3. At the top of the `finally`, flush `sys.stdout` and `sys.stderr` under
   `contextlib.suppress(Exception)` before the UPDATE.
4. Drop `exc_info=True` from the two WARNING records and switch them to the
   pinned format strings in Proposed Hardening step 5 (`enter failed for` /
   `exit update failed for`, with `type(exc).__name__: exc`). Update the
   docstring: `Exception`-wide contract, and the note that stderr delivery
   comes from `logging.lastResort`.
5. Add the tests described in Acceptance Criteria: the in-process locked-DB
   `ll-queue list --json` test and the subprocess stderr one-line test (both
   in `test_cli_queue.py`), and the non-`sqlite3.Error` test (in
   `test_session_store_writers.py::TestCliEventContext`); extend the two
   existing `TestCliEventContext` locked-DB tests to assert `caplog.text`
   with the new substrings.
6. Add a `### cli_event_context` subsection to `docs/reference/API.md`
   (insertion point in Integration Map → Documentation) stating the
   best-effort contract.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Add a test to `scripts/tests/test_config.py` ...~~ **Dropped (2026-09-10 review)**: misplaced — a `test_config.py` test cannot exercise the `writers.py` guard. The malformed-config case is covered by AC item 7 in `test_session_store_writers.py::TestCliEventContext` (`config={"analytics": "oops"}` → `AttributeError` swallowed, body runs; and `config={"analytics": {"capture": {"cli_commands": [42]}}}` → `TypeError` swallowed, body runs).
- Write the new locked-DB `ll-queue list --json` test (AC item 5) in `scripts/tests/test_cli_queue.py` using the flat `"..." in caplog.text` idiom with `caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")`, matching the convention already used throughout `test_session_store_writers.py`. Add the subprocess stderr test (AC item 6) alongside it.

## Impact

- **Priority**: P3 - affects automation reliability, but only under a
  hard-to-reproduce lock-contention trigger; not user-facing by
  default.
- **Effort**: Small - two widened except clauses, a stdout flush, and a
  one-line warning format, scoped to one function plus tests and an API.md
  subsection.
- **Risk**: Low - only touches a best-effort analytics side-channel with
  existing `sqlite3.Error`-catching precedent in the same function.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3

## Success Metrics

- Locked-DB regression test (Acceptance Criteria items 5 and 6) passes and stays
  green in CI.
- No further silent empty-stdout reports against `ll-*` JSON CLIs after the
  fix ships.

## Scope Boundaries

- **In scope**: hardening `cli_event_context`'s connect/insert/finally-UPDATE
  paths (plus the unguarded `resolve_history_db` / config-gating prefix),
  flushing stdout before the exit UPDATE, and the one-line stderr warning.
- **Out of scope — tracked as BUG-3432**: the unguarded `.ll/queue.db` read in
  `ll-queue list` (`cli/queue.py:249`, `list_entries(QUEUE_DB_PATH)`) and the
  same call inside `ll-mcp`'s `queue_list` tool (`mcp_server/tools.py:478`).
  A locked queue.db there produces the exact symptom this issue was captured
  from (traceback, exit 1, empty stdout) and is not touched by any change to
  `cli_event_context`.
- **Out of scope**: hardening `AnalyticsCaptureConfig.from_dict` to filter
  non-string `skills`/`cli_commands` entries the way it already filters
  `correction_patterns` (`features.py:916-919`). This issue closes the
  `TypeError` at the `cli_event_context` call site by guarding the prefix; the
  `from_dict` inconsistency is a separate, optional follow-up.
- **Out of scope**: the `except BaseException: exit_code = 1` fidelity nit
  (`SystemExit(2)` from argparse and `SystemExit(0)` are both recorded as 1);
  `skill_event_context`'s bare `conn.close()`; any size-gated behavior on
  `history.db` (size does not affect the writer; 7.6 GB / 1.5M rows is routine
  for SQLite); auto-compaction or pruning of `history.db` (manual-only per
  project rule — see `raw_events` compact()/prune()); replacing SQLite as the
  history store; and any change to the `cli_events` schema.

## API/Interface

N/A - no public API changes; `cli_event_context`'s call signature is
unchanged, only its internal error handling widens.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-10_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a
record of what was wrong and fixed, not an outstanding action item).

- Every `writers.py`/`schema.py` line citation checked against the current
  checkout (`writers.py:483-561`, `:506`, `:512-518`, `:521`, `:528`, `:547`,
  `:552`, `:602`, `:698`; `schema.py:124`, `:1392-1408`, `:1405`, `:1407`,
  `:1424-1438`, `:1550`, `:1560-1569`, `:1565-1567`) is exact — no drift, no
  refinement needed.
- Test citations checked: `test_session_store_writers.py:489-542`,
  `test_ll_issues_research_triage.py:140-157`, `test_hook_post_tool_use.py`
  (test body at 184-199), and `test_set_status_cli.py:1289-1325` all exist as
  described in file/line terms. One factual error found and fixed in the same
  pass: `test_set_status_cli.py`'s test monkeypatches `record_issue_event`,
  not `connect` — two Tests-section bullets claimed otherwise (corrected
  inline above).
- One stale Program Design entry found and struck through: the `Signatures`
  section's `timeout=2.0` kwarg proposal predates and contradicts the issue's
  own later conclusion (AC #2, Implementation Steps #2) that no new timeout
  is needed — corrected inline above.
- BUG-2706 (cited as the prior fix this issue builds on) confirmed `status:
  done`.
- Decisions log (`.ll/decisions.d/`) checked: no active required rules —
  clean pass, no conflict possible.
- `ll-verify-evidence --json` flagged one span ("with contextlib.suppress
  (Exception):", attributed to EPIC-2457, `## Codebase Research Findings`
  line ~167) as not appearing verbatim in EPIC-2457. Manually confirmed as a
  tool attribution artifact, not fabricated evidence: EPIC-2457 does contain
  the substance (`contextlib.suppress(Exception)`-guarded writes, lines
  85/265) and the code pattern itself is real and correctly attributed to the
  seven named call sites (`user_prompt_submit.py`, `action.py`,
  `pytest_history_plugin.py`) — the mismatch is only the added `with ...:`
  wrapper syntax in the issue's prose vs. EPIC-2457's bare function-name
  form. No correction needed.
- No `## Blocked By`/`## Blocks` sections present — no dependency checks
  apply.
- Proposal-vs-code consequence check (B6): no unsound consequence found
  beyond the stale `timeout=2.0` fragment above (already corrected); the
  widened-guard plan and AC coverage are otherwise internally consistent.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

### Concerns
- ~~No repo-wide precedent exists for the exact 2-tuple `except (sqlite3.Error, OSError)`~~ **Resolved (2026-09-10 review)**: the plan no longer uses the 2-tuple. Proposed Hardening step 2 and AC #1 settled on `except Exception`, which follows the established EPIC-2457 best-effort convention. The earlier 2026-09-09 Confidence Check section (which also listed the already-superseded Step 1 as open) was removed as stale.
- `cli_event_context`'s insert and exit-UPDATE paths are already partially guarded by the prior fix BUG-2706 (`sqlite3.Error` only); this issue extends existing partial coverage (widen to `Exception`, guard `resolve_history_db`/config-gating prefix) rather than building on a clean slate — re-verify the extension doesn't disturb BUG-2706's existing guard behavior (its two `TestCliEventContext` locked-DB tests must stay green).

## Session Log
- `/ll:refine-issue` - 2026-09-10T01:54:48 - `13270282-d9ad-49f5-8239-cf39c3df395e.jsonl`
- `/ll:verify-issues` - 2026-09-10T01:47:41 - `e5f879ce-163c-470b-875a-3db482daf36b.jsonl`
- `/ll:confidence-check` - 2026-09-10T01:22:23 - `af1b5be3-0894-42b0-b637-6b7a540d5db7.jsonl`
- `/ll:confidence-check` - 2026-09-10T00:41:39 - `d1b11d5d-bd78-420e-91a1-5dfc94d4273b.jsonl`
- `/ll:verify-issues` - 2026-09-10T00:28:01 - `626872e1-6f1e-434a-bfbc-2499d9a3d127.jsonl`
- `/ll:verify-issues` - 2026-09-10T00:20:35 - `6e1e18a4-dc28-495d-a48a-ed24698d5775.jsonl`
- `/ll:confidence-check` - 2026-09-10T00:02:36 - `e1e987d9-5a25-4adf-9f93-78b6e7b380b0.jsonl`
- `/ll:wire-issue` - 2026-09-09T23:41:59 - `5825e8f7-a405-4f10-9f6c-b98ebb708843.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:23:47 - `00ea4689-f70b-4623-84a3-269ac3fcabb8.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T23:10:51 - `719e35d3-e0ad-40bf-86c3-2b6c7827a005.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:05:44 - `97c1c5a3-138f-48f2-b148-91b0309c6eab.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:49:09 - `05b369f7-30a2-4959-8bec-aa3ab3083faf.jsonl`
- `/ll:format-issue` - 2026-09-09T22:40:10 - `419c0f66-ac03-408b-af11-4cdc8ba58375.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
