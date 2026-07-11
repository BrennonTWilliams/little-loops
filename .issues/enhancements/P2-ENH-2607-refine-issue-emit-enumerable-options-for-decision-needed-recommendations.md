---
id: ENH-2607
title: refine-issue should emit enumerable options when depositing a decision recommendation
type: ENH
status: open
priority: P2
captured_at: "2026-07-11T18:07:11Z"
discovered_date: "2026-07-11"
discovered_by: capture-issue
relates_to:
- BUG-2605
- BUG-2606
- ENH-2443
labels:
- refine-issue
- decision-gate
- skills
---

# ENH-2607: refine-issue should emit enumerable options when depositing a decision recommendation

## Summary

`/ll:refine-issue --auto`'s "Option-Count Detection" step
(`commands/refine-issue.md:284-296`) only sets `decision_needed: true` when it
detects 2+ options matching one of three formal patterns (numbered top-level
items, `### Option A/B/C` headers, or `**Option A/B**` bold labels). When a
research pass identifies competing alternatives but writes them as inline
prose with a recommendation (e.g. "Two viable resolutions: (a) ... or (b) ...
Recommendation: X for v1" — the actual shape of ENH-2492's stuck decision),
none of the three patterns match, so `decision_needed` is left as whatever it
already was. Combined with the Preservation Rule (`refine-issue.md:307-323`,
"append, don't replace, when a section already has meaningful content"),
subsequent refine passes never restructure that prose into a machine-decidable
shape — the issue can cycle through refine indefinitely without ever
acquiring real `### Option A/B` blocks.

## Current Behavior

`ll-issues check-decidable` reports `OPTIONS_MISSING` for ~40 of ~70 issues
currently flagged `decision_needed: true` in this repo's own backlog — the
large majority of them contain a clear prose recommendation naming named
alternatives (matching decide-issue's own Phase 3b Pattern D shape) but never
in a form `count_enumerable_options()` (Patterns 1-4,
`scripts/little_loops/issue_parser.py:285-307`) recognizes.

## Expected Behavior

When refine-issue's research pass (Step 5a / Enrichment Rules) identifies a
decision point with named alternatives — whether from fresh research or from
existing prose it's about to append findings near — it formats the
alternatives using one of the three recognized patterns (bold `**Option A**`
labels are the lowest-friction fit for inline recommendations) rather than
leaving them as unstructured prose. This makes `decision_needed: true`
issues machine-decidable by construction, closing the gap that BUG-2605 and
BUG-2606 currently have to work around after the fact.

## Motivation

BUG-2605 and BUG-2606 fix the *consumption* side (the FSM and the decide-issue
skill both now get more chances to salvage a prose-only decision). This issue
fixes the *production* side: if refine-issue reliably deposits options in a
recognized shape to begin with, decide-issue's Phase 3b provisional-scan
fallback becomes a safety net instead of the primary mechanism, and future
issues don't join the backlog of ~40 stuck ones. Root-causing this prevents
the failure class from recurring as new issues get refined, rather than only
treating issues already in the backlog.

## Proposed Solution

Extend the "Option-Count Detection" enrichment rule
(`commands/refine-issue.md:284-296`) with a fourth case: when the research
pass is about to write a decision point that names 2+ concrete alternatives
(the same shape decide-issue's Phase 3b Pattern D already looks for — a
recommendation naming one option among several named alternatives), format it
as:

```markdown
**Option A**: [first alternative, verbatim from the research/existing text]

**Option B**: [second alternative, verbatim from the research/existing text]

**Recommended**: Option [X] — [existing rationale, preserved verbatim]
```

placed under the relevant subsection (e.g. as a `### Codebase Research
Findings` addendum near the original prose, per the existing Preservation
Rule — this is additive, not a rewrite of the original text) so
`count_enumerable_options()` picks it up via the `**Option A**` bold-label
pattern (Pattern 2) without requiring any parser changes.

This is scoped to refine-issue's *own* freshly-written research content —
it does not retroactively rewrite pre-existing human-authored prose it
didn't write, consistent with the Preservation Rule.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — extend the Option-Count Detection section
  (lines 284-296) with the bold-label formatting rule described above.

### Similar Patterns
- `commands/refine-issue.md:246-269` (Integration Map / Root Cause enrichment
  templates) — existing precedent for structured markdown templates the
  command already asks refine to emit.
- `skills/decide-issue/SKILL.md:241-249` (Provisional Pattern D) — the exact
  shape this fix aims to make refine-issue produce natively instead of
  requiring decide-issue to reverse-engineer it from prose.

### Tests
- No existing automated test targets refine-issue's markdown-generation
  prose (LLM-driven, not Python). Verify manually against 2-3 issues with
  prose-only recommendations (e.g. run `/ll:refine-issue --auto` on a fresh
  copy of ENH-2492's decision text) and confirm
  `ll-issues check-decidable` reports `Decidable` afterward instead of
  `OPTIONS_MISSING`.

## Implementation Steps

1. Add the bold-label decision-formatting rule to refine-issue.md's
   Option-Count Detection section.
2. Manually verify against a sample of currently-stuck issues that a fresh
   `/ll:refine-issue --auto` pass now produces `**Option A/B**` blocks
   `check-decidable` recognizes.
3. Consider (follow-on, not in scope here) a one-time bulk remediation pass
   over the ~40 already-stuck issues once BUG-2605/BUG-2606/this land, since
   existing prose won't retroactively reformat itself.

## Impact

- **Priority**: P2 - Root-causes the failure class that BUG-2605/BUG-2606
  otherwise only mitigate after the fact; prevents backlog regrowth.
- **Effort**: Medium - prompt-instruction tuning in a skill/command markdown
  file; needs sampling against real stuck issues to validate the formatting
  rule actually produces Pattern-2-matching output reliably.
- **Risk**: Medium - imprecise prompt wording could either fail to trigger
  (no improvement) or over-trigger (spuriously setting `decision_needed: true`
  on issues with a single clear recommendation and no real ambiguity); needs
  validation against several issue shapes before considering it converged.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/issue_parser.py` | `count_enumerable_options()` — the Pattern 1-4 logic this fix targets |
| `.claude/CLAUDE.md` | Development Preferences — skill/command authoring conventions |

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-11T18:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`
