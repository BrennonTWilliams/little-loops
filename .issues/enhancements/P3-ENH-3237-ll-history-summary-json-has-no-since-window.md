---
id: ENH-3237
type: ENH
title: '`ll-history summary --json` has no `--since`, so downstream tools query history.db
  directly'
priority: P3
status: done
testable: true
discovered_commit: c01ee04200af9190db777a8b60a942e693a43e32
discovered_branch: main
discovered_date: 2026-08-17 18:30:00+00:00
discovered_by: little-loops-hermes
completed_at: '2026-08-17T23:20:17Z'
confidence_score: 90
outcome_confidence: 75
labels:
- enhancement
- cli
- history
- integration
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

<!-- ll-prose-ok: `--since` is the flag this issue proposes; it does not exist yet -->
`ll-history summary --json --since <DATE>` returns the same summary shape
restricted to the window, and includes loop-run counts from `loop_runs`.

Accepting `--until` for symmetry with `analyze`, and a date-only `YYYY-MM-DD`
form for consistency with `analyze --since`, both seem right but are not the
point of the request.

Whatever the shape, the useful contract for a polling consumer is that a
metric the store cannot answer is **null rather than 0** — a caller that
cannot distinguish "not recorded" from "nothing happened" will report the
first as the second, which is exactly the bug this request came out of.

_Added by pre-implementation review — 2026-08-17:_ the same contract requires
the JSON to name **which store answered**. `summary` reads `issue_events` when
the DB is populated and falls back to parsing issue *files* when it is not
(`cli/history.py:285-292`) — two sources that disagree by ~40% on this repo (the
107-vs-66 gap below). A windowed consumer that cannot tell which one it got
will silently mix them across polls. Emit `"source": "issue_events" | "files"`
alongside the counts. This does not resolve the discrepancy — that stays
deferred — it makes the deferral safe by making the number self-describing.

## Location

- **File**: `scripts/little_loops/cli/history.py`
- **Line(s)**: 66-79 (`summary` parser), 285-300 (`summary` dispatch)
- **Anchor**: `in HistoryCLI.build_parser()` / `in HistoryCLI.run()`

## Implementation Steps

_Reordered by pre-implementation review — 2026-08-17. Step 1 was previously step
2's parenthetical; it must come first because every later step depends on it,
and implementing the old step 2 as written introduces the very defect step 5
tests for. See Program Design > The fallback trap._

1. **Fix the fallback trigger before adding any window.** `cli/history.py:285-292`
   currently reads `issues = scan_completed_issues_from_db(db); if not issues:
   issues = scan_completed_issues(issues_dir)` — it falls back on *zero rows*,
   not on *no database*. Change the trigger to "DB absent or unqueryable" so an
   empty result is a real answer. Without this, a legitimately empty window
   silently falls through to an unfiltered file scan.
2. Add `--since` (and optionally `--until`) to `summary_parser`
   (`cli/history.py:66-79`), matching `analyze`'s `-S` short flag and
   `YYYY-MM-DD` metavar (`:119-130`).
3. Apply the window filter. With step 1 done, `scan_completed_issues_from_db`
   (`issue_history/parsing.py:411`) is a safe place for it; the file-parsing
   path must apply the same window so the two sources stay comparable.
4. Extend the summary shape with loop-run counts for the window from `loop_runs`
   (`session_store/schema.py:557-570`), distinguishing runs *started* from runs
   *ended* in it — they are different questions and both have callers. Note
   in-flight runs carry `ended_at IS NULL`, so they count as started-not-ended
   rather than as absent.
5. Emit `null`, not `0`, for anything the window cannot be computed for, and
   emit `"source"` naming which store answered (see Expected Behavior).
6. Decide and document what `velocity` / `date_range_days`
   (`issue_history/models.py:56-68`) mean under a window — see Program Design.
7. Tests covering: window boundaries; an empty window on a populated store
   (must return zeros with `source: issue_events`, **not** fall through to the
   file scan); the file-fallback path when the DB is genuinely absent; and a
   loop-run window with an in-flight run.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/issue_history/analysis.py:91` — pass the new
  `source` kwarg at its `calculate_summary(completed_issues)` call site once
  `source` becomes required. (Corrected by `/ll:ready-issue`: the previous
  citation, `scripts/little_loops/cli/issues/decisions.py`, does not call
  `calculate_summary` anywhere; this is the actual second call site.)
- Update `scripts/tests/test_issue_history_cli.py` — add `--since`/`--until` to
  both local `_parse_history_args()` parser replicas (`:21-25`, `:359-364`).
- Update `scripts/tests/test_issue_history_summary.py::TestCalculateSummary` —
  add the `source` kwarg to existing positional `calculate_summary(issues)` calls.
- Update `docs/reference/API.md` — `HistorySummary` field sketch, `calculate_summary`
  table entry, `main_history` `summary` row.
- Update `docs/guides/HISTORY_SESSION_GUIDE.md` — add a `--since`/`--until`
  example next to the existing `analyze --since` one.

## Integration Map

- **Modified**: `scripts/little_loops/cli/history.py` — `summary` parser
  (`:66-79`), dispatch (`:285-300`), and the fallback trigger at `:285-292`
- **Modified**: `scripts/little_loops/issue_history/parsing.py:411`
  (`scan_completed_issues_from_db`) — where the window filter lands
- **Modified**: `scripts/little_loops/issue_history/summary.py:21`
  (`calculate_summary`)
- **Modified**: `scripts/little_loops/issue_history/models.py:46-76`
  (`HistorySummary`) — *added by the 2026-08-17 review; previously unlisted.*
  This dataclass **is** the JSON contract: `to_dict()` at `:70-76` produces the
  `--json` payload. It has no loop-run fields today, so step 4 requires
  extending it (or introducing a sibling), and the `"source"` field lands here
  too. Its `velocity` (`:63-68`) and `date_range_days` (`:56-61`) properties
  derive from *observed* earliest/latest completion dates, not a requested
  window — see Program Design.
- **Read, not modified**: `scripts/little_loops/session_store/schema.py:557-570`
  (`loop_runs` DDL) — confirms `started_at` and `ended_at` both exist, so step
  4's started-vs-ended split is implementable as specified.
- **Downstream consumer**: `little-loops-hermes`
  `src/little_loops_hermes/db/history.py` drops its raw SQL once this exists.
  (Flagged `stale_file_ref` by `ll-issues format-check` — expected: it is a path
  in a *separate* repository, not this one, and is not meant to be git-tracked
  here.)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/analysis.py:91` — calls
  `calculate_summary(completed_issues)` positionally, feeding `HistoryAnalysis`
  (the `analyze` subcommand's summary field). Step 4's proposed signature makes
  `source` a required keyword-only argument, so this call site breaks unless
  updated alongside the primary change. (Corrected by `/ll:ready-issue`: the
  file previously cited here, `scripts/little_loops/cli/issues/decisions.py`,
  has no `calculate_summary` call at all.)
- `scripts/tests/test_issue_history_cli.py` — maintains its own standalone
  `argparse` replica of the `summary` subparser in two places (`_parse_history_args()`
  around `:21-25`, and a second inline replica around `:359-364`); both need
  `--since`/`--until` added or any new test exercising those flags through the
  local parser (rather than `main_history` directly) fails with "unrecognized
  arguments." [Agent 1/2 finding]
- `scripts/tests/test_issue_history_summary.py` — `TestCalculateSummary`
  (`:118-176`) has multiple call sites passing `calculate_summary(issues)`
  positionally; all need the new `source` kwarg once it becomes required.
  [Agent 3 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_cli.py::TestSummaryDbSource` (`:212-350`) —
  the class most directly relevant to the fallback-trigger fix (Implementation
  Step 1 / AC 2): `test_summary_uses_db_when_populated`, `test_summary_uses_live_written_db_rows`,
  and `test_summary_falls_back_to_files_when_db_empty` are the precedent to
  extend with the new "empty window on a populated store must stay DB-sourced"
  case. [Agent 3 finding]
- `scripts/tests/test_issue_history_cli.py::TestAnalyzeArgumentParsing` and
  `TestMainHistoryAnalyze` — the existing `--since`/`--until` test pattern for
  `analyze` (boundary-inclusive `>=`/`<=` on `completed_date`,
  `cli/history.py:308-317`) to mirror for `summary`'s new flags, including the
  `-S` short-form coverage in `TestAnalyzeDateArgParsing::test_analyze_since_short_form`.
  [Agent 3 finding]
- `scripts/tests/test_cli_ctx_stats.py::_populate_waste_run` (`:67-87`) — seeds a
  `loop_runs` row via `record_loop_run_summary()` (`session_store/writers.py:1415`);
  the pattern to follow for the new loop-run-window tests, including an
  in-flight run via `ended_at=None`. No existing test in the `issue_history`/
  `cli/history` suites touches `loop_runs` at all today. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `HistorySummary` dataclass field sketch, the
  `calculate_summary(issues)` function-table entry, and the `main_history`
  subcommand table row for `summary` all need updating for the new
  `source`/`loop_runs`/window fields and signature. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` (`:365-369`) — the `ll-history summary`
  usage example sits next to an existing `analyze --since` example; stale once
  `summary` gains the same flags. [Agent 2 finding]

_Lower-priority, text-format consumers (not JSON-coupled, flagged for awareness):_
`scripts/little_loops/loops/backlog-flow-optimizer.yaml` and
`scripts/little_loops/loops/evaluation-quality.yaml` both shell out to
`ll-history summary` (no `--json`) and reason over `velocity` in an LLM prompt
via the **text** formatter, not `to_dict()`; `scripts/little_loops/loops/lib/cli.yaml`
defines the reusable `ll_history_summary` fragment other loops call. None break
from the JSON-shape change, but if `format_summary_text()` also gains
window/source lines, these loops' prompt context changes. [Agent 2 finding]

## Program Design

_Added by pre-implementation review — 2026-08-17._

### Deviations

_Added by `/ll:manage-issue` — 2026-08-17._

- **`calculate_summary`'s `source` is keyword-only with a default (`source:
  str = "files"`), not the required keyword-only param the signature below
  specifies.** `source` collided as a *dataclass field default* concern too:
  dozens of call sites across the test suite construct `HistorySummary(...)`
  or call `calculate_summary(issues)` positionally without `source`, none of
  them listed in this issue's wiring inventory (only `analysis.py:91` and the
  `cli/history.py` dispatch were). Making it strictly required would have
  forced edits to every one of those unrelated call sites for no behavioral
  gain — the default reproduces the pre-ENH-3237 file-scan meaning exactly.
  The two call sites this issue actually cares about (`analysis.py:91`,
  `cli/history.py`'s `summary` dispatch) pass `source` explicitly regardless.
- **The DB-availability gate is not "DB file exists," it's "`issue_events`
  has ever recorded a transition."** Discovered during implementation:
  `ll-history`'s own `cli_event_context` (wraps every subcommand) writes a
  `cli_events` row on *every* invocation — which creates `.ll/history.db` as
  a side effect before `summary`'s dispatch runs. So `db_path.exists()` is
  true starting with the very first `ll-history` call ever made, including a
  project that has never backfilled or live-written any issue lifecycle
  data. Gating on file existence alone (as literally written in "The
  fallback trap" below) would have silently reported `total_count: 0,
  source: issue_events` for a project with real `done` issue files, the
  exact failure class this issue exists to prevent, just from the opposite
  direction. Fix: added `issue_events_ever_recorded()`
  (`issue_history/parsing.py`) — checks for *any* row in `issue_events`,
  not just `transition='done'` in the requested window — and gate on that
  instead of `db_path.exists()`.

### Signatures

- `scan_completed_issues_from_db(db_path: Path, since: date | None = None, until: date | None = None) -> list[CompletedIssue]`
  (`issue_history/parsing.py:411`) — window params added; existing callers unaffected by the
  defaults.
- `calculate_summary(issues: list[CompletedIssue], *, source: str, since: date | None = None, until: date | None = None) -> HistorySummary`
  (`issue_history/summary.py:21`) — takes the resolved source and bounds so the window can be
  recorded on the result rather than inferred from the data.
- `HistorySummary.to_dict(self) -> dict[str, Any]` (`issue_history/models.py:70`) — gains
  `source`, the loop-run counts, and the window bounds.
- `HistorySummary.velocity(self) -> float | None` (`issue_history/models.py:63`) — denominator
  semantics decided below.

### Call Path

<!-- ll-prose-ok: `--since` is the flag this issue proposes; it does not exist yet -->
`ll-history summary --json --since` → `HistoryCLI.run()` (`cli/history.py:285`) → source
selection (**the fallback trap below**) → `scan_completed_issues_from_db()`
(`issue_history/parsing.py:411`) *or* `scan_completed_issues()` on the file path → windowed
`loop_runs` query against `session_store/schema.py:557-570` → `calculate_summary()`
(`issue_history/summary.py:21`) → `format_summary_json()` → stdout.

### The fallback trap

`cli/history.py:285-292` selects its source by result-emptiness, not by source
availability:

```python
issues = scan_completed_issues_from_db(db_path)
if not issues:                                    # ← triggers on zero ROWS
    issues = scan_completed_issues(issues_dir)
```

Today that is harmless: zero `done` rows in a populated store is rare and the
file scan is a reasonable guess. **Under `--since` it becomes a defect.** A
window with no completions is the common case (ask about yesterday, ask about a
quiet week), and it returns `[]` from the DB path — which trips the fallback,
runs an unfiltered file scan, and returns an all-time file-derived summary
labeled as a window. The caller sees a large number where the truthful answer
was zero. That is the same class of failure this issue was filed to prevent, so
it must not be introduced by the fix.

Fix: gate the fallback on source availability — DB file absent, or the
`issue_events` query raising — not on row count. `scan_completed_issues_from_db`
already distinguishes these internally (`parsing.py:425-427` returns `[]` for a
missing path; `:440-443` returns `[]` on a failed read) but collapses both into
the same empty list the caller cannot interpret. Either return a sentinel that
separates "no such store" from "no matching rows", or hoist the
`db_path.exists()` check into the dispatch.

### Windowed velocity

`HistorySummary.velocity` divides `total_count` by `date_range_days`, which is
computed from the earliest and latest completion actually *observed*
(`models.py:56-68`). Under a window those are the observed dates **within** the
window, not the window's own bounds — so a `--since 2026-01-01` query on a store
whose only two completions are in March reports velocity over the March span,
not over the requested range. Both readings are defensible; the current one is
not obviously wrong, only unstated. Decide and document one:

- **Observed range** (status quo, no code change): velocity describes the burst,
  not the window. Cheap, but two callers passing the same `--since` get
  different denominators as data arrives.
- **Requested range** (denominator = the `--since`/`--until` span): stable across
  polls and comparable between windows, which is what a polling consumer wants.
  Requires threading the bounds into `HistorySummary`.

Recommend the requested range when both bounds are given, falling back to
observed when `--until` is omitted and the window is open-ended.

### Source disclosure

`to_dict()` gains `"source": "issue_events" | "files"`. This is the minimum that
keeps the deferred 107-vs-66 discrepancy from becoming a silent one: the two
sources answer different questions (`issue_events` records emitted events;
`analyze` and the file fallback scan completed issue *files*), and a consumer
polling across a fallback boundary would otherwise attribute the jump to real
activity.

## Acceptance Criteria

<!-- ll-prose-ok: `--since` is the flag this issue proposes; it does not exist yet -->
- [x] `ll-history summary --json --since YYYY-MM-DD` restricts the summary to
      the window; `--until` is accepted for symmetry with `analyze`.
- [x] The source fallback triggers on DB absence/unqueryability, **not** on zero
      rows. A test asserts that an empty window on a populated store returns
      zero counts with `source: issue_events` and does not fall through to the
      file scan.
- [x] The JSON payload names its source as `"source": "issue_events" | "files"`.
- [x] Loop-run counts for the window are included, distinguishing runs started
      from runs ended, with in-flight runs (`ended_at IS NULL`) counted as
      started-not-ended.
- [x] Metrics the window cannot answer are `null`, not `0`.
- [x] The meaning of `velocity` / `date_range_days` under a window is decided,
      implemented, and documented in `docs/reference/CLI.md`.
- [x] Default behavior is unchanged when neither flag is passed (additive).
- [x] `python -m pytest scripts/tests/` exits 0.

## Resolution

- **Action**: improve
- **Completed**: 2026-08-17
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/history.py`: `summary` subcommand gains `--since`/`-S`
  and `--until`; dispatch gates DB-vs-files on `issue_events_ever_recorded()`
  (not row count, not bare file existence — see Program Design > Deviations),
  applies the window to both the DB and file-scan paths, and computes
  windowed loop-run counts.
- `scripts/little_loops/issue_history/parsing.py`: `scan_completed_issues_from_db`
  gained `since`/`until` params and now raises `HistoryDbUnavailable` (new
  exception) on open/query failure instead of swallowing to `[]`; added
  `issue_events_ever_recorded()` and `count_loop_runs_in_window()`.
- `scripts/little_loops/issue_history/models.py`: `HistorySummary` gained
  `source`, `since`, `until`, `loop_runs_started`, `loop_runs_ended`;
  `date_range_days` uses the requested window when both bounds are given,
  else falls back to the observed span (unchanged default).
- `scripts/little_loops/issue_history/summary.py`: `calculate_summary` gained
  keyword-only `source`/`since`/`until`/`loop_runs_started`/`loop_runs_ended`
  (all defaulted, see Program Design > Deviations for why `source` isn't
  strictly required); fixed an unrelated local-variable collision with the
  new `source` param (`discovery_counts` loop was reassigning `source`).
- `scripts/little_loops/issue_history/analysis.py`: `analyze`'s
  `calculate_summary(completed_issues)` call now passes `source="files"`.
- `scripts/little_loops/decisions.py`: `generate_from_completed` catches the
  new `HistoryDbUnavailable` to preserve its pre-existing empty-list-on-failure
  behavior.
- `scripts/little_loops/issue_history/__init__.py`: exports `HistoryDbUnavailable`,
  `count_loop_runs_in_window`, `issue_events_ever_recorded`.
- `scripts/tests/test_issue_history_cli.py`, `test_issue_history_parsing.py`:
  new coverage for window boundaries, empty-window-stays-DB-sourced,
  in-flight loop runs, `HistoryDbUnavailable`, and null-vs-zero loop-run
  counts; several pre-existing tests gained `LL_HISTORY_DB` isolation — they
  were unknowingly resolving to this repo's own real `.ll/history.db` and
  only passed by coincidence of the old row-count fallback trigger.
- `docs/reference/API.md`, `docs/reference/CLI.md`,
  `docs/guides/HISTORY_SESSION_GUIDE.md`: documented the new flags, JSON
  fields, and windowed `date_range_days`/`velocity` semantics.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 19790 passed, 46 skipped)
- Lint: PASS (`ruff check`)
- Format: PASS (`ruff format --check`)
- Types: PASS (`mypy`)

## Status

- [x] done

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


## Session Log
- `/ll:manage-issue` - 2026-08-17T23:20:04 - `9448ff51-f860-44fe-b6bf-5413141537f4.jsonl`
- `/ll:ready-issue` - 2026-08-17T22:53:07 - `c6b4d94f-79ce-4851-b775-03d6da2684de.jsonl`
- `/ll:wire-issue` - 2026-08-17T21:49:12 - `0510d699-a148-43d1-84c2-d05ff33b93f2.jsonl`
- `/ll:format-issue` - 2026-08-17T21:38:25 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
