---
id: ENH-3426
type: ENH
title: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:42Z'
---

# ENH-3426: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently

## Summary

Every `ll-*` CLI entry point wraps its body in `cli_event_context` (`scripts/little_loops/session_store/writers.py:505-548`), which opens `.ll/history.db`, inserts a `cli_events` row, and updates it with exit code and duration on exit. When `history.db` is very large (the live source checkout's is 7.6 GB) or held by a concurrent writer, a machine consumer of a JSON-emitting command (`ll-queue list --json`, `ll-loop show -j`, `ll-issues ... --json`) can observe the failure mode the ll-console agent reported on 2026-09-09: the process dies with empty stdout. ll-console tolerates it (non-zero exit maps to its `QueueError`), but the contract for a JSON-emitting CLI should be explicit: exit non-zero **and** print a diagnostic to stderr, never a silent empty stdout.

## What Is Verified

- On this checkout, with the same 7.6 GB `history.db`, `ll-queue list --json` returned exit 0 with `[]` on stdout in 0.2 s. The crash **did not reproduce** here. The likely trigger was a concurrent writer holding the SQLite lock while the ll-console session ran it.
- `cli_event_context` already catches `sqlite3.Error` on the insert (writers.py:528) and logs a warning rather than raising, so the insert path is not the hole. Unhandled surfaces remain: `resolve_history_db` / `_pkg.connect` (schema migration or WAL checkpoint on a huge file, writers.py:520-521 runs inside the try but `connect` may block on `busy_timeout` rather than raise), the `finally` UPDATE (writers.py:543 onward), and any non-`sqlite3.Error` exception (e.g. `OSError` from disk-full, `MemoryError`) escaping either.

## Proposed Hardening

1. Establish the failure contract first: ask the ll-console side for the exact stderr and exit code from the observed failure before changing behavior. If stderr was empty on a non-zero exit, that is the defect; if stdout was empty on exit 0, that is a different and worse defect.
2. Make the history writer best-effort on every path: wrap `connect` and the `finally` UPDATE in the same `sqlite3.Error`/`OSError` guard as the insert, with a bounded `busy_timeout` (e.g. 2 s) so a locked or slow DB degrades to "no analytics row" instead of stalling or killing the command.
3. Consider a size guard: when `history.db` exceeds a configurable threshold, skip the `cli_events` write and emit a one-line stderr warning pointing at the compaction command. Do **not** auto-compact or prune (see project rule: raw_events deletion is manual-only).
4. Add a test that simulates a locked DB (second connection holding an exclusive lock) and asserts the wrapped command still emits its JSON on stdout with exit 0, plus a warning on stderr.

## Context

Belongs with the in-flight session-store lifecycle work (FEAT-3417, ENH-3420). Flagged by the ll-console agent as a concern to route here rather than PR themselves.

## Acceptance Criteria

- [ ] Any exception raised by the history writer (connect, insert, finally-update) is caught and logged; the wrapped command's stdout and exit code are unaffected.
- [ ] `busy_timeout` on the `cli_events` connection is bounded and documented.
- [ ] Test: locked `history.db` → `ll-queue list --json` prints valid JSON, exits 0, warning on stderr.
- [ ] If a size guard is added, it is opt-in via config with a documented default and never deletes data.


## Current Behavior

`cli_event_context` (`writers.py:483-561`) already catches `sqlite3.Error` on
both the insert (`writers.py:528`) and the `finally` UPDATE (`writers.py:552`)
and degrades to a no-op with a `logger.warning`. It does **not** catch
non-`sqlite3.Error` exceptions (`OSError` from disk-full, `MemoryError`) that
could escape `_pkg.connect()` (`writers.py:521`) or the UPDATE, and `connect()`
sets no explicit `busy_timeout`, so a long-held lock can block the wrapped
command rather than fail fast into the existing warning path.

## Expected Behavior

Every `ll-*` JSON-emitting CLI wrapped by `cli_event_context` exits
deterministically: on any history-writer failure (locked DB, oversized DB,
disk-full, OOM) the wrapped command still completes and prints its JSON on
stdout with exit 0, plus a one-line warning on stderr — never a silent
empty-stdout hang or crash.

## Motivation

This enhancement would:
- Eliminate a failure mode where analytics-row writes to `history.db` (a
  side-channel, not the CLI's actual payload) can crash or hang a
  machine-facing JSON CLI, corrupting automation that parses
  `ll-queue list --json` / `ll-loop show -j` / `ll-issues ... --json` output.
- Business value: keeps ll-console and other machine consumers reliable even
  when `history.db` is large (7.6 GB on the live checkout) or lock-contended.
- Technical debt: closes the one remaining unguarded path (`connect` and the
  `finally` UPDATE only catch `sqlite3.Error`, not `OSError`) in an otherwise
  best-effort writer.

## Proposed Solution

See `## Proposed Hardening` above for the full plan. Summary: widen the
`except sqlite3.Error` guards already on the insert (`writers.py:528`) and
`finally` UPDATE (`writers.py:552`) to also catch `OSError` around `connect`
(`writers.py:521`) and the UPDATE call, add a bounded `busy_timeout` (e.g. 2s)
to the connection, and consider an opt-in size guard that skips the write
above a configurable `history.db` threshold — never auto-compacting.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` (`cli_event_context`, `writers.py:483-561`)

### Dependent Files (Callers/Importers)
- Every `ll-*` CLI entry point wraps its body in `cli_event_context` — no
  per-caller changes needed; verify with
  `grep -rn "cli_event_context" scripts/little_loops/`

### Similar Patterns
- `skill_event_context` (same file, `writers.py:587` onward) is the
  best-effort analogue for skill-host completions; keep its error handling
  consistent with any widened guard added here.

### Tests
- `scripts/tests/test_session_store_writers.py`
- `scripts/tests/test_ll_session.py`
- `scripts/tests/test_issue_history_cli.py`

### Documentation
- `docs/reference/API.md` (session_store writers section), if the
  `busy_timeout` or size-guard behavior becomes externally documented

### Configuration
- N/A, unless the size guard (Proposed Hardening step 3) is added, in which
  case it needs a new opt-in key under `history` in
  `scripts/little_loops/config-schema.json`

## Program Design

### Types

- No new types — reuses `sqlite3.Connection`, existing `cli_events` schema.

### Signatures

- `cli_event_context(binary: str, args: list[str] | None, db_path: Path | None, config: dict | None) -> ContextManager[None]` (unchanged signature, `writers.py:483`)
- Internal: `_pkg.connect(effective_path, timeout=2.0)` — add explicit `timeout` kwarg at `writers.py:521`

### Call Path

`cli_event_context` (`writers.py:483`) -> `_pkg.connect` (`writers.py:521`, widened `except (sqlite3.Error, OSError)`) -> `conn.execute(...UPDATE cli_events...)` (`writers.py:547`, same widened guard)

## Implementation Steps

1. Confirm the exact failure contract from ll-console (stderr content, exit
   code) before changing behavior (Proposed Hardening step 1).
2. Widen the `except sqlite3.Error` guards around `connect` and the `finally`
   UPDATE to also catch `OSError`, and set a bounded `busy_timeout`.
3. Add the opt-in size-guard config key and stderr warning, if pursued.
4. Add a locked-DB test asserting the wrapped command still emits JSON on
   stdout with exit 0 and a stderr warning.

## Impact

- **Priority**: P3 - affects automation reliability, but only under a
  hard-to-reproduce lock-contention/oversized-DB trigger; not user-facing by
  default.
- **Effort**: Small - a widened except clause plus a `busy_timeout` kwarg,
  scoped to one function.
- **Risk**: Low - only touches a best-effort analytics side-channel with
  existing `sqlite3.Error`-catching precedent in the same function.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3

## Success Metrics

- Locked-DB regression test (Acceptance Criteria item 3) passes and stays
  green in CI.
- No further silent empty-stdout reports against `ll-*` JSON CLIs after the
  fix ships.

## Scope Boundaries

- **In scope**: hardening `cli_event_context`'s connect/insert/finally-UPDATE
  paths, a bounded `busy_timeout`, an optional opt-in size guard, and
  confirming the ll-console stderr/exit-code contract first.
- **Out of scope**: auto-compaction or pruning of `history.db` (manual-only
  per project rule — see `raw_events` compact()/prune()), replacing SQLite as
  the history store, and any change to the `cli_events` schema.

## API/Interface

N/A - no public API changes; `cli_event_context`'s call signature is
unchanged, only its internal error handling widens (optional `busy_timeout`
becomes a connection-level default, not a new parameter).


## Session Log
- `/ll:format-issue` - 2026-09-09T22:40:10 - `419c0f66-ac03-408b-af11-4cdc8ba58375.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
