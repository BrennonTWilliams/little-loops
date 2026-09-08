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

## Program Design

### Types

- `WorkspaceMember`: `repo_path: Path`, `role: str`, `db_path: Path`
- `AggregationResult`: `per_repo: dict[str, QualityAnalysis]`, `totals: QualityAnalysis`, `skipped: list[tuple[str, str]]` (repo, reason)

### Signatures

- `discover_workspace_members(manifest_path: Path = Path("ll-workspace.yaml")) -> list[WorkspaceMember]`
- `aggregate_history_dbs(members: list[WorkspaceMember]) -> AggregationResult`

### Call Path

`discover_workspace_members()` -> `aggregate_history_dbs()` (opens one connection, `ATTACH DATABASE ? AS repo_N` per member via `_connect_readonly()`'s read-only URI pattern from `little_loops/history_reader/_base.py`) -> `analyze_agent_quality()` per attached schema -> `format_agent_quality_markdown()` (extended to render `AggregationResult`)

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
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
