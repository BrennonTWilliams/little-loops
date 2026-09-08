---
id: BUG-3412
type: BUG
title: check-unresolved-decisions merges sibling decision points sharing a tier into
  one group
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T19:44:58Z'
---

# BUG-3412: check-unresolved-decisions merges sibling decision points sharing a tier into one group

## Summary

[Description extracted from input]

## Current Behavior

`ll-issues check-unresolved-decisions <ID>` (backed by `locate_unresolved_decisions()` /
`is_group_resolved()` in `scripts/little_loops/issue_parser.py`) can report "no unresolved
decision group remains" (exit 0) even when a real, un-decided decision point remains in the
issue's `## Proposed Solution` section — as long as it shares its option-block tier with an
already-decided sibling decision point in the same section.

Root cause: `_decision_groups_in_body()` splits a section's tagged option-block matches into
`DecisionGroup`s only on a *tier change* (e.g. `bold_label` -> `numbered`) or when a Pattern E
directive window falls between two matches — never on a `**Decision point:**` prose boundary.
When a `## Proposed Solution` section contains several distinct "Decision point:" blocks that
all happen to use the same tier (e.g. all `**Option A**/**Option B**` bold-label blocks in a
row, with no intervening tier change), they get merged into a single `DecisionGroup` spanning
the whole run.

`is_group_resolved()` then returns `True` for that merged group as soon as **any** member
option's span carries a `> **Selected:**` callout — it has no way to know the merged group
actually represents 3-4 independent decision points, only one of which was decided.

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

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

`/ll:decide-issue`'s Phase 7b and Phase 3b step 4 gate clearing `decision_needed` directly on
this check's exit code. In `--auto` mode, an issue whose Proposed Solution section holds
multiple same-tier decision points can have `decision_needed` silently cleared after only one
of them is actually decided — the remaining decision point(s) stay unresolved in the issue body
but the frontmatter flag no longer signals it, so downstream automation (`/ll:wire-issue`,
`/ll:manage-issue`) proceeds as if the issue were fully decided.

## Steps to Reproduce

1. Create (or find) an issue whose `## Proposed Solution` section has 2+ separate
   `**Decision point:** ...` blocks, each followed by `**Option A**`/`**Option B**` bold-label
   option pairs, with no section-header-tier options and no Pattern E directive between them.
2. Resolve only the *first* decision point by inserting a `> **Selected:** Option A — ...`
   callout on its winning option. Leave the second (or later) decision point's options with no
   Selected callout (e.g. only a `**Recommended**: Option B` line, or nothing at all).
3. Run `ll-issues check-unresolved-decisions <ID>`.

**Expected**: exit 1, naming the still-undecided decision point as an unresolved group.

**Actual**: exit 0 — "No unresolved decision group remains" — because the two decision points
were merged into one `DecisionGroup` by `_decision_groups_in_body()`, and the first decision
point's Selected callout satisfies `is_group_resolved()` for the whole merged group.

## Discovered Via

Live `/ll:decide-issue FEAT-3409 --auto` run (2026-09-08). FEAT-3409's `## Proposed Solution`
section has 4 `**Decision point:**` blocks, all using the `bold_label` tier
(`**Option A**/**Option B**/**Option C**`), with 3 already resolved via `> **Selected:**`
callouts and a 4th ("Default `manifest_path` resolution") left only with a declarative
`**Recommended**: Option B` line (no Selected callout). `ll-issues check-unresolved-decisions
FEAT-3409` reported 0 unresolved groups despite the 4th decision point being genuinely
undecided. Caught by manual inspection, not by the tool.

## Files to Modify

- `scripts/little_loops/issue_parser.py` — `_decision_groups_in_body()` (the run-splitting
  loop, currently keyed only on `tier_name == prev_tier` and `directive_between`) needs to also
  split a run when a `**Decision point:**` marker (or equivalent decision-point boundary text)
  falls between two consecutive same-tier matches, mirroring the existing `directive_between`
  boundary check.
- `scripts/little_loops/issue_parser.py` — `is_group_resolved()`'s single-Selected-callout check
  is otherwise correct per-group; the fix belongs in group construction, not resolution.

## Acceptance Criteria

- A `## Proposed Solution` section with 2+ `**Decision point:**` blocks sharing the same option
  tier is split into separate `DecisionGroup`s by `_decision_groups_in_body()`.
- `ll-issues check-unresolved-decisions` correctly reports an unresolved group when only some
  same-tier decision points in a section have been decided.
- Regression test reproducing the FEAT-3409 shape: 2+ same-tier decision points in one section,
  only the first decided, asserting `check-unresolved-decisions` still reports the second as
  unresolved.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-08T19:45:05 - `ce7357ff-ca14-4ec7-8141-84e7fba71ec5.jsonl`
