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
members' `history.db` tables via multi-`ATTACH`, plus the two problems that
made totals unsound as a simple merge of N finished per-repo analyses:

1. **Cross-repo `issue_num`/`issue_id` collisions.** Every little-loops repo
   numbers issues from 1, and `agent_quality.py::_load_closed_issues`/
   `_session_issue_map` key on bare `issue_num` while `rework.py::_load_issue_events`
   keys on bare `issue_id`. A naive union merges different repos' issues that
   share an ID. Needs either a repo discriminator threaded through every
   keying site in `agent_quality.py` and `rework.py`, or an `issue_num`
   remapping in the union views — the remapping option must not break
   `analyze_rework()`'s on-disk `supersedes:` join.
2. **`SQLITE_LIMIT_ATTACHED` defaults to 10** on this interpreter
   (confirmed via `sqlite3.connect(":memory:").getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)`)
   and cannot be raised above the compile-time `SQLITE_MAX_ATTACHED`. Any
   ATTACH-union design needs a fail-loud rule for workspaces with more than
   10 members (per-member connections, as FEAT-3410 uses, have no such
   limit).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

See Option A/Option B decision under Proposed Solution → Codebase Research Findings.

## Current Behavior

`aggregate_history_dbs()` (from FEAT-3410) returns an `AggregationResult`
with only `per_repo: dict[str, QualityAnalysis]` and
`skipped: list[SkippedMember]` — `AggregationResult.totals` does not exist.
`agent_quality.py::_load_closed_issues`/`_session_issue_map` and
`rework.py::_load_issue_events` key on bare `issue_num`/`issue_id`, so a
naive union across repos would conflate different repos' issues that happen
to share a number.

## Expected Behavior

`aggregate_history_dbs()` additionally computes `AggregationResult.totals:
QualityAnalysis` by ATTACH-ing every workspace member's `history.db` (each
`file:...?mode=ro`) to one `:memory:` connection and running the existing
analysis functions over a schema-qualified union of their tables. Cross-repo
`issue_num`/`issue_id` collisions are resolved (repo discriminator or
`issue_num` remapping, without breaking `analyze_rework()`'s `supersedes:`
join), and workspaces with more than 10 members fail loudly instead of
silently truncating (SQLite's `SQLITE_LIMIT_ATTACHED` default of 10).

## Use Case

A developer running `ll-history quality --workspace` across several
little-loops checkouts wants one aggregate quality verdict for the whole
workspace, not just N separate per-repo numbers — e.g. to see whether agent
rework rate is trending up organization-wide even though no single repo
crossed a threshold on its own.

## Acceptance Criteria

- `AggregationResult.totals: QualityAnalysis` is populated when
  `aggregate_history_dbs()` runs on 2+ non-skipped members.
- The union analysis's rates/denominators reflect all members' combined
  event counts, not an average of per-repo rates.
- Cross-repo issues sharing the same `issue_num`/`issue_id` are not
  conflated in `totals` (verified with a fixture of 2+ repos deliberately
  reusing IDs).
- `analyze_rework()`'s on-disk `supersedes:` join still resolves correctly
  against the union.
- All 8 schema-qualification call sites are schema-qualified (current
  line numbers, corrected for +10-line drift in `agent_quality.py`:
  `agent_quality.py:239,255,269,283,311-314,429-432`,
  `rework.py:136-137,150-151` (unchanged), `_utils.py:81-82` (unchanged),
  plus `session_store/queries.py:211` (`read_schema_version()`) — an
  unqualified query against the attached connection is a bug per the
  confirmed SQLite search-order trap.
- A workspace with more than 10 members raises a clear, actionable error
  instead of a silent `SQLITE_LIMIT_ATTACHED` truncation.
- The `sqlite3` Learning Test Registry entry for this multi-ATTACH spike is
  formalized via `/ll:explore-api` before implementation lands.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

**Option A**: Repo discriminator threaded through every keying site — thread a discriminator into the keys `agent_quality.py::_load_closed_issues`/`_session_issue_map` build (bare `issue_num`, `agent_quality.py:239-264`, corrected line numbers) and `rework.py::_load_issue_events` builds (bare `issue_id`, `rework.py:132-145`), so two repos' rows sharing a number/ID no longer collide in `issue_window`/`events_by_issue`. `WorkspaceMember` (`workspace.py:31-44`) has no dedicated discriminator field today — only `repo_path`, `role`, `db_path` — so this option needs a new discriminator value derived from one of those (or a new field).

> **Selected:** Option A — repo-discriminator threading generalizes to the real `issue_id` collision surface and matches the existing tuple-key-widening idiom already used throughout these modules; Option B's `issue_num`-only remap doesn't touch `issue_id` (the actual primary key) and risks breaking the on-disk `supersedes:` join.

**Option B**: `issue_num` remapping in the union views — offset or remap each attached repo's `issue_num` range in the SQL view/query itself before the existing keying dicts in `agent_quality.py` ever see it, leaving that keying code unchanged. Must keep `issue_id` strings resolvable against `superseded_by()`'s on-disk join (`issue_parser.py:4367-4373`), since that join matches on `issue_id`, not `issue_num`.

Both options are compatible with the existing skip-and-report per-member skew gate (`workspace_quality.py:64-139`) and the `conn=`-forwarding convention already shipped by FEAT-3410 (`agent_quality.py:472-511`, `rework.py:271-278`) — see Program Design for the correction that `aggregate_history_dbs()` itself has no `conn=` parameter yet.

### Decision Rationale

**Selected:** Option A — Repo discriminator threaded through every keying site.

**Reasoning:** The decisive factor is that Option B is named for `issue_num` remapping, but the actual primary key and collision surface is `issue_id` (a `TYPE-NNN` string that `issue_num` is parsed *out of*, per `session_store/schema.py:842-874`), which multiple downstream sites key on directly (`rework.py::_load_issue_events`/`_load_commits`, `_utils.py::orchestrator_labels`). A pure `issue_num` remap leaves those `issue_id` collisions unresolved, and remapping `issue_id` too would risk breaking `issue_parser.py::superseded_by()`'s on-disk set-membership join (`issue_parser.py:4367-4373`), which has no SQL surface to intercept a remap through. Option A's discriminator-threading instead extends the tuple-key-widening pattern (`dict[tuple[str, str], ...]`) already pervasive in `agent_quality.py`/`rework.py`/`quality_regressions.py`/`debt.py`, and `repo_path.name` is already used as a per-member distinguishing label one layer up in `workspace_quality.py::_label()` — giving it direct precedent to build from. Its cost is a larger blast radius (~10 call sites plus a new `WorkspaceMember` field or derived value) and no existing precedent for a *cross-repo* discriminator specifically, but this is a mechanical, low-risk threading change rather than a novel SQL-generation problem across dynamically attached schemas.

**Scoring summary:**

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Discriminator threading | 2 | 1 | 2 | 1 | 6/12 |
| B — `issue_num` remap in SQL | 1 | 0 | 1 | 0 | 2/12 |

**Key evidence:**
- Option B's own name-scope gap: it remaps `issue_num`, not `issue_id` — the string primary key `issue_num` is derived from (`session_store/schema.py:842-874`) — so it structurally fails to resolve the `issue_id`-keyed collision sites (`rework.py:132-145`, `309-312`; `_utils.py:74-88`) without a second, unaddressed transform.
- Option B also leaves the on-disk `issues: list[IssueInfo]` combination step (feeding `superseded_by()`) unsolved by a SQL-layer-only remap — real footprint extends beyond what the option describes.
- Option A reuses the pervasive `dict[tuple[str, str], ...]` composite-key idiom already in `agent_quality.py:280,288,309,319,358,387-391,397,437`, `rework.py:344,348`, `quality_regressions.py:189-190,201,226,251,286-288`, `debt.py:164`, and `repo_path.name` is already the per-member label in `workspace_quality.py:64-65`.
- No existing repo-wide `remap|offset` convention exists for `issue_num`/ID values (confirmed via unfiltered grep) — Option B's core mechanism would be novel SQL generation across up to `SQLITE_LIMIT_ATTACHED` dynamically-named schemas, a materially different shape than the one existing 2-schema ATTACH precedent (`session_store/queries.py:242,291,300`).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/issue_history/workspace_quality.py` — `aggregate_history_dbs()` (lines 83-139) has no `conn:` parameter of its own today; it opens each member's connection internally via `_open_member_readonly()` (lines 68-80) and calls `analyze_agent_quality(issues, conn=conn, ...)` per member (lines 127-135). A new connection-supplying helper is needed to hand this call site a shared multi-ATTACH connection instead.
- `scripts/little_loops/issue_history/agent_quality.py` — schema-qualification call sites have drifted from this issue's original line citations (see Program Design for the corrected table).
- `scripts/little_loops/issue_history/rework.py` — schema-qualification call sites (136-137, 150-151) are unchanged from this issue's citations.
- `scripts/little_loops/issue_history/_utils.py` — schema-qualification call site (81-82, `orchestrator_labels`) is unchanged from this issue's citations.
- `scripts/little_loops/session_store/queries.py` — `read_schema_version()` (line 211, `SELECT value FROM meta WHERE key = 'schema_version'`) is also unqualified and in scope per the Acceptance Criteria.
- `scripts/little_loops/workspace.py` — `WorkspaceMember` (frozen dataclass, `workspace.py:31-44`) has exactly 3 fields — `repo_path: Path`, `role: str`, `db_path: Path` — no discriminator field exists today.

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/history.py:565` — `main_history()` calls `aggregate_history_dbs()`.
- `scripts/little_loops/issue_history/agent_quality.py:520` — `analyze_agent_quality()` calls `analyze_rework(issues, conn=conn, ...)`, forwarding whatever connection it was given.
- Importers of `workspace_quality.py`: `agent_quality.py:64`, `cli/history.py:18`, `issue_history/__init__.py:196`, `tests/test_feat3410_workspace_quality.py:22`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/quality_regressions.py::load_window_compositions()` (lines 168-170, with internal `issue_window.get(issue_num)` lookups at 217, 242, 268) — consumes `issue_window: dict[int, tuple[str, str]]` built by `agent_quality.py` from `_load_closed_issues()`/`_session_issue_map()`'s keys. If Option A's discriminator threading changes those keys' shape (bare `issue_num` -> a composite key), this signature and its three internal lookups must change in lockstep. [Agent 1 + Agent 3 finding]
- `scripts/little_loops/workspace.py::_member_from_entry()` (line 126) — the sole production constructor of `WorkspaceMember`; must be updated to populate the new discriminator field/value once one is added to the dataclass. [Agent 1 finding]

**Conventions in Force**
- Multi-schema queries in this codebase are schema-qualified in the SQL text itself (`main.{table}` / `snap.{table}`), annotated `# noqa: S608` since identifiers can't be bound as parameters — evidence: `session_store/queries.py:242` (`_snapshot_select`), used inside the only existing `ATTACH DATABASE` call site in the repo (`queries.py:291`, in `build_snapshot_db()`), paired with `DETACH DATABASE` in a `finally` (line 300).
- Read-only cross-repo/export connections use a raw `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, never the package's migrating `connect()`/`ensure_db()` — evidence: `session_store/queries.py:191-200` (`_connect_readonly`), `workspace_quality.py:68-80` (`_open_member_readonly`); enforced by a source-inspection test, `test_feat3410_workspace_quality.py::TestSourceDbUntouched::test_never_uses_migrating_opener`.
- A function that can be handed an already-open connection accepts `conn: sqlite3.Connection | None = None` and neither opens nor closes it — the caller that passed it keeps ownership — evidence: `agent_quality.py:472-511` (`analyze_agent_quality`, `owns_conn = conn is None`), which already forwards into `analyze_rework(conn=conn, ...)` at line 520. `aggregate_history_dbs()` itself has no such parameter yet (see Files to Modify above).
- Per-member workspace operations build `label = f"{member.repo_path.name} ({member.role})"`, try each fallible step individually, and append `(label, reason)` to a `skipped` list rather than raising — evidence: `workspace_quality.py:64-139`.
- Precondition guards elsewhere in the codebase raise `ValueError` naming the actual offending value/count — evidence: `workspace.py:236`, `session_store/queries.py:75`, `stats.py:31-33`, `queue_store.py:237`. No existing `>N-items` guard of this shape exists to model a `SQLITE_LIMIT_ATTACHED` check on directly.
- Value-object dataclasses in `issue_history/` hand-write `to_dict()` as one line per field, with no dataclass-to-dict lockstep test — evidence: `agent_quality.py:143-162` (`QualityAnalysis`), `rework.py:80-129`, `workspace_quality.py:45-61` (`AggregationResult`). Frozen vs. mutable is inconsistent across these dataclasses with no stated rule (`AggregationResult` and `_utils.py:94`'s `MetricDefinition` are frozen; `QualityAnalysis`/`ReworkAnalysis`/`ReworkWindow` are not).
- Formatters accepting either a single-repo or aggregated result duck-type on `hasattr(analysis, "per_repo")` rather than `isinstance`, to avoid a `workspace_quality` <-> `agent_quality` import cycle — evidence: `agent_quality.py:636-871` (`format_agent_quality_*`).

### Tests
- `scripts/tests/test_feat3410_workspace_quality.py` — existing coverage for `aggregate_history_dbs()`/`AggregationResult`.
- `scripts/tests/test_feat3418_workspace_quality.py` — already added (TDD red, per Confidence Check Notes) with a deliberate cross-repo `issue_id` collision fixture (two members both recording `BUG-1`), asserting `AggregationResult.totals` exists and is not conflated; both tests currently fail pending implementation.
- `scripts/tests/test_issue_history_agent_quality.py`, `scripts/tests/test_issue_history_rework.py` — existing per-repo coverage of the keying logic this issue must not regress.
- Fixture pattern for multi-repo scenarios: one `WorkspaceMember` per fake repo under `tmp_path`, each with its own `.ll/<name>-history.db` (never the default-shaped path, since an autouse fixture routes default paths through one shared `LL_HISTORY_DB`) — evidence: `test_feat3410_workspace_quality.py::_healthy_member`/`_bare_sqlite_member`.
- Source-untouched verification: sha256 the source db before/after every skip-path test — evidence: `test_feat3410_workspace_quality.py::_sha256`, used across `test_missing_meta_table`, `test_schema_behind`, `test_schema_ahead`, `TestSourceDbUntouched::test_main_file_hash_unchanged_after_run`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3418_workspace_quality.py` — currently asserts only that `totals` exists and closed-issue counts aren't conflated (`TestWorkspaceTotals::test_totals_populated_for_two_members`/`test_totals_not_conflated_across_id_collision`). Gaps to add: (a) rates/denominators reflect the union's combined event counts rather than an average of per-repo rates (AC #2), (b) the `>10`-member fail-loud `ValueError` guard (AC #6), (c) `analyze_rework()`'s `supersedes:` join still resolves against the union — no current fixture passes a non-empty `issues: list[IssueInfo]` with a `supersedes:` edge (AC #4), (d) `read_schema_version()` schema-qualification against the attached connection, the 8th call site in AC #5. [Agent 3 finding]
- `scripts/tests/test_feat3410_workspace_quality.py::TestAggregationResultFormatters` — `_sample_result()` and `test_no_skipped_members_reports_none()` construct `AggregationResult(per_repo=..., skipped=...)` with no `totals=` kwarg; since `AggregationResult` is `@dataclass(frozen=True)`, both raise `TypeError` once `totals` is added unless it carries a default. Update both call sites, or give `totals` its own default. [Agent 2 + Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py::_compositions()` (lines 132-158) — manually rebuilds `issue_window`/`issue_ids` dicts keyed on bare `issue_num` from `_load_closed_issues()`/`_session_issue_map()`, used by `TestAttribution::test_synthetic_model_excluded_from_dimension`, `test_model_share_weighted_by_row_count`, `test_multi_run_issue_uses_latest_started_at_ll_version`. If discriminator threading changes those keys' shape, this helper will silently key differently or raise a type mismatch — update in lockstep. [Agent 3 finding]
- `scripts/tests/test_workspace.py` — covers `WorkspaceMember` construction (`TestWorkspaceMemberFrozen`, `TestDiscoverWorkspaceMembers*`); no test pins the dataclass's exact field count, so a new discriminator field with a default won't break existing constructor calls, but add coverage asserting the new field is populated by `_member_from_entry()`. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_session_store_queries.py` — existing coverage of `session_store.queries`; no test currently calls `read_schema_version()` directly against an attached (`ATTACH DATABASE`) connection — add one modeled on `test_feat3304_artifact_dashboard.py::TestBuildSnapshotDb`'s attach/select/detach round-trip pattern (the only other `ATTACH DATABASE` test in the repo). [Agent 3 finding]

### Documentation
- `docs/reference/API.md:2387,2400` — `aggregate_history_dbs`/`AggregationResult` API rows; will need a `totals` row.
- `docs/reference/CLI.md:3301-3304` — explicitly states "there is no combined-across-repos number yet (tracked separately)".
- `docs/guides/HISTORY_SESSION_GUIDE.md:461-465` — same "not yet supported" note for workspace totals.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/workspace_quality.py:16-17` (module docstring) — "Workspace-wide totals ... are out of scope -- see FEAT-3410's Design Notes..." and `:49` (`AggregationResult` class docstring) — "No `totals` field -- see the module docstring's..." — both stale once this issue lands; rewrite in the same edit. [Agent 2 finding]
- `scripts/little_loops/issue_history/__init__.py:72` (package docstring) — "... renders an AggregationResult, one section per workspace member" has no mention of a totals section; stale once totals rendering is added to the text/markdown formatters. [Agent 2 finding]
- `docs/reference/API.md:12185-12205` (`### WorkspaceMember` section, including its fenced dataclass code block) — a second `WorkspaceMember` documentation site beyond the already-known `:2387`/`:2400` rows; needs updating if a discriminator field is added to the dataclass. [Agent 2 finding]

### Configuration
- No dedicated config file for this feature beyond `history.workspace_manifest_path` (read via `BRConfig` in `workspace.py:93`). No `ll-workspace.yaml` template/example exists in the repo.

### Learning Test Registry
- `.ll/learning-tests/sqlite3.md` already exists (`status: proven`, dated 2026-09-08) with 4 assertions (isolation_level/in_transaction, WAL concurrent reader/writer, BEGIN IMMEDIATE + busy_timeout, PRAGMA table_info composite-PK numbering) — none cover this issue's multi-ATTACH spike claims (readonly-URI ATTACH, `PRAGMA database_list`, cross-schema `UNION ALL`, view-in-attached-schema query, `PRAGMA query_only` blocking `CREATE TEMP`). Formalizing this spike via `/ll:explore-api` re-proves into this same file rather than creating a second one.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. This issue has no `## Implementation Steps` section to append to, so they are recorded here instead:_

- Update `agent_quality.py::_format_agent_quality_text_workspace()` (line 652) and `_format_agent_quality_markdown_workspace()` (line 747) to render `AggregationResult.totals` — `format_agent_quality_json()`/`_yaml()` (lines 855, 864) already pick it up for free via `to_dict()`, so only the text/markdown paths need code changes.
- Update `workspace.py::_member_from_entry()` (line 126) to populate the new discriminator field/value on `WorkspaceMember`.
- Update `quality_regressions.py::load_window_compositions()` (lines 168-170, 217, 242, 268) if the discriminator design changes `issue_window`'s key shape from bare `issue_num`.
- Give `AggregationResult.totals` a field default (or update both breaking call sites in `test_feat3410_workspace_quality.py::TestAggregationResultFormatters`) — `AggregationResult` is a frozen dataclass and `skipped` already has a `default_factory`, so a new non-default field must either come after all defaulted fields with none itself, or carry its own default.
- Rewrite the stale "totals are deferred" / "No totals field" docstrings in `workspace_quality.py` (module docstring lines 16-17, `AggregationResult` docstring line 49) and `issue_history/__init__.py` package docstring (line 72).

## Program Design

### Types

- `AggregationResult.totals: QualityAnalysis` (new field on FEAT-3410's dataclass)

### Signatures

- `aggregate_history_dbs(members: list[WorkspaceMember]) -> AggregationResult` (extended)
- `_attach_and_union(members: list[WorkspaceMember]) -> sqlite3.Connection` (new; enforces the >10-member fail-loud rule)
- `_resolve_issue_discriminator(conn: sqlite3.Connection, member_count: int) -> None` (new; repo discriminator or `issue_num` remapping)

### Call Path

`aggregate_history_dbs()` -> `_attach_and_union()` ->
`analyze_agent_quality(conn=...)` / `analyze_rework(conn=...)` (FEAT-3410's
`conn=` plumbing) -> schema-qualified queries in `agent_quality.py`/`rework.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

`aggregate_history_dbs()` (`workspace_quality.py:83-90`) has no `conn:` parameter of its own — contrary to what the Call Path above might imply. The `conn=` plumbing that already exists lives on `analyze_agent_quality()` (`agent_quality.py:472-481`) and `analyze_rework()` (`rework.py:271-278`); both already forward an already-open connection unchanged when given one (`owns_conn = conn is None` at `agent_quality.py:509`, `rework.py:295`). A new helper (e.g. `_attach_and_union()`) would need to build the multi-ATTACH connection and hand it into `aggregate_history_dbs()`'s existing `analyze_agent_quality(issues, conn=conn, ...)` call site (lines 127-135), not receive a `conn=` argument on `aggregate_history_dbs()` itself.

Corrected schema-qualification line numbers — `agent_quality.py`'s sites have drifted +10 lines from this issue's original citations; `rework.py`/`_utils.py` have not drifted:

| Function | Query | Issue's cited line(s) | Current line(s) |
|---|---|---|---|
| `_load_closed_issues` | `FROM issue_events` | 229 | 239 |
| `_session_issue_map` | `FROM issue_sessions` | 245 | 255 |
| `_load_retirement_fingerprints` | `FROM correction_retirements` | 259 | 269 |
| `_correction_totals` | `FROM user_corrections` | 273 | 283 |
| `_usage_totals` | `FROM usage_events` | 301-304 | 311-314 |
| `_compute_retry_windows` | `FROM loop_runs` | 419-422 | 429-432 |
| `rework.py::_load_issue_events` | `FROM issue_events` | 136-137 | unchanged |
| `rework.py::_load_commits` | `FROM commit_events` | 150-151 | unchanged |
| `_utils.py::orchestrator_labels` | `FROM orchestration_runs` | 81-82 | unchanged |
| `session_store/queries.py::read_schema_version` | `FROM meta` | (uncited) | 211 |

`WorkspaceMember` (`workspace.py:31-44`, frozen) has exactly 3 fields — `repo_path: Path`, `role: str`, `db_path: Path` — no repo-discriminator field exists today; a discriminator design has nothing pre-built beyond `repo_path.name` (already used for display-only labeling in `_label()`, `workspace_quality.py:64-65`).

`SQLITE_LIMIT_ATTACHED`/`getlimit`/`setlimit` have zero references anywhere in `scripts/` — confirmed only in this issue's and FEAT-3410's own markdown text, not in code.

The on-disk `supersedes:` join `analyze_rework()` must keep resolving (AC #4) is `issue_parser.py::superseded_by()` (lines 4367-4373) — a Python-side set-membership check between `_load_issue_events()`'s DB-sourced `issue_id` keys and each `IssueInfo.issue_id` parsed from disk. It runs no SQL of its own, so compatibility here is about keeping `issue_id` strings matchable between the on-disk `issues` list and whatever the union DB exposes under `issue_id` — not about the SQL query shape.

### Decision Rules

- **ID-collision resolution**: **resolved** — Option A (repo discriminator threaded through every keying site), per `## Proposed Solution` → Decision Rationale. The discriminator must leave `superseded_by()`'s `issue_id` set-membership join (above) resolvable against whatever the union stores under `issue_id`.
- **`SQLITE_LIMIT_ATTACHED` fail-loud threshold**: the guard should call `sqlite3.connect(":memory:").getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)` itself rather than hardcode `10`, since `SQLITE_MAX_ATTACHED` is compile-time and can differ across interpreters/builds. No escape hatch specified anywhere in this issue — any workspace exceeding the limit must raise, with no fallback to a partial/truncated union.

## Impact

- **Priority**: P2 - Deferred correctness/completeness follow-up to FEAT-3410 (P1); the per-repo breakdown already ships without workspace totals.
- **Effort**: Medium - Mechanism is spiked and confirmed (see below); remaining work is schema-qualifying ~8 call sites, designing the ID-discriminator, and the fail-loud member-count guard.
- **Risk**: Medium - Touches shared keying logic in `agent_quality.py` and `rework.py` that must stay correct for the existing single-repo path; the ID-remapping option specifically must not break `analyze_rework()`'s `supersedes:` join.
- **Breaking Change**: No - Adds `AggregationResult.totals`; existing `per_repo`/`skipped` fields and call sites are unaffected.

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

**Confirmed trap:** an unqualified `FROM issue_events` on that connection
silently returned rows from exactly one schema (SQLite search order:
temp -> main -> attached in order), not a union — every unqualified query
site needs schema-qualified SQL (`f"... FROM repo_N.{table}"`, following
`session_store/queries.py::_snapshot_select()`'s `main.{table}`/`snap.{table}`
precedent) since SQLite bind parameters cannot parameterize identifiers.

Note `PRAGMA query_only=ON` also blocks `CREATE TEMP TABLE`/`CREATE TEMP
VIEW`, so a union-view design must create its views in the writable
`:memory:` main *before* enabling the pragma, or skip the pragma and rely on
`mode=ro` alone.

**This issue owns:** formalizing the `sqlite3` Learning Test Registry entry
for this spike (via `/ll:explore-api`) before implementing, the 8
schema-qualification call sites cataloged in FEAT-3410's Integration Map
(`agent_quality.py:229,245,259,273,301-304,419-422`, `rework.py:136-137,150-151`,
`_utils.py:81-82`, plus `read_schema_version()`'s own `FROM meta` query),
the repo discriminator or `issue_num` remapping design, the >10-member
fail-loud rule, and the `AggregationResult.totals: QualityAnalysis` field
FEAT-3410 deliberately omitted.

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

- `blocked_by: FEAT-3410` — needs `aggregate_history_dbs()`'s
  `WorkspaceMember` iteration, per-member schema-skew gate, and `conn=`
  plumbing on `analyze_agent_quality()`/`analyze_rework()` as the
  foundation; this issue's ATTACH-union path reuses the same skew gate
  before attaching a member.

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08; updated 2026-09-08 after remediation_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE (was 48/100 → LOW)

### Resolved
- `unapplied_decision` gap: the Program Design paragraphs referencing `conn=` and `superseded_by()` were marked `⚠ Superseded` (clarifying they cite FEAT-3410's existing `conn=` convention and the pre-existing `superseded_by()` join requirement — not Option B's rejected mechanism), confirmed clear via `ll-issues format-check`. Ambiguity score raised 10 → 18.
- Cross-module keying regression risk: added `scripts/tests/test_feat3418_workspace_quality.py` with a deliberate cross-repo `issue_id` collision fixture (two members both recording `BUG-1`), asserting `AggregationResult.totals` exists and is not conflated. Both tests currently fail (TDD red — `AggregationResult` has no `totals` field yet), specifying the behavior FEAT-3418 must implement. Test coverage score raised 18 → 25.

## Session Log
- `/ll:wire-issue` - 2026-09-09T04:15:40 - `e1e686a9-1440-44fa-b3e0-814ed4ea3e38.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T04:03:56 - `92947113-ae24-4c67-9cb1-ea2af355904e.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:47:52 - `5ddcabee-5484-4c88-9c31-8734a1bafe5a.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:42:19 - `b83f9a4d-c528-406f-9176-2cc312651f52.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:17:35 - `ae93785e-f7d9-41cc-96ab-d51f1883c15a.jsonl`
- `/ll:format-issue` - 2026-09-09T02:56:59 - `b1423fb6-b93c-443b-8f26-be96a57e6e5f.jsonl`
