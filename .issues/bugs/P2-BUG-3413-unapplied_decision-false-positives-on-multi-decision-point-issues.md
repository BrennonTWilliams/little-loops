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
  > ⚠ Superseded — no functional scoring test exists in this file today

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decide_issue_skill.py` — `TestPhase7cFixtures` (lines 264-330)
  imports `_unapplied_decision_pairs()` directly against golden fixtures under
  `scripts/tests/fixtures/issues/` (`ENH-3280-fixture-*.md`,
  `ENH-3277-pre-repair-reproducer.md`); all 5 existing fixtures are
  single-decision-point (confirmed: none contain a second `**Decision point:**`
  marker or `> **Selected:**` callout). This exercises `/ll:decide-issue` Phase 7c's
  `unapplied_decision_detail` consumption path — structurally separate from
  `TestUnappliedDecision`'s formatted-reason-string assertions — and was not in this
  issue's original test plan. Add a new multi-decision-point golden fixture here
  (shaped like FEAT-3409's 3 decision points) asserting decision-point 2+'s winning
  identifiers are absent from the result. [Agent 3 finding]
- `scripts/tests/test_confidence_check_skill.py` — confirmed this file has **no**
  functional test invoking `_unapplied_decision_pairs`/`_unapplied_decision` or
  feeding real issue content through Criterion C scoring; its existing
  `unapplied_decision`-related tests (~lines 582-645) only assert that
  `SKILL.md`/`rubric.md` *document* the cap, not that the detector's output is
  correctly scored. The line above ("verify Criterion C no longer penalizes...")
  does not map onto any existing runnable assertion here — it requires writing new
  content-driven coverage, not "adjusting" existing coverage. [Agent 3 finding]

### Documentation
- N/A — no public API or docs surface changes; internal parser fix only.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `TestUnappliedDecision` (`scripts/tests/test_issue_parser.py:5228-5610`) is the class covering `_unapplied_decision_pairs()`'s formatter, `_unapplied_decision()`. Every test in it builds its fixture through a shared helper, `_issue(self, proposed_solution: str, **directive_sections: str)` (`test_issue_parser.py:5236-5241`), which takes the `## Proposed Solution` body as a positional string and any number of directive-section bodies as keyword args (underscores become spaces in the heading). Every test imports `_unapplied_decision` inline inside the test method body, not at module top, and asserts either `== []` or `any(<section> in r and <identifier> in r for r in reasons)` against the formatted reason strings — no existing test in this class imports `_unapplied_decision_pairs` directly or passes `_issue()` a `proposed_solution` containing more than one `**Decision point:**` marker or more than one `> **Selected:**` callout.
- BUG-3412's own multi-decision-point fixtures live in a *different* file and class: `TestDecisionGroups` in `scripts/tests/test_issue_parser_unresolved.py` (e.g. `test_bold_decision_point_marker_splits_a_same_tier_run`, line 1323) — built as inline string-literal concatenation with inline imports, asserting directly against `_iter_decision_groups()`/`is_group_resolved()`/`locate_unresolved_decisions()` return values rather than formatted reason strings. This is a separate fixture convention from `TestUnappliedDecision`'s `_issue()` helper.
- `TestPhase7cFixtures` (`scripts/tests/test_decide_issue_skill.py:264-330`) is the one place in the test suite that imports `_unapplied_decision_pairs()` directly (not the `_unapplied_decision()` formatter), against golden fixture files under `scripts/tests/fixtures/issues/` (e.g. `ENH-3280-fixture-recommendation-marker.md`) — a third, separate fixture convention (external golden files rather than inline content).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `_decision_point_marker_positions(body: str, fences: list[tuple[int, int]]) -> list[int]` (`issue_parser.py:2797`) requires a `fences` argument the caller must compute itself — `_decision_groups_in_body()` computes it locally via `fences = fence_spans(body)` (`issue_parser.py:2834`) immediately before use; `_unapplied_decision_pairs()` does not currently hold a `fences` value (its only fence-aware step happens inside `_option_block_spans()`, which computes its own `fences = fence_spans(text)` internally at `issue_parser.py:1513` and does not expose it). Any reuse of `_decision_point_marker_positions()` needs an equivalent `fences = fence_spans(proposed_body)` call of its own.
- `_selected_option_title()` (`issue_parser.py:1402`) is a single `_SELECTED_CALLOUT_RE.search()` call — by construction it can return at most one title from the whole input string, with no per-decision-point segmentation. Its docstring (`issue_parser.py:1405-1409`) documents this first-occurrence behavior as intentional per ENH-3256 for the single-decision-point case, not as an oversight.
- `_option_block_spans()`'s return type `list[tuple[int, int, str]]` (`(start, end, heading_line)`) carries no group/tier/decision-point id in the tuple — grouping by decision point is not latent in the existing span data and requires comparing span start offsets against `_decision_point_marker_positions()` output as new logic.
- No function in `issue_parser.py` currently iterates decision-point groups and unions a per-group `set` result across groups. The one existing multi-group merge, `locate_unresolved_decisions()` (`issue_parser.py:3049`), merges via a list-comprehension filter (`[g for g in groups if not is_group_resolved(...)]`) over per-group booleans, not a set union. The file's only `set` union (`|=`) is the flat, non-grouped one inside `_unapplied_decision_pairs()` itself (`issue_parser.py:1629`) — the exact line this issue's fix changes from whole-section to per-group scope.
- `_decision_groups_in_body()`'s run-splitting technique (`issue_parser.py:2816-2862`, tag matches with tier name, sort by position, then bucket into runs by checking `[mp for mp in marker_positions if prev_pos < mp < pos]` between consecutive matches) uses plain list-comprehension range checks, not `bisect` — there is no `bisect` import or usage anywhere in `issue_parser.py`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Precise anchors for the steps a per-group rewrite must preserve, in call order (`_unapplied_decision_pairs()`, `issue_parser.py:1550-1691`):
  1. Last-block trailing-prose trim (`issue_parser.py:1587-1592`) — if the *last* option span contains a `> **Selected:**` callout, the span end is clamped to that callout line's end so free-form rationale prose after the winner's callout does not leak into REJ (comment at `issue_parser.py:1578-1586`, BUG-3279).
  2. Per-block own-callout-line masking (`issue_parser.py:1603-1611`) — each span's own `> **Selected:**` line (if present) is stripped from that block's text before identifier extraction, so a rejected block's cross-reference callout does not leak the winner's identifiers into that block.
  3. `sel_ids`/`rej_ids` split (`issue_parser.py:1625-1629`) — currently whole-section; this is the exact line where a second decision point's winning block is misclassified as rejected.
  4. BUG-3295 containment exclusion (`issue_parser.py:1631-1643`): `subsumed = {r for r in rej_ids if any(r in s for s in sel_ids)}` — one-directional (rejected-in-selected only).
  5. BUG-3289 shared-subject exclusion (`issue_parser.py:1644-1649`): `shared_ids = _shared_subject_identifiers(content)`, subtracted last: `discriminating = (rej_ids - subsumed) - sel_ids - shared_ids`. The comment at `issue_parser.py:1644-1647` states this ordering (`subsumed` → `sel_ids` → `shared_ids`) is intentional so shared-subject exclusion never masks the containment exclusion — this relative ordering must hold within each group, not just once globally.
  6. Self-scan scrub (`issue_parser.py:1660-1665`): `scrub_start = min(dr_start, spans[-1][1])`, all option spans up to `scrub_start` are deleted from a copy of `proposed_body` before directive-section scanning, so option blocks don't self-fire when `## Proposed Solution` is later scanned as a directive section.
- `_unapplied_decision_pairs()` has exactly two production callers: `check_format_gaps()` (`issue_parser.py:1177`) and `_unapplied_decision()` (`issue_parser.py:1538`, a thin formatter per its own docstring at `issue_parser.py:1541`, called at `:1546`) — confirmed via unfiltered repo-wide grep, no other production caller exists.

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
- `/ll:refine-issue` - 2026-09-08T23:07:32 - `4eafacf3-ae84-4013-9a60-e7cb82f6fe90.jsonl`
- `/ll:format-issue` - 2026-09-08T22:58:53 - `e2e838a6-6a34-4a2d-913f-3f74b4596a32.jsonl`
- `/ll:capture-issue` - 2026-09-08T22:42:53 - `4f0efb73-1906-4514-9695-1db0defa8ce3.jsonl`
