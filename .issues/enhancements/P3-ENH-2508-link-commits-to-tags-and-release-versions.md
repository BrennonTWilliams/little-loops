---
id: ENH-2508
title: Link commits to git tags and release versions in commit_events
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
  - release
  - widening
  - captured
---

# ENH-2508: Link commits to git tags and release versions in commit_events

## Summary

`commit_events` (ENH-2458, schema v17) carries `commit_sha`, branch,
author, message, touched-files — but no tag or release-version linkage.
So `ll-session search` can't answer "what was touched by v0.4.2" or
"which commits landed in v0.5.0." Add two nullable columns:
`tag TEXT` and `release_version TEXT`. `_backfill_commit_events` reads
`git tag --points-at <sha>` for each existing row and populates both;
live commits read `git describe --tags --exact-match <sha>` at
`post-commit` time. Lets the release notes generator, regression
investigator, and `ll-history` consumer all ask release-scoped
questions.

## Motivation

- **The release-axis is currently invisible in the DB.** ENH-2458 made
  commits first-class; the tag/release join was a deliberate deferral.
  Without it, "show me everything in v0.4.2" requires re-walking git
  history at query time.
- **Trivial additive column.** Two nullable TEXT columns + a one-line
  backfill. `_backfill_commit_events` already iterates every commit; the
  tag lookup is `subprocess.run(["git", "tag", "--points-at", sha])`,
  one call per row.
- **Widens ENH-2458 rather than spawning a new table.** Adding
  nullable columns to an existing table is cheaper than a join table
  (`commit_tags(commit_sha, tag)`) and aligns with the EPIC-1707
  "additive only" contract.
- **Lets release scoping become a routine query.** `ll-history`,
  `ll-session search --fts "v0.4.2"`, `ll-issues list --since-tag
  v0.4.2` (optional follow-on CLI) all become possible.

## Current Behavior

- `commit_events` (`session_store.py:506-519`) has columns `(ts,
  commit_sha, message, author, branch, issue_id, files_json, head_sha,
  repo_path)` — no `tag`, no `release_version`.
- A `git describe` / `git tag` lookup at query time requires shelling
  out per query, which is expensive for the "list all commits in v0.4.2"
  workflow.
- `ll-session search --fts "v0.4.2"` only matches if the string appears
  in `message` or `files_json` — usually it doesn't.

## Expected Behavior

- `commit_events` gains two nullable columns: `tag TEXT` and
  `release_version TEXT` (where `release_version` is the tag stripped
  of any leading `v` — `0.4.2`, not `v0.4.2` — for clean numeric
  comparison).
- `_backfill_commit_events` populates both columns for every existing
  row using `git tag --points-at <sha>` (one shell-out per commit).
- Live `record_commit_event` (post-commit) computes both columns before
  the INSERT.
- A commit can carry multiple tags (e.g., both `v0.4.2` and `stable`).
  Decision needed: comma-separated list in `tag`, or a join table.
  Default to **comma-separated list** (single column, no join, lower
  schema cost) — see "Decision needed" below.
- `ll-session search --fts "v0.4.2" --kind commit` matches.

## Proposed Solution

### Schema migration (v19)

```sql
ALTER TABLE commit_events ADD COLUMN tag TEXT;             -- comma-separated list, NULL if untagged
ALTER TABLE commit_events ADD COLUMN release_version TEXT;  -- tag minus leading 'v', NULL if not a release tag
CREATE INDEX IF NOT EXISTS idx_commit_events_tag ON commit_events(tag);
CREATE INDEX IF NOT EXISTS idx_commit_events_release_version ON commit_events(release_version);
```

Bump `SCHEMA_VERSION = 18` → `19` (or roll into the same migration as
the items landing alongside it; coordinate with ENH-2495/2497/2504
which all target v19 — see "Coordination note" below). Nullable so
pre-migration rows read back with `tag=NULL` (no data fix required).

### Producer wiring

- Extend `record_commit_event()` at `session_store.py:1041-1091` to:
  - Call `git tag --points-at <sha>` and store the result
    (comma-joined) in `tag`.
  - Strip leading `v` from any tag matching `v\d+\.\d+\.\d+` pattern
    and store in `release_version`.
- Extend `_backfill_commit_events()` at `session_store.py:1094-1188` to
  do the same for every historical commit.

### Read API

- `history_reader.commits_by_tag(tag, since=None)` — list of commits
  with `tag LIKE '%<tag>%'`.
- `history_reader.commits_in_release(version, since=None)` —
  `release_version = ?`.
- `history_reader.tag_summary()` — list of `(tag, commit_count,
  first_ts, last_ts)` rollups.

### CLI surface

- `ll-session recent --kind commit --tag v0.4.2` (optional flag).
- `ll-history issue <ID> --tag v0.4.2` (optional follow-on — list the
  issue's commits that landed in a release).

### Decision needed

**Multi-tag representation**: comma-separated list (cheaper, matches the
EPIC-1707 "additive only" preference) vs. a join table
`commit_tags(commit_sha, tag)` (cleaner queries, more schema cost).
Default to comma-separated; flag here for implementer confirmation.

### Coordination note

Multiple children (ENH-2495 session_lifecycle_events, ENH-2497
agent_type column, this issue, ENH-2506 hook_events, etc.) all target
`SCHEMA_VERSION = 19`. Either land them as a single migration batch
(one commit, one version bump) or sequence them (v19, v20, v21...).
The first pattern matches the v15-v18 batch landed 2026-07-03
(see commit `98ae796a docs(observability): cover EPIC-2457 v15-v18
schema migrations`). Default to **batched**.

## Acceptance Criteria

- Schema migration lands; `tag` and `release_version` columns exist on
  `commit_events`; `SCHEMA_VERSION` bumped.
- Existing pre-migration commits read back with `tag=NULL` (no data
  fix required).
- `_backfill_commit_events` populates `tag` for every historical commit
  that has at least one tag pointing at it.
- A live `git commit` followed by `git tag v0.4.2` produces a row with
  `tag="v0.4.2"`, `release_version="0.4.2"` (nullable).
- `ll-session search --fts "v0.4.2" --kind commit` matches tagged rows.
- Writes are best-effort: a missing `git` binary or empty repo writes
  `tag=NULL`, never raises.
- Tests cover: tagged commit, untagged commit, multi-tag commit,
  pre-migration NULL handling, DB-absent graceful degradation.

## Sources

- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list
- ENH-2458 — sibling `commit_events` table work (this issue widens it)
- `scripts/little_loops/git_utils.py` — the `get_head_sha()` /
  `get_current_branch()` helpers; add `get_tags_at(sha)` here as the
  shared substrate
- `scripts/little_loops/hooks/post_commit.py` — live producer
- `scripts/little_loops/cli/manage_release.py` — release tooling that
  would consume this

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `git_utils` modules |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`