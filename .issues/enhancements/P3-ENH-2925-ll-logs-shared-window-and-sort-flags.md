---
id: ENH-2925
title: 'll-logs: consolidate duplicated target/window flags, add --since/--until and
  count-based --sort'
type: ENH
status: done
priority: P3
captured_at: '2026-07-30T02:43:17Z'
completed_at: '2026-07-31T01:45:52Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- ENH-2317
- ENH-2130
- ENH-2926
labels:
- ll-logs
- cli-consistency
confidence_score: 92
outcome_confidence: 82
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2925: `ll-logs` — consolidate duplicated target/window flags, add `--since`/`--until` and count-based `--sort`

## Summary

`scripts/little_loops/cli/logs.py` hand-writes the same two argparse blocks
once per subcommand instead of using shared parent parsers: the
`--project`/`--all` mutually-exclusive group appears six times, and the
relative-window cutoff computation appears five times
(logs.py:575, 906, 1149, 1255, 1885). The file uses exactly one of
`cli_args.py`'s 20+ `add_*_arg` helpers (`add_json_arg`).

That duplication is the reason two real gaps have stayed open: there is no
absolute `--since`/`--until` date filter anywhere in `ll-logs` (only relative
`--window-days`), and two subcommands order output by name when the useful
order is by severity. Adding either flag in the file's current shape means
five copy-paste edits.

This issue extracts the shared parsers first, then lands the two flag gaps as
one-line-per-subcommand additions on top.

## Current Behavior

- **Duplication.** Six copies of the `--project`/`--all` mutex group
  (`extract`, `sequences`, `stats`, `scan-failures`, `dead-skills`,
  `loop-fleet`) and five copies of
  `cutoff = datetime.now(UTC) - timedelta(days=args.window_days) if ... else None`.
- **No absolute date filter.** Only relative `--window-days` exists, so a
  result set is not reproducible or comparable across days — re-running the
  same command tomorrow silently shifts the window. `cli/history.py` (`analyze`)
  is the nearest local precedent, but read it carefully before copying: `--since`
  is inside `date_filter_group` while `--until` is added to `analyze_parser`
  directly (line ~127), *outside* the group. That asymmetry is load-bearing, not
  an oversight — see the Proposed Solution.
- **`dead-skills` orders by name, not severity.** `_cmd_dead_skills`
  (logs.py:925-931) iterates `sorted(catalog_names)` and appends `never` and
  `rarely` rows interleaved, so the most severe entries are scattered through
  an alphabetical list.
- **`loop-fleet` orders loops alphabetically** (logs.py:1930) when the triage
  question it exists to answer is "which built-in loop is failing most."
- **`loop-fleet --json` is genuinely unbounded** — unlike the human table
  (bounded by loop count), the JSON branch emits one row per *run* across
  every discovered project (logs.py:1911-1927), with no cap.
- **`scan-failures` has no top-N cap** even though its clusters are already
  sorted by count descending (logs.py:1157), so the cheap triage view isn't
  available.

## Expected Behavior

1. `--project`/`--all` and the window flags come from shared `cli_args.py`
   helper functions; the cutoff is computed in exactly one place.
2. `--since YYYY-MM-DD` and `--until YYYY-MM-DD` are accepted wherever
   `--window-days` is accepted. `--since` and `--window-days` are mutually
   exclusive; `--since` and `--until` compose (a closed date range must work).
3. `dead-skills` orders by tier (`never` before `rarely`) then by invocation
   count; `--sort name` restores the old alphabetical order.
4. `loop-fleet` orders loops by success rate ascending (worst first);
   `--sort name` restores alphabetical.
5. `--limit N` caps `scan-failures` output (top N clusters by count) and
   `loop-fleet --json` output.

## Motivation

The window and sort gaps are individually small, but each one currently costs
five near-identical edits, and the duplicated `--project`/`--all` group is the
same surface ENH-2317 (deferred) has to modify for its three-way resolver.
Consolidating first means ENH-2317 changes one function instead of six, and
this issue's own additions become one line per subcommand. Landing the flags
without the consolidation makes ENH-2317 strictly harder.

The two ordering defaults are the sharper user-facing complaint: `dead-skills`
and `loop-fleet` both exist for triage, and both currently bury the rows a
maintainer opened them to find.

## Proposed Solution

Sequenced — step 1 is a prerequisite for the rest.

1. **Extract shared argument helpers into `cli_args.py`** — as `add_*_arg`
   *functions*, not argparse `parents=[...]` parsers:
   - `add_corpus_target_args(parser, *, required: bool = False) -> None` — the
     `--project`/`--all` mutex group. Preserve each subcommand's current
     `required=` behavior and help text; `eval-export` intentionally differs
     (bare `--project` defaulting to CWD, no `--all`) and must be left alone —
     that difference is ENH-2317's scope.
   - `add_window_args(parser) -> None` — `--window-days`, `--since`, `--until`.
   - `_resolve_window(args) -> tuple[datetime | None, datetime | None]` in
     `cli/logs.py` — single conversion of all three into `(cutoff, until)`,
     replacing the five inline copies.

   **Why functions, not `parents=`.** Two reasons, both blocking:

   - A parent parser is shared *by reference*, so one parent yields one
     `required=` value across all six subcommands — which directly contradicts
     this issue's own requirement to preserve each subcommand's current
     `required=` behavior. A function taking `required` as a keyword handles it
     in one line.
   - `parents=[...]` appears **nowhere** in `scripts/little_loops/cli/`. The
     established house pattern is exactly the `cli_args.py` `add_*_arg(parser)`
     family this issue's own Summary faults `logs.py` for underusing (it calls
     only `add_json_arg` of 20+). Introducing a second, competing
     argument-sharing mechanism in the same file would make the inconsistency
     worse, not better. Putting the helpers in `cli_args.py` also makes them
     reusable by ENH-2317 and by any other CLI needing a window filter.

2. **Wire `--since`/`--until`** through `_resolve_window` for `sequences`,
   `stats`, `scan-failures`, `dead-skills`, `loop-fleet`. Parse dates as
   UTC-anchored per ENH-2130's calendar-day anchor semantics, so
   `--since`/`--window-days` agree on boundary handling.

   **Mutual exclusion cannot be expressed as one argparse group.** An
   `add_mutually_exclusive_group` makes *all* members exclusive with each other,
   so putting `--window-days`, `--since`, and `--until` in one group means
   `--since X --until Y` errors out — destroying the closed date range that is
   the main reason to add the flags. This is why `cli/history.py` keeps `--until`
   outside its `date_filter_group`. Do the same: `--window-days` and `--since` in
   the mutex group, `--until` a plain argument, plus an explicit
   `since > until` check in `_resolve_window` raising `parser.error`.

   **`_resolve_window` must return a pair, not a single cutoff.** `--until` is an
   upper bound and a lone `datetime | None` cutoff cannot carry it. All five call
   sites must apply *both* bounds — a `--until` that parses but filters nothing
   is the likely failure mode here, so the ACs assert filtering behavior, not
   just flag acceptance.
3. **Fix the two sort defaults** and add `--sort` to `dead-skills`
   (`tier`/`name`, default `tier`) and `loop-fleet`
   (`success`/`name`, default `success`), mirroring `stats --sort`'s
   `choices=` shape.
4. **Add `--limit N`** to `scan-failures` and `loop-fleet`. On `loop-fleet`
   the cap applies to the per-run JSON rows, not the aggregated table.

Changes 3 and 4 alter default output ordering. That is intended (the current
order is the defect) and non-breaking for JSON consumers keying by field, but
call it out in the changelog entry and add `--sort name` as the escape hatch.

## Program Design

### Signatures

- `add_corpus_target_args(parser: argparse.ArgumentParser, *, required: bool = True, project_help: str = ..., all_help: str = ...) -> None`

  New helper in `cli_args.py`. Adds a `--project`/`--all` mutually exclusive
  group. `project_help`/`all_help` let each of the six call sites preserve its
  current per-subcommand wording.

- `add_window_args(parser: argparse.ArgumentParser, *, noun: str = "records") -> None`

  New helper in `cli_args.py`. Adds `--window-days`/`--since` as one mutually
  exclusive group, plus a standalone `--until` (outside the group, so it
  composes with either).

- `_resolve_window(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]`

  New in `cli/logs.py`. Single conversion point for all five window-flag call
  sites. Returns `(cutoff, until)` as UTC-aware `datetime` objects (built via
  `datetime.combine(date.fromisoformat(...), time.min/time.max, tzinfo=UTC)`),
  not calendar `date` objects, because every call site filters against
  `_parse_iso_timestamp()` results, which are UTC-aware. Exits via
  `sys.exit(2)` with a stderr message when `--since` resolves later than
  `--until`.

### Call Path

`_build_parser()` calls `add_corpus_target_args`/`add_window_args` once per
subcommand → `_parse_args()` → each `_cmd_*` handler calls
`_resolve_window(args)` once → passes `(cutoff, until)` into
`_extract_ll_event_streams`/`_aggregate_skill_stats`/`_collect_loop_runs` (each
gained an `until: datetime | None = None` parameter alongside the existing
`cutoff`) or, for `scan-failures`, applies both bounds as inline dict-filter
passes over `raw_clusters`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Site counts and line numbers reconfirmed against current source** (drifted
  by a few lines since discovery, all counts otherwise accurate). The six
  `--project`/`--all` mutex groups are at `logs.py:2001` (`extract`),
  `:2023` (`sequences`), `:2069` (`stats`), `:2100` (`scan-failures`),
  `:2135` (`dead-skills`), `:2213` (`loop-fleet`) — all six currently pass
  `required=True`, so the AC's per-subcommand `required=` assertion is
  trivially satisfied today but should still be written explicitly as a
  regression guard. The five cutoff sites are at `logs.py:574-578`
  (`sequences`), `:905-909` (`dead-skills`), `:1148-1152` (`scan-failures`,
  conditioned on `args.window_days is not None` rather than a ternary),
  `:1254-1258` (`stats`), `:1884-1888` (`loop-fleet`). `_cmd_dead_skills`'s
  sort loop is `logs.py:927-933`; `loop-fleet`'s unbounded `--json` branch is
  `logs.py:1909-1925`; `scan-failures`'s uncapped sorted-by-count clusters are
  `logs.py:1157-1171`.
- **`--since`/`--until` type mismatch vs. the `cli/history.py` precedent**:
  `history.py`'s `analyze` resolution (`history.py:293-309`) parses with
  plain `datetime.date.fromisoformat(...)` (calendar dates, no timezone),
  because it filters `Issue.completed_date`. `ll-logs`'s `_resolve_window`
  must instead build `UTC`-aware `datetime` objects, since the five call
  sites filter against `_parse_iso_timestamp()` results
  (`logs.py:378-395`), which are `UTC`-aware — a straight port of
  `history.py`'s date-parsing line would raise on comparison. Construct via
  `datetime.combine(date.fromisoformat(args.since), time.min, tzinfo=UTC)`
  (or equivalent) rather than reusing `history.py`'s type directly.
- **`--limit N` convention precedent already in `logs.py`**:
  `eval_export_parser.add_argument("--limit", type=int, default=0, metavar="N", help="Cap output records (0 = unlimited)")`
  (`logs.py:2195-2201`) is the file's own existing `--limit` shape — mirror
  its `0 = unlimited` default for the new `scan-failures --limit` and
  `loop-fleet --json --limit`, rather than introducing a different
  no-cap sentinel.
- **No existing `cli_args.py` helper wraps `add_mutually_exclusive_group` or
  takes a `required: bool` kwarg** — confirmed by reading all 20+ current
  `add_*_arg` helpers. `add_corpus_target_args(parser, *, required: bool = True)`
  would be the first of this shape in the file; it is a consistent extension
  of the existing "parser-mutation function, keyword-configurable" pattern
  (e.g. `add_timeout_arg`'s `default` param, `add_skip_arg`'s `help_text`
  param), not a competing mechanism. Remember to add both new helpers to
  `cli_args.py`'s `__all__` list (currently `cli_args.py:473-501`).
- **Concrete test patterns to model new regression tests after** (all in
  `scripts/tests/test_ll_logs.py` unless noted):
  - `test_sequences_project_and_all_mutually_exclusive` (`:827-834`) —
    `SystemExit` pattern for the mutex-group requirement.
  - `test_sequences_window_days_none_by_default` (`:815-819`) — plain
    default-value assertion via `_parse_args()`.
  - `test_stats_sort_default_freq` / `test_stats_sort_corrections`
    (`:1821-1831`) and the behavioral ordering test
    `test_stats_sort_by_corrections` (`:2025-2042`) — direct model for the
    new `dead-skills`/`loop-fleet` `--sort` tests (flag-parses +
    behavioral-ordering pair).
  - `test_stats_window_days_behavioral` (`:1839-1866`) — populates
    `history.db` with old/recent timestamped rows via
    `_populate_skill_events`, runs `main_logs()` with `--window-days N
    --json`, and asserts only recent rows survive; the direct model for the
    new "`--until` demonstrably filters" ACs.
  - `scripts/tests/test_issue_history_cli.py:423-446` (`test_analyze_since`,
    `test_analyze_until`, `test_analyze_date_range`,
    `test_analyze_since_defaults_none`) and
    `:668-693`
    (`test_main_history_analyze_compare_and_since_mutually_exclusive`) — the
    `--since`/`--until`/mutual-exclusivity test shapes to mirror for
    `ll-logs`, adapted to `_parse_args()` instead of a local mini-parser.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Documentation

- `docs/reference/CLI.md` — the primary `ll-logs` flag reference (`### ll-logs`,
  ~lines 2432-2564), not just `docs/reference/API.md`/`.claude/CLAUDE.md`. Its
  per-subcommand flag tables (`sequences` ~2472-2482, `stats` ~2486-2494,
  `dead-skills` ~2496-2504, `scan-failures` ~2506-2515) list `--window-days`
  only and need `--since`/`--until` rows; `dead-skills` needs a new `--sort`
  row (it has none today); `scan-failures` needs a `--limit` row; `loop-fleet`
  has no dedicated flags subsection at all and needs one added for
  `--sort`/`--limit`. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` (lines 404-405, 413-414, 422-423,
  439) — existing `ll-logs stats`/`scan-failures`/`dead-skills` example
  invocations stay syntactically valid (all current flags preserved), but the
  guide is worth a note if it describes reading `dead-skills` output in the
  old alphabetical order, since the new default is tier-then-count. Optional,
  not a forced edit. [Agent 2 finding]
- `.loops/ll-logs-telemetry-digest.yaml` (FEAT-1925 companion loop, lines 41
  and 99) calls `ll-logs scan-failures --json` and `ll-logs dead-skills
  --json` with no `--sort`/`--limit`/window flags. Not a required code edit,
  but the `dead-skills --json` row order changes from alphabetical to
  tier-then-count — worth a post-change run to confirm its downstream digest
  prompt narrative still matches the new ordering. [Agent 2 finding]
- `CHANGELOG.md` — per this repo's no-`[Unreleased]`-entries convention, the
  two default-ordering changes (`dead-skills`, `loop-fleet`) get a changelog
  entry at release-prep time under a concrete version section, not
  immediately. [Agent 2 finding]

### Tests

- `scripts/tests/test_cli_args.py` — no existing `TestAdd<Name>Arg` class
  covers a `required:` kwarg or an `add_mutually_exclusive_group` helper (the
  file's 20+ helper tests are all single-flag shapes). New
  `TestAddCorpusTargetArgs` / `TestAddWindowArgs` classes are a genuinely new
  test shape here — model the mutex-group assertion on `logs.py`'s current
  `add_mutually_exclusive_group(required=True)` usage plus
  `pytest.raises(SystemExit)` (as in `test_ll_logs.py`'s existing
  `test_dead_skills_project_and_all_mutually_exclusive`,
  `test_loop_fleet_project_and_all_mutually_exclusive`). [Agent 3 finding]
- `scripts/tests/test_cli.py`'s `TestMainLogsIntegration` (~line 2940+) — no
  case exercises `--since`/`--until`/`--sort`/`--limit` on any subcommand
  today. Add smoke cases modeled on `test_scan_failures_returns_0`
  (~2984-2997: argv + `main_logs()` + `result == 0`), combined with
  `test_issue_history_cli.py`'s `main_history()`-level since/until
  integration tests (`test_analyze_since_default_none`,
  `test_analyze_since_parsed`, `test_analyze_until_parsed`,
  `test_analyze_since_short_form`, ~lines 699-757) as the integration-level
  (not just `_parse_args()`-level) shape to mirror. [Agent 3 finding]
- No existing test in `test_ll_logs.py` asserts the *current* alphabetical
  `dead-skills`/`loop-fleet` order or an exact argparse error string for any
  of the six mutex groups — confirmed by reading all `dead-skills`,
  `loop-fleet`, and `scan-failures` test bodies. The refactor and the
  ordering-default change are both refactor-safe against the existing suite;
  this is a pure test-writing gap (new tests asserting the new default order),
  not a breaking-test risk. [Agent 3 finding]
- No test anywhere references `--limit` on `scan-failures` or `loop-fleet`
  (only `eval-export`'s existing, unrelated `--limit` has coverage) — new
  `--limit`-capping tests need to be written from scratch once the flag
  lands. [Agent 3 finding]

## Scope Boundaries

**In scope:** `scripts/little_loops/cli/logs.py` argparse construction and the
five cutoff call sites; the two new `add_*_arg` helpers in
`scripts/little_loops/cli_args.py`; ordering defaults and `--sort`/`--limit` on
`dead-skills`, `loop-fleet`, `scan-failures`; regression tests over the
affected subcommands' flag sets.

**Out of scope (detail below):** flag *resolution* semantics for
`--project`/`--all` (ENH-2317), `--skill` scoping on `stats`/`dead-skills`
(dropped), `-j` on `tail` (dropped), `-j` on `extract` (ENH-2926), and
`eval-export`'s intentionally different target-flag shape.

- **`--project`/`--all` CWD-default resolution and `--host` threading** —
  fully scoped by **ENH-2317** (deferred), including its own three-way
  resolver design. This issue only *relocates* the existing flags into a
  shared parser without changing their resolution semantics.
- **`--skill` scoping on `stats`/`dead-skills`** — deliberately dropped. On
  `stats` it duplicates `grep`/`jq` over an already-sorted one-row-per-skill
  table. On `dead-skills` a filter is actively ambiguous: the subcommand only
  emits rows *below* threshold, so `--skill X` returns empty both when X is
  healthy and when X is absent from the catalog. If a scriptable per-skill
  health gate is wanted, that is a `--check NAME` exit-code contract and
  needs its own issue. **ENH-2923**'s `scan-failures --skill` work is
  unaffected — it carries the harder tool→enclosing-skill attribution lookup
  and stands alone.
- **`-j/--json` on `tail`** — deliberately dropped. `tail` follows
  `.loops/.running/<loop>.events.jsonl`, which is already NDJSON; a JSON mode
  would reimplement `tail -f` on that file, and a streaming JSON tail
  conflicts with every other `-j` in the file being a one-shot
  `print_json(...)` document.
- **`-j/--json` on `extract`** — moved to **ENH-2926**. It is not a parity
  gap: `_cmd_extract` (logs.py:666) prints nothing at all on success, so
  there is no report to serialize. The real defect is that extract silently
  writes N session files plus an index with no accounting, which is a new
  output surface rather than `add_json_arg` wiring.

## Impact

- **Priority**: P3 — consistency/triage-ergonomics improvement, not blocking
  any workflow.
- **Effort**: Medium — one refactor plus three small additive changes, all in
  `cli/logs.py`; net line count should decrease.
- **Risk**: Low-Medium. The parent-parser extraction touches six subcommands'
  argument surfaces at once, so `scripts/tests/test_ll_logs.py` must assert
  each subcommand still accepts its prior flag set and `required=` behavior.
  Default-ordering changes on two subcommands are the only user-visible
  behavior change.
- **Breaking Change**: No — all new flags are optional; ordering changes have
  a `--sort name` escape hatch.

## Acceptance Criteria

- [x] `add_corpus_target_args` and `add_window_args` exist in `cli_args.py` and
      `_resolve_window` in `cli/logs.py`; the six duplicated mutex groups and
      five inline cutoff blocks are gone. No `parents=[...]` is introduced.
- [x] Each of the six subcommands retains its pre-refactor `required=` behavior
      on `--project`/`--all` (assert the differing cases, not just one).
- [x] `--since`/`--until` accepted on `sequences`, `stats`, `scan-failures`,
      `dead-skills`, `loop-fleet`; `--since` is mutually exclusive with
      `--window-days`; `--since X --until Y` together is **accepted** and filters
      to a closed range; `--since` later than `--until` errors out.
- [x] `--until` demonstrably filters: a record newer than `--until` is absent
      from the output of each of the five subcommands (not merely a flag-parses
      assertion).
- [x] `dead-skills` defaults to tier-then-count order; `--sort name` restores
      alphabetical.
- [x] `loop-fleet` defaults to success-ascending order; `--sort name`
      restores alphabetical.
- [x] `--limit N` caps `scan-failures` clusters and `loop-fleet --json` run
      rows.
- [x] Tests assert every affected subcommand still accepts its pre-refactor
      flag set (regression guard on the parent-parser extraction).
- [x] `python -m pytest scripts/tests/` exits 0.
- [x] `docs/reference/API.md` and `.claude/CLAUDE.md`'s `ll-logs` line reflect
      the new flags; `docs/reference/CLI.md`'s per-subcommand `ll-logs` flag
      tables gain `--since`/`--until`/`--sort` (`dead-skills`)/`--limit`
      (`scan-failures`, `loop-fleet`) rows, and `loop-fleet` gets a flags
      subsection (it has none today).
- [x] `cli_args.py`'s new `add_corpus_target_args`/`add_window_args` get
      `TestAddCorpusTargetArgs`/`TestAddWindowArgs` coverage in
      `test_cli_args.py`, and `TestMainLogsIntegration` in `test_cli.py`
      gains `--since`/`--until`/`--sort`/`--limit` integration cases.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-30_

**Readiness Score**: 92/100 → PROCEED (blocked by hard override — see Gaps to Address)
**Outcome Confidence**: 82/100 → High

### Gaps to Address
- Program Design gate (ENH-2852) is armed for this project
  (`.ll/program-design-cutover.json` stamped 2026-07-30) and this issue has no
  `## Program Design` section — the last `/ll:refine-issue` Session Log entry
  (2026-07-31) postdates the cutover, so it is not grandfathered. Populate
  `## Program Design` with concrete signatures for `add_corpus_target_args`,
  `add_window_args`, and `_resolve_window` (types are already implied by the
  Proposed Solution's prose but not stated as a signature-shaped block), or set
  `program_design_not_applicable: true` if this is judged too mechanical to
  warrant it — run `/ll:refine-issue` or `/ll:reconcile-issue` to add the
  section.

### Outcome Risk Factors
- **Breadth**: six call sites for the mutex-group extraction plus five for the
  cutoff/window extraction, spanning `cli_args.py` (two new helpers) and
  `cli/logs.py` (five subcommands) — a real multi-site refactor, not a
  single-function change.
- **Depth**: mostly mechanical relocation, but the mutex-group split
  (`--window-days`/`--since` grouped, `--until` standalone with an explicit
  `since > until` check in `_resolve_window`) and the UTC-aware date
  construction (diverging from the `cli/history.py` precedent on purpose) are
  judgment-bearing, not pure copy-paste — a naive port of `history.py`'s
  `date.fromisoformat` would raise on comparison against the UTC-aware
  timestamps the five call sites actually filter.

## Session Log
- `/ll:manage-issue` - 2026-07-31T01:45:06Z - `719fd454-91a7-4a23-a3b4-1a78b5cf4421.jsonl`
- `/ll:ready-issue` - 2026-07-31T01:19:24 - `6642fa6b-6ead-4baf-8834-6545a8ff4f95.jsonl`
- `/ll:confidence-check` - 2026-07-30T00:00:00 - `b2da1a6c-f875-4d45-9551-b8aad3626027.jsonl`
- `/ll:wire-issue` - 2026-07-31T01:15:38 - `1a7a1be1-46df-4611-b8d3-6f3606921ae6.jsonl`
- `/ll:refine-issue` - 2026-07-31T01:07:32 - `2ca560d7-7e1b-4f09-926d-e474f51c6d83.jsonl`
- `/ll:capture-issue` - 2026-07-30T02:43:17Z - `b1cb0370-8b55-4a10-a364-649e81045dd0.jsonl`
- Scope review - 2026-07-29 - dropped `--skill` (stats/dead-skills) and `-j` (tail) as low/negative value; split `extract` reporting to ENH-2926; added the parent-parser consolidation as the prerequisite.
- Pre-implementation review - 2026-07-30 - verified all counts against source (6 mutex groups, 5 cutoff sites at logs.py:575/906/1149/1255/1885 — all accurate). Replaced the `parents=[...]` mechanism with `cli_args.py` `add_*_arg` helpers: a shared parent parser cannot carry per-subcommand `required=`, and `parents=` appears nowhere in `cli/`. Split the single mutex group — `--since`+`--until` in one group would reject closed date ranges, which is why `cli/history.py` keeps `--until` outside its group. Widened `_resolve_cutoff` to `_resolve_window` returning a `(cutoff, until)` pair, and added ACs asserting `--until` actually filters.

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
