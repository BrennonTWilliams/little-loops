---
id: BUG-3537
type: BUG
title: reconcile-issue leaves resolved Concerns and stale confidence scores uncleared
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T01:32:52Z'
---

# BUG-3537: reconcile-issue leaves resolved Concerns and stale confidence scores uncleared

## Summary

`/ll:reconcile-issue` rewrites an issue's directive sections but leaves the `### Concerns` bullets in `## Confidence Check Notes` describing the now-fixed contradictions as live, and leaves `outcome_confidence` / `confidence_score` at their pre-reconcile values. Gates and readers that consult the notes or scores keep seeing the issue as contradictory until someone edits it by hand.

## Current Behavior

`commands/reconcile-issue.md` states its purpose as stopping `/ll:confidence-check` from re-flagging the same Concern and the Readiness score from plateauing. Its rewrite scope covers Implementation Steps, Acceptance Criteria and Integration Map (plus conditional sections), and excludes `## Confidence Check Notes`. It does not mark stored scores stale; the only nudge is a suggestion in its CONCERNS output to re-run `/ll:confidence-check`. The stale Concerns and scores therefore survive a successful reconcile and were cleared only by a manual edit.

## Expected Behavior

After a reconcile that substantively rewrites an issue:

- **Resolved Concerns leave the scanned section.** Each resolved Concern bullet is removed from `## Confidence Check Notes` and recorded under a `## Resolved Concerns` section in a fixed, machine-readable form:
  `- [resolved <YYYY-MM-DD> by /ll:reconcile-issue] <original concern text> — <how the rewrite resolved it>`.
  Strikethrough in place is **not** enough. `ll-issues set-flags` substring-matches the whole Confidence Check Notes body (`cli/issues/set_flags.py:291-307`) and ignores `~~…~~`. It was reproduced: a `~~Open decision: …~~ Resolved` note with `outcome_confidence: 59` still stamped `decision_needed: true`. Moving the note out of the scanned section keeps a later low re-score from reactivating it.
- **All six scores are cleared.** Reconcile removes `confidence_score`, `outcome_confidence` and the four components `score_complexity`, `score_test_coverage`, `score_ambiguity` and `score_change_surface` (`issue_parser.py:3780-3783`).
  - Why clear rather than add a stale flag: existing consumers already treat a missing score as "never assessed". `check_readiness.py:129-132` fails the gate, `issue_manager.py:838-841` reports "no confidence score (never assessed)", and `refine_status.py:453-458` renders "—". A new stale flag would need changes in about 30 readers (CLIs, loop YAMLs, skills).
  - Why the components too: a leftover `score_test_coverage` alone still drives the spike gate (`set_flags.py:154-155`).
- **Unresolved Concerns stay in place and remain active.**
- **Flag ownership is unchanged.**
  - Reconcile never clears `decision_needed` or the other outcome flags; clearing stays owned by `/ll:decide-issue` (`set_flags.py:262-264`, `skills/decide-issue/SKILL.md:289-297`).
  - Reconcile's own branch that *sets* `decision_needed: true` (`commands/reconcile-issue.md:240`) keeps working.
- **No-op runs preserve everything.** `--check` already never writes (`commands/reconcile-issue.md:125-126`, §7). A non-check run that finds nothing stale and rewrites no directive section must also leave the scores and notes untouched.
- **Defense in depth.** `set-flags` strips `~~…~~` spans before phrase matching, so hand-written strikethroughs elsewhere cannot fire flags either.

## Motivation

Reconcile exists to stop `/ll:confidence-check` from re-raising a Concern the rewrite already fixed. Today the fixed Concern and the pre-reconcile scores survive, so `refine-to-ready` and the readiness gates act on a verdict about text that no longer exists. Once the rescore dips below 75, the struck-through Concerns re-fire outcome flags.

## Proposed Solution

1. **`commands/reconcile-issue.md`**: in the write step, which runs only when at least one directive section was rewritten and never under `--check`, add these sub-steps:
   - (a) Move each resolved Concern bullet to `## Resolved Concerns` using the format above.
   - (b) Remove the six score keys from frontmatter.
   - (c) Change the CONCERNS output nudge from optional to "scores cleared — re-run `/ll:confidence-check`".
   - Leave the §2b `decision_needed: true` path untouched.
2. **`little_loops.cli.issues.set_flags`**: remove `~~…~~` spans from `notes` before `lowered = notes.lower()`.
3. **`skills/confidence-check`**: when re-scoring, read `## Resolved Concerns` and do not re-raise a listed concern unless there is new evidence. Keep the `## Resolved Concerns` section when rewriting Confidence Check Notes.

## Integration Map

- `commands/reconcile-issue.md`: the rewrite/write step, §2b (`:240`, preserve), `--check` / §7 (`:19`, `:125-126`, `:257-267`), and `reconcile_attempted` (`:146`).
- `scripts/little_loops/cli/issues/set_flags.py`: notes scan (`:291-307`), outcome-threshold precondition (`:130-134`, `:214`), and the set-only docstring (`:262-264`).
- `skills/confidence-check/SKILL.md` (Phase 4.5 notes write, `:438`) and `skills/confidence-check/rubric.md` (Confidence Check Notes template, `:616`).
- Readers of missing scores, which must still behave with the scores cleared (no change expected): `check_readiness.py:129-132`, `issue_manager.py:838-841`, `refine_status.py:453-458`.
- `loops/refine-to-ready-issue.yaml`: confirm the reconcile → re-score path re-runs confidence-check after scores are cleared.
- Tests: `scripts/tests/test_reconcile_issue_command.py`, `test_set_flags_cli.py`, `test_check_readiness.py`, `test_confidence_check_skill.py`.

## Implementation Steps

1. `set_flags.py`: strip strikethrough spans; add a test showing a struck-through resolved note does not fire.
2. `reconcile-issue.md`: add the Resolved Concerns move and the six-key score clear to the write step, gated on a substantive rewrite.
3. `confidence-check`: honor `## Resolved Concerns` on re-score.
4. Tests for each acceptance criterion; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — the issue body is correct; the stale notes and scores mislead gates and readers.
- **Effort**: Small — a bounded addition to the reconcile command's output step.
- **Risk**: Low.

## Steps to Reproduce

1. Take an issue whose `## Confidence Check Notes` lists Concerns that its Acceptance Criteria contradict (observed on BUG-3530, 2026-09-24; `outcome_confidence: 59`).
2. Run `/ll:reconcile-issue BUG-3530`. It rewrites Acceptance Criteria (delete-all-replayable-channels, rollout-not-duplicated) and strikes the withdrawn design hint in Verification Notes; `reconcile_attempted: true` is set.
3. Read the issue afterwards: the Concerns in Confidence Check Notes still present the fixed contradictions as open, and `outcome_confidence` is still 59 (LOW).

## Acceptance Criteria

- [ ] After a reconcile that resolves a Concern, the bullet is gone from `## Confidence Check Notes` and appears under `## Resolved Concerns` in the `[resolved <date> by /ll:reconcile-issue]` form.
- [ ] After a substantive reconcile, `confidence_score`, `outcome_confidence` and all four `score_*` keys are absent from frontmatter. `ll-issues check-readiness` then reports the issue as needing reassessment.
- [ ] Unresolved Concerns remain in `## Confidence Check Notes`. With a sub-threshold `outcome_confidence` present, they still fire their flags through `set-flags`.
- [ ] Resolved Concerns do not re-trigger flags. Neither a `## Resolved Concerns` entry nor a `~~struck~~` note in Confidence Check Notes fires `set-flags`, even at `outcome_confidence: 59`.
- [ ] `--check` runs, and non-check runs that rewrite nothing, leave scores, notes and flags byte-for-byte unchanged.
- [ ] Reconcile never clears `decision_needed` (or other outcome flags); the §2b path that sets it still works.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T01:32:57 - `2f8f7a22-ff27-4b63-912d-b3be6e3850a5.jsonl`
