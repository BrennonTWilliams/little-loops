---
id: BUG-3414
type: BUG
title: unapplied_decision checker conflates identifiers across multiple decision points
  in one issue
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T23:54:29Z'
labels:
- issue-parser
- format-check
- confidence-check
- false-positive
---

# BUG-3414: unapplied_decision checker conflates identifiers across multiple decision points in one issue

## Summary

[Description extracted from input]

## Current Behavior

`_unapplied_decision_pairs()` (`scripts/little_loops/issue_parser.py:1550-1691`, the
`unapplied_decision` gap class backing `ll-issues format-check` and
`/ll:confidence-check`'s `DECISION_GAP`) only scopes itself to **one** decision point
per issue, even when `## Proposed Solution` documents several:

1. `_selected_option_title()` (`:1402-1412`) reads the **first**
   `> **Selected:**` callout in the whole `Proposed Solution` body.
2. `_option_block_spans()` (`:1494-1535`) enumerates **every** `### Option X` /
   `**Option X**` heading across the **entire** section, not scoped per
   decision point.
3. `matching = [... if _option_label(heading) == label]` (`:1620`) finds the one
   block whose label matches the first callout's option letter — call it
   `selected_index`.
4. Every other block in the section — `rej_ids` (`:1626-1629`) — is unioned
   together and treated as "rejected", **including the selected option of every
   other decision point** in the same issue, because those blocks don't carry
   the first decision's option letter.

Result: on an issue with N decision points, decisions 2..N contribute their own
**selected** identifiers into `rej_ids` for decision 1's scan, and those
identifiers then fire as `unapplied_decision: "<section> still specifies
`<identifier>` (rejected option)"` even though the implementer correctly
implemented them.

## Expected Behavior

The function should scope `rej_ids` to a **single decision point's** block
group at a time, iterating over every `> **Selected:**` callout in the
section rather than only the first one, and only flagging identifiers unique
to blocks that share that decision point's own group (bounded by the option
headings between one decision point and the next, or by a decision-separator
convention already in use — e.g. `**Decision point:**` bold-lead-in lines, as
seen in `FEAT-3409`'s own Proposed Solution structure). An identifier
belonging to a *different* decision point's blocks (selected or rejected)
must never be treated as "rejected" input for a decision point it doesn't
belong to.

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

- **Priority**: P2 — inflates `unapplied_decision`/`DECISION_GAP` false
  positives on any issue with more than one resolved decision point in
  `## Proposed Solution`, which caps Criterion C (Ambiguity) in
  `/ll:confidence-check`'s outcome-confidence scoring even when every
  decision is genuinely resolved and correctly reflected in the directive
  sections. `FEAT-3409` scored `score_ambiguity: 10/25` almost entirely on
  this false-positive list.
- Does not block readiness (`unapplied_decision` is advisory, per
  `_ADVISORY_GAP_CLASSES`-adjacent framing in `/ll:confidence-check`'s Phase
  1.8) but degrades outcome-confidence signal quality and would mislead a
  contributor trying to "clean up" a well-formed issue by stripping
  load-bearing selected-option content to satisfy the checker.
- **Effort**: Medium — needs to group option blocks by decision point before
  the rej/sel split, likely keyed off the nearest preceding decision-point
  marker or by treating consecutive callout-to-callout spans as one group.
- **Breaking Change**: No — corpus-facing output only; existing single-decision-point
  issues (the common case, covered by `TestUnappliedDecisionLiveCorpusSweep`)
  are unaffected since grouping is a no-op when there's exactly one decision
  point.

## Reproduction

`.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`
has four `## Proposed Solution` decision points, each with its own
`> **Selected:**` callout:

1. Malformed-manifest posture — Selected: **Option C**
2. `db_path` derivation — Selected: **Option A** (identifiers include
   `history.db_path`, `resolve_history_db(root=member.repo_path)`, `root=`)
3. Config registration path — Selected: **Option A**, nest under
   `history.workspace_manifest_path` (identifiers include
   `history.workspace_manifest_path`, `HistoryConfig`, `manifest_path`,
   `config/features.py:1513-1554`)
4. Default `manifest_path` resolution — Selected: **Option B**, subsequently
   revised (identifiers include `decisions.py::_resolve_path()`, `root=`)

`ll-issues format-check FEAT-3409 --format json` reports 26 `unapplied_decision`
entries. Every one of them names an identifier from decision 2, 3, or 4's
blocks — none from decision 1's own rejected options (A/B) — because the
first callout matched is decision 1's ("Option C"), so decisions 2-4's blocks
(both their selected *and* rejected halves) are indiscriminately folded into
`rej_ids`. `history.workspace_manifest_path` and `HistoryConfig` are decision
3's own **selected** identifiers, flagged as "rejected option" — a false
positive.

Confirmed by direct call:

```python
from little_loops.issue_parser import _unapplied_decision_pairs
content = Path(".issues/features/P1-FEAT-3409-....md").read_text()
pairs = _unapplied_decision_pairs(content)
# 26 pairs; all four decision points' identifiers appear despite three of
# the four being resolved and implemented correctly per their own callouts.
```

## Files to Modify

- `scripts/little_loops/issue_parser.py:1550-1691` (`_unapplied_decision_pairs`) —
  add decision-point grouping before the `matching`/`rej_ids` computation.
- `scripts/tests/test_issue_parser.py` — `TestUnappliedDecision` (`:5228`) and
  `TestUnappliedDecisionLiveCorpusSweep` (`:5743`) have no case with more than
  one `> **Selected:**` callout in the same `Proposed Solution` section; add
  one.

## Acceptance Criteria

- A `## Proposed Solution` section with two or more decision points (each its
  own `> **Selected:**` callout and its own `### Option X` / `**Option X**`
  group) produces `unapplied_decision` entries only for identifiers
  discriminating within the *same* decision point as the callout they belong
  to.
- A regression test built from (or equivalent to) `FEAT-3409`'s four-decision-point
  structure asserts zero `unapplied_decision` false positives for its three
  fully-resolved, correctly-implemented decisions, while still catching a
  genuine unapplied-rejected-option case within a single decision point.
- Existing single-decision-point corpus behavior (`TestUnappliedDecisionLiveCorpusSweep`)
  is unchanged.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2
