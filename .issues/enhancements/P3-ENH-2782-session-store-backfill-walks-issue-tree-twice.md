---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
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

## Impact

- **Effort**: Medium
- Halves the issue-tree I/O of every `backfill()` call (run by session hooks
  and `ll-session backfill`).

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
