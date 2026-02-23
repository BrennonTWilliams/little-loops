# ENH-452: Add Progress Indicator to Init Wizard Rounds

## Plan Summary

Add step progress indicators ("Step X of Y — Round Name") as output text before each `AskUserQuestion` call in the init interactive wizard. The total is calculated dynamically: starts at 7 (mandatory rounds), updated after Round 3b (adds 1-2 for Round 5a/5b) and after Round 6.5 (adds 3 if "Configure" selected).

## Changes

### 1. `skills/init/interactive.md` — Add progress tracking

**Add a "Progress Tracking Setup" section** before Round 1 that initializes counters and explains the pattern.

**Before each round**, insert a text-output instruction:
```
Output: **Step [STEP] of [TOTAL]** — [Round Name]
```

**After Round 3b**, insert a recalculation block to count active conditions and update TOTAL.

**After Round 6.5**, insert a recalculation block to add 3 if "Configure" is selected.

**Round-by-round indicator plan:**

| Step | Round | Label | Notes |
|------|-------|-------|-------|
| 1 | Round 1 | Core Settings | TOTAL shows as `~7` |
| 2 | Round 2 | Additional Configuration | TOTAL shows as `~7` |
| 3 | Round 3a | Core Features | TOTAL shows as `~7` |
| 4 | Round 3b | Automation Features | TOTAL shows as `~7` |
| — | After 3b | Recalculate TOTAL | TOTAL becomes 7-9 |
| 5 | Round 4 | Product Analysis | Exact TOTAL shown |
| 6 | Round 5a | Advanced Settings | Only if shown |
| 7 | Round 5b | Advanced Settings (continued) | Only if shown |
| N | Round 6 | Document Tracking | Dynamic STEP |
| N+1 | Round 6.5 | Extended Configuration | Dynamic STEP |
| — | After 6.5 | Recalculate TOTAL | +3 if Configure |
| N+2 | Round 7 | Project Advanced | Only if Configure |
| N+3 | Round 8 | Continuation Behavior | Only if Configure |
| N+4 | Round 9 | Prompt Optimization | Only if Configure |

**TOTAL calculation logic:**
```
Initial: TOTAL = 7

After Round 3b responses:
  ACTIVE = count of:
    - Round 2 "Yes, custom directory" → +1
    - Round 3a "Parallel processing" → +1
    - Round 3a "Context monitoring" → +1
    - Round 3a "GitHub sync" → +2 (priority_labels + sync_completed)
    - Round 3a "Confidence gate" → +1
    - Round 3b "Sprint management" → +1
    - Round 3b "Sequential automation" → +1
  if ACTIVE >= 1: TOTAL += 1  (Round 5a)
  if ACTIVE > 4:  TOTAL += 1  (Round 5b)

After Round 6.5:
  if user selected "Configure": TOTAL += 3  (Rounds 7, 8, 9)
```

### 2. `skills/init/SKILL.md` — Update round count reference

Line 81 says "6-10 rounds". Update to "7-12 rounds" to match the actual range (7 mandatory + up to 5 conditional).

## Success Criteria

- [x] Progress Tracking Setup section added at top of interactive.md
- [x] "Step X of Y" output added before every AskUserQuestion call (Rounds 1–9)
- [x] TOTAL recalculated after Round 3b based on active conditions
- [x] TOTAL recalculated after Round 6.5 based on gate selection
- [x] SKILL.md round count updated from "6-10" to "7-12"
