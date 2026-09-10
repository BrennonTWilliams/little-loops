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
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3426: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently

## Summary

Every `ll-*` CLI entry point wraps its body in `cli_event_context` (`scripts/little_loops/session_store/writers.py:505-548`), which opens `.ll/history.db`, inserts a `cli_events` row, and updates it with exit code and duration on exit. When `history.db` is held by a concurrent writer past the 5 s `busy_timeout`, a machine consumer of a JSON-emitting command (`ll-queue list --json`, `ll-loop show -j`, `ll-issues ... --json`) can observe the failure mode the ll-console agent reported on 2026-09-09: the process dies with empty stdout. ll-console tolerates it (non-zero exit maps to its `QueueError`), but the contract for a JSON-emitting CLI should be explicit: exit non-zero **and** print a diagnostic to stderr, never a silent empty stdout.

## What Is Verified

- On this checkout, with the same 7.6 GB `history.db`, `ll-queue list --json` returned exit 0 with `[]` on stdout in 0.2 s. The crash **did not reproduce** here. The likely trigger was a concurrent writer holding the SQLite lock while the ll-console session ran it.
- Database size is **not** a factor (2026-09-09 review). `history.db` is 7.6 GB / 1.9M pages / 1.49M `raw_events` rows / 342K `cli_events` rows (WAL mode, zero freelist) — routine for SQLite (281 TB limit). `cli_event_context` only does a single-row INSERT and UPDATE, both O(log n) B-tree tail operations independent of file size, as the 0.2 s result above shows. The only size-sensitive path is a schema migration in `ensure_db` on first connect after an upgrade (one-time, not steady-state); WAL checkpoint cost scales with WAL size (5 MB here), not DB size. The original size-guard proposal was dropped on this basis.
- `cli_event_context` already catches `sqlite3.Error` on the insert (writers.py:528) and logs a warning rather than raising, so the insert path is not the hole. Unhandled surfaces remain: `resolve_history_db` / `_pkg.connect` (schema migration on first connect after an upgrade, writers.py:520-521 runs inside the try but `connect` may block on `busy_timeout` rather than raise), the `finally` UPDATE (writers.py:543 onward), and any non-`sqlite3.Error` exception (e.g. `OSError` from disk-full, `MemoryError`) escaping either.

## Proposed Hardening

1. Establish the failure contract first: ask the ll-console side for the exact stderr and exit code from the observed failure before changing behavior. If stderr was empty on a non-zero exit, that is the defect; if stdout was empty on exit 0, that is a different and worse defect.
2. Make the history writer best-effort on every path: wrap `connect` and the `finally` UPDATE in the same `sqlite3.Error`/`OSError` guard as the insert, with a bounded `busy_timeout` (e.g. 2 s) so a locked or slow DB degrades to "no analytics row" instead of stalling or killing the command.
3. Add a test that simulates a locked DB (second connection holding an exclusive lock) and asserts the wrapped command still emits its JSON on stdout with exit 0, plus a warning on stderr.

## Context

Belongs with the in-flight session-store lifecycle work (FEAT-3417, ENH-3420). Flagged by the ll-console agent as a concern to route here rather than PR themselves.

## Acceptance Criteria

- [ ] Any exception raised by the history writer (`resolve_history_db`, the config-gating prefix, connect, insert, finally-update) is caught and logged; the wrapped command's stdout and exit code are unaffected.
- [ ] The existing `busy_timeout` (5000ms via `PRAGMA`, applied unconditionally through `connect()` at `schema.py:1405`) is documented as already covering `cli_event_context`'s connection; no new timeout is introduced.
- [ ] Test: locked `history.db` → `ll-queue list --json` prints valid JSON, exits 0, warning on stderr.


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
OOM) the wrapped command still completes and prints its JSON on
stdout with exit 0, plus a one-line warning on stderr — never a silent
empty-stdout hang or crash.

## Motivation

This enhancement would:
- Eliminate a failure mode where analytics-row writes to `history.db` (a
  side-channel, not the CLI's actual payload) can crash or hang a
  machine-facing JSON CLI, corrupting automation that parses
  `ll-queue list --json` / `ll-loop show -j` / `ll-issues ... --json` output.
- Business value: keeps ll-console and other machine consumers reliable even
  when `history.db` is lock-contended.
- Technical debt: closes the one remaining unguarded path (`connect` and the
  `finally` UPDATE only catch `sqlite3.Error`, not `OSError`) in an otherwise
  best-effort writer.

## Proposed Solution

See `## Proposed Hardening` above for the full plan. Summary: widen the
`except sqlite3.Error` guards already on the insert (`writers.py:528`) and
`finally` UPDATE (`writers.py:552`) to also catch `OSError` around `connect`
(`writers.py:521`) and the UPDATE call, and guard `resolve_history_db` and the
config-gating prefix so no analytics-path exception reaches the wrapped body.
No size guard: DB size does not affect the writer path (see What Is Verified).

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
- `test_still_exits_zero_when_db_unwritable` (`test_ll_issues_research_triage.py:140-157`) is the closest existing precedent to Acceptance Criteria item 3: it monkeypatches `connect` to raise `sqlite3.OperationalError`, invokes the full `ll-issues research-triage ... --json` CLI, and asserts exit code 0 with valid JSON parsed from stdout. No existing test does this for `ll-queue list --json` specifically, and none of the three tests found assert a stderr warning was emitted.
- Every locked-DB test found in the suite (also `test_set_status_cli.py:1286-1325`, `test_hook_post_tool_use.py:189-193`) simulates the failure via `monkeypatch.setattr(<module>, "connect", <raising stub>)`; no test in `scripts/tests/` opens a genuine second `sqlite3.Connection` and holds a real `BEGIN IMMEDIATE`/`BEGIN EXCLUSIVE` lock against the writer under test.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` (`TestFeatureEnabledForHelper`, line 1963-2019; `TestAnalyticsCaptureConfig`, line 2022-2097) — existing coverage only exercises well-formed `analytics.capture` dicts, `None`, bare strings, and non-list `correction_patterns` (`test_correction_patterns_malformed_non_list`/`_mixed`, line 2085/2091). No test simulates a non-dict `analytics` or `capture` value (e.g. `{"analytics": "oops"}`, raising `AttributeError` at `writers.py:512-518`'s `config.get("analytics", {}).get("capture", {})` chain) or non-string entries inside `skills`/`cli_commands` reaching `fnmatch.fnmatch()` in `feature_enabled_for` (`TypeError`) — the exact unguarded surface this issue's own Codebase Research Findings already identified (above) but had not yet scheduled a test file for. [Agent 3 finding]
- For the new locked-DB stderr-warning test (Acceptance Criteria item 3), use the flat `"..." in caplog.text` idiom with `caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")` — this matches all 8 existing caplog assertions already in `test_session_store_writers.py` (e.g. `TestRecordIssueSnapshot.test_record_issue_snapshot_number_reuse_warns`, line 720-741) and the pattern used by `test_set_status_cli.py`'s closest analogue (`test_sqlite_error_is_caught_and_logged`, line 1289-1325). The alternative `any(... for rec in caplog.records)` form appears only in `test_session_store_schema.py` and would be inconsistent with this file's convention. [Agent 3 finding]

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
- All four locked-DB tests found in the suite (`test_session_store_writers.py:489-542`, `test_ll_issues_research_triage.py:140-157`, `test_set_status_cli.py:1286-1325`, `test_hook_post_tool_use.py:184-199`) simulate the failure via `monkeypatch.setattr(<module>, "connect", <raising stub>)` raising `sqlite3.OperationalError("database is locked")`; none open a real second connection holding `BEGIN IMMEDIATE`/`BEGIN EXCLUSIVE`, and none assert stderr/warning text specifically (only exit code and/or stdout JSON). A `caplog`-based warning-text assertion convention exists elsewhere (`test_session_store_schema.py:2313-2341`) but has not been applied to any locked-DB scenario.

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `docs/reference/API.md`'s `## little_loops.session_store` section (`API.md:9507`) has no dedicated `### cli_event_context` subsection — unlike `skill_event_context` and `hook_event_context`, which each carry their own subsection with explicit "Best-effort per the EPIC-1707 contract" language. The only mention of `cli_event_context` anywhere in API.md is a passing cross-reference inside `### skill_event_context` (`API.md:9674`). Confirmed as of this pass (API.md last modified 2026-09-09T23:16:57Z, after the prior refine pass) — the conditional documentation task named above ("if the best-effort guarantee becomes externally documented") is still outstanding.
- Convention check: every internal-guard site in this codebase (`cli_event_context`, `skill_event_context`, `hook_event_context`/`record_hook_event`, all `history_reader/*.py` readers, `issue_history/*.py`, `cli/ctx_stats.py`, `cli/doctor.py`, `codequery/codegraph.py` — 62+ sites) uses a bare `except sqlite3.Error:`, never widened with `OSError` or `Exception`. The lone widened guard in the repo, `set_status.py:178`'s `except (sqlite3.Error, ImportError, OSError):`, is a 3-tuple driven by a local `ImportError`-raising import, not a 2-tuple precedent. No 2-tuple `except (sqlite3.Error, OSError)` exists anywhere in the repo today.
- No shared pytest fixture for simulating a locked SQLite DB exists anywhere in `scripts/tests/` (checked `conftest.py` and repo-wide) — every locked-DB test builds its own inline `monkeypatch.setattr(<module>, "connect", <raising stub>)`. The closest *real* (non-mocked) lock-contention test pattern in the repo, `test_file_utils.py:194-239` (`test_second_open_nb_acquire_raises_blocking_io_error`), holds a genuine second `flock` file descriptor and asserts `BlockingIOError` — structurally similar to what a real-lock SQLite test would need, but targets a filesystem lock, not SQLite, and provides no ready-made SQLite fixture.
- Two disagreeing-but-both-live `caplog` warning-assertion idioms exist for locked-DB tests: `assert any(<substr> in rec.message for rec in caplog.records)` (`test_session_store_schema.py:2341,2416` — 1 file) vs. a flat `assert "<substr>" in caplog.text` (`test_set_status_cli.py:1325`, `test_session_store_writers.py:718,739-741`, plus `test_ll_loop_commands.py`, `test_sprint.py:334-335`, `test_recursive_finalize.py:250`, `test_link_cli.py:145` — 7+ files, the more common form). `test_set_status_cli.py:1289-1325` (`test_sqlite_error_is_caught_and_logged`) combines the monkeypatch-locked-DB pattern with the `caplog.text` form and is the closest existing analogue to Acceptance Criteria item 3's not-yet-written test.

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

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Ordering relevant to the widened-guard Call Path entries (`writers.py:521`, `writers.py:547`): `ensure_db()`'s unguarded `mkdir` (`schema.py:1550`) runs BEFORE `_configure_connection()` applies `PRAGMA busy_timeout` to either the throwaway migration connection (`schema.py:1553`) or `connect()`'s returned connection (`schema.py:1567`) — a bounded busy_timeout only guards lock contention, not disk-full/permission failures during directory creation.
- No exact-2-tuple `except (sqlite3.Error, OSError)` precedent exists repo-wide (searched both orderings, zero hits); the nearest shape is a 3-tuple at `set_status.py:178`. The proposed widened guard would follow a common tuple-with-OSError shape used elsewhere (100+ sites), not a previously-used exact pairing.

## Implementation Steps

1. Confirm the exact failure contract from ll-console (stderr content, exit
   code) before changing behavior (Proposed Hardening step 1).
2. Widen the exception guards to also catch `OSError` — no new `busy_timeout`
   is needed, it is already set unconditionally (5000ms via `PRAGMA`,
   `schema.py:1405`). Wrap `resolve_history_db()` (`writers.py:506`), the
   config-gating prefix (`writers.py:512-518`), `_pkg.connect()`
   (`writers.py:521`), and the `finally` UPDATE (`writers.py:547`) so no
   analytics-path exception reaches the wrapped body.
3. Add a locked-DB test asserting the wrapped command still emits JSON on
   stdout with exit 0 and a stderr warning.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a test to `scripts/tests/test_config.py` (near `TestFeatureEnabledForHelper`/`TestAnalyticsCaptureConfig`) covering a malformed `config["analytics"]`/`config["analytics"]["capture"]` shape (non-dict value, or non-string entries in `skills`/`cli_commands`) to confirm the `AttributeError`/`TypeError` surface at `writers.py:512-518` is closed once the config-gating prefix is guarded.
- Write the new locked-DB stderr-warning test (Acceptance Criteria item 3) using the flat `"..." in caplog.text` idiom with `caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")`, matching the convention already used throughout `test_session_store_writers.py`.

## Impact

- **Priority**: P3 - affects automation reliability, but only under a
  hard-to-reproduce lock-contention trigger; not user-facing by
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
  paths (plus the unguarded `resolve_history_db` / config-gating prefix) and
  confirming the ll-console stderr/exit-code contract first.
- **Out of scope**: any size-gated behavior on `history.db` (size does not
  affect the writer; 7.6 GB / 1.5M rows is routine for SQLite), auto-compaction or pruning of `history.db` (manual-only
  per project rule — see `raw_events` compact()/prune()), replacing SQLite as
  the history store, and any change to the `cli_events` schema.

## API/Interface

N/A - no public API changes; `cli_event_context`'s call signature is
unchanged, only its internal error handling widens.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-09_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

### Concerns
- No repo-wide precedent exists for the exact 2-tuple `except (sqlite3.Error, OSError)` (nearest is a 3-tuple at `set_status.py:178`); the tuple-with-`OSError` shape itself is common (100+ sites), so this is a minor, low-risk deviation.
- Implementation Step 1 calls for confirming the exact ll-console failure contract (stderr content, exit code) before changing behavior; the issue notes this has not yet been confirmed.

## Session Log
- `/ll:confidence-check` - 2026-09-10T00:02:36 - `e1e987d9-5a25-4adf-9f93-78b6e7b380b0.jsonl`
- `/ll:wire-issue` - 2026-09-09T23:41:59 - `5825e8f7-a405-4f10-9f6c-b98ebb708843.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:23:47 - `00ea4689-f70b-4623-84a3-269ac3fcabb8.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T23:10:51 - `719e35d3-e0ad-40bf-86c3-2b6c7827a005.jsonl`
- `/ll:refine-issue` - 2026-09-09T23:05:44 - `97c1c5a3-138f-48f2-b148-91b0309c6eab.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:49:09 - `05b369f7-30a2-4959-8bec-aa3ab3083faf.jsonl`
- `/ll:format-issue` - 2026-09-09T22:40:10 - `419c0f66-ac03-408b-af11-4cdc8ba58375.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
