---
id: BUG-3413
type: BUG
title: unapplied_decision false-positives on multi-decision-point issues
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T22:42:47Z'
---

# BUG-3413: unapplied_decision false-positives on multi-decision-point issues

## Summary

`_unapplied_decision_pairs()` in `scripts/little_loops/issue_parser.py:1550` (backs
`format-check`'s `unapplied_decision`/`DECISION_GAP` field, consumed by
`/ll:confidence-check`'s Criterion C scoring) assumes an issue's `## Proposed Solution`
section contains exactly one decision point. When a section has 2+ independent decision
points (each with its own `**Option A/B(/C)**` blocks and its own `> **Selected:**`
callout), the function false-positives: it treats every option block except the one
matching the *first* `Selected` callout's label as "rejected," including the winning
options of the other decision points.

Confirmed on `.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`
during a `/ll:confidence-check FEAT-3409` run: `HistoryConfig`, the winning Option A
identifier for that issue's 3rd decision point ("Config registration path"), was
flagged as a leftover rejected-option mention purely because it wasn't part of decision
point 1's winning block ("Malformed-manifest posture", Option C).

## Context

Identified during `/ll:resume` follow-up investigation of a continuation-prompt task:
a `/ll:confidence-check FEAT-3409` run flagged `DECISION_GAP` on terms that also
appeared in FEAT-3409's own selected-option text, suspected as a possible detector
false-positive rather than genuine leftover rejected-option prose. Root-caused as
above.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

`_unapplied_decision_pairs()` groups option blocks by decision point (splitting on the
same `**Decision point:**` marker boundary BUG-3412 uses), resolves a `sel_ids`/
`rej_ids` pair independently per group, and unions the resulting `discriminating`
identifiers across groups — so a winning option's identifiers from decision point N
are never treated as "rejected" leftovers just because they weren't decision point 1's
winner.

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

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`_unapplied_decision_pairs()`:
1. Calls `_selected_option_title()`, which returns the title from the *first*
   `> **Selected:**` callout in the whole `## Proposed Solution` body (by design, per
   its own docstring — correct for the single-decision case).
2. Calls `_option_block_spans()`, which returns *every* option block in the section
   flattened into one list, with no grouping by decision point.
3. Matches `selected_index` to the single span whose heading label equals that one
   title's option label (e.g. "option c").
4. Puts every *other* span's identifiers into `rej_ids` — including the winning
   options of decision points 2, 3, 4, ... which were never wrong, just not decision
   point 1's winner.

Reproducer:

```python
from little_loops.issue_parser import _unapplied_decision_pairs
content = open(".issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md").read()
print(_unapplied_decision_pairs(content))
# 22 pairs, including ('Implementation Steps', 'HistoryConfig') and
# ('Program Design', 'manifest_path') — HistoryConfig is decision point 3's
# WINNING identifier, not a rejected-option leftover.
```

## Relation to BUG-3412

Sister bug, same root symptom ("multiple decision points sharing state get
conflated"), different code path. BUG-3412 covers `_decision_groups_in_body()` /
`is_group_resolved()` (backing `ll-issues check-unresolved-decisions`), which merges
same-tier decision points into one `DecisionGroup`. This issue covers
`_unapplied_decision_pairs()` (backing `format-check`'s `unapplied_decision` /
`DECISION_GAP`), which is a structurally separate function built on
`_option_block_spans()` directly — it does not call `_decision_groups_in_body()` at
all, so BUG-3412's fix does not touch it.

BUG-3412's in-progress fix (uncommitted on `main` at investigation time) adds
`_DECISION_POINT_MARKER_RE` / `_decision_point_marker_positions()` to detect
`**Decision point:**` prose/heading boundaries. The fix for this issue can likely
reuse those same primitives to group `_option_block_spans()`'s flat span list by
decision point, then compute `sel_ids`/`rej_ids` (and the existing BUG-3295
containment exclusion, BUG-3289 shared-subject exclusion) per group instead of
globally, before merging the per-group `discriminating` sets.

## Corpus Impact

At investigation time, `.issues/features/P1-FEAT-3409-...md` is the only issue in the
corpus with 2+ decision points in `## Proposed Solution` (verified via a scripted scan
of all `.issues/**/*.md`), so live blast radius is narrow today. The bug will recur
for any future issue authored with multiple decision points in one section — an
increasingly common convention per ENH-3256's per-decision-point authoring pattern.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-08T22:42:53 - `4f0efb73-1906-4514-9695-1db0defa8ce3.jsonl`
