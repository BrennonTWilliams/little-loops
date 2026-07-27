---
id: FEAT-2867
title: Measure rework rate as the quality-adjustment term on batch throughput
type: FEAT
priority: P2
status: open
discovered_by: epic-review
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- observability
---

# FEAT-2867: Measure rework rate as the quality-adjustment term on batch throughput

## Summary

EPIC-2856 opens by stating that nothing in little-loops "measures or reduces the
share of that work that has to be redone," and its Impact section promises to
convert batch throughput "from a volume metric into a quality-adjusted one." No
child delivers the measurement. FEAT-2855 measures *codebase maintainability* —
whether the repo is getting harder to change — which is a different quantity
from rework.

Measure rework directly: what share of closed issues came back. This is the
epic's own success criterion, and without it "did the design gate reduce rework"
is unanswerable.

## Motivation

Rework is the epic's subject and its unit of success, and it is the cheapest
thing in the set to compute — `.ll/history.db` already carries the raw material:

- `commit_events` (`commit_sha` UNIQUE, `issue_id`, `files_json`) already
  attributes commits to issues via `record_commit_event()` / `_infer_issue_id()`,
  read through `history_reader.py::recent_commit_events()`.
- Issue status transitions and closure metadata are already on disk and mirrored
  into the store.

No `git log --numstat` parsing, no rename detection, no new subprocess
machinery — the things that make FEAT-2855 the largest child. This is joins and
ratios over data that already exists, which is why it should sequence **first**,
not last: it is the baseline the other three children are measured against.

## Current Behavior

`ll-history` and the `issue_history` package report agent *outcome* quality —
success rate, retries, corrections, cost, rejection-rate trends
(`quality.py::analyze_rejection_rates()`), coupling and hotspot analysis over
paths mentioned in issue markdown. A repo-wide grep for `rework` or `reopen`
across `issue_history/` and `history_reader.py` returns nothing. Batch
throughput is reported as a raw closed-issue count with no quality-adjustment
term, so a run that closes many issues badly and a run that closes fewer issues
well are indistinguishable in the output.

## Expected Behavior

An `ll-history` subcommand reports reopen rate, follow-up rate, touch-back rate,
and revert rate as a time series across sampling windows, each with an
`improving` / `stable` / `degrading` verdict against an earlier window, and each
window labeled by the orchestrator that produced the work. Alongside the raw
closed-issue count it reports a quality-adjusted figure discounted by the
window's rework share, with the two visibly distinguished. Windows below the
minimum-sample threshold report "insufficient history" rather than a computed
ratio, low-attribution-coverage windows say so, and the output states that
orchestrator attribution is correlational. Everything is read-only and LLM-free.

## Proposed Change

Compute a small set of rework signals over closed-issue history and report them
as a time series with the same improving / stable / degrading verdict vocabulary
the codebase already uses.

Candidate signals:

- **Reopen rate** — share of issues that moved to `done` and later left it
  (reopened, or superseded by a replacement declaring `supersedes:`).
- **Follow-up rate** — share of closed issues that acquire a new BUG within N
  days naming the same files, joined via `commit_events.files_json`.
- **Touch-back rate** — share of closed issues whose files are modified again
  within N days by a *different* issue. Distinguishes "came back to the same
  code" from "came back to the same ticket."
- **Revert rate** — commits attributed to an issue that are later reverted.
  **First cut is message-lineage only**: `commit_events.message` already stores
  full commit messages, so `git revert`'s "This reverts commit <sha>" lineage is
  a pure in-store query joined through the SHA→issue reverse lookup — no `git
  log` parsing. Diff-inverse detection (a commit whose diff undoes an earlier
  one without `git revert`) is expensive and fuzzy; it is explicitly deferred to
  a follow-up, not quietly in scope.

Output:

1. An `ll-history` subcommand reporting each signal as a time series across
   sampling windows.
2. Windows labeled by the orchestrator that produced the work (`ll-auto` /
   `ll-parallel` / `ll-sprint` / interactive) so batch and hand-driven work can
   be compared.
3. A quality-adjusted throughput figure: issues closed per window, discounted by
   the window's rework share, alongside the raw count — so the two numbers are
   visibly different quantities.

## Design Notes

- **Reuse, don't parallel-build.** Home this under the existing `ll-history` CLI
  as a subcommand (the same call FEAT-2855 makes), not a new top-level entry
  point. Both features are `ll-history` subcommands over the same store.
- **Verdict vocabulary is already fixed**: `improving` / `stable` / `degrading`,
  per `analyze_rejection_rates()` in `issue_history/quality.py` (~L197), which
  buckets a metric by period and compares the most recent window against the
  earliest with ratio thresholds. Mirror that shape; do not invent a fourth
  value (note FEAT-2855's own advisory flagged a `"flat"` synonym as drift).
- **Minimum-sample guard.** Follow `issue_history/debt.py`'s convention: below
  threshold, silently default the field or report "insufficient history" —
  never raise, and never emit a confident ratio computed from three issues.
- **Attribution is correlational**, exactly as FEAT-2855 states for its own
  windows. A window labeled `ll-auto` is not a claim `ll-auto` caused its rework
  rate. Say so in the output.
- **Read-only against every source**, including `.ll/history.db`. Use
  `history_reader.py::_connect_readonly()` rather than re-implementing the
  URI-mode connect; `issue_history/evolution.py::_open_db()`'s
  `PRAGMA query_only = ON` is the stricter variant.
- **A reverse commit→issue lookup does not exist yet.** `history_reader.py` has
  `recent_commit_events(branch, issue_id, ...)` but no SHA→issue direction; it
  is a trivial `SELECT issue_id FROM commit_events WHERE commit_sha = ?`
  addition, needed by the revert-rate signal.
- **Attribution coverage is itself a reportable number.** Rework ratios computed
  over a window where most commits carry no `issue_id` are unreliable in a way
  the ratio alone doesn't show. Report the share of the window's commits that
  were attributable, so a low-coverage window is visibly weak evidence rather
  than a clean-looking figure.
- **Reopen detection reads `issue_events`, and its dedup shapes what is
  countable** (verified 2026-07-27). `session_store.py`'s `issue_events` table
  records per-transition rows (written by the EventBus producer and
  `ll-issues set-status`), so "reached `done` and later left it" is detectable
  from transition history — current-status-only issue files are not the source.
  Two caveats the implementation must respect: (1) rows are idempotent per
  `(issue_id, transition)`, so a *second* done→open→done cycle on the same issue
  collapses into the first — reopen rate counts "issues that ever reopened," not
  reopen *events*; state that in the output. (2) Retroactive coverage extends
  only as far as backfilled/mirrored transition history; a pre-intervention
  window with sparse `issue_events` coverage should surface through the same
  attribution-coverage reporting rather than reading as a clean zero.
  Supersession-based rework (`supersedes:` edges) is fully retroactive either
  way.
- Cancelled-as-superseded is rework, deferred is not. ENH-2829's model — a
  superseded issue is `cancelled`, the replacement declares `supersedes:` — is
  the edge to follow; do not treat every `cancelled` as rework, and do not count
  `deferred` (the issue was never delivered, so nothing was redone).

## Acceptance Criteria

- [ ] Each rework signal is computed as a time series across sampling windows
      over `.ll/history.db` plus on-disk issue state.
- [ ] The command ships as an `ll-history` subcommand, not a new top-level CLI.
- [ ] Each signal reports a verdict using the existing
      `improving` / `stable` / `degrading` vocabulary, with magnitude and the
      window compared.
- [ ] Windows are labeled by the orchestrator that produced the work.
- [ ] Quality-adjusted throughput is reported alongside the raw closed-issue
      count, with the two visibly distinguished.
- [ ] The share of the window's commits that were issue-attributable is reported,
      so low-coverage windows are visibly weak evidence.
- [ ] Supersession (`cancelled` + a replacement declaring `supersedes:`) counts
      as rework; `deferred` does not.
- [ ] A window below the minimum-sample threshold gets an explicit
      "insufficient history" result, not a computed ratio.
- [ ] Output states that orchestrator attribution is correlational.
- [ ] All sources are opened read-only; no source DB or repo state is mutated.
- [ ] Revert rate is computed from `commit_events.message` revert lineage only;
      no diff-inverse comparison ships in this issue.
- [ ] Reopen rate is computed from `issue_events` transition history, counts
      issues (not reopen events, per the dedup caveat), and the output labels it
      accordingly.
- [ ] No LLM calls.
- [ ] Tests cover: a synthetic history with injected rework, one with injected
      improvement, a flat history, a below-threshold history, and a
      low-attribution-coverage window.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — new subparser + dispatch branch in
  `main_history()`, following the `analyze` subcommand's shape (arg block +
  `resolve_history_db()` + lazy import + multi-format print). Dispatch is a
  sequential `if args.command == ...` chain (L242/258/296/313/373), so the
  addition is purely additive
- `scripts/little_loops/history_reader.py` — add the SHA→issue reverse lookup
  the revert signal needs
- `scripts/little_loops/issue_history/__init__.py` (L65-207) — re-export the new
  module's public functions, per package convention

### New Files
- `scripts/little_loops/issue_history/rework.py` — sibling to `quality.py` /
  `coupling.py`; signal computation, minimum-sample guard, verdict
  classification

### Dependent Files (Reused Infrastructure)
- `scripts/little_loops/session_store.py` `commit_events` table (schema ~L677) —
  the commit ↔ issue attribution this feature joins on
- `scripts/little_loops/history_reader.py:_connect_readonly()` (~L417) —
  read-only DB idiom
- `scripts/little_loops/issue_history/quality.py:analyze_rejection_rates()`
  (~L197) — verdict ratio-threshold pattern to mirror
- `scripts/little_loops/issue_history/debt.py` — minimum-sample guard pattern
  (silent default, not exception)
- `scripts/little_loops/issue_history/formatting.py` —
  `format_analysis_{json,yaml,markdown,text}()` multi-format dispatch
- `scripts/little_loops/issue_parser.py:superseded_by()` — derived supersession
  edge (ENH-2829); do not hand-read a `superseded_by` frontmatter field

### Similar Patterns
- `scripts/tests/test_issue_history_advanced_analytics.py::TestAnalyzeRejectionRates`
  (~L1389) — verdict-string assertion shape: construct with known inputs, call
  `to_dict()`, assert a plain string literal rather than doing tolerance math in
  the test
- `scripts/tests/test_cli_history.py` (`TestHistoryAnalyzeYaml` /
  `TestHistoryRootSubcommand`, ~L46-130) — CLI end-to-end pattern; function-local
  imports in `main_history()` mean mocks must target the *source* module, not
  `little_loops.cli.history.*`. `test_root_no_db_returns_1` is the shape for the
  minimum-history guard path

### Tests
- `scripts/tests/test_cli_history.py` — new subcommand coverage
- `scripts/tests/test_issue_history_advanced_analytics.py` — signal computation
- New test module for the synthetic-history scenarios

### Documentation
- `docs/reference/CLI.md` (`### ll-history`, ~L2078) — new `####` subsection
  following the per-subcommand format
- `docs/reference/API.md` (`main_history()`, ~L4028)
- `.claude/CLAUDE.md` `ll-history` line (~L212-213) **and**
  `scripts/little_loops/init/writers.py` (~L108) — the description is duplicated
  verbatim; both must change together or they drift
- `skills/analyze-history/SKILL.md` — "When to Activate" bullets (~L16-24) and
  the intent-mapping table (~L96-103); add a rework trigger phrase or the skill
  won't surface it

### Relationship to FEAT-2855
Complementary, not overlapping. FEAT-2855's subject is the **repository** (is it
getting harder to change, from `git log` structure). This feature's subject is
the **work** (what share of it came back, from issue and commit attribution).
Both land as `ll-history` subcommands over the same store and should share the
verdict vocabulary and minimum-sample conventions.

## Use Case

A maintainer finishes a week of unattended `ll-auto` batches and wants to know
whether the throughput was real. Today the available answer is "N issues
closed." They run the new subcommand and get: N closed, N′ quality-adjusted, the
reopen / follow-up / touch-back / revert rates behind the discount, each with an
improving-stable-degrading verdict against the prior window, the share of the
window's commits that were attributable, and a note that orchestrator
attribution is correlational.

The second use case is the epic's own: after ENH-2852's design gate ships and
its cutover SHA is stamped at `.ll/program-design-cutover.json`, the same command answers "did the
gate reduce rework" by comparing the windows either side of that stamp. Without
this feature that question has no instrument.

## Impact

Supplies the epic's success measurement. EPIC-2856 promises to convert batch
throughput "from a volume metric into a quality-adjusted one" — this is the
quality-adjustment term. It is also the cheapest child to build (joins and
ratios over `commit_events` attribution that already exists; no `git log`
parsing, no rename detection, no new subprocess machinery), which is why it
sequences first: every other child's effect is measured against the baseline it
establishes.

## Status

**Open** | Created: 2026-07-27 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): this issue and FEAT-2855 both add
an `ll-history` subcommand and both edit the same duplicated anchors
(`.claude/CLAUDE.md` ~L212-213 **and** `scripts/little_loops/init/writers.py`
~L108; `skills/analyze-history/SKILL.md` "When to Activate" ~L16-24 and the
intent-mapping table ~L96-103). Subcommand names are reserved as
**`ll-history rework`** (this issue) and **`ll-history trend`** (FEAT-2855).
FEAT-2867 lands first and establishes the shared scaffolding — the SHA→issue
reverse lookup in `history_reader.py`, the verdict vocabulary, the
minimum-sample guard, and the docs/skill anchors. FEAT-2855 extends those
anchors rather than re-authoring them.

Window boundaries here derive from commit timestamps. If ENH-2866's dequeue-SHA
stamp has landed, prefer it as the window boundary — an additive refinement, not
a prerequisite. The ENH-2852 cutover stamp at `.ll/program-design-cutover.json`
(`{"sha": ..., "date": ...}`; path/schema pinned in ENH-2852's Design Notes) is
a shared consumer contract with FEAT-2855.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:09 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
