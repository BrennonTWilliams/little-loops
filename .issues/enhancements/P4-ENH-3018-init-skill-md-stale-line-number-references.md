---
id: ENH-3018
title: skills/init/SKILL.md cites stale cli.py line numbers for _run_plan/_run_apply
type: ENH
status: open
priority: P4
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
program_design_not_applicable: true
testable: false
labels:
- docs
- skills
- ll-init
milestone: epic-3008
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3018: `skills/init/SKILL.md` cites stale `cli.py` line numbers for `_run_plan`/`_run_apply`

## Summary

`skills/init/SKILL.md:140-141` cites hardcoded line ranges for `_run_plan`
(`cli.py:525-593`) and `_run_apply` (`cli.py:597-678`) in
`scripts/little_loops/init/cli.py`. As of this audit, the actual functions are
at `_run_plan` = `cli.py:560-629` and `_run_apply` = `cli.py:632-719` — both
have already drifted from the cited ranges, a concrete example of the
fragile-line-reference pattern this file relies on.

## Current Behavior

`SKILL.md` embeds exact line numbers that will drift every time `cli.py` is
edited above those functions, silently going stale with no test or lint
catching it (this is markdown prose, not code the test suite parses for line
accuracy).

## Scope Boundaries

In scope: `skills/init/SKILL.md:140-141` and a spot-check of other line-number
references in that same file. Out of scope: auditing line-number references
across all other skill files (separate effort if warranted).

## Expected Behavior

References to `_run_plan`/`_run_apply` should point readers to the function by
name (and file) without committing to line numbers that will inevitably drift,
or — if line numbers are valuable for quick navigation — should be
periodically re-verified rather than assumed durable.

## Suggested Fix Direction

**Drop the line numbers; do not refresh them.** Rewriting `SKILL.md:140-141`
to the currently-correct ranges (`_run_plan` = `cli.py:560-629`, `_run_apply` =
`cli.py:632-719`) restores accuracy for exactly as long as it takes for someone
to add a line above `cli.py:560` — which is the defect, not the fix. Replace the
citations with function-name references, e.g. `` `scripts/little_loops/init/cli.py`'s
`_run_plan` / `_run_apply` functions `` — durable under any edit above them, and
directly greppable.

Then spot-check the rest of `skills/init/SKILL.md` for other `path:NNN`-style
citations and convert those the same way.

## Acceptance Criteria

- [ ] `skills/init/SKILL.md`'s `_run_plan`/`_run_apply` references name the
      functions and file, with **no** line numbers.
- [ ] `grep -nE ':[0-9]+' skills/init/SKILL.md` surfaces no remaining
      source-line citations (URLs/version strings excepted); any found are
      converted to symbol references.
- [ ] The referenced symbols exist: `grep -n "def _run_plan\|def _run_apply"
      scripts/little_loops/init/cli.py` returns both.
- [ ] `skills/init/SKILL.md` still passes `ll-verify-skills` and stays under the
      500-line skill cap.
- [ ] No change to `scripts/little_loops/init/cli.py`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P4

## Impact

- **Priority**: P4 — cosmetic/maintainability, not user-facing (this file is
  agent-consumed prompt text, not shipped documentation).
- **Effort**: Trivial.
- **Risk**: None.
- **Breaking Change**: No.


## Session Log
- `/ll:confidence-check` - 2026-08-03T15:14:32 - `0458f341-5d0d-4bc1-8a93-3bb282c63063.jsonl`
