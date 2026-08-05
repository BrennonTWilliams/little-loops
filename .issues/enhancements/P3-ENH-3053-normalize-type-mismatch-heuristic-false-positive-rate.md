---
id: ENH-3053
title: normalize type_mismatch heuristic false-positives on EPIC keyword and never excludes closed issues
type: ENH
priority: P3
status: open
discovered_by: ll-issues normalize
discovered_date: 2026-08-05
captured_at: '2026-08-05T02:14:50Z'
labels:
- issues
- normalize
- heuristic
decision_needed: false
testable: true
program_design_not_applicable: true
---

# ENH-3053: normalize type_mismatch heuristic false-positives on EPIC keyword and never excludes closed issues

## Summary

`ll-issues normalize` reported 250 `type_mismatch` findings on a full-backlog scan
(2,956 issue files). Manually investigating all 68 findings at confidence >= 0.85
found the heuristic to be almost entirely noise: ~29/68 were spurious "-> EPIC"
suggestions caused by the candidate-type keyword ("epic") appearing in the title/body
because the issue is *about* the epic feature (`epic-progress`, `--group-by epic`,
"EPIC schema") rather than actually epic-shaped; ~26/68 were spurious "-> FEAT"
suggestions from over-weighting action verbs ("implement", "add", "extend") that
appear routinely in correctly-typed BUG/ENH issue prose. Only ~13/68 (all "-> BUG"
suggestions on ENH issues) had any plausible signal, and just 2 of those
(ENH-2093, ENH-2135) were arguably correct on a full read. Separately, every single
one of the 68 findings was already `status: done`, `deferred`, or `cancelled` —
reclassifying closed historical work has no practical value even where the
suggestion is right.

## Current Behavior

The `type_mismatch` check in `ll-issues normalize` counts signal keywords per
candidate type (see `.claude/CLAUDE.md` § normalize-issues Heuristics table) across
Summary/Motivation/Root Cause text, with no regard to:
- whether the matched keyword is the literal type name appearing because the issue
  documents that type's *feature area* (e.g. "epic" matching because the issue is
  about epic tooling, not because the issue should be an EPIC)
- the issue's `status` — `done`/`cancelled`/`deferred` issues get flagged and
  reported identically to `open`/`in_progress` ones, even though there is no
  actionable follow-up for closed work

This produces a large volume of low-signal findings (250 on this repo's backlog)
that a human reviewer must wade through per `/ll:normalize-issues` Step 2, when the
overwhelming majority are not worth reviewing at all.

## Expected Behavior

1. The EPIC candidate-type signal should not count a bare match of the word "epic"
   (or its keyword variants) as strongly as it does today — it needs a smarter
   signal (e.g. explicit coordination/decomposition language: "decompose into",
   "umbrella", "rollup of", "multi-issue initiative") rather than raw keyword
   frequency, since "epic" is also this project's own feature-area vocabulary.
2. `type_mismatch` findings should skip or clearly deprioritize issues whose
   `status` is `done`, `cancelled`, or `deferred` — either omit them from the
   default report, or bucket them separately from actionable (`open`/
   `in_progress`/`blocked`) findings, so `/ll:normalize-issues` Step 2 only asks a
   human to review issues where reclassification is actually actionable.

## Motivation

At the current false-positive rate, `type_mismatch` findings are effectively
unusable signal — a human (or LLM doing Step 2 review) cannot productively spot-check
250 findings per backlog scan, and the two-part cause (feature-name keyword
collision + no closed-issue filtering) is fixable without discarding the check
entirely. Improving precision here makes `/ll:normalize-issues` cheaper to run
regularly instead of something to skip past.

## Proposed Solution

TBD - requires investigation into the exact scoring implementation (likely
`scripts/little_loops/issue_normalize.py` or similar — needs codebase location) to:
- add a status filter (`done`/`cancelled`/`deferred` excluded from default
  `type_mismatch` reporting, or surfaced under a separate low-priority bucket)
- replace/augment the EPIC candidate's raw "epic" keyword count with phrase-level
  signals that don't fire on feature-name mentions

## Integration Map

### Files to Modify
- TBD - requires codebase analysis to locate the `type_mismatch` scoring logic

### Dependent Files (Callers/Importers)
- `commands/normalize-issues.md` / `skills/normalize-issues` (documents the
  heuristics table this issue proposes changing)
- `.claude/CLAUDE.md` § normalize-issues Heuristics table, if the signal-keyword
  table there needs updating to match

### Similar Patterns
- TBD - search for consistency with other closed-issue-aware filters in
  `ll-issues` subcommands

### Tests
- TBD - identify/add tests covering EPIC-keyword-collision and closed-status
  exclusion cases

### Documentation
- `.claude/CLAUDE.md` normalize-issues Heuristics table if signal definitions change

### Configuration
- N/A

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Defines the `normalize-issues` heuristics table this issue proposes revising |
| `docs/reference/API.md` | Reference for `little_loops` modules, including wherever `type_mismatch` scoring is implemented |

## Status

- [ ] Not started


## Session Log
- `/ll:capture-issue` - 2026-08-05T02:15:56 - `7d7d4b6a-30bd-4214-a516-9ddf81a651e2.jsonl`
