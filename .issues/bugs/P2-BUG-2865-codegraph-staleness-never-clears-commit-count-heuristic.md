---
id: BUG-2865
type: BUG
title: "ll-code codegraph freshness is permanently stale \u2014 commit-count heuristic\
  \ can never be satisfied by a sync"
priority: P2
status: done
captured_at: '2026-07-27T19:20:00Z'
completed_at: '2026-07-27T19:44:13Z'
discovered_date: 2026-07-27
discovered_by: manual-verification
labels:
- codequery
- ll-code
- staleness
relates_to:
- ENH-2863
confidence_score: 94
outcome_confidence: 79
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 23
---

# BUG-2865: ll-code codegraph freshness is permanently stale — commit-count heuristic can never be satisfied by a sync

## Summary

`CodegraphProvider.status()` (`scripts/little_loops/codequery/codegraph.py:181`) reports
`freshness: stale` indefinitely on a clean, fully-indexed working tree. ENH-2863's
`auto_sync` shell-out fires correctly on every call, but the staleness signal it is meant to
clear is one that a sync structurally *cannot* clear.

The staleness verdict is `head_moved == 0 and dirty_files == 0`, where `head_moved` is
`git log --since=<MAX(indexed_at)> --oneline | wc -l` (line 214-215). `codegraph sync` only
advances a `files.indexed_at` row when that file's **content hash changes**. The normal
development order is edit → index/sync → commit, so a commit lands content that is *already
indexed*: HEAD moves past `MAX(indexed_at)` while every content hash stays identical. `sync`
correctly answers "Already up to date", `MAX(indexed_at)` does not advance, and `head_moved`
stays `>= 1` forever.

Net effect: users with `auto_sync: true` see a perpetual staleness warning on a genuinely
current index, and pay an unnecessary `codegraph sync` subprocess on every single
`status()` call (and therefore on every `ll-code` query that checks status first).

## Steps to Reproduce

1. In a repo with a `codegraph` index and `code_query.codegraph.auto_sync: true`,
   ensure the working tree is clean (`git status --porcelain` empty).
2. Run `codegraph sync "$(git rev-parse --show-toplevel)"` until it reports
   "Already up to date".
3. Make any commit (even one touching only already-indexed content).
4. Run `ll-code -j status` twice in a row.

**Expected**: the first call may report `stale` (the sync it triggers is observed by the
*next* read, per `_sync_if_stale`'s docstring at line 138-139); the second reports `fresh`.

**Actual**: both report `stale`, and `MAX(indexed_at)` in `.codegraph/codegraph.db` is
unchanged across both calls. Repeats forever.

## Current Behavior

Every `ll-code status` call on a clean, fully-indexed tree reports
`freshness: stale` with `head_moved >= 1, dirty_files=0`, and fires a `codegraph sync`
subprocess that finds nothing to do. `MAX(indexed_at)` never advances, so the next call
reports exactly the same thing. The warning never self-clears.

## Expected Behavior

Once the index content matches the working tree, `ll-code status` reports
`freshness: fresh` and stops shelling out to `codegraph sync`. Staleness is reported only
when the index genuinely lags the content it indexes.

## Impact

- Every consumer of `ll-code` sees a permanent, unactionable staleness warning, training
  users to ignore a signal that is supposed to mean something.
- `auto_sync: true` pays a `codegraph sync` subprocess on every `status()` call forever
  (bounded by `_SYNC_TIMEOUT`), on an index that is already current.
- ENH-2863's shipped promise — "staleness naturally clears on the caller's next
  `status()`" — does not hold in the common case.

## Observed Evidence (2026-07-27, this repo)

```
$ git status --porcelain                       # clean
$ ll-code -j status
  "freshness": "stale",
  "indexed_at": "2026-07-27T19:09:28Z",
  "detail": "indexed_at=2026-07-27T19:09:28Z, head_moved=1 commits, dirty_files=0, policy=warn"
$ sqlite3 .codegraph/codegraph.db "select max(indexed_at) from files;"
1785179368797                                  # 14:09:28 local
$ ll-code -j status                            # identical output
$ sqlite3 .codegraph/codegraph.db "select max(indexed_at) from files;"
1785179368797                                  # unchanged — sync had nothing to do
```

The single commit counted by `head_moved=1` is `86a64569` (14:11:51), whose files were all
edited before the 14:09:28 index and whose indexed content hashes match the working tree
byte-for-byte:

```
scripts/little_loops/codequery/codegraph.py
  files.content_hash : 0e58811270bec8099dc564fbf33a83d4bf6f5cbfa02296025f425d6d3541fe13
  sha256(on-disk)    : 0e58811270bec8099dc564fbf33a83d4bf6f5cbfa02296025f425d6d3541fe13
```

## Root Cause

`head_moved` is a **proxy** for "content changed since index" that is not implied by the
thing it measures. Committing does not change file content or mtime, so:

- `codegraph`'s own staleness model (content hash per file) says fresh.
- `ll-code`'s staleness model (commits since last index timestamp) says stale.

These disagree by construction, and only `codegraph`'s model is actually load-bearing for
whether query results are correct. `dirty_files` (line 221-229) is a sound signal —
uncommitted edits really do mean unindexed content. `head_moved` is the defective half.

## Proposed Solution

Make `head_moved` content-aware instead of removing it (a commit *can* legitimately bring in
unindexed content — e.g. `git pull`, branch switch, revert). Bound the work by commit churn,
not repo size:

1. `git log --since=<indexed_at> --name-only --pretty=format:` → the set of paths touched
   since the index.
2. Filter with the existing `_is_scan_relevant()` (line 116).
3. For each surviving path, compare `sha256(on-disk bytes)` against that row's
   `files.content_hash`. **`content_hash` is confirmed to be a plain sha256 of the file
   bytes** (verified above). A path missing from `files` counts as stale.
4. `head_moved` becomes the count of paths that actually differ (or are unindexed).

This makes the "staleness clears on the next `status()`" contract in `_sync_if_stale`'s
docstring true, and stops the per-call subprocess on an already-current index.

Open design question to settle during implementation: whether to cap the hashed-path count
(a long-idle index could name thousands of paths) and fall back to the current cheap
commit-count when over the cap.

## Acceptance Criteria

- [x] On a clean tree whose indexed content hashes all match the working tree,
      `ll-code status` reports `freshness: fresh` regardless of how many commits have
      landed since `MAX(indexed_at)`.
- [x] A commit that introduces genuinely unindexed content (e.g. `git pull` of a new file)
      still reports `stale` on the first `status()` and `fresh` on the next, after
      `auto_sync` runs.
- [x] Uncommitted scan-relevant edits still report `stale` (no regression to `dirty_files`).
- [x] With `auto_sync: true` and a current index, `status()` does **not** shell out to
      `codegraph sync`.
- [x] A test exercises the real `codegraph` staleness contract without mocking the
      subprocess — `scripts/tests/test_codequery_codegraph.py`'s 29 existing tests all mock
      `subprocess.run`, which is exactly why this shipped undetected. Skip gracefully when
      the `codegraph` binary is absent, per the repo's external-tool gate convention.

## Resolution

`head_moved` is now content-hash-aware (`_content_aware_head_moved` in
`scripts/little_loops/codequery/codegraph.py`). Instead of counting raw commits since
`MAX(indexed_at)`, `status()` now:

1. Lists the paths touched by commits since `indexed_at` (`git log --since=... --name-only`).
2. Filters to scan-relevant paths via the existing `_is_scan_relevant()`.
3. Compares each surviving path's on-disk sha256 against `files.content_hash`; a path
   missing from the index or hash-mismatched counts as genuinely stale.
4. Falls back to the old cheap commit-count heuristic when more than
   `_HEAD_MOVED_PATH_CAP` (500) paths were touched, to bound hashing cost.

A commit that lands already-indexed bytes (the normal edit → index → commit order) no
longer flips freshness to `stale`, and `auto_sync`'s `codegraph sync` shell-out no longer
fires on an already-current index. Added `TestContentAwareHeadMoved` covering the
already-indexed-content-stays-fresh case, the genuinely-new-content-reports-stale case, and
the no-spurious-sync case; updated two existing fixtures (`test_commits_ahead_marks_stale_per_policy`,
`TestAutoSync._stale_repo`) whose unindexed file previously lived outside `scan.focus_dirs`
and would otherwise have silently stopped exercising staleness under the new, more precise
signal.

The hashed-path-cap design question is resolved: cap at 500 touched paths, falling back to
the commit-count heuristic above that (a conservative over-report of staleness, never an
under-report).

## Status

Done — see Resolution.

## Related

- ENH-2863 / commit `91a6174b` — added `_sync_if_stale`; correct as coded, but wired to a
  signal the sync cannot clear.

## Session Log
- `/ll:confidence-check` - 2026-07-27T19:21:22Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03a1deef-0966-4e20-9875-a530e5aadb11.jsonl`
- `/ll:manage-issue` - 2026-07-27T19:43:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c19944a-c49f-4075-bc8a-2fbab0680c68.jsonl`
