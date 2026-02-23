---
type: ENH
id: ENH-452
title: Add progress indicator to init wizard rounds
priority: P2
status: open
created: 2026-02-22
---

# Add progress indicator to init wizard rounds

## Summary

The init interactive wizard has 6-10 rounds of AskUserQuestion calls. Users have no sense of progress — they don't know if they're near the beginning, middle, or end of the wizard.

## Proposed Change

Add a progress indicator to each round. This could be:

1. **Prefix in the question text**: "Step 3 of 7: Which lint command should be used?"
2. **Header annotation**: Use the `header` field creatively, e.g., "3/7 Lint Cmd"
3. **Text output between rounds**: Display "Step 3 of 7 — Features" before each AskUserQuestion call

Option 3 is the most flexible since the total round count is dynamic (6-10 depending on feature selections and the Extended Config Gate).

## Implementation Notes

- Rounds 1-4 and 6 are always shown (5 mandatory rounds)
- Round 5 is conditional
- Round 6.5 is always shown (gate)
- Rounds 7-9 are conditional on the gate
- The total should be calculated after Round 3 (feature selections) and Round 6.5 (gate choice)

## Files

- `skills/init/interactive.md` (all rounds)
- `skills/init/SKILL.md` (wizard flow description)
