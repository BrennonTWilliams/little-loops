# ENH-454: Renumber Init Wizard Rounds

## Summary
Renumber init wizard rounds in `skills/init/interactive.md` to eliminate the "Round 6.5" designation, shifting to clean sequential numbering.

## Mapping
| Current | New | Content |
|---------|-----|---------|
| Round 6.5 | Round 7 | Extended Configuration Gate |
| Round 7 | Round 8 | Project Advanced (Optional) |
| Round 8 | Round 9 | Continuation Behavior (Optional) |
| Round 9 | Round 10 | Prompt Optimization (Optional) |

## Changes Required

### File: `skills/init/interactive.md`

1. **Progress Tracking Setup (lines 13-15)**
   - Line 13: `6.5` → `7` in mandatory rounds list
   - Line 15: `Round 6.5` → `Round 7` in comment

2. **Round 6 transition (line 610)**
   - `Round 6.5` → `Round 7`

3. **Round 6.5 header (line 612)**
   - `## Round 6.5:` → `## Round 7:`

4. **Round 6.5 body (lines 631, 633, 636)**
   - `Rounds 7-9` → `Rounds 8-10`
   - `Round 6.5` → `Round 7`
   - `Rounds 7, 8, 9` → `Rounds 8, 9, 10`

5. **Round headers (lines 639, 689, 740)**
   - `## Round 7:` → `## Round 8:`
   - `## Round 8:` → `## Round 9:`
   - `## Round 9:` → `## Round 10:`

6. **Summary table (lines 784, 796-799)**
   - `7-11` → `7-12` (correcting existing inconsistency with SKILL.md)
   - `6.5` → `7`, `7` → `8`, `8` → `9`, `9` → `10` in table rows

### File: `skills/init/SKILL.md`
- Line 81: Already says "7-12 rounds" — no change needed

## Risk
- Low — pure text renaming, no behavioral changes
