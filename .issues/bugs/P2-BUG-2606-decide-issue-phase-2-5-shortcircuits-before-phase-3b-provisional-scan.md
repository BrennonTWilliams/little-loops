---
id: BUG-2606
title: decide-issue Phase 2.5 auto-recovery short-circuits before Phase 3b's provisional-language scan can run
type: BUG
status: open
priority: P2
captured_at: "2026-07-11T18:07:11Z"
discovered_date: "2026-07-11"
discovered_by: capture-issue
relates_to:
- BUG-2605
- ENH-2443
labels:
- decide-issue
- decision-gate
- skills
---

# BUG-2606: decide-issue Phase 2.5 auto-recovery short-circuits before Phase 3b's provisional-language scan can run

## Summary

`skills/decide-issue/SKILL.md` has two independent mechanisms for handling an
issue with `decision_needed: true` but no formally-structured options:

- **Phase 2.5** (lines 103-129, ENH-2443): a pre-check that runs Patterns 1-4
  (the same enumerable-option extraction as Phase 3). If `OPTIONS == 0` and
  `AUTO_MODE = true`, it invokes `/ll:refine-issue --auto` once, re-scans, and
  if still `OPTIONS == 0`, emits `MANUAL_REVIEW_RECOMMENDED` and exits
  straight to Phase 8 (Session Log) — **skipping Phases 3-7 entirely**.
- **Phase 3b** (lines 189-276, "Inline Decision Scan"): a smarter fallback,
  reachable only via normal Phase 3 flow, that scans for *provisional decision
  language* (parenthetical `e.g.,`, `TBD` markers, "must be replaced with",
  and declarative recommendations like "Recommended: (b)") and can lock in a
  clear winner even when no formal `### Option A/B` blocks exist.

Phase 2.5's failure path (line 120-124) exits before Phase 3 is ever reached,
so Phase 3b — the mechanism specifically designed to catch exactly the
"prose recommendation, no formal option blocks" shape — never runs during
the one code path (`AUTO_MODE = true`, first attempt) that most needs it.

## Current Behavior

For an issue like ENH-2492, whose `## Proposed Solution` item 13 reads
"Two viable resolutions: (a) ... or (b) ... Recommendation: `wave TEXT` for
v1", Phase 2.5's one recovery attempt (a `/ll:refine-issue --auto` call) does
not produce Pattern 1-4 enumerable options (refine-issue's Preservation Rule
appends rather than restructures existing prose — see sibling issue), so
Phase 2.5 re-scans, still finds `OPTIONS == 0`, and exits with
`MANUAL_REVIEW_RECOMMENDED` — `decision_needed` stays `true` permanently.
Phase 3b's Pattern D ("Declarative recommendation") is never given a chance
to evaluate the same text, even though it was purpose-built for this case.

## Expected Behavior

When Phase 2.5's one auto-recovery attempt still finds `OPTIONS == 0`, instead
of exiting to `MANUAL_REVIEW_RECOMMENDED`, control should fall through to
Phase 3 → Phase 3b (in `AUTO_MODE`) so the provisional-language scan gets a
chance to lock in a clear winner before giving up. Only if Phase 3b also finds
no clear winner should the skill leave `decision_needed: true` and exit.

## Motivation

This is the mechanism-level twin of BUG-2605 (autodev's FSM-level bypass): even
once autodev correctly routes every decision-gated issue through
`deposit_options` → `run_decide`, `decide-issue --auto` itself still gives up
one phase too early for prose-recommendation-shaped decisions, which per the
sibling investigation account for a large share of the ~40 currently-stuck
`OPTIONS_MISSING` issues. Fixing this at the skill level benefits every
caller of `/ll:decide-issue --auto` (autodev, rn-remediate, and any future
FSM loop), not just one.

## Proposed Solution

In `skills/decide-issue/SKILL.md` Phase 2.5 (lines 114-129), change the
`OPTIONS == 0` + auto-recovery-still-empty branch (lines 120-124) from:

```
- If the re-scan still finds `OPTIONS == 0`: leave `decision_needed: true` unchanged,
  emit `MANUAL_REVIEW_RECOMMENDED` on stdout ..., exit non-zero. Proceed to Phase 8
  (Append Session Log) only — skip Phases 3-7 and Phase 9's normal report.
```

to fall through to Phase 3 (which will itself fall through to Phase 3b per its
existing `AUTO_MODE` + `OPTIONS == 0` precondition, lines 183 and 189-191).
`DEPOSIT_ATTEMPTED = true` is already set at this point, so the existing
bound (Phase 2.5 only ever attempts the recovery `/ll:refine-issue --auto`
call once) is preserved — this change only affects what happens *after* that
one attempt, not how many times it fires.

If Phase 3b also finds no clear winner, its own existing exit path (lines
272-275: log, leave `decision_needed: true`, exit cleanly) already produces
the correct terminal behavior — no new dead-end is introduced.

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — Phase 2.5 branch at lines 120-124.

### Similar Patterns
- `skills/decide-issue/SKILL.md:125-129` — the existing "fall through to
  Phase 3 unchanged" branch for the non-auto-recovery case, to model the
  wording/structure of the new branch after.

### Tests
- No automated test harness currently exercises `decide-issue`'s Phase 2.5/3b
  branching directly (it's LLM-driven skill prose, not Python). Verify
  manually: run `/ll:decide-issue ENH-2492 --auto` (or another stuck
  `OPTIONS_MISSING` issue) after the fix and confirm Phase 3b's Pattern D
  either locks in a winner or produces a clean `NO_ACTIONABLE_DECISIONS`
  disposition — not a bare `MANUAL_REVIEW_RECOMMENDED` skip.

## Implementation Steps

1. Edit Phase 2.5's failure branch in `SKILL.md` to fall through to Phase 3
   instead of exiting to Phase 8.
2. Manually verify against 2-3 currently-`OPTIONS_MISSING` issues (e.g.
   ENH-2492, BUG-1378, ENH-1686) that `/ll:decide-issue --auto` now reaches
   Phase 3b instead of short-circuiting.
3. Re-check `ll-issues check-decidable` / `check-open-questions` status on
   those issues after the run to confirm forward progress (either a locked-in
   decision or a legitimate `NO_ACTIONABLE_DECISIONS` disposition).

## Impact

- **Priority**: P2 - Same backlog-unblocking value as BUG-2605; affects every
  FSM/direct caller of `decide-issue --auto`, not just autodev.
- **Effort**: Small - single skill-markdown branch edit, no code changes.
- **Risk**: Low - reuses Phase 3b's existing, already-scoped exit paths;
  `DEPOSIT_ATTEMPTED` bound is unchanged so no infinite-retry risk.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `skills/decide-issue/reference.md` | Output report template referenced by Phase 9 |

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-11T18:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`
