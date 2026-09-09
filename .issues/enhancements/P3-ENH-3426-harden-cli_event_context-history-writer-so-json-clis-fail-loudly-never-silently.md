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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `resolve_history_db(db_path)` (`writers.py:506`) is **not** inside any try/except — it runs unconditionally before the `if gate_open:` block (`writers.py:519`) and the `try:` that guards the INSERT (`writers.py:520`). This corrects the "What Is Verified" claim that "writers.py:520-521 runs inside the try" for both `resolve_history_db` and `connect` together: only `_pkg.connect()` (line 521) is inside the try; `resolve_history_db()` (line 506) is fully unguarded, as is the `config`-gating block (`writers.py:512-518`, `AnalyticsCaptureConfig.from_dict`/`feature_enabled_for`). Any exception from `resolve_history_db` → `_resolve_db_path` (`session_store/db.py:72`) propagates before the wrapped CLI body ever runs — the whole `ll-*` command crashes, not just the analytics row.
- The claim "`connect()` sets no explicit `busy_timeout`" is inaccurate. `connect()` (`schema.py:1560-1569`) calls `ensure_db(path)` then `_configure_connection(conn)` (`schema.py:1392-1408`), which unconditionally executes `PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}` (`_BUSY_TIMEOUT_MS = 5000`, `schema.py:124`) on every connection opened through `connect()` — including `cli_event_context`'s. That pragma call has its own narrow `except sqlite3.OperationalError` (`schema.py:1407`), separate from `cli_event_context`'s guard. A busy_timeout already exists (5s, applied via SQLite `PRAGMA`, not the `sqlite3.connect(timeout=...)` Python kwarg).

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
- Confirmed: 41 distinct `main_*()` call sites, each individually wrapping
  its own body (not a central dispatcher). One documented non-caller:
  `scripts/little_loops/mcp_server/__init__.py:31` (long-running process,
  not a one-shot CLI invocation).

### Similar Patterns
- `skill_event_context` (same file, `writers.py:587` onward) is the
  best-effort analogue for skill-host completions; keep its error handling
  consistent with any widened guard added here.

### Tests
- `scripts/tests/test_session_store_writers.py`
- `scripts/tests/test_ll_session.py`
- `scripts/tests/test_issue_history_cli.py`
- Two tests already exercise `cli_event_context` under a simulated locked DB: `TestCliEventContext.test_cli_event_locked_db_does_not_crash_body` (`test_session_store_writers.py:489-511`) monkeypatches `connect` to raise `sqlite3.OperationalError("database is locked")` on the INSERT and asserts the wrapped body still runs; `.test_cli_event_locked_exit_update_does_not_mask_success` (`test_session_store_writers.py:513-542`) does the same for the exit UPDATE via a connection proxy that raises on the `UPDATE cli_events` statement. Neither asserts stderr warning content, and both simulate `sqlite3.OperationalError` specifically, not `OSError`.
- `test_still_exits_zero_when_db_unwritable` (`test_ll_issues_research_triage.py:140-157`) is the closest existing precedent to Acceptance Criteria item 3: it monkeypatches `connect` to raise `sqlite3.OperationalError`, invokes the full `ll-issues research-triage ... --json` CLI, and asserts exit code 0 with valid JSON parsed from stdout. No existing test does this for `ll-queue list --json` specifically, and none of the three tests found assert a stderr warning was emitted.
- Every locked-DB test found in the suite (also `test_set_status_cli.py:1286-1325`, `test_hook_post_tool_use.py:189-193`) simulates the failure via `monkeypatch.setattr(<module>, "connect", <raising stub>)`; no test in `scripts/tests/` opens a genuine second `sqlite3.Connection` and holds a real `BEGIN IMMEDIATE`/`BEGIN EXCLUSIVE` lock against the writer under test.

### Documentation
- `docs/reference/API.md` (session_store writers section), if the
  `busy_timeout` or size-guard behavior becomes externally documented

### Configuration
- N/A, unless the size guard (Proposed Hardening step 3) is added, in which
  case it needs a new opt-in key under `history` in
  `scripts/little_loops/config-schema.json`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed via grep: `cli_event_context` is wired per-CLI, not through a central dispatcher — 41 distinct `main_*()` entry points each individually call `with cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:]):` around their body (e.g. `cli/issues/__init__.py:21`, `cli/queue.py:923`, `cli/harness.py:1751`, `cli/docs.py:23,126,252,329`). One documented exception: `mcp_server/__init__.py:31` explicitly notes no `cli_event_context()` wrapper is used there (a long-running process, not a one-shot CLI invocation).
- `cli_event_context`'s current guard shape (narrow `except sqlite3.Error` around the INSERT and the exit UPDATE, each independently wrapped, `writers.py:519-536` and `writers.py:543-560`) is itself the result of a prior fix, `BUG-2706` (status `done`, `.issues/bugs/P2-BUG-2706-cli-event-context-crashes-every-ll-cli-on-locked-db.md`) — not the pre-hardening baseline the issue's framing implies. BUG-2706 names `skill_event_context` as the contract it brought `cli_event_context` into line with, and its postmortem states `_BUSY_TIMEOUT_MS = 5000` was deliberately left unchanged during that fix ("raising it only makes contended commands hang longer").
- `skill_event_context` (`writers.py:577-665`) is not fully consistent with `cli_event_context` today, despite being cited as the analogue to match: its final `finally: conn.close()` (`writers.py:665`) is a bare, unguarded call, whereas `cli_event_context`'s equivalent close calls (`writers.py:530-534`, `writers.py:556-560`) are each independently wrapped in `try/except sqlite3.Error: pass`. Two other EPIC-1707-tagged best-effort writers in the same file — `record_hook_event`/`hook_event_context` — follow the same internal-guard shape as `cli_event_context`; a second, distinct best-effort convention also exists in the file (`record_prompt_opt_event`, `record_correction`, `record_skill_event`), which raises unguarded and relies on the *caller* wrapping in `contextlib.suppress(Exception)` rather than guarding internally.
- No existing site anywhere in the codebase pairs `except (sqlite3.Error, OSError)` (checked both orderings, repo-wide) — the only occurrence of that tuple is this issue's own prose. Pairing `OSError` with an unrelated exception type in one guard is otherwise a routine, widely-used convention elsewhere in the codebase (`fsm/persistence.py`, `fleet_improve.py`, `decisions.py`), so widening the guard here would follow an established pattern shape, just not one previously applied to this specific pair at this call site.
- Config-key precedent for a size-gated behavior on `history.db`: `analytics.retention.min_db_size_mb` (`config-schema.json:2087-2108`, default 800) is dual-gated with `min_project_age_days` and consumed via `RetentionConfig.from_dict()` (`config/features.py:1485-1509`) inside `lifecycle.py::prune()` (`lifecycle.py:1273-1358`), which measures size via `db_path.stat().st_size / (1024*1024)`. This is the codebase's only existing "declared threshold, read via a dataclass, compared against `history.db`'s on-disk size" shape — for pruning, not for skipping a write — and is the closest structural precedent if the opt-in size guard (Proposed Hardening step 3) is pursued. (Test-coverage findings folded into the existing `### Tests` subsection above rather than a second `### Tests` heading here.)

## Program Design

### Types

- No new types — reuses `sqlite3.Connection`, existing `cli_events` schema.

### Signatures

- `cli_event_context(binary: str, args: list[str] | None, db_path: Path | None, config: dict | None) -> ContextManager[None]` (unchanged signature, `writers.py:483`)
- Internal: `_pkg.connect(effective_path, timeout=2.0)` — add explicit `timeout` kwarg at `writers.py:521`

### Call Path

`cli_event_context` (`writers.py:483`) -> `_pkg.connect` (`writers.py:521`, widened `except (sqlite3.Error, OSError)`) -> `conn.execute(...UPDATE cli_events...)` (`writers.py:547`, same widened guard)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Actual current signature (`writers.py:483-488`): `cli_event_context(db_path: Path | str = DEFAULT_DB_PATH, binary: str = "", args: list[str] | None = None, config: dict | None = None) -> Generator[None, None, None]`. This corrects the "Signatures" entry above: param order is `db_path, binary, args, config` (not `binary`-first), `db_path` defaults to `DEFAULT_DB_PATH` (not `None`), and the return annotation is `Generator[None, None, None]` (not `ContextManager[None]`). Confirmed against all 41 real call sites, which pass positionally as `cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:])` (e.g. `cli/issues/__init__.py:21`, `cli/queue.py:923`, `cli/session.py:424`).
- `_pkg.connect` (`writers.py:521`) resolves to `little_loops.session_store.connect`, re-exported verbatim from `schema.connect` (`schema.py:1560-1569`) — not a wrapper with its own defaults. `schema.connect()` calls `ensure_db(path)` (mkdir + migrations, can raise `OSError`) before `sqlite3.connect(str(db_path))` (`schema.py:1566`, no `timeout=` kwarg — the 5s stdlib default applies at the Python connect level), then `_configure_connection()` applies the 5000ms `PRAGMA busy_timeout` described above.
- No call site in the repo passes an explicit `timeout=` kwarg to `sqlite3.connect()` (checked all 25 `sqlite3.connect(` sites across `session_store/`, `cli/`, `queue_store.py`, `codequery/`, `history_reader/`). The codebase's sole busy-wait precedent is the shared `PRAGMA busy_timeout` in `_configure_connection` (`schema.py:1392-1408`), independently mirrored (not shared code) in `queue_store.py`'s own `_configure_connection` (`queue_store.py:202-214`).

## Implementation Steps

1. Confirm the exact failure contract from ll-console (stderr content, exit
   code) before changing behavior (Proposed Hardening step 1).
2. Widen the `except sqlite3.Error` guards around `connect` and the `finally`
   UPDATE to also catch `OSError`, and set a bounded `busy_timeout`.
   > ⚠ Superseded — busy_timeout already set (5000ms via PRAGMA, `schema.py:1405`); see § Codebase Research Findings under Program Design
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
- `/ll:refine-issue` - 2026-09-09T22:49:09 - `05b369f7-30a2-4959-8bec-aa3ab3083faf.jsonl`
- `/ll:format-issue` - 2026-09-09T22:40:10 - `419c0f66-ac03-408b-af11-4cdc8ba58375.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
