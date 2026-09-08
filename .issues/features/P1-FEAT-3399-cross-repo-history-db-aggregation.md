---
id: FEAT-3399
title: Cross-repo history.db aggregation (read-only workspace rollup)
type: FEAT
priority: P1
status: open
discovered_date: '2026-09-07'
labels:
- path-a
- history-db
- multi-repo
learning_tests_required:
- yaml
- sqlite3
confidence_score: 70
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

## Summary

Aggregate multiple projects' `history.db` files into a single read-only rollup so one invocation can report agent quality across an entire workspace, not one repo at a time.

## Current Behavior

`history_reader`/`session_store` (`little_loops/history_reader/`, `little_loops/session_store/`) read a single repo's `.ll/history.db` via `_connect_readonly()` against `DEFAULT_DB_PATH`. Every quality question — including the agent-quality report from `analyze_agent_quality()` — is scoped to whichever repo the invocation runs in; there is no way to ask the question across a workspace of several repos in one invocation.

## Expected Behavior

One invocation attaches every member repo's `history.db` read-only via SQLite `ATTACH` and unions the queries, producing a per-repo breakdown plus workspace totals. Source databases are never written to. A member with a mismatched or missing schema version is reported and skipped rather than silently unioned or treated as fatal. With no workspace manifest present, behavior falls back byte-for-byte to today's single-repo output.

## Use Case

**Who**: A developer running several agent-heavy little-loops projects at once.

**Context**: They want to know whether agent quality moved across their whole set of projects, not check each repo's report one at a time.

**Goal**: Run one command from a workspace root and see quality broken down per repo plus rolled up totals.

**Outcome**: A single read-only rollup report, with any repo whose schema doesn't match clearly called out and skipped rather than corrupting the totals.

## Motivation

`history.db` is currently single-repo, single-user and local. That is the right write-path design — events are emitted by per-repo sessions and hooks, and the write path should not cross repo boundaries — but it means every quality question can only be asked one project at a time. A developer running several agent-heavy projects has no way to see whether quality moved across all of them, which is precisely the view that makes a regression legible.

Solving it locally and read-only is also the prerequisite shape any aggregation layer above this would reuse.

## Design notes

The mechanism is SQLite `ATTACH`: attach each member repo's database read-only and union the queries. No materialized cross-repo database, no migration of the source schemas, no second registry — a materialized rollup is a premature optimization at this size, and the ATTACH-union approach respects graceful degradation for free (a missing database means a skipped member, not a failed run).

Repo discovery should reuse the existing workspace topology rather than introducing a second registry. The workspace manifest (`ll-workspace.yaml`) names member repos by path with a role apiece; this feature is a consumer of that membership list. Where the topology mechanism is not yet built, the manifest as it stands is the discovery source, and its absence must fall back cleanly to single-repo behavior — byte-for-byte today's output.

Schema-version skew is the interesting failure. Member databases will not all be at the same migration level, and silently unioning across a schema boundary produces numbers that look fine and are wrong. Skew must be either normalized explicitly or reported and the member skipped — never silently mismatched.

## Constraints

- **Read-only**: source databases are never written, migrated, or locked for writes.
- Schema-version skew across repos must be handled explicitly — either normalized or reported, never silently mismatched.
- Repo discovery reuses the existing workspace/multi-repo topology rather than introducing a second registry.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator and codebase-analyzer agents confirmed the workspace-aggregation concepts this issue proposes are entirely new (no existing manifest, no existing multi-repo topology) and identified the one existing ATTACH-based precedent to build from:

### Files to Modify
- New module (path not yet chosen) implementing `discover_workspace_members()` / `aggregate_history_dbs()` — no existing file to modify since neither symbol exists anywhere in the codebase today (confirmed 0 hits repo-wide for `WorkspaceMember`, `AggregationResult`, `discover_workspace_members`, `aggregate_history_dbs`).
- `scripts/little_loops/history_reader/_base.py` — `_connect_readonly()` (line 60) is the read-only connection primitive named in the issue's own Call Path. It takes `db_path: Path` as a required positional param (already supports a non-default path) but calls `ensure_db(db_path)` first, which can create/migrate the file — relevant to the "never written, migrated" constraint if reused as-is for attaching member DBs.
- `scripts/little_loops/issue_history/agent_quality.py` — `analyze_agent_quality()` takes a **path**, not a connection: it opens and closes its own `_connect_readonly()` connection internally, and every internal query uses unqualified table names (`issue_events`, `usage_events`, etc.). It cannot currently be pointed at an already-open connection with an ATTACHed schema without either (a) opening one throwaway connection per member exactly as today, or (b) a signature change to accept an open connection/schema-qualifier and schema-qualify every internal SQL string.
- `scripts/little_loops/cli/history.py` — `ll-history quality` subcommand is the current single-repo entry point; the issue's byte-for-byte no-manifest fallback must reproduce this path unchanged.

_Wiring pass added by `/ll:wire-issue`:_
- `resolve_history_db()`'s `root=` parameter (`scripts/little_loops/session_store/db.py:121`, added per BUG-3181) already exists specifically to anchor db-path resolution at a caller-supplied project root — this is the exact per-member resolution primitive `aggregate_history_dbs()` should call once per `WorkspaceMember.repo_path`, rather than reinventing path resolution.
- `analyze_agent_quality()`'s formatter siblings `format_agent_quality_text`/`_json`/`_yaml` (`agent_quality.py:588,670,675`) all take `analysis: QualityAnalysis` positionally — only `format_agent_quality_markdown()` is named in this issue's Call Path for `AggregationResult` extension. A `--workspace --format json/yaml/text` combination has no specified output shape yet.
- **Cross-issue sequencing**: FEAT-3398 (P0, open) already names `analyze_agent_quality()` (line 462) and `format_agent_quality_markdown()` (line 619) as functions its own `detect_quality_regressions()`/`attribute_change()` will consume, citing the current signatures. If this issue changes those signatures first, FEAT-3398's own Integration Map citations need re-verification.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- Importers of the `history_reader/_base.py` `_connect_readonly()` variant (16 files, beyond `agent_quality.py` already known): `summary_dag.py`, `usage.py`, `runs.py`, `search.py`, `context.py`, `formatting.py`, `events.py`, `subagents.py`, `harness.py`, `hooks.py`, `sessions.py`, `digest.py`, `history_reader/__init__.py` (re-export), `issue_history/collisions.py`, `issue_history/rework.py` — all in `scripts/little_loops/`. Any change to this variant's contract (e.g. to support ATTACHed schemas) ripples through every one of these.
- The `_open_db` variant (issue's "third variant", `evolution.py:30-47`/`codegraph.py:81-91`) has its own two callers, self-contained within each file — not affected unless this issue picks that variant to model.
- `docs/reference/API.md:10421` — documents `queue_store`'s **own independent copy** of `SCHEMA_VERSION`/`_MIGRATIONS` ("copied rather than shared" from `session_store`) — a fourth, unrelated `SCHEMA_VERSION` namesake to disambiguate from when implementing the schema-skew gate.
- `docs/reference/API.md:8209` and `CONTRIBUTING.md:299` — both document the `history_reader/_base.py` package-layout (`_connect_readonly`/`_row_to_dataclass`/`_stale_cutoff`) in prose/diagram form; these would need a mention of the new aggregation module once its location is chosen.

### Naming collision (read carefully)
- **Two distinct functions are both named `_connect_readonly()`** and are NOT the same code: `scripts/little_loops/history_reader/_base.py:60` (calls `ensure_db()` first, sets `PRAGMA query_only = ON`, returns `None` on any error, never raises) vs. `scripts/little_loops/session_store/queries.py:189` (no `ensure_db()`, no pragma, **raises** on failure — returns `sqlite3.Connection`, not `Connection | None`). `analyze_agent_quality()`'s call path uses the `history_reader/_base.py` variant. `build_snapshot_db()` (below) uses the `session_store/queries.py` variant. A third variant (`issue_history/evolution.py:30-47`, `codequery/codegraph.py:81-91`) deliberately skips `ensure_db()` "to avoid failing on a database created by the test harness." Pick the variant deliberately; do not assume there is only one.

### Existing ATTACH precedent — opposite direction from this issue's proposal
- `scripts/little_loops/session_store/queries.py::build_snapshot_db()` (lines ~246-301) is the only `ATTACH DATABASE` call in the codebase: it opens **one** source DB read-only (`main`), then `ATTACH DATABASE ? AS snap` attaches a **writable scratch** DB onto that same connection, reads `read_schema_version(conn)` *before* the ATTACH (version-read-before-touch), and `DETACH`es in a `finally`. This issue's proposed shape — several **read-only source** DBs ATTACHed onto one connection for a union query — is the inverse direction and has no direct precedent; only the ATTACH/DETACH mechanics themselves are established.

### Schema-version marker (for the skew check)
- `history.db` carries an explicit version marker in a `meta` key/value table (`key = 'schema_version'`), **not** `PRAGMA user_version` (confirmed: zero `PRAGMA user_version` calls anywhere in `scripts/`). Read via `read_schema_version(conn)` (`session_store/queries.py`) — returns `str | None`, swallows only `sqlite3.OperationalError` (missing table). `SCHEMA_VERSION` (`session_store/schema.py`, currently `47`) is the installed code's target version. A mismatch between a member's `read_schema_version()` value and the aggregator's own `SCHEMA_VERSION` is the exact skew signal this issue's "reported and skipped" requirement needs.

### Conventions in Force
- **Manifest-absent graceful degradation** is an established pattern: `decisions.py::load_decisions()` and `design_tokens.py::_resolve_token_root()` both do an explicit `Path.exists()`/`is_dir()` check, document the fallback target in the docstring, and have a dedicated test class (`TestDecisionsGracefulDegradation`, `TestLoadDesignTokensFallbacks`) — follow this shape for the no-`ll-workspace.yaml` fallback.
- **Skip-and-report** has three close-but-not-identical precedents, none an exact match for `AggregationResult.skipped: list[tuple[str,str]]`: `SyncResult.failed`/`skipped` (`sync.py:41-51`), `ValidationResult`'s five `list[tuple[str,str]]` fields (`dependency_mapper/models.py:66-71`), `StatusTransition.failures`/`cascaded` (`cli/issues/set_status.py:28-44`). The three-way `per_repo / totals / skipped-with-reason` combination this issue's `AggregationResult` proposes has each element precedented separately but not combined before.
- **No precedent for merging multiple instances of the same analysis dataclass** exists anywhere (searched for `merge`/`combine`/`union`/`__add__` repo-wide) — every existing `*Analysis` dataclass (`QualityAnalysis`, `ReworkAnalysis`, `CostReport`) is built once from one connection's results. `AggregationResult.totals: QualityAnalysis` combining N per-repo `QualityAnalysis` instances would be the first instance of this pattern in the codebase — there is no `merge()`/reducer to reuse.
- `ll-workspace.yaml` / any workspace-membership manifest, `WorkspaceMember`, `discover_workspace_members`, `aggregate_history_dbs` — zero hits anywhere outside this issue's own file. This issue is the first to introduce workspace-topology discovery; there is nothing to reuse from an existing "topology" concept (83 unrelated `topology` hits elsewhere are all FSM diagram-layout code).

### Tests
- `scripts/tests/test_feat3304_artifact_dashboard.py::TestSourceDbUntouched` (lines 443-458) is a direct existing precedent for this issue's "Source DBs are provably unmodified after a run (checksum assertion in tests)" AC: `hashlib.sha256(db.read_bytes()).hexdigest()` before/after, plus a companion `test_snapshot_builder_never_uses_the_migrating_open_path` that asserts (by source inspection) the export path never calls the migrating `connect()` and does use `mode=ro` — the same class of assertion this issue's read-only guarantee needs.
- `scripts/tests/test_issue_history_agent_quality.py`, `scripts/tests/test_session_store_queries.py`, `scripts/tests/test_session_store_schema.py` — existing coverage for `analyze_agent_quality`/`_connect_readonly`/`read_schema_version`/`ATTACH` to extend or model new tests after.

_Wiring pass added by `/ll:wire-issue`:_
- **No dedicated test file exists for `history_reader/_base.py` itself** — `_connect_readonly()` coverage is entirely indirect, through the 12+ sibling query-module test files that each test the missing-DB/degrade-to-empty branch via their own public function (e.g. `test_history_reader_usage.py:78`, `test_history_reader_runs.py:60,138`, `test_history_reader_search.py:29-49`, `test_history_reader_sessions.py:191-603`, `test_history_reader_events.py:521-626`). No existing test exercises this variant directly.
- The `session_store/queries.py:189` variant's only direct-name tests: `test_feat3304_artifact_dashboard.py:451-458` (source-inspection) and `test_feat3323_sse_bridge.py:1157-1162` (imports and calls it directly) — the latter is coverage for this variant not previously in the issue's known-tests list.
- **Manifest-absent graceful-degradation template classes, confirmed exact code**: `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) and `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`) — one test per short-circuit branch, `tmp_path`-based (no manifest created), direct `== []`/`is None` return-value assertion. Model the no-`ll-workspace.yaml` fallback test class after these.
- **ATTACH/DETACH test precedent is NOT in `test_session_store_queries.py`** (confirmed zero `ATTACH` hits there) — it lives in `test_feat3304_artifact_dashboard.py:734-760` `TestBuildSnapshotDb`, which tests `build_snapshot_db()` behaviorally (return value, error paths) rather than inspecting the ATTACH SQL directly; no existing test exercises multiple simultaneous ATTACHes.
- **Byte-for-byte-identical assertion precedent** for the no-manifest fallback AC: `test_worker_pool.py:2267-2294` `test_update_branch_base_no_epic_branch_uses_base_branch` (run both branches, assert identical captured argv) and the simpler `test_issues_cli.py:83-103` `test_next_id_count_one_matches_default` (exact string-equality). Model the "manifest absent falls back to today's output" test on these, not a diff/checksum approach.
- `TestHistoryQualitySubcommand` (`test_cli_history.py:220-271`) — existing `ll-history quality` coverage; no `--workspace` flag exists today, so a new flag/test would be a fifth class member following the same argv-patch + `tmp_path` fixture shape as the existing four tests.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:712` (§ "History DB: Producer→Consumer Flow") states outright: *".ll/history.db is the per-project event history store"* — explicit single-repo framing that needs updating; its adjoining Read Path flowchart (`:735-744`) has no aggregation node.
- `docs/reference/API.md:92` (`little_loops.session_store` module-table entry) and `:8207` (`little_loops.history_reader` package docstring) both carry the same "per-project" single-repo phrasing, in separate locations from the ARCHITECTURE.md one.
- `docs/reference/CLI.md:3162-3206` (`#### ll-history quality`) — full flag table and metric-definition prose is single-repo-scoped; a `--workspace` flag and `AggregationResult` output shape need a new subsection here.
- `docs/guides/HISTORY_SESSION_GUIDE.md:446-486` (§ "Rework and agent-quality trends" / "Quality Metric Definitions") — points to `CLI.md` for flag tables; needs a workspace-rollup mention.
- `docs/reference/API.md:9412` — already states *"Current schema version: 45"* while `schema.py:25` has `SCHEMA_VERSION = 47` (a pre-existing, unrelated staleness) — whoever documents the schema-skew gate here will be editing a paragraph that already has a stale version number in it.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:2117-2146` — the `history` object is documented as *"Single namespace owner for all history.db consumer tunables"* and already has a `db_path` property (`:2143-2146`) with the same `LL_HISTORY_DB`-env-var-precedence shape `resolve_history_db()` implements. If a configurable manifest path is wanted, `history.workspace_manifest_path` alongside `history.db_path` is the sibling location to register it in — the issue's own `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml"))` signature is currently a bare function default, not routed through this config/env-var chain.
- `config-schema.json:704-728` — the `decisions` object's registration shape (top-level object, `enabled`/`log_path`/`auto_generate` properties with inline-documented defaults) is the closest existing precedent for registering a new top-level `workspace` config section, if one is introduced instead of nesting under `history`.

## Program Design

### Types

- `WorkspaceMember`: `repo_path: Path`, `role: str`, `db_path: Path`
- `AggregationResult`: `per_repo: dict[str, QualityAnalysis]`, `totals: QualityAnalysis`, `skipped: list[tuple[str, str]]` (repo, reason)

### Signatures

- `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml")) -> list[WorkspaceMember]`
- `aggregate_history_dbs(members: list[WorkspaceMember]) -> AggregationResult`

### Call Path

`discover_workspace_members()` -> `aggregate_history_dbs()` (opens one connection, `ATTACH DATABASE ? AS repo_N` per member via `_connect_readonly()`'s read-only URI pattern from `little_loops/history_reader/_base.py`) -> `analyze_agent_quality()` per attached schema -> `format_agent_quality_markdown()` (extended to render `AggregationResult`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Analyzer and pattern-finder agents pinned down the schema-version marker and the one existing ATTACH precedent these rules are built on:

### Decision Rules

- **Schema-skew gate**: a member's `read_schema_version(conn)` value that does not equal the aggregator's own `SCHEMA_VERSION` (`session_store/schema.py`, currently 47) is skipped and reported via `AggregationResult.skipped`, never unioned. No normalization path is implied — skew is always "report and skip," never "coerce."
- **No-manifest fallback**: absence of `ll-workspace.yaml` at the discovery path falls back to exactly today's single-repo `ll-history quality` output, byte-for-byte — no partial-aggregation mode with one member.
- **Read-only enforcement**: member connections must go through a `mode=ro`-URI-based `_connect_readonly()` variant, never the migrating `session_store.connect()`/`ensure_db()` path in a way that could write — see the three-variant naming collision above; which of the three existing variants to model this on is an open implementation call, since none of them is itself the ATTACH-multiple-read-only-sources shape this issue needs.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. `discover_workspace_members()` parses `ll-workspace.yaml` (new format; no existing parser) into `WorkspaceMember` rows, following the manifest-absent graceful-degradation shape of `decisions.py::load_decisions()`/`design_tokens.py::_resolve_token_root()` for the "no manifest → single-repo fallback" branch; verified by a graceful-degradation test class per that convention.
2. `aggregate_history_dbs()` opens one connection and `ATTACH DATABASE ? AS repo_N` per member — the ATTACH/DETACH bracketing follows `session_store/queries.py::build_snapshot_db()`'s existing precedent, but in the reverse direction (N read-only sources onto one connection, not one read-only source plus a writable scratch); `read_schema_version(conn)` is read per member before any query runs, matching that function's version-read-before-touch ordering.
3. A member whose `read_schema_version()` disagrees with the aggregator's own `SCHEMA_VERSION` is appended to `AggregationResult.skipped` and excluded from `totals`, never raising.
4. `analyze_agent_quality()` runs per attached schema — since it currently opens/closes its own connection from a path and issues unqualified SQL, either call it once per member's own throwaway `_connect_readonly()` connection (bypassing ATTACH for this call), or give it a schema-qualifier/open-connection parameter so its existing unqualified queries can run against `repo_N.*` tables; this is an open implementation call research could not resolve further (see Integration Map → Files to Modify).
5. `format_agent_quality_markdown()` is extended to render `AggregationResult`'s per-repo breakdown plus totals; since no existing dataclass-merge precedent exists in this codebase, the `totals: QualityAnalysis` combination is new code, not an adaptation.
6. Source DBs are asserted unmodified via a `hashlib.sha256` before/after checksum test, following `test_feat3304_artifact_dashboard.py::TestSourceDbUntouched`'s existing template.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Model the no-manifest graceful-degradation test on `TestDecisionsGracefulDegradation` (`test_decisions.py:639-651`) / `TestLoadDesignTokensFallbacks` (`test_design_tokens.py:227-258`) exactly, and the byte-for-byte fallback assertion on `test_worker_pool.py:2267-2294` / `test_issues_cli.py:83-103`'s exact-equality shape — not a diff/checksum approach.
- Model the multi-ATTACH test on `test_feat3304_artifact_dashboard.py:734-760::TestBuildSnapshotDb`'s behavioral-assertion shape, extended for N simultaneous read-only ATTACHes (no existing test covers more than one ATTACH at a time).
- Reuse `resolve_history_db()`'s `root=` parameter (`session_store/db.py:121`) for per-member path resolution in `aggregate_history_dbs()` rather than reimplementing path discovery.
- Decide and implement the config registration for a configurable `ll-workspace.yaml` path (if wanted): `history.workspace_manifest_path` alongside `history.db_path` in `config-schema.json:2117-2146`, following that property's existing `LL_HISTORY_DB`-precedence shape.
- Update `docs/ARCHITECTURE.md:712` (Producer→Consumer Flow) and `docs/reference/API.md:92,8207` to describe the workspace rollup instead of purely single-repo framing; add a `--workspace` subsection to `docs/reference/CLI.md:3162-3206`.
- Add a `--workspace` flag test to `TestHistoryQualitySubcommand` (`test_cli_history.py:220-271`), following the same argv-patch + `tmp_path` shape as its four existing tests.
- Cross-check FEAT-3398's Integration Map citations of `analyze_agent_quality()`/`format_agent_quality_markdown()` signatures if this issue lands first and changes them.

## Impact

- **Priority**: P1 - Valuable multi-repo visibility, but each repo's own report already exists as a fallback; this is additive rather than blocking.
- **Effort**: Medium - the ATTACH-union mechanism is well-scoped, but workspace-topology discovery (`ll-workspace.yaml`) does not exist yet and is a prerequisite this issue introduces.
- **Risk**: Low - read-only by design; a schema-skew or missing-DB member degrades to a skip, not a failure.
- **Breaking Change**: No

## Acceptance Criteria

- One invocation reports across ≥2 repos, with per-repo breakdown and workspace totals.
- Source DBs are provably unmodified after a run (checksum assertion in tests).
- A repo with a mismatched or missing schema is reported and skipped, not fatal.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-07_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Architecture compliance (10/20): the only existing `ATTACH` precedent (`build_snapshot_db()`) attaches one writable scratch DB onto a single read-only source — the opposite direction from this issue's several-read-only-sources-onto-one-connection shape. There is no direct precedent, and the codebase has three near-identical `_connect_readonly()` variants; the default `history_reader/_base.py` one calls `ensure_db()` first, which can create/migrate the file — reusing it as-is would risk violating the issue's own "never written, migrated" constraint. Pick the connection primitive deliberately.
- Issue well-specified (10/20): three implementation choices remain genuinely open — where the new aggregation module lives, whether `analyze_agent_quality()` gets a schema-qualifier/open-connection parameter or is called once per member via its own throwaway connection, and what `--workspace --format json/yaml/text` should output (no shape specified yet).
- No duplicate implementations (15/20, base 20 with a −5 learning-test modifier): the `sqlite3` learning-test target is `stale` (last proven 2026-07-20) — verify ATTACH/read-only-URI behavior still holds before relying on it.
- Sequencing: FEAT-3398 (P0, open) already cites `analyze_agent_quality()`/`format_agent_quality_markdown()` signatures in its own Integration Map; if this issue lands first and changes either signature, FEAT-3398 needs its citations re-verified.

### Outcome Risk Factors
- Change surface (10/25): blast radius is contingent on which open implementation call above is resolved — the schema-qualifier approach would ripple through the 16+ files importing the `history_reader` `_connect_readonly()` family, while the per-member-throwaway-connection approach stays isolated. Not yet locked in.
- Ambiguity (10/25): the same open design decisions (module location, connection variant, per-schema query approach) require judgment calls during implementation; no `unapplied_decision` gap is flagged, but real design latitude remains.
- Complexity (10/25): moderate breadth (~7 integration sites spanning a new module, CLI flag, config, and docs) combined with genuinely novel logic — `AggregationResult.totals` merging N `QualityAnalysis` instances has no precedent anywhere in the codebase (searched for `merge`/`combine`/`union`/`__add__`, zero hits).

## Status

**Open** | Created: 2026-09-07 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-08T02:13:32 - `8a6cd350-cac1-4f1e-a42b-0221ef8ee56a.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:10:50 - `8a6cd350-cac1-4f1e-a42b-0221ef8ee56a.jsonl`
- `/ll:wire-issue` - 2026-09-08T02:00:49 - `2d920f5a-2d4d-4a14-9303-a5bfb4bae86a.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:56:23 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
