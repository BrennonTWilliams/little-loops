---
id: 3399
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

## Acceptance Criteria

- One invocation reports across ≥2 repos, with per-repo breakdown and workspace totals.
- Source DBs are provably unmodified after a run (checksum assertion in tests).
- A repo with a mismatched or missing schema is reported and skipped, not fatal.
