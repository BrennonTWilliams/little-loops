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

`_unapplied_decision_pairs()` (`scripts/little_loops/issue_parser.py:1550`) matches
`_selected_option_title()`'s single, first-callout-only title against every option
span `_option_block_spans()` returns for the whole `## Proposed Solution` body, with
no per-decision-point grouping. On an issue with 2+ decision points, every option
block outside the one matching that first title's label — including the *winning*
options of decision points 2, 3, ... — lands in `rej_ids`, so their identifiers get
reported as leftover rejected-option mentions (`unapplied_decision`/`DECISION_GAP`)
even where they are the section's own selected content. Confirmed via the
`_unapplied_decision_pairs()` reproducer above: `HistoryConfig`, decision point 3's
winning identifier on FEAT-3409, was flagged as a rejected-option leftover.

## Expected Behavior

`_unapplied_decision_pairs()` groups option blocks by decision point (splitting on the
same `**Decision point:**` marker boundary BUG-3412 uses), resolves a `sel_ids`/
`rej_ids` pair independently per group, and unions the resulting `discriminating`
identifiers across groups — so a winning option's identifiers from decision point N
are never treated as "rejected" leftovers just because they weren't decision point 1's
winner.

## Motivation

- `_unapplied_decision_pairs()` feeds `format-check`'s `unapplied_decision`/
  `DECISION_GAP` field, which `/ll:confidence-check`'s Criterion C scoring reads
  directly — a false positive here silently lowers an otherwise-ready issue's
  readiness score and produces spurious "leftover rejected option" findings a
  reviewer has to manually dismiss.
- ENH-3256 established per-decision-point authoring (`**Decision point:**`
  markers, one `Selected` callout per point) as the multi-option convention;
  BUG-3412 confirms the pattern is already in active use. Any issue authored
  with 2+ decision points in `## Proposed Solution` hits this false positive,
  so the blast radius grows with adoption of that convention even though only
  one corpus issue (FEAT-3409) trips it today.

## Proposed Solution

Reuse BUG-3412's `_decision_point_marker_positions()` /
`_DECISION_POINT_MARKER_RE` primitives (`scripts/little_loops/issue_parser.py:2272`,
`:2797`) to group `_option_block_spans()`'s flat span list by decision point before
computing `sel_ids`/`rej_ids`:

1. In `_unapplied_decision_pairs()`, after `spans = _option_block_spans(proposed_body)`,
   partition `spans` into per-decision-point groups using the same marker-position
   boundaries `_decision_groups_in_body()` already uses to split same-tier runs.
2. For each group independently: find its own `_selected_option_title()`-equivalent
   (the group's own `> **Selected:**` callout), match it to the one span in *that
   group* whose heading label matches, and compute `sel_ids`/`rej_ids` scoped to the
   group (keeping the existing BUG-3295 containment and BUG-3289 shared-subject
   exclusions, applied per group).
3. Union each group's `discriminating` (rej_ids - sel_ids, minus exclusions) set
   across groups into the function's final return value.
4. Groups with < 2 option spans (a single-decision-point group) short-circuit to
   `[]` for that group, matching the existing whole-function early return.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_unapplied_decision_pairs()` (line 1550)
  gains per-group scoping; likely factor `_decision_point_marker_positions()`-based
  grouping into a small shared helper alongside `_decision_groups_in_body()`.

### Dependent Files (Callers/Importers)
- `grep -rn "_unapplied_decision_pairs\|unapplied_decision" scripts/little_loops/` —
  `_unapplied_decision_reasons()` (`issue_parser.py:1541`, a thin formatter over this
  function) and `format-check`'s `unapplied_decision` field consumer are the direct
  callers; both must keep their existing reason-string / field format for
  single-decision-point issues (regression risk, not intentional scope).

### Similar Patterns
- `_decision_groups_in_body()` (`issue_parser.py:2816`) already solves the identical
  "group by decision-point marker, don't conflate same-tier runs" problem for
  `is_group_resolved()` / `ll-issues check-unresolved-decisions` (BUG-3412) — model
  the grouping logic after it rather than reinventing marker-boundary splitting.

### Tests
- `scripts/tests/test_issue_parser.py` — add a multi-decision-point
  `_unapplied_decision_pairs()` case (winning identifiers of decision point 2+ must
  not appear in the result).
- `scripts/tests/test_ll_issues_format_check.py` — add/adjust `unapplied_decision`
  field coverage for a multi-decision-point fixture.
- `scripts/tests/test_confidence_check_skill.py` — verify Criterion C no longer
  penalizes a multi-decision-point issue for its own winning identifiers.

### Documentation
- N/A — no public API or docs surface changes; internal parser fix only.

### Configuration
- N/A

## Program Design

### Types

- No new types; existing `list[tuple[int, int, str]]` span tuples
  (`_option_block_spans()`'s return type) and `list[int]` marker positions
  (`_decision_point_marker_positions()`'s return type) are reused as-is.

### Signatures

- `_unapplied_decision_pairs(content: str) -> list[tuple[str, str]]` — unchanged
  signature; internal grouping logic changes only.
- `_group_spans_by_decision_point(spans: list[tuple[int, int, str]], marker_positions: list[int]) -> list[list[tuple[int, int, str]]]`
  (new helper, or inlined equivalent) — partitions `_option_block_spans()`'s flat
  span list at `_decision_point_marker_positions()` boundaries.

### Call Path

`check_format_gaps()` -> `_unapplied_decision_pairs()` -> `_option_block_spans()`
(existing) -> `_decision_point_marker_positions()` (BUG-3412, reused) -> new
grouping step -> per-group `_selected_option_title()` + `_decision_identifiers()`
(existing) -> union into the function's `list[tuple[str, str]]` return.

## Implementation Steps

1. Add a helper that partitions `_option_block_spans()`'s flat span list into
   per-decision-point groups using `_decision_point_marker_positions()` boundaries
   (mirroring `_decision_groups_in_body()`'s run-splitting logic).
2. Rewrite `_unapplied_decision_pairs()`'s body to resolve `sel_ids`/`rej_ids` per
   group instead of globally, preserving the BUG-3295/BUG-3289 exclusions and the
   last-block callout-line trimming per group.
3. Union each group's `discriminating` identifiers into the final return value.
4. Add multi-decision-point regression tests (`test_issue_parser.py`,
   `test_ll_issues_format_check.py`) using a fixture shaped like FEAT-3409's 3
   decision points; verify the `_unapplied_decision_pairs()` reproducer above now
   returns `[]` for `HistoryConfig`/`manifest_path`.
5. Run `python -m pytest scripts/tests/test_issue_parser.py
   scripts/tests/test_ll_issues_format_check.py
   scripts/tests/test_confidence_check_skill.py` and confirm existing
   single-decision-point cases still pass unchanged.

## Impact

- **Priority**: P2 — narrow live blast radius today (one corpus issue), but silently
  corrupts `/ll:confidence-check` Criterion C scoring wherever it does trigger, and
  the triggering pattern (multi-decision-point authoring) is an actively growing
  convention (ENH-3256).
- **Effort**: Small — reuses BUG-3412's marker-detection primitives directly; the
  change is scoped to one function's internal grouping logic with no new external
  dependencies or API surface.
- **Risk**: Low — internal parser helper with no public API; existing
  single-decision-point behavior must stay byte-identical (`_unapplied_decision_reasons()`'s
  reason-string format is a preserved contract per its own docstring).
- **Breaking Change**: No.

## Steps to Reproduce

1. Take an issue whose `## Proposed Solution` section has 2+ independent decision
   points, each with its own `**Option A/B(/C)**` blocks and its own
   `> **Selected:**` callout (e.g.
   `.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`).
2. Run the reproducer below against that file's content.
3. Observe: identifiers belonging to decision point 2's (or 3's, ...) *winning*
   option — never decision point 1's winner — appear in the returned pairs as if
   they were rejected-option leftovers.

```python
from little_loops.issue_parser import _unapplied_decision_pairs
content = open(".issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md").read()
print(_unapplied_decision_pairs(content))
# 22 pairs, including ('Implementation Steps', 'HistoryConfig') and
# ('Program Design', 'manifest_path') — HistoryConfig is decision point 3's
# WINNING identifier, not a rejected-option leftover.
```

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

At investigation time,
`.issues/features/P1-FEAT-3409-workspace-membership-discovery-for-cross-repo-history-db-aggregation.md`
is the only issue in the
corpus with 2+ decision points in `## Proposed Solution` (verified via a scripted scan
of all `.issues/**/*.md`), so live blast radius is narrow today. The bug will recur
for any future issue authored with multiple decision points in one section — an
increasingly common convention per ENH-3256's per-decision-point authoring pattern.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-08T22:58:53 - `e2e838a6-6a34-4a2d-913f-3f74b4596a32.jsonl`
- `/ll:capture-issue` - 2026-09-08T22:42:53 - `4f0efb73-1906-4514-9695-1db0defa8ce3.jsonl`
