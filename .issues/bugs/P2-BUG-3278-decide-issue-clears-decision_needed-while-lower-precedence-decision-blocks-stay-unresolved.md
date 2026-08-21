---
id: BUG-3278
type: BUG
title: decide-issue clears decision_needed while lower-precedence decision blocks
  stay unresolved
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:45:13Z'
labels:
- decide-issue
- skills
- decision-needed
- pipeline
relates_to:
- BUG-3279
- ENH-3280
- ENH-3277
---

# BUG-3278: decide-issue clears decision_needed while lower-precedence decision blocks stay unresolved

## Summary

`/ll:decide-issue` Phase 7b sets `decision_needed: false` unconditionally after annotating a
winner. When an issue contains more than one decision point expressed at *different*
`locate_enumerable_options` precedence tiers, only the highest tier is ever extracted — the
remaining decision blocks are invisible to the skill, yet the file-level flag is cleared as
if every decision were settled. Downstream `/ll:wire-issue`, `/ll:ready-issue`, and
`/ll:manage-issue` then treat the issue as decided.

## Current Behavior

Observed on ENH-3277 (2026-08-21), which contains two distinct decision points:

1. `**Option A**` / `**Option B**` / `**Option C**` under *DECISION REQUIRED* — `bold_label` tier
2. `- **(a) Make the documented override real.**` / `- **(b) Drop the knob.**` under
   *Dead site — ...*, prefixed by the literal directive
   `**DECISION — pick one before step 4 touches this file:**` — `bullet` tier

`ll-issues locate-options ENH-3277 --json` returns:

```
count 3  pattern bold_label  heading "Proposed Solution"
 - Option A — permanently exempt both.    160-165
 - Option B — accept the guess.           166-171
 - Option C — add a no-default read mode. 172-404
```

Precedence in `issue_parser.locate_enumerable_options` is winner-take-all: `section_header` >
`bold_label` > `numbered` > `bullet`. `bold_label` fired, so the `bullet`-tier (a)/(b) block was
never returned. `/ll:decide-issue` scored A/B/C, selected A, and Phase 7b set
`decision_needed: false` — while the (a)/(b) decision remains open in the body.

## Steps to Reproduce

1. Take an issue with two decision points at different precedence tiers — ENH-3277 as it stood at
   commit-time is the live case (`bold_label` Option A/B/C at lines 154–203; `bullet` (a)/(b)
   under `**DECISION — pick one before step 4 touches this file:**` at lines 265–278).
2. Run `ll-issues locate-options ENH-3277 --json` — observe `count 3`, `pattern bold_label`, and
   no (a)/(b) entries.
3. Run `/ll:decide-issue ENH-3277`.
4. Read the frontmatter: `decision_needed: false`.
5. Read the body: the (a)/(b) block and its "pick one before step 4" directive are unchanged and
   unresolved.

## Expected Behavior

`decision_needed` is cleared only when no unresolved decision point remains in the file. If
lower-tier decision blocks survive the pass, the flag stays `true` and the report names which
blocks are still open.

## Motivation

`decision_needed` is the pipeline's gate between refinement and implementation. A falsely-cleared
flag does not surface as an error — it surfaces as `/ll:manage-issue` implementing an issue whose
body still says "pick one before step 4 touches this file". The failure is silent by construction,
and the more thoroughly an issue was refined (multiple decision points, mixed formatting tiers)
the more likely it is to trip.

## Proposed Solution

Before Phase 7b's write, re-run extraction with the decided span excluded (lines
`options[0].start_line`–`options[-1].end_line`) and check whether any lower-tier decision block
remains:

- If a further decision point is found: leave `decision_needed: true`, and in Phase 9 report
  `⚠ decision_needed remains true — N unresolved decision point(s): <heading/line refs>`.
- If none: clear as today.

The exclusion is what makes this tractable — a plain re-scan would re-match the just-decided
`bold_label` block. An alternative shape is to have `locate-options` optionally return *all*
tiers (`--all-tiers`) rather than only the winning one, letting the skill see the full decision
inventory in one call; that also fixes the multi-decision blind spot for other consumers
(`ll-issues check-decidable`, the FSM pre-`decide` gate).

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — Phase 7b gains the pre-write re-scan; Phase 9 report gains the
  unresolved-decisions line
- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` if the `--all-tiers` shape
  is taken
- `scripts/little_loops/cli/issues/locate_options.py` and `cli/issues/__init__.py` —
  `locate-options` flag plumbing, same condition

### Tests

- An issue fixture with two decision points at different tiers: assert `decision_needed` survives
  as `true` after a `--auto` run
- Single-decision fixture: assert the flag still clears (no regression on the common path)

## Implementation Steps

1. Decide the detection mechanism: span-excluding re-scan in the skill, or `--all-tiers` on
   `locate-options`. The second is more work but also fixes `ll-issues check-decidable` and the
   FSM pre-`decide` gate, which share the same blind spot.
2. Add the pre-write check to Phase 7b; leave `decision_needed: true` and name the surviving
   blocks when any are found.
3. Extend the Phase 9 report (`skills/decide-issue/reference.md`) with the unresolved-decisions
   line.
4. Verify: two-tier fixture keeps the flag `true`; single-decision fixture still clears it.

## Impact

- **Priority**: P2 — silent false-ready into the implementation pipeline, but it needs a
  multi-decision issue to trigger, so it is not a blanket break of the common path
- **Effort**: Small for the skill-local re-scan; Medium if `--all-tiers` is taken
- **Risk**: Low — the change can only make the skill *more* conservative about clearing a flag;
  worst case is a flag left true that a human clears
- **Breaking Change**: No

## Root Cause

`skills/decide-issue/SKILL.md` Phase 7b (§ *7b: Update Frontmatter*) performs an unconditional
set-to-`false` with only an idempotency check ("if already `false`, skip the write"). There is no
re-scan for surviving decision points.

The skill already establishes the correct principle elsewhere and simply does not apply it here —
Phase 3b-i refuses to clear the flag in the `NO_ACTIONABLE_DECISIONS` case with the explicit
rationale *"automation cannot clear a flag it did not earn"*. Phase 7b earns the flag for one
decision and clears it for all of them.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3b-i states the "flag it did not earn" principle Phase 7b
  violates
- ENH-3277 — the issue where this was observed

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
