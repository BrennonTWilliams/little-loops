---
id: ENH-2504
title: Persist verification / readiness-review verdict outcomes into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - verification
  - audit
  - captured
---

# ENH-2504: Persist verification / readiness-review verdict outcomes into history.db

## Summary

`ll-ready-issue`, `ll-tradeoff-review`, `ll-confidence-check`, `ll-go-no-go`,
`ll-refine-issue`, `ll-format-issue`, `ll-verify-issues`, `ll-prioritize-issues`,
`ll-align-issues`, and `/ll:verify-issue-loop` each compute a pass/fail
verdict with a severity count and a findings list. Today the verdict only
survives in the CLI's stdout — once the terminal scrolls, there's no record of
"the confidence-check on BUG-2501 ran at 2026-07-07T02:55:00 and scored 97
with 0 P0 findings" or "the tradeoff review recommended `implement` over
`defer`." Add a `verdict_events` table capturing every verifier's structured
outcome so issue-readiness trends are queryable alongside the executor
events ENH-2493 already persists.

## Motivation

- **The read-side is completely dark.** ENH-2493 (`harness_events`) and
  ENH-2459 (`test_run_events`) cover the executor side (pytest, ll-harness,
  dsl evals). The verifier side — the commands an agent invokes to *decide*
  whether to implement — leaves no trace, so the velocity story
  ("how many issues passed readiness this week?") is unreachable.
- **`/ll:verify-issue-loop` outputs are already structured but throwaway.**
  The same harness runner that ENH-2493 captures produces the rows this issue
  would store; nothing currently distinguishes "executor verdict" from
  "verifier verdict."
- **Adjacent to but distinct from ENH-2493.** ENH-2493 captures
  *executor* outcomes (`runner`, `target`, `semantic_verdict`). This issue
  captures *verifier* outcomes — the readiness/confidence/refine side that
  feeds the executor. Different producers (readiness-review vs. harness
  runners), same shape. Either a sibling table (`verdict_events`) or a
  shared table with a `verdict_kind` discriminator works; this issue
  proposes a sibling table for clearer provenance.

## Current Behavior

- `ll-ready-issue`, `ll-tradeoff-review`, `ll-confidence-check`,
  `ll-go-no-go`, `ll-refine-issue`, `ll-format-issue`, `ll-verify-issues`,
  `ll-prioritize-issues`, `ll-align-issues` each print a verdict and exit
  code, then exit; nothing persists.
- `/ll:verify-issue-loop` produces the same shape via `ll-harness`; ENH-2493
  would capture those rows (they're harness invocations), but the verifier
  ones (`ll-ready-issue --json` etc.) bypass `ll-harness` entirely.
- No `--kind verdict` in `ll-session recent`.

## Expected Behavior

- A `verdict_events` table records one row per verifier invocation with
  `verdict_kind` (the command/skill name), `target_kind` (`issue` | `epic` |
  `sprint` | `loop`), `target_id`, `verdict` (`pass` | `fail` | `warn` |
  `defer` | `implement` | `close`), `severity_counts` (JSON: `{p0: 0, p1: 2,
  ...}`), `findings_count`, plus `session_id`, `ts`, `head_sha`, `branch`.
- Each verifier calls `record_verdict_event(...)` before returning (best-
  effort guarded).
- `ll-session recent --kind verdict` returns rows; FTS matches
  `target_id` / findings text.
- Same shape is reachable from `/ll:verify-issue-loop` outputs (no double-
  write; the harness table gets the executor row, this table gets the
  verifier row when the skill is invoked standalone).

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS verdict_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    verdict_kind TEXT NOT NULL,   -- "ll-ready-issue" | "ll-confidence-check" | "/ll:tradeoff-review-issues" | ...
    target_kind TEXT,             -- "issue" | "epic" | "sprint" | "loop"
    target_id TEXT,               -- "BUG-2501" | "EPIC-2457" | ...
    verdict TEXT NOT NULL,        -- "pass" | "fail" | "warn" | "implement" | "defer" | "close"
    severity_counts TEXT,         -- JSON: {"p0": 0, "p1": 2, ...}
    findings_count INTEGER,
    confidence INTEGER,           -- numeric confidence when produced (e.g., 97)
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_verdict_kind ON verdict_events(verdict_kind);
CREATE INDEX IF NOT EXISTS idx_verdict_target ON verdict_events(target_id);
CREATE INDEX IF NOT EXISTS idx_verdict_session ON verdict_events(session_id);
```

Bump `SCHEMA_VERSION`. Add `"verdict"` to `_VALID_KINDS` and
`"verdict": "verdict_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_verdict_event(db_path, *, ts, session_id, verdict_kind,
  target_kind, target_id, verdict, severity_counts=None, findings_count=None,
  confidence=None, head_sha=None, branch=None)` to `session_store.py`,
  best-effort, FTS-indexing `target_id` + `verdict_kind`.
- Wire into the terminal-return point of each verifier's main(): each
  command already builds the structured result it prints; capture that
  same dict into `record_verdict_event(...)` before the final return.
- A small helper module (e.g. `scripts/little_loops/verdict_events.py`)
  exporting a `record(command, target, verdict, ...)` shortcut would
  centralize the call sites and reduce duplication across the nine
  verifier entry points.

### Read API

- `history_reader.recent_verdict_events(verdict_kind=None, target_id=None,
  since=None, limit=50)`.
- `history_reader.verdict_pass_rate(verdict_kind=None, target_id=None,
  since=None)` — pass rate over a window, the readiness-trend rollup.

### CLI surface

- `ll-session recent --kind verdict`.
- `ll-history issue-readiness <ISSUE_ID>` (optional follow-on) — surfaces
  the most recent verifier scores for an issue across readiness/confidence/
  tradeoff/go-no-go.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema version slot**: The live `SCHEMA_VERSION` constant in
  `scripts/little_loops/session_store.py:207` is `20` (per Anchor Refresh
  against current `main`; v17=`commit_events`/ENH-2458, v18=`test_run_events`/ENH-2459,
  v19=`raw_events`/ENH-2581, v20=`usage_events`/ENH-2461). The next-open slot
  is `v21`, NOT v19 as the issue's Proposed Solution prose implies. Read the
  live constant at implementation time — per the issue's own Scope Boundary
  note, several EPIC-2457 siblings race for the same slot and each child
  lands its migration at whatever version is open when it is implemented.
- **Canonical kind name**: The constant is `VALID_KINDS` (session_store.py:209-222,
  a `tuple[str, ...]`, no underscore prefix). The issue's `_VALID_KINDS`
  reference is a stale anchor shared across some sibling issues; use the
  unprefixed name in any new code.
- **Migration mechanics**: Each migration in `_MIGRATIONS: list[str]`
  (session_store.py:333-734) is a multi-statement string split on `;` by
  `_split_sql_statements()` (line 768). The full pending sequence runs
  inside a single `BEGIN IMMEDIATE` transaction via `_apply_migrations()`
  (lines 798-834); per-migration bookkeeping stamps
  `meta(key='schema_version', value=...)` after each entry lands. Append
  the v21 block as one new list element — do not edit existing ones.
- **Idempotency consideration**: The issue's spec doesn't require dedup,
  so mirror the **non-idempotent** `record_test_run_event` pattern
  (session_store.py:1352-1414: plain `INSERT` + `_index()` + `conn.commit()`,
  no return value) rather than the idempotent `record_commit_event` pattern
  (which uses `INSERT OR IGNORE` on a UNIQUE column and returns `bool`).
  Each verifier invocation is naturally a single row.
- **`head_sha` / `branch` source**: Use the `_git_output(*args)` helper at
  `scripts/little_loops/pytest_history_plugin.py:61-74` (14-line helper
  returning `None` on failure). The `git_utils.py` file referenced in
  some sibling issues' Integration Maps **does not exist** — do not import
  it. If the producer can't tolerate the cost of a git call, capture
  `head_sha`/`branch` once at module load and pass them through.
- **Best-effort at call site, not in the producer**: The two reference
  producers both raise on `sqlite3.Error`; the graceful-degradation is
  enforced by `contextlib.suppress(Exception)` at the call site. Mirror
  `pytest_history_plugin.py:120-121`. The newer `skill_event_context`
  (session_store.py:1108-1181) does swallow `sqlite3.Error` internally —
  the older `cli_event_context` (line 1054) does NOT, so any record call
  inside an `ll-action` dispatch wrap needs the explicit suppress.
- **FTS5 indexing**: All event types write to the shared `search_index`
  virtual table via `_index(content, kind, ref, anchor, ts)`
  (session_store.py:890-903). The `kind` column is `UNINDEXED`; filtering
  happens via WHERE clause. The `fts_phrase()` helper (line 1422-1431)
  wraps hyphenated IDs (`BUG-2501`) as literal FTS5 phrases so the
  tokenizer doesn't split them (BUG-2651). Mirror the FTS content
  pattern of `record_commit_event` at line 1263:
  `f"{target_id} {verdict} {verdict_kind} {severity_counts or ''}".strip()[:512]`.
- **Read-path dispatch**: `recent(db, *, kind, limit)` (session_store.py:1462-1484)
  routes via `_KIND_TABLE[kind]` — no change needed for the new kind.
  The `# noqa: S608 - table from fixed map` is the safety annotation;
  never interpolate a table name from user input.
- **CLI auto-extension**: `cli/session.py:99-118` uses
  `choices=list(VALID_KINDS)` for both `--kind` flags; `ll-session recent
  --kind verdict` works automatically once `VALID_KINDS` is updated. No
  further CLI plumbing required. The docstring example block at
  `cli/session.py:73` and the `docs/reference/CLI.md:2509-2514` example
  block both need a `verdict` example added.
- **`ll-session export` parity**: Add `"verdict_event": ("verdict_events", "ts")`
  to `_EXPORT_TABLE_MAP` (session_store.py:3304-3329) AND append
  `"verdict_event"` to `_EXPORT_DEFAULT_TABLES`. The 2-tuple shape is
  `(table_name, timestamp_col)` — NOT a 3-tuple. This is the parity
  contract that `ll-session export` needs to dump verdict rows.
- **FTS5 query with hyphenated IDs**: The proposed `search --kind verdict
  --fts "BUG-2501"` call must use the `fts_phrase()` wrapper or
  `search_index` (FTS5) will tokenize `BUG` and `2501` separately, missing
  the row. This is BUG-2651.
- **Issue's stated producer paths are aspirational**: The nine
  `scripts/little_loops/cli/{ready_issue,confidence_check,go_no_go,
  tradeoff_review,refine_issue,format_issue,verify_issues,prioritize_issues,
  align_issues}.py` files do NOT exist on disk. The verifiers are
  skills bridged via `ll-action`. The actual integration point for the
  8 skill-bridged verifiers is `scripts/little_loops/cli/action.py:67-100`
  (`cmd_invoke()`) — wrap each invocation in `skill_event_context(...)` and
  capture the structured result dict before subprocess return. The
  `/ll:verify-issue-loop` producer is skill-bridged too but its result
  flows through `ll-harness` (already covered by ENH-2493 `harness_events`).
- **Decision: no central helper module required**: The issue proposes a
  `scripts/little_loops/verdict_events.py` helper, but the actual
  integration surface is `cli/action.py:cmd_invoke()` — a 5-line inline
  `record_verdict_event(...)` call there covers all 8 skill-bridged
  verifiers uniformly. Skip the helper module unless the call site grows
  to need per-verifier customisation.

## Acceptance Criteria

- Schema migration lands; `verdict_events` exists; `SCHEMA_VERSION` bumped.
- An `ll-ready-issue BUG-2501` invocation writes one row with
  `verdict_kind="ll-ready-issue"`, `target_id="BUG-2501"`, the computed
  verdict, and severity counts.
- An `/ll:verify-issue-loop` invocation produces the verifier row from
  this table (alongside, not instead of, the executor row in
  `harness_events`).
- `ll-session recent --kind verdict` returns rows; FTS matches
  `target_id`.
- Writes are best-effort: DB absent/locked does not change the verifier
  exit code.
- Tests cover: each verifier producer, DB-absent graceful degradation,
  severity_counts JSON round-trip.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Test gate command** (per `.claude/CLAUDE.md` § Testing & CI Policy:
  "CI" = `python -m pytest scripts/tests/`, no GitHub Actions):
  ```
  python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py scripts/tests/test_ll_session.py -v
  ```
  This is the local CI gate. All three files must pass before the
  migration is considered landed.
- **Additional gate**: `python -m pytest scripts/tests/test_verify_kinds.py -v`
  — verifies every `CREATE TABLE` in `_MIGRATIONS` is registered in
  `_KIND_TABLE` (or explicitly listed in `_KINDLESS_TABLES`). The new
  `verdict_events` table will be checked here (ENH-2581).
- **Reference test classes** (mirror these exactly):
  - `TestRecordTestRunEvent` at `scripts/tests/test_session_store.py:4362-4432`
    — round-trip, FTS, multi-row, upgrade-path. **Reference for
    `TestRecordVerdictEvent`.**
  - `_bootstrap_schema_at(db, version)` helper at
    `scripts/tests/test_session_store.py:3891-3911` — required for the
    `test_v20_db_upgrades_gains_verdict_events` upgrade test.
  - `test_recent_test_runs_and_pass_rate` at
    `scripts/tests/test_history_reader.py:1459-1482` — **reference for
    `test_recent_verdict_events_and_pass_rate`** (covers both reader
    and rollup).
  - `test_readers_return_empty_on_missing_db` at
    `scripts/tests/test_history_reader.py:1530-1544` — graceful
    degradation pattern (DB absent → return `[]`, not raise).
  - `test_recent_kind_test_run_outputs_row` at
    `scripts/tests/test_ll_session.py:1086-1100` — **reference for
    `test_recent_kind_verdict_outputs_row`** (CLI dispatch).
  - `test_recent_kind_commit_outputs_row` at
    `scripts/tests/test_ll_session.py:1073-1085` — second reference.
  - `test_search_kind_commit_filters` at
    `scripts/tests/test_ll_session.py` — reference for
    `test_search_kind_verdict_filters` (verifies FTS5 + kind filter
    combination; BUG-2651 fts_phrase wrap).
  - `test_best_effort_on_unopenable_db` at
    `scripts/tests/test_session_store.py:4025-4033` — pattern for
    "DB absent does not change the verifier exit code" AC.
- **Per-verifier producer tests**: The 9 producers are skill-bridged
  (not Python modules); the producer-level test is *integration* via the
  `ll-action` dispatch in `cli/action.py:cmd_invoke()`. Mirror the
  `TestRecordCommitEvent` round-trip pattern (test_session_store.py:4235-4308)
  for the producer function itself; verify a row lands when `ll-action`
  is invoked with a representative skill name.
- **`severity_counts` JSON round-trip**: Use `json.dumps(severity_counts)`
  on write, `json.loads(severity_counts_json)` on read. Schema requires
  `TEXT` (SQLite has no native JSON; `JSON1` is enabled but storing as
  `TEXT` is consistent with `commit_events.files_json` at
  session_store.py:1254). Round-trip test: write `{"p0": 0, "p1": 2,
  "p2": 1}`, read back, assert deep equality.
- **Best-effort guard test**: Mirror `test_best_effort_on_unopenable_db`
  (test_session_store.py:4025-4033) — pass a directory path as
  `db_path`, verify the producer returns without raising and without
  the verifier's exit code changing.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — "the missing `events.jsonl`
  is what would distinguish Modes A/B/C" — the analysis couldn't run because
  no verifier-event trail existed for the killed run
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- ENH-2493 — sibling structured-result table for executors
- ENH-2497 / `post_tool_use.py` — `subagent_type` already shows what
  agent invoked the verifier
- `scripts/little_loops/cli/{ready_issue,confidence_check,go_no_go,
  tradeoff_review,refine_issue,format_issue,verify_issues,
  prioritize_issues,align_issues}.py` — nine producer entry points

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Integration Map

_Added by `/ll:refine-issue` — verified against current `main`._

### Files to Modify

- `scripts/little_loops/session_store.py:207` — bump `SCHEMA_VERSION = 20` → `21`
  (read the live constant at implementation time per the Scope Boundary note).
- `scripts/little_loops/session_store.py:209-222` — append `"verdict"` to
  `VALID_KINDS` (becomes 13th). Canonical name is `VALID_KINDS` (no underscore).
- `scripts/little_loops/session_store.py:223-236` — append
  `"verdict": "verdict_events"` to `_KIND_TABLE`.
- `scripts/little_loops/session_store.py:333-734` (`_MIGRATIONS` list, end
  around line 734) — append the v21 migration block: `CREATE TABLE IF NOT
  EXISTS verdict_events(...)` + 3 indexes
  (`idx_verdict_kind`, `idx_verdict_target`, `idx_verdict_session`).
- `scripts/little_loops/session_store.py:1352-1414` (next to
  `record_test_run_event()`) — add `record_verdict_event(db_path, *, ts,
  session_id, verdict_kind, target_kind, target_id, verdict,
  severity_counts=None, findings_count=None, confidence=None,
  head_sha=None, branch=None, config=None) -> None`. Mirror the
  non-idempotent test_run pattern (plain `INSERT` + `_index()` +
  `conn.commit()`). Export via `__all__` (line 61-93).
- `scripts/little_loops/session_store.py:3304-3329` — add
  `"verdict_event": ("verdict_events", "ts")` to `_EXPORT_TABLE_MAP` AND
  append `"verdict_event"` to `_EXPORT_DEFAULT_TABLES`. 2-tuple shape
  is `(table_name, timestamp_col)`, not 3-tuple.
- `scripts/little_loops/history_reader.py:1-42` — module docstring Public
  API list (must mention `VerdictEvent`, `recent_verdict_events`,
  `verdict_pass_rate`).
- `scripts/little_loops/history_reader.py:138-161` (next to `RunEvent`
  dataclass) — add `VerdictEvent` dataclass with field names matching SQL
  column names exactly. All fields nullable except `ts`.
- `scripts/little_loops/history_reader.py:689-725` (next to
  `recent_test_runs()`) — add
  `recent_verdict_events(verdict_kind=None, target_id=None, since=None,
  limit=50, db=DEFAULT_DB_PATH) -> list[VerdictEvent]`. Mirror the
  parameterized WHERE + `_connect_readonly` graceful-degradation pattern.
- `scripts/little_loops/history_reader.py:497-546` (next to
  `summarize_skills()`) — add
  `verdict_pass_rate(verdict_kind=None, target_id=None, since=None, db=DEFAULT_DB_PATH) -> list[dict]`.
  `SUM(CASE WHEN verdict IN ('pass','implement') THEN 1 ELSE 0 END)`
  for the numerator; mirror `success_rate` field shape.
- `scripts/little_loops/cli/action.py:67-100` (`cmd_invoke()`) — the
  **actual** call site for the 8 skill-bridged verifiers
  (`ll-ready-issue`, `ll-confidence-check`, `ll-go-no-go`,
  `ll-tradeoff-review-issues`, `ll-refine-issue`, `format-issue`,
  `ll-verify-issues`, `ll-prioritize-issues`, `ll-align-issues`). Wrap
  in `skill_event_context` (which already swallows `sqlite3.Error`) and
  add `contextlib.suppress(Exception)` around the `record_verdict_event`
  call. The issue's claimed path
  `scripts/little_loops/cli/{ready_issue,confidence_check,...}.py` does
  **not exist** — the verifiers are skills, not Python modules.
- `docs/ARCHITECTURE.md:676-678` — append v21 row to schema versions table
  (template rows for v18, v19, v20).
- `docs/reference/API.md:4102-4103` — `--kind` flag table for `search` /
  `recent` (add `verdict`).
- `docs/reference/API.md:7065-7077, 7346-7389` — add `recent_verdict_events`
  / `verdict_pass_rate` / `record_verdict_event` reference sections next
  to the test_run and commit references.
- `docs/reference/API.md:7280-7287` — `__all__` / Public API summary
  (add `VerdictEvent`, `recent_verdict_events`, `verdict_pass_rate`).
- `docs/reference/CLI.md:2427, 2435` — add `verdict` to `--kind` choices
  table for `search` / `recent`.
- `docs/reference/CLI.md:2509-2514` — add `ll-session recent --kind verdict`
  example.

### Dependent Files (Callers / Importers)

- `scripts/little_loops/pytest_history_plugin.py:17-21, 120-148` —
  `LLHistoryPlugin` consumer pattern for `record_test_run_event()` with
  `contextlib.suppress(Exception)`-wrapped best-effort writes; canonical
  pattern for the call-site guard.
- `scripts/little_loops/pytest_history_plugin.py:61-74` — `_git_output()`
  helper for capturing `head_sha` / `branch` (replaces the aspirational
  `git_utils.py` reference; that file does not exist).
- `scripts/little_loops/cli/session.py:99-118` — both `search`/`recent`
  `--kind` parsers auto-extend via `choices=list(VALID_KINDS)`. No
  change needed; the new kind appears in `--help` automatically.
- `scripts/little_loops/cli/session.py:73` — docstring example block
  needs a `verdict` example added.
- `scripts/little_loops/cli/verify_kinds.py` — CI gate that checks every
  `CREATE TABLE` in `_MIGRATIONS` is registered in `_KIND_TABLE` (or
  explicitly listed in `_KINDLESS_TABLES`). The new `verdict_events`
  table will be checked here (ENH-2581).

### Similar Patterns (Most Relevant Siblings)

- `scripts/little_loops/session_store.py:1222-1272` — `record_commit_event()`
  (ENH-2458, **idempotent** mirror): same FTS pattern, returns `bool`,
  keyword-only parameters. Use this for the FTS content shape
  (line 1263): `f"{target_id} {verdict} {verdict_kind} {severity_counts or ''}".strip()[:512]`.
- `scripts/little_loops/session_store.py:1352-1414` — `record_test_run_event()`
  (ENH-2459, **non-idempotent** mirror): plain `INSERT` + `_index()` FTS,
  no return value, includes `head_sha`/`branch` columns. **Use this for
  the function shape.**
- `scripts/little_loops/session_store.py:890-903` — `_index()` helper for
  the FTS5 write.
- `scripts/little_loops/session_store.py:1054-1091` — `cli_event_context`
  (does NOT swallow `sqlite3.Error`; producers must wrap call sites).
- `scripts/little_loops/session_store.py:1108-1181` — `skill_event_context`
  (DOES swallow `sqlite3.Error`; the safer wrap for the
  `cli/action.py:cmd_invoke` call site).
- `scripts/little_loops/session_store.py:1422-1431` — `fts_phrase()` helper
  for hyphenated IDs (BUG-2651).
- `scripts/little_loops/history_reader.py:651-686` — `recent_commit_events()`
  (closest reader mirror; use as template for `recent_verdict_events`).
- `scripts/little_loops/history_reader.py:689-725` — `recent_test_runs()`
  (alternative reader mirror with `head_sha`/`branch` filters and
  `pass_rate` @property precedent).
- `scripts/little_loops/history_reader.py:497-546` — `summarize_skills()`
  (closest pass-rate aggregation template; returns dicts with
  `success_rate` field; mirror for `verdict_pass_rate`).
- `scripts/little_loops/history_reader.py:124-135` — `CommitEvent` dataclass
  (closest row-shape template; all fields nullable except `ts`).
- `scripts/little_loops/history_reader.py:138-161` — `RunEvent` dataclass
  (alternative; includes `pass_rate` @property at lines 156-161).

### Tests

- `scripts/tests/test_session_store.py:4362-4432` — `TestRecordTestRunEvent`
  (direct sibling; **reference for `TestRecordVerdictEvent`**).
- `scripts/tests/test_session_store.py:4235-4308` — `TestRecordCommitEvent`
  (alternative reference; covers FTS and idempotency).
- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at()`
  helper for the v20→v21 upgrade test.
- `scripts/tests/test_session_store.py:4025-4033` — `test_best_effort_on_unopenable_db`
  (reference for the DB-absent graceful-degradation AC).
- `scripts/tests/test_history_reader.py:1459-1482` — `test_recent_test_runs_and_pass_rate`
  (direct reference for `test_recent_verdict_events_and_pass_rate`).
- `scripts/tests/test_history_reader.py:1438` — `test_recent_commit_events_filters`
  (reference for `test_recent_verdict_events_filters`).
- `scripts/tests/test_history_reader.py:1530-1544` — `test_readers_return_empty_on_missing_db`
  (graceful-degradation pattern; reference for `recent_verdict_events`).
- `scripts/tests/test_ll_session.py:15-114` — `TestArgumentParsing` (need
  `test_recent_subcommand_verdict_accepted` and
  `test_recent_rejects_invalid_kind`-style test for new kind).
- `scripts/tests/test_ll_session.py:1073-1085` — `test_recent_kind_commit_outputs_row`
  (direct mirror for `test_recent_kind_verdict_outputs_row`).
- `scripts/tests/test_ll_session.py:1086-1100` — `test_recent_kind_test_run_outputs_row`
  (second direct mirror).
- `scripts/tests/test_ll_session.py` — `test_search_kind_commit_filters`
  (reference for `test_search_kind_verdict_filters`).

### Configuration

- `scripts/little_loops/config-schema.json:1577-1611` — `analytics.capture`
  block (`additionalProperties: false`); adding a `verdict_events: true`
  toggle is **optional** parity. ENH-2459 `test_run_events` does not gate
  on this — precedent for not gating.

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("Bump
`SCHEMA_VERSION`"). Several other active EPIC-2457 siblings (ENH-2492,
ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2493, ENH-2494, ENH-2495,
ENH-2496, ENH-2497, ENH-2498, ENH-2506, ENH-2511, and others) independently
make the same schema-slot claim in their own Integration Maps — they cannot
all land at the same version number. Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's implied slot;
each child lands its own migration at whatever version is open when it is
implemented (no coordinated release; per EPIC-2457's own "no shared helper
module is required" scope note).

## Session Log
- `/ll:refine-issue` - 2026-07-16T15:56:02 - `64744f61-c486-4d99-a2e6-3ec33ede907d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`