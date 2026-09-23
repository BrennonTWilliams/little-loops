---
id: ENH-3526
type: ENH
title: Route remaining history-store write consumers through the backend chokepoint
  (ENH-3525 A2)
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T23:16:32Z'
completed_at: '2026-09-23T00:37:34Z'
verify_verdict: NON_VALID
blocks:
- FEAT-3524
relates_to:
- ENH-3525
confidence_score: 90
outcome_confidence: 59
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
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
  already existed (`session_store/backend.py`, landed in A1) — this issue
  raises them from call sites; no new error types were added.
- `sqlite3.Connection` — still what `open_history()`/`connect_readonly()`
  return; **Step 1 resolved to Option (a)** (below), so no wrapper/protocol
  type was introduced.

### Signatures

**Step 1 decision: Option (a), narrow per-site wrap** — Option (b)'s
translating-connection-wrapper was rejected: it would have required
auditing the ~50 confirmed `open_history()` callers already typed against a
concrete `sqlite3.Connection`, a blast radius wider than this issue's five
files, and Program Design's own note that `Backend.connect()` staying
concretely `sqlite3.Connection`-typed is deliberate until FEAT-3524's
second provider exists.

- `open_history(target: Path | str | None = None, *, check_same_thread: bool = True) -> sqlite3.Connection`
  (`backend.py`) — additive keyword-only parameter, default preserves the
  prior signature/behavior for all existing callers verbatim.
- `translate_sqlite_errors() -> ContextManager[None]` (`backend.py`, new) —
  generalizes `connect_readonly()`'s existing inline
  `try/except sqlite3.Error as exc: raise HistoryOperationError(...) from
  exc` wrap into a reusable context manager (also translating
  `sqlite3.IntegrityError` to `HistoryIntegrityError`), so a call site with
  several `execute()`/`commit()` calls under one best-effort degrade
  boundary wraps the block once instead of hand-rolling the same
  try/except chain at each of the ~10 converted sites. This is still
  Option (a) in spirit — no `HistoryConnection` runtime type, `open_history()`
  keeps returning a plain `sqlite3.Connection` — just de-duplicated
  boilerplate the original issue text didn't anticipate.

### Call Path

`open_history()`/`connect_readonly()` -> `resolve_backend().connect()`/
`.connect_readonly()` -> call site wraps its execute/commit block in
`translate_sqlite_errors()` -> `except HistoryError:` at the same degrade
boundary each site previously caught `sqlite3.Error` at.

### Deviations

_2026-09-23, `/ll:manage-issue implement ENH-3526`_

- **Read vs. write routing corrected.** The issue's Current Behavior/
  Integration Map framed all five files uniformly as "write consumers."
  Direct inspection found `cli/logs.py`'s two sites, `cli/ctx_stats.py`'s
  three sites, and `cli/history.py`'s one site are all read-only (`SELECT`
  only, no `INSERT`/`UPDATE`/`VACUUM`). These route through
  `connect_readonly()` (the strict D19 contract, matching A1's own
  read-only precedent) instead of `open_history()`; only
  `writers.py`'s `SQLiteTransport` and `lifecycle.py`'s two VACUUM sites
  plus `list_retirements` are genuine writes and route through
  `open_history()`.
- **`SqliteBackend.connect(check_same_thread=False)` added.**
  `SQLiteTransport` needs one long-lived connection usable from multiple
  threads (its own `threading.Lock` serializes access) — `schema.connect()`
  has no such parameter and Program Design (ENH-3525) explicitly keeps its
  signature fixed. Added an optional, default-`True` `check_same_thread`
  keyword to `Backend.connect()`/`SqliteBackend.connect()`/`open_history()`:
  the default path still delegates to `schema.connect()` verbatim (zero
  behavior change for the ~50 other callers, none of which pass this
  kwarg); `check_same_thread=False` opens its own connection inside
  `backend.py` (`ensure_db()` + raw `sqlite3.connect(check_same_thread=False)`
  + `_configure_connection()`), wrapped in the same open-failure ->
  `HistoryUnavailable` translation `connect_readonly()` already used.
- **Seven named tests needed no changes.** Verified by running all seven
  with the implementation in place (all pass unmodified): six
  (`test_hook_user_prompt_submit.py`, `test_ll_issues_research_triage.py`,
  `test_set_status_cli.py`, `test_hook_post_tool_use.py`) monkeypatch
  `session_store.connect`/`record_issue_event` directly to simulate a
  failure and assert the *caller's* broad `except Exception`/
  `contextlib.suppress(Exception)` degrade — unaffected by this issue's
  narrower `HistoryError` taxonomy, and `session_store.connect`
  (`schema.connect()`) is unchanged per Program Design. The seventh,
  `test_feat3323_sse_bridge.py:1203`, exercises `session_store.queries`'s
  own `_connect_readonly()` (a different, permanently-allowlisted
  read-only opener, not `backend.py`'s), so its `sqlite3.OperationalError`
  assertion is correct as written and untouched by this issue's scope.
- **Regression tests added instead of "one per site."** Given ~10 converted
  sites share only two behavioral shapes (open-failure degrade,
  execute/commit-failure degrade), added targeted regressions for each
  shape (`SQLiteTransport`'s open/send/close in
  `test_session_store_writers.py`, `prune()`'s VACUUM path in
  `test_session_store_lifecycle.py`) rather than one test per call site.

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

## Resolution

Implemented per the Program Design Deviations above (Option (a), narrow
per-site translation via a new `translate_sqlite_errors()` context manager;
`SqliteBackend.connect(check_same_thread=False)` added for `SQLiteTransport`).

- `session_store/backend.py`: added `translate_sqlite_errors()` and the
  `check_same_thread` keyword on `Backend.connect()`/`SqliteBackend.connect()`/
  `open_history()`.
- `session_store/writers.py`: `SQLiteTransport` now opens via
  `open_history(check_same_thread=False)` and catches `HistoryError`
  (translated via `translate_sqlite_errors()`) in `send()`/`close()`.
- `session_store/lifecycle.py`: both VACUUM sites and `list_retirements` route
  through `open_history()`; `prune()`'s VACUUM degrade converted to
  `except HistoryError`.
- `cli/logs.py`, `cli/ctx_stats.py`, `cli/history.py`: all six sites are
  read-only and route through `connect_readonly()` (corrected from the
  issue's "write consumer" framing — see Deviations).
- `scripts/tests/test_history_store_chokepoint_gate.py`: `_ALLOWLIST` shrunk
  to zero provisional entries (only the pre-existing permanent entries
  remain).
- The seven tests named in Tests/Compatibility Guarantees needed no changes
  (verified by running all seven; see Deviations for why).
- Added regressions: `test_session_store_writers.py` (open/send/close
  degrade under a simulated `HistoryError`), `test_session_store_lifecycle.py`
  (`prune()`'s VACUUM degrade).
- Fixed an unrelated line-number allowlist drift in
  `test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` caused by
  this issue's line shifts in `writers.py`.
- `docs/ARCHITECTURE.md` and `docs/reference/API.md` updated to document the
  finished chokepoint.
- Full suite: `python -m pytest scripts/tests/ -m "not integration and not
  conformance"` — 24416 passed, 13 skipped, 2 pre-existing failures
  unrelated to this change (`test_verify_evidence.py`,
  `test_prose_dep_sweep_gate.py`; confirmed present on `main` before this
  branch via `git stash`).

## Status

**Done** | Created: 2026-09-22 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-22_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- Deep per-site complexity: Step 1's translation-shape decision is unresolved between a narrow per-site `try/except` wrap (Option a) and a translating connection/cursor wrapper (Option b); Option b would require auditing ~50 confirmed `resolve_history_db()`/`open_history()` callers typed against a concrete `sqlite3.Connection` today, materially widening the blast radius beyond the 5 files this issue enumerates.
- `session_store/writers.py`'s `SQLiteTransport` holds one long-lived connection shared across ~20 best-effort event-writer functions — a cross-module, shared-state site, not a mechanical one-line substitution like the CLI files.
- Preserving each site's existing best-effort degrade behavior (return `False`/`None`/empty, never raise) exactly means every site needs individual verification rather than a single automated completeness check — mitigate by adding the "new regression per resolved write call site" test named in this issue's Tests section as each site lands, not deferring it to the end.


## Session Log
- `/ll:manage-issue` - 2026-09-23T00:37:18 - `39e6472f-5cb7-45fb-a872-6efef2ed4bca.jsonl`
- `/ll:refine-issue` - 2026-09-23T00:01:46 - `058f6a9a-c1ce-402e-92f0-f40af32a52a4.jsonl`
- `/ll:confidence-check` - 2026-09-22T23:58:51 - `1605603b-2cc9-4989-a5b7-4d7f6139e9f1.jsonl`
- `/ll:verify-issues` - 2026-09-22T23:39:32 - `719ed6d0-2e4e-41db-ae76-8176f4dcd29a.jsonl`
- `/ll:manage-issue` - 2026-09-22T23:29:05 - `4f3ece7f-4412-4831-a895-fcf5c78a9b60.jsonl`
