---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15 00:00:00+00:00
discovered_by: capture-issue
completed_at: '2026-07-15T23:05:12Z'
status: done
labels:
- history
- fts5
- triage
confidence_score: 100
outcome_confidence: 94
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Root cause confirmed.** `history_reader.search()` begins at
`scripts/little_loops/history_reader.py:353`. Both `MATCH ?` branches
(`history_reader.py:372` kind-filtered, `history_reader.py:379` unfiltered) bind
`query` verbatim, and the `except sqlite3.OperationalError` handler at
`history_reader.py:383` logs a warning and returns `[]` — exactly the swallow the
issue describes.

**Caller confirmed.** `scripts/little_loops/cli/history_context.py:254-256` calls
`search(query=args.issue_id, kind="correction", limit=20, db=args.db)`, passing
the raw hyphenated ID. The sibling `find_user_corrections(topic=args.issue_id,...)`
at `history_context.py:250-252` uses `LIKE` and is unaffected (matches the issue's
note).

### Integration Map

#### Files to Modify
- `scripts/little_loops/history_reader.py:353` (`search()`) — add a
  `_fts_phrase(query)` helper (double-quote + `"` → `""` escaping) and apply it to
  the bound value in **both** `MATCH ?` branches (lines 372, 379). Fix at this
  boundary so all `MATCH` callers benefit, per the Proposed Solution.

#### Sibling MATCH site (evaluate, do not silently skip)
- `scripts/little_loops/session_store.py:1438` — a second, structurally identical
  `WHERE search_index MATCH ?` query. It does **not** swallow: it re-raises as
  `ValueError(f"invalid FTS query {query!r}: ...")` (`session_store.py:1431`).
  It has no hyphenated-ID caller today, but the same phrase-quoting helper should
  be applied here (or shared) for consistency — otherwise a future hyphenated-ID
  caller of this path raises instead of matching. Note the divergent error
  contract when deciding whether to share one helper.

#### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py:378-387` — the `ll-session search` subcommand
  handler. Line 381 calls `history_search(args.fts, ...)` (aliased import of
  `history_reader.search`) and line 384 calls `search(args.db, query=args.fts, ...)`
  (`session_store.search`). Line 381's `--kind` branch inherits the primary
  `history_reader` fix for free. **Contract coupling:** lines 385-387
  (`except ValueError as exc: logger.error(str(exc)); return 1`) depend on
  `session_store.search()` continuing to raise `ValueError("invalid FTS query …")`
  for malformed input. Applying `_fts_phrase()` in `session_store.search()` narrows
  (does not remove) that raise — dash-containing queries stop raising and start
  matching, which is the intended fix; genuinely malformed FTS (e.g. unbalanced
  quotes) still raises. No regression test guards this CLI exit-code-1 path today
  (see Tests). [Agent 1 + Agent 2 finding]

#### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6980-6988` — `history_reader.search()` reference states
  "Returns `[]` if the database is unavailable or the FTS5 query syntax is invalid."
  Still accurate after the fix, but the class of "invalid syntax" shrinks (hyphenated
  IDs no longer count). Update if the entry enumerates hyphenated-ID handling. [Agent 2 finding]
- `docs/reference/CLI.md:2547-2576` (`### ll-history-context`) and the `ll-session
  search --fts` section (~2372-2508) — both use hyphenated issue IDs (`ENH-1708`,
  `BUG-1759`) as canonical examples, i.e. exactly the shape this bug breaks. Verify
  the "returns empty when no matches" prose distinguishes "no matches" from
  "FTS rejected the ID." [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md:35,87,288,293` — hyphenated-ID
  `ll-history-context BUG-1759` examples; line 87 documents the snapshot/FTS
  fallback chain the fix interacts with (FTS now matches for hyphenated IDs, so the
  snapshot fallback fires less often). [Agent 2 finding]

#### Tests
- `scripts/tests/test_history_reader.py:238` (`TestSearch`) — existing coverage:
  `test_search_returns_ranked_results` (line 241), `test_search_with_kind_filter`
  (line 252), `test_search_invalid_query_returns_empty` (line 268). Model the
  regression test on these: seed via `SQLiteTransport(db).send({...})` /
  `transport.close()`, then assert `search("BUG-490", db=db)` (and `search("ENH-2589",
  kind="correction", ...)`) returns the seeded rows rather than `[]`.
- Seeding a `correction`-kind row: the FTS `kind="correction"` filter used by the
  caller requires seeding a correction event (see how `issue.completed` /
  `state_enter` events map to kinds in `test_search_with_kind_filter`); confirm the
  correct event shape produces `kind="correction"` when authoring the test.

_Wiring pass added by `/ll:wire-issue`:_
- **Seeding helper (canonical):** `record_correction(db, session_id, content, source)`
  in `session_store.py:940-969` writes to `user_corrections` (line 964, the
  `find_user_corrections` LIKE table) **and** calls `_index(..., kind="correction")`
  (line 967) which populates the FTS `search_index` `search()` queries. It is the
  right seeding call for the regression test. `test_history_context_cli.py`
  (`TestHistoryContextWithMatches`, lines 38-70, esp. line 45) already uses it. [Agent 3 finding]
- **CLI e2e tests do NOT currently catch the bug** — `cli/history_context.py:268-278`
  builds `rows` from `find_user_corrections()` (LIKE) *first*, so existing
  `test_history_context_cli.py` assertions pass regardless of the FTS `search()`
  bug. A regression test must isolate the FTS path: either call
  `history_reader.search(query="BUG-490", kind="correction", ...)` directly (à la
  `TestSearch`), or add a CLI case where LIKE returns nothing but FTS should. Add a
  hyphen-specific case to `test_history_context_cli.py:TestHistoryContextWithMatches`. [Agent 3 finding]
- `scripts/tests/test_session_store.py` (`TestSearch`, ~lines 395-415) — exercises
  `session_store.search()` directly but has **no** coverage of the
  `ValueError("invalid FTS query …")` raise path or hyphenated-ID input. No test
  string-matches that error, so changing it breaks nothing — but if the sibling fix
  touches `session_store.search()`, add a case here to lock in the new/preserved
  behavior. [Agent 2 + Agent 3 finding]
- `scripts/tests/test_ll_session.py:23-66` — CLI arg-parsing / subcommand tests for
  `ll-session search`; check whether a hyphenated `--fts` value needs a case once
  `cli/session.py`'s error contract narrows. [Agent 1 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

1. Add `_fts_phrase(query)` helper (double-quote wrap + `"` → `""` escaping) and
   apply it in both `history_reader.search()` MATCH branches (lines 372, 379).
2. Apply the same helper in `session_store.search()` (line 1438). Confirm the
   `except ValueError` at `cli/session.py:385-387` still fires only for genuinely
   malformed FTS (unbalanced quotes), not for dash-containing queries.
3. Add the FTS-isolating regression test in `test_history_reader.py:TestSearch`
   (seed via `record_correction`, assert `search("BUG-490", kind="correction")`
   returns rows, not `[]`).
4. Add a hyphen-specific case to `test_history_context_cli.py:TestHistoryContextWithMatches`
   that isolates the FTS path from the LIKE fallback.
5. If `session_store.search()` is changed, add a `TestSearch` case in
   `test_session_store.py` covering hyphenated-ID input.
6. Sweep docs for hyphenated-ID example accuracy: `docs/reference/API.md:6980-6988`,
   `docs/reference/CLI.md` (`ll-history-context` + `ll-session search`),
   `docs/guides/HISTORY_SESSION_GUIDE.md`.

## Impact

Medium. Isolated, high-confidence, ~1-line fix plus a test. Every hyphenated
issue ID (i.e. every real ID) currently gets zero historical context, silently
lowering the quality of `ready-issue` / refine triage that depends on
`ll-history-context`. No data loss, but a persistent invisible degradation.

## Status

open — captured from consumer-project run findings (sprint base-branch mismatch
investigation). Independent of sibling issues FEAT-2652 / ENH-2653; can ship on
its own.


## Resolution

Fixed by adding `fts_phrase(query)` in `session_store.py` (double-quote wrap +
`"`→`""` escaping) and applying it in both `history_reader.search()` MATCH
branches and `session_store.search()`. Hyphenated issue IDs are now matched as
literal FTS5 phrases instead of being parsed as column-filter/negation operators,
so `ll-history-context BUG-490` returns matches rather than a swallowed
`OperationalError`. Regression coverage in `test_history_reader.py::TestSearch`,
`test_session_store.py::TestSearch`, and an FTS-isolating CLI case in
`test_history_context_cli.py`. Docs updated in `API.md`. Full suite: 15057 passed.

## Session Log
- `/ll:manage-issue` - 2026-07-15T23:04:47 - `8d207819-80f4-4de9-af1a-ed38c3beaa7b.jsonl`
- `/ll:ready-issue` - 2026-07-15T22:58:34 - `87a165b4-4762-4e11-887d-3eb75a1e0d5f.jsonl`
- `/ll:confidence-check` - 2026-07-15T22:57:29 - `de21a72d-506f-4864-a918-a82e774b3296.jsonl`
- `/ll:wire-issue` - 2026-07-15T22:56:24 - `607ab690-33c9-449f-b8a4-cf4eb8473483.jsonl`
- `/ll:refine-issue` - 2026-07-15T22:50:43 - `89365727-60ed-44bd-bf28-511c7698787b.jsonl`
