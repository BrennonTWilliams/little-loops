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
unproven_mechanism: false
verify_verdict: VALID
size: Large
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
spike_needed: false
---

## Summary

Given a list of `WorkspaceMember` rows (from FEAT-3409's
`discover_workspace_members()`), implement `aggregate_history_dbs()`: open
every member's `history.db` read-only, run the quality analysis per member,
and surface the per-repo breakdown (plus skipped members with reasons) through
a new `--workspace` flag on `ll-history quality`. A member with mismatched or
missing schema is reported and skipped, never analyzed. Source databases are
never written to.

**Scope decision (2026-09-08 pre-implementation review):** workspace-wide
*totals* (one `QualityAnalysis` computed over the union of all members) are
split out to a follow-up issue — see Design Notes § "Why totals are deferred".
This issue ships `per_repo` + `skipped` only. Consequently the multi-`ATTACH`
union mechanism named in the title is *not* exercised by this issue's code
path (per-member `mode=ro` connections need no ATTACH); the title is retained
for continuity with FEAT-3399, and the ATTACH spike result is recorded below
for the follow-up. Because this issue's own mechanism (per-member read-only
connections, precedented by `issue_history/evolution.py::_open_db()`) is not
unproven, `unproven_mechanism`/`spike_needed` were cleared on 2026-09-08 and
the Learning Test Registry entry for multi-ATTACH moved to the follow-up
issue (Step 13).

## Parent Issue

Decomposed from FEAT-3399: Cross-repo history.db aggregation (read-only
workspace rollup). This child covers the ATTACH-union mechanism, the
`analyze_agent_quality()` per-schema integration, the `AggregationResult`
formatting, and the `--workspace` CLI wiring. It consumes the `WorkspaceMember` type and
`discover_workspace_members()` function that FEAT-3409 landed on 2026-09-08
(`scripts/little_loops/workspace.py`).

## Current Behavior

`history_reader`/`session_store` (`little_loops/history_reader/`,
`little_loops/session_store/`) read a single repo's `.ll/history.db` via
`_connect_readonly()` against `DEFAULT_DB_PATH`. Every quality question —
including the agent-quality report from `analyze_agent_quality()` — is scoped to
whichever repo the invocation runs in; there is no way to ask the question
across a workspace of several repos in one invocation.

## Expected Behavior

One invocation opens every member repo's `history.db` read-only and runs the
quality analysis per member, producing a per-repo breakdown (labeled
`<repo> (<role>)`) plus a list of skipped members with reasons. Source
databases are never written to. A member with a mismatched or missing schema
version is reported and skipped rather than silently analyzed or treated as
fatal. With no workspace manifest present (FEAT-3409's
`discover_workspace_members()` returns `[]`), behavior falls back
byte-for-byte to today's single-repo output. Workspace-wide totals are a
follow-up (see Design Notes).

## Use Case

**Who**: A developer or team lead who works across a workspace of several
little-loops-enabled repos (e.g. a monorepo-adjacent set of sibling projects
sharing one workspace manifest).

**Context**: They want to check agent-quality metrics (fix rate, correction
rate, retry inflation) for the whole workspace, not one repo at a time — today
`ll-history quality` only ever answers for the single repo it's invoked in.

**Goal**: Run `ll-history quality` with the new `--workspace` flag once and
get a per-repo breakdown, with any repo whose `history.db` schema is stale or
missing clearly called out rather than silently analyzed.

**Outcome**: One report replaces manually running `ll-history quality` in each
member repo; a schema-skewed or absent member is reported by name instead of
producing wrong numbers or crashing the run.

## Design Notes

Each member's database is opened through its own raw `file:{path}?mode=ro`
URI connection (never through an opener that calls `ensure_db()` — see
"Read-only enforcement" below) and the existing single-repo analysis runs once
per member against that connection. No materialized cross-repo database, no
migration of the source schemas, no second registry.

Schema-version skew is the interesting failure. Member databases will not all be
at the same migration level, and silently analyzing across a schema boundary
produces numbers that look fine and are wrong. Skew must be reported and the
member skipped — never silently mismatched, never normalized.

### Why totals are deferred (2026-09-08 review)

A workspace-wide `QualityAnalysis` cannot be produced by merging N finished
per-repo instances (rates carry no denominator; verdicts are relative to each
repo's own baseline — see Codebase Research Findings). The only sound route is
one analysis run over the *union* of all members' tables, which is exactly
what multi-`ATTACH` is for. But that union has a second problem this issue's
research had not surfaced: **issue identifiers collide across repos.** Every
little-loops repo numbers issues from 1, and the analysis keys on bare
`issue_num` (`agent_quality.py::_load_closed_issues`, `_session_issue_map`)
and bare `issue_id` (`rework.py::_load_issue_events`). A union would merge
different repos' issues that share an ID. Fixing that means either a repo
discriminator threaded through every keying site in `agent_quality.py` and
`rework.py`, or an `issue_num` remapping in the union views that also breaks
`analyze_rework()`'s on-disk `supersedes:` join. Either is its own issue.
Additionally SQLite's attached-database limit is 10 by default
(`sqlite3.connect(":memory:").getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)` == 10
on this interpreter; it cannot be raised above the compile-time
`SQLITE_MAX_ATTACHED`), so any ATTACH-union design also needs a fail-loud rule
for workspaces with more than 10 members. Per-member connections have no such
limit. **Decision:** ship `per_repo` + `skipped` here; file a follow-up for
union totals that owns the discriminator, the >10-member rule, and the
`ATTACH` mechanics proven by the spike in Verification Notes.

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
- _(2026-09-08 review: the two "approach (a)" findings below and the
  "option (b) blast radius" wiring note describe the ATTACH-union design,
  which is now the deferred totals follow-up's concern. They are retained as
  research for that issue; this issue's per-member-connection design needs no
  SQL qualification. The `SCHEMA_VERSION` literals in this section are
  historical — never compare against a number.)_
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

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- No CLI flag anywhere in this codebase forks an entire subcommand function body into two structurally different code paths. Every existing scope flag (`_cmd_dead_skills`/`_cmd_stats`/`_cmd_loop_fleet` in `cli/logs.py`, via `--project`/`--all`) only narrows the *list-construction* step (`db_paths`/`discovered`) — every line after the branch is unbranched and iterates the resulting list uniformly. The one full-function fork found in this codebase (`cli/history.py`'s `summary` subcommand, `db_available = issue_events_ever_recorded(db_path)` branching to `scan_completed_issues_from_db` vs. `scan_completed_issues`) is condition-driven on data availability, not CLI-flag-driven. `--workspace` has no existing flag-driven full-fork precedent to model; the closest analogues are the narrow list-construction branch (Pattern 1) or a data-availability fork resembling the `summary` subcommand's shape (relevant to the no-manifest fallback decision rule already in this issue).
- No type-level distinction (type alias, `NewType`, or protocol) between a read-only and a writable `sqlite3.Connection` exists anywhere in this codebase (searched repo-wide) — every connection, read-only or not, is typed as bare `sqlite3.Connection` (or `Connection | None`). "Read-only" is signaled only by the `file:{path}?mode=ro` URI string plus a `_connect_readonly`-named helper, never by a type-level marker.
- No function anywhere in this codebase accepts an already-open `sqlite3.Connection` documented/typed as "may have N attached schemas" as a parameter (searched all `ATTACH` occurrences repo-wide). The one existing ATTACH call site (`build_snapshot_db`) takes two `Path` arguments and opens/attaches/detaches internally within one function body, on paths it opened itself — it never receives a pre-attached connection from a caller. This reinforces the Program Design "Read-only enforcement" decision rule's statement that none of the three existing `_connect_readonly` variants is itself the ATTACH-multiple-read-only-sources shape this issue needs.
- No test in `issue_history/` or `history_reader/` asserts schema-version-mismatch skip behavior specifically. The existing "missing/empty DB" test convention in those modules (`class TestMissingDatabase`-style: a `db = tmp_path / "nonexistent.db"` case plus a separate `ensure_db(db)`-then-empty-tables case, both asserting degrade-to-the-type's-own-empty-value with no assertion on a recorded reason) is a distinct behavior from this issue's schema-skew skip-and-report requirement — the skew-specific test this issue needs (Implementation Step 7's sibling for the schema-skew gate) has no existing test to extend, only the missing-DB shape to pattern-match structurally.
- Two more "skip and record why" shapes exist beyond the three already cited (`SyncResult`, `ValidationResult`, `StatusTransition`), both weaker matches than those three: `ConsultStats.skipped: int` (`history_reader/events.py:265,279,299-308`) is a bare incrementing counter with no reason string attached per skip; `RejectionAnalysis.common_reasons: list[tuple[str, int]]` (`issue_history/models.py:373`) tallies reasons by frequency but detaches the reason from which record produced it once counted. Neither preserves a per-skipped-item `(item, reason)` pair the way `AggregationResult.skipped: list[tuple[str, str]]` needs to.

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
  `_connect_readonly()` connection internally. **Passing a member's path
  (`db=member.db_path`) is NOT a read-only option** (2026-09-08 review):
  `history_reader/_base.py::_connect_readonly()` calls `ensure_db(db_path)`
  first, which opens read-write, runs `_apply_migrations()`, and sets WAL via
  `_configure_connection()` (`session_store/schema.py:1519-1557,1392`). A
  stale member would be silently migrated to the current version *before*
  the skew gate could see it, and even a current member gets `-wal`/`-shm`
  sidecars written. `analyze_rework()` (`rework.py:292`) opens its own
  connection the same way. Both functions therefore need a `conn=` parameter
  (see Program Design § Signatures) so the aggregator can hand in a raw
  `mode=ro` connection it opened itself.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand is
  the current single-repo entry point; the no-manifest fallback must reproduce
  this path unchanged. **Citation refresh (2026-09-08, after FEAT-3398/3405
  landed):** `quality_parser` is at lines 266-310 and now defines five flags
  (`-f/--format`, `--min-sample`, `--sensitivity`, `--baseline-windows`,
  `--all-windows`); the dispatch block is at lines 508-553, calling
  `analyze_agent_quality(all_issues, db=db_path, min_sample=…,
  sensitivity=…, baseline_windows=…, latest_only=not args.all_windows)` at
  line 535. The `--workspace` path must forward all of `min_sample`,
  `sensitivity`, `baseline_windows`, `latest_only` to every per-member call.
- **Per-member `issues` argument** (2026-09-08 review): `analyze_agent_quality()`
  forwards `issues` to `analyze_rework()` to resolve `supersedes:` edges. The
  CLI builds `all_issues` from the *invoking* repo's `config` only. Each member
  needs its own on-disk issues: `find_issues(BRConfig(member.repo_path),
  status_filter=all_statuses)` (`BRConfig(project_root: Path)`,
  `config/core.py:277`; `workspace.py:93` already constructs `BRConfig(root)`
  the same way). `aggregate_history_dbs()` owns this per-member lookup.
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
- `scripts/little_loops/cli/artifact/dashboard.py:225` `build_history_payload()`
  is a second caller of `build_snapshot_db()` beyond the three
  `TestBuildSnapshotDb` tests already named under Existing ATTACH precedent
  below. It invokes `build_snapshot_db()` inside a `tempfile.TemporaryDirectory`
  block with no `try/except` around the call, and neither it nor its own caller
  `build_dashboard_html()` (dashboard.py:277) catches anything but `ValueError`
  (dashboard.py:426, 447; `cli/artifact/serve.py:102` likewise). A raw
  `sqlite3.Error` from an incompatible-schema ATTACH is not caught anywhere in
  this call chain — there is no "detect bad schema on this one attachment,
  report it, continue with the others" precedent here to adapt; the per-member
  skip-and-continue logic this issue needs would be new code in this respect
  too, not an adaptation of an existing catch.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/__init__.py:75-85,159-273` — re-exports
  `analyze_agent_quality`, `format_agent_quality_text/_json/_markdown/_yaml`,
  `QualityAnalysis`, `QualityMetric`, `QualityWindow`, `RetryWindow` (both as
  direct imports and in `__all__`), with one-line docstring summaries of each.
  A signature change to `analyze_agent_quality()` needs this docstring updated
  too, and if `aggregate_history_dbs()`/`AggregationResult` are meant to be
  publicly importable, this is the export point to add them to — no existing
  citation in this issue names it.
- `scripts/little_loops/cli/doctor.py:483-608` (`_schema_drift_data()` /
  `_schema_drift_check()`, ENH-3242) — a **third**, independently-implemented
  `.ll/history.db` schema-mismatch detector, distinct from both this issue's
  proposed skew gate and `dashboard.py::schema_version_warning()`. It does a
  structural PRAGMA-manifest diff (not a simple version-number compare) and
  reports wording like "missing from database", "behind (recorded N of M...)",
  or "recorded schema_version N exceeds this install's M known migrations",
  registered via `@register_check` and asserted by
  `scripts/tests/test_cli_doctor_install_checks.py` (`TestSchemaDrift`-shaped,
  ~lines 231-430). Relevant to Implementation Step 12's align-or-diverge
  wording decision — that decision now has three existing wordings to weigh
  against, not one.
- `scripts/little_loops/templates/dashboard.llat/manifest.yaml:16-19,33-36` and
  `template.html.j2:83-88` — the dashboard artifact template declares
  `schema_version_warning` as a manifest field and renders it verbatim into a
  `<p class="warn">` block in generated HTML. `schema_version_warning()`'s
  exact wording is therefore also directly user-facing rendered content, not
  just asserted by the 3 unit tests already cited — a fourth site Step 12's
  wording decision should account for.
- `.issues/features/P0-FEAT-3405-quality-regression-detection-attribution-and-report-cli-wiring.md`
  — a live sibling issue (beyond the already-cited FEAT-3398) that cites the
  exact current signatures of `analyze_agent_quality()` and
  `format_agent_quality_markdown()`/`_text()` and proposes its own additive
  extensions (`sensitivity`, `baseline_windows`, `latest_only` kwargs; a new
  `QualityAnalysis.regressions` field). FEAT-3405's own Dependencies section
  already names FEAT-3410 as the sibling to coordinate with ("whichever lands
  second re-verifies its citations"), but this issue's Implementation Step 11
  only names FEAT-3398 for the cross-check — FEAT-3405 should be added to that
  cross-check list.

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
  `SCHEMA_VERSION` (`session_store/schema.py:25`) is the installed code's
  target version. Do **not** cite its numeric value anywhere in this issue or
  in code/tests — it drifted 47 → 48 → 49 within 2026-09-08 alone; compare
  against the imported constant. A mismatch between a member's
  `read_schema_version()` value and `str(SCHEMA_VERSION)` is the exact skew
  signal this issue's "reported and skipped" requirement needs. Note
  `read_schema_version()` returns `None` for two distinct conditions (no
  `meta` table vs. no `schema_version` row); the skip reason must
  distinguish these from a missing file (see Decision Rules). It swallows
  **only** `sqlite3.OperationalError`: a file that is not SQLite at all (or
  is corrupt) opens lazily without error and then raises
  `sqlite3.DatabaseError: file is not a database` on this first query
  (confirmed 2026-09-08), so the gate must wrap the version read in its own
  `sqlite3.Error` catch — the open call alone is not enough.

### WAL sidecars are expected (confirmed 2026-09-08)

`ensure_db()` sets `PRAGMA journal_mode = WAL` (`session_store/schema.py:1406`),
which is persisted in the file header, so every real member `history.db` is
WAL-mode. Opening a WAL-mode database with `file:…?mode=ro` **creates
`history.db-wal` and `history.db-shm`** on the first read and, because a
read-only connection cannot delete them, they **persist after close**. The
main file's sha256 is unchanged throughout. Consequences: the untouched-source
assertion is main-file-checksum only (never "no sidecars"), and `immutable=1`
must **not** be used to avoid the sidecars — it ignores an un-checkpointed WAL
left by a live writer (a hook in the member repo) and would read stale data.

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

_Wiring pass added by `/ll:wire-issue`:_
- **Concrete blast radius if Implementation Step 3 picks option (b)**
  (schema-qualifier/open-connection param): `analyze_agent_quality(db=...)` is
  called with the current path-based signature 31 times (per `grep -c`,
  2026-09-08; the per-class list below is a sample, not exhaustive) in
  `test_issue_history_agent_quality.py` (`TestEmptyAndMissingDb:107`,
  `TestBelowMinimumSample:118,128`, `TestFixRate:143`,
  `TestCorrectionRate:159,177,193`, `TestCostAndTokensPerIssue:207`,
  `TestCostCoverageGate:223,237,253`, `TestRetryInflation:293,311`,
  `TestUnattributedDominant:333`, `TestMinSampleZero:346`,
  `TestFormatting:360,377`), plus the one production caller
  `cli/history.py:487` and the re-export at
  `issue_history/__init__.py:80,248`. Option (a) (bypass ATTACH, throwaway
  connection per member) leaves all of these call sites unchanged.
- A third module-private single-project DB builder exists beyond the two
  `_build_history_db(path)` factories already cited:
  `test_issue_history_agent_quality.py:32-102`'s helper set (`_issue`,
  `_stamp_ts`, `_close`, `_link_session`, `_reopen`, `_usage_event`,
  `_retire`) is a write-API-based builder, distinct from the two raw-SQL
  factories. No conftest.py fixture exists for a multi-project/multi-repo
  directory pair or for writing a workspace manifest to `tmp_path` — confirmed
  by full enumeration of `scripts/tests/conftest.py`'s fixtures.
- **`_guard_real_history_db` does not cover `_connect_readonly()`'s own
  connect call**: `scripts/tests/conftest.py:952`'s autouse guard
  monkeypatches `little_loops.session_store.sqlite3.connect` to fail-fast on
  any open of the real `.ll/history.db`, but `history_reader/_base.py`'s
  `_connect_readonly()` (line 60/78) uses its own local `import sqlite3`
  (line 24) and calls `sqlite3.connect` directly — the guard does not
  intercept it. A "source DB untouched" test for this issue's ATTACH path
  must rely on the explicit `hashlib.sha256` checksum (already Implementation
  Step 6), not on this guard.
- **Closest existing structural template for an N=1-vs-N>1 assertion**: no
  test anywhere asserts "N=1 aggregated output equals the pre-aggregation
  single-source output" directly (matches this issue's own Codebase Research
  Finding). The nearest analog is `test_ll_logs.py::TestFleetReview`
  (~lines 6509-6554), which has a 2-source case (`discover_all_projects`
  returning `[proj_a, proj_b]`, asserting both `only-in-a`/`only-in-b` present)
  and a separate 1-source degenerate case (`[proj_a]`, asserting
  `data["loops"] == {}`) — useful as a structural pattern for the
  no-manifest-fallback test, though it doesn't itself assert byte-for-byte
  equivalence.

### Documentation

- `docs/reference/CLI.md:3162-3206` (`#### ll-history quality`) — full flag
  table and metric-definition prose is single-repo-scoped; a `--workspace` flag
  and `AggregationResult` output shape need a new subsection here.
- `docs/guides/HISTORY_SESSION_GUIDE.md:446-486` (§ "Rework and agent-quality
  trends" / "Quality Metric Definitions") — points to `CLI.md` for flag tables;
  needs a workspace-rollup mention.
- `docs/reference/API.md:9419` — already states "Current schema version: 45"
  while `schema.py:25`'s `SCHEMA_VERSION` is higher (49 as of 2026-09-08; a pre-existing, unrelated
  staleness) — whoever documents the schema-skew gate here will be editing a
  paragraph that already has a stale version number in it.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2380,2393` — a separate module-reference table
  documents `analyze_agent_quality(issues, *, db=DEFAULT_DB_PATH,
  min_sample=5)`'s exact current signature and
  `format_agent_quality_{text,json,markdown,yaml}(analysis)`'s. Distinct from
  the three API.md line numbers already cited above (9412 stale-version
  prose, 10421 `queue_store`'s own `SCHEMA_VERSION`, 8209 package-layout
  prose) — this is the literal signature-reference row that goes stale if
  Implementation Step 3 changes `analyze_agent_quality()`'s signature.

## Program Design

### Types

- `class AggregationResult` (frozen dataclass, new module per Step 2). **No
  `totals` field** — see Design Notes § "Why totals are deferred".
  - `per_repo: dict[str, QualityAnalysis]` — keyed by the display label
    `f"{member.repo_path.name} ({member.role})"`
  - `skipped: list[tuple[str, str]]` — (same label, reason string)
  - `to_dict() -> dict[str, Any]` — for the json/yaml formatters, mirroring
    `QualityAnalysis.to_dict()`

### Signatures

- `aggregate_history_dbs(members: list[WorkspaceMember], *, min_sample: int, sensitivity: float, baseline_windows: int, latest_only: bool) -> AggregationResult`
  — `WorkspaceMember` from FEAT-3409; the four kwargs mirror
  `analyze_agent_quality()`'s and are forwarded verbatim per member.
- `analyze_agent_quality(issues: list[IssueInfo], *, db: Path | str = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None, min_sample: int = MIN_SAMPLE_SIZE, sensitivity: float = DEFAULT_SENSITIVITY, baseline_windows: int = DEFAULT_BASELINE_WINDOWS, latest_only: bool = True) -> QualityAnalysis`
  — additive `conn=` kwarg. When given, the function uses it and neither
  opens nor closes a connection; `db` is ignored.
- `analyze_rework(issues: list[IssueInfo], *, db: Path | str = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None, min_sample: int = MIN_SAMPLE_SIZE, follow_up_days: int = FOLLOW_UP_WINDOW_DAYS) -> ReworkAnalysis`
  — same additive `conn=`; `analyze_agent_quality()` forwards its `conn`
  here. `orchestrator_labels()` (`_utils.py:74`) already takes a connection.
  All 31 existing `analyze_agent_quality(` call sites in
  `test_issue_history_agent_quality.py` and the production caller at
  `cli/history.py:535` stay unchanged.

### Call Path

`discover_workspace_members()` [FEAT-3409] -> `aggregate_history_dbs()`, which
for each member: `db_path.exists()` guard -> open
`sqlite3.connect(f"file:{member.db_path}?mode=ro", uri=True)` with
`row_factory = sqlite3.Row` and `PRAGMA query_only = ON` (modeled on
`evolution.py::_open_db()`, no `ensure_db()`) -> `read_schema_version(conn)`
vs `str(SCHEMA_VERSION)` gate -> `find_issues(BRConfig(member.repo_path),
status_filter=all_statuses)` -> `analyze_agent_quality(issues, conn=conn, …)`
-> close. Then `format_agent_quality_{text,markdown,json,yaml}` each gain an
`AggregationResult` rendering (see Step 4/5).

Confirmed current wiring the `--workspace` branch above must insert into
(line numbers refreshed 2026-09-08 after FEAT-3398/3405 landed):
`main_history()`'s `quality` dispatch block (`cli/history.py:508-553`) resolves
a single `db_path` via `resolve_history_db()` at line 516, calls
`analyze_agent_quality(all_issues, db=db_path, min_sample=…, sensitivity=…,
baseline_windows=…, latest_only=…)` unconditionally at line 535, then
dispatches to one of four `format_agent_quality_{json,yaml,markdown,text}`
formatters at lines 544-551 keyed only on `args.format`. The `quality_parser`
(`cli/history.py:266-310`) defines `-f/--format`, `--min-sample`,
`--sensitivity`, `--baseline-windows`, `--all-windows` — no `db`/`--db`
argument exists on this subparser, so `--workspace` would be its first
per-invocation source-selection flag. Nothing in lines 516-533 (the `db_path`
resolve, `find_issues()` call, kwarg defaults) depends on there being exactly
one `db_path`, so the natural insertion point is a conditional after the kwarg
defaults (line 533) and before the unconditional formatter dispatch.

### Decision Rules

- **Schema-skew gate**: a member's `read_schema_version(conn)` value that does
  not equal `str(SCHEMA_VERSION)` (imported from `session_store/schema.py`;
  never a literal) is skipped and reported via `AggregationResult.skipped`,
  never analyzed. No normalization path is implied — skew is always "report
  and skip," never "coerce." Skip reasons are three distinct strings so a user
  can tell them apart: `history.db not found at <path>`, `schema_version
  missing (no meta row)` (one shared string for both `None` conditions —
  `meta` table absent and `schema_version` row absent), and `schema_version
  <N> != installed <M>`. A `sqlite3.Error` raised by **either the open or the
  version read** is a fourth: `could not read read-only: <err>` — the read
  must be covered because a non-SQLite/corrupt file fails only on its first
  query with `sqlite3.DatabaseError` (see Schema-version marker).
- **`--workspace [PATH]` flag shape** (2026-09-08 review): `nargs="?"`,
  `default=None` (absent), `const=""` (bare), so the dispatch tests
  `args.workspace is not None` and then `args.workspace == ""` — no
  `hasattr`/`argparse.SUPPRESS` (this CLI uses `SUPPRESS` only for `help=`,
  never as an absent sentinel). Bare
  `--workspace` → `discover_workspace_members(start=project_root)` (config key
  then ancestor walk); `--workspace PATH` →
  `discover_workspace_members(Path(PATH), start=project_root)`; flag absent →
  today's single-repo path **even if a manifest is discoverable**. Only
  manifest-listed members participate; the invoking repo is included only if
  the manifest lists it. This is deliberately a different shape from
  `cli_args.add_corpus_target_args()`'s `--project/--all` group — that helper
  models "which corpus", not "opt into a declared topology".
- **No ATTACH limit rule needed here**: per-member connections have no
  attached-database cap. The follow-up totals issue owns the >10-member rule.
- **No-manifest fallback**: an empty list (`[]`, never `None`) from FEAT-3409's
  `discover_workspace_members()` falls back to exactly today's single-repo
  `ll-history quality` output, byte-for-byte — no partial-aggregation mode with
  one member. (2026-09-08, from FEAT-3409 third-pass review) `[]` is only the
  *absent-by-discovery* outcome. When the manifest path was declared — an
  explicit `--workspace <path>` or `history.workspace_manifest_path` — and the
  file does not exist, `discover_workspace_members()` raises
  `FileNotFoundError` naming the path; the CLI must surface that as a user
  error (non-zero exit, message on stderr), never catch it into the
  single-repo fallback. `discover_workspace_members()` also takes a
  keyword-only `start: Path | None` seed; the CLI may leave it unset.
- **`role` is consumed, not just carried** (added 2026-09-08 from FEAT-3409
  review): the per-repo breakdown labels each member with `member.role`
  alongside its repo path (e.g. `little-loops (primary)`), and
  `AggregationResult.skipped` entries carry the same label. FEAT-3409 makes
  `role` a required manifest field; without a consumer here it would be dead
  data. `member.db_path` is used as-is — discovery does no existence check, so
  the `db_path.exists()` guard in this issue is the sole missing-DB gate.
- **Read-only enforcement** (resolved 2026-09-08): member connections are
  opened by `aggregate_history_dbs()` itself with a raw
  `file:{path}?mode=ro` URI plus `PRAGMA query_only = ON`, modeled on
  `issue_history/evolution.py::_open_db()` (`exists()` guard, no
  `ensure_db()`, `sqlite3.Error` → skip). **Never** `history_reader/_base.py::
  _connect_readonly()` — it calls `ensure_db()` and would migrate a member
  in place (see Files to Modify). A source-inspection test in the style of
  `test_snapshot_builder_never_uses_the_migrating_open_path` asserts the new
  module never references `ensure_db`, `session_store.connect`,
  `history_reader._base._connect_readonly`, or `immutable=1`. "Untouched"
  means the main file's sha256 is unchanged; `-wal`/`-shm` sidecars **will**
  appear (see Design Notes § WAL sidecars) and are not a violation.
- **Per-member `BRConfig` side effect** (2026-09-08): constructing
  `BRConfig(member.repo_path)` for the issues lookup runs
  `load_env_fallback()` on that member's `.env` (`env_file.py:65`), which
  sets every key not already in `os.environ`, process-wide, first-member-wins
  in manifest order. Nothing downstream in the aggregator reads those keys
  (it never calls `resolve_history_db()`), so this is accepted as-is —
  document it in the new module's docstring rather than mitigating it.

## Implementation Steps

1. Add `conn: sqlite3.Connection | None = None` to `analyze_agent_quality()`
   and `analyze_rework()`. When set, use it (no open/close, `db` ignored) and
   forward it from the former to the latter. Update the `issue_history/__init__.py`
   docstrings and the `docs/reference/API.md:2380,2393` signature rows.
2. New module `scripts/little_loops/issue_history/workspace_quality.py` (new)
   (sits beside `agent_quality.py`; keeps `workspace.py` at the package root
   free of `issue_history` imports) implementing `AggregationResult` and
   `aggregate_history_dbs()`. Per member, in order: `db_path.exists()` guard →
   raw `mode=ro` open (Decision Rules § Read-only enforcement) →
   `read_schema_version(conn)` vs `str(SCHEMA_VERSION)` gate →
   `find_issues(BRConfig(member.repo_path), status_filter=all_statuses)` →
   `analyze_agent_quality(issues, conn=conn, min_sample=…, sensitivity=…,
   baseline_windows=…, latest_only=…)` → close in `finally`. `member.db_path`
   is used as-is (FEAT-3409 already resolved it); do **not** re-resolve via
   `resolve_history_db()` — its env/config chain would redirect a
   root-anchored path (BUG-3181's contract, per `_connect_readonly()`'s
   docstring). Note in the module docstring that the per-member `BRConfig`
   construction runs `load_env_fallback()` on each member's `.env`
   (Decision Rules § Per-member `BRConfig` side effect).
3. Any gate failure appends `(label, reason)` to `AggregationResult.skipped`
   with one of the four reason strings in Decision Rules and continues to the
   next member; nothing raises. The `sqlite3.Error` catch wraps both the
   `sqlite3.connect(...)` call **and** the `read_schema_version(conn)` call
   (a non-SQLite file only fails on the latter). Manifest-level errors from
   `discover_workspace_members()` (`FileNotFoundError` for a declared-but-
   missing path, `yaml.YAMLError`/`KeyError`/`ValueError` for a malformed
   manifest) are **not** caught by the aggregator — the CLI surfaces them as a
   user error (non-zero exit, message on stderr).
4. Extend all four formatters. `format_agent_quality_text/_markdown` gain an
   `AggregationResult` overload that emits one "## <label>" section per
   `per_repo` entry (each rendered by the existing single-analysis body) then
   a "Skipped" section listing `(label, reason)` pairs, or "none". `_json/_yaml`
   serialize `AggregationResult.to_dict()` → `{"per_repo": {label:
   QualityAnalysis.to_dict()}, "skipped": [{"repo": …, "reason": …}]}`. A
   `--workspace` run with a manifest that lists zero analyzable members still
   emits the structure (empty `per_repo`, populated `skipped`) — it does not
   fall back to single-repo.
5. Add `--workspace [PATH]` to `quality_parser` (`cli/history.py:266-310`) per
   the Decision Rules flag shape, and branch after the kwarg defaults
   (line 533): flag absent → existing lines 535-551 untouched; flag present →
   `members = discover_workspace_members(...)`; `members == []` → existing
   single-repo path (the no-manifest fallback); otherwise
   `aggregate_history_dbs(members, …)` → formatter dispatch on `args.format`.
6. Source DBs are asserted unmodified via a `hashlib.sha256` before/after
   checksum test over every member's **main** `history.db` file, following
   `test_feat3304_artifact_dashboard.py::TestSourceDbUntouched`'s template
   exactly — do **not** assert on `-wal`/`-shm` sidecars; they are created
   by any `mode=ro` open of a WAL-mode file and persist after close (Design
   Notes § WAL sidecars). Plus the source-inspection test named in Decision
   Rules § Read-only enforcement. Build member DBs by promoting one of the two existing
   `_build_history_db(path)` factories (`test_feat3304_artifact_dashboard.py:68`,
   `test_feat3323_sse_bridge.py:877`) to `scripts/tests/conftest.py` rather
   than adding a third copy.
7. Skew-gate tests: one member each for (a) file missing, (b) `meta` table
   absent, (c) `schema_version` row absent, (d) `schema_version` one behind
   `SCHEMA_VERSION`, (e) one ahead, (f) a non-SQLite file at `db_path`
   (e.g. `db_path.write_text("not a database")`) — all six appear in
   `skipped` with the matching reason string ((b) and (c) share the
   `schema_version missing (no meta row)` string; (f) gets the
   `could not read read-only:` string), the healthy sibling still appears in
   `per_repo`, and each stale/garbage member's main-file hash is unchanged
   afterward (proves the gate ran before any migrating path could).
8. Add `--workspace` flag tests to `TestHistoryQualitySubcommand`
   (`test_cli_history.py:220`), following the argv-patch + `tmp_path` shape:
   two-member manifest → both labels in output; bare flag with no manifest →
   output byte-identical to the no-flag run; `--workspace <missing path>` →
   non-zero exit with the path on stderr; flag absent with a discoverable
   manifest → single-repo output (opt-in semantics).
9. Add a `("docs/reference/CLI.md", "--workspace", "FEAT-3410")` entry to
   `test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` list once the
   `--workspace` flag's CLI.md doc lands.
10. Update `docs/reference/CLI.md:3205` (`#### ll-history quality`),
    `docs/guides/HISTORY_SESSION_GUIDE.md:446-486`, `docs/reference/API.md`
    (new module row + `conn=` signature rows), and the package-layout prose at
    `docs/reference/API.md:8209` / `CONTRIBUTING.md:299`.
11. ~~Cross-check FEAT-3398/FEAT-3405 citations~~ — **moot** as of 2026-09-08:
    both landed before this issue (`analyze_agent_quality()` already carries
    their `sensitivity`/`baseline_windows`/`latest_only` kwargs and
    `QualityAnalysis.regressions`). Replaced by the forward-all-kwargs rule in
    Step 2.
12. Skew-message wording: the reason strings in Decision Rules deliberately
    diverge from `cli/artifact/dashboard.py::schema_version_warning()` (a
    *warn* semantic rendered into HTML) and `cli/doctor.py::_schema_drift_check()`
    (a structural diff). Ours is a *skip* semantic; do not reuse either
    function or its tests' verbatim strings.
13. **Before Step 1**: file the follow-up issue for union totals (owner of:
    ATTACH mechanics, the `sqlite3` Learning Test Registry entry for the
    multi-ATTACH read-only spike recorded in Verification Notes, the
    `issue_num`/`issue_id` repo discriminator, the >10-member limit rule, and
    the `totals` field) with `blocked_by: [FEAT-3410]`, and link it from this
    issue's Design Notes § "Why totals are deferred" and Resolution. The
    learning test is not exercised by this issue's production code, which is
    why `unproven_mechanism`/`spike_needed` are already cleared here
    (2026-09-08) rather than gated on it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~FEAT-3405 cross-check~~ — moot; FEAT-3405 landed 2026-09-08 (see Step 11).
- Step 12's wording decision is resolved (diverge from both
  `schema_version_warning()` and `_schema_drift_check()`); the
  `templates/dashboard.llat/template.html.j2` rendering is unaffected.
- Update `scripts/little_loops/issue_history/__init__.py` — docstrings for
  `analyze_agent_quality`/`analyze_rework` gain the `conn=` kwarg; add
  `aggregate_history_dbs`/`AggregationResult` to the imports and `__all__`
  (they are public: the CLI imports them).
- Update `docs/reference/API.md:2380,2393` — the signature-reference rows for
  `analyze_agent_quality()` (now with `conn=`) and the four formatters (now
  accepting `QualityAnalysis | AggregationResult`).
- The `conn=` kwarg is additive, so the 31 `analyze_agent_quality(` call sites
  in `test_issue_history_agent_quality.py`, `cli/history.py:535`, and the
  `issue_history/__init__.py` re-export are all unchanged.
- Use an explicit `hashlib.sha256` checksum (Step 6), not
  `conftest.py::_guard_real_history_db`, to assert source DBs are untouched —
  that guard patches `little_loops.session_store.sqlite3.connect` only and
  will not see the new module's own `sqlite3.connect`.

## Impact

- **Priority**: P1 — Valuable multi-repo visibility, but each repo's own report
  already exists as a fallback; this is additive rather than blocking.
- **Effort**: Medium — with totals deferred, every implementation choice
  (connection opener, `conn=` plumbing, flag shape, output shape, skip reasons)
  is now decided above; remaining work is plumbing, formatters, and tests.
- **Risk**: Low — read-only by design; a schema-skew or missing-DB member
  degrades to a skip, not a failure. The one read-only trap (`ensure_db()` via
  `history_reader/_base.py::_connect_readonly()`) is fenced by a
  source-inspection test.
- **Breaking Change**: No — `conn=` is additive on both analysis functions.

## Acceptance Criteria

- One invocation reports across ≥2 repos with a per-repo breakdown, each
  section labeled `<repo> (<role>)`, in all four `--format` modes.
- Source DBs are provably unmodified after a run: sha256 checksum assertion
  in tests over every member's main `history.db` file (WAL `-wal`/`-shm`
  sidecars are expected and excluded — see Design Notes § WAL sidecars), and
  a source-inspection test proving the aggregator never touches a migrating
  opener or `immutable=1`.
- A repo with a mismatched (behind *or* ahead), missing, or unreadable schema
  — including a non-SQLite/corrupt file at `db_path` — is reported by label
  and reason and skipped, not fatal; the healthy members are still analyzed;
  the skewed member's main file is byte-identical afterward.
- `--workspace` absent, or present with no discoverable manifest, produces
  output byte-identical to today's single-repo run; `--workspace <missing
  path>` exits non-zero with the path on stderr.
- Workspace-wide totals are **out of scope**; a follow-up issue is filed and
  linked (Step 14).

## Verification Notes

- **Graph**: provider=`codegraph` freshness=`fresh`
- **Pre-implementation review** — 2026-09-08 — five design gaps folded in
  (see Summary/Design Notes/Decision Rules): (1) the per-member-path call
  into `analyze_agent_quality()` migrates member DBs via `ensure_db()`, so a
  `conn=` kwarg is mandatory; (2) `totals: QualityAnalysis` was unsound and
  any union hits cross-repo `issue_num`/`issue_id` collisions — deferred to a
  follow-up; (3) per-member `find_issues(BRConfig(member.repo_path))` was
  unaddressed; (4) `--workspace` flag shape was undefined; (5)
  `SQLITE_LIMIT_ATTACHED` defaults to 10. Citations refreshed after
  FEAT-3398/FEAT-3405 landed (`SCHEMA_VERSION` is now 49 — literal removed
  from this issue; `analyze_agent_quality()` gained three kwargs;
  `cli/history.py` quality parser 266-310 / dispatch 508-553).
- **Spike (2026-09-08)** — multi-ATTACH read-only mechanism confirmed on this
  interpreter, for the follow-up totals issue: three `file:…?mode=ro` URIs
  attached to a `:memory:` main via `ATTACH DATABASE ? AS repo_N`;
  `PRAGMA database_list` showed all four schemas; per-schema
  `repo_N.meta` reads returned each member's own version; a cross-schema
  `UNION ALL` worked; a view inside an attached schema was queryable via
  `repo_N.<view>`; an `INSERT` into an attached table raised `attempt to
  write a readonly database` (the `mode=ro` URI alone enforces this, before
  `PRAGMA query_only`); sha256 of all three files was unchanged afterward.
  **Confirmed trap:** an unqualified `FROM issue_events` on that connection
  silently returned rows from exactly one schema (SQLite search order:
  temp → main → attached in order), not a union. Note `PRAGMA query_only=ON`
  also blocks `CREATE TEMP TABLE`/`CREATE TEMP VIEW`, so a union-view design
  must create its views in the writable `:memory:` main *before* enabling
  the pragma, or skip the pragma and rely on `mode=ro`.
- **Pre-implementation review (2026-09-08, second pass)** — two empirical
  checks against this interpreter's `sqlite3`, both folded into Decision
  Rules / Steps / ACs above: (1) an `ensure_db()`-created (WAL-mode)
  `history.db` opened via `file:…?mode=ro` + `PRAGMA query_only = ON`
  gained `-wal` and `-shm` sidecars on the first `SELECT` and they persisted
  after `close()`; main-file sha256 unchanged. The original "no sidecars"
  AC was therefore unsatisfiable under this issue's own opener and was
  dropped. (2) `sqlite3.connect("file:<non-sqlite file>?mode=ro", uri=True)`
  succeeds; the first query raises `sqlite3.DatabaseError: file is not a
  database`, which `read_schema_version()` (catches `OperationalError`
  only) does not swallow — the gate's catch was widened to cover the read.
  Also: `size` re-labeled Very Large → Large (the earlier score predates
  the totals deferral; Impact says Medium effort), `unproven_mechanism`/
  `spike_needed` cleared (mechanism moved to the follow-up), and the
  per-member `BRConfig` `load_env_fallback()` side effect documented.
  `verify_verdict: NON_VALID` is stale (set by the since-corrected 47→48
  drift) and `ll-issues check-verify-verdict FEAT-3410` still exits 1 —
  re-run `/ll:verify-issues FEAT-3410 --auto` before automation picks this
  issue up.
- `/ll:verify-issues` — 2026-09-08 — verdict **OUTDATED**. All file:line
  citations, signatures, and mechanism claims checked against current code
  (~20 items spanning `agent_quality.py`, `rework.py`, `_utils.py`,
  `session_store/queries.py`, `session_store/schema.py`, `cli/history.py`,
  `cli_args.py`, `cli/logs.py`, `cli/artifact/dashboard.py`,
  `history_reader/_base.py`, `issue_history/evolution.py`,
  `issue_history/__init__.py`, `test_cli_history.py`, `docs/reference/API.md`)
  held, with one drift: `session_store/schema.py:25`'s `SCHEMA_VERSION` is now
  `48`, not the `47` cited in the Schema-version marker section, the
  Schema-skew gate Decision Rule, and the API.md staleness note — corrected
  in place (the API.md citation's own line number also drifted, `9412` ->
  `9419`, corrected). No other correction needed; `ll-verify-evidence
  --json` reported zero unverifiable spans, no active required decision
  rules exist, `blocked_by: [FEAT-3409]` resolves (FEAT-3409 is open, no
  broken ref), and `## Proposed Solution` is absent so the B6
  proposal-vs-code check does not apply (issue uses Program Design /
  Decision Rules / Implementation Steps instead, matching FEAT-3409's own
  precedent).
- **Graph**: provider=`codegraph` freshness=`fresh`
- `/ll:verify-issues` — 2026-09-09 — verdict **VALID** (superseding the
  stale `NON_VALID` frontmatter left by the since-corrected 47→48 drift).
  `session_store/schema.py:25` `SCHEMA_VERSION` confirmed `49`, matching this
  issue's own Design Notes ("49 as of 2026-09-08") — no literal is cited in
  Decision Rules/Program Design, per this issue's own rule. `blocked_by:
  [FEAT-3409]` resolves and is now `status: done` (satisfied). FEAT-3409's
  landed code confirmed to match every assumption this issue's design
  depends on: `WorkspaceMember` (`workspace.py:31-44`, frozen dataclass,
  fields `repo_path: Path`/`role: str`/`db_path: Path`) and
  `discover_workspace_members(manifest_path: Path | None = None, *, start:
  Path | None = None) -> list[WorkspaceMember]` (`workspace.py:163-165`)
  match this issue's Call Path/Decision Rules verbatim, including the
  `[]`-vs-`FileNotFoundError` declared/discovered split.
  `analyze_agent_quality()` (`agent_quality.py:471-479`) confirmed to still
  lack `conn=` — Implementation Step 1 is accurately scoped as not-yet-done,
  not stale. `cli/history.py` formatter dispatch confirmed at lines 545-551
  (issue cites 544-551, off by one, immaterial). `ll-verify-evidence --json`
  reported zero unverifiable spans; no active required decision rules exist;
  `ll-code --json status` reports `provider=codegraph`, `freshness=fresh`.
  **DEP_ISSUES (minor, informational)**: FEAT-3409 has no `## Blocks`
  section naming FEAT-3410 (MISSING_BACKLINK) — cosmetic only, since the
  dependency is already `done`/satisfied and both issues cross-reference
  each other extensively as parent/sibling in prose.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- `unproven_mechanism: true` is still set and neither `spike_attempted` nor `spike_completed` is stamped, so the Outcome Confidence Cap (ENH-3350) forces the aggregate to 64 regardless of the raw Criteria A-D sum (89). The multi-ATTACH mechanism was already exercised inline (see Verification Notes § Spike) but not yet formalized — Implementation Step 13 (record a `sqlite3` Learning Test Registry entry via `/ll:explore-api`, then clear `unproven_mechanism`) is the prerequisite to lift this cap.
- Criterion A (Complexity) is the next-lowest contributor at 14/25: ~13 distinct files touched (new module, `agent_quality.py`/`rework.py` `conn=` additions, `cli/history.py` wiring, `issue_history/__init__.py` exports, 4 docs files, 3-4 test files) puts Breadth in the 6-15-site band (5/12); per-site depth is mostly Local/Moderate (9/13) since the new aggregator composes several existing calls per member without shared mutable state. Not a blocker, but expect the implementation to touch more files than a typical Medium-effort issue despite Effort being labeled "Medium" in Impact.

## Session Log
- `/ll:confidence-check` - 2026-09-09T02:24:51 - `d79062d3-b1b9-4961-8159-a13a899d5467.jsonl`
- `/ll:verify-issues` - 2026-09-09T02:11:38 - `eaffa681-fbae-45e2-b31c-438286e7946e.jsonl`
- `/ll:confidence-check` - 2026-09-09T01:46:02 - `876d7307-25cb-43ad-ac4c-5e31687d40fd.jsonl`
- `/ll:format-issue` - 2026-09-08T18:31:14 - `d235f946-7b83-4228-9eed-a9bd5517b547.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T18:20:35 - `7bee39e0-dbd1-43e1-ab8d-3353f1d8f05f.jsonl`
- `/ll:verify-issues` - 2026-09-08T18:14:31 - `0c248636-ebaa-42e8-a21d-567126bbbb58.jsonl`
- `/ll:wire-issue` - 2026-09-08T18:06:21 - `1e01fe75-84c0-48d8-81d9-277491fe7648.jsonl`
- `/ll:refine-issue` - 2026-09-08T17:56:30 - `f96712d2-147b-4ff6-a136-9066baf77b51.jsonl`
- `/ll:issue-size-review` - 2026-09-08T06:21:27 - `c53583bd-6c7a-49a7-8685-76b64ad999da.jsonl`
