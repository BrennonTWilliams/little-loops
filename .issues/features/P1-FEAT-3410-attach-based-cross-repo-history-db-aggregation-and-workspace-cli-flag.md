---
id: FEAT-3410
title: ATTACH-based cross-repo history.db aggregation and --workspace CLI flag
type: FEAT
priority: P1
status: open
discovered_date: '2026-09-08'
labels:
- path-a
- history-db
- multi-repo
learning_tests_required:
- sqlite3
blocked_by:
- FEAT-3409
parent: FEAT-3399
unproven_mechanism: true
---

## Summary

Given a list of `WorkspaceMember` rows (from FEAT-3409's
`discover_workspace_members()`), implement `aggregate_history_dbs()`: attach
every member's `history.db` read-only onto one connection via SQLite `ATTACH`,
union the quality-analysis queries, and surface the result through a new
`--workspace` flag on `ll-history quality`. A member with mismatched or missing
schema is reported and skipped, never unioned. Source databases are never
written to.

## Parent Issue

Decomposed from FEAT-3399: Cross-repo history.db aggregation (read-only
workspace rollup). This child covers the ATTACH-union mechanism, the
`analyze_agent_quality()` per-schema integration, the `AggregationResult`
formatting, and the `--workspace` CLI wiring. It depends on FEAT-3409 for the
`WorkspaceMember` type and `discover_workspace_members()` function.

## Current Behavior

`history_reader`/`session_store` (`little_loops/history_reader/`,
`little_loops/session_store/`) read a single repo's `.ll/history.db` via
`_connect_readonly()` against `DEFAULT_DB_PATH`. Every quality question —
including the agent-quality report from `analyze_agent_quality()` — is scoped to
whichever repo the invocation runs in; there is no way to ask the question
across a workspace of several repos in one invocation.

## Expected Behavior

One invocation attaches every member repo's `history.db` read-only via SQLite
`ATTACH` and unions the queries, producing a per-repo breakdown plus workspace
totals. Source databases are never written to. A member with a mismatched or
missing schema version is reported and skipped rather than silently unioned or
treated as fatal. With no workspace manifest present (FEAT-3409's
`discover_workspace_members()` returns empty/None), behavior falls back
byte-for-byte to today's single-repo output.

## Design Notes

The mechanism is SQLite `ATTACH`: attach each member repo's database read-only
and union the queries. No materialized cross-repo database, no migration of the
source schemas, no second registry.

Schema-version skew is the interesting failure. Member databases will not all be
at the same migration level, and silently unioning across a schema boundary
produces numbers that look fine and are wrong. Skew must be reported and the
member skipped — never silently mismatched, never normalized.

## Constraints

- **Read-only**: source databases are never written, migrated, or locked for
  writes.
- Schema-version skew across repos must be reported, the member skipped — never
  silently mismatched.

## Integration Map

### Codebase Research Findings

- `scripts/little_loops/issue_history/rework.py` — `analyze_rework()` (called
  internally by `analyze_agent_quality()` at `agent_quality.py:493`) opens its
  own independent `_connect_readonly(db_path)` connection (`rework.py:292`),
  separate from the connection `analyze_agent_quality()` already has open; its
  own queries (`_load_issue_events` `rework.py:136` `FROM issue_events`,
  `_load_commits` `rework.py:151` `FROM commit_events`) are likewise
  unqualified. `_utils.py::orchestrator_labels()` (`_utils.py:74`, called from
  `agent_quality.py:505`) issues a third unqualified query (`FROM
  orchestration_runs`, `_utils.py:81`) against the connection
  `analyze_agent_quality` passes it. This widens the schema-qualification
  surface beyond `agent_quality.py` alone to include `rework.py` and
  `_utils.py`.
- `scripts/little_loops/session_store/queries.py:240` `_snapshot_select()` is
  the only place in the codebase that issues schema-qualified cross-schema SQL
  (`main.{table}`/`snap.{table}`) — the sole existing model for what
  schema-qualified queries would look like if `agent_quality.py`'s/`rework.py`'s
  internal SQL were retargeted at `repo_N.*`.
- No guard or constant for SQLite's attached-database-count limit exists
  anywhere (`SQLITE_MAX_ATTACHED`, 0 hits repo-wide), and no test anywhere
  exercises more than one simultaneous `ATTACH` — the only `ATTACH` call site in
  the entire codebase remains the single one already named
  (`session_store/queries.py:289`, one writable scratch DB).
  > ⚠ Unproven mechanism — multi-ATTACH of several read-only sources has no
  > confirming precedent
- `scripts/little_loops/cli_args.py:260`
  `add_corpus_target_args(parser, *, required, project_help, all_help)` is the
  codebase's existing convention for a report-scope-changing CLI flag: a
  `mutually_exclusive_group` of `--project PATH` / `--all`, called from every
  scope-aware `ll-logs` subcommand. `cli/history.py`'s own subcommands
  (`summary`, `analyze`, `rework`, `quality`) have no such flag today and don't
  use this helper — it is a sibling-module convention, not yet used in
  `cli/history.py`.
- `scripts/little_loops/cli/logs.py:2318` `_cmd_loop_fleet()` /
  `scripts/little_loops/cli/logs.py:1218`
  `_aggregate_fleet_runs(runs: list[_LoopRunRecord])` is the codebase's existing
  convention for aggregating data that is not safely summable per-source (rates,
  medians, deterministic top-picks): collect every source's raw records into one
  flat list first, then call one aggregation function once over the combined
  list — never compute N per-source finished aggregates and then merge those. A
  second convention exists for genuinely additive data: `_cmd_stats()`
  (`cli/logs.py:1634`) sums finished per-DB dicts field-by-field — this works
  only because the fields being summed are raw additive counts, not rates.
- No existing test asserts identical/parallel behavior for N=1 vs N>1
  same-shaped multi-source inputs.
- `QualityAnalysis` (`issue_history/agent_quality.py:135-152`)'s five fields
  split into two combinability classes: `definitions`/`notes`/`min_sample_size`
  are static/config-derived and trivially combinable across repos;
  `windows: list[QualityWindow]` and `retry_windows: list[RetryWindow]` are NOT
  safely combinable by list-concatenation. `QualityMetric.value`
  (`_rate_metrics()`, `agent_quality.py:398`) is an already-divided rate
  (`numerator / closed_count`) with no denominator preserved on the object, and
  `QualityMetric.verdict`/`baseline_period` plus `RetryWindow.mean_iterations`/
  its verdict are each computed relative to a per-repo baseline window selected
  only from that repo's own time series. Concatenating two repos' `windows` rows
  for the same `(period, orchestrator)` key would produce two verdicts each
  computed against a different repo's own baseline, not one workspace-wide
  baseline — `AggregationResult.totals: QualityAnalysis` as a merge of N
  finished per-repo `QualityAnalysis` instances is unsound for these two fields
  specifically.
- **Exact unqualified-SQL call sites for schema-qualification approach (a)** (8
  total, all `conn.execute(...)` with a bare `FROM <table>`):
  `agent_quality.py:229` (`issue_events`), `agent_quality.py:245`
  (`issue_sessions`, a view), `agent_quality.py:259`
  (`correction_retirements`), `agent_quality.py:273` (`user_corrections`),
  `agent_quality.py:301-304` (`usage_events`), `agent_quality.py:419-422`
  (`loop_runs`), `rework.py:136-137` (`issue_events`), `rework.py:150-151`
  (`commit_events`), `_utils.py:81-82` (`orchestration_runs`).
- **Critical constraint on approach (a)**: SQLite resolves an unqualified table
  name against a connection with multiple ATTACHed schemas by searching `main`
  then attached schemas in attach order — it does NOT union across them. A bare
  `FROM issue_events` on a connection with several `repo_N` schemas ATTACHed
  would read only one member's rows, not all of them. Approach (a) is therefore
  a requirement for correctness at all 8 call sites above, via f-string
  interpolation of the schema prefix (`_snapshot_select()`'s `f"... FROM
  main.{table}"` pattern) — SQLite bind parameters cannot parameterize
  identifiers. Approach (b) (call `analyze_agent_quality()` once per member via
  that member's own throwaway connection, bypassing ATTACH for this call)
  requires zero SQL changes at any of the 8 sites.
- `read_schema_version()` (`session_store/queries.py:201-214`, `SELECT value
  FROM meta WHERE key = 'schema_version'`) is itself unqualified (`FROM meta`)
  — the schema-skew gate's own precondition read needs the same qualification
  treatment as the 8 sites above if it is to run against an ATTACHed `repo_N`
  schema rather than a member's own throwaway connection.
- `issue_history/evolution.py::_open_db()` (`evolution.py:30-47`) is the closest
  existing template for a read-only opener that skips `ensure_db()`: checks
  `db_path.exists()` first and returns `None` if missing, opens `mode=ro` URI +
  `PRAGMA query_only = ON`, catches `sqlite3.Error` to return `None`. Adapting
  `history_reader/_base.py::_connect_readonly()` for ATTACH use (rather than
  bypassing it) would mean reshaping it into this same structure — drop the
  `ensure_db(db_path)` call, add the `exists()` guard.

### Files to Modify

- New module (path not yet chosen) implementing `aggregate_history_dbs()` — no
  existing file to modify since the symbol doesn't exist anywhere in the
  codebase today.
- `scripts/little_loops/history_reader/_base.py` — `_connect_readonly()`
  (line 60) is the read-only connection primitive named in this issue's own
  Call Path. It takes `db_path: Path` as a required positional param but calls
  `ensure_db(db_path)` first, which can create/migrate the file — relevant to
  the "never written, migrated" constraint if reused as-is for attaching member
  DBs.
- `scripts/little_loops/issue_history/agent_quality.py` — `analyze_agent_quality()`
  takes a **path**, not a connection: it opens and closes its own
  `_connect_readonly()` connection internally, and every internal query uses
  unqualified table names. It cannot currently be pointed at an already-open
  connection with an ATTACHed schema without either (a) opening one throwaway
  connection per member exactly as today, or (b) a signature change to accept
  an open connection/schema-qualifier and schema-qualify every internal SQL
  string.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand is
  the current single-repo entry point; the no-manifest fallback must reproduce
  this path unchanged.
- `analyze_agent_quality()`'s formatter siblings
  `format_agent_quality_text`/`_json`/`_yaml` (`agent_quality.py:588,670,675`)
  all take `analysis: QualityAnalysis` positionally — only
  `format_agent_quality_markdown()` is named in this issue's Call Path for
  `AggregationResult` extension. A `--workspace --format json/yaml/text`
  combination has no specified output shape yet — decide one.

### Dependent Files (Callers/Importers)

- Importers of the `history_reader/_base.py` `_connect_readonly()` variant (16
  files, beyond `agent_quality.py`): `summary_dag.py`, `usage.py`, `runs.py`,
  `search.py`, `context.py`, `formatting.py`, `events.py`, `subagents.py`,
  `harness.py`, `hooks.py`, `sessions.py`, `digest.py`,
  `history_reader/__init__.py` (re-export), `issue_history/collisions.py`,
  `issue_history/rework.py` — all in `scripts/little_loops/`. Any change to this
  variant's contract (e.g. to support ATTACHed schemas) ripples through every
  one of these.
- The `_open_db` variant (`evolution.py:30-47`/`codegraph.py:81-91`) has its own
  two callers, self-contained within each file — not affected unless this issue
  picks that variant to model.
- `docs/reference/API.md:10421` — documents `queue_store`'s own independent
  `SCHEMA_VERSION`/`_MIGRATIONS` copy — a fourth, unrelated `SCHEMA_VERSION`
  namesake to disambiguate from when implementing the schema-skew gate.
- `docs/reference/API.md:8209` and `CONTRIBUTING.md:299` — both document the
  `history_reader/_base.py` package-layout in prose/diagram form; need a
  mention of the new aggregation module once its location is chosen.
- `scripts/little_loops/pricing.py:11` — a code comment referencing
  `ll-history quality`'s cost-coverage gate; not an importer, but the only other
  production file mentioning the `quality` subcommand by name.
- `scripts/little_loops/cli/artifact/dashboard.py:110`
  `schema_version_warning(source_version)` — a second, independently-implemented
  schema-mismatch detector with its own literal wording, asserted verbatim by
  three tests in `test_feat3304_artifact_dashboard.py`. It is a **warn**
  semantic (artifact still produced with a caveat), whereas this issue's
  decision rule is **skip-and-report** — a different action on the same
  detection. Decide whether the new workspace-level skew message should align
  with or deliberately diverge from this existing wording.

### Naming collision (read carefully)

- **Two distinct functions are both named `_connect_readonly()`** and are NOT
  the same code: `scripts/little_loops/history_reader/_base.py:60` (calls
  `ensure_db()` first, sets `PRAGMA query_only = ON`, returns `None` on any
  error, never raises) vs. `scripts/little_loops/session_store/queries.py:189`
  (no `ensure_db()`, no pragma, **raises** on failure — returns
  `sqlite3.Connection`, not `Connection | None`). `analyze_agent_quality()`'s
  call path uses the `history_reader/_base.py` variant. `build_snapshot_db()`
  (below) uses the `session_store/queries.py` variant. A third variant
  (`issue_history/evolution.py:30-47`, `codequery/codegraph.py:81-91`)
  deliberately skips `ensure_db()` "to avoid failing on a database created by
  the test harness." Pick the variant deliberately; do not assume there is only
  one.

### Existing ATTACH precedent — opposite direction from this issue's proposal

- `scripts/little_loops/session_store/queries.py::build_snapshot_db()`
  (lines ~246-301) is the only `ATTACH DATABASE` call in the codebase: it opens
  **one** source DB read-only (`main`), then `ATTACH DATABASE ? AS snap`
  attaches a **writable scratch** DB onto that same connection, reads
  `read_schema_version(conn)` *before* the ATTACH, and `DETACH`es in a
  `finally`. This issue's proposed shape — several **read-only source** DBs
  ATTACHed onto one connection for a union query — is the inverse direction and
  has no direct precedent; only the ATTACH/DETACH mechanics themselves are
  established.

### Schema-version marker (for the skew check)

- `history.db` carries an explicit version marker in a `meta` key/value table
  (`key = 'schema_version'`), **not** `PRAGMA user_version`. Read via
  `read_schema_version(conn)` (`session_store/queries.py`) — returns
  `str | None`, swallows only `sqlite3.OperationalError` (missing table).
  `SCHEMA_VERSION` (`session_store/schema.py`, currently `47`) is the installed
  code's target version. A mismatch between a member's `read_schema_version()`
  value and the aggregator's own `SCHEMA_VERSION` is the exact skew signal this
  issue's "reported and skipped" requirement needs.

### Conventions in Force

- **Skip-and-report** has three close-but-not-identical precedents, none an
  exact match for `AggregationResult.skipped: list[tuple[str,str]]`:
  `SyncResult.failed`/`skipped` (`sync.py:41-51`), `ValidationResult`'s five
  `list[tuple[str,str]]` fields (`dependency_mapper/models.py:66-71`),
  `StatusTransition.failures`/`cascaded` (`cli/issues/set_status.py:28-44`). The
  three-way `per_repo / totals / skipped-with-reason` combination this issue's
  `AggregationResult` proposes has each element precedented separately but not
  combined before.
- **No precedent for merging multiple instances of the same analysis dataclass**
  exists anywhere (searched for `merge`/`combine`/`union`/`__add__` repo-wide) —
  every existing `*Analysis` dataclass (`QualityAnalysis`, `ReworkAnalysis`,
  `CostReport`) is built once from one connection's results.
  `AggregationResult.totals: QualityAnalysis` combining N per-repo
  `QualityAnalysis` instances would be the first instance of this pattern in
  the codebase — there is no `merge()`/reducer to reuse.

### Tests

- `scripts/tests/test_feat3304_artifact_dashboard.py::TestSourceDbUntouched`
  (lines 443-458) is a direct existing precedent for this issue's "Source DBs
  are provably unmodified after a run" AC:
  `hashlib.sha256(db.read_bytes()).hexdigest()` before/after, plus a companion
  `test_snapshot_builder_never_uses_the_migrating_open_path` that asserts (by
  source inspection) the export path never calls the migrating `connect()` and
  does use `mode=ro`.
- `scripts/tests/test_issue_history_agent_quality.py`,
  `scripts/tests/test_session_store_queries.py`,
  `scripts/tests/test_session_store_schema.py` — existing coverage for
  `analyze_agent_quality`/`_connect_readonly`/`read_schema_version`/`ATTACH` to
  extend or model new tests after.
- **No dedicated test file exists for `history_reader/_base.py` itself** —
  `_connect_readonly()` coverage is entirely indirect, through 12+ sibling
  query-module test files that each test the missing-DB/degrade-to-empty branch
  via their own public function.
- The `session_store/queries.py:189` variant's only direct-name tests:
  `test_feat3304_artifact_dashboard.py:451-458` (source-inspection) and
  `test_feat3323_sse_bridge.py:1157-1162` (imports and calls it directly).
- **ATTACH/DETACH test precedent is NOT in `test_session_store_queries.py`**
  (confirmed zero `ATTACH` hits there) — it lives in
  `test_feat3304_artifact_dashboard.py:734-760::TestBuildSnapshotDb`, which
  tests `build_snapshot_db()` behaviorally rather than inspecting the ATTACH SQL
  directly; no existing test exercises multiple simultaneous ATTACHes.
- `TestHistoryQualitySubcommand` (`test_cli_history.py:220-271`) — existing
  `ll-history quality` coverage; no `--workspace` flag exists today, so a new
  flag/test would be a fifth class member following the same argv-patch +
  `tmp_path` fixture shape as the existing four tests.
- `scripts/tests/test_wiring_cli_registry.py` `DOC_STRINGS_PRESENT`
  (parametrized list, 111 existing entries) — add a `("docs/reference/CLI.md",
  "--workspace", "FEAT-3399")`-shaped entry once the flag's doc prose lands.
- `_build_history_db(path)` — two near-duplicate, module-private, single-project
  DB factories exist (`test_feat3304_artifact_dashboard.py:68-139`,
  `test_feat3323_sse_bridge.py:877-923`), neither shared nor imported by the
  other. No existing test builds more than one repo/history.db per test case
  anywhere in the suite. Tests calling one of these N times to build N member
  DBs would need to either duplicate the factory a third time or promote one to
  a shared/importable fixture.

### Documentation

- `docs/reference/CLI.md:3162-3206` (`#### ll-history quality`) — full flag
  table and metric-definition prose is single-repo-scoped; a `--workspace` flag
  and `AggregationResult` output shape need a new subsection here.
- `docs/guides/HISTORY_SESSION_GUIDE.md:446-486` (§ "Rework and agent-quality
  trends" / "Quality Metric Definitions") — points to `CLI.md` for flag tables;
  needs a workspace-rollup mention.
- `docs/reference/API.md:9412` — already states "Current schema version: 45"
  while `schema.py:25` has `SCHEMA_VERSION = 47` (a pre-existing, unrelated
  staleness) — whoever documents the schema-skew gate here will be editing a
  paragraph that already has a stale version number in it.

## Program Design

### Types

- `AggregationResult`: `per_repo: dict[str, QualityAnalysis]`, `totals:
  QualityAnalysis`, `skipped: list[tuple[str, str]]` (repo, reason)

### Signatures

- `aggregate_history_dbs(members: list[WorkspaceMember]) -> AggregationResult`
  (`WorkspaceMember` from FEAT-3409)

### Call Path

`discover_workspace_members()` [FEAT-3409] -> `aggregate_history_dbs()` (opens
one connection, `ATTACH DATABASE ? AS repo_N` per member via
`_connect_readonly()`'s read-only URI pattern) -> `analyze_agent_quality()` per
attached schema -> `format_agent_quality_markdown()` (extended to render
`AggregationResult`)

### Decision Rules

- **Schema-skew gate**: a member's `read_schema_version(conn)` value that does
  not equal the aggregator's own `SCHEMA_VERSION` (`session_store/schema.py`,
  currently 47) is skipped and reported via `AggregationResult.skipped`, never
  unioned. No normalization path is implied — skew is always "report and skip,"
  never "coerce."
- **No-manifest fallback**: an empty/None result from FEAT-3409's
  `discover_workspace_members()` falls back to exactly today's single-repo
  `ll-history quality` output, byte-for-byte — no partial-aggregation mode with
  one member.
- **Read-only enforcement**: member connections must go through a
  `mode=ro`-URI-based `_connect_readonly()` variant, never the migrating
  `session_store.connect()`/`ensure_db()` path in a way that could write — see
  the three-variant naming collision above; which of the three existing
  variants to model this on is an open implementation call, since none of them
  is itself the ATTACH-multiple-read-only-sources shape this issue needs.

## Implementation Steps

1. `aggregate_history_dbs()` opens one connection and `ATTACH DATABASE ? AS
   repo_N` per member — the ATTACH/DETACH bracketing follows
   `session_store/queries.py::build_snapshot_db()`'s existing precedent, but in
   the reverse direction (N read-only sources onto one connection, not one
   read-only source plus a writable scratch); `read_schema_version(conn)` is
   read per member before any query runs, matching that function's
   version-read-before-touch ordering. Reuse `resolve_history_db()`'s `root=`
   parameter (`session_store/db.py:121`, added per BUG-3181) for per-member path
   resolution rather than reimplementing path discovery.
2. A member whose `read_schema_version()` disagrees with the aggregator's own
   `SCHEMA_VERSION` is appended to `AggregationResult.skipped` and excluded
   from `totals`, never raising.
3. Resolve the open implementation call for `analyze_agent_quality()`: either
   call it once per member's own throwaway `_connect_readonly()` connection
   (bypassing ATTACH for this call, zero SQL changes), or give it a
   schema-qualifier/open-connection parameter and schema-qualify all 8 internal
   unqualified queries plus `read_schema_version()`'s own query.
4. `format_agent_quality_markdown()` is extended to render
   `AggregationResult`'s per-repo breakdown plus totals; since no existing
   dataclass-merge precedent exists in this codebase, the `totals:
   QualityAnalysis` combination is new code, not an adaptation.
5. Decide the `--workspace --format json/yaml/text` output shape and add a
   `--workspace` flag to `ll-history quality` (`cli/history.py`), following
   `cli_args.py::add_corpus_target_args()`'s scope-flag convention (change what
   gets collected, not which formatter branch runs).
6. Source DBs are asserted unmodified via a `hashlib.sha256` before/after
   checksum test, following
   `test_feat3304_artifact_dashboard.py::TestSourceDbUntouched`'s existing
   template.
7. Add a multi-ATTACH test modeled on
   `test_feat3304_artifact_dashboard.py:734-760::TestBuildSnapshotDb`'s
   behavioral-assertion shape, extended for N simultaneous read-only ATTACHes.
8. Add a `--workspace` flag test to `TestHistoryQualitySubcommand`
   (`test_cli_history.py:220-271`), following the same argv-patch + `tmp_path`
   shape as its four existing tests.
9. Add a `("docs/reference/CLI.md", "--workspace", "FEAT-3399")` entry to
   `test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` list once the
   `--workspace` flag's CLI.md doc lands.
10. Update `docs/reference/CLI.md:3162-3206`,
    `docs/guides/HISTORY_SESSION_GUIDE.md:446-486` for the `--workspace` flag
    and `AggregationResult` output shape.
11. Cross-check FEAT-3398's Integration Map citations of
    `analyze_agent_quality()`/`format_agent_quality_markdown()` signatures,
    since this issue changes them.
12. Decide whether the new skip-and-report schema-skew message should align
    with or deliberately diverge from
    `cli/artifact/dashboard.py::schema_version_warning()`'s existing
    warn-semantic wording.

## Impact

- **Priority**: P1 — Valuable multi-repo visibility, but each repo's own report
  already exists as a fallback; this is additive rather than blocking.
- **Effort**: Medium — the ATTACH-union mechanism is well-scoped, but several
  implementation choices (connection variant, schema-qualification approach,
  output format shape) remain open and require a deliberate decision during
  implementation.
- **Risk**: Low — read-only by design; a schema-skew or missing-DB member
  degrades to a skip, not a failure. The multi-ATTACH-of-read-only-sources
  mechanism itself is unproven (no confirming precedent) and should be spiked
  or verified early.
- **Breaking Change**: No

## Acceptance Criteria

- One invocation reports across ≥2 repos, with per-repo breakdown and workspace
  totals.
- Source DBs are provably unmodified after a run (checksum assertion in tests).
- A repo with a mismatched or missing schema is reported and skipped, not
  fatal.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Session Log
- `/ll:issue-size-review` - 2026-09-08T06:21:27 - `c53583bd-6c7a-49a7-8685-76b64ad999da.jsonl`
