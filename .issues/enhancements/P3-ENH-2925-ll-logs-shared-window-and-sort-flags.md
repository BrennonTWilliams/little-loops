---
id: ENH-2925
title: 'll-logs: consolidate duplicated target/window flags, add --since/--until and count-based --sort'
type: ENH
status: open
priority: P3
captured_at: '2026-07-30T02:43:17Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- ENH-2317
- ENH-2130
- ENH-2926
labels:
- ll-logs
- cli-consistency
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
  argument surfaces at once, so `scripts/tests/test_cli_logs.py` must assert
  each subcommand still accepts its prior flag set and `required=` behavior.
  Default-ordering changes on two subcommands are the only user-visible
  behavior change.
- **Breaking Change**: No — all new flags are optional; ordering changes have
  a `--sort name` escape hatch.

## Acceptance Criteria

- [ ] `add_corpus_target_args` and `add_window_args` exist in `cli_args.py` and
      `_resolve_window` in `cli/logs.py`; the six duplicated mutex groups and
      five inline cutoff blocks are gone. No `parents=[...]` is introduced.
- [ ] Each of the six subcommands retains its pre-refactor `required=` behavior
      on `--project`/`--all` (assert the differing cases, not just one).
- [ ] `--since`/`--until` accepted on `sequences`, `stats`, `scan-failures`,
      `dead-skills`, `loop-fleet`; `--since` is mutually exclusive with
      `--window-days`; `--since X --until Y` together is **accepted** and filters
      to a closed range; `--since` later than `--until` errors out.
- [ ] `--until` demonstrably filters: a record newer than `--until` is absent
      from the output of each of the five subcommands (not merely a flag-parses
      assertion).
- [ ] `dead-skills` defaults to tier-then-count order; `--sort name` restores
      alphabetical.
- [ ] `loop-fleet` defaults to success-ascending order; `--sort name`
      restores alphabetical.
- [ ] `--limit N` caps `scan-failures` clusters and `loop-fleet --json` run
      rows.
- [ ] Tests assert every affected subcommand still accepts its pre-refactor
      flag set (regression guard on the parent-parser extraction).
- [ ] `python -m pytest scripts/tests/` exits 0.
- [ ] `docs/reference/API.md` and `.claude/CLAUDE.md`'s `ll-logs` line reflect
      the new flags.

## Session Log
- `/ll:capture-issue` - 2026-07-30T02:43:17Z - `b1cb0370-8b55-4a10-a364-649e81045dd0.jsonl`
- Scope review - 2026-07-29 - dropped `--skill` (stats/dead-skills) and `-j` (tail) as low/negative value; split `extract` reporting to ENH-2926; added the parent-parser consolidation as the prerequisite.
- Pre-implementation review - 2026-07-30 - verified all counts against source (6 mutex groups, 5 cutoff sites at logs.py:575/906/1149/1255/1885 — all accurate). Replaced the `parents=[...]` mechanism with `cli_args.py` `add_*_arg` helpers: a shared parent parser cannot carry per-subcommand `required=`, and `parents=` appears nowhere in `cli/`. Split the single mutex group — `--since`+`--until` in one group would reject closed date ranges, which is why `cli/history.py` keeps `--until` outside its group. Widened `_resolve_cutoff` to `_resolve_window` returning a `(cutoff, until)` pair, and added ACs asserting `--until` actually filters.

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
