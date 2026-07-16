---
id: ENH-2508
title: Link commits to git tags and release versions in commit_events
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
decision_needed: true
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

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py:333+` — append new v21 migration
  entry to `_MIGRATIONS` (slot after the v20 ENH-2461 entry at lines
  709–733); bump `SCHEMA_VERSION = 20` → `21` at line 207
- `scripts/little_loops/session_store.py:1222-1272` — extend
  `record_commit_event()` with `tag` / `release_version` kwargs; include
  in INSERT column list; append to FTS5 `_index()` content at line 1263
- `scripts/little_loops/session_store.py:1275-1335+` — extend
  `_backfill_commit_events()` to issue `git tag --points-at <sha>` per
  commit and UPDATE the new columns after `INSERT OR IGNORE`
- `scripts/little_loops/history_reader.py:124-135` — extend `CommitEvent`
  dataclass with `tag: str | None = None`, `release_version: str | None = None`
- `scripts/little_loops/history_reader.py:651-686` — extend
  `recent_commit_events()` with optional `tag` / `release_version`
  filter params; add three new functions `commits_by_tag()`,
  `commits_in_release()`, `tag_summary()` (modeled on
  `aggregate_usage()` at lines 596-648)
- `scripts/little_loops/hooks/post_commit.py:44-82` — extend
  `record_head_commit()` with `_git(root, "tag", "--points-at", sha)`
  call before the INSERT
- `scripts/little_loops/cli/session.py:~449+` — add `--tag v0.4.2` flag
  to `recent` subcommand argparse; route through
  `history_reader.recent_commit_events(tag=...)`

### Closest Precedent (ALTER TABLE Pattern)

- `scripts/little_loops/session_store.py:580-583` — **v15 (ENH-2460)**
  adds 3 nullable columns to `skill_events` (`exit_code`, `success`,
  `duration_ms`). Same structural shape as ENH-2508's 2-column additive
  widening. Migration text template (copy this comment style and the
  multi-statement `;`-delimited SQL verbatim):

  ```python
  # v15 (ENH-2460): completion-side columns on skill_events so skill hosts can
  # record exit_code/success/duration_ms via skill_event_context(), mirroring
  # cli_events (ENH-1834). Nullable so pre-migration dispatch-only rows remain
  # valid (NULL = "no completion signal recorded").
  """
  ALTER TABLE skill_events ADD COLUMN exit_code INTEGER;
  ALTER TABLE skill_events ADD COLUMN success INTEGER;
  ALTER TABLE skill_events ADD COLUMN duration_ms INTEGER;
  """,
  ```

### Subprocess Helper (Reuse)

- `scripts/little_loops/hooks/post_commit.py:27-41` — `_git(repo_root,
  *args)` helper, 10-second timeout, swallows OSError /
  TimeoutExpired to `None`. Add a sibling helper
  `_get_tags_at(repo_root, sha, *, timeout: int = 10)` alongside it.
  Live `record_head_commit()` uses the 10-second default; backfill path
  overrides with `timeout=60` (matching `_backfill_commit_events`'s
  batch pattern at `session_store.py:1288-1296`).
- Alternative: `scripts/little_loops/pytest_history_plugin.py:61-74`
  `_git_output()` is structurally identical (5-second timeout) and
  could be promoted to a shared helper.

### Tests (Add)

- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at(
  db, version)` helper used by every migration upgrade test
- `scripts/tests/test_session_store.py:3914-3966` — `TestSchemaV15Skill
  CompletionColumns` is the closest test template for the new v21
  column-additive upgrade test (copy its structure exactly)
- `scripts/tests/test_session_store.py:4235-4283` — `TestRecordCommit
  Event`; extend with `test_tagged_commit`, `test_untagged_commit`,
  `test_multi_tag_commit`
- `scripts/tests/test_session_store.py:4286-4359` — `TestBackfill
  CommitEvents`; extend the `repo` fixture to call
  `self._git(repo, "tag", "v0.4.2")` after the second commit; assert
  `rows[0]["tag"] == "v0.4.2"` and `rows[0]["release_version"] == "0.4.2"`.
  Add a sibling `repo_untagged` fixture without the tag call
- `scripts/tests/test_history_reader.py:1438-1457` — extend with
  `test_recent_commit_events_tag_filter`, `test_commits_by_tag`,
  `test_commits_in_release`, `test_tag_summary`
- `scripts/tests/test_ll_session.py:78-86` — extend with
  `test_recent_subcommand_commit_with_tag` (mirror existing
  `test_recent_subcommand_commit_accepted`)

### Documentation (Update)

- `docs/ARCHITECTURE.md:675` — schema versions table; bump the v17 row
  for `commit_events` to v21 with the new columns
- `docs/reference/API.md:54, 6847, 7051-7063` — `recent_commit_events`
  listing + signature; document the three new functions
- `docs/reference/API.md:7286, 7346, 7349, 7364` — `record_commit_event`
  listing and signature; document the new `tag` / `release_version`
  kwargs
- `docs/reference/API.md` — add new `commits_by_tag`, `commits_in_release`,
  `tag_summary` function listings (no existing line anchors; insert
  near `recent_commit_events` block at lines 7051-7063)
- `docs/reference/CLI.md:2510` — add `ll-session recent --kind commit
  --tag v0.4.2` example alongside the existing `--kind commit` example
- `docs/observability/des-audit.md:75` — verify `CommitEventVariant`
  schema contract still maps to `commit_event` after the column add
- `docs/guides/HISTORY_SESSION_GUIDE.md:40, 71, 95, 208` — update any
  `commit_events` column examples that surface `tag` or
  `release_version`

### Sibling Issues (Cross-Reference)

- `.issues/enhancements/P2-ENH-2458-capture-git-commit-metadata-into-
  history-db.md` — done (v17); provides the column names, index
  patterns, and `_backfill_commit_events` shape that ENH-2508 mirrors
- `.issues/enhancements/P3-ENH-2459-persist-pytest-run-results.md` —
  done (v18); analogous additive widening where `test_run_events`
  gained `head_sha` / `branch` columns populated by the producer's
  git-subprocess call
- `.issues/epics/P3-EPIC-2457-post-epic-1707-history-db-coverage-
  expansion.md` — parent epic; ENH-2508 is one of its children
- `.issues/epics/P3-EPIC-1707-*.md` — closed parent epic; establishes
  the "additive only" / graceful-degradation contract ENH-2508 inherits

### Coordination Note (Re-stated)

- Per the issue's Scope Boundary section: `SCHEMA_VERSION` is currently
  **20** (verified at `session_store.py:207`). Next available slot is
  **v21** unless another sibling issue lands first. No coordinated
  release — each child lands its migration at whatever version is open
  when implemented.

## Current Behavior

- `commit_events` (`session_store.py:626-645`, the v17 migration) has
  columns `(id, ts, commit_sha, parent_sha, message, author, branch,
  issue_id, files_json)` — 8 columns total, no `tag`, no
  `release_version`. (The line-number anchor in the original issue
  body, `506-519`, is stale; the actual migration is at 626-645 per
  codebase analysis.)
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

## Implementation Steps

1. **Add the v21 migration entry** to `_MIGRATIONS` in
   `scripts/little_loops/session_store.py` (append after the v20 entry
   at lines 709–733). Bump `SCHEMA_VERSION = 20` → `21` at line 207.
   Use the v15 ENH-2460 comment style verbatim. Migration body:
   ```sql
   ALTER TABLE commit_events ADD COLUMN tag TEXT;
   ALTER TABLE commit_events ADD COLUMN release_version TEXT;
   CREATE INDEX IF NOT EXISTS idx_commit_events_tag ON commit_events(tag);
   CREATE INDEX IF NOT EXISTS idx_commit_events_release_version ON commit_events(release_version);
   ```
   `_split_sql_statements()` (lines 768–778) tokenises on `;` so the
   four statements land atomically inside `BEGIN IMMEDIATE`.

2. **Extend `record_commit_event()`** (lines 1222–1272) to accept
   `tag: str | None = None` and `release_version: str | None = None`
   kwargs. Add both to the INSERT column list and VALUES tuple
   (currently 8 placeholders at line 1253). Append them to the FTS5
   `_index()` content string at line 1263 so `ll-session search --fts
   "v0.4.2"` matches tagged commits — recommended format:
   `f"{commit_sha[:12]} {issue_id or ''} {tag or ''} {release_version or ''} {message}".strip()[:512]`.

3. **Extend `_backfill_commit_events()`** (lines 1275–1335+) — keep the
   existing `git log --all` loop; after the `INSERT OR IGNORE` per
   commit, issue a separate `git tag --points-at <sha>` subprocess and
   `UPDATE commit_events SET tag=?, release_version=? WHERE commit_sha=?`
   for rows where tags exist. Use a 60-second timeout matching the
   `git log` subprocess at lines 1288–1296. Skip the UPDATE on missing
   git binary / empty stdout / non-zero exit code (EPIC-1707
   graceful-degradation contract).

4. **Add a shared `_get_tags_at()` helper** in
   `scripts/little_loops/hooks/post_commit.py` alongside the existing
   `_git()` helper (lines 27–41). Signature:
   ```python
   def _get_tags_at(repo_root: Path, sha: str, *, timeout: int = 10) -> list[str]:
       """Return list of tags pointing at ``sha``, or [] on any failure."""
   ```
   Reuse it from both `record_head_commit()` (lines 44–82, default 10s
   timeout) and `_backfill_commit_events()` (override to 60s).

5. **Extend `CommitEvent` dataclass** at
   `scripts/little_loops/history_reader.py:124-135` with `tag:
   str | None = None` and `release_version: str | None = None`.
   `_row_to_dataclass()` (lines 273–277) handles the new fields
   automatically — no signature change needed.

6. **Extend `recent_commit_events()`** (lines 651–686) with optional
   `tag: str | None = None` and `release_version: str | None = None`
   filter params, following the existing `branch` / `issue_id`
   pattern.

7. **Add three new read-API functions** in
   `scripts/little_loops/history_reader.py` (alongside
   `recent_commit_events`):
   - `commits_by_tag(tag: str, *, limit: int = 20, db: Path | str =
     DEFAULT_DB_PATH) -> list[CommitEvent]` — `WHERE tag LIKE
     '%' || ? || '%'`
   - `commits_in_release(version: str, *, limit: int = 20, db: Path
     | str = DEFAULT_DB_PATH) -> list[CommitEvent]` — `WHERE
     release_version = ?`
   - `tag_summary(*, db: Path | str = DEFAULT_DB_PATH) -> list[tuple
     [str, int, str, str]]` — `SELECT tag, COUNT(*), MIN(ts), MAX(ts)
     FROM commit_events WHERE tag IS NOT NULL GROUP BY tag` (model
     after `aggregate_usage()` at lines 596–648).
   All three must use `_connect_readonly()` (lines 256–270) for
   graceful DB-absent degradation.

8. **Extend live producer** in
   `scripts/little_loops/hooks/post_commit.py:record_head_commit()`
   (lines 44–82): after the existing three `_git()` calls (lines
   60–67), call `_get_tags_at(root, sha)`. Comma-join the result into
   `tag`. Extract the first tag matching `^v\d+\.\d+\.\d+$`, strip
   the leading `v`, and pass both into `record_commit_event(...)` as
   the new kwargs.

9. **Add CLI flag** `--tag <tag>` to `ll-session recent` in
   `scripts/little_loops/cli/session.py` (the `recent` subcommand
   argparse at lines ~449+). Route through
   `history_reader.recent_commit_events(tag=...)`. When both
   `--issue` and `--tag` are given, AND the filters.

10. **Add tests** mirroring the ENH-2458 and ENH-2460 patterns:
    - `TestSchemaV21CommitTagColumns` in
      `scripts/tests/test_session_store.py` — model after
      `TestSchemaV15SkillCompletionColumns` at lines 3914–3966. Use
      `_bootstrap_schema_at(db, 20)` (lines 3891–3911) → `ensure_db(db)`
      to verify the column add + pre-migration NULL preservation.
    - Extend `TestRecordCommitEvent` at lines 4235–4283 with
      `test_tagged_commit`, `test_untagged_commit`,
      `test_multi_tag_commit`.
    - Extend `TestBackfillCommitEvents` at lines 4286–4359 — extend
      the `repo` fixture to call `self._git(repo, "tag", "v0.4.2")`
      after the second commit; assert `rows[0]["tag"] == "v0.4.2"`
      and `rows[0]["release_version"] == "0.4.2"`. Add a sibling
      `repo_untagged` fixture (no tag call) and assert both columns
      are NULL.
    - In `scripts/tests/test_history_reader.py`, add
      `test_recent_commit_events_tag_filter`, `test_commits_by_tag`,
      `test_commits_in_release`, `test_tag_summary` (mirror the
      structure of `test_recent_commit_events_filters` at lines
      1438–1457).
    - In `scripts/tests/test_ll_session.py`, add
      `test_recent_subcommand_commit_with_tag` (mirror
      `test_recent_subcommand_commit_accepted` at lines 78–86).

11. **Update documentation** — bump the v17 row in
    `docs/ARCHITECTURE.md:675` to v21 with the new columns; document
    the new `record_commit_event` kwargs in `docs/reference/API.md`
    (lines 7286, 7346, 7349, 7364); document the new functions next to
    `recent_commit_events` (lines 7051–7063); add `ll-session recent
    --kind commit --tag v0.4.2` example in `docs/reference/CLI.md:2510`;
    update `docs/guides/HISTORY_SESSION_GUIDE.md` column examples.

12. **Verification**: Run `python -m pytest scripts/tests/test_session
    _store.py scripts/tests/test_history_reader.py scripts/tests/test_
    ll_session.py -v`. Note that `ll-verify-kinds` is a no-op for
    ALTER TABLE-only migrations (per `scripts/little_loops/cli/
    verify_kinds.py:38-47`, which scans `_MIGRATIONS` for `CREATE TABLE`
    statements only).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale path references in the Sources section above**:
  - `scripts/little_loops/git_utils.py` does NOT exist as a discrete
    file. The equivalent helpers live inline at
    `scripts/little_loops/hooks/post_commit.py:_git` (lines 27–41) and
    inside `scripts/little_loops/git_operations.py`. ENH-2508 should
    either extend the inline `_git` helper or create a new
    `git_utils.py` module as part of the implementation (the issue's
    body assumed the latter; the former is the path of least change).
  - `scripts/little_loops/cli/manage_release.py` does NOT exist. The
    canonical release CLI surface is the `/ll:manage-release` slash
    command at
    `commands/manage-release.md`. ENH-2508's "release tooling that
    would consume this" relationship is to the slash command, not a
    Python module.

- **Stale line-number anchors in the issue body**:
  - `session_store.py:506-519` (Current Behavior) → actual range is
    `:626-645` (the v17 migration defining `commit_events`).
  - `session_store.py:1041-1091` (Proposed Solution,
    `record_commit_event()`) → actual range is `:1222-1272`.
  - `session_store.py:1094-1188` (Proposed Solution,
    `_backfill_commit_events()`) → actual range is `:1275-1335+`.
  The file paths are correct; the line anchors should be refreshed at
  implementation time.

- **No existing tag / release-version code in the repo**: No call
  site currently invokes `git tag --points-at` or `git describe
  --tags --exact-match`. ENH-2508 establishes this pattern from
  scratch; the closest subprocess templates are
  `hooks/post_commit.py:_git()` (10s timeout) and
  `pytest_history_plugin.py:_git_output()` (5s timeout).

- **No comma-separated list precedent in the codebase**: All
  multi-value columns are JSON arrays (`commit_events.files_json`,
  `test_run_events.failing_names_json`). The issue's "comma-separated
  list" preference remains valid because (a) tags are LIKE-matched
  rather than piecemeal-queried, and (b) JSON would force every
  consumer to parse on read. The `LIKE '%' || ? || '%'` query
  pattern in `commits_by_tag()` will work with either representation.

- **`INSERT OR IGNORE` + `commit_sha UNIQUE` requires a separate
  UPDATE path**: Because `record_commit_event` uses `INSERT OR
  IGNORE` (line 1253) for idempotency, a live tag-write for a row
  that already exists must use `UPDATE`. The backfill flow should
  keep the `INSERT OR IGNORE` per row, then `UPDATE commit_events
  SET tag=?, release_version=? WHERE commit_sha=?` for rows where
  tags exist — this preserves the original message/branch
  attribution that won't be re-derived on a re-run.

- **No `_KIND_TABLE` / `VALID_KINDS` change required**: Verified by
  `scripts/little_loops/cli/verify_kinds.py:38-47`, which scans
  `_MIGRATIONS` for `CREATE TABLE` statements only. ALTER TABLE
  migrations bypass this gate. Neither `VALID_KINDS` nor
  `_KIND_TABLE` needs a new entry.

- **Multi-tag decision options (re-stated per Decision-Point
  Formatting)**:
  - **Option A**: Comma-separated TEXT in a single `tag` column
    (recommended by the issue, matches EPIC-1707 "additive only"
    preference, no schema cost beyond the column).
  - **Option B**: Join table `commit_tags(commit_sha, tag)` with
    `(commit_sha TEXT NOT NULL REFERENCES commit_events(commit_sha),
    tag TEXT NOT NULL, PRIMARY KEY (commit_sha, tag))` — cleaner
    per-tag queries (`GROUP BY tag`, exact match without LIKE), but
    adds a second table + migration + an extra `_KIND_TABLE` /
    `VALID_KINDS` decision (and `ll-verify-kinds` registration).
  - **Recommended**: Option A. The codebase has no other
    comma-separated-list columns, but the alternative — a full
    join table — is overkill for a query pattern that's satisfied
    by `tag LIKE '%' || ? || '%'`. If future requirements demand
    per-tag analytics, Option B can be added later as v22 without
    breaking Option A rows.

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("widens
`commit_events`; `SCHEMA_VERSION` bumped"). Several other active EPIC-2457
siblings (ENH-2492, ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2493,
ENH-2494, ENH-2495, ENH-2496, ENH-2497, ENH-2498, ENH-2504, ENH-2506,
ENH-2511, and others) independently make the same schema-slot claim in their
own Integration Maps — they cannot all land at the same version number.
Verified against current code (`scripts/little_loops/session_store.py`):
`SCHEMA_VERSION` is now **20** (v17=`commit_events`/ENH-2458 done,
v18=`test_run_events`/ENH-2459 done, v19=`raw_events`/ENH-2581 done,
v20=`usage_events`/ENH-2461 done). At implementation time, read the live
`SCHEMA_VERSION` constant to determine the actual next-available slot rather
than trusting this issue's implied slot; each child lands its own migration
at whatever version is open when it is implemented (no coordinated release;
per EPIC-2457's own "no shared helper module is required" scope note).

## Session Log
- `/ll:refine-issue` - 2026-07-16T16:39:50 - `02969852-e3bd-41f7-a7c6-d6ff4d79a629.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`