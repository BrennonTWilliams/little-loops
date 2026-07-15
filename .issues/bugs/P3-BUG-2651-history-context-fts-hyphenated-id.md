---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15T00:00:00Z
discovered_by: capture-issue
status: open
labels: [history, fts5, triage]
---

# BUG-2651: `ll-history-context <ID>` silently returns empty for hyphenated issue IDs (FTS5 parses `-NNN` as a column filter)

## Summary

`ll-history-context BUG-490` (and any hyphenated issue ID) produces no output
because the raw ID is passed straight into an FTS5 `MATCH` query. FTS5 parses the
hyphen as a column-filter / negation operator, so `BUG-490` becomes an invalid
expression. The resulting `sqlite3.OperationalError` is swallowed and the search
returns an empty list, degrading triage context quality with no error surfaced.

This was observed during a `sprint-refine-and-implement` run on a consumer
project: the run log recorded *"`ll-history-context BUG-490` failed during the
run: the history query treated the hyphenated ID as an invalid FTS expression."*

## Location

- **File**: `scripts/little_loops/history_reader.py`
- **Line(s)**: ~353-383 (`search()`), the `WHERE search_index MATCH ?` branches
- **Caller**: `scripts/little_loops/cli/history_context.py:~255` passes
  `query=args.issue_id` unquoted into `search(...)`

## Current Behavior

`history_reader.search()` binds the caller's `query` directly to the FTS5 `MATCH`
operator:

```python
rows = conn.execute(
    "SELECT content, kind, ref, anchor, ts, bm25(search_index) AS score "
    "FROM search_index WHERE search_index MATCH ? AND kind = ? "
    "ORDER BY score LIMIT ?",
    (query, kind, limit),
).fetchall()
```

With `query = "BUG-490"`, FTS5 interprets `-490` as a column filter and raises
`OperationalError: no such column: 490`. The `except sqlite3.OperationalError`
handler (~line 383) logs a warning and returns `[]`, so the failure is invisible
to the caller and to the user.

Reproduced empirically:

```
$ sqlite3 :memory: "CREATE VIRTUAL TABLE t USING fts5(c); \
    INSERT INTO t VALUES('BUG-490 was fixed'); \
    SELECT c FROM t WHERE t MATCH 'BUG-490';"
Error: stepping, no such column: 490
```

Note `find_user_corrections()` in the same module is **not** affected — it uses a
`LIKE '%{topic}%'` search, which treats the hyphen literally.

## Steps to Reproduce

1. Ensure `.ll/history.db` has at least one correction/FTS row mentioning a
   hyphenated issue ID (e.g. `BUG-490`).
2. Run `ll-history-context BUG-490`.
3. Observe: empty output (no historical context block), despite matching rows
   existing. A `no such column: 490` `OperationalError` was raised internally and
   swallowed by the `except sqlite3.OperationalError` handler.

Minimal FTS5 repro (no project needed):

```
sqlite3 :memory: "CREATE VIRTUAL TABLE t USING fts5(c); \
  INSERT INTO t VALUES('BUG-490 was fixed'); \
  SELECT c FROM t WHERE t MATCH 'BUG-490';"
# -> Error: stepping, no such column: 490
```

## Expected Behavior

A hyphenated issue ID matches its literal occurrences in the history index.
`ll-history-context BUG-490` returns the corrections / FTS matches for that issue
(or a clean empty result when there genuinely are none), never a swallowed
parse error.

## Proposed Solution

Quote the ID as an FTS5 phrase before binding it to `MATCH`, e.g. wrap the query
in double quotes (`'"' + query.replace('"', '""') + '"'`) so `-`, and any other
FTS5 operator characters, are treated literally. Apply at the `search()` boundary
(or a small `_fts_phrase()` helper) so all `MATCH` callers benefit.

Add a regression test asserting `search(query="BUG-490", ...)` (and an ID like
`ENH-2589`) returns seeded rows rather than `[]`, and that no `OperationalError`
is swallowed.

## Impact

Medium. Isolated, high-confidence, ~1-line fix plus a test. Every hyphenated
issue ID (i.e. every real ID) currently gets zero historical context, silently
lowering the quality of `ready-issue` / refine triage that depends on
`ll-history-context`. No data loss, but a persistent invisible degradation.

## Status

open — captured from consumer-project run findings (sprint base-branch mismatch
investigation). Independent of sibling issues FEAT-2652 / ENH-2653; can ship on
its own.
