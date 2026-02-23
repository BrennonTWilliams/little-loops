# BUG-449: Init wizard Round 5 can exceed AskUserQuestion 4-question limit

**Date**: 2026-02-22
**Issue**: P1-BUG-449-init-round5-exceeds-askuserquestion-limit.md
**Action**: fix

## Problem

Round 5 of the `--interactive` wizard dynamically builds follow-up questions based on
user selections in Rounds 2 and 3. When all 4 optional features are selected in Round 3
**plus** a custom issues directory in Round 2, Round 5 must ask 6 questions:

1. `issues_path` — custom directory (Round 2 condition)
2. `worktree_files` — parallel processing (Round 3)
3. `threshold` — context monitoring (Round 3)
4. `priority_labels` — GitHub sync (Round 3)
5. `sync_completed` — GitHub sync (Round 3) ← second question for same feature
6. `gate_threshold` — confidence gate (Round 3)

`AskUserQuestion` has a hard limit of 4 questions per call. The current code puts all
conditional questions in a single YAML block with no overflow strategy, so the wizard
fails or silently drops questions when 5+ conditions are active.

## Root Cause

`skills/init/interactive.md` Round 5 section (lines ~287-401) has one `AskUserQuestion`
call with up to 6 conditional questions and no split/batch logic.

Additionally the conditions list incorrectly shows "sync_settings" as a single condition
when it actually generates **two** questions (`priority_labels` and `sync_completed`).

## Solution

1. **Correct the conditions list** — expand "sync_settings" into two entries so the true
   maximum of 6 is visible.

2. **Add overflow detection** — before presenting, count active conditions. If > 4,
   split into two sub-rounds.

3. **Round 5a** — first 4 active questions (always presented when any condition is true).

4. **Round 5b** — remaining active questions (only presented when count > 4).
   Questions 5 (`sync_completed`) and 6 (`gate_threshold`) always land here when
   overflow occurs because they are last in the ordered list.

5. **Update the summary table** at the bottom of `interactive.md` to reflect the
   conditional 5b round.

## Files to Modify

- `skills/init/interactive.md` — Round 5 section and summary table

## Implementation Steps

- [x] Read `skills/init/interactive.md`
- [ ] Replace Round 5 section with split Round 5a / Round 5b logic
- [ ] Update summary table to show Round 5b as conditional
- [ ] Verify file structure is intact
- [ ] Move issue to completed

## Risk

Low — additive change, only affects overflow path (> 4 active conditions). No behavior
change when ≤ 4 questions are active.
