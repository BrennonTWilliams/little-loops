---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T07:31:36Z'
parent: EPIC-2792
confidence_score: 100
outcome_confidence: 95
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 23
status: done
---

# ENH-2782: `session_store.backfill()` reads and parses every issue file's frontmatter twice

## Summary

`backfill()` calls `_backfill_issues()` and then `_backfill_snapshots()`
back-to-back; each independently does its own `issues_dir.rglob("*.md")`
walk, `read_text()`, and `parse_frontmatter()` for every issue file, so each
file is read and parsed from disk twice per backfill invocation
(`_backfill_snapshots` additionally calls `strip_frontmatter()` on the same
content).

## Location

- **File**: `scripts/little_loops/session_store.py`
- **Line(s)**: `_backfill_issues` at 3072 (walk 3085-3087), `_backfill_snapshots` at 3135 (walk 3146-3151), call site 4701-4703 (at scan commit: fb567390)
- **Anchor**: `in functions _backfill_issues() / _backfill_snapshots()`
- **Code**:
```python
# _backfill_issues
for issue_file in sorted(issues_dir.rglob("*.md")):
    fm = parse_frontmatter(issue_file.read_text(encoding="utf-8"))
...
# _backfill_snapshots
for issue_file in sorted(issues_dir.rglob("*.md")):
    content = issue_file.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
...
# backfill()
counts["issues"] = _backfill_issues(conn, issues_dir)
counts["snapshots"] = _backfill_snapshots(conn, issues_dir)
```

> ⚠ Line numbers above are stale relative to current `main` — the file has
> grown since `discovered_commit`. Current locations (verified 2026-07-25):
> `_backfill_issues()` at `session_store.py:3322` (walk at 3335),
> `_backfill_snapshots()` at `session_store.py:3383` (walk at 3394),
> call site at `session_store.py:4957-4958`. See Codebase Research Findings
> below for full current-line detail.

## Current Behavior

Two full directory walks + frontmatter parses of ~2,600 files per
`ll-session backfill` run.

## Expected Behavior

A single walk reads and parses each file once, feeding both the
`issue_events` and `issue_snapshots` insert logic.

## Proposed Solution

Merge the loops into one pass, or have `_backfill_snapshots` accept a
pre-read `{path: (content, frontmatter)}` map produced by
`_backfill_issues`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Direct precedent to follow**: `0fc282ff improve(issue_parser): collapse
  find_issues(skip_blocked=True) to a single parse pass`
  (`scripts/little_loops/issue_parser.py:find_issues()`, single-pass branch
  starting line 1275) — one unfiltered walk builds a superset list, and the
  narrower/filtered result is derived from that same in-loop iteration
  in-memory rather than re-walking. `bebf02e4 improve(cli/issues): collapse
  next-issue(s) --include-blocked double-parse`
  (`scripts/little_loops/cli/issues/next_issue.py:cmd_next_issue()`, lines
  42-58) applies the same shape at a caller site. A merged
  `_backfill_issues`/`_backfill_snapshots` pass should follow this exact
  precedent: one `rglob("*.md")` + one `read_text()` + one
  `parse_frontmatter()` per file, performing both the `issue_events` INSERT
  and the `issue_snapshots` INSERT (plus both `_index()` calls) inside that
  single loop body.
- **Notable divergences that a merge must preserve** (both functions in
  `session_store.py`):
  - `_backfill_issues()` (line 3322, walk 3335) wraps `parse_frontmatter()`
    inside the same `try/except OSError` as the read (lines 3336-3339);
    `_backfill_snapshots()` (line 3383, walk 3394) only wraps `read_text()`
    in the try (lines 3395-3398) and calls `parse_frontmatter()` unguarded
    afterward (line 3399) — a parse exception there currently propagates
    rather than being caught.
  - `_backfill_issues()` derives a per-file `ts` from frontmatter fields
    (fallback chain `completed_at` → `captured_at` → `discovered_date` →
    `""`); `_backfill_snapshots()` computes one `_now()` timestamp (line
    3393) shared by every snapshot row in the call.
  - `_backfill_issues()` derives `issue_type`/`priority` via
    `_derive_type_priority(issue_file.name, fm)`; `_backfill_snapshots()`
    uses raw `fm.get("type")` / `fm.get("priority")` directly, without that
    helper.
  - The two `_index()` calls write different `kind` values into the same
    `search_index` table: `_backfill_issues()` indexes a short
    `"{issue_id} {status} {issue_type}"` summary (`kind="issue"`);
    `_backfill_snapshots()` indexes the full body text (`kind="snapshot"`)
    for full-text search over issue content. Both must still fire per file
    in a merged pass.
- **Call site**: both helpers are invoked back-to-back from `backfill()`
  (`session_store.py:4957-4958`) sharing one open `sqlite3.Connection`
  (single `conn.commit()` at the end of `backfill()`, line ~4974) — no
  separate transactions to reconcile when merging.
- **Standalone wrapper convention**: `_backfill_snapshots()` is also exposed
  independently via public `backfill_snapshots()` (lines 4889-4909), which
  does its own `issues_dir.is_dir()` check + connection lifecycle. A merged
  private helper should keep `_backfill_issues`/`_backfill_snapshots`
  callable standalone (or leave thin wrappers) so `backfill_snapshots()`'s
  existing public contract and its tests keep working unchanged.
- **Tests to extend**: `scripts/tests/test_session_store.py` —
  `TestBackfillIssuesV2Columns` (line ~875) and `TestBackfillSnapshots`
  (line ~4170, helper `_make_issues_dir()` at line ~4173) assert only on
  `counts[...]` values and resulting DB rows; neither currently spies on
  `Path.read_text`/`parse_frontmatter` call counts. Add an IO-count
  assertion (e.g. patch `parse_frontmatter` with a call-counting wrapper) so
  the fix is regression-tested, not just behavior-preserving.
- **No shared caching primitive exists yet** — other `rglob("*.md")` sites
  (`recursive_finalize.py`, `cli/migrate_*.py`, `link_checker.py`) are each
  single-purpose and unrelated; this merge would be the first
  read-once/feed-multiple-consumers helper for `issues_dir`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py` — `ll-session backfill` CLI dispatch calls `backfill()` (`main_session()`, ~line 589) and `backfill_snapshots()` for the `--snapshots` flag path (~line 523). Only depends on the return value being an int count and on no unhandled exception reaching the CLI — no coupling to internal walk/parse mechanics, so the merge is safe here as long as `backfill()`/`backfill_snapshots()` signatures and return types are preserved. [Agent 1 + Agent 2 finding]
- `scripts/tests/test_ll_session.py` — `test_snapshots_flag_calls_backfill_snapshots` (~line 1047) and `test_snapshots_flag_default_is_false` (~line 1040) mock `little_loops.cli.session.backfill`/`backfill_snapshots` entirely at the CLI layer; unaffected by the merge but should still be re-run since they exercise the wrapper entry points being touched. [Agent 2 + Agent 3 finding]

Note: `scripts/little_loops/cli/backfill_worker.py` and `scripts/little_loops/hooks/session_start.py` call `backfill_incremental()`, a separate JSONL-derived backfill family unrelated to `_backfill_issues`/`_backfill_snapshots` — confirmed out of scope, not added here. [Agent 1 finding, filtered]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- **New regression test** (`scripts/tests/test_session_store.py`) — no existing test asserts read/parse call counts for `_backfill_issues`/`_backfill_snapshots`; add one following the exact template already used for this same problem shape at `scripts/tests/test_issue_parser.py:1267` (`test_find_issues_skip_blocked_single_parse_pass`, commit 0fc282ff): `patch.object`/`patch` a counting wrapper around `Path.read_text` or `parse_frontmatter` (imported locally inside `_backfill_issues`/`_backfill_snapshots` at lines 3332/3390), call `backfill(...)`, and assert every issue file's call count == 1 (currently 2). [Agent 3 finding]
- **Confirmed no break risk**: no test in `test_session_store.py` exercises `_backfill_snapshots`'s unguarded `parse_frontmatter` exception propagation with a malformed-frontmatter fixture — the exception-handling asymmetry the issue flags is an untested gap, not a live regression risk, so any behavior-preserving choice made during the merge has no existing assertion to break. Optionally add a malformed-frontmatter fixture test to lock in whichever guard scope the merge settles on. [Agent 3 finding]
- `TestBackfillIssuesV2Columns` (`test_session_store.py:875`) and `TestBackfillSnapshots` (`test_session_store.py:4170`, helper `_make_issues_dir()` at 4173) both go through the public `backfill()` entry point and assert only on `counts[...]`/DB rows — confirmed these need no changes and should pass unchanged post-merge as long as output rows are identical. [Agent 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Add a single-pass I/O-count regression test in `scripts/tests/test_session_store.py`, patching `Path.read_text`/`parse_frontmatter` with a counting wrapper (template: `test_issue_parser.py:1267`'s `test_find_issues_skip_blocked_single_parse_pass`), asserting each issue file is read/parsed exactly once via `backfill(...)`.
2. Re-run `scripts/tests/test_ll_session.py`'s `test_snapshots_flag_calls_backfill_snapshots`/`test_snapshots_flag_default_is_false` after the merge — mocked at the CLI layer, no code change expected but confirms the `cli/session.py` contract (int return, no unhandled raise) still holds.
3. No documentation, config, or CLI help-text changes required — confirmed no doc file describes the double-walk internals at a level the merge would invalidate.

## Impact

- **Effort**: Medium
- Halves the issue-tree I/O of every `backfill()` call (run by session hooks
  and `ll-session backfill`).

## Resolution

Added `_backfill_issues_and_snapshots()` in `session_store.py`, a single
`rglob("*.md")` pass that reads and parses each issue file's frontmatter
once and performs both the `issue_events` and `issue_snapshots` inserts (plus
both `_index()` calls) per file. `backfill()`'s call site now calls this
merged helper instead of `_backfill_issues()` + `_backfill_snapshots()`
back-to-back. `_backfill_issues()` (now dead — its only caller was
`backfill()`) was removed; `_backfill_snapshots()` is kept as-is since it's
still used standalone by the public `backfill_snapshots()` wrapper. The merge
wraps read+parse in one `try/except OSError` (matching `_backfill_issues`'s
broader guard rather than `_backfill_snapshots`'s narrower one — no existing
test asserted on the narrower propagation behavior, per the issue's wiring
notes) and otherwise preserves each function's independent per-file logic
(event `ts` derivation, `_derive_type_priority()`, shared snapshot `ts`).

Added `TestBackfillSinglePass::test_backfill_reads_each_issue_file_once` in
`test_session_store.py`, patching `little_loops.frontmatter.parse_frontmatter`
with a counting wrapper and asserting every issue file's content is parsed
exactly once via `backfill(...)`.

All of `test_session_store.py` (505 tests) and `test_ll_session.py` pass.
Full suite: 16165 passed, 5 pre-existing failures unrelated to this change
(confirmed present on `main` before this fix — schema-version drift and
unrelated `history_reader`/`history_context_cli` fixture issues).

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T07:31:09 - `d4ae4e94-4b23-4f4c-bced-da37325c711d.jsonl`
- `/ll:ready-issue` - 2026-07-25T07:24:55 - `d4ae4e94-4b23-4f4c-bced-da37325c711d.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `86dcdf1e-bc1b-4f8c-9dc9-da835c5ac9d3.jsonl`
- `/ll:wire-issue` - 2026-07-25T07:22:23 - `a47aa472-bcaa-4f88-863b-577bea536b97.jsonl`
- `/ll:refine-issue` - 2026-07-25T07:17:47 - `f6439a85-f046-4f54-ac9d-fc83b2a9ab38.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
