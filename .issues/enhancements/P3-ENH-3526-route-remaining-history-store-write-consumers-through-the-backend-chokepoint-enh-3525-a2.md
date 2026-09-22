---
id: ENH-3526
type: ENH
title: Route remaining history-store write consumers through the backend chokepoint
  (ENH-3525 A2)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T23:16:32Z'
verify_verdict: NON_VALID
blocks:
- FEAT-3524
relates_to:
- ENH-3525
---

# ENH-3526: Route remaining history-store write consumers through the backend chokepoint (ENH-3525 A2)

## Summary

ENH-3525 Phase A was staged as two independently landable commits. A1
(chokepoint, contracts, three path-bypass fixes) landed in commit
`bb2c9c2b3` (2026-09-22). This issue is A2: Implementation Steps 5-6 —
route the remaining raw `sqlite3.connect(` write call sites through the
chokepoint (`little_loops.session_store.backend`), convert their
`except sqlite3.*` branches to the `HistoryError` taxonomy, update the
seven tests that deliberately assert on raw `sqlite3.OperationalError`/
`sqlite3.Error` for "history failed", and update
`docs/reference/API.md` / `docs/ARCHITECTURE.md`.

Split out of ENH-3525 rather than attempted in the same pass, per that
issue's own Sizing note ("If `/ll:issue-size-review` agrees, split A2
into its own issue that also blocks FEAT-3524") and its Confidence
Check Notes (Outcome Confidence 55/100 — LOW — recommending
landing/soaking A1 first and re-running confidence-check before
starting A2).

## Current Behavior

`scripts/tests/test_history_store_chokepoint_gate.py`'s `_ALLOWLIST`
marks five files "Provisional (ENH-3525 A2)" — real `history.db`
connections A1 deliberately left unrouted:

- `session_store/writers.py` — `SQLiteTransport` keeps one long-lived
  connection across many events (not a per-call open); ~20 sites across
  best-effort event-writer functions each catch `sqlite3.Error` broadly
  and degrade (return `False`/`None`/empty, never raise), per the
  EPIC-1707 best-effort contract.
- `session_store/lifecycle.py` — VACUUM maintenance connections
  (`lifecycle.py:910`, `:1388`) and a backfill/session path catching
  `sqlite3.Error`/`sqlite3.OperationalError` (`:1396`, `:1447`).
- `cli/logs.py` — two raw opens (`:865`, `:1603`), each with an
  `except sqlite3.OperationalError` degrade path.
- `cli/ctx_stats.py` — three raw opens (`:139`, `:245`, `:309`), two
  wrapped in `except sqlite3.Error` around the open itself, all three
  degrading on `sqlite3.OperationalError` for the query.
- `cli/history.py` — one raw open (`:795`) with `except sqlite3.Error`.

### Open design question (found while scoping this split)

`SqliteBackend.connect()` (`backend.py:146`) returns a **raw**
`sqlite3.Connection` — it delegates to `schema.connect()` and does not
wrap it in any translating proxy, unlike `connect_readonly()`
(`backend.py:151`), which does catch `sqlite3.Error` and raises
`HistoryUnavailable` around the open itself. `Backend.connect()`'s
signature is typed as `-> sqlite3.Connection`, not the abstract
`HistoryConnection` protocol (Program Design's own rationale: "the only
registered provider is SQLite... FEAT-3524's second provider is the
point at which these narrow to `HistoryConnection`").

This means "convert `except sqlite3.*` to `HistoryError` subclasses"
(Step 5) cannot be a call-site catch-clause rename — a raw
`conn.execute()`/`.commit()` on the connection `open_history()` returns
still raises real `sqlite3.OperationalError`/`sqlite3.IntegrityError`,
not `HistoryError`. Before Step 5's ~20+ call sites can be converted,
this issue must resolve **where** the sqlite3→HistoryError translation
actually happens for the *write* path — options include (a) wrapping
each site's own `try/except sqlite3.Error as exc: raise
HistoryOperationError(...) from exc` inline (narrow, matches "adapters
wrap narrowly around driver calls only", but is per-call-site
boilerplate across ~20 sites with different granularity today), or
(b) a thin translating wrapper/proxy object `open_history()` returns
instead of the raw connection (centralizes translation, but is a
`HistoryConnection`-shaped runtime type change Program Design didn't
scope for Phase A, and risks breaking the ~50 confirmed
`resolve_history_db()`/`connect()` callers that already type against
`sqlite3.Connection` concretely). This decision should be made and
recorded (with a Program Design update) before Step 5 implementation
starts, not discovered mid-conversion.

## Expected Behavior

Same as ENH-3525's Expected Behavior for the write side: the five
provisional files route through `open_history()` (or a resolution of
the open design question above), each site's `except sqlite3.*` for
"history-store failed" becomes `except HistoryError` (or the specific
subclass), with `__cause__` preserving the original `sqlite3`
exception. Best-effort degrade contracts (never raise, return
`False`/`None`/empty) are preserved exactly — this is a call-site error
*type* change, not a call-site error *handling* change.

Per ENH-3525's Compatibility Guarantees, the seven tests below are
updated deliberately (not a regression):
`test_feat3323_sse_bridge.py:1203`,
`test_hook_user_prompt_submit.py:146,305,607`,
`test_ll_issues_research_triage.py:148`, `test_set_status_cli.py:1312`,
`test_hook_post_tool_use.py:193`,
`test_feat3445_workspace_activity.py:92`.

`docs/reference/API.md` (session-store signatures) and
`docs/ARCHITECTURE.md:636,717` are updated to describe the finished
chokepoint.

## Motivation

FEAT-3524 (remote libSQL support) is blocked on this the same way it
was blocked on A1 — a remaining raw `sqlite3.connect` write site is a
site that can't be redirected to a remote backend later. Splitting
this out (rather than bundling into ENH-3525) keeps A1's already-landed,
low-risk chokepoint work cleanly separated in history from A2's
higher-risk consumer error-type conversion, per ENH-3525's own sizing
and confidence-check guidance.

## Proposed Solution

First resolve the sqlite3→`HistoryError` write-path translation design
question above (Program Design records both candidate shapes). Then route
each of the five provisional-allowlist files' connections through
`open_history()` (or the chosen wrapper), converting each site's
`except sqlite3.*` to `HistoryError`/a named subclass while preserving its
existing best-effort degrade behavior exactly. Shrink
`test_history_store_chokepoint_gate.py`'s `_ALLOWLIST` to zero provisional
entries as each file is migrated (the gate's own
`test_allowlist_entries_still_exist_and_still_have_raw_connects` catches an
entry left behind after its file is fully migrated). Update the seven named
tests that assert on raw `sqlite3` exceptions for "history failed", then
`docs/reference/API.md` / `docs/ARCHITECTURE.md`.

## Integration Map

### Files to Modify
- `little_loops/session_store/writers.py` — `SQLiteTransport` and ~20
  best-effort event-writer functions (EPIC-1707 contract: catch, log, degrade,
  never raise).
- `little_loops/session_store/lifecycle.py` — VACUUM maintenance connections
  (`:910`, `:1388`) and the backfill/session path (`:1396`, `:1447`).
- `little_loops/cli/logs.py` (`:865`, `:1603`), `little_loops/cli/ctx_stats.py`
  (`:139`, `:245`, `:309`), `little_loops/cli/history.py` (`:795`).
- `little_loops/session_store/backend.py` — only if the design question
  resolves to option (b) (a translating wrapper); otherwise unchanged.
- `scripts/tests/test_history_store_chokepoint_gate.py` — shrink `_ALLOWLIST`.
- `docs/reference/API.md`, `docs/ARCHITECTURE.md:636,717`.

### Dependent Files (Callers/Importers)
- `SQLiteTransport` importers per ENH-3525's wiring pass:
  `little_loops/__init__.py:75-79`, `little_loops/transport.py`,
  `little_loops/config/features.py`, `little_loops/cli/sprint/run.py:657,660,796,807`,
  `little_loops/issue_manager.py:54,1742`, `little_loops/cli/parallel.py`,
  `little_loops/cli/issues/set_status.py:163` (comment-only) — none need their
  own call sites changed if `SQLiteTransport`'s public contract stays the
  same; they are regression-coverage surface.
- The seven named tests (see Tests below) are direct callers of the
  behavior being changed, not incidental coverage.

### Similar Patterns
- `SqliteBackend.connect_readonly()`'s narrow `try/except sqlite3.Error as
  exc: raise HistoryUnavailable(...) from exc` wrap (`backend.py:151-159`)
  is the one existing precedent in this codebase for the sqlite3→
  `HistoryError` translation shape — apply it around each write call site
  once the design question is resolved.

### Tests
- Update the seven tests ENH-3525's Compatibility Guarantees names as
  deliberate rewrites: `test_feat3323_sse_bridge.py:1203`,
  `test_hook_user_prompt_submit.py:146,305,607`,
  `test_ll_issues_research_triage.py:148`, `test_set_status_cli.py:1312`,
  `test_hook_post_tool_use.py:193`, `test_feat3445_workspace_activity.py:92`.
- `scripts/tests/test_history_store_chokepoint_gate.py` — both existing
  tests (`test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist`,
  `test_allowlist_entries_still_exist_and_still_have_raw_connects`) gate
  this issue's completion; no new gate test needed.
- New: a regression per resolved write call site proving the best-effort
  degrade behavior (return `False`/`None`/empty, never raise) is unchanged
  under a simulated `HistoryError`.

### Documentation
- `docs/reference/API.md` — `little_loops.session_store` signatures.
- `docs/ARCHITECTURE.md:636,717` — session-store / history.db
  architecture, updated to describe the finished (not partial) chokepoint.

### Configuration
- N/A — no new dependency, no `history.backend` config key (same
  guarantee as ENH-3525).

## Implementation Steps

1. Resolve the sqlite3→`HistoryError` write-path translation design
   question (Program Design's two candidate options below); record the
   decision and update Program Design's Call Path accordingly.
2. Route `session_store/writers.py` (`SQLiteTransport` + event writers)
   through the resolved translation shape, preserving best-effort degrade
   contracts exactly.
3. Route `session_store/lifecycle.py`'s VACUUM (gated on
   `supports("vacuum")`) and backfill/session connections.
4. Route `cli/logs.py`, `cli/ctx_stats.py`, `cli/history.py`; shrink
   `test_history_store_chokepoint_gate.py`'s `_ALLOWLIST` to zero
   provisional entries.
5. Update the seven named tests to assert on `HistoryError` subclasses.
6. Update `docs/reference/API.md` / `docs/ARCHITECTURE.md`; run the full
   suite and confirm every suite ENH-3525 named under Tests stays green.

## Impact

- **Priority**: P3 - blocks FEAT-3524, same as ENH-3525; independently
  finishes the exception-taxonomy consolidation A1 started.
- **Effort**: Medium-Large - ~20 write call sites across 5 files, one
  unresolved design question to settle first, seven deliberate test
  rewrites, two doc updates.
- **Risk**: Medium - a per-site behavioral change to error handling on
  load-bearing best-effort write paths (event history, hooks); mitigated
  by preserving degrade contracts exactly and the seven named regression
  tests plus the chokepoint gate.
- **Breaking Change**: No for behavior, paths, or degrade contracts; yes,
  intentionally, for the exception types these five files' consumers
  raise/catch (mirrors ENH-3525's own breaking-change note).

## Program Design

### Types

- `HistoryError(Exception)` and its four subclasses `HistoryUnavailable`,
  `HistoryIntegrityError`, `HistoryUnsupported`, `HistoryOperationError`
  already exist (`session_store/backend.py`, landed in A1) — this issue
  raises them from write call sites, it does not add new types, unless
  Step 1 resolves the design question to option (b) below, in which case a
  translating connection/cursor wrapper type is added.
- `sqlite3.Connection` — what `SqliteBackend.connect()` (`backend.py:146`)
  returns today; the type the design question is about.

### Signatures

Unresolved — Step 1 decides between the two options below.

- `open_history(target: Path | str | None = None) -> sqlite3.Connection` — current signature (`backend.py:228`); unchanged by Option (a), narrowed to `HistoryConnection` by Option (b).
- **Option (a), narrow per-site wrap:** no signature change. Each write call
  site wraps its own `conn.execute()`/`.commit()` block:
  `try: ... except sqlite3.IntegrityError as exc: raise
  HistoryIntegrityError(...) from exc except sqlite3.Error as exc: raise
  HistoryOperationError(...) from exc`, mirroring
  `SqliteBackend.connect_readonly()`'s existing shape.
- **Option (b), translating wrapper:** `open_history()` returns
  `HistoryConnection`, a thin proxy whose `execute`/`executemany`/`commit`
  methods catch `sqlite3.Error` and re-raise the matching `HistoryError`
  subclass. Requires auditing the ~50 confirmed
  `resolve_history_db()`/`open_history()` callers that today type against
  `sqlite3.Connection` concretely (per ENH-3525's Program Design note on
  `Backend.connect()`'s current typing) for anything that depends on an
  un-proxied `sqlite3.Connection` (e.g. `isinstance` checks,
  `sqlite3`-specific methods outside the `HistoryConnection` protocol
  surface such as `create_function`, `set_trace_callback`, or attribute
  access this protocol doesn't cover).

### Call Path

Unresolved pending Step 1. Both options preserve:
`open_history()` -> `resolve_backend().connect()` -> (write call site) ->
`SQLiteTransport` / CLI command, catching `HistoryError` at the same
degrade boundary each site catches `sqlite3.Error` today.

## Scope Boundaries

In scope: the five provisional-allowlist files, shrinking
`test_history_store_chokepoint_gate.py`'s `_ALLOWLIST` to zero
provisional entries, the seven named test updates, the two doc updates,
resolving the sqlite3→HistoryError translation design question above.
Out of scope: everything ENH-3525 already scoped out (remote provider,
`history.backend` config key, `connect()`'s two-connection-per-call
shape, `queue.db`/codegraph/Codex-index exclusions).

## Related Key Documentation

- ENH-3525 (this issue's parent scope; A1 landed in `bb2c9c2b3`)
- FEAT-3524 (the remote libSQL feature this unblocks)
- `scripts/tests/test_history_store_chokepoint_gate.py` (the allowlist
  this issue shrinks to zero)

## Verification Notes

Verdict at time of check: **OUTDATED** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a
record of what was wrong and fixed, not an outstanding action item).

- All five provisional-allowlist files, their `sqlite3.connect(`/`except
  sqlite3.*` line numbers (`lifecycle.py:910,1388,1396,1447`,
  `cli/logs.py:865,1603`, `cli/ctx_stats.py:139,245,309`,
  `cli/history.py:795`, `writers.py`'s `SQLiteTransport` connect), the four
  `HistoryError` subclasses, and `backend.py`'s `connect()`/
  `connect_readonly()`/`open_history()` line numbers (146/151/228) were all
  confirmed exact against current code. `test_history_store_chokepoint_gate.py`'s
  `_ALLOWLIST` matches the five files and rationale described. Evidence-quote
  check (`ll-verify-evidence`) and the decisions-log required-rule check both
  came back clean.
- **Fixed**: the seven named test line references had drifted 3-5 lines from
  unrelated edits since ENH-3525 was written — corrected to
  `test_feat3323_sse_bridge.py:1203`, `test_hook_user_prompt_submit.py:146,305,607`,
  `test_ll_issues_research_triage.py:148`, `test_set_status_cli.py:1312`,
  `test_hook_post_tool_use.py:193` (`test_feat3445_workspace_activity.py:92`
  was already accurate).
- **Fixed**: `docs/ARCHITECTURE.md:89,636,832` (inherited verbatim from
  ENH-3525, which A1 never touched) named two lines with no relation to
  session-store/history.db architecture — line 89 is mid-hooks-adapter
  directory tree, and line 832 documents `.ll/queue.db`, which that same
  paragraph explicitly calls "distinct from `.ll/history.db`". Corrected to
  `docs/ARCHITECTURE.md:636,717` (schema-versions table and the `.ll/history.db`
  overview paragraph), the two locations that actually describe history.db.
- **Fixed (dependency)**: this issue's `blocks: [FEAT-3524]` had no
  reciprocal entry in FEAT-3524's `blocked_by` (only listed ENH-3525) —
  added `ENH-3526` to `FEAT-3524`'s `blocked_by`.
- **Remaining**: this issue has no `## Acceptance Criteria` section at all
  (its parent ENH-3525 has one), so check B6's AC-coverage-of-Integration-Map
  sub-check finds a total gap — none of the five files' integration points
  have a corresponding AC. Not corrected here (drafting ACs against the
  unresolved Step 1 design question is substantive authoring work, not a
  verification fix); recommend `/ll:format-issue` or `/ll:refine-issue`
  before implementation starts.

## Status

**Open** | Created: 2026-09-22 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-22T23:39:32 - `719ed6d0-2e4e-41db-ae76-8176f4dcd29a.jsonl`
- `/ll:manage-issue` - 2026-09-22T23:29:05 - `4f3ece7f-4412-4831-a895-fcf5c78a9b60.jsonl`
