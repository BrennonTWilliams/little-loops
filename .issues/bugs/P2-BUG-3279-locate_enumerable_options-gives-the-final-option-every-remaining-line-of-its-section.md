---
id: BUG-3279
type: BUG
title: locate_enumerable_options gives the final option every remaining line of its
  section
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:45:38Z'
labels:
- decide-issue
- issue-parser
- locate-options
- scoring
relates_to:
- BUG-3278
- ENH-3280
- ENH-3277
---

# BUG-3279: locate_enumerable_options gives the final option every remaining line of its section

## Summary

Option spans produced by `issue_parser.locate_enumerable_options` end at the next option's start
or, for the last option, at the end of the containing section. In a refined issue the prose that
follows the option list — analysis subsections, research findings, tables, and any
`### Decision Rationale` already appended — is therefore absorbed into the final option's `text`.
`/ll:decide-issue` Phase 4 hands that text to a scoring agent as the option's description.

## Current Behavior

`ll-issues locate-options ENH-3277 --json` (2026-08-21):

```
count 3  pattern bold_label  heading "Proposed Solution"
 - Option A — permanently exempt both.    160-165   (6 lines)
 - Option B — accept the guess.           166-171   (6 lines)
 - Option C — add a no-default read mode. 172-404   (232 lines)
```

`## Proposed Solution` spans 109–404, ending at `## Integration Map` on 405. Option C's real
description is roughly `172-188`. The remaining ~215 lines are unrelated content that belongs to
no option: the *Hard prerequisite* §2b table, *Dead site*, *Pinning `dead-code-cleanup`'s skip
edge*, *The three `harness-*` sites*, *Precedence*, *Codebase Research Findings*, and the
`### Decision Rationale` block.

Two consequences:

1. **Scoring reads the wrong text.** The Phase 4 `ll:codebase-pattern-finder` agent for Option C
   was given 232 lines of mostly-unrelated material as that option's description. Option C lost
   here anyway, so the outcome held — but the input was not the option.
2. **Re-running is not idempotent in effect.** `/ll:decide-issue` appends `### Decision Rationale`
   at the end of Proposed Solution (Phase 7a). On a second run that block falls inside the last
   option's span, so the previous decision's rationale and scoring table are fed back in as part
   of the final option's description. Phase 7a's idempotency rule skips the *write* but does not
   prevent the *extraction* from having already consumed it.

## Steps to Reproduce

1. Take any issue whose `## Proposed Solution` continues with `###` analysis subsections after the
   last option — ENH-3277 as it stood at commit-time is the live case.
2. Run `ll-issues locate-options ENH-3277 --json`.
3. Compare the last option's `end_line` (404) against the line where its prose actually stops
   (~188) and against the next subheading (`### Hard prerequisite …`, line 205).
4. Inspect `options[-1].text` — it contains the §2b table, *Dead site*, *Pinning*, *Precedence*,
   *Codebase Research Findings*, and `### Decision Rationale`, none of which describe that option.

### Second consumer, same defect — `_unapplied_decision` (verified 2026-08-21)

`issue_parser._unapplied_decision` (`:1392`) does not call `locate_enumerable_options`; it uses a
sibling span function, `_option_block_spans`. It has the identical last-block absorption bug, and
`ll-issues format-check ENH-3277` shows it firing:

```
unapplied_decision: Proposed Solution still specifies `pytest` (rejected option)
unapplied_decision: Proposed Solution still specifies `lint_cmd` (rejected option)
unapplied_decision: Proposed Solution still specifies `ll-config get` (rejected option)
... ~40 more
```

None of those are rejected-option identifiers. They are ordinary vocabulary from the ~230 lines of
analysis prose that the last option block absorbed, reported as things the rejected option
"specifies".

**Its existing mitigations are the right idea and insufficient.** ENH-3256 already hardened this
function against exactly this failure with two clamps, both documented in its docstring: clamp the
final block at `### Decision Rationale`, and trim it at the end of its own `> **Selected:**`
callout line. Neither helps here — the last block is a *rejected* option (no callout to trim at),
and the `### Decision Rationale` boundary still leaves every intervening `###` subsection inside
the span.

The fix proposed below — terminate at the next heading of any depth — subsumes both existing
clamps and repairs this consumer too. **Fix both functions, or factor the boundary rule into one
helper they share**; two independent span implementations with the same bug is the reason this
recurred after ENH-3256 supposedly closed it.

## Expected Behavior

An option's span ends at the first structural boundary after it — the next option, the next
subheading (`###`/`####`), or the section end — whichever comes first. Trailing analysis prose
belongs to no option and is excluded from every option's `text`.

## Motivation

Option text is the sole input to Phase 4/5 scoring — the agents never read the issue themselves,
they read the span. A span that is 93% unrelated content makes the resulting scores unearned, and
because the extra content is *plausible* issue prose there is no signal that anything went wrong.
The distortion also scales the wrong way: it is worst on heavily-refined issues, which are exactly
the ones whose decisions carry the most downstream weight.

## Proposed Solution

Terminate each option span at the earliest of:

- the next extracted option's `start_line`
- the next markdown heading at any depth after the option's start
- the section end (current behavior, now the fallback rather than the rule)

The heading boundary is what resolves the observed case: the first `###` after Option C's start is
`### Hard prerequisite — pick a §2b row per site before writing any shell` at line 205, bounding
Option C to `172-204` instead of `172-404`.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` span termination, and
  `_option_block_spans` / `_unapplied_decision` (`:1392`), which carry the same bug independently.
  Prefer a shared boundary helper over two parallel fixes

### Tests

- A fixture with a trailing `###` subsection after the last option: assert the last option's
  `end_line` stops at the subheading, not the section end
- A fixture whose option list *is* the section tail: assert the span still runs to section end
  (fallback preserved)
- A fixture containing a prior `### Decision Rationale` block: assert it appears in no option's
  `text`

## Implementation Steps

1. Add the heading boundary to span termination in `locate_enumerable_options`, keeping section
   end as the fallback.
2. Confirm the boundary does not truncate legitimately-subheaded options — a `### Option A`
   (`section_header` tier) block whose body contains a `####` subheading must not stop there.
   This is the one shape where the fix could over-trim.
3. Verify: `ll-issues locate-options ENH-3277 --json` bounds Option C at `172-204` rather than
   `172-404`, and no option's `text` contains `### Decision Rationale`.

## Impact

- **Priority**: P2 — degrades decision quality on the issues that matter most, but does not
  corrupt files or block the pipeline
- **Effort**: Small — one span-termination rule plus fixtures
- **Risk**: Medium — `locate_enumerable_options` is shared by `/ll:decide-issue`,
  `ll-issues check-decidable`, and the FSM pre-`decide` gate, so a too-aggressive boundary
  could shrink options that legitimately contain subheadings (see step 2)
- **Breaking Change**: No — spans narrow, `count` and `pattern` are unaffected

## Root Cause

`scripts/little_loops/issue_parser.py`, `locate_enumerable_options` — the last option's
`end_line` is set to the section end with no intervening boundary check. The bug is invisible for
short unrefined issues (where the option list *is* the tail of the section) and grows with the
amount of post-option analysis a refined issue accumulates, so it surfaces exactly on the issues
where the decision matters most.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3 (extraction contract), Phase 4 (consumer), Phase 7a
  (the appended block this bug re-consumes)

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
