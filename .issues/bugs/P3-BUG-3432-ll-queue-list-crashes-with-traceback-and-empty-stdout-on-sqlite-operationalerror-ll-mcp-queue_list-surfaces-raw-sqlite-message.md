---
id: BUG-3432
type: BUG
title: ll-queue list crashes with traceback and empty stdout on sqlite OperationalError;
  ll-mcp queue_list surfaces the raw sqlite message
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T01:41:55Z'
completed_at: '2026-09-10T04:37:08Z'
learning_tests_required:
- sqlite3
- mcp
confidence_score: 95
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3432: ll-queue list crashes with traceback and empty stdout on sqlite OperationalError; ll-mcp queue_list surfaces the raw sqlite message

## Summary

`ll-queue list` (`scripts/little_loops/cli/queue.py:249`) calls `queue_store.list_entries(QUEUE_DB_PATH)` with no exception guard. Any `sqlite3.OperationalError` raised inside `list_entries` — from the `SELECT`, or from `connect()` -> `ensure_db()` -> `_apply_migrations()` (`BEGIN IMMEDIATE`) before it — propagates straight out of `cmd_list`: traceback on stderr, exit 1, nothing on stdout. A machine consumer of `ll-queue list --json` gets an empty payload with no JSON to parse. The same unguarded `list_entries`/`resolve_entry` reads sit behind `_not_found_or_ambiguous` (`cli/queue.py:273-303`), so the four id-taking subcommands
(`status`, `remove`, `requeue`, `cancel`) share the crash shape.

`ll-mcp`'s `queue_list` tool (`scripts/little_loops/mcp_server/tools.py:478-489`) does **not** crash: `handle_call_tool` (`tools.py:1238-1310`) already converts any handler exception into `CallToolResult(is_error=True, ...)`. Its defect is message shape only — the client sees the raw `str(sqlite3.OperationalError(...))` instead of a message that names queue.db, unlike every other `_tool_*` failure which goes through `raise ValueError(<message>)`.

Split out of ENH-3426, which was captured from an ll-console report of `ll-queue list --json` dying with empty stdout but mis-attributed it to a locked `history.db`. ENH-3426's own verification showed the `cli_event_context` history writer already guards that lock path and cannot produce a non-zero exit with empty stdout. **The original ll-console traceback was never captured**, so the unguarded queue.db read here is a candidate cause, not a confirmed one; this issue is hardening of a real gap regardless of whether it was that specific incident. ENH-3426 hardens the history writer only and explicitly leaves this path out of scope.

## Current Behavior

- `cmd_list` (`cli/queue.py:245-260`) reads `list_entries(QUEUE_DB_PATH)` before any output is produced. An `OperationalError` raises out of the command with a traceback and exit 1; `--json` consumers see empty stdout.
- `_not_found_or_ambiguous` (`cli/queue.py:273-303`) catches only `AmbiguousEntryIdError`; an `OperationalError` from `resolve_entry` propagates the same way out of `cmd_status`/`cmd_remove`/`cmd_requeue`/`cmd_cancel`.
- `_tool_queue_list` (`mcp_server/tools.py:478-489`) returns a structured `is_error=True` result today via `handle_call_tool`'s blanket `except Exception` (`tools.py:1283-1297`), but with the raw sqlite text as the message. ll-console's `queue_client.py` moved onto this tool on 2026-09-09 (commit `56448d3` in ll-console), so the primary consumer no longer sees empty stdout from this path — only pre-move subprocess callers of `ll-queue list --json` did.
- `queue_store.connect` (`queue_store.py:287-297`) applies `PRAGMA busy_timeout = 5000` and `PRAGMA journal_mode = WAL` best-effort (`queue_store.py:202-214`).

### When does a read-only `list_entries` actually raise?

`_configure_connection` puts queue.db in WAL mode on first connect, and WAL persists. **In WAL mode a reader never blocks on a writer holding `BEGIN IMMEDIATE`, however long it holds**, so the intuitive "a `ll-queue run --watch` writer held the lock past 5 s" story does not produce `database is locked` on the `SELECT`. The realistic `OperationalError` paths on the read side are:

- `ensure_db()` -> `_apply_migrations()` (`queue_store.py:238-284`) takes `BEGIN IMMEDIATE` when the schema is behind (first-ever creation, or a new migration shipped). Two processes racing that transaction can exceed `busy_timeout`.
- queue.db still in rollback-journal mode because the best-effort `PRAGMA journal_mode = WAL` failed (it needs an exclusive lock; the failure is swallowed at `queue_store.py:213`). Then a plain `SELECT` does block against a writer and can hit `database is locked`.
- Non-lock `OperationalError`s with the same empty-stdout symptom: `unable to open database file` (permissions, missing parent after `.ll/` removed mid-run), `disk I/O error`, `no such table` on a truncated/corrupted file.

Consequence for the fix: catch `sqlite3.OperationalError` broadly, and do **not** label the failure "locked" in the payload — the message may be any of the above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Correction** (folded into Summary/Current Behavior above): `_tool_queue_list` does *not* share `cmd_list`'s crash exposure. The MCP dispatch layer's `handle_call_tool` (`mcp_server/tools.py:1238-1310`, built by `make_call_tool_handler`) wraps every non-mutating tool-handler call in `try: ... except Exception as exc: return types.CallToolResult(content=[TextContent(text=str(exc))], is_error=True)` (`tools.py:1283-1297`). `queue_list` is not in `MUTATING_TOOLS`, so any `sqlite3.OperationalError` raised inside `_tool_queue_list` already lands in that `except Exception` and is converted to a structured `is_error=True` result today — not an unhandled crash. The module docstring at `tools.py:1244-1247` states this explicitly. A fix at this layer is therefore about *message shape* (matching the `raise ValueError(...)` convention used by every other `_tool_*` function, e.g. `tools.py:141`, `:502`, `:506`, `:600`), not about preventing a crash.
- **Additional unguarded call sites** (same crash class as `cmd_list`): `_drain_once` (`cli/queue.py:554`, `pending = [e for e in list_entries(QUEUE_DB_PATH) if e.status == "pending"]`) and `_reclaim_stale` (`cli/queue.py:680`, `running = [e for e in list_entries(db_path) if e.status == "running"]`). Both are called from `cmd_run`/`_run_watch` (`cli/queue.py:695-826`) inside a `try/finally` whose `finally` only restores signal handlers — no `except` clause, so an `OperationalError` from either call propagates uncaught. **Scope decision: out of this issue — see Scope Decisions.**

## Expected Behavior

`ll-queue list` and the `_not_found_or_ambiguous` chokepoint report a `sqlite3.OperationalError` as a structured error instead of a traceback, using the error-branch shape already in force in `cli/queue.py` (`_not_found_or_ambiguous:283-300`, `cmd_remove`, `cmd_requeue`, `cmd_cancel`):

- `--json`: `{"error": <msg>}` on **stdout** (parseable), nothing on stderr, exit 1. No `locked` or other boolean sentinel key — none exists in shipped code, and the exception is not always a lock. Exit 1 plus the `error` key already distinguishes an unreadable queue from an empty one (`[]`, exit 0).
- text mode: one line on stderr, nothing on stdout, exit 1.
- `<msg>` names the database and carries the sqlite text, e.g. `Could not read queue database <path>: database is locked`.

`ll-mcp queue_list` (and the three `resolve_entry`-backed queue tools) raise `ValueError(<msg>)` with the same message so the `is_error=True` result the client already receives carries a clean, queue.db-attributed message rather than the bare sqlite string.

**No retry.** A read-side retry loop would be new code (no read-side retry helper exists; see finding below), and a `busy_timeout` of 5 s already covers short contention. Silently returning `[]` is forbidden: an empty queue and an unreadable queue must stay distinguishable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Correction**: `queue_store.py:191-199`'s `compute_backoff_s(attempt: int) -> int` is not a reusable read-side retry helper. It is a pure delay calculator consumed only by `schedule_retry()` (`queue_store.py:553-576`) to compute `next_attempt_at` when a queue *entry* transitions `running` -> `pending` after a dispatch failure — an application-level entry-scheduling concern, not a SQLite-operation retry loop. It never catches `sqlite3.OperationalError`, never sleeps, and is not called near `list_entries`. No read-side retry/backoff helper for `connect()`/`SELECT` exists anywhere in this codebase (confirmed by repo-wide search for `while.*OperationalError`, `_retry_on_locked`, `with_retry`, `retry_sqlite` — no hits). A retry-based resolution would need new code, not reuse of `compute_backoff_s`. **Resolved: no retry (see Expected Behavior).**
- **Existing convention for the "distinguishable error" requirement**: no `locked: true`/similar boolean sentinel key exists anywhere in shipped code today (repo-wide search for `"locked": True` / `locked=True` found only this issue's own prose) — every existing CLI error branch in `cli/queue.py` (`_not_found_or_ambiguous`, `cmd_remove`, `cmd_requeue`, `cmd_cancel`) instead shapes the `--json` error payload as `{"error": <msg>, ...correlating keys}` (no boolean flag), text mode as a bare `print(msg, file=sys.stderr)`, both followed by `return 1`. On the MCP side, `is_error=True` on the `CallToolResult` already is a machine-distinguishable signal separate from the payload's content. **Resolved: `{"error": <msg>}` only, no `locked` key (see Expected Behavior).**

## Scope Decisions

- **In scope — `cmd_list`** (`cli/queue.py:245`): wrap `list_entries` in `try`/`except sqlite3.OperationalError`.
- **In scope — `_not_found_or_ambiguous`** (`cli/queue.py:273-303`): add an `except sqlite3.OperationalError` branch alongside the existing `AmbiguousEntryIdError` one. One branch covers `status`/`remove`/`requeue`/`cancel`; same file, same shape, no new abstraction.
- **In scope — MCP `_tool_queue_list`, `_tool_queue_get`, `_tool_queue_remove`, `_tool_queue_requeue`** (`mcp_server/tools.py:478`, `:492`, `:598`, `:631`): wrap the `list_entries`/`resolve_entry` call and re-raise as `ValueError(<msg>)`. All four are the same one-line change against the same convention; doing one and "flagging" three would leave the MCP surface inconsistent.
- **Out of scope — `_drain_once` / `_reclaim_stale`** (`cli/queue.py:554`, `:680`): these run inside `cmd_run` and the `_run_watch` polling loop, where the right shape is log-and-continue with a consecutive-failure ceiling rather than `return 1`. Crashing the watcher on one transient error is a worse regression than a one-shot CLI exit, but a watcher that loops forever on a permanently broken DB is also wrong. That is a design decision, not this fix — **file as a separate issue** (blocked_by this one is not required; it can land independently).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` (`cmd_list`, `:245-260`; `_not_found_or_ambiguous`, `:273-303`)
- `scripts/little_loops/mcp_server/tools.py`:
  - `_tool_queue_list` (`:478-489`)
  - `_tool_queue_get` (`:492-507`)
  - `_tool_queue_remove` (`:598`-area)
  - `_tool_queue_requeue` (`:631`-area)
- `scripts/little_loops/queue_store.py` — **no change**; the store keeps raising, callers shape the error.

### Dependent Files (Callers/Importers)
- `queue_store.py:469` `resolve_entry()` — calls `list_entries` on an id-not-found fallback path; reached from `cmd_status`/`cmd_remove`/`cmd_requeue`/`cmd_cancel` (`cli/queue.py`) via `_not_found_or_ambiguous` — covered by the `_not_found_or_ambiguous` branch above.
- `cli/queue.py:554` `_drain_once` and `cli/queue.py:680` `_reclaim_stale` — both call `list_entries` unguarded; called from `cmd_run`/`_run_watch` (`cli/queue.py:695-826`) — **out of scope, separate issue (see Scope Decisions)**.
- `mcp_server/tools.py:727` — `_TOOL_HANDLERS["queue_list"] = _tool_queue_list`; `_tool_queue_list` has no direct-call callers, only this registry lookup inside `handle_call_tool` (`tools.py:1274`)

_Wiring pass added by `/ll:wire-issue`:_
- `mcp_server/tools.py:504` `_tool_queue_get`, `:598` `_tool_queue_remove`, `:631` `_tool_queue_requeue` — all three call `resolve_entry()`, which calls `list_entries` (confirmed via `ll-code callers-of little_loops.queue_store.resolve_entry`); same raw-`OperationalError`-message exposure as `_tool_queue_list` — **now in scope (see Scope Decisions)**.

### Tests
- `scripts/tests/test_cli_queue.py` (autouse fixture already isolates `.ll/queue.db` per test via `monkeypatch.chdir(tmp_path)`)
- `scripts/tests/test_feat_queue_mcp_tools.py`
- `scripts/tests/test_queue_store.py` — no store change expected; only touch if a shared message-formatting helper is added.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_queue_run.py` — existing test file exercising `_drain_once` (`TestCmdRunOnlyPending`, `:998`+) and `_reclaim_stale` (`:640`+) — relevant to the **separate** watch-loop issue, not this one.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4138-4150` (`list` flags table, under `ll-queue`) — no error/lock-behavior row; `status`/`get` document their error case ("or a tool-level error if id doesn't resolve") but `list` documents only the success shape
- `docs/reference/CLI.md:5433` — "`queue_list` returns a list of entries, byte-identical to `ll-queue list --json`" has no error-case caveat, unlike the adjacent `queue_get` sentence in the same line ("or a tool-level error if `id` doesn't resolve")

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Files to Modify gap**: `_drain_once` (`cli/queue.py:554`) and `_reclaim_stale` (`cli/queue.py:680`) call the same unguarded `list_entries()` and are reached from `cmd_run`/`_run_watch` (`cli/queue.py:695-826`), which run inside a long-lived polling loop rather than a single request/response — the fix shape there differs from `cmd_list`'s one-shot request (log-and-continue-the-loop rather than a single `return 1`). **Resolved: split to a separate issue (see Scope Decisions).**
- **Conventions in Force** — CLI JSON/text error-branch shape (`cli/queue.py`): every existing error branch (`_not_found_or_ambiguous:283-300`, `cmd_remove:352`, `cmd_requeue:861/874`, `cmd_cancel:908`) returns `{"error": <msg>, ...correlating keys}` for `--json` and a bare `print(msg, file=sys.stderr)` for text mode, both followed by `return 1` — evidence: `cli/queue.py:283-300`. None includes a `"locked"` boolean key.
- **Conventions in Force** — MCP tool-failure shape: every `_tool_*` function in `mcp_server/tools.py` raises a bare `ValueError(<message>)` for a tool-level failure (no distinct `McpError`/structured-error class at this layer) — evidence: `tools.py:141` (`_tool_issue_get`), `:502`/`:506` (`_tool_queue_get`), `:600`-area (`_tool_queue_remove`). Any `ValueError` raised this way is already caught by `handle_call_tool`'s blanket `except Exception as exc` (`tools.py:1293`) and converted to `CallToolResult(is_error=True, ...)`.
- **Test convention**: every located locked-DB simulation test (`test_session_store_writers.py:489-511`, `test_ll_issues_research_triage.py:140-157`, `test_hook_post_tool_use.py:184-199`) monkeypatches the module-level `connect` name with a stub that unconditionally raises `sqlite3.OperationalError("database is locked")` — none open a real second connection and hold `BEGIN IMMEDIATE`. No shared pytest fixture for this exists; each test builds its own inline stub. `test_cli_queue.py`'s `_isolate_cwd` autouse fixture (lines 20-24) already isolates `.ll/queue.db` per test, so a new test there follows the same inline-stub shape against `little_loops.queue_store.connect`. This works because `cmd_list` imports `list_entries` from `little_loops.queue_store` and `list_entries` looks up `connect` as a module global at call time.

## Program Design

### Signatures

- `cmd_list(args: argparse.Namespace) -> int` (`cli/queue.py:245`) — wrap the existing `list_entries` call in `try`/`except sqlite3.OperationalError`
- `_not_found_or_ambiguous(args: argparse.Namespace) -> int | None` (`cli/queue.py:273`) — add `except sqlite3.OperationalError` next to the existing `except AmbiguousEntryIdError`
- `_tool_queue_list(_arguments: dict[str, Any], *, project_root: Path) -> Any` (`mcp_server/tools.py:478`) — wrap `list_entries`, re-raise as `ValueError`
- `_tool_queue_get` / `_tool_queue_remove` / `_tool_queue_requeue` (`mcp_server/tools.py:492`, `:598`, `:631`) — wrap `resolve_entry`, re-raise as `ValueError`

### Call Path

`cmd_list` -> `queue_store.list_entries` (raises `sqlite3.OperationalError` from `connect()`/`ensure_db()`/`SELECT`) -> caught -> `cli.output.print_json({"error": msg})` (json mode) or `print(msg, file=sys.stderr)` (text mode), `return 1` — mirrors the existing `AmbiguousEntryIdError`/not-found handling in `cli/queue.py:283-300`.

`_not_found_or_ambiguous` -> `queue_store.resolve_entry` (raises `sqlite3.OperationalError`) -> caught -> `print_json({"error": msg, "id": args.id})` / `print(msg, file=sys.stderr)`, `return 1` — the four callers already treat a non-`None` return as "handled, exit with this code".

`_tool_queue_*` -> `queue_store.list_entries` / `resolve_entry` (raises `sqlite3.OperationalError`) -> caught -> `raise ValueError(msg) from exc` -> `handle_call_tool` (`tools.py:1283-1297`) -> `CallToolResult(is_error=True, content=[TextContent(text=msg)])`. This changes the *message text* the client sees, not whether the failure is structured — that part is already true.

`msg` is built once, e.g. `f"Could not read queue database {db_path}: {exc}"`; the `sqlite3.OperationalError` text is preserved verbatim so `database is locked` vs `unable to open database file` stays diagnosable.

## Acceptance Criteria

- [ ] `ll-queue list --json` with `little_loops.queue_store.connect` monkeypatched to raise `sqlite3.OperationalError("database is locked")`: stdout is exactly one parseable JSON object with an `error` key whose value contains `database is locked`; stderr is empty; exit code 1.
- [ ] Same in text mode: one line on stderr containing `database is locked`; stdout empty; exit code 1.
- [ ] Empty queue, no error: `ll-queue list --json` still emits `[]` with exit 0 (unreadable vs empty stays distinguishable).
- [ ] `ll-queue status <id> --json` (via `_not_found_or_ambiguous`) under the same monkeypatch: `{"error": ..., "id": <id>}` on stdout, exit 1; the non-error not-found and ambiguous branches are unchanged (existing tests still pass).
- [ ] MCP `queue_list` under the same monkeypatch, exercised through `client.call_tool` in `test_feat_queue_mcp_tools.py`: `result.is_error is True` and `result.content[0].text` names the queue database and contains `database is locked`.
- [ ] MCP `queue_get` under the same monkeypatch: `is_error is True` with the same message shape; `test_queue_get_unknown_id_is_error` still passes.
- [ ] MCP `queue_remove` under the same monkeypatch: `is_error is True` and `result.content[0].text` names the queue database and contains `database is locked`; `test_queue_remove_dry_run_then_apply` still passes.
- [ ] MCP `queue_requeue` under the same monkeypatch: `is_error is True` and `result.content[0].text` names the queue database and contains `database is locked`; `test_queue_requeue_running_entry` and `test_queue_requeue_dead_letter_entry` still pass.
- [ ] No `locked` key or any new boolean sentinel is introduced in any JSON payload.
- [ ] `docs/reference/CLI.md` `ll-queue list` table (`:4138-4150`) and the `queue_list` sentence (`:5433`) each gain one sentence describing the error case.
- [ ] `queue_store.py` is unchanged.
- [ ] `python -m pytest scripts/tests/test_cli_queue.py scripts/tests/test_feat_queue_mcp_tools.py` passes; full suite green.

## Impact

- **Priority**: P3 - Read-only CLI crash under `OperationalError`; the MCP side (ll-console's consumer since 2026-09-09) is already structured, so the remaining exposure is subprocess callers of `ll-queue list --json` and the four `resolve_entry`-backed subcommands. Not data loss, race-dependent trigger.
- **Effort**: Small - Reuses the `try`/`except` + `print_json({"error": ...})` + `return 1` pattern already present in `cli/queue.py:283-300` and the `raise ValueError` convention already used by every other `_tool_*` function in `tools.py`; no new abstractions or store-layer changes.
- **Risk**: Low - Read-only path, purely additive exception handling around existing calls; behavior on the non-error path is unchanged.
- **Breaking Change**: No - `--json` success-case payload shape is unchanged; the failure case, which previously exited with a traceback and empty stdout, now emits `{"error": ...}`.

## Verification Notes

**Verdict: PROPOSAL_UNSOUND.** Every claim about current-code state checked out exact —
file paths, line numbers, and code shapes all confirmed by direct read: `cmd_list`
(`cli/queue.py:245-260`), `_not_found_or_ambiguous` (`:273-303`, catches only
`AmbiguousEntryIdError`), the unguarded `list_entries` calls in `_drain_once`/
`_reclaim_stale` (`:554`/`:680`), `_tool_queue_list`/`_tool_queue_get`
(`mcp_server/tools.py:478-489`/`:492-507`), the `resolve_entry` call sites inside
`_tool_queue_remove`/`_tool_queue_requeue` (`:598`/`:631`), `handle_call_tool`'s
blanket `except Exception` (`:1283-1297`, confirmed to also cover the mutating-tool
branch at `:1287` since both sit inside the same `try`), `MUTATING_TOOLS` membership
(`policy.py:55-65` — `queue_remove`/`queue_requeue` are mutating, `queue_list`/
`queue_get` are not, immaterial to the shared `except` claim), and
`queue_store.py`'s `connect`/`_configure_connection`/`_apply_migrations`/`ensure_db`/
`resolve_entry`'s `list_entries` call at `:469`. The "no read-side retry helper" and
"no `locked` boolean sentinel" repo-wide claims were re-run and still return no hits.
`ll-verify-evidence` reports clean (no fabricated quotes); no active required
decision rules are in force.

The defect is prospective, not retrospective: **Scope Decisions** and the wire-issue
pass both put all four MCP tools — `_tool_queue_list`, `_tool_queue_get`,
`_tool_queue_remove`, `_tool_queue_requeue` — in scope for the same one-line
`ValueError`-wrapping change, explicitly reasoning that "doing one and 'flagging'
three would leave the MCP surface inconsistent." But the **Acceptance Criteria only
exercise `queue_list` and `queue_get`** — there is no AC asserting that
`_tool_queue_remove`/`_tool_queue_requeue` raise the new structured, queue.db-
attributed `ValueError` (instead of the raw sqlite text) under the same
`OperationalError` monkeypatch. An implementer working strictly off the AC checklist
could land the fix on 2 of the 4 declared-in-scope tools untested, reproducing the
inconsistent-surface outcome the four-tool grouping exists to prevent.

Remaining: add two Acceptance Criteria (mirroring the existing `queue_list`/
`queue_get` pair) covering `_tool_queue_remove`/`_tool_queue_requeue` under the
`OperationalError` monkeypatch. Not corrected in this pass — `/ll:verify-issues`
reports on prescriptive sections (Scope Decisions/Program Design/Acceptance
Criteria) but does not rewrite them; route through `/ll:reconcile-issue` or a manual
edit.

**Update (`/ll:ready-issue`, 2026-09-09):** the two missing Acceptance Criteria for
`_tool_queue_remove`/`_tool_queue_requeue` have been added above, closing the gap
this section flagged. The four-tool MCP grouping is now fully covered by AC.

Graph: provider=`codegraph` freshness=`stale` — not used to originate any verdict;
every cited symbol was confirmed by a direct file read per the freshness-demotion
rule.

## Steps to Reproduce

1. Monkeypatch `little_loops.queue_store.connect` to raise `sqlite3.OperationalError("database is locked")` (the pattern used throughout `scripts/tests/` for locked-DB cases).
2. Run `ll-queue list --json`.
3. Observe traceback on stderr, exit 1, empty stdout.

Note: holding `BEGIN IMMEDIATE` on a second real connection does **not** reproduce this against a normal queue.db, because the store puts the file in WAL mode and WAL readers do not block on writers. To reproduce with a real second connection, first switch the file to rollback mode (`PRAGMA journal_mode=DELETE`) so the `SELECT` contends with the writer, or race two processes through a pending `ensure_db` migration.

## Related

- ENH-3426 — hardens `cli_event_context` (history.db side); this BUG covers the queue.db side it scoped out.
- ENH-2927 — default queue.db path resolution (`_resolve_queue_db_path`).
- BUG-2706 — the analogous locked-DB fix for `cli_event_context`.
- Follow-up (to file): `_drain_once` / `_reclaim_stale` `OperationalError` handling in the `ll-queue run --watch` loop (log-and-continue with a consecutive-failure ceiling) — see Scope Decisions.

## Resolution

Implemented exactly as scoped: `cmd_list` and `_not_found_or_ambiguous` in
`scripts/little_loops/cli/queue.py` now catch `sqlite3.OperationalError` and report
`{"error": <msg>}` (JSON) / stderr line (text) with exit 1, instead of an unhandled
traceback. The four MCP tools (`_tool_queue_list`, `_tool_queue_get`,
`_tool_queue_remove`, `_tool_queue_requeue` in `scripts/little_loops/mcp_server/tools.py`)
now catch the same exception and re-raise `ValueError` via a shared `_queue_read_error`
helper, so the already-structured `is_error=True` result carries a queue.db-attributed
message instead of the raw sqlite text. `queue_store.py` untouched, as scoped. TDD
(Red confirmed against pre-fix code, then Green): added
`test_list_operational_error_json`/`_text` and `test_status_operational_error_json` to
`test_cli_queue.py`, and four `test_queue_{list,get,remove,requeue}_operational_error_is_structured`
tests to `test_feat_queue_mcp_tools.py`. `docs/reference/CLI.md` gained the two
sentences the AC required (`list` flags section, and the `queue_list`/`queue_get`
tool-return sentence). Full suite: 23823 passed, 43 skipped, 6 pre-existing failures
(repo-wide corpus/gate tests unrelated to this change — confirmed identical on
unmodified `main` via `git stash`).

## Status

**Open** | Created: 2026-09-10 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-10T04:37:03 - `58c863fa-c03a-4046-a3d0-1ff2020ab466.jsonl`
- `/ll:ready-issue` - 2026-09-10T04:24:54 - `e3be7bb0-3462-4876-a3ba-5e1e717b63e1.jsonl`
- `/ll:confidence-check` - 2026-09-10T03:26:56 - `cc7ebe5f-c73c-4a1e-8191-adbb508e3997.jsonl`
- `/ll:verify-issues` - 2026-09-10T03:16:08 - `5034953b-2c32-4c04-8aeb-ef755a4d9eb0.jsonl`
- `/ll:wire-issue` - 2026-09-10T02:45:55 - `ccf4b116-f388-4b46-b017-1735a236d98c.jsonl`
- `/ll:refine-issue` - 2026-09-10T02:40:25 - `904e00dc-d918-45ce-a5a3-6476558d4520.jsonl`
- `/ll:format-issue` - 2026-09-10T02:20:14 - `53454f7b-c63c-4adf-8a13-82f32f7513d8.jsonl`
- manual review - 2026-09-10 - reconciled directive sections with refine findings (MCP does not crash; WAL readers don't block; no `locked` key; no retry), added Scope Decisions and Acceptance Criteria, split watch-loop sites to a follow-up
