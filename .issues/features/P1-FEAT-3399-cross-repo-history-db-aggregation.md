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

## Impact

- **Priority**: P1 - Valuable multi-repo visibility, but each repo's own report already exists as a fallback; this is additive rather than blocking.
- **Effort**: Medium - the ATTACH-union mechanism is well-scoped, but workspace-topology discovery (`ll-workspace.yaml`) does not exist yet and is a prerequisite this issue introduces.
- **Risk**: Low - read-only by design; a schema-skew or missing-DB member degrades to a skip, not a failure.
- **Breaking Change**: No

## Acceptance Criteria

- One invocation reports across ≥2 repos, with per-repo breakdown and workspace totals.
- Source DBs are provably unmodified after a run (checksum assertion in tests).
- A repo with a mismatched or missing schema is reported and skipped, not fatal.

## Status

**Open** | Created: 2026-09-07 | Priority: P1


## Session Log
- `/ll:refine-issue` - 2026-09-08T00:56:23 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
