---
id: BUG-3295
type: BUG
title: unapplied_decision flags bare key mentions as discriminating identifiers
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T21:27:39Z'
---

# BUG-3295: unapplied_decision flags bare key mentions as discriminating identifiers

## Summary

`_unapplied_decision()`'s decision-gap detector produces false-positive
`unapplied_decision` findings whenever a decision is about "what literal value
to assign to some field/key" and any option's prose mentions the bare key
name as its own backtick span. The root cause is structural, not a wording
quirk on any one issue: it will recur on any similarly-shaped decision.

## Current Behavior

`_decision_identifiers()` (`scripts/little_loops/issue_parser.py:1401-1403`,
regex `_DECISION_IDENTIFIER_RE = re.compile(r"`([^`\n]{3,})`")` at `:1379`)
extracts each backtick-delimited span as one opaque, atomic string. There is
no relationship between a bare identifier (e.g. `` `scope:` ``) and any
compound identifier that embeds it as a substring (e.g.
`` `scope: ["scripts/"]` ``, `` `scope: ["."]` ``).

In `_unapplied_decision()` (`:1499` onward, the `discriminating = rej_ids -
sel_ids` set-difference around `:1572`): if the selected option always writes
the full literal (`` `scope: ["."]` ``) but a rejected option happens to
mention the bare key alone anywhere in its own text (natural phrasing:
"...then change `` `scope:` `` to `` `["${context.src_dir}"]` ``"), the bare
key lands in `discriminating` even though both options are about the same
field, not competing identifiers. The second pass then greps every directive
section for that literal bare-backtick substring and fires on any narrative
mention of the field name — common, not rare, in this codebase's
issue-writing convention (heavily backtick-quoted, mechanism-explaining prose
from `/ll:refine-issue` and `/ll:wire-issue`).

**Reproduced on ENH-3292** (`.issues/enhancements/P3-ENH-3292-*.md`): Option A
(selected) writes `scope: ["scripts/"]` -> `scope: ["."]`; Option B (rejected)
contains the bare span `` `scope:` `` once. That bare `scope:` is not in
Option A's identifier set (which only has the compound literal spans), so it
is flagged as "discriminating," and then matches 27 separate bare `` `scope:`
`` mentions elsewhere in the issue's Program Design/Acceptance
Criteria/Motivation sections that are pure narrative explanation — producing
a spurious `unapplied_decision` gap that caps `/ll:confidence-check`'s
Ambiguity criterion at 10/25 for a fully-decided, well-specified issue.

## Expected Behavior

A bare identifier that is a substring of / subsumed by a compound identifier
already present in the selected option's identifier set should not count as
"discriminating." `_decision_identifiers`/`_unapplied_decision` need a real
containment/equivalence relationship between backtick spans, not pure
atomic-string set difference.

## Motivation

This is not an isolated glitch — it is the same option-locator/decision-
identifier subsystem that already has two other false-negative/invisibility
bug reports on file:

- BUG-3287: two shapes of tier-match/bullet-tier misses
- BUG-3293: bold-numbered decision points invisible to tier scan and Pattern E

This is a fourth flavor of the same still-maturing heuristic family
(introduced by ENH-3256), and it will keep recurring on any "pick a literal
value for field X" decision issue unless the underlying identifier-
relationship gap is fixed — not just patched for this one field name.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`scripts/little_loops/issue_parser.py:1379` (`_DECISION_IDENTIFIER_RE`) and
`:1401-1403` (`_decision_identifiers`) extract whole backtick spans as
opaque, unrelated strings. `_unapplied_decision`'s `discriminating = rej_ids
- sel_ids` (`:1572`) then treats a bare key span and a compound literal
containing that key as unrelated identifiers, so a rejected option's
incidental bare-key mention gets promoted to "discriminating" even when the
selected option's own text fully covers that key via a longer literal.

## Scope Boundaries

**In scope**: fixing the identifier-relationship gap in
`_decision_identifiers`/`_unapplied_decision` so a bare key subsumed by a
compound literal in the selected option is not treated as discriminating.

**Out of scope**: a special case for `scope:` or for this specific issue's
wording — that would just be another one-off patch on the same brittle
detector, reproducing the exact pattern this bug exists to stop. Also out of
scope: BUG-3287 and BUG-3293's own (different) invisibility shapes in the
option-locator tier scan — those are separate, already-filed defects in a
different function (`_locate_directive_alternatives` / tier matching, not
`_decision_identifiers`).

## Related Key Documentation

- BUG-3287 — prior false-negative shapes in the same option-locator family
- BUG-3293 — bold-numbered decision points invisible to tier scan/Pattern E
- ENH-3256 — introduced `_unapplied_decision`
- ENH-3292 — where this false positive was discovered during
  `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-22 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-22T21:27:47 - `1c97624b-6c5a-4655-8896-9cd12a9f503b.jsonl`
