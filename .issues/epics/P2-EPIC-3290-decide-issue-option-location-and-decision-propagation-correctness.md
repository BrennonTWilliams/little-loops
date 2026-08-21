---
id: EPIC-3290
type: EPIC
title: decide-issue option location and decision propagation correctness
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T19:24:50Z'
labels:
- epic
- issue-parser
- decide-issue
- locate-options
- pipeline
---

# EPIC-3290: decide-issue option location and decision propagation correctness

## Summary

Six open issues — five of them filed on 2026-08-21, four split out of each other during a single
refinement session — all describe defects in one pipeline: how an issue's *enumerable options* are
located in markdown, and what `/ll:decide-issue` does with the selection once one is made. They
were unparented and cross-linked only by ad-hoc `relates_to` edges.

Five of the six touch `scripts/little_loops/issue_parser.py`; two touch
`skills/decide-issue/SKILL.md`. Scheduling them independently means repeatedly re-deriving the same
span/tier/marker semantics, and — as **BUG-3287** documents explicitly — risks **BUG-3278** growing
its own private copy of fixes that belong in the shared precedence chain.

The epic exists to make the shared boundary explicit and to fix the locator *before* the consumers
that misbehave because of it.

## Motivation

`/ll:decide-issue` is the gate between a refined issue and an implementable one. Every defect here
degrades it in a way that is invisible at the call site:

- Option spans that absorb trailing prose feed scoring agents analysis text as an option
  description (**BUG-3279**).
- Bold prose (`**Option A evidence**:`) is counted as a real option, inflating the option set with
  commentary about options (**BUG-3285**).
- The idiomatic option shape in this repo — `- **(a) Make the override real.**` — matches **zero**
  tiers, and any tier match anywhere in the section hides a co-located prose decision directive.
  Measured over the live corpus: **6 issues** are misparsed today with no code change required
  (**BUG-3287**).
- Shared subject vocabulary is treated as option-discriminating, firing `unapplied_decision`
  against ordinary terms — ~23 spurious reports on ENH-3277 alone (**BUG-3289**).
- `decision_needed: false` is written unconditionally even when only the highest-precedence
  decision point was ever extracted, so downstream `/ll:wire-issue`, `/ll:ready-issue`, and
  `/ll:manage-issue` treat a partly-decided issue as settled (**BUG-3278**).
- Prose recommending a *losing* option survives the decision verbatim, so the file ships with
  implementation steps for work that was decided against (**ENH-3280**).

The first four are locator defects; the last two are consumer defects that inherit them.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` (`:2134`),
  `_locate_directive_alternatives` (`:2062`), `_OPTION_PATTERNS`, `_option_block_spans`,
  `_iter_option_blocks`, `_decision_identifiers` (`:1351`), `_unapplied_decision` (`:1530`).
  Shared by BUG-3279, BUG-3285, BUG-3287, BUG-3289, and read by BUG-3278.
- `skills/decide-issue/SKILL.md` — Phases 4, 6, 7, 7b (BUG-3278, ENH-3280).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/` — `locate-options`, `check-decidable`, `format-check`
  entry points that surface the locator's output.
- `/ll:wire-issue`, `/ll:ready-issue`, `/ll:manage-issue` — downstream consumers of
  `decision_needed`.

### Tests
- `scripts/tests/test_issue_parser.py` — `TestUnappliedDecision` (`:4757`),
  `TestUnappliedDecisionLiveCorpusSweep` (`:5005`).
- `scripts/tests/test_issue_parser_unresolved.py` — `TestLastOptionSpanBoundary` (`:817`).

### Documentation
- `docs/reference/CLI.md` § `ll-issues locate-options` / `check-decidable` if the precedence
  chain's contract changes.

## Impact

- **Priority**: P2 — the highest child priority. Not user-facing breakage, but it corrupts the
  input to every decision the issue pipeline makes, with measured live misparses (6 issues for
  BUG-3287, ~23 spurious reports for BUG-3289).
- **Effort**: Medium-Large — five of six touch one file, which makes the chain serial but each
  step small. BUG-3278 and ENH-3280 are the two substantial items.
- **Risk**: Medium — `issue_parser.py` is load-bearing for the whole `.issues/` corpus, and the
  span semantics have already been reopened once. The live-corpus sweep tests are the safety net.

## Children

Implementation order is bottom-up: locator primitives, then the decision model, then propagation.

- **BUG-3279** (P2) — last option's span runs to section end and absorbs trailing prose. **The
  parser fix already landed in `f39a417e`**; the issue is reopened for residual *test-only* work
  (an ENH-2692 new-report-direction fixture, and a corpus-sweep invariant test). Its item 3 was
  split out as BUG-3289. Verify remaining scope before scheduling — it is much smaller than its
  `size: Large` suggests.
- **BUG-3285** (P3) — `bold_label` matches by prefix only, so `**Option A evidence**:` and
  `**Option B was already applied**:` are spanned as options. Widens the option set incorrectly;
  **blocks BUG-3289**, whose measurement depends on clean spans.
- **BUG-3287** (P2) — two defects in the shared precedence chain: a tier match anywhere preempts
  the Pattern E directive heuristic, and the `bullet` tier cannot see a bold-wrapped marker.
  **Sequence before BUG-3278** — BUG-3278 otherwise re-fixes both inside its own new group
  iterator rather than consuming a corrected chain.
- **BUG-3289** (P3, `blocked_by: BUG-3285`) — `_decision_identifiers` extracts every backticked
  span >= 3 chars as option-discriminating, with no filter for the issue's shared vocabulary.
  Candidate rule already recorded: subtract identifiers appearing in the title/Summary or in any
  section preceding `## Proposed Solution`.
- **BUG-3278** (P2) — introduces the **decision group** model: one group per decision point,
  resolved as a unit, so `decision_needed` is cleared only when every group is settled. The first
  consumer-side fix, and the largest.
- **ENH-3280** (P2, `blocked_by: BUG-3279`, `depends_on: BUG-3278`) — reconcile the rest of the
  document against the selection instead of writing only the three existing markers. Genuinely
  last.

Dependency edges declared in frontmatter: `BUG-3285 -> BUG-3289`, `BUG-3279 -> ENH-3280`,
`BUG-3278 -> ENH-3280`. The BUG-3287-before-BUG-3278 ordering is a *design* preference recorded in
BUG-3287's own body, not a hard block.

## Goal

`/ll:decide-issue` sees exactly the options an author wrote — no absorbed prose, no commentary
counted as an option, no idiomatic shape unreachable, no directive preempted — and a decision it
records is complete and propagated through the whole document.

## Scope

In scope: the six children above; the option-location precedence chain and its span semantics; the
decision-group model and its propagation into the issue body.

Out of scope: the priority-source drift in `IssueParser` (**BUG-3286**, independent); evidence-quote
validation (**BUG-3282** / **ENH-3283**); `blocked_by` promotion in refine-issue (**ENH-3284**); any
change to how issues are *scored* once options are correctly located.

## Success Criteria

- [ ] All six children are `done` or `cancelled`.
- [ ] `- **(a) …**` bullet options and co-located Pattern E directives both resolve on the live
      `.issues/` corpus; the 6 issues BUG-3287 measured as preempted no longer are.
- [ ] `_unapplied_decision` fires no report attributable to shared subject vocabulary across the
      live corpus.
- [ ] An issue with two decision points retains `decision_needed: true` until both groups resolve.
- [ ] `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `.claude/CLAUDE.md` § Issue File Format — status/supersession semantics the decision model writes into.
- `docs/reference/CLI.md` § `ll-issues locate-options` — the locator's documented contract.

## Status

**Open** | Created: 2026-08-21 | Priority: P2
