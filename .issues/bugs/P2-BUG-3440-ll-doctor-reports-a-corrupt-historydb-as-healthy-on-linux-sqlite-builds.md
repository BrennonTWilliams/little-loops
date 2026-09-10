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
---

# BUG-3440: ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds

## Summary

_history_db_data (cli/doctor.py ~451-459) probes readability with `SELECT 1`, a constant expression that does not force a page-1 header read on every SQLite build; on CI a 54-byte garbage file returns status=full instead of unsupported. Replace with `PRAGMA quick_check` or validate the 16-byte header magic before connecting, and add a regression test asserting both probes agree so the check cannot silently degrade again (A3).

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

### Tests
- `scripts/tests/test_cli_doctor_install_checks.py` — `TestHistoryDb::test_present_but_corrupt_reports_error` (:193-203) already writes a 55-byte garbage file and asserts `unsupported`/`error`: this is the test failing on Linux CI, not a test to add. `test_present_and_readable_is_full` (:176) builds a real DB via raw `sqlite3.connect`; `test_absent_is_informational_and_does_not_create` (:164) pins no-create
- `scripts/tests/test_cli_doctor.py` — `TestCheckRegistry` (:718) pins the `_exit_code_for` error+unsupported exit-code axis; `TestMainDoctor` (:67) exercises exit codes end-to-end (`monkeypatch.chdir` + patched `sys.argv`)
- Net-new (EPIC-3436 A3): an agreement test asserting `_history_db_data()` and `_schema_drift_data()` return the same readability verdict on the same garbage file — no existing test cross-checks the two

### Documentation
- `docs/reference/CLI.md:398-476` — ll-doctor section; no change needed, verdict semantics are unchanged

### Configuration
- None — the probe has no config surface

## Expected Behavior

A `.ll/history.db` whose content is not a valid SQLite database must be reported as unreadable (`status=unsupported`, `severity=error`, note naming the failure) — never as healthy. The readability verdict must agree with `_schema_drift_data()`'s on the same file, enforced by a regression test, so the health check cannot silently degrade again (A3).

## Proposed Solution

Replace the `SELECT 1` probe in `_history_db_data()` with one that forces an actual database read — `conn.execute("PRAGMA quick_check").fetchone()` — or validate the 16-byte header magic (`b"SQLite format 3\x00"`) by reading the first bytes of the file before connecting. Add a regression test that writes a garbage file and asserts the new probe classifies it as unreadable (and that `_schema_drift_data()` agrees), per EPIC-3436 A3.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- The garbage-file regression test already exists: `TestHistoryDb::test_present_but_corrupt_reports_error` (`scripts/tests/test_cli_doctor_install_checks.py:193-203`) writes a 55-byte garbage file and asserts `unsupported`/`error` — it is the test failing on Linux CI, not a test to add. The net-new test work is only the agreement assertion against `_schema_drift_data()`; no existing test cross-checks the two checks
- Neither proposed mechanism has precedent in this codebase: no source invokes `PRAGMA quick_check`/`integrity_check`, and no constant or comparison for the `b"SQLite format 3\x00"` header magic exists repo-wide — both variants are net-new code
- The underlying mechanism is confirmed by precedent: a `mode=ro` connect succeeds on a non-database file and the error surfaces at the first executed statement (PRAGMA or SELECT alike) — documented and handled in `session_store/sessions.py` `_query_threads_db` (docstring ~:116-119), `issue_history/workspace_quality.py` `_open_member_readonly` (~:108-115), and `cli/doctor_trim.py` (catches `sqlite3.OperationalError` on first query, ~:282). A statement-level probe is the established family pattern; `SELECT 1` is the lone constant-expression probe that defeats it
- Whichever probe lands, the corrected verdict flows unchanged: `unsupported`/`error` → `_history_db_check()` → `_exit_code_for()` (exit 1 iff `severity == "error" and status == "unsupported"`, `doctor.py:125-127`); both statuses already exist in `CheckResult`'s Literal (`doctor.py:71`) and `_STATUS_SYMBOLS` (`doctor.py:36`)

## Program Design

### Types

None new — statuses reuse the existing `full`/`unsupported` strings and the existing `CheckResult` dataclass.

### Signatures

- `_history_db_data() -> dict` (existing; probe body changes)
- `_is_sqlite_file(db_path: Path) -> bool` (new helper: reads the first 16 bytes and compares against `b"SQLite format 3\x00"`)

### Call Path

`_history_db_check()` / `_print_history_db_section()` / `_print_report()` -> `_history_db_data()` -> `_is_sqlite_file()` (pre-connect header check) or `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + `PRAGMA quick_check`

Constraint (unchanged): must not create the DB — keep the `Path.exists()` guard and read-only URI connect.

## Implementation Steps

1. The garbage-file verdict is correct on every SQLite build: the probe inside `_history_db_data()` (`scripts/little_loops/cli/doctor.py:438`) forces an actual database read — a statement-level probe such as `PRAGMA quick_check`, or a pre-connect 16-byte header-magic check — so a non-SQLite file raises `sqlite3.Error` into the existing `unreadable: {exc}` path (`doctor.py:458`). Neither `quick_check` nor header-magic validation exists anywhere in this codebase today; both are net-new
2. The existing regression test passes on Linux: `TestHistoryDb::test_present_but_corrupt_reports_error` (`scripts/tests/test_cli_doctor_install_checks.py:193`) already writes the garbage file and asserts `unsupported`/`error` — it is the failing CI test, not new work
3. Probe agreement is pinned: a new test asserts `_history_db_data()` and `_schema_drift_data()` return the same readability verdict (both `unsupported`/`error`) on the same garbage file (EPIC-3436 A3)
4. The never-create and read-only invariants hold: `test_absent_is_informational_and_does_not_create` and the byte-identity convention (`test_never_creates_or_migrates_database`) still pass
5. Verification: `python -m pytest scripts/tests/test_cli_doctor_install_checks.py scripts/tests/test_cli_doctor.py -v` exits 0 — on a Linux SQLite build specifically, `test_present_but_corrupt_reports_error` flips from fail to pass

## Impact

- **Priority**: P2 - Health check silently lies about corrupt state; no data loss by itself, but it masks real corruption and undermines ll-doctor's diagnostic purpose (child of P1 EPIC-3436).
- **Effort**: Small - One probe body swap plus one new helper and regression test; no schema or API changes.
- **Risk**: Low - Contained to doctor's read-only probe; `PRAGMA quick_check` is cheap on a quick fetchone and cannot mutate the DB.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-10T23:26:08 - `02118696-855f-4cc5-9fdd-f4b3209b4230.jsonl`
- `/ll:format-issue` - 2026-09-10T22:03:12 - `7aab593c-b8b9-4480-bbb1-55d17a6f8a70.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
