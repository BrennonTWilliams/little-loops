---
id: BUG-3440
type: BUG
title: ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
confidence_score: 85
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3440: ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds

## Summary

_history_db_data (cli/doctor.py ~451-459) probes readability with `SELECT 1`, a constant expression that does not force a page-1 header read on every SQLite build; on CI a 54-byte garbage file returns status=full instead of unsupported. Validate the 16-byte header magic (`b"SQLite format 3\x00"`) before connecting, and add a regression test asserting both checks agree so the verdict cannot silently degrade again (A3).

`PRAGMA quick_check` was the alternative mechanism and is **rejected** — measured at 32.12 s against this project's real 7.88 GB `.ll/history.db`, and `_history_db_data()` runs twice per `ll-doctor` invocation (~64 s added to a command that currently completes in 4.88 s). See Proposed Solution.

## Current Behavior

`ll-doctor`'s History DB check (`_history_db_data()`, `scripts/little_loops/cli/doctor.py`) probes readability with `conn.execute("SELECT 1").fetchone()`. `SELECT 1` is a constant expression that many SQLite builds — notably on Linux/CI — answer without reading page 1's file header, so a corrupt file passes the probe without raising `sqlite3.Error`. On CI, a 54-byte garbage `.ll/history.db` is reported as `status=full` (healthy) instead of unreadable.

## Steps to Reproduce

1. In a project with a `.ll/` directory, create a garbage DB file: `head -c 54 /dev/urandom > .ll/history.db`
2. Run `ll doctor` (on a Linux SQLite build)
3. Observe: the History DB section prints the DB path with the healthy/`full` symbol instead of flagging the file as unreadable

## Root Cause

- **File**: `scripts/little_loops/cli/doctor.py`
- **Anchor**: `in function _history_db_data()` — the `conn.execute("SELECT 1")` probe
- **Cause**: `SELECT 1` is a constant expression; SQLite builds that lazy-read the database header evaluate it without touching page 1, so the read-only connect + probe never encounters the corrupt content and never raises `sqlite3.Error` for it.

**Confirmed (2026-09-10 pre-implementation review).** CI run [`34519368279`](https://github.com/BrennonTWilliams/little-loops/actions/runs/34519368279) (unit-tests job, 2026-09-10T19:31Z, Python 3.11.16) failed on exactly `TestHistoryDb::test_present_but_corrupt_reports_error` with `AssertionError: assert 'full' == 'unsupported'` — the `SELECT 1` probe answered without raising on that Linux build, confirming the lazy-header mechanism end-to-end. The bug does **not** reproduce locally: on macOS / SQLite 3.49.2 all four candidate probes raise `DatabaseError: file is not a database` on both a 54-byte and a 55-byte garbage file — **including `SELECT 1`** — which is why local runs are green while CI is red.

A constant-expression probe is not a readability probe on any build, so the fix also stands on its own merits (Implementation Steps step 5 carries the platform-independent guard).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — the probe body inside `_history_db_data()` (:438); nothing else in the check chain changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:66` — imports/re-exports `main_doctor`
- `scripts/little_loops/cli/doctor.py:473` — `_history_db_check()` maps the data dict into `CheckResult(name="history_db", ...)`
- `scripts/little_loops/cli/doctor.py:125` — `_exit_code_for()` is the verdict consumer: exit 1 iff `severity == "error" and status == "unsupported"`
- `scripts/little_loops/cli/doctor.py:1306-1307` — `_print_report()` embeds `"history_db"` / `"schema_drift"` data in `--json` output
- `scripts/little_loops/cli/doctor.py:1423` — `main_doctor()` calls `_print_history_db_section()`

### Conventions in Force
- Doctor data functions are no-arg `_*_data() -> dict` returning `{"status", "severity", "note"}` and never raise; failures render the exception into `note` — evidence: `doctor.py` `_decisions_store_data` / `_code_query_data` / `_schema_drift_data`
- Read-only probes guard the *statement*, not the connect: a `mode=ro` connect succeeds on a non-database file and the error surfaces only at the first executed statement (PRAGMA or SELECT alike) — evidence: `session_store/sessions.py` `_query_threads_db` docstring (~:116-119), `issue_history/workspace_quality.py` `_open_member_readonly` (~:108-115)
- The never-create constraint is test-enforced via byte-identity (`before = read_bytes()` … `assert read_bytes() == before`) — evidence: `test_cli_doctor_install_checks.py::TestSchemaDrift::test_never_creates_or_migrates_database`
- `_history_db_data` resolves `Path.cwd() / DEFAULT_DB_PATH` (`session_store/db.py:15`), bypassing `resolve_history_db()`/`LL_HISTORY_DB`; conftest's `LL_HISTORY_DB` isolation does not reach it — its tests isolate via `monkeypatch.chdir(tmp_path)`, not env vars
- **The probe is a hot path and runs twice per invocation.** `_history_db_data()` is called at `doctor.py:464` (`_print_history_db_section`, text mode) *and* `:475` (`_history_db_check`, via `_run_registered_checks()` at `:1436`); `--json` mode swaps `:464` for `:1306` but still totals two calls. Any per-call cost is paid twice on every `ll-doctor` run, against a database that is **7.88 GB** in this project. Probe cost is therefore part of the contract, not an implementation detail — and it is invisible to the test suite, which exercises `monkeypatch.chdir(tmp_path)` DBs of a few KB

### Tests
- `scripts/tests/test_cli_doctor_install_checks.py` — `TestHistoryDb::test_present_but_corrupt_reports_error` (:193-203) already writes a 55-byte garbage file and asserts `unsupported`/`error`: this is the test failing on Linux CI, not a test to add. `test_present_and_readable_is_full` (:176) builds a real DB via raw `sqlite3.connect`; `test_absent_is_informational_and_does_not_create` (:164) pins no-create
- `scripts/tests/test_cli_doctor.py` — `TestCheckRegistry` (:718) pins the `_exit_code_for` error+unsupported exit-code axis; `TestMainDoctor` (:67) exercises exit codes end-to-end (`monkeypatch.chdir` + patched `sys.argv`)
- Net-new (EPIC-3436 A3): an agreement test asserting `_history_db_data()` and `_schema_drift_data()` return the same readability verdict on the same garbage file — no existing test cross-checks the two. **Caveat:** on builds where `SELECT 1` already raises (macOS/3.49.2 confirmed), both checks agree *today*, so this test passes before and after the fix and cannot catch a future regression to a constant-expression probe on those builds. It earns its keep only on the lazy-header builds. Pair it with the platform-independent guard below. **Scope it to garbage files:** on a 0-byte file the two checks disagree by design (`_schema_drift_data()` says `uninitialized`/informational; post-fix `_history_db_data()` says `unsupported`/error), so a generalized "same verdict on any bad file" assertion would fail
- Net-new (platform-independent): a test asserting `_is_sqlite_file()` returns `False` for a garbage file and `True` for a real DB, and that `_history_db_data()` classifies via the header check rather than via whatever `sqlite3.Error` the local build happens to raise. This is the only coverage in the set whose verdict does not depend on the host SQLite build. Extend it with the edge cases a naive implementation fails: sub-16-byte file → `False` without raising, 0-byte file → `False`, and `.ll/history.db` as a *directory* → `False` via the `OSError` path (plus an `_history_db_data()` variant asserting the directory case yields `unsupported`/`error` without raising — that assertion fails against a header read with no `OSError` handling)

### Documentation
- `docs/reference/CLI.md:398-476` — ll-doctor section; no change needed, verdict semantics are unchanged

### Configuration
- None — the probe has no config surface

## Expected Behavior

A `.ll/history.db` whose content is not a valid SQLite database must be reported as unreadable (`status=unsupported`, `severity=error`, note naming the failure) — never as healthy, **on every SQLite build and without depending on which exceptions a given build happens to raise**. The readability verdict must agree with `_schema_drift_data()`'s on the same file, enforced by a regression test, so the health check cannot silently degrade again (A3).

The corrected probe must also stay cheap: `_history_db_data()` runs twice per `ll-doctor` invocation against a database that reaches multiple GB, so the readability verdict must not cost more than a bounded header read.

## Proposed Solution

Validate the 16-byte header magic (`b"SQLite format 3\x00"`) by reading the first bytes of the file **before** connecting, and classify a mismatch as unreadable without ever handing the path to `sqlite3`. The header read itself must stay inside the never-raise convention: today every bad-path failure surfaces as `sqlite3.OperationalError` (directory-as-DB, unreadable permissions → "unable to open database file") and is caught, but a raw `open(db_path, "rb")` ahead of the connect puts `IsADirectoryError`/`PermissionError` outside any `try` — so `_is_sqlite_file()` must catch `OSError` and return `False` (magic unverifiable → not-SQLite is the safe verdict). Keep the existing read-only connect + statement probe behind it as the secondary check for files that carry a valid header but are damaged past it. Add a regression test that writes a garbage file and asserts the new probe classifies it as unreadable (and that `_schema_drift_data()` agrees), per EPIC-3436 A3.

**`PRAGMA quick_check` is rejected.** It was the alternative mechanism named in earlier revisions of this issue and fails on three counts, all measured against this project's real 7.88 GB `.ll/history.db`:

1. **Cost.** `PRAGMA quick_check` + `fetchone()` took **32.12 s**. `fetchone()` does not bound the work — SQLite must scan every page to produce the `ok` row. Two calls per run adds **~64 s** to a command that currently completes in **4.88 s** total (~14× slowdown, ~80,000× on the probe itself). The header read costs **22 µs**; `SELECT count(*) FROM sqlite_master` and `PRAGMA schema_version` both complete in **<1 ms** on the same 7.88 GB file.
2. **It does not raise on real corruption.** Against a database with a valid header and a deliberately smashed index, `quick_check` *returned a row* of corruption text (`'*** in database main ***\nTree 5 page 7 cell 15: Extends off end of page\n…'`) with no exception. `conn.execute("PRAGMA quick_check").fetchone()` without comparing the row to `'ok'` therefore still reports a corrupt database as healthy — it does not even fix the class of bug in this issue's title.
3. **Comparing to `'ok'` widens scope.** Doing so would flip any DB with minor index damage to `unsupported`/`error`, and hence `ll-doctor` to exit 1. That may be desirable, but it is a separate behavior change beyond this bug and needs its own decision.

Header magic is also the only candidate whose verdict is **platform-independent** — pure Python file I/O, no reliance on host SQLite behavior — which matters because the reported failure is itself build-specific and does not reproduce locally.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- The garbage-file regression test already exists: `TestHistoryDb::test_present_but_corrupt_reports_error` (`scripts/tests/test_cli_doctor_install_checks.py:193-203`) writes a 55-byte garbage file and asserts `unsupported`/`error` — it is the test failing on Linux CI, not a test to add. The net-new test work is only the agreement assertion against `_schema_drift_data()`; no existing test cross-checks the two checks
- Neither proposed mechanism has precedent in this codebase: no source invokes `PRAGMA quick_check`/`integrity_check`, and no constant or comparison for the `b"SQLite format 3\x00"` header magic exists repo-wide — both variants are net-new code
- The underlying mechanism is confirmed by precedent: a `mode=ro` connect succeeds on a non-database file and the error surfaces at the first executed statement (PRAGMA or SELECT alike) — documented and handled in `session_store/sessions.py` `_query_threads_db` (docstring ~:116-119), `issue_history/workspace_quality.py` `_open_member_readonly` (~:108-115), and `cli/doctor_trim.py` (catches `sqlite3.OperationalError` on first query, ~:282). A statement-level probe is the established family pattern; `SELECT 1` is the lone constant-expression probe that defeats it
- Whichever probe lands, the corrected verdict flows unchanged: `unsupported`/`error` → `_history_db_check()` → `_exit_code_for()` (exit 1 iff `severity == "error" and status == "unsupported"`, `doctor.py:125-127`); both statuses already exist in `CheckResult`'s Literal (`doctor.py:71`) and `_STATUS_SYMBOLS` (`doctor.py:36`)

_Added by `/ll:confidence-check` — 2026-09-10 — measured empirically, not inferred:_

- **Probe cost on the real database** (`.ll/history.db`, 7,884,320,768 bytes / 7.88 GB, read-only connect): `SELECT 1` 0.0004 s · `PRAGMA schema_version` <0.0001 s · `SELECT count(*) FROM sqlite_master` <0.0001 s · 16-byte header read 0.000022 s · **`PRAGMA quick_check` 32.12 s**. Whole-command baseline: `ll-doctor` completes in **4.88 s** today and reports History DB `✓` / Schema Drift `✓ structure matches recorded version 50`
- **`quick_check` does not raise on a valid-header corrupt DB.** Fixture: real DB, 500 rows, index created, then 200 bytes of the file tail overwritten with random data. `SELECT 1` → `(1,)`, `SELECT count(*) FROM sqlite_master` → `(2,)`, `PRAGMA schema_version` → `(2,)`, and `PRAGMA quick_check` → a single row of corruption text, **no exception**. Only a comparison against `'ok'` detects this case
- **Header magic + garbage body still raises on every probe.** A 4096-byte file beginning `b"SQLite format 3\x00"` followed by random bytes yields `DatabaseError: file is not a database` from all four statement probes — so the secondary connect+statement probe behind the header check retains real value and is not redundant
- **The reported bug does not reproduce on the development platform.** macOS / SQLite 3.49.2 / Python sqlite3 2.6.0: `SELECT 1` raises `DatabaseError: file is not a database` on both a 54-byte and a 55-byte `os.urandom` file. The Linux-only lazy-header behavior claimed in Root Cause is unconfirmed and no CI log is attached
- **`_history_db_data()` call sites confirmed**: `:464` (`_print_history_db_section`), `:475` (`_history_db_check`), `:1306` (`_print_report`, `--json` only). Text mode = 2 calls, JSON mode = 2 calls. `_schema_drift_data()` likewise at `:592`, `:603`, `:1307` — but its `_current_version`/`_schema_manifest` queries are metadata-only and stay cheap
- **No hot-path caller**: nothing in `hooks/`, `loops/*.yaml`, or `.github/workflows/confidence-check` invokes `ll-doctor` automatically. It is a manual diagnostic plus a suggested `ll-init` step (`init/cli.py:599`), so a probe regression degrades a human-run command rather than stalling automation — but it is still user-visible and unbounded in DB size

_Added by pre-implementation review — 2026-09-10:_

- **Diagnosis confirmed.** CI run 34519368279 (unit-tests job, 2026-09-10T19:31Z, Python 3.11.16) failed on exactly `TestHistoryDb::test_present_but_corrupt_reports_error` with `AssertionError: assert 'full' == 'unsupported'` — `SELECT 1` answered without touching page 1 on that Linux build. The same run's other failures (verify-evidence span gate — BUG-3442's territory — and `TestSseBridgeFanIn::test_producer_at_max_clients_backs_off_sub_linearly`) are unrelated to this check
- **Why `_schema_drift_data()` needs no header check:** its first statement (`_current_version()` → meta-table query) must read sqlite_master/page 1 on every build, which is why only the history_db test failed on CI while the schema-drift tests passed. The header check is only needed where the probe is a constant expression
- **OSError is the one unguarded path in the proposed design.** Today a directory-as-DB or unreadable-permissions file fails inside `sqlite3.connect()` as `sqlite3.OperationalError` (caught at doctor.py:457). A raw `open(db_path, "rb")` placed before the connect raises `IsADirectoryError`/`PermissionError` outside any `try`, violating the never-raise convention recorded in Conventions in Force. `_is_sqlite_file()` must catch `OSError → False`
- **0-byte verdict flips.** SQLite treats a 0-byte file as a valid empty database, so today's probe returns `full`; the header check classifies it `unsupported`/`error`. Desired — a truncated create should not read as healthy — but it is a behavior change to state, and it is why the A3 agreement test must stay scoped to garbage files

## Program Design

### Types

None new — statuses reuse the existing `full`/`unsupported` strings and the existing `CheckResult` dataclass.

### Signatures

- `_history_db_data() -> dict` (existing; probe body changes)
- `_is_sqlite_file(db_path: Path) -> bool` (new helper: reads the first 16 bytes and compares against `b"SQLite format 3\x00"`). Must tolerate a short read — a file under 16 bytes yields fewer bytes and must compare `False`, not raise. Must also catch `OSError` → `False` (unreadable path — directory, permissions — is not a confirmed-SQLite file), keeping `_history_db_data()` inside its never-raise convention. A 0-byte file compares `False`: **behavior change** — today SQLite treats 0-byte as a valid empty DB and the probe returns `full`; post-fix it reports `unsupported`/`error`, the desired verdict for a truncated create (see Implementation Steps step 5)
- `_SQLITE_HEADER_MAGIC = b"SQLite format 3\x00"` (new module constant; no such constant exists repo-wide today)

### Call Path

`_history_db_check()` / `_print_history_db_section()` / `_print_report()` -> `_history_db_data()` -> `_is_sqlite_file()` (pre-connect header check; mismatch returns `{"status": "unsupported", "severity": "error", "note": "unreadable: not a SQLite database (bad header magic)"}` without connecting) -> otherwise `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + the existing statement probe as the secondary check.

If the secondary statement probe is changed at all, it must stay O(1) in database size — `SELECT count(*) FROM sqlite_master` or `PRAGMA schema_version`, both measured <1 ms on the 7.88 GB file. **Not** `PRAGMA quick_check` (32.12 s, and silent on valid-header corruption unless compared to `'ok'`).

Constraints (unchanged): must not create the DB — keep the `Path.exists()` guard and read-only URI connect. New: the readability verdict must remain a bounded header read, because it is paid twice per invocation.

## Implementation Steps

1. **~~Attach the CI evidence first.~~ Done (2026-09-10 pre-implementation review).** CI run [`34519368279`](https://github.com/BrennonTWilliams/little-loops/actions/runs/34519368279) (unit-tests job, Python 3.11.16) confirms `TestHistoryDb::test_present_but_corrupt_reports_error` is the failing test — `assert 'full' == 'unsupported'` — so the diagnosis holds; proceed
2. The garbage-file verdict is correct on every SQLite build and every platform: `_history_db_data()` (`scripts/little_loops/cli/doctor.py:438`) classifies via the new `_is_sqlite_file()` header-magic check **before** connecting, so a non-SQLite file returns `unsupported`/`error` through a new `unreadable: not a SQLite database` note rather than depending on whether the host build raises. Header-magic validation does not exist anywhere in this codebase today; it is net-new. Route all header-read failures through `_is_sqlite_file()`'s `OSError → False` handling so a directory or unreadable file lands in the same `unsupported`/`error` dict rather than raising — today those cases fail inside `sqlite3.connect()` as `sqlite3.OperationalError` and are caught; the pre-connect read must not regress that
3. The existing regression test passes on Linux: `TestHistoryDb::test_present_but_corrupt_reports_error` (`scripts/tests/test_cli_doctor_install_checks.py:193`) already writes the garbage file and asserts `unsupported`/`error` — it is the failing CI test, not new work. Its assertion is unchanged; only the mechanism that satisfies it changes
4. Probe agreement is pinned: a new test asserts `_history_db_data()` and `_schema_drift_data()` return the same readability verdict (both `unsupported`/`error`) on the same garbage file (EPIC-3436 A3)
5. **Platform-independent coverage is added**, because step 4's agreement test passes both before and after the fix on any build where `SELECT 1` already raises: a direct `_is_sqlite_file()` test (garbage → `False`, real DB → `True`, sub-16-byte file → `False` without raising, 0-byte file → `False`, and `.ll/history.db` as a *directory* → `False` via the `OSError` path), plus an `_history_db_data()` variant asserting the directory case yields `unsupported`/`error` without raising — that assertion fails against a naive header read with no `OSError` handling
6. The never-create and read-only invariants hold: `test_absent_is_informational_and_does_not_create` and the byte-identity convention (`test_never_creates_or_migrates_database`) still pass. The header check must open the file read-only (`"rb"`) and must not create it — the `Path.exists()` guard stays ahead of it
7. **Probe cost is unchanged**: `ll-doctor` wall time on this project's real 7.88 GB `.ll/history.db` stays at ~5 s. Do **not** introduce `PRAGMA quick_check` (32.12 s per call × 2 calls per run). If the secondary statement probe is touched at all, re-time it against the real DB, not a `tmp_path` fixture
8. Verification: `python -m pytest scripts/tests/test_cli_doctor_install_checks.py scripts/tests/test_cli_doctor.py -v` exits 0 locally, **plus** a Linux CI run showing `test_present_but_corrupt_reports_error` flip from fail to pass. The success criterion is *that test* passing, **not** a green run: run 34519368279 also carries unrelated failures (verify-evidence span gate — BUG-3442's territory — and `TestSseBridgeFanIn::test_producer_at_max_clients_backs_off_sub_linearly`). Local green is necessary but not sufficient — it was already green before the fix

## Impact

- **Priority**: P2 - Health check silently lies about corrupt state; no data loss by itself, but it masks real corruption and undermines ll-doctor's diagnostic purpose (child of P1 EPIC-3436).
- **Effort**: Small - One probe body swap plus one new helper, one module constant, and two regression tests; no schema or API changes.
- **Risk**: Low **for the header-magic fix** - Contained to doctor's read-only probe; a 16-byte `"rb"` read cannot mutate the DB and costs 22 µs. Residual risks: (a) the header check alone cannot detect a valid-header-but-damaged database, so the existing connect+statement probe must stay behind it as the secondary check; (b) the pre-connect header read must catch `OSError` or it introduces an uncaught-exception crash path (directory/unreadable file) that today's `sqlite3.Error`-caught probe does not have; (c) the 0-byte verdict flips from `full` to `unsupported`/`error` — intended, but a behavior change to state. The diagnosis itself is **confirmed** (CI run 34519368279; see Root Cause), removing the prior unverified-premise risk.
  - **Risk of the rejected `quick_check` variant was NOT low.** The prior text of this issue claimed `PRAGMA quick_check` "is cheap on a quick fetchone"; measured on this project's real 7.88 GB `.ll/history.db` it takes **32.12 s per call**, and `_history_db_data()` runs **twice per `ll-doctor` invocation** — ~64 s added to a 4.88 s command (~14× slower). `fetchone()` does not bound the scan. It is also silent on valid-header corruption (returns a row of findings rather than raising), so it would not fully fix the titled bug without an added `== 'ok'` comparison that in turn widens scope. Test fixtures use `tmp_path` DBs of a few KB and would never have caught this.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- **The diagnosis is unconfirmed.** The Linux lazy-header mechanism does not reproduce locally: on macOS / SQLite 3.49.2 all four candidate probes — including the current `SELECT 1` — raise `DatabaseError: file is not a database` on 54- and 55-byte garbage. No CI log is attached to this issue. Implementation Steps step 1 now requires attaching the failing job output before code changes; if a different test is failing on Linux, the probe swap will not fix the observed symptom. **Resolved 2026-09-10 (pre-implementation review):** CI run 34519368279 shows exactly this test failing with `assert 'full' == 'unsupported'` — diagnosis confirmed; see Root Cause.
- **The originally proposed mechanism was rejected on measured cost.** `PRAGMA quick_check` took 32.12 s against this project's real 7.88 GB `.ll/history.db`, and `_history_db_data()` runs twice per `ll-doctor` invocation (~64 s added to a 4.88 s command). It is also silent on valid-header corruption, returning a findings row rather than raising. The issue now mandates the 16-byte header-magic pre-check (22 µs, platform-independent) with the statement probe retained as a secondary check.
- **The A3 agreement test cannot regress-guard on this platform.** Where `SELECT 1` already raises, `_history_db_data()` and `_schema_drift_data()` agree today, so the agreement test passes before and after the fix. A platform-independent `_is_sqlite_file()` test was added to Implementation Steps step 5 to carry that weight instead.
- **Probe cost is invisible to the test suite.** Fixtures use `monkeypatch.chdir(tmp_path)` databases of a few KB, so a future O(DB-size) probe would pass every test while adding a minute to real invocations. Step 7 pins the ~5 s wall-time expectation explicitly.


## Session Log
- Pre-implementation review (direct session) - 2026-09-10 - CI evidence attached (run 34519368279); OSError never-raise gap, 0-byte verdict flip, and agreement-test scoping folded in
- `/ll:confidence-check` - 2026-09-11T03:46:23 - `3c54b1f6-0a02-45d5-aeb1-ed084c2c42f8.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:26:08 - `02118696-855f-4cc5-9fdd-f4b3209b4230.jsonl`
- `/ll:format-issue` - 2026-09-10T22:03:12 - `7aab593c-b8b9-4480-bbb1-55d17a6f8a70.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
