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
- All 8 schema-qualification call sites from FEAT-3410's Integration Map
  (`agent_quality.py:229,245,259,273,301-304,419-422`,
  `rework.py:136-137,150-151`, `_utils.py:81-82`, plus
  `read_schema_version()`) are schema-qualified — an unqualified query
  against the attached connection is a bug per the confirmed SQLite
  search-order trap.
- A workspace with more than 10 members raises a clear, actionable error
  instead of a silent `SQLITE_LIMIT_ATTACHED` truncation.
- The `sqlite3` Learning Test Registry entry for this multi-ATTACH spike is
  formalized via `/ll:explore-api` before implementation lands.

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


## Session Log
- `/ll:format-issue` - 2026-09-09T02:56:59 - `b1423fb6-b93c-443b-8f26-be96a57e6e5f.jsonl`
