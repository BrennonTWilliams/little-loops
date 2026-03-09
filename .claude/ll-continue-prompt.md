# Session Continuation: Debugging /ll:review-loop — FSM Flow Review Not Executing

## Conversation Summary

### Primary Intent
Fix `/ll:review-loop` so that the FSM Flow Review (anti-pattern checks FA-1 through FA-6 + narrative) actually executes. Currently the model runs QC-1 through QC-7, sees zero findings, and jumps to summary — skipping the FSM logic analysis entirely.

### What Happened

**Phase 1 — Diagnosis (run 1, `review-loop-debug.txt`):**
- Ran `/ll:review-loop issue-refinement-git`
- Model ran QC-1→QC-7 (all clean), output "No findings." — Step 2c never reached
- Root cause: model treats zero QC findings as "done" and skips Step 2c

**Phase 2 — Fix attempt 1 (wording, run 2):**
- Changed skip condition from vague "you want faster output" to unconditional
- Added "Do not output findings yet" guard after QC-7
- Result: identical failure

**Phase 3 — Fix attempt 2 (structural, run 3):**
- Moved FA-1 through FA-6 inline into Step 2b (same section as QC checks)
- Added `### FSM Mental Model` section header between QC-7 and FA-1
- Result: still failed — model narrated "QC-7 ✓ --- No Findings" and stopped

**Phase 4 — Fix attempt 3 (naming, applied in this session, NOT YET TESTED):**
- Root cause confirmed: the `FA-N` naming creates a semantic break. The model treats `QC-N` as the complete check sequence. When it hits `### FA-1` after `### QC-7`, it interprets this as a different phase and stops
- Fix applied: renamed FA-1 through FA-6 → **QC-8 through QC-13** in `SKILL.md`
- Removed the `### FSM Mental Model` section header (replaced with inline paragraph before QC-8) to eliminate the visual break
- FA-N IDs preserved as `check_id` values in findings output (e.g., `check_id: FA-1`) for display/reference alignment with `reference.md`

### Errors and Resolutions
| Error | How Fixed | User Feedback |
|-------|-----------|---------------|
| Step 2c always skipped when QC clean | Wording: added "always run", "do not output yet" | Still failed |
| Step 2c always skipped | Structural: moved FA checks inline to Step 2b | Still failed |
| FA checks still skipped despite being in Step 2b | Renamed FA-N to QC-8 through QC-13; removed section break | Not yet tested |

### Code Changes
| File | Changes Made |
|------|--------------|
| `skills/review-loop/SKILL.md` | Multiple iterations — current state: FA-1→FA-6 renamed to QC-8→QC-13 inline in Step 2b; mental model section header removed; Step 2c is narrative-only |

## Resume Point

### What Was Being Worked On
Verifying whether the QC-8→QC-13 rename fixes the behavioral skip.

### Next Step
Run `/ll:review-loop issue-refinement-git` and check whether the model narrates QC-8 through QC-13.

**Expected output if fix works:**
```
- QC-7 ... ✓
- QC-8 Spin Detection: evaluate — on_partial: evaluate (loops back), on_error: evaluate (loops back), no escape. WARNING.
- QC-9 Missing Failure Terminal: only terminal is 'done', no failed/error state. WARNING.
- QC-10 Unresetting Shared State: check_commit writes /tmp/issue-refinement-commit-count, no reset in initial state. WARNING.
- QC-11 Monolithic Prompt State: fix state — count numbered steps...
- QC-12 Unreachable States: all 5 states reachable. ✓
- QC-13 Dead-End Non-Terminal: all have outbound transitions. ✓

### FSM Flow Review: issue-refinement-git
  **Issues to consider**
  1. Spin risk on evaluate errors...
  2. No explicit failure terminal...
  3. /tmp counter never resets...
```

**If fix still fails, fallback plan:**
Change the check format from `### QC-N: Name` section headers to a flat numbered list under a single header, e.g.:
```markdown
## All Checks (QC-1 through QC-13)
Run each check in order. Record findings.

**QC-1** max_iterations range: ...
**QC-2** Missing on_error routing: ...
...
**QC-8** Spin detection: ...
```
Removing `###` section headers between checks may prevent the model from treating QC-8+ as a new phase.

## Important Context

### Key Behavioral Insight
The model has a strong prior: "`QC-N` prefix = quality check sequence." It cannot be overridden by instruction text ("always run", "do not output yet") — only by making the FA checks look identical to QC checks (same prefix, continuous numbering, no section breaks between them).

### Decisions Made
- **FA-N IDs preserved in check_id**: `reference.md` documents FA-1 through FA-6 by those names. SKILL.md now labels section headers QC-8 through QC-13, but the `check_id` in each finding still says `FA-1` through `FA-6`. This keeps the display consistent with reference.md.
- **reference.md not changed**: The canonical FA-* definitions in `reference.md` are unchanged. Only `SKILL.md` uses the QC-N labels.

### Loop Under Review
`issue-refinement-git` — 5-state FSM: `evaluate → fix → check_commit → commit → done`

Known issues the FA checks SHOULD surface (verified by manual inspection):
1. `check_commit` writes `/tmp/issue-refinement-commit-count`, never reset → QC-10/FA-3
2. `evaluate` has `on_partial: evaluate` AND `on_error: evaluate` — no escape → QC-8/FA-1
3. Only terminal is `done` — no failure terminal → QC-9/FA-2
4. `fix` is a multi-step prompt state — may trigger QC-11/FA-4

### User Preference
User expects to see these as "Issues to consider" in the FSM Flow Review narrative block.
