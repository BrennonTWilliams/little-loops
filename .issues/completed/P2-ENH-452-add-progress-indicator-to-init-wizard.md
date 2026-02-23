---
type: ENH
id: ENH-452
title: Add progress indicator to init wizard rounds
priority: P2
status: completed
created: 2026-02-22
---

# Add progress indicator to init wizard rounds

## Summary

The init interactive wizard has 6-10 rounds of AskUserQuestion calls. Users have no sense of progress — they don't know if they're near the beginning, middle, or end of the wizard.

## Current Behavior

The init interactive wizard presents 6-10 rounds of AskUserQuestion calls with no indication of progress. Users cannot tell how many rounds remain or where they are in the wizard.

## Expected Behavior

Each round displays a progress indicator (e.g., "Step 3 of 7") so users know where they are in the wizard and approximately how many rounds remain. The total round count is calculated dynamically based on feature selections.

## Motivation

Without progress indication, users feel uncertain about how long the wizard will take. Progress indicators are a standard UX pattern that reduce anxiety during multi-step flows and give users context to decide whether to continue or exit.

## Proposed Solution

Add a progress indicator to each round. This could be:

1. **Prefix in the question text**: "Step 3 of 7: Which lint command should be used?"
2. **Header annotation**: Use the `header` field creatively, e.g., "3/7 Lint Cmd"
3. **Text output between rounds**: Display "Step 3 of 7 — Features" before each AskUserQuestion call

Option 3 is the most flexible since the total round count is dynamic (6-10 depending on feature selections and the Extended Config Gate).

**Round count notes:**
- Rounds 1-4 and 6 are always shown (5 mandatory rounds)
- Round 5 is conditional (if any features selected)
- Round 6.5 is always shown (gate)
- Rounds 7-9 are conditional on the gate
- Total should be calculated after Round 3 (features) and Round 6.5 (gate)

## Scope Boundaries

- **In scope**: Adding step indicator text before or within each round's AskUserQuestion call; dynamically calculating total rounds after Round 3 and Round 6.5
- **Out of scope**: Visual progress bars, persistent UI state, changes to wizard logic or round ordering

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — All rounds: add progress output before each AskUserQuestion call
- `skills/init/SKILL.md` — Wizard flow description (if it documents round structure)

### Similar Patterns
- N/A — no existing progress indication in other wizard-style skills

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Decide on progress indicator format: text output before round vs. prefix in question text
2. Calculate total rounds: 5 mandatory + conditional Round 5 + Round 6.5 + conditional Rounds 7-9
3. Add progress output at the start of each round in `interactive.md`
4. Update total after Round 3 (features determine if Round 5 appears) and after Round 6.5 (gate determines if Rounds 7-9 appear)

## Impact

- **Priority**: P2 — Improves onboarding UX for all new users; reduces wizard abandonment
- **Effort**: Small — Text additions to each round; no logic changes
- **Risk**: Low — Cosmetic change only; no behavioral impact
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `interactive-wizard`, `ux`

## Resolution

Implemented Option 3 (text output before each round) with dynamic total calculation:

- Added **Progress Tracking Setup** section to `interactive.md` initializing `STEP=0`, `TOTAL=7`
- Added `**Step [N] of [TOTAL]**` output instruction before every AskUserQuestion call (Rounds 1–9)
- Rounds 1–4 show `~7` (tilde prefix) until conditions are evaluated; Round 5+ shows exact total
- TOTAL recalculated after Round 3b (adds 1-2 for conditional Rounds 5a/5b based on active condition count)
- TOTAL recalculated after Round 6.5 (adds 3 if "Configure" selected for Rounds 7-9)
- Updated SKILL.md round count from "6-10" to "7-12"

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:manage-issue` - 2026-02-22 - implemented

## Blocked By

- ENH-451

## Blocks

- ENH-454
- ENH-455
- ENH-456

---

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-22 | Priority: P2
