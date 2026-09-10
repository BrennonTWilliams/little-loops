---
id: BUG-3414
type: BUG
title: unapplied_decision checker conflates identifiers across multiple decision points
  in one issue
priority: P2
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T23:54:29Z'
labels:
- issue-parser
- format-check
- confidence-check
- false-positive
relates_to:
- BUG-3413
closed_reason: superseded
---

# BUG-3414: unapplied_decision checker conflates identifiers across multiple decision points in one issue

## Summary

`_unapplied_decision_pairs()` (`scripts/little_loops/issue_parser.py:1550-1691`)
scopes itself to only the **first** decision point when `## Proposed Solution`
documents 2+, so every other decision point's own **selected** option blocks
get unioned into `rej_ids` and reported as false-positive `unapplied_decision`
entries.

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
3. `matching = [i for i, (_, _, heading) in enumerate(group) if _option_label(heading) == label]`
   (`:1829`) finds the one block whose label matches the first callout's
   option letter — call it `selected_index`.
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

- Inflates `unapplied_decision`/`DECISION_GAP` false positives on any issue
  with 2+ resolved decision points in `## Proposed Solution`, which caps
  Criterion C (Ambiguity) in `/ll:confidence-check`'s outcome-confidence
  scoring even when every decision is genuinely resolved — `FEAT-3409` scored
  `score_ambiguity: 10` (out of a 25-point scale) almost entirely on this
  false-positive list.
- Though advisory (does not block `/ll:ready-issue`), the noise could mislead
  a contributor into stripping load-bearing selected-option content from a
  well-formed issue just to satisfy the checker.
- Multi-decision-point issues are a growing authoring convention, so the
  false-positive rate climbs without a fix.

## Proposed Solution

Scope `_unapplied_decision_pairs()`'s `rej_ids` computation to one decision
point at a time instead of unioning across the whole `## Proposed Solution`
section:

1. Iterate every `> **Selected:**` callout in the section (not just the
   first, as `_selected_option_title()` currently does) to get one winning
   label per decision point.
2. Group `_option_block_spans()`'s flat span list so each group contains only
   the option blocks belonging to one decision point — bounded by consecutive
   callouts or an existing decision-separator convention (e.g.
   `**Decision point:**` lines, per `FEAT-3409`'s own structure).
3. Within each group, compute `sel_ids`/`rej_ids` against that group's own
   callout only; never let another group's blocks (selected or rejected) leak
   into the current group's `rej_ids`.
4. Union each group's own `rej_ids` (minus each group's own `sel_ids`) across
   all groups for the function's final return.

Note: `BUG-3413` (open, same file/function) proposes a related but broader
grouping mechanism (marker + heading + label-restart boundary rules) covering
this same false-positive plus a companion false-negative mode. Check
`BUG-3413`'s status before starting — the two may converge on one
implementation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

**Status check against the current working tree (uncommitted)**: `scripts/little_loops/issue_parser.py` already contains an uncommitted fix for `BUG-3413` — `_decision_point_boundary_positions()` (`issue_parser.py:1545-1566`) and `_group_spans_by_decision_point()` (`issue_parser.py:1569-1604`), wired into `_unapplied_decision_pairs()` at `issue_parser.py:1654-1656`. It groups `_option_block_spans()`'s flat span list per decision point and computes `sel_ids`/`rej_ids` independently within each group (`issue_parser.py:1661-1748`), which structurally eliminates the conflation this issue describes: `_selected_option_title()`/`matching` are now resolved per group (`region_start`/`region_end` scoped to that group's own span range, `:1710-1725`), so a later decision point's own winner can no longer be compared against an earlier decision point's `> **Selected:**` label. The actual helper name in the tree is `_group_spans_by_decision_point` (BUG-3413's naming) — this issue's own `## Program Design` names a differently-spelled helper, `_group_option_blocks_by_decision_point()`, which does not exist anywhere in the codebase.

Re-running `_unapplied_decision_pairs()` against the file this issue cites for reproduction (`.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`, unchanged on disk since this issue was captured) against the current working tree returns 9 pairs, down from the 26 this issue reports. Neither of this issue's cited false positives (`HistoryConfig`, `history.workspace_manifest_path` — decision point 3's own selected identifiers) appears in the current output.

Both of this issue's Acceptance Criteria are satisfied by the current (uncommitted) implementation:
- "unapplied_decision entries only for identifiers discriminating within the same decision point" — the remaining 9 pairs are decision point 2's and 3's own genuinely-rejected identifiers (e.g. `resolve_history_db(root=member.repo_path)`, `root=`, `LL_HISTORY_DB` from decision point 2's rejected Option B at FEAT-3409:383; `config/core.py`, `_DATACLASS_SECTION_MAP` from decision point 3's rejected Option B), never another decision point's winner.
- "zero unapplied_decision false positives for [FEAT-3409's] three fully-resolved, correctly-implemented decisions" — confirmed by the same run.

The residual 9 pairs are a separate, already-documented, out-of-scope detector limitation (genuinely-rejected identifiers narratively re-mentioned in `Program Design`/`Files to Modify`/`Acceptance Criteria` prose explaining why they were rejected) — `BUG-3413`'s own Implementation Steps item 4 explicitly anticipates this exact residual and excludes it from its own correctness bar, naming `config/core.py` as an example.

Test coverage for the uncommitted fix is in place and passing: `python -m pytest scripts/tests/test_issue_parser.py -k "UnappliedDecision or Bug3295"` (31 passed), `scripts/tests/test_decide_issue_skill.py -k "Phase7cFixtures"` (9 passed, including `test_bug_3413_multi_decision_point_winner_never_reported` built from this exact FEAT-3409 shape), and `scripts/tests/test_ll_issues_format_check.py -k "MultiPoint"` (1 passed) — confirmed in this pass.

This issue's own text already named the possibility this research confirms: "Check `BUG-3413`'s status before starting — the two may converge on one implementation." They have converged: `BUG-3413` (still `status: open` in frontmatter despite the implementation, all five of its named test shapes, its corpus-differential update, and its golden fixture all being present, passing, and uncommitted in the working tree) is the issue this fix was built against.

This codebase's established convention for two issues that converge on one implementation is `supersedes: [ID]` frontmatter on the surviving issue plus `status: cancelled` on the other (`.claude/CLAUDE.md` § Issue File Format; example: `EPIC-3336` frontmatter `supersedes: [BUG-3331]` paired with `BUG-3331` frontmatter `status: cancelled`). Whether that convention applies here, and to which of the two issues, is a disposition decision this pass does not make.

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

Ordering check: if `BUG-3413` lands (or is committed) after this issue is closed on its own, no additional work is needed — `BUG-3413`'s fix already satisfies this issue's Acceptance Criteria in full (confirmed above), so there is nothing for a hypothetical independent BUG-3414-only implementation to add or conflict with.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py:1550-1691` (`_unapplied_decision_pairs`)

### Dependent Files (Callers/Importers)
- `ll-issues format-check` (surfaces `unapplied_decision`)
- `/ll:confidence-check` (Criterion C / `DECISION_GAP` scoring)

### Similar Patterns
- `BUG-3413` — same function, an overlapping/broader fix for the same
  single-decision-point assumption.

### Tests
- `scripts/tests/test_issue_parser.py` — `TestUnappliedDecision` and
  `TestUnappliedDecisionLiveCorpusSweep`

### Documentation
- N/A

### Configuration
- N/A

## Program Design

### Types

- `OptionSpan: tuple[int, int, str]` — alias for the span tuples
  `_option_block_spans()` already returns; no new type.

### Signatures

- `_unapplied_decision_pairs(content: str) -> list[tuple[str, str]]` — unchanged
  signature; internal grouping logic changes only.
- `_group_option_blocks_by_decision_point(spans: list[OptionSpan], body: str) -> list[list[OptionSpan]]`
  (new helper) — partitions `_option_block_spans()`'s flat span list into one
  group per `> **Selected:**` callout (or decision-separator boundary).

### Call Path

`check_format_gaps()` -> `_unapplied_decision_pairs()` -> `_option_block_spans()`
(existing) -> `_group_option_blocks_by_decision_point()` (new) -> per-group
`_selected_option_title()` + `matching`/`rej_ids` resolution -> union of
per-group `rej_ids` minus union of `sel_ids` -> the function's
`list[tuple[str, str]]` return.

## Implementation Steps

1. Add `_group_option_blocks_by_decision_point()` to partition
   `_option_block_spans()`'s flat span list by decision point.
   > ⚠ Superseded — no such helper exists; see § Codebase Research Findings under Proposed Solution
2. Rewrite `_unapplied_decision_pairs()` to resolve `sel_ids`/`rej_ids` per
   group instead of globally, unioning `rej_ids` across groups.
3. Add a regression test built from `FEAT-3409`'s four-decision-point
   structure (or equivalent) asserting zero false positives on its resolved
   decisions while still catching a genuine unapplied-rejected-option case.
4. Confirm `TestUnappliedDecisionLiveCorpusSweep` (single-decision-point
   corpus) is unchanged.
5. Run `python -m pytest scripts/tests/test_issue_parser.py` and verify.

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

## Steps to Reproduce

1. Take an issue whose `## Proposed Solution` has 2+ independent decision
   points, each with its own `> **Selected:**` callout — e.g.
   `.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`,
   which has four:
   1. Malformed-manifest posture — Selected: **Option C**
   2. `db_path` derivation — Selected: **Option A** (identifiers include
      `history.db_path`, `resolve_history_db(root=member.repo_path)`, `root=`)
   3. Config registration path — Selected: **Option A**, nest under
      `history.workspace_manifest_path` (identifiers include
      `history.workspace_manifest_path`, `HistoryConfig`, `manifest_path`,
      `config/features.py:1513-1554`)
   4. Default `manifest_path` resolution — Selected: **Option B**,
      subsequently revised (identifiers include `decisions.py::_resolve_path()`,
      `root=`)
2. Run `ll-issues format-check FEAT-3409 --format json` (or call
   `_unapplied_decision_pairs()` directly against the file's content).
3. Observe: it reports 26 `unapplied_decision` entries, every one naming an
   identifier from decision 2, 3, or 4's blocks — none from decision 1's own
   rejected options (A/B) — because the first callout matched is decision 1's
   ("Option C"), so decisions 2-4's blocks (both their selected *and* rejected
   halves) are indiscriminately folded into `rej_ids`. `history.workspace_manifest_path`
   and `HistoryConfig` are decision 3's own **selected** identifiers, flagged
   as "rejected option" — a false positive.

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


## Session Log
- `/ll:refine-issue` - 2026-09-09T00:12:26 - `f7f97d9e-bdab-4b75-991a-0e213908b8e5.jsonl`
- `/ll:format-issue` - 2026-09-09T00:00:47 - `6ecd89df-4783-49de-a06a-67b0f2e61709.jsonl`
