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

## Expected Behavior

A `.ll/history.db` whose content is not a valid SQLite database must be reported as unreadable (`status=unsupported`, `severity=error`, note naming the failure) — never as healthy. The readability verdict must agree with `_schema_drift_data()`'s on the same file, enforced by a regression test, so the health check cannot silently degrade again (A3).

## Proposed Solution

Replace the `SELECT 1` probe in `_history_db_data()` with one that forces an actual database read — `conn.execute("PRAGMA quick_check").fetchone()` — or validate the 16-byte header magic (`b"SQLite format 3\x00"`) by reading the first bytes of the file before connecting. Add a regression test that writes a garbage file and asserts the new probe classifies it as unreadable (and that `_schema_drift_data()` agrees), per EPIC-3436 A3.

## Program Design

### Types

None new — statuses reuse the existing `full`/`unsupported` strings and the existing `CheckResult` dataclass.

### Signatures

- `_history_db_data() -> dict` (existing; probe body changes)
- `_is_sqlite_file(db_path: Path) -> bool` (new helper: reads the first 16 bytes and compares against `b"SQLite format 3\x00"`)

### Call Path

`_history_db_check()` / `_print_history_db_section()` / `_print_report()` -> `_history_db_data()` -> `_is_sqlite_file()` (pre-connect header check) or `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + `PRAGMA quick_check`

Constraint (unchanged): must not create the DB — keep the `Path.exists()` guard and read-only URI connect.

## Impact

- **Priority**: P2 - Health check silently lies about corrupt state; no data loss by itself, but it masks real corruption and undermines ll-doctor's diagnostic purpose (child of P1 EPIC-3436).
- **Effort**: Small - One probe body swap plus one new helper and regression test; no schema or API changes.
- **Risk**: Low - Contained to doctor's read-only probe; `PRAGMA quick_check` is cheap on a quick fetchone and cannot mutate the DB.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-10T22:03:12 - `7aab593c-b8b9-4480-bbb1-55d17a6f8a70.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
