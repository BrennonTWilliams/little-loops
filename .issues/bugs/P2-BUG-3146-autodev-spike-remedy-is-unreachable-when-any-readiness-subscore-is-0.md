---
id: BUG-3146
type: BUG
title: autodev spike remedy is unreachable when any readiness subscore is 0
priority: P2
status: done
testable: true
verify_verdict: NON_VALID
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-08-10'
captured_at: '2026-08-10T23:09:34Z'
completed_at: '2026-08-11T04:43:34Z'
labels:
- loops
- autodev
relates_to:
- BUG-3147
- ENH-3148
size: Very Large
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3146: autodev spike remedy is unreachable when any readiness subscore is 0

## Summary

The pre-deferral remedy dispatcher in `scripts/little_loops/loops/autodev.yaml`
(state `recheck_after_size_review`, ~line 2083) selects between the `spike` and
`reconcile` readiness remedies with:

```python
amb = int(d.get('score_ambiguity') or 0)
others = [int(d.get(k) or 0) for k in
          ('score_complexity', 'score_test_coverage', 'score_change_surface')]
print('spike' if (amb and amb < min(others)) else 'reconcile')
```

When any of the three "other" subscores is `0`, `min(others)` is `0`, so
`amb < 0` is never true and the dispatcher always returns `reconcile`. Since
`score_test_coverage: 0` is the normal value for an issue with no test coverage
yet, **any issue lacking test coverage can never be routed to `spike`** — which
inverts the intent, because a no-coverage issue is exactly the
unproven-mechanism case `spike` exists to serve.

Observed in run `.loops/runs/autodev-20260810T171140/` on FEAT-3145
(`score_ambiguity: 10`, `score_complexity: 10`, `score_test_coverage: 0`,
`score_change_surface: 18`): the dispatcher chose `reconcile`, the issue
plateaued at readiness 65, and it deferred `low_readiness`.

The likely fix is to treat `0` as "unscored / not applicable" and exclude it
from the `min()` (falling back to `reconcile` only if no scored dimension
remains), rather than letting an unscored dimension pin the floor at zero.
Whether `0` genuinely means "zero coverage" vs. "not measured" needs settling —
if it means the former, the comparison should probably use a different
predicate entirely (e.g. `amb` being the strictly weakest *scored* dimension).


## Current Behavior

The remedy dispatcher returns `reconcile` for every issue whose
`score_complexity`, `score_test_coverage`, or `score_change_surface` is `0`,
regardless of how weak `score_ambiguity` is. The `spike` branch is dead code on
that input class.

## Expected Behavior

An issue whose ambiguity is the strictly weakest *scored* dimension routes to
`spike`, whether or not some other dimension is unscored. A `0` in a sibling
dimension should not silently disable the branch.

## Motivation

`spike` and `reconcile` are the only two non-refine readiness remedies autodev
has. Losing one of them for a large input class means those issues get a weaker
remedy and reach `low_readiness` deferral having exhausted a ladder that never
offered them the right rung. The cost is measurable: run
`.loops/runs/autodev-20260810T171140/` spent ~$4.48 / 38m on a single issue and
deferred it anyway.

## Proposed Solution

Exclude unscored (`0`) dimensions from the `min()` comparison, falling back to
`reconcile` only when no scored sibling dimension remains:

```python
others = [int(d.get(k) or 0) for k in
          ('score_complexity', 'score_test_coverage', 'score_change_surface')]
scored = [v for v in others if v]
print('spike' if (amb and scored and amb < min(scored)) else 'reconcile')
```

**Open question that gates the fix**: whether `0` means "not measured" or
"genuinely zero coverage". The patch above assumes the former. If it is the
latter, the predicate itself is wrong — a truly zero-coverage dimension is the
weakest, and the dispatcher should say so rather than being skipped.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

### Codebase research resolves the semantics question, but leaves a design decision open

`skills/confidence-check/rubric.md` establishes that `0` is a real, intended
worst-case score for each of the four `score_*` criteria — not a "not
measured" sentinel (see findings under `## Root Cause`). Given that, the
patch this section proposes (excluding `0`-valued dimensions from the
`min()` before comparing) is not supported: it would make the dispatcher
ignore a dimension the rubric deliberately scored at the worst possible
value, which is the opposite of what `min()` is there to catch. `0` is
mathematically the weakest possible score on the `0-25` scale, so under the
current predicate's semantics (`spike` only when ambiguity is *strictly*
below the weakest of the other three), a real `0` sibling correctly makes
`spike` unreachable for that issue — that reading treats the observed
FEAT-3145 case as by-design, not a bug.

Two ways to resolve this remain, and codebase research does not determine
which matches actual intent for the remedy ladder:

**Option A**: Treat the current behavior as correct. A genuinely `0`-scored
sibling dimension (e.g. zero test coverage) legitimately outranks ambiguity
as the primary blocker, so `reconcile` (not `spike`) is the right remedy —
`spike` exists to resolve ambiguity/unproven-mechanism risk, not coverage
gaps. Under this option BUG-3146 would be reclassified as not-a-bug, or
narrowed to only the cases where `amb` ties the sibling floor (`amb == 0`
too), which the current strict `<` also excludes.

> **Selected:** Option A — the rubric documents `0` as a genuine worst-case
> score, not a "not measured" sentinel, and no precedent exists in
> `autodev.yaml` for excluding or loosening a comparison on a real `0`.

**Option B**: Change the comparison so ambiguity does not have to beat an
unrelated dimension's absolute floor to route to `spike`. For example,
compare `amb` against the *other three's* median or second-lowest value
instead of their `min()`, or drop the "strictly below every sibling"
requirement in favor of "ambiguity is tied-or-weakest among all four
dimensions including itself" (`amb <= min(others + [amb])`, which is
`amb <= min(others)`). This keeps a real sibling `0` from unconditionally
blocking `spike`, but changes the remedy-selection rule's meaning, which is
an intent decision, not a bug-fix-shaped code change.

**Recommended**: Option A for v1 — it requires no code change and matches
the rubric's own semantics for what `0` means, but confirm against actual
autodev design intent (was `spike` meant to fire whenever ambiguity is
present at all, regardless of other dimensions?) before closing this issue
as not-a-bug, since the Motivation section's cost data (`$4.48 / 38m` spent
on FEAT-3145) suggests the ladder is not serving that issue well regardless
of which option is chosen.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-10.

**Selected**: Option A — treat the current behavior as correct; no code change

**Reasoning**: `skills/confidence-check/rubric.md:298-305` documents `0` as an intentional, real
worst-case score for all four `score_*` criteria, not a "not measured" sentinel — the exact
premise Option A's semantic reading depends on, and the one Option B's `<=`-tie-break directly
conflicts with. No precedent exists anywhere in `autodev.yaml` for excluding a genuine `0`-valued
sibling from a `min()` comparison or for loosening a cross-dimension comparison to a tie-break;
the issue's own `## Decision Rules` section already flags that kind of change as an unconfirmed
intent decision, not a bug-fix-shaped one. Option A requires zero code change, and if narrowed to
add regression coverage for the `amb == 0` tie case, the existing
`_run_pre_deferral_remedy_selector()` test harness (`scripts/tests/test_autodev_loop.py:632-681`)
covers it directly with no new infrastructure.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 0/3 | 2/3 | 3/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: rubric (`rubric.md:298-305`) gives every `score_*` criterion an explicit `0` row; the
  issue's own Root Cause research already concludes a real `0` sibling correctly outranks
  ambiguity under the current predicate's semantics.
- Option B: no existing `min()`-tie-break precedent in `autodev.yaml` (only 1 cross-dimension
  `min()` call site total, and it's the one this issue is about); the issue's own text labels the
  change an unconfirmed "intent decision."

## Integration Map

### Files to Modify
- None — `scripts/little_loops/loops/autodev.yaml`'s remedy dispatcher (state
  `recheck_after_size_review`, inline `python3 -c` block at line 2083) is
  correct-as-designed per the Decision Rationale (Option A: no code change).
  The only change is a regression test (see `### Tests` below).

### Dependent Files (Callers/Importers)
- None directly — the predicate is inline in the FSM YAML action. Behavior is
  observable through `autodev-pre-deferral-remedy.txt` in the run dir.

_Wiring pass added by `/ll:wire-issue`:_
- No other loop YAML, hook, or script reads `autodev-pre-deferral-remedy.txt`
  or the `spike`/`reconcile` token — confirmed by repo-wide grep; the only
  consumers are `check_pre_deferral_remedy` and `dispatch_pre_deferral_remedy`,
  both already inside `autodev.yaml` [Agent 1/2 finding].
- The broader score-plumbing chain (`scripts/little_loops/issue_parser.py:1727-1730`,
  `scripts/little_loops/cli/issues/show.py:387-393`, `cli/issues/set_flags.py`
  `cmd_set_scores`) feeds `score_*` values into this dispatcher but needs no
  change under Option A — listed for completeness only, not as work [Agent 1
  finding].

### Similar Patterns
- The `plateau` / `fresh_below` predicate in `check_pre_deferral_remedy`
  (autodev.yaml ~1539) is the neighbouring inline-Python routing idiom; keep the
  same single-inline-script shape.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a case asserting the dispatcher
  selects `spike` when ambiguity is weakest among scored dimensions and a
  sibling is `0`.
  > ⚠ Superseded — decided behavior is `reconcile`, not `spike`, per Option A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_loop.py` — `TestRecheckAfterSizeReviewMeasurementGateBranch`
  (lines 684-747) is the correct, lower-effort target: call
  `_run_pre_deferral_remedy_selector()` (lines 632-681) with
  `gate_marker="false", score_ambiguity=14, score_complexity=14,
  score_test_coverage=25, score_change_surface=25` (the `amb == min(others)`
  tie boundary) and assert `remedy == "reconcile"`. No existing test in this
  class or in `test_builtin_loops.py:6381-6423` covers the tie case or an
  explicit `0`-sibling with an assertion on the score-comparison branch — not
  redundant [Agent 3 finding].
- `scripts/tests/test_builtin_loops.py:6381-6423` — overlapping coverage of
  the same state via substring assertions on the literal action string, not
  subprocess execution; no change needed for this fix, listed for awareness
  only [Agent 1/3 finding].

### Documentation
- None expected; the behavior is internal to the loop.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no doc file (`skills/confidence-check/rubric.md`,
  `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/DEFERRAL_CODES.md`)
  describes this dispatcher's `0`-handling semantics or mischaracterizes it
  as a bug — none needs a change [Agent 2 finding].

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- `scripts/tests/test_autodev_loop.py` already has a purpose-built helper for
  this exact dispatcher: `_run_pre_deferral_remedy_selector()` (~lines
  632-681), which subprocess-executes the real inline script sliced out of
  the live `autodev.yaml` (via `_extract_python_script()`/`_load_autodev_yaml()`),
  with `score_ambiguity`/`score_complexity`/`score_test_coverage`/
  `score_change_surface` kwargs each defaulting to `0`. The existing test
  class `TestRecheckAfterSizeReviewMeasurementGateBranch`
  (`test_autodev_loop.py:684-747`) already covers several score combinations
  but none pass `0` for a sibling dimension — this is a lower-effort
  regression-test entry point than the `test_builtin_loops.py` substring
  assertions originally cited.
- `scripts/tests/test_builtin_loops.py:6381-6423` covers the same state via a
  different technique — plain `action.index(...)`/`assert "..." in action`
  substring checks on the literal `action` string, not subprocess execution.
  Both files currently test overlapping states of the same dispatcher.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

### Types

- `score_complexity: int | None` — `scripts/little_loops/issue_parser.py:1727` (`IssueInfo` dataclass field)
- `score_test_coverage: int | None` — `scripts/little_loops/issue_parser.py:1728`
- `score_ambiguity: int | None` — `scripts/little_loops/issue_parser.py:1729`
- `score_change_surface: int | None` — `scripts/little_loops/issue_parser.py:1730`

Each is on a `0-25` scale per `skills/confidence-check/rubric.md`. `None` =
never written by `/ll:confidence-check`; a written value (including a real
`0`) is preserved distinctly through parsing (`issue_parser.py:1893-1916`).

### Signatures

- `cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int` — the
  frontmatter write path for all four `score_*` fields, invoked by
  `/ll:confidence-check` (`scripts/little_loops/cli/issues/set_scores.py:13`).

`ll-issues show <ID> --json` serializes each `score_*` field to a JSON string
when set, JSON `null` when unset (`scripts/little_loops/cli/issues/show.py:387-393`).
The inline dispatcher (`autodev.yaml:2080-2083`, current/buggy form) is:
`amb = int(d.get('score_ambiguity') or 0)`; `others = [int(d.get(k) or 0) for
k in (...)]`; `'spike' if (amb and amb < min(others)) else 'reconcile'`.

### Call Path

`/ll:confidence-check` (rubric scoring, `skills/confidence-check/rubric.md`)
-> `cmd_set_scores` (`scripts/little_loops/cli/issues/set_scores.py`, writes
frontmatter) -> `ll-issues show "$ID" --json` (`scripts/little_loops/cli/issues/show.py`,
reads frontmatter, serializes null-vs-zero distinctly) -> inline `python3 -c`
remedy dispatcher in state `recheck_after_size_review`
(`scripts/little_loops/loops/autodev.yaml:2067-2083`, collapses null-vs-zero
via `d.get(k) or 0`) -> `${context.run_dir}/autodev-pre-deferral-remedy.txt`
-> state `check_pre_deferral_remedy` (`autodev.yaml:2107`, checks file
non-empty) -> `dispatch_pre_deferral_remedy` (`autodev.yaml:2152`, consumes
the `spike`/`reconcile` token).

### Decision Rules

- Current rule: route to `spike` only when `score_ambiguity` is truthy AND
  strictly less than `min(score_complexity, score_test_coverage,
  score_change_surface)` (each defaulted to `0` via `or 0` if falsy);
  otherwise `reconcile`.
- Per the Root Cause and Proposed Solution findings above, whether this rule
  should change (and to what) is an open design decision — Option A/B under
  `## Proposed Solution` — not a settled threshold to encode here.

## Implementation Steps

1. No code change to `scripts/little_loops/loops/autodev.yaml` — Decision
   Rationale selected Option A: the current dispatcher is correct-as-designed
   (a real `0`-scored sibling legitimately outranks ambiguity).
2. Add a regression test to `scripts/tests/test_autodev_loop.py`'s
   `TestRecheckAfterSizeReviewMeasurementGateBranch` using
   `_run_pre_deferral_remedy_selector(gate_marker="false", score_ambiguity=14,
   score_complexity=14, score_test_coverage=25, score_change_surface=25)`
   asserting `remedy == "reconcile"` (the `amb == min(others)` tie boundary,
   not previously covered).
3. Verify with `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a regression test to `scripts/tests/test_autodev_loop.py`'s
  `TestRecheckAfterSizeReviewMeasurementGateBranch` using
  `_run_pre_deferral_remedy_selector(gate_marker="false", score_ambiguity=14,
  score_complexity=14, score_test_coverage=25, score_change_surface=25)`
  asserting `remedy == "reconcile"` (the `amb == min(others)` tie boundary,
  not previously covered).
- No production file changes — `scripts/little_loops/loops/autodev.yaml` is
  correct-as-designed per the Decision Rationale (Option A).
- Verify with `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 - Silently disables one of two readiness remedies for a
  common input class; wastes real money per affected run.
- **Effort**: Small - One predicate line plus a test, once the semantics
  question is settled.
- **Risk**: Low - Widens which issues reach `spike`; the remedy itself is
  already bounded one-shot per issue per run.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-10 | Priority: P2

## Steps to Reproduce

1. Take an issue with `score_ambiguity: 10`, `score_complexity: 10`,
   `score_test_coverage: 0`, `score_change_surface: 18`, readiness below the
   configured threshold, and neither `spike_attempted` nor `reconcile_attempted`
   set (FEAT-3145 as of run `autodev-20260810T171140` is a live example).
2. Run `ll-loop run autodev <ID>`.
3. Observe `${run_dir}/autodev-pre-deferral-remedy.txt` contains `reconcile`,
   never `spike`, despite ambiguity being the weakest scored dimension.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: state `recheck_after_size_review`, inline remedy-dispatcher
  `python3 -c` block
- **Cause**: `min(others)` includes unscored `0` dimensions, pinning the
  comparison floor at `0`. `amb < 0` is unsatisfiable for any non-negative
  `amb`, so the `spike` branch is unreachable whenever any sibling subscore is
  `0`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- `0` is a genuine, intentional worst-case rubric score for all four
  `score_*` criteria, not a "not measured" sentinel: `skills/confidence-check/rubric.md`
  gives each of Criterion A (Complexity), B (Test Coverage), C (Ambiguity), and D
  (Change Surface) an explicit `0` row (e.g. `rubric.md:298-305` Criterion B —
  `No tests exist for modified areas | 0`), and the `## Examples` section shows
  worked cases actually reaching `0/25` and `0/12` for real issues.
- The codebase *does* distinguish "unwritten" from "written as 0" one layer up:
  `scripts/little_loops/issue_parser.py:1727-1730` types all four fields as
  `int | None = None`, and `IssueInfo` parsing (`issue_parser.py:1893-1916`)
  coerces an absent/non-digit frontmatter key to `None`, never to `0`.
  `scripts/little_loops/cli/issues/show.py:387-393` mirrors this in the
  `--json` output: `None` → JSON `null`, a real `0` score → JSON string `"0"`.
- The inline dispatcher's `int(d.get(k) or 0)` (`autodev.yaml:2080-2082`)
  collapses both `null` (unwritten) and `"0"` (genuinely scored worst) to
  Python `0`. In practice this state only fires after `/ll:confidence-check`
  has scored the issue, so the `null` case is not expected to occur here — the
  observed FEAT-3145 case (`score_test_coverage: 0`) is a real, intentional
  worst-case score, not a missing value.
- This resolves the issue's "Open question that gates the fix": the Proposed
  Solution's patch (excluding falsy/`0` dimensions from the `min()`) is built
  on the "0 means not measured" reading, which this research does not support.
  See the added findings under `## Proposed Solution` for the implication.
- `check_pre_deferral_remedy`/`recheck_after_size_review`'s sibling states
  (`autodev.yaml` — `GATE` computation ~1943-1952, `STATUS` check ~1962-1964)
  use the same `int(d.get(k) or 0)` idiom for `confidence`/`outcome`/`status`,
  but those fields are gate-required to be present by the time those states
  run, so the None-vs-0 collision has no practical effect there. There is no
  existing precedent in `autodev.yaml` for excluding unscored dimensions from
  a `min()`/comparison — the `score_*` block at 2080-2083 is the only inline
  cross-dimension `min()` in the file.

## Location

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Line(s)**: 2079-2083 (at scan commit: 83b6d51b)
- **Anchor**: remedy dispatcher inside `recheck_after_size_review`
- **Code**:
```python
          amb = int(d.get('score_ambiguity') or 0)
          others = [int(d.get(k) or 0) for k in
                    ('score_complexity', 'score_test_coverage', 'score_change_surface')]
          print('spike' if (amb and amb < min(others)) else 'reconcile')
```

## Session Log
- `/ll:manage-issue` - 2026-08-11T04:43:17 - `017906d5-d431-4e0c-bc66-f0c7d02ef1f4.jsonl`
- `/ll:confidence-check` - 2026-08-11T04:30:12 - `4b51cd3b-0b71-4edb-805e-befee76b0153.jsonl`
- `/ll:reconcile-issue` - 2026-08-11T04:28:23 - `a9604285-d614-4a8a-9efe-d8bd24046813.jsonl`
- `/ll:refine-issue` - 2026-08-11T04:22:50 - `f1106bd8-718c-46c7-935a-06b0644b12ed.jsonl`
- `/ll:verify-issues` - 2026-08-11T04:21:28 - `d5efe2ea-0004-4b2c-8103-ceef1c36ba58.jsonl`
- `/ll:wire-issue` - 2026-08-11T04:19:55 - `7444bcfa-9594-4224-b3ba-7cac223f4c8d.jsonl`
- `/ll:decide-issue` - 2026-08-11T04:13:50 - `07c8ff10-9b81-4ba9-968d-c8bbd062c0a9.jsonl`
- `/ll:refine-issue` - 2026-08-11T04:08:47 - `9e1df719-d3bc-40f3-b598-758e8df9cba5.jsonl`
- `/ll:capture-issue` - 2026-08-10T23:10:11 - `81255c48-5bc6-4004-a8cd-3f14858f5cb5.jsonl`
