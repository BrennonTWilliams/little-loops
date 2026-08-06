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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

**Option A**: Reuse the existing two-value `_TERMINAL_STATUSES` convention (`done`, `cancelled`) already established in `scripts/little_loops/issue_progress.py:12-14` and duplicated in `scripts/little_loops/cli/issues/epic_consistency.py:16-17`. Consistent with every other terminal-status precedent in this codebase and with `.claude/CLAUDE.md`'s "Deferral discriminator" note that `deferred` is non-terminal — but does not fully satisfy this issue's own Expected Behavior wording, which asks to also exclude/deprioritize `deferred` issues.

**Option B**: Introduce a three-value status set (`done`, `cancelled`, `deferred`) scoped specifically to `type_mismatch` filtering, matching this issue's Expected Behavior text exactly. Diverges from every existing terminal-status precedent in this codebase, but can be scoped narrowly to this one check's reporting loop rather than touching the shared `_TERMINAL_STATUSES` constant.

> **Selected:** Option B — a scan-local three-value status set matches this issue's Expected Behavior exactly and avoids widening the shared `_TERMINAL_STATUSES` constant, which is load-bearing elsewhere (dependency-graph resolution, BUG-2897).

**Recommended**: Option B for the status filter itself — this issue's own measured false-positive data (68/68 findings on this repo's backlog were already `done`/`deferred`/`cancelled`) and its Expected Behavior section explicitly name `deferred` alongside `done`/`cancelled`, and a scan-local set avoids destabilizing the shared `_TERMINAL_STATUSES` constant's existing (narrower) meaning elsewhere.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-05.

**Selected**: Option B — scan-local three-value status set (`done`, `cancelled`, `deferred`)

**Reasoning**: Option A's two-value `_TERMINAL_STATUSES` convention is well-established but semantically narrower than this issue requires — every live caller of that shared constant deliberately treats `deferred` as non-terminal (a contract `issue_parser.find_issues_for_graph()` and BUG-2897 depend on), so reusing it as-is would fail to exclude `deferred` findings per this issue's own Expected Behavior. Option B's local set has direct precedent in `find_issues(status_filter=...)`'s established pattern of accepting arbitrary inline sets (`sweep_stale_refs.py:170`, `sequence.py:128`, `deferred_triage.py:83`) and in `show.py:521`'s own divergent, module-local `_TERMINAL_STATUSES`, so it introduces no new infrastructure while avoiding any ripple into dependency-graph resolution.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |
| Option B | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: Reuses an established constant, but every existing caller of `issue_progress._TERMINAL_STATUSES` treats `deferred` as non-terminal by design (BUG-2897), so it under-filters relative to this issue's Expected Behavior without further modification.
- Option B: Reuses the well-trodden `find_issues(status_filter=<local set>)` mechanism and mirrors `show.py`'s existing divergent local `_TERMINAL_STATUSES` precedent; scoped narrowly to the `type_mismatch` loop with no ripple to shared dependency-graph semantics.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- The `type_mismatch` check lives in `scripts/little_loops/cli/issues/normalize.py`: keyword table `_TYPE_SIGNALS` (lines 37-78), compiled patterns `_KEYWORD_RES` (86-89), section scoping `_CLASSIFY_SECTIONS` (177-182), scoring function `classify_type()` (185-216), confidence cutoff `_TYPE_MISMATCH_CONFIDENCE_CUTOFF` (line 80), and the reporting loop in `scan_normalize()`'s type_mismatch block (358-376), which iterates `find_issues(config, status_filter=set(_ALL_STATUSES))` (line 249) with no status-based exclusion anywhere in that loop. `_print_findings()`'s type_mismatch branch is at lines 492-496.
- The EPIC keyword already carries a targeted exclusion: `re.escape(kw) + r"(?!-\d)"` (lines 82-89) suppresses matches on `EPIC-1234`-style ID cross-references. This does not cover the bare-"epic"-in-feature-area-prose case this issue reports ("epic-progress", "--group-by epic", "EPIC schema") — those matches have no trailing `-\d` and still count.
- `_CLASSIFY_SECTIONS = ("Summary", "Motivation", "Current Behavior", "Root Cause")` (177-182) is already an allowlist of sections (a whole-file scan was tried and rejected per the comment at 172-176 for a near-100% false-positive rate) — the section-scoping half of this issue's problem is already handled. What remains unhandled is word-level disambiguation within those allowed sections.
- Two conflicting status-set precedents exist for a terminal-status exemption: the canonical `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` in `scripts/little_loops/issue_progress.py:12-14`, and a locally duplicated copy of the same two-value set in `scripts/little_loops/cli/issues/epic_consistency.py:16-17` (used to gate a different EPIC-consistency sub-check). Both treat `deferred` as non-terminal, consistent with `.claude/CLAUDE.md`'s "Deferral discriminator" note. `scripts/little_loops/hooks/sweep_stale_refs.py:170` shows a narrower single-value `status_filter={"done"}` is also an established shape via `find_issues()`'s `status_filter=` kwarg — so `{"done"}`, `{"done","cancelled"}`, and `{"done","cancelled","deferred"}` are all mechanically available choices, not just the two already in use. See § Proposed Solution for the resulting decision point.
- Precedent for word-level disambiguation (relevant to "a smarter EPIC signal" rather than raw keyword frequency): `scripts/little_loops/issue_parser.py:889-901` (`_BEHAVIOR_PARITY_SCOPE_H2_SECTIONS`, an allowlist of section names), `scripts/little_loops/text_utils.py:127` (`_PLANNED_NEW_RE`, a fixed-marker regex), and `scripts/little_loops/issues/prose_deps.py:21-32` (`_PHRASE_RE`, fixed canonical phrases only) all use fixed-marker or section-allowlist scoping, not free-text verb/phrase frequency detection. `.issues/bugs/P2-BUG-3063-stale-symbol-ref-fires-on-forward-looking-design-claims.md` documents an explicitly rejected "creation-verb discriminator" for a sibling gap kind, citing false-negative risk from fuzzy verb matching as the reason — directly relevant to this issue's proposed "explicit coordination/decomposition language" idea for EPIC.
- No dedicated test coverage exists for `classify_type()`/`type_mismatch` today — the only `type_mismatch` hit anywhere in `scripts/tests/` is an unrelated FSM-fragment-binding test (`test_fsm_validation_structural.py:1683`). `scripts/tests/test_ll_issues_normalize.py` has reusable scaffolding: `_NORMALIZE_CONFIG` (17-29), `normalize_dir` fixture (32-40), `_issue_body()` (53-63, hardcodes `status: open` at line 59 with no status-override param today), `_write()` (47-50), `_invoke()` (66-76). `scripts/tests/test_ll_issues_format_check.py::TestMissingBehaviorParity` (paired tests at lines 875 and 972, "fires inside scope" / "does not fire outside scope") is the structural template this codebase already uses for this shape of scoping test.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Defines the `normalize-issues` heuristics table this issue proposes revising |
| `docs/reference/API.md` | Reference for `little_loops` modules, including wherever `type_mismatch` scoring is implemented |

## Status

- [ ] Not started


## Session Log
- `/ll:decide-issue` - 2026-08-06T04:15:41 - `2ccb54ed-3c09-40c8-a5de-ca5f2244d26f.jsonl`
- `/ll:refine-issue` - 2026-08-06T04:09:47 - `4b855c62-651d-448c-a114-23d7b08f1bd8.jsonl`
- `/ll:capture-issue` - 2026-08-05T02:15:56 - `7d7d4b6a-30bd-4214-a516-9ddf81a651e2.jsonl`
