---
id: ENH-3045
title: 'Replacement parity + negative-claim doctrine for /ll:wire-issue and /ll:refine-issue'
type: ENH
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: "2026-08-04T20:47:11Z"
relates_to:
- FEAT-3048
- FEAT-2942
labels:
- skills
- issues
- quality
---

# ENH-3045: Replacement parity + negative-claim doctrine for wire/refine

## Summary

Two related doctrine changes to `/ll:wire-issue` and `/ll:refine-issue`, both instances of the
same blind spot — **the passes examine the codebase and the issue, but never the artifact the
issue is about to replace, and never justify a negative finding**:

1. **Replacement parity** — when an issue rewrites, deletes, or delegates away an existing
   artifact, require a `### Behavior Parity` subsection enumerating each behavior of the old
   artifact with a disposition (preserved / changed / dropped + why).
2. **Negative-claim doctrine** — a conclusion of the form "no existing implementation exists"
   must name what was searched, and must search by *capability*, not by algorithm name.

Explicitly **not** parented to EPIC-2938: that epic's Scope excludes rewriting reasoning-heavy
skills like `refine-issue`, and these are prompt/doctrine changes, not prose→CLI conversions.

## Current Behavior

**Parity.** Nothing in either skill reads the artifact being replaced.
`skills/wire-issue/SKILL.md` Phase 5 diffs agent findings against `EXISTING_WIRING` extracted
from the *issue*; Phase 8c is literally a "Preservation Rule" protecting text already present.
`commands/refine-issue.md` researches the codebase for gaps but has no replaced-artifact step.

Measured cost on FEAT-2942, which deletes a 362-line skill — three defects, all the same shape,
all behaviors that existed only in the artifact being deleted and were never transcribed:

- Scoring corpus silently narrows from **title + `## Summary`** (`skills/link-epics/SKILL.md`)
  to **title-only** (`IssueInfo` has no summary field; `find_similar`/`batch_similarity` score
  titles only) — a real signal regression nothing flagged.
- The HIGH/MEDIUM/LOW **tier boundaries (0.7/0.4)** appear nowhere in the issue, though
  `EpicProposal.tier` is declared.
- The definition of **"orphan"** — the term the whole feature turns on — exists only in the
  skill being deleted.

**Negative claims.** `/ll:wire-issue` wrote into FEAT-2942:

> No union-find/disjoint-set implementation exists anywhere in `scripts/little_loops/` today
> (confirmed by grep) — `synthesize_clusters()` is new code.

Literally true, materially wrong: it grepped for the **algorithm name**. `batch_similarity()`
in `scripts/little_loops/cli/issues/find_similar.py` already performs the exact O(n²) pairwise
`calculate_word_overlap` scan that produces the edge list `synthesize_clusters()` needs. A grep
for *callers of the shared primitive* would have surfaced it immediately.

## Expected Behavior

**Parity.** When an issue names an existing file it will rewrite/delete/delegate away, wire and
refine emit a `### Behavior Parity` subsection under Integration Map:

```markdown
### Behavior Parity — skills/link-epics/SKILL.md

| Behavior | Disposition | Notes |
|---|---|---|
| Scores title + `## Summary` | CHANGED | CLI scores title only — accepted regression? |
| Tiers HIGH/MED/LOW at 0.7/0.4 | DROPPED | not carried into CLI spec |
| Orphan = open BUG/FEAT/ENH, no `parent:` | PRESERVED | must be restated in the CLI spec |
```

**Negative claims.** Before concluding "no existing implementation," the agent must search by
capability — the input/output shape, and the callers of the shared primitive the new code
would call — and the resulting claim must state what was searched.

## Motivation

Parity alone accounts for 3 of the 7 defects found reviewing FEAT-2942 after three passes; the
negative-claim fix accounts for a 4th. Both are prompt-level changes to skills that already do
the surrounding research — very high ratio of caught defects to effort. They combine because
they are the same instruction to the same two skills: *look at what you are replacing, and say
what you looked for.*

## Proposed Solution

- **Wire** (`skills/wire-issue/SKILL.md`): add a replaced-artifact extraction step alongside
  Phase 3's `EXISTING_WIRING`; emit the parity table in Phase 8a; add the capability-search
  requirement to the Agent 1 and Agent 3 prompts (Phase 4).
- **Refine** (`commands/refine-issue.md`): same parity requirement in its Integration Map
  emission (Step 5a).
- **Detection** (optional, same change): a `missing_behavior_parity` gap kind in
  `check_format_gaps()` — issue cites a file it will rewrite, that file exists, no
  `### Behavior Parity` section. Follows the `ENH-2946` precedent for adding gap kinds and
  makes the doctrine enforceable rather than advisory.

`/ll:wire-issue` is a skill and `/ll:refine-issue` is a command — both markdown, but confirm
the wire skill's line budget (`ll-verify-skills` caps `SKILL.md` at 500 lines; it is currently
455) and extract to a companion file per the ENH-494 pattern if the addition overflows.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 3/4/8a changes (watch the 500-line cap; 455 today)
- `commands/refine-issue.md` — Integration Map emission step
- `scripts/little_loops/issue_parser.py` + `cli/issues/format_check.py` — optional gap kind
- `scripts/tests/test_wire_issue_static_layer.py` and
  `scripts/tests/test_refine_issue_command.py` — the existing structural test homes for these
  two artifacts; extend rather than adding a new test module
- `docs/reference/COMMANDS.md` — updated descriptions

### Similar Patterns
- `ENH-2946` — extending `format-check` with new gap kinds
- `ENH-494` — SKILL.md companion-file extraction when over the line cap

## Implementation Steps

1. Add the parity step + table emission to wire and refine.
2. Add the capability-search requirement to wire's Agent 1/3 prompts.
3. Optional `missing_behavior_parity` gap kind + tests.
4. Validate against FEAT-2942: parity table surfaces the corpus/tier/orphan gaps.

## Impact

- **Priority**: P2 — 4 of 7 observed defects, prompt-level effort
- **Effort**: Low-Medium — markdown doctrine; optional small Python gate
- **Risk**: Low — additive; worst case is a parity table on issues that don't need one

## Related Key Documentation

- `.claude/CLAUDE.md` § Development Preferences — prefer Skills over Agents
- `docs/reference/COMMANDS.md` — `/ll:wire-issue`, `/ll:refine-issue` descriptions

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-04T20:50:27 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
