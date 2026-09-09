---
id: FEAT-3418
type: FEAT
title: ATTACH-based union totals for cross-repo history.db aggregation with issue_id
  discriminator
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T02:36:19Z'
labels:
- path-a
- history-db
- multi-repo
blocked_by:
- FEAT-3410
decision_needed: false
reconcile_attempted: true
learning_tests_required:
- sqlite3
confidence_score: 90
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# FEAT-3418: ATTACH-based union totals for cross-repo history.db aggregation with issue_id discriminator

## Summary

Follow-up to FEAT-3410, which ships `aggregate_history_dbs()` with
`per_repo` + `skipped` only. This issue owns the deferred workspace-wide
*totals*: one `QualityAnalysis` computed over the union of all workspace
members' `history.db` tables via multi-`ATTACH`, plus the three problems that
made totals unsound as a simple merge of N finished per-repo analyses:

1. **Cross-repo `issue_num`/`issue_id` collisions, in the DB and on disk.**
   Every little-loops repo numbers issues from 1, and
   `agent_quality.py::_load_closed_issues`/`_session_issue_map` key on bare
   `issue_num` while `rework.py::_load_issue_events`/`_load_commits` and
   `_utils.py::orchestrator_labels` key on bare `issue_id`. A naive union
   merges different repos' issues that share an ID. The same collision
   exists on the *on-disk* side: `analyze_rework()` derives `superseded_ids`
   from `superseded_by(info.issue_id, issues)` over whatever `issues` list
   it is given, so concatenating members' `find_issues()` lists lets repo B's
   `FEAT-9 supersedes: [BUG-1]` mark repo A's `BUG-1` as reopened.
2. **`SQLITE_LIMIT_ATTACHED` defaults to 10** on this interpreter
   (confirmed via `sqlite3.connect(":memory:").getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)`)
   and cannot be raised above the compile-time `SQLITE_MAX_ATTACHED`. A
   workspace with more analyzable members than the limit must not silently
   produce a truncated union (per-member connections, as FEAT-3410 uses, have
   no such limit).
3. **The analysis SQL is shared with the single-repo path.** The ~13 query
   sites in `agent_quality.py`/`rework.py`/`_utils.py`/`quality_regressions.py`
   run unqualified `FROM <table>` against `main` for `ll-history quality` and
   for FEAT-3410's per-member connections. Any design that rewrites those
   sites for the union (schema-qualified `UNION ALL` across N attached
   schemas, or a `repo` column that real tables do not have) forks the SQL
   between the two paths. The design below leaves every query site untouched.

### Design (revised 2026-09-09): union views in TEMP, not `main`

Attach each analyzable member's `history.db` read-only as schema `r{i}` to a
`:memory:` connection, then create one **TEMP view** per relation the
analysis reads, as a `UNION ALL` over `r0.<rel>`, `r1.<rel>`, .... SQLite
resolves an unqualified table name in search order `temp -> main -> attached`,
so once a temp view named `issue_events` exists every existing
`FROM issue_events` query hits the union view unchanged.

**Correction (2026-09-09, `/ll:explore-api sqlite3` re-proof):** the
2026-09-08 spike's "define the name in `main`" conclusion is wrong. SQLite
rejects `CREATE VIEW main.<name> AS ...` outright whenever the view body
references *any* attached-schema object — not only in the multi-schema
`UNION ALL` case; even a single-attachment reference fails
(`sqlite3.OperationalError: view <name> cannot reference objects in
database <schema>`), confirmed for both a single-attachment `main` view and
a two-attachment `UNION ALL` `main` view. Only `CREATE TEMP VIEW <name> AS
...` (no schema qualifier — temp views cannot be schema-qualified) can span
attached schemas; the `temp -> main -> attached` resolution order still
makes an unqualified query hit it. Recorded in
`.ll/learning-tests/sqlite3.md` as the `unqualified SELECT ... FROM t
resolves to a persistent main.t VIEW ...` assertion (`result: fail`), with
the working mechanism captured as the corrective claim in the same record.
Every `CREATE VIEW main.<relation>` reference in this issue means `CREATE
TEMP VIEW <relation>`.

The cross-repo discriminator lives **inside the views**, in the id columns
themselves, for the four id-bearing relations (`issue_events`,
`issue_sessions`, `commit_events`, `orchestration_runs`):

```sql
CREATE TEMP VIEW issue_events AS
SELECT 'r0:' || issue_id AS issue_id, 0 * 1000000000 + issue_num AS issue_num, <other cols...>
  FROM r0.issue_events
UNION ALL
SELECT 'r1:' || issue_id AS issue_id, 1 * 1000000000 + issue_num AS issue_num, <other cols...>
  FROM r1.issue_events;
```

`NULL` ids stay `NULL` (`'r0:' || NULL` and `0 + NULL` are `NULL`), so the
existing `IS NOT NULL` filters keep working. Session ids are UUIDs and need
no discriminator; they remain the cross-table join key exactly as today. No
output type (`QualityWindow`, `ReworkWindow`, `RetryWindow`,
`WindowComposition`) carries an issue id, so the prefixed ids never reach a
formatter. The on-disk side is handled symmetrically: the `issues` list
handed to `analyze_agent_quality()` for totals is the concatenation of each
member's `find_issues()` list with `issue_id` and every `supersedes` entry
prefixed with the same `r{i}:` — so `superseded_by()`'s set-membership join
matches DB ids to disk ids only within one member.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis; revised 2026-09-08:_

See Option A/B/C decision under Proposed Solution → Decision Rationale.

## Current Behavior

`aggregate_history_dbs()` (from FEAT-3410) returns an `AggregationResult`
with only `per_repo: dict[str, QualityAnalysis]` and
`skipped: list[SkippedMember]` — `AggregationResult.totals` does not exist.
`agent_quality.py::_load_closed_issues`/`_session_issue_map` and
`rework.py::_load_issue_events` key on bare `issue_num`/`issue_id`, and
`rework.py::analyze_rework` computes `superseded_ids` from a single on-disk
`issues` list, so a naive union across repos — in either the DB or the
`issues` list — would conflate different repos' issues that happen to share
a number.

## Expected Behavior

`aggregate_history_dbs()` additionally computes
`AggregationResult.totals: QualityAnalysis | None` by ATTACH-ing every
member that passed the existing schema-skew gate (each `file:...?mode=ro`)
to one `:memory:` connection, creating union views in `main` for every
relation the analysis reads (with the `r{i}:` / `i * STRIDE` discriminator
baked into the id columns), and running the *unchanged* `analyze_agent_quality()`
over that connection with a discriminated on-disk `issues` list. Cross-repo
`issue_num`/`issue_id` collisions are resolved in both the DB and the
`supersedes:` join. When the analyzable-member count exceeds the
connection's `SQLITE_LIMIT_ATTACHED`, `totals` is `None` and
`AggregationResult.totals_skipped` carries an actionable reason; `per_repo`
is still fully populated (no regression of FEAT-3410's breakdown for large
workspaces).

## Use Case

A developer running `ll-history quality --workspace` across several
little-loops checkouts wants one aggregate quality verdict for the whole
workspace, not just N separate per-repo numbers — e.g. to see whether agent
rework rate is trending up organization-wide even though no single repo
crossed a threshold on its own.

## Acceptance Criteria

- `AggregationResult.totals: QualityAnalysis | None` is populated whenever
  `aggregate_history_dbs()` has at least one member that passed the skew
  gate; it is `None` (with `totals_skipped` set) when zero members are
  analyzable or the attach limit is exceeded. For exactly one analyzable
  member, `totals` equals that member's `per_repo` entry (same
  `to_dict()`).
- The union analysis's rates/denominators reflect all members' combined
  event counts, not an average of per-repo rates (fixture: repo A 3 closed +
  1 reopened, repo B 1 closed + 0 reopened in the same month → union reopen
  rate 0.25, not the per-repo mean 0.167).
- Cross-repo issues sharing the same `issue_num`/`issue_id` are not
  conflated in `totals` (fixture of 2+ repos deliberately reusing `BUG-1`;
  both count as closed).
- `analyze_rework()`'s on-disk `supersedes:` join resolves only within a
  member: repo A's cancelled `BUG-1` is **not** reopened by repo B's
  `FEAT-9 supersedes: [BUG-1]`, while a same-repo `supersedes:` edge still
  is.
- **No query site in `agent_quality.py`, `rework.py`, `_utils.py`, or
  `quality_regressions.py` changes.** Instead, `_open_union()` defines a
  **TEMP** union view for each of the 9 relations those sites read:
  `issue_events`, `issue_sessions`, `correction_retirements`,
  `user_corrections`, `usage_events`, `loop_runs`, `commit_events`,
  `orchestration_runs`, `raw_events` (`main` cannot host these — see Design
  → 2026-09-09 correction: SQLite rejects a `main`-schema view that
  references any attached-schema object). A test asserts all 9 names exist
  in `sqlite_temp_master` (**not** `main.sqlite_master` — a temp view is
  invisible there, confirmed in `.ll/learning-tests/sqlite3.md`) after
  `_open_union()` and that `SELECT COUNT(*) FROM <rel>` on the union
  connection equals the sum across members for at least `issue_events` and
  `usage_events`.
- The id columns of `issue_events`, `issue_sessions`, `commit_events`, and
  `orchestration_runs` views are discriminated (`'r{i}:' || issue_id`,
  `i * STRIDE + issue_num`); `NULL` stays `NULL`.
- When analyzable members exceed `conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)`
  (read from the union connection, never hardcoded), `totals` is `None`,
  `totals_skipped` names the member count and the limit, and `per_repo` is
  unaffected. Tested by monkeypatching the limit helper to return 1 with two
  members.
- Every member's `history.db` main file has an unchanged sha256 after a
  totals run (existing `_sha256` pattern).
- The `sqlite3` Learning Test Registry entry is extended via `/ll:explore-api`
  before implementation lands, covering the claims listed under
  Integration Map → Learning Test Registry.
- `ll-history quality --workspace` text and markdown output render a
  "Workspace totals" section (or the `totals_skipped` reason); JSON/YAML
  gain `totals` and `totals_skipped` keys via `to_dict()`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis; revised 2026-09-08:_

**Option A** (previously selected, now rejected): Repo discriminator threaded through every keying site — widen the keys `agent_quality.py::_load_closed_issues`/`_session_issue_map` build (bare `issue_num`, `agent_quality.py:235-264`) and `rework.py::_load_issue_events` builds (bare `issue_id`, `rework.py:132-145`) to `(repo, issue_num)` / `(repo, issue_id)` tuples, plus a new `WorkspaceMember` discriminator field. Rejected on re-review because it has no SQL mechanism: the real tables have no `repo` column, so `SELECT repo, issue_num FROM issue_events` fails on the single-repo and per-member paths, and supplying one for the union means forking every query into a dynamically generated `UNION ALL` across N attached schemas. It also does nothing for the on-disk `superseded_by()` collision.

**Option B** (previously rejected): `issue_num` remapping in the union views, leaving keying code unchanged. Rejected originally for remapping only `issue_num` and not the `issue_id` string that `rework.py`/`_utils.py` key on.

**Option C** (selected): Option B generalized — union views in `main` that remap **both** `issue_id` (`'r{i}:' || issue_id`) and `issue_num` (`i * STRIDE + issue_num`) for the four id-bearing relations, plus pass-through union views for the other five relations, plus a symmetrically prefixed on-disk `issues` list for the `supersedes:` join. Keying code, `load_window_compositions()`'s signature, `WorkspaceMember`, and every existing query site stay untouched.

> **Selected:** Option C. The discriminator is applied once, at the data boundary in `workspace_quality.py`, in both directions (DB via views, disk via `dataclasses.replace`), and every consumer downstream is unchanged.

### Decision Rationale

**Selected:** Option C — union views in `main` with the discriminator baked into the id columns.

**Reasoning:** The decisive fact is SQLite's name-resolution order (`temp -> main -> attached`): defining a same-named view in `main` makes every existing unqualified query read the union with zero edits, which collapses the previously counted "8 schema-qualification call sites" (really 13 — `quality_regressions.py` has four more at lines 204, 229, 256, 291 that the earlier count missed) to none. Option A's cost was never just "widen some dict keys": the repo column has to come from SQL, and no shared query can select a column that exists only in the union. Option C keeps the single-repo, per-member, and totals paths running byte-identical SQL, so a regression in one is a regression in all three and the existing `test_issue_history_agent_quality.py`/`test_issue_history_rework.py` coverage protects the union path for free. The remaining risk — that a prefixed id could leak into output — was checked: no window/composition dataclass carries an issue id.

**Scoring summary:**

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Discriminator threading | 1 | 0 | 1 | 0 | 2/12 |
| B — `issue_num`-only remap | 1 | 1 | 1 | 0 | 3/12 |
| C — View-layer remap of both ids + prefixed on-disk list | 3 | 3 | 3 | 2 | 11/12 |

**Key evidence:**
- Search order: FEAT-3410's spike showed an unqualified `FROM issue_events` on a multi-ATTACH connection returned exactly one schema's rows — because `main` (a bare `:memory:` db) had no such table and the first attached schema won. A `main` view of that name is resolved first.
- Query inventory that stays unchanged under Option C: `agent_quality.py:239,255,269,283,311-314,429-432`; `rework.py:136-137,150-151`; `_utils.py:81-82`; `quality_regressions.py:204,229,256,291`. Option A/qualification would have had to touch all 13.
- `superseded_by()` (`issue_parser.py:4367-4373`) is a pure Python set-membership over `info.supersedes` lists; prefixing `issue_id` and `supersedes` per member (via `dataclasses.replace` on the plain `@dataclass IssueInfo`, `issue_parser.py:3542`) is the only way to scope it per repo without changing `analyze_rework()`.
- `issue_sessions` (`session_store/schema.py:903-920`) is itself a view inside each attached schema; the spike confirmed `r{i}.<view>` is queryable, so the `main` union view wraps it like any table.
- Existing 2-schema precedent for views/queries spanning `main` + an attached schema: `session_store/queries.py:242,291,300` (`_snapshot_select`/`build_snapshot_db`).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis; revised 2026-09-08:_

**Files to Modify**
- `scripts/little_loops/issue_history/workspace_quality.py` — the only production module that changes. `aggregate_history_dbs()` (lines 83-139) keeps its per-member loop and gate; members that pass the gate are additionally collected (with their `find_issues()` list) for the totals pass that runs after the loop. New helpers `_open_union()`, `_union_view_sql()`, `_attach_limit()`, `_discriminate_issues()` (see Program Design). `_open_member_readonly()` (68-80) is reused unchanged for the gate. `AggregationResult` (45-61) gains `totals` and `totals_skipped` with defaults and serializes both in `to_dict()`. Module docstring lines 16-19 and class docstring line 49 ("No `totals` field") are rewritten.
- `scripts/little_loops/issue_history/agent_quality.py` — **no query changes.** Only `_format_agent_quality_text_workspace()` (line 652) and `_format_agent_quality_markdown_workspace()` (line 747) gain a totals section; `format_agent_quality_json()`/`_yaml()` (855, 864) pick up the new keys via `to_dict()`.
- `scripts/little_loops/issue_history/__init__.py:72` — package docstring mentions "one section per workspace member"; add the totals section.

**Files explicitly NOT modified (regression guard)**
- `agent_quality.py` query sites 239, 255, 269, 283, 311-314, 429-432; `rework.py:136-137,150-151`; `_utils.py:81-82`; `quality_regressions.py:204,229,256,291` — all remain unqualified.
- `session_store/queries.py:211` (`read_schema_version`) — runs on each member's own connection before attach; `main` has no `meta` table by design and never needs one.
- `workspace.py::WorkspaceMember` (31-44) and `_member_from_entry()` (126) — no discriminator field; the discriminator is the attach index `r{i}`, which is unique by construction (`repo_path.name` is not: two members can share a directory name and role, and `discover_workspace_members` only dedups on `db_path`, `workspace.py:233-237`).
- `quality_regressions.py::load_window_compositions()` signature and `issue_window: dict[int, tuple[str, str]]` shape — unchanged.

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/history.py:565` — `main_history()` calls `aggregate_history_dbs()`; no signature change, but the formatter it feeds now renders totals.
- `scripts/little_loops/issue_history/agent_quality.py:520` — `analyze_agent_quality()` forwards `conn=` into `analyze_rework(issues, conn=conn, ...)`; the union connection rides this existing plumbing.
- Importers of `workspace_quality.py`: `agent_quality.py:64`, `cli/history.py:18`, `issue_history/__init__.py:196`, `tests/test_feat3410_workspace_quality.py:22`.

**Conventions in Force**
- Multi-schema SQL is schema-qualified in the statement text and annotated `# noqa: S608` since identifiers can't be bound — evidence: `session_store/queries.py:242` (`_snapshot_select`), inside the only existing `ATTACH DATABASE` site (`queries.py:291`), paired with `DETACH` in `finally` (300). Here this applies to the `CREATE TEMP VIEW <rel> AS ... FROM r{i}.<rel>` statements only (no schema qualifier on the view name itself — temp views can't take one); closing the `:memory:` connection releases every attach, so no explicit `DETACH` is needed.
- Read-only member connections use `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, never the migrating `connect()`/`ensure_db()` — evidence: `queries.py:191-200`, `workspace_quality.py:68-80`; enforced by `test_feat3410_workspace_quality.py::TestSourceDbUntouched::test_never_uses_migrating_opener`. The union connection must be `sqlite3.connect(":memory:", uri=True)` so `ATTACH DATABASE 'file:...?mode=ro'` is parsed as a URI.
- `PRAGMA query_only = ON` blocks `CREATE TEMP VIEW` (spike; re-confirmed 2026-09-09); `_open_union()` creates all views first, then sets the pragma. `mode=ro` on each attach already guarantees the members are never written.
- A function handed an open `conn` neither opens nor closes it — evidence: `agent_quality.py:472-511` (`owns_conn = conn is None`), `rework.py:271-299`. `aggregate_history_dbs()` owns the union connection and closes it in `finally`.
- Per-member fallible steps append `(label, reason)` to `skipped` rather than raising — evidence: `workspace_quality.py:64-139`. The totals pass follows the same shape via `totals_skipped` instead of raising, so an oversized workspace still gets its per-repo breakdown.
- Value-object dataclasses in `issue_history/` hand-write `to_dict()` one line per field — evidence: `agent_quality.py:143-162`, `workspace_quality.py:45-61`. `AggregationResult` is frozen with `skipped` defaulted, so the new fields must carry defaults.
- Formatters duck-type on `hasattr(analysis, "per_repo")` rather than `isinstance` to avoid an import cycle — evidence: `agent_quality.py:636-871`.

### Tests
- `scripts/tests/test_feat3418_workspace_quality.py` — already added (TDD red): `TestWorkspaceTotals::test_totals_populated_for_two_members` and `test_totals_not_conflated_across_id_collision` (two members both recording `BUG-1`). Update its module docstring's "Option A" reference to Option C. Add:
  - (a) denominator test (AC #2) — needs `record_issue_event` `done` then `in_progress` rows for the reopened issue in repo A;
  - (b) cross-repo `supersedes:` test (AC #4) — write a real `.issues/` file in repo B with `supersedes: [BUG-1]` so `find_issues()` produces the edge, and one same-repo supersedes edge in repo A that must still count as reopened;
  - (c) attach-limit test (AC #7) — `monkeypatch.setattr(workspace_quality, "_attach_limit", lambda conn: 1)` with two members → `totals is None`, `totals_skipped` mentions `2` and `1`, `per_repo` has both;
  - (d) view coverage test (AC #5) — all 9 names in `main.sqlite_master` with `type='view'`; counts sum across members;
  - (e) one-member totals equals that member's `per_repo.to_dict()`; zero analyzable members → `totals is None`;
  - (f) sha256 of every member's main db file unchanged after a totals run.
- `scripts/tests/test_feat3410_workspace_quality.py::TestAggregationResultFormatters` — `_sample_result()` and `test_no_skipped_members_reports_none()` construct `AggregationResult(per_repo=..., skipped=...)`; they keep working because both new fields default. Add a formatter case with `totals` set and one with `totals_skipped` set.
- `scripts/tests/test_issue_history_agent_quality.py`, `scripts/tests/test_issue_history_rework.py` — existing per-repo coverage; unchanged and doubling as the union-path guard since the SQL is shared. `_compositions()` (132-158) is untouched.
- Fixture pattern: one `WorkspaceMember` per fake repo under `tmp_path`, each with `.ll/<name>-history.db` (never the default-shaped path — the autouse `_isolate_history_db` fixture would collapse them) — evidence: `test_feat3410_workspace_quality.py::_healthy_member`, `test_feat3418_workspace_quality.py::_member_with_closed_issue`.

### Documentation
- `docs/reference/API.md:2387,2400` — `aggregate_history_dbs`/`AggregationResult` rows; add `totals`/`totals_skipped` and the `_open_union()` helper.
- `docs/reference/CLI.md:3301-3304` — replace "there is no combined-across-repos number yet (tracked separately)" with the totals section description and the attach-limit caveat.
- `docs/guides/HISTORY_SESSION_GUIDE.md:461-465` — same "not yet supported" note.
- `scripts/little_loops/issue_history/workspace_quality.py:16-19` (module docstring) and `:49` (`AggregationResult` docstring) — rewrite; document the view-in-`main` mechanism and why query sites must stay unqualified.
- `scripts/little_loops/issue_history/__init__.py:72` — add the totals section to the package docstring.

### Configuration
- No dedicated config beyond `history.workspace_manifest_path` (read via `BRConfig` in `workspace.py:93`).

### Learning Test Registry
- `.ll/learning-tests/sqlite3.md` extended via `/ll:explore-api sqlite3` on 2026-09-09
  with the 5 claims this design load-bears on, plus one follow-up claim
  triggered by claim 2's refutation. Results (`status: proven`, 15
  assertions total, 2 `fail`):
  1. `ATTACH DATABASE 'file:<path>?mode=ro' AS r0` on a `sqlite3.connect(":memory:", uri=True)` connection works, including for a WAL-mode source; an `INSERT` into `r0.<table>` raises "attempt to write a readonly database". **pass.**
  2. An unqualified `SELECT ... FROM t` resolves to `main.t` when `main` defines a **view** named `t`, even though `r0.t`/`r1.t` tables exist. **FAIL — refuted.** SQLite rejects `CREATE VIEW main.t` outright when the view body references any attached-schema object (`view t cannot reference objects in database <schema>`), even for a single attachment. Only `CREATE TEMP VIEW t` can span attached schemas; the corrective claim (pass) confirms the same unqualified-resolution behavior works via `temp -> main -> attached` search order once the view is TEMP instead. This is the reason for the Design → 2026-09-09 correction above.
  3. `CREATE VIEW main.t AS SELECT ... FROM r0.t UNION ALL SELECT ... FROM r1.t` is allowed on a `:memory:` main and remains queryable after `PRAGMA query_only = ON` (which blocks further `CREATE`). **Superseded by claim 2's refutation** — re-tested as `CREATE TEMP VIEW t ...`: **pass** (queryable after `query_only = ON`; further `CREATE TEMP VIEW` is blocked).
  4. `PRAGMA r0.table_info(<view>)` returns the column list for a view inside an attached schema (used to build the pass-through column lists). **pass.**
  5. `conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)` returns 10 here; `conn.setlimit(...)` can lower it but not raise it above the compile-time max. **pass** (a `setlimit` above 10 is silently clamped back to 10).
  6. Follow-up: a `CREATE TEMP VIEW` is listed in `sqlite_temp_master`/`temp.sqlite_master`, **not** in `main.sqlite_master` or bare unqualified `sqlite_master`. **pass** — this is why the AC #5 test below asserts against `sqlite_temp_master`, not `main.sqlite_master`.

### Wiring Phase (added by `/ll:wire-issue`; revised 2026-09-08)

- `agent_quality.py::_format_agent_quality_text_workspace()` (652) and `_format_agent_quality_markdown_workspace()` (747): render `result.totals` as a "Workspace totals" section using the existing single-repo formatter body, or one line with `result.totals_skipped` when `totals` is `None`.
- `AggregationResult`: add `totals: QualityAnalysis | None = None` and `totals_skipped: str | None = None` after `skipped`; `to_dict()` emits `"totals": self.totals.to_dict() if self.totals else None` and `"totals_skipped"`.
- Rewrite the stale "totals are deferred" / "No totals field" docstrings (`workspace_quality.py:16-19, 49`; `issue_history/__init__.py:72`).
- Update `test_feat3418_workspace_quality.py`'s module docstring (currently cites "Option A").

## Program Design

### Types

- `AggregationResult.totals: QualityAnalysis | None = None` (new)
- `AggregationResult.totals_skipped: str | None = None` (new; reason `totals` is `None`)
- `_UNION_RELATIONS: tuple[str, ...] = ("issue_events", "issue_sessions", "correction_retirements", "user_corrections", "usage_events", "loop_runs", "commit_events", "orchestration_runs", "raw_events")`
- `_ISSUE_KEYED_RELATIONS: frozenset[str] = {"issue_events", "issue_sessions", "commit_events", "orchestration_runs"}`
- `_ISSUE_NUM_STRIDE: int = 1_000_000_000`

### Signatures

- `aggregate_history_dbs(members, *, min_sample, sensitivity, baseline_windows, latest_only) -> AggregationResult` (unchanged signature; now also fills `totals`/`totals_skipped`)
- `_attach_limit(conn: sqlite3.Connection) -> int` (new; returns `conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)`; monkeypatch seam for tests)
- `_open_union(db_paths: list[Path]) -> sqlite3.Connection` (new; `:memory:` + `uri=True` + `sqlite3.Row`; ATTACHes each path as `r{i}`, creates the 9 TEMP views, then `PRAGMA query_only = ON`; caller has already checked `len(db_paths) <= _attach_limit(conn)`)
- `_union_view_sql(conn: sqlite3.Connection, relation: str, schema_count: int) -> str` (new; reads `PRAGMA r0.table_info(relation)` for the column list, substitutes the discriminated `issue_id`/`issue_num` expressions when `relation in _ISSUE_KEYED_RELATIONS`, returns the `CREATE TEMP VIEW <relation> AS ... UNION ALL ...` statement — no schema qualifier on the view name; `main` cannot host a view that references an attached schema, see Design → 2026-09-09 correction; `# noqa: S608`)
- `_discriminate_issues(issues: list[IssueInfo], prefix: str) -> list[IssueInfo]` (new; `dataclasses.replace(info, issue_id=f"{prefix}{info.issue_id}", supersedes=[f"{prefix}{s}" for s in info.supersedes])`)

### Call Path

`aggregate_history_dbs()` -> per-member loop (unchanged gate + `analyze_agent_quality(conn=member_conn)`; collects `(db_path, issues)` for gated members) -> after loop: `_open_union([...])` guarded by `_attach_limit()` -> `_discriminate_issues()` per member, concatenated -> `analyze_agent_quality(combined_issues, conn=union_conn, ...)` -> existing unqualified queries in `agent_quality.py`/`rework.py`/`_utils.py`/`quality_regressions.py` resolve to `main.<view>` -> `AggregationResult(per_repo, skipped, totals, totals_skipped)`.

Totals-pass rules:
- zero gated members → `totals=None`, `totals_skipped="no analyzable members"`;
- `len(gated) > _attach_limit(conn)` → `totals=None`, `totals_skipped=f"{n} analyzable members exceed this SQLite build's SQLITE_LIMIT_ATTACHED={limit}; trim the workspace manifest to at most {limit} members with a history.db"`;
- otherwise `totals` is the union analysis; the union connection is closed in `finally`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis; revised 2026-09-08:_

`aggregate_history_dbs()` (`workspace_quality.py:83-90`) has no `conn:` parameter and gains none. The `conn=` plumbing lives on `analyze_agent_quality()` (`agent_quality.py:472-481`) and `analyze_rework()` (`rework.py:271-278`); both forward an already-open connection unchanged (`owns_conn = conn is None` at `agent_quality.py:509`, `rework.py:295`). The totals pass hands the union connection to the same `analyze_agent_quality(issues, conn=..., ...)` call shape the per-member loop uses (lines 127-135).

Query inventory the union views must cover (all stay unqualified):

| Function | Relation | Line(s) |
|---|---|---|
| `agent_quality.py::_load_closed_issues` | `issue_events` | 239 |
| `agent_quality.py::_session_issue_map` | `issue_sessions` (view) | 255 |
| `agent_quality.py::_load_retirement_fingerprints` | `correction_retirements` | 269 |
| `agent_quality.py::_correction_totals` | `user_corrections` | 283 |
| `agent_quality.py::_usage_totals` | `usage_events` | 311-314 |
| `agent_quality.py::_compute_retry_windows` | `loop_runs` | 429-432 |
| `rework.py::_load_issue_events` | `issue_events` | 136-137 |
| `rework.py::_load_commits` | `commit_events` | 150-151 |
| `_utils.py::orchestrator_labels` | `orchestration_runs` | 81-82 |
| `quality_regressions.py::load_window_compositions` | `usage_events` | 204 |
| `quality_regressions.py::load_window_compositions` | `raw_events` | 229 |
| `quality_regressions.py::load_window_compositions` | `orchestration_runs` | 256 |
| `quality_regressions.py` (retry compositions) | `loop_runs` | 291 |

Every member reaching the union is at `SCHEMA_VERSION` (the gate guarantees it), so `PRAGMA r0.table_info(<relation>)` is a valid column list for all schemas. `issue_sessions` inside each attached schema (`schema.py:903-920`) references its own schema's `issue_events`/`sessions`/`legacy_issue_sessions_ts_overlap` and resolves correctly when read as `r{i}.issue_sessions` (spike-confirmed).

`WorkspaceMember` (`workspace.py:31-44`, frozen, 3 fields) is not modified; the attach index is the discriminator.

`SQLITE_LIMIT_ATTACHED`/`getlimit`/`setlimit` have zero references anywhere in `scripts/` — `_attach_limit()` is the first.

`superseded_by()` (`issue_parser.py:4367-4373`) is Python-side set-membership between `_load_issue_events()`'s DB-sourced `issue_id` keys and `IssueInfo.issue_id`/`IssueInfo.supersedes` from disk. Prefixing both sides identically per member keeps the join exact and scoped.

### Decision Rules

- **ID-collision resolution**: **resolved** — Option C (view-layer remap of both `issue_id` and `issue_num` plus prefixed on-disk `issues`), per `## Proposed Solution` → Decision Rationale. Supersedes the 2026-09-09 Option A decision entry.
- **Query sites**: **must not change.** The single-repo, per-member, and totals paths run identical SQL; the union is expressed entirely as `main` views.
- **`SQLITE_LIMIT_ATTACHED` handling**: **revised** — read the limit from the union connection via `_attach_limit()`; on overflow set `totals=None` + `totals_skipped`, do not raise, so `per_repo` keeps working for large workspaces. Never attach a truncated subset.
- **Discriminator value**: the attach index (`r{i}`), never `repo_path.name` or `_label()` (not unique).
- **1-member workspaces**: `totals` is populated (equals the single `per_repo` entry); the "2+ members" wording in the original AC is dropped for the simpler invariant.

## Impact

- **Priority**: P2 - Deferred correctness/completeness follow-up to FEAT-3410 (P1); the per-repo breakdown already ships without workspace totals.
- **Effort**: Small–Medium - Mechanism is spiked; all production changes are confined to `workspace_quality.py` (union helpers, two dataclass fields) plus two formatter sections. No shared query or keying code changes.
- **Risk**: Low–Medium - The shared analysis code is untouched, so the single-repo path cannot regress from SQL changes; residual risk is in view construction (column-list drift, `NULL` handling) and the on-disk prefixing, both directly tested.
- **Breaking Change**: No - Adds `AggregationResult.totals`/`totals_skipped` with defaults; existing `per_repo`/`skipped` fields and call sites are unaffected.

## Spike result to formalize (from FEAT-3410's inline spike, 2026-09-08)

Multi-ATTACH read-only mechanism confirmed on this interpreter: three
`file:...?mode=ro` URIs attached to a `:memory:` main via
`ATTACH DATABASE ? AS repo_N`; `PRAGMA database_list` showed all four
schemas; per-schema `repo_N.meta` reads returned each member's own version;
a cross-schema `UNION ALL` worked; a view inside an attached schema was
queryable via `repo_N.<view>`; an `INSERT` into an attached table raised
`attempt to write a readonly database` (the `mode=ro` URI alone enforces
this, before `PRAGMA query_only`); sha256 of all three files was unchanged
afterward.

**Confirmed trap, and what it actually implies:** an unqualified
`FROM issue_events` on that connection silently returned rows from exactly
one schema (SQLite search order: temp -> main -> attached in order), not a
union — because the bare `:memory:` main had no `issue_events`. The earlier
conclusion drawn from this ("every unqualified query site needs
schema-qualified SQL") is **retracted**: the same search order means a
view named `issue_events` wins over every attached table of that name, so
the fix is to define the union as a view, not to rewrite the queries.

**Further correction (2026-09-09, `/ll:explore-api sqlite3` re-proof):** the
2026-09-08 conclusion that the union view should live in `main` is itself
wrong. SQLite rejects `CREATE VIEW main.<name> AS ...` outright when the
view body references *any* attached-schema object, confirmed for both a
single-attachment and a two-attachment `UNION ALL` case
(`sqlite3.OperationalError: view <name> cannot reference objects in
database <schema>`). Only `CREATE TEMP VIEW <name> AS ...` (no schema
qualifier) can span attached schemas, and the same `temp -> main ->
attached` search order still makes an unqualified query resolve to it —
`temp` is checked *before* `main`, so a TEMP view is if anything a stronger
fit for this trap than a `main` view would have been.
`session_store/queries.py::_snapshot_select()`'s `main.{table}`/`snap.{table}`
precedent applies only to the `CREATE TEMP VIEW ... FROM r{i}.<rel>`
statements `_union_view_sql()` generates.

Note `PRAGMA query_only=ON` also blocks `CREATE TEMP TABLE`/`CREATE TEMP
VIEW`/`CREATE VIEW` (re-confirmed 2026-09-09), so `_open_union()` creates
its TEMP views *before* enabling the pragma.

**This issue owns:** extending the `sqlite3` Learning Test Registry entry
(via `/ll:explore-api`) with the five claims listed under Integration Map,
the `main` union views with the id discriminator, the prefixed on-disk
`issues` list for the `supersedes:` join, the attach-limit guard, and the
`AggregationResult.totals`/`totals_skipped` fields FEAT-3410 deliberately
omitted.

## Why this is a separate issue

`AggregationResult.totals` cannot be produced by merging N finished
per-repo `QualityAnalysis` instances: rates carry no denominator, and
verdicts/baselines are relative to each repo's own time series — see
FEAT-3410's Design Notes § "Why totals are deferred" and Codebase Research
Findings for the full unsoundness argument. The only sound route is one
analysis run over the union of all members' tables, which is exactly what
multi-ATTACH is for, but that requires solving the ID-collision problem
first — new scope, not a small addition to FEAT-3410.

## Dependencies

- `blocked_by: FEAT-3410` (done) — needs `aggregate_history_dbs()`'s
  `WorkspaceMember` iteration, per-member schema-skew gate, and `conn=`
  plumbing on `analyze_agent_quality()`/`analyze_rework()` as the
  foundation; this issue's union path reuses the same skew gate before
  attaching a member.

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08; updated 2026-09-08 after remediation_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE (was 48/100 → LOW)

_Note (2026-09-08, manual review): the scores above predate the Option A → Option C design revision and should be re-run. The revision removes the cross-module keying changes that drove the earlier outcome-confidence deductions._

### Resolved
- `unapplied_decision` gap: the Program Design paragraphs referencing `conn=` and `superseded_by()` were marked `⚠ Superseded` (clarifying they cite FEAT-3410's existing `conn=` convention and the pre-existing `superseded_by()` join requirement — not Option B's rejected mechanism), confirmed clear via `ll-issues format-check`. Ambiguity score raised 10 → 18.
- Cross-module keying regression risk: added `scripts/tests/test_feat3418_workspace_quality.py` with a deliberate cross-repo `issue_id` collision fixture (two members both recording `BUG-1`), asserting `AggregationResult.totals` exists and is not conflated. Both tests currently fail (TDD red — `AggregationResult` has no `totals` field yet), specifying the behavior FEAT-3418 must implement. Test coverage score raised 18 → 25.

## Session Log
- `/ll:explore-api sqlite3` - 2026-09-09 - extended `.ll/learning-tests/sqlite3.md` with FEAT-3418's 5 required claims (+1 follow-up); refuted the `CREATE VIEW main.<relation>` design premise (SQLite rejects a `main`-schema view referencing any attached object) and confirmed `CREATE TEMP VIEW` as the working mechanism, with temp-view visibility living in `sqlite_temp_master` not `main.sqlite_master`; reconciled Design, Program Design, Integration Map, Conventions, AC #5, and the Spike Result section accordingly
- `/ll:wire-issue` - 2026-09-09T04:15:40 - `e1e686a9-1440-44fa-b3e0-814ed4ea3e38.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T04:03:56 - `92947113-ae24-4c67-9cb1-ea2af355904e.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:47:52 - `5ddcabee-5484-4c88-9c31-8734a1bafe5a.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:42:19 - `b83f9a4d-c528-406f-9176-2cc312651f52.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:17:35 - `ae93785e-f7d9-41cc-96ab-d51f1883c15a.jsonl`
- `/ll:format-issue` - 2026-09-09T02:56:59 - `b1423fb6-b93c-443b-8f26-be96a57e6e5f.jsonl`
