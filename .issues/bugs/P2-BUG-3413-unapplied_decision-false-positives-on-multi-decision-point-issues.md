---
id: BUG-3413
type: BUG
title: unapplied_decision false-positives on multi-decision-point issues
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T22:42:47Z'
completed_at: '2026-09-09T00:15:16Z'
confidence_score: 100
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 23
supersedes:
- BUG-3414
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
(4 decision points in `## Proposed Solution`) during a `/ll:confidence-check FEAT-3409`
run: `HistoryConfig`, the winning Option A identifier for that issue's 3rd decision
point ("Config registration path"), was flagged as a leftover rejected-option mention
purely because it wasn't part of decision point 1's winning block ("Malformed-manifest
posture", Option C).

The same single-decision assumption has a sibling **false-negative** mode: when the
first callout's option label (e.g. "Option A") also heads a block in a later decision
point, `len(matching) != 1` aborts the whole function and returns `[]`, silently
disabling the detector for that issue. Corpus scan (2026-09-08): 15 issues besides
FEAT-3409 carry 2+ `> **Selected:**` callouts in `## Proposed Solution`; most of them
hit this silent-off mode today (see Corpus Impact).

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

Two observable failure modes, depending on whether the first callout's label repeats:

- **False positive** (label unique across the section): FEAT-3409 (26 pairs, 5 of
  them winning identifiers of decision points 2-4), FEAT-2478 (7 pairs; Decision 2's
  winner Option D treated as rejected).
- **Silent false negative** (label repeats, `len(matching) != 1` → `[]`): FEAT-2878,
  FEAT-3078, FEAT-2598, ENH-2888 (labels restart A,B,A,B per decision point) and
  ENH-2463 (7 callouts, labels A1/A2, B1/B2, ...). The detector is off for these
  issues and `/ll:confidence-check` Criterion C credits them as clean.

## Expected Behavior

`_unapplied_decision_pairs()` groups option blocks by decision point, resolves a
`sel_ids`/`rej_ids` pair independently per group, and unions the resulting
`discriminating` identifiers across groups — so a winning option's identifiers from
decision point N are never treated as "rejected" leftovers just because they weren't
decision point 1's winner, and a repeated option label in a later decision point no
longer switches the detector off for the whole issue.

A group boundary between two consecutive option spans is any of:

1. a `**Decision point:**` marker (`_DECISION_POINT_MARKER_RE`, BUG-3412) between them;
2. a non-option markdown heading (any depth, fence-excluded) between them — the
   `#### Decision N — ...` shape (FEAT-2478, FEAT-2598) and the `### <topic>` shape
   (ENH-2463);
3. an option-label restart — the next span's `_option_label()` is already present in
   the current group (the bare A,B,A,B shape with no delimiter at all: FEAT-2878,
   ENH-2888, FEAT-3078).

Markers at or past `### Decision Rationale` (`dr_start`) are ignored — FEAT-3409
carries three bold `**Decision point: X**` lines inside its Decision Rationale that
match the marker regex. A section with no boundary yields one group, so
single-decision-point issues keep byte-identical output.

Per group: the group's own first `> **Selected:**` callout names the winner; a group
with no callout, or whose label matches 0 or 2+ spans *within that group*, contributes
nothing (it does not abort the other groups). The final set additionally subtracts
the union of every group's `sel_ids`, so an identifier rejected in decision point 1
but chosen in decision point 3 is never reported.

## Motivation

- `_unapplied_decision_pairs()` feeds `format-check`'s `unapplied_decision`/
  `DECISION_GAP` field, which `/ll:confidence-check`'s Criterion C scoring reads
  directly — a false positive here silently lowers an otherwise-ready issue's
  readiness score and produces spurious "leftover rejected option" findings a
  reviewer has to manually dismiss.
- ENH-3256 established per-decision-point authoring (`**Decision point:**`
  markers, one `Selected` callout per point) as the multi-option convention;
  BUG-3412 confirms the pattern is already in active use. Any issue authored
  with 2+ decision points in `## Proposed Solution` hits one of the two failure
  modes; 16 corpus issues do so today (2 false-positive, the rest silently off),
  and the blast radius grows with adoption of that convention.

## Proposed Solution

Group `_option_block_spans()`'s flat span list by decision point before computing
`sel_ids`/`rej_ids`, reusing BUG-3412's `_decision_point_marker_positions()` /
`_DECISION_POINT_MARKER_RE` primitives (`scripts/little_loops/issue_parser.py:2272`,
`:2797`) for boundary rule 1 and adding the heading and label-restart rules:

1. In `_unapplied_decision_pairs()`, after `spans = _option_block_spans(proposed_body)`,
   partition `spans` into groups with a new `_group_spans_by_decision_point()` helper.
   A new group starts at span *i* when, between `spans[i-1]` and `spans[i]`, there is
   a fence-excluded `**Decision point:**` marker or a non-option heading line, or when
   `_option_label(spans[i].heading)` is already present in the current group. Compute
   `fences = fence_spans(proposed_body)` locally (the helper needs it and
   `_option_block_spans()` does not expose its own). Only markers/headings before
   `dr_start` count.
2. Clamp each group's last span at the next group's leading marker/heading line, the
   same `next_marker < next_start` clamp `_decision_groups_in_body()` applies at
   `issue_parser.py:2872-2874`. Without it, group N's last span absorbs group N+1's
   `**Decision point:** ... \`ident\`` line (on FEAT-3409, span 640-1026 contains the
   marker at 983) and that line's backticked identifiers leak into group N's ids. On
   FEAT-3409 the leak is masked only because those identifiers also appear in
   `## Summary` (BUG-3289 shared-subject exclusion); the clamp makes it structurally
   impossible.
3. For each group independently: take the group's own first `> **Selected:**` callout
   (searched within the group's region, not the whole section), match its label to the
   one span in *that group*, and compute `sel_ids`/`rej_ids` scoped to the group. Keep
   the per-block own-callout-line masking and the BUG-3295 containment exclusion per
   group. A group with no callout, or with 0 or 2+ label matches, is skipped — not a
   whole-function `return []`. Keep the existing BUG-3279 last-block callout-line trim
   per group's last span.
4. Union each group's `(rej_ids - subsumed)` set across groups, then subtract the union
   of every group's `sel_ids` and the BUG-3289 `shared_ids` (computed once, as now).
   The `subsumed → sel_ids → shared_ids` ordering is preserved.
5. Groups with < 2 option spans contribute nothing, matching the existing
   whole-function `len(spans) < 2` early return. A section with no boundary is one
   group: the single-decision-point path must be byte-identical to today's output.

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
- `scripts/tests/test_issue_parser.py` — in `TestUnappliedDecision` (via its
  `_issue()` helper), add one case per corpus boundary shape, each asserting the
  winning identifiers of decision point 2+ are absent AND a genuinely rejected
  identifier from decision point 2+ still fires when a directive section names it
  (this second half is the false-negative regression guard):
  - marker-delimited, 4 decision points (FEAT-3409 shape, first label unique);
  - `#### Decision N — ...` heading-delimited (FEAT-2478 shape, labels A,B,C,D
    continue across points — exercises boundary rule 2 alone);
  - undelimited label restart A,B,A,B (FEAT-2878 shape — exercises rule 3 alone;
    today returns `[]` via `len(matching) != 1`);
  - letter-prefixed labels A1,A2,B1,B2 (ENH-2463 shape);
  - marker-line identifier leak (rule-2 clamp): a `**Decision point:** \`leaky\``
    line whose `leaky` is NOT in title/Summary must not be reported.
  - single-decision-point fixtures already in the class must pass unchanged.
- `scripts/tests/test_ll_issues_format_check.py` — add `unapplied_decision` /
  `unapplied_decision_detail` field coverage for one multi-decision-point fixture.
- `scripts/tests/test_decide_issue_skill.py` — `TestPhase7cFixtures` (lines 264-330)
  imports `_unapplied_decision_pairs()` directly against golden fixtures under
  `scripts/tests/fixtures/issues/`; all 5 existing fixtures are single-decision-point.
  Add a multi-decision-point golden fixture (FEAT-3409 shape, 4 decision points) and
  a case asserting decision-point 2+'s winning identifiers are absent — this is the
  `/ll:decide-issue` Phase 7c `unapplied_decision_detail` consumption path.
- Corpus differential (same style as `TestBug3295ContainmentCorpusDifferential`):
  the fix changes output on 16 live issues — it removes pairs on FEAT-3409/FEAT-2478
  and *adds* pairs on the previously silent issues, which will lower their Criterion
  C scores. Record before/after pair counts per affected issue in this issue's
  Session Log and assert no single-callout issue's output changes.
- `scripts/tests/test_confidence_check_skill.py` — no functional Criterion C scoring
  test exists there (its `unapplied_decision` tests only check that `SKILL.md` /
  `rubric.md` document the cap). Not touched; the detector-level assertions above
  are the verification.

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

### Deviations

- 2026-09-08 — `_group_spans_by_decision_point()` was implemented without the
  spec'd `body: str` parameter: it only needs `spans` (already offset-carrying)
  and `boundary_positions` to partition and clamp, so `body` was unused dead
  weight. Signature is
  `_group_spans_by_decision_point(spans: list[tuple[int, int, str]], boundary_positions: list[int]) -> list[list[tuple[int, int, str]]]`.
- 2026-09-08 — one addition beyond the spec'd per-group `_selected_option_title()`
  scoping: the *first* group's title-search region starts at offset 0 (the
  whole `## Proposed Solution` body), not its own first option span's start.
  Corpus differential surfaced a real single-decision-point shape (e.g.
  BUG-2731) where the `> **Selected:**` callout is written in prose *before*
  either option block (a `### Codebase Research Findings` summary of an
  already-made decision) — scoping group 0's search to `[group[0][0], ...)`
  as originally planned would miss that callout and silently drop all of
  that file's genuine reports, violating the "single-decision-point issues
  keep byte-identical output" requirement. Later groups still start their
  region at their own first span, matching the original design.

- No new types; existing `list[tuple[int, int, str]]` span tuples
  (`_option_block_spans()`'s return type) and `list[int]` marker positions
  (`_decision_point_marker_positions()`'s return type) are reused as-is.

### Signatures

- `_unapplied_decision_pairs(content: str) -> list[tuple[str, str]]` — unchanged
  signature; internal grouping logic changes only.
- `_group_spans_by_decision_point(body: str, spans: list[tuple[int, int, str]], boundary_positions: list[int]) -> list[list[tuple[int, int, str]]]`
  (new helper) — partitions `_option_block_spans()`'s flat span list into groups at
  `boundary_positions` (sorted, fence-excluded offsets of `**Decision point:**`
  markers and non-option headings before `dr_start`) and at option-label restarts;
  clamps each group's last span at the next group's leading boundary line.
- `_decision_point_boundary_positions(body: str, fences: list[tuple[int, int]], limit: int) -> list[int]`
  (new helper, or inlined) — `_decision_point_marker_positions()` output merged with
  non-option heading offsets, filtered to `< limit` (`dr_start`).

### Call Path

`check_format_gaps()` -> `_unapplied_decision_pairs()` -> `_option_block_spans()`
(existing) -> `_decision_point_marker_positions()` (BUG-3412, reused) + heading scan
-> `_group_spans_by_decision_point()` (new) -> per-group `_selected_option_title()`
on the group region + `_decision_identifiers()` (existing) -> union of per-group
`(rej - subsumed)` minus union of `sel_ids` minus `shared_ids` -> the function's
`list[tuple[str, str]]` return.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `_decision_point_marker_positions(body: str, fences: list[tuple[int, int]]) -> list[int]` (`issue_parser.py:2797`) requires a `fences` argument the caller must compute itself — `_decision_groups_in_body()` computes it locally via `fences = fence_spans(body)` (`issue_parser.py:2834`) immediately before use; `_unapplied_decision_pairs()` does not currently hold a `fences` value (its only fence-aware step happens inside `_option_block_spans()`, which computes its own `fences = fence_spans(text)` internally at `issue_parser.py:1513` and does not expose it). Any reuse of `_decision_point_marker_positions()` needs an equivalent `fences = fence_spans(proposed_body)` call of its own.
- `_selected_option_title()` (`issue_parser.py:1402`) is a single `_SELECTED_CALLOUT_RE.search()` call — by construction it can return at most one title from the whole input string, with no per-decision-point segmentation. Its docstring (`issue_parser.py:1405-1409`) documents this first-occurrence behavior as intentional per ENH-3256 for the single-decision-point case, not as an oversight.
- `_option_block_spans()`'s return type `list[tuple[int, int, str]]` (`(start, end, heading_line)`) carries no group/tier/decision-point id in the tuple — grouping by decision point is not latent in the existing span data and requires comparing span start offsets against `_decision_point_marker_positions()` output as new logic.
- No function in `issue_parser.py` currently iterates decision-point groups and unions a per-group `set` result across groups. The one existing multi-group merge, `locate_unresolved_decisions()` (`issue_parser.py:3049`), merges via a list-comprehension filter (`[g for g in groups if not is_group_resolved(...)]`) over per-group booleans, not a set union. The file's only `set` union (`|=`) is the flat, non-grouped one inside `_unapplied_decision_pairs()` itself (`issue_parser.py:1629`) — the exact line this issue's fix changes from whole-section to per-group scope.
- `_decision_groups_in_body()`'s run-splitting technique (`issue_parser.py:2816-2862`, tag matches with tier name, sort by position, then bucket into runs by checking `[mp for mp in marker_positions if prev_pos < mp < pos]` between consecutive matches) uses plain list-comprehension range checks, not `bisect` — there is no `bisect` import or usage anywhere in `issue_parser.py`.

## Implementation Steps

1. Add `_group_spans_by_decision_point()` (plus the boundary-position helper) that
   partitions `_option_block_spans()`'s flat span list into per-decision-point groups
   on the three boundary rules (marker, non-option heading, label restart), ignores
   boundaries at or past `dr_start`, and clamps each group's last span at the next
   group's leading boundary line (mirroring `_decision_groups_in_body()`'s
   run-splitting and `next_marker` clamp).
2. Rewrite `_unapplied_decision_pairs()`'s body to resolve `sel_ids`/`rej_ids` per
   group instead of globally: per-group callout lookup, per-group `matching` check
   that skips the group rather than returning `[]`, per-group own-callout masking,
   last-block trim, and BUG-3295 containment.
3. Union each group's `(rej_ids - subsumed)` into one set, subtract the union of all
   groups' `sel_ids`, then subtract `shared_ids` (BUG-3289), then run the existing
   scrub + directive-section scan unchanged.
4. Add the regression tests listed under Integration Map › Tests (one per corpus
   boundary shape, plus the leak-clamp case and the Phase 7c golden fixture).
   Acceptance on the FEAT-3409 reproducer is **not** an empty list — genuinely
   rejected identifiers that directive sections still name (e.g. `('Files to Modify',
   'config/core.py')` from a "no change needed to `config/core.py`" sentence) remain
   and are a separate, pre-existing detector limitation. Assert instead that none of
   `HistoryConfig`, `manifest_path`, `history.db_path`,
   `history.workspace_manifest_path`, `workspace` appear in any returned pair.
5. Run the corpus differential over `.issues/**/*.md`: exactly the 16 multi-callout
   issues change output, no single-callout issue changes. Record per-issue
   before/after counts in the Session Log.
6. Run `python -m pytest scripts/tests/test_issue_parser.py
   scripts/tests/test_ll_issues_format_check.py scripts/tests/test_decide_issue_skill.py`
   and confirm existing single-decision-point cases pass unchanged.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a multi-decision-point golden fixture under `scripts/tests/fixtures/issues/`
  and a corresponding case in `scripts/tests/test_decide_issue_skill.py`'s
  `TestPhase7cFixtures` — asserts decision-point 2+'s winning identifiers are
  absent from `_unapplied_decision_pairs()`'s output via the `/ll:decide-issue`
  Phase 7c consumption path (`unapplied_decision_detail`), not just
  format-check's formatter path already covered by `test_issue_parser.py`.
- `test_confidence_check_skill.py` is out of scope (no functional Criterion C
  scoring test exists there); verification is the detector-level assertions in
  `test_issue_parser.py` / `test_ll_issues_format_check.py`.

## Impact

- **Priority**: P2 — 16 live corpus issues affected (2 false-positive, 14 with the
  detector silently off), corrupting `/ll:confidence-check` Criterion C scoring in
  both directions, and the triggering pattern (multi-decision-point authoring) is an
  actively growing convention (ENH-3256).
- **Effort**: Small-to-medium — reuses BUG-3412's marker-detection primitives; adds
  two boundary rules (heading, label restart) and a span clamp inside one function's
  grouping logic, no new external dependencies or API surface. Most of the effort is
  the per-shape fixtures and the corpus differential.
- **Risk**: Low-to-medium — internal parser helper with no public API; existing
  single-decision-point behavior must stay byte-identical (`_unapplied_decision()`'s
  reason-string format is a preserved contract per its own docstring). The
  previously silent issues will start reporting pairs, so their confidence scores
  may drop; that is the intended correction, but it must be measured, not assumed.
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
pairs = _unapplied_decision_pairs(content)
# 26 pairs at 2026-09-08 (count drifts as FEAT-3409 is edited; the shape is what
# matters). Includes ('Implementation Steps', 'HistoryConfig') and
# ('Program Design', 'manifest_path') — HistoryConfig is decision point 3's
# WINNING identifier, not a rejected-option leftover.
assert any(ident == "HistoryConfig" for _, ident in pairs)
```

False-negative reproducer (label repeats across decision points):

```python
from little_loops.issue_parser import _unapplied_decision_pairs
content = open(".issues/features/P1-FEAT-2878-trace-level-assertions-in-the-eval-harness-with-optional-multi-host-divergence-runs.md").read()
print(_unapplied_decision_pairs(content))  # [] — 3 decision points, all "Option A" winners;
# `len(matching) != 1` aborts before any identifier is compared.
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
5. Or, when that one label heads a block in 2+ decision points (`len(matching) != 1`,
   `issue_parser.py:1621`), returns `[]` for the whole issue — the silent-off mode.

Reproducers: see Steps to Reproduce.

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

BUG-3412's fix (committed as `e9417d1f7`) adds `_DECISION_POINT_MARKER_RE` /
`_decision_point_marker_positions()` to detect `**Decision point:**` prose/heading
boundaries. This issue reuses those primitives for boundary rule 1 and adds the
heading and label-restart rules the marker regex does not cover.

## Corpus Impact

Scripted scan of `.issues/**/*.md` (2026-09-08, counting `> **Selected:**` callouts
before `### Decision Rationale` in `## Proposed Solution`): 16 issues carry 2+
callouts. FEAT-3409 is the only one that also uses `**Decision point:**` markers, so
a marker-only grouping would fix exactly one issue — hence boundary rules 2 and 3.

| Issue | Callouts | Delimiter between decision points | Today |
|---|---|---|---|
| FEAT-3409 | 4 | `**Decision point:**` markers | 26 pairs, false positives |
| FEAT-2478 | 2 | `#### Decision N — ...` headings, labels A,B,C,D | 7 pairs, false positives |
| FEAT-2598 | 2 | `#### Decision N` headings, labels A,B,A,B | `[]` (silent) |
| FEAT-3078 | 2 | `###` topic headings, labels A,B,A,B,C | `[]` (silent) |
| FEAT-2878 | 3 | none, labels A,B,A,B,A,B | `[]` (silent) |
| ENH-2888 | 2 | none, labels A,B,A,B | `[]` (silent) |
| ENH-2463 | 7 | letter-prefixed labels A1,A2,B1..,C1.. | `[]` (silent) |
| 9 others | 2 each | mixed; several have 0-3 option spans (callout used as a cross-reference) | `[]` |

The bug will recur for any future issue authored with multiple decision points in one
section — an increasingly common convention per ENH-3256's per-decision-point
authoring pattern.

### Measured Results (implementation, 2026-09-08)

Corpus differential re-run at fix time (`.issues/**/*.md`, all files) — the live
corpus drifted since the table above was authored (issues get edited continuously),
so file-level counts differ somewhat from the original scan, but the shape holds:
8 files changed output, zero single-decision-point (single-callout) file changed,
total report count 535 → 562 (net +27, consistent with this fix both removing
false positives and un-silencing previously-off files):

| Issue | Before | After |
|---|---|---|
| FEAT-3409 | 26 | 9 |
| FEAT-2478 | 7 | 6 |
| BUG-3331 | 0 | 1 |
| ENH-3346 | 0 | 25 |
| FEAT-2878 | 0 | 13 |
| FEAT-2598 | 0 | 2 |
| FEAT-3078 | 0 | 2 |
| FEAT-3335 | 0 | 2 |

`TestBug3295ContainmentCorpusDifferential`'s pre-existing report-count ceiling
test (`test_issue_parser.py`) was updated in step with this — its 525 pre-BUG-3295
ceiling no longer holds now that BUG-3413 legitimately widens the corpus total;
see that test's updated docstring for the new post-BUG-3413 ceiling (562).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented per Program Design (with two documented Deviations): added
`_decision_point_boundary_positions()` and `_group_spans_by_decision_point()`
to `scripts/little_loops/issue_parser.py`, and rewrote
`_unapplied_decision_pairs()` to resolve `sel_ids`/`rej_ids` per decision-point
group instead of globally, unioning `(rej_ids - subsumed)` per group before the
final `sel_ids`/`shared_ids` subtraction. Both reproducers from Steps to
Reproduce now behave as expected (`HistoryConfig` no longer flagged on
FEAT-3409; FEAT-2878 no longer silently returns `[]`). All 25 pre-existing
`TestUnappliedDecision` tests pass unchanged (single-decision-point path is
byte-identical). Added 5 new boundary-shape unit tests, a Phase 7c golden
fixture (`BUG-3413-fixture-multi-decision-point.md`), and a format-check field
test. Corpus differential and the updated `TestBug3295ContainmentCorpusDifferential`
ceiling are recorded under Corpus Impact › Measured Results. Full suite
(`python -m pytest scripts/tests/`): 23453 passed, 5 pre-existing unrelated
failures confirmed via `git stash` to already exist on the unmodified tree
(`TestPriorityRegexCompletenessAllowlist` x2, `test_host_runner`
`TestAC8BaselineCoverage`, `test_cli_harness` `TestReadTargetHistory`,
`test_verify_evidence` `TestRepoGate`) — zero new failures introduced.

## Status

**Done** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-09T00:14:32 - `6ecd89df-4783-49de-a06a-67b0f2e61709.jsonl`
- `/ll:ready-issue` - 2026-09-08T23:50:48 - `8bf772bc-0685-4c2b-b977-3c8982a6fc9d.jsonl`
- `/ll:confidence-check` - 2026-09-08T23:46:28 - `e4f9d0c3-b434-4a60-a8a9-bb40fcc5c75a.jsonl`
- `/ll:confidence-check` - 2026-09-08T23:19:30 - `6c87a100-fdff-4f6c-8c02-661175f66952.jsonl`
- `/ll:wire-issue` - 2026-09-08T23:16:35 - `5525351e-3d29-48e7-8627-a2102c2d6ce0.jsonl`
- `/ll:refine-issue` - 2026-09-08T23:07:32 - `4eafacf3-ae84-4013-9a60-e7cb82f6fe90.jsonl`
- `/ll:format-issue` - 2026-09-08T22:58:53 - `e2e838a6-6a34-4a2d-913f-3f74b4596a32.jsonl`
- `/ll:capture-issue` - 2026-09-08T22:42:53 - `4f0efb73-1906-4514-9695-1db0defa8ce3.jsonl`
