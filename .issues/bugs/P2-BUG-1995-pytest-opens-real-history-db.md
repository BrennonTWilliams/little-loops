---
id: BUG-1995
type: BUG
priority: P2
status: open
captured_at: '2026-06-07T01:32:37Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
labels:
- testing
- session-store
- isolation
confidence_score: 82
outcome_confidence: 76
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 17
---

# BUG-1995: pytest opens the real `.ll/history.db` instead of an isolated temp DB

## Summary

During the investigation of the `ll-issues` "table tool_events already exists"
crash, `lsof .ll/history.db` showed **two live `python -m pytest` processes
holding the project's real `.ll/history.db` open** (FDs `11u`/`12r`/`13u`),
alongside the expected `ll-loop` and `ll-auto` runs. Tests should never touch
the real per-project database — some code path or fixture exercised during the
suite opens `DEFAULT_DB_PATH` (`.ll/history.db`) rather than a `tmp_path`-scoped
file.

## Current Behavior

Running `python -m pytest scripts/tests/` opens and holds a connection to the
real `.ll/history.db`. This both **pollutes real session history** with
test-generated rows and **contributes to lock contention** against concurrent
`ll-*` processes (it was one of four processes locking the DB at crash time).

## Expected Behavior

The test suite must be fully isolated from the real project database. No pytest
process should ever open `.ll/history.db`; every test that touches the session
store should write to a `tmp_path`-scoped DB (most already pass an explicit
`db` path — the gap is the code path that defaults to `DEFAULT_DB_PATH`).

## Motivation

- **Data integrity**: test runs silently injecting rows into the real history DB
  corrupts analytics (`ll-history`, `ll-ctx-stats`, correction mining, SFT corpus).
- **Concurrency**: a stray test connection widens the lock-contention window that
  produced the original `ll-issues` crash (see Related).
- **Reproducibility**: tests that read shared state are order-dependent and flaky.

## Steps to Reproduce

1. Start a test run: `python -m pytest scripts/tests/ -q`
2. While it runs, in another shell: `lsof .ll/history.db`
3. Observe one or more `python` (pytest) processes holding the real DB open.

## Root Cause

Not yet pinpointed. Candidate sources of the unscoped open:

- A fixture or test that calls `connect()` / `ensure_db()` / `SQLiteTransport()`
  / `cli_event_context()` / `backfill*()` with no `db_path`, so it defaults to
  `DEFAULT_DB_PATH = .ll/history.db` (`scripts/little_loops/session_store.py`).
- Code-under-test that resolves `DEFAULT_DB_PATH` relative to the CWD instead of
  accepting an injected path, invoked by a test without monkeypatching CWD or the
  default.
- A hook handler test (e.g. `session_start`) that runs the real hook against the
  project root.

Investigation: `grep -rn "DEFAULT_DB_PATH\|history.db" scripts/tests/` and audit
any session_store entry point called without an explicit `db`/`db_path` argument.

## Proposed Solution

1. Identify the unscoped call site(s) via `lsof` + grep audit above.
2. Either pass an explicit `tmp_path` DB everywhere, or add an autouse fixture in
   `scripts/tests/conftest.py` that monkeypatches
   `little_loops.session_store.DEFAULT_DB_PATH` (and any hook-resolved default)
   to a `tmp_path` location for the whole session, so a missed explicit arg can
   never escape to the real DB.
3. Add a guard test asserting `.ll/history.db` is not opened during the suite
   (e.g. assert the real file's mtime/size is unchanged across a representative
   test, or that `DEFAULT_DB_PATH` points outside the repo during tests).

## Integration Map

- `scripts/little_loops/session_store.py` — `DEFAULT_DB_PATH`, `connect`,
  `ensure_db`, `SQLiteTransport`, `cli_event_context`, `backfill*`.
- `scripts/tests/conftest.py` — candidate location for the isolation fixture.
- Hook handlers under `scripts/little_loops/hooks/` that open the store on
  `session_start`.

## Implementation Steps

1. Audit: `lsof` during a run + grep for default-path entry points called in tests.
2. Add autouse isolation fixture in `conftest.py` (belt-and-suspenders).
3. Fix any test/code that genuinely needs an explicit path.
4. Add a regression guard that fails if the real DB is opened during tests.
5. Run full suite; confirm `lsof .ll/history.db` shows no pytest process.

## Impact

- **Severity**: real-history pollution + flaky/order-dependent tests; aggravates
  the DB lock-contention class of bugs.
- **Scope**: test suite hygiene + session-store default-path handling.
- **Risk if unfixed**: corrupted analytics and recurring intermittent lock crashes.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopssession_store` | session store public API & defaults |
| `.claude/CLAUDE.md` § Automation: Scratch Pad | per-instance artifact isolation philosophy |

Related: surfaced while fixing the `ll-issues` `table tool_events already exists`
crash (lock-contention race in `session_store._current_version` /
`_apply_migrations`).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-06_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 76/100 → MODERATE

### Concerns
- Root cause is not pinpointed to a specific file:line. Three candidate sources are listed but unconfirmed. Implementation should begin with the `lsof`+grep investigation, not with writing code.

### Gaps to Address
- Run the lsof investigation first: start the test suite in background, then `lsof .ll/history.db` to identify the actual leaking module/test. The grep audit alone (`grep -rn "DEFAULT_DB_PATH\|history.db" scripts/tests/`) won't confirm the active call site.
- Verify that `test_issue_manager.py`'s `config.project_root / ".ll" / "history.db"` usage is within a temp fixture dir and not contributing to the leak (appears safe from fixture analysis but confirm with lsof).
- After lsof identifies the site, confirm whether the autouse conftest monkeypatch alone is sufficient or whether explicit path fixes are also needed.

## Session Log
- `/ll:format-issue` - 2026-06-07T01:34:42 - `784755b2-ee36-4dab-b9ae-65246aa23931.jsonl`
- `/ll:capture-issue` - 2026-06-07T01:32:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5141031e-db2a-4193-90dd-496d74847e81.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d80b8-1a92-406b-86d8-7de5a29b6f5b.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
