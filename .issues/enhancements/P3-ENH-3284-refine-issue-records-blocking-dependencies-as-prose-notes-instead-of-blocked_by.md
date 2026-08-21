---
id: ENH-3284
type: ENH
title: refine-issue records blocking dependencies as prose notes instead of blocked_by
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:30:43Z'
labels:
- refine-issue
- skills
- dependencies
- frontmatter
relates_to:
- BUG-3282
- BUG-3278
- BUG-3279
---

# ENH-3284: refine-issue records blocking dependencies as prose notes instead of blocked_by

## Summary

When `/ll:refine-issue` discovers that another open issue blocks the one it is refining, it writes
the finding as a hedged prose bullet in `## Codebase Research Findings` rather than setting
`blocked_by:` in frontmatter. The dependency is recorded but not machine-readable, so no gate,
loop, or sprint scheduler can act on it.

## Current Behavior

`refine-issue` appends findings as prose under `## Codebase Research Findings`, using
recommendation language ("worth checking whether…", "may share a code path with…"). Nothing in the
pass promotes a discovered hard dependency into the `blocked_by:` frontmatter field, even though
the field exists and is consumed by dependency resolution (only `done`/`cancelled` resolve a
`blocked_by` edge — see `.claude/CLAUDE.md` § Issue File Format).

Observed on BUG-3278 (2026-08-21). Refinement recorded:

> `locate_enumerable_options`/`_unapplied_decision` (same two functions this bug touches) carry a
> separately-tracked sibling span-boundary defect: BUG-3279 … — worth checking whether a fix here
> should share a code path with that fix [pattern-finder finding].

That undersells it. BUG-3278's proposed fix at the time was a span-excluding re-scan over
`options[0].start_line`–`options[-1].end_line`. BUG-3279 is precisely that the final option's
`end_line` over-consumes to the end of its section — measured on ENH-3277, `options[-1].end_line`
is 435 while the section runs to ~546, so the excluded span swallows the very region the surviving
decision lives in. The proposed fix was unimplementable until BUG-3279 landed. The issue's
frontmatter listed BUG-3279 under `relates_to:` only.

## Expected Behavior

[What should happen instead]

## Motivation

`relates_to` and `blocked_by` are not interchangeable: the first is a reading hint, the second is
a scheduling constraint. An ordering requirement filed as prose is invisible to
`ll-issues`-driven dependency resolution and to the FSM loops that dequeue by readiness, so an
issue can be picked up, implemented against a broken primitive, and fail late — or worse, ship a
fix that silently doesn't work.

The information was already in the file. Only its encoding was wrong.

## Proposed Solution

Extend the refine pass with a promotion step:

1. When a finding names another issue as affecting *how or whether* this issue can be implemented
   — not merely as related context — classify it as a hard dependency.
2. Set `blocked_by:` in frontmatter (append if present) and state the ordering constraint plainly
   in the prose finding: what breaks if the order is violated, not "worth checking".
3. Keep `relates_to` for genuine see-also links.

The classification cue is whether the other issue changes the *correctness* of a proposed
mechanism here. "Touches the same function" is `relates_to`; "the mechanism this issue proposes
does not work until that issue lands" is `blocked_by`.

## Integration Map

### Files to Modify

- `skills/refine-issue/SKILL.md` (or `commands/refine-issue.md`) — dependency-classification and
  frontmatter-promotion step

### Tests

- Skill-prose assertions for the promotion step and the `blocked_by` vs `relates_to` discriminator,
  following the structural convention used for LLM-executed skills

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 — the information survives either way; this makes it actionable
- **Effort**: Small — prose change to the skill, no new mechanism
- **Risk**: Low-Medium — over-eager promotion produces spurious `blocked_by` edges that stall
  sprint dequeue. The correctness-based discriminator is what keeps it bounded.
- **Breaking Change**: No

## Related Key Documentation

- BUG-3278 / BUG-3279 — the pair where the hard dependency was filed as a soft note
- `.claude/CLAUDE.md` § Issue File Format — deferral discriminator and which statuses resolve a
  `blocked_by` edge

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
