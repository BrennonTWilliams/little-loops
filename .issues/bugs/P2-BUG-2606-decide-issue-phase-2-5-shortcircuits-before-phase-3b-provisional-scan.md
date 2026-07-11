---
id: BUG-2606
title: decide-issue Phase 2.5 auto-recovery short-circuits before Phase 3b's provisional-language
  scan can run
type: BUG
status: done
priority: P2
captured_at: '2026-07-11T18:07:11Z'
completed_at: '2026-07-11T19:44:36Z'
discovered_date: '2026-07-11'
discovered_by: capture-issue
relates_to:
- BUG-2605
- ENH-2443
labels:
- decide-issue
- decision-gate
- skills
confidence_score: 98
outcome_confidence: 86
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 23
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

## Steps to Reproduce

1. Find (or create) an issue with `decision_needed: true` whose `## Proposed
   Solution` contains a prose recommendation but no formally-structured
   `### Option A/B` blocks — e.g. ENH-2492's item 13: "Two viable
   resolutions: (a) ... or (b) ... Recommendation: `wave TEXT` for v1".
2. Run `/ll:decide-issue <ISSUE_ID> --auto`.
3. Observe Phase 2.5 count `OPTIONS == 0`, invoke its one bounded
   `/ll:refine-issue <ISSUE_ID> --auto` recovery attempt, re-scan, still find
   `OPTIONS == 0`, and exit straight to Phase 8 with
   `MANUAL_REVIEW_RECOMMENDED` (`skills/decide-issue/SKILL.md:120-124`) —
   `decision_needed` stays `true` permanently.
4. Note that Phase 3b's Pattern D ("Declarative recommendation",
   `SKILL.md:189-276`), which is purpose-built to lock in exactly this
   "prose recommendation, no formal option blocks" shape, is never reached
   because Phase 2.5's failure branch exits before Phase 3 is ever entered.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decide_issue_skill.py` — beyond the token-preservation
  update already covered in Implementation Step 2, add a **new** test locking
  in the fall-through behavior itself: assert the exhausted-retry branch text
  contains "fall through" and references Phase 3, in `TestPhase2_5Detection`
  or a new sibling class. Model on
  `TestPattern3bDeclarativeRecommendation.test_absent_open_questions_falls_through`
  (`scripts/tests/test_decide_issue_skill.py:557-562`), a same-shape precedent
  from a prior sibling fix (FEAT-389) that also converted an early-exit branch
  into a fall-through. All phase-boundary slicing in this file is
  text-anchored (`content.index("## Phase 2.5: Decidability Gate")` /
  `content.index("## Phase 3: Extract Options")`), never line-number-anchored,
  so this new test is safe to add regardless of the option (a)/(b) tradeoff
  chosen for the token-preservation question.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` (~line 241) — the `/ll:decide-issue` entry
  states the exhausted-retry path always ends in `MANUAL_REVIEW_RECOMMENDED`;
  no longer true once Phase 3b is attempted first.
- `docs/guides/DECISIONS_LOG_GUIDE.md` (~line 180) — the most direct
  restatement of pre-fix Phase 2.5 mechanics ("...before falling back to
  `MANUAL_REVIEW_RECOMMENDED`... if the retry also finds nothing"); needs the
  Phase 3b detour folded in.
- `docs/guides/LOOPS_REFERENCE.md` (~lines 624-625) — the FSM-flow phrase
  "nothing to score even after one retry" implicitly assumes decide-issue
  never tried Phase 3b; the same file already got one stale-claim correction
  in the sibling BUG-2605 fix.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (~line 228) — the outcome-token
  table entry for `MANUAL_REVIEW_RECOMMENDED` is coarse-accurate but omits the
  new Phase 3b detour; a one-clause addition would keep it precise.
- `.ll/decisions.yaml` ARCHITECTURE-090 entry (~lines 3670-3693, low
  priority/optional) — its `rationale` field attributes
  `MANUAL_REVIEW_RECOMMENDED` emission to "Phase 2.5 gave up"; the reason
  shifts to "Phase 3b also found no winner" after this fix. Historical log
  entry, not enforced code — safe to defer.
- **No FSM/code coupling found**: `autodev.yaml` and `rn-remediate.yaml`
  invoke `/ll:decide-issue --auto` as one opaque `slash_command` state and
  derive their own `MANUAL_REVIEW_RECOMMENDED`/`MANUAL_REVIEW_NEEDED` tokens
  from a marker file they write themselves
  (`decide_options_deposited_<ID>.txt`, checked in `emit_needs_manual_review`,
  `rn-remediate.yaml:~944-966`) — not by scraping decide-issue's stdout. The
  FSM's pre-`decide` gate (`check_decision_decidable` →
  `ll-issues check-decidable`/`check-open-questions`, backed by
  `count_enumerable_options` in `scripts/little_loops/issue_parser.py`) also
  runs independently, before `/ll:decide-issue --auto` is ever invoked. This
  confirms the fix's blast radius is prose+docs only — no loop YAML or CLI
  code needs to change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the Tests claim above**: `scripts/tests/test_decide_issue_skill.py`
  *does* assert on this exact wording via structural (prose-substring) tests
  scoped to the Phase 2.5 text span (`## Phase 2.5: Decidability Gate` through
  `## Phase 3: Extract Options`). Specifically:
  - `TestPhase2_5Detection.test_manual_review_recommended_token_documented`
    (`scripts/tests/test_decide_issue_skill.py:412-417`) asserts the literal
    string `"MANUAL_REVIEW_RECOMMENDED"` still appears somewhere in Phase 2.5's
    text. If the fix deletes the lines 120-124 branch outright (rather than
    keeping the token documented in a comment/contrast clause), this test
    will fail and must be updated in the same change.
  - `TestOptionsMissing.test_decision_needed_left_unchanged_on_exhausted_retry`
    (`scripts/tests/test_decide_issue_skill.py:447-452`) asserts `"unchanged"`
    appears in the Phase 2.5 text — this will keep passing regardless, since
    the sibling fall-through branch (lines 125-129) already contains the word
    `"unchanged"`.
  - `TestDepositAttemptedFlag.test_deposit_attempted_flag_documented`
    (`scripts/tests/test_decide_issue_skill.py:377-384`) only checks Phase 1
    text, unaffected by this fix.
  - Precedent for lockstep test updates on this exact sibling bug (BUG-2605):
    its fix was a 3-line `on_yes:` retarget in `autodev.yaml`, and the PR
    updated `scripts/tests/test_builtin_loops.py` and
    `scripts/tests/test_autodev_decision_gate.py` in the same change. Add
    `scripts/tests/test_decide_issue_skill.py` to Implementation Steps for
    the same reason.
- **Redundancy note**: the triggering condition for lines 120-124 (exhausted
  single retry, i.e. `DEPOSIT_ATTEMPTED` now `true`) is a strict subset of
  line 125's second disjunct (`DEPOSIT_ATTEMPTED = true`). Once merged, the
  two branches become logically redundant — the fix can either (a) delete
  120-124 outright and let line 125's existing condition catch it, or (b)
  keep 120-124 as a distinct sentence with matching "fall through" wording if
  `MANUAL_REVIEW_RECOMMENDED` needs to stay documented for the test above.
  Option (a) is simpler; option (b) is safer for the existing test without
  editing it. Either choice should be made explicit in the implementation.
- **`DEPOSIT_ATTEMPTED` scope confirmed safe to leave un-threaded**: the flag
  is declared/read/set only in Phase 1 (`SKILL.md:63`) and Phase 2.5
  (`SKILL.md:44,116,117,125`) — it is never read in Phase 3 or Phase 3b.
  Phase 3's own `OPTIONS == 0` + `AUTO_MODE = true` precondition
  (`SKILL.md:183`) is self-contained, and only Phase 2.5 (`SKILL.md:116-118`)
  ever invokes `/ll:refine-issue --auto` — so falling through cannot trigger
  a second refine-issue call.
- **Wording convention to model the new branch on** (confirms the issue's own
  Proposed Solution guidance): `SKILL.md:125-129`'s pattern is `fall through
  to Phase N unchanged — <em-dash clause citing the downstream phase's own
  handling as authoritative>`. The same convention recurs at
  `skills/scope-epic/SKILL.md:155,166,183`, `skills/audit-docs/SKILL.md:156`,
  and `skills/manage-issue/SKILL.md:166,176` (`proceed to Phase N [with
  state]`, contrasted with `HALT` for the terminal case) — useful precedent
  if the new sentence needs adjustment during review.
- **Adjacent gap noticed, out of this issue's direct scope**: Phase 3b's own
  no-clear-winner exit (`SKILL.md:272-275`) says only "Exit cleanly" with no
  explicit "proceed to Phase 8" instruction, unlike its sibling exits (the
  clear-winner path at 258-270 and the `NO_ACTIONABLE_DECISIONS` path at
  193-213 both name Phase 8/9 explicitly). Once Phase 2.5 routes into this
  exit for the first time, its under-specified phase-routing becomes
  user-visible (no session log may be appended). Worth a one-line
  clarification in the same edit, or a follow-up issue if out of scope.

## Implementation Steps

1. Edit Phase 2.5's failure branch in `SKILL.md` to fall through to Phase 3
   instead of exiting to Phase 8 (see Redundancy note in Codebase Research
   Findings above for the delete-vs-keep tradeoff on the
   `MANUAL_REVIEW_RECOMMENDED` token).
2. Update `scripts/tests/test_decide_issue_skill.py` in the same change if
   the `MANUAL_REVIEW_RECOMMENDED` token is removed from Phase 2.5's text —
   `TestPhase2_5Detection.test_manual_review_recommended_token_documented`
   (lines 412-417) will otherwise fail. Run
   `python -m pytest scripts/tests/test_decide_issue_skill.py -v` to confirm.
3. Manually verify against 2-3 currently-`OPTIONS_MISSING` issues (e.g.
   ENH-2492, BUG-1378, ENH-1686) that `/ll:decide-issue --auto` now reaches
   Phase 3b instead of short-circuiting.
4. Re-check `ll-issues check-decidable` / `check-open-questions` status on
   those issues after the run to confirm forward progress (either a locked-in
   decision or a legitimate `NO_ACTIONABLE_DECISIONS` disposition).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add a new test to `scripts/tests/test_decide_issue_skill.py` locking in the
   fall-through behavior itself (distinct from Step 2's token-preservation
   check) — model on `test_absent_open_questions_falls_through`
   (lines 557-562).
6. Update `docs/reference/COMMANDS.md` (~line 241) and
   `docs/guides/DECISIONS_LOG_GUIDE.md` (~line 180) — both state the
   exhausted-retry path always ends in `MANUAL_REVIEW_RECOMMENDED`; fold in
   the new Phase 3b detour.
7. Update `docs/guides/LOOPS_REFERENCE.md` (~lines 624-625) and
   `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (~line 228) for the same
   stale-mechanics reason (optional/lower-priority — FSM-level token
   derivation itself is unaffected, only the prose explaining *why* it fires).
8. Optional: update `.ll/decisions.yaml` ARCHITECTURE-090's `rationale` text
   for the same reason (historical log entry, safe to defer).

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

## Resolution

Changed `skills/decide-issue/SKILL.md` Phase 2.5's exhausted-retry branch
(previously lines 120-124) so that after the one bounded
`/ll:refine-issue --auto` recovery attempt still finds `OPTIONS == 0`,
control falls through to Phase 3 → Phase 3b instead of exiting to
`MANUAL_REVIEW_RECOMMENDED` before Phase 3 is ever reached. Went with
Option (a) from the Codebase Research Findings' redundancy note (delete
the now-logically-redundant exhausted-retry branch and let the sibling
"fall through to Phase 3 unchanged" bullet's existing `DEPOSIT_ATTEMPTED =
true` condition catch it), while keeping the `MANUAL_REVIEW_RECOMMENDED`
string documented as "no longer emitted from this phase" so the existing
`test_manual_review_recommended_token_documented` test needed no changes.

Also added a one-line "Proceed to Phase 8" clarification to Phase 3b's
no-clear-winner exit (previously just "Exit cleanly"), since Phase 2.5's
new fall-through makes that exit path reachable for the first time on the
exhausted-retry path (adjacent gap noted in the issue's research).

Added `TestPhase2_5Detection.test_exhausted_retry_falls_through_to_phase_3`
(TDD red → green) asserting the branch documents "fall through" + "Phase
3" and no longer documents "skip Phases 3". Folded the Phase 3b detour
into `docs/reference/COMMANDS.md`, `docs/guides/DECISIONS_LOG_GUIDE.md`,
`docs/guides/LOOPS_REFERENCE.md`, and `docs/guides/RECURSIVE_LOOPS_GUIDE.md`
per the wiring pass. Left `.ll/decisions.yaml` ARCHITECTURE-090 untouched
per the issue's own guidance (historical log entry, safe to defer).

Full suite: `python -m pytest scripts/tests/` — 14622 passed, 36 skipped.

## Status

**Done** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-11T19:43:40Z - `0c092d9c-2d7d-4f6b-a606-6e3ffa4a142f.jsonl`
- `/ll:ready-issue` - 2026-07-11T19:36:03 - `cc16991e-4f22-4124-b6a4-73bf6a552e31.jsonl`
- `/ll:confidence-check` - 2026-07-11T19:32:30 - `39d754c9-859b-4e7f-a82b-a601c8b51aa5.jsonl`
- `/ll:wire-issue` - 2026-07-11T19:30:55 - `8bb621c4-f469-48a1-a6ee-38521390e121.jsonl`
- `/ll:refine-issue` - 2026-07-11T19:25:49 - `49a57bbd-b409-4464-ae6f-9165ae272e59.jsonl`
- `/ll:capture-issue` - 2026-07-11T18:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`
