---
discovered_commit: c01ee04200af9190db777a8b60a942e693a43e32
discovered_branch: main
discovered_date: 2026-08-17T18:30:00Z
discovered_by: little-loops-hermes
confidence_score: 90
outcome_confidence: 75
status: open
---

# ENH-3237: `ll-history summary --json` has no `--since`, so downstream tools query `history.db` directly

## Summary

`ll-history summary --json` is all-time only. There is no way to ask any
`ll-history` subcommand "how much happened in the last N days" and get machine-
readable counts of both issue transitions *and* loop runs, so a consumer that
needs a window opens `.ll/history.db` and writes its own SQL against this
project's schema.

That consumer exists today: `little-loops-hermes` reads `issue_events` and
`loop_runs` directly from `.ll/history.db` to populate the activity window in
its portfolio and briefing tools (`src/little_loops_hermes/db/history.py`).
It is read-only and defensive, but it is coupled to column names and
transition vocabulary that this repo is free to change without notice.

## Motivation

A private schema with an external reader is a schema that breaks someone
silently. The reader cannot be told when `issue_events.transition` gains a
value or `loop_runs` gains a column, and the failure mode is not a crash — it
is a plausible wrong number in a weekly report.

The CLI is the supported surface and already owns the semantics (which
transitions count as completed, how the dedup index affects counting). Moving
the window into it means the semantics live in one place, and the downstream
tool asks a question instead of reading a table.

## Current Behavior

- `summary` accepts `--json` and `--directory` only
  (`scripts/little_loops/cli/history.py:66-79`). No date filtering.
- `analyze` accepts `--since` / `--until` / `--compare` and `--format json`
  (`scripts/little_loops/cli/history.py:107-130`), and *does* answer the
  issue half of the question. Three reasons it does not close this gap:
  1. **It does not report loop runs at all.** `loop_runs` is not exposed as
     JSON by any `ll-history` subcommand. A consumer wanting "loops run this
     week" has no CLI path.
  2. **It answers a different question than the event store does.** On this
     repo, for 2026-08-10 onward: `analyze --format json --since 2026-08-10`
     reports `total_completed: 107`, where `SELECT COUNT(*) FROM issue_events
     WHERE ts >= '2026-08-10T00:00:00Z' AND transition = 'done'` returns 66
     (66 by `date(ts)` too, and 66 distinct `issue_num` — the gap is not a
     timestamp-format artifact and not double counting). `analyze` scans
     completed issue *files*; `issue_events` records emitted events, and the
     ~41 difference is presumably issues closed by a path that does not emit
     one. Whichever is "right", a downstream tool currently has to pick
     without being told they differ.
  3. It computes trends, subsystem breakdowns and debt metrics for a caller
     that wants five integers. The direct query it displaced runs in 3-4 ms
     against a 5.8 GB store.

## Expected Behavior

`ll-history summary --json --since <DATE>` returns the same summary shape
restricted to the window, and includes loop-run counts from `loop_runs`.

Accepting `--until` for symmetry with `analyze`, and a date-only `YYYY-MM-DD`
form for consistency with `analyze --since`, both seem right but are not the
point of the request.

Whatever the shape, the useful contract for a polling consumer is that a
metric the store cannot answer is **null rather than 0** — a caller that
cannot distinguish "not recorded" from "nothing happened" will report the
first as the second, which is exactly the bug this request came out of.

## Location

- **File**: `scripts/little_loops/cli/history.py`
- **Line(s)**: 66-79 (`summary` parser), 285-300 (`summary` dispatch)
- **Anchor**: `in HistoryCLI.build_parser()` / `in HistoryCLI.run()`

## Implementation Steps

1. Add `--since` (and optionally `--until`) to `summary_parser`, matching
   `analyze`'s `-S` short flag and `YYYY-MM-DD` metavar.
2. Filter in `scan_completed_issues_from_db` (or at `calculate_summary`) by the
   window; keep the file-parsing fallback path consistent with it.
3. Add loop-run counts for the window from `loop_runs`, distinguishing runs
   *started* from runs *ended* in it — they are different questions and both
   have callers.
4. Emit `null`, not `0`, for anything the window cannot be computed for.
5. Tests covering: window boundaries, an empty window on a populated store
   (must not read as an unpopulated store), and the file-fallback path.

## Integration Map

- **Modified**: `scripts/little_loops/cli/history.py` — `summary` parser and
  dispatch
- **Likely modified**: the `scan_completed_issues_from_db` / `calculate_summary`
  pair, wherever the window filter lands
- **Downstream consumer**: `little-loops-hermes`
  `src/little_loops_hermes/db/history.py` drops its raw SQL once this exists

## Scope Boundaries

- Does **not** ask for the 107-vs-66 discrepancy to be resolved, though
  documenting which number `summary` reports would help. That is its own issue.
- Does **not** ask for webhook/`WebhookTransport` changes.

## Impact

- **Priority**: P3 - removes a schema coupling to an external reader
- **Effort**: Small-Medium - argument plumbing plus a windowed query and tests
- **Risk**: Low - additive flag; default behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `history`, `integration`
